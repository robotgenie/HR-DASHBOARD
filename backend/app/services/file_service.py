"""Secure upload handling: validation, safe naming and path-traversal prevention.

Files are never served from a static directory. Every read goes through an
authenticated API endpoint that resolves the stored name against a fixed base
directory and rejects anything that escapes it.
"""
import base64
import binascii
import hashlib
import io
import mimetypes
import re
import secrets
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.utils.timeutil import utcnow
from app.core.config import settings

# Sub-folders inside UPLOAD_DIR
DOCUMENTS = "documents"
PHOTOS = "photos"
PAYSLIPS = "payslips"
REPORTS = "reports"
SELFIES = "selfies"

EXTENSION_MIME_MAP = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "webp": {"image/webp"},
    "doc": {"application/msword"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
}

# Leading bytes used to confirm the declared type actually matches the content.
MAGIC_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "webp": [b"RIFF"],
    "docx": [b"PK\x03\x04"],
    "doc": [b"\xd0\xcf\x11\xe0"],
}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def ensure_dirs() -> None:
    for sub in (DOCUMENTS, PHOTOS, PAYSLIPS, REPORTS, SELFIES):
        (settings.upload_path / sub).mkdir(parents=True, exist_ok=True)


def sanitise_filename(filename: str) -> str:
    """Strip directories, control characters and anything non-portable."""
    name = unicodedata.normalize("NFKD", filename or "")
    name = name.replace("\\", "/").split("/")[-1]
    name = name.replace("\x00", "")
    name = _SAFE_NAME.sub("_", name).strip("._")
    return name[:120] or "file"


def get_extension(filename: str) -> str:
    return Path(sanitise_filename(filename)).suffix.lower().lstrip(".")


def build_stored_name(prefix: str, original_filename: str) -> str:
    """Server-side name: caller-controlled text never reaches the filesystem path."""
    ext = get_extension(original_filename)
    stamp = utcnow().strftime("%Y%m%d%H%M%S")
    token = secrets.token_hex(8)
    safe_prefix = _SAFE_NAME.sub("_", prefix)[:40].strip("._") or "file"
    return f"{safe_prefix}_{stamp}_{token}.{ext}" if ext else f"{safe_prefix}_{stamp}_{token}"


# def resolve_path(subdir: str, stored_filename: str) -> Path:
#     """Resolve a stored file, guaranteeing it stays inside UPLOAD_DIR/subdir."""
#     base = (settings.upload_path / subdir).resolve()
#     candidate = (base / Path(stored_filename).name).resolve()
#     if not str(candidate).startswith(str(base) + "/") and candidate != base:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path."
#         )
#     return candidate


def resolve_path(subdir: str, stored_filename: str) -> Path:
    base = (settings.upload_path / subdir).resolve()
    candidate = (base / Path(stored_filename).name).resolve()

    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid file path.",
        )

    return candidate

async def validate_and_read(
    upload: UploadFile,
    allowed_extensions: Optional[Iterable[str]] = None,
    max_size: Optional[int] = None,
) -> Tuple[bytes, str, str, str]:
    """Validate an upload and return (content, extension, mime_type, sha256)."""
    if upload is None or not upload.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No file was provided."
        )

    allowed = {e.lower().lstrip(".") for e in (allowed_extensions or settings.allowed_extension_set)}
    limit = max_size or settings.MAX_FILE_SIZE

    ext = get_extension(upload.filename)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file needs an extension.",
        )
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{ext}' files aren't accepted here. Allowed: {', '.join(sorted(allowed))}.",
        )

    content = await upload.read()
    await upload.close()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The file is empty."
        )
    if len(content) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"The file is larger than the {limit // (1024 * 1024)} MB limit.",
        )

    declared = (upload.content_type or "").split(";")[0].strip().lower()
    expected = EXTENSION_MIME_MAP.get(ext, set())
    if declared and expected and declared not in expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file content type doesn't match its extension.",
        )

    signatures = MAGIC_SIGNATURES.get(ext)
    if signatures and not any(content.startswith(sig) for sig in signatures):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file contents don't look like a valid "
                   f"{ext.upper()} file.",
        )

    mime = declared or (mimetypes.guess_type(upload.filename)[0] or "application/octet-stream")
    return content, ext, mime, hashlib.sha256(content).hexdigest()


def save_bytes(subdir: str, stored_filename: str, content: bytes) -> Path:
    ensure_dirs()
    path = resolve_path(subdir, stored_filename)
    path.write_bytes(content)
    return path


def save_selfie_data_url(data_url: str, prefix: str) -> str:
    """Validate a browser-captured data URL and store a normalized JPEG selfie."""
    value = (data_url or "").strip()
    match = re.fullmatch(r"data:image/(?:jpeg|jpg|png);base64,([A-Za-z0-9+/=\s]+)", value, re.IGNORECASE)
    if not match:
        raise HTTPException(400, "Please provide a valid live selfie image.")

    try:
        raw = base64.b64decode(match.group(1), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "The selfie image could not be read.")

    if not raw or len(raw) > 2 * 1024 * 1024:
        raise HTTPException(413, "The selfie image must be smaller than 2 MB.")

    try:
        with Image.open(io.BytesIO(raw)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((720, 720), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=86, optimize=True)
            normalized = output.getvalue()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "The selfie image is invalid.")

    stored = build_stored_name(prefix, "selfie.jpg")
    save_bytes(SELFIES, stored, normalized)
    return stored


def delete_file(subdir: str, stored_filename: str) -> None:
    """Used only by HR-side cleanup paths; employee flows never call this."""
    path = resolve_path(subdir, stored_filename)
    if path.exists():
        path.unlink()

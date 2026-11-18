"""Electronic employee ID card generator.

Renders a CR80 (standard ID-card sized) PDF so the card can be printed
straight onto a badge, or downloaded and viewed as-is. Every value comes from
the employee record; nothing here is hard-coded except the company branding,
which comes from settings.
"""
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

from app.core.config import settings

# CR80 badge: 85.6mm x 54mm
CARD_W, CARD_H = 242.6, 153.0

# Brand palette, matching the frontend design tokens
BLUE = colors.HexColor("#547FFF")
INDIGO = colors.HexColor("#6E5CFF")
VIOLET = colors.HexColor("#A055FF")
INK = colors.HexColor("#151A38")
MUTED = colors.HexColor("#5B6385")
LINE = colors.HexColor("#E3E7F3")
WHITE = colors.white

BAND_H = 34.0
FOOTER_H = 15.0


def _blend(c1: colors.Color, c2: colors.Color, t: float) -> colors.Color:
    return colors.Color(
        c1.red + (c2.red - c1.red) * t,
        c1.green + (c2.green - c1.green) * t,
        c1.blue + (c2.blue - c1.blue) * t,
    )


def _gradient_band(c, x: float, y: float, w: float, h: float) -> None:
    """Blue -> indigo -> violet sweep, drawn as thin strips."""
    steps = 72
    step_w = w / steps
    for i in range(steps):
        t = i / (steps - 1)
        colour = _blend(BLUE, INDIGO, t * 2) if t < 0.5 else _blend(INDIGO, VIOLET, (t - 0.5) * 2)
        c.setFillColor(colour)
        # overlap by a hairline so no seams show
        c.rect(x + i * step_w, y, step_w + 0.4, h, stroke=0, fill=1)


def _fit(c, text: str, font: str, size: float, max_w: float) -> float:
    """Shrink the font until the text fits the available width."""
    while size > 4.5 and c.stringWidth(text, font, size) > max_w:
        size -= 0.5
    return size


def _draw_image(
    c, path: Path, x: float, y: float, w: float, h: float, cover: bool = False
) -> bool:
    """Draw an image to fit (default) or to fill the box (cover, needs clipping)."""
    try:
        image = ImageReader(str(path))
        iw, ih = image.getSize()
    except Exception:  # noqa: BLE001 - a bad image must not break the card
        return False
    scale = max(w / iw, h / ih) if cover else min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    c.drawImage(
        image, x + (w - dw) / 2, y + (h - dh) / 2, width=dw, height=dh,
        mask="auto", preserveAspectRatio=True, anchor="c",
    )
    return True


def _rounded_clip_photo(
    c, path: Optional[Path], x: float, y: float, w: float, h: float
) -> None:
    """Photo panel. Falls back to a neutral placeholder if the file is unusable."""
    c.saveState()
    c.setFillColor(colors.HexColor("#F4F6FC"))
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, 5, stroke=1, fill=1)
    drawn = False
    if path is not None and path.exists():
        c.saveState()
        pth = c.beginPath()
        pth.roundRect(x + 1.2, y + 1.2, w - 2.4, h - 2.4, 4)
        c.clipPath(pth, stroke=0, fill=0)
        # cover-fill so a square photo does not leave gaps in a portrait panel
        drawn = _draw_image(
            c, path, x + 1.2, y + 1.2, w - 2.4, h - 2.4, cover=True
        )
        c.restoreState()
    if not drawn:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 6)
        c.drawCentredString(x + w / 2, y + h / 2, "PHOTO")
    c.restoreState()


def _field(c, label: str, value: str, x: float, y: float, max_w: float) -> None:
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 4.6)
    c.drawString(x, y + 6.2, label.upper())
    c.setFillColor(INK)
    size = _fit(c, value, "Helvetica-Bold", 7.0, max_w)
    c.setFont("Helvetica-Bold", size)
    c.drawString(x, y, value)


def build_id_card_pdf(
    *,
    full_name: str,
    unique_employee_id: str,
    department: str,
    designation: str,
    date_of_joining: str,
    email: str = "",
    phone: str = "",
    blood_group: str = "",
    photo_path: Optional[Path] = None,
    company_name: Optional[str] = None,
    company_address: Optional[str] = None,
    logo_path: Optional[Path] = None,
    card_title: str = "EMPLOYEE IDENTITY CARD",
) -> bytes:
    company_name = company_name or settings.COMPANY_NAME
    company_address = company_address or settings.COMPANY_ADDRESS
    if logo_path is None and settings.COMPANY_LOGO_PATH:
        logo_path = Path(settings.COMPANY_LOGO_PATH)

    buffer = BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=(CARD_W, CARD_H))
    c.setTitle(f"Employee ID Card - {unique_employee_id}")

    # --- card body ---
    c.setFillColor(WHITE)
    c.rect(0, 0, CARD_W, CARD_H, stroke=0, fill=1)

    # --- top brand band ---
    band_y = CARD_H - BAND_H
    _gradient_band(c, 0, band_y, CARD_W, BAND_H)

    logo_drawn = False
    if logo_path is not None and Path(logo_path).exists():
        logo_drawn = _draw_image(c, Path(logo_path), 8, band_y + 5, 26, BAND_H - 10)

    text_x = 38 if logo_drawn else 10
    c.setFillColor(WHITE)
    size = _fit(c, company_name, "Helvetica-Bold", 11.0, CARD_W - text_x - 10)
    c.setFont("Helvetica-Bold", size)
    c.drawString(text_x, band_y + BAND_H - 15, company_name)
    c.setFont("Helvetica", 5.2)
    c.drawString(text_x, band_y + BAND_H - 24, card_title.upper())

    # --- photo + identity ---
    photo_w, photo_h = 46.0, 55.0
    photo_x = 10.0
    photo_y = band_y - 6 - photo_h
    _rounded_clip_photo(c, photo_path, photo_x, photo_y, photo_w, photo_h)

    info_x = photo_x + photo_w + 10
    info_w = CARD_W - info_x - 10

    name_y = band_y - 18
    c.setFillColor(INK)
    size = _fit(c, full_name, "Helvetica-Bold", 11.0, info_w)
    c.setFont("Helvetica-Bold", size)
    c.drawString(info_x, name_y, full_name)

    c.setFillColor(INDIGO)
    size = _fit(c, designation, "Helvetica", 7.0, info_w)
    c.setFont("Helvetica", size)
    c.drawString(info_x, name_y - 9, designation)

    # ID chip
    chip_y = name_y - 26
    chip_label = unique_employee_id
    chip_w = c.stringWidth(chip_label, "Helvetica-Bold", 8.5) + 14
    c.setFillColor(colors.HexColor("#EEF1FF"))
    c.setStrokeColor(colors.HexColor("#C9D2FF"))
    c.setLineWidth(0.7)
    c.roundRect(info_x, chip_y - 3, chip_w, 13.5, 3, stroke=1, fill=1)
    c.setFillColor(INDIGO)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(info_x + 7, chip_y + 1.5, chip_label)

    # --- detail fields, below the photo panel ---
    col_w = (CARD_W - 20) / 2 - 6
    row_y = photo_y - 14
    _field(c, "Department", department or "-", 10, row_y, col_w)
    _field(c, "Date of Joining", date_of_joining or "-", 10 + col_w + 12, row_y, col_w)

    row2_y = row_y - 14
    if email:
        _field(c, "Email", email, 10, row2_y, col_w)
    if phone:
        _field(c, "Phone", phone, 10 + col_w + 12, row2_y, col_w)

    # --- footer ---
    c.setFillColor(colors.HexColor("#F4F6FC"))
    c.rect(0, 0, CARD_W, FOOTER_H, stroke=0, fill=1)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(0, FOOTER_H, CARD_W, FOOTER_H)
    c.setFillColor(MUTED)
    addr = (company_address or "").replace("\n", " ")
    size = _fit(c, addr, "Helvetica", 4.4, CARD_W - 16)
    c.setFont("Helvetica", size)
    c.drawCentredString(CARD_W / 2, 5.6, addr)

    c.showPage()
    c.save()
    return buffer.getvalue()


def card_size() -> Tuple[float, float]:
    return CARD_W, CARD_H

"""Document upload, versioning, deletion prevention and secure access."""
import io

from tests.conftest import MINIMAL_PDF, MINIMAL_PNG


def _upload(client, headers, document_type_id, content=MINIMAL_PDF,
            filename="pan.pdf", mime="application/pdf"):
    return client.post(
        "/api/documents/upload",
        data={"document_type_id": str(document_type_id)},
        files={"file": (filename, io.BytesIO(content), mime)},
        headers=headers,
    )


def _type_id(client, headers, code):
    types = client.get("/api/documents/types", headers=headers).json()
    return next(t["id"] for t in types if t["code"] == code)


def test_checklist_lists_every_active_document_type(client, emp_a_headers):
    response = client.get("/api/documents/me", headers=emp_a_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) >= 7
    # Mandatory: Photograph, Aadhaar, PAN, CV. Qualification/Experience are optional.
    assert body["completion"]["total_required"] == 4
    required = {i["code"] for i in body["items"] if i["is_required"]}
    assert required == {"PHOTO", "AADHAAR", "PAN", "CV"}
    optional = {i["code"] for i in body["items"] if not i["is_required"]}
    assert {"QUALIFICATION", "EXPERIENCE"} <= optional
    assert all(i["status"] == "Missing" for i in body["items"])


def test_employee_uploads_a_document(client, emp_a_headers):
    type_id = _type_id(client, emp_a_headers, "PAN")
    response = _upload(client, emp_a_headers, type_id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "Pending"
    assert body["version_count"] == 1


def test_completion_percentage_updates(client, emp_a_headers):
    body = client.get("/api/documents/me", headers=emp_a_headers).json()
    assert body["completion"]["uploaded"] == 1
    assert body["completion"]["label"] == "1 / 4 Documents"
    assert 0 < body["completion"]["percent"] < 100


def test_disallowed_extension_is_rejected(client, emp_a_headers):
    type_id = _type_id(client, emp_a_headers, "AADHAAR")
    response = _upload(
        client, emp_a_headers, type_id, content=b"MZ\x90\x00malware",
        filename="virus.exe", mime="application/octet-stream",
    )
    assert response.status_code == 400
    assert "aren't accepted" in response.json()["detail"]


def test_content_must_match_the_extension(client, emp_a_headers):
    """A .pdf whose bytes aren't a PDF is refused."""
    type_id = _type_id(client, emp_a_headers, "AADHAAR")
    response = _upload(
        client, emp_a_headers, type_id, content=b"this is plain text, not a pdf",
        filename="fake.pdf", mime="application/pdf",
    )
    assert response.status_code == 400


def test_empty_file_is_rejected(client, emp_a_headers):
    type_id = _type_id(client, emp_a_headers, "CV")
    response = _upload(client, emp_a_headers, type_id, content=b"", filename="blank.pdf")
    assert response.status_code == 400


def test_path_traversal_filename_is_neutralised(client, emp_a_headers, hr_headers):
    """A ../ filename must not escape the upload directory."""
    type_id = _type_id(client, emp_a_headers, "QUALIFICATION")
    response = _upload(
        client, emp_a_headers, type_id, content=MINIMAL_PDF,
        filename="../../../../etc/passwd.pdf",
    )
    assert response.status_code == 201
    assert "/" not in response.json()["original_filename"]
    assert ".." not in response.json()["original_filename"]


def test_employee_cannot_delete_a_submitted_document(client, emp_a_headers):
    doc = next(
        i for i in client.get("/api/documents/me", headers=emp_a_headers).json()["items"]
        if i["document_id"]
    )
    response = client.delete(f"/api/documents/{doc['document_id']}", headers=emp_a_headers)
    assert response.status_code == 403
    assert "can't be deleted" in response.json()["detail"]


def test_hr_cannot_delete_a_submitted_document_either(client, hr_headers, emp_a_headers):
    doc = next(
        i for i in client.get("/api/documents/me", headers=emp_a_headers).json()["items"]
        if i["document_id"]
    )
    assert client.delete(
        f"/api/documents/{doc['document_id']}", headers=hr_headers
    ).status_code == 403


def test_document_survives_the_delete_attempt(client, emp_a_headers):
    items = client.get("/api/documents/me", headers=emp_a_headers).json()["items"]
    assert any(i["document_id"] and i["version_count"] >= 1 for i in items)


def test_employee_b_cannot_download_employee_a_document(
    client, emp_a_headers, emp_b_headers
):
    doc = next(
        i for i in client.get("/api/documents/me", headers=emp_a_headers).json()["items"]
        if i["document_id"]
    )
    response = client.get(
        f"/api/documents/{doc['document_id']}/download", headers=emp_b_headers
    )
    assert response.status_code == 403


def test_owner_and_hr_can_download(client, emp_a_headers, hr_headers):
    doc = next(
        i for i in client.get("/api/documents/me", headers=emp_a_headers).json()["items"]
        if i["document_id"]
    )
    assert client.get(
        f"/api/documents/{doc['document_id']}/download", headers=emp_a_headers
    ).status_code == 200
    assert client.get(
        f"/api/documents/{doc['document_id']}/download", headers=hr_headers
    ).status_code == 200


def test_pending_document_cannot_be_silently_replaced(client, emp_a_headers):
    type_id = _type_id(client, emp_a_headers, "PAN")
    response = _upload(client, emp_a_headers, type_id)
    assert response.status_code == 409


def test_rejection_then_reupload_creates_version_two(client, emp_a_headers, hr_headers):
    items = client.get("/api/documents/me", headers=emp_a_headers).json()["items"]
    pan = next(i for i in items if i["code"] == "PAN")

    rejected = client.post(
        f"/api/documents/{pan['document_id']}/reject",
        json={"remarks": "Please upload a clearer PAN card."},
        headers=hr_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "Rejected"

    type_id = _type_id(client, emp_a_headers, "PAN")
    again = _upload(client, emp_a_headers, type_id, filename="pan-v2.pdf")
    assert again.status_code == 201
    assert again.json()["version_count"] == 2

    versions = client.get(
        f"/api/documents/{pan['document_id']}/versions", headers=emp_a_headers
    ).json()
    assert [v["version_no"] for v in versions] == [1, 2]
    # Version 1 is preserved with its rejection on record.
    assert versions[0]["status"] == "Rejected"
    assert versions[0]["hr_remarks"] == "Please upload a clearer PAN card."


def test_hr_verifies_version_two(client, emp_a_headers, hr_headers):
    items = client.get("/api/documents/me", headers=emp_a_headers).json()["items"]
    pan = next(i for i in items if i["code"] == "PAN")
    response = client.post(
        f"/api/documents/{pan['document_id']}/verify", json={}, headers=hr_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Verified"


def test_verified_document_cannot_be_replaced_by_the_employee(client, emp_a_headers):
    type_id = _type_id(client, emp_a_headers, "PAN")
    response = _upload(client, emp_a_headers, type_id)
    assert response.status_code == 409
    assert "already verified" in response.json()["detail"]


def test_rejection_requires_a_remark(client, emp_a_headers, hr_headers):
    items = client.get("/api/documents/me", headers=emp_a_headers).json()["items"]
    doc = next(i for i in items if i["code"] == "QUALIFICATION")
    response = client.post(
        f"/api/documents/{doc['document_id']}/reject", json={}, headers=hr_headers
    )
    assert response.status_code == 422


def test_employee_cannot_verify_their_own_document(client, emp_a_headers):
    items = client.get("/api/documents/me", headers=emp_a_headers).json()["items"]
    doc = next(i for i in items if i["document_id"])
    assert client.post(
        f"/api/documents/{doc['document_id']}/verify", json={}, headers=emp_a_headers
    ).status_code == 403


def test_download_of_nonexistent_document_is_not_found(client, hr_headers):
    assert client.get("/api/documents/999999/download", headers=hr_headers).status_code == 404


def test_photo_document_accepts_png(client, emp_b_headers):
    type_id = _type_id(client, emp_b_headers, "PHOTO")
    response = _upload(
        client, emp_b_headers, type_id, content=MINIMAL_PNG,
        filename="me.png", mime="image/png",
    )
    assert response.status_code == 201

"""Centralised SMTP email service.

If SMTP isn't configured the message is written to the application log and
recorded with status 'logged', so the whole workflow stays testable offline.
Every send is written to email_logs; a dedupe_key makes a send idempotent.
"""
import logging
import smtplib
from email.message import EmailMessage
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AuditAction, EmailStatus
from app.models.email_log import EmailLog
from app.models.user import User
from app.services import audit_service

logger = logging.getLogger("rocketgenie.email")

BRAND_BLUE = "#3D7BFC"
BRAND_VIOLET = "#9B54FC"


def smtp_configured() -> bool:
    return bool(settings.SMTP_HOST)


def _wrap(title: str, body_html: str, cta_label: str = "", cta_url: str = "") -> str:
    cta = ""
    if cta_label and cta_url:
        cta = (
            f'<tr><td style="padding:8px 32px 28px;">'
            f'<a href="{cta_url}" style="display:inline-block;padding:12px 24px;'
            f"border-radius:10px;background:linear-gradient(135deg,{BRAND_BLUE},{BRAND_VIOLET});"
            f'color:#fff;text-decoration:none;font-weight:600;font-size:14px;">{cta_label}</a>'
            f"</td></tr>"
        )
    return f"""<!doctype html>
<html><body style="margin:0;background:#F5F6FB;font-family:'Segoe UI',Arial,sans-serif;color:#15172B;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px;">
<table width="100%" style="max-width:560px;background:#fff;border-radius:16px;overflow:hidden;
  border:1px solid #E6E8F2;" cellpadding="0" cellspacing="0">
<tr><td style="background:linear-gradient(135deg,{BRAND_BLUE},{BRAND_VIOLET});padding:22px 32px;">
  <span style="color:#fff;font-size:19px;font-weight:700;letter-spacing:.3px;">
  {settings.COMPANY_NAME}</span></td></tr>
<tr><td style="padding:28px 32px 6px;"><h1 style="margin:0 0 14px;font-size:19px;">{title}</h1>
  <div style="font-size:14px;line-height:1.65;color:#3C4059;">{body_html}</div></td></tr>
{cta}
<tr><td style="padding:18px 32px;border-top:1px solid #E6E8F2;font-size:12px;color:#8A90A6;">
  {settings.COMPANY_NAME}<br>{settings.COMPANY_ADDRESS}<br><br>
  This is an automated message from the {settings.COMPANY_NAME} HR portal.
</td></tr></table></td></tr></table></body></html>"""


def _dispatch(
    db: Session,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    template: str,
    related_entity: Optional[str] = None,
    related_id: Optional[int] = None,
    dedupe_key: Optional[str] = None,
    attachment: Optional[Tuple[str, bytes, str]] = None,
    actor: Optional[User] = None,
) -> Optional[EmailLog]:
    """Send (or log) one message. Returns None if dedupe_key was already used."""
    if dedupe_key:
        if db.query(EmailLog).filter(EmailLog.dedupe_key == dedupe_key).first():
            logger.info("Skipping duplicate email for key=%s", dedupe_key)
            return None

    status_value, error = EmailStatus.LOGGED, None

    if smtp_configured():
        try:
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            message["To"] = to_email
            message.set_content(text_body)
            message.add_alternative(html_body, subtype="html")

            if attachment:
                filename, content, mime = attachment
                maintype, _, subtype = mime.partition("/")
                message.add_attachment(
                    content, maintype=maintype or "application",
                    subtype=subtype or "octet-stream", filename=filename,
                )

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
                if settings.SMTP_USE_TLS:
                    smtp.starttls()
                if settings.SMTP_USERNAME:
                    smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                smtp.send_message(message)
            status_value = EmailStatus.SENT
        except Exception as exc:  # noqa: BLE001 - never break a workflow on mail failure
            status_value, error = EmailStatus.FAILED, f"{type(exc).__name__}: {exc}"
            logger.error("Email to %s failed: %s", to_email, error)
    else:
        logger.info(
            "[EMAIL NOT SENT - SMTP not configured]\nTo: %s\nSubject: %s\n%s",
            to_email, subject, text_body,
        )

    log = EmailLog(
        to_email=to_email, subject=subject, template=template,
        body_preview=text_body[:1000], status=status_value, error=error,
        attachment_name=attachment[0] if attachment else None,
        related_entity=related_entity, related_id=related_id, dedupe_key=dedupe_key,
    )
    db.add(log)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None

    audit_service.record(
        db, AuditAction.EMAIL_SENT, user=actor, entity_type="email_log",
        entity_id=log.id, meta={"template": template, "status": status_value, "to": to_email},
    )
    return log


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------
def send_salary_credited_email(
    db: Session, to_email: str, employee_name: str, period_label: str,
    net_pay_display: str, salary_id: int,
    payslip: Optional[Tuple[str, bytes, str]] = None, actor: Optional[User] = None,
) -> Optional[EmailLog]:
    subject = f"Salary Credited - {period_label}"
    link = f"{settings.FRONTEND_BASE_URL}/employee/salary-slips.html"
    text = (
        f"Hello {employee_name},\n\n"
        f"Your salary for {period_label} has been credited.\n"
        f"Net pay: {net_pay_display}\n\n"
        f"Your salary slip is now available in the {settings.COMPANY_NAME} HR portal.\n"
        f"{link}\n\nRegards,\nHR Team\n{settings.COMPANY_NAME}"
    )
    html = _wrap(
        f"Salary credited for {period_label}",
        f"<p>Hello {employee_name},</p><p>Your salary for <strong>{period_label}</strong> "
        f"has been credited.</p><p>Net pay: <strong>{net_pay_display}</strong></p>"
        f"<p>Your salary slip is now available in the HR portal.</p>",
        "Access salary slip", link,
    )
    return _dispatch(
        db, to_email, subject, html, text, "salary_credited",
        related_entity="salary_record", related_id=salary_id,
        dedupe_key=f"salary:{salary_id}:credited", attachment=payslip, actor=actor,
    )


def send_document_verified_email(
    db: Session, to_email: str, employee_name: str, document_name: str,
    document_id: int, version_no: int, actor: Optional[User] = None,
) -> Optional[EmailLog]:
    subject = f"Document Verified - {document_name}"
    link = f"{settings.FRONTEND_BASE_URL}/employee/documents.html"
    text = (
        f"Hello {employee_name},\n\nYour {document_name} has been verified by HR.\n"
        f"{link}\n\nRegards,\nHR Team\n{settings.COMPANY_NAME}"
    )
    html = _wrap(
        "Document verified",
        f"<p>Hello {employee_name},</p><p>Your <strong>{document_name}</strong> "
        f"has been verified by HR. No further action is needed.</p>",
        "View my documents", link,
    )
    return _dispatch(
        db, to_email, subject, html, text, "document_verified",
        related_entity="employee_document", related_id=document_id,
        dedupe_key=f"document:{document_id}:v{version_no}:verified", actor=actor,
    )


def send_document_rejected_email(
    db: Session, to_email: str, employee_name: str, document_name: str,
    remarks: str, document_id: int, version_no: int, reupload: bool = False,
    actor: Optional[User] = None,
) -> Optional[EmailLog]:
    action = "A new upload is required" if reupload else "It was rejected"
    subject = f"Action Required - {document_name}"
    link = f"{settings.FRONTEND_BASE_URL}/employee/documents.html"
    text = (
        f"Hello {employee_name},\n\nHR reviewed your {document_name}. {action}.\n"
        f"Reason: {remarks}\n\nUpload a new copy here: {link}\n\n"
        f"Regards,\nHR Team\n{settings.COMPANY_NAME}"
    )
    html = _wrap(
        f"{document_name} needs attention",
        f"<p>Hello {employee_name},</p><p>HR reviewed your <strong>{document_name}</strong>. "
        f"{action}.</p><p style='padding:12px 14px;background:#FFF4F5;border-radius:10px;"
        f"border-left:3px solid #E0455B;'><strong>Reason:</strong> {remarks}</p>"
        f"<p>Upload a corrected copy from the portal.</p>",
        "Upload new copy", link,
    )
    key = "reupload" if reupload else "rejected"
    return _dispatch(
        db, to_email, subject, html, text, f"document_{key}",
        related_entity="employee_document", related_id=document_id,
        dedupe_key=f"document:{document_id}:v{version_no}:{key}", actor=actor,
    )


def send_password_reset_email(
    db: Session, to_email: str, employee_name: str, raw_token: str,
) -> Optional[EmailLog]:
    subject = "Reset your Rocket Genie password"
    link = f"{settings.FRONTEND_BASE_URL}/reset-password.html?token={raw_token}"
    minutes = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    text = (
        f"Hello {employee_name},\n\nUse the link below to set a new password. "
        f"It expires in {minutes} minutes.\n{link}\n\n"
        f"If you didn't request this, you can ignore this email.\n\n"
        f"Regards,\nHR Team\n{settings.COMPANY_NAME}"
    )
    html = _wrap(
        "Reset your password",
        f"<p>Hello {employee_name},</p><p>Use the button below to set a new password. "
        f"The link expires in {minutes} minutes.</p>"
        f"<p style='color:#8A90A6;font-size:13px;'>Didn't request this? Ignore this email — "
        f"your password stays unchanged.</p>",
        "Set a new password", link,
    )
    return _dispatch(db, to_email, subject, html, text, "password_reset")


def send_meeting_reminder_email(
    db: Session, to_email: str, employee_name: str, meeting_title: str,
    department: str, when: str, meet_url: str, meeting_id: int,
    actor: Optional[User] = None,
) -> Optional[EmailLog]:
    subject = f"Meeting Reminder - {meeting_title}"
    text = (
        f"Hello {employee_name},\n\n{department} meeting: {meeting_title}\nWhen: {when}\n"
        f"Join: {meet_url}\n\nRegards,\nHR Team\n{settings.COMPANY_NAME}"
    )
    html = _wrap(
        meeting_title,
        f"<p>Hello {employee_name},</p><p>{department} — <strong>{when}</strong></p>",
        "Join Google Meet", meet_url,
    )
    return _dispatch(
        db, to_email, subject, html, text, "meeting_reminder",
        related_entity="meeting", related_id=meeting_id,
        dedupe_key=f"meeting:{meeting_id}:reminder:{to_email}", actor=actor,
    )


def send_employee_account_email(
    db: Session, to_email: str, employee_name: str, employee_code: str,
    temp_password: str, user_id: int, actor: Optional[User] = None,
) -> Optional[EmailLog]:
    subject = f"Your {settings.COMPANY_NAME} HR portal account"
    link = f"{settings.FRONTEND_BASE_URL}/login.html"
    text = (
        f"Hello {employee_name},\n\nYour HR portal account is ready.\n\n"
        f"Employee ID: {employee_code}\nEmail: {to_email}\n"
        f"Temporary password: {temp_password}\n\n"
        f"Sign in at {link} and change your password straight away.\n\n"
        f"Regards,\nHR Team\n{settings.COMPANY_NAME}"
    )
    html = _wrap(
        "Your HR portal account is ready",
        f"<p>Hello {employee_name},</p>"
        f"<p>Employee ID: <strong>{employee_code}</strong><br>"
        f"Email: <strong>{to_email}</strong><br>"
        f"Temporary password: <strong>{temp_password}</strong></p>"
        f"<p>You'll be asked to change this password the first time you sign in.</p>",
        "Sign in", link,
    )
    return _dispatch(
        db, to_email, subject, html, text, "employee_account",
        related_entity="user", related_id=user_id,
        dedupe_key=f"user:{user_id}:account_created", actor=actor,
    )

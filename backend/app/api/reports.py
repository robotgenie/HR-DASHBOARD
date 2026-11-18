# from datetime import date
# from typing import List, Optional

# from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
# from fastapi.responses import StreamingResponse
# from sqlalchemy.orm import Session, joinedload

# from app.utils.timeutil import utcnow
# from app.api.serializers import report_out
# from app.core.constants import AuditAction, ReportStatus, ReportType
# from app.core.dependencies import (
#     assert_can_access_employee, get_current_employee, get_current_user, is_hr, require_hr,
# )
# from app.database.database import get_db
# from app.models.daily_report import DailyReport
# from app.models.employee import Employee
# from app.models.report_attachment import ReportAttachment
# from app.models.user import User
# from app.schemas.common import Page, paginate
# from app.schemas.report import (
#     DailyReportIn, DailyReportOut, LogoutRequirements, ReportReviewRequest,
# )
# from app.services import audit_service, file_service, report_service

# router = APIRouter(prefix="/reports", tags=["Daily Reports"])

# ATTACHMENT_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "pdf", "doc", "docx"}


# def _query(db: Session):
#     return db.query(DailyReport).options(
#         joinedload(DailyReport.employee).joinedload(Employee.department),
#         joinedload(DailyReport.attachments),
#     )


# @router.get("", response_model=Page[DailyReportOut])
# def list_reports(
#     page: int = Query(1, ge=1),
#     page_size: int = Query(25, ge=1, le=200),
#     employee_id: Optional[int] = None,
#     department_id: Optional[int] = None,
#     report_date: Optional[date] = None,
#     date_from: Optional[date] = None,
#     date_to: Optional[date] = None,
#     status_filter: Optional[str] = Query(None, alias="status"),
#     report_type: Optional[str] = Query(None),
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     query = _query(db)

#     if not is_hr(current_user):
#         employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
#         if employee is None:
#             raise HTTPException(status_code=404, detail="No employee profile on this account.")
#         query = query.filter(DailyReport.employee_id == employee.id)
#     else:
#         if employee_id:
#             query = query.filter(DailyReport.employee_id == employee_id)
#         if department_id:
#             query = query.join(Employee).filter(Employee.department_id == department_id)

#     if report_date:
#         query = query.filter(DailyReport.report_date == report_date)
#     if date_from:
#         query = query.filter(DailyReport.report_date >= date_from)
#     if date_to:
#         query = query.filter(DailyReport.report_date <= date_to)
#     if status_filter and status_filter.lower() != "all":
#         query = query.filter(DailyReport.status == status_filter)
#     if report_type and report_type.lower() != "all":
#         if report_type.title() not in ReportType.ALL:
#             raise HTTPException(status_code=422, detail="report_type must be Noon or EOD.")
#         query = query.filter(DailyReport.report_type == report_type.title())

#     query = query.order_by(DailyReport.report_date.desc(), DailyReport.id.desc())
#     rows, meta = paginate(query, page, page_size)
#     return Page[DailyReportOut](items=[DailyReportOut(**report_out(r)) for r in rows], meta=meta)


# @router.get("/me/today", response_model=Optional[DailyReportOut])
# def my_report_today(
#     report_type: str = Query(ReportType.EOD),
#     db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee)
# ):
#     report_type = report_type.title()
#     if report_type not in ReportType.ALL:
#         raise HTTPException(status_code=422, detail="report_type must be Noon or EOD.")
#     report = report_service.get_for_date(db, employee, date.today(), report_type)
#     return DailyReportOut(**report_out(report)) if report else None


# @router.get("/logout-check", response_model=LogoutRequirements)
# def logout_check(
#     db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee)
# ):
#     """Drives the 'Before you log out' prompt. Logging out never submits a report."""
#     return LogoutRequirements(**report_service.logout_requirements(db, employee))


# @router.post("", response_model=DailyReportOut, status_code=status.HTTP_201_CREATED)
# def submit_report(
#     payload: DailyReportIn,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
#     employee: Employee = Depends(get_current_employee),
# ):
#     report = report_service.upsert(db, employee, payload, current_user, submit=payload.submit)
#     db.commit()
#     db.refresh(report)
#     return DailyReportOut(**report_out(report))


# def _load(db: Session, report_id: int, user: User) -> DailyReport:
#     report = _query(db).filter(DailyReport.id == report_id).first()
#     if report is None:
#         raise HTTPException(status_code=404, detail="Report not found.")
#     assert_can_access_employee(user, report.employee_id, db)
#     return report


# @router.get("/{report_id}", response_model=DailyReportOut)
# def get_report(
#     report_id: int,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     return DailyReportOut(**report_out(_load(db, report_id, current_user)))


# @router.post("/{report_id}/attachments", response_model=DailyReportOut)
# async def add_attachment(
#     report_id: int,
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     report = _load(db, report_id, current_user)
#     if report.status == ReportStatus.REVIEWED:
#         raise HTTPException(
#             status_code=status.HTTP_409_CONFLICT,
#             detail="This report has been reviewed and can't be changed.",
#         )
#     if len(report.attachments) >= 10:
#         raise HTTPException(
#             status_code=status.HTTP_409_CONFLICT, detail="Up to 10 attachments per report."
#         )

#     content, ext, mime, _ = await file_service.validate_and_read(
#         file, allowed_extensions=ATTACHMENT_EXTENSIONS, max_size=10 * 1024 * 1024
#     )
#     stored = file_service.build_stored_name(f"report_{report.id}", file.filename)
#     file_service.save_bytes(file_service.REPORTS, stored, content)

#     db.add(
#         ReportAttachment(
#             daily_report_id=report.id,
#             stored_filename=stored,
#             original_filename=file_service.sanitise_filename(file.filename),
#             mime_type=mime,
#             file_size=len(content),
#             uploaded_by_id=current_user.id,
#         )
#     )
#     db.commit()
#     db.refresh(report)
#     return DailyReportOut(**report_out(report))


# @router.get("/attachments/{attachment_id}/download")
# def download_attachment(
#     attachment_id: int,
#     inline: bool = True,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     attachment = (
#         db.query(ReportAttachment).filter(ReportAttachment.id == attachment_id).first()
#     )
#     if attachment is None:
#         raise HTTPException(status_code=404, detail="Attachment not found.")
#     # Ownership flows through the parent report.
#     assert_can_access_employee(current_user, attachment.report.employee_id, db)

#     path = file_service.resolve_path(file_service.REPORTS, attachment.stored_filename)
#     if not path.exists():
#         raise HTTPException(status_code=404, detail="The stored file is missing.")

#     disposition = "inline" if inline else "attachment"
#     return StreamingResponse(
#         iter([path.read_bytes()]),
#         media_type=attachment.mime_type,
#         headers={
#             "Content-Disposition": f'{disposition}; filename="{attachment.original_filename}"'
#         },
#     )


# @router.post("/{report_id}/review", response_model=DailyReportOut)
# def review_report(
#     report_id: int,
#     payload: ReportReviewRequest,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(require_hr),
# ):
#     from datetime import datetime

#     report = _load(db, report_id, current_user)
#     if report.status == ReportStatus.DRAFT:
#         raise HTTPException(
#             status_code=status.HTTP_409_CONFLICT, detail="This report hasn't been submitted yet."
#         )
#     report.status = ReportStatus.REVIEWED
#     report.reviewed_by_id = current_user.id
#     report.reviewed_at = utcnow()
#     report.review_notes = payload.review_notes
#     db.flush()
#     audit_service.record(
#         db, AuditAction.REPORT_REVIEWED, user=current_user, entity_type="daily_report",
#         entity_id=report.id, meta={"employee_id": report.employee_id},
#     )
#     db.commit()
#     db.refresh(report)
#     return DailyReportOut(**report_out(report))

from datetime import date
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.utils.timeutil import utcnow
from app.utils.clock import local_today
from app.api.serializers import report_out
from app.core.constants import AuditAction, ReportStatus, ReportType
from app.core.dependencies import (
    assert_can_access_employee,
    get_current_employee,
    get_current_user,
    is_hr,
    require_hr,
)
from app.database.database import get_db
from app.models.daily_report import DailyReport
from app.models.employee import Employee
from app.models.report_attachment import ReportAttachment
from app.models.user import User
from app.schemas.common import Page, paginate
from app.schemas.report import (
    DailyReportIn,
    DailyReportOut,
    LogoutRequirements,
    ReportReviewRequest,
)
from app.services import audit_service, file_service, hierarchy_service, report_service


router = APIRouter(prefix="/reports", tags=["Daily Reports"])


# ============================================================
# ATTACHMENTS
# ============================================================

ATTACHMENT_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp",
    "pdf",
    "doc",
    "docx",
}


# ============================================================
# REPORT TYPE HELPERS
# ============================================================

def _normalise_report_type(value: Optional[str]) -> Optional[str]:
    """
    Normalise report type values coming from the frontend.

    Supported values:
        Noon
        EOD
        Noon Report
        EOD Report
        all

    Returns:
        "Noon"
        "EOD"
        "all"
        None
    """

    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    normalised = value.lower()

    if normalised == "all":
        return "all"

    if normalised in {"noon", "noon report"}:
        return "Noon"

    if normalised in {"eod", "eod report"}:
        return "EOD"

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="report_type must be Noon or EOD.",
    )


# ============================================================
# BASE QUERY
# ============================================================

def _query(db: Session):
    return db.query(DailyReport).options(
        joinedload(DailyReport.employee).joinedload(Employee.department),
        joinedload(DailyReport.attachments),
    )


# ============================================================
# LIST REPORTS
# ============================================================

@router.get("", response_model=Page[DailyReportOut])
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    report_date: Optional[date] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    report_type: Optional[str] = Query(None),
    reporting_hr_id: Optional[int] = None,
    reporting_manager_id: Optional[int] = None,
    mine: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return daily work reports.

    Employee/Intern:
        - Can see only their own reports.

    HR:
        - Can see all reports.
        - Can filter by employee.
        - Can filter by department.
        - Can filter by report type.
        - Can filter by status.
        - Can filter by date.
    """

    query = _query(db)

    # --------------------------------------------------------
    # ROLE-BASED ACCESS
    # --------------------------------------------------------

    # Hierarchy: own reports for everyone ("mine"); supervisors otherwise see
    # the people below them (Manager -> team, HR -> hierarchy, Admin -> all).
    if mine or not hierarchy_service.is_supervisor(current_user):
        employee = current_user.employee
        if employee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No employee profile on this account.",
            )
        query = query.filter(DailyReport.employee_id == employee.id)
    else:
        query = query.join(Employee, DailyReport.employee_id == Employee.id)
        query = hierarchy_service.restrict(query, db, current_user, Employee.id, include_self=False)
        if employee_id:
            query = query.filter(DailyReport.employee_id == employee_id)
        if department_id:
            query = query.filter(Employee.department_id == department_id)
        if reporting_hr_id:
            query = query.filter(Employee.reporting_hr_id == reporting_hr_id)
        if reporting_manager_id:
            query = query.filter(Employee.reporting_manager_id == reporting_manager_id)

    # --------------------------------------------------------
    # DATE FILTERS
    # --------------------------------------------------------

    if report_date:
        query = query.filter(
            DailyReport.report_date == report_date
        )

    if date_from:
        query = query.filter(
            DailyReport.report_date >= date_from
        )

    if date_to:
        query = query.filter(
            DailyReport.report_date <= date_to
        )

    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    if status_filter:
        normalised_status = status_filter.strip().lower()

        if normalised_status != "all":
            query = query.filter(
                DailyReport.status == status_filter
            )

    # --------------------------------------------------------
    # REPORT TYPE FILTER
    # --------------------------------------------------------

    normalised_report_type = _normalise_report_type(report_type)

    if normalised_report_type and normalised_report_type != "all":
        query = query.filter(
            DailyReport.report_type == normalised_report_type
        )

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    query = query.order_by(
        DailyReport.report_date.desc(),
        DailyReport.id.desc(),
    )

    # --------------------------------------------------------
    # PAGINATION
    # --------------------------------------------------------

    rows, meta = paginate(
        query,
        page,
        page_size,
    )

    return Page[DailyReportOut](
        items=[
            DailyReportOut(**report_out(report))
            for report in rows
        ],
        meta=meta,
    )


# ============================================================
# TODAY'S REPORT FOR LOGGED-IN EMPLOYEE
# ============================================================

@router.get(
    "/me/today",
    response_model=Optional[DailyReportOut],
)
def my_report_today(
    report_type: str = Query(ReportType.EOD),
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    """
    Return today's Noon or EOD report for the logged-in employee.
    """

    normalised_report_type = _normalise_report_type(
        report_type
    )

    if normalised_report_type in (None, "all"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="report_type must be Noon or EOD.",
        )

    report = report_service.get_for_date(
        db,
        employee,
        local_today(),
        normalised_report_type,
    )

    if report is None:
        return None

    return DailyReportOut(
        **report_out(report)
    )


# ============================================================
# LOGOUT CHECK
# ============================================================

@router.get(
    "/logout-check",
    response_model=LogoutRequirements,
)
def logout_check(
    db: Session = Depends(get_db),
    employee: Employee = Depends(get_current_employee),
):
    """
    Drives the "Before you log out" prompt.

    Logging out never submits a report automatically.
    """

    return LogoutRequirements(
        **report_service.logout_requirements(
            db,
            employee,
        )
    )


# ============================================================
# CREATE / UPDATE REPORT
# ============================================================

@router.post(
    "",
    response_model=DailyReportOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_report(
    payload: DailyReportIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    employee: Employee = Depends(get_current_employee),
):
    """
    Create or update a Noon/EOD report.
    """

    # Validate report type before sending it to the service.
    normalised_report_type = _normalise_report_type(
        payload.report_type
    )

    if normalised_report_type in (None, "all"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="report_type must be Noon or EOD.",
        )

    # Make sure the payload contains the canonical value.
    payload.report_type = normalised_report_type

    report = report_service.upsert(
        db,
        employee,
        payload,
        current_user,
        submit=payload.submit,
    )

    db.commit()
    db.refresh(report)

    return DailyReportOut(
        **report_out(report)
    )


# ============================================================
# LOAD SINGLE REPORT
# ============================================================

def _load(
    db: Session,
    report_id: int,
    user: User,
) -> DailyReport:

    report = (
        _query(db)
        .filter(DailyReport.id == report_id)
        .first()
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    assert_can_access_employee(
        user,
        report.employee_id,
        db,
    )

    return report


# ============================================================
# GET SINGLE REPORT
# ============================================================

@router.get(
    "/{report_id}",
    response_model=DailyReportOut,
)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = _load(
        db,
        report_id,
        current_user,
    )

    return DailyReportOut(
        **report_out(report)
    )


# ============================================================
# ADD ATTACHMENT
# ============================================================

@router.post(
    "/{report_id}/attachments",
    response_model=DailyReportOut,
)
async def add_attachment(
    report_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = _load(
        db,
        report_id,
        current_user,
    )

    # Approved leave can make this report not applicable (e.g. EOD during an
    # Afternoon Half leave): then no proof-of-work attachment can be added.
    is_owner = report.employee is not None and report.employee.user_id == current_user.id
    if not is_owner and not hierarchy_service.can_manage_employee(db, current_user, report.employee):
        raise HTTPException(status_code=403, detail="Only the author can attach work proof.")
    if is_owner:
        report_service.assert_report_applicable(
            db, report.employee, report.report_type, report.report_date, current_user
        )

    # Reviewed reports cannot be changed.
    if report.status == ReportStatus.REVIEWED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This report has been reviewed and can't be changed.",
        )

    # Maximum attachments.
    if len(report.attachments) >= 10:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Up to 10 attachments per report.",
        )

    content, ext, mime, _ = await file_service.validate_and_read(
        file,
        allowed_extensions=ATTACHMENT_EXTENSIONS,
        max_size=10 * 1024 * 1024,
    )

    stored = file_service.build_stored_name(
        f"report_{report.id}",
        file.filename,
    )

    file_service.save_bytes(
        file_service.REPORTS,
        stored,
        content,
    )

    db.add(
        ReportAttachment(
            daily_report_id=report.id,
            stored_filename=stored,
            original_filename=file_service.sanitise_filename(
                file.filename
            ),
            mime_type=mime,
            file_size=len(content),
            uploaded_by_id=current_user.id,
        )
    )

    db.commit()
    db.refresh(report)

    return DailyReportOut(
        **report_out(report)
    )


# ============================================================
# DOWNLOAD ATTACHMENT
# ============================================================

@router.get(
    "/attachments/{attachment_id}/download"
)
def download_attachment(
    attachment_id: int,
    inline: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = (
        db.query(ReportAttachment)
        .filter(
            ReportAttachment.id == attachment_id
        )
        .first()
    )

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        )

    # Ownership flows through the parent report.
    assert_can_access_employee(
        current_user,
        attachment.report.employee_id,
        db,
    )

    path = file_service.resolve_path(
        file_service.REPORTS,
        attachment.stored_filename,
    )

    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The stored file is missing.",
        )

    disposition = (
        "inline"
        if inline
        else "attachment"
    )

    return StreamingResponse(
        iter([path.read_bytes()]),
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; '
                f'filename="{attachment.original_filename}"'
            )
        },
    )


# ============================================================
# HR REVIEW REPORT
# ============================================================

@router.post(
    "/{report_id}/review",
    response_model=DailyReportOut,
)
def review_report(
    report_id: int,
    payload: ReportReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = _load(
        db,
        report_id,
        current_user,
    )

    # Manager -> own team, HR -> hierarchy, Admin -> everyone. Never your own.
    if not hierarchy_service.can_review_report(db, current_user, report):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can review reports of the people who report to you.",
        )

    # Draft reports cannot be reviewed.
    if report.status == ReportStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This report hasn't been submitted yet.",
        )

    report.status = ReportStatus.REVIEWED
    report.reviewed_by_id = current_user.id
    report.reviewed_at = utcnow()
    report.review_notes = payload.review_notes

    db.flush()

    audit_service.record(
        db,
        AuditAction.REPORT_REVIEWED,
        user=current_user,
        entity_type="daily_report",
        entity_id=report.id,
        meta={
            "employee_id": report.employee_id,
        },
    )

    db.commit()
    db.refresh(report)

    return DailyReportOut(
        **report_out(report)
    )


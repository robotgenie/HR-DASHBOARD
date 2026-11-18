"""Central application configuration. Every value comes from the environment.

Nothing secret is hard-coded: `.env` is read for local development and real
environment variables always win (that is how the test suite redirects the
database and upload directory).
"""
from functools import lru_cache
from pathlib import Path
from typing import List, Set

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- Application ----------
    APP_NAME: str = "Rocket Genie HRMS"
    APP_ENV: str = "development"
    API_PREFIX: str = "/api"

    # ---------- Database ----------
    DATABASE_URL: str = "postgresql+psycopg2://rocket:rocket@localhost:5432/rocket_genie_hrms"
    TEST_DATABASE_URL: str = (
        "postgresql+psycopg2://rocket:rocket@localhost:5432/rocket_genie_hrms_test"
    )
    SQL_ECHO: bool = False

    # ---------- Authentication ----------
    JWT_SECRET_KEY: str = "change-me-to-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 60

    # ---------- Email ----------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 2525
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "hr@rocketgenie.com"
    SMTP_FROM_NAME: str = "Rocket Genie HR"
    SMTP_USE_TLS: bool = True

    # ---------- Files ----------
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS: str = "pdf,png,jpg,jpeg,webp,doc,docx"

    # ---------- Company branding ----------
    COMPANY_NAME: str = "Robot Genie"
    COMPANY_ADDRESS: str = (
        "Hno. 35, Office no. 301, 3rd Floor, Metro Pillar no. 35, "
        "Near Sai Baba Mandir, Laxmi Nagar, New Delhi - 110092"
    )
    COMPANY_UDYAM: str = "UDYAM-DL-02-0061089"
    COMPANY_LOGO_PATH: str = str(
        PROJECT_ROOT / "frontend" / "assets" / "logo" / "rocket-genie-mark.png"
    )
    FRONTEND_BASE_URL: str = "http://localhost:8000/app"

    # ---------- CORS ----------
    CORS_ORIGINS: str = (
        "http://localhost:8000,http://127.0.0.1:8000,"
        "http://localhost:5500,http://127.0.0.1:5500"
    )

    # ---------- Automatic monthly salary slips ----------
    # A background loop inside the API process creates the current month's
    # salary record for every employee from their previous month (also
    # runnable from an OS scheduler: `python generate_monthly_salaries.py`).
    SALARY_AUTOGEN_ENABLED: bool = True
    SALARY_AUTOGEN_INTERVAL_MINUTES: int = 60
    # Missing months are filled in when the employee's last salary is at most
    # this many months old; an older last salary is left to HR.
    SALARY_AUTOGEN_MAX_BACKFILL_MONTHS: int = 3

    # ---------- Seed accounts (development only) ----------

    SEED_HR_PASSWORD: str = "RocketHR@2026"
    SEED_EMPLOYEE_PASSWORD: str = "RocketEmp@2026"

    # ---------- Derived helpers ----------
    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_extension_set(self) -> Set[str]:
        return {
            ext.strip().lower().lstrip(".")
            for ext in self.ALLOWED_EXTENSIONS.split(",")
            if ext.strip()
        }

    @property
    def upload_path(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        return path if path.is_absolute() else BACKEND_ROOT / path

    @property
    def is_sqlite(self) -> bool:
        """True on the portable test profile; Alembic needs batch mode there."""
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USERNAME and self.SMTP_PASSWORD)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

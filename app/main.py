"""Launch from project root: python -m streamlit run app/main.py."""
import logging
import sys
from pathlib import Path

# Streamlit executes this file as a script; make the package importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app.core.config import load_settings
from app.core.logger import configure_logging
from app.database.session import create_database
from app.ui.dashboard import dashboard

st.set_page_config(page_title="Fashion AI Localizer", page_icon="🎬", layout="wide")


@st.cache_resource
def bootstrap():
    settings = load_settings()
    configure_logging(settings.log_level)
    for directory in ("projects", "temp", "exports"):
        (settings.storage_root / directory).mkdir(parents=True, exist_ok=True)
    sessions = create_database(settings.database_url)
    logging.getLogger("fashion_ai").info("application_started env=%s", settings.app_env)
    return settings, sessions


try:
    settings, sessions = bootstrap()
    dashboard(settings, sessions)
except Exception as exc:
    logging.getLogger("fashion_ai").error("application_failed type=%s", type(exc).__name__)
    st.error("Không thể mở ứng dụng. Hãy kiểm tra cấu hình .env, quyền ghi kho lưu trữ và SQLite.")

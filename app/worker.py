"""Local worker entry point. Native models cannot block the Streamlit process."""
import argparse
import os

from app.core.config import load_settings
from app.core.logger import configure_logging
from app.database.session import create_database
from app.services.ocr_service import run_job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    settings = load_settings()
    configure_logging(settings.log_level)
    sessions = create_database(args.database_url)
    try:
        run_job(sessions, args.job)
    finally:
        sessions.kw["bind"].dispose()
    # Disposable worker must exit even if a timed-out native inference thread is
    # still alive. Transactions have been closed before this process-only exit.
    os._exit(0)


if __name__ == "__main__":
    main()

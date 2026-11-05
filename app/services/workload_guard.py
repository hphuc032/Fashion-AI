"""Called under the queue's SQLite write lock; independent feature schemas optional."""
from sqlalchemy import inspect,text
from app.utils.validators import UserError


def ensure_idle(session,exclude=''):
    tables=set(inspect(session.bind).get_table_names())
    for table in ('ocr_jobs','render_jobs','dub_jobs'):
        if table==exclude or table not in tables:continue
        if session.execute(text(f"SELECT id FROM {table} WHERE status NOT IN ('COMPLETED','FAILED','CANCELLED') LIMIT 1")).first():
            raise UserError('Đang có tác vụ OCR/render/lồng tiếng khác; chờ hoặc hủy trước.')

from pathlib import PureWindowsPath
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, ValidationError


class UserError(ValueError):
    """An actionable error safe to display to the user."""


class SourceInfo(BaseModel):
    source_url: HttpUrl | None = None
    creator_name: str | None = Field(default=None, max_length=255)
    rights_status: Literal["unknown", "owned", "licensed", "permission_granted"] = "unknown"
    rights_notes: str | None = Field(default=None, max_length=4000)


def validate_source(**values) -> SourceInfo:
    try:
        return SourceInfo(**values)
    except ValidationError as exc:
        raise UserError("Thông tin nguồn không hợp lệ. URL phải dùng http/https; hãy kiểm tra độ dài và quyền sử dụng.") from exc


def validate_filename(filename: str) -> str:
    path = PureWindowsPath(filename)
    if (not filename or len(filename) > 255 or path.name != filename
            or path.drive or any(c in filename for c in '/\\:<>"|?*')
            or any(ord(c) < 32 for c in filename) or filename.endswith((".", " "))):
        raise UserError("Tên tệp không an toàn. Hãy đổi tên và tải lại.")
    if path.stem.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
        raise UserError("Tên tệp dành riêng cho Windows. Hãy đổi tên.")
    suffix = path.suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv"}:
        raise UserError("Chỉ hỗ trợ video MP4, MOV hoặc MKV.")
    return suffix

from uuid import uuid4

from fastapi.responses import JSONResponse


def error(status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "request_id": str(uuid4())}})

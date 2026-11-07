from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from fashion_api.core.errors import error
from fashion_api.core.security import COOKIE
from fashion_api.schemas.system import BootstrapIn, SessionOut

router = APIRouter(prefix="/api/v1/session")


def dto(session):
    return SessionOut(csrf_token=session.csrf,
        expires_at=datetime.fromtimestamp(session.expires, timezone.utc).isoformat())


@router.post("/bootstrap", response_model=SessionOut)
def bootstrap(body: BootstrapIn, request: Request):
    result = request.app.state.access.exchange(body.bootstrap_secret)
    if result is None:
        return error(401, "BOOTSTRAP_REJECTED", "The startup link is invalid or expired. Restart the Web runtime.")
    token, session = result
    response = JSONResponse(dto(session).model_dump())
    response.set_cookie(COOKIE, token, max_age=request.app.state.config.session_ttl,
                        httponly=True, samesite="strict", path="/api", secure=False)
    return response


@router.get("", response_model=SessionOut)
def current(request: Request):
    return dto(request.state.session)


@router.delete("", status_code=204)
def revoke(request: Request):
    request.app.state.access.revoke(request.state.session_token)
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/api", httponly=True, samesite="strict")
    return response

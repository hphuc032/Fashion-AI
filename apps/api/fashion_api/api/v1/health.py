from fastapi import APIRouter, Request
from fashion_api.schemas.system import Health, SystemStatus

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=Health)
def health(request: Request):
    return Health(instance_id=request.app.state.instance_id)


@router.get("/system/status", response_model=SystemStatus)
def status(request: Request):
    return request.app.state.diagnostics

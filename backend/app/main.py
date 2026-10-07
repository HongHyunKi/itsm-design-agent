import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1 import design, health, items
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_request_logger, setup_logging
from app.db.init_db import init_db
from app.db.seed import seed
from app.schemas.common import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    if settings.initialize_database:
        init_db()
        if not settings.is_live:
            seed()
    yield


def _logger(request: Request):
    return get_request_logger(getattr(request.state, "request_id", "-"))


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{get_settings().app_name} · ITSM 설계 자동화",
        description="서비스 요청·장애 관리 요구사항으로 설계 초안을 생성하는 백엔드 API입니다.",
        openapi_tags=[
            {"name": "design", "description": "요구사항 기반 설계 생성"},
            {"name": "health", "description": "서버 상태 확인"},
            {"name": "items", "description": "샘플 코드 · 기본 CRUD 예제"},
        ],
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex[:8]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        _logger(request).warning("%s %s: %s", exc.status_code, exc.code, exc.message)
        body = ErrorResponse(code=exc.code, message=exc.message, detail=exc.detail)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 'input'/'ctx'에는 사용자가 보낸 원본 값(비밀번호 등)이 들어 있으므로 위치와 사유만 남깁니다.
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        _logger(request).info("validation failed: %s", [(e["loc"], e["type"]) for e in errors])
        body = ErrorResponse(code="validation_failed", message="Invalid request", detail=errors)
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # 원인은 로그에만 남기고 응답에는 내부 정보를 싣지 않습니다.
        # 이 핸들러는 request_id 미들웨어 바깥에서 돌기 때문에 헤더를 직접 붙입니다.
        request_id = getattr(request.state, "request_id", "-")
        get_request_logger(request_id).error("unhandled error", exc_info=exc)
        body = ErrorResponse(code="internal_error", message="Internal server error")
        return JSONResponse(status_code=500, content=body.model_dump(mode="json"), headers={"X-Request-ID": request_id})

    app.include_router(design.router, prefix="/api/v1")
    app.include_router(health.router)
    app.include_router(items.router, prefix="/api/v1")

    default_openapi = app.openapi

    def openapi_with_examples():
        schema = default_openapi()
        # FastAPI가 문서 메타데이터의 None을 제거하므로 필수 nullable 필드의 예시를 복원한다.
        schema["paths"]["/api/v1/design"]["post"]["responses"]["200"]["content"]["application/json"]["example"] = (
            design.RESPONSE_EXAMPLE
        )
        return schema

    app.openapi = openapi_with_examples
    return app


app = create_app()

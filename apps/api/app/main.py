import os

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import DatabaseHealthError, check_database_connection
from app.routers.concepts import router as concepts_router
from app.routers.appointments import router as appointments_router
from app.routers.booking import router as booking_router
from app.routers.doctors import router as doctors_router
from app.routers.recommendations import router as recommendations_router


def create_app() -> FastAPI:
    app = FastAPI(title="Doctor Matching Agent API", version="0.1.0")

    frontend_origins = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/db/health", response_model=None)
    def database_health():
        try:
            return check_database_connection()
        except DatabaseHealthError as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unavailable", "detail": exc.message},
            )

    app.include_router(doctors_router)
    app.include_router(appointments_router)
    app.include_router(booking_router)
    app.include_router(concepts_router)
    app.include_router(recommendations_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/booking/"):
            return JSONResponse(
                status_code=422,
                content={"detail": "請確認患者資料、驗證碼與同意欄位格式。"},
                headers={"Cache-Control": "no-store, private"},
            )
        return await request_validation_exception_handler(request, exc)

    return app


app = create_app()

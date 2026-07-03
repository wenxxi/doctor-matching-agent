import os

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import DatabaseHealthError, check_database_connection
from app.routers.doctors import router as doctors_router


def create_app() -> FastAPI:
    app = FastAPI(title="Doctor Matching Agent API", version="0.1.0")

    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin],
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

    return app


app = create_app()

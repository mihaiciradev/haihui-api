import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth_admin, auth_staff, auth_traveler
from app.config import get_settings
from app.core.middleware import SecurityHeadersMiddleware

logging.basicConfig(level=logging.INFO)
settings = get_settings()

if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

app = FastAPI(title="HaiHui – Storage API", version="0.1.0")

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(auth_traveler.router)
app.include_router(auth_staff.router)
app.include_router(auth_staff.me_router)
app.include_router(auth_admin.router)
app.include_router(auth_admin.me_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

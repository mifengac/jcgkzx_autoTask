from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from autotask_api.api.contacts import router as contacts_router
from autotask_api.api.health import router as health_router
from autotask_api.api.rules import router as rules_router
from autotask_api.api.runs import router as runs_router
from autotask_api.api.scripts import router as scripts_router
from autotask_api.api.tasks import router as tasks_router
from autotask_api.api.templates import router as templates_router
from autotask_api.api.theme_runs import router as theme_runs_router
from autotask_api.api.theme_sources import router as theme_sources_router
from autotask_api.config import get_settings
from autotask_api.database import init_db
from autotask_api.services.scheduler import scheduler_service
from autotask_api.services.script_storage import ensure_script_upload_dir


settings = get_settings()
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title=settings.app_name)

app.include_router(health_router)
app.include_router(scripts_router)
app.include_router(templates_router)
app.include_router(tasks_router)
app.include_router(rules_router)
app.include_router(runs_router)
app.include_router(contacts_router)
app.include_router(theme_sources_router)
app.include_router(theme_runs_router)
app.mount("/assets", StaticFiles(directory=frontend_dir / "assets"), name="assets")


@app.on_event("startup")
def on_startup() -> None:
    ensure_script_upload_dir()
    init_db()
    scheduler_service.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler_service.shutdown()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")

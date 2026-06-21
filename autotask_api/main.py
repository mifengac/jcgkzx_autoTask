from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from autotask_api.api.auth import router as auth_router
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
from autotask_api.database import SessionLocal, init_db
from autotask_api.services.auth import (
    ensure_default_platform_user,
    get_current_user_from_request,
    require_authenticated_user,
)
from autotask_api.services.scheduler import scheduler_service
from autotask_api.services.script_storage import ensure_script_upload_dir


settings = get_settings()
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title=settings.app_name)


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(scripts_router, dependencies=[Depends(require_authenticated_user)])
app.include_router(templates_router, dependencies=[Depends(require_authenticated_user)])
app.include_router(tasks_router, dependencies=[Depends(require_authenticated_user)])
app.include_router(rules_router, dependencies=[Depends(require_authenticated_user)])
app.include_router(runs_router, dependencies=[Depends(require_authenticated_user)])
app.include_router(contacts_router, dependencies=[Depends(require_authenticated_user)])
app.include_router(theme_sources_router, dependencies=[Depends(require_authenticated_user)])
app.include_router(theme_runs_router, dependencies=[Depends(require_authenticated_user)])
app.mount("/assets", NoCacheStaticFiles(directory=frontend_dir / "assets"), name="assets")


@app.on_event("startup")
def on_startup() -> None:
    ensure_script_upload_dir()
    init_db()
    with SessionLocal() as db:
        ensure_default_platform_user(db)
    scheduler_service.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler_service.shutdown()


@app.get("/", response_model=None)
def index(request: Request) -> FileResponse | RedirectResponse:
    with SessionLocal() as db:
        user = get_current_user_from_request(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return FileResponse(frontend_dir / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/login", response_model=None)
def login_page(request: Request) -> FileResponse | RedirectResponse:
    with SessionLocal() as db:
        user = get_current_user_from_request(request, db)
    if user is not None:
        return RedirectResponse(url="/", status_code=303)
    return FileResponse(frontend_dir / "login.html", headers={"Cache-Control": "no-store"})


@app.get("/logout")
def logout_page() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return response

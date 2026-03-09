from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autotask_api.api.serializers import serialize_script
from autotask_api.database import get_db
from autotask_api.models import ScriptDefinition, ScriptVersion
from autotask_api.schemas import ScriptRead, ScriptUploadResponse
from autotask_api.services.rule_engine import dump_json_text
from autotask_api.services.script_storage import save_script_package


router = APIRouter(prefix="/api/scripts", tags=["scripts"])


@router.post("/upload", response_model=ScriptUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_script(
    script_name: str = Form(...),
    script_code: str = Form(...),
    version_no: str = Form(...),
    change_log: str = Form(""),
    entry_file: str | None = Form(default=None),
    entry_func: str | None = Form(default=None),
    package: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ScriptUploadResponse:
    target_path, checksum, manifest = await save_script_package(package, script_code, version_no)

    resolved_entry_file = manifest.get("entry_file") or entry_file
    resolved_entry_func = manifest.get("entry_func") or entry_func
    if not resolved_entry_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entry_file is required, either in manifest.json or form field.",
        )

    script = db.scalar(select(ScriptDefinition).where(ScriptDefinition.script_code == script_code))
    if not script:
        script = ScriptDefinition(
            script_name=script_name,
            script_code=script_code,
            script_type=manifest.get("script_type", "python_zip"),
            entry_file=resolved_entry_file,
            entry_func=resolved_entry_func,
            manifest_json=dump_json_text(manifest),
            status="draft",
        )
        db.add(script)
        db.flush()
    else:
        script.script_name = script_name
        script.script_type = manifest.get("script_type", script.script_type)
        script.entry_file = resolved_entry_file
        script.entry_func = resolved_entry_func
        script.manifest_json = dump_json_text(manifest)

    version_exists = db.scalar(
        select(ScriptVersion).where(
            ScriptVersion.script_id == script.id,
            ScriptVersion.version_no == version_no,
        )
    )
    if version_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="version_no already exists for this script.",
        )

    version = ScriptVersion(
        script_id=script.id,
        version_no=version_no,
        package_path=str(target_path),
        checksum=checksum,
        manifest_json=json.dumps(manifest, ensure_ascii=False),
        change_log=change_log,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    return ScriptUploadResponse(
        script_id=script.id,
        script_version_id=version.id,
        script_code=script.script_code,
        version_no=version.version_no,
        checksum=version.checksum,
        manifest=manifest,
        package_path=version.package_path,
    )


@router.get("", response_model=list[ScriptRead])
def list_scripts(db: Session = Depends(get_db)) -> list[ScriptRead]:
    stmt = select(ScriptDefinition).options(selectinload(ScriptDefinition.versions)).order_by(
        ScriptDefinition.id.desc()
    )
    scripts = db.scalars(stmt).all()
    return [serialize_script(script) for script in scripts]


@router.get("/{script_id}", response_model=ScriptRead)
def get_script(script_id: int, db: Session = Depends(get_db)) -> ScriptRead:
    stmt = (
        select(ScriptDefinition)
        .options(selectinload(ScriptDefinition.versions))
        .where(ScriptDefinition.id == script_id)
    )
    script = db.scalar(stmt)
    if not script:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found.")
    return serialize_script(script)

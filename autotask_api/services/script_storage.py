from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from fastapi import HTTPException, UploadFile, status

from autotask_api.config import get_settings
from autotask_api.services.time_utils import now_shanghai


settings = get_settings()


def ensure_script_upload_dir() -> Path:
    settings.script_upload_dir.mkdir(parents=True, exist_ok=True)
    return settings.script_upload_dir


async def save_script_package(
    upload: UploadFile,
    script_code: str,
    version_no: str,
) -> tuple[Path, str, dict]:
    if not upload.filename or not upload.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Script package must be a .zip file.",
        )

    root = ensure_script_upload_dir()
    timestamp = now_shanghai().strftime("%Y%m%d%H%M%S")
    safe_name = Path(upload.filename).name
    target_dir = root / script_code / version_no
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{timestamp}_{safe_name}"

    content = await upload.read()
    checksum = hashlib.sha256(content).hexdigest()
    target_path.write_bytes(content)

    manifest = load_manifest_from_zip(target_path)
    return target_path, checksum, manifest


def load_manifest_from_zip(zip_path: Path) -> dict:
    try:
        with ZipFile(zip_path) as zf:
            if "manifest.json" not in zf.namelist():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded zip is missing manifest.json at package root.",
                )
            with zf.open("manifest.json") as manifest_file:
                return json.loads(manifest_file.read().decode("utf-8"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse manifest.json: {exc}",
        ) from exc

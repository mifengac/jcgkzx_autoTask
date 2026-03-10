from __future__ import annotations

import asyncio
from collections.abc import Callable
import importlib.util
import inspect
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4
from zipfile import ZipFile

from fastapi import HTTPException, status

from autotask_api.models import ScriptDefinition, ScriptVersion
from autotask_api.services.rule_engine import parse_json_text


def _load_runner(module_path: Path, entry_func: str | None) -> Callable[[dict[str, Any]], Any]:
    module_name = f"autotask_runner_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if not spec or not spec.loader:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load module from {module_path}.",
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    resolved_entry_func = entry_func or "run"
    runner = getattr(module, resolved_entry_func, None)
    if not callable(runner):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entry function {resolved_entry_func} not found in {module_path.name}.",
        )
    return runner


def _coerce_result_rows(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    if not isinstance(result, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Script runner must return a list of dict rows.",
        )
    rows: list[dict[str, Any]] = []
    for item in result:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Every script result row must be a dict.",
            )
        rows.append(item)
    return rows


def execute_script(
    *,
    script: ScriptDefinition,
    version: ScriptVersion,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    package_path = Path(version.package_path)
    if not package_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Script package not found: {package_path}",
        )

    manifest = parse_json_text(version.manifest_json, {})
    entry_file = str(manifest.get("entry_file") or script.entry_file)
    entry_func = manifest.get("entry_func") or script.entry_func or "run"

    with TemporaryDirectory(prefix="autotask_script_") as temp_dir:
        temp_root = Path(temp_dir)
        with ZipFile(package_path) as zf:
            zf.extractall(temp_root)

        module_path = temp_root / entry_file
        if not module_path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Entry file {entry_file} not found in uploaded package.",
            )

        sys.path.insert(0, str(temp_root))
        try:
            runner = _load_runner(module_path, entry_func)
            result = runner(context)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            return _coerce_result_rows(result)
        finally:
            if "runner" in locals():
                sys.modules.pop(getattr(runner, "__module__", ""), None)
            if sys.path and sys.path[0] == str(temp_root):
                sys.path.pop(0)

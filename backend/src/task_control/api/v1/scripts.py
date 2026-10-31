from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from task_control.api.deps import AuthContext, require_roles
from task_control.api.schemas import ScriptEntry, ScriptList
from task_control.config import get_settings
from task_control.domain.enums import Role
from task_control.domain.errors import NotFoundError, ValidationError

router = APIRouter(prefix="/scripts", tags=["scripts"])


@router.get("", response_model=ScriptList)
def list_scripts(
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR))],
    path: str = Query(default="", max_length=1024),
) -> ScriptList:
    root = Path(get_settings().script_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValidationError("path escapes script root")
    if not target.exists() or not target.is_dir():
        raise NotFoundError("script directory not found")
    items: list[ScriptEntry] = []
    for entry in sorted(
        target.iterdir(), key=lambda item: (item.is_dir() is False, item.name.lower())
    ):
        if entry.name.startswith("."):
            continue
        relative = entry.relative_to(root).as_posix()
        items.append(
            ScriptEntry(
                name=entry.name,
                path=relative,
                type="dir" if entry.is_dir() else "file",
                size=None if entry.is_dir() else entry.stat().st_size,
            )
        )
    relative_path = target.relative_to(root).as_posix()
    parent = None
    if target != root:
        parent = target.parent.relative_to(root).as_posix()
        if parent == ".":
            parent = ""
    return ScriptList(root=str(root), path=relative_path, parent=parent, items=items)

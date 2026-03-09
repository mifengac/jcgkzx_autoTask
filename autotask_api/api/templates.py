from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotask_api.api.serializers import serialize_template
from autotask_api.database import get_db
from autotask_api.models import MessageTemplate
from autotask_api.schemas import (
    MessageTemplateCreate,
    MessageTemplateRead,
    MessageTemplateUpdate,
    TemplateRenderRequest,
    TemplateRenderResponse,
)
from autotask_api.services.rule_engine import render_template


router = APIRouter(prefix="/api/message-templates", tags=["message-templates"])


@router.post("", response_model=MessageTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(payload: MessageTemplateCreate, db: Session = Depends(get_db)) -> MessageTemplateRead:
    exists = db.scalar(
        select(MessageTemplate).where(MessageTemplate.template_code == payload.template_code)
    )
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="template_code already exists.",
        )

    template = MessageTemplate(**payload.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return serialize_template(template)


@router.get("", response_model=list[MessageTemplateRead])
def list_templates(db: Session = Depends(get_db)) -> list[MessageTemplateRead]:
    templates = db.scalars(select(MessageTemplate).order_by(MessageTemplate.id.desc())).all()
    return [serialize_template(template) for template in templates]


@router.get("/{template_id}", response_model=MessageTemplateRead)
def get_template(template_id: int, db: Session = Depends(get_db)) -> MessageTemplateRead:
    template = db.get(MessageTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    return serialize_template(template)


@router.put("/{template_id}", response_model=MessageTemplateRead)
def update_template(
    template_id: int,
    payload: MessageTemplateUpdate,
    db: Session = Depends(get_db),
) -> MessageTemplateRead:
    template = db.get(MessageTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, key, value)

    db.add(template)
    db.commit()
    db.refresh(template)
    return serialize_template(template)


@router.post("/{template_id}/render", response_model=TemplateRenderResponse)
def render_template_preview(
    template_id: int,
    payload: TemplateRenderRequest,
    db: Session = Depends(get_db),
) -> TemplateRenderResponse:
    template = db.get(MessageTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    return TemplateRenderResponse(
        rendered_text=render_template(template.template_content, payload.variables)
    )

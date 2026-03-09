from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from autotask_api.api.serializers import serialize_contact, serialize_rule
from autotask_api.database import get_db
from autotask_api.models import AlertTask, TaskRule
from autotask_api.schemas import RuleCreate, RuleRead, RuleTestRequest, RuleTestResponse, RuleUpdate
from autotask_api.services.rule_engine import dump_json_text, resolve_rule_mobiles


router = APIRouter(tags=["rules"])


def get_rule_or_404(db: Session, rule_id: int) -> TaskRule:
    rule = db.get(TaskRule, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    return rule


@router.post("/api/tasks/{task_id}/rules", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(
    task_id: int,
    payload: RuleCreate,
    db: Session = Depends(get_db),
) -> RuleRead:
    task = db.get(AlertTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    rule = TaskRule(
        task_id=task_id,
        rule_name=payload.rule_name,
        rule_type=payload.rule_type,
        priority=payload.priority,
        enabled=payload.enabled,
        source_field=payload.source_field,
        target_table=payload.target_table,
        target_match_field=payload.target_match_field,
        target_mobile_field=payload.target_mobile_field,
        include_self=payload.include_self,
        include_county=payload.include_county,
        include_city=payload.include_city,
        filter_json=dump_json_text(payload.filter_json),
        fixed_receivers_json=dump_json_text(payload.fixed_receivers),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return serialize_rule(rule)


@router.put("/api/rules/{rule_id}", response_model=RuleRead)
def update_rule(rule_id: int, payload: RuleUpdate, db: Session = Depends(get_db)) -> RuleRead:
    rule = get_rule_or_404(db, rule_id)
    data = payload.model_dump(exclude_unset=True)
    if "filter_json" in data:
        rule.filter_json = dump_json_text(data.pop("filter_json"))
    if "fixed_receivers" in data:
        rule.fixed_receivers_json = dump_json_text(data.pop("fixed_receivers"))
    for key, value in data.items():
        setattr(rule, key, value)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return serialize_rule(rule)


@router.delete("/api/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, db: Session = Depends(get_db)) -> None:
    rule = get_rule_or_404(db, rule_id)
    db.delete(rule)
    db.commit()


@router.post("/api/rules/{rule_id}/test", response_model=RuleTestResponse)
def test_rule(
    rule_id: int,
    payload: RuleTestRequest,
    db: Session = Depends(get_db),
) -> RuleTestResponse:
    rule = get_rule_or_404(db, rule_id)
    codes, mobiles, contacts = resolve_rule_mobiles(db, rule, payload.sample_row)
    return RuleTestResponse(
        resolved_codes=codes,
        mobiles=mobiles,
        contacts=[serialize_contact(contact) for contact in contacts],
    )

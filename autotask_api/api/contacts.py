from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from autotask_api.api.serializers import serialize_contact
from autotask_api.database import get_db
from autotask_api.models import OrgContact
from autotask_api.schemas import ContactSearchResponse


router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("", response_model=ContactSearchResponse)
def search_contacts(
    keyword: str | None = Query(default=None),
    sspcsdm: str | None = Query(default=None),
    xqdm: str | None = Query(default=None),
    rwzt: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ContactSearchResponse:
    stmt = (
        select(OrgContact)
        .options(joinedload(OrgContact.phones))
        .where(OrgContact.status == "active")
    )

    if keyword:
        like_value = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                OrgContact.xm.ilike(like_value),
                OrgContact.sspcs.ilike(like_value),
                OrgContact.xq.ilike(like_value),
                OrgContact.zw.ilike(like_value),
            )
        )
    if sspcsdm:
        stmt = stmt.where(OrgContact.sspcsdm == sspcsdm.strip())
    if xqdm:
        stmt = stmt.where(OrgContact.xqdm == xqdm.strip())
    if rwzt:
        stmt = stmt.where(OrgContact.rwzt == rwzt.strip())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0
    contacts = list(db.scalars(stmt.order_by(OrgContact.id.desc()).limit(limit)).unique())
    return ContactSearchResponse(
        items=[serialize_contact(contact) for contact in contacts],
        total=total,
    )

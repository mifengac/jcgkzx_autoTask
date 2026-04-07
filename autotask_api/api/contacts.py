from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from autotask_api.api.serializers import serialize_contact
from autotask_api.database import get_db
from autotask_api.models import OrgContact, OrgContactPhone
from autotask_api.schemas import ContactCreate, ContactRead, ContactSearchResponse, ContactUpdate
from autotask_api.services.rule_engine import normalize_mobile
from autotask_api.services.task_fields import normalize_non_null_text_input


router = APIRouter(prefix="/api/contacts", tags=["contacts"])

MANUAL_CONTACT_SOURCE = "manual_ui"
IMPORT_CONTACT_SOURCE = "ywdata.b_dxpt_mdjfyj"


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def contact_query():
    return select(OrgContact).options(joinedload(OrgContact.phones))


def get_contact_or_404(db: Session, contact_id: int) -> OrgContact:
    stmt = contact_query().where(OrgContact.id == contact_id)
    contact = db.scalars(stmt).unique().one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found.",
        )
    return contact


def ensure_manual_contact(contact: OrgContact) -> None:
    if contact.source_system != MANUAL_CONTACT_SOURCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Imported contacts are read-only.",
        )


def normalize_phone_payloads(phones: Iterable) -> list[dict[str, str | bool]]:
    normalized: list[dict[str, str | bool]] = []
    seen: set[str] = set()
    primary_indexes: list[int] = []

    for index, phone in enumerate(phones):
        phone_raw = str(phone.phone_raw or "").strip()
        if not phone_raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Phone row {index + 1} is empty.",
            )
        mobile = normalize_mobile(phone_raw)
        if not mobile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Phone row {index + 1} is not a valid mainland China mobile number.",
            )
        if mobile in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate phone number detected: {mobile}.",
            )
        seen.add(mobile)
        item = {
            "phone_raw": phone_raw,
            "mobile": mobile,
            "is_primary": bool(phone.is_primary),
            "status": str(phone.status),
        }
        normalized.append(item)
        if item["is_primary"]:
            primary_indexes.append(index)

    if len(primary_indexes) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only one primary phone number is allowed.",
        )

    if normalized and not primary_indexes:
        primary_index = next(
            (index for index, item in enumerate(normalized) if item["status"] == "active"),
            0,
        )
        normalized[primary_index]["is_primary"] = True

    return normalized


def ensure_contact_can_be_active(contact_status: str, phones: list[dict[str, str | bool]]) -> None:
    if contact_status != "active":
        return
    if not any(str(phone["status"]) == "active" for phone in phones):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active contacts must have at least one active phone number.",
        )


def replace_contact_phones(contact: OrgContact, phones: list[dict[str, str | bool]]) -> None:
    contact.phones.clear()
    for phone in phones:
        contact.phones.append(
            OrgContactPhone(
                phone_raw=str(phone["phone_raw"]),
                mobile=str(phone["mobile"]),
                is_primary=bool(phone["is_primary"]),
                status=str(phone["status"]),
            )
        )
    contact.raw_lxdh = ",".join(str(phone["phone_raw"]) for phone in phones) if phones else None


def apply_contact_fields(contact: OrgContact, data: dict, *, partial: bool) -> None:
    text_fields = [
        "xq",
        "xqdm",
        "sspcs",
        "sspcsdm",
        "city_code",
        "county_code",
        "xm",
        "zw",
        "rwzt",
    ]
    for field_name in text_fields:
        if partial and field_name not in data:
            continue
        setattr(contact, field_name, normalize_optional_text(data.get(field_name)))

    if not partial or "unit_level" in data:
        contact.unit_level = data.get("unit_level") or "unknown"
    if not partial or "status" in data:
        contact.status = data.get("status") or "active"
    if not partial or "remark" in data:
        contact.remark = normalize_non_null_text_input(data.get("remark"))


@router.get("", response_model=ContactSearchResponse)
def search_contacts(
    keyword: str | None = Query(default=None),
    sspcsdm: str | None = Query(default=None),
    xqdm: str | None = Query(default=None),
    rwzt: str | None = Query(default=None),
    source_system: str | None = Query(default=None),
    status_text: str = Query(default="active", alias="status"),
    unit_level: str | None = Query(default=None),
    mobile: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ContactSearchResponse:
    stmt = contact_query()

    normalized_status = (status_text or "active").strip().lower()
    if normalized_status != "all":
        stmt = stmt.where(OrgContact.status == normalized_status)

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
    if source_system:
        stmt = stmt.where(OrgContact.source_system == source_system.strip())
    if unit_level:
        stmt = stmt.where(OrgContact.unit_level == unit_level.strip())
    if mobile:
        mobile_text = mobile.strip()
        normalized_mobile = normalize_mobile(mobile_text)
        phone_stmt = select(OrgContactPhone.id).where(
            OrgContactPhone.contact_id == OrgContact.id,
            OrgContactPhone.status == "active",
        )
        if normalized_mobile:
            phone_stmt = phone_stmt.where(OrgContactPhone.mobile == normalized_mobile)
        else:
            like_value = f"%{mobile_text}%"
            phone_stmt = phone_stmt.where(
                or_(
                    OrgContactPhone.mobile.ilike(like_value),
                    OrgContactPhone.phone_raw.ilike(like_value),
                )
            )
        stmt = stmt.where(phone_stmt.exists())

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0
    contacts = list(db.scalars(stmt.order_by(OrgContact.id.desc()).limit(limit)).unique())
    return ContactSearchResponse(
        items=[serialize_contact(contact) for contact in contacts],
        total=total,
    )


@router.get("/{contact_id}", response_model=ContactRead)
def get_contact(contact_id: int, db: Session = Depends(get_db)) -> ContactRead:
    return serialize_contact(get_contact_or_404(db, contact_id))


@router.post("", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db)) -> ContactRead:
    phones = normalize_phone_payloads(payload.phones)
    ensure_contact_can_be_active(payload.status, phones)

    contact = OrgContact(
        source_system=MANUAL_CONTACT_SOURCE,
        source_pk=None,
    )
    apply_contact_fields(contact, payload.model_dump(), partial=False)
    replace_contact_phones(contact, phones)

    db.add(contact)
    db.commit()
    return serialize_contact(get_contact_or_404(db, contact.id))


@router.put("/{contact_id}", response_model=ContactRead)
def update_contact(
    contact_id: int,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
) -> ContactRead:
    contact = get_contact_or_404(db, contact_id)
    ensure_manual_contact(contact)

    data = payload.model_dump(exclude_unset=True)
    phones = None
    if "phones" in data:
        phones = normalize_phone_payloads(payload.phones or [])

    apply_contact_fields(contact, data, partial=True)

    if phones is not None:
        ensure_contact_can_be_active(contact.status, phones)
        replace_contact_phones(contact, phones)
    else:
        existing_phones = [
            {
                "status": phone.status,
            }
            for phone in contact.phones
        ]
        ensure_contact_can_be_active(contact.status, existing_phones)

    db.add(contact)
    db.commit()
    return serialize_contact(get_contact_or_404(db, contact.id))

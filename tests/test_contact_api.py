from __future__ import annotations

import os
from io import BytesIO
from types import SimpleNamespace
import unittest
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.pool import StaticPool

from autotask_api.api.contacts import (
    IMPORT_CONTACT_SOURCE,
    MANUAL_CONTACT_SOURCE,
    XLSX_IMPORT_CONTACT_SOURCE,
    create_contact,
    search_contacts,
    update_contact,
)
from autotask_api.database import Base
from autotask_api.models import OrgContact, OrgContactPhone
from autotask_api.schemas import ContactCreate, ContactUpdate
from autotask_api.services.contact_xlsx_import import import_contacts_from_xlsx
from autotask_api.services.rule_engine import resolve_rule_mobiles


def create_test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def attach_schema(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS jcgkzx_autotask")
        cursor.execute("ATTACH DATABASE ':memory:' AS stdata")
        cursor.close()

    return engine


def column_name(index: int) -> str:
    value = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(ord("A") + remainder) + value
    return value


def build_inline_xlsx(sheets: dict[str, list[list[str]]]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as zip_file:
        content_types = [
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
"""
        ]
        for index in range(1, len(sheets) + 1):
            content_types.append(
                f'  <Override PartName="/xl/worksheets/sheet{index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
            )
        content_types.append("</Types>")
        zip_file.writestr("[Content_Types].xml", "".join(content_types))
        zip_file.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        sheet_refs = []
        workbook_rels = []
        for index, sheet_name in enumerate(sheets, start=1):
            sheet_refs.append(
                f'<sheet name="{escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
            )
            workbook_rels.append(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            )
        zip_file.writestr(
            "xl/workbook.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>{''.join(sheet_refs)}</sheets>
</workbook>""",
        )
        zip_file.writestr(
            "xl/_rels/workbook.xml.rels",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {''.join(workbook_rels)}
</Relationships>""",
        )
        zip_file.writestr(
            "xl/styles.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>""",
        )
        for sheet_index, rows in enumerate(sheets.values(), start=1):
            xml_rows = []
            for row_index, row in enumerate(rows, start=1):
                cells = []
                for column_index, value in enumerate(row):
                    ref = f"{column_name(column_index)}{row_index}"
                    cells.append(
                        f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
                    )
                xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
            zip_file.writestr(
                f"xl/worksheets/sheet{sheet_index}.xml",
                f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(xml_rows)}</sheetData>
</worksheet>""",
            )
    return output.getvalue()


class ContactApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_test_engine()
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, future=True)
        self.seed_data()

    def tearDown(self) -> None:
        self.engine.dispose()

    def seed_data(self) -> None:
        with self.session_factory() as db:
            db.execute(text(
                """
                CREATE TABLE stdata.b_dic_zzjgdm (
                    ssfjdm TEXT NOT NULL,
                    sspcs TEXT NOT NULL,
                    sspcsdm TEXT NOT NULL
                )
                """
            ))
            db.execute(
                text(
                    """
                    INSERT INTO stdata.b_dic_zzjgdm (ssfjdm, sspcs, sspcsdm)
                    VALUES
                        ('445302000000', '123派出所', '445302010001'),
                        ('445302000000', '城南派出所', '445302010002'),
                        ('445303000000', '云安派出所', '445303010001')
                    """
                )
            )
            manual_contact = OrgContact(
                source_system=MANUAL_CONTACT_SOURCE,
                xq="青秀区",
                xqdm="450103",
                sspcs="中山派出所",
                sspcsdm="450103000001",
                city_code="450100",
                county_code="450103",
                unit_level="station",
                xm="张三",
                zw="民警",
                rwzt="值班",
                raw_lxdh="13800000001",
                status="active",
                remark="manual seed",
                phones=[
                    OrgContactPhone(
                        phone_raw="13800000001",
                        mobile="13800000001",
                        is_primary=True,
                        status="active",
                    )
                ],
            )
            imported_contact = OrgContact(
                source_system=IMPORT_CONTACT_SOURCE,
                source_pk="101",
                xq="青秀区",
                xqdm="450103",
                sspcs="新城派出所",
                sspcsdm="450103000002",
                city_code="450100",
                county_code="450103",
                unit_level="station",
                xm="李四",
                zw="辅警",
                rwzt="巡防",
                raw_lxdh="13900000002",
                status="active",
                remark="imported seed",
                phones=[
                    OrgContactPhone(
                        phone_raw="13900000002",
                        mobile="13900000002",
                        is_primary=True,
                        status="active",
                    )
                ],
            )
            county_contact = OrgContact(
                source_system=MANUAL_CONTACT_SOURCE,
                xq="青秀区",
                xqdm="450103",
                sspcs="青秀分局",
                sspcsdm=None,
                city_code="450100",
                county_code="450103",
                unit_level="county",
                xm="王五",
                zw="值班长",
                rwzt="县级联动",
                raw_lxdh="13700000003",
                status="active",
                remark="county seed",
                phones=[
                    OrgContactPhone(
                        phone_raw="13700000003",
                        mobile="13700000003",
                        is_primary=True,
                        status="active",
                    )
                ],
            )
            db.add_all([manual_contact, imported_contact, county_contact])
            db.commit()

    def test_search_contacts_supports_source_status_and_mobile_filters(self) -> None:
        with self.session_factory() as db:
            result = search_contacts(
                keyword=None,
                sspcsdm=None,
                xqdm=None,
                rwzt=None,
                source_system=MANUAL_CONTACT_SOURCE,
                status_text="all",
                unit_level=None,
                mobile="13800000001",
                limit=100,
                offset=0,
                db=db,
            )
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].source_system, MANUAL_CONTACT_SOURCE)
        self.assertEqual(result.items[0].phones[0].mobile, "13800000001")

    def test_create_contact_sets_manual_source_and_normalizes_phone(self) -> None:
        payload = ContactCreate(
            xm="赵六",
            zw="教导员",
            sspcs="朝阳派出所",
            sspcsdm="450103000009",
            xq="青秀区",
            xqdm="450103",
            status="active",
            phones=[
                {
                    "phone_raw": "138-1234-5678",
                    "status": "active",
                    "is_primary": False,
                }
            ],
        )
        with self.session_factory() as db:
            created = create_contact(payload, db)
        self.assertEqual(created.source_system, MANUAL_CONTACT_SOURCE)
        self.assertEqual(created.phones[0].mobile, "13812345678")
        self.assertTrue(created.phones[0].is_primary)

    def test_update_contact_replaces_phones_and_preserves_single_primary(self) -> None:
        payload = ContactUpdate(
            zw="副所长",
            phones=[
                {
                    "phone_raw": "13600000010",
                    "status": "inactive",
                    "is_primary": False,
                },
                {
                    "phone_raw": "13600000011",
                    "status": "active",
                    "is_primary": True,
                },
            ],
        )
        with self.session_factory() as db:
            updated = update_contact(1, payload, db)
        self.assertEqual(updated.zw, "副所长")
        self.assertEqual([phone.mobile for phone in updated.phones], ["13600000010", "13600000011"])
        self.assertEqual(sum(1 for phone in updated.phones if phone.is_primary), 1)
        self.assertEqual(next(phone.mobile for phone in updated.phones if phone.is_primary), "13600000011")

    def test_update_imported_contact_is_rejected(self) -> None:
        payload = ContactUpdate(remark="should fail")
        with self.session_factory() as db:
            with self.assertRaises(HTTPException) as ctx:
                update_contact(2, payload, db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("read-only", ctx.exception.detail)

    def test_active_contact_requires_active_phone(self) -> None:
        payload = ContactCreate(
            xm="无效联系人",
            status="active",
            phones=[
                {
                    "phone_raw": "13500000000",
                    "status": "inactive",
                    "is_primary": False,
                }
            ],
        )
        with self.session_factory() as db:
            with self.assertRaises(HTTPException) as ctx:
                create_contact(payload, db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("at least one active phone", ctx.exception.detail)

    def test_import_xlsx_contacts_creates_station_contact_and_phone(self) -> None:
        workbook = build_inline_xlsx({
            "云城": [
                ["序号", "县区", "派出所", "姓名", "职务", "电话号码", "备注"],
                ["1", "云城区", "123派出所", "导入联系人", "值班员", "13800000009", "首次导入"],
            ]
        })
        with self.session_factory() as db:
            result = import_contacts_from_xlsx(db, workbook, filename="contacts.xlsx")
            contact = db.scalars(
                select(OrgContact)
                .options(joinedload(OrgContact.phones))
                .where(OrgContact.source_system == XLSX_IMPORT_CONTACT_SOURCE)
            ).unique().one()

        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["updated_count"], 0)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(contact.source_pk, "445302010001:13800000009")
        self.assertEqual(contact.xqdm, "445302")
        self.assertEqual(contact.county_code, "445302000000")
        self.assertEqual(contact.sspcsdm, "445302010001")
        self.assertEqual(contact.xm, "导入联系人")
        self.assertEqual(contact.raw_lxdh, "13800000009")
        self.assertEqual(contact.phones[0].mobile, "13800000009")
        self.assertTrue(contact.phones[0].is_primary)

    def test_import_xlsx_contacts_overwrites_by_station_and_mobile(self) -> None:
        first_workbook = build_inline_xlsx({
            "云城": [
                ["序号", "县区", "派出所", "姓名", "职务", "电话号码", "备注"],
                ["1", "云城区", "123派出所", "导入联系人", "值班员", "13800000009", "首次导入"],
            ]
        })
        second_workbook = build_inline_xlsx({
            "云城": [
                ["序号", "县区", "派出所", "姓名", "职务", "电话号码", "备注"],
                ["1", "云城区", "123派出所", "导入联系人更新", "负责人", "13800000009", "覆盖导入"],
            ]
        })
        with self.session_factory() as db:
            import_contacts_from_xlsx(db, first_workbook, filename="contacts.xlsx")
            result = import_contacts_from_xlsx(db, second_workbook, filename="contacts.xlsx")
            contacts = list(db.scalars(
                select(OrgContact)
                .options(joinedload(OrgContact.phones))
                .where(OrgContact.source_system == XLSX_IMPORT_CONTACT_SOURCE)
            ).unique())

        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0].xm, "导入联系人更新")
        self.assertEqual(contacts[0].zw, "负责人")
        self.assertEqual(contacts[0].remark, "覆盖导入")

    def test_import_xlsx_contacts_reports_unmatched_station(self) -> None:
        workbook = build_inline_xlsx({
            "云城": [
                ["序号", "县区", "派出所", "姓名", "职务", "电话号码", "备注"],
                ["1", "云城区", "不存在派出所", "导入联系人", "值班员", "13800000009", ""],
            ]
        })
        with self.session_factory() as db:
            result = import_contacts_from_xlsx(db, workbook, filename="contacts.xlsx")
            count = db.scalar(
                select(func.count()).select_from(OrgContact).where(
                    OrgContact.source_system == XLSX_IMPORT_CONTACT_SOURCE
                )
            )

        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["imported_rows"], 0)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(count, 0)
        self.assertIn("派出所未在", result["errors"][0]["message"])

    def test_manual_station_contact_matches_field_match_rule(self) -> None:
        rule = SimpleNamespace(
            enabled=True,
            rule_type="field_match",
            source_field="sspcsdm",
            target_match_field="sspcsdm",
            include_self=True,
            include_county=False,
            include_city=False,
            filter_json="{}",
            fixed_receivers_json="[]",
        )
        with self.session_factory() as db:
            codes, mobiles, contacts = resolve_rule_mobiles(
                db,
                rule,
                {"sspcsdm": "450103000001"},
            )
        self.assertEqual(codes, ["450103000001"])
        self.assertEqual(mobiles, ["13800000001"])
        self.assertEqual(contacts[0].xm, "张三")

    def test_manual_county_contact_matches_ancestor_rule_and_inactive_contact_is_excluded(self) -> None:
        county_rule = SimpleNamespace(
            enabled=True,
            rule_type="field_match_with_ancestors",
            source_field="sspcsdm",
            target_match_field="xqdm",
            include_self=True,
            include_county=True,
            include_city=False,
            filter_json='{"unit_level":"county"}',
            fixed_receivers_json="[]",
        )
        with self.session_factory() as db:
            codes, mobiles, contacts = resolve_rule_mobiles(
                db,
                county_rule,
                {"sspcsdm": "450103000999"},
            )
            county_contact_name = contacts[0].xm
            update_contact(1, ContactUpdate(status="inactive"), db)
            _codes_after_disable, mobiles_after_disable, _contacts_after_disable = resolve_rule_mobiles(
                db,
                SimpleNamespace(
                    enabled=True,
                    rule_type="field_match",
                    source_field="sspcsdm",
                    target_match_field="sspcsdm",
                    include_self=True,
                    include_county=False,
                    include_city=False,
                    filter_json="{}",
                    fixed_receivers_json="[]",
                ),
                {"sspcsdm": "450103000001"},
            )
        self.assertEqual(codes, ["450103"])
        self.assertEqual(mobiles, ["13700000003"])
        self.assertEqual(county_contact_name, "王五")
        self.assertEqual(mobiles_after_disable, [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from html import escape as xml_escape
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from sqlalchemy import bindparam, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from autotask_api.models import OrgContact, OrgContactPhone
from autotask_api.services.task_fields import normalize_non_null_text_input


XLSX_CONTACT_IMPORT_SOURCE = "xlsx_contact_import"

SHEET_COUNTY_CODES = {
    "云城": "445302000000",
    "云安": "445303000000",
    "罗定": "445381000000",
    "新兴": "445321000000",
    "郁南": "445322000000",
    "市局": "445300000000",
}

EXPECTED_HEADERS = ("序号", "县区", "派出所", "姓名", "职务", "电话号码", "备注")
REQUIRED_HEADERS = ("县区", "派出所", "姓名", "职务", "电话号码", "备注")
MOBILE_EXTRACT_PATTERN = re.compile(r"1[3-9]\d{9}")
XLSX_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RELS_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
OFFICE_REL_NS = {"rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}

TEMPLATE_COLUMN_NOTES_BY_INDEX = (
    "选填，建议从 1 开始顺序填写。",
    "必填，填写所属县区名称，应与当前 sheet 对应。",
    "必填，填写派出所名称；系统会按 sheet 县区匹配 sspcsdm，未匹配时使用县区代码。",
    "必填，联系人姓名。",
    "必填，联系人职务或岗位。",
    "必填，可填写一个或多个大陆手机号，系统会提取有效 11 位手机号。",
    "选填，导入后写入联系人备注；为空时系统按空备注处理。",
)
TEMPLATE_SAMPLE_VALUES_BY_INDEX = (
    "1",
    "云城",
    "123派出所",
    "张三",
    "值班员",
    "13800000000",
    "示例：可填写分管范围或其它说明",
)


class ContactImportFatalError(RuntimeError):
    pass


def xlsx_cell_ref(column_index: int, row_index: int) -> str:
    letters = ""
    index = column_index + 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_index}"


def xlsx_inline_cell(value: Any, column_index: int, row_index: int, *, red: bool = False) -> str:
    text_value = xml_escape(str(value or ""))
    cell_ref = xlsx_cell_ref(column_index, row_index)
    if red:
        return (
            f'<c r="{cell_ref}" t="inlineStr"><is><r><rPr><color rgb="FFFF0000"/></rPr>'
            f"<t>{text_value}</t></r></is></c>"
        )
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text_value}</t></is></c>'


def xlsx_row(values: list[Any], row_index: int, *, red: bool = False) -> str:
    cells = "".join(xlsx_inline_cell(value, index, row_index, red=red) for index, value in enumerate(values))
    return f'<row r="{row_index}">{cells}</row>'


def xlsx_sheet_xml(headers: tuple[str, ...], notes: list[str], sample: list[str]) -> str:
    rows = [
        xlsx_row(list(headers), 1),
        xlsx_row(notes, 2, red=True),
        xlsx_row(sample, 3),
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        '<cols><col min="1" max="1" width="8" customWidth="1"/>'
        '<col min="2" max="7" width="28" customWidth="1"/></cols>'
        f"<sheetData>{''.join(rows)}</sheetData>"
        "</worksheet>"
    )


def create_contact_import_template_xlsx() -> bytes:
    headers = EXPECTED_HEADERS
    notes = list(TEMPLATE_COLUMN_NOTES_BY_INDEX)
    sample_base = list(TEMPLATE_SAMPLE_VALUES_BY_INDEX)

    workbook_sheets: list[str] = []
    workbook_rels: list[str] = []
    content_overrides: list[str] = []
    sheets: list[tuple[str, str]] = []
    for index, sheet_name in enumerate(SHEET_COUNTY_CODES.keys(), start=1):
        workbook_sheets.append(
            f'<sheet name="{xml_escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
        workbook_rels.append(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
        content_overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        sample = list(sample_base)
        sample[1] = sheet_name
        sheets.append((f"xl/worksheets/sheet{index}.xml", xlsx_sheet_xml(headers, notes, sample)))

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(workbook_sheets)}</sheets></workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(workbook_rels)}</Relationships>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{''.join(content_overrides)}</Types>"
    )

    output = BytesIO()
    with ZipFile(output, "w") as zip_file:
        zip_file.writestr("[Content_Types].xml", content_types_xml)
        zip_file.writestr("_rels/.rels", root_rels_xml)
        zip_file.writestr("xl/workbook.xml", workbook_xml)
        zip_file.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        for path, xml in sheets:
            zip_file.writestr(path, xml)
    return output.getvalue()


@dataclass(frozen=True)
class StationUnit:
    ssfjdm: str
    sspcs: str
    sspcsdm: str


@dataclass(frozen=True)
class ImportRow:
    sheet: str
    row_number: int
    county_code: str
    xq: str | None
    sspcs: str | None
    xm: str | None
    zw: str | None
    raw_lxdh: str | None
    remark: str


def normalize_text(value: Any) -> str | None:
    text_value = str(value or "").strip()
    return text_value or None


def normalize_station_key(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def derive_city_code(county_code: str) -> str:
    if len(county_code) >= 4:
        return f"{county_code[:4]}00000000"
    return county_code


def derive_xqdm(county_code: str) -> str:
    if len(county_code) >= 6:
        return county_code[:6]
    return county_code


def extract_mobiles(raw: str | None) -> list[str]:
    digits = re.sub(r"\D", "", raw or "")
    mobiles: list[str] = []
    seen: set[str] = set()
    for match in MOBILE_EXTRACT_PATTERN.findall(digits):
        if match in seen:
            continue
        seen.add(match)
        mobiles.append(match)
    return mobiles


def contact_source_pk(sspcsdm: str | None, county_code: str, mobile: str) -> str:
    return f"{sspcsdm or county_code}:{mobile}"


def cell_column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return max(index - 1, 0)


def normalize_number_text(value: str) -> str:
    if re.fullmatch(r"-?\d+\.0+", value):
        return value.split(".", 1)[0]
    return value


def read_shared_strings(zip_file: ZipFile) -> list[str]:
    try:
        xml_bytes = zip_file.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ET.fromstring(xml_bytes)
    strings: list[str] = []
    for item in root.findall("main:si", XLSX_NS):
        parts = [node.text or "" for node in item.findall(".//main:t", XLSX_NS)]
        strings.append("".join(parts))
    return strings


def workbook_sheet_paths(zip_file: ZipFile) -> dict[str, str]:
    try:
        workbook_root = ET.fromstring(zip_file.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
    except KeyError as exc:
        raise ContactImportFatalError("Excel 文件结构不完整，缺少 workbook 信息。") from exc

    rel_targets: dict[str, str] = {}
    for rel in rels_root.findall("rel:Relationship", RELS_NS):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target", "")
        if not rel_id or not target:
            continue
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = f"xl/{target}"
        rel_targets[rel_id] = path.replace("\\", "/")

    sheet_paths: dict[str, str] = {}
    for sheet in workbook_root.findall("main:sheets/main:sheet", XLSX_NS):
        name = sheet.attrib.get("name", "").strip()
        rel_id = sheet.attrib.get(f"{{{OFFICE_REL_NS['rel']}}}id")
        if name and rel_id and rel_id in rel_targets:
            sheet_paths[name] = rel_targets[rel_id]
    return sheet_paths


def read_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", XLSX_NS)).strip()

    value_node = cell.find("main:v", XLSX_NS)
    if value_node is None or value_node.text is None:
        return ""

    raw_value = value_node.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)].strip()
        except (ValueError, IndexError):
            return ""
    if cell_type == "b":
        return "是" if raw_value == "1" else "否"
    return normalize_number_text(raw_value).strip()


def read_sheet_rows(zip_file: ZipFile, path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(zip_file.read(path))
    rows: list[list[str]] = []
    for row in root.findall(".//main:sheetData/main:row", XLSX_NS):
        values: list[str] = []
        for cell in row.findall("main:c", XLSX_NS):
            ref = cell.attrib.get("r", "")
            column_index = cell_column_index(ref)
            while len(values) <= column_index:
                values.append("")
            values[column_index] = read_cell_text(cell, shared_strings)
        rows.append(values)
    return rows


def read_xlsx_rows(content: bytes) -> dict[str, list[list[str]]]:
    try:
        with ZipFile(BytesIO(content)) as zip_file:
            shared_strings = read_shared_strings(zip_file)
            return {
                name: read_sheet_rows(zip_file, path, shared_strings)
                for name, path in workbook_sheet_paths(zip_file).items()
            }
    except BadZipFile as exc:
        raise ContactImportFatalError("上传文件不是有效的 xlsx 文件。") from exc
    except ET.ParseError as exc:
        raise ContactImportFatalError("Excel XML 内容解析失败。") from exc


def find_header_row(rows: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    for index, row in enumerate(rows[:10]):
        normalized = {str(value).strip(): column for column, value in enumerate(row)}
        if all(header in normalized for header in REQUIRED_HEADERS):
            return index, normalized
    return None


def value_from_row(row: list[str], header_map: dict[str, int], header: str) -> str | None:
    column = header_map.get(header)
    if column is None or column >= len(row):
        return None
    return normalize_text(row[column])


def parse_import_rows(content: bytes) -> tuple[list[ImportRow], list[dict[str, Any]], set[str]]:
    workbook = read_xlsx_rows(content)
    parsed_rows: list[ImportRow] = []
    errors: list[dict[str, Any]] = []
    county_codes: set[str] = set()

    for sheet_name, rows in workbook.items():
        sheet = sheet_name.strip()
        county_code = SHEET_COUNTY_CODES.get(sheet)
        if not county_code:
            if any(any(normalize_text(cell) for cell in row) for row in rows):
                errors.append({
                    "sheet": sheet,
                    "row": None,
                    "message": "未识别的 sheet 名称，已跳过。",
                    "values": {"sheet": sheet},
                })
            continue

        header_info = find_header_row(rows)
        if header_info is None:
            errors.append({
                "sheet": sheet,
                "row": None,
                "message": "未找到表头：序号、县区、派出所、姓名、职务、电话号码、备注。",
                "values": {},
            })
            continue

        header_index, header_map = header_info
        county_codes.add(county_code)
        for row_offset, row in enumerate(rows[header_index + 1:], start=header_index + 2):
            if not any(normalize_text(cell) for cell in row):
                continue
            parsed_rows.append(
                ImportRow(
                    sheet=sheet,
                    row_number=row_offset,
                    county_code=county_code,
                    xq=value_from_row(row, header_map, "县区") or sheet,
                    sspcs=value_from_row(row, header_map, "派出所"),
                    xm=value_from_row(row, header_map, "姓名"),
                    zw=value_from_row(row, header_map, "职务"),
                    raw_lxdh=value_from_row(row, header_map, "电话号码"),
                    remark=value_from_row(row, header_map, "备注") or "",
                )
            )

    return parsed_rows, errors, county_codes


def load_station_lookup(db: Session, county_codes: set[str]) -> dict[str, dict[str, list[StationUnit]]]:
    if not county_codes:
        return {}
    stmt = text(
        """
        SELECT CAST(ssfjdm AS TEXT) AS ssfjdm,
               CAST(sspcs AS TEXT) AS sspcs,
               CAST(sspcsdm AS TEXT) AS sspcsdm
          FROM stdata.b_dic_zzjgdm
         WHERE ssfjdm IN :county_codes
        """
    ).bindparams(bindparam("county_codes", expanding=True))
    try:
        rows = db.execute(stmt, {"county_codes": sorted(county_codes)}).mappings().all()
    except SQLAlchemyError as exc:
        raise ContactImportFatalError(
            "读取 stdata.b_dic_zzjgdm 失败，请确认 Kingbase 中存在该表且当前账号有查询权限。"
        ) from exc

    lookup: dict[str, dict[str, list[StationUnit]]] = {}
    for row in rows:
        unit = StationUnit(
            ssfjdm=str(row["ssfjdm"] or "").strip(),
            sspcs=str(row["sspcs"] or "").strip(),
            sspcsdm=str(row["sspcsdm"] or "").strip(),
        )
        if not unit.ssfjdm or not unit.sspcs or not unit.sspcsdm:
            continue
        lookup.setdefault(unit.ssfjdm, {}).setdefault(normalize_station_key(unit.sspcs), []).append(unit)
    return lookup


def resolve_station(
    row: ImportRow,
    station_lookup: dict[str, dict[str, list[StationUnit]]],
) -> tuple[str | None, str | None, str]:
    fallback_unit_level = "city" if row.sheet == "市局" else "county"
    station_name = normalize_text(row.sspcs)
    if not station_name:
        return None, row.county_code, fallback_unit_level

    if row.sheet == "市局" and normalize_station_key(station_name) in {"市局", "市公安局", "局机关"}:
        return station_name, row.county_code, "city"

    matches = station_lookup.get(row.county_code, {}).get(normalize_station_key(station_name), [])
    if len(matches) == 1:
        unit = matches[0]
        return unit.sspcs, unit.sspcsdm, "station"
    if not matches:
        return station_name, row.county_code, fallback_unit_level
    raise ValueError(f"派出所名称在 stdata.b_dic_zzjgdm 中存在多条匹配：{station_name}")


def find_existing_import_contact(
    db: Session,
    *,
    sspcsdm: str | None,
    county_code: str,
    mobiles: list[str],
    primary_source_pk: str,
) -> OrgContact | None:
    base_stmt = select(OrgContact).options(joinedload(OrgContact.phones)).where(
        OrgContact.source_system == XLSX_CONTACT_IMPORT_SOURCE
    )
    phone_stmt = base_stmt.join(OrgContactPhone).where(OrgContactPhone.mobile.in_(mobiles))
    if sspcsdm:
        phone_stmt = phone_stmt.where(OrgContact.sspcsdm == sspcsdm)
    else:
        phone_stmt = phone_stmt.where(
            OrgContact.sspcsdm.is_(None),
            OrgContact.county_code == county_code,
        )

    contact = db.scalars(phone_stmt).unique().first()
    if contact is not None:
        return contact

    return db.scalars(base_stmt.where(OrgContact.source_pk == primary_source_pk)).unique().one_or_none()


def replace_import_contact_phones(contact: OrgContact, raw_lxdh: str, mobiles: list[str]) -> None:
    existing_by_mobile = {phone.mobile: phone for phone in contact.phones}
    desired_phones: list[OrgContactPhone] = []
    for index, mobile in enumerate(mobiles):
        phone = existing_by_mobile.get(mobile)
        if phone is None:
            phone = OrgContactPhone(mobile=mobile)
        phone.phone_raw = raw_lxdh
        phone.mobile = mobile
        phone.is_primary = index == 0
        phone.status = "active"
        desired_phones.append(phone)
    contact.phones[:] = desired_phones
    contact.raw_lxdh = raw_lxdh


def apply_import_contact_fields(
    contact: OrgContact,
    row: ImportRow,
    *,
    sspcs: str | None,
    sspcsdm: str | None,
    unit_level: str,
    source_pk: str,
) -> None:
    contact.source_system = XLSX_CONTACT_IMPORT_SOURCE
    contact.source_pk = source_pk
    contact.xq = row.xq
    contact.xqdm = derive_xqdm(row.county_code)
    contact.sspcs = sspcs
    contact.sspcsdm = sspcsdm
    contact.city_code = derive_city_code(row.county_code)
    contact.county_code = row.county_code
    contact.unit_level = unit_level
    contact.xm = row.xm
    contact.zw = row.zw
    contact.rwzt = ""
    contact.status = "active"
    contact.remark = normalize_non_null_text_input(row.remark)


def import_contacts_from_xlsx(db: Session, content: bytes, *, filename: str = "") -> dict[str, Any]:
    rows, errors, county_codes = parse_import_rows(content)
    station_lookup = load_station_lookup(db, county_codes)

    created_count = 0
    updated_count = 0
    imported_rows = 0

    for row in rows:
        row_values = {
            "县区": row.xq or "",
            "派出所": row.sspcs or "",
            "姓名": row.xm or "",
            "职务": row.zw or "",
            "电话号码": row.raw_lxdh or "",
            "备注": row.remark or "",
        }
        try:
            if not row.xm:
                raise ValueError("姓名为空。")
            mobiles = extract_mobiles(row.raw_lxdh)
            if not mobiles:
                raise ValueError("电话号码中未找到有效的大陆手机号。")
            sspcs, sspcsdm, unit_level = resolve_station(row, station_lookup)
            source_pk = contact_source_pk(sspcsdm, row.county_code, mobiles[0])
            contact = find_existing_import_contact(
                db,
                sspcsdm=sspcsdm,
                county_code=row.county_code,
                mobiles=mobiles,
                primary_source_pk=source_pk,
            )
            if contact is None:
                contact = OrgContact(source_system=XLSX_CONTACT_IMPORT_SOURCE, source_pk=source_pk)
                db.add(contact)
                created_count += 1
            else:
                updated_count += 1

            apply_import_contact_fields(
                contact,
                row,
                sspcs=sspcs,
                sspcsdm=sspcsdm,
                unit_level=unit_level,
                source_pk=source_pk,
            )
            replace_import_contact_phones(contact, row.raw_lxdh or "", mobiles)
            db.flush()
            imported_rows += 1
        except ValueError as exc:
            errors.append({
                "sheet": row.sheet,
                "row": row.row_number,
                "message": str(exc),
                "values": row_values,
            })

    db.commit()
    return {
        "filename": filename,
        "source_system": XLSX_CONTACT_IMPORT_SOURCE,
        "total_rows": len(rows),
        "imported_rows": imported_rows,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": len(errors),
        "error_count": len(errors),
        "errors": errors[:100],
    }

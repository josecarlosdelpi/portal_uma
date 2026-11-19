"""Leitura das planilhas de carteira de televendas (xlsx e csv).

Formato de referencia (TELEVENDAS - REGIAO ITAJAI):
- uma aba por cidade; a primeira linha traz o nome da cidade;
- a segunda linha traz o cabecalho EMPRESA, CONTATO, CELULAR, PESSOA,
  DATA ANIVER, STATUS, TAG, DATA CONTATO, OBS.;
- abas sem registros (ex.: COP) sao ignoradas;
- a data de contato da planilha NAO representa ultima compra.

O parser nunca descarta nem altera silenciosamente o conteudo lido:
valores nao reconhecidos voltam em *_raw acompanhados de avisos.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from typing import Any

import openpyxl

MAX_ROWS = 5000

HEADERS = {
    "EMPRESA": "name",
    "CONTATO": "phone",
    "CELULAR": "cellphone",
    "PESSOA": "contact_person",
    "DATA ANIVER": "birthday",
    "STATUS": "status",
    "TAG": "tag",
    "DATA CONTATO": "last_contact",
    "OBS": "notes",
    "OBS.": "notes",
}

STATUS_MAP = {
    "ATIVO": "ativo",
    "INATIVO": "inativo",
    "PROSPECT": "prospect",
    "PROSPECTO": "prospect",
}


def _key(text: str) -> str:
    stripped = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in stripped if unicodedata.category(ch) != "Mn")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value).strip()
    return text or None


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def parse_day_month(value: Any) -> tuple[int | None, int | None, str | None]:
    """Aniversario sem ano: aceita datetime ou 'dd/mm' com texto extra."""
    raw = _text(value)
    if raw is None:
        return None, None, None
    if isinstance(value, datetime):
        return value.day, value.month, raw
    match = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", raw)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            return day, month, raw
    return None, None, raw


def parse_date(value: Any) -> tuple[str | None, str | None]:
    """Datas de contato em datetime, 'dd/mm/aaaa', 'dd/mm/aa' ou 'dd-mm-aaaa'."""
    raw = _text(value)
    if raw is None:
        return None, None
    if isinstance(value, datetime):
        return value.date().isoformat(), raw
    match = re.search(r"(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2,4})", raw)
    if match:
        day, month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat(), raw
        except ValueError:
            return None, raw
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        return raw, raw
    return None, raw


def _row_to_record(city: str | None, sheet: str, values: list[Any],
                   columns: dict[int, str], index: int) -> dict:
    fields: dict[str, Any] = {}
    for position, field in columns.items():
        fields[field] = values[position] if position < len(values) else None
    warnings: list[str] = []
    name = _text(fields.get("name"))
    if not name:
        return {}
    birthday_day, birthday_month, birthday_raw = parse_day_month(fields.get("birthday"))
    if birthday_raw and birthday_day is None:
        warnings.append("aniversario_nao_reconhecido")
    last_contact, contact_raw = parse_date(fields.get("last_contact"))
    if contact_raw and last_contact is None:
        warnings.append("data_contato_nao_reconhecida")
    status_raw = _text(fields.get("status"))
    status = STATUS_MAP.get(_key(status_raw).upper()) if status_raw else None
    if status_raw and status is None:
        warnings.append("status_desconhecido")
    return {
        "index": index,
        "sheet": sheet,
        "city": city,
        "name": name,
        "phone": _text(fields.get("phone")),
        "cellphone": _text(fields.get("cellphone")),
        "contact_person": _text(fields.get("contact_person")),
        "birthday_day": birthday_day,
        "birthday_month": birthday_month,
        "birthday_raw": birthday_raw,
        "status": status,
        "status_raw": status_raw,
        "tag": _text(fields.get("tag")),
        "last_contact_on": last_contact,
        "last_contact_raw": contact_raw,
        "notes": _text(fields.get("notes")),
        "warnings": warnings,
    }


def _parse_rows(grid: list[list[Any]], sheet: str, default_city: str | None,
                start_index: int) -> list[dict]:
    """Localiza o cabecalho EMPRESA na grade e extrai os registros."""
    records: list[dict] = []
    header_row = None
    columns: dict[int, str] = {}
    for number, values in enumerate(grid):
        first = _text(values[0]) if values else None
        if first and _key(first).upper() == "EMPRESA":
            header_row = number
            for position, cell in enumerate(values):
                label = _text(cell)
                if label and _key(label).upper() in HEADERS:
                    columns[position] = HEADERS[_key(label).upper()]
            break
    if header_row is None:
        return records
    city = default_city
    for prior in range(header_row):
        candidate = _text(grid[prior][0]) if grid[prior] else None
        if candidate:
            city = candidate
    index = start_index
    for values in grid[header_row + 1:]:
        if not any(_text(cell) for cell in values):
            continue
        record = _row_to_record(city, sheet, values, columns, index)
        if record:
            index += 1
            record["index"] = index
            records.append(record)
        if len(records) > MAX_ROWS:
            raise ValueError(
                f"A aba '{sheet}' excede o limite de {MAX_ROWS} registros. "
                "Divida o arquivo e reenvie — nenhum registro foi importado.")
    return records


def parse_xlsx(data: bytes) -> list[dict]:
    book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    records: list[dict] = []
    index = 0
    for sheet in book.sheetnames:
        grid = [list(row) for row in book[sheet].iter_rows(values_only=True)]
        rows = _parse_rows(grid, sheet, sheet, index)
        if rows:
            index = rows[-1]["index"]
        records.extend(rows)
    return records


def parse_csv(data: bytes, default_city: str | None) -> list[dict]:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Arquivo CSV com codificação não suportada")
    sample = text[:4096]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    grid = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    return _parse_rows(grid, default_city or "CSV", default_city, 0)


def _flag_intra_duplicates(records: list[dict]) -> None:
    """Sinaliza duplicidades dentro do proprio arquivo (nunca decide sozinho)."""
    seen_phones: set[str] = set()
    seen_names: set[tuple[str, str]] = set()
    for record in records:
        flagged = False
        numbers = (digits(record.get("phone")), digits(record.get("cellphone")))
        if any(len(num) >= 8 and num in seen_phones for num in numbers):
            flagged = True
        name_key = _key((record.get("name") or "").lower())
        city_key = _key((record.get("city") or "").lower())
        pair = (name_key, city_key)
        if name_key and pair in seen_names:
            flagged = True
        if flagged and "duplicado_no_arquivo" not in record["warnings"]:
            record["warnings"].append("duplicado_no_arquivo")
        seen_phones.update(num for num in numbers if len(num) >= 8)
        if name_key:
            seen_names.add(pair)


def parse_file(filename: str, data: bytes, default_city: str | None = None) -> list[dict]:
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        records = parse_xlsx(data)
    elif lower.endswith(".csv"):
        records = parse_csv(data, default_city)
    else:
        raise ValueError("Formato não suportado. Envie um arquivo .xlsx ou .csv")
    _flag_intra_duplicates(records)
    return records

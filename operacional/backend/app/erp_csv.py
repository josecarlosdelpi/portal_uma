"""Parser dos CSVs comerciais exportados pelo ERP (Vendas e Devolucoes).

Formato observado em 11/2026: cabecalho, separador ';', data DD/MM/AAAA,
decimais com virgula, terminador CRLF, codificacao ASCII compativel com UTF-8.
Codigos de loja: 1=Joinville, 2=Tubarao, 3=Itajai. CNPJs e codigos de produto
sao preservados como texto (zeros a esquerda e espacos normalizados).
"""
import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

KIND_VENDAS = "VENDAS"
KIND_DEVOLUCOES = "DEVOLUCOES"
KINDS = {KIND_VENDAS, KIND_DEVOLUCOES}

EXPECTED_HEADER = (
    "data;loja;loja_descricao;vendedor;cnpj_cliente;razao_cliente;"
    "produto;quantidade;valor_unitario;valor_total"
).split(";")

STORE_CODE_MAP = {"1": "JOINVILLE", "2": "TUBARAO", "3": "ITAJAI"}

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_STORED_ERRORS = 25
CENT = Decimal("0.02")


@dataclass
class ParsedRow:
    sale_date: date
    store_code: str
    seller_code: str
    customer_cnpj: str
    customer_name: str
    product_code: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    row_hash: str


@dataclass
class ParsedFile:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_lines: int = 0

    @property
    def fatal(self) -> str | None:
        if self.errors and not self.rows:
            return self.errors[0]
        return None


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _decimal(raw: str) -> Decimal:
    value = raw.strip()
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    return Decimal(value)


def _clean(raw: str) -> str:
    return " ".join(raw.split())


def _row_hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def parse_erp_csv(content: bytes) -> ParsedFile:
    """Converte o arquivo em linhas tipadas; nunca descarta linhas identicas."""
    parsed = ParsedFile()
    if not content or len(content) > MAX_FILE_BYTES:
        parsed.errors.append("Arquivo vazio ou acima do limite de 10 MB.")
        return parsed

    text = _decode(content)
    reader = csv.reader(io.StringIO(text), delimiter=";")
    try:
        header = next(reader)
    except StopIteration:
        parsed.errors.append("Arquivo sem cabeçalho.")
        return parsed
    normalized = [cell.strip().lower() for cell in header]
    if normalized != EXPECTED_HEADER:
        parsed.errors.append(
            "Cabeçalho divergente do layout oficial do ERP: " + ";".join(normalized)
        )
        return parsed

    for number, fields in enumerate(reader, start=2):
        if not fields or all(not cell.strip() for cell in fields):
            continue
        parsed.total_lines += 1
        if len(fields) != len(EXPECTED_HEADER):
            parsed.errors.append(f"Linha {number}: {len(fields)} colunas, esperado 10.")
            continue
        try:
            sale_date = datetime.strptime(fields[0].strip(), "%d/%m/%Y").date()
        except ValueError:
            parsed.errors.append(f"Linha {number}: data inválida '{fields[0].strip()}'.")
            continue
        store_code = STORE_CODE_MAP.get(fields[1].strip())
        if store_code is None:
            parsed.errors.append(f"Linha {number}: loja desconhecida '{fields[1].strip()}'.")
            continue
        try:
            quantity = _decimal(fields[7])
            unit_price = _decimal(fields[8])
            total = _decimal(fields[9])
        except (InvalidOperation, ValueError):
            parsed.errors.append(f"Linha {number}: valor numérico inválido.")
            continue
        if quantity < 0 or total < 0 or unit_price < 0:
            parsed.errors.append(f"Linha {number}: valor negativo não aceito.")
            continue
        if abs(quantity * unit_price - total) > CENT:
            parsed.warnings.append(
                f"Linha {number}: quantidade x unitário difere do total em mais de R$ 0,02."
            )
        parts = [
            sale_date.isoformat(), store_code, _clean(fields[3]), _clean(fields[4]),
            _clean(fields[5]), _clean(fields[6]),
            str(quantity), str(unit_price), str(total),
        ]
        parsed.rows.append(ParsedRow(
            sale_date=sale_date,
            store_code=store_code,
            seller_code=_clean(fields[3]) or "0",
            customer_cnpj=_clean(fields[4]),
            customer_name=_clean(fields[5]),
            product_code=_clean(fields[6]),
            quantity=quantity,
            unit_price=unit_price,
            total=total,
            row_hash=_row_hash(parts),
        ))

    if parsed.errors and len(parsed.errors) > MAX_STORED_ERRORS:
        extra = len(parsed.errors) - MAX_STORED_ERRORS
        parsed.errors = parsed.errors[:MAX_STORED_ERRORS]
        parsed.errors.append(f"... e mais {extra} linhas com erro.")
    return parsed

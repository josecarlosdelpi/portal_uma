"""Parser dos CSVs comerciais exportados pelo ERP (Vendas e Devolucoes).

Formato observado em 11/2026: cabecalho, separador ';', data DD/MM/AAAA,
decimais com virgula, codificacao ASCII compativel com UTF-8. Codigos de
loja: 1=Joinville, 2=Tubarao, 3=Itajai. CNPJs e codigos sao preservados
como texto (zeros a esquerda e espacos normalizados).

Dois layouts sao aceitos por kind (deteccao pelo cabecalho):
- v1 (10 colunas): layout original de Vendas.csv e Devolucoes.csv;
- v2: Vendas.csv com 14 colunas (id/nome do vendedor, id/descricao/unidade
  do produto, custo unitario) e Devolucoes.csv com 11 colunas (sem
  vendedor, com descricao/unidade do produto).

Quebras de linha: a exportacao do ERP deveria usar CRLF, mas ja foi
observado CR solitario (estilo Mac antigo). Todo texto e normalizado
para '\n' antes da leitura — variante de fim de linha padrao, sem
reconstrucao de registros; a validacao estrutural permanece completa.
"""
import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

KIND_VENDAS = "VENDAS"
KIND_DEVOLUCOES = "DEVOLUCOES"
KIND_DESPESAS = "DESPESAS"
KINDS = {KIND_VENDAS, KIND_DEVOLUCOES}

HEADER_V1 = (
    "data;loja;loja_descricao;vendedor;cnpj_cliente;razao_cliente;"
    "produto;quantidade;valor_unitario;valor_total"
).split(";")
HEADER_VENDAS_V2 = (
    "data;loja;loja_descricao;id_vendedor;nome_vendedor;cnpj_cliente;"
    "razao_cliente;id_produto;produto_descricao;produto_unidade;"
    "quantidade;valor_unitario;valor_total;custo_unitario"
).split(";")
HEADER_DEVOLUCOES_V2 = (
    "data;loja;loja_descricao;cnpj_cliente;razao_cliente;id_produto;"
    "produto_descricao;produto_unidade;quantidade;valor_unitario;valor_total"
).split(";")
EXPECTED_HEADER = HEADER_V1  # compatibilidade com importacoes antigas

# Indices por nome canonico dentro de cada layout aceito.
_LAYOUT_V1 = {
    "header": HEADER_V1,
    "idx": {"date": 0, "store": 1, "seller": 3, "customer_doc": 4,
            "customer_name": 5, "product": 6, "qty": 7, "unit_price": 8,
            "total": 9},
}
_LAYOUT_VENDAS_V2 = {
    "header": HEADER_VENDAS_V2,
    "idx": {"date": 0, "store": 1, "seller": 3, "seller_name": 4,
            "customer_doc": 5, "customer_name": 6, "product": 7,
            "product_desc": 8, "product_unit": 9, "qty": 10,
            "unit_price": 11, "total": 12, "unit_cost": 13},
}
_LAYOUT_DEVOLUCOES_V2 = {
    "header": HEADER_DEVOLUCOES_V2,
    "idx": {"date": 0, "store": 1, "customer_doc": 3, "customer_name": 4,
            "product": 5, "product_desc": 6, "product_unit": 7, "qty": 8,
            "unit_price": 9, "total": 10},
}
EXPECTED_LAYOUTS = {
    KIND_VENDAS: [_LAYOUT_V1, _LAYOUT_VENDAS_V2],
    KIND_DEVOLUCOES: [_LAYOUT_V1, _LAYOUT_DEVOLUCOES_V2],
}

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
    seller_name: str | None = None
    product_description: str | None = None
    product_unit: str | None = None
    unit_cost: Decimal | None = None


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
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    # O ERP ja exportou com CR solitario como separador de linha
    # (Devolucoes.csv, 11/2026): normaliza CRLF e CR para '\n'.
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _decimal(raw: str) -> Decimal:
    value = raw.strip()
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    return Decimal(value)


def _clean(raw: str) -> str:
    return " ".join(raw.split())


def _optional_decimal(raw: str) -> Decimal | None:
    if not raw.strip():
        return None
    return _decimal(raw)


def _row_hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def parse_erp_csv(content: bytes, kind: str = KIND_VENDAS) -> ParsedFile:
    """Converte o arquivo em linhas tipadas; nunca descarta linhas identicas."""
    parsed = ParsedFile()
    if not content or len(content) > MAX_FILE_BYTES:
        parsed.errors.append("Arquivo vazio ou acima do limite de 10 MB.")
        return parsed

    layouts = EXPECTED_LAYOUTS.get(kind)
    if layouts is None:
        parsed.errors.append(f"Tipo de arquivo sem layout definido: {kind}.")
        return parsed

    text = _decode(content)
    reader = csv.reader(io.StringIO(text), delimiter=";")
    try:
        header = next(reader)
    except StopIteration:
        parsed.errors.append("Arquivo sem cabeçalho.")
        return parsed
    normalized = [cell.strip().lower() for cell in header]
    layout = next(
        (candidate for candidate in layouts if candidate["header"] == normalized),
        None,
    )
    if layout is None:
        parsed.errors.append(
            "Cabeçalho divergente dos layouts oficiais do ERP: " + ";".join(normalized)
        )
        return parsed

    idx = layout["idx"]
    expected_cols = len(layout["header"])

    def field(fields: list[str], key: str) -> str:
        position = idx.get(key)
        return fields[position] if position is not None else ""

    for number, fields in enumerate(reader, start=2):
        if not fields or all(not cell.strip() for cell in fields):
            continue
        parsed.total_lines += 1
        if len(fields) != expected_cols:
            parsed.errors.append(
                f"Linha {number}: {len(fields)} colunas, esperado {expected_cols}."
            )
            continue
        try:
            sale_date = datetime.strptime(
                field(fields, "date").strip(), "%d/%m/%Y"
            ).date()
        except ValueError:
            parsed.errors.append(
                f"Linha {number}: data inválida '{field(fields, 'date').strip()}'."
            )
            continue
        store_code = STORE_CODE_MAP.get(field(fields, "store").strip())
        if store_code is None:
            parsed.errors.append(
                f"Linha {number}: loja desconhecida '{field(fields, 'store').strip()}'."
            )
            continue
        try:
            quantity = _decimal(field(fields, "qty"))
            unit_price = _decimal(field(fields, "unit_price"))
            total = _decimal(field(fields, "total"))
            unit_cost = _optional_decimal(field(fields, "unit_cost"))
        except (InvalidOperation, ValueError):
            parsed.errors.append(f"Linha {number}: valor numérico inválido.")
            continue
        if quantity < 0 or total < 0 or unit_price < 0 or (unit_cost or 0) < 0:
            parsed.errors.append(f"Linha {number}: valor negativo não aceito.")
            continue
        if abs(quantity * unit_price - total) > CENT:
            parsed.warnings.append(
                f"Linha {number}: quantidade x unitário difere do total em mais de R$ 0,02."
            )
        parts = [
            sale_date.isoformat(), store_code, _clean(field(fields, "seller")),
            _clean(field(fields, "customer_doc")), _clean(field(fields, "customer_name")),
            _clean(field(fields, "product")), _clean(field(fields, "seller_name")),
            _clean(field(fields, "product_desc")), _clean(field(fields, "product_unit")),
            str(quantity), str(unit_price), str(total), str(unit_cost or ""),
        ]
        parsed.rows.append(ParsedRow(
            sale_date=sale_date,
            store_code=store_code,
            seller_code=_clean(field(fields, "seller")) or "0",
            customer_cnpj=_clean(field(fields, "customer_doc")),
            customer_name=_clean(field(fields, "customer_name")),
            product_code=_clean(field(fields, "product")),
            quantity=quantity,
            unit_price=unit_price,
            total=total,
            row_hash=_row_hash(parts),
            seller_name=_clean(field(fields, "seller_name")) or None,
            product_description=_clean(field(fields, "product_desc")) or None,
            product_unit=_clean(field(fields, "product_unit")) or None,
            unit_cost=unit_cost,
        ))

    if parsed.errors and len(parsed.errors) > MAX_STORED_ERRORS:
        extra = len(parsed.errors) - MAX_STORED_ERRORS
        parsed.errors = parsed.errors[:MAX_STORED_ERRORS]
        parsed.errors.append(f"... e mais {extra} linhas com erro.")
    return parsed

"""Parser do Despesas.csv do ERP (Frente B: despesas e pagamentos).

Formato inspecionado em 11/11/2026:
- cabecalho obrigatorio, separador ';', decimais com ',', datas DD/MM/AAAA;
- cnpj_fornecedor aceita CNPJ (14), CPF (11) ou vazio (obrigacoes fiscais
  como GPS, Simples Nacional e financiamentos);
- loja: 1=Joinville, 2=Tubarao, 3=Itajai;
- situacao 'Pago' exige dt_pagamento preenchida; 'Aberto' exige vazia.

Linhas aparentemente duplicadas sao lancamentos legitimos: nunca deduplicar.
"""
import csv
import io
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

EXPECTED_HEADER = [
    "cnpj_fornecedor", "nome_fornecedor", "valor", "dt_vencimento",
    "dt_pagamento", "categoria", "loja", "loja_descricao", "situacao",
]

STORE_BY_NUMBER = {"1": "JOINVILLE", "2": "TUBARAO", "3": "ITAJAI"}
STORE_LABEL_KEY = {"JOINVILLE": "joinville", "TUBARAO": "tubarao", "ITAJAI": "itajai"}

CATEGORY_BY_LABEL = {
    "despesa": "despesa",
    "compra p/ revenda": "compra_revenda",
    "compra p revenda": "compra_revenda",
}
STATUS_BY_LABEL = {"pago": "pago", "aberto": "aberto"}

MAX_ERRORS = 30
MAX_FIELD = 400


class ImportFormatError(Exception):
    """Arquivo fora do contrato; o lote inteiro e rejeitado, nada e importado."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors[:5]))


@dataclass(frozen=True)
class ParsedRow:
    source_row: int
    supplier_doc: str | None
    supplier_name: str
    amount: Decimal
    due_date: date
    paid_at: date | None
    category: str
    store_code: str
    status: str


@dataclass
class QualityFlag:
    row: int
    code: str
    detail: str

    def as_dict(self) -> dict:
        return {"row": self.row, "code": self.code, "detail": self.detail}


@dataclass
class ParsedDespesas:
    rows: list[ParsedRow]
    flags: list[QualityFlag] = field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None


def _norm_text(value: str) -> str:
    folded = "".join(
        char for char in unicodedata.normalize("NFD", value.casefold().strip())
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(folded.split())


def parse_amount(raw: str, row: int) -> Decimal:
    text = raw.strip().replace("R$", "").replace(" ", "")
    if not text:
        raise ValueError(f"linha {row}: valor vazio")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"linha {row}: valor invalido '{raw.strip()}'") from exc
    if amount < 0:
        raise ValueError(f"linha {row}: valor negativo")
    if amount > Decimal("999999999999.99"):
        raise ValueError(f"linha {row}: valor acima do limite")
    return amount.quantize(Decimal("0.01"))


def parse_date(raw: str, row: int, field_name: str) -> date:
    text = raw.strip()
    try:
        day, month, year = (int(part) for part in text.split("/"))
        return date(year, month, day)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"linha {row}: {field_name} invalida '{text}'") from exc


def parse_despesas(payload: bytes, today: date | None = None) -> ParsedDespesas:
    """Valida e tipa todas as linhas; qualquer erro estrutural rejeita o lote."""
    today = today or date.today()
    errors: list[str] = []

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = payload.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise ImportFormatError(["arquivo nao esta em codificacao de texto legivel"]) from exc

    reader = csv.reader(io.StringIO(text), delimiter=";")
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ImportFormatError(["arquivo vazio"]) from exc

    normalized_header = [_norm_text(col).replace(" ", "_") for col in header]
    if normalized_header != EXPECTED_HEADER:
        raise ImportFormatError([
            "cabecalho fora do contrato Despesas.csv: "
            + ";".join(EXPECTED_HEADER)
        ])

    rows: list[ParsedRow] = []
    flags: list[QualityFlag] = []

    def fail(message: str) -> None:
        errors.append(message)
        if len(errors) >= MAX_ERRORS:
            raise ImportFormatError(errors + ["..."])

    for number, columns in enumerate(reader, start=2):
        if not columns or all(not col.strip() for col in columns):
            continue
        if len(columns) != len(EXPECTED_HEADER):
            fail(f"linha {number}: esperadas 9 colunas, encontradas {len(columns)}")
            continue
        raw = [col.strip()[:MAX_FIELD] for col in columns]
        try:
            amount = parse_amount(raw[2], number)
            due = parse_date(raw[3], number, "dt_vencimento")
            paid = parse_date(raw[4], number, "dt_pagamento") if raw[4] else None
        except ValueError as exc:
            fail(str(exc))
            continue

        category = CATEGORY_BY_LABEL.get(_norm_text(raw[5]))
        if category is None:
            fail(f"linha {number}: categoria desconhecida '{raw[5]}'")
            continue
        store = STORE_BY_NUMBER.get(raw[6])
        if store is None:
            fail(f"linha {number}: loja desconhecida '{raw[6]}'")
            continue
        status = STATUS_BY_LABEL.get(_norm_text(raw[8]))
        if status is None:
            fail(f"linha {number}: situacao desconhecida '{raw[8]}'")
            continue
        if not raw[1]:
            fail(f"linha {number}: nome_fornecedor vazio")
            continue
        if (status == "pago") != (paid is not None):
            fail(f"linha {number}: situacao '{raw[8]}' incoerente com dt_pagamento")
            continue

        doc = raw[0] or None
        label = _norm_text(raw[7])
        if label and label != STORE_LABEL_KEY[store]:
            flags.append(QualityFlag(
                number, "loja_descricao_divergente",
                f"descricao '{raw[7][:40]}' diverge do codigo de loja"))
        if doc is None:
            flags.append(QualityFlag(number, "fornecedor_sem_documento",
                                     "cnpj/cpf do fornecedor ausente"))
        elif len(doc) not in (11, 14) or not doc.isdigit():
            flags.append(QualityFlag(number, "documento_atipico",
                                     "documento fora dos padroes CPF(11)/CNPJ(14)"))
        if paid is not None and paid < due:
            flags.append(QualityFlag(number, "pago_antes_do_vencimento",
                                     "pagamento anterior ao vencimento"))
        if due.year > today.year + 1:
            flags.append(QualityFlag(number, "vencimento_distante",
                                     "vencimento mais de um ano alem da data atual"))
        if amount == 0:
            flags.append(QualityFlag(number, "valor_zerado", "valor igual a zero"))

        rows.append(ParsedRow(
            source_row=number, supplier_doc=doc,
            supplier_name=" ".join(raw[1].split())[:200],
            amount=amount, due_date=due, paid_at=paid,
            category=category, store_code=store, status=status,
        ))

    if errors:
        raise ImportFormatError(errors)
    if not rows:
        raise ImportFormatError(["arquivo sem linhas de dados"])

    dates = [row.due_date for row in rows]
    return ParsedDespesas(
        rows=rows, flags=flags,
        period_start=min(dates), period_end=max(dates),
    )

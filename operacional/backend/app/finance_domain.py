"""Parser do Despesas.csv do ERP (Frente B: despesas e pagamentos).

Formato inspecionado em 11/11/2026:
- cabecalho obrigatorio, separador ';', decimais com ',', datas DD/MM/AAAA;
- cnpj_fornecedor aceita CNPJ (14), CPF (11) ou vazio (obrigacoes fiscais
  como GPS, Simples Nacional e financiamentos);
- loja: 1=Joinville, 2=Tubarao, 3=Itajai;
- situacao 'Pago' exige dt_pagamento preenchida; 'Aberto' exige vazia.

Layouts aceitos (deteccao pelo cabecalho):
- v1 (9 colunas): layout original;
- v2 (17 colunas): nr_documento, nr_parcela, dt_emissao, valor_original,
  acrescimos, descontos, valor_liquido e plano de contas. Em v2, 'amount'
  do dominio recebe o valor_liquido; os componentes ficam preservados.
Quebras de linha: normalizadas para '\n' antes da leitura — o ERP ja
exportou outros arquivos com CR solitario.

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
EXPECTED_HEADER_V2 = [
    "loja", "loja_descricao", "nr_documento", "nr_parcela", "cnpj_fornecedor",
    "nome_fornecedor", "dt_emissao", "dt_vencimento", "dt_pagamento",
    "valor_original", "acrescimos", "descontos", "valor_liquido",
    "categoria", "nr_conta", "descricao_conta", "situacao",
]

_LAYOUT_V1 = {
    "header": EXPECTED_HEADER,
    "idx": {"doc": 0, "name": 1, "amount": 2, "due": 3, "paid": 4,
            "category": 5, "store": 6, "store_label": 7, "status": 8},
}
_LAYOUT_V2 = {
    "header": EXPECTED_HEADER_V2,
    "idx": {"store": 0, "store_label": 1, "doc_number": 2, "installment": 3,
            "doc": 4, "name": 5, "issued": 6, "due": 7, "paid": 8,
            "original": 9, "additions": 10, "discounts": 11, "amount": 12,
            "category": 13, "account": 14, "account_desc": 15, "status": 16},
}
LAYOUTS = [_LAYOUT_V1, _LAYOUT_V2]

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
    document_number: str | None = None
    installment_number: str | None = None
    issued_at: date | None = None
    original_amount: Decimal | None = None
    additions: Decimal | None = None
    discounts: Decimal | None = None
    account_code: str | None = None
    account_description: str | None = None


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
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    reader = csv.reader(io.StringIO(text), delimiter=";")
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ImportFormatError(["arquivo vazio"]) from exc

    normalized_header = [_norm_text(col).replace(" ", "_") for col in header]
    layout = next(
        (candidate for candidate in LAYOUTS if candidate["header"] == normalized_header),
        None,
    )
    if layout is None:
        raise ImportFormatError([
            "cabecalho fora do contrato Despesas.csv: "
            + ";".join(normalized_header)
        ])

    idx = layout["idx"]
    expected_cols = len(layout["header"])

    def at(columns: list[str], key: str) -> str:
        position = idx.get(key)
        return columns[position] if position is not None else ""

    rows: list[ParsedRow] = []
    flags: list[QualityFlag] = []

    def fail(message: str) -> None:
        errors.append(message)
        if len(errors) >= MAX_ERRORS:
            raise ImportFormatError(errors + ["..."])

    for number, columns in enumerate(reader, start=2):
        if not columns or all(not col.strip() for col in columns):
            continue
        if len(columns) != expected_cols:
            fail(f"linha {number}: esperadas {expected_cols} colunas, encontradas {len(columns)}")
            continue
        raw = [col.strip()[:MAX_FIELD] for col in columns]
        try:
            amount = parse_amount(at(raw, "amount"), number)
            due = parse_date(at(raw, "due"), number, "dt_vencimento")
            paid = parse_date(at(raw, "paid"), number, "dt_pagamento") if at(raw, "paid") else None
            issued = parse_date(at(raw, "issued"), number, "dt_emissao") if at(raw, "issued") else None
            original = parse_amount(at(raw, "original"), number) if at(raw, "original") else None
            additions = parse_amount(at(raw, "additions"), number) if at(raw, "additions") else None
            discounts = parse_amount(at(raw, "discounts"), number) if at(raw, "discounts") else None
        except ValueError as exc:
            fail(str(exc))
            continue

        category = CATEGORY_BY_LABEL.get(_norm_text(at(raw, "category")))
        if category is None:
            fail(f"linha {number}: categoria desconhecida '{at(raw, 'category')}'")
            continue
        store = STORE_BY_NUMBER.get(at(raw, "store"))
        if store is None:
            fail(f"linha {number}: loja desconhecida '{at(raw, 'store')}'")
            continue
        status = STATUS_BY_LABEL.get(_norm_text(at(raw, "status")))
        if status is None:
            fail(f"linha {number}: situacao desconhecida '{at(raw, 'status')}'")
            continue
        if not at(raw, "name"):
            fail(f"linha {number}: nome_fornecedor vazio")
            continue
        if (status == "pago") != (paid is not None):
            fail(f"linha {number}: situacao '{at(raw, 'status')}' incoerente com dt_pagamento")
            continue

        doc = at(raw, "doc") or None
        label = _norm_text(at(raw, "store_label"))
        if label and label != STORE_LABEL_KEY[store]:
            flags.append(QualityFlag(
                number, "loja_descricao_divergente",
                f"descricao '{at(raw, 'store_label')[:40]}' diverge do codigo de loja"))
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
        if None not in (original, additions, discounts) and (
            abs(original + additions - discounts - amount) > Decimal("0.02")
        ):
            flags.append(QualityFlag(
                number, "valor_liquido_divergente",
                "valor_liquido difere de original + acrescimos - descontos"))

        rows.append(ParsedRow(
            source_row=number, supplier_doc=doc,
            supplier_name=" ".join(at(raw, "name").split())[:200],
            amount=amount, due_date=due, paid_at=paid,
            category=category, store_code=store, status=status,
            document_number=at(raw, "doc_number") or None,
            installment_number=at(raw, "installment") or None,
            issued_at=issued,
            original_amount=original, additions=additions, discounts=discounts,
            account_code=at(raw, "account") or None,
            account_description=at(raw, "account_desc") or None,
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

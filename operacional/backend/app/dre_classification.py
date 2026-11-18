"""Classificacao gerencial preliminar das obrigacoes do ERP (DRE).

Regras separadas do calculo, versionadas e testadas. A precedencia segue a
diretriz aprovada:

1. Barreira de seguranca: categoria 'compra_revenda' fica fora das despesas
   da DRE, independentemente do codigo de conta;
2. Excecao especifica: combinacao de conta + fornecedor normalizado
   (ex.: conta 67, que e mista e nunca classificada integralmente);
3. Regra pelo codigo de conta;
4. A CLASSIFICAR — nada e descartado silenciosamente.

O mapeamento inicial (DEFAULT_RULES) e provisorio e revisavel; a mesma
semente alimenta a tabela dre_classification_rules (migration 0025), que
passa a valer quando contiver regras ativas. Nenhum mapeamento e verdade
contabil apenas por conter determinado nome.
"""
import unicodedata
from dataclasses import dataclass

# Buckets de destino da classificacao gerencial.
BUCKET_DESPESA_COMERCIAL = "despesa_comercial"
BUCKET_DESPESA_OPERACIONAL = "despesa_operacional"
BUCKET_DAS = "das_identificado"
BUCKET_COMPRA_REVENDA = "compra_revenda"
BUCKET_FINANCIAMENTO = "financiamento"
BUCKET_IMOBILIZADO = "imobilizado"
BUCKET_A_CLASSIFICAR = "a_classificar"

BUCKETS = (
    BUCKET_DESPESA_COMERCIAL, BUCKET_DESPESA_OPERACIONAL, BUCKET_DAS,
    BUCKET_COMPRA_REVENDA, BUCKET_FINANCIAMENTO, BUCKET_IMOBILIZADO,
    BUCKET_A_CLASSIFICAR,
)
# Entram no saldo gerencial parcial; os demais ficam no quadro de excluidos.
RESULT_BUCKETS = frozenset({
    BUCKET_DESPESA_COMERCIAL, BUCKET_DESPESA_OPERACIONAL, BUCKET_DAS,
})
# Quadro "Fora da DRE / A classificar" — sempre visivel, nunca somado.
EXCLUDED_BUCKETS = (
    BUCKET_COMPRA_REVENDA, BUCKET_FINANCIAMENTO, BUCKET_IMOBILIZADO,
    BUCKET_A_CLASSIFICAR,
)

# Alocacao economica: loja registrada no ERP, compartilhado/nao distribuido
# ou revisao pendente. Nunca ha rateio automatico entre lojas.
ALLOC_ERP_STORE = "erp_store"
ALLOC_SHARED = "shared"
ALLOC_PENDING = "pending_review"

SHARED_COLUMN = "COMPARTILHADO"
TOTAL_COLUMN = "UMA"

BUCKET_LABELS = {
    BUCKET_DESPESA_COMERCIAL: "Despesas comerciais",
    BUCKET_DESPESA_OPERACIONAL: "Despesas operacionais e pessoal",
    BUCKET_DAS: "DAS identificado",
    BUCKET_COMPRA_REVENDA: "Compras para revenda",
    BUCKET_FINANCIAMENTO: "Financiamentos / amortizacoes",
    BUCKET_IMOBILIZADO: "Aquisicao de imobilizado",
    BUCKET_A_CLASSIFICAR: "A classificar",
}


@dataclass(frozen=True)
class ClassificationRule:
    account_code: str | None
    supplier_pattern: str | None
    bucket: str
    allocation: str = ALLOC_ERP_STORE
    note: str = ""


@dataclass(frozen=True)
class Classification:
    bucket: str
    allocation: str
    rule: ClassificationRule | None
    reason: str  # barreira_categoria | excecao_fornecedor | codigo_conta | sem_regra


def normalize_text(value: str | None) -> str:
    """Mesma normalizacao do parser de despesas: casefold + sem acentos."""
    folded = "".join(
        char for char in unicodedata.normalize("NFD", (value or "").casefold().strip())
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(folded.split())


def normalize_account(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


# Mapeamento inicial aprovado (17/11/2026) — provisorio e revisavel.
# Conta 67 nunca e classificada integralmente: somente as excecoes por
# fornecedor entram; todo o restante permanece A CLASSIFICAR.
DEFAULT_RULES: tuple[ClassificationRule, ...] = (
    # -- excecoes obrigatorias da conta 67 (avaliadas antes do codigo) --
    ClassificationRule(
        "67", "guia simples nacional das", BUCKET_DAS, ALLOC_SHARED,
        "Conta 67: DAS por vencimento, consolidado — referencia tributaria provisoria"),
    ClassificationRule(
        "67", "fundo de garantia", BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
        "Conta 67: FGTS como despesa de pessoal preliminar"),
    # -- fora do resultado gerencial --
    ClassificationRule(
        "80", None, BUCKET_COMPRA_REVENDA, ALLOC_ERP_STORE,
        "Compra para revenda — fora das despesas da DRE (nao duplica CMV)"),
    ClassificationRule(
        "15", None, BUCKET_FINANCIAMENTO, ALLOC_ERP_STORE,
        "Financiamento — fora do calculo ate segregar juros e principal"),
    ClassificationRule(
        "26", None, BUCKET_FINANCIAMENTO, ALLOC_ERP_STORE,
        "Financiamento — fora do calculo ate segregar juros e principal"),
    ClassificationRule(
        "97", None, BUCKET_FINANCIAMENTO, ALLOC_ERP_STORE,
        "Amortizacao — fora do calculo ate segregar juros e principal"),
    ClassificationRule(
        "21", None, BUCKET_IMOBILIZADO, ALLOC_ERP_STORE,
        "Aquisicao de imobilizado — quadro de investimentos, sem depreciacao"),
    ClassificationRule(
        "22", None, BUCKET_IMOBILIZADO, ALLOC_ERP_STORE,
        "Aquisicao de imobilizado — quadro de investimentos, sem depreciacao"),
    # -- despesas comerciais preliminares --
    ClassificationRule("50", None, BUCKET_DESPESA_COMERCIAL, ALLOC_ERP_STORE,
                       "Fretes sobre vendas — despesa comercial preliminar"),
    ClassificationRule("44", None, BUCKET_DESPESA_COMERCIAL, ALLOC_ERP_STORE,
                       "Marketing — despesa comercial preliminar"),
    ClassificationRule("129", None, BUCKET_DESPESA_COMERCIAL, ALLOC_ERP_STORE,
                       "Brindes — despesa comercial preliminar"),
    # -- despesas operacionais preliminares --
    ClassificationRule("60", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Pessoal — preliminar; folha/provisoes nao reconciliadas"),
    ClassificationRule("70", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Pessoal — preliminar; folha/provisoes nao reconciliadas"),
    ClassificationRule("65", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Pessoal/beneficios — preliminar"),
    ClassificationRule("27", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Aluguel — operacional preliminar pela loja do ERP"),
    ClassificationRule("25", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Agua — operacional preliminar pela loja do ERP"),
    ClassificationRule("29", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Energia — operacional preliminar pela loja do ERP"),
    ClassificationRule("30", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Internet — operacional preliminar pela loja do ERP"),
    ClassificationRule("31", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "IPTU — operacional preliminar pela loja do ERP"),
    ClassificationRule("43", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Telefones — operacional preliminar pela loja do ERP"),
    ClassificationRule("75", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Contabilidade — operacional preliminar; revisar uso compartilhado"),
    ClassificationRule("76", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Manutencao — operacional preliminar; revisar uso compartilhado"),
    ClassificationRule("77", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Manutencao — operacional preliminar; revisar uso compartilhado"),
    ClassificationRule("78", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Seguranca — operacional preliminar; revisar uso compartilhado"),
    ClassificationRule("126", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Advocacia — operacional preliminar; revisar uso compartilhado"),
    ClassificationRule("73", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Terceiros — operacional preliminar; revisar uso compartilhado"),
    ClassificationRule("130", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Viagens — operacional preliminar; revisar uso compartilhado"),
    ClassificationRule("36", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Copa — operacional preliminar"),
    ClassificationRule("37", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Expediente — operacional preliminar"),
    ClassificationRule("38", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Limpeza — operacional preliminar"),
    ClassificationRule("33", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Refeicoes — operacional preliminar"),
    ClassificationRule("63", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Confraternizacoes — operacional preliminar"),
    ClassificationRule("40", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Seguros — operacional preliminar"),
    ClassificationRule("41", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Seguros — operacional preliminar"),
    ClassificationRule("72", None, BUCKET_DESPESA_OPERACIONAL, ALLOC_ERP_STORE,
                       "Seguros — operacional preliminar"),
    # -- conta mista e tributos nao confiaveis --
    ClassificationRule(
        "67", None, BUCKET_A_CLASSIFICAR, ALLOC_PENDING,
        "Conta 67 mista (GPS/INSS/IRRF/repasses) — pendente de revisao"),
    ClassificationRule("94", None, BUCKET_A_CLASSIFICAR, ALLOC_PENDING,
                       "Tributos/taxas — pendente de revisao"),
    ClassificationRule("86", None, BUCKET_A_CLASSIFICAR, ALLOC_PENDING,
                       "Tributos/taxas — pendente de revisao"),
    ClassificationRule("0", None, BUCKET_A_CLASSIFICAR, ALLOC_PENDING,
                       "Sem conta confiavel — pendente de revisao"),
)


def classify(
    *, category: str, account_code: str | None, supplier_name: str | None,
    rules: tuple[ClassificationRule, ...] | list[ClassificationRule] = DEFAULT_RULES,
) -> Classification:
    """Classifica uma obrigacao conforme a precedencia da diretriz."""
    code = normalize_account(account_code)
    supplier = normalize_text(supplier_name)

    # (a) Barreira de seguranca: compra para revenda nunca e despesa da DRE.
    if category == "compra_revenda":
        return Classification(BUCKET_COMPRA_REVENDA, ALLOC_ERP_STORE, None,
                              "barreira_categoria")

    # Ordem deterministica: excecoes com conta antes das genericas e padroes
    # mais longos antes dos curtos — nao depende da ordem de gravacao.
    ordered = sorted(
        rules,
        key=lambda rule: (
            0 if rule.account_code is not None else 1,
            -len(rule.supplier_pattern or ""),
        ),
    )

    # (b) Excecao por combinacao conta + fornecedor normalizado.
    for rule in ordered:
        if rule.supplier_pattern is None:
            continue
        if rule.account_code is not None and rule.account_code != code:
            continue
        if normalize_text(rule.supplier_pattern) in supplier:
            return Classification(rule.bucket, rule.allocation, rule,
                                  "excecao_fornecedor")

    # (c) Regra pelo codigo de conta.
    for rule in rules:
        if rule.supplier_pattern is not None:
            continue
        if rule.account_code is not None and rule.account_code == code:
            return Classification(rule.bucket, rule.allocation, rule,
                                  "codigo_conta")

    # (d) A CLASSIFICAR: codigo novo ou ausente nunca e descartado.
    return Classification(BUCKET_A_CLASSIFICAR, ALLOC_PENDING, None, "sem_regra")

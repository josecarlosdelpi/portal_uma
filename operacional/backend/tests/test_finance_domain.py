"""Parser do Despesas.csv: formato BR, cardinalidade e flags de qualidade.

Todos os dados sao ficticios; nunca usar CNPJ/CPF/nomes reais em fixtures.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.finance_domain import ImportFormatError, parse_amount, parse_despesas

HEADER = ("cnpj_fornecedor;nome_fornecedor;valor;dt_vencimento;dt_pagamento;"
          "categoria;loja;loja_descricao;situacao\n")

VALID = HEADER + (
    "11111111000100;FORNECEDOR ALFA LTDA;1000,50;05/10/2026;05/10/2026;Compra p/ Revenda;1;Joinville;Pago\n"
    "22222222000100;FORNECEDOR BETA SA;250;10/11/2026;;Despesa;2;Tubarao;Aberto\n"
    ";GUIA IMPOSTO FICTICIO;300;20/11/2026;20/11/2026;Despesa;1;Joinville;Pago\n"
    "11111111000100;FORNECEDOR ALFA LTDA;1000,50;05/10/2026;05/10/2026;Compra p/ Revenda;1;Joinville;Pago\n"
    "33333333000100;FORNECEDOR GAMMA;99,90;15/12/2026;;Compra p/ Revenda;3;Itajai;Aberto\n"
)


def test_parse_valido_preserva_cardinalidade_e_tipos():
    parsed = parse_despesas(VALID.encode())
    assert len(parsed.rows) == 5  # linha identica e lancamento legitimo
    assert parsed.rows[0].amount == Decimal("1000.50")
    assert parsed.rows[0].category == "compra_revenda"
    assert parsed.rows[0].store_code == "JOINVILLE"
    assert parsed.rows[1].status == "aberto" and parsed.rows[1].paid_at is None
    assert parsed.rows[2].supplier_doc is None  # obrigacao fiscal sem documento
    assert parsed.period_start == date(2026, 10, 5)
    assert parsed.period_end == date(2026, 12, 15)


def test_flags_de_qualidade_nao_bloqueiam():
    parsed = parse_despesas(VALID.encode())
    codes = {flag.code for flag in parsed.flags}
    assert "fornecedor_sem_documento" in codes


def test_flag_pago_antes_do_vencimento_e_vencimento_distante():
    content = HEADER + (
        "44444444000100;FORNECEDOR DELTA;100;10/11/2026;01/11/2026;Despesa;1;Joinville;Pago\n"
        "55555555000100;FORNECEDOR EPSILON;200;29/05/2029;;Despesa;2;Tubarao;Aberto\n"
    )
    parsed = parse_despesas(content.encode(), today=date(2026, 11, 11))
    codes = {flag.code for flag in parsed.flags}
    assert "pago_antes_do_vencimento" in codes
    assert "vencimento_distante" in codes


def test_formatos_de_valor_brasileiros():
    assert parse_amount("1.234,56", 2) == Decimal("1234.56")
    assert parse_amount("1550", 2) == Decimal("1550.00")
    assert parse_amount("10748,5", 2) == Decimal("10748.50")
    assert parse_amount("0,07", 2) == Decimal("0.07")


@pytest.mark.parametrize("line,fragment", [
    ("111;FORNECEDOR;abc;01/10/2026;;Despesa;1;Joinville;Aberto", "valor invalido"),
    ("111;FORNECEDOR;100;32/10/2026;;Despesa;1;Joinville;Aberto", "dt_vencimento invalida"),
    ("111;FORNECEDOR;100;01/10/2026;;Outra;1;Joinville;Aberto", "categoria desconhecida"),
    ("111;FORNECEDOR;100;01/10/2026;;Despesa;9;Joinville;Aberto", "loja desconhecida"),
    ("111;FORNECEDOR;100;01/10/2026;;Despesa;1;Joinville;Outro", "situacao desconhecida"),
    ("111;FORNECEDOR;100;01/10/2026;;Despesa;1;Joinville;Pago", "incoerente"),
    ("111;;100;01/10/2026;;Despesa;1;Joinville;Aberto", "nome_fornecedor vazio"),
    ("111;FORNECEDOR;100;01/10/2026;31/12/2026;Despesa;1;Joinville;Aberto", "incoerente"),
])
def test_linhas_invalidas_rejeitam_o_lote(line, fragment):
    with pytest.raises(ImportFormatError) as exc:
        parse_despesas((HEADER + line + "\n").encode())
    assert any(fragment in erro for erro in exc.value.errors)


def test_cabecalho_fora_do_contrato():
    with pytest.raises(ImportFormatError):
        parse_despesas(b"a;b;c\n1;2;3\n")


HEADER_V2 = (
    "loja;loja_descricao;nr_documento;nr_parcela;cnpj_fornecedor;"
    "nome_fornecedor;dt_emissao;dt_vencimento;dt_pagamento;valor_original;"
    "acrescimos;descontos;valor_liquido;categoria;nr_conta;"
    "descricao_conta;situacao\n"
)
VALID_V2 = HEADER_V2 + (
    "2;Tubarao;42;1;11111111000100;FORNECEDOR ALFA;01/08/2026;05/08/2026;"
    "05/08/2026;1350;10;5;1355;Despesa;27;Alugueis;Pago\n"
    "1;Joinville;100344;2;;GUIA IMPOSTO FICTICIO;02/09/2026;10/09/2026;;"
    "200;0;0;200;Despesa;36;Impostos;Aberto\n"
)


def test_layout_v2_17_colunas_campos_extras():
    parsed = parse_despesas(VALID_V2.encode(), today=date(2026, 11, 11))
    assert len(parsed.rows) == 2
    first = parsed.rows[0]
    assert first.amount == Decimal("1355.00")  # valor_liquido vira o amount
    assert first.store_code == "TUBARAO"
    assert first.status == "pago" and first.paid_at == date(2026, 8, 5)
    assert first.document_number == "42" and first.installment_number == "1"
    assert first.issued_at == date(2026, 8, 1)
    assert first.original_amount == Decimal("1350.00")
    assert first.additions == Decimal("10.00")
    assert first.discounts == Decimal("5.00")
    assert first.account_code == "27" and first.account_description == "Alugueis"
    second = parsed.rows[1]
    assert second.status == "aberto" and second.paid_at is None
    assert second.supplier_doc is None


def test_layout_v2_flag_valor_liquido_divergente():
    content = HEADER_V2 + (
        "2;Tubarao;42;1;11111111000100;FORNECEDOR ALFA;01/08/2026;05/08/2026;"
        "05/08/2026;1350;10;5;2000;Despesa;27;Alugueis;Pago\n"
    )
    parsed = parse_despesas(content.encode(), today=date(2026, 11, 11))
    codes = {flag.code for flag in parsed.flags}
    assert "valor_liquido_divergente" in codes


def test_arquivo_sem_dados():
    with pytest.raises(ImportFormatError):
        parse_despesas(HEADER.encode())


def test_erros_sao_agregados_com_linha():
    content = HEADER + (
        "111;FORNECEDOR;xyz;01/10/2026;;Despesa;1;Joinville;Aberto\n"
        "222;FORNECEDOR;10;xx/yy/zzzz;;Despesa;2;Tubarao;Aberto\n"
    )
    with pytest.raises(ImportFormatError) as exc:
        parse_despesas(content.encode())
    assert len(exc.value.errors) == 2
    assert "linha 2" in exc.value.errors[0] and "linha 3" in exc.value.errors[1]

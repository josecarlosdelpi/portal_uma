"""Contrato compartilhado de importacao do ERP — Frentes A (vendas) e B (financeiro).

Leia-me antes de implementar um novo dominio de importacao:

1. Tabela unica `erp_import_batches` (revisao 0017f). Cada frente grava seu
   proprio `domain`: 'despesas' (B), 'vendas'/'devolucoes' (A). Nao criar
   tabelas de lote paralelas.
2. `domain + sha256` e unico: reenviar o mesmo arquivo nunca duplica dados —
   o serviço devolve o lote existente marcado como `duplicated=True`.
3. Snapshot vigente: `is_current=True` identifica o lote ativo por dominio.
   Ao importar um novo snapshot, o lote corrente anterior e desmarcado na
   mesma transacao. Lotes antigos NUNCA sao apagados: guardam `payload`
   (arquivo bruto, privado) para auditoria, reconciliacao e rollback logico.
4. `coverage='full_snapshot'` (atual): o arquivo representa a base inteira do
   dominio. `coverage='window'` (futuro): substituir apenas a janela declarada
   em `period_start`/`period_end`, preservando o restante do historico.
   Implementar a janela somente quando o fornecedor confirmar a abrangencia.
5. `channel='manual'` hoje; 'drive' reservado para o sincronizador unico do
   Google Drive (um so componente de aquisicao, compartilhado; `drive_file_id`
   registra a origem). Nao criar um segundo sincronizador.
6. Falhas de validacao: lote gravado com `status='failed'`, `is_current=False`
   e `error_detail` SEM dados pessoais (apenas numeros de linha e motivos
   estruturais). O snapshot vigente permanece intacto.
7. `quality_flags` registra inconsistencias nao bloqueantes do ERP
   (ex.: pago antes do vencimento, data atipica, documento ausente) com
   `row`, `code` e `detail` sem CNPJ/CPF/nomes.

Dominios reservados: 'despesas' (Frente B), 'vendas' e 'devolucoes' (Frente A).
"""
from hashlib import sha256

DOMAIN_DESPESAS = "despesas"
DOMAIN_VENDAS = "vendas"
DOMAIN_DEVOLUCOES = "devolucoes"

CHANNEL_MANUAL = "manual"
CHANNEL_DRIVE = "drive"

COVERAGE_FULL_SNAPSHOT = "full_snapshot"
COVERAGE_WINDOW = "window"

STATUS_IMPORTED = "imported"
STATUS_FAILED = "failed"

#: Teto de flags gravadas por lote; o total real fica em quality_flag_count.
QUALITY_FLAGS_LIMIT = 200


def file_sha256(payload: bytes) -> str:
    """Digest canonico usado para deduplicacao arquivo-a-arquivo."""
    return sha256(payload).hexdigest()

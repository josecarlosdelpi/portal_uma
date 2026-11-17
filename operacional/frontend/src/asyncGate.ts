/** Protecao contra respostas assincronas fora de ordem.
 *
 *  Se o usuario muda rapidamente a selecao (grupo, lojas, destino de
 *  reatribuicao), varias previas ficam em voo ao mesmo tempo. Somente a
 *  resposta da ULTIMA requisicao emitida pode atualizar a interface —
 *  respostas antigas resolvem para `null` e sao ignoradas. Erros de
 *  requisicoes antigas tambem sao engolidos; so a falha da requisicao
 *  atual e propagada. */
export class LatestRequest<T> {
  private seq = 0;

  issue(call: () => Promise<T>): Promise<T | null> {
    const id = ++this.seq;
    return call().then(
      (result) => (id === this.seq ? result : null),
      (error) => {
        if (id === this.seq) throw error;
        return null;
      },
    );
  }

  /** Invalida qualquer requisicao em voo (ex.: selecao desfeita). */
  invalidate(): void {
    this.seq += 1;
  }
}

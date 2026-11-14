import { describe, expect, it } from "vitest";
import { LatestRequest } from "./asyncGate";

describe("LatestRequest — previas assincronas", () => {
  it("descarta resposta antiga que chega depois da mais recente", async () => {
    const gate = new LatestRequest<string>();
    const resolvers: Array<(value: string) => void> = [];
    const stale = gate.issue(() => new Promise((r) => resolvers.push(r)));
    const current = gate.issue(() => new Promise((r) => resolvers.push(r)));
    // Fora de ordem: a resposta da requisicao nova chega primeiro.
    resolvers[1]("novo");
    resolvers[0]("antigo");
    expect(await stale).toBeNull();
    expect(await current).toBe("novo");
  });

  it("descarta resposta nova que ja nao e a mais recente", async () => {
    const gate = new LatestRequest<string>();
    const resolvers: Array<(value: string) => void> = [];
    const a = gate.issue(() => new Promise((r) => resolvers.push(r)));
    const b = gate.issue(() => new Promise((r) => resolvers.push(r)));
    const c = gate.issue(() => new Promise((r) => resolvers.push(r)));
    resolvers[2]("c");
    resolvers[0]("a");
    resolvers[1]("b");
    expect(await a).toBeNull();
    expect(await b).toBeNull();
    expect(await c).toBe("c");
  });

  it("propaga erro apenas da requisicao atual; erro antigo e engolido", async () => {
    const gate = new LatestRequest<string>();
    const rejects: Array<(e: unknown) => void> = [];
    const stale = gate.issue(
      () => new Promise<string>((_, rj) => rejects.push(rj)));
    const current = gate.issue(
      () => new Promise<string>((_, rj) => rejects.push(rj)));
    rejects[1](new Error("falha atual"));
    rejects[0](new Error("falha antiga"));
    await expect(current).rejects.toThrow("falha atual");
    await expect(stale).resolves.toBeNull();
  });

  it("invalidate() impede que resposta em voo atualize a UI", async () => {
    const gate = new LatestRequest<string>();
    let resolve!: (value: string) => void;
    const pending = gate.issue(
      () => new Promise((r) => { resolve = r; }));
    gate.invalidate();
    resolve("chegou tarde");
    expect(await pending).toBeNull();
  });
});

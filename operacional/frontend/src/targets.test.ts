import { describe, expect, it } from "vitest";
import { readPermissionCodes } from "./catalog";

describe("modulo operacional de metas", () => {
  it("mantem metas como permissao de visualizacao separada da edicao", () => {
    expect(readPermissionCodes.includes("targets.view")).toBe(true);
    expect(readPermissionCodes.includes("targets.edit")).toBe(false);
  });
});

import { describe, expect, it } from "vitest";
import { grantableCodes, permissionGroups } from "./catalog";

describe("modulo operacional de metas", () => {
  it("mantem metas como permissao de visualizacao separada da edicao", () => {
    expect(grantableCodes).toContain("targets.view");
    expect(grantableCodes).toContain("targets.edit");
    const targets = permissionGroups.find((g) => g.module === "targets");
    expect(targets?.permissions.find((p) => p.code === "targets.view")?.kind).toBe("view");
    expect(targets?.permissions.find((p) => p.code === "targets.edit")?.kind).toBe("edit");
  });
});

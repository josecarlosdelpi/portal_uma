import { describe, expect, it } from "vitest";
import { accessDecision, readPermissionCodes, stores } from "./catalog";

describe("catalogo de permissoes", () => {
  it("mantem codigos de indicadores distintos de vendas", () => {
    expect(readPermissionCodes).toContain("sales.view");
    expect(readPermissionCodes).toContain("sales.revenue.view");
    expect(readPermissionCodes).not.toContain("sales.import");
    expect(new Set(readPermissionCodes).size).toBe(readPermissionCodes.length);
  });

  it("tem somente as tres lojas existentes", () => {
    expect(Object.keys(stores).sort()).toEqual(["ITAJAI", "JOINVILLE", "TUBARAO"]);
  });

  it("override negado prevalece sobre permissao de grupo", () => {
    expect(accessDecision(true, false)).toBe("denied");
    expect(accessDecision(false, true)).toBe("granted");
    expect(accessDecision(false, undefined)).toBe("denied");
    expect(accessDecision(true, undefined)).toBe("granted");
  });
});

import { describe, expect, it } from "vitest";
import { accessDecision, grantableCodes, permissionGroups, stores } from "./catalog";

describe("catalogo de permissoes", () => {
  it("mantem codigos de indicadores distintos de vendas", () => {
    expect(grantableCodes).toContain("sales.view");
    expect(grantableCodes).toContain("sales.revenue.view");
    expect(new Set(grantableCodes).size).toBe(grantableCodes.length);
  });

  it("espelha o catalogo delegavel do backend (sem governanca)", () => {
    // view + edit + acoes elegiveis; governanca nunca aparece
    expect(grantableCodes).toContain("targets.edit");
    expect(grantableCodes).toContain("daily_tasks.edit");
    expect(grantableCodes).toContain("sales.import");
    expect(grantableCodes).toContain("finance.view");
    expect(grantableCodes).not.toContain("users.manage");
    expect(grantableCodes).not.toContain("audit.view");
    expect(grantableCodes).not.toContain("security.manage");
    expect(grantableCodes).not.toContain("finance.import");
    // fechamento consolidado exige as tres lojas
    const closing = permissionGroups.find((g) => g.module === "monthly_closing");
    expect(closing?.permissions.every((p) => p.requiresAllStores)).toBe(true);
  });

  it("whatsapp_status.edit declara o efeito global da concessao", () => {
    const whatsapp = permissionGroups
      .find((g) => g.module === "whatsapp_status")
      ?.permissions.find((p) => p.code === "whatsapp_status.edit");
    expect(whatsapp?.note).toMatch(/global da UMA/i);
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

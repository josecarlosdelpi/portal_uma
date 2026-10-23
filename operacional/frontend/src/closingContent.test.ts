import {describe,expect,it} from "vitest";
import {canArchive, EMPTY_CLOSING, nextMonthDue, SLIDE_MINUTES, SLIDE_TITLES} from "./closingContent";

describe("Fechamento mensal de sete slides",()=>{
  it("mantem a apresentacao aprovada em 20 minutos",()=>{
    expect(SLIDE_MINUTES).toHaveLength(7);
    expect(SLIDE_TITLES).toHaveLength(7);
    expect(SLIDE_MINUTES.reduce((sum,n)=>sum+n,0)).toBe(20);
  });
  it("arquivamento pede tres prioridades completas e rascunho salvo",()=>{
    const current=structuredClone(EMPTY_CLOSING);
    expect(canArchive(current,true)).toBe(false);
    current.priorities=[1,2,3].map((number)=>({
      id:"p"+number,what:"Ação",owner:"Responsável",scope:"all",
      due:"2026-11-14",status:"pendente" as const
    }));
    expect(canArchive(current,false)).toBe(false);
    expect(canArchive(current,true)).toBe(true);
    current.priorities.push({...current.priorities[0]});
    expect(canArchive(current,true)).toBe(false);
  });
  it("prepara prazo do proximo mes inclusive dezembro",()=>{
    expect(nextMonthDue(2026,12)).toBe("2027-01-14");
    expect(nextMonthDue(2026,10)).toBe("2026-11-14");
  });
});

import type {ClosingDraft, ClosingPriority} from "./api";

export const SLIDE_MINUTES = [1, 3, 5, 3, 2, 2, 4] as const;
export const SLIDE_TITLES = [
  "Abertura", "Resultado geral", "Desempenho por loja",
  "Atividades comerciais", "Rotinas e qualidade",
  "Reconhecimentos e avisos", "Prioridades do próximo mês",
] as const;

export const EMPTY_CLOSING: ClosingDraft = {
  opening: "",
  stores: {JOINVILLE:"",TUBARAO:"",ITAJAI:""},
  opportunities: "", wins: "", improvements: "", notices: "",
  notes: {JOINVILLE:"",TUBARAO:"",ITAJAI:""},
  priorities: [],
};

export const STORE_LABELS: Record<string,string> = {
  JOINVILLE:"Joinville",TUBARAO:"Tubarão",ITAJAI:"Itajaí",all:"Todas as lojas",
};

export function canArchive(draft: ClosingDraft, isSaved: boolean): boolean {
  return isSaved && draft.priorities.length>=3 && draft.priorities.length<=5 &&
    new Set(draft.priorities.map((p) => p.id)).size===draft.priorities.length &&
    draft.priorities.every((p) => p.what.trim()!=="" && p.owner.trim()!=="" && p.due!=="");
}

export function monthText(year:number,month:number): string {
  return new Intl.DateTimeFormat("pt-BR",{month:"long",year:"numeric"}).format(new Date(year,month-1,12));
}

export function statusLabel(status: ClosingPriority["status"]): string {
  return status==="concluida"?"Concluída":status==="andamento"?"Em andamento":"Pendente";
}

export function nextMonthDue(year:number,month:number): string {
  const d=new Date(year,month,14,12);
  return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),"14"].join("-");
}

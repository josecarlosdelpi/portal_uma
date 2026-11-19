import { Fragment, useCallback, useEffect, useState } from "react";
import type { MyProfile } from "./api";
import { labelStore } from "./catalog";
import {
  expensesApi, type ExpAnalysis, type ExpCatalogItem, type ExpCategory,
  type ExpLine, type ExpLinesPage, type ExpRule, type ExpSupplier,
} from "./expensesApi";

type Props = { token: string; profile: MyProfile };
type View = "analysis" | "classify";
type PeriodKind = "month" | "quarter" | "semester" | "year" | "custom";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmt = (v?: string | null) => v == null || v === "" ? "—" : brl.format(Number(v));
const dmy = (iso?: string | null) => iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—";
const monthNow = () => {
  const d = new Date();
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0")].join("-");
};
const lastDayOf = (ym: string) =>
  new Date(+ym.slice(0, 4), +ym.slice(5, 7), 0).toISOString().slice(0, 10);
const iso = (y: number, m: number, d: number) =>
  [y, String(m).padStart(2, "0"), String(d).padStart(2, "0")].join("-");
const monthName = (ym: string) => {
  const d = new Date(ym + "-01T12:00:00");
  const s = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(d);
  return s.charAt(0).toUpperCase() + s.slice(1);
};
const shiftMonth = (ym: string, delta: number) => {
  const d = new Date(ym + "-01T12:00:00");
  d.setMonth(d.getMonth() + delta);
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0")].join("-");
};

const PERIOD_KIND_LABEL: Record<PeriodKind, string> = {
  month: "Mês", quarter: "Trimestre", semester: "Semestre",
  year: "Ano", custom: "Intervalo personalizado",
};
const ORIGIN_LABEL: Record<string, string> = {
  manual: "Manual",
  rule_store: "Automática (loja)",
  rule_general: "Automática (UMA)",
  none: "—",
};
const STORE_ORDER = ["JOINVILLE", "TUBARAO", "ITAJAI"];
const storeRank = (c: string) =>
  c === "COMPARTILHADO" ? 80
    : STORE_ORDER.indexOf(c) >= 0 ? STORE_ORDER.indexOf(c) : 50;
const orderStores = (codes: string[]) =>
  [...codes].sort((a, b) => storeRank(a) - storeRank(b));

type Filters = {
  store: string; kind: PeriodKind; month: string; year: number;
  quarter: string; semester: string; customFrom: string; customTo: string;
  categoryId: string; situation: string; supplier: string;
};

function rangeOf(f: Filters): { from: string; to: string } | null {
  if (f.kind === "month") return { from: f.month + "-01", to: lastDayOf(f.month) };
  if (f.kind === "quarter") {
    const q = Number(f.quarter);
    return { from: iso(f.year, (q - 1) * 3 + 1, 1), to: lastDayOf(iso(f.year, q * 3, 1).slice(0, 7)) };
  }
  if (f.kind === "semester") {
    return f.semester === "1"
      ? { from: iso(f.year, 1, 1), to: iso(f.year, 6, 30) }
      : { from: iso(f.year, 7, 1), to: iso(f.year, 12, 31) };
  }
  if (f.kind === "year") return { from: iso(f.year, 1, 1), to: iso(f.year, 12, 31) };
  if (!f.customFrom || !f.customTo) return null;
  return { from: f.customFrom, to: f.customTo };
}

function PeriodFilters({ profile, f, onChange, cats, showExtra }:
  { profile: MyProfile; f: Filters; onChange: (f: Filters) => void;
    cats: ExpCategory[]; showExtra?: boolean }) {
  const set = (patch: Partial<Filters>) => onChange({ ...f, ...patch });
  return <div className="routine-filters">
    <label>Loja
      <select value={f.store} onChange={e => set({ store: e.target.value })}>
        {profile.stores.length > 1 && <option value="TODAS">UMA consolidado</option>}
        {profile.stores.map(code => <option key={code} value={code}>{labelStore(code)}</option>)}
      </select></label>
    <label>Período
      <select value={f.kind} onChange={e => set({ kind: e.target.value as PeriodKind })}>
        {(Object.keys(PERIOD_KIND_LABEL) as PeriodKind[]).map(k =>
          <option key={k} value={k}>{PERIOD_KIND_LABEL[k]}</option>)}
      </select></label>
    {f.kind === "month" &&
      <div className="exp-month-nav">
        <button className="btn-ghost exp-month-arrow" aria-label="Mês anterior"
          onClick={() => set({ month: shiftMonth(f.month, -1) })}>←</button>
        <span className="exp-month-name">{monthName(f.month)}</span>
        <button className="btn-ghost exp-month-arrow" aria-label="Próximo mês"
          onClick={() => set({ month: shiftMonth(f.month, 1) })}>→</button>
      </div>}
    {f.kind === "quarter" && <>
      <label>Trimestre<select value={f.quarter} onChange={e => set({ quarter: e.target.value })}>
        <option value="1">1º trimestre</option><option value="2">2º trimestre</option>
        <option value="3">3º trimestre</option><option value="4">4º trimestre</option>
      </select></label>
      <label>Ano<input type="number" min="2020" max="2100"
        value={f.year} onChange={e => set({ year: Number(e.target.value) })} /></label></>}
    {f.kind === "semester" && <>
      <label>Semestre<select value={f.semester} onChange={e => set({ semester: e.target.value })}>
        <option value="1">1º semestre</option><option value="2">2º semestre</option>
      </select></label>
      <label>Ano<input type="number" min="2020" max="2100"
        value={f.year} onChange={e => set({ year: Number(e.target.value) })} /></label></>}
    {f.kind === "year" &&
      <label>Ano<input type="number" min="2020" max="2100"
        value={f.year} onChange={e => set({ year: Number(e.target.value) })} /></label>}
    {f.kind === "custom" && <>
      <label>De<input type="date" value={f.customFrom}
        onChange={e => set({ customFrom: e.target.value })} /></label>
      <label>Até<input type="date" value={f.customTo}
        onChange={e => set({ customTo: e.target.value })} /></label></>}
    {showExtra && <>
      <label>Categoria
        <select value={f.categoryId} onChange={e => set({ categoryId: e.target.value })}>
          <option value="">Todas</option>
          <option value="none">Sem categoria</option>
          {cats.filter(c => c.active).map(c =>
            <option key={c.id} value={c.id}>{c.name}</option>)}
        </select></label>
      <label>Situação
        <select value={f.situation} onChange={e => set({ situation: e.target.value })}>
          <option value="">Todas</option>
          <option value="classified">Classificadas</option>
          <option value="unclassified">Sem categoria</option>
        </select></label>
      <label>Fornecedor<input type="search" placeholder="Nome ou CNPJ/CPF"
        value={f.supplier} onChange={e => set({ supplier: e.target.value })} /></label>
    </>}
  </div>;
}

function Pager({ total, page, pageSize, onPage }:
  { total: number; page: number; pageSize: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= 0) return null;
  return <div className="paging">
    <button className="btn-ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>Anterior</button>
    <span>Página {page} de {pages} · {total} lançamentos</span>
    <button className="btn-ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>Próxima</button>
  </div>;
}

function SaveState({ state }: { state?: "saving" | "saved" | "error" }) {
  if (!state) return null;
  return <small className={"exp-save exp-save-" + state} role="status">
    {state === "saving" ? "Salvando…" : state === "saved" ? "Salvo ✓" : "Falha ao salvar"}
  </small>;
}

// ---------- modal Gerenciar Categorias ----------

function CategoriesModal({ token, profile, canManage, onClose, onChanged }:
  { token: string; profile: MyProfile; canManage: boolean;
    onClose: () => void; onChanged: () => void }) {
  const [cats, setCats] = useState<ExpCategory[]>([]);
  const [rules, setRules] = useState<ExpRule[]>([]);
  const [newName, setNewName] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [supQ, setSupQ] = useState("");
  const [supItems, setSupItems] = useState<ExpSupplier[]>([]);
  const [supSel, setSupSel] = useState<ExpSupplier | null>(null);
  const [ruleCat, setRuleCat] = useState("");
  const [ruleStore, setRuleStore] = useState("");

  const refresh = useCallback(async () => {
    try {
      setCats((await expensesApi.categories(token)).items);
      setRules((await expensesApi.rules(token)).items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao carregar categorias.");
    }
  }, [token]);
  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    const t = setTimeout(async () => {
      if (!supQ.trim()) { setSupItems([]); return; }
      try { setSupItems((await expensesApi.suppliers(token, supQ.trim())).items); }
      catch { setSupItems([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [token, supQ]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError("");
    try { await fn(); await refresh(); onChanged(); }
    catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao salvar.");
    } finally { setBusy(false); }
  };

  const createCat = () => void run(() => expensesApi.createCategory(token, newName).then(c => {
    setNewName(""); return c;
  }));

  const saveRename = (cat: ExpCategory) => void run(async () => {
    await expensesApi.updateCategory(token, cat.id, { name: editName });
    setEditId(null);
  });

  const toggleCat = (cat: ExpCategory) =>
    void run(() => expensesApi.updateCategory(token, cat.id, { active: !cat.active }));

  const createRule = () => {
    if (!supSel || !ruleCat) return;
    void run(() => expensesApi.createRule(token, {
      supplier_key: supSel.supplier_key, supplier_label: supSel.label,
      store_code: ruleStore || null, category_id: ruleCat,
    }).then(r => { setSupSel(null); setSupQ(""); setRuleCat(""); return r; }));
  };

  const activeCats = cats.filter(c => c.active);

  return <div className="modal-backdrop" role="dialog" aria-modal="true"
    aria-label="Gerenciar Categorias" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="modal-card exp-cat-modal">
      <div className="panel-head"><div>
        <h2>Gerenciar Categorias</h2>
        <p>Categorias gerenciais compartilhadas entre as lojas e regras automáticas
          por fornecedor. Classificações manuais nunca são sobrescritas pelas regras.</p>
      </div>
      <button className="fin-notice-close" onClick={onClose} aria-label="Fechar">×</button></div>
      {error && <div className="notice notice-error" role="alert">{error}</div>}

      <section className="exp-cat-section">
        <h3>Categorias gerenciais</h3>
        {canManage && <div className="exp-cat-new">
          <input type="text" placeholder="Nova categoria" value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && newName.trim()) createCat(); }} />
          <button className="btn-ghost" disabled={busy || !newName.trim()}
            onClick={createCat}>Criar</button>
        </div>}
        {!cats.length && <p className="empty">Nenhuma categoria cadastrada.</p>}
        <ul className="exp-cat-list">
          {cats.map(cat => <li key={cat.id} className={cat.active ? "" : "exp-cat-off"}>
            {editId === cat.id
              ? <>
                  <input type="text" value={editName} autoFocus
                    onChange={e => setEditName(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === "Enter") saveRename(cat);
                      if (e.key === "Escape") setEditId(null);
                    }} />
                  <button className="btn-ghost" disabled={busy || !editName.trim()}
                    onClick={() => saveRename(cat)}>OK</button>
                  <button className="btn-ghost" onClick={() => setEditId(null)}>Cancelar</button>
                </>
              : <>
                  <span>{cat.name}{!cat.active && <small> (desativada)</small>}</span>
                  {canManage && <>
                    <button className="btn-ghost" disabled={busy}
                      onClick={() => { setEditId(cat.id); setEditName(cat.name); }}>Renomear</button>
                    <button className="btn-ghost" disabled={busy}
                      onClick={() => toggleCat(cat)}>{cat.active ? "Desativar" : "Reativar"}</button>
                  </>}
                </>}
          </li>)}
        </ul>
      </section>

      <section className="exp-cat-section">
        <h3>Regras automáticas por fornecedor</h3>
        <p className="dre-note">A regra preenche lançamentos sem classificação manual,
          inclusive retroativamente. Regra de loja específica prevalece sobre a regra
          geral da UMA.</p>
        {canManage && <div className="exp-rule-new">
          <div className="exp-sup-picker">
            <input type="search" placeholder="Pesquisar fornecedor (nome ou CNPJ/CPF)"
              value={supQ} onChange={e => { setSupQ(e.target.value); setSupSel(null); }} />
            {supSel
              ? <span className="exp-sup-sel">{supSel.label}
                  <button className="fin-notice-close" aria-label="Limpar"
                    onClick={() => { setSupSel(null); }}>×</button></span>
              : supItems.length > 0 && <ul className="exp-sup-results">
                  {supItems.map(s => <li key={s.supplier_key + "|" + s.name}>
                    <button className="btn-ghost" onClick={() => { setSupSel(s); setSupItems([]); }}>
                      <strong>{s.name}</strong>
                      {s.doc && <small> {s.doc}</small>}
                      <small> · {s.rows} lanç.</small>
                    </button>
                  </li>)}
                </ul>}
          </div>
          <select value={ruleCat} onChange={e => setRuleCat(e.target.value)}>
            <option value="">Categoria padrão…</option>
            {activeCats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={ruleStore} onChange={e => setRuleStore(e.target.value)}>
            <option value="">Todas as lojas</option>
            {profile.stores.map(code =>
              <option key={code} value={code}>{labelStore(code)}</option>)}
          </select>
          <button className="btn-ghost" disabled={busy || !supSel || !ruleCat}
            onClick={createRule}>Criar regra</button>
        </div>}
        {!rules.length && <p className="empty">Nenhuma regra cadastrada.</p>}
        {rules.length > 0 && <div className="table-wrap"><table className="dre-table exp-rules-table">
          <thead><tr>
            <th>Fornecedor</th><th>Abrangência</th><th>Categoria padrão</th>
            {canManage && <th></th>}
          </tr></thead>
          <tbody>
            {rules.map(r => <tr key={r.id} className={r.active ? "" : "exp-cat-off"}>
              <td>{r.supplier_label}</td>
              <td>{r.store_code ? labelStore(r.store_code) : "Todas as lojas"}</td>
              <td>{canManage
                ? <select value={r.category_id} disabled={busy || !r.active}
                    onChange={e => void run(() =>
                      expensesApi.updateRule(token, r.id, { category_id: e.target.value }))}>
                    {!activeCats.some(c => c.id === r.category_id) &&
                      <option value={r.category_id}>{r.category_name}</option>}
                    {activeCats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                : r.category_name}</td>
              {canManage && <td className="fin-num">
                <button className="btn-ghost" disabled={busy}
                  onClick={() => void run(() =>
                    expensesApi.updateRule(token, r.id, { active: !r.active }))}>
                  {r.active ? "Desativar" : "Reativar"}</button></td>}
            </tr>)}
          </tbody>
        </table></div>}
      </section>

      <SupplierCatalog token={token} profile={profile} canManage={canManage}
        activeCats={activeCats} onChanged={onChanged} />
    </div>
  </div>;
}

// ---------- catalogo completo de fornecedores ----------

function SupplierCatalog({ token, profile, canManage, activeCats, onChanged }:
  { token: string; profile: MyProfile; canManage: boolean;
    activeCats: ExpCategory[]; onChanged: () => void }) {
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [withoutRule, setWithoutRule] = useState(false);
  const [sort, setSort] = useState("alpha");
  const [items, setItems] = useState<ExpCatalogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [lastPage, setLastPage] = useState(0);
  const [availability, setAvailability] = useState("current");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [scopeSel, setScopeSel] = useState<Record<string, string>>({});
  const [saving, setSaving] =
    useState<Record<string, "saving" | "saved" | "error">>({});

  const canGeneral = STORE_ORDER.every(s => profile.stores.includes(s));

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(async (pg: number, append: boolean) => {
    setLoading(true); setError("");
    try {
      const res = await expensesApi.supplierCatalog(token, {
        q: debouncedQ, page: pg, page_size: 25,
        without_rule: withoutRule, sort });
      setItems(cur => append ? [...cur, ...res.items] : res.items);
      setTotal(res.total); setLastPage(pg);
      setAvailability(res.availability ?? "current");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message
        : "Falha ao listar fornecedores.");
    } finally { setLoading(false); }
  }, [token, debouncedQ, withoutRule, sort]);
  useEffect(() => { void load(1, false); }, [load]);

  const editableStores = (s: ExpCatalogItem) =>
    s.stores.filter(st => profile.stores.includes(st));
  const scopeOf = (s: ExpCatalogItem) =>
    scopeSel[s.supplier_key]
    ?? (canGeneral ? "uma" : editableStores(s)[0] ?? "uma");
  const ruleOf = (s: ExpCatalogItem) => {
    const scope = scopeOf(s);
    return scope === "uma" ? s.rules["general"] : s.rules[scope];
  };

  async function saveRule(s: ExpCatalogItem, categoryId: string) {
    const scope = scopeOf(s);
    const slot = scope === "uma" ? "general" : scope;
    const key = s.supplier_key + "|" + slot;
    const rule = ruleOf(s);
    if (!categoryId && !rule?.active) return;
    setSaving(m => ({ ...m, [key]: "saving" }));
    const catName = (id: string) =>
      activeCats.find(c => c.id === id)?.name ?? rule?.category_name ?? "";
    try {
      if (categoryId && rule) {
        await expensesApi.updateRule(token, rule.id,
          { category_id: categoryId, active: true });
        setItems(cur => cur.map(i => i.supplier_key === s.supplier_key
          ? { ...i, has_rule: true, rules: { ...i.rules, [slot]:
              { ...rule, category_id: categoryId, active: true,
                category_name: catName(categoryId) } } }
          : i));
      } else if (categoryId) {
        const res = await expensesApi.createRule(token, {
          supplier_key: s.supplier_key, supplier_label: s.label,
          store_code: scope === "uma" ? null : scope,
          category_id: categoryId });
        setItems(cur => cur.map(i => i.supplier_key === s.supplier_key
          ? { ...i, has_rule: true, rules: { ...i.rules, [slot]:
              { id: res.id, category_id: categoryId, active: true,
                category_name: catName(categoryId) } } }
          : i));
      } else if (rule) {
        await expensesApi.updateRule(token, rule.id, { active: false });
        setItems(cur => cur.map(i => {
          if (i.supplier_key !== s.supplier_key) return i;
          const rules = { ...i.rules, [slot]: { ...rule, active: false } };
          return { ...i, rules,
                   has_rule: Object.values(rules).some(r => r.active) };
        }));
      }
      setSaving(m => ({ ...m, [key]: "saved" }));
      setTimeout(() => setSaving(m => {
        const next = { ...m }; delete next[key]; return next;
      }), 2500);
      onChanged();
    } catch (cause) {
      setSaving(m => ({ ...m, [key]: "error" }));
      setError(cause instanceof Error ? cause.message
        : "Falha ao salvar a regra do fornecedor.");
    }
  }

  return <section className="exp-cat-section">
    <h3>Fornecedores do ERP</h3>
    <p className="dre-note">Todos os fornecedores do arquivo vigente — pagos e em
      aberto. A categoria padrão preenche os lançamentos elegíveis sem classificação
      manual, inclusive retroativamente. Escolha a abrangência antes de selecionar.</p>
    {availability !== "current" &&
      <div className="notice notice-amber" role="note">Fonte de despesas indisponível —
        a classificação manual de lançamentos está bloqueada até nova
        sincronização válida.</div>}
    <div className="exp-sup-tools">
      <input type="search" placeholder="Pesquisar por nome ou CNPJ/CPF"
        value={q} onChange={e => setQ(e.target.value)} />
      <label className="exp-sup-onlynone">
        <input type="checkbox" checked={withoutRule}
          onChange={e => setWithoutRule(e.target.checked)} />
        Somente sem categoria
      </label>
      <select value={sort} onChange={e => setSort(e.target.value)}
        aria-label="Ordenação dos fornecedores">
        <option value="alpha">Ordem alfabética</option>
        <option value="unclassified_first">Sem categoria primeiro</option>
      </select>
    </div>
    {error && <div className="notice notice-error" role="alert">{error}</div>}
    {loading && !items.length && <p role="status">Listando fornecedores…</p>}
    {!loading && !items.length &&
      <p className="empty">Nenhum fornecedor encontrado.</p>}
    {items.length > 0 && <>
      <ul className="exp-sup-list">
        {items.map(s => {
          const scope = scopeOf(s);
          const rule = ruleOf(s);
          const st = saving[s.supplier_key + "|" +
            (scope === "uma" ? "general" : scope)];
          const stores = editableStores(s);
          return <li key={s.supplier_key} className="exp-sup-item">
            <div className="exp-sup-info">
              <strong>{s.name}</strong>
              {s.doc && <span className="mono fin-doc">{s.doc}</span>}
              <small>{s.rows} lanç. · {s.stores.map(labelStore).join(", ")}</small>
            </div>
            <div className="exp-sup-rule">
              {(canGeneral || stores.length > 1) &&
                <select aria-label={"Abrangência — " + s.name} value={scope}
                  disabled={!canManage || st === "saving"}
                  onChange={e => setScopeSel(m => ({
                    ...m, [s.supplier_key]: e.target.value }))}>
                  {canGeneral &&
                    <option value="uma">Todas as lojas (UMA)</option>}
                  {stores.map(code =>
                    <option key={code} value={code}>
                      Somente {labelStore(code)}</option>)}
                </select>}
              <select aria-label={"Categoria padrão — " + s.name}
                disabled={!canManage || st === "saving"}
                value={rule?.active ? rule.category_id : ""}
                onChange={e => void saveRule(s, e.target.value)}>
                <option value="">Sem categoria</option>
                {rule?.active &&
                  !activeCats.some(c => c.id === rule.category_id) &&
                  <option value={rule.category_id}>
                    {rule.category_name} (desativada)</option>}
                {activeCats.map(c =>
                  <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <SaveState state={st} />
            </div>
          </li>;
        })}
      </ul>
      <p className="dre-note">{total} fornecedor(es) no arquivo vigente —
        exibindo {items.length}.</p>
      {items.length < total &&
        <button className="btn-ghost" disabled={loading}
          onClick={() => void load(lastPage + 1, true)}>
          {loading ? "Carregando…" :
            `Carregar mais (${total - items.length} restantes)`}
        </button>}
    </>}
  </section>;
}

// ---------- detalhe de categoria (analise) ----------

function CategoryDrill({ token, categoryId, from, to, store, supplier,
                        situation, columns }:
  { token: string; categoryId: string; from: string; to: string;
    store?: string; supplier?: string; situation?: string;
    columns: number }) {
  const [items, setItems] = useState<ExpLine[]>([]);
  const [total, setTotal] = useState(0);
  const [lastPage, setLastPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (pg: number, append: boolean) => {
    setLoading(true); setError("");
    try {
      const res = await expensesApi.lines(token, {
        date_from: from, date_to: to, store, supplier, situation,
        category_id: categoryId, page: pg, page_size: 50 });
      setItems(cur => append ? [...cur, ...res.items] : res.items);
      setTotal(res.total); setLastPage(pg);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao detalhar.");
    } finally { setLoading(false); }
  }, [token, categoryId, from, to, store, supplier, situation]);
  useEffect(() => { void load(1, false); }, [load]);

  if (loading && !items.length)
    return <tr className="dre-drill"><td colSpan={columns}>Carregando pagamentos…</td></tr>;
  if (error)
    return <tr className="dre-drill"><td colSpan={columns}><span className="notice notice-error">{error}</span></td></tr>;
  if (!items.length)
    return <tr className="dre-drill"><td colSpan={columns}>Nenhum pagamento nesta categoria.</td></tr>;
  return <tr className="dre-drill"><td colSpan={columns}>
    <div className="dre-drill-box">
      <table className="dre-drill-table">
        <thead><tr>
          <th>Pagamento</th><th>Fornecedor</th><th>Doc/Parcela</th>
          <th>Loja</th><th>Origem</th><th className="fin-num">Valor</th>
        </tr></thead>
        <tbody>
          {items.map(item => <tr key={item.row_key}>
            <td>{dmy(item.paid_at)}</td>
            <td><strong>{item.supplier_name}</strong>
              {item.supplier_doc && <small className="dre-doc"> {item.supplier_doc}</small>}</td>
            <td>{[item.document_number, item.installment_number].filter(Boolean).join(" / ") || "—"}</td>
            <td>{item.allocation === "COMPARTILHADO" ? "Compartilhado"
                : labelStore(item.store_code)}</td>
            <td>{ORIGIN_LABEL[item.origin] ?? item.origin}</td>
            <td className="fin-num">{fmt(item.amount)}</td>
          </tr>)}
        </tbody>
      </table>
      {items.length < total &&
        <button className="btn-ghost dre-drill-more" disabled={loading}
          onClick={() => void load(lastPage + 1, true)}>
          {loading ? "Carregando…" :
            `Carregar mais (${total - items.length} de ${total} restantes)`}
        </button>}
    </div>
  </td></tr>;
}

// ---------- painel ----------

export function ExpensesPanel({ token, profile }: Props) {
  const canManage = profile.features.expenses_manage;
  const firstStore = profile.stores.length === 1 ? profile.stores[0] : "TODAS";

  const [view, setView] = useState<View>("analysis");
  const [showCats, setShowCats] = useState(false);
  const [cats, setCats] = useState<ExpCategory[]>([]);
  const [f, setF] = useState<Filters>({
    store: firstStore, kind: "month", month: monthNow(),
    year: new Date().getFullYear(), quarter: "1", semester: "1",
    customFrom: "", customTo: "", categoryId: "", situation: "", supplier: "",
  });
  const [debouncedSupplier, setDebouncedSupplier] = useState("");

  const [analysis, setAnalysis] = useState<ExpAnalysis | null>(null);
  const [aLoading, setALoading] = useState(false);
  const [lines, setLines] = useState<ExpLinesPage | null>(null);
  const [lLoading, setLLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState<Record<string, "saving" | "saved" | "error">>({});
  const [openCat, setOpenCat] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSupplier(f.supplier), 350);
    return () => clearTimeout(t);
  }, [f.supplier]);
  useEffect(() => { setPage(1); }, [f, debouncedSupplier]);

  const refreshCats = useCallback(async () => {
    try { setCats((await expensesApi.categories(token)).items); }
    catch { setCats([]); }
  }, [token]);
  useEffect(() => { void refreshCats(); }, [refreshCats]);

  const storeParam = f.store === "TODAS" ? undefined : f.store;
  const r = rangeOf(f);
  const catParam = f.categoryId || undefined;
  const sitParam = f.situation || undefined;
  const supParam = debouncedSupplier || undefined;

  const loadAnalysis = useCallback(async () => {
    const rr = rangeOf(f);
    if (!rr) { setAnalysis(null); return; }
    setALoading(true); setError(""); setOpenCat(null);
    try {
      setAnalysis(await expensesApi.analysis(token, {
        date_from: rr.from, date_to: rr.to, store: storeParam,
        category_id: catParam, situation: sitParam, supplier: supParam }));
    } catch (cause) {
      setAnalysis(null);
      setError(cause instanceof Error ? cause.message : "Falha ao apurar a análise.");
    } finally { setALoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, f, debouncedSupplier]);
  useEffect(() => { if (view === "analysis") void loadAnalysis(); }, [view, loadAnalysis]);

  const loadLines = useCallback(async () => {
    const rr = rangeOf(f);
    if (!rr) { setLines(null); return; }
    setLLoading(true); setError("");
    try {
      setLines(await expensesApi.lines(token, {
        date_from: rr.from, date_to: rr.to, store: storeParam,
        category_id: catParam, situation: sitParam, supplier: supParam,
        page, page_size: 25 }));
    } catch (cause) {
      setLines(null);
      setError(cause instanceof Error ? cause.message : "Falha ao consultar os lançamentos.");
    } finally { setLLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, f, debouncedSupplier, page]);
  useEffect(() => { if (view === "classify") void loadLines(); }, [view, loadLines]);

  async function classify(line: ExpLine, categoryId: string) {
    const fp = line.fingerprint;
    const prev = line.category_id;
    const value = categoryId || null;
    setSaving(s => ({ ...s, [fp]: "saving" }));
    try {
      const res = await expensesApi.setCategory(token, fp, value);
      setSaving(s => ({ ...s, [fp]: "saved" }));
      setLines(cur => cur && ({
        ...cur,
        items: cur.items.map(i => i.fingerprint === fp
          ? { ...i, category_id: res.category_id,
              category_name: res.category_name ?? null,
              origin: res.origin === "removed" ? "none" : res.origin }
          : i),
      }));
      setTimeout(() => setSaving(s => {
        const next = { ...s }; delete next[fp]; return next;
      }), 2500);
    } catch (cause) {
      setSaving(s => ({ ...s, [fp]: "error" }));
      setError(cause instanceof Error ? cause.message
        : "Falha ao salvar a classificação — seleção restaurada.");
      setLines(cur => cur && ({
        ...cur,
        items: cur.items.map(i => i.fingerprint === fp ? { ...i, category_id: prev } : i),
      }));
      void loadLines();
    }
  }

  const t = analysis?.totals;
  const consolidated = f.store === "TODAS";
  const storeCols = orderStores((analysis?.by_store ?? []).map(s => s.store));

  return <div className="dre">
    {error && <div className="notice notice-error" role="alert">{error}
      <button className="fin-notice-close" onClick={() => setError("")} aria-label="Fechar">×</button></div>}

    <div className="exp-toolbar">
      <div className="tabs" role="tablist" aria-label="Gestão de Despesas">
        <button role="tab" aria-selected={view === "analysis"}
          className={"tab" + (view === "analysis" ? " active" : "")}
          onClick={() => setView("analysis")}>Análise por Categoria</button>
        <button role="tab" aria-selected={view === "classify"}
          className={"tab" + (view === "classify" ? " active" : "")}
          onClick={() => setView("classify")}>Classificar Despesas</button>
      </div>
      <button className="btn-ghost exp-cats-btn" onClick={() => setShowCats(true)}>
        Gerenciar Categorias</button>
    </div>

    <PeriodFilters profile={profile} f={f} onChange={setF} cats={cats} showExtra />

    <p className="dre-disclaimer" role="note">
      GESTÃO DE DESPESAS — dimensão gerencial adicional sobre os pagamentos efetivos
      do Despesas.csv vigente; não altera a DRE, o Fluxo de Caixa nem os dados do ERP.
      Resultados preliminares, sujeitos a validação gerencial.
    </p>

    {view === "analysis" && <>
      {aLoading && <p role="status">Apurando análise…</p>}
      {!aLoading && f.kind === "custom" && !r &&
        <p className="empty">Informe o intervalo de datas para apurar.</p>}
      {analysis && !aLoading && r && <>
        {analysis.availability !== "current" &&
          <div className="notice notice-amber">Fonte de despesas indisponível —
            análise não apurável no momento.</div>}
        {analysis.warnings.map(w =>
          <div className="notice notice-amber" key={w.code} role="note">{w.message}</div>)}
        {t && <>
          <div className="dre-kpis" aria-label="Indicadores de despesas">
            <div className="panel dre-kpi"><span>Despesas pagas no período</span>
              <strong>{fmt(t.paid_total)}</strong>
              <small>{t.payment_rows} pagamento(s) elegíveis</small></div>
            <div className="panel dre-kpi"><span>Classificadas</span>
              <strong>{fmt(t.classified)}</strong>
              <small>com categoria gerencial</small></div>
            <div className={"panel dre-kpi" + (Number(t.unclassified) > 0 ? " dre-kpi-neg" : "")}>
              <span>Sem categoria</span>
              <strong>{fmt(t.unclassified)}</strong>
              <small>{t.unclassified_rows} pagamento(s) pendentes</small></div>
            <div className="panel dre-kpi"><span>% classificadas</span>
              <strong>{t.classified_pct == null ? "—" : t.classified_pct + "%"}</strong>
              <small>sem categoria entram no denominador</small></div>
          </div>

          {analysis.shared_memo &&
            <p className="dre-note dre-shared-memo">
              Pagamentos compartilhados fora deste recorte: {fmt(analysis.shared_memo.amount)}
              {" "}({analysis.shared_memo.rows} lançamento(s)) — compõem somente o consolidado UMA.</p>}

          {analysis.by_category.length > 0 && <>
            <article className="panel cf-section">
              <div className="panel-head"><div>
                <h2>Distribuição dos gastos por categoria</h2>
                <p>Clique em uma categoria para ver os pagamentos que compõem o valor.</p>
              </div></div>
              <div className="exp-cat-bars">
                {analysis.by_category.map(c =>
                  <button key={c.category_id ?? "none"}
                    className={"exp-cat-bar" + (c.category_id == null ? " exp-cat-none" : "")}
                    onClick={() => setOpenCat(openCat === (c.category_id ?? "none") ? null : (c.category_id ?? "none"))}>
                    <span className="exp-cat-bar-name">{c.name}</span>
                    <span className="exp-cat-bar-track">
                      <span className="exp-cat-bar-fill" style={{
                        width: Math.max(2,
                          Number(c.total) / Number(analysis.by_category[0]?.total || 1) * 100) + "%" }} />
                    </span>
                    <span className="exp-cat-bar-value">{fmt(c.total)} · {c.pct}%</span>
                  </button>)}
              </div>
              <div className="table-wrap"><table className="dre-table">
                <thead><tr>
                  <th>Categoria</th><th className="fin-num">Valor pago</th>
                  <th className="fin-num">Participação</th><th className="fin-num">Pagamentos</th>
                </tr></thead>
                <tbody>
                  {analysis.by_category.map(c => <Fragment key={c.category_id ?? "none"}>
                    <tr className={c.category_id == null ? "exp-row-none" : ""}>
                      <td><button className="dre-expand" onClick={() =>
                          setOpenCat(openCat === (c.category_id ?? "none") ? null : (c.category_id ?? "none"))}>
                        {openCat === (c.category_id ?? "none") ? "▾" : "▸"} {c.name}</button></td>
                      <td className="fin-num"><strong>{fmt(c.total)}</strong></td>
                      <td className="fin-num">{c.pct}%</td>
                      <td className="fin-num">{c.rows}</td>
                    </tr>
                    {openCat === (c.category_id ?? "none") && <CategoryDrill
                      token={token} categoryId={c.category_id ?? "none"}
                      from={r.from} to={r.to} store={storeParam}
                      supplier={supParam} situation={sitParam} columns={4} />}
                  </Fragment>)}
                </tbody>
              </table></div>
            </article>

            {consolidated && storeCols.length > 1 &&
              <article className="panel cf-section">
                <div className="panel-head"><div>
                  <h2>Comparativo entre lojas</h2>
                  <p>Gasto por loja e participação de cada categoria no total da respectiva
                    loja — sem rateio de despesas compartilhadas.</p>
                </div></div>
                <div className="table-wrap"><table className="dre-table">
                  <thead><tr>
                    <th>Categoria</th>
                    {storeCols.map(s => <th key={s} className="fin-num">
                      {s === "COMPARTILHADO" ? "Compartilhado" : labelStore(s)}</th>)}
                  </tr></thead>
                  <tbody>
                    <tr className="dre-row-subtotal">
                      <td>Total</td>
                      {storeCols.map(s => {
                        const col = analysis.by_store.find(x => x.store === s);
                        return <td key={s} className="fin-num"><strong>{fmt(col?.total)}</strong></td>;
                      })}
                    </tr>
                    {(() => {
                      const names = new Set<string>();
                      analysis.by_store.forEach(s =>
                        s.categories.forEach(c => names.add(c.name)));
                      return [...names].map(name => <tr key={name}
                        className={name === "Sem categoria" ? "exp-row-none" : ""}>
                        <td>{name}</td>
                        {storeCols.map(s => {
                          const col = analysis.by_store.find(x => x.store === s);
                          const cat = col?.categories.find(c => c.name === name);
                          return <td key={s} className={"fin-num" + (cat ? "" : " dre-cell-empty")}>
                            {cat ? fmt(cat.total) : "—"}
                            {cat && <small className="dre-pct">{cat.pct}%</small>}</td>;
                        })}
                      </tr>);
                    })()}
                  </tbody>
                </table></div>
                <p className="dre-note">A atribuição por loja segue o ERP — centralização
                  em uma unidade não representa necessariamente o consumo econômico real
                  de cada loja.</p>
              </article>}

            {analysis.excluded_natures.length > 0 &&
              <article className="panel cf-section">
                <div className="panel-head"><div>
                  <h2>Saídas separadas da análise operacional</h2>
                  <p>Pagas no período, mas fora dos percentuais de despesas
                    operacionais — conferência dos totais.</p>
                </div></div>
                <div className="table-wrap"><table className="dre-table">
                  <thead><tr>
                    <th>Natureza</th><th className="fin-num">Valor pago</th>
                    <th className="fin-num">Pagamentos</th>
                  </tr></thead>
                  <tbody>
                    {analysis.excluded_natures.map(n => <tr key={n.bucket}>
                      <td>{n.label}</td>
                      <td className="fin-num">{fmt(n.total)}</td>
                      <td className="fin-num">{n.rows}</td>
                    </tr>)}
                  </tbody>
                </table></div>
              </article>}

            <article className="panel dre-tech">
              <div className="panel-head"><div>
                <h2>Metodologia e premissas</h2>
                <p>Como a análise é apurada — sempre sobre o arquivo vigente.</p>
              </div></div>
              <ul className="dre-methodology">
                {analysis.methodology.map((m, i) => <li key={i}>{m}</li>)}
              </ul>
            </article>
          </>}
        </>}
      </>}
    </>}

    {view === "classify" && <>
      {lLoading && <p role="status">Carregando lançamentos…</p>}
      {lines && !lLoading && <>
        {(lines.orphan_classifications ?? 0) > 0 &&
          <div className="notice notice-amber" role="note">
            {lines.orphan_classifications} classificação(ões) manual(is) sem correspondente
            no arquivo vigente — o ERP pode ter alterado o lançamento; revisão pendente.
            Nada foi transferido automaticamente.</div>}
        <div className="fin-total-line">
          {lines.total} lançamento(s) no período — classificação salva automaticamente.</div>
        {!lines.items.length
          ? <p className="empty">Nenhum lançamento encontrado com esses filtros.</p>
          : <div className="table-wrap"><table className="dre-table exp-lines-table">
            <thead><tr>
              <th>Fornecedor</th><th>Loja</th><th>Pagamento</th><th>Doc/Parcela</th>
              <th className="fin-num">Valor</th><th>Natureza</th>
              <th>Categoria gerencial</th><th>Origem</th>
            </tr></thead>
            <tbody>
              {lines.items.map(line => {
                const st = saving[line.fingerprint];
                const inactive = line.category_id &&
                  !cats.some(c => c.id === line.category_id && c.active);
                return <tr key={line.row_key}
                  className={line.eligible && !line.category_id ? "exp-row-none" : ""}>
                  <td><strong>{line.supplier_name}</strong>
                    {line.supplier_doc && <div className="mono fin-doc">{line.supplier_doc}</div>}</td>
                  <td>{labelStore(line.store_code)}
                    {line.allocation === "COMPARTILHADO" &&
                      <small className="dre-note"> compartilhado</small>}</td>
                  <td>{dmy(line.paid_at)}</td>
                  <td>{[line.document_number, line.installment_number]
                        .filter(Boolean).join(" / ") || "—"}
                    {line.duplicate_count > 1 &&
                      <span className="exp-dup" role="note"
                        title={"Existem " + line.duplicate_count +
                          " lançamentos com identidade idêntica — a " +
                          "classificação manual vale para todos eles."}>
                        ×{line.duplicate_count}</span>}</td>
                  <td className="fin-num">{fmt(line.amount)}</td>
                  <td>{line.nature_label}
                    {!line.eligible && <small className="dre-note"> fora da análise</small>}</td>
                  <td>
                    {line.eligible
                      ? <>
                          <select className="exp-cat-select" disabled={!canManage || st === "saving"}
                            value={line.category_id ?? ""}
                            onChange={e => void classify(line, e.target.value)}>
                            <option value="">Sem categoria</option>
                            {cats.filter(c => c.active).map(c =>
                              <option key={c.id} value={c.id}>{c.name}</option>)}
                            {inactive &&
                              <option value={line.category_id ?? ""}>
                                {line.category_name} (desativada)</option>}
                          </select>
                          <SaveState state={st} />
                        </>
                      : <span className="dre-note">—</span>}
                  </td>
                  <td>{ORIGIN_LABEL[line.origin] ?? line.origin}</td>
                </tr>;
              })}
            </tbody>
          </table></div>}
        <Pager total={lines.total} page={lines.page} pageSize={lines.page_size}
          onPage={setPage} />
        {!canManage &&
          <p className="dre-note">Sua conta possui acesso de leitura — a alteração de
            categorias exige a permissão de gestão de despesas.</p>}
      </>}
    </>}

    {showCats && <CategoriesModal token={token} profile={profile} canManage={canManage}
      onClose={() => setShowCats(false)}
      onChanged={() => {
        void refreshCats();
        if (view === "analysis") void loadAnalysis(); else void loadLines();
      }} />}
  </div>;
}

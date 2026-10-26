import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {Script} from "node:vm";

const forbidden = [/\bfetch\s*\(/, /\blocalStorage\b/, /\bsessionStorage\b/, /\/api\/v1\//];

function verify(fileName, expected, options = {requireOriginalLogo:true}) {
  const path = new URL("../../../preview-operacional/" + fileName, import.meta.url);
  const html = readFileSync(path,"utf8");
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script, fileName + " precisa de script interno.");
  new Script(script, {filename:fileName});
  for (const feature of expected) {
    assert.ok(html.includes(feature), fileName + " não possui " + feature);
  }
  if (options.requireOriginalLogo) {
    assert.ok(html.includes("brand-logo-image") && html.includes("data:image/jpeg;base64,"),
      fileName + " deve usar o logotipo original UMA.");
  }
  assert.ok(html.includes("#ffd900"), fileName + " não possui a identidade amarela da UMA.");
  assert.ok(html.includes("#000"), fileName + " não possui a identidade preta da UMA.");
  for (const pattern of forbidden) {
    assert.ok(!pattern.test(script), fileName + " não pode consultar API nem guardar dados.");
  }
  console.log("Verificado: " + fileName + " (sintaxe, identidade e segurança da prévia).");
}

verify("index.html", [
  "Visão Geral", "Fechamento mensal", "Permissões por loja",
  "slideDurations=[1,3,5,3,2,2,4]",
  "Cadastro de colaboradores", "Cadastrar e gerar senha", "Excluir usuário", 'href="./rotinas.html"',
]);
verify("rotinas.html", [
  "Avaliações no Google", "Materiais e insumos", "Televendas e ligações",
  "Checklist semanal", "Status WhatsApp / Instagram", "Padrões e treinamento",
  "Anexar arte", "Anexar PDF",
]);

verify("acessos.html", [
  "Cadastro de colaboradores", "Cadastrar e gerar senha", "Excluir usuário", "DEMO-SEM-ACESSO"
]);


verify("diarias.html", [
  "Tarefas diárias", "Tarefas previstas", "Cadastrar tarefa",
  "Concluir", "Reabrir", "Excluir", "SuperAdmin"
], {requireOriginalLogo:false});

verify("superadmin.html", [
  "Fechamento Mensal · 7 slides", "Tarefas diárias", "Avaliações Google",
  "Usuários e senhas", "Permissões por loja", "Histórico e auditoria",
  "./diarias.html", "./rotinas.html", "./acessos.html", "./index.html"
], {requireOriginalLogo:false});

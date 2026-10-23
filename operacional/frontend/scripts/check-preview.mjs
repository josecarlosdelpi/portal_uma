import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {Script} from "node:vm";

const path = new URL("../../../preview-operacional/index.html",import.meta.url);
const html = readFileSync(path,"utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script,"A prévia precisa ter script interno.");
new Script(script,{filename:"preview-operacional/index.html"});
for(const feature of ["Visão Geral","Fechamento mensal","Permissões por loja","slideDurations=[1,3,5,3,2,2,4]"]){
  assert.ok(html.includes(feature),"Prévia sem a funcionalidade "+feature);
}
for(const forbidden of [/\bfetch\s*\(/,/\blocalStorage\b/,/\bsessionStorage\b/,/\/api\/v1\//]){
  assert.ok(!forbidden.test(script),"Prévia não deve consultar API, armazenar dados ou acessar contas.");
}
console.log("Prévia verificada: sintaxe, sete slides e isolamento sem dados reais.");

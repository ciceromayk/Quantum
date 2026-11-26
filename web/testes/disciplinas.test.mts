// Disciplinas do pavimento e arquivos guardados por disciplina. Rodam no Node: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { formatoDocumento } from "../src/conversao.ts";
import { DISCIPLINAS, disciplinaDe, ehDisciplina, infoDisciplina } from "../src/disciplinas.ts";

const enc = new TextEncoder();
const DXF = "  0\nSECTION\n  2\nENTITIES\n  0\nENDSEC\n  0\nEOF\n";

test("as sete disciplinas pedidas, na ordem do cadastro", () => {
  assert.deepEqual(
    DISCIPLINAS.map((d) => d.nome),
    ["Arquitetura", "Alvenarias", "Esquadrias", "Estrutura", "Instalações elétricas", "Hidrossanitárias", "Incêndio"],
  );
});

test("registro de antes das disciplinas é da Arquitetura", () => {
  assert.equal(disciplinaDe({}), "arquitetura");
  assert.equal(disciplinaDe({ disciplina: null }), "arquitetura");
  assert.equal(disciplinaDe({ disciplina: "estrutura" }), "estrutura");
  assert.equal(disciplinaDe({ disciplina: "inventada" }), "arquitetura");
  assert.equal(ehDisciplina("incendio"), true);
  assert.equal(ehDisciplina("paisagismo"), false);
});

test("só a Arquitetura diz que quantifica; as outras dizem o que falta", () => {
  for (const d of DISCIPLINAS) {
    if (d.chave === "arquitetura") assert.equal(d.situacao, "quantifica");
    else {
      assert.notEqual(d.situacao, "quantifica", d.nome);
      assert.ok(d.falta.length > 0, `${d.nome} sem lista do que falta`);
    }
  }
  assert.equal(infoDisciplina("xyz").chave, "arquitetura");
});

test("arquivo de disciplina: confere o conteúdo, não a extensão", async () => {
  assert.equal(await formatoDocumento(new Blob([enc.encode("%PDF-1.7\n...")]), "forma.pdf"), "PDF");
  assert.equal(await formatoDocumento(new Blob([enc.encode(DXF)]), "forma.dxf"), "DXF");
  assert.equal(await formatoDocumento(new Blob([enc.encode("AC1032" + "\0".repeat(40))]), "forma.dwg"), "DWG");
  await assert.rejects(formatoDocumento(new Blob([enc.encode("isto não é desenho")]), "forma.dwg"), /não reconhecido/);
});

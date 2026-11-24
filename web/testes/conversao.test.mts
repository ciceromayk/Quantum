// Testes da preparação de arquivos (detecção de formato e .zip). Rodam no Node:
//   npm test   (node --test --experimental-strip-types)
import assert from "node:assert/strict";
import { test } from "node:test";

import { detectar, ErroArquivo, prepararDesenho, type ConverterDwg } from "../src/conversao.ts";

const DXF = "  0\nSECTION\n  2\nHEADER\n  0\nENDSEC\n  0\nSECTION\n  2\nENTITIES\n  0\nENDSEC\n  0\nEOF\n";
const enc = new TextEncoder();

async function deflateRaw(dados: Uint8Array) {
  return new Uint8Array(await new Response(new Blob([dados]).stream().pipeThrough(new CompressionStream("deflate-raw"))).arrayBuffer());
}

/** Monta um .zip mínimo (o leitor não confere CRC, então ele fica zerado). */
async function zip(arquivos: { nome: string; dados: Uint8Array; deflate?: boolean }[]) {
  const partes: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let off = 0;
  for (const a of arquivos) {
    const nome = enc.encode(a.nome);
    const corpo = a.deflate === false ? a.dados : await deflateRaw(a.dados);
    const loc = new DataView(new ArrayBuffer(30));
    loc.setUint32(0, 0x04034b50, true);
    loc.setUint16(6, 0x800, true);
    loc.setUint16(8, a.deflate === false ? 0 : 8, true);
    loc.setUint32(18, corpo.length, true);
    loc.setUint32(22, a.dados.length, true);
    loc.setUint16(26, nome.length, true);
    partes.push(new Uint8Array(loc.buffer), nome, corpo);
    const cen = new DataView(new ArrayBuffer(46));
    cen.setUint32(0, 0x02014b50, true);
    cen.setUint16(8, 0x800, true);
    cen.setUint16(10, a.deflate === false ? 0 : 8, true);
    cen.setUint32(20, corpo.length, true);
    cen.setUint32(24, a.dados.length, true);
    cen.setUint16(28, nome.length, true);
    cen.setUint32(42, off, true);
    central.push(new Uint8Array(cen.buffer), nome);
    off += 30 + nome.length + corpo.length;
  }
  const tamDir = central.reduce((s, p) => s + p.length, 0);
  const fim = new DataView(new ArrayBuffer(22));
  fim.setUint32(0, 0x06054b50, true);
  fim.setUint16(8, arquivos.length, true);
  fim.setUint16(10, arquivos.length, true);
  fim.setUint32(12, tamDir, true);
  fim.setUint32(16, off, true);
  return new Blob([...partes, ...central, new Uint8Array(fim.buffer)]);
}

const semDwg: ConverterDwg = async () => {
  throw new Error("não deveria converter");
};
const dwgFalso: ConverterDwg = async (_b, versao) => ({ dxf: new Blob([DXF]), aviso: versao === "AC1032" ? null : "?" });

test("detecta DXF texto, DXF binário, DWG e zip pelo conteúdo", async () => {
  assert.equal((await detectar(new Blob([DXF]))).formato, "dxf");
  assert.equal((await detectar(new Blob(["999\nexportado\n  0\nSECTION\n"]))).formato, "dxf");
  assert.equal((await detectar(new Blob(["AutoCAD Binary DXF\r\n\x1a\0"]))).formato, "dxf_binario");
  assert.deepEqual(await detectar(new Blob(["AC1032\0\0\0"])), { formato: "dwg", versaoDwg: "AC1032" });
  assert.equal((await detectar(await zip([{ nome: "a.dxf", dados: enc.encode(DXF) }]))).formato, "zip");
  assert.equal((await detectar(new Blob(["%PDF-1.7"]))).formato, "desconhecido");
});

test("DXF segue sem mudança", async () => {
  const b = new Blob([DXF]);
  const r = await prepararDesenho(b, "planta.dxf", semDwg);
  assert.equal(r.dxf, b);
  assert.equal(r.nota, null);
});

test("descompacta o DXF de dentro do .zip (deflate e sem compressão)", async () => {
  for (const deflate of [true, false]) {
    const z = await zip([
      { nome: "__MACOSX/._planta.dxf", dados: enc.encode("x"), deflate },
      { nome: "pasta/Planta Térreo.dxf", dados: enc.encode(DXF), deflate },
      { nome: "leia-me.txt", dados: enc.encode("oi"), deflate },
    ]);
    const r = await prepararDesenho(z, "planta.zip", semDwg);
    assert.equal(await r.dxf.text(), DXF);
    assert.equal(r.origem, "dxf");
    assert.match(r.nota ?? "", /zip/);
  }
});

test("DWG dentro do .zip é convertido", async () => {
  const z = await zip([{ nome: "planta.dwg", dados: enc.encode("AC1032" + "\0".repeat(100)) }]);
  const r = await prepararDesenho(z, "planta.zip", dwgFalso);
  assert.equal(r.origem, "dwg");
  assert.match(r.nota ?? "", /AutoCAD 2018.*zip/);
});

test("mensagens claras para .zip sem desenho, com dois desenhos e arquivo desconhecido", async () => {
  const doisDesenhos = await zip([
    { nome: "a.dxf", dados: enc.encode(DXF) },
    { nome: "b.dwg", dados: enc.encode("AC1032") },
  ]);
  await assert.rejects(prepararDesenho(doisDesenhos, "x.zip", semDwg), /2 desenhos/);
  await assert.rejects(prepararDesenho(await zip([{ nome: "a.txt", dados: enc.encode("oi") }]), "x.zip", semDwg), /nenhum arquivo/);
  await assert.rejects(prepararDesenho(new Blob(["qualquer coisa"]), "x.dwg", semDwg), /assinatura de um DWG/);
  await assert.rejects(prepararDesenho(new Blob(["qualquer coisa"]), "x.pdf", semDwg), ErroArquivo);
});

test("conversão DWG: avisos do LibreDWG não barram, erro crítico e versão desconhecida pedem DXF", async () => {
  const { dwgParaDxf } = await import("../src/conversao.ts");
  const modulo = (codigo: number, saida: string | null) => {
    const fs = new Map<string, Uint8Array>();
    return {
      FS: {
        writeFile: (c: string, d: Uint8Array) => void fs.set(c, d),
        readFile: (c: string) => fs.get(c)!,
        unlink: (c: string) => void fs.delete(c),
        analyzePath: (c: string) => ({ exists: fs.has(c) }),
      },
      dwg_write_dxf: (_e: string, s: string) => {
        if (saida !== null) fs.set(s, enc.encode(saida));
        return codigo;
      },
      fs,
    };
  };
  const dwg = enc.encode("AC1032");
  const ok = modulo(0, DXF);
  assert.equal(dwgParaDxf(ok, dwg, "AC1032").aviso, null);
  assert.equal(ok.fs.size, 0, "arquivos temporários apagados");
  assert.match(dwgParaDxf(modulo(64, DXF), dwg, "AC1032").aviso ?? "", /avisos/);
  assert.match(dwgParaDxf(modulo(0, DXF), dwg, "AC1009").aviso ?? "", /experimental/);
  assert.throws(() => dwgParaDxf(modulo(2048, null), dwg, "AC1032"), /Exporte o desenho como DXF/);
  assert.throws(() => dwgParaDxf(modulo(0, DXF), dwg, "AC1099"), /versão que o leitor ainda não conhece/);
});

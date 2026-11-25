#!/usr/bin/env node
// Verificação no navegador: abre o site gerado (web/dist) num Chromium headless e faz o caminho
// de quem usa o Quantum: cria empreendimento e pavimento, envia os cortes e a planta, espera a
// análise e abre cada aba. Falha se a análise não concluir, se a tela ficar em branco ou cair na
// barreira de erro, se o motor Python morrer, ou se a planta não desenhar.
//
// É aqui que aparecem os erros que o pytest não pega: o GEOS do Pyodide é outro (3.12) e um erro
// dele derruba o motor no navegador, com a tela travada.
//
// Uso (na pasta web, depois de `npm run build`):
//   node testes/navegador/verificar.mjs --planta PLANTA.dxf [--corte CORTE.dxf ...]
//        [--min-ambientes 56] [--alturas-do-corte] [--minutos 20] [--saida verificacao]
//
// Saída: capturas de tela de cada aba e resultado.json na pasta --saida. Código de saída 1 se falhar.

import { createReadStream, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const RAIZ_WEB = resolve(fileURLToPath(import.meta.url), "../../..");

function argumentos(argv) {
  const o = { cortes: [], minutos: 20, saida: "verificacao", minAmbientes: 0, alturasDoCorte: false, dist: join(RAIZ_WEB, "dist") };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const prox = () => argv[++i];
    if (a === "--planta") o.planta = resolve(prox());
    else if (a === "--corte") o.cortes.push(resolve(prox()));
    else if (a === "--min-ambientes") o.minAmbientes = Number(prox());
    else if (a === "--alturas-do-corte") o.alturasDoCorte = true;
    else if (a === "--minutos") o.minutos = Number(prox());
    else if (a === "--saida") o.saida = resolve(prox());
    else if (a === "--dist") o.dist = resolve(prox());
    else throw new Error(`Opção desconhecida: ${a}`);
  }
  if (!o.planta) throw new Error("Informe --planta <arquivo DXF/DWG>.");
  for (const f of [o.planta, ...o.cortes]) if (!existsSync(f)) throw new Error(`Arquivo não encontrado: ${f}`);
  if (!existsSync(join(o.dist, "index.html"))) throw new Error(`Site não gerado em ${o.dist}. Rode npm run build antes.`);
  return o;
}

const TIPOS = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".whl": "application/zip",
  ".zip": "application/zip",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

/** Servidor estático mínimo para o dist (o vite preview não serve .whl e .wasm com o tipo certo em todo lugar). */
function servir(pasta) {
  const srv = createServer((req, res) => {
    const caminho = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let arq = join(pasta, caminho === "/" ? "index.html" : caminho);
    if (!arq.startsWith(pasta) || !existsSync(arq) || statSync(arq).isDirectory()) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "Content-Type": TIPOS[extname(arq)] ?? "application/octet-stream" });
    createReadStream(arq).pipe(res);
  });
  return new Promise((ok) => srv.listen(0, "127.0.0.1", () => ok(srv)));
}

function navegador() {
  // Neste ambiente de desenvolvimento o Chromium já vem instalado fora do cache do Playwright.
  const fixo = process.env.QUANTUM_CHROMIUM || (existsSync("/opt/pw-browsers/chromium") ? "/opt/pw-browsers/chromium" : undefined);
  const exe = fixo && statSync(fixo).isDirectory() ? undefined : fixo;
  return chromium.launch(exe ? { executablePath: exe } : {});
}

const MOTOR_MORREU = /fatal error|Pyodide has suffered|TopologyException|RuntimeError: unreachable|Aborted\(/i;

async function main() {
  const o = argumentos(process.argv.slice(2));
  mkdirSync(o.saida, { recursive: true });
  const srv = await servir(o.dist);
  const url = `http://127.0.0.1:${srv.address().port}/`;
  const nav = await navegador();
  const pagina = await nav.newPage({ viewport: { width: 1400, height: 900 } });

  const falhas = [];
  const avisos = [];
  const resultado = { planta: o.planta, cortes: o.cortes, etapas: [], falhas, avisos };
  const etapa = (t) => {
    resultado.etapas.push(t);
    console.log(`· ${t}`);
  };
  const tela = (nome) => pagina.screenshot({ path: join(o.saida, `${nome}.png`), fullPage: true }).catch(() => undefined);

  const ouvir = (origem) => (m) => {
    const texto = typeof m === "string" ? m : m.text();
    if (MOTOR_MORREU.test(texto)) falhas.push(`Motor Python caiu (${origem}): ${texto.slice(0, 400)}`);
    else if (typeof m !== "string" && m.type() === "error" && !/Failed to load resource/.test(texto)) avisos.push(`console (${origem}): ${texto.slice(0, 300)}`);
  };
  pagina.on("console", ouvir("página"));
  pagina.on("pageerror", (e) => falhas.push(`Erro de JavaScript na página: ${e.message.slice(0, 400)}`));
  pagina.on("worker", (w) => w.on("console", ouvir("motor")));
  pagina.on("response", (r) => {
    if (r.status() >= 400 && !/favicon/.test(r.url())) avisos.push(`HTTP ${r.status()} em ${r.url()}`);
  });

  /** A barreira de erro (Falha.tsx) ou uma página sem conteúdo contam como tela quebrada. */
  async function telaInteira(onde) {
    if (await pagina.getByRole("heading", { name: "Esta tela não abriu" }).count()) {
      const msg = await pagina.locator(".cartao .erro").first().textContent();
      falhas.push(`${onde}: caiu na barreira de erro: ${msg}`);
      return false;
    }
    const texto = (await pagina.locator("main").textContent().catch(() => "")) ?? "";
    if (!texto.trim()) {
      falhas.push(`${onde}: página em branco`);
      return false;
    }
    return true;
  }

  try {
    await pagina.goto(url);
    await pagina.getByRole("heading", { name: "Empreendimentos" }).waitFor({ timeout: 60_000 });
    etapa("site abriu");

    await pagina.getByPlaceholder("Ex.: Edifício IDGP").fill("Verificação automática");
    await pagina.getByRole("button", { name: "Criar" }).click();
    await pagina.getByPlaceholder("Ex.: Pavimento tipo").fill("Pavimento verificado");
    await pagina.getByRole("button", { name: "Adicionar" }).click();
    await pagina.getByRole("heading", { name: /Pavimento verificado/ }).waitFor();
    etapa("empreendimento e pavimento criados");

    const limite = o.minutos * 60_000;
    if (o.cortes.length) {
      await pagina.locator("input[type=file][multiple]").setInputFiles(o.cortes);
      await pagina.locator(".lista-cortes li").nth(o.cortes.length - 1).waitFor({ timeout: limite });
      await pagina.getByText("Adicionar cortes", { exact: true }).waitFor({ timeout: limite });
      etapa(`${o.cortes.length} corte(s) guardado(s)`);
    }
    if (!(await telaInteira("envio dos cortes"))) throw new Error("tela quebrada");

    await pagina.locator("label:has-text('Enviar DXF / DWG') input[type=file]").setInputFiles(o.planta);
    const status = pagina.locator(".tabela .status").first();
    await status.waitFor({ timeout: limite });
    const t0 = Date.now();
    let ultimo = "";
    while (Date.now() - t0 < limite) {
      ultimo = ((await status.textContent().catch(() => "")) ?? "").trim();
      if (ultimo === "Concluída" || ultimo === "Erro" || falhas.length) break;
      await pagina.waitForTimeout(2000);
    }
    resultado.segundos_analise = Math.round((Date.now() - t0) / 1000);
    await tela("1-pavimento");
    if (falhas.length) throw new Error("motor caiu");
    if (ultimo === "Erro") {
      const msg = await pagina.locator(".tabela .erro").first().textContent().catch(() => "");
      falhas.push(`A análise terminou com erro: ${msg}`);
      throw new Error("análise com erro");
    }
    if (ultimo !== "Concluída") {
      const fase = await pagina.locator(".tabela .discreto").first().textContent().catch(() => "");
      falhas.push(`A análise não terminou em ${o.minutos} min (status "${ultimo}", etapa "${fase}"): o app travou ou ficou lento demais.`);
      throw new Error("tempo esgotado");
    }
    etapa(`análise concluída em ${resultado.segundos_analise} s`);

    await pagina.getByRole("link", { name: "Abrir análise" }).first().click();
    await pagina.locator("nav.abas").waitFor({ timeout: 60_000 });
    resultado.contadores = (await pagina.locator(".resumo").innerText()).replace(/\s+/g, " ").trim();
    resultado.pendencias = await pagina.locator(".pendencia > p:not(.acao)").allTextContents();
    await tela("2-pendencias");

    if (o.cortes.length) {
      const lidas = resultado.pendencias.find((p) => p.startsWith("Alturas lidas no(s) corte(s)"));
      resultado.alturas_do_corte = lidas ?? null;
      if (o.alturasDoCorte && !lidas) falhas.push("Nenhuma altura foi lida dos cortes enviados.");
    }

    const abas = await pagina.locator("nav.abas button").allTextContents();
    for (const [i, nome] of abas.entries()) {
      await pagina.locator("nav.abas button", { hasText: nome }).click();
      await pagina.waitForTimeout(nome === "Planta" ? 3000 : 500);
      if (!(await telaInteira(`aba ${nome}`))) break;
      if (nome === "Planta") {
        const tracos = await pagina.locator("canvas").evaluate((c) => {
          const ctx = c.getContext("2d");
          if (!ctx || !c.width || !c.height) return 0;
          const d = ctx.getImageData(0, 0, c.width, c.height).data;
          let n = 0;
          for (let k = 0; k < d.length; k += 4 * 7) if (d[k + 3] > 0 && (d[k] !== d[0] || d[k + 1] !== d[1] || d[k + 2] !== d[2])) n++;
          return n;
        });
        resultado.pixels_desenhados = tracos;
        if (tracos < 500) falhas.push(`A aba Planta não desenhou a planta (${tracos} pontos pintados).`);
        const pintar = await pagina.getByText(/Pintar os ambientes \(\d+ de \d+\)/).textContent().catch(() => null);
        const m = pintar?.match(/\((\d+) de (\d+)\)/);
        if (m) resultado.ambientes = { com_contorno: Number(m[1]), total: Number(m[2]) };
      }
      if (nome === "Conferência") {
        resultado.conferencia = (await pagina.locator(".conferencia-resumo").textContent().catch(() => ""))?.replace(/\s+/g, " ").trim();
      }
      await tela(`${3 + i}-${nome.normalize("NFD").replace(/[^\w]/g, "").toLowerCase()}`);
    }
    etapa(`abas abertas: ${abas.join(", ")}`);

    if (o.minAmbientes) {
      const n = resultado.ambientes?.com_contorno ?? 0;
      if (n < o.minAmbientes) falhas.push(`Só ${n} ambientes com contorno; o mínimo esperado é ${o.minAmbientes}.`);
    }
  } catch (e) {
    if (!falhas.length) falhas.push(`Verificação interrompida: ${e.message}`);
    await tela("falha");
  } finally {
    writeFileSync(join(o.saida, "resultado.json"), JSON.stringify(resultado, null, 2));
    await nav.close();
    srv.close();
  }

  if (avisos.length) console.log(`\nAvisos do console (${avisos.length}):\n  ${avisos.slice(0, 10).join("\n  ")}`);
  if (falhas.length) {
    console.error(`\nFALHOU:\n  ${falhas.join("\n  ")}`);
    process.exit(1);
  }
  console.log(
    `\nOK: ${resultado.contadores ?? ""}` +
      (resultado.ambientes ? ` · ambientes ${resultado.ambientes.com_contorno} de ${resultado.ambientes.total}` : "") +
      `. Capturas e resultado.json em ${o.saida}`,
  );
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});

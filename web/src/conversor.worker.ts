/// <reference lib="webworker" />
// Converte DWG em DXF no navegador com o LibreDWG compilado para WebAssembly
// (@mlightcad/libredwg-web, licença GPL-3.0). Roda num Web Worker próprio, que é
// encerrado após cada arquivo para devolver a memória antes do motor Python rodar.

import { dwgParaDxf, ErroArquivo, PEDIR_DXF, type ModuloLibreDwg } from "./conversao";

const WASM_URL = new URL("../node_modules/@mlightcad/libredwg-web/wasm/libredwg-web.wasm", import.meta.url).href;

type Pedido = { dwg: Blob; versao?: string };

// Falha fora do try (ex.: abort assíncrono do WebAssembly) também precisa chegar à tela.
const falhaSolta = (motivo: unknown) => {
  const msg = motivo instanceof Error ? motivo.message : String(motivo);
  postMessage({
    tipo: "erro",
    erro: /memory|OOM|Cannot enlarge|allocation/i.test(msg)
      ? `Faltou memória no navegador para converter este DWG. ${PEDIR_DXF}`
      : `O leitor de DWG parou neste arquivo (${msg}). ${PEDIR_DXF}`,
  });
};
self.addEventListener("unhandledrejection", (ev) => falhaSolta((ev as PromiseRejectionEvent).reason));

self.onmessage = async (ev: MessageEvent<Pedido>) => {
  const { dwg, versao } = ev.data;
  try {
    const { default: criar } = await import("../node_modules/@mlightcad/libredwg-web/wasm/libredwg-web.js");
    const m = (await criar({ locateFile: () => WASM_URL })) as unknown as ModuloLibreDwg;
    const { dxf, aviso } = dwgParaDxf(m, new Uint8Array(await dwg.arrayBuffer()), versao);
    const blob = new Blob([dxf], { type: "application/dxf" });
    postMessage({ tipo: "ok", dxf: blob, aviso });
  } catch (e) {
    let msg = e instanceof Error ? e.message : String(e);
    if (!(e instanceof ErroArquivo)) {
      msg = /memory|Cannot enlarge|allocation failed|OOM|Array buffer allocation/i.test(msg)
        ? `Faltou memória no navegador para converter este DWG. Feche outras abas e tente de novo, ou envie o DXF. ${PEDIR_DXF}`
        : `O leitor de DWG falhou neste arquivo (${msg}). ${PEDIR_DXF}`;
    }
    postMessage({ tipo: "erro", erro: msg });
  }
};

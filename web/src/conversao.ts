// Preparação do arquivo enviado, no navegador: descobre o formato pelo conteúdo
// (não só pela extensão), descompacta .zip e converte DWG em DXF. O resultado é
// sempre um DXF (texto ou binário), que segue para o mesmo motor de sempre.
// Gravar DWG não faz parte do sistema: a saída continua sendo DXF.

export type Formato = "dxf" | "dxf_binario" | "dwg" | "zip" | "desconhecido";

export interface Preparado {
  /** DXF pronto para o motor. */
  dxf: Blob;
  /** Formato do arquivo original (o de dentro do .zip, se for o caso). */
  origem: Formato;
  /** Nota curta para mostrar ao usuário (ex.: "convertido de DWG AutoCAD 2018"). */
  nota: string | null;
}

export const LIMITE_MB = 500;
const MB = 1024 * 1024;

const SENTINELA_DXF_BINARIO = "AutoCAD Binary DXF";

/** Versões de DWG pela assinatura dos 6 primeiros bytes. */
export const VERSOES_DWG: Record<string, string> = {
  "MC0.0": "AutoCAD 1.x",
  AC1001: "AutoCAD 2.2",
  AC1002: "AutoCAD 2.5",
  AC1003: "AutoCAD 2.6",
  AC1004: "AutoCAD R9",
  AC1006: "AutoCAD R10",
  AC1009: "AutoCAD R11/R12",
  AC1012: "AutoCAD R13",
  AC1014: "AutoCAD R14",
  AC1015: "AutoCAD 2000",
  AC1018: "AutoCAD 2004",
  AC1021: "AutoCAD 2007",
  AC1024: "AutoCAD 2010",
  AC1027: "AutoCAD 2013",
  AC1032: "AutoCAD 2018",
};
/** Lidas com segurança pelo LibreDWG (R13 em diante). As anteriores são experimentais. */
const DWG_SUPORTADAS = new Set(["AC1012", "AC1014", "AC1015", "AC1018", "AC1021", "AC1024", "AC1027", "AC1032"]);

export const PEDIR_DXF =
  "Exporte o desenho como DXF no CAD (Salvar como > DXF, de preferência versão 2013 ou 2018) e envie o DXF.";

export class ErroArquivo extends Error {}

const latin1 = (b: Uint8Array) => Array.from(b, (c) => String.fromCharCode(c)).join("");

export async function detectar(arquivo: Blob): Promise<{ formato: Formato; versaoDwg?: string }> {
  const cab = new Uint8Array(await arquivo.slice(0, 32).arrayBuffer());
  if (cab[0] === 0x50 && cab[1] === 0x4b && (cab[2] === 3 || cab[2] === 5) && (cab[3] === 4 || cab[3] === 6)) return { formato: "zip" };
  const txt = latin1(cab);
  if (txt.startsWith(SENTINELA_DXF_BINARIO)) return { formato: "dxf_binario" };
  if (/^(AC\d{4}|MC0\.0)/.test(txt)) return { formato: "dwg", versaoDwg: txt.slice(0, 6) };
  // DXF texto: começa (depois de espaços, BOM ou comentário 999) com o código de grupo 0 ou 999.
  const ini = latin1(new Uint8Array(await arquivo.slice(0, 4096).arrayBuffer())).replace(/^﻿|^\xEF\xBB\xBF/, "");
  if (/^\s*(0|999)\s*\r?\n/.test(ini)) return { formato: "dxf" };
  return { formato: "desconhecido" };
}

// --- .zip --------------------------------------------------------------------------------

export interface EntradaZip {
  nome: string;
  metodo: number;
  compactado: number;
  tamanho: number;
  offsetLocal: number;
  criptografado: boolean;
}

const u16 = (v: DataView, o: number) => v.getUint16(o, true);
const u32 = (v: DataView, o: number) => v.getUint32(o, true);
const u64 = (v: DataView, o: number) => Number(v.getBigUint64(o, true));

/** Lê o diretório central do .zip (no fim do arquivo) sem descompactar nada. */
export async function listarZip(zip: Blob): Promise<EntradaZip[]> {
  const n = Math.min(zip.size, 65557 + 20);
  const fim = new DataView(await zip.slice(zip.size - n).arrayBuffer());
  let eocd = -1;
  for (let i = fim.byteLength - 22; i >= 0; i--) {
    if (u32(fim, i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new ErroArquivo("O .zip está corrompido ou incompleto (diretório não encontrado).");
  let total = u16(fim, eocd + 10);
  let tamDir = u32(fim, eocd + 12);
  let iniDir = u32(fim, eocd + 16);
  // ZIP64: o localizador fica logo antes do EOCD
  if ((iniDir === 0xffffffff || total === 0xffff) && eocd >= 20 && u32(fim, eocd - 20) === 0x07064b50) {
    const off64 = u64(fim, eocd - 20 + 8);
    const z = new DataView(await zip.slice(off64, off64 + 56).arrayBuffer());
    if (u32(z, 0) === 0x06064b50) {
      total = u64(z, 32);
      tamDir = u64(z, 40);
      iniDir = u64(z, 48);
    }
  }
  const dir = new DataView(await zip.slice(iniDir, iniDir + tamDir).arrayBuffer());
  const dec = new TextDecoder();
  const entradas: EntradaZip[] = [];
  let p = 0;
  for (let i = 0; i < total && p + 46 <= dir.byteLength; i++) {
    if (u32(dir, p) !== 0x02014b50) throw new ErroArquivo("O .zip está corrompido (diretório inválido).");
    const flags = u16(dir, p + 8);
    const metodo = u16(dir, p + 10);
    let compactado = u32(dir, p + 20);
    let tamanho = u32(dir, p + 24);
    const lNome = u16(dir, p + 28);
    const lExtra = u16(dir, p + 30);
    const lCom = u16(dir, p + 32);
    let offsetLocal = u32(dir, p + 42);
    const bytesNome = new Uint8Array(dir.buffer, dir.byteOffset + p + 46, lNome);
    // bit 11 = UTF-8; sem ele o nome é CP437, que para nomes simples coincide com latin-1
    const nome = flags & 0x800 ? dec.decode(bytesNome) : latin1(bytesNome);
    // campo extra ZIP64 com os valores de 64 bits
    let e = p + 46 + lNome;
    const fimExtra = e + lExtra;
    while (e + 4 <= fimExtra) {
      const id = u16(dir, e);
      const len = u16(dir, e + 2);
      if (id === 0x0001) {
        let q = e + 4;
        if (tamanho === 0xffffffff) (tamanho = u64(dir, q)), (q += 8);
        if (compactado === 0xffffffff) (compactado = u64(dir, q)), (q += 8);
        if (offsetLocal === 0xffffffff) offsetLocal = u64(dir, q);
      }
      e += 4 + len;
    }
    entradas.push({ nome, metodo, compactado, tamanho, offsetLocal, criptografado: !!(flags & 1) });
    p = fimExtra + lCom;
  }
  return entradas;
}

/** Escolhe o desenho dentro do .zip: o único .dxf/.dwg (ignora pastas e lixo do macOS). */
export function escolherDesenho(entradas: EntradaZip[]): EntradaZip {
  const desenhos = entradas.filter(
    (e) => /\.(dxf|dwg)$/i.test(e.nome) && !e.nome.endsWith("/") && !/(^|\/)(__MACOSX\/|\._)/.test(e.nome),
  );
  if (desenhos.length === 0) throw new ErroArquivo("O .zip não tem nenhum arquivo .dxf ou .dwg.");
  if (desenhos.length > 1) {
    const nomes = desenhos.slice(0, 5).map((d) => d.nome.split("/").pop()).join(", ");
    throw new ErroArquivo(
      `O .zip tem ${desenhos.length} desenhos (${nomes}${desenhos.length > 5 ? ", …" : ""}). Envie um .zip por desenho.`,
    );
  }
  return desenhos[0];
}

/** Descompacta uma entrada em fluxo (DecompressionStream nativo), sem carregar o .zip na memória. */
export async function extrairZip(zip: Blob, e: EntradaZip): Promise<Blob> {
  if (e.criptografado) throw new ErroArquivo("O .zip está protegido por senha. Envie sem senha.");
  const loc = new DataView(await zip.slice(e.offsetLocal, e.offsetLocal + 30).arrayBuffer());
  if (u32(loc, 0) !== 0x04034b50) throw new ErroArquivo("O .zip está corrompido (cabeçalho local inválido).");
  const ini = e.offsetLocal + 30 + u16(loc, 26) + u16(loc, 28);
  const dados = zip.slice(ini, ini + e.compactado);
  let saida: Blob;
  if (e.metodo === 0) saida = dados;
  else if (e.metodo === 8) {
    if (typeof DecompressionStream === "undefined")
      throw new ErroArquivo("Este navegador não descompacta .zip. Use Chrome, Edge ou Firefox atualizados, ou envie o DXF sem compactar.");
    saida = await new Response(dados.stream().pipeThrough(new DecompressionStream("deflate-raw"))).blob();
  } else throw new ErroArquivo(`O .zip usa uma compressão não suportada (método ${e.metodo}). Compacte de novo no padrão (Deflate).`);
  if (saida.size !== e.tamanho) throw new ErroArquivo("O .zip está corrompido (tamanho descompactado não confere).");
  return saida;
}

// --- DWG ---------------------------------------------------------------------------------

/** Módulo WebAssembly do LibreDWG (só a parte usada aqui). */
export interface ModuloLibreDwg {
  FS: {
    writeFile(caminho: string, dados: Uint8Array): void;
    readFile(caminho: string): Uint8Array;
    unlink(caminho: string): void;
    analyzePath(caminho: string): { exists: boolean };
  };
  dwg_write_dxf(entrada: string, saida: string): number;
}

/** Erros do LibreDWG a partir deste bit são críticos (DWG_ERR_CRITICAL); abaixo são avisos. */
const DWG_ERR_CRITICO = 128;

export function nomeVersaoDwg(versao: string | undefined) {
  return (versao && VERSOES_DWG[versao]) || `versão desconhecida (${versao ?? "?"})`;
}

/** Converte DWG em DXF com o LibreDWG. Os bytes ficam no sistema de arquivos em memória do módulo. */
export function dwgParaDxf(m: ModuloLibreDwg, dwg: Uint8Array, versao: string | undefined): { dxf: Uint8Array; aviso: string | null } {
  const nome = nomeVersaoDwg(versao);
  if (versao && !VERSOES_DWG[versao])
    throw new ErroArquivo(`Este DWG é de uma versão que o leitor ainda não conhece (${versao}). ${PEDIR_DXF}`);
  const ent = "/entrada.dwg";
  const sai = "/saida.dxf";
  let codigo: number;
  try {
    m.FS.writeFile(ent, dwg);
    try {
      codigo = m.dwg_write_dxf(ent, sai);
    } catch (e) {
      throw new ErroArquivo(`O leitor de DWG não conseguiu abrir este arquivo (${nome}): ${(e as Error).message || e}. ${PEDIR_DXF}`);
    }
    const existe = m.FS.analyzePath(sai).exists;
    const dxf = existe ? m.FS.readFile(sai) : new Uint8Array();
    if (codigo >= DWG_ERR_CRITICO || dxf.length < 64)
      throw new ErroArquivo(`Não foi possível converter este DWG (${nome}, erro ${codigo}). ${PEDIR_DXF}`);
    const aviso = !DWG_SUPORTADAS.has(versao ?? "")
      ? `DWG ${nome} é antigo e a leitura é experimental: confira o desenho no visualizador.`
      : codigo
        ? `O leitor de DWG reportou avisos (código ${codigo}): confira o desenho no visualizador.`
        : null;
    return { dxf, aviso };
  } finally {
    for (const f of [ent, sai]) {
      try {
        if (m.FS.analyzePath(f).exists) m.FS.unlink(f);
      } catch {
        /* nada */
      }
    }
  }
}

// --- fluxo completo ----------------------------------------------------------------------

export type ConverterDwg = (dwg: Blob, versao: string | undefined) => Promise<{ dxf: Blob; aviso: string | null }>;

/**
 * Recebe o arquivo enviado e devolve um DXF. `converterDwg` roda o LibreDWG (num Web Worker,
 * no navegador) e só é carregado quando chega um DWG.
 */
export async function prepararDesenho(
  arquivo: Blob,
  nome: string,
  converterDwg: ConverterDwg,
  aoProgredir: (etapa: string) => void = () => undefined,
): Promise<Preparado> {
  if (arquivo.size > LIMITE_MB * MB) throw new ErroArquivo(`Arquivo maior que ${LIMITE_MB} MB.`);
  let { formato, versaoDwg } = await detectar(arquivo);
  let dados = arquivo;
  let veioDeZip = false;
  if (formato === "zip") {
    aoProgredir("Descompactando o .zip…");
    const entrada = escolherDesenho(await listarZip(arquivo));
    if (entrada.tamanho > LIMITE_MB * MB)
      throw new ErroArquivo(`O desenho dentro do .zip tem ${Math.round(entrada.tamanho / MB)} MB, acima do limite de ${LIMITE_MB} MB.`);
    dados = await extrairZip(arquivo, entrada);
    nome = entrada.nome;
    ({ formato, versaoDwg } = await detectar(dados));
    veioDeZip = true;
    if (formato === "zip") throw new ErroArquivo("O .zip tem outro .zip dentro. Envie o desenho compactado uma vez só.");
  }
  const sufixoZip = veioDeZip ? " (descompactado do .zip)" : "";
  if (formato === "dwg") {
    aoProgredir(`Convertendo DWG (${nomeVersaoDwg(versaoDwg)}) em DXF…`);
    const { dxf, aviso } = await converterDwg(dados, versaoDwg);
    const nota = `Convertido de DWG ${nomeVersaoDwg(versaoDwg)} para DXF no navegador (LibreDWG)${sufixoZip}.`;
    return { dxf, origem: "dwg", nota: aviso ? `${nota} ${aviso}` : nota };
  }
  if (formato === "dxf" || formato === "dxf_binario")
    return {
      dxf: dados,
      origem: formato,
      nota: formato === "dxf_binario" ? `DXF binário${sufixoZip}.` : veioDeZip ? "Descompactado do .zip." : null,
    };
  const ext = nome.toLowerCase().split(".").pop();
  if (ext === "dwg") throw new ErroArquivo(`Este arquivo .dwg não tem a assinatura de um DWG válido. ${PEDIR_DXF}`);
  throw new ErroArquivo("Arquivo não reconhecido. Envie um .dxf, um .dwg ou um .zip com um deles.");
}

const NOME_FORMATO: Partial<Record<Formato, string>> = { dxf: "DXF", dxf_binario: "DXF binário", dwg: "DWG", zip: ".zip" };

/**
 * Arquivo de disciplina guardado como foi enviado: confere o conteúdo (não só a extensão) e devolve
 * o formato por extenso. Aceita DXF, DWG, .zip e PDF (este só para consulta).
 */
export async function formatoDocumento(arquivo: Blob, nome: string): Promise<string> {
  if (arquivo.size > LIMITE_MB * MB) throw new ErroArquivo(`${nome}: arquivo maior que ${LIMITE_MB} MB.`);
  if (latin1(new Uint8Array(await arquivo.slice(0, 5).arrayBuffer())) === "%PDF-") return "PDF";
  const rotulo = NOME_FORMATO[(await detectar(arquivo)).formato];
  if (rotulo) return rotulo;
  throw new ErroArquivo(`${nome}: arquivo não reconhecido. Envie um .dxf, .dwg, .zip ou .pdf.`);
}

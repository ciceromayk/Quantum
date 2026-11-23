// Armazenamento local no navegador (IndexedDB). Os dados ficam só neste navegador:
// use Exportar/Importar projeto para levar para outro computador ou fazer backup.

const NOME = "quantum";
const VERSAO = 2; // v2: loja "cortes"
export const LOJAS = ["projetos", "pavimentos", "analises", "arquivos", "relatorios", "cortes"] as const;
export type Loja = (typeof LOJAS)[number];

let conexao: Promise<IDBDatabase> | null = null;

function abrir(): Promise<IDBDatabase> {
  if (!conexao) {
    conexao = new Promise((ok, falha) => {
      const r = indexedDB.open(NOME, VERSAO);
      r.onupgradeneeded = () => {
        const db = r.result;
        for (const loja of LOJAS) {
          if (!db.objectStoreNames.contains(loja)) {
            // arquivos e relatórios usam o id da análise como chave
            const auto = loja !== "arquivos" && loja !== "relatorios";
            db.createObjectStore(loja, auto ? { keyPath: "id", autoIncrement: true } : undefined);
          }
        }
      };
      r.onsuccess = () => ok(r.result);
      r.onerror = () => falha(r.error);
    });
  }
  return conexao;
}

function req<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((ok, falha) => {
    r.onsuccess = () => ok(r.result);
    r.onerror = () => falha(r.error);
  });
}

async function loja(nome: Loja, modo: IDBTransactionMode = "readonly") {
  return (await abrir()).transaction(nome, modo).objectStore(nome);
}

export const banco = {
  async todos<T>(nome: Loja): Promise<T[]> {
    return req((await loja(nome)).getAll()) as Promise<T[]>;
  },
  async obter<T>(nome: Loja, chave: IDBValidKey): Promise<T | undefined> {
    return req((await loja(nome)).get(chave)) as Promise<T | undefined>;
  },
  /** Grava e devolve a chave. Em lojas com id automático, omita `id` para criar. */
  async gravar(nome: Loja, valor: unknown, chave?: IDBValidKey): Promise<number> {
    const s = await loja(nome, "readwrite");
    return req(chave === undefined ? s.put(valor) : s.put(valor, chave)) as Promise<number>;
  },
  async apagar(nome: Loja, chave: IDBValidKey): Promise<void> {
    await req((await loja(nome, "readwrite")).delete(chave));
  },
};

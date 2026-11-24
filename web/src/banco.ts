// Armazenamento local no navegador (IndexedDB). Os dados ficam só neste navegador:
// use Exportar/Importar projeto para levar para outro computador ou fazer backup.

const NOME = "quantum";
const VERSAO = 2; // v2: loja "cortes"
export const LOJAS = ["projetos", "pavimentos", "analises", "arquivos", "relatorios", "cortes"] as const;
export type Loja = (typeof LOJAS)[number];

let conexao: Promise<IDBDatabase> | null = null;

const MSG_BLOQUEADO =
  "O Quantum está aberto em outra aba com uma versão anterior e está impedindo a atualização dos dados salvos. " +
  "Feche as outras abas do Quantum e recarregue esta página.";

function abrir(): Promise<IDBDatabase> {
  if (!conexao) {
    conexao = new Promise<IDBDatabase>((ok, falha) => {
      if (typeof indexedDB === "undefined") {
        falha(new Error("Este navegador não permite salvar dados locais (IndexedDB). Saia da janela anônima ou use outro navegador."));
        return;
      }
      let r: IDBOpenDBRequest;
      try {
        r = indexedDB.open(NOME, VERSAO);
      } catch (e) {
        falha(new Error(`Não foi possível abrir os dados locais: ${(e as Error).message}`));
        return;
      }
      // Sem resposta em 15 s: outra aba segurando a versão antiga ou armazenamento travado.
      const tempo = window.setTimeout(() => falha(new Error(MSG_BLOQUEADO)), 15000);
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
      r.onblocked = () => {
        window.clearTimeout(tempo);
        falha(new Error(MSG_BLOQUEADO));
      };
      r.onsuccess = () => {
        window.clearTimeout(tempo);
        const db = r.result;
        // Uma aba mais nova quer atualizar o banco: esta fecha a conexão para não travar a outra.
        db.onversionchange = () => {
          db.close();
          conexao = null;
          alertarVersaoNova();
        };
        ok(db);
      };
      r.onerror = () => {
        window.clearTimeout(tempo);
        falha(new Error(`Não foi possível abrir os dados locais: ${r.error?.message ?? "erro desconhecido"}`));
      };
    }).catch((e) => {
      conexao = null; // permite tentar de novo depois
      throw e;
    });
  }
  return conexao;
}

/** Avisa a interface (App) que outra aba atualizou o Quantum. */
function alertarVersaoNova() {
  window.dispatchEvent(new CustomEvent("quantum:versao-nova"));
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
  /** Abre (e atualiza, se preciso) o banco local; rejeita com mensagem clara se não der. */
  abrir: () => abrir().then(() => undefined),
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
  /** Apaga várias chaves de várias lojas numa transação só: ou sai tudo, ou nada. */
  async apagarVarios(itens: [Loja, IDBValidKey][]): Promise<void> {
    if (!itens.length) return;
    const nomes = [...new Set(itens.map(([l]) => l))];
    const t = (await abrir()).transaction(nomes, "readwrite");
    await new Promise<void>((ok, falha) => {
      t.oncomplete = () => ok();
      t.onerror = () => falha(t.error);
      t.onabort = () => falha(t.error ?? new Error("Exclusão cancelada pelo navegador"));
      for (const [l, chave] of itens) t.objectStore(l).delete(chave);
    });
  },
};

import { FormEvent, useEffect, useState } from "react";
import { api, Projeto } from "../api";
import { dataHora } from "../formato";

export default function Projetos() {
  const [lista, setLista] = useState<Projeto[] | null>(null);
  const [erro, setErro] = useState("");
  const [nome, setNome] = useState("");
  const [endereco, setEndereco] = useState("");
  const [dataBase, setDataBase] = useState("");

  const carregar = () => api.projetos().then(setLista).catch((e) => setErro(e.message));
  useEffect(() => {
    carregar();
  }, []);

  async function criar(e: FormEvent) {
    e.preventDefault();
    setErro("");
    try {
      const p = await api.criarProjeto({ nome, endereco: endereco || undefined, data_base: dataBase || undefined });
      window.location.hash = `#/projetos/${p.id}`;
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <>
      <h1>Empreendimentos</h1>
      {erro && <p className="erro">{erro}</p>}
      <section className="cartao">
        <h2>Novo empreendimento</h2>
        <form className="form-linha" onSubmit={criar}>
          <label>
            Nome
            <input required value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Edifício IDGP" />
          </label>
          <label>
            Endereço
            <input value={endereco} onChange={(e) => setEndereco(e.target.value)} placeholder="Opcional" />
          </label>
          <label className="curto">
            Data-base
            <input value={dataBase} onChange={(e) => setDataBase(e.target.value)} placeholder="11/2026" />
          </label>
          <button type="submit">Criar</button>
        </form>
      </section>

      <div className="barra">
        <label className="botao secundario">
          Importar projeto
          <input
            type="file"
            accept=".json"
            hidden
            onChange={async (e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              setErro("");
              try {
                const id = await api.importarProjeto(f);
                window.location.hash = `#/projetos/${id}`;
              } catch (err) {
                setErro((err as Error).message);
              }
            }}
          />
        </label>
      </div>

      {lista === null ? (
        <p className="discreto">Carregando…</p>
      ) : lista.length === 0 ? (
        <p className="discreto">Nenhum empreendimento ainda. Crie o primeiro acima.</p>
      ) : (
        <table className="tabela">
          <thead>
            <tr>
              <th>Empreendimento</th>
              <th>Endereço</th>
              <th>Data-base</th>
              <th className="num">Pavimentos</th>
              <th>Criado em</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {lista.map((p) => (
              <tr key={p.id} className="clicavel" onClick={() => (window.location.hash = `#/projetos/${p.id}`)}>
                <td>
                  <a href={`#/projetos/${p.id}`}>{p.nome}</a>
                </td>
                <td>{p.endereco ?? "—"}</td>
                <td>{p.data_base ?? "—"}</td>
                <td className="num">{p.pavimentos.length}</td>
                <td>{dataHora(p.criado_em)}</td>
                <td className="num">
                  <button
                    className="secundario-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      api.exportarProjeto(p.id).catch((err) => setErro(err.message));
                    }}
                  >
                    Exportar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

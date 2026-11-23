import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, Pavimento, Projeto } from "../api";
import { dataHora, STATUS } from "../formato";

export default function ProjetoTela({ id }: { id: number }) {
  const [projeto, setProjeto] = useState<Projeto | null>(null);
  const [erro, setErro] = useState("");
  const [nome, setNome] = useState("");
  const [repeticoes, setRepeticoes] = useState(1);

  const carregar = useCallback(
    () =>
      api
        .projeto(id)
        .then(setProjeto)
        .catch((e) => setErro(e.message)),
    [id],
  );
  useEffect(() => {
    carregar();
  }, [carregar]);

  // Atualiza sozinho enquanto algum arquivo está na fila ou processando.
  const emAndamento = projeto?.pavimentos.some((p) => p.analises.some((a) => a.status === "na_fila" || a.status === "processando"));
  useEffect(() => {
    if (!emAndamento) return;
    const t = window.setInterval(carregar, 1500);
    return () => window.clearInterval(t);
  }, [emAndamento, carregar]);

  async function criarPavimento(e: FormEvent) {
    e.preventDefault();
    setErro("");
    try {
      await api.criarPavimento(id, { nome, repeticoes });
      setNome("");
      setRepeticoes(1);
      carregar();
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  if (!projeto) return erro ? <p className="erro">{erro}</p> : <p className="discreto">Carregando…</p>;

  return (
    <>
      <p className="trilha">
        <a href="#/">Empreendimentos</a> / {projeto.nome}
      </p>
      <h1>{projeto.nome}</h1>
      <p className="discreto">
        {[projeto.endereco, projeto.data_base && `Data-base ${projeto.data_base}`].filter(Boolean).join(" · ") || "Sem endereço e data-base"}
      </p>
      {erro && <p className="erro">{erro}</p>}

      <section className="cartao">
        <h2>Novo pavimento</h2>
        <form className="form-linha" onSubmit={criarPavimento}>
          <label>
            Nome
            <input required value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Pavimento tipo" />
          </label>
          <label className="curto">
            Repetições
            <input type="number" min={1} max={200} value={repeticoes} onChange={(e) => setRepeticoes(Number(e.target.value))} />
          </label>
          <button type="submit">Adicionar</button>
        </form>
      </section>

      {projeto.pavimentos.length === 0 && <p className="discreto">Adicione um pavimento para enviar o DXF.</p>}
      {projeto.pavimentos.map((p) => (
        <PavimentoCartao key={p.id} pav={p} aoMudar={carregar} />
      ))}
    </>
  );
}

function PavimentoCartao({ pav, aoMudar }: { pav: Pavimento; aoMudar: () => void }) {
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  async function enviar(arquivo: File | undefined) {
    if (!arquivo) return;
    setErro("");
    setEnviando(true);
    try {
      await api.enviarArquivo(pav.id, arquivo);
      aoMudar();
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  const params = Object.entries(pav.parametros);
  const analises = [...pav.analises].reverse();

  return (
    <section className="cartao">
      <div className="cartao-topo">
        <div>
          <h2>
            {pav.nome} <span className="selo">× {pav.repeticoes}</span>
          </h2>
          <p className="discreto">
            {params.length ? params.map(([k, v]) => `${k} = ${v} m`).join(" · ") : "Sem parâmetros informados"}
            {pav.unidade && ` · unidade ${pav.unidade}`}
          </p>
        </div>
        <label className={`botao ${enviando ? "desativado" : ""}`}>
          {enviando ? "Enviando…" : "Enviar DXF"}
          <input
            type="file"
            accept=".dxf"
            hidden
            disabled={enviando}
            onChange={(e) => {
              enviar(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {erro && <p className="erro">{erro}</p>}
      {analises.length === 0 ? (
        <p className="discreto">Nenhum arquivo enviado. Exporte o pavimento como DXF no CAD e envie aqui.</p>
      ) : (
        <table className="tabela">
          <thead>
            <tr>
              <th>Rev.</th>
              <th>Arquivo</th>
              <th>Status</th>
              <th>Enviado em</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {analises.map((a) => (
              <tr key={a.id}>
                <td>R{a.revisao}</td>
                <td>{a.arquivo_nome}</td>
                <td>
                  <span className={`status status-${a.status}`}>{STATUS[a.status]}</span>
                  {a.etapa && (a.status === "na_fila" || a.status === "processando") && (
                    <div className="discreto pequeno">{a.etapa}</div>
                  )}
                  {a.erro && <div className="erro pequeno">{a.erro}</div>}
                </td>
                <td>{dataHora(a.criado_em)}</td>
                <td className="num">
                  {a.status === "concluida" && <a href={`#/analises/${a.id}`}>Abrir análise</a>}
                  {a.status === "erro" && (
                    <button
                      className="secundario-btn"
                      onClick={() =>
                        api
                          .reprocessar(a.id)
                          .then(aoMudar)
                          .catch((e) => setErro((e as Error).message))
                      }
                    >
                      Reprocessar
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ACEITOS, api, DWG_GRANDE_MB, Pavimento, PLANTA_GRANDE_MB, preparoInterrompido, Projeto } from "../api";
import { dataHora, STATUS } from "../formato";

export default function ProjetoTela({ id }: { id: number }) {
  const [projeto, setProjeto] = useState<Projeto | null>(null);
  const [erro, setErro] = useState("");
  const [nome, setNome] = useState("");
  const [repeticoes, setRepeticoes] = useState(1);

  // A aba caiu no meio de uma conversão (quase sempre falta de memória com DWG grande)?
  useEffect(() => {
    const p = preparoInterrompido();
    if (p)
      setErro(
        `A preparação ${p.tipo === "corte" ? "do corte" : "da planta"} "${p.nome}" (${mb(p.tamanho)} MB) não terminou: a página foi fechada ou o navegador ficou sem memória e reiniciou a aba. ` +
          (/\.dwg$/i.test(p.nome)
            ? "DWG grande pesa muito para converter no navegador. Exporte esse desenho como DXF no CAD (Salvar como > DXF 2013) e envie o DXF, que é lido em partes e aguenta até 500 MB."
            : "Tente de novo com as outras abas fechadas."),
      );
  }, []);

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

      {projeto.pavimentos.length === 0 && <p className="discreto">Adicione um pavimento para enviar o desenho (DXF ou DWG).</p>}
      {projeto.pavimentos.map((p) => (
        <PavimentoCartao key={p.id} pav={p} aoMudar={carregar} />
      ))}
    </>
  );
}

function PavimentoCartao({ pav, aoMudar }: { pav: Pavimento; aoMudar: () => void }) {
  const [enviando, setEnviando] = useState(false);
  const [etapa, setEtapa] = useState("");
  const [erro, setErro] = useState("");

  const [aviso, setAviso] = useState("");

  async function enviar(arquivo: File | undefined) {
    if (!arquivo) return;
    setErro("");
    setAviso(
      avisoDwg([arquivo]) ||
        (arquivo.size > PLANTA_GRANDE_MB * 1048576
          ? `Planta com ${Math.round(arquivo.size / 1048576)} MB: pode faltar memória no navegador. Se der erro, exporte só o pavimento, sem outras pranchas e xrefs.`
          : ""),
    );
    setEnviando(true);
    try {
      await api.enviarArquivo(pav.id, arquivo, setEtapa);
      aoMudar();
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setEnviando(false);
      setEtapa("");
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
            {params.length ? params.map(([k, v]) => `${k} = ${v}${v === "teto" ? "" : " m"}`).join(" · ") : "Sem parâmetros informados"}
            {pav.unidade && ` · unidade ${pav.unidade}`}
          </p>
        </div>
        <label className={`botao ${enviando ? "desativado" : ""}`}>
          {enviando ? etapa || "Enviando…" : "Enviar DXF / DWG"}
          <input
            type="file"
            accept={ACEITOS}
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
      {aviso && <p className="discreto pequeno">{aviso}</p>}
      <Cortes pav={pav} aoMudar={aoMudar} aoErrar={setErro} />
      {analises.length === 0 ? (
        <p className="discreto">Nenhum arquivo enviado. Envie o pavimento em DXF, DWG ou .zip com um deles (até 500 MB). Só o espaço do modelo (Model) é lido.</p>
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
                  {a.conversao && <div className="discreto pequeno">{a.conversao}</div>}
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

const mb = (bytes: number) => (bytes / 1048576).toFixed(1).replace(".", ",");

/** Aviso antes de converter DWG grande no navegador. */
function avisoDwg(arquivos: File[]): string {
  const grandes = arquivos.filter((a) => /\.dwg$/i.test(a.name) && a.size > DWG_GRANDE_MB * 1048576);
  if (!grandes.length) return "";
  return `${grandes.map((a) => `${a.name} (${mb(a.size)} MB)`).join(", ")}: DWG grande. A conversão no navegador pode levar minutos e, se faltar memória, a aba pode recarregar sozinha. Não feche a página. Se falhar, exporte como DXF e envie o DXF.`;
}

function Cortes({ pav, aoMudar, aoErrar }: { pav: Pavimento; aoMudar: () => void; aoErrar: (m: string) => void }) {
  const [enviando, setEnviando] = useState(false);
  const [etapa, setEtapa] = useState("");
  const [aviso, setAviso] = useState("");

  async function enviar(arquivos: FileList | null) {
    if (!arquivos?.length) return;
    aoErrar("");
    setAviso(avisoDwg(Array.from(arquivos)));
    setEnviando(true);
    try {
      for (const a of Array.from(arquivos)) {
        try {
          await api.enviarCorte(pav.id, a, setEtapa);
        } catch (err) {
          throw new Error(`${a.name}: ${(err as Error).message}`);
        }
      }
      aoMudar();
    } catch (err) {
      aoMudar();
      aoErrar((err as Error).message);
    } finally {
      setEnviando(false);
      setEtapa("");
      setAviso("");
    }
  }

  return (
    <div className="cortes">
      <div className="cortes-topo">
        <strong>Cortes para alturas de revestimento</strong>
        <label className={`botao secundario ${enviando ? "desativado" : ""}`}>
          {enviando ? etapa || "Enviando…" : "Adicionar cortes"}
          <input
            type="file"
            accept={ACEITOS}
            multiple
            hidden
            disabled={enviando}
            onChange={(e) => {
              enviar(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {enviando && (
        <p className="pequeno">
          {etapa || "Enviando…"} {aviso}
        </p>
      )}
      <p className="discreto pequeno">
        Alturas tiradas de cortes valem só para os ambientes que aparecem cortados e precisam de conferência. Os demais ficam como
        pendência até a altura ser informada em Parâmetros. Depois de adicionar ou remover cortes, use Reprocessar na análise.
      </p>
      {pav.cortes.length > 0 && (
        <ul className="lista-cortes">
          {pav.cortes.map((c) => (
            <li key={c.id}>
              {c.nome} <span className="discreto pequeno">({mb(c.tamanho)} MB)</span>
              {c.conversao && <span className="discreto pequeno"> · {c.conversao}</span>}
              {c.tamanho > 100 * 1048576 && <span className="discreto pequeno"> · arquivo grande: a leitura leva alguns minutos</span>}
              <button
                className="secundario-btn"
                onClick={() =>
                  api
                    .removerCorte(c.id)
                    .then(aoMudar)
                    .catch((e) => aoErrar((e as Error).message))
                }
              >
                Remover
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

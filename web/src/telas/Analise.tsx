import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Acabamentos, AnaliseDetalhe, api, Item, Parametros, Pavimento, Pendencia, Severidade } from "../api";
import { dataHora, num, SEVERIDADE, STATUS } from "../formato";

type Aba = "pendencias" | "quantitativos" | "parametros" | "camadas";
const ORDEM: Severidade[] = ["bloqueante", "alerta", "info"];

export default function AnaliseTela({ id }: { id: number }) {
  const [analise, setAnalise] = useState<AnaliseDetalhe | null>(null);
  const [pav, setPav] = useState<Pavimento | null>(null);
  const [nomeProjeto, setNomeProjeto] = useState("");
  const [aba, setAba] = useState<Aba>("pendencias");
  const [erro, setErro] = useState("");
  const [temDxf, setTemDxf] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const a = await api.analise(id);
      setAnalise(a);
      setTemDxf(await api.temDxfAcabamentos(id));
      const p = await api.pavimento(a.pavimento_id);
      setPav(p);
      const proj = await api.projeto(p.projeto_id);
      setNomeProjeto(proj.nome);
    } catch (e) {
      setErro((e as Error).message);
    }
  }, [id]);
  useEffect(() => {
    carregar();
  }, [carregar]);

  const emAndamento = analise?.status === "na_fila" || analise?.status === "processando";
  useEffect(() => {
    if (!emAndamento) return;
    const t = window.setInterval(carregar, 1500);
    return () => window.clearInterval(t);
  }, [emAndamento, carregar]);

  if (!analise || !pav) return erro ? <p className="erro">{erro}</p> : <p className="discreto">Carregando…</p>;
  const r = analise.resultado;
  const sev = analise.pendencias_por_severidade;

  return (
    <>
      <p className="trilha">
        <a href="#/">Empreendimentos</a> / <a href={`#/projetos/${pav.projeto_id}`}>{nomeProjeto}</a> / {pav.nome} / R{analise.revisao}
      </p>
      <div className="cartao-topo">
        <div>
          <h1>
            {pav.nome} · R{analise.revisao}
          </h1>
          <p className="discreto">
            {analise.arquivo_nome} · {STATUS[analise.status]} em {dataHora(analise.concluido_em ?? analise.criado_em)}
            {r && ` · unidade ${r.desenho.unidade ?? "DESCONHECIDA"} (${r.desenho.origem_unidade}) · ${r.desenho.total_entidades.toLocaleString("pt-BR")} entidades`}
          </p>
        </div>
        {analise.status === "concluida" && (
          <div className="acoes">
            <button onClick={() => api.baixarRelatorio(id, "xlsx").catch((e) => setErro(e.message))}>Baixar Excel</button>
            <button className="botao secundario" onClick={() => api.baixarRelatorio(id, "md").catch((e) => setErro(e.message))}>
              Baixar relatório
            </button>
            {temDxf && (
              <button className="botao secundario" onClick={() => api.baixarRelatorio(id, "dxf").catch((e) => setErro(e.message))}>
                Baixar DXF de acabamentos
              </button>
            )}
          </div>
        )}
      </div>
      {erro && <p className="erro">{erro}</p>}
      {emAndamento && <p className="faixa">{analise.etapa || "Processando o arquivo…"} A página atualiza sozinha.</p>}
      {analise.status === "erro" && <p className="erro">{analise.erro}</p>}

      {r && (
        <>
          <div className="resumo">
            {ORDEM.map((s) => (
              <button key={s} className={`contador sev-${s}`} onClick={() => setAba("pendencias")}>
                <strong>{sev[s] ?? 0}</strong> {SEVERIDADE[s].toLowerCase()}
                {(sev[s] ?? 0) === 1 ? "" : "s"}
              </button>
            ))}
            <span className="contador neutro">
              <strong>{r.itens.length}</strong> itens de quantitativo
            </span>
          </div>
          {(sev.bloqueante ?? 0) > 0 && (
            <p className="faixa alerta">
              Há pendências bloqueantes. Os itens que dependem delas ficam sem quantidade até serem resolvidas.
            </p>
          )}

          <nav className="abas">
            {(
              [
                ["pendencias", "Pendências"],
                ["quantitativos", "Quantitativos"],
                ["parametros", "Parâmetros"],
                ["camadas", "Camadas"],
              ] as [Aba, string][]
            ).map(([k, t]) => (
              <button key={k} className={aba === k ? "ativa" : ""} onClick={() => setAba(k)}>
                {t}
              </button>
            ))}
          </nav>

          {aba === "pendencias" && <Pendencias lista={r.pendencias} />}
          {aba === "quantitativos" && <Quantitativos itens={r.itens} />}
          {aba === "parametros" && (
            <ParametrosTela pav={pav} analiseId={id} aoSalvar={carregar} acabamentos={r.acabamentos as Acabamentos | undefined} />
          )}
          {aba === "camadas" && <Camadas itens={r.itens} naoClassificadas={r.camadas_nao_classificadas} />}
        </>
      )}
    </>
  );
}

function Pendencias({ lista }: { lista: Pendencia[] }) {
  const ordenada = [...lista].sort((a, b) => ORDEM.indexOf(a.severidade) - ORDEM.indexOf(b.severidade));
  if (!ordenada.length) return <p className="discreto">O auditor não encontrou pendências. A revisão humana continua obrigatória.</p>;
  return (
    <ul className="pendencias">
      {ordenada.map((p, i) => (
        <li key={i} className={`pendencia sev-${p.severidade}`}>
          <div className="pendencia-topo">
            <span className={`selo sev-${p.severidade}`}>{SEVERIDADE[p.severidade]}</span>
            <span className="discreto">{p.disciplina}</span>
            {p.camada && <span className="discreto">· camada {p.camada}</span>}
          </div>
          <p>{p.mensagem}</p>
          {p.acao_sugerida && <p className="acao">→ {p.acao_sugerida}</p>}
        </li>
      ))}
    </ul>
  );
}

function Quantitativos({ itens }: { itens: Item[] }) {
  const porDisciplina = useMemo(() => {
    const m = new Map<string, Item[]>();
    itens.forEach((i) => m.set(i.disciplina, [...(m.get(i.disciplina) ?? []), i]));
    return [...m.entries()];
  }, [itens]);
  if (!porDisciplina.length) return <p className="discreto">Nenhum item encontrado. Confira os nomes das camadas na aba Camadas.</p>;
  return (
    <>
      {porDisciplina.map(([disc, lista]) => (
        <section key={disc} className="cartao">
          <h2>{disc}</h2>
          <table className="tabela">
            <thead>
              <tr>
                <th>Código</th>
                <th>Descrição</th>
                <th>Detalhe</th>
                <th className="num">Quantidade</th>
                <th>Un.</th>
                <th>Observação</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((i, k) => (
                <tr key={k} className={i.detalhe === "total" ? "linha-total" : ""}>
                  <td className="codigo">{i.codigo}</td>
                  <td>{i.descricao}</td>
                  <td>{i.detalhe ?? ""}</td>
                  <td className="num">{i.quantidade === null ? <span className="selo sev-bloqueante">pendente</span> : num(i.quantidade)}</td>
                  <td>{i.unidade}</td>
                  <td className="obs">{i.observacao ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </>
  );
}

function ParametrosTela({
  pav,
  analiseId,
  aoSalvar,
  acabamentos,
}: {
  pav: Pavimento;
  analiseId: number;
  aoSalvar: () => void;
  acabamentos?: Acabamentos;
}) {
  const [conhecidos, setConhecidos] = useState<Record<string, string>>({});
  const [valores, setValores] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(pav.parametros).map(([k, v]) => [k, String(v).replace(".", ",")])),
  );
  const paredes = acabamentos?.codigos_parede ?? [];
  const descParede = (c: string) => acabamentos?.catalogo?.parede?.[c] ?? "código fora do quadro";
  const [unidade, setUnidade] = useState<string>(pav.unidade ?? "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api.parametrosConhecidos().then(setConhecidos).catch(() => setConhecidos({}));
  }, []);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setErro("");
    const limpos: Parametros = {};
    for (const [k, v] of Object.entries(valores)) {
      if (!v.trim()) continue;
      if (v === "teto" && k.startsWith("altura_parede_")) {
        limpos[k] = "teto";
        continue;
      }
      const n = Number(v.replace(",", "."));
      if (!Number.isFinite(n) || n <= 0) {
        setErro(`Valor inválido para ${conhecidos[k] ?? k}`);
        return;
      }
      limpos[k] = n;
    }
    setSalvando(true);
    try {
      await api.definirParametros(pav.id, limpos, unidade || null);
      await api.reprocessar(analiseId);
      aoSalvar();
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setSalvando(false);
    }
  }

  const nomes = [...new Set([...Object.keys(conhecidos), ...Object.keys(valores)])].filter((k) => !k.startsWith("altura_parede_"));
  return (
    <section className="cartao">
      <h2>Parâmetros do pavimento</h2>
      <p className="discreto">
        Valores em metros que o desenho 2D não contém. O Quantum não usa valores padrão: campo vazio deixa o item como
        pendência. Confira no projeto antes de preencher.
      </p>
      <form className="form-grade" onSubmit={salvar}>
        {nomes.map((k) => (
          <label key={k}>
            {conhecidos[k] ?? k}
            <input
              inputMode="decimal"
              value={valores[k] ?? ""}
              onChange={(e) => setValores({ ...valores, [k]: e.target.value })}
              placeholder="não informado"
            />
          </label>
        ))}
        {paredes.length > 0 && (
          <div className="form-acoes">
            <h2>Altura do revestimento de parede</h2>
            <p className="faixa">{acabamentos?.aviso_alturas}</p>
          </div>
        )}
        {paredes.map((c) => {
          const k = `altura_parede_${c}`;
          const ateTeto = valores[k] === "teto";
          return (
            <label key={k}>
              Parede {c}: {descParede(c)}
              <input
                inputMode="decimal"
                value={ateTeto ? "" : (valores[k] ?? "")}
                disabled={ateTeto}
                onChange={(e) => setValores({ ...valores, [k]: e.target.value })}
                placeholder={ateTeto ? "até o teto (pé-direito)" : "altura em m, não informada"}
              />
              <span className="marcar">
                <input
                  type="checkbox"
                  checked={ateTeto}
                  onChange={(e) => setValores({ ...valores, [k]: e.target.checked ? "teto" : "" })}
                />{" "}
                até o teto
              </span>
            </label>
          );
        })}
        <label>
          Unidade do desenho
          <select value={unidade} onChange={(e) => setUnidade(e.target.value)}>
            <option value="">Usar a do arquivo ($INSUNITS)</option>
            <option value="mm">milímetro</option>
            <option value="cm">centímetro</option>
            <option value="dm">decímetro</option>
            <option value="m">metro</option>
          </select>
        </label>
        <div className="form-acoes">
          <button type="submit" disabled={salvando}>
            {salvando ? "Salvando…" : "Salvar e reprocessar"}
          </button>
        </div>
      </form>
      {erro && <p className="erro">{erro}</p>}
    </section>
  );
}

function Camadas({ itens, naoClassificadas }: { itens: Item[]; naoClassificadas: Record<string, number> }) {
  const classificadas = useMemo(() => {
    const m = new Map<string, Set<string>>();
    itens.forEach((i) => i.camadas.forEach((c) => m.set(c, new Set([...(m.get(c) ?? []), i.disciplina]))));
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [itens]);
  const nao = Object.entries(naoClassificadas).sort(([, a], [, b]) => b - a);
  return (
    <div className="duas-colunas">
      <section className="cartao">
        <h2>Sem disciplina ({nao.length})</h2>
        <p className="discreto">Geometria nessas camadas não entrou em nenhum quantitativo.</p>
        <table className="tabela">
          <thead>
            <tr>
              <th>Camada</th>
              <th className="num">Entidades</th>
            </tr>
          </thead>
          <tbody>
            {nao.map(([c, n]) => (
              <tr key={c}>
                <td>{c}</td>
                <td className="num">{n.toLocaleString("pt-BR")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="cartao">
        <h2>Classificadas ({classificadas.length})</h2>
        <table className="tabela">
          <thead>
            <tr>
              <th>Camada</th>
              <th>Disciplina</th>
            </tr>
          </thead>
          <tbody>
            {classificadas.map(([c, d]) => (
              <tr key={c}>
                <td>{c}</td>
                <td>{[...d].join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

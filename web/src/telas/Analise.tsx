import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { aceitaLaje, Acabamentos, AnaliseDetalhe, api, Item, Parametros, Pavimento, Pendencia, Severidade } from "../api";
import Visualizador from "./Visualizador";
import { dataHora, num, SEVERIDADE, STATUS } from "../formato";

type Aba = "pendencias" | "planta" | "quantitativos" | "parametros" | "camadas";
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
                ["planta", "Planta"],
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
          {aba === "planta" && <Visualizador analiseId={id} acabamentos={r.acabamentos as Acabamentos | undefined} />}
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
      if ((v === "teto" || v === "laje") && aceitaLaje(k)) {
        limpos[k] = "laje";
        continue;
      }
      const n = Number(v.replace(",", "."));
      if (!Number.isFinite(n) || n < 0 || (n === 0 && !k.startsWith("peitoril_vao_"))) {
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

  const proprios = ["altura_parede_", "altura_ambiente_", "altura_vao_", "peitoril_vao_"];
  const nomes = [...new Set([...Object.keys(conhecidos), ...Object.keys(valores)])].filter(
    (k) => !proprios.some((p) => k.startsWith(p)),
  );
  // um ambiente por nome (o corte e a altura informada valem pelo nome)
  const porNome = new Map<string, { nome: string; parametro: string; codigos: Set<string>; corte: number | null }>();
  for (const a of acabamentos?.alturas_parede ?? []) {
    const r = porNome.get(a.parametro) ?? { nome: a.nome, parametro: a.parametro, codigos: new Set(), corte: null };
    r.codigos.add(a.codigo);
    if (a.origem_altura === "corte" && a.altura_m != null) r.corte = a.altura_m;
    porNome.set(a.parametro, r);
  }
  const ambientes = [...porNome.values()].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  const pml = acabamentos?.pe_menos_laje;
  const textoLaje = pml != null ? `pé-direito − laje (${num(pml)} m)` : "pé-direito − laje (informe pé-direito e espessura da laje)";
  // ambiente que já tem altura pelo código de parede (altura_parede_<código>) não falta: marcar
  // "pé-direito − laje" nele trocaria em silêncio uma altura informada
  const temPorCodigo = (a: { codigos: Set<string> }) =>
    [...a.codigos].every((c) => (valores[`altura_parede_${c}`] ?? "").trim() !== "");
  const faltando = ambientes.filter(
    (a) => a.corte == null && !(valores[a.parametro] ?? "").trim() && !temPorCodigo(a),
  );
  const vaos = acabamentos?.vaos ?? [];
  const limite = acabamentos?.limite_vao_m2 ?? 2;
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
        {ambientes.length > 0 && (
          <div className="form-acoes">
            <h2>Altura do revestimento por ambiente</h2>
            <p className="faixa">{acabamentos?.aviso_alturas}</p>
            {faltando.length > 0 && (
              <p className="faixa alerta">
                {faltando.length} ambiente(s) sem altura lida no corte nem informada: {faltando.map((a) => a.nome).join(", ")}.{" "}
                <button
                  type="button"
                  className="botao secundario"
                  onClick={() =>
                    setValores({ ...valores, ...Object.fromEntries(faltando.map((a) => [a.parametro, "laje"])) })
                  }
                >
                  Usar pé-direito − laje em todos eles
                </button>
              </p>
            )}
          </div>
        )}
        {ambientes.map((a) => {
          const k = a.parametro;
          const ateLaje = valores[k] === "laje" || valores[k] === "teto";
          const codigos = [...a.codigos].sort().join(", ");
          if (a.corte != null)
            return (
              <label key={k}>
                {a.nome} (parede {codigos})
                <input value={`${num(a.corte)} m, lida no corte`} disabled />
              </label>
            );
          return (
            <label key={k}>
              {a.nome} (parede {codigos})
              <input
                inputMode="decimal"
                value={ateLaje ? "" : (valores[k] ?? "")}
                disabled={ateLaje}
                onChange={(e) => setValores({ ...valores, [k]: e.target.value })}
                placeholder={ateLaje ? textoLaje : "não está no corte: altura em m"}
              />
              <span className="marcar">
                <input
                  type="checkbox"
                  checked={ateLaje}
                  onChange={(e) => setValores({ ...valores, [k]: e.target.checked ? "laje" : "" })}
                />{" "}
                {textoLaje}
              </span>
            </label>
          );
        })}
        {vaos.length > 0 && (
          <div className="form-acoes">
            <h2>Vãos de portas e janelas</h2>
            <p className="faixa">
              Só vãos com área acima de {num(limite)} m² são descontados do revestimento; os de até {num(limite)} m² entram
              cheios. A planta não traz a altura das esquadrias: preencha pelo quadro de esquadrias. Largura medida no
              bloco, dentro da parede. Vão que nem com a altura máxima ({pml != null ? `${num(pml)} m` : "pé-direito − laje"}) passa
              de {num(limite)} m² não precisa de altura.
            </p>
          </div>
        )}
        {vaos.map((v) => {
          const ka = `altura_vao_${v.chave}`;
          const kp = `peitoril_vao_${v.chave}`;
          const dispensa = pml != null && v.largura_m * pml <= limite;
          return (
            <label key={v.chave}>
              {v.tipo === "janela" ? "Janela" : "Porta"} {num(v.largura_m)} m · {v.quantidade} vão(s) ·{" "}
              <span className="discreto">{v.ambientes.join(", ")}</span>
              <input
                inputMode="decimal"
                value={valores[ka] ?? ""}
                onChange={(e) => setValores({ ...valores, [ka]: e.target.value })}
                placeholder={dispensa ? "dispensada (até 2 m² de qualquer jeito)" : "altura do vão em m"}
              />
              {v.tipo === "janela" && (
                <input
                  inputMode="decimal"
                  value={valores[kp] ?? ""}
                  onChange={(e) => setValores({ ...valores, [kp]: e.target.value })}
                  placeholder="peitoril em m"
                />
              )}
            </label>
          );
        })}
        {paredes.length > 0 && (
          <div className="form-acoes">
            <h2>Altura por código de parede (opcional)</h2>
            <p className="discreto">Vale para os ambientes do código que não têm altura de corte nem altura própria acima.</p>
          </div>
        )}
        {paredes.map((c) => {
          const k = `altura_parede_${c}`;
          const ateTeto = valores[k] === "teto" || valores[k] === "laje";
          return (
            <label key={k}>
              Parede {c}: {descParede(c)}
              <input
                inputMode="decimal"
                value={ateTeto ? "" : (valores[k] ?? "")}
                disabled={ateTeto}
                onChange={(e) => setValores({ ...valores, [k]: e.target.value })}
                placeholder={ateTeto ? textoLaje : "altura em m, não informada"}
              />
              <span className="marcar">
                <input
                  type="checkbox"
                  checked={ateTeto}
                  onChange={(e) => setValores({ ...valores, [k]: e.target.checked ? "laje" : "" })}
                />{" "}
                {textoLaje}
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

import { useMemo, useState } from "react";
import { Acabamentos, AmbienteAcabamento } from "../api";
import { num } from "../formato";

// Tela de conferência dos ambientes: o que o Quantum leu (rótulo e etiqueta) ao lado do que ele
// mediu (contorno), com a situação de cada um escrita por extenso. Diretrizes em docs/INTERFACE.md.

/** Mesma tolerância que a detecção usa para aceitar um contorno (src/quantum/ambientes.py). */
const TOLERANCIA = 0.05;

type Situacao = "sem_contorno" | "divergente" | "proposta" | "confere";

const SITUACAO: Record<Situacao, { nome: string; classe: string; ajuda: string }> = {
  sem_contorno: {
    nome: "Sem contorno",
    classe: "sev-bloqueante",
    ajuda: "O Quantum não fechou o contorno: piso, teto e parede deste ambiente não foram medidos.",
  },
  divergente: {
    nome: "Área diverge",
    classe: "sev-alerta",
    ajuda: "A área medida difere mais de 5% da área do rótulo. Confira o contorno na aba Planta.",
  },
  proposta: {
    nome: "Divisa proposta",
    classe: "sev-alerta",
    ajuda: "Parte do contorno é uma divisa traçada pelo Quantum entre ambientes sem parede. Confira na aba Planta.",
  },
  confere: { nome: "Confere", classe: "sev-ok", ajuda: "Área medida até 5% da área do rótulo, contorno pelas paredes ou pela projeção." },
};
const ORDEM: Situacao[] = ["sem_contorno", "divergente", "proposta", "confere"];

const ORIGEM: Record<string, string> = {
  polilinha: "polilinha do desenho",
  paredes: "paredes",
  divisao: "linha de projeção",
  proposta: "divisa proposta",
};

type Linha = { a: AmbienteAcabamento; dif: number | null; situacao: Situacao };

function situacao(a: AmbienteAcabamento): { dif: number | null; situacao: Situacao } {
  if (a.area_contorno_m2 == null) return { dif: null, situacao: "sem_contorno" };
  const dif = a.area_rotulo > 0 ? (a.area_contorno_m2 - a.area_rotulo) / a.area_rotulo : null;
  if (dif !== null && Math.abs(dif) > TOLERANCIA) return { dif, situacao: "divergente" };
  if (a.contorno_origem === "proposta") return { dif, situacao: "proposta" };
  return { dif, situacao: "confere" };
}

const pct = (v: number | null) => (v === null ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(1).replace(".", ",")}%`);
const semAcento = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export default function Conferencia({ acabamentos, aoVerPlanta }: { acabamentos: Acabamentos; aoVerPlanta: () => void }) {
  const [filtro, setFiltro] = useState<"todos" | "conferir" | Situacao>("conferir");
  const [busca, setBusca] = useState("");

  const linhas: Linha[] = useMemo(
    () =>
      acabamentos.ambientes
        .map((a) => ({ a, ...situacao(a) }))
        .sort((x, y) => ORDEM.indexOf(x.situacao) - ORDEM.indexOf(y.situacao) || x.a.nome.localeCompare(y.a.nome, "pt-BR")),
    [acabamentos],
  );
  const conta = (s: Situacao) => linhas.filter((l) => l.situacao === s).length;
  const aConferir = linhas.filter((l) => l.situacao !== "confere").length;
  const visiveis = linhas.filter(
    (l) =>
      (filtro === "todos" || (filtro === "conferir" ? l.situacao !== "confere" : l.situacao === filtro)) &&
      (!busca.trim() || semAcento(l.a.nome).includes(semAcento(busca.trim()))),
  );
  const desc = (tipo: "piso" | "parede" | "teto", c?: string) => (c ? acabamentos.catalogo?.[tipo]?.[c] ?? "código fora do quadro" : "");
  const alturas = Object.entries(acabamentos.alturas_corte ?? {}).sort(([a], [b]) => a.localeCompare(b, "pt-BR"));

  const chip = (chave: typeof filtro, rotulo: string, n: number) => (
    <button key={chave} type="button" className={`chip ${filtro === chave ? "ativo" : ""}`} aria-pressed={filtro === chave} onClick={() => setFiltro(chave)}>
      {rotulo} <strong>{n}</strong>
    </button>
  );

  if (!linhas.length)
    return (
      <section className="cartao">
        <h2>Conferência dos ambientes</h2>
        <p className="discreto">
          Nenhum rótulo de ambiente foi encontrado na planta, então não há o que conferir. Confira na aba Camadas se os rótulos estão na
          camada de textos esperada.
        </p>
      </section>
    );

  return (
    <>
      <section className="cartao">
        <h2>Conferência dos ambientes</h2>
        <p className="conferencia-resumo" role="status">
          {linhas.length} ambientes no rótulo · {linhas.length - conta("sem_contorno")} com contorno medido · <strong>{aConferir} a conferir</strong>
        </p>
        <div className="chips" role="group" aria-label="Filtrar ambientes">
          {chip("conferir", "A conferir", aConferir)}
          {ORDEM.filter((s) => s !== "confere").map((s) => chip(s, SITUACAO[s].nome, conta(s)))}
          {chip("confere", SITUACAO.confere.nome, conta("confere"))}
          {chip("todos", "Todos", linhas.length)}
          <label className="busca">
            <span className="visivel-leitor">Buscar ambiente</span>
            <input type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar ambiente" />
          </label>
        </div>
        <p className="discreto pequeno">
          A área do rótulo é a escrita no projeto; a medida é a do contorno que o Quantum fechou, a mesma das polilinhas do DXF de
          acabamentos. Para ver um contorno, abra a{" "}
          <button type="button" className="link-btn" onClick={aoVerPlanta}>
            aba Planta
          </button>{" "}
          e clique no ambiente.
        </p>
        {visiveis.length === 0 ? (
          <p className="vazio">
            {filtro === "conferir" && !busca ? "Nada a conferir: todos os ambientes têm contorno e área dentro de 5% do rótulo." : "Nenhum ambiente com esse filtro."}
          </p>
        ) : (
          <div className="rolagem-tabela">
            <table className="tabela tabela-conferencia">
              <thead>
                <tr>
                  <th scope="col">Ambiente</th>
                  <th scope="col">Situação</th>
                  <th scope="col">Piso</th>
                  <th scope="col">Parede</th>
                  <th scope="col">Teto</th>
                  <th scope="col" className="num">
                    Rótulo (m²)
                  </th>
                  <th scope="col" className="num">
                    Medida (m²)
                  </th>
                  <th scope="col" className="num">
                    Diferença
                  </th>
                  <th scope="col" className="num">
                    Perímetro (m)
                  </th>
                  <th scope="col">Contorno por</th>
                </tr>
              </thead>
              <tbody>
                {visiveis.map(({ a, dif, situacao: s }, i) => (
                  <tr key={`${a.nome}-${i}`}>
                    <th scope="row">{a.nome}</th>
                    <td>
                      <span className={`selo ${SITUACAO[s].classe}`} title={SITUACAO[s].ajuda}>
                        {SITUACAO[s].nome}
                      </span>
                    </td>
                    {(["piso", "parede", "teto"] as const).map((t) => (
                      <td key={t} className="codigo" title={desc(t, a.codigos[t])}>
                        {a.codigos[t] ?? <span className="discreto">sem etiqueta</span>}
                      </td>
                    ))}
                    <td className="num">{num(a.area_rotulo)}</td>
                    <td className="num">{num(a.area_contorno_m2)}</td>
                    <td className={`num ${s === "divergente" ? "destaque-alerta" : ""}`}>{pct(dif)}</td>
                    <td className="num">{num(a.perimetro_m)}</td>
                    <td className="discreto">{a.contorno_origem ? ORIGEM[a.contorno_origem] ?? a.contorno_origem : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="cartao">
        <h2>Alturas lidas nos cortes</h2>
        {alturas.length === 0 ? (
          <p className="vazio">
            Nenhuma altura veio de corte. Os ambientes ficam com a altura informada em Parâmetros, ou como pendência se ela faltar.
          </p>
        ) : (
          <>
            <p className="discreto pequeno">
              Nome como está escrito no corte. Ambientes da planta que não aparecem aqui precisam da altura em Parâmetros (pé-direito menos a
              espessura da laje, quando o revestimento vai até o teto). Veja na aba Pendências quais ficaram sem altura.
            </p>
            <table className="tabela tabela-estreita">
              <thead>
                <tr>
                  <th scope="col">Ambiente no corte</th>
                  <th scope="col" className="num">
                    Altura do revestimento (m)
                  </th>
                </tr>
              </thead>
              <tbody>
                {alturas.map(([nome, h]) => (
                  <tr key={nome}>
                    <th scope="row">{nome}</th>
                    <td className="num">{num(h)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </>
  );
}

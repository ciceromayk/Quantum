import { PointerEvent as RPointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Acabamentos, AmbienteAcabamento, api, Geometria } from "../api";

// Visualizador do Model: desenho em canvas, com camadas, textos e os contornos de ambiente
// detectados. Arrastar move, roda do mouse ou pinça aproxima, clique num ambiente mostra os dados.

type Vista = { s: number; tx: number; ty: number }; // tela = (x*s + tx, -y*s + ty)

const ORIGEM: Record<string, { nome: string; cor: string }> = {
  polilinha: { nome: "polilinha do desenho", cor: "#1a7f37" },
  paredes: { nome: "detectado pelas paredes", cor: "#1a7f37" },
  divisao: { nome: "separado por linha de projeção", cor: "#1f5fbf" },
  proposta: { nome: "divisa proposta (conferir)", cor: "#d97706" },
};

function m2(v: number | null | undefined) {
  return v == null ? "—" : `${v.toFixed(2).replace(".", ",")} m²`;
}

function dentro(x: number, y: number, pts: [number, number][]) {
  let ok = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i];
    const [xj, yj] = pts[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) ok = !ok;
  }
  return ok;
}

export default function Visualizador({ analiseId, acabamentos }: { analiseId: number; acabamentos?: Acabamentos }) {
  const [geo, setGeo] = useState<Geometria | null | undefined>(undefined);
  const [erro, setErro] = useState("");
  useEffect(() => {
    api
      .geometria(analiseId)
      .then(setGeo)
      .catch((e) => setErro((e as Error).message));
  }, [analiseId]);

  if (erro) return <p className="erro">{erro}</p>;
  if (geo === undefined) return <p className="discreto">Montando o desenho…</p>;
  if (geo === null)
    return <p className="discreto">Esta análise é de antes do visualizador. Use Reprocessar no pavimento para ver o desenho.</p>;
  if (!geo.caixa) return <p className="discreto">Nenhuma linha no Model deste arquivo.</p>;
  return <Tela geo={geo} acabamentos={acabamentos} />;
}

function Tela({ geo, acabamentos }: { geo: Geometria; acabamentos?: Acabamentos }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const caixaRef = useRef<HTMLDivElement>(null);
  const [vista, setVista] = useState<Vista | null>(null);
  const [ocultas, setOcultas] = useState<Set<string>>(new Set());
  const [verTextos, setVerTextos] = useState(true);
  const [verAmbientes, setVerAmbientes] = useState(true);
  const [sel, setSel] = useState<AmbienteAcabamento | null>(null);
  const ponteiros = useRef(new Map<number, { x: number; y: number }>());
  const arrastou = useRef(false);

  const f = geo.fator_m || 1;
  const nomes = useMemo(() => Object.keys(geo.camadas).sort(), [geo]);
  // Caminhos montados uma vez, em metros; o zoom só muda a transformação.
  const caminhos = useMemo(() => {
    const out: Record<string, Path2D> = {};
    for (const [nome, c] of Object.entries(geo.camadas)) {
      const p = new Path2D();
      for (const l of c.linhas) {
        p.moveTo(l[0], l[1]);
        for (let i = 2; i < l.length; i += 2) p.lineTo(l[i], l[i + 1]);
      }
      out[nome] = p;
    }
    return out;
  }, [geo]);
  const ambientes = useMemo(
    () =>
      (acabamentos?.ambientes ?? [])
        .filter((a) => a.contorno && a.contorno.length > 2)
        .map((a) => ({ a, pts: a.contorno!.map(([x, y]) => [x * f, y * f] as [number, number]) })),
    [acabamentos, f],
  );

  const enquadrar = useCallback(() => {
    const el = canvas.current;
    const caixa = geo.foco ?? geo.caixa;
    if (!el || !caixa) return;
    const [x0, y0, x1, y1] = caixa;
    const w = el.clientWidth;
    const h = el.clientHeight;
    const s = 0.94 * Math.min(w / Math.max(x1 - x0, 1e-6), h / Math.max(y1 - y0, 1e-6));
    setVista({ s, tx: w / 2 - ((x0 + x1) / 2) * s, ty: h / 2 + ((y0 + y1) / 2) * s });
  }, [geo]);

  // tamanho do canvas acompanha o contêiner (e a densidade de pixels da tela)
  useEffect(() => {
    const el = canvas.current;
    const caixa = caixaRef.current;
    if (!el || !caixa) return;
    const ajustar = () => {
      const dpr = window.devicePixelRatio || 1;
      el.width = Math.round(el.clientWidth * dpr);
      el.height = Math.round(el.clientHeight * dpr);
      setVista((v) => (v ? { ...v } : v)); // redesenha no novo tamanho
    };
    ajustar();
    enquadrar();
    const ro = new ResizeObserver(ajustar);
    ro.observe(caixa);
    return () => ro.disconnect();
  }, [enquadrar]);

  // desenho
  useEffect(() => {
    const el = canvas.current;
    if (!el || !vista) return;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, el.width, el.height);
    ctx.setTransform(vista.s * dpr, 0, 0, -vista.s * dpr, vista.tx * dpr, vista.ty * dpr);
    if (verAmbientes) {
      for (const { a, pts } of ambientes) {
        const cor = ORIGEM[a.contorno_origem ?? ""]?.cor ?? "#1a7f37";
        ctx.beginPath();
        pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
        ctx.closePath();
        ctx.globalAlpha = a === sel ? 0.45 : 0.18;
        ctx.fillStyle = cor;
        ctx.fill();
        ctx.globalAlpha = 1;
      }
    }
    ctx.lineWidth = 1 / (vista.s * dpr);
    for (const nome of nomes) {
      if (ocultas.has(nome)) continue;
      ctx.strokeStyle = geo.camadas[nome].cor;
      ctx.stroke(caminhos[nome]);
    }
    if (verAmbientes && sel) {
      const item = ambientes.find((x) => x.a === sel);
      if (item) {
        ctx.beginPath();
        item.pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
        ctx.closePath();
        ctx.lineWidth = 3 / (vista.s * dpr);
        ctx.strokeStyle = ORIGEM[sel.contorno_origem ?? ""]?.cor ?? "#1a7f37";
        ctx.stroke();
      }
    }
    if (verTextos) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = "#1c2430";
      ctx.textBaseline = "bottom";
      for (const [x, y, h, txt, camada] of geo.textos) {
        if (ocultas.has(camada)) continue;
        const px = h * vista.s;
        if (px < 6) continue; // pequeno demais nesta escala
        const sx = x * vista.s + vista.tx;
        const sy = -y * vista.s + vista.ty;
        if (sx < -400 || sy < -50 || sx > el.clientWidth + 50 || sy > el.clientHeight + 400) continue;
        ctx.font = `${Math.min(px, 40)}px system-ui, sans-serif`;
        ctx.fillText(txt, sx, sy);
      }
    }
  }, [vista, ocultas, verTextos, verAmbientes, sel, caminhos, nomes, geo, ambientes]);

  function zoom(fator: number, cx: number, cy: number) {
    setVista((v) => v && { s: v.s * fator, tx: cx - (cx - v.tx) * fator, ty: cy - (cy - v.ty) * fator });
  }

  // roda do mouse: listener não passivo para impedir a rolagem da página
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const roda = (ev: WheelEvent) => {
      ev.preventDefault();
      const r = el.getBoundingClientRect();
      zoom(Math.exp(-ev.deltaY * 0.0015), ev.clientX - r.left, ev.clientY - r.top);
    };
    el.addEventListener("wheel", roda, { passive: false });
    return () => el.removeEventListener("wheel", roda);
  }, []);

  function aoApertar(ev: RPointerEvent<HTMLCanvasElement>) {
    ev.currentTarget.setPointerCapture(ev.pointerId);
    ponteiros.current.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    arrastou.current = false;
  }
  function aoMover(ev: RPointerEvent<HTMLCanvasElement>) {
    const mapa = ponteiros.current;
    const antes = mapa.get(ev.pointerId);
    if (!antes) return;
    const agora = { x: ev.clientX, y: ev.clientY };
    if (mapa.size === 1) {
      const dx = agora.x - antes.x;
      const dy = agora.y - antes.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) arrastou.current = true;
      setVista((v) => v && { ...v, tx: v.tx + dx, ty: v.ty + dy });
    } else if (mapa.size === 2) {
      const outro = [...mapa.entries()].find(([k]) => k !== ev.pointerId)![1];
      const d0 = Math.hypot(antes.x - outro.x, antes.y - outro.y);
      const d1 = Math.hypot(agora.x - outro.x, agora.y - outro.y);
      const r = ev.currentTarget.getBoundingClientRect();
      if (d0 > 0) zoom(d1 / d0, (agora.x + outro.x) / 2 - r.left, (agora.y + outro.y) / 2 - r.top);
      arrastou.current = true;
    }
    mapa.set(ev.pointerId, agora);
  }
  function aoSoltar(ev: RPointerEvent<HTMLCanvasElement>) {
    ponteiros.current.delete(ev.pointerId);
    if (arrastou.current || !vista || !verAmbientes) return;
    const r = ev.currentTarget.getBoundingClientRect();
    const x = (ev.clientX - r.left - vista.tx) / vista.s;
    const y = -(ev.clientY - r.top - vista.ty) / vista.s;
    const achados = ambientes.filter(({ pts }) => dentro(x, y, pts));
    // o menor contém o clique com mais precisão (ambientes não se sobrepõem, mas por garantia)
    achados.sort((p, q) => (p.a.area_contorno_m2 ?? 0) - (q.a.area_contorno_m2 ?? 0));
    setSel(achados[0]?.a ?? null);
  }

  const alternar = (nome: string) =>
    setOcultas((o) => {
      const n = new Set(o);
      if (n.has(nome)) n.delete(nome);
      else n.add(nome);
      return n;
    });

  const total = acabamentos?.ambientes.length ?? 0;

  return (
    <div className="visualizador">
      <div className="vis-barra">
        <button className="secundario-btn" onClick={enquadrar}>
          Enquadrar
        </button>
        <button className="secundario-btn" onClick={() => canvas.current && zoom(1.4, canvas.current.clientWidth / 2, canvas.current.clientHeight / 2)}>
          +
        </button>
        <button className="secundario-btn" onClick={() => canvas.current && zoom(1 / 1.4, canvas.current.clientWidth / 2, canvas.current.clientHeight / 2)}>
          −
        </button>
        <label className="marcar">
          <input type="checkbox" checked={verTextos} onChange={(e) => setVerTextos(e.target.checked)} /> Textos
        </label>
        {total > 0 && (
          <label className="marcar">
            <input type="checkbox" checked={verAmbientes} onChange={(e) => setVerAmbientes(e.target.checked)} /> Contornos dos ambientes (
            {ambientes.length} de {total})
          </label>
        )}
      </div>
      <div className="vis-corpo">
        <div className="vis-tela" ref={caixaRef}>
          <canvas
            ref={canvas}
            onPointerDown={aoApertar}
            onPointerMove={aoMover}
            onPointerUp={aoSoltar}
            onPointerCancel={(e) => ponteiros.current.delete(e.pointerId)}
            onDoubleClick={enquadrar}
            aria-label="Desenho do Model do arquivo enviado"
          />
          {sel && (
            <div className="vis-info">
              <strong>{sel.nome}</strong>
              <div>Rótulo: {m2(sel.area_rotulo)}</div>
              <div>Contorno: {m2(sel.area_contorno_m2)}</div>
              {sel.perimetro_m != null && <div>Perímetro de parede: {sel.perimetro_m.toFixed(2).replace(".", ",")} m</div>}
              <div>
                {(["piso", "parede", "teto"] as const)
                  .filter((t) => sel.codigos[t])
                  .map((t) => `${t[0].toUpperCase()}${t.slice(1)} ${sel.codigos[t]}`)
                  .join(" · ") || "Sem etiqueta de acabamento"}
              </div>
              <div className="discreto pequeno">{ORIGEM[sel.contorno_origem ?? ""]?.nome ?? ""}</div>
            </div>
          )}
        </div>
        <ul className="vis-camadas">
          {nomes.map((n) => (
            <li key={n}>
              <label className="marcar">
                <input type="checkbox" checked={!ocultas.has(n)} onChange={() => alternar(n)} />
                <span className="amostra" style={{ background: geo.camadas[n].cor }} />
                {n}
              </label>
            </li>
          ))}
        </ul>
      </div>
      <p className="discreto pequeno">
        Só o Model do arquivo (pranchas e layouts não entram). Arraste para mover, use a roda do mouse ou a pinça para aproximar, clique
        num ambiente para ver os dados.
        {verAmbientes && total > 0 && " Verde: contorno detectado; azul: separado por projeção; laranja: divisa proposta, a conferir."}
        {geo.cortado && " Desenho muito grande: parte das linhas não foi mostrada (os quantitativos usam o arquivo inteiro)."}
      </p>
    </div>
  );
}

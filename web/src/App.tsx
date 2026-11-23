import { useEffect, useState } from "react";
import { api } from "./api";
import Projetos from "./telas/Projetos";
import ProjetoTela from "./telas/Projeto";
import AnaliseTela from "./telas/Analise";

// Rotas por hash: #/  ·  #/projetos/3  ·  #/analises/7
function useRota() {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const f = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return hash.slice(1).split("/").filter(Boolean);
}

export default function App() {
  const partes = useRota();
  const [aviso, setAviso] = useState<string>("");
  useEffect(() => {
    api.saude().then((s) => setAviso(s.aviso)).catch(() => setAviso(""));
  }, []);

  let tela = <Projetos />;
  if (partes[0] === "projetos" && partes[1]) tela = <ProjetoTela id={Number(partes[1])} />;
  if (partes[0] === "analises" && partes[1]) tela = <AnaliseTela id={Number(partes[1])} />;

  return (
    <div className="app">
      <header className="topo">
        <a href="#/" className="marca">
          Quantum
        </a>
        <span className="subtitulo">Quantitativos e orçamento a partir de DXF</span>
      </header>
      <main className="conteudo">{tela}</main>
      {aviso && <footer className="aviso-rodape">{aviso}</footer>}
    </div>
  );
}

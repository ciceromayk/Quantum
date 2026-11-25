import { useEffect, useState } from "react";
import { AVISO, recuperarInterrompidas } from "./api";
import { banco } from "./banco";
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
  const [pronto, setPronto] = useState(false);
  const [erro, setErro] = useState("");
  const [versaoNova, setVersaoNova] = useState(false);
  useEffect(() => {
    banco
      .abrir()
      .then(() => recuperarInterrompidas().catch(() => undefined))
      .then(() => setPronto(true))
      .catch((e: Error) => setErro(e.message));
    const f = () => setVersaoNova(true);
    window.addEventListener("quantum:versao-nova", f);
    return () => window.removeEventListener("quantum:versao-nova", f);
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
      <main className="conteudo">
        {versaoNova && (
          <p className="erro" role="alert">O Quantum foi atualizado em outra aba. Recarregue esta página para continuar.</p>
        )}
        {erro ? (
          <div className="cartao">
            <p className="erro" role="alert">{erro}</p>
            <button onClick={() => window.location.reload()}>Recarregar</button>
          </div>
        ) : pronto ? (
          tela
        ) : (
          <p className="discreto">Abrindo os dados salvos neste navegador…</p>
        )}
      </main>
      <footer className="aviso-rodape">
        <p>{AVISO}</p>
        <p>
          Tudo roda neste navegador: os arquivos não são enviados a nenhum servidor e os dados ficam salvos só aqui. Use
          Exportar para fazer backup ou levar o projeto para outro computador.
        </p>
      </footer>
    </div>
  );
}

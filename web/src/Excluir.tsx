import { useState } from "react";

/**
 * Botão de exclusão em dois passos: o primeiro clique mostra o que será apagado e pede
 * confirmação na própria linha (sem janela do navegador). Nada é apagado sem o segundo clique.
 */
export default function Excluir({
  rotulo = "Excluir",
  pergunta,
  aoConfirmar,
  aoErrar,
  pequeno = true,
}: {
  rotulo?: string;
  pergunta: string;
  aoConfirmar: () => Promise<unknown>;
  aoErrar: (m: string) => void;
  pequeno?: boolean;
}) {
  const [aberto, setAberto] = useState(false);
  const [apagando, setApagando] = useState(false);

  const parar = (e: React.MouseEvent) => e.stopPropagation(); // não abre a linha clicável por baixo

  if (!aberto)
    return (
      <button
        type="button"
        className={pequeno ? "perigo-btn" : "perigo-btn grande"}
        onClick={(e) => {
          parar(e);
          aoErrar("");
          setAberto(true);
        }}
      >
        {rotulo}
      </button>
    );

  return (
    <span className="confirmar-exclusao" role="alertdialog" aria-label={pergunta} onClick={parar}>
      <span className="pergunta">{pergunta}</span>
      <button
        type="button"
        className="perigo-btn cheio"
        disabled={apagando}
        autoFocus
        onClick={async () => {
          setApagando(true);
          try {
            await aoConfirmar();
          } catch (err) {
            aoErrar((err as Error).message);
            setApagando(false);
            setAberto(false);
          }
        }}
      >
        {apagando ? "Excluindo…" : "Sim, excluir"}
      </button>
      <button type="button" className="secundario-btn" disabled={apagando} onClick={() => setAberto(false)}>
        Cancelar
      </button>
    </span>
  );
}

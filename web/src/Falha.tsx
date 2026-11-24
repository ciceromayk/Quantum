import { Component, ErrorInfo, ReactNode } from "react";

// Rede de segurança: o React 18 desmonta a página inteira quando um erro escapa de um render,
// e a tela fica em branco. Com esta barreira a pessoa vê o que aconteceu e consegue sair dali.

type Props = { children: ReactNode };
type Estado = { erro: Error | null };

export default class Falha extends Component<Props, Estado> {
  state: Estado = { erro: null };

  static getDerivedStateFromError(erro: Error): Estado {
    return { erro };
  }

  componentDidCatch(erro: Error, info: ErrorInfo) {
    console.error("Falha na tela:", erro, info.componentStack);
  }

  // sair para outra tela limpa o erro: a navegação por hash não remonta o app sozinha
  limpar = () => this.setState({ erro: null });

  componentDidMount() {
    window.addEventListener("hashchange", this.limpar);
  }

  componentWillUnmount() {
    window.removeEventListener("hashchange", this.limpar);
  }

  render() {
    const { erro } = this.state;
    if (!erro) return this.props.children;
    return (
      <div className="app">
        <header className="topo">
          <a href="#/" className="marca">
            Quantum
          </a>
          <span className="subtitulo">Quantitativos e orçamento a partir de DXF</span>
        </header>
        <main className="conteudo">
          <div className="cartao">
            <h1>Esta tela não abriu</h1>
            <p className="erro">{erro.message || String(erro)}</p>
            <p className="discreto">
              Os seus dados continuam salvos neste navegador. Recarregue a página; se a tela repetir o erro, volte para a
              lista e use <strong>Reprocessar</strong> na revisão, que refaz a análise com a versão atual.
            </p>
            <div className="acoes">
              <button onClick={() => window.location.reload()}>Recarregar</button>
              <button
                className="botao secundario"
                onClick={() => {
                  window.location.hash = "#/";
                  this.limpar();
                }}
              >
                Ir para Empreendimentos
              </button>
            </div>
            <details className="discreto pequeno">
              <summary>Detalhes técnicos</summary>
              <pre>{(erro.stack || "").slice(0, 1200)}</pre>
            </details>
          </div>
        </main>
      </div>
    );
  }
}

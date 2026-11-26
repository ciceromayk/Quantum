// Disciplinas de projeto de cada pavimento. O empreendimento é cadastrado, cada pavimento recebe
// os arquivos por disciplina, e cada disciplina diz o que o Quantum já quantifica e o que falta.
//
// Hoje só a Arquitetura (plantas de acabamentos + cortes) é processada pelo motor. As paredes e
// painéis (Alvenarias) saem da mesma análise da planta de arquitetura, como planta falada
// pré-classificada. As demais disciplinas guardam os arquivos no navegador, prontos para quando
// a extração de cada uma existir.

export type Disciplina =
  | "arquitetura"
  | "alvenarias"
  | "esquadrias"
  | "estrutura"
  | "eletrica"
  | "hidrossanitaria"
  | "incendio";

/** Situação da extração de quantitativos na disciplina, por extenso (não só por cor). */
export type Situacao = "quantifica" | "parcial" | "so_arquivos";

export interface InfoDisciplina {
  chave: Disciplina;
  nome: string;
  /** O que entra nesta disciplina (para o texto de envio). */
  arquivos: string;
  situacao: Situacao;
  /** O que o Quantum já faz com esta disciplina. */
  hoje: string;
  /** O que falta para quantificar (dados técnicos e regras que precisam vir do usuário ou do projeto). */
  falta: string[];
}

export const SITUACAO: Record<Situacao, string> = {
  quantifica: "Quantifica",
  parcial: "Quantifica em parte",
  so_arquivos: "Só guarda os arquivos",
};

export const DISCIPLINAS: InfoDisciplina[] = [
  {
    chave: "arquitetura",
    nome: "Arquitetura",
    arquivos: "plantas de acabamentos (piso, parede, forro) e cortes com as alturas de revestimento",
    situacao: "quantifica",
    hoje: "Detecta os ambientes, lê as etiquetas de acabamento, mede piso, forro, rodapé e revestimento de parede, lê as alturas dos cortes e gera o DXF de acabamentos.",
    falta: [],
  },
  {
    chave: "alvenarias",
    nome: "Alvenarias",
    arquivos: "plantas de alvenaria / paredes e painéis (planta falada)",
    situacao: "parcial",
    hoje: "A planta falada de paredes e painéis é gerada a partir da planta de arquitetura (aba Arquitetura) e alimenta a planilha padrão de paredes e painéis.",
    falta: [
      "Ler a planta de alvenaria própria enviada aqui (hoje ela só fica guardada; a medição usa a planta de arquitetura).",
      "Pé-esquerdo (piso a piso) e altura de viga por trecho, para descontar a viga da altura da parede.",
      "Especificação de bloco e espessura por camada ou etiqueta, quando a planta não trouxer.",
    ],
  },
  {
    chave: "esquadrias",
    nome: "Esquadrias",
    arquivos: "planta e quadro de esquadrias (portas, janelas, vidros, guarda-corpos)",
    situacao: "parcial",
    hoje: "Os vãos de portas e janelas da planta de arquitetura já são contados e usados no desconto de revestimento (só vãos acima de 2 m²).",
    falta: [
      "Ler o quadro de esquadrias deste arquivo (código, largura, altura, peitoril, tipologia e material).",
      "Casar cada código do quadro com os blocos da planta, para contar por tipologia.",
      "Altura e peitoril das esquadrias que o quadro não informar: ficam como pendência.",
    ],
  },
  {
    chave: "estrutura",
    nome: "Estrutura",
    arquivos: "formas do pavimento (pilares, vigas e lajes)",
    situacao: "so_arquivos",
    hoje: "Os arquivos ficam guardados neste pavimento. O motor tem regras de camada para pilares, vigas e lajes, ainda não ligadas a este envio.",
    falta: [
      "Padrão de camadas e textos do projetista (nomes de pilares, vigas e lajes e como vêm as dimensões, ex.: V12 14x50).",
      "Altura do lance de pilar e espessura de cada laje, quando não estiverem escritas na forma.",
      "Regra de medição de forma e concreto (descontos em cruzamentos de viga e pilar), a ser definida com você.",
    ],
  },
  {
    chave: "eletrica",
    nome: "Instalações elétricas",
    arquivos: "plantas de pontos, eletrodutos e quadros",
    situacao: "so_arquivos",
    hoje: "Os arquivos ficam guardados neste pavimento. O motor tem regras de camada para tomadas, interruptores, iluminação, quadros e eletrodutos, ainda não ligadas a este envio.",
    falta: [
      "Lista dos blocos usados para cada ponto (tomada baixa/média/alta, interruptor, luminária) no padrão do projetista.",
      "Pé-direito e altura de montagem dos pontos, para somar as descidas aos eletrodutos.",
      "Diâmetro dos eletrodutos e fiação: só entram se estiverem escritos no desenho.",
    ],
  },
  {
    chave: "hidrossanitaria",
    nome: "Hidrossanitárias",
    arquivos: "plantas e isométricos de água fria, água quente, esgoto e pluvial",
    situacao: "so_arquivos",
    hoje: "Os arquivos ficam guardados neste pavimento. O motor tem regras de camada para água fria, água quente, esgoto, pluvial e louças, ainda não ligadas a este envio.",
    falta: [
      "Padrão de camadas por sistema e como o diâmetro vem escrito nas tubulações.",
      "Trechos verticais: a planta não mostra a altura; o comprimento vem do isométrico ou fica como pendência.",
      "Lista de conexões e peças: só o que estiver desenhado ou no quadro de materiais.",
    ],
  },
  {
    chave: "incendio",
    nome: "Incêndio",
    arquivos: "plantas de prevenção e combate a incêndio (hidrantes, extintores, sinalização, detecção)",
    situacao: "so_arquivos",
    hoje: "Os arquivos ficam guardados neste pavimento. Ainda não há regras de camada para incêndio no motor.",
    falta: [
      "Padrão de blocos e camadas (extintor por tipo, hidrante, sinalização, detector, acionador, iluminação de emergência).",
      "Tubulação de hidrantes e sprinklers: diâmetro escrito no desenho e trechos verticais pelo isométrico.",
      "Regras de contagem a combinar com você (ex.: placas de sinalização por item ou por kit).",
    ],
  },
];

const POR_CHAVE = new Map(DISCIPLINAS.map((d) => [d.chave, d]));

export function infoDisciplina(chave: string): InfoDisciplina {
  return POR_CHAVE.get(chave as Disciplina) ?? POR_CHAVE.get("arquitetura")!;
}

/** Registros de antes das disciplinas (sem o campo) são da Arquitetura, que era tudo o que havia. */
export function disciplinaDe(registro: { disciplina?: string | null }): Disciplina {
  const d = registro.disciplina;
  return d && POR_CHAVE.has(d as Disciplina) ? (d as Disciplina) : "arquitetura";
}

export function ehDisciplina(chave: string): chave is Disciplina {
  return POR_CHAVE.has(chave as Disciplina);
}

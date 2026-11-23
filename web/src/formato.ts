export const num = (v: number | null | undefined, casas = 2) =>
  v === null || v === undefined
    ? "—"
    : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

export const dataHora = (iso: string | null) =>
  iso ? new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").toLocaleString("pt-BR", { timeZone: "America/Fortaleza" }) : "—";

export const STATUS: Record<string, string> = {
  na_fila: "Na fila",
  processando: "Processando",
  concluida: "Concluída",
  erro: "Erro",
};

export const SEVERIDADE: Record<string, string> = { bloqueante: "Bloqueante", alerta: "Alerta", info: "Info" };

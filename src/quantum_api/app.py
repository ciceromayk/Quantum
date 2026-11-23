"""Rotas da API do Quantum.

Rodar em desenvolvimento:  uvicorn quantum_api.main:app --reload
Documentação interativa:   http://127.0.0.1:8000/docs  (rotas sob /api)
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from quantum import AVISO_ESTIMATIVA, __version__

from .config import Config
from .db import Analise, Pavimento, Projeto, criar_sessoes
from .processamento import caminhos_relatorio, processar, recuperar_interrompidas
from .schemas import (
    PARAMETROS_CONHECIDOS,
    AnaliseDetalhe,
    AnaliseResumo,
    Parametros,
    PavimentoEntrada,
    PavimentoSaida,
    ProjetoEntrada,
    ProjetoSaida,
)

BLOCO_LEITURA = 1024 * 1024


def criar_app(config: Config | None = None) -> FastAPI:
    config = config or Config.do_ambiente()
    config.pasta_arquivos.mkdir(parents=True, exist_ok=True)
    sessoes: sessionmaker = criar_sessoes(config.database_url)
    recuperar_interrompidas(sessoes)

    app = FastAPI(
        title="Quantum",
        version=__version__,
        description="Quantitativos e orçamento a partir de DXF. " + AVISO_ESTIMATIVA,
    )

    rotas = APIRouter(prefix="/api")

    def sessao():
        with sessoes() as s:
            yield s

    def obter(s: Session, modelo, id_: int, nome: str):
        obj = s.get(modelo, id_)
        if obj is None:
            raise HTTPException(404, f"{nome} {id_} não encontrado")
        return obj

    # --- geral ------------------------------------------------------------------------

    @rotas.get("/saude")
    def saude():
        return {"status": "ok", "versao": __version__, "aviso": AVISO_ESTIMATIVA}

    @rotas.get("/parametros-conhecidos")
    def parametros_conhecidos():
        return PARAMETROS_CONHECIDOS

    # --- projetos ---------------------------------------------------------------------

    @rotas.post("/projetos", response_model=ProjetoSaida, status_code=201)
    def criar_projeto(dados: ProjetoEntrada, s: Session = Depends(sessao)):
        p = Projeto(**dados.model_dump())
        s.add(p)
        s.commit()
        s.refresh(p)
        return p

    @rotas.get("/projetos", response_model=list[ProjetoSaida])
    def listar_projetos(s: Session = Depends(sessao)):
        return s.scalars(select(Projeto).order_by(Projeto.id.desc())).all()

    @rotas.get("/projetos/{projeto_id}", response_model=ProjetoSaida)
    def ver_projeto(projeto_id: int, s: Session = Depends(sessao)):
        return obter(s, Projeto, projeto_id, "Projeto")

    # --- pavimentos -------------------------------------------------------------------

    @rotas.post("/projetos/{projeto_id}/pavimentos", response_model=PavimentoSaida, status_code=201)
    def criar_pavimento(projeto_id: int, dados: PavimentoEntrada, s: Session = Depends(sessao)):
        obter(s, Projeto, projeto_id, "Projeto")
        pav = Pavimento(projeto_id=projeto_id, parametros={}, **dados.model_dump())
        s.add(pav)
        s.commit()
        s.refresh(pav)
        return pav

    @rotas.get("/pavimentos/{pavimento_id}", response_model=PavimentoSaida)
    def ver_pavimento(pavimento_id: int, s: Session = Depends(sessao)):
        return obter(s, Pavimento, pavimento_id, "Pavimento")

    @rotas.put("/pavimentos/{pavimento_id}/parametros", response_model=PavimentoSaida)
    def definir_parametros(pavimento_id: int, dados: Parametros, s: Session = Depends(sessao)):
        """Substitui os parâmetros do pavimento. Reprocesse a análise para aplicá-los."""
        pav = obter(s, Pavimento, pavimento_id, "Pavimento")
        pav.parametros = dict(dados.valores)
        pav.unidade = dados.unidade
        s.commit()
        s.refresh(pav)
        return pav

    # --- arquivos e análises ----------------------------------------------------------

    @rotas.post("/pavimentos/{pavimento_id}/arquivos", response_model=AnaliseResumo, status_code=202)
    async def enviar_arquivo(
        pavimento_id: int,
        arquivo: UploadFile,
        tarefas: BackgroundTasks,
        s: Session = Depends(sessao),
    ):
        pav = obter(s, Pavimento, pavimento_id, "Pavimento")
        nome = (arquivo.filename or "arquivo").strip()
        sufixo = nome.lower().rsplit(".", 1)[-1] if "." in nome else ""
        if sufixo == "dwg":
            raise HTTPException(
                415, "DWG ainda não é lido na nuvem. Exporte o arquivo como DXF no CAD (Salvar como > DXF) e envie novamente."
            )
        if sufixo != "dxf":
            raise HTTPException(415, "Envie um arquivo .dxf")

        revisao = (s.scalar(select(func.max(Analise.revisao)).where(Analise.pavimento_id == pav.id)) or 0) + 1
        analise = Analise(pavimento_id=pav.id, revisao=revisao, arquivo_nome=nome[:300], arquivo_caminho="")
        s.add(analise)
        s.flush()  # gera o id; o nome no disco usa só ids, nunca o nome enviado
        destino = config.pasta_arquivos / f"pav{pav.id}_analise{analise.id}.dxf"
        limite = config.tamanho_max_mb * 1024 * 1024
        total = 0
        with destino.open("wb") as f:
            while bloco := await arquivo.read(BLOCO_LEITURA):
                total += len(bloco)
                if total > limite:
                    f.close()
                    destino.unlink(missing_ok=True)
                    s.rollback()
                    raise HTTPException(413, f"Arquivo maior que {config.tamanho_max_mb} MB")
                f.write(bloco)
        analise.arquivo_caminho = str(destino)
        s.commit()
        s.refresh(analise)
        tarefas.add_task(processar, sessoes, analise.id)
        return analise

    @rotas.post("/analises/{analise_id}/reprocessar", response_model=AnaliseResumo, status_code=202)
    def reprocessar(analise_id: int, tarefas: BackgroundTasks, s: Session = Depends(sessao)):
        """Roda de novo com os parâmetros e a unidade atuais do pavimento."""
        analise = obter(s, Analise, analise_id, "Análise")
        if analise.status == "processando":
            raise HTTPException(409, "A análise ainda está em processamento")
        analise.status = "na_fila"
        s.commit()
        s.refresh(analise)
        tarefas.add_task(processar, sessoes, analise.id)
        return analise

    @rotas.get("/analises/{analise_id}", response_model=AnaliseDetalhe)
    def ver_analise(analise_id: int, incluir_resultado: bool = True, s: Session = Depends(sessao)):
        analise = obter(s, Analise, analise_id, "Análise")
        sev = Counter(p["severidade"] for p in (analise.resultado or {}).get("pendencias", []))
        dados = AnaliseDetalhe.model_validate(analise, from_attributes=True)
        dados.pendencias_por_severidade = dict(sev)
        if not incluir_resultado:
            dados.resultado = None
        return dados

    @rotas.get("/analises/{analise_id}/relatorio.{formato}")
    def baixar_relatorio(analise_id: int, formato: str, s: Session = Depends(sessao)):
        analise = obter(s, Analise, analise_id, "Análise")
        if formato not in ("md", "xlsx"):
            raise HTTPException(404, "Formatos disponíveis: md, xlsx")
        if analise.status != "concluida":
            raise HTTPException(409, f"Análise ainda não concluída (status: {analise.status})")
        caminho = caminhos_relatorio(analise)[formato]
        if not caminho.exists():
            raise HTTPException(404, "Relatório não encontrado; reprocesse a análise")
        base = analise.arquivo_nome.rsplit(".", 1)[0]
        return FileResponse(caminho, filename=f"{base}_R{analise.revisao}.{formato}")

    app.include_router(rotas)

    # Interface web (build do Vite em web/dist), servida na raiz quando existir.
    if config.pasta_web and (config.pasta_web / "index.html").exists():
        app.mount("/", StaticFiles(directory=config.pasta_web, html=True), name="web")

    return app


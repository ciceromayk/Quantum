"""Modelos do banco (SQLAlchemy 2). SQLite em desenvolvimento, PostgreSQL em produção."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Projeto(Base):
    __tablename__ = "projetos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    endereco: Mapped[str | None] = mapped_column(String(300), default=None)
    data_base: Mapped[str | None] = mapped_column(String(20), default=None)  # ex.: "11/2026"
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    pavimentos: Mapped[list["Pavimento"]] = relationship(
        back_populates="projeto", cascade="all, delete-orphan", order_by="Pavimento.id"
    )


class Pavimento(Base):
    __tablename__ = "pavimentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    projeto_id: Mapped[int] = mapped_column(ForeignKey("projetos.id"))
    nome: Mapped[str] = mapped_column(String(120))
    repeticoes: Mapped[int] = mapped_column(Integer, default=1)
    parametros: Mapped[dict] = mapped_column(JSON, default=dict)  # pe_direito, altura_pilar... em metros
    unidade: Mapped[str | None] = mapped_column(String(4), default=None)  # sobrepõe $INSUNITS
    projeto: Mapped[Projeto] = relationship(back_populates="pavimentos")
    analises: Mapped[list["Analise"]] = relationship(
        back_populates="pavimento", cascade="all, delete-orphan", order_by="Analise.revisao"
    )


class Analise(Base):
    """Um arquivo DXF enviado para um pavimento (uma revisão) e o resultado do processamento."""

    __tablename__ = "analises"
    id: Mapped[int] = mapped_column(primary_key=True)
    pavimento_id: Mapped[int] = mapped_column(ForeignKey("pavimentos.id"))
    revisao: Mapped[int] = mapped_column(Integer)
    arquivo_nome: Mapped[str] = mapped_column(String(300))
    arquivo_caminho: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="na_fila")  # na_fila|processando|concluida|erro
    erro: Mapped[str | None] = mapped_column(Text, default=None)
    resultado: Mapped[dict | None] = mapped_column(JSON, default=None)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    pavimento: Mapped[Pavimento] = relationship(back_populates="analises")


def criar_sessoes(database_url: str) -> sessionmaker:
    if database_url.startswith("sqlite:///"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)

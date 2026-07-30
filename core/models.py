from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome_canonico: Mapped[str] = mapped_column(String, unique=True)
    categoria: Mapped[str] = mapped_column(String)  # strength | olympic | wod_movement | accessory
    traccia_1rm: Mapped[bool] = mapped_column(Boolean, default=False)

    aliases: Mapped[List["ExerciseAlias"]] = relationship(back_populates="exercise")


class ExerciseAlias(Base):
    __tablename__ = "exercise_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    alias: Mapped[str] = mapped_column(String, unique=True)

    exercise: Mapped["Exercise"] = relationship(back_populates="aliases")


class NomeEsercizioAlias(Base):
    """Mappa di unificazione per nomi esercizio/WOD duplicati (testo libero,
    non legata ai 9 sollevamenti tracciati per l'1RM - vedi ExerciseAlias sopra
    per quello). Popolata dall'azione di unione nel tab "Duplicati esercizi"."""

    __tablename__ = "nomi_esercizio_alias"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String, unique=True)
    nome_canonico: Mapped[str] = mapped_column(String)
    creato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome_mese: Mapped[str] = mapped_column(String)
    file_originale: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    data_import: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    json_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    weeks: Mapped[List["ProgramDay"]] = relationship(back_populates="program", cascade="all, delete-orphan")


class ProgramDay(Base):
    __tablename__ = "program_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))
    settimana: Mapped[int] = mapped_column(Integer)
    giorno_label: Mapped[str] = mapped_column(String)
    focus: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    program: Mapped["Program"] = relationship(back_populates="weeks")
    blocks: Mapped[List["ProgramBlock"]] = relationship(back_populates="day", cascade="all, delete-orphan")


class ProgramBlock(Base):
    __tablename__ = "program_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("program_days.id"))
    ordine: Mapped[int] = mapped_column(Integer, default=0)
    tipo: Mapped[str] = mapped_column(String)  # strength | complex | wod | accessorio
    esercizio: Mapped[str] = mapped_column(String)
    exercise_id: Mapped[Optional[int]] = mapped_column(ForeignKey("exercises.id"), nullable=True)
    schema_reps: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_carico_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_percentuale: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    riferimento_percentuale: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_rpe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    formato_wod: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    durata_wod_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    nome_wod: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    day: Mapped["ProgramDay"] = relationship(back_populates="blocks")
    exercise: Mapped[Optional["Exercise"]] = relationship()


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date)
    day_id: Mapped[Optional[int]] = mapped_column(ForeignKey("program_days.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    entries: Mapped[List["LogEntry"]] = relationship(back_populates="log", cascade="all, delete-orphan")


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_id: Mapped[int] = mapped_column(ForeignKey("logs.id"))
    block_id: Mapped[Optional[int]] = mapped_column(ForeignKey("program_blocks.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String)
    esercizio: Mapped[str] = mapped_column(String)
    exercise_id: Mapped[Optional[int]] = mapped_column(ForeignKey("exercises.id"), nullable=True)
    set_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    carico_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rpe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    formato_wod: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    nome_wod: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    risultato_tempo_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risultato_round: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risultato_reps_extra: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risultato_reps_totali: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    emom_minuti_per_round: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carico_totale_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    splits_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    log: Mapped["Log"] = relationship(back_populates="entries")
    exercise: Mapped[Optional["Exercise"]] = relationship()

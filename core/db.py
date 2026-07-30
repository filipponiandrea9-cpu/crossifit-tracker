from pathlib import Path

import streamlit as st
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from core.models import Base
from core.secrets import get_secret

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "crossfit.db"

DATABASE_URL = get_secret("DATABASE_URL")

if DATABASE_URL:
    # Connessione cloud (Postgres/Supabase) potenzialmente inattiva a lungo fra
    # una sessione Streamlit e l'altra: pool_pre_ping verifica/ricrea la
    # connessione prima di riusarla; pool contenuto perche' e' un solo utente.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=3, max_overflow=2)
else:
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@st.cache_resource(show_spinner=False)
def init_db() -> None:
    """Crea/migra lo schema e semina gli esercizi tracciati. Cache_resource la
    fa girare una sola volta per processo dell'app (non ad ogni rerun causato
    da un click), evitando un round-trip verso il DB - remoto su Postgres/
    Supabase - ad ogni interazione utente."""
    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        _migrate_schema()
    _seed_exercises()


def _migrate_schema() -> None:
    """Add columns introduced after a DB was already created, preserving existing rows."""
    nuove_colonne = {
        "log_entries": {
            "emom_minuti_per_round": "FLOAT",
            "carico_totale_kg": "FLOAT",
            "splits_json": "TEXT",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as conn:
        for tabella, colonne in nuove_colonne.items():
            if tabella not in inspector.get_table_names():
                continue
            esistenti = {c["name"] for c in inspector.get_columns(tabella)}
            for nome, tipo in colonne.items():
                if nome not in esistenti:
                    conn.execute(text(f"ALTER TABLE {tabella} ADD COLUMN {nome} {tipo}"))


def _seed_exercises() -> None:
    from core.models import Exercise

    tracked = [
        "Back Squat",
        "Front Squat",
        "Bench Press",
        "Deadlift",
        "Power Clean",
        "Power Snatch",
        "Split Jerk",
        "Push Press",
        "Clean & Jerk",
    ]
    with SessionLocal() as session:
        existing = {e.nome_canonico for e in session.query(Exercise).all()}
        for nome in tracked:
            if nome not in existing:
                session.add(Exercise(nome_canonico=nome, categoria="strength", traccia_1rm=True))
        session.commit()

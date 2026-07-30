"""Funzioni di persistenza del log allenamenti usate da Log_Giornaliero.py
per creare/aggiornare le voci di log dei blocchi pianificati."""

from __future__ import annotations

from datetime import date

from core.exercise_matching import resolve_exercise_id
from core.exercise_names import applica_alias_esercizio
from core.models import Log, LogEntry


def get_or_create_log(session, giorno_data: date, day_id) -> Log:
    log = session.query(Log).filter_by(data=giorno_data, day_id=day_id).first()
    if log is None:
        log = Log(data=giorno_data, day_id=day_id)
        session.add(log)
        session.flush()
    return log


def salva_wod(save_session, log_id: int, block_id, tipo: str, esercizio: str, values: dict) -> None:
    entry = None
    if block_id is not None:
        entry = save_session.query(LogEntry).filter_by(log_id=log_id, block_id=block_id).first()
    if entry is None:
        esercizio = applica_alias_esercizio(save_session, esercizio.strip())
        entry = LogEntry(log_id=log_id, block_id=block_id, tipo=tipo, esercizio=esercizio)
        entry.exercise_id = resolve_exercise_id(save_session, esercizio)
        save_session.add(entry)
    for field, value in values.items():
        setattr(entry, field, value)

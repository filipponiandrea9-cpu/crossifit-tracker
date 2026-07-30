from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from core.models import Exercise, Log, LogEntry, ProgramDay


def rpe_to_rir(rpe: Optional[float]) -> float:
    """Standard linear RPE->RIR conversion (RPE8=2RIR, RPE9=1RIR, RPE10=0RIR).

    Extends linearly to other RPE values (RIR = 10 - RPE), clamped at 0. If RPE is
    missing, assumes RIR=0 (the logged reps are treated as an all-out set).
    """
    if rpe is None:
        return 0.0
    return max(0.0, 10.0 - rpe)


def epley_1rm(weight: float, reps: float) -> float:
    return weight * (1 + reps / 30)


def brzycki_1rm(weight: float, reps: float) -> Optional[float]:
    denom = 37 - reps
    if denom <= 0:
        return None
    return weight * 36 / denom


def estimate_1rm(weight: float, reps: int, rpe: Optional[float]) -> dict:
    """Estimate 1RM from a logged set, adjusting reps for RIR when RPE is known.

    Returns a dict with epley, brzycki (nullable), and average (mean of the two,
    or just epley if brzycki is undefined for this rep range).
    """
    adjusted_reps = reps + rpe_to_rir(rpe)
    epley = epley_1rm(weight, adjusted_reps)
    brzycki = brzycki_1rm(weight, adjusted_reps)
    average = (epley + brzycki) / 2 if brzycki is not None else epley
    return {"epley": epley, "brzycki": brzycki, "average": average}


def calcola_streak(session: Session, riferimento: Optional[date] = None) -> int:
    """Giorni consecutivi (fino a `riferimento`, default oggi) con almeno un `Log`
    che abbia >=1 `LogEntry`. Se il giorno più recente loggato è precedente a ieri,
    lo streak è già interrotto e la funzione ritorna 0."""
    riferimento = riferimento or date.today()
    giorni = sorted(
        {
            log_data
            for (log_data,) in (
                session.query(Log.data).join(LogEntry, LogEntry.log_id == Log.id).distinct()
            )
        },
        reverse=True,
    )
    if not giorni or giorni[0] < riferimento - timedelta(days=1):
        return 0
    streak = 1
    for i in range(1, len(giorni)):
        if giorni[i - 1] - giorni[i] == timedelta(days=1):
            streak += 1
        else:
            break
    return streak


def conta_pr_nel_mese(session: Session, anno: int, mese: int) -> int:
    """Conta i set (tra i sollevamenti tracciati per l'1RM) il cui 1RM stimato
    supera il massimo storico precedente a quella data, con data nel mese/anno
    indicati. Copre solo i PR di forza (1RM stimato via `estimate_1rm`), non i
    risultati WOD - un miglior tempo/round è un confronto strutturalmente
    diverso e non è incluso qui."""
    esercizi_tracciati = session.query(Exercise).filter_by(traccia_1rm=True).all()
    pr_nel_mese = 0
    for esercizio in esercizi_tracciati:
        righe = (
            session.query(LogEntry, Log.data)
            .join(Log, LogEntry.log_id == Log.id)
            .filter(
                LogEntry.exercise_id == esercizio.id,
                LogEntry.carico_kg.isnot(None),
                LogEntry.reps.isnot(None),
            )
            .order_by(Log.data)
            .all()
        )
        record = None
        for entry, log_data in righe:
            stima = estimate_1rm(entry.carico_kg, entry.reps, entry.rpe)["average"]
            if record is None or stima > record:
                if record is not None and log_data.year == anno and log_data.month == mese:
                    pr_nel_mese += 1
                record = stima
    return pr_nel_mese


def calcola_aderenza(session: Session, program_id: int, data_da: date, data_a: date) -> dict:
    """% aderenza al piano, adattata: `ProgramDay` non ha una data propria (è
    tracciato per settimana/numero allenamento, non per data solare), quindi
    "sessione pianificata fatta" è misurata guardando se almeno un `Log`
    collegato a quel `ProgramDay` cade nel periodo filtrato - invece del
    letterale "ProgramDay con data passata" del testo di riferimento.

    Ritorna {"fatte": int, "pianificate": int, "percentuale": float}."""
    pianificate = session.query(ProgramDay).filter_by(program_id=program_id).count()
    fatte = (
        session.query(ProgramDay.id)
        .join(Log, Log.day_id == ProgramDay.id)
        .join(LogEntry, LogEntry.log_id == Log.id)
        .filter(ProgramDay.program_id == program_id, Log.data >= data_da, Log.data <= data_a)
        .distinct()
        .count()
    )
    percentuale = round(100 * fatte / pianificate, 1) if pianificate else 0.0
    return {"fatte": fatte, "pianificate": pianificate, "percentuale": percentuale}


def distribuzione_rpe(session: Session, data_da: date, data_a: date, tipo: Optional[str] = None) -> list:
    """Istogramma di `LogEntry.rpe` nel periodo, bucket interi 1-10 (indice 0 =
    RPE 1, indice 9 = RPE 10). RPE non intero è arrotondato al bucket più vicino."""
    query = (
        session.query(LogEntry.rpe)
        .join(Log, LogEntry.log_id == Log.id)
        .filter(Log.data >= data_da, Log.data <= data_a, LogEntry.rpe.isnot(None))
    )
    if tipo and tipo != "Tutti":
        query = query.filter(LogEntry.tipo == tipo.lower())
    conteggi = [0] * 10
    for (rpe,) in query.all():
        bucket = max(1, min(10, round(rpe))) - 1
        conteggi[bucket] += 1
    return conteggi


def metriche_periodo(session: Session, data_da: date, data_a: date, tipo: Optional[str] = None) -> dict:
    """Metriche aggregate per un periodo, usate sia dalla vista Confronto (due
    volte, periodo A e B) sia dalle stat-card di Statistiche. `tipo` filtra per
    tipo blocco ("strength"/"complex"/"wod"/"accessorio"), None/"Tutti" = nessun filtro.

    Ritorna {"volume_totale", "tonnellaggio", "n_sessioni", "rpe_medio", "pr_ottenuti"}.
    "Tonnellaggio" è il volume (kg x reps) del solo esercizio principale tracciato
    per l'1RM (il primo in ordine alfabetico tra quelli con `traccia_1rm=True`),
    a differenza di "Volume totale" che somma tutti i blocchi di forza/complessi."""
    query_entries = session.query(LogEntry, Log.data).join(Log, LogEntry.log_id == Log.id).filter(
        Log.data >= data_da, Log.data <= data_a
    )
    if tipo and tipo != "Tutti":
        query_entries = query_entries.filter(LogEntry.tipo == tipo.lower())
    righe = query_entries.all()

    volume_totale = sum(
        e.carico_kg * e.reps for e, _ in righe if e.tipo in ("strength", "complex") and e.carico_kg and e.reps
    )
    rpe_validi = [e.rpe for e, _ in righe if e.rpe is not None]
    rpe_medio = round(sum(rpe_validi) / len(rpe_validi), 1) if rpe_validi else None
    n_sessioni = len({d for _, d in righe})

    esercizio_principale = (
        session.query(Exercise).filter_by(traccia_1rm=True).order_by(Exercise.nome_canonico).first()
    )
    tonnellaggio = 0.0
    if esercizio_principale is not None:
        tonnellaggio = sum(
            e.carico_kg * e.reps
            for e, _ in righe
            if e.exercise_id == esercizio_principale.id and e.carico_kg and e.reps
        )

    pr_ottenuti = 0
    esercizi_tracciati = session.query(Exercise).filter_by(traccia_1rm=True).all()
    for esercizio in esercizi_tracciati:
        storico = (
            session.query(LogEntry, Log.data)
            .join(Log, LogEntry.log_id == Log.id)
            .filter(
                LogEntry.exercise_id == esercizio.id,
                LogEntry.carico_kg.isnot(None),
                LogEntry.reps.isnot(None),
            )
            .order_by(Log.data)
            .all()
        )
        record = None
        for entry, log_data in storico:
            stima = estimate_1rm(entry.carico_kg, entry.reps, entry.rpe)["average"]
            if record is None or stima > record:
                if record is not None and data_da <= log_data <= data_a:
                    pr_ottenuti += 1
                record = stima

    return {
        "volume_totale": volume_totale,
        "tonnellaggio": tonnellaggio,
        "n_sessioni": n_sessioni,
        "rpe_medio": rpe_medio,
        "pr_ottenuti": pr_ottenuti,
    }

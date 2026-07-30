import json
import re
from typing import Optional

AMRAP = "AMRAP"
EMOM = "EMOM"
FOR_TIME = "For Time"
ROUND_LIBERI = "Round liberi"
VOLUME_ACCUMULATION = "Volume Accumulation"
LIBERO = "Libero/Altro"

WOD_FORMATS = [AMRAP, EMOM, FOR_TIME, ROUND_LIBERI, VOLUME_ACCUMULATION, LIBERO]

# Campi da mostrare per ciascun formato. "Libero/Altro" mostra tutto.
CAMPI_PER_FORMATO = {
    AMRAP: {"round", "reps_extra"},
    EMOM: {"emom_minuti", "round", "reps_totali"},
    FOR_TIME: {"tempo", "splits"},
    ROUND_LIBERI: {"round"},
    VOLUME_ACCUMULATION: {"reps_totali", "carico_totale"},
    LIBERO: {"tempo", "round", "reps_extra", "reps_totali", "emom_minuti", "carico_totale"},
}

# "E5MO5M", "E2MOM", "EMOM", "ogni 5:00", "ogni 3 min" -> intervallo in minuti
_EMOM_PATTERNS = [
    re.compile(r"\bE(\d+)MO\d*M\b", re.IGNORECASE),   # E5MO5M
    re.compile(r"\bE(\d+)MOM\b", re.IGNORECASE),      # E2MOM
    re.compile(r"\bogni\s+(\d+)\s*:\s*\d+", re.IGNORECASE),  # ogni 5:00
    re.compile(r"\bogni\s+(\d+)\s*min", re.IGNORECASE),      # ogni 3 min
]


def deduce_wod_format(*testi: Optional[str]) -> str:
    """Guess the WOD format from the free-text fields of the imported program.

    Checks the given strings (typically formato_wod, esercizio, note) in order and
    returns one of WOD_FORMATS. Falls back to LIBERO when nothing matches.
    """
    testo = " ".join(t for t in testi if t).lower()
    if not testo.strip():
        return LIBERO

    if "amrap" in testo:
        return AMRAP
    if "emom" in testo or re.search(r"\be\d+mo\d*m\b", testo) or "ogni" in testo:
        return EMOM
    if "volume accumulation" in testo or "accumulation" in testo:
        return VOLUME_ACCUMULATION
    if "for time" in testo or "death by" in testo or "tabata" in testo:
        return FOR_TIME
    if "round" in testo:
        return ROUND_LIBERI
    return LIBERO


def deduce_emom_interval(*testi: Optional[str]) -> Optional[float]:
    """Extract the ExMOM interval in minutes (E5MO5M -> 5, 'ogni 3 min' -> 3).

    Returns None when no interval is stated; a plain "EMOM" implies 1 minute.
    """
    testo = " ".join(t for t in testi if t)
    if not testo.strip():
        return None
    for pattern in _EMOM_PATTERNS:
        match = pattern.search(testo)
        if match:
            return float(match.group(1))
    if re.search(r"\bemom\b", testo, re.IGNORECASE):
        return 1.0
    return None


def campi_visibili(formato: Optional[str]) -> set:
    return CAMPI_PER_FORMATO.get(formato or LIBERO, CAMPI_PER_FORMATO[LIBERO])


def parse_splits(splits_json: Optional[str]) -> list:
    """Deserialize LogEntry.splits_json into a list of {"label": str, "time_sec": int}.

    Returns [] for None/empty/malformed data — log entries saved before this field
    existed simply have no splits, not an error.
    """
    if not splits_json:
        return []
    try:
        dati = json.loads(splits_json)
    except (ValueError, TypeError):
        return []
    if not isinstance(dati, list):
        return []
    risultato = []
    for voce in dati:
        if isinstance(voce, dict) and "label" in voce and "time_sec" in voce:
            risultato.append({"label": str(voce["label"]), "time_sec": int(voce["time_sec"])})
    return risultato


def serialize_splits(splits: list) -> Optional[str]:
    """Inverse of parse_splits. Returns None for an empty list (nothing to store)."""
    puliti = [
        {"label": str(s["label"]), "time_sec": int(s["time_sec"])}
        for s in splits
        if s.get("label") and s.get("time_sec") is not None
    ]
    return json.dumps(puliti) if puliti else None

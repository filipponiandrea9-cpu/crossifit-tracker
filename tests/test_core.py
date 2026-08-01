from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import plotly.express as px
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.calculations import brzycki_1rm, epley_1rm, estimate_1rm, rpe_to_rir
from core.chart_utils import guarda_asse_singolo_punto
from core.exercise_names import (
    applica_alias_esercizio,
    get_nomi_esercizi_esistenti,
    normalizza_nome_esercizio,
    trova_possibili_duplicati,
    unifica_nomi_esercizio,
)
from core.llm_parser import parse_program_with_claude
from core.models import Base, Exercise, Log, LogEntry, Program, ProgramBlock, ProgramDay
from core.wod_format import (
    AMRAP,
    EMOM,
    FOR_TIME,
    LIBERO,
    ROUND_LIBERI,
    VOLUME_ACCUMULATION,
    campi_visibili,
    deduce_emom_interval,
    deduce_wod_format,
    parse_splits,
    serialize_splits,
)


@pytest.mark.parametrize(
    "testi,atteso",
    [
        (("For Time", "Bb Thrusters + Pull Ups"), FOR_TIME),
        (("AMRAP 12", "Burpees"), AMRAP),
        (("8 Min EMOM", "Bb Power Clean"), EMOM),
        (("20 Min E5MO5M (ogni 5:00 x 4 sets)", "Bb Power Snatch"), EMOM),
        (("24 Min E6MO6M", "Double Db Devil Press"), EMOM),
        (("10 Min Volume Accumulation", "Double Db Box Step Overs"), VOLUME_ACCUMULATION),
        (("6 Round", "Bb Thrusters (40kg) 10 Reps"), ROUND_LIBERI),
        ((None, "Qualcosa di non categorizzabile"), LIBERO),
        ((None, None), LIBERO),
    ],
)
def test_deduce_wod_format(testi, atteso):
    assert deduce_wod_format(*testi) == atteso


@pytest.mark.parametrize(
    "testi,atteso",
    [
        (("20 Min E5MO5M",), 5.0),
        (("24 Min E6MO6M",), 6.0),
        (("E2MOM",), 2.0),
        (("8 Min EMOM",), 1.0),
        (("Ogni 3 min x 5 sets",), 3.0),
        (("For Time",), None),
    ],
)
def test_deduce_emom_interval(testi, atteso):
    assert deduce_emom_interval(*testi) == atteso


def test_campi_visibili_per_formato():
    assert campi_visibili(AMRAP) == {"round", "reps_extra"}
    assert "tempo" not in campi_visibili(AMRAP)
    assert "emom_minuti" in campi_visibili(EMOM)
    assert campi_visibili(FOR_TIME) == {"tempo", "splits"}
    assert campi_visibili(ROUND_LIBERI) == {"round"}
    assert campi_visibili(VOLUME_ACCUMULATION) == {"reps_totali", "carico_totale"}
    # Libero mostra tutto, e un formato sconosciuto ricade su Libero
    assert campi_visibili(LIBERO) == campi_visibili("formato-inesistente")


def parse_default_reps(schema_reps):
    """Copia della logica in pages/2_Log_Giornaliero.py (le pagine Streamlit non
    sono importabili fuori dal runtime di Streamlit)."""
    if not schema_reps:
        return [1]
    segmenti = [s for s in schema_reps.replace(" ", "").split("-") if s]
    if not segmenti:
        return [1]
    reps = []
    for seg in segmenti:
        if seg.startswith("("):
            reps.append(1)
        else:
            cifre = "".join(ch for ch in seg if ch.isdigit())
            reps.append(int(cifre) if cifre else 1)
    return reps


@pytest.mark.parametrize(
    "schema,atteso",
    [
        ("1-1-1-1-1-1-1-1-1-1", [1] * 10),
        ("8-8-8-8", [8, 8, 8, 8]),
        ("(1+1+1)-(1+1+1)-(1+1+1)", [1, 1, 1]),
        ("21-15-9", [21, 15, 9]),
        (None, [1]),
        ("", [1]),
    ],
)
def test_parse_default_reps(schema, atteso):
    assert parse_default_reps(schema) == atteso


def valida_sets(edited_df):
    """Copia della validazione in pages/2_Log_Giornaliero.py."""
    errori, avvisi = [], []
    for i, row in edited_df.reset_index(drop=True).iterrows():
        carico, reps, rpe = row.get("carico_kg"), row.get("reps"), row.get("rpe")
        if pd.isna(carico) and pd.isna(reps) and pd.isna(rpe):
            continue
        num = i + 1
        if pd.notna(rpe) and not (1 <= float(rpe) <= 10):
            errori.append(f"Set {num}: RPE {rpe} fuori range (ammesso 1-10).")
        if pd.notna(reps) and pd.isna(carico):
            avvisi.append(f"Set {num}: reps senza carico.")
        elif pd.notna(carico) and pd.isna(reps):
            avvisi.append(f"Set {num}: carico senza reps.")
    return errori, avvisi


def test_valida_sets_reps_senza_carico():
    df = pd.DataFrame([{"carico_kg": None, "reps": 5, "rpe": 8}])
    errori, avvisi = valida_sets(df)
    assert not errori
    assert "reps senza carico" in avvisi[0]


def test_valida_sets_carico_senza_reps():
    df = pd.DataFrame([{"carico_kg": 100.0, "reps": None, "rpe": None}])
    errori, avvisi = valida_sets(df)
    assert not errori
    assert "carico senza reps" in avvisi[0]


@pytest.mark.parametrize("rpe", [0.5, 11, 15])
def test_valida_sets_rpe_fuori_range(rpe):
    df = pd.DataFrame([{"carico_kg": 100.0, "reps": 5, "rpe": rpe}])
    errori, _ = valida_sets(df)
    assert errori and "fuori range" in errori[0]


def test_valida_sets_riga_valida_e_riga_vuota():
    df = pd.DataFrame(
        [
            {"carico_kg": 100.0, "reps": 5, "rpe": 8.0},
            {"carico_kg": None, "reps": None, "rpe": None},
        ]
    )
    errori, avvisi = valida_sets(df)
    assert not errori and not avvisi


def test_rpe_to_rir():
    assert rpe_to_rir(8) == 2
    assert rpe_to_rir(9) == 1
    assert rpe_to_rir(10) == 0
    assert rpe_to_rir(None) == 0
    assert rpe_to_rir(12) == 0  # clamp


def test_estimate_1rm_con_rpe_aggiunge_rir():
    senza = estimate_1rm(100, 5, 10)
    con = estimate_1rm(100, 5, 8)
    assert con["average"] > senza["average"]


def test_estimate_1rm_formule():
    stime = estimate_1rm(100, 5, 10)
    assert stime["epley"] == pytest.approx(epley_1rm(100, 5))
    assert stime["brzycki"] == pytest.approx(brzycki_1rm(100, 5))
    assert stime["average"] == pytest.approx((stime["epley"] + stime["brzycki"]) / 2)


def test_brzycki_indefinito_ad_alte_reps():
    assert brzycki_1rm(100, 37) is None
    stime = estimate_1rm(100, 40, None)
    assert stime["brzycki"] is None
    assert stime["average"] == stime["epley"]


def test_serialize_parse_splits_roundtrip():
    splits = [{"label": "Round 1", "time_sec": 90}, {"label": "Round 2", "time_sec": 195}]
    serializzato = serialize_splits(splits)
    assert parse_splits(serializzato) == splits


def test_parse_splits_retrocompatibile_con_none():
    # Log salvati prima dell'introduzione degli splits hanno splits_json=None
    assert parse_splits(None) == []
    assert parse_splits("") == []


def test_parse_splits_ignora_dati_malformati():
    assert parse_splits("non è json") == []
    assert parse_splits("42") == []
    assert parse_splits('[{"label": "ok"}]') == []  # manca time_sec


def test_serialize_splits_scarta_righe_incomplete():
    splits = [{"label": "Round 1", "time_sec": 60}, {"label": "", "time_sec": 120}, {"label": "Round 3", "time_sec": None}]
    serializzato = serialize_splits(splits)
    assert parse_splits(serializzato) == [{"label": "Round 1", "time_sec": 60}]


def test_serialize_splits_lista_vuota_da_none():
    assert serialize_splits([]) is None


def test_guarda_asse_singolo_punto_forza_categoria_con_un_solo_valore():
    df = pd.DataFrame({"data": ["2026-07-27"], "valore": [132.2]})
    fig = px.line(df, x="data", y="valore")
    guarda_asse_singolo_punto(fig, df["data"].nunique())
    assert fig.layout.xaxis.type == "category"


def test_guarda_asse_singolo_punto_non_tocca_asse_con_piu_valori():
    df = pd.DataFrame({"data": ["2026-07-06", "2026-07-13", "2026-07-20"], "valore": [100, 105, 110]})
    fig = px.line(df, x="data", y="valore")
    guarda_asse_singolo_punto(fig, df["data"].nunique())
    assert fig.layout.xaxis.type != "category"


@pytest.mark.parametrize(
    "testo,atteso",
    [
        ("  bb   THRUSTERS  ", "Bb Thrusters"),
        ("good mornings", "Good Mornings"),
        ("romanian   deadlift", "Romanian Deadlift"),
        ("Back Squat", "Back Squat"),
    ],
)
def test_normalizza_nome_esercizio(testo, atteso):
    assert normalizza_nome_esercizio(testo) == atteso


def test_trova_possibili_duplicati_rileva_varianti_simili():
    nomi = ["Back Squat", "Bak Squat", "Deadlift", "Romanian Deadlift"]
    duplicati = trova_possibili_duplicati(nomi, soglia=80)
    coppie = {frozenset((a, b)) for a, b, _ in duplicati}
    assert frozenset(("Back Squat", "Bak Squat")) in coppie


def test_trova_possibili_duplicati_nessun_falso_positivo_tra_esercizi_diversi():
    nomi = ["Back Squat", "Bench Press", "Deadlift"]
    duplicati = trova_possibili_duplicati(nomi, soglia=85)
    assert duplicati == []


def test_trova_possibili_duplicati_soglia_piu_alta_riduce_i_risultati():
    nomi = ["Back Squat", "Bak Squat", "Front Squat"]
    pochi = trova_possibili_duplicati(nomi, soglia=95)
    molti = trova_possibili_duplicati(nomi, soglia=60)
    assert len(pochi) <= len(molti)


def test_trova_possibili_duplicati_ignora_pura_differenza_di_maiuscole():
    # Stesso nome a meno di maiuscole/spazi: la normalizzazione dovrebbe già
    # unificarli a monte, ma la funzione non deve comunque duplicare la coppia.
    nomi = ["Back Squat", "back squat"]
    duplicati = trova_possibili_duplicati(nomi, soglia=85)
    assert duplicati == []


# --- Unificazione esercizi duplicati: DB SQLite in-memory, non tocca data/crossfit.db ---


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_programma(session, esercizio_blocco="Bb Back Squat"):
    programma = Program(nome_mese="Test")
    session.add(programma)
    session.flush()
    giorno = ProgramDay(program_id=programma.id, settimana=1, giorno_label="Day 1")
    session.add(giorno)
    session.flush()
    blocco = ProgramBlock(day_id=giorno.id, ordine=1, tipo="strength", esercizio=esercizio_blocco)
    session.add(blocco)
    session.flush()
    return blocco


def _seed_log_entry(session, esercizio="Bb Back Squat", carico_kg=100.0):
    log = Log(data=date(2026, 7, 27))
    session.add(log)
    session.flush()
    voce = LogEntry(log_id=log.id, block_id=None, tipo="strength", esercizio=esercizio, carico_kg=carico_kg, reps=5)
    session.add(voce)
    session.flush()
    return voce


def test_applica_alias_esercizio_senza_mappa_ritorna_invariato(db_session):
    assert applica_alias_esercizio(db_session, "Bb Back Squat") == "Bb Back Squat"


def test_applica_alias_esercizio_con_mappa(db_session):
    _seed_programma(db_session)
    unifica_nomi_esercizio(db_session, "Bb Back Squat", "Back Squat")
    assert applica_alias_esercizio(db_session, "Bb Back Squat") == "Back Squat"


def test_applica_alias_esercizio_segue_la_catena(db_session):
    _seed_programma(db_session, esercizio_blocco="Bak Squat")
    unifica_nomi_esercizio(db_session, "Bak Squat", "Bb Back Squat")
    unifica_nomi_esercizio(db_session, "Bb Back Squat", "Back Squat")
    # "Bak Squat" -> "Bb Back Squat" (collassato) -> "Back Squat"
    assert applica_alias_esercizio(db_session, "Bak Squat") == "Back Squat"


def test_unifica_nomi_esercizio_riscrive_program_block_e_log_entry(db_session):
    _seed_programma(db_session, esercizio_blocco="Bb Back Squat")
    _seed_log_entry(db_session, esercizio="Bb Back Squat")

    risultato = unifica_nomi_esercizio(db_session, "Bb Back Squat", "Back Squat")

    assert risultato == {"blocchi_aggiornati": 1, "voci_log_aggiornate": 1}
    assert db_session.query(ProgramBlock).filter_by(esercizio="Bb Back Squat").count() == 0
    assert db_session.query(ProgramBlock).filter_by(esercizio="Back Squat").count() == 1
    voce = db_session.query(LogEntry).first()
    assert voce.esercizio == "Back Squat"


def test_unifica_nomi_esercizio_ricalcola_exercise_id(db_session):
    db_session.add(Exercise(nome_canonico="Back Squat", categoria="strength", traccia_1rm=True))
    db_session.flush()
    voce = _seed_log_entry(db_session, esercizio="Bb Back Squat")
    assert voce.exercise_id is None

    unifica_nomi_esercizio(db_session, "Bb Back Squat", "Back Squat")

    voce_aggiornata = db_session.query(LogEntry).filter_by(id=voce.id).first()
    esercizio_tracciato = db_session.query(Exercise).filter_by(nome_canonico="Back Squat").first()
    assert voce_aggiornata.exercise_id == esercizio_tracciato.id


def test_unifica_nomi_esercizio_blocca_se_si_scarta_un_sollevamento_tracciato(db_session):
    db_session.add(Exercise(nome_canonico="Back Squat", categoria="strength", traccia_1rm=True))
    db_session.flush()
    with pytest.raises(ValueError):
        unifica_nomi_esercizio(db_session, "Back Squat", "Bb Back Squat")


def test_unifica_nomi_esercizio_rifiuta_nomi_vuoti_o_uguali(db_session):
    with pytest.raises(ValueError):
        unifica_nomi_esercizio(db_session, "", "Back Squat")
    with pytest.raises(ValueError):
        unifica_nomi_esercizio(db_session, "Back Squat", "Back Squat")


def test_dopo_merge_il_nome_scartato_scompare_dai_nomi_esistenti(db_session):
    _seed_programma(db_session, esercizio_blocco="Bb Back Squat")
    unifica_nomi_esercizio(db_session, "Bb Back Squat", "Back Squat")

    nomi = get_nomi_esercizi_esistenti(db_session)
    assert "Bb Back Squat" not in nomi
    assert "Back Squat" in nomi


def test_parse_program_with_claude_segnala_troncamento_invece_di_json_grezzo():
    """Se Claude tronca la risposta per max_tokens, deve arrivare un errore
    leggibile prima del json.loads, non un JSONDecodeError criptico."""
    risposta_troncata = MagicMock()
    risposta_troncata.stop_reason = "max_tokens"

    with patch("core.llm_parser.anthropic.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = risposta_troncata
        with pytest.raises(ValueError, match="troppo lungo"):
            parse_program_with_claude("Week 1\nDay 1 - Test\n• Bb Back Squat 5-5-5")

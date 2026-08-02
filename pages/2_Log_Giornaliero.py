from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

from core.db import SessionLocal, init_db
from core.exercise_matching import resolve_exercise_id
from core.exercise_names import (
    applica_alias_esercizio,
    get_nomi_esercizi_esistenti,
    normalizza_nome_esercizio,
)
from core.models import Log, LogEntry, Program, ProgramBlock, ProgramDay
from core.theme import (
    FONT_DISPLAY,
    GREEN,
    PRIMARY_SECONDARY_RATIO,
    STEPPER_GROUP_GAP,
    STEPPER_INNER_GAP,
    SURFACE_HOVER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    chip_selector,
    icon_button,
    inject_global_css,
    pill_html,
    popover_panel,
    progress_bar,
    styled_button,
    subscreen_header,
    text_button,
    type_badge_html,
)
from core.log_entries import get_or_create_log, salva_wod
from core.wod_format import (
    AMRAP,
    EMOM,
    FOR_TIME,
    LIBERO,
    WOD_FORMATS,
    campi_visibili,
    deduce_emom_interval,
    deduce_wod_format,
    parse_splits,
    serialize_splits,
)

init_db()
inject_global_css()

TYPE_BADGE = {"strength": "STR", "complex": "CPX", "wod": "WOD", "accessorio": "ACC"}
FORMATO_CHIP_LABELS = {LIBERO: "Libero"}
DOW_LABELS = ["L", "M", "M", "G", "V", "S", "D"]  # weekday(): lunedì=0 ... domenica=6
MESI_ABBR = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

st.session_state.setdefault("log_screen", "main")
st.session_state.setdefault("log_menu_open", False)
st.session_state.setdefault("kg_step", 2.5)
st.session_state.setdefault("reps_step", 1)
st.session_state.setdefault("rpe_step", 0.5)


def parse_default_reps(schema_reps: Optional[str]) -> list:
    """Guess a per-set rep count from a dash-separated scheme like '8-8-8-8' or
    '1-1-1-1-1' (one entry per set). Complex-style segments like '(1+1+1)' default
    to 1 rep of the complex per set. Falls back to a single set of 1 rep."""
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


def valida_sets(edited_df: pd.DataFrame) -> tuple:
    """Return (errori_bloccanti, avvisi) for a strength/complex sets table."""
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


def save_sets(save_session, log_id: int, block_id, tipo: str, esercizio: str, edited_df: pd.DataFrame) -> int:
    esercizio = applica_alias_esercizio(save_session, esercizio.strip())
    if block_id is not None:
        save_session.query(LogEntry).filter_by(log_id=log_id, block_id=block_id).delete()
    exercise_id = resolve_exercise_id(save_session, esercizio)
    set_num = 0
    for _, row in edited_df.reset_index(drop=True).iterrows():
        carico, reps, rpe = row.get("carico_kg"), row.get("reps"), row.get("rpe")
        if pd.isna(carico) and pd.isna(reps) and pd.isna(rpe):
            continue
        set_num += 1
        save_session.add(
            LogEntry(
                log_id=log_id,
                block_id=block_id,
                tipo=tipo,
                esercizio=esercizio,
                exercise_id=exercise_id,
                set_index=set_num,
                carico_kg=float(carico) if pd.notna(carico) else None,
                reps=int(reps) if pd.notna(reps) else None,
                rpe=float(rpe) if pd.notna(rpe) else None,
            )
        )
    return set_num


def format_target_line(b: ProgramBlock) -> str:
    parti = []
    if b.tipo == "wod":
        if b.nome_wod:
            parti.append(b.nome_wod)
        if b.schema_reps:
            parti.append(b.schema_reps)
        if b.formato_wod:
            parti.append(b.formato_wod)
        if b.durata_wod_min:
            parti.append(f"{b.durata_wod_min:g} min")
    else:
        if b.schema_reps:
            parti.append(b.schema_reps)
        if b.target_carico_kg:
            parti.append(f"{b.target_carico_kg:g}kg")
        if b.target_percentuale:
            parti.append(f"{b.target_percentuale:g}% 1RM")
        if b.target_rpe:
            parti.append(f"RPE {b.target_rpe:g}")
    return " · ".join(parti) if parti else (b.note or "")


def _sets_state_key(block_id, data_sessione: date) -> str:
    return f"sets_{block_id}_{data_sessione.isoformat()}"


def get_sets_state(block_id, schema_reps: Optional[str], existing_entries: list, data_sessione: date) -> list:
    key = _sets_state_key(block_id, data_sessione)
    if key not in st.session_state:
        if existing_entries:
            ordinate = sorted(existing_entries, key=lambda e: e.set_index or 0)
            st.session_state[key] = [
                {"carico_kg": e.carico_kg, "reps": e.reps, "rpe": e.rpe, "confermato": True} for e in ordinate
            ]
        elif schema_reps:
            st.session_state[key] = [
                {"carico_kg": None, "reps": reps, "rpe": None, "confermato": False}
                for reps in parse_default_reps(schema_reps)
            ]
        else:
            st.session_state[key] = [{"carico_kg": None, "reps": None, "rpe": None, "confermato": False}]
    return st.session_state[key]


def simple_stepper(
    container: dict, field: str, key: str, step, min_value=None, max_value=None,
    fmt=None, label: str = "valore", is_int: bool = False,
) -> None:
    """Mutates container[field] in place and reruns immediately on change, so a
    tap shows its own effect right away instead of lagging one interaction
    behind (the display below is drawn from `value` captured before any click
    this run, so without an explicit rerun the user would only see the result
    of THIS click after a later, unrelated one).

    `label` (es. "reps", "RPE") alimenta il tooltip accessibile dei bottoni
    −/+ ("Diminuisci reps"/"Aumenta reps") tramite il parametro help di
    st.button, dato che Streamlit non espone un aria-label diretto.

    Tap sul valore centrale passa in modalità "digita il numero" (un
    st.number_input al posto del testo statico, con un bottone "OK" per
    confermare e tornare alla vista +/-), stesso pattern usato per il carico
    in kg_stepper() qui sotto - `editing_field` in session_state tiene traccia
    di quale stepper è in modifica in questo momento sull'intera pagina, per
    cui un solo campo alla volta può essere in editing. `is_int` sceglie se il
    valore digitato va trattato come intero (Reps, Round, Reps extra/totali,
    Tempo min/sec) o float (RPE, kg, minuti EMOM)."""
    value = container[field]
    fmt = fmt or (lambda v: str(v) if v is not None else "—")
    editing = st.session_state.get("editing_field") == key
    with st.container(key=f"stepper_inner_{key}"):
        if editing:
            c1, c2, c3, c4 = st.columns([1, 2, 1.6, 1], gap=STEPPER_INNER_GAP)
        else:
            c1, c2, c3 = st.columns([1, 1.6, 1], gap=STEPPER_INNER_GAP)
            c4 = None
        with c1:
            minus = styled_button("–", key=f"{key}_m", help=f"Diminuisci {label}")
        with c2:
            # minus/plus passano da styled_button(), che oltre a st.container(key=...)
            # inietta anche un piccolo st.markdown("<style>...") *prima* di aprire quel
            # container: è proprio quell'elemento markdown, come "sibling" nella stessa
            # colonna, a occupare lo spazio verticale extra che rende le colonne di
            # minus/plus più alte (56px) di una cella senza quell'elemento (40px) - da
            # cui gli 8px di offset quando la riga viene centrata con align-items:center.
            # Replichiamo qui la stessa identica struttura (markdown "gemello" + stesso
            # st.container(key=...) di styled_button) così che tutte e tre le celle
            # della riga abbiano esattamente la stessa altezza naturale.
            st.markdown("<style></style>", unsafe_allow_html=True)
            with st.container(key=f"{key}_val"):
                if editing:
                    # Clamp difensivo del valore iniziale del widget: se il dato
                    # esistente fosse fuori range (min_value/max_value), passarlo
                    # cosi' com'e' a st.number_input solleverebbe un'eccezione.
                    iniziale = value if value is not None else (min_value if min_value is not None else 0)
                    if min_value is not None:
                        iniziale = max(min_value, iniziale)
                    if max_value is not None:
                        iniziale = min(max_value, iniziale)
                    if is_int:
                        value = st.number_input(
                            label, value=int(iniziale), step=int(step),
                            min_value=int(min_value) if min_value is not None else None,
                            max_value=int(max_value) if max_value is not None else None,
                            key=f"{key}_input", label_visibility="collapsed",
                        )
                    else:
                        value = st.number_input(
                            label, value=float(iniziale), step=float(step),
                            min_value=float(min_value) if min_value is not None else None,
                            max_value=float(max_value) if max_value is not None else None,
                            key=f"{key}_input", label_visibility="collapsed",
                        )
                    # st.number_input passa min_value/max_value al widget ma non li
                    # impone rigidamente sul valore digitato (verificato: si può
                    # ancora digitare un numero fuori range) - clamp esplicito qui,
                    # stessa regola già applicata sotto per i click +/-.
                    if min_value is not None:
                        value = max(min_value, value)
                    if max_value is not None:
                        value = min(max_value, value)
                    container[field] = value
                else:
                    if st.button(fmt(value), key=f"{key}_lbl", use_container_width=True, help=f"Modifica manualmente {label}"):
                        st.session_state["editing_field"] = key
                        st.rerun()
        if editing:
            with c3:
                if styled_button("OK", key=f"{key}_ok", variant="green", help=f"Conferma {label}"):
                    st.session_state["editing_field"] = None
                    st.rerun()
            with c4:
                plus = styled_button("\\+", key=f"{key}_p", help=f"Aumenta {label}")
        else:
            with c3:
                plus = styled_button("\\+", key=f"{key}_p", help=f"Aumenta {label}")
    if not (minus or plus):
        return
    if minus:
        # Invariato: da non impostato parte da min_value (o 0) e sottrae uno
        # step, poi il clamp riporta comunque il risultato al minimo - quindi
        # "−" da "non impostato" atterra già correttamente sul minimo.
        base = value if value is not None else (min_value if min_value is not None else 0)
        base = base - step
        if min_value is not None:
            base = max(min_value, base)
    else:
        if value is None and min_value:
            # Da non impostato, "+" atterra esattamente sul minimo della scala
            # quando questo è un vero limite (es. RPE: 1.0, non 1.0+step=1.5)
            # invece di saltarlo con un doppio step. Per campi il cui minimo è
            # semplicemente lo zero "vuoto" (Reps, Round, ...) min_value è
            # falsy e si applica invece il comportamento invariato sotto.
            base = min_value
        else:
            base = (value if value is not None else (min_value if min_value is not None else 0)) + step
        if max_value is not None:
            base = min(max_value, base)
    container[field] = base
    st.rerun()


def kg_stepper(sets_list: list, idx: int, key: str, step: float) -> None:
    """Stepper del carico (kg) per le serie forza/complex: alias su
    simple_stepper con l'etichetta "Xkg" e il minimo 0 già impliciti
    nell'uso storico di questo campo."""
    simple_stepper(
        sets_list[idx], "carico_kg", key, step=step, min_value=0.0,
        fmt=lambda v: f"{v:g}kg" if v is not None else "—", label="carico",
    )


def _riga_set_confermato(num: int, s: dict) -> str:
    kg_lbl = f"{s['carico_kg']:g}kg" if s.get("carico_kg") is not None else "—"
    reps_lbl = str(int(s["reps"])) if s.get("reps") is not None else "—"
    rpe_lbl = f"{s['rpe']:g}" if s.get("rpe") is not None else "—"
    return (
        f'<div style="display:flex; align-items:center; gap:10px; background:{SURFACE_HOVER}; '
        f'border-radius:12px; padding:8px 10px; margin-bottom:6px;">'
        f'<div style="width:16px; color:{GREEN}; font-weight:700; font-size:12px;">✓</div>'
        f'<div style="width:18px; color:{TEXT_TERTIARY}; font-weight:700; font-size:12px;">{num}</div>'
        f'<div style="flex:1; font-family:{FONT_DISPLAY}; font-size:13px; color:{TEXT_PRIMARY}; text-align:right;">'
        f'{kg_lbl} × {reps_lbl} <span style="color:{TEXT_SECONDARY}; font-family:inherit;">@ RPE {rpe_lbl}</span></div>'
        f"</div>"
    )


def render_sets_card_body(blocco: ProgramBlock, prefix: str, existing_list: list, data_sessione: date, giorno_id, done: bool) -> None:
    sets = get_sets_state(blocco.id, blocco.schema_reps, existing_list, data_sessione)
    kg_step = st.session_state.get("kg_step", 2.5)
    reps_step = st.session_state.get("reps_step", 1)
    rpe_step = st.session_state.get("rpe_step", 0.5)

    primo_non_confermato = next((i for i, s in enumerate(sets) if not s.get("confermato")), None)
    tutti_confermati = primo_non_confermato is None
    confermati_visibili = sets if tutti_confermati else sets[:primo_non_confermato]

    for i, s in enumerate(confermati_visibili):
        st.markdown(_riga_set_confermato(i + 1, s), unsafe_allow_html=True)

    if not tutti_confermati:
        i = primo_non_confermato
        s = sets[i]
        row_key = f"{prefix}_set{i}"
        with st.container(key=f"stepper_row_{row_key}_header"):
            c_num, c_kg, c_reps, c_rpe = st.columns([0.5, 1.6, 1.6, 1.6], gap=STEPPER_GROUP_GAP)
            with c_kg:
                st.markdown('<div class="cft-mini-label">Carico</div>', unsafe_allow_html=True)
            with c_reps:
                st.markdown('<div class="cft-mini-label">Reps</div>', unsafe_allow_html=True)
            with c_rpe:
                st.markdown('<div class="cft-mini-label">RPE</div>', unsafe_allow_html=True)
        with st.container(key=f"stepper_row_{row_key}"):
            c_num, c_kg, c_reps, c_rpe = st.columns([0.5, 1.6, 1.6, 1.6], gap=STEPPER_GROUP_GAP)
            with c_num:
                st.markdown(f'<div class="cft-set-num">{i + 1}</div>', unsafe_allow_html=True)
            with c_kg:
                kg_stepper(sets, i, f"{row_key}_kg", kg_step)
            with c_reps:
                simple_stepper(
                    s, "reps", f"{row_key}_reps", step=reps_step, min_value=0,
                    fmt=lambda v: str(int(v)) if v is not None else "—", label="reps", is_int=True,
                )
            with c_rpe:
                simple_stepper(
                    s, "rpe", f"{row_key}_rpe", step=rpe_step, min_value=1.0, max_value=10.0,
                    fmt=lambda v: f"{v:g}" if v is not None else "—", label="RPE",
                )
        if styled_button(f"✓ Conferma set {i + 1}", key=f"{row_key}_confirm", variant="magenta"):
            if i + 1 < len(sets) and not sets[i + 1]["confermato"]:
                # Propaga carico/RPE (non reps, che resta quello da schema) al set
                # successivo generato in blocco da get_sets_state() - senza questo,
                # solo i set aggiunti a mano con "+ Aggiungi set" li ereditavano.
                if sets[i + 1]["carico_kg"] is None:
                    sets[i + 1]["carico_kg"] = sets[i]["carico_kg"]
                if sets[i + 1]["rpe"] is None:
                    sets[i + 1]["rpe"] = sets[i]["rpe"]
            sets[i]["confermato"] = True
            st.rerun()

    if tutti_confermati:
        col_add, col_done = st.columns(PRIMARY_SECONDARY_RATIO)
        with col_add:
            if styled_button("+ Aggiungi set", key=f"{prefix}_add"):
                if sets:
                    ultimo_set = sets[-1]
                    sets.append({"carico_kg": ultimo_set["carico_kg"], "reps": ultimo_set["reps"], "rpe": ultimo_set["rpe"], "confermato": False})
                else:
                    sets.append({"carico_kg": None, "reps": None, "rpe": None, "confermato": False})
        with col_done:
            label = "💾 Salva modifiche" if done else "✓ Segna come fatto"
            if styled_button(label, key=f"{prefix}_done", variant="green"):
                df = pd.DataFrame(sets, columns=["carico_kg", "reps", "rpe"])
                errori, avvisi = valida_sets(df)
                if errori:
                    for e in errori:
                        st.error(e)
                    st.error("Correggi gli errori evidenziati prima di salvare.")
                else:
                    with SessionLocal() as save_session:
                        log = get_or_create_log(save_session, data_sessione, giorno_id)
                        n = save_sets(save_session, log.id, blocco.id, blocco.tipo, blocco.esercizio, df)
                        save_session.commit()
                    _carica_entries_per_blocco.clear()
                    for a in avvisi:
                        st.warning(f"{a} Il set non sarà incluso nei grafici di trend/progressi.")
                    st.toast(f"Salvato: {blocco.esercizio}", icon="✅")
                    st.session_state.pop(_sets_state_key(blocco.id, data_sessione), None)
                    st.rerun()


def render_wod_card_body(blocco: Optional[ProgramBlock], prefix: str, existing_list: list, data_sessione: date, giorno_id, done: bool, tipo: str, esercizio: str) -> None:
    existing = existing_list[0] if existing_list else None
    if existing and existing.formato_wod in WOD_FORMATS:
        formato_default = existing.formato_wod
    elif blocco is not None:
        formato_default = deduce_wod_format(blocco.formato_wod, blocco.esercizio, blocco.note)
    else:
        formato_default = LIBERO

    formato_options = [(f, FORMATO_CHIP_LABELS.get(f, f)) for f in WOD_FORMATS]
    formato = chip_selector(formato_options, session_key=f"{prefix}_formato_sel", default=formato_default, per_row=3)
    campi = campi_visibili(formato)

    kg_step = st.session_state.get("kg_step", 2.5)
    state_key = f"{prefix}_wodstate"
    if state_key not in st.session_state:
        st.session_state[state_key] = {
            "tempo_min": (existing.risultato_tempo_sec // 60) if existing and existing.risultato_tempo_sec else 0,
            "tempo_sec": (existing.risultato_tempo_sec % 60) if existing and existing.risultato_tempo_sec else 0,
            "round": existing.risultato_round if existing and existing.risultato_round else 0,
            "reps_extra": existing.risultato_reps_extra if existing and existing.risultato_reps_extra else 0,
            "reps_totali": existing.risultato_reps_totali if existing and existing.risultato_reps_totali else 0,
            "emom_minuti": (
                float(existing.emom_minuti_per_round) if existing and existing.emom_minuti_per_round
                else (deduce_emom_interval(blocco.formato_wod, blocco.esercizio, blocco.note) if blocco else None) or 1.0
            ),
            "carico_totale": existing.carico_totale_kg if existing and existing.carico_totale_kg else 0.0,
        }
    wstate = st.session_state[state_key]

    campi_da_mostrare = [
        c for c in ("tempo", "round", "reps_extra", "reps_totali", "emom_minuti", "carico_totale") if c in campi
    ]
    if campi_da_mostrare:
        with st.container(key=f"stepper_row_{prefix}_wod"):
            cols = st.columns(len(campi_da_mostrare), gap=STEPPER_GROUP_GAP)
            for col, campo in zip(cols, campi_da_mostrare):
                with col:
                    if campo == "tempo":
                        st.markdown('<div class="cft-mini-label">Tempo (min : sec)</div>', unsafe_allow_html=True)
                        cm, cs = st.columns(2, gap=STEPPER_INNER_GAP)
                        with cm:
                            simple_stepper(
                                wstate, "tempo_min", f"{prefix}_min", step=1, min_value=0,
                                fmt=lambda v: f"{int(v):02d}", label="minuti", is_int=True,
                            )
                        with cs:
                            simple_stepper(
                                wstate, "tempo_sec", f"{prefix}_sec", step=1, min_value=0, max_value=59,
                                fmt=lambda v: f"{int(v):02d}", label="secondi", is_int=True,
                            )
                    elif campo == "round":
                        etichetta = "Round / intervallo" if formato == "EMOM" else "Round completati"
                        st.markdown(f'<div class="cft-mini-label">{etichetta}</div>', unsafe_allow_html=True)
                        simple_stepper(
                            wstate, "round", f"{prefix}_round", step=1, min_value=0, fmt=lambda v: str(int(v)),
                            label="round", is_int=True,
                        )
                    elif campo == "reps_extra":
                        st.markdown('<div class="cft-mini-label">Reps extra</div>', unsafe_allow_html=True)
                        simple_stepper(
                            wstate, "reps_extra", f"{prefix}_repsextra", step=1, min_value=0, fmt=lambda v: str(int(v)),
                            label="reps extra", is_int=True,
                        )
                    elif campo == "reps_totali":
                        st.markdown('<div class="cft-mini-label">Reps totali</div>', unsafe_allow_html=True)
                        simple_stepper(
                            wstate, "reps_totali", f"{prefix}_repstot", step=1, min_value=0, fmt=lambda v: str(int(v)),
                            label="reps totali", is_int=True,
                        )
                    elif campo == "emom_minuti":
                        st.markdown('<div class="cft-mini-label">Min / round</div>', unsafe_allow_html=True)
                        simple_stepper(
                            wstate, "emom_minuti", f"{prefix}_emom", step=0.5, min_value=0.5, fmt=lambda v: f"{v:g}",
                            label="minuti per round",
                        )
                    elif campo == "carico_totale":
                        st.markdown('<div class="cft-mini-label">Carico tot. (kg)</div>', unsafe_allow_html=True)
                        simple_stepper(
                            wstate, "carico_totale", f"{prefix}_caricotot", step=kg_step, min_value=0.0, fmt=lambda v: f"{v:g}",
                            label="carico totale",
                        )

    splits_json = existing.splits_json if existing else None
    if formato == FOR_TIME:
        splits_key = f"{prefix}_splits_state"
        if splits_key not in st.session_state:
            esistenti = parse_splits(splits_json)
            st.session_state[splits_key] = [
                {"label": s["label"], "time_sec": s["time_sec"]} for s in esistenti
            ] or [{"label": "", "time_sec": 0}]
        splits = st.session_state[splits_key]

        st.markdown('<div class="cft-mini-label" style="margin-top:10px;">Split / parziali per esercizio</div>', unsafe_allow_html=True)
        for i, sp in enumerate(splits):
            row_key = f"{prefix}_split{i}"
            with st.container(key=f"stepper_row_{row_key}"):
                c_label, c_stepper = st.columns([2, 2], gap=STEPPER_GROUP_GAP)
                with c_label:
                    sp["label"] = st.text_input(
                        "Split", value=sp["label"], key=f"{row_key}_label",
                        label_visibility="collapsed", placeholder="es. Thrusters 21",
                    )
                with c_stepper:
                    simple_stepper(
                        sp, "time_sec", f"{row_key}_time", step=5, min_value=0,
                        fmt=lambda v: f"{int(v) // 60}:{int(v) % 60:02d}", label="tempo parziale", is_int=True,
                    )
        if styled_button("+ Aggiungi parziale", key=f"{prefix}_addsplit"):
            splits.append({"label": "", "time_sec": 0})
        splits_json = serialize_splits(splits)

    note = st.text_area("Note", key=f"{prefix}_note", value=(existing.note if existing and existing.note else ""))

    label = "💾 Salva modifiche" if done else "✓ Segna come fatto"
    if styled_button(label, key=f"{prefix}_done", variant="green"):
        values = {
            "formato_wod": formato,
            "risultato_tempo_sec": (
                (int(wstate["tempo_min"]) * 60 + int(wstate["tempo_sec"]))
                if "tempo" in campi and (wstate["tempo_min"] or wstate["tempo_sec"]) else None
            ),
            "risultato_round": int(wstate["round"]) if "round" in campi and wstate["round"] else None,
            "risultato_reps_extra": int(wstate["reps_extra"]) if "reps_extra" in campi and wstate["reps_extra"] else None,
            "risultato_reps_totali": int(wstate["reps_totali"]) if "reps_totali" in campi and wstate["reps_totali"] else None,
            "emom_minuti_per_round": float(wstate["emom_minuti"]) if "emom_minuti" in campi and wstate["emom_minuti"] else None,
            "carico_totale_kg": float(wstate["carico_totale"]) if "carico_totale" in campi and wstate["carico_totale"] else None,
            "splits_json": splits_json if formato == FOR_TIME else None,
            "note": note or None,
        }
        if not esercizio.strip():
            st.error("Inserisci il nome dell'esercizio o del WOD.")
        else:
            with SessionLocal() as save_session:
                log = get_or_create_log(save_session, data_sessione, giorno_id)
                block_id = blocco.id if blocco is not None else None
                salva_wod(save_session, log.id, block_id, tipo, esercizio, values)
                save_session.commit()
            _carica_entries_per_blocco.clear()
            st.toast(f"Salvato: {esercizio}", icon="✅")
            st.session_state.pop(state_key, None)
            st.session_state.pop(f"{prefix}_splits_state", None)
            st.rerun()


def render_block_card(blocco: ProgramBlock, data_sessione: date, giorno_id, existing_list: list) -> None:
    done = bool(existing_list)
    card_key = f"card_{blocco.id}"
    border_tint = "oklch(45% 0.1 152 / 0.35)" if done else "oklch(45% 0.12 345 / 0.35)"
    st.markdown(
        f"""<style>.st-key-{card_key} {{
            background: oklch(19% 0.015 265) !important;
            border-radius: 16px !important;
            border: 1px solid {border_tint} !important;
        }}</style>""",
        unsafe_allow_html=True,
    )

    with st.container(key=card_key, border=True):
        col_badge, col_main, col_status = st.columns([1, 5, 2])
        with col_badge:
            st.markdown(type_badge_html(TYPE_BADGE.get(blocco.tipo, blocco.tipo.upper()[:3])), unsafe_allow_html=True)
        with col_main:
            st.markdown(
                f'<div style="font-weight:600; font-size:15px;">{blocco.esercizio}</div>'
                f'<div style="color:{TEXT_SECONDARY}; font-size:12.5px; margin-top:1px;">{format_target_line(blocco)}</div>',
                unsafe_allow_html=True,
            )
        with col_status:
            st.markdown(pill_html("✓ Fatto" if done else "● Da fare", done), unsafe_allow_html=True)

        if text_button("🔍 Confronta storico", key=f"cerca_storico_{blocco.id}", use_container_width=False):
            st.session_state["storico_search_query"] = blocco.esercizio
            st.switch_page("pages/3_Storico_Progressi.py")

        show_body = st.session_state.get("log_active_block") == blocco.id
        if st.button("Chiudi ▴" if show_body else "Dettagli ▾", key=f"toggle_{blocco.id}", use_container_width=True):
            st.session_state["log_active_block"] = None if show_body else blocco.id
            st.rerun()

        if show_body:
            prefix = f"block_{blocco.id}_{data_sessione.isoformat()}"
            if blocco.tipo in ("strength", "complex"):
                render_sets_card_body(blocco, prefix, existing_list, data_sessione, giorno_id, done)
            else:
                render_wod_card_body(blocco, prefix, existing_list, data_sessione, giorno_id, done, blocco.tipo, blocco.esercizio)


def render_sets_card_body_libero(prefix: str, data_sessione: date, giorno_id, tipo: str, esercizio: str) -> None:
    key = f"sets_libero_{data_sessione.isoformat()}"
    if key not in st.session_state:
        st.session_state[key] = [{"carico_kg": None, "reps": None, "rpe": None, "confermato": False}]
    sets = st.session_state[key]
    kg_step = st.session_state.get("kg_step", 2.5)
    reps_step = st.session_state.get("reps_step", 1)
    rpe_step = st.session_state.get("rpe_step", 0.5)

    primo_non_confermato = next((i for i, s in enumerate(sets) if not s.get("confermato")), None)
    tutti_confermati = primo_non_confermato is None
    confermati_visibili = sets if tutti_confermati else sets[:primo_non_confermato]

    for i, s in enumerate(confermati_visibili):
        st.markdown(_riga_set_confermato(i + 1, s), unsafe_allow_html=True)

    if not tutti_confermati:
        i = primo_non_confermato
        s = sets[i]
        row_key = f"{prefix}_set{i}"
        with st.container(key=f"stepper_row_{row_key}_header"):
            c_num, c_kg, c_reps, c_rpe = st.columns([0.5, 1.6, 1.6, 1.6], gap=STEPPER_GROUP_GAP)
            with c_kg:
                st.markdown('<div class="cft-mini-label">Carico</div>', unsafe_allow_html=True)
            with c_reps:
                st.markdown('<div class="cft-mini-label">Reps</div>', unsafe_allow_html=True)
            with c_rpe:
                st.markdown('<div class="cft-mini-label">RPE</div>', unsafe_allow_html=True)
        with st.container(key=f"stepper_row_{row_key}"):
            c_num, c_kg, c_reps, c_rpe = st.columns([0.5, 1.6, 1.6, 1.6], gap=STEPPER_GROUP_GAP)
            with c_num:
                st.markdown(f'<div class="cft-set-num">{i + 1}</div>', unsafe_allow_html=True)
            with c_kg:
                kg_stepper(sets, i, f"{row_key}_kg", kg_step)
            with c_reps:
                simple_stepper(
                    s, "reps", f"{row_key}_reps", step=reps_step, min_value=0,
                    fmt=lambda v: str(int(v)) if v is not None else "—", label="reps", is_int=True,
                )
            with c_rpe:
                simple_stepper(
                    s, "rpe", f"{row_key}_rpe", step=rpe_step, min_value=1.0, max_value=10.0,
                    fmt=lambda v: f"{v:g}" if v is not None else "—", label="RPE",
                )
        if styled_button(f"✓ Conferma set {i + 1}", key=f"{row_key}_confirm", variant="magenta"):
            if i + 1 < len(sets) and not sets[i + 1]["confermato"]:
                if sets[i + 1]["carico_kg"] is None:
                    sets[i + 1]["carico_kg"] = sets[i]["carico_kg"]
                if sets[i + 1]["rpe"] is None:
                    sets[i + 1]["rpe"] = sets[i]["rpe"]
            sets[i]["confermato"] = True
            st.rerun()

    if tutti_confermati:
        col_add, col_done = st.columns(PRIMARY_SECONDARY_RATIO)
        with col_add:
            if styled_button("+ Aggiungi set", key=f"{prefix}_add"):
                if sets:
                    ultimo_set = sets[-1]
                    sets.append({"carico_kg": ultimo_set["carico_kg"], "reps": ultimo_set["reps"], "rpe": ultimo_set["rpe"], "confermato": False})
                else:
                    sets.append({"carico_kg": None, "reps": None, "rpe": None, "confermato": False})
        with col_done:
            if styled_button("✓ Aggiungi voce", key=f"{prefix}_done", variant="green"):
                df = pd.DataFrame(sets, columns=["carico_kg", "reps", "rpe"])
                errori, avvisi = valida_sets(df)
                if errori:
                    for e in errori:
                        st.error(e)
                    st.error("Correggi gli errori evidenziati prima di salvare.")
                else:
                    with SessionLocal() as save_session:
                        log = get_or_create_log(save_session, data_sessione, giorno_id)
                        n = save_sets(save_session, log.id, None, tipo, esercizio, df)
                        save_session.commit()
                    _carica_entries_per_blocco.clear()
                    for a in avvisi:
                        st.warning(f"{a} Il set non sarà incluso nei grafici di trend/progressi.")
                    st.toast(f"Aggiunto: {esercizio}", icon="✅")
                    st.session_state.pop(key, None)
                    st.session_state["log_active_block"] = None
                    st.rerun()


def render_free_entry_card(data_sessione: date, giorno_id) -> None:
    card_key = "card_libero"
    st.markdown(
        f"""<style>.st-key-{card_key} {{
            background: oklch(19% 0.015 265) !important;
            border-radius: 16px !important;
            border: 1px dashed oklch(40% 0.02 265) !important;
        }}</style>""",
        unsafe_allow_html=True,
    )
    with st.container(key=card_key, border=True):
        col_badge, col_main = st.columns([1, 8])
        with col_badge:
            st.markdown(type_badge_html("LIBERO"), unsafe_allow_html=True)
        with col_main:
            st.markdown('<div style="font-weight:600; font-size:15px;">Aggiungi voce senza piano</div>', unsafe_allow_html=True)

        show_body = st.session_state.get("log_active_block") == "libero"
        if st.button("Chiudi ▴" if show_body else "Dettagli ▾", key="toggle_libero", use_container_width=True):
            st.session_state["log_active_block"] = None if show_body else "libero"
            st.rerun()

        if show_body:
            st.caption("Per allenamenti liberi, o esercizi extra non presenti nel programma di questo giorno.")

            tipo_libero = st.selectbox("Tipo", ["strength", "complex", "wod", "accessorio"], key="libero_tipo")

            with SessionLocal() as _session:
                nomi_esercizi_esistenti = get_nomi_esercizi_esistenti(_session)

            NUOVO_ESERCIZIO = "➕ Nuovo esercizio..."
            scelta_esercizio = st.selectbox(
                "Esercizio / WOD",
                [NUOVO_ESERCIZIO] + nomi_esercizi_esistenti,
                key="libero_esercizio_scelta",
                help="Digita per cercare tra gli esercizi già usati, oppure scegli 'Nuovo esercizio...' per aggiungerne uno.",
            )
            if scelta_esercizio == NUOVO_ESERCIZIO:
                esercizio_libero_raw = st.text_input("Nome nuovo esercizio", key="libero_esercizio_nuovo")
                esercizio_libero = normalizza_nome_esercizio(esercizio_libero_raw) if esercizio_libero_raw.strip() else ""
                if esercizio_libero_raw.strip() and esercizio_libero != esercizio_libero_raw.strip():
                    st.caption(f"Verrà salvato come: **{esercizio_libero}**")
            else:
                esercizio_libero = scelta_esercizio

            prefix = f"libero_{data_sessione.isoformat()}"
            if tipo_libero in ("strength", "complex"):
                if not esercizio_libero.strip():
                    st.info("Inserisci il nome dell'esercizio per iniziare a compilare i set.")
                else:
                    render_sets_card_body_libero(prefix, data_sessione, giorno_id, tipo_libero, esercizio_libero)
            else:
                render_wod_card_body(None, prefix, [], data_sessione, giorno_id, False, tipo_libero, esercizio_libero)


def _programma_attivo_id(programmi: list) -> Optional[int]:
    """Risolve il programma corrente da session_state senza ridisegnare il
    selectbox - usato dalla sotto-schermata 'Tutti gli allenamenti', che non
    mostra i controlli piano/programma (vedi Interactions & Behavior nel
    README: le sotto-schermate sostituiscono il contenuto principale)."""
    if not programmi:
        return None
    nome_scelto = st.session_state.get("log_programma_select")
    for p in programmi:
        if p.nome_mese == nome_scelto:
            return p.id
    return programmi[0].id


def _vai_al_giorno(giorno_target: ProgramDay) -> None:
    st.session_state["log_giorno_id"] = giorno_target.id
    st.session_state["log_settimana_select"] = giorno_target.settimana
    st.session_state["log_giorno_select"] = giorno_target.giorno_label


@st.cache_data(ttl=300, show_spinner=False)
def _carica_programmi() -> list:
    """Programmi importati: cambiano solo quando si importa un nuovo piano in
    Import Programma, non ad ogni interazione qui. Senza cache, ogni tap su
    uno stepper (che chiama st.rerun() per il feedback immediato) rifarebbe
    questa query contro Postgres/Supabase da capo."""
    with SessionLocal() as _session:
        return _session.query(Program).order_by(Program.data_import.desc()).all()


@st.cache_data(ttl=300, show_spinner=False)
def _carica_giorni_programma(program_id: int) -> list:
    with SessionLocal() as _session:
        return (
            _session.query(ProgramDay)
            .filter_by(program_id=program_id)
            .order_by(ProgramDay.settimana, ProgramDay.id)
            .all()
        )


@st.cache_data(ttl=300, show_spinner=False)
def _carica_blocchi(giorno_id: int) -> list:
    with SessionLocal() as _session:
        return (
            _session.query(ProgramBlock)
            .filter_by(day_id=giorno_id)
            .order_by(ProgramBlock.ordine)
            .all()
        )


@st.cache_data(ttl=300, show_spinner=False)
def _carica_entries_per_blocco(giorno_id: int, data: date) -> dict:
    """A differenza di programmi/giorni/blocchi, cambia ad ogni salvataggio di
    un set o un WOD - non e' "statica" come quelle, quindi va invalidata
    esplicitamente con _carica_entries_per_blocco.clear() subito dopo ogni
    save_session.commit() (vedi i tre punti di salvataggio più sotto), non
    lasciata scadere solo con il ttl."""
    with SessionLocal() as _session:
        entries: dict = {}
        for e in (
            _session.query(LogEntry)
            .join(Log)
            .filter(Log.data == data, Log.day_id == giorno_id)
            .all()
        ):
            entries.setdefault(e.block_id, []).append(e)
        return entries


programmi = _carica_programmi()

screen = st.session_state["log_screen"]

if screen == "settings":
    if subscreen_header("Impostazioni stepper", back_key="log_back_settings"):
        st.session_state["log_screen"] = "main"
        st.rerun()

    def _step_chips(label: str, session_key: str, options: list) -> None:
        st.markdown(f'<div class="cft-mini-label" style="margin-top:16px;">{label}</div>', unsafe_allow_html=True)
        valori_str = [f"{v:g}" for v in options]
        default_corrente = f"{st.session_state.get(session_key, options[len(options) // 2]):g}"
        scelto = chip_selector(list(zip(valori_str, valori_str)), session_key=f"{session_key}_chip", default=default_corrente, per_row=4)
        st.session_state[session_key] = float(scelto)

    _step_chips("Step carico (kg)", "kg_step", [0.5, 1, 2.5, 5])
    _step_chips("Step reps", "reps_step", [1, 2, 5])
    _step_chips("Step RPE", "rpe_step", [0.25, 0.5, 1])

elif screen == "all":
    if subscreen_header("Tutti gli allenamenti", back_key="log_back_all"):
        st.session_state["log_screen"] = "main"
        st.rerun()

    programma_id = _programma_attivo_id(programmi)
    if programma_id is None:
        st.info("Nessun programma disponibile.")
    else:
        giorni_programma = _carica_giorni_programma(programma_id)
        giorno_corrente_id = st.session_state.get("log_giorno_id")
        for g in giorni_programma:
            etichetta_riga = f"Settimana {g.settimana} · {g.giorno_label}"
            if g.focus:
                etichetta_riga += f" — {g.focus}"
            if g.id == giorno_corrente_id:
                st.markdown(f"➡️ **{etichetta_riga}**")
            elif styled_button(etichetta_riga, key=f"jump_{g.id}", use_container_width=True, wrap=True):
                _vai_al_giorno(g)
                st.session_state["log_screen"] = "main"
                st.rerun()

else:
    # --- Navigatore compatto Programma/Settimana/Giorno/Data (vedi
    # design_handoff_log_navigator/README.md, opzione 1b) al posto del vecchio
    # toggle sempre visibile + le due select + la riga di 7 pillole data.

    # Fase 1: calcola lo stato corrente (programma/settimana/giorno) leggendo/
    # normalizzando session_state, SENZA disegnare ancora nessun controllo -
    # serve a Riga 1 per mostrare subito il sottotitolo con focus corretto.
    if not programmi:
        usa_piano = False
        programma_id = None
    elif len(programmi) == 1:
        usa_piano = True
        programma_id = programmi[0].id
    else:
        st.session_state.setdefault("log_usa_piano_toggle", True)
        usa_piano = st.session_state["log_usa_piano_toggle"]
        nomi_programmi = [p.nome_mese for p in programmi]
        if st.session_state.get("log_programma_select") not in nomi_programmi:
            st.session_state["log_programma_select"] = nomi_programmi[0]
        programma_id = next(p.id for p in programmi if p.nome_mese == st.session_state["log_programma_select"])

    giorno_selezionato_id = None
    blocchi_ids = []
    settimana_corrente = giorno_label_corrente = focus_corrente = None
    giorni_programma: list = []
    settimana_scelta = None
    labels: list = []
    label_scelta = None

    if usa_piano and programma_id is not None:
        giorni_programma = _carica_giorni_programma(programma_id)
        if not giorni_programma:
            st.warning("Questo programma non ha giorni importati.")
        else:
            settimane = sorted({g.settimana for g in giorni_programma})
            settimane_str = [str(s) for s in settimane]
            # log_settimana_select puo' arrivare qui anche come int puro (lo
            # scrive cosi' _vai_al_giorno() dalla sotto-schermata "Tutti gli
            # allenamenti"): normalizzo sempre a stringa, che e' il tipo con
            # cui lavora chip_selector piu' sotto.
            if str(st.session_state.get("log_settimana_select")) not in settimane_str:
                st.session_state["log_settimana_select"] = settimane_str[0]
            else:
                st.session_state["log_settimana_select"] = str(st.session_state["log_settimana_select"])
            settimana_scelta = int(st.session_state["log_settimana_select"])

            giorni_settimana = [g for g in giorni_programma if g.settimana == settimana_scelta]
            labels = [g.giorno_label for g in giorni_settimana]
            if st.session_state.get("log_giorno_select") not in labels:
                st.session_state["log_giorno_select"] = labels[0]
            label_scelta = st.session_state["log_giorno_select"]

            giorno = next(g for g in giorni_settimana if g.giorno_label == label_scelta)
            st.session_state["log_giorno_id"] = giorno.id
            giorno_selezionato_id = giorno.id
            settimana_corrente = giorno.settimana
            giorno_label_corrente = giorno.giorno_label
            focus_corrente = giorno.focus

            blocchi_ids = [b.id for b in _carica_blocchi(giorno_selezionato_id)]

    # Riga 1 — titolo + sottotitolo programma (cliccabile solo con >1 programma;
    # con un solo programma è già la scelta implicita, niente popover).
    col_title, col_menu = st.columns([5, 1])
    with col_title:
        st.markdown("## Log")
        if programmi:
            nome_prog_corrente = next((p.nome_mese for p in programmi if p.id == programma_id), programmi[0].nome_mese)
            focus_suffix = f" · {focus_corrente}" if focus_corrente else ""
            if len(programmi) > 1:
                if text_button(f"**{nome_prog_corrente}**{focus_suffix}  ⌄", key="log_program_subtitle", wrap=True):
                    st.session_state["log_program_popover_open"] = not st.session_state.get("log_program_popover_open", False)
                    st.rerun()
            else:
                st.markdown(
                    f'<div style="font-size:13px; margin-top:4px;">'
                    f'<span style="color:{TEXT_PRIMARY}; font-weight:700;">{nome_prog_corrente}</span>'
                    f'<span style="color:{TEXT_SECONDARY};">{focus_suffix}</span></div>',
                    unsafe_allow_html=True,
                )
    with col_menu:
        if icon_button("⋯", key="log_menu_icon", active=st.session_state.get("log_menu_open", False), help="Altre opzioni"):
            st.session_state["log_menu_open"] = not st.session_state.get("log_menu_open", False)
            st.rerun()

    if st.session_state.get("log_menu_open"):
        with popover_panel("log_menu_panel"):
            if giorno_selezionato_id and st.button("📋 Tutti gli allenamenti", key="menu_all", use_container_width=True):
                st.session_state["log_screen"] = "all"
                st.session_state["log_menu_open"] = False
                st.rerun()
            if st.button("⚙️ Impostazioni stepper", key="menu_settings", use_container_width=True):
                st.session_state["log_screen"] = "settings"
                st.session_state["log_menu_open"] = False
                st.rerun()

    if len(programmi) > 1 and st.session_state.get("log_program_popover_open"):
        with popover_panel("log_program_popover"):
            # Il toggle "piano/libero" si sposta qui (assieme alla scelta
            # programma) invece di stare sempre visibile in cima.
            # value=usa_piano esplicito: il widget e' montato solo quando il
            # popover e' aperto (condizionale), e al primissimo mount NON
            # rifletteva session_state pre-impostato da setdefault() sopra -
            # restava graficamente su "off" anche a usa_piano=True finche' non
            # veniva toccato una volta (bug di visualizzazione, verificato).
            st.toggle("Collega a un allenamento pianificato", value=usa_piano, key="log_usa_piano_toggle")
            nomi_programmi = [p.nome_mese for p in programmi]
            corrente = st.session_state.get("log_programma_select", nomi_programmi[0])
            opzioni_prog = [(n, f"{n}  ✓" if n == corrente else n) for n in nomi_programmi]
            chip_selector(opzioni_prog, session_key="log_programma_select", per_row=1)

    # Riga 2 — card Settimana/Giorno: cliccabile, apre un popover con due righe
    # di chip al posto delle vecchie due st.selectbox.
    if usa_piano and giorni_programma:
        titolo_card = f"Sett. {settimana_corrente} · {giorno_label_corrente}"
        sottotitolo_card = f"{focus_corrente} — tocca per cambiare" if focus_corrente else "Tocca per cambiare"
        if styled_button(f"**{titolo_card}**  \n{sottotitolo_card}  ⌄", key="log_daynav_card", variant="neutral", wrap=True):
            st.session_state["log_daynav_popover_open"] = not st.session_state.get("log_daynav_popover_open", False)
            st.rerun()

        if st.session_state.get("log_daynav_popover_open"):
            with popover_panel("log_daynav_popover"):
                st.markdown('<div class="cft-mini-label" style="text-align:left; margin-bottom:2px;">Settimana</div>', unsafe_allow_html=True)
                chip_selector(
                    [(s, s) for s in settimane_str], session_key="log_settimana_select",
                    default=str(settimana_scelta), per_row=min(len(settimane_str), 6) or 1,
                )

                st.markdown(
                    '<div class="cft-mini-label" style="text-align:left; margin-bottom:2px; margin-top:10px;">Allenamento</div>',
                    unsafe_allow_html=True,
                )
                # Riga giorno costruita a mano (non chip_selector) solo perché
                # qui, a differenza della settimana, la scelta deve anche
                # chiudere il popover subito - chip_selector fa già il suo
                # st.rerun() interno appena cliccato, quindi non c'è modo di
                # aggiungere quella chiusura *dopo* averlo chiamato.
                cols_giorno = st.columns(min(len(labels), 4) or 1)
                for i, lab in enumerate(labels):
                    with cols_giorno[i % len(cols_giorno)]:
                        variant = "magenta" if lab == label_scelta else "neutral"
                        if styled_button(lab, key=f"log_daynav_giorno_{i}", variant=variant):
                            st.session_state["log_giorno_select"] = lab
                            st.session_state["log_daynav_popover_open"] = False
                            st.rerun()

    # Riga 3 — data di log: sposta data_sessione ± 1 giorno, indipendente dal
    # giorno di piano scelto in Riga 2 (per questo è una riga separata).
    st.session_state.setdefault("log_data_sessione", date.today())
    data_sessione = st.session_state["log_data_sessione"]

    col_data_label, col_data_stepper, col_cal = st.columns([1.3, 4.4, 0.9])
    with col_data_label:
        st.markdown(f'<div style="color:{TEXT_TERTIARY}; font-size:11px; padding-top:9px;">Data log</div>', unsafe_allow_html=True)
    with col_data_stepper:
        with st.container(key="stepper_inner_log_data"):
            c_data_prev, c_data_lbl, c_data_next = st.columns([1, 3.4, 1], gap=STEPPER_INNER_GAP)
            with c_data_prev:
                data_prev = icon_button("‹", key="log_data_prev", help="Giorno precedente")
            with c_data_lbl:
                etichetta_data = f"{DOW_LABELS[data_sessione.weekday()]} {data_sessione.day} {MESI_ABBR[data_sessione.month - 1]}"
                if data_sessione == date.today():
                    etichetta_data += " · oggi"
                st.markdown(f'<div class="cft-value-label">{etichetta_data}</div>', unsafe_allow_html=True)
            with c_data_next:
                data_next = icon_button("›", key="log_data_next", help="Giorno successivo")
        if data_prev:
            st.session_state["log_data_sessione"] = data_sessione - timedelta(days=1)
            st.rerun()
        if data_next:
            st.session_state["log_data_sessione"] = data_sessione + timedelta(days=1)
            st.rerun()
    with col_cal:
        if icon_button("📅", key="log_cal_icon", active=st.session_state.get("log_cal_open", False), help="Scegli un'altra data"):
            st.session_state["log_cal_open"] = not st.session_state.get("log_cal_open", False)
            st.rerun()

    if st.session_state.get("log_cal_open"):
        nuova_data = st.date_input("Data", value=data_sessione, key="log_date_input_hidden")
        if nuova_data != data_sessione:
            st.session_state["log_data_sessione"] = nuova_data
            data_sessione = nuova_data

    if usa_piano and giorno_selezionato_id and blocchi_ids:
        blocchi = _carica_blocchi(giorno_selezionato_id)
        entries_per_blocco = _carica_entries_per_blocco(giorno_selezionato_id, data_sessione)

        blocchi_fatti = sum(1 for b in blocchi if entries_per_blocco.get(b.id))
        progress_bar(blocchi_fatti, len(blocchi), f"{blocchi_fatti}/{len(blocchi)} blocchi")

        ids_del_giorno = {b.id for b in blocchi}
        attivo = st.session_state.get("log_active_block")
        if attivo not in ids_del_giorno and attivo != "libero":
            primo_da_fare = next((b.id for b in blocchi if not entries_per_blocco.get(b.id)), None)
            st.session_state["log_active_block"] = primo_da_fare

        for blocco in blocchi:
            render_block_card(blocco, data_sessione, giorno_selezionato_id, entries_per_blocco.get(blocco.id, []))
        render_free_entry_card(data_sessione, giorno_selezionato_id)
    else:
        render_free_entry_card(data_sessione, giorno_selezionato_id)

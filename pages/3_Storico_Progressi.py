import calendar as pycalendar
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.calculations import (
    calcola_aderenza,
    calcola_streak,
    conta_pr_nel_mese,
    distribuzione_rpe,
    estimate_1rm,
    metriche_periodo,
)
from core.chart_utils import guarda_asse_singolo_punto
from core.db import SessionLocal, init_db
from core.exercise_names import cerca_nomi_simili, get_nomi_esercizi_esistenti
from core.models import Exercise, Log, LogEntry, Program, ProgramBlock, ProgramDay
from core.theme import (
    AMBER_HEX,
    BLUE_HEX,
    BORDER,
    FONT_DISPLAY,
    GREEN,
    GREEN_HEX,
    MAGENTA,
    MAGENTA_HEX,
    TEXT_PRIMARY,
    TEXT_PRIMARY_HEX,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    bar_row_html,
    calendar_day_button,
    chip_selector,
    icon_button,
    inject_global_css,
    pill_html,
    popover_panel,
    stat_grid,
    styled_button,
    type_badge_html,
)
from core.wod_format import parse_splits

init_db()
inject_global_css()

DOW_LABELS = ["L", "M", "M", "G", "V", "S", "D"]
VISTE = [
    ("1rm", "1RM"), ("wod", "WOD"), ("volume", "Volume"),
    ("confronto", "Confronto"), ("calendario", "Calendario"), ("statistiche", "Statistiche"),
]
RANGE_OPTIONS = [("7g", "7g"), ("30g", "30g"), ("90g", "90g"), ("tutto", "Tutto")]
TIPO_OPTIONS = [("tutti", "Tutti"), ("strength", "Strength"), ("complex", "Complex"), ("wod", "WOD"), ("accessorio", "Accessorio")]
TYPE_BADGE_STORICO = {"strength": "STR", "complex": "CPX", "wod": "WOD", "accessorio": "ACC"}


def _dark_plotly(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color=TEXT_PRIMARY_HEX,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.08)")
    return fig


def _intervallo_periodo(rng: str) -> tuple:
    oggi = date.today()
    if rng == "7g":
        return oggi - timedelta(days=6), oggi
    if rng == "30g":
        return oggi - timedelta(days=29), oggi
    if rng == "90g":
        return oggi - timedelta(days=89), oggi
    return date(2000, 1, 1), oggi


def _formatta_target_blocco(b: ProgramBlock) -> str:
    parti = []
    if b.tipo == "wod":
        if b.nome_wod:
            parti.append(b.nome_wod)
        if b.schema_reps:
            parti.append(b.schema_reps)
        if b.formato_wod:
            parti.append(b.formato_wod)
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


def _riga_set_log_html(num: int, e: LogEntry) -> str:
    kg_lbl = f"{e.carico_kg:g}kg" if e.carico_kg is not None else "—"
    reps_lbl = str(e.reps) if e.reps is not None else "—"
    rpe_lbl = f"{e.rpe:g}" if e.rpe is not None else "—"
    return (
        f'<div style="display:flex; align-items:center; gap:10px; background:oklch(23% 0.015 265); '
        f'border-radius:10px; padding:7px 10px; margin-bottom:4px;">'
        f'<div style="width:18px; color:{TEXT_TERTIARY}; font-weight:700; font-size:12px;">{num}</div>'
        f'<div style="flex:1; font-family:{FONT_DISPLAY}; font-size:13px; color:{TEXT_PRIMARY}; text-align:right;">'
        f'{kg_lbl} × {reps_lbl} <span style="color:{TEXT_SECONDARY}; font-family:inherit;">@ RPE {rpe_lbl}</span></div>'
        f"</div>"
    )


def _wod_headline_log(e: LogEntry) -> str:
    if e.risultato_tempo_sec:
        return f"{e.risultato_tempo_sec // 60}:{e.risultato_tempo_sec % 60:02d}"
    if e.risultato_round:
        extra = f" +{e.risultato_reps_extra}" if e.risultato_reps_extra else ""
        return f"{e.risultato_round} round{extra}"
    if e.risultato_reps_totali:
        return f"{e.risultato_reps_totali} reps"
    if e.carico_totale_kg:
        return f"{e.carico_totale_kg:g} kg tot."
    return "—"


def _riga_esecuzione(entry: LogEntry, data_sessione: date) -> dict:
    """Una riga della tabella 'ultime esecuzioni' della ricerca fuzzy: granularità
    per singolo LogEntry (un set = un'esecuzione), non aggregata per giornata,
    così carico/reps/RPE restano quelli effettivamente loggati riga per riga."""
    ha_set = entry.carico_kg is not None and entry.reps is not None
    volume = round(entry.carico_kg * entry.reps, 1) if ha_set else None
    stima_1rm = round(estimate_1rm(entry.carico_kg, entry.reps, entry.rpe)["average"], 1) if ha_set else None
    return {
        "Data": data_sessione,
        "Tipo": TYPE_BADGE_STORICO.get(entry.tipo, entry.tipo.upper()[:3]),
        "Carico (kg)": entry.carico_kg,
        "Reps": entry.reps,
        "RPE": entry.rpe,
        "Volume (kg)": volume,
        "1RM stimato (kg)": stima_1rm,
        "Risultato WOD": None if ha_set else _wod_headline_log(entry),
    }


def _dettaglio_giorno(session, giorno: date) -> list:
    """Righe da mostrare nel popup di dettaglio: una per ogni ProgramBlock del/dei
    giorni di piano loggati in questa data (con lo stato Fatto/Da fare), più una
    per ogni voce libera. Una stessa data può avere più `Log` (day_id diversi, es.
    un giorno di piano più una voce libera senza piano), quindi si aggregano tutti
    i day_id trovati invece di assumerne uno solo."""
    entries = (
        session.query(LogEntry)
        .join(Log, LogEntry.log_id == Log.id)
        .filter(Log.data == giorno)
        .all()
    )
    if not entries:
        return []

    day_ids = {
        day_id
        for (day_id,) in session.query(Log.day_id).filter(Log.data == giorno, Log.day_id.isnot(None)).distinct()
    }

    entries_per_blocco = defaultdict(list)
    entries_libere = []
    for e in entries:
        if e.block_id is not None:
            entries_per_blocco[e.block_id].append(e)
        else:
            entries_libere.append(e)

    righe = []
    for day_id in day_ids:
        blocchi = session.query(ProgramBlock).filter_by(day_id=day_id).order_by(ProgramBlock.ordine).all()
        for b in blocchi:
            voci = entries_per_blocco.pop(b.id, [])
            righe.append(
                {
                    "badge": TYPE_BADGE_STORICO.get(b.tipo, b.tipo.upper()[:3]),
                    "esercizio": b.esercizio,
                    "target": _formatta_target_blocco(b),
                    "tipo": b.tipo,
                    "done": bool(voci),
                    "voci": voci,
                }
            )

    for voci in entries_per_blocco.values():
        primo = voci[0]
        righe.append({"badge": "LIBERO", "esercizio": primo.esercizio, "target": "", "tipo": primo.tipo, "done": True, "voci": voci})
    for e in entries_libere:
        righe.append({"badge": "LIBERO", "esercizio": e.esercizio, "target": "", "tipo": e.tipo, "done": True, "voci": [e]})

    return righe


@st.dialog("Dettaglio allenamento")
def _mostra_dettaglio_giorno_dialog(giorno: date) -> None:
    st.markdown(
        f'<div style="font-family:{FONT_DISPLAY}; font-weight:700; font-size:18px; color:{TEXT_PRIMARY};">'
        f'{giorno.strftime("%d/%m/%Y")}</div>',
        unsafe_allow_html=True,
    )
    with SessionLocal() as session:
        righe = _dettaglio_giorno(session, giorno)

    if not righe:
        st.info("Nessun allenamento registrato.")
    else:
        for r in righe:
            st.markdown(
                f"""<div class="cft-card">
                    <div style="display:flex; align-items:center; gap:10px;">
                        {type_badge_html(r['badge'])}
                        <div style="flex:1; min-width:0;">
                            <div style="font-weight:600; font-size:14px; color:{TEXT_PRIMARY};">{r['esercizio']}</div>
                            <div style="color:{TEXT_SECONDARY}; font-size:12px; margin-top:1px;">{r['target']}</div>
                        </div>
                        {pill_html("✓ Fatto" if r['done'] else "● Da fare", r['done'])}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
            if r["voci"]:
                if r["tipo"] in ("strength", "complex", "accessorio"):
                    ordinate = sorted(r["voci"], key=lambda e: e.set_index or 0)
                    righe_html = "".join(_riga_set_log_html(i + 1, e) for i, e in enumerate(ordinate))
                    st.markdown(f'<div style="margin:-6px 0 12px;">{righe_html}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(
                        f'<div style="margin:-4px 0 12px; font-family:{FONT_DISPLAY}; font-weight:700; '
                        f'font-size:16px; color:{TEXT_PRIMARY};">{_wod_headline_log(r["voci"][0])}</div>',
                        unsafe_allow_html=True,
                    )

    col_link, col_close = st.columns(2)
    with col_link:
        if styled_button("→ Vai al Log", key="cal_dialog_vailog", variant="magenta"):
            with SessionLocal() as session:
                log_con_piano = (
                    session.query(Log).filter(Log.data == giorno, Log.day_id.isnot(None)).first()
                )
                if log_con_piano is not None:
                    program_day = session.get(ProgramDay, log_con_piano.day_id)
                    if program_day is not None:
                        programma = session.get(Program, program_day.program_id)
                        if programma is not None:
                            st.session_state["log_programma_select"] = programma.nome_mese
                        st.session_state["log_settimana_select"] = program_day.settimana
                        st.session_state["log_giorno_select"] = program_day.giorno_label
                        st.session_state["log_giorno_id"] = program_day.id
            st.session_state["log_data_sessione"] = giorno
            st.session_state["log_active_block"] = None
            st.session_state["log_screen"] = "main"
            st.switch_page("pages/2_Log_Giornaliero.py")
    with col_close:
        if styled_button("Chiudi", key="cal_dialog_close"):
            st.rerun()


st.session_state.setdefault("storico_view", "1rm")
st.session_state.setdefault("storico_filter_open", False)
st.session_state.setdefault("storico_range", "30g")
st.session_state.setdefault("storico_tipo", "tutti")

col_title, col_filter = st.columns([5, 1])
with col_title:
    st.markdown("## Storico")
with col_filter:
    if icon_button("⚗", key="storico_filter_icon", active=st.session_state["storico_filter_open"], help="Filtri periodo/tipo"):
        st.session_state["storico_filter_open"] = not st.session_state["storico_filter_open"]
        st.rerun()

if st.session_state["storico_filter_open"]:
    with popover_panel("storico_filter_panel"):
        st.markdown('<div class="cft-mini-label">Periodo</div>', unsafe_allow_html=True)
        chip_selector(RANGE_OPTIONS, session_key="storico_range", default="30g", per_row=4)
        st.markdown('<div class="cft-mini-label" style="margin-top:10px;">Tipo blocco</div>', unsafe_allow_html=True)
        chip_selector(TIPO_OPTIONS, session_key="storico_tipo", default="tutti", per_row=5)

st.text_input(
    "🔍 Cerca esercizio o WOD",
    key="storico_search_query",
    placeholder="es. clean & jerk, bb front squat, fran...",
    help="Ricerca fuzzy: tollera typo, maiuscole/minuscole, ordine parole e abbreviazioni (\"Bb\" per Barbell).",
)
query_ricerca = st.session_state.get("storico_search_query", "")

if query_ricerca.strip():
    with SessionLocal() as session:
        nomi_tutti = get_nomi_esercizi_esistenti(session)
    risultati = cerca_nomi_simili(query_ricerca, nomi_tutti, soglia=60)

    if not risultati:
        st.info(f"Nessun esercizio o WOD trovato per «{query_ricerca}».")
    else:
        nomi_risultato = [nome for nome, _ in risultati]
        if len(nomi_risultato) > 1:
            st.caption(f"{len(nomi_risultato)} corrispondenze trovate — scegli quale confrontare:")
            scelto = chip_selector(
                [(n, n) for n in nomi_risultato], session_key="storico_search_scelto",
                default=nomi_risultato[0], per_row=3,
            )
            # styled_button() forza white-space: nowrap !important sul bottone (oltre al
            # nowrap non-important già globale su .stButton) - va benissimo per le chip
            # corte (tab, day-pill) ma tronca/overflowa i nomi lunghi di esercizi/WOD
            # composti tipici dei risultati di questa ricerca. Override mirato ai soli
            # bottoni di questo chip_selector (prefisso di classe storico_search_scelto_chip_),
            # iniettato DOPO la chiamata cosi' vince la cascata (stessa specificita' +
            # !important, l'ultima regola in ordine di DOM ha la meglio) senza toccare gli
            # altri bottoni con contorno colorato già a posto altrove nell'app.
            st.markdown(
                """<style>
                [class*="st-key-storico_search_scelto_chip_"] button {
                    white-space: normal !important;
                    overflow-wrap: break-word !important;
                    word-break: break-word !important;
                    height: auto !important;
                    min-height: 2.5rem !important;
                    line-height: 1.3 !important;
                    padding-top: 0.55rem !important;
                    padding-bottom: 0.55rem !important;
                }
                </style>""",
                unsafe_allow_html=True,
            )
        else:
            scelto = nomi_risultato[0]

        with SessionLocal() as session:
            entries_con_data = (
                session.query(LogEntry, Log.data)
                .join(Log, LogEntry.log_id == Log.id)
                .filter(LogEntry.esercizio == scelto)
                .order_by(Log.data.desc(), LogEntry.set_index.desc())
                .limit(5)
                .all()
            )

        if not entries_con_data:
            st.info(f"Nessuna esecuzione storica trovata per '{scelto}'.")
        else:
            n_disponibili = len(entries_con_data)
            etichetta_conteggio = (
                f"Ultime {n_disponibili} esecuzioni" if n_disponibili >= 5
                else f"{n_disponibili} esecuzion{'e' if n_disponibili == 1 else 'i'} disponibil{'e' if n_disponibili == 1 else 'i'} (meno di 5 in totale)"
            )
            st.markdown(f'<div class="cft-mini-label" style="margin-top:8px;">{etichetta_conteggio} — {scelto}</div>', unsafe_allow_html=True)
            df_esecuzioni = pd.DataFrame(_riga_esecuzione(e, d) for e, d in entries_con_data)
            st.dataframe(df_esecuzioni, use_container_width=True, hide_index=True)
    st.divider()

data_da, data_a = _intervallo_periodo(st.session_state["storico_range"])
tipo_filtro = st.session_state["storico_tipo"]
tipo_db = None if tipo_filtro == "tutti" else tipo_filtro

vista = chip_selector(VISTE, session_key="storico_view", default="1rm", per_row=3)

if vista == "1rm":
    with SessionLocal() as session:
        esercizi_tracciati = (
            session.query(Exercise).filter_by(traccia_1rm=True).order_by(Exercise.nome_canonico).all()
        )

    if not esercizi_tracciati:
        st.info("Nessun esercizio tracciato configurato.")
    else:
        nomi = [e.nome_canonico for e in esercizi_tracciati]
        st.session_state.setdefault("storico_1rm_esercizi", [nomi[0]])
        st.session_state["storico_1rm_esercizi"] = [
            n for n in st.session_state["storico_1rm_esercizi"] if n in nomi
        ] or [nomi[0]]
        selezionati = st.session_state["storico_1rm_esercizi"]

        st.caption("Tocca per aggiungere/togliere dal confronto (max 4)")
        for i in range(0, len(nomi), 4):
            riga = nomi[i : i + 4]
            cols = st.columns(len(riga))
            for j, (col, nome) in enumerate(zip(cols, riga)):
                with col:
                    attivo = nome in selezionati
                    if styled_button(nome, key=f"1rm_chip_{i + j}", variant="magenta" if attivo else "neutral"):
                        if attivo:
                            if len(selezionati) > 1:
                                selezionati.remove(nome)
                        elif len(selezionati) < 4:
                            selezionati.append(nome)
                        else:
                            st.toast("Massimo 4 esercizi sovrapponibili nello stesso grafico.", icon="⚠️")
                        st.rerun()

        colori_hex = [GREEN_HEX, MAGENTA_HEX, BLUE_HEX, AMBER_HEX]
        serie = []
        for idx, nome in enumerate(selezionati):
            esercizio_id = next(e.id for e in esercizi_tracciati if e.nome_canonico == nome)
            with SessionLocal() as session:
                righe_db = (
                    session.query(LogEntry, Log.data)
                    .join(Log, LogEntry.log_id == Log.id)
                    .filter(
                        LogEntry.exercise_id == esercizio_id,
                        LogEntry.carico_kg.isnot(None),
                        LogEntry.reps.isnot(None),
                        Log.data >= data_da,
                        Log.data <= data_a,
                    )
                    .order_by(Log.data)
                    .all()
                )
            if not righe_db:
                continue
            dati = []
            for entry, data_sessione in righe_db:
                stime = estimate_1rm(entry.carico_kg, entry.reps, entry.rpe)
                dati.append(
                    {
                        "data": data_sessione,
                        "carico_kg": entry.carico_kg,
                        "reps": entry.reps,
                        "1RM stimato": round(stime["average"], 1),
                    }
                )
            df = pd.DataFrame(dati)
            df_migliore = df.loc[df.groupby("data")["1RM stimato"].idxmax()].reset_index(drop=True)
            serie.append({"nome": nome, "df": df_migliore, "colore": colori_hex[idx % 4]})

        if not serie:
            st.info(f"Nessun set con carico e reps compilati nel periodo selezionato ({st.session_state['storico_range']}).")
        else:
            primo = serie[0]
            record = primo["df"].loc[primo["df"]["1RM stimato"].idxmax()]
            if len(primo["df"]) >= 2:
                delta = primo["df"].iloc[-1]["1RM stimato"] - primo["df"].iloc[-2]["1RM stimato"]
                delta_str = f"{'+' if delta >= 0 else ''}{delta:.1f}kg"
            else:
                delta_str = "—"

            st.markdown(
                f"""
                <div class="cft-card">
                    <div style="color:{TEXT_SECONDARY}; font-size:12.5px;">Miglior 1RM stimato — {primo['nome']}</div>
                    <div style="display:flex; align-items:baseline; gap:8px; margin-top:4px;">
                        <div style="font-family:{FONT_DISPLAY}; font-weight:700; font-size:32px; color:{TEXT_PRIMARY};">{record['1RM stimato']:g} kg</div>
                        <div style="font-size:13px; font-weight:700; color:{GREEN};">{delta_str}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            fig = go.Figure()
            for s in serie:
                fig.add_trace(
                    go.Scatter(
                        x=s["df"]["data"], y=s["df"]["1RM stimato"], mode="lines+markers",
                        name=s["nome"], line=dict(color=s["colore"], width=2.5), marker=dict(size=7),
                    )
                )
            _dark_plotly(fig)
            n_punti_unici = max((s["df"]["data"].nunique() for s in serie), default=0)
            guarda_asse_singolo_punto(fig, n_punti_unici)
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("Dettaglio di tutti i set"):
                for s in serie:
                    st.caption(s["nome"])
                    st.dataframe(s["df"], use_container_width=True, hide_index=True)

elif vista == "wod":
    with SessionLocal() as session:
        wod_entries = (
            session.query(LogEntry, Log.data)
            .join(Log, LogEntry.log_id == Log.id)
            .filter(LogEntry.tipo == "wod", Log.data >= data_da, Log.data <= data_a)
            .order_by(Log.data)
            .all()
        )

    if not wod_entries:
        st.info("Nessun WOD loggato nel periodo selezionato.")
    else:
        gruppi = defaultdict(list)
        for entry, data_sessione in wod_entries:
            chiave = entry.esercizio.strip().lower()
            gruppi[chiave].append((entry, data_sessione))

        ripetuti = {k: v for k, v in gruppi.items() if len(v) > 1}

        if not ripetuti:
            st.info(
                "Nessun WOD ripetuto (stessa combinazione di movimenti) trovato nel periodo. "
                "Torna qui dopo aver rifatto lo stesso WOD in un'altra settimana."
            )
        else:
            etichette = {}
            for chiave, voci in ripetuti.items():
                nome_esplicito = None
                for entry, _ in voci:
                    if entry.note and "nome:" in entry.note.lower():
                        nome_esplicito = entry.note.split(":", 1)[1].strip().split(";")[0].strip()
                        break
                etichette[chiave] = nome_esplicito or voci[0][0].esercizio

            chiavi = list(ripetuti.keys())
            scelta_chiave = chip_selector(
                [(k, etichette[k]) for k in chiavi], session_key="storico_wod_scelta", default=chiavi[0]
            )
            voci = sorted(ripetuti[scelta_chiave], key=lambda v: v[1])

            righe = []
            for entry, data_sessione in voci:
                tempo_str = None
                if entry.risultato_tempo_sec:
                    tempo_str = f"{entry.risultato_tempo_sec // 60}:{entry.risultato_tempo_sec % 60:02d}"
                righe.append(
                    {
                        "data": data_sessione,
                        "formato": entry.formato_wod,
                        "tempo": tempo_str,
                        "round": entry.risultato_round,
                        "reps_extra": entry.risultato_reps_extra,
                        "reps_totali": entry.risultato_reps_totali,
                        "carico_totale_kg": entry.carico_totale_kg,
                        "note": entry.note,
                    }
                )
            df_wod = pd.DataFrame(righe)

            def _headline(riga: dict) -> str:
                if riga["tempo"]:
                    return riga["tempo"]
                if riga["round"]:
                    extra = f" +{riga['reps_extra']}" if riga["reps_extra"] else ""
                    return f"{riga['round']} round{extra}"
                if riga["reps_totali"]:
                    return f"{riga['reps_totali']} reps"
                if riga["carico_totale_kg"]:
                    return f"{riga['carico_totale_kg']:g} kg tot."
                return "—"

            for i, riga in enumerate(righe):
                is_last = i == len(righe) - 1
                border = "oklch(72% 0.23 345 / 0.4)" if is_last else BORDER
                color = MAGENTA if is_last else TEXT_PRIMARY
                st.markdown(
                    f"""
                    <div style="display:flex; align-items:center; justify-content:space-between;
                                background:oklch(19% 0.015 265); border-radius:12px; padding:12px 14px;
                                margin-bottom:8px; border:1px solid {border};">
                        <div style="color:{TEXT_SECONDARY}; font-size:13px;">{riga['data']}</div>
                        <div style="font-family:{FONT_DISPLAY}; font-weight:700; font-size:16px; color:{color};">{_headline(riga)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with st.expander("Dettaglio completo"):
                st.dataframe(df_wod, use_container_width=True, hide_index=True)

            if any(e.risultato_tempo_sec for e, _ in voci):
                df_plot = pd.DataFrame(
                    {"data": [d for _, d in voci], "secondi": [e.risultato_tempo_sec for e, _ in voci]}
                ).dropna()
                fig = px.line(df_plot, x="data", y="secondi", markers=True, title=f"Tempo — {etichette[scelta_chiave]}")
                fig.update_traces(line_color=MAGENTA_HEX, marker_color=GREEN_HEX)
                fig.update_yaxes(autorange="reversed")
                _dark_plotly(fig)
                guarda_asse_singolo_punto(fig, df_plot["data"].nunique())
                st.plotly_chart(fig, use_container_width=True)
            elif any(e.risultato_round for e, _ in voci):
                df_plot = pd.DataFrame(
                    {"data": [d for _, d in voci], "round": [e.risultato_round for e, _ in voci]}
                ).dropna()
                fig = px.line(df_plot, x="data", y="round", markers=True, title=f"Round completati — {etichette[scelta_chiave]}")
                fig.update_traces(line_color=MAGENTA_HEX, marker_color=GREEN_HEX)
                _dark_plotly(fig)
                guarda_asse_singolo_punto(fig, df_plot["data"].nunique())
                st.plotly_chart(fig, use_container_width=True)

            sessioni_con_split = [
                (data_sessione, parse_splits(entry.splits_json)) for entry, data_sessione in voci
            ]
            sessioni_con_split = [(d, s) for d, s in sessioni_con_split if s]
            if len(sessioni_con_split) >= 2:
                st.subheader(f"Pacing round-by-round — {etichette[scelta_chiave]}")
                righe_pacing = []
                for data_sessione, splits in sessioni_con_split:
                    for indice, split in enumerate(splits, start=1):
                        righe_pacing.append(
                            {
                                "sessione": data_sessione.isoformat(),
                                "posizione": indice,
                                "split": split["label"],
                                "secondi": split["time_sec"],
                            }
                        )
                df_pacing = pd.DataFrame(righe_pacing)
                etichette_split = df_pacing.groupby("posizione")["split"].first().to_dict()
                df_pacing["posizione_label"] = df_pacing["posizione"].map(
                    lambda p: f"{p}. {etichette_split[p]}"
                )
                fig_pacing = px.line(
                    df_pacing.sort_values("posizione"),
                    x="posizione_label", y="secondi", color="sessione", markers=True,
                    title=f"Tempo cumulativo per split — {etichette[scelta_chiave]}",
                )
                fig_pacing.update_layout(xaxis_title="Split", yaxis_title="Tempo trascorso (s)")
                _dark_plotly(fig_pacing)
                st.plotly_chart(fig_pacing, use_container_width=True)

elif vista == "volume":
    with SessionLocal() as session:
        query = (
            session.query(LogEntry, Log.data)
            .join(Log, LogEntry.log_id == Log.id)
            .filter(
                LogEntry.carico_kg.isnot(None), LogEntry.reps.isnot(None),
                Log.data >= data_da, Log.data <= data_a,
            )
        )
        if tipo_db:
            query = query.filter(LogEntry.tipo == tipo_db)
        else:
            query = query.filter(LogEntry.tipo.in_(["strength", "complex"]))
        entries = query.all()

    if not entries:
        st.info("Nessun dato di volume disponibile per il periodo/tipo selezionati.")
    else:
        righe = []
        for entry, data_sessione in entries:
            iso_anno, iso_settimana, _ = data_sessione.isocalendar()
            righe.append(
                {
                    "volume": entry.carico_kg * entry.reps,
                    "anno": iso_anno,
                    "settimana": iso_settimana,
                    "mese": data_sessione.strftime("%Y-%m"),
                }
            )
        df = pd.DataFrame(righe)

        col1, col2 = st.columns(2)
        with col1:
            df_sett = df.groupby(["anno", "settimana"], as_index=False)["volume"].sum()
            df_sett["etichetta"] = df_sett["anno"].astype(str) + "-W" + df_sett["settimana"].astype(str)
            fig = px.bar(
                df_sett, x="etichetta", y="volume", title="Volume settimanale (kg totali)",
                color_discrete_sequence=[GREEN_HEX],
            )
            _dark_plotly(fig)
            guarda_asse_singolo_punto(fig, df_sett["etichetta"].nunique())
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            df_mese = df.groupby("mese", as_index=False)["volume"].sum()
            fig = px.bar(
                df_mese, x="mese", y="volume", title="Volume mensile (kg totali)",
                color_discrete_sequence=[MAGENTA_HEX],
            )
            _dark_plotly(fig)
            guarda_asse_singolo_punto(fig, df_mese["mese"].nunique())
            st.plotly_chart(fig, use_container_width=True)

elif vista == "confronto":
    oggi = date.today()
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f'<div style="color:{GREEN}; font-size:11px; font-weight:700;">Periodo A</div>', unsafe_allow_html=True)
        periodo_a = st.date_input(
            "Periodo A", value=(data_da, data_a), key="storico_compare_a", label_visibility="collapsed",
        )
    with col_b:
        st.markdown(f'<div style="color:{MAGENTA}; font-size:11px; font-weight:700;">Periodo B</div>', unsafe_allow_html=True)
        periodo_b = st.date_input(
            "Periodo B", value=(oggi - timedelta(days=13), oggi - timedelta(days=7)),
            key="storico_compare_b", label_visibility="collapsed",
        )

    if len(periodo_a) == 2 and len(periodo_b) == 2:
        with SessionLocal() as session:
            metriche_a = metriche_periodo(session, periodo_a[0], periodo_a[1], tipo_filtro if tipo_filtro != "tutti" else None)
            metriche_b = metriche_periodo(session, periodo_b[0], periodo_b[1], tipo_filtro if tipo_filtro != "tutti" else None)

        righe_confronto = [
            ("Volume totale (kg)", "volume_totale", "{:,.0f}"),
            ("Tonnellaggio princ. (kg)", "tonnellaggio", "{:,.0f}"),
            ("N. sessioni", "n_sessioni", "{:d}"),
            ("RPE medio", "rpe_medio", "{:.1f}"),
            ("PR ottenuti", "pr_ottenuti", "{:d}"),
        ]
        righe_html = []
        for label, chiave, fmt in righe_confronto:
            va, vb = metriche_a[chiave], metriche_b[chiave]
            va_str = fmt.format(va) if va is not None else "—"
            vb_str = fmt.format(vb) if vb is not None else "—"
            if va is not None and vb is not None:
                delta = vb - va
                delta_str = f"{'+' if delta >= 0 else ''}{delta:,.1f}"
                delta_color = GREEN if delta >= 0 else MAGENTA
            else:
                delta_str, delta_color = "—", TEXT_TERTIARY
            righe_html.append(
                f'<div style="display:flex; align-items:center; padding:12px 0; border-bottom:1px solid {BORDER};">'
                f'<div style="flex:1.3; color:{TEXT_SECONDARY}; font-size:12.5px;">{label}</div>'
                f'<div style="flex:1; text-align:right; font-family:{FONT_DISPLAY}; font-weight:700; font-size:14px; color:{GREEN};">{va_str}</div>'
                f'<div style="flex:1; text-align:right; font-family:{FONT_DISPLAY}; font-weight:700; font-size:14px; color:{MAGENTA};">{vb_str}</div>'
                f'<div style="flex:0.9; text-align:right; font-size:11.5px; font-weight:700; color:{delta_color};">{delta_str}</div>'
                f"</div>"
            )
        st.markdown(
            f'<div style="margin-top:14px; background:oklch(19% 0.015 265); border-radius:16px; padding:2px 16px;">{"".join(righe_html)}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("Scegli una data di inizio e una di fine per entrambi i periodi.")

elif vista == "calendario":
    st.session_state.setdefault("storico_cal_month", date.today().replace(day=1))
    mese_corrente = st.session_state["storico_cal_month"]

    col_prev, col_label, col_next = st.columns([1, 4, 1])
    with col_prev:
        if st.button("◀", key="cal_prev_month", use_container_width=True):
            precedente = mese_corrente - timedelta(days=1)
            st.session_state["storico_cal_month"] = precedente.replace(day=1)
            st.rerun()
    with col_label:
        st.markdown(
            f'<div style="text-align:center; font-family:{FONT_DISPLAY}; font-weight:700; color:{TEXT_PRIMARY};">'
            f'{mese_corrente.strftime("%B %Y").capitalize()}</div>',
            unsafe_allow_html=True,
        )
    with col_next:
        prossimo_mese_oltre_oggi = mese_corrente.replace(day=28) + timedelta(days=4) > date.today()
        if st.button("▶", key="cal_next_month", use_container_width=True, disabled=prossimo_mese_oltre_oggi):
            successivo = mese_corrente.replace(day=28) + timedelta(days=4)
            st.session_state["storico_cal_month"] = successivo.replace(day=1)
            st.rerun()

    _, giorni_nel_mese = pycalendar.monthrange(mese_corrente.year, mese_corrente.month)
    primo_del_mese = date(mese_corrente.year, mese_corrente.month, 1)
    ultimo_del_mese = date(mese_corrente.year, mese_corrente.month, giorni_nel_mese)

    with SessionLocal() as session:
        entries_mese = (
            session.query(LogEntry, Log.data)
            .join(Log, LogEntry.log_id == Log.id)
            .filter(Log.data >= primo_del_mese, Log.data <= ultimo_del_mese)
            .all()
        )

    volume_per_giorno = defaultdict(float)
    esercizi_per_giorno = defaultdict(set)
    for entry, d in entries_mese:
        esercizi_per_giorno[d].add(entry.esercizio)
        if entry.carico_kg and entry.reps:
            volume_per_giorno[d] += entry.carico_kg * entry.reps

    massimo_volume = max(volume_per_giorno.values()) if volume_per_giorno else 0.0

    offset_lunedi = primo_del_mese.weekday()
    celle = [None] * offset_lunedi + [date(mese_corrente.year, mese_corrente.month, g) for g in range(1, giorni_nel_mese + 1)]
    while len(celle) % 7 != 0:
        celle.append(None)

    header_cols = st.columns(7)
    for col, lbl in zip(header_cols, DOW_LABELS):
        with col:
            st.markdown(f'<div style="text-align:center; font-size:10.5px; color:{TEXT_TERTIARY};">{lbl}</div>', unsafe_allow_html=True)

    giorno_selezionato = st.session_state.get("storico_cal_day")
    for inizio_settimana in range(0, len(celle), 7):
        settimana = celle[inizio_settimana : inizio_settimana + 7]
        cols = st.columns(7)
        for col, d in zip(cols, settimana):
            with col:
                if d is None:
                    st.write("")
                else:
                    intensity = (volume_per_giorno.get(d, 0) / massimo_volume) if massimo_volume else 0.0
                    selezionato = giorno_selezionato == d
                    if calendar_day_button(str(d.day), key=f"cal_day_{d.isoformat()}", intensity=intensity, selected=selezionato):
                        if selezionato:
                            st.session_state["storico_cal_day"] = None
                            st.rerun()
                        else:
                            st.session_state["storico_cal_day"] = d
                            if d in esercizi_per_giorno:
                                # Il dialog va invocato direttamente qui, nello stesso run del
                                # click - non tramite un flag persistente in session_state
                                # controllato ad ogni rerun (pattern che causava la riapertura
                                # involontaria: se l'utente chiudeva il dialog con la X nativa
                                # di st.dialog invece del bottone "Chiudi", il flag restava
                                # settato e QUALSIASI rerun successivo, anche di un filtro
                                # scorrelato, lo ritrovava vero e riapriva la stessa modale).
                                # st.dialog si chiude da solo quando la funzione decorata non
                                # viene richiamata in un run: qui non lo è mai, a meno di un
                                # nuovo click esplicito sul giorno.
                                _mostra_dettaglio_giorno_dialog(d)
                            else:
                                st.rerun()

    st.markdown(
        f"""<div style="display:flex; align-items:center; gap:6px; margin-top:8px; font-size:10.5px; color:{TEXT_TERTIARY};">
            meno
            <div style="width:12px; height:12px; border-radius:3px; background:oklch(80% 0.19 152 / 0.12);"></div>
            <div style="width:12px; height:12px; border-radius:3px; background:oklch(80% 0.19 152 / 0.4);"></div>
            <div style="width:12px; height:12px; border-radius:3px; background:oklch(80% 0.19 152 / 0.8);"></div>
            più
        </div>""",
        unsafe_allow_html=True,
    )

    if giorno_selezionato and giorno_selezionato.month == mese_corrente.month:
        esercizi = sorted(esercizi_per_giorno.get(giorno_selezionato, []))
        volume_sel = volume_per_giorno.get(giorno_selezionato, 0)
        if esercizi:
            dettaglio = f"{len(esercizi)} esercizi: {', '.join(esercizi)} · Volume: {volume_sel:.0f} kg"
        else:
            dettaglio = "Nessun allenamento registrato."
        st.markdown(
            f"""<div class="cft-card">
                <div style="font-weight:600; color:{TEXT_PRIMARY};">{giorno_selezionato.strftime('%d/%m/%Y')}</div>
                <div style="color:{TEXT_SECONDARY}; font-size:12px; margin-top:3px;">{dettaglio}</div>
            </div>""",
            unsafe_allow_html=True,
        )

else:  # statistiche
    oggi = date.today()
    with SessionLocal() as session:
        streak = calcola_streak(session)
        pr_mese = conta_pr_nel_mese(session, oggi.year, oggi.month)
        programmi_tutti = session.query(Program).order_by(Program.data_import.desc()).all()
        if programmi_tutti:
            aderenza = calcola_aderenza(session, programmi_tutti[0].id, data_da, data_a)
            aderenza_label = f"{aderenza['percentuale']:g}%"
        else:
            aderenza_label = "—"
        rpe_conteggi_30 = distribuzione_rpe(session, oggi - timedelta(days=29), oggi)
        metriche_30 = metriche_periodo(session, oggi - timedelta(days=29), oggi)

    rpe_medio_30 = metriche_30["rpe_medio"]
    stat_grid(
        [
            ("🔥", str(streak), "streak giorni consecutivi"),
            ("🏆", str(pr_mese), "PR nel mese"),
            ("📊", aderenza_label, "% aderenza al piano"),
            ("💪", f"{rpe_medio_30:g}" if rpe_medio_30 is not None else "—", "RPE medio ultimi 30gg"),
        ]
    )

    st.markdown('<div class="cft-mini-label" style="margin-top:16px;">Distribuzione RPE (ultimi 30gg)</div>', unsafe_allow_html=True)
    colori_bar = []
    for i in range(10):
        bucket = i + 1
        if bucket >= 9:
            colori_bar.append(MAGENTA_HEX)
        elif bucket >= 7:
            colori_bar.append(GREEN_HEX)
        else:
            colori_bar.append("#4b5563")
    etichette_bar = [str(i + 1) for i in range(10)]
    st.markdown(bar_row_html(rpe_conteggi_30, etichette_bar, colori_bar), unsafe_allow_html=True)

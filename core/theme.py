"""Dark theme (palette, global CSS, small UI helpers) shared by app.py and all pages.

Design tokens come from design_handoff_ux_redesign/README.md. Widgets are still
native Streamlit - this module only supplies colors/CSS and thin wrappers so the
same look (cards, pills, chips, steppers) is reachable from every page without
duplicating markup.
"""

from __future__ import annotations

import re

import streamlit as st

BG = "oklch(12% 0.01 265)"
SURFACE = "oklch(19% 0.015 265)"
SURFACE_HOVER = "oklch(25% 0.015 265)"
SURFACE_HOVER_2 = "oklch(28% 0.015 265)"
BORDER = "oklch(32% 0.02 265)"
TEXT_PRIMARY = "oklch(97% 0.005 265)"
TEXT_SECONDARY = "oklch(64% 0.02 265)"
TEXT_TERTIARY = "oklch(50% 0.02 265)"

GREEN = "oklch(80% 0.19 152)"
GREEN_BG = "oklch(80% 0.19 152 / 0.14)"
GREEN_BORDER = "oklch(80% 0.19 152 / 0.4)"

MAGENTA = "oklch(72% 0.23 345)"
MAGENTA_BG = "oklch(72% 0.23 345 / 0.14)"
MAGENTA_BORDER = "oklch(72% 0.23 345 / 0.4)"

# Bordo colorato centralizzato per qualunque elemento cliccabile ma NON
# selezionato (tab di Storico, chip esercizio, day-pill, bottoni "Dettagli"/
# "Chiudi"/"+ Aggiungi..."): stessa tinta di MAGENTA_BORDER, esposta con un
# nome semantico così l'intento resta esplicito ovunque venga consumato,
# invece di ripetere stili inline sparsi per componente. Lo stato selezionato/
# attivo resta invece a fill pieno (styled_button variant "magenta"/"green"),
# senza bordo - il contorno è il segnale "disponibile ma non selezionato".
INTERACTIVE_BORDER = MAGENTA_BORDER

# Usati solo come 3a/4a serie quando Storico > 1RM sovrappone più di 2
# esercizi tracciati (selezione multipla) - vedi design_handoff_ux_redesign/README.md.
BLUE = "oklch(72% 0.15 250)"
BLUE_BG = "oklch(72% 0.15 250 / 0.14)"
BLUE_BORDER = "oklch(72% 0.15 250 / 0.4)"

AMBER = "oklch(78% 0.15 80)"
AMBER_BG = "oklch(78% 0.15 80 / 0.14)"
AMBER_BORDER = "oklch(78% 0.15 80 / 0.4)"

# Plotly's color validation doesn't understand oklch() (unlike browsers, which
# render the CSS above just fine) - these hex equivalents are for use in
# Plotly figures (line_color, marker colors, color_discrete_sequence, font_color...).
GREEN_HEX = "#4ade80"
MAGENTA_HEX = "#ec4899"
BLUE_HEX = "#60a5fa"
AMBER_HEX = "#fbbf24"
TEXT_PRIMARY_HEX = "#f7f7f8"

ON_ACCENT = "oklch(12% 0.01 265)"  # testo scuro sopra bottoni pieni verdi/magenta

FONT_DISPLAY = "'Space Grotesk', sans-serif"

# Gap unico e coerente per i controlli stepper (−/valore/+): STEPPER_INNER_GAP
# separa i 3 elementi di un singolo gruppo (minus/valore/plus), STEPPER_GROUP_GAP
# separa gruppi diversi dello stesso stepper (es. Carico | Reps | RPE) così da
# leggersi come colonne distinte. Riusato identico in tabella set e impostazioni
# EMOM tramite st.columns(..., gap=...).
STEPPER_INNER_GAP = "small"
STEPPER_GROUP_GAP = "medium"

# Rapporto di larghezza fisso per le coppie di bottoni secondario/primario
# (es. "Aggiungi set" / "Salva modifiche"), invece di lasciare che la
# larghezza dipenda solo dal testo contenuto.
PRIMARY_SECONDARY_RATIO = [0.4, 0.6]


def inject_global_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&display=swap');

        html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"],
        [data-testid="stHeader"], [data-testid="stMain"] {{
            background-color: {BG} !important;
        }}
        [data-testid="stSidebar"] {{
            background-color: {BG} !important;
            border-right: 1px solid {BORDER};
        }}
        [data-testid="stSidebarNav"] a span {{
            font-weight: 600;
        }}

        h1, h2, h3, h4, h5,
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3 {{
            font-family: {FONT_DISPLAY} !important;
            font-weight: 700 !important;
            color: {TEXT_PRIMARY} !important;
            letter-spacing: -0.3px;
        }}
        [data-testid="stCaptionContainer"] {{
            color: {TEXT_SECONDARY} !important;
        }}

        /* Bottoni: pillola scura di default, con contorno magenta tenue
        già a riposo (non solo su hover) - segnala "cliccabile" a colpo
        d'occhio anche per i bottoni plain (es. "Dettagli"/"Chiudi", "+
        Aggiungi set") che non passano da styled_button(). */
        .stButton button, .stDownloadButton button {{
            background: {SURFACE_HOVER};
            color: {TEXT_PRIMARY};
            border: 1px solid {INTERACTIVE_BORDER};
            border-radius: 10px;
            font-weight: 600;
            white-space: nowrap;
        }}
        .stButton button:hover, .stDownloadButton button:hover {{
            border-color: {MAGENTA};
            color: {MAGENTA};
        }}
        .stButton button[kind="primary"] {{
            background: {MAGENTA} !important;
            color: {ON_ACCENT} !important;
            border: none !important;
        }}
        .stButton button:disabled {{
            opacity: 0.35;
        }}

        /* Tabs -> segmented control scuro */
        [data-testid="stTabs"] [data-baseweb="tab-list"] {{
            background: {SURFACE};
            border-radius: 12px;
            padding: 4px;
            gap: 4px;
        }}
        [data-testid="stTabs"] button[data-baseweb="tab"] {{
            border-radius: 9px !important;
            color: {TEXT_SECONDARY} !important;
            font-weight: 600;
        }}
        [data-testid="stTabs"] button[aria-selected="true"] {{
            background: {MAGENTA} !important;
            color: {ON_ACCENT} !important;
        }}
        [data-testid="stTabs"] [data-baseweb="tab-highlight"],
        [data-testid="stTabs"] [data-baseweb="tab-border"] {{
            display: none !important;
        }}

        [data-testid="stMetricValue"] {{
            font-family: {FONT_DISPLAY} !important;
            color: {TEXT_PRIMARY} !important;
        }}
        [data-testid="stMetricDelta"] {{ color: {GREEN} !important; }}

        [data-testid="stFileUploaderDropzone"] {{
            background: {SURFACE} !important;
            border: 1.5px dashed {BORDER} !important;
            border-radius: 16px !important;
        }}
        [data-testid="stExpander"] {{
            background: {SURFACE};
            border: 1px solid {BORDER} !important;
            border-radius: 14px !important;
        }}
        [data-testid="stExpander"] summary {{
            color: {TEXT_PRIMARY} !important;
        }}

        input, textarea,
        .stNumberInput input, .stTextInput input, .stDateInput input {{
            background: {SURFACE_HOVER} !important;
            color: {TEXT_PRIMARY} !important;
            border: 1px solid {BORDER} !important;
            border-radius: 8px !important;
        }}
        [data-baseweb="select"] > div {{
            background: {SURFACE_HOVER} !important;
            border-color: {BORDER} !important;
            border-radius: 8px !important;
        }}

        [data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {{
            background: {MAGENTA} !important;
        }}

        .cft-card {{
            background: {SURFACE};
            border-radius: 16px;
            border: 1px solid {BORDER};
            padding: 14px 14px 4px;
            margin-bottom: 4px;
        }}
        .cft-card-done {{ border-color: oklch(45% 0.1 152 / 0.35); }}
        .cft-card-todo {{ border-color: oklch(45% 0.12 345 / 0.35); }}

        .cft-pill {{
            display: inline-block;
            font-size: 11.5px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 999px;
            border: 1px solid transparent;
            white-space: nowrap;
        }}
        .cft-pill-done {{ background: {GREEN_BG}; color: {GREEN}; border-color: {GREEN_BORDER}; }}
        .cft-pill-todo {{ background: {MAGENTA_BG}; color: {MAGENTA}; border-color: {MAGENTA_BORDER}; }}

        .cft-badge-type {{
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.4px;
            color: {TEXT_SECONDARY};
            background: {SURFACE_HOVER};
            border-radius: 6px;
            padding: 3px 6px;
            display: inline-block;
        }}

        .cft-progress-track {{
            height: 8px;
            border-radius: 4px;
            background: {SURFACE_HOVER};
            overflow: hidden;
        }}
        .cft-progress-fill {{ height: 100%; border-radius: 4px; background: {GREEN}; }}

        .cft-stat {{
            text-align: center;
            border-radius: 12px;
            padding: 10px;
            background: {GREEN_BG};
            border: 1px solid {GREEN_BORDER};
        }}
        .cft-stat .cft-stat-num {{
            font-family: {FONT_DISPLAY};
            font-weight: 700;
            font-size: 18px;
            color: {GREEN};
        }}
        .cft-stat .cft-stat-lbl {{ font-size: 10.5px; color: {TEXT_SECONDARY}; margin-top: 2px; }}

        /* Stesso riquadro con bordo del bottone "Carico", riusato per tutti i
        valori stepper (Reps, RPE, Round, Reps totali, Min/round, ...) così che
        nessun campo si distingua per essere semplice testo non centrato. */
        .cft-value-label {{
            font-family: {FONT_DISPLAY};
            font-size: 14px;
            font-weight: 600;
            color: {TEXT_PRIMARY};
            text-align: center;
            background: {SURFACE_HOVER};
            border: 1px solid {BORDER};
            border-radius: 10px;
            padding: 0.5rem 0.6rem;
            box-sizing: border-box;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 2.5rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .cft-set-num {{
            font-size: 12px;
            color: {TEXT_TERTIARY};
            font-weight: 700;
            text-align: center;
        }}
        .cft-mini-label {{
            font-size: 11px;
            color: {TEXT_TERTIARY};
            text-align: center;
            margin-bottom: 2px;
        }}

        /* Centra verticalmente (flexbox align-items:center) i bottoni −/+ e il
        valore sulla stessa riga, sia per il gruppo singolo (−/valore/+) sia per
        la riga che affianca più gruppi (Carico | Reps | RPE, o Round | Reps
        totali | Min/round). Vedi simple_stepper()/kg_stepper() in
        pages/2_Log_Giornaliero.py per dove vengono applicate le chiavi
        "stepper_inner_*" e "stepper_row_*". */
        [class*="st-key-stepper_inner"] [data-testid="stHorizontalBlock"],
        [class*="st-key-stepper_row"] [data-testid="stHorizontalBlock"] {{
            align-items: center !important;
        }}
        /* Su viewport stretti (iPhone) il doppio annidamento st.columns()
        (gruppo esterno Carico|Reps|RPE -> riga −/valore/+ interna) fa andare
        a capo il livello interno, trasformando −/valore/+ in una colonna di
        bottoni a piena larghezza. Forziamo qui SOLO il livello "stepper_inner"
        (−/valore/+) a restare su una riga orizzontale: il livello esterno
        "stepper_row" può continuare a impilarsi verticalmente su schermi
        stretti, è già leggibile così. */
        [class*="st-key-stepper_inner"] [data-testid="stHorizontalBlock"] {{
            flex-direction: row !important;
            flex-wrap: nowrap !important;
        }}
        [class*="st-key-stepper_inner"] [data-testid="stColumn"] {{
            min-width: 0 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _safe_key(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", key)


def styled_button(
    label: str,
    key: str,
    variant: str = "neutral",
    use_container_width: bool = True,
    disabled: bool = False,
    help: str | None = None,
) -> bool:
    """`st.button` recolored via the `st-key-<key>` class Streamlit attaches to
    st.container(key=...). variant: "green" | "magenta" | "neutral-selected" | "neutral"."""
    bg, color, border = {
        "green": (GREEN, ON_ACCENT, "none"),
        "magenta": (MAGENTA, ON_ACCENT, "none"),
        "neutral-selected": (SURFACE_HOVER_2, TEXT_PRIMARY, INTERACTIVE_BORDER),
        "neutral": (SURFACE_HOVER, TEXT_PRIMARY, INTERACTIVE_BORDER),
    }[variant]
    css_key = _safe_key(key)
    st.markdown(
        f"""<style>.st-key-{css_key} button {{
            background: {bg} !important; color: {color} !important;
            border: 1px solid {border} !important;
            white-space: nowrap !important;
        }}</style>""",
        unsafe_allow_html=True,
    )
    with st.container(key=key):
        return st.button(
            label, key=f"{key}_btn", use_container_width=use_container_width,
            disabled=disabled, help=help,
        )


def chip_selector(options: list[tuple[str, str]], session_key: str, default: str | None = None, per_row: int = 5) -> str:
    """Riga (o righe, se più di `per_row` opzioni) di chip orizzontali a selezione
    singola. `options`: [(value, label), ...]. Ritorna il valore corrente
    (persistito in session_state[session_key])."""
    if session_key not in st.session_state or st.session_state[session_key] not in [v for v, _ in options]:
        st.session_state[session_key] = default if default is not None else options[0][0]

    selected = st.session_state[session_key]
    for i in range(0, len(options), per_row):
        riga = options[i : i + per_row]
        cols = st.columns(len(riga))
        for col, (value, label) in zip(cols, riga):
            with col:
                variant = "magenta" if value == selected else "neutral"
                if styled_button(label, key=f"{session_key}_chip_{_safe_key(value)}", variant=variant):
                    st.session_state[session_key] = value
                    st.rerun()
    return st.session_state[session_key]


def text_button(label: str, key: str, use_container_width: bool = True) -> bool:
    """Bottone senza sfondo/bordo, sottolineatura tratteggiata: usato per il numero
    del carico cliccabile che apre l'editing manuale."""
    css_key = _safe_key(key)
    st.markdown(
        f"""<style>.st-key-{css_key} button {{
            background: transparent !important;
            border: none !important;
            border-bottom: 1px dotted {TEXT_TERTIARY} !important;
            border-radius: 0 !important;
            color: {TEXT_PRIMARY} !important;
            font-family: {FONT_DISPLAY};
        }}</style>""",
        unsafe_allow_html=True,
    )
    with st.container(key=key):
        return st.button(label, key=f"{key}_btn", use_container_width=use_container_width)


def pill_html(label: str, done: bool) -> str:
    variant = "done" if done else "todo"
    return f'<span class="cft-pill cft-pill-{variant}">{label}</span>'


def type_badge_html(label: str) -> str:
    return f'<span class="cft-badge-type">{label}</span>'


def progress_bar(done: int, total: int, label: str) -> None:
    pct = round(100 * done / total) if total else 0
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:10px; margin: 6px 0 4px;">
            <div class="cft-progress-track" style="flex:1;">
                <div class="cft-progress-fill" style="width:{pct}%;"></div>
            </div>
            <div style="font-size:13px; color:{TEXT_SECONDARY}; font-weight:600; white-space:nowrap;">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def stat_badges(items: list[tuple[str, str]]) -> None:
    """items: [(numero, etichetta), ...] mostrati come mini-card verdi in riga."""
    cols = st.columns(len(items))
    for col, (num, lbl) in zip(cols, items):
        with col:
            st.markdown(
                f"""<div class="cft-stat">
                    <div class="cft-stat-num">{num}</div>
                    <div class="cft-stat-lbl">{lbl}</div>
                </div>""",
                unsafe_allow_html=True,
            )


def icon_button(icon: str, key: str, active: bool = False, help: str | None = None) -> bool:
    """Bottone icona quadrato (~2.4rem) per i trigger dei popover leggeri: "⋯"
    del Log, "📅" data, "⚗" filtri di Storico. `active` lo evidenzia in magenta
    quando il popover che apre è attualmente visibile."""
    bg, color, border = (SURFACE_HOVER_2, MAGENTA, MAGENTA_BORDER) if active else (SURFACE_HOVER, TEXT_PRIMARY, INTERACTIVE_BORDER)
    css_key = _safe_key(key)
    st.markdown(
        f"""<style>.st-key-{css_key} button {{
            background: {bg} !important; color: {color} !important;
            border: 1px solid {border} !important; border-radius: 10px !important;
            width: 2.4rem !important; min-width: 2.4rem !important; height: 2.4rem !important;
            padding: 0 !important; font-size: 16px !important; min-height: 0 !important;
        }}</style>""",
        unsafe_allow_html=True,
    )
    with st.container(key=key):
        return st.button(icon, key=f"{key}_btn", help=help)


def popover_panel(key: str):
    """Container stilizzato come mini-pannello popover (sfondo card + bordo),
    usato subito sotto un `icon_button` per il menu "⋯" e il pannello filtri di
    Storico. Va usato come `with popover_panel("key"): ...`."""
    css_key = _safe_key(key)
    st.markdown(
        f"""<style>.st-key-{css_key} {{
            background: {SURFACE} !important; border-radius: 14px !important;
            border: 1px solid {BORDER} !important; padding: 6px !important;
        }}</style>""",
        unsafe_allow_html=True,
    )
    return st.container(key=key, border=True)


def subscreen_header(title: str, back_key: str) -> bool:
    """Header "← Torna" delle sotto-schermate a piena pagina (Log: Tutti gli
    allenamenti / Impostazioni stepper) che sostituiscono temporaneamente il
    contenuto principale invece di un vero overlay modale. Ritorna True se
    l'utente ha premuto "← Torna"."""
    col_back, col_title = st.columns([1, 4])
    with col_back:
        tornato = styled_button("← Torna", key=back_key, use_container_width=True)
    with col_title:
        st.markdown(
            f'<div style="font-family:{FONT_DISPLAY}; font-weight:700; font-size:18px; padding-top:8px;">{title}</div>',
            unsafe_allow_html=True,
        )
    return tornato


def calendar_day_button(label: str, key: str, intensity: float, selected: bool = False, disabled: bool = False) -> bool:
    """Cella-bottone quadrata della griglia mensile di Storico > Calendario:
    sfondo verde con opacità proporzionale a `intensity` (0-1, volume/frequenza
    normalizzato sul mese), bordo magenta se `selected`. Un vero st.button (non
    solo HTML) perché il tap deve aprire il riepilogo del giorno sotto la griglia."""
    opacity = round(0.10 + 0.70 * max(0.0, min(1.0, intensity)), 2) if intensity > 0 else 0.0
    bg = f"oklch(80% 0.19 152 / {opacity})" if opacity > 0 else SURFACE_HOVER
    border = MAGENTA if selected else BORDER
    css_key = _safe_key(key)
    st.markdown(
        f"""<style>.st-key-{css_key} button {{
            background: {bg} !important; color: {TEXT_PRIMARY} !important;
            border: 1.5px solid {border} !important; border-radius: 8px !important;
            aspect-ratio: 1; padding: 0 !important; font-weight: 600 !important;
        }}</style>""",
        unsafe_allow_html=True,
    )
    with st.container(key=key):
        return st.button(label, key=f"{key}_btn", use_container_width=True, disabled=disabled)


def bar_row_html(valori: list, etichette: list, colori: list, height_px: int = 90) -> str:
    """Mini bar-chart verticale in puro HTML/CSS (barre con altezza
    proporzionale al massimo valore) - usato per l'istogramma di distribuzione
    RPE in Storico > Statistiche, senza tirare in ballo Plotly per un grafico
    così semplice. Va passato a st.markdown(..., unsafe_allow_html=True)."""
    massimo = max(valori) if valori and max(valori) > 0 else 1
    barre = "".join(
        f'<div style="display:flex; flex-direction:column; align-items:center; gap:4px; flex:1;">'
        f'<div style="width:100%; max-width:22px; height:{max(3, round(height_px * v / massimo))}px; '
        f'background:{c}; border-radius:4px 4px 0 0; align-self:flex-end;"></div>'
        f'<div style="font-size:10px; color:{TEXT_TERTIARY};">{lbl}</div>'
        f"</div>"
        for v, lbl, c in zip(valori, etichette, colori)
    )
    return f'<div style="display:flex; align-items:flex-end; gap:6px; height:{height_px + 20}px;">{barre}</div>'


def stat_grid(items: list[tuple[str, str, str]]) -> None:
    """items: [(icona, valore, etichetta), ...] mostrati in una griglia 2x2 di
    stat-card (Storico > Statistiche: streak, PR nel mese, aderenza, RPE medio)."""
    for i in range(0, len(items), 2):
        riga = items[i : i + 2]
        cols = st.columns(2)
        for col, (icon, valore, lbl) in zip(cols, riga):
            with col:
                st.markdown(
                    f"""<div class="cft-card" style="padding-bottom:14px;">
                        <div style="font-size:20px; line-height:1;">{icon}</div>
                        <div style="font-family:{FONT_DISPLAY}; font-weight:700; font-size:22px; color:{TEXT_PRIMARY}; margin-top:6px;">{valore}</div>
                        <div style="font-size:11.5px; color:{TEXT_SECONDARY}; margin-top:2px;">{lbl}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

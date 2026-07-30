import pandas as pd
import streamlit as st

from core.db import SessionLocal, init_db
from core.exercise_names import (
    get_nomi_esercizi_esistenti,
    trova_possibili_duplicati,
    unifica_nomi_esercizio,
)
from core.models import LogEntry, ProgramBlock
from core.theme import inject_global_css

init_db()
inject_global_css()

st.markdown("## Manutenzione dati")
st.caption(
    "Operazioni una tantum sui dati grezzi, separate dall'analisi di Storico "
    "(vedi design_handoff_ux_redesign/README.md: 'Duplicati esercizi' è manutenzione, non analisi)."
)

st.subheader("🔍 Duplicati esercizi")
st.caption(
    "Confronto fuzzy tra tutti i nomi esercizio/WOD visti nei programmi importati e nei log. "
    "Nessuna unificazione automatica: sono solo segnalazioni da valutare tu."
)
with SessionLocal() as session:
    nomi = get_nomi_esercizi_esistenti(session)

if len(nomi) < 2:
    st.info("Servono almeno due nomi esercizio distinti per confrontarli.")
else:
    soglia = st.slider(
        "Soglia di somiglianza (%)", min_value=50, max_value=100, value=85, step=5,
        help="Più alta = solo coppie quasi identiche. Più bassa = più candidati, anche meno simili.",
    )
    duplicati = trova_possibili_duplicati(nomi, soglia=soglia)

    if not duplicati:
        st.success(f"Nessun possibile duplicato sopra il {soglia}% di somiglianza, su {len(nomi)} nomi confrontati.")
    else:
        st.warning(f"{len(duplicati)} possibile/i coppia/e di duplicati trovata/e su {len(nomi)} nomi:")
        df_dup = pd.DataFrame(duplicati, columns=["Nome A", "Nome B", "Somiglianza %"])
        st.dataframe(df_dup, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Unifica una coppia")

        etichette_coppie = [f"{a} ↔ {b}  ({score}%)" for a, b, score in duplicati]
        indice_scelto = st.selectbox(
            "Coppia da unificare", range(len(duplicati)), format_func=lambda i: etichette_coppie[i]
        )
        nome_a, nome_b, score = duplicati[indice_scelto]
        chiave_coppia = f"{hash((nome_a, nome_b))}"

        with SessionLocal() as session:
            conteggio_a = (
                session.query(ProgramBlock).filter_by(esercizio=nome_a).count()
                + session.query(LogEntry).filter_by(esercizio=nome_a).count()
            )
            conteggio_b = (
                session.query(ProgramBlock).filter_by(esercizio=nome_b).count()
                + session.query(LogEntry).filter_by(esercizio=nome_b).count()
            )
        st.caption(f"'{nome_a}' compare in {conteggio_a} record · '{nome_b}' compare in {conteggio_b} record")

        scelta_canonico = st.radio(
            "Tieni come nome canonico:",
            [f"'{nome_a}' ({conteggio_a} record)", f"'{nome_b}' ({conteggio_b} record)", "Altro (modifica manualmente)"],
            key=f"radio_{chiave_coppia}",
        )

        if scelta_canonico.startswith("Altro"):
            nome_canonico_finale = st.text_input(
                "Nome canonico personalizzato", value=nome_a, key=f"custom_{chiave_coppia}"
            ).strip()
            nomi_da_scartare = [nome_a, nome_b]
        elif scelta_canonico.startswith(f"'{nome_a}'"):
            nome_canonico_finale = nome_a
            nomi_da_scartare = [nome_b]
        else:
            nome_canonico_finale = nome_b
            nomi_da_scartare = [nome_a]

        st.caption(f"Verrà mantenuto: **{nome_canonico_finale}**")

        conferma_merge = st.checkbox(
            "Confermo l'unificazione (riscrive i record esistenti, azione irreversibile)",
            key=f"conf_merge_{chiave_coppia}",
        )
        if st.button("🔀 Unifica", key=f"unifica_{chiave_coppia}"):
            if not conferma_merge:
                st.error("Spunta 'Confermo l'unificazione' prima di procedere.")
            elif not nome_canonico_finale:
                st.error("Il nome canonico non può essere vuoto.")
            else:
                try:
                    blocchi_tot, voci_tot = 0, 0
                    with SessionLocal() as save_session:
                        for nome_scartato in nomi_da_scartare:
                            if nome_scartato == nome_canonico_finale:
                                continue
                            esito = unifica_nomi_esercizio(save_session, nome_scartato, nome_canonico_finale)
                            blocchi_tot += esito["blocchi_aggiornati"]
                            voci_tot += esito["voci_log_aggiornate"]
                except ValueError as errore:
                    st.error(str(errore))
                else:
                    st.success(
                        f"Unificato in '{nome_canonico_finale}': {blocchi_tot} blocchi piano e "
                        f"{voci_tot} voci di log aggiornate."
                    )
                    st.toast(f"Unificato: {nome_canonico_finale}", icon="🔀")
                    st.rerun()

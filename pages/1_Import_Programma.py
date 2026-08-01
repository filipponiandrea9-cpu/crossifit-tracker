import pandas as pd
import streamlit as st

from core.db import SessionLocal, init_db
from core.docx_parser import extract_text_from_docx
from core.exercise_names import applica_alias_esercizio
from core.llm_parser import parse_program_with_claude
from core.models import Program, ProgramBlock, ProgramDay
from core.theme import (
    BORDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    inject_global_css,
    stat_badges,
    styled_button,
)

init_db()
inject_global_css()

st.markdown("## Import")
st.caption("Carica il programma mensile in .docx")

COLUMNS = [
    "settimana",
    "allenamento",
    "focus",
    "tipo",
    "esercizio",
    "target_carico_kg",
    "target_percentuale",
    "target_reps",
    "target_rpe",
    "formato_wod",
    "note",
]


def flatten_to_dataframe(parsed: dict) -> pd.DataFrame:
    rows = []
    for settimana in parsed["settimane"]:
        s_num = settimana["settimana"]
        for giorno in settimana["giorni"]:
            blocchi = giorno.get("blocchi") or [{}]
            for blocco in blocchi:
                rows.append(
                    {
                        "settimana": s_num,
                        "allenamento": giorno.get("giorno", ""),
                        "focus": giorno.get("focus"),
                        "tipo": blocco.get("tipo", "strength"),
                        "esercizio": blocco.get("esercizio", ""),
                        "target_carico_kg": blocco.get("target_carico_kg"),
                        "target_percentuale": blocco.get("target_percentuale"),
                        "target_reps": blocco.get("target_reps"),
                        "target_rpe": blocco.get("target_rpe"),
                        "formato_wod": blocco.get("formato_wod"),
                        "note": blocco.get("note"),
                    }
                )
    return pd.DataFrame(rows, columns=COLUMNS)


def save_program(nome_mese: str, file_originale: str, df: pd.DataFrame, json_raw: str) -> None:
    with SessionLocal() as session:
        program = Program(nome_mese=nome_mese, file_originale=file_originale, json_raw=json_raw)
        session.add(program)
        session.flush()

        day_lookup: dict[tuple, ProgramDay] = {}
        block_order: dict[tuple, int] = {}
        for _, row in df.iterrows():
            key = (row["settimana"], row["allenamento"])
            if key not in day_lookup:
                day = ProgramDay(
                    program_id=program.id,
                    settimana=int(row["settimana"]),
                    giorno_label=str(row["allenamento"]),
                    focus=row["focus"] if pd.notna(row["focus"]) else None,
                )
                session.add(day)
                session.flush()
                day_lookup[key] = day
                block_order[key] = 0
            day = day_lookup[key]

            if not str(row["esercizio"]).strip():
                continue

            esercizio_normalizzato = applica_alias_esercizio(session, str(row["esercizio"]).strip())

            block_order[key] += 1
            block = ProgramBlock(
                day_id=day.id,
                ordine=block_order[key],
                tipo=row["tipo"] or "strength",
                esercizio=esercizio_normalizzato,
                target_carico_kg=row["target_carico_kg"] if pd.notna(row["target_carico_kg"]) else None,
                target_percentuale=row["target_percentuale"] if pd.notna(row["target_percentuale"]) else None,
                schema_reps=row["target_reps"] if pd.notna(row["target_reps"]) else None,
                target_rpe=row["target_rpe"] if pd.notna(row["target_rpe"]) else None,
                formato_wod=row["formato_wod"] if pd.notna(row["formato_wod"]) else None,
                note=row["note"] if pd.notna(row["note"]) else None,
            )
            session.add(block)

        session.commit()


def _bullet_line(row) -> str:
    dettagli = []
    if pd.notna(row.get("target_reps")) and str(row.get("target_reps")).strip():
        dettagli.append(str(row["target_reps"]))
    if pd.notna(row.get("target_carico_kg")):
        dettagli.append(f"{row['target_carico_kg']:g}kg")
    if pd.notna(row.get("target_percentuale")):
        dettagli.append(f"{row['target_percentuale']:g}%")
    if pd.notna(row.get("target_rpe")):
        dettagli.append(f"RPE {row['target_rpe']:g}")
    if pd.notna(row.get("formato_wod")) and str(row.get("formato_wod")).strip():
        dettagli.append(str(row["formato_wod"]))
    riga = str(row["esercizio"])
    if dettagli:
        riga += " — " + " · ".join(dettagli)
    return riga


def render_preview_cards(df: pd.DataFrame) -> None:
    for settimana in sorted(df["settimana"].dropna().unique()):
        df_sett = df[df["settimana"] == settimana]
        card_key = f"prev_week_{int(settimana)}"
        st.markdown(
            f"""<style>.st-key-{card_key} {{
                background: oklch(19% 0.015 265) !important;
                border-radius: 14px !important;
                border: 1px solid {BORDER} !important;
            }}</style>""",
            unsafe_allow_html=True,
        )
        with st.container(key=card_key, border=True):
            st.markdown(
                f'<div style="color:{TEXT_PRIMARY}; font-weight:700; font-size:13.5px;">Settimana {int(settimana)}</div>',
                unsafe_allow_html=True,
            )
            for giorno in df_sett["allenamento"].drop_duplicates():
                df_giorno = df_sett[df_sett["allenamento"] == giorno]
                focus = df_giorno["focus"].iloc[0] if pd.notna(df_giorno["focus"].iloc[0]) else None
                intestazione = f'<div style="color:{TEXT_SECONDARY}; font-size:12.5px; font-weight:600; margin-top:8px;">{giorno}'
                if focus:
                    intestazione += f' · <span style="font-weight:400; color:{TEXT_TERTIARY};">{focus}</span>'
                intestazione += "</div>"
                st.markdown(intestazione, unsafe_allow_html=True)

                righe_blocco = [row for _, row in df_giorno.iterrows() if str(row["esercizio"]).strip()]
                if not righe_blocco:
                    st.markdown(
                        f'<div style="color:{TEXT_TERTIARY}; font-size:12px; padding-left:8px;">(nessun blocco)</div>',
                        unsafe_allow_html=True,
                    )
                    continue
                bullets = "".join(
                    f'<div style="display:flex; gap:8px; align-items:baseline; margin-top:4px; padding-left:4px;">'
                    f'<div style="width:4px; height:4px; border-radius:999px; background:{TEXT_TERTIARY}; flex-shrink:0;"></div>'
                    f'<div style="color:{TEXT_PRIMARY}; font-size:12.5px;">{_bullet_line(row)}</div></div>'
                    for row in righe_blocco
                )
                st.markdown(bullets, unsafe_allow_html=True)


uploaded_file = st.file_uploader("Carica il file .docx del programma mensile", type=["docx"])

if uploaded_file is not None:
    raw_text = extract_text_from_docx(uploaded_file)
    with st.expander("Testo estratto dal Word (verifica)"):
        st.text(raw_text)

    nome_mese = st.text_input("Nome del mese", value="")

    if styled_button("🤖 Genera struttura con Claude", key="parse_btn", variant="magenta", use_container_width=False):
        if not nome_mese.strip():
            st.error("Inserisci il nome del mese prima di avviare il parsing.")
        else:
            with st.spinner("Claude sta analizzando il programma..."):
                try:
                    parsed = parse_program_with_claude(raw_text)
                except Exception as exc:
                    st.error(f"Errore durante il parsing: {exc}")
                else:
                    st.session_state["parsed_program"] = parsed
                    st.session_state["parsed_json_raw"] = str(parsed)
                    st.session_state["editable_df"] = flatten_to_dataframe(parsed)
                    if not nome_mese:
                        nome_mese = parsed.get("mese", "")
                    st.session_state["nome_mese"] = nome_mese

if "editable_df" in st.session_state:
    df_corrente = st.session_state["editable_df"]

    n_settimane = int(df_corrente["settimana"].nunique())
    n_allenamenti = int(df_corrente[["settimana", "allenamento"]].drop_duplicates().shape[0])
    n_blocchi = int(df_corrente[df_corrente["esercizio"].astype(str).str.strip() != ""].shape[0])
    stat_badges([(n_settimane, "settimane"), (n_allenamenti, "allenamenti"), (n_blocchi, "blocchi")])

    st.markdown(
        f'<div style="color:{TEXT_SECONDARY}; font-size:12.5px; margin-top:14px;">'
        f'Anteprima — {st.session_state.get("nome_mese", "")}</div>',
        unsafe_allow_html=True,
    )
    render_preview_cards(df_corrente)

    with st.expander("✏️ Modifica come tabella"):
        st.caption(
            "Il parsing su notazione libera non è mai perfetto al 100%: correggi righe, settimana/"
            "allenamento, carichi o note prima di salvare. La data di ogni sessione non è fissata qui: "
            "la scegli tu quando registri l'allenamento svolto, in qualsiasi ordine ti sia comodo "
            "all'interno della settimana."
        )
        edited_df = st.data_editor(
            df_corrente,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "tipo": st.column_config.SelectboxColumn(
                    "Tipo", options=["strength", "complex", "wod", "accessorio"]
                ),
                "target_percentuale": st.column_config.NumberColumn("% 1RM", format="%.1f%%"),
            },
            key="program_editor",
        )
        st.session_state["editable_df"] = edited_df

    nome_mese_finale = st.text_input(
        "Nome mese da salvare", value=st.session_state.get("nome_mese", "")
    )

    if styled_button("✅ Conferma e salva programma", key="save_program_btn", variant="green", use_container_width=False):
        if not nome_mese_finale.strip():
            st.error("Inserisci un nome per il mese prima di salvare.")
        else:
            save_program(
                nome_mese=nome_mese_finale,
                file_originale=uploaded_file.name if uploaded_file else "sconosciuto",
                df=st.session_state["editable_df"],
                json_raw=st.session_state.get("parsed_json_raw", ""),
            )
            st.success(f"Programma '{nome_mese_finale}' salvato correttamente.")
            for key in ["editable_df", "parsed_program", "parsed_json_raw", "nome_mese"]:
                st.session_state.pop(key, None)
            st.rerun()


st.divider()
st.subheader("📂 File importati")

with SessionLocal() as _session:
    programmi_importati = _session.query(Program).order_by(Program.data_import.desc()).all()
    metadati = {}
    for p in programmi_importati:
        n_settimane = (
            _session.query(ProgramDay.settimana).filter_by(program_id=p.id).distinct().count()
        )
        n_giorni = _session.query(ProgramDay).filter_by(program_id=p.id).count()
        metadati[p.id] = (n_settimane, n_giorni)

if not programmi_importati:
    st.info("Nessun programma importato ancora.")
else:
    for p in programmi_importati:
        n_settimane, n_giorni = metadati[p.id]
        card_key = f"import_row_{p.id}"
        st.markdown(
            f"""<style>.st-key-{card_key} {{
                background: oklch(19% 0.015 265) !important;
                border-radius: 14px !important;
                border: 1px solid {BORDER} !important;
            }}</style>""",
            unsafe_allow_html=True,
        )
        with st.container(key=card_key, border=True):
            col_info, col_del = st.columns([4, 1])
            with col_info:
                st.markdown(
                    f'<div style="color:{TEXT_PRIMARY}; font-weight:700; font-size:14px;">{p.nome_mese}</div>'
                    f'<div style="color:{TEXT_SECONDARY}; font-size:12px; margin-top:2px;">'
                    f'{p.file_originale or "sconosciuto"} · importato il {p.data_import.strftime("%d/%m/%Y %H:%M")} · '
                    f'{n_settimane} settimane, {n_giorni} allenamenti</div>',
                    unsafe_allow_html=True,
                )
            with col_del:
                if styled_button("🗑️ Elimina", key=f"del_btn_{p.id}", use_container_width=True):
                    st.session_state[f"confirm_delete_{p.id}"] = True
                    st.rerun()

            if st.session_state.get(f"confirm_delete_{p.id}"):
                st.warning(
                    f"Eliminare definitivamente '{p.nome_mese}'? I blocchi pianificati di questo "
                    "programma saranno rimossi; gli allenamenti già registrati nel Log restano "
                    "salvati, solo scollegati dal programma."
                )
                conferma = st.checkbox("Confermo l'eliminazione", key=f"confirm_chk_{p.id}")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if styled_button(
                        "Elimina definitivamente", key=f"del_confirm_{p.id}",
                        variant="magenta", disabled=not conferma,
                    ):
                        with SessionLocal() as _save_session:
                            programma_da_eliminare = _save_session.get(Program, p.id)
                            if programma_da_eliminare is not None:
                                _save_session.delete(programma_da_eliminare)
                                _save_session.commit()
                        st.session_state.pop(f"confirm_delete_{p.id}", None)
                        st.session_state.pop(f"confirm_chk_{p.id}", None)
                        st.toast(f"Eliminato: {p.nome_mese}", icon="🗑️")
                        st.rerun()
                with col_no:
                    if styled_button("Annulla", key=f"del_cancel_{p.id}"):
                        st.session_state.pop(f"confirm_delete_{p.id}", None)
                        st.rerun()

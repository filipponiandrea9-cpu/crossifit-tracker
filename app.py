import streamlit as st

from core.db import init_db
from core.theme import inject_global_css

st.set_page_config(page_title="CrossFit Tracker", page_icon="🏋️", layout="wide")
inject_global_css()

init_db()

st.title("🏋️ CrossFit / Forza Tracker")
st.write(
    "Usa il menu a sinistra per importare un programma mensile, loggare l'allenamento "
    "giornaliero o consultare storico e progressi."
)

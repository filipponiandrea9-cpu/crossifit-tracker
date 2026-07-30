"""Lettura dei secret dell'app: prima `st.secrets` (Streamlit Community Cloud),
poi `os.environ`/`.env` (sviluppo locale). `st.secrets` solleva un'eccezione se
`.streamlit/secrets.toml` non esiste (caso normale in locale senza Postgres),
quindi il fallback va gestito qui invece che ripetuto in ogni chiamante."""

from __future__ import annotations

import os

import streamlit as st


def get_secret(key: str) -> str | None:
    try:
        value = st.secrets[key]
    except Exception:
        value = None
    return value or os.environ.get(key)

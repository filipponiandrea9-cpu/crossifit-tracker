import json

import anthropic
from dotenv import load_dotenv

from core.secrets import get_secret

load_dotenv()

MODEL = "claude-opus-5"

PROGRAM_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "mese": {"type": "string"},
        "settimane": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "settimana": {"type": "integer"},
                    "giorni": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "giorno": {"type": "string"},
                                "focus": {"type": ["string", "null"]},
                                "blocchi": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "tipo": {
                                                "type": "string",
                                                "enum": ["strength", "complex", "wod", "accessorio"],
                                            },
                                            "esercizio": {"type": "string"},
                                            "target_carico_kg": {"type": ["number", "null"]},
                                            "target_percentuale": {"type": ["number", "null"]},
                                            "target_reps": {"type": ["string", "null"]},
                                            "target_rpe": {"type": ["number", "null"]},
                                            "formato_wod": {"type": ["string", "null"]},
                                            "note": {"type": ["string", "null"]},
                                        },
                                        "required": [
                                            "tipo",
                                            "esercizio",
                                            "target_carico_kg",
                                            "target_percentuale",
                                            "target_reps",
                                            "target_rpe",
                                            "formato_wod",
                                            "note",
                                        ],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["giorno", "focus", "blocchi"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["settimana", "giorni"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["mese", "settimane"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Sei un assistente che trasforma un programma di allenamento di forza/sollevamento
olimpico/CrossFit, scritto da un coach in notazione libera (spesso mista italiano/inglese, con
abbreviazioni tipo "Bb"=barbell, "Mb"=medicine ball, "Kb"=kettlebell, "Db"=dumbbell), in un JSON
strutturato secondo lo schema fornito.

STRUTTURA DEL TESTO SORGENTE
- Il testo e' organizzato in "Week N" (settimana) e "Day N" (giorno), spesso seguiti da un trattino
  e una breve etichetta di focus (es. "Day 1 - Power + Work Capacity"). A volte l'etichetta di
  focus e' su una riga separata subito dopo "Day N" (senza trattino): in quel caso trattala comunque
  come "focus" di quel giorno.
- All'interno di un giorno, ogni blocco di lavoro e' introdotto da un elenco puntato ("•") o da una
  riga tipo "N-N-N Of:" / "(1+1+1) Of:" / "For Time:" / "X Min Emom Of:" seguita da una o piu' righe
  con i movimenti.
- Se lo stesso numero di "Day" appare due volte nella stessa settimana (probabile refuso del coach),
  NON correggerlo: riporta il "giorno" esattamente come scritto nel testo, l'utente lo sistemera'
  nell'anteprima editabile.

CLASSIFICAZIONE DEI BLOCCHI (campo "tipo")
- "strength": un singolo esercizio con uno schema di reps e un carico (fisso in kg o percentuale di
  1RM), es. "Bb Back Squats 60% 1rm 8-8-8-8 Reps". Include anche i test a un solo massimale (es.
  "1-...-1 Of: Bb Back Squat / 1rm"): in questo caso target_reps="1", note="Test 1RM (nessun carico
  prefissato)".
- "complex": piu' movimenti olimpici concatenati nello stesso set, tipicamente scritti come
  "(1+1+1)-(1+1+1)-... Of:" seguito da movimenti separati da "+" (es. "Bb Squat Clean + Front
  Squat + Split Jerk"). Metti tutti i movimenti in "esercizio" separati da " + ", esattamente
  nell'ordine scritto.
- "wod": blocchi con formato For Time / AMRAP / EMOM (incluse varianti come "E5MO5M" = ogni 5:00 al
  minuto per N set) / Round Of / Death By / Tabata / accumulo a tempo. Anche se il WOD ha piu'
  movimenti (es. "6 Round Of: Bb Thrusters (40kg) 10 Reps + Pull Ups 10 Reps"), crea UN SOLO blocco
  "wod": metti tutti i movimenti (con eventuali carichi tra parentesi, cosi' come scritti) in
  "esercizio" separati da " + ", lo schema di round/reps in "target_reps", il formato (es. "For
  Time", "6 Round", "20 Min EMOM ogni 5:00") in "formato_wod". NON provare a scomporre il WOD in un
  blocco per movimento: chi usa l'app logga solo il risultato finale del WOD (tempo/round/reps), non
  il dettaglio per movimento.
- "accessorio": lavoro complementare (core, mobilita', accessori).
- Se il WOD ha un nome proprio tra virgolette (es. "Fran"), scrivilo in "note" come "Nome: Fran".

CARICHI (target_carico_kg, target_percentuale, target_rpe)
- Se il testo indica un carico assoluto in kg per l'intero blocco (tipico dei blocchi "strength",
  es. "Bb Deadlifts (50kg)"), usa target_carico_kg e lascia target_percentuale=null.
- Se il testo indica una percentuale di 1RM (es. "Parti @ 80% 1rm", "60% 1rm 8-8-8-8 Reps"), metti
  il valore numerico in target_percentuale (se e' un range tipo "65-72.5% 1rm" usa il valore piu'
  basso) e lascia target_carico_kg=null. Riporta SEMPRE per intero in "note" l'istruzione originale
  legata al carico (es. "Parti @ 80% 1RM, aggiungi peso by feeling. Resta conservativo, non
  arrivare al massimale.", oppure "65-72.5% 1RM riferito a Squat Snatch 1RM" se la percentuale si
  riferisce a un sollevamento diverso da quello del blocco). Non perdere questa informazione: e'
  fondamentale per l'atleta.
- Se non c'e' ne' RPE ne' percentuale ne' kg indicati esplicitamente, lascia tutti e tre i campi
  null: non dedurre e non inventare valori.
- "target_rpe" va valorizzato solo se il testo scrive esplicitamente un RPE (es. "@7RPE").

ALTRI CAMPI
- "target_reps" e' lo schema di ripetizioni COSI' COME SCRITTO nel testo originale (es. "8-8-8",
  "(1+1+1)-(1+1+1)", "21-15-9", "1-...-1"). Stringa libera, non normalizzare.
- "focus" e' la breve etichetta del giorno se presente (es. "Power + Work Capacity"), altrimenti
  null.
- "note" puo' contenere piu' informazioni concatenate con "; " (istruzione sul carico, nome del
  WOD, dettagli extra) quando serve riportare piu' di una cosa.
- Se un valore non e' presente nel testo, usa null. Non inventare mai dati assenti dal testo.
"""


def parse_program_with_claude(raw_text: str) -> dict:
    """Send raw program text to Claude and return the structured program dict.

    Requires ANTHROPIC_API_KEY in `.streamlit/secrets.toml` (Streamlit Community
    Cloud) or in the environment/.env file (locale).
    """
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": PROGRAM_JSON_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": f"Ecco il testo grezzo del programma mensile, estratto da un file Word:\n\n{raw_text}",
            }
        ],
    )

    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)

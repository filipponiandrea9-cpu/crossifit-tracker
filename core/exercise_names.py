from sqlalchemy.orm import Session

from core.exercise_matching import resolve_exercise_id
from core.models import Exercise, LogEntry, NomeEsercizioAlias, ProgramBlock


def normalizza_nome_esercizio(testo: str) -> str:
    """Title case + spazi multipli collassati + trim, per i nomi inseriti a mano.

    Non tocca il testo degli esercizi/WOD importati dal piano (quello resta
    esattamente come estratto da Claude) - si applica solo a input liberi
    dell'utente in "Aggiungi voce senza piano".
    """
    return " ".join(testo.split()).strip().title()


def get_nomi_esercizi_esistenti(session: Session) -> list:
    """Elenco ordinato di tutti i nomi esercizio/WOD gia' visti nell'app: nei
    programmi importati, nei log storici e nell'anagrafica tracciata per l'1RM.
    Usato per popolare il selectbox con ricerca in "Aggiungi voce senza piano".
    """
    nomi = set()
    for (esercizio,) in session.query(ProgramBlock.esercizio).distinct():
        if esercizio:
            nomi.add(esercizio.strip())
    for (esercizio,) in session.query(LogEntry.esercizio).distinct():
        if esercizio:
            nomi.add(esercizio.strip())
    for (nome,) in session.query(Exercise.nome_canonico).distinct():
        if nome:
            nomi.add(nome.strip())
    return sorted(nomi, key=str.lower)


def trova_possibili_duplicati(nomi: list, soglia: int = 85) -> list:
    """Coppie di nomi esercizio con similarita' fuzzy >= soglia (0-100).

    Non unifica nulla: restituisce solo i candidati, l'utente decide se e come
    intervenire. Confronto case-insensitive; una coppia (a, b) e' riportata una
    sola volta (a < b alfabeticamente).
    """
    from rapidfuzz import fuzz

    coppie = []
    nomi_ordinati = sorted(set(nomi), key=str.lower)
    for i, nome_a in enumerate(nomi_ordinati):
        for nome_b in nomi_ordinati[i + 1 :]:
            if nome_a.strip().lower() == nome_b.strip().lower():
                continue  # differiscono solo per maiuscole/spazi, non un "possibile" duplicato: lo sono
            punteggio = fuzz.token_sort_ratio(nome_a, nome_b)
            if punteggio >= soglia:
                coppie.append((nome_a, nome_b, round(punteggio, 1)))
    return sorted(coppie, key=lambda c: -c[2])


def cerca_nomi_simili(query: str, nomi: list, soglia: int = 60, limit: int = 20) -> list:
    """Cerca tra `nomi` quelli fuzzy-simili a `query` (barra di ricerca in
    Storico): a differenza di `trova_possibili_duplicati` (confronta coppie di
    nomi già in anagrafica tra loro), qui si confronta un singolo testo libero
    digitato dall'utente contro l'anagrafica esistente. Stessa libreria
    (rapidfuzz) per coerenza, ma `process.extract` con lo scorer WRatio invece
    di `token_sort_ratio`: WRatio pesa meglio corrispondenze parziali e
    abbreviazioni ("bb" per "Barbell", ordine parole diverso) tipiche di una
    ricerca "a naso" piuttosto che del confronto simmetrico usato per i
    duplicati. Soglia di default più bassa (60 invece di 85) perché qui
    l'obiettivo è essere permissivi con typo/abbreviazioni, non evitare falsi
    positivi tra nomi già canonici.

    Ritorna [(nome, punteggio), ...] ordinati per punteggio decrescente,
    punteggio 0-100.
    """
    from rapidfuzz import fuzz, process

    query = (query or "").strip()
    if not query or not nomi:
        return []
    corrispondenze = process.extract(query, nomi, scorer=fuzz.WRatio, limit=limit)
    return [(nome, round(punteggio, 1)) for nome, punteggio, _ in corrispondenze if punteggio >= soglia]


def applica_alias_esercizio(session: Session, nome: str) -> str:
    """Se `nome` e' stato unificato in passato, ritorna il nome canonico finale
    (seguendo la catena nel caso il canonico sia a sua volta un alias verso un
    terzo nome). Se non c'e' nessuna mappatura, ritorna `nome` invariato.

    Va chiamata prima di scrivere un nuovo ProgramBlock/LogEntry, cosi' che i
    nomi gia' unificati non ricompaiano mai piu' nel DB.
    """
    if not nome:
        return nome
    corrente = nome.strip()
    visti = {corrente}
    for _ in range(10):  # guardia anti-ciclo
        alias = session.query(NomeEsercizioAlias).filter_by(alias=corrente).first()
        if alias is None:
            return corrente
        if alias.nome_canonico in visti:
            return corrente  # ciclo anomalo: meglio fermarsi che spaccare tutto
        corrente = alias.nome_canonico
        visti.add(corrente)
    return corrente


def unifica_nomi_esercizio(session: Session, nome_scartato: str, nome_canonico: str) -> dict:
    """Unifica `nome_scartato` in `nome_canonico`: riscrive retroattivamente
    tutte le righe ProgramBlock/LogEntry che usano il nome scartato, e salva la
    mappatura cosi' che i futuri import/log lo normalizzino automaticamente.

    Solleva ValueError se i nomi non sono validi, o se si tenta di scartare il
    nome canonico di uno dei sollevamenti tracciati per l'1RM (per non
    comprometterne l'identita').

    Un solo commit a fine funzione: se qualcosa fallisce prima, il chiamante
    (tipicamente un `with SessionLocal() as session:`) scarta tutto alla
    chiusura senza bisogno di gestione transazionale esplicita.
    """
    nome_scartato = (nome_scartato or "").strip()
    nome_canonico = (nome_canonico or "").strip()

    if not nome_scartato or not nome_canonico:
        raise ValueError("Entrambi i nomi devono essere non vuoti.")
    if nome_scartato == nome_canonico:
        raise ValueError("I due nomi coincidono: niente da unificare.")

    nome_canonico_finale = applica_alias_esercizio(session, nome_canonico)

    if nome_scartato == nome_canonico_finale:
        raise ValueError("I due nomi risolvono allo stesso nome canonico: niente da unificare.")

    esercizio_tracciato = (
        session.query(Exercise).filter_by(nome_canonico=nome_scartato, traccia_1rm=True).first()
    )
    if esercizio_tracciato is not None:
        raise ValueError(
            f"'{nome_scartato}' e' il nome canonico di un sollevamento tracciato per l'1RM: "
            "non puo' essere scartato."
        )

    blocchi_aggiornati = (
        session.query(ProgramBlock)
        .filter(ProgramBlock.esercizio == nome_scartato)
        .update({"esercizio": nome_canonico_finale}, synchronize_session=False)
    )

    voci_log = session.query(LogEntry).filter(LogEntry.esercizio == nome_scartato).all()
    for voce in voci_log:
        voce.esercizio = nome_canonico_finale
        voce.exercise_id = resolve_exercise_id(session, nome_canonico_finale)

    # Collassa eventuali alias che puntavano al nome appena scartato.
    session.query(NomeEsercizioAlias).filter_by(nome_canonico=nome_scartato).update(
        {"nome_canonico": nome_canonico_finale}, synchronize_session=False
    )

    alias_esistente = session.query(NomeEsercizioAlias).filter_by(alias=nome_scartato).first()
    if alias_esistente is not None:
        alias_esistente.nome_canonico = nome_canonico_finale
    else:
        session.add(NomeEsercizioAlias(alias=nome_scartato, nome_canonico=nome_canonico_finale))

    session.commit()

    return {"blocchi_aggiornati": blocchi_aggiornati, "voci_log_aggiornate": len(voci_log)}

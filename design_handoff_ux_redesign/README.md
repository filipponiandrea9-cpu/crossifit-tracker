# Handoff: Analisi UX + Redesign Log/Storico — CrossFit Tracker (Streamlit)

## Overview
Questo pacchetto contiene due cose: (1) un'**analisi UX** dell'app Streamlit esistente (punti di forza e criticità, basata sulla lettura di `app.py`, `pages/*.py`, `core/*.py`) e (2) un **redesign mirato** di due schermate:

- **Log**: reso più semplice, essenziale e veloce (uso da telefono in palestra, tra un set e l'altro).
- **Storico**: reso molto più ricco — confronti, calendario, statistiche avanzate (uso da seduti, dopo l'allenamento, per chi vuole scavare nei dati).

Import Programma non è toccato: resta come nel redesign precedente (`design_handoff_ux_redesign/`).

## About the design files
`CrossFit_Tracker_Redesign_v2.dc.html` è un **riferimento di design in HTML**, un prototipo interattivo con dati finti — non è codice da copiare. Il task è **reimplementare questo comportamento e questo look nell'app Streamlit esistente** (widget nativi + CSS iniettato via `core/theme.py`, come già avviene oggi), non introdurre un frontend separato.

## Fidelity
**High-fidelity** per palette, tipografia e gerarchia (riusa esattamente i token già in `core/theme.py`). Per le viste nuove di Storico (Confronto, Calendario, Statistiche) è **alta fedeltà visiva ma i dati e alcuni dettagli di calcolo sono indicativi** — vanno agganciati alle query reali descritte più sotto.

---

## Analisi UX dell'app esistente

### Punti di forza
1. **Sistema visivo già coerente e maturo**: palette oklch, tipografia Space Grotesk/Helvetica, pillole di stato verde/magenta, badge tipo blocco — tutto centralizzato in `core/theme.py` e riusato ovunque. Non c'è incoerenza visiva tra pagine.
2. **Modello dati solido e già "gym-nerd friendly"**: `LogEntry` traccia carico/reps/RPE per set, split per WOD, formati WOD distinti (AMRAP/EMOM/For Time/...), e `core/calculations.py` stima già il 5RM con Epley+Brzycki corretto per RIR — una base di calcolo migliore di molte app CrossFit commerciali.
3. **Attenzione ai dettagli di interazione**: stepper +/- con step configurabili, editing manuale del carico con tap-to-edit, gestione esplicita di `st.session_state` per sopravvivere ai rerun — è codice maturo, non un MVP.
4. **Deduplica esercizi con fuzzy matching** (`exercise_names.py`): gestisce un problema reale (nomi inseriti a mano che divergono) con una soluzione ragionevole (suggerimenti, mai unificazione automatica silenziosa).
5. **Validazione morbida**: `valida_sets` blocca solo errori hard (RPE fuori range) e avvisa (non blocca) su incongruenze soft (reps senza carico) — buon bilanciamento tra rigore e velocità d'inserimento.

### Punti critici
1. **Troppa navigazione strutturale prima di arrivare all'azione, nel Log**: per loggare un set oggi servi passare da toggle "piano/libero" → select programma → prev/succ giorno → select settimana → select giorno → eventuale espansione "tutti gli allenamenti" → toggle vista Blocchi/Wizard. Sono **6-7 livelli di scelta** prima del primo tap utile. In palestra, con poco tempo tra un set e l'altro, questo è il problema più costoso.
2. **Due viste ridondanti (Blocchi/Wizard) per lo stesso compito**: entrambe fanno la stessa cosa (compilare i set di un blocco); la differenza è solo quanti blocchi sono visibili insieme. Un utente deve *decidere* quale usare invece di essere guidato — la scelta stessa è un costo cognitivo che si somma a ogni sessione.
3. **La sezione "Aggiungi voce senza piano" è isolata in fondo alla pagina**, sempre visibile anche quando non serve (98% delle sessioni sono su piano) — occupa spazio e attenzione per un caso d'uso minoritario.
4. **Impostazioni stepper sempre in cima, sempre espandibili**: è un `st.expander` visibile in ogni caricamento della pagina, per un'impostazione che si tocca una volta ogni tanto.
5. **Storico è tre viste isolate senza possibilità di incrociare i dati**: non si può confrontare due periodi, non c'è vista temporale/calendario che mostri pattern di frequenza, non ci sono statistiche derivate (streak, PR, aderenza, distribuzione RPE) — dati che l'app *ha già* nel DB ma non espone. Per chi vuole analizzare a fondo (target dichiarato "tana del bianconiglio"), oggi manca quasi tutto oltre ai tre grafici base.
6. **Il grafico 1RM mostra un solo esercizio alla volta**: non permette di sovrapporre curve per confrontare progressi relativi tra sollevamenti.
7. **Nessun filtro globale** (intervallo date, tipo blocco) su Storico: ogni tab ricalcola su tutto lo storico disponibile, rendendo impossibile isolare "l'ultimo mese" o "solo strength" senza scorrere manualmente i dati.
8. **Deep-link/contesto perso tra pagine**: il tab "Duplicati esercizi" (manutenzione dati) sta all'interno della stessa pagina "Storico e Progressi" (analisi), mischiando due intenti d'uso molto diversi (uno operativo/una tantum, uno esplorativo/frequente).

---

## Screens / Views

### 1. Log — semplificato
File attuale: `pages/2_Log_Giornaliero.py`

**Principio guida**: un solo flusso, non due modalità. La lista di blocchi si comporta come un accordion a singola apertura: il **primo blocco non ancora fatto è già aperto** all'arrivo sulla pagina (elimina la scelta "Blocchi vs Wizard" — è già focalizzato come il Wizard, ma resti nella stessa lista scrollabile come i Blocchi, quindi puoi comunque sbirciare avanti). Toccare l'header di un altro blocco lo apre e chiude quello corrente.

**Header**: titolo "Log", sottotitolo "Sett. X · Giorno Y · Focus" a sinistra; a destra un **bottone icona "⋯"** che apre un piccolo menu con 2 voci, sostituendo sia l'expander "Tutti gli allenamenti" sia l'expander "Impostazioni stepper" che oggi occupano spazio permanente:
  - "📋 Tutti gli allenamenti" → apre una sotto-schermata con l'elenco di tutti i giorni del programma (tap per saltare), con freccia "←" per tornare.
  - "⚙️ Impostazioni stepper" → apre una sotto-schermata con gli step kg/reps/RPE come chip selezionabili, con freccia "←" per tornare.

**Navigazione data**: riga di 7 pillole giorno (oggi/selezionato in magenta) identica a oggi, ma il vero date-picker per date lontane è dietro un'**icona calendario 📅** a destra della riga (toggle inline, non un `st.expander` sempre presente).

**Barra di progresso**: invariata (barra 8px verde + label "N/M blocchi").

**Card blocco** (per ogni `ProgramBlock`): riga header con badge tipo (STR/CPX/WOD/ACC), nome esercizio, target, pillola di stato ("✓ Fatto" verde / "● Da fare" magenta outline). Tap sulla riga = accordion toggle (chiude qualsiasi altro blocco aperto). Corpo identico a oggi nel comportamento (stepper carico/reps/RPE tap-to-edit per strength/complex; chip formato + campi dinamici per WOD, secondo lo stesso mapping di `core/wod_format.py::campi_visibili`), con due correzioni rispetto al prototipo iniziale:
- **AMRAP**: oltre a "Round completati" mostra anche uno stepper "Rep extra (round incompleto)" — le ripetizioni fatte nell'ultimo round non finito, già previsto da `CAMPI_PER_FORMATO[AMRAP] = {"round", "reps_extra"}` ma mancante nel primo mock.
- **For Time**: non mostra più uno stepper "Reps tot." isolato — mostra invece l'editor **Split / parziali per esercizio** (come già in `st.data_editor` di `pages/2_Log_Giornaliero.py`, qui restilizzato a righe con stepper ±5s): una riga per ciascun parziale con etichetta libera (es. "Thrusters 21", "Pull-up 21") e tempo mm:ss, più "+ Aggiungi parziale". Per un WOD 21-15-9 come Fran sono **6 parziali** (Thruster/Pull-up × 3 round), precompilati nel mock.
- **EMOM**: invariato (round + reps totali) — non c'è altro da tracciare oltre a quello già presente.

**Compilazione set (strength/complex), flusso sequenziale**: non più una tabella con tutte le righe editabili insieme. Le serie già confermate scorrono in cima come righe compatte di sola lettura (✓ · "N" · "kg × reps @ RPE"); sotto compare **una sola riga attiva** con gli stepper kg/reps/RPE (tap-to-edit sul carico come oggi) e un bottone pieno **"✓ Conferma set N"**. Confermare una serie la trasforma in riga compatta e fa comparire la riga attiva successiva sotto. Solo quando **tutte** le serie previste dallo schema (es. 5×5 → 5 serie) sono state confermate compaiono, in coda, i due bottoni "+ Set" (per aggiungerne oltre il piano) e "✓ Segna come fatto" — prima di quel momento nessuno dei due è visibile. Un blocco già fatto, se riaperto per modifica, mostra tutte le serie come già confermate e i due bottoni di coda subito disponibili.

**Voce libera**: non più una sezione separata in fondo alla pagina — è **l'ultima card della stessa lista**, stile tratteggiato, badge "LIBERO", che si espande/collassa come le altre.

**Cosa NON è stato tagliato**: nessuna funzione è stata rimossa. "Tutti gli allenamenti" e "Impostazioni stepper" restano raggiungibili in 2 tap (icona → voce di menu) invece di essere sempre visibili; il toggle piano/libero e la selezione programma restano necessari solo se l'utente ha più programmi importati o vuole loggare senza piano — vanno mantenuti come oggi ma con lo stesso trattamento "nascosti finché non servono" se l'utente ha un solo programma attivo (caso comune): se `programmi` ha un solo elemento, saltare la scelta ed entrare direttamente nel giorno corrente del programma attivo.

### 2. Storico — ricco, "tana del bianconiglio"
File attuale: `pages/3_Storico_Progressi.py`

**Header**: titolo "Storico" + **bottone icona filtro** (⚗) a destra che apre/chiude un pannello con:
  - Chip periodo: 7g / 30g / 90g / Tutto.
  - Chip tipo blocco: Tutti / Strength / Complex / WOD / Accessorio.
  Questi filtri sono **globali**: si applicano a qualunque tab sotto (oggi ogni tab ignora completamente periodo/tipo).

**Selettore vista**: riga di chip orizzontali scrollabile con **6 viste** (oggi erano 3 tab + 1 tab di manutenzione mischiata): **1RM · WOD · Volume · Confronto · Calendario · Statistiche**. "Duplicati esercizi" (manutenzione dati, non analisi) è stato spostato fuori da questa pagina — va in una sezione impostazioni/manutenzione separata, non tra le viste di analisi.

**Tab 1RM**: ora supporta **selezione multipla** di esercizi tracciati (chip toggle, non singola selezione) — il grafico sovrappone una linea per esercizio selezionato, ciascuna con colore proprio (verde/magenta/blu/ambra) e legenda sotto. La card del valore migliore mostra il primo esercizio selezionato come riferimento principale. Permette di rispondere a "la mia panca sta crescendo alla stessa velocità del mio squat?" senza aprire due grafici separati.

**Tab WOD**: invariato nel comportamento (lista sessioni per WOD ripetuto, ultima evidenziata, grafico tempo/round, pacing per split se presente) — beneficia comunque del filtro periodo globale.

**Tab Volume**: invariato (barre settimanali/mensili) — beneficia del filtro periodo/tipo globale.

**Tab Confronto (nuovo)**: due selettori "Periodo A" / "Periodo B" (es. settimane o mesi), colorati verde/magenta per richiamare coerentemente A/B in tutta la vista. Sotto, una tabella di metriche affiancate: Volume totale, Tonnellaggio (per l'esercizio principale tracciato), N. sessioni, RPE medio, PR ottenuti — ogni riga mostra valore A, valore B, e un **delta con segno e colore** (verde se migliora, magenta se peggiora). Risponde direttamente alla richiesta "paragoni di peso" tra due finestre qualsiasi, non solo settimana-vs-settimana-precedente.

**Tab Calendario (nuovo)**: griglia mensile (7 colonne L→D) tipo heatmap GitHub-contributions, intensità del verde proporzionale al volume/frequenza di quel giorno; il giorno selezionato ha bordo magenta. Tap su una cella mostra sotto un riepilogo testuale (esercizi fatti, blocchi completati). Rende visibili a colpo d'occhio pattern di costanza/buchi che oggi non si vedono da nessuna parte nell'app.

**Tab Statistiche (nuovo)**: griglia 2×2 di stat-card (🔥 streak giorni consecutivi, 🏆 PR nel mese, 📊 % aderenza al piano — sessioni fatte / sessioni pianificate, 💪 RPE medio ultimi 30gg) + istogramma di distribuzione RPE (1-10) sugli ultimi 30 giorni, per capire se ci si allena troppo sotto-soglia o troppo vicino al cedimento in modo sistematico.

---

## Interactions & Behavior
- L'accordion del Log ha **una sola card aperta alla volta** (stato `activeBlock`); aprirne una chiude l'altra. Questo sostituisce sia il comportamento "Blocchi" (tutte aperte/collassabili indipendentemente) sia "Wizard" (una alla volta con Prev/Dopo) — qui non serve Prev/Dopo: scorrere la lista *è* la navigazione.
- Il menu "⋯" e il pannello filtri di Storico sono **popover leggeri**: un tap li apre, un secondo tap fuori o sulla stessa icona li chiude. Le due sotto-schermate del Log (Tutti gli allenamenti / Impostazioni) sostituiscono temporaneamente il contenuto principale con un header "← Torna al log", non un vero overlay modale (più semplice da implementare in Streamlit con un flag in `session_state`).
- Selezione multipla esercizi in Storico 1RM: tap aggiunge/rimuove dal confronto; non si può deselezionare l'ultimo esercizio rimasto (il grafico non può restare vuoto).
- I filtri di Storico (periodo/tipo) e le viste Confronto/Calendario/Statistiche leggono le stesse tabelle già interrogate oggi (`LogEntry` + `Log` + join su `ProgramBlock`/`Exercise`) — nessuna modifica allo schema DB richiesta, solo nuove query aggregate:
  - **Streak**: giorni consecutivi con almeno un `Log` che abbia ≥1 `LogEntry` compilata.
  - **PR nel mese**: conteggio di set/entry il cui 1RM stimato (`estimate_1rm`) o risultato WOD supera il massimo storico precedente a quella data, per esercizi tracciati.
  - **Aderenza**: `ProgramDay` con data passata e almeno un log collegato / totale `ProgramDay` con data passata, nel periodo filtrato.
  - **Distribuzione RPE**: istogramma di `LogEntry.rpe` (bucket 1-10) nel periodo filtrato.
  - **Confronto periodi**: stesse aggregazioni di Volume (già in `tab_volume`) e RPE medio, ripetute due volte (periodo A, periodo B) e messe a confronto riga per riga.

## State Management
- `st.session_state.log_active_block`: id del blocco attualmente espanso (o `None`) — sostituisce sia `log_view`/`wizard_index` sia gli `expanded_{id}` indipendenti di oggi.
- Per blocco strength/complex, ogni set in `st.session_state[sets_key]` ha ora anche un flag `confermato: bool` (oltre a `carico_kg`/`reps`/`rpe`), per pilotare il flusso sequenziale: solo le serie confermate + la prima non confermata sono renderizzate.
- `st.session_state.log_screen`: `"main" | "all" | "settings"` — quale contenuto mostrare nella pagina Log (sostituisce i due `st.expander` con vere sotto-schermate).
- `st.session_state.log_menu_open`: bool, stato del popover "⋯".
- `st.session_state.storico_view`: `"1rm" | "wod" | "volume" | "confronto" | "calendario" | "statistiche"`.
- `st.session_state.storico_filter_open`: bool.
- `st.session_state.storico_range`, `storico_tipo`: filtri globali applicati alle query di tutte le viste.
- `st.session_state.storico_1rm_esercizi`: lista (non più stringa singola) di esercizi selezionati per il confronto sovrapposto.
- `st.session_state.storico_compare_a`, `storico_compare_b`: periodo scelto per la vista Confronto.
- `st.session_state.storico_cal_day`: giorno selezionato nel Calendario.
- Dati continuano a venire da `core/db.py` / `core/models.py` — nessuna modifica allo schema richiesta.

## Design Tokens
Riusa **esattamente** i token esistenti in `core/theme.py` — non introdurre nuovi colori:
- Sfondo app `oklch(12% 0.01 265)`, superficie card `oklch(19% 0.015 265)`, superficie hover `oklch(23-28% 0.015 265)`, bordo `oklch(32% 0.02 265)`.
- Testo primario `oklch(97% 0.005 265)`, secondario `oklch(64% 0.02 265)`, terziario `oklch(50% 0.02 265)`.
- Verde (fatto/positivo) `oklch(80% 0.19 152)`, magenta (da fare/attivo/CTA) `oklch(72% 0.23 345)`.
- **Nuovo, solo per il confronto multi-esercizio 1RM**: due colori aggiuntivi con stessa lightness/chroma della palette, hue diverso — blu `oklch(72% 0.15 250)` e ambra `oklch(78% 0.15 80)` — usati esclusivamente come 3ª/4ª serie quando l'utente sceglie di sovrapporre più di 2 esercizi.
- Font titoli/numeri: Space Grotesk 700 (500 per sottotitoli); corpo: Helvetica Neue/Arial/system sans.
- Border radius: card 14-18px, badge/pill 999px, bottoni stepper 8px — invariati.

## Assets
Nessun asset esterno oltre al font Google "Space Grotesk" già in uso.

## Files
- `CrossFit_Tracker_Redesign_v2.dc.html` — prototipo di riferimento (apri in un browser); include tab **Log** e **Storico** ridisegnati.
- `ios-frame.jsx` — bezel iPhone usato solo per la presentazione del prototipo, non fa parte del deliverable di codice.
- Riferimento codice esistente nel repo (da modificare): `pages/2_Log_Giornaliero.py`, `pages/3_Storico_Progressi.py`, `core/theme.py` (eventuali nuovi helper: popover/menu, sotto-schermata, heatmap), `core/calculations.py` (funzioni per streak/PR/aderenza se non già presenti).

# Handoff — Gestore Inni

## Obiettivo
App desktop cross-platform (Mac + Windows) per gestire e proiettare inni durante funzioni religiose. L'operatore usa l'app come pannello di controllo: cerca inni da database PPTX, li prepara negli slot fissi (Apertura/Offertorio/Chiusura), vede il testo in anteprima, fa partire la base musicale, e lancia la presentazione PowerPoint sul secondo schermo.

---

## Stato attuale del codice

### Stack
- **Python 3.12** (installato da python.org — il Python di sistema 3.9 ha Tk 8.5 che non supporta CustomTkinter)
- **CustomTkinter** — UI
- **python-pptx** — lettura testo degli inni dai file PPTX
- **pygame** — riproduzione audio MP3
- **mutagen** — lettura durata file audio

### Struttura file
```
programma inni/
├── main.py                        # entry point
├── core/
│   ├── hymn.py                    # dataclass Hymn (number, title, file_path, slides_text, audio_path)
│   ├── database.py                # scansione cartella PPTX + ricerca file audio abbinato
│   ├── projector.py               # apre PPTX in PowerPoint (open -a su Mac, powerpnt.exe su Win)
│   ├── history.py                 # cronologia con serializzazione {path, number, title}
│   ├── audio.py                   # AudioPlayer con play/pause/stop e callback progresso
│   └── settings.py                # load/save settings.json
├── ui/
│   ├── app.py                     # finestra principale (tutto il layout e la logica UI)
│   └── settings_window.py         # finestra modale impostazioni
├── config/
│   └── settings.json              # persistenza: database, cronologia, slot count, nomi slot, tema
├── database di esempio/           # 6 PPTX di test creati con crea_esempi.py
└── crea_esempi.py                 # script una-tantum per generare i PPTX di esempio
```

### Funzionalità implementate e funzionanti
- **Ricerca full-text** — cerca in numero, titolo e testo di ogni slide; filtro ♩ per inni con base
- **Database multipli persistenti** — cartelle PPTX salvate in settings.json, dropdown sempre popolato al riavvio
- **Slot configurabili** — da 3 a 6, con nomi personalizzabili dalle impostazioni; ogni slot ha: anteprima (clic sul nome), proietta (▶), svuota (✕), assegna selezionato
- **Anteprima testo** — testo diviso per slide con separatori; rimane dopo la proiezione (non si cancella)
- **Player audio integrato** — appare solo quando l'inno ha una base MP3 abbinata (stesso nome, stessa cartella); play/pausa/stop + barra avanzamento + tempo
- **Proiezione** — apre il PPTX in PowerPoint; non cancella slot né anteprima (rimangono finché l'utente non preme ✕)
- **Cronologia persistente** — salvata come lista di dict `{path, number, title}`, sopravvive a riavvii e cambi database; gli inni di altri database appaiono in rosso scuro
- **Pannelli ridimensionabili e nascondibili** — PanedWindow trascinabile; bottoni ◀/▶ collassano il pannello a 30px, freccia per riaprire
- **Impostazioni** — rotellina ⚙ in alto a destra: numero slot, nomi slot, max cronologia, tema

### Come abbinare una base musicale
Metti il file MP3 nella stessa cartella del PPTX con lo stesso nome:
```
001 - Lode a Dio.pptx
001 - Lode a Dio.mp3   ← rilevato automaticamente
```
La ♩ blu appare nella lista; il player compare nell'anteprima.

---

## File attivamente modificati
- `ui/app.py` — il più grande e modificato; contiene tutta la logica UI
- `core/history.py` — aggiornato per serializzare dict invece di soli path
- `core/hymn.py` — aggiunto campo `audio_path`
- `core/database.py` — aggiunta ricerca file audio abbinato (`_find_audio`)
- `core/audio.py` — nuovo, gestisce pygame.mixer
- `config/settings.json` — aggiornato automaticamente dall'app

---

## Tentativi falliti

### Python di sistema (3.9 + Tk 8.5)
CustomTkinter richiede Tk 8.6. Con Python 3.9 di sistema la finestra si apriva completamente nera senza errori visibili. Risolto installando Python 3.12 da python.org.

### Processi Python multipli in background
Durante i test si sono accumulati 4+ processi Python contemporaneamente (ogni rilancio lasciava il precedente in background), causando esaurimento RAM (80 GB). Da ora l'app va avviata manualmente dal terminale, non via subprocess nei test.

### Rimozione pannello dal PanedWindow (`paned.forget()`)
Il primo approccio per "nascondere" un pannello era rimuoverlo dal PanedWindow con `paned.forget()` e ri-aggiungerlo con `paned.add(..., before=...)`. Il pannello una volta rimosso non tornava più. Risolto tenendolo sempre nel PanedWindow e collassandolo a 30px con `sash_place()` + `grid_remove()` del contenuto.

### `_show_preview(None)` nascondeva il player
La funzione di pulizia anteprima chiamava `_show_player(False)`, quindi dopo ogni proiezione il player spariva. Risolto rimuovendo quella chiamata: il player ora persiste fino a quando non si seleziona un nuovo inno senza base.

### `grid_rowconfigure(1, weight=1)` sulla riga del player
Causava uno spazio vuoto fisso nell'anteprima anche quando il player era nascosto. Rimosso: solo la riga del testo (row=2) ha `weight=1`.

### `_view_slot` non aggiornava il player
Cliccando uno slot per vedere l'anteprima, il player mostrava ancora la base dell'inno precedente. `_view_slot` chiamava solo `_show_preview` senza toccare `_audio_player`. Risolto aggiungendo la stessa logica audio di `_select_hymn`.

---

## Prossimi passi suggeriti

1. **Design UI** — l'utente vuole ridisegnare l'interfaccia in Claude Design in una sessione separata. Il codice è già strutturato in modo da rendere i colori e i font facilmente modificabili (costanti `ACCENT`, `SLOT_COLORS` in cima ad `app.py`).

2. **Avanzamento barra audio con clic** — la barra di avanzamento è solo visiva; si potrebbe rendere cliccabile per fare seek nella traccia (richiede `pygame.mixer.music.set_pos()`).

3. **Packaging** — creare un eseguibile standalone con PyInstaller per distribuire senza richiedere Python installato:
   ```bash
   python3.12 -m pip install pyinstaller
   pyinstaller --onefile --windowed main.py
   ```
   Da testare su Windows (potrebbe richiedere aggiustamenti al `projector.py`).

4. **Gestione database** — attualmente si possono solo aggiungere cartelle; manca un modo per rimuoverne una dal dropdown dalle impostazioni.

5. **Indicatore "già proiettato"** — l'utente non ha un feedback visivo su quale slot è già stato proiettato in questa sessione. Si potrebbe aggiungere un bordo o colore diverso dopo la proiezione.

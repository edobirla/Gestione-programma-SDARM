# Contesto per revisione design — "Programma Servizio"

## Cos'è l'app
App desktop (Mac + Windows) che gestisce l'intero culto della Chiesa Avventista da un
pannello di controllo unico: inni, versetti biblici, presentazioni (PDF/PPTX), video,
timer di pausa, musica di sottofondo, campanello, QR offerta, richieste di preghiera.
L'operatore prepara la scaletta la mattina stessa e durante il culto proietta tutto su
un secondo schermo (TV/monitor in chiesa), senza mai dover toccare lo schermo proiettato.

## Vincoli tecnici (importante — le proposte devono essere realizzabili con questi)
- Scritta in Python con **customtkinter**, non è un'app web: niente CSS, niente ombre/blur/
  gradienti arbitrari, niente animazioni complesse. Si può lavorare con: colori pieni
  (con coppie separate per tema chiaro/scuro), `corner_radius`, `border_width`, un set
  limitato di font, stati hover di base.
- Deve funzionare **identica su Mac e Windows**.

## Chi la usa
Un solo operatore, spesso non particolarmente esperto di tecnologia, seduto in fondo
alla sala durante il culto dal vivo. Priorità: chiarezza sopra tutto, non perdere mai
il filo di cosa viene dopo, zero rischio di azioni accidentali irreversibili durante
il culto.

## Linguaggio visivo attuale
- Tema scuro di default (con opzione chiaro/sistema)
- Colore accento blu (#2563eb)
- Card piatte con leggere tinte di sfondo, nessuna ombra
- Icone minimali (niente emoji colorate, solo simboli Unicode semplici)
- Testo dell'interfaccia in italiano

## Cosa serve dalla revisione

- **Tipo di feedback cercato:** tutto — critica generale di coerenza visiva, audit di
  consistenza tra le schermate (colori/spaziature/font non uniformi), proposte di
  redesign per schermate specifiche, e feedback mirato su gerarchia visiva/leggibilità
  per l'uso dal vivo durante il culto, a distanza.
- **Schermata che convince meno:** nessuna in particolare — **tutte le schermate
  vanno ridisegnate e rifatte in modo più moderno ed elegante**. Non è un problema
  localizzato a una schermata, è un redesign complessivo del linguaggio visivo.
- **Riferimento visivo:** nessuno specifico — libertà di proporre entro i vincoli
  tecnici sopra (customtkinter, niente CSS/ombre/gradienti/animazioni complesse).
- **Ampiezza dei cambiamenti accettati:** ampia — l'utente è aperto anche a
  riorganizzare il layout delle schermate, non solo rifiniture di colori/spaziature.

## Schermate incluse (cartella `screenshot app/`)
Le 35 schermate sono organizzate e numerate in ordine di percorso nell'app:

1. `01-scaletta-vista-principale.png` — vista principale: scaletta a sinistra,
   pannello dettaglio al centro (vuoto), pannello "in riproduzione" a destra
2. `02-scaletta-dettaglio-video.png` — scaletta con uno slot Video selezionato
3. `03-dettaglio-video-vuoto.png` — dettaglio Video prima di proiettare
4. `04-dettaglio-audio-player.png` — dettaglio Audio con barra di riproduzione
   trascinabile
5. `05-dettaglio-documento.png` — dettaglio Documento
6. `06-dettaglio-inno-testo.png` — dettaglio Inno con testo/liriche
7. `07-dettaglio-presentazione.png` — dettaglio Presentazione (PDF/PPTX)
8. `08-dettaglio-timer.png` — dettaglio Timer (countdown + preset minuti)
9. `09-modale-aggiungi-elemento.png` — modale "Aggiungi a «Culto»" (scelta tipo
   elemento)
10. `10-dettaglio-preghiere-slot.png` — dettaglio slot Preghiere nella scaletta
11. `11-dettaglio-testo-libero.png` — dettaglio Testo libero
12. `12-libreria-inni-lista.png` — Libreria Inni, elenco ricercabile
13. `13-bibbia-libri.png` — Bibbia, navigazione libri
14. `14-bibbia-capitoli.png` — Bibbia, navigazione capitoli
15. `15-bibbia-versetti.png` — Bibbia, elenco versetti con pulsanti Proietta
16. `16-bibbia-cronologia-versetti.png` — Bibbia, cronologia versetti usati
17. `17-libreria-inni-cronologia.png` — Libreria Inni, cronologia inni usati
18. `18-libreria-inni-anteprima.png` — Libreria Inni, risultati con anteprima
    laterale del testo
19. `19-preghiere-elenco.png` — Preghiere, elenco richieste
20. `20-modale-modifica-preghiera.png` — modale di modifica di una richiesta di
    preghiera
21. `21-media-youtube-pausa.png` — Media: download YouTube + musica di
    sottofondo pausa
22. `22-impostazioni-generale.png` — Impostazioni → Generale
23. `23-impostazioni-inni.png` — Impostazioni → Inni (cartelle database)
24. `24-impostazioni-bibbia-anteprima.png` — Impostazioni → Bibbia, con
    l'anteprima live trascinabile/ridimensionabile per la proiezione versetti
    (caratteristica particolare, utile mostrarla)
25. `25-impostazioni-timer.png` — Impostazioni → Timer (attualmente dietro un
    pulsante che apre un'altra finestra — da rivedere, vedi HANDOFF.md)
26. `26-impostazioni-pausa.png` — Impostazioni → Pausa (musica di sottofondo)
27. `27-impostazioni-offerta.png` — Impostazioni → Offerta (QR)
28. `28-impostazioni-sfondo.png` — Impostazioni → Sfondo
29. `29-impostazioni-lezione.png` — Impostazioni → Lezione (Scuola del Sabato)
30. `30-impostazioni-campanello.png` — Impostazioni → Campanello
31. `31-impostazioni-youtube.png` — Impostazioni → YouTube (cartella download)
32. `32-impostazioni-cronologia.png` — Impostazioni → Cronologia (pulizia dati)
33. `33-libreria-inni-base-musicale.png` — Libreria Inni con base musicale in
    anteprima (barra di riproduzione)
34. `34-scaletta-dettaglio-inno-player.png` — scaletta con Inno selezionato,
    player base musicale nel pannello centrale, pannello destro con campanello
    e comandi rapidi
35. `35-dettaglio-lezione.png` — dettaglio slot Lezione (Scuola del Sabato):
    selettore lezione, selettore rapido per giorno ("Vai a"), domanda corrente
    con Precedente/Successiva, anteprima dei versetti citati (con testo
    biblico) e della nota, ciascuno con proprio pulsante Proietta

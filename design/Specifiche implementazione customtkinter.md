# Specifiche di implementazione — Redesign "Programma Servizio"

Riferimento vivo: apri `Redesign.dc.html` in qualunque momento per vedere/zoomare
ogni schermata — è il mockup di riferimento definitivo, queste sono le misure
concrete da tradurre in codice.

## Palette — tema scuro (default)

| Ruolo | Hex |
|---|---|
| Sfondo pagina | `#06070a` |
| Superficie 1 — card | `#0b0d12` |
| Superficie 2 — riga/card interna | `#111419` |
| Superficie 3 — bottone secondario | `#15181e` |
| Superficie 4 — bottone/riga attiva | `#1c1f25` |
| Bordo | `#25292f` |
| Bordo tenue | `#21242a` |
| Testo primario | `#f0f2f4` |
| Testo secondario | `#cbced2` |
| Testo terziario | `#8c8f95` |
| Testo etichetta (maiuscolo) | `#6e7278` |
| Testo tenue | `#4f5358` |
| Accento (blu) | `#2b6dd3` |
| Accento hover | `#478af1` |
| Errore/danger | `#c74b47` |

## Palette — tema chiaro

| Ruolo | Hex |
|---|---|
| Sfondo pagina | `#e5e8ed` |
| Superficie 1 — card | `#dadee5` |
| Superficie 2 — riga/card interna | `#d0d4dc` |
| Superficie 3 — bottone secondario | `#c9ced6` |
| Superficie 4 — bottone/riga attiva | `#c0c4cc` |
| Bordo | `#b3b8bf` |
| Bordo tenue | `#b9bec6` |
| Testo primario | `#030304` |
| Testo secondario | `#17181b` |
| Testo terziario | `#474b50` |
| Testo etichetta (maiuscolo) | `#63666c` |
| Testo tenue | `#83868c` |
| Accento, errore | *stessi valori del tema scuro* — l'accento non cambia tra i due temi |

## Colori per categoria elemento
Stessa luminosità/chroma, hue diverso — usati SOLO su etichette/icone/puntini, mai come sfondo pieno di intere card.

| Categoria | Hex |
|---|---|
| Inno (viola) | `#888dec` |
| Video (blu) | `#6198ee` |
| Audio (verde acqua) | `#12b382` |
| Versetto (ambra) | `#de7949` |
| Lezione (verde) | `#5aae5f` |
| Presentazione (ciano) | `#00b1ba` |
| Timer (arancio) | `#e38d3d` |
| Documento (grigio) | `#8f9298` |
| Preghiere (rosa) | `#ee7c90` |
| Testo libero (magenta) | `#cb86db` |

## Tipografia
- Famiglia: **Inter** (bundlare i file .ttf con l'app per garantire coerenza Mac/Windows — CTkFont non garantisce Inter di sistema).
- Titolo schermata: 26px / peso 700
- Titolo sezione: 16–24px / peso 600–700
- Testo corrente: 14–15px / peso 400–500
- Etichetta maiuscola (categoria, sezioni): 10–11px / peso 700 / letter-spacing ~0.06–0.08em

## Forme e spaziature
- `corner_radius`: 6–10px per bottoni/righe, 10–14px per card e modali, pillole (border_width 1) per badge/stato.
- `border_width`: 1px per bordi card/tab non attivi; 2px per contenitori con focus/attivi (es. anteprima trascinabile).
- Padding card: 24–30px; padding riga lista: 9–14px.
- Icone: 15–18px nella barra laterale/badge, 20–30px nelle icone grandi (fondamenta, modale "Aggiungi").

## Componenti chiave e loro stato
- **Riga scaletta**: icona categoria (colore categoria) + testo colorato categoria in alto, titolo elemento in bianco/nero sotto, pallino di stato a destra (contorno = non proiettato, verde pieno = proiettato), matita/X per modifica/rimozione.
- **Card attiva/selezionata**: sfondo = accento al 16% di opacità + bordo 1px accento pieno (mai riempimento accento a piena opacità su un'intera card).
- **Bottone primario**: sfondo accento pieno, testo bianco.
- **Bottone secondario**: superficie 3, testo secondario.
- **Azione distruttiva**: sfondo/bordo rosso (`#c74b47` derivati), mai lo stesso rosso del tasto "Azzera" generico.

## Le 3 icone nuove (Inno / Bibbia / Preghiera)
Disegnate come icone lineari (stroke, non riempite), coerenti con il resto del set:
- **Inno**: lira/arpa stilizzata (sostituisce la nota musicale).
- **Bibbia**: libro aperto con dorso centrale.
- **Preghiera**: mani giunte con dita separate (sostituisce il cuore, usato ora solo per "Preghiere" come icona di categoria/tipo — vedi 1a in Redesign.dc.html per l'SVG esatto).

Gli SVG sorgente di tutte le icone sono nel file `Redesign.dc.html` — copiabili direttamente (path coordinates in viewBox 24×24).

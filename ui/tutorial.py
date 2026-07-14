"""First-run / on-demand walkthrough — a paged welcome card.

Shown automatically the first time the app is ever started (settings key
"tutorial_seen") and re-openable any time from Impostazioni → Generale →
«Rivedi il tutorial». It's a full-window overlay placed on the root window
(covering the nav rail too, deliberately — it's a focused welcome moment,
and blocking navigation keeps the overlay from being orphaned by a view
switch), with the same visual language as the rest of the operator UI.

Keyboard: ← → move between pages, Esc closes. The root window's own
Right/Left/Ctrl+1-3 bindings are temporarily replaced while the overlay is
open and restored via app._bind_global_keys() on close.
"""
import customtkinter as ctk

from ui import theme
from ui.theme import (ACCENT, ACCENT_HOVER, BORDER, BTN_SECONDARY,
                      BTN_SECONDARY_HOVER, CARD, CARD_ROW, SLOT_COLORS,
                      SURFACE_3, TEXT_LABEL, TEXT_PRIMARY, TEXT_SECONDARY,
                      TEXT_TERTIARY)

# (icon_name, icon_variant, title, subtitle, [(bullet_color, text), ...])
_PAGES = [
    ("scaletta", "muted", "Benvenuto in Gestione programma SDARM",
     "L'app che gestisce l'intero servizio di culto da un unico pannello: "
     "inni, versetti, lezione, timer e media, proiettati sul secondo schermo.",
     [(ACCENT, "A sinistra trovi le sei aree: Scaletta, Inni, Bibbia, "
               "Preghiere, Media e Impostazioni."),
      (SLOT_COLORS["lezione"], "Il computer mostra i comandi; il proiettore "
                               "mostra solo il contenuto per la congregazione."),
      (SLOT_COLORS["timer"], "Questo tutorial dura un minuto — lo ritrovi "
                             "quando vuoi in Impostazioni → Generale.")]),

    ("scaletta", "muted", "La scaletta del servizio",
     "Il cuore dell'app: prepari qui, in ordine, tutto quello che verrà "
     "proiettato durante il culto.",
     [(SLOT_COLORS["inno"], "Crea le sezioni (Scuola del Sabato, Culto…) e "
                            "aggiungi elementi con ＋: inni, versetti, timer, video…"),
      (SLOT_COLORS["versetto"], "Trascina con ⠿ per riordinare; doppio clic "
                                "per rinominare."),
      (SLOT_COLORS["lezione"], "«Salva» memorizza la scaletta come modello: "
                               "la ricarichi ogni settimana con «Carica»."),
      (ACCENT, "Clicca un elemento per vederne dettagli e comandi al centro.")]),

    ("inno", "category", "Inni",
     "Il tuo innario in PowerPoint, cercabile all'istante.",
     [(SLOT_COLORS["inno"], "In Impostazioni → Inni aggiungi la cartella con "
                            "i file PPTX (es. «001 - Titolo.pptx»)."),
      (ACCENT, "Cerca per numero, titolo o testo — gli accenti vengono ignorati."),
      (SLOT_COLORS["audio"], "Un file audio con lo stesso nome del PPTX "
                             "diventa la base musicale ♪."),
      (SLOT_COLORS["presentazione"], "«Proietta» avvia la presentazione "
                                     "PowerPoint sul secondo schermo.")]),

    ("bibbia", "muted", "Bibbia",
     "Cinque bibbie incluse: Italiano, Română, Español, English, Português.",
     [(SLOT_COLORS["versetto"], "Naviga per libro → capitolo → versetto, "
                                "oppure cerca direttamente il testo."),
      (ACCENT, "Puoi proiettare più lingue insieme: scegli quelle da "
               "affiancare al testo principale."),
      (SLOT_COLORS["lezione"], "Con un versetto in proiezione, le frecce "
                               "← → passano al precedente/successivo."),
      (SLOT_COLORS["timer"], "Altre versioni si importano da file .bib in "
                             "Impostazioni → Bibbia.")]),

    ("lezione", "category", "Lezione (Scuola del Sabato)",
     "Carica il trimestre una volta: l'app trova da sola la lezione di oggi.",
     [(SLOT_COLORS["lezione"], "In Impostazioni → Lezione carichi il file "
                               "JSON del trimestre."),
      (SLOT_COLORS["versetto"], "Proietti domande, note e versetti citati, "
                                "navigando giorno per giorno."),
      (ACCENT, "Template grafici, colori e riquadri di testo si personalizzano "
               "in Impostazioni → Lezione.")]),

    ("presentazione", "category", "Proiezione e comandi rapidi",
     "Tutto quello che serve durante il servizio, senza toccare il proiettore.",
     [(ACCENT, "La proiezione va sul secondo schermo automaticamente "
               "(configurabile in Impostazioni → Generale)."),
      (SLOT_COLORS["timer"], "Nero / Sfondo / Congela: Ctrl+1, Ctrl+2, Ctrl+3 "
                             "oppure i pulsanti nel pannello destro."),
      (SLOT_COLORS["versetto"], "PagSù/PagGiù e le frecce comandano diapositive "
                                "e versetti — funziona anche col telecomando."),
      (SLOT_COLORS["audio"], "Timer con avviso sonoro e musica di pausa: nel "
                             "pannello dell'elemento Timer.")]),

    ("impostazioni", "muted", "Pronti!",
     "Qualche ultima cosa utile, poi tocca a te.",
     [(SLOT_COLORS["preghiera"], "Le Preghiere hanno la loro sezione: aggiungi "
                                 "richieste e proiettale singole o in elenco."),
      (SLOT_COLORS["video"], "Da Media scarichi audio e video da YouTube "
                             "nella cartella che preferisci."),
      (ACCENT, "In Impostazioni personalizzi colori, font, sfondi, campanello "
               "e immagine dell'offerta."),
      (SLOT_COLORS["lezione"], "Rivedi questo tutorial quando vuoi: "
                               "Impostazioni → Generale.")]),
]


class TutorialOverlay(ctk.CTkFrame):
    def __init__(self, app, on_close=None):
        super().__init__(app, fg_color=theme.BG, corner_radius=0)
        self._app = app
        self._on_close = on_close
        self._page = 0
        self._closed = False
        self.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._card = ctk.CTkFrame(self, width=640, height=520, corner_radius=16,
                                  fg_color=CARD, border_width=1, border_color=BORDER)
        self._card.place(relx=0.5, rely=0.5, anchor="center")
        self._card.pack_propagate(False)

        # Temporarily take over the root-level key bindings (bind() replaces);
        # close() restores the app's own via app._bind_global_keys().
        app.bind("<Escape>", lambda e: self.close())
        app.bind("<Right>", lambda e: self._go(1))
        app.bind("<Left>", lambda e: self._go(-1))
        self._render()

    def _go(self, delta: int):
        new = self._page + delta
        if new >= len(_PAGES):
            self.close()
            return
        if 0 <= new < len(_PAGES):
            self._page = new
            self._render()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._app.unbind("<Escape>")
            self._app._bind_global_keys()  # restore Right/Left/PgUp/PgDn/Ctrl+1-3
        except Exception:
            pass
        try:
            self.place_forget()
            self.destroy()
        except Exception:
            pass
        if self._on_close:
            try:
                self._on_close()
            except Exception:
                pass

    def _render(self):
        for w in self._card.winfo_children():
            w.destroy()
        icon_name, icon_variant, title, subtitle, rows = _PAGES[self._page]
        n = len(_PAGES)
        last = self._page == n - 1

        body = ctk.CTkFrame(self._card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=(24, 20))

        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=f"TUTORIAL · {self._page + 1} DI {n}",
                     font=theme.font_label(11), text_color=TEXT_LABEL).pack(side="left")
        ctk.CTkButton(head, text="Salta ✕", width=70, height=24, corner_radius=10,
                      fg_color="transparent", text_color=TEXT_TERTIARY,
                      hover_color=SURFACE_3, font=theme.font_body(12),
                      command=self.close).pack(side="right")

        title_row = ctk.CTkFrame(body, fg_color="transparent")
        title_row.pack(fill="x", pady=(14, 0))
        icon_img = theme.icon(icon_name, icon_variant, size=18)
        if icon_img is not None:
            badge = ctk.CTkFrame(title_row, width=34, height=34, corner_radius=17,
                                 fg_color=SURFACE_3)
            badge.grid_propagate(False)
            badge.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(badge, text="", image=icon_img).place(relx=0.5, rely=0.5,
                                                               anchor="center")
        ctk.CTkLabel(title_row, text=title, font=theme.font_section(21),
                     text_color=TEXT_PRIMARY, anchor="w", justify="left",
                     wraplength=500).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(body, text=subtitle, font=theme.font_body(13),
                     text_color=TEXT_TERTIARY, anchor="w", justify="left",
                     wraplength=560).pack(fill="x", pady=(8, 14))

        for color, text in rows:
            row = ctk.CTkFrame(body, fg_color=CARD_ROW, corner_radius=12)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text="●", text_color=color, width=26,
                         font=("", 12)).pack(side="left", padx=(10, 0), pady=10)
            ctk.CTkLabel(row, text=text, font=theme.font_body(13),
                         text_color=TEXT_SECONDARY, anchor="w", justify="left",
                         wraplength=500).pack(side="left", fill="x", expand=True,
                                              padx=(4, 12), pady=10)

        footer = ctk.CTkFrame(self._card, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=30, pady=(0, 22))
        dots = ctk.CTkFrame(footer, fg_color="transparent")
        dots.pack(side="left")
        for i in range(n):
            on = i == self._page
            dot = ctk.CTkFrame(dots, width=18 if on else 7, height=7, corner_radius=4,
                               fg_color=ACCENT if on else BORDER)
            dot.pack(side="left", padx=3)
            dot.pack_propagate(False)

        btns = ctk.CTkFrame(footer, fg_color="transparent")
        btns.pack(side="right")
        if self._page > 0:
            ctk.CTkButton(btns, text="‹ Indietro", width=100, height=34,
                          corner_radius=12, fg_color=BTN_SECONDARY,
                          hover_color=BTN_SECONDARY_HOVER, text_color=TEXT_SECONDARY,
                          font=theme.font_body(13, bold=True),
                          command=lambda: self._go(-1)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Inizia! ✓" if last else "Avanti ›", width=110,
                      height=34, corner_radius=12, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, font=theme.font_body(13, bold=True),
                      command=lambda: self._go(1)).pack(side="left")

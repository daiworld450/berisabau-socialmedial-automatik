# Einwilligungen: Handprüfung statt Codesperre

**Der wichtigste Satz zuerst.** Die technische Sperre ist am 01.09.2026 auf
Wunsch des Inhabers aus dem Code geflogen (Commit `f068b5a`). Das bleibt so.
Modul `src/einwilligung.py`, der Filter in `planer._bilder()`/`_videos()` und
die Freigabeliste `content/medien/freigabe.json` existieren nicht mehr. Der
Planer wählt jedes Motiv aus `content/medien/`, egal was hier eingetragen ist.

**Wer prüft jetzt?** Ein Mensch. Wer die Telegram-Freigabe für einen Beitrag
erteilt, entscheidet in dem Moment auch, ob der Kunde diesem Foto zugestimmt
hat. Ohne diesen Blick geht das Motiv raus.

**Trotzdem Pflicht.** Als Handwerker in einer fremden Wohnung zu arbeiten ist
keine Erlaubnis, sie zu zeigen. Das Einverständnis des Kunden bleibt nötig,
auch ohne Programm dahinter.

## Was hier liegt

| Datei | Zweck |
|---|---|
| `VORLAGE-WHATSAPP.md` | Fertiger Text, um den Kunden zu fragen, dazu die Regel, was aus dem Bild muss |
| `verwalten.py` | Register führen, Lage anzeigen, Einwilligung eintragen |
| `EINWILLIGUNG-EINTRAGEN.command` | Doppelklick-Start für `verwalten.py` |

Diese drei Dateien sind Werkzeug und Textvorlage. Kundendaten stehen in keiner
davon.

**Veralteter Text in den Dateien.** `EINWILLIGUNG-EINTRAGEN.command` behauptet,
ein Foto ohne Eintrag bleibe gesperrt. `verwalten.py` schreibt weiterhin
`content/medien/freigabe.json`. Beides stammt aus der Zeit der Codesperre und
stimmt seit dem 01.09. nicht mehr. Der Eintrag hier ist eine Notiz für den
Menschen an der Telegram-Freigabe.

## Was lokal bleibt

- `register.json` — Kundenname, Objekt, Datum, Nachweis
- `nachweise/` — Screenshots aus privaten Chats

Beides sperrt `.gitignore`, in `berisabau-social/.gitignore` und im
Wurzel-`.gitignore` mit Präfix. Geprüft am 01.09.2026 mit `git check-ignore`.
Wer eine dieser Sperren aufhebt, veröffentlicht Kundendaten in ein öffentliches
Repo.

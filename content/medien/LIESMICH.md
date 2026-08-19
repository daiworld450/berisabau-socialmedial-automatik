# Baustellenfotos ablegen

Hier kommen Ihre eigenen Fotos rein. Alles andere macht das System allein.
Ohne Fotos läuft es trotzdem weiter – dann kommen an den Foto-Terminen
automatisch Text-Posts. Gepostet wird zweimal pro Woche (Dienstag und
Donnerstag, siehe `content/themen.json` -> `posttage`).

Zwei Wege, Fotos abzulegen – je nachdem, wie viel Aufwand Sie investieren
wollen:

## Ordner `eingang/` – einfach reinwerfen, fertig

Der bequeme Weg für den Alltag. Fotos direkt vom Handy hier ablegen, egal
wie sie heißen, egal ob quer oder hochkant fotografiert:

```
eingang/
  IMG_4821.jpg
  Baustelle Dienstag.jpg
  WhatsApp Bild 2026-08-19.jpg
```

Vor jedem Post-Lauf sichtet das System diesen Ordner selbst:

```bash
python src/main.py fotos-verarbeiten
```

Was dabei passiert – Bearbeitung, keine Erzeugung:

- **Ausrichtung** aus den Handydaten korrigiert (nicht mehr seitlich verdreht)
- **Belichtung und Kontrast** mild angeglichen, keine Filter
- **Leichte Schärfung**, wie sie jedes Foto vom Handy ohnehin braucht

Das bearbeitete Foto landet in `pool/` und ist danach ganz normal für die
Säulen „Detail" und „Mensch" verfügbar. Das Original bleibt unangetastet in
`eingang/verarbeitet/` liegen – nichts geht verloren.

**Kein KI-Bild ersetzt oder ergänzt ein Foto.** Es wird ausschließlich das
bearbeitet, was tatsächlich fotografiert wurde – alles andere wäre nach
Regel 1 im Content-Prompt Wettbewerbsbetrug.

## Ordner `projekte/` – ein Ordner je Bauvorhaben, für Vorher/Nachher und Carousels

Etwas mehr Aufwand, dafür mehr Wirkung: für Vorher/Nachher-Vergleiche und
Wisch-Carousels müssen die Fotos einem Projekt zugeordnet und benannt sein.

```
projekte/
  bad-heiermannstr/
     nachher.jpg         <- kommt zuerst, ist die sichtbare Kachel
     detail-1.jpg        <- weitere Fotos, frei benennbar
     detail-2.jpg
     vorher.jpg          <- kommt zuletzt im Carousel
     rundgang.mp4        <- optional: Video
     info.json           <- optional, aber empfohlen
```

**Was der Planer daraus macht – automatisch, nach dieser Reihenfolge:**

| Im Ordner liegt | Daraus wird |
|---|---|
| ein Video (`.mp4`, `.mov`) | **Reel** – Titelbild gebrandet, Video unverändert |
| zwei oder mehr Fotos | **Carousel** zum Wischen, bis zu 10 Slides |
| ein Foto | Einzelbild |
| `vorher` **und** `nachher` | zusätzlich ein Vorher/Nachher-Post am Mi oder Fr |

Die Dateinamen steuern die Reihenfolge: `nachher…` kommt zuerst (das ist die
Kachel, die im Profil zu sehen ist), `vorher…` zuletzt, alles andere dazwischen
alphabetisch.

Endungen für Bilder: `.jpg`, `.jpeg`, `.png`, `.webp` · für Videos: `.mp4`, `.mov`.

### Videos

- **Hochformat 9:16**, mindestens 720p, H.264 mit AAC-Ton.
- **3 bis 90 Sekunden.** Kürzer wird selten zu Ende gesehen, länger selten
  überhaupt gestartet.
- Ein `cover.jpg` oder `nachher.jpg` im selben Ordner wird als Titelbild
  verwendet und im Rasterlayout gebrandet.
- Instagram lädt das Video selbst herunter und transkodiert es. Das dauert
  bis zu fünf Minuten – der Workflow wartet entsprechend.

### `info.json` – so wird der Post gut

```json
{
  "titel": "Bad in zwei Wochen",
  "gewerk": "Badsanierung",
  "titel_vor": "Bad in ",
  "titel_stark": "zwei Wochen",
  "titel_nach": ".",
  "lead": "Alte Fliesen raus, neue Abdichtung, bodengleiche Dusche in Betonoptik.",
  "dauer": "14 Tage",
  "ort": "Mülheim a. d. Ruhr",
  "details": ["Großformat 60×120", "Bodengleiche Dusche", "Feinmontage inklusive"],
  "hashtags": "bad",
  "caption": "Optionaler eigener Text unter dem Bild."
}
```

`titel_stark` ist der Teil, der den roten Schrägstrich bekommt.
`hashtags` wählt das Set aus `content/hashtags.json`:
`bad`, `fliesen`, `maler`, `mikrozement`, `sanierung`, `smarthome`, `allgemein`.

Fehlt die `info.json`, wird der Ordnername als Titel benutzt.

## Ordner `pool/` – einzelne gute Fotos ohne Projektzuordnung

Einfach Bilder hineinlegen. Sie werden für „Aus der Werkstatt"-Posts genutzt,
wenn kein Projektordner an der Reihe ist.

## Foto-Regeln aus der Praxis

- **Hochformat 4:5 oder 9:16.** Querformat wird beschnitten.
- **Mindestens 1080 px breit**, besser 1440 px.
- **Vorher und Nachher aus demselben Blickwinkel** – das ist der ganze Effekt.
- **Aufgeräumt fotografieren.** Werkzeug, Kabel und Kaffeebecher raus.
- **Keine Personen ohne Einwilligung**, keine erkennbaren Kundendaten
  (Namensschilder, Post, Türschilder).
- **Sperrfrist:** ein Motiv erscheint frühestens nach 30 Tagen wieder.
  Fünf bis sechs Projektordner reichen für ein ganzes Jahr ohne Wiederholung.

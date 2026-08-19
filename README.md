# Berisa Bau – Instagram- und Facebook-Automatik

Erzeugt zweimal pro Woche (Dienstag und Donnerstag) einen Beitrag im Design
von berisabau.de und veröffentlicht ihn auf
[@berisabau](https://instagram.com/berisabau) sowie auf
[facebook.com/BerisaBau](https://facebook.com/BerisaBau).

**Kosten: 0 €.** Offizielle APIs von Instagram und Facebook, GitHub Actions
als Zeitgeber, GitHub Pages als Bildablage, Rendering lokal per Chromium,
Fotobearbeitung lokal per Pillow. Keine Abo-Dienste, keine Zwischenanbieter,
keine KI-Kosten – KI-Textpolitur ist zuschaltbar, aber nicht nötig.

**Warum Dienstag/Donnerstag und diese Uhrzeit:** recherchiert, nicht
geraten. Sprout Social und Hootsuite werten dafür 2026 jeweils
mehrere Hunderttausend Profile bzw. über eine Million Beiträge aus – beide
nennen Dienstag/Donnerstag unter den stärksten Wochentagen, mit dem
höchsten B2C-Engagement abends außerhalb der Arbeitszeit. Änderbar über
`posttage` in `content/themen.json` und die Uhrzeit im GitHub-Workflow.
[Quelle Sprout Social](https://sproutsocial.com/insights/best-times-to-post-on-instagram/) ·
[Quelle Hootsuite](https://blog.hootsuite.com/best-time-to-post-on-instagram/)

---

## In drei Minuten ausprobieren

```bash
pip install -r requirements.txt
python -m playwright install chromium
python src/main.py muster
```

Danach liegen in `out/muster/` sechs Beispielbilder – eins je Rubrik.

Nächste 14 Tage anschauen:

```bash
python src/main.py vorschau --tage 14
```

Den heutigen Beitrag erzeugen, **ohne** ihn zu posten:

```bash
python src/main.py heute
```

Bild und Text landen in `out/`. Zum Prüfen, bevor irgendetwas live geht.

---

## Wie es funktioniert

```
Eingang/  ──▶ Fotobearbeitung ──▶ Pool
                                    │
Di + Do  ──▶ Planer ──▶ Vorlage + Themenbank ──▶ Chromium ──▶ JPEG 1080×1350
   18:30       │                                                    │
               └──▶ Texter ──▶ Bildunterschrift + Hashtags ──────────┤
                                                                     ▼
                                    GitHub Pages ──▶ Instagram Graph API
                                                  └─▶ Facebook Graph API
```

**Posttage:** Dienstag und Donnerstag, 18:30 Uhr – siehe die Begründung
oben. Welche Säule an der Reihe ist, rotiert über die tatsächlichen
Post-Termine (nicht über Kalendertage), gewichtet nach dem Zielverhältnis
aus [`content/CONTENT-PROMPT.md`](content/CONTENT-PROMPT.md):

| Säule | Zielanteil | Braucht Medien |
|---|---|---|
| Vorher / Nachher | 30 % | ja |
| Detail | 25 % | ja |
| Wissen | 25 % | nein |
| Fehler | 10 % | nein |
| Mensch | 10 % | ja |

Fehlt für eine Foto-Säule Material, weicht der Planer auf eine Textsäule
aus – rotierend, damit nie zweimal dieselbe Säule hintereinander läuft.
**Der Kalender reißt nie ab, auch wenn wochenlang nichts nachgelegt wird.**

Ein Thema kommt frühestens nach 30 Tagen wieder. Aktuell sind
**71 Themen** hinterlegt, dazu drei fertige Carousels. Beides in
`content/themen.json` änderbar, inklusive `posttage` und `rotation`.

---

## Fotos einfach reinwerfen

```bash
python src/main.py fotos-verarbeiten
```

Fotos landen roh in `content/medien/eingang/` – egal wie benannt, egal ob
quer oder hochkant. Das System richtet sie aus, gleicht Kontrast und
Belichtung mild an und schärft nach; danach liegen sie fertig im `pool/`
für die Säulen „Detail" und „Mensch". Das Original bleibt unangetastet in
`eingang/verarbeitet/`.

**Bearbeitet wird, nicht erzeugt.** Kein KI-Bild ersetzt ein echtes Foto –
das wäre nach Regel 1 im Content-Prompt Wettbewerbsbetrug. Für
Vorher/Nachher-Vergleiche und Wisch-Carousels braucht es weiterhin einen
benannten Projektordner, siehe
[`content/medien/LIESMICH.md`](content/medien/LIESMICH.md).

Der tägliche GitHub-Workflow sichtet den Eingang von selbst, bevor er
rendert – Fotos landen also spätestens am nächsten Posttermin im Feed.

---

## Was Sie beitragen – und was nicht

**Sie:** ab und zu Baustellenfotos in `content/medien/` ablegen.
Fünf bis sechs Projektordner reichen für ein Jahr. Anleitung dort in
[`LIESMICH.md`](content/medien/LIESMICH.md).

**Das System:** Themenwahl, Layout, Text, Hashtags, Zeitpunkt,
Veröffentlichung, Verlauf.

---

## Ordnerübersicht

```
brand/          Design-Tokens (brand.json), Logos, Schriften
templates/      Die Vorlagen – hier ändern Sie das Aussehen
content/
  themen.json       Themenbank – hier ändern Sie die Inhalte
  hashtags.json     Hashtag-Sets und CTA-Varianten
  medien/           Ihre Fotos
  verlauf.json      Was wann gepostet wurde (wird automatisch gefüllt)
src/            Planer, Texter, Renderer, Publisher
out/            Erzeugte Bilder und Texte
docs/           Markenanalyse und Einrichtungsanleitung
.github/        Zeitsteuerung
```

---

## Befehle

| Befehl | Zweck |
|---|---|
| `python src/main.py muster` | alle Vorlagen einmal rendern |
| `python src/main.py vorschau --tage 30` | Redaktionsplan anzeigen |
| `python src/main.py vorschau --tage 7 --rendern` | Woche vorproduzieren |
| `python src/main.py heute` | Beitrag erzeugen, nicht posten |
| `python src/main.py heute --posten` | erzeugen und veröffentlichen |
| `python src/main.py heute --datum 2026-09-01` | für ein anderes Datum |
| `python src/main.py heute --ki` | Text von Claude glätten (kostenpflichtig) |
| `python src/main.py heute --posten --trocken` | Veröffentlichung simulieren |
| `python src/main.py zugang` | Instagram- und Facebook-Verbindung prüfen |
| `python src/main.py protokoll` | letzte Post-Versuche mit Fehlermeldung |
| `python src/main.py freigeben <id>` | Thema freigeben (nur bei Freigabe-Pflicht) |
| `python src/main.py carousel` | verfügbare Carousels auflisten |
| `python src/main.py carousel c-bad-ablauf` | Carousel rendern |
| `python src/main.py raster` | Profil-Rasteransicht der nächsten 9 Beiträge |
| `python src/main.py monatsplan` | Redaktionsplan für den Monat, alle Texte |
| `python src/main.py fotobedarf` | welche Fotos welchen Tag füllen würden |
| `python src/main.py auswerten` | eigene Beiträge auswerten (braucht Zugang) |
| `python src/main.py export` | Monatsordner mit Tabelle, Bildern, Texten |
| `python src/main.py fb-seiten --token …` | Facebook-Seiten-Token ermitteln |
| `python src/main.py fotos-verarbeiten` | Eingang sichten, ausrichten, in den Pool legen |
| `python src/main.py vorschlagen` | Kandidat rendern, zur Freigabe an Telegram schicken |
| `python src/main.py telegram-abfragen` | Telegram-Antworten auswerten (freigeben/ablehnen) |

---

## Monatsplan

```bash
python src/main.py monatsplan --jahr 2026 --monat 9
```

Erzeugt in `out/` zwei Dateien: eine Markdown-Fassung zum Lesen und
Weitergeben, und eine HTML-Fassung zum Durchklicken im Browser. Beide
enthalten für jeden Tag des Monats:

- die Bild-Headline, Unterzeile und Stichpunkte
- den vollständigen Text unter dem Beitrag, so wie er live geht
- **warum** dieser Beitrag an diesem Tag steht
- ob er als Ersatz läuft, weil ein Foto fehlt

Damit lässt sich der komplette Monat abnehmen, bevor irgendetwas
veröffentlicht wird.

---

## Auswertung

```bash
python src/main.py auswerten --tage 30
```

Drei Auswertungen über die offizielle Schnittstelle, ohne Zusatzdienst:

1. **Selbst-Audit** – Reichweite, Speicherungen, Shares, Kommentare
2. **Ausreißer** – welche eigenen Beiträge über dem eigenen Median liegen
   (Median statt Mittelwert, damit ein viraler Ausreißer die Messlatte
   nicht dauerhaft verschiebt)
3. **Muster** – welche Säule, welcher Wochentag, welches Format trägt

Der Vergleich mit fremden Konten (`--vergleich @betrieb`) braucht den Weg
über eine Facebook-Seite. Ist er nicht verfügbar, sagt das Programm das
klar, statt zu raten.

Aussagekräftig wird die Auswertung erst ab etwa 20 Beiträgen je Säule –
das steht auch so im Bericht.

---

## KI schreibt Themen (optional)

```bash
python src/main.py ki-thema --saeule wissen --gewerk Fliesen --stichwort "Randfugen"
```

Lässt ChatGPT (primär) oder Claude (Ausweichoption) ein neues Thema
schreiben – als Systemprompt bekommt die KI **wortwörtlich**
[`content/CONTENT-PROMPT.md`](content/CONTENT-PROMPT.md), keine verkürzte
Zusammenfassung. Das Ergebnis durchläuft danach dieselbe mechanische
Selbstprüfung wie jeder von Hand geschriebene Text (`src/pruefung.py`) –
Hook-Länge, verbotene Wörter, Normen-Positivliste, Layoutgrenzen. Erst wenn
das ohne Beanstandung durchläuft, lässt es sich mit `einpflegen` übernehmen.

**SEO/Keywords:** Die KI baut gezielt ein bis zwei lokale Suchbegriffe in
den Fließtext ein (Mülheim an der Ruhr, Badsanierung, Fliesenleger, …) –
das hilft bei der Instagram-Suche und bei öffentlich indexierten
Facebook-Beiträgen. Prüfen, wie es aktuell um die Themenbank steht:

```bash
python src/main.py seo-check
```

Ohne `OPENAI_API_KEY` oder `ANTHROPIC_API_KEY` in der `.env` bleibt alles
unverändert regelbasiert und kostenlos – `ki-thema` ist eine Ergänzung,
keine Voraussetzung.

> **Ihr Schlüssel gehört in die `.env`, nicht in den Chat.** Diese Datei ist
> für mich aus Sicherheitsgründen komplett gesperrt (weder lesen noch
> schreiben) – das ist bewusst so eingerichtet. Tragen Sie den Schlüssel
> selbst ein. Ein im Chat eingefügter Schlüssel wird von mir nur einmalig
> im Arbeitsspeicher zum Testen verwendet, nie gespeichert.

---

## Facebook läuft mit

Jeder Beitrag geht automatisch auch auf **facebook.com/BerisaBau** – sobald
`FB_PAGE_ID` und `FB_PAGE_TOKEN` hinterlegt sind. Fehlen sie, bleibt Facebook
einfach aus; es ist keine Umstellung nötig.

Der Text ist dort ein anderer, und das mit Absicht:

| | Instagram | Facebook |
|---|---|---|
| Links im Text | nicht klickbar | **klickbar** – die Website steht als echte Adresse drin |
| Hashtags | 12, bringen Reichweite | 2, mehr wirkt deplatziert |
| Carousel | Carousel | Beitrag mit mehreren Bildern |
| Reel | Reel | Video-Beitrag auf der Seite |

Beide Fassungen liegen nach `python src/main.py heute` nebeneinander in `out/`:
die Instagram-Fassung als `.txt`, die Facebook-Fassung als `.facebook.txt`.
In der Monatstabelle steht sie als eigene Spalte.

Einrichtung (etwa 20 Minuten, kostenlos):
[`docs/03-FACEBOOK-EINRICHTEN.md`](docs/03-FACEBOOK-EINRICHTEN.md)

Einzelnen Tag nur auf Instagram: `--kein-facebook`.

**Wichtig:** Ein privates Facebook-Profil lässt sich nicht per API bespielen.
Es muss eine Seite sein – die gibt es bei Berisa Bau bereits.

Klemmt Facebook, ist der Instagram-Beitrag trotzdem draußen. Der Fehler wird
auf der Konsole ausgegeben, der Lauf gilt aber nicht als gescheitert.

---

## Freigabe per Telegram (optional)

Ohne Einrichtung läuft alles wie beschrieben vollautomatisch. Mit
`TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` bekommt jeder Beitrag vorher
einen Zwischenstopp: das fertige Bild landet im Chat mit zwei Tasten
(**✅ Freigeben** / **❌ Ablehnen**). Bei Ablehnen wird sofort ein neuer
Kandidat gerendert und erneut geschickt – so lange, bis einer passt oder das
Material der Rubrik aufgebraucht ist. Ohne Freigabe postet der planmäßige
Job nichts.

Dienstags ist die Rotation textlastig (Wissen/Achtung), donnerstags
fotolastig (echtes Baustellenfoto aus `content/medien/`) – mit automatischem
Rückfall auf Text, wenn kein frisches Foto vorliegt.

Einrichtung (etwa 10 Minuten, kostenlos):
[`docs/04-TELEGRAM-EINRICHTEN.md`](docs/04-TELEGRAM-EINRICHTEN.md)

---
gemeldet, der Tageslauf gilt nicht als gescheitert.

---

## Monatspaket zum Abnehmen

```bash
python src/main.py export --jahr 2026 --monat 9
```

Legt `monatspakete/September-2026/` an:

| Datei | Inhalt |
|---|---|
| `UEBERSICHT.html` | die Tabelle – Doppelklick genügt, filterbar nach Säule |
| `tabelle.csv` | dieselben Daten für Excel (Semikolon, UTF-8) |
| `bilder/` | alle fertigen Beitragsbilder, bei Carousels jede Slide |
| `texte/` | jeder Text als einzelne Datei zum Kopieren |

Damit lässt sich der komplette Monat abnehmen, bevor irgendetwas online geht.

---

## Beitragsarten

Der Planer entscheidet nach dem, was im Projektordner liegt:

| Im Ordner | Daraus wird |
|---|---|
| ein Video | **Reel** – Titelbild gebrandet, Video unverändert |
| zwei oder mehr Fotos | **Carousel** zum Wischen, bis zu 10 Slides |
| ein Foto | Einzelbild |
| `vorher` + `nachher` | zusätzlich ein Vorher/Nachher-Post |
| nichts | Textkachel aus der Themenbank |

### Das Rasterlayout

Was im Profil zuerst gesehen wird – die Cover von Carousels und Reels – nutzt
`templates/cover-raster.html`: Logo oben mittig, Foto in einem Rahmen mit
Player-Leiste, große Headline, Website unten.

Drei Grundfarben wechseln sich ab: **Rot**, **Dunkel**, **Hellgrau**. Weil
Instagram drei Kacheln je Reihe zeigt und die Rotation eine Periode von drei
hat, landet jede Farbe immer in derselben Spalte – im Profil entstehen ruhige
gleichfarbige Streifen statt eines zufälligen Flickenteppichs.

Prüfen mit `python src/main.py raster`.

---

## Carousels

Reels machen dich auffindbar, **Carousels bringen Anfragen**: Leser bleiben
länger, speichern öfter und lesen bis zum Handlungsaufruf.

Aufbau in `content/carousels.json`, fünf Beats über 6–7 Slides:

```
Cover      Hook – wird hier nicht gestoppt, liest niemand weiter
Slide 2–n  ein Gedanke je Slide, erklärend
Abschluss  Speicher-Hinweis + Kontakt. Nur hier wird gefragt.
```

Drei fertige Carousels sind hinterlegt: Badsanierungs-Ablauf, Pfusch
erkennen, Fliesenformat. Rendern mit `python src/main.py carousel <id>`.

Instagram erlaubt bis zu 10 Slides; 6–7 ist der brauchbare Bereich.

---

## Rasteransicht

Niemand folgt einem einzelnen Beitrag – gefolgt wird dem Profil, und die
ersten drei Reihen entscheiden.

```bash
python src/main.py raster
```

Erzeugt `out/raster.html`: die nächsten neun Beiträge als 3×3-Raster, mit
demselben quadratischen Zuschnitt, den Instagram im Profil anwendet.
Im Browser öffnen und prüfen, ob die Kacheln nebeneinander ruhig wirken.

---

## Freigabe: automatisch oder auf Zuruf

Standard ist **volle Automatik** – der Beitrag geht ohne Zutun raus.

Wer lieber jeden Beitrag vorher sieht, setzt die Repository-Variable
`FREIGABE_PFLICHT=true`. Dann veröffentlicht die Automatik nur Themen, die
vorher mit `python src/main.py freigeben <id>` eingetragen wurden – alles
andere wird erzeugt, aber nicht gepostet.

Zusätzlich greift immer eine Sicherheitsgrenze: höchstens
`MAX_POSTS_24H` Beiträge in 24 Stunden (Standard 5). Das Kontingent wird vor
jedem Post live bei Instagram abgefragt, nicht geraten.

---

## Wenn etwas schiefgeht

`logs/posts.jsonl` protokolliert jeden Versuch – auch die fehlgeschlagenen,
mit Fehlermeldung und Permalink.

Der Publisher unterscheidet zwischen Fehlern, bei denen Wiederholen hilft
(Netz, Auslastung – exponentieller Backoff, bis zu vier Versuche) und
solchen, bei denen es nichts bringt (Token, Rechte – sofortiger Abbruch mit
Klartext-Hinweis). Ein erschöpftes Kontingent gilt nicht als Fehlschlag:
der Beitrag kommt am Folgetag.

Diagnose übernimmt der Agent `berisabau-betrieb`.

---

## Design ändern

Alles Visuelle steckt in zwei Dateien:

- [`brand/brand.json`](brand/brand.json) – Farben, Schriften, Firmendaten
- [`templates/_base.css`](templates/_base.css) – das Layout

Die Werte stammen 1:1 aus dem CSS von berisabau.de. Wenn sich die Website
ändert, hier nachziehen – dann bleibt der Feed anschlussfähig.

---

## Inhalte ändern

[`content/themen.json`](content/themen.json). Ein neues Thema ist ein
Objekt in `themen` – Struktur von den vorhandenen abschauen.
`titel_stark` ist der Teil mit dem roten Schrägbalken.

**Freigabe-Sperre:** Themen mit `"pruefen": true` werden nie automatisch
gepostet. Alle vier Kundenstimmen stehen aktuell auf `true` – drei davon
sind Platzhalter. Bitte durch echte, so tatsächlich erhaltene Aussagen
ersetzen und erst dann freigeben. Erfundene Bewertungen sind nach UWG
abmahnfähig.

---

## Einrichtung

Einmalig, 30–45 Minuten: [`docs/02-INSTAGRAM-EINRICHTEN.md`](docs/02-INSTAGRAM-EINRICHTEN.md)

Kurzfassung:
1. @berisabau auf **Profikonto** umstellen (zwingend)
2. Meta-App anlegen, Instagram-Produkt hinzufügen, Token holen
3. GitHub Pages als Bildablage aktivieren
4. Drei Secrets im Repository hinterlegen

Eine Meta-App-Prüfung ist **nicht** nötig, solange nur das eigene Konto
bespielt wird.

---

## Analyse

Warum die Vorlagen so aussehen, wie sie aussehen:
[`docs/01-MARKENANALYSE.md`](docs/01-MARKENANALYSE.md)

---

## Grenzen

- **Kein Community-Management.** Kommentare und DMs beantworten Sie selbst.
  Das sollte auch so bleiben – dort entstehen die Aufträge.
- **Zwei Beiträge pro Woche.** Mehr wäre technisch möglich (Instagram
  erlaubt bis 25/Tag), ist bei einem wachsenden Konto aber die bewusst
  gewählte Kadenz – lieber zwei durchdachte Beiträge als viele beliebige.
  Änderbar über `posttage` in `content/themen.json`.
- **Fotobearbeitung ist klassisch, nicht KI.** `fotos-verarbeiten` richtet
  aus, korrigiert Kontrast und schärft nach – es erzeugt nichts. Ein
  KI-generiertes Bad als eigene Arbeit zu zeigen wäre nach Regel 1 im
  Content-Prompt Wettbewerbsbetrug.

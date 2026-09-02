# Clip-Werk: vom Twitch-Stream zu TikTok, Reels und Shorts

Das Clip-Werk sieht sich einen kompletten Stream an, sucht die Momente, die
als Short tragen, bewertet sie nach einem festen 100-Punkte-Maßstab und legt
zu jedem Clip alles hin, was zum Veröffentlichen fehlt: Zeitstempel, Hook,
Schnittanweisungen, Untertitel, Titel, Captions, Hashtags und – wenn das
Quellvideo dabei ist – den fertigen ffmpeg-Befehl für 1080 × 1920.

Der Maßstab steht in [`content/CLIP-PROMPT.md`](../content/CLIP-PROMPT.md).
Jedes Modul in `src/clipwerk/` nennt in seinem Kopf, welchen Abschnitt
daraus es umsetzt.

---

## Warum über den Ton und nicht über den Chat

Der Chat wäre das stärkere Signal — er zeigt die Ausschläge unmittelbar.
Automatisch abrufen lässt er sich aber nicht mehr: Twitch verlangt für
Chatabrufe einen signierten Nachweis aus einem angemeldeten Browser. Ohne
den kommt

    Twitch lehnt die Abfrage ab: failed integrity check

und zwar unabhängig vom Werkzeug. Das ist eine bewusste Schutzmaßnahme, und
sie wird hier nicht umgangen.

Betroffen ist ausschließlich der Chat. Videodaten und Ton sind anonym
abrufbar — am GitHub-Runner mehrfach nachgemessen. Deshalb läuft alles über
die Spracherkennung, und das ist kein Behelf: mit Transkript entstehen
Untertitel, Zitate als Hook, saubere Satzgrenzen beim Zuschnitt und das
Herausschneiden von Stille. Der Chat-Modus im Code bleibt erhalten für den
Fall, dass jemand eine `chat.json` von Hand beisteuert — angemeldet im
eigenen Browser darf das jeder für seinen eigenen Kanal tun.

Der Preis ist Rechenzeit: Spracherkennung über zweieinhalb Stunden dauert
ein bis drei Stunden.

---

## Der einfachste Weg: auf GitHub klicken

Unter **Actions → „Clip-Werk – Stream auswerten" → „Run workflow"** die
Adresse des VODs eintragen und starten. Der Lauf holt den Ton, erkennt den
Text, wertet aus und legt den Bericht als Datei ins Repo unter
`docs/clips/<vod>/bericht.md` — dort direkt lesbar, zusätzlich als Download
am Lauf.

Kein Terminal, kein eingerichteter Rechner. Rechne mit ein bis drei Stunden
Laufzeit.

---

## Der Weg über den eigenen Rechner: doppelklicken

`clip-holen.command` im Hauptordner macht alles allein — Werkzeuge
nachinstallieren, Ton laden, Text erkennen, auswerten, Ergebnisordner
öffnen. Gebraucht wird nur die Adresse des VODs (die Seite mit `/videos/`
darin, nicht die Kanalseite).

Am Ende fragt es, ob auch das Video geladen und die Clips gerendert werden
sollen. Ton und Transkript werden zwischengespeichert: ein abgebrochener
Lauf fängt beim nächsten Start nicht wieder von vorn an.

---

## Von Hand: in fünf Minuten ausprobieren

```bash
python src/main.py clip analyse \
  --transkript stream.srt \
  --chat chat.json \
  --stream-id 2401234567 \
  --datum 2026-09-01 \
  --streamer K1ANUSH \
  --spiel "Counter-Strike 2"
```

Danach liegt in `out/clips/2401234567/`:

```
bericht.md              Clips im Format aus Abschnitt 10, plus Kanal-Auswertung
clips.json              dieselben Daten maschinenlesbar
untertitel/clip-01.ass  zum Einbrennen (groß, mit Akzentfarbe)
untertitel/clip-01.srt  zum Hochladen
rendern.sh              nur wenn --video angegeben wurde
```

Der Befehl geht auch ohne den Rest dieses Repos:

```bash
PYTHONPATH=src python3 -m clipwerk analyse ...
```

## Was hineingeht

**Transkript** (freiwillig) – SRT, WebVTT oder Whisper-JSON. Whisper-JSON
ist besser, weil es Wortzeiten mitbringt: die Untertitel sitzen dann auf
dem Wort statt auf dem Satz.

Ohne Transkript läuft der **Chat-Modus**. Er findet dieselben Momente, denn
die Ausschläge stehen im Chat, nicht in der Sprache. Was fehlt, ist alles,
wofür man den Wortlaut braucht: Untertitel, Zitate als Hook, Satzgrenzen
beim Zuschnitt und das Herausschneiden von Stille. Die Zeitstempel sind
dann Anhaltspunkte, kein fertiger Schnitt.

Der Chat-Modus rechnet außerdem mit einer eigenen Schwelle: 58 statt 65.
Das ist keine Nachsicht, sondern eine Korrektur. Zwei der sechs Teilnoten
sind ohne Wortlaut unbekannt und stehen auf einem neutralen Wert — dadurch
ist die erreichbare Höchstpunktzahl gedeckelt. Über dieselben sieben
Momente gemessen lagen die Werte im Mittel 7,3 Punkte tiefer (einzeln 2 bis
12), ohne dass die Clips schlechter gewesen wären. Ohne die Korrektur
bedeutete „65" im Chat-Modus faktisch 72. Der Wert stammt aus einem
synthetischen Vergleichslauf und gehört an echten Streams nachgemessen.

```bash
# Beispiel: Ton aus dem VOD ziehen und transkribieren
yt-dlp -f bestaudio -o stream.m4a "https://www.twitch.tv/videos/2401234567"
whisper stream.m4a --language de --output_format json
```

**Chat** (freiwillig, aber der Unterschied ist groß) – der VOD-Export mit
`content_offset_seconds`, eine JSONL-Datei oder ein IRC-Mitschnitt der Form
`[00:12:34] name: text`. Ohne Chat stützt sich die Auswahl allein auf die
Sprache; der Bericht weist oben darauf hin.

**Video** (nur fürs Rendern) – `--video vod.mp4`. Ohne es entsteht kein
`rendern.sh`, alles andere aber schon.

**Facecam** (nur für geteilte Layouts) – `--facecam x:y:breite:höhe`, in
Pixeln des Quellvideos. Bei 1920 × 1080 mit Webcam rechts oben ist das
typischerweise etwas wie `--facecam 1450:60:440:300`. Ohne diese Angabe
rendert jedes Layout als Vollbild, statt einen leeren Kasten einzubauen.

## Wie ausgewählt wird

1. **Interessenkurve.** Je Sekunde werden Chatgeschwindigkeit, Emote-Art
   (Lachen, Schock, Wut, Fremdscham, „clip it") und Sprachsignale gezählt
   und **gegen die Grundlast desselben Streams** normiert. Ein Stream mit
   40.000 Zuschauern hat eine andere Grundlast als einer mit 400 – der
   Ausschlag darüber ist in beiden das Signal.
2. **Fenster.** Um jede Spitze wird ein Fenster gelegt: Ende dort, wo die
   Reaktion abklingt; Anfang an dem Satzanfang, der den stärksten Einstieg
   hat. Stille über 1,2 Sekunden wird als Auslassung markiert und zählt
   nicht zur Länge.
3. **Bewertung.** Hook 25, Unterhaltung 20, Watchtime 20, Share 15,
   Kommentar 10, Follower 10. Unter 65 Punkten wird verworfen, ab 80 gilt
   höchste Priorität. Die Teilnoten stehen im Bericht – man sieht also,
   warum ein Clip 71 und nicht 84 hat.
4. **Entdoppelung.** Fenster, die sich zu mehr als 40 Prozent überlappen,
   sind derselbe Clip; das schwächere fällt weg.

Kommt kein Clip über die Schwelle, sagt der Bericht genau das. Das ist ein
gültiges Ergebnis (Abschnitt 15) und kein Fehler.

## Was herauskommt

Je Clip ein Block mit den Feldnamen aus Abschnitt 10 – wörtlich, damit die
Person am Schnittplatz die Zeile findet, die sie sucht:

```
CLIP NUMMER: 03   (2401234567-000932)
Timestamp Start: 0:15:31
Timestamp Ende: 0:15:56
Dauer: 23 s  (roh 25 s, 2 s Stille raus)
Kategorie: FUNNY
Virality Score /100: 75
  Hook 21.1/25 · Unterhaltung 16.4/20 · Watchtime 18.9/20 · …
Warum dieser Clip: Lach-Emotes brechen aus und Zuschauer fordern selbst
einen Clip bei 15:36. Die Pointe liegt bei 41 % der Cliplänge, davor 9 s
Aufbau.
```

Danach Hook, Schnittplan mit Zeitmarken, vollständiger Untertiteltext,
TikTok-Titel und -Caption, Hashtags, Instagram-Caption, YouTube-Titel.

Am Ende des Berichts steht die Kanal-Auswertung nach Abschnitt 11: die drei
stärksten Clip-Arten, wiederkehrende Stichworte, was Kommentare erzeugt und
welche Serienformate dieser Stream hergibt.

## Veröffentlichen

```bash
# 1. Clips in die Datenbank aufnehmen (verhindert Doppelungen)
python src/main.py clip analyse ... --aufnehmen

# 2. Rhythmus planen: bester Score zuerst, Crossposting mit Versatz
python src/main.py clip plan --clips out/clips/2401234567/clips.json

# 3. nach dem Posten eintragen
python src/main.py clip verlauf --veroeffentlicht 2401234567-000932 tiktok

# 4. nach ein paar Tagen die Zahlen nachtragen
python src/main.py clip kennzahlen 2401234567-000932 tiktok \
  --views 120000 --completion 61 --shares 900 --kommentare 400 --follower 260

# 5. sehen, was daraus gelernt wurde
python src/main.py clip lernen
```

Der Plan hält zwei TikToks pro Tag mit dreieinhalb Stunden Abstand,
Instagram einen Tag versetzt, YouTube zwei – und wandelt den Hook je
Plattform leicht ab. Zwei wortgleiche Posts nebeneinander sehen nach Bot
aus.

Schritt 3 ist die Sperre aus Abschnitt 13: derselbe Clip lässt sich auf
derselben Plattform kein zweites Mal eintragen.

## Wie das System besser wird

Ab etwa zwei erfassten Clips je Kategorie beginnt `clip lernen` zu
rechnen. Verglichen wird nicht mit Branchenwerten, sondern mit dem
Durchschnitt **dieses** Kontos, und zwar je View – ein Clip mit 400.000
Views hat natürlich mehr Kommentare als einer mit 4.000.

Was daraus entsteht, ist ein Faktor je Kategorie und Teilnote, gedeckelt
auf 0,85 bis 1,15 und nach Stichprobengröße gedämpft. Laufen Rage-Clips
besser als Gaming-Clips, rutschen Rage-Momente in der Bewertung nach oben.
Der Deckel ist Absicht: ohne ihn frisst sich das System in die Kategorie,
die zufällig zuerst gut lief, und der Kanal wird eintönig.

`--ohne-lernen` schaltet das für einen Lauf ab.

## Rendern

```bash
python src/main.py clip analyse ... --video vod.mp4 --facecam 1450:60:440:300
sh out/clips/2401234567/rendern.sh
```

Ein ffmpeg-Aufruf je Clip erledigt alles in einem Durchgang: Zuschnitt,
innere Schnitte, Bildaufteilung, Punch-In-Zoom und eingebrannte Untertitel.
Vier Aufteilungen stehen zur Wahl (`--layout`), gewählt wird sonst nach
Kategorie:

| Layout | wofür |
|---|---|
| `vollbild` | ohne Facecam-Angabe, Hintergrund unscharf gedoppelt |
| `geteilt` | Facecam oben, Gameplay unten – Gaming, Fails, Wins |
| `facecam_gross` | Gameplay als Hintergrund, Facecam groß – Reaktionen, Rage |
| `nur_person` | reine Wortclips – Storys, Meinungen |

Gebraucht wird ffmpeg ab Version 5 (`zoompan` mit `it`). Die vier
Filtergraphen sind gegen ffmpeg 7.0 geprüft und liefern 1080 × 1920 bei
Pixelseitenverhältnis 1:1.

Ohne ffmpeg auf dem Rechner wird trotzdem geschrieben – das Skript lässt
sich auf den Schnittrechner mitnehmen.

## Was das Clip-Werk nicht tut

* **Es lädt nichts hoch.** TikTok, Instagram Reels und YouTube Shorts
  brauchen je einen eigenen API-Zugang mit eigener Freigabe. Der Plan sagt,
  was wann wohin gehört; das Hochladen bleibt vorerst Handarbeit.
* **Es erkennt keine Gesichter.** Der Facecam-Ausschnitt wird angegeben,
  nicht gesucht. Bei einem festen Streaming-Layout ist das einmal Arbeit
  und danach für jeden Stream derselbe Wert.
* **Es erfindet keine Hooks.** Ist kein Signal stark genug für eine
  Behauptung wie „Chat ist komplett eskaliert", wird aus dem tatsächlich
  Gesagten zitiert. Irreführender Clickbait holt einmal Views und kostet
  danach dauerhaft Reichweite.
* **Es kennt keine aktuellen Trend-Hashtags.** Die Liste `trend` in
  `content/clip_hashtags.json` pflegt ein Mensch. Trend-Tags veralten in
  Wochen; im Code wären sie nach dem zweiten Monat falsch.

## Die Dateien

| Datei | wofür |
|---|---|
| `clip-holen.command` | Doppelklick: holt einen Stream und wertet ihn aus |
| `.github/workflows/clip-auswerten.yml` | dasselbe auf GitHubs Servern, per Klick |
| `content/CLIP-PROMPT.md` | der Maßstab, dem der Code folgt |
| `content/clip_lexikon.json` | Emotes und Redewendungen je Signalart |
| `content/clip_hashtags.json` | Hashtag-Sätze je Kategorie, Trend-Liste |
| `content/clip_verlauf.json` | Clip-Datenbank gegen Doppelungen (Abschnitt 13) |
| `src/clipwerk/` | das Paket, ein Modul je Abschnitt |
| `tests/test_clipwerk.py` | 73 Tests, ohne Netz und ohne ffmpeg |

Lexikon und Hashtags liegen bewusst als Datei vor: Emotes und Sprüche
wechseln schneller als Software.

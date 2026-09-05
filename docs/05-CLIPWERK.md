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

Kein Terminal, kein eingerichteter Rechner. Gemessen an zweieinhalb Stunden
Stream: acht Minuten Ton laden, 33 Minuten Spracherkennung, der Rest in
Sekunden — zusammen gut vierzig Minuten.

**Einen Stream ein zweites Mal auswerten:** in das Feld `aus_lauf` die
Nummer eines früheren Laufs eintragen (steht in der Adresse des Laufs unter
Actions). Dann wird dessen Transkript übernommen statt derselbe Ton noch
einmal durch dasselbe Modell geschickt — ein Nachlauf kostet damit eine
Minute statt vierzig. Nützlich, wenn sich an der Auswertung etwas geändert
hat und nicht am Stream. Die Anhänge laufen nach 30 Tagen ab; danach geht
nur noch der volle Weg.

Das Transkript liegt bewusst nur am Lauf und nicht im Repository: es ist
die wörtliche Mitschrift eines fremden Streams und gehört nicht in ein
öffentliches Repo. Im Repo landen die Clip-Vorschläge.

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

### Jede Betriebsart hat ihre eigene Schwelle

| Vorhanden | Schwelle |
|---|---|
| Transkript **und** Chat | 65 |
| nur Transkript | 61 |
| nur Chat | 73 |

Das ist keine Nachsicht und keine Strenge, sondern eine Korrektur an der
Punktzahl selbst. Ein Bestandteil, den es in einem Stream gar nicht gibt —
der Clipruf ohne Chat, die Wortdichte ohne Transkript — zählt nicht als
Null; eine fehlende Messung ist kein schlechter Wert. Er fällt heraus, und
sein Gewicht verteilt sich auf den Rest. Was übrig bleibt, trägt dadurch
volles Gewicht, und im Chatbetrieb sind das vor allem die großzügigen Teile:
Kategorieneigung und Chatausschlag. Ohne Gegengewicht bekäme derselbe Moment
ohne Transkript *mehr* Punkte als mit.

Nachgemessen an fünf synthetischen Streams mit unterschiedlich lebhaftem
Chat, jeweils derselbe Stream in allen drei Betriebsarten: der Chatbetrieb
lag 5 bis 11 Punkte über dem Vollbetrieb, der Betrieb ohne Chat 0 bis 11
darunter. Die Streuung ist groß, weil sie daran hängt, wie laut der Chat
ist. Erfundenes Material, erste Eichung — an echten Streams gehört das
nachgemessen. `tests/test_clipwerk.py` hält den Vergleich als Test fest.

> Bis zum 02.09.2026 stand hier eine einzelne abgesenkte Schwelle von 58
> für den Chatbetrieb. Sie war gegen eine Fassung gemessen, die fehlende
> Werte als Null zählte, und hätte die Korrektur seither doppelt gezählt —
> in die falsche Richtung.

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
   Kommentar 10, Follower 10. Unter der Schwelle der jeweiligen Betriebsart
   wird verworfen (65 im Vollbetrieb), ab 80 gilt höchste Priorität. Die
   Teilnoten stehen im Bericht – man sieht also, warum ein Clip 71 und
   nicht 84 hat.
4. **Entdoppelung.** Fenster, die sich zu mehr als 40 Prozent überlappen,
   sind derselbe Clip; das schwächere fällt weg.

Kommt kein Clip über die Schwelle, sagt der Bericht genau das. Das ist ein
gültiges Ergebnis (Abschnitt 15) und kein Fehler.

**Kein geprüfter Moment ist etwas anderes.** „Geprüft und zu schwach" ist
ein Urteil über den Stream. „Gar nichts geprüft" heißt, die Signalkurve hat
nirgends ausgeschlagen — und das ist bei einem Stream mit Sprache oder Chat
fast immer eine Eichung, die nicht zur Datenlage passt, kein langweiliger
Stream. Der Bericht sagt beides getrennt.

```bash
python src/main.py clip diagnose \
  --transkript transkript.json --stream-id 2401234567
```

`clip diagnose` zeigt die Zahlen dahinter, ohne Clips und ohne Zitate:
welche Signalreihen überhaupt tragen und wie oft sie feuern, wie hoch die
Kurve liegt (Perzentile), wo die Spitzenschwelle steht und wie sich die
Punkte der gefundenen Momente verteilen. Damit lässt sich in einem Blick
unterscheiden, ob ein Stream nichts hergab oder ob die Kurve schiefsteht.

Der erste Lauf über einen echten Stream endete genau hier: 1549 erkannte
Sprachsegmente, **null** geprüfte Momente. Ursache waren nicht die Inhalte,
sondern drei Annahmen, die alle aus dem Chatbetrieb stammten — eine
Grundlast, die seltene Reihen auslöschte; Sprachsignale, die nur auf der
Anfangssekunde ihres Satzes saßen; und feste Schwellen, gemessen an einer
Kurve mit doppelt so vielen Sensoren.

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

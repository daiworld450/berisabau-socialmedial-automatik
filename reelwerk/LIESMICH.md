# Reel-Werk

Rohclip rein, fertiges Reel raus. Läuft lokal auf dem Mac und kostet nichts.

## So benutzt Du es

1. Clips ablegen in `~/Desktop/Berisa Baufotos/REELS-ROH/`
2. Doppelklick auf `REELS-MACHEN.command`
3. Fertige Reels liegen in `reelwerk/fertig/`

Beim ersten Lauf lädt es einmalig das Sprachmodell (rund 500 MB). Danach
braucht es kein Internet mehr. Ein 30-Sekunden-Clip dauert etwa 40 Sekunden.

## Was es automatisch macht

| | |
|---|---|
| Format | auf 1080 × 1920 (hochkant) skalieren und mittig zuschneiden |
| Anfang/Ende | Stille wegschneiden — die zwei Sekunden Wackeln am Anfang kosten Zuschauer |
| Untertitel | Ton wird lokal transkribiert und in kurzen Zeilen eingebrannt |
| Logo | oben links, **immer rot** — auf einem weichen dunklen Verlauf, damit es auch auf schwarzem Marmor steht |
| Endkarte | 1,8 Sekunden: rotes Logo, Telefonnummer **weiß**, @berisabau und berisabau.de **rot** |
| Größe | rund 8 MB, für Instagram passend kodiert |

## Drei Regeln fürs Filmen

**1. Hochkant.** Quer gefilmtes Material verliert links und rechts die Hälfte.
Das Skript warnt, kann es aber nicht reparieren.

**2. Der Dateiname wird zur Einblendung.** Er erscheint die ersten drei
Sekunden groß im Bild — das ist der Aufhänger, der über Weiterwischen oder
Bleiben entscheidet.

- gut: `Dichtband in jede Ecke.mov`
- gut: `Das kostet dich später 5000 Euro.mov`
- nutzlos: `IMG_4711.mov` → dann kommt keine Einblendung

**3. Sofort loslegen.** Kein Vorlauf, kein „so, also …". Die erste Sekunde
entscheidet. Wenn Du sprichst: direkt mit dem Satz anfangen, der zählt.

## Bilder statt Video: der Diashow-Modus

Wenn für ein Thema kein Video da ist, werden mehrere Fotos zu einem bewegten
Reel — nie ein einzelnes Standbild, das wirkt tot und wird weggewischt.

1. Ordner anlegen unter `~/Desktop/Berisa Baufotos/DIASHOW/`
2. Mindestens zwei Fotos hineinlegen (fünf bis sieben sind gut)
3. Optional: eine Tonaufnahme daneben legen, z. B. `stimme.m4a`
4. Im Terminal: `.venv/bin/python reelwerk/reelwerk.py --diashow`

Jedes Foto bekommt eine langsame Kamerafahrt, die Richtung wechselt von Bild
zu Bild. Liegt eine Tonaufnahme dabei, richtet sich die Länge der Bilder nach
ihr und die Untertitel entstehen automatisch daraus.

## Die Stimme

Eingebaut ist **Chatterbox Multilingual** (Resemble AI, MIT-Lizenz, also
gewerblich nutzbar). Coqui XTTS-v2 waere technisch aehnlich, ist aber
ausdruecklich nur privat erlaubt — fuer einen Betrieb keine Option.

### Einmalig einrichten

1. Sprachmemo aufnehmen: **rund 60 Sekunden**, ruhiger Raum, kein
   Baustellenlaerm, normales Tempo. Inhalt egal.
2. Datei nach `reelwerk/stimme/` legen.
3. Doppelklick auf `STIMME-EINRICHTEN.command` — es spricht eine Probe und
   spielt sie ab.

Die Aufnahme bleibt auf diesem Rechner. Sie ist per `.gitignore` gesperrt und
kann nicht versehentlich ins oeffentliche Repo geraten.

### Benutzen

Text schreiben, Reel bekommt die Ansage automatisch:

```
~/Desktop/Berisa Baufotos/DIASHOW/
    foto-1.jpg
    foto-2.jpg
    text.txt        ← was gesagt werden soll
```

Dann `.venv/bin/python reelwerk/reelwerk.py --diashow`. Die Ansage wird
gesprochen, die Bildlaengen richten sich danach, die Untertitel entstehen
daraus. Ein Reel aus vier Bildern dauert rund 40 Sekunden.

Einzelne Ansage ohne Reel:

```bash
.venv-stimme/bin/python reelwerk/stimme.py "Der Satz, der gesprochen wird."
```

### Was Du wissen solltest

- **Untertitel gegenlesen.** Die kuenstliche Stimme verschluckt gelegentlich
  ein Wort („Erster Ständerwerk" statt „Erst das Ständerwerk"), und der
  Untertitel uebernimmt das. Bei echtem Ton aus dem Video passiert das nicht.
- **Jede erzeugte Datei traegt ein unhoerbares Wasserzeichen** des Modells.
  Das ist so gewollt und weist die Datei als maschinell erzeugt aus.
- **Echter Ton bleibt besser.** Wenn Du beim Filmen ohnehin sprichst, wird
  dieser Ton genommen — er klingt lebendiger als jede Nachbildung. Die
  Stimme ist fuer Diashows gedacht, bei denen niemand gesprochen hat.

## Vom fertigen Reel zum Beitrag

`reelwerk/fertig/` ist eine Sackgasse: der Ordner ist per `.gitignore`
gesperrt, die Automatik sieht ihn nie. Ein Befehl holt das fertige Reel
heraus und legt es dort ab, wo der Planer sucht:

```bash
python src/main.py reel-einpflegen                      # was liegt bereit
python src/main.py reel-einpflegen "Dichtband in jede Ecke.mp4"
```

Was dabei entsteht:

```
content/medien/projekte/dichtband-in-jede-ecke/
    reel.mp4        das Reel, unveraendert kopiert
    cover.jpg       erstes Bild des Videos, mit ffmpeg gezogen
    info.json       Titel, Gewerk, Ort, Hashtag-Satz
```

Ab da laeuft es wie bei jedem anderen Bauvorhaben: der Planer erkennt das
Video und macht daraus einen Beitrag vom Typ `reel`, das Titelbild wird ins
Rasterlayout gebrandet, die Freigabe kommt per Telegram.

| Schalter | Wofuer |
|---|---|
| `--name bad-heiermannstr` | Ordnername, sonst aus dem Dateinamen abgeleitet |
| `--titel "Bad in zwei Wochen"` | Titel in der `info.json`, sonst der Dateiname |
| `--gewerk Badsanierung` | steuert die Beschriftung im Titelbild |
| `--ort Essen` | erscheint im Text unter dem Beitrag |
| `--hashtags bad` | Satz aus `content/hashtags.json` |
| `--titelbild eigenes.jpg` | eigenes Titelbild statt des Auszugs aus dem Video |
| `--sekunde 1.5` | Zeitpunkt des Einzelbilds, falls das erste Bild schwarz ist |
| `--trocken` | nur zeigen, was passieren wuerde |
| `--ueberschreiben` | ein schon eingepflegtes Reel ersetzen |

**Die 20-MB-Grenze.** `content/medien/projekte/` liegt im Repo, `fertig/`
nicht. Deshalb prueft der Befehl die Dateigroesse und bricht ueber 20 MB ab.
Ein Reel aus dem Reel-Werk wiegt rund 8 MB; wer die Grenze reisst, hat eine
unbearbeitete Handydatei erwischt. Die gehoert einmal durch
`REELS-MACHEN.command`.

Eine `info.json`, die Du danach von Hand nachgeschaerft hast, ueberlebt das
erneute Einpflegen desselben Bauvorhabens: der Befehl ergaenzt nur fehlende
Felder.

## Was es nicht kann

Es macht kein Video viral. Es macht ein Video sauber, verständlich und
wiedererkennbar — und sorgt dafür, dass Du oft veröffentlichen kannst, ohne
je etwas zu schneiden. Ob eines durch die Decke geht, hängt am Inhalt.

## Wenn etwas fehlt

Die Arbeitsumgebung einmalig einrichten:

```bash
cd berisabau-social
~/.local/python312/bin/python3.12 -m venv .venv
.venv/bin/pip install jinja2 playwright faster-whisper
.venv/bin/playwright install chromium
```

`ffmpeg` und `ffprobe` liegen als fertige Binaries in `~/.local/ffmpeg`,
verlinkt nach `~/.local/bin`. Kein Homebrew, kein `sudo` nötig.

## Noch nicht gebaut

- Cross-Posting nach TikTok und YouTube Shorts
- `reel-einpflegen` automatisch aus dem Reel-Werk heraus aufrufen, statt von
  Hand nach dem Doppelklick

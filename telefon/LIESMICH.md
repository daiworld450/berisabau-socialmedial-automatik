# Telefonagent

Ein Sprachassistent, der über eine echte Telefonleitung Gespräche führt: deine
geklonte Stimme, Antwort in etwa einer halben Sekunde, Ziel ist ein Rückruf-
termin oder die Erlaubnis, ein Angebot per E-Mail zu schicken.

Getrennt vom Rest des Projekts, weil er nicht in GitHub Actions laufen kann —
ein Telefonat ist eine offene Verbindung und braucht einen Server unter einer
festen Adresse.

---

## Bevor du das einschaltest

**Kaltakquise per Telefon ist in Deutschland rechtswidrig.** Das ist keine
Grauzone und wird durch KI-Offenlegung, Sperrliste oder Zeitfenster nicht
zulässig — diese Bauteile senken das Risiko, sie beseitigen es nicht.

- **Privatpersonen** (§ 7 Abs. 2 Nr. 1 UWG): nur mit vorheriger *ausdrücklicher*
  Einwilligung. Ohne die ist jeder Anruf ein Verstoß. Deshalb sind Mobilnummern
  im Standard gesperrt.
- **Firmen**: nur mit „mutmaßlicher Einwilligung". Die Gerichte legen das eng
  aus. Dass ein Betrieb keine Webseite hat und dein Angebot ihm nützen *könnte*,
  reicht nach der überwiegenden Rechtsprechung **nicht**.
- **Bußgeld** bis 300.000 € (§ 20 UWG, Bundesnetzagentur).
- **Praktisch häufiger**: Abmahnungen durch Wettbewerbszentrale oder Konkurrenz.
  Telefonwerbung gehört zu den meistabgemahnten Themen überhaupt.
- **Art. 50 KI-VO**: Der Angerufene muss erfahren, dass er mit einer KI spricht.
  Der Eröffnungssatz erledigt das und ist fest verdrahtet, nicht vom Sprach-
  modell erzeugt.
- **Anrufe mitschneiden** ist ohne Einwilligung beider Seiten strafbar
  (§ 201 StGB). Der Agent zeichnet deshalb **keinen Ton auf**. Was ins
  Protokoll geht, ist die Texterkennung — auch die ist ein personenbezogenes
  Datum und gehört nicht in fremde Hände.

Der Inhaber hat das am 02.09.2026 in Kenntnis dieser Lage entschieden. Diese
Liste steht hier, damit sie später nicht rekonstruiert werden muss.

**Der risikoärmere Weg mit derselben Technik**: eingehende Anrufe annehmen,
wenn niemand ans Telefon kann, und Rückrufe bei Leuten, die selbst angefragt
haben. Beides ist zulässig, braucht keine Sperrliste und dieselben Bausteine.

---

## Was gebaut ist

| Datei | Aufgabe |
|---|---|
| `einstellungen.py` | Zugänge, Grenzwerte. Liest nur Umgebungsvariablen. |
| `nummern.py` | Rufnummern in eine einheitliche Form bringen (E.164). |
| `sperrliste.py` | Wer widerspricht, wird dauerhaft gesperrt. |
| `zeitfenster.py` | Anrufzeiten, NRW-Feiertage. |
| `protokoll.py` | Nachweis jedes Anrufs, auch der nicht zustande gekommenen. |
| `freigabe.py` | **Das Nadelöhr.** Entscheidet als einzige Stelle, ob gewählt wird. |
| `gespraech.py` | Eröffnung mit KI-Offenlegung, Systemprompt, Abbruchmuster. |
| `agent.py` | Die Gesprächsschleife (Pipecat). |
| `server.py` | Endpunkte, die Twilio anruft. |
| `waehler.py` | Arbeitet eine CSV-Liste ab. |
| `angebot.json` | Was angeboten wird. Hier änderst du den Pitch, nicht im Code. |

Getestet: `python3 -m unittest tests.test_telefon` — 26 Tests, ohne Netz und
ohne dass gewählt wird.

## Die Bremsen, die eingebaut sind

- **Sperrliste ist unwiderruflich.** Es gibt keine `entfernen()`-Funktion. Wer
  eine Nummer wieder freigeben will, greift von Hand in die Datei.
- **Zwei unabhängige Wege zum Abbruch.** Das Sprachmodell hat ein Werkzeug
  `nicht_mehr_anrufen`, und zusätzlich läuft ein Mustervergleich über jeden
  erkannten Satz — noch bevor das Modell ihn sieht. Ein Modell, das eine
  Anweisung übergeht, ist ein Alltagsfall.
- **Geprüft wird zweimal**: beim Zusammenstellen der Liste und in der Sekunde
  vor dem Wählen.
- **Höchstens 2 Versuche je Nummer**, mindestens 14 Tage Abstand.
- **40 Anrufe am Tag**, eine Leitung, 45 Sekunden Pause. Wer schneller wählt,
  erzeugt das Muster, an dem Massenwerbung erkannt wird.
- **Mo–Do 9–17 Uhr, Fr 9–15 Uhr**, Mittagspause 12:30–13:30, keine Feiertage.
- **Mobilnummern gesperrt** (`TELEFON_MOBIL_ERLAUBT=1` hebt das auf — nur für
  nachweislich geschäftliche Nummern).
- **Kein Text auf den Anrufbeantworter.** Twilios Erkennung meldet die Mailbox,
  dann wird aufgelegt.
- **Kein Preis im Gespräch.** Steht im Systemprompt, gilt wie im Social-Teil.
- **Höchstens 3 Minuten je Gespräch.**

## Einrichten

**1. Stimme klonen.** ElevenLabs → Voice Lab → Professional Voice Clone,
30 Minuten sauber eingelesenes Material. Instant Clone mit 2 Minuten geht auch,
klingt am Telefon aber flacher. Die Stimm-ID kommt in `ELEVENLABS_STIMME_ID`.

**2. Nummer besorgen.** Twilio-Konto, deutsche Rufnummer. Twilio verlangt dafür
eine Adressprüfung — mit der Betriebsadresse, nicht privat. Rufnummernunter-
drückung und gefälschte Absender sind nach § 120 TKG verboten.

**3. Umgebungsvariablen** (in `.env`, wie beim Rest des Projekts):

```
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_NUMMER=+49...
TELEFON_BASIS_URL=https://telefon.example.de
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_STIMME_ID=...
OPENAI_API_KEY=...            # der aus dem Social-Teil reicht
```

**4. Installieren und starten:**

```
python3 -m venv .venv-telefon
.venv-telefon/bin/pip install -r telefon/requirements.txt
.venv-telefon/bin/python telefon/server.py
```

Der Server muss unter `TELEFON_BASIS_URL` per HTTPS erreichbar sein, mit
gültigem Zertifikat — Twilio verbindet sich nicht auf ein selbstsigniertes.
Zum Ausprobieren geht `ngrok http 8080`.

**5. Prüfen, ohne zu wählen:**

```
.venv-telefon/bin/python telefon/waehler.py telefon/liste-vorlage.csv --pruefen
```

Zeigt je Zeile, ob sie durchkäme und woran sie sonst scheitert. Wählt nicht.

**6. Trockenlauf:** `TELEFON_TROCKENLAUF=1` — der Wähler geht die Liste durch
und protokolliert, was passiert wäre, ohne eine Verbindung aufzubauen.

**7. Echter Lauf:**

```
.venv-telefon/bin/python telefon/waehler.py meine-liste.csv --hoechstens 10
```

Fang mit `--hoechstens 5` an und hör dir die Mitschriften an, bevor du
hochgehst.

## Anrufliste

CSV mit Kopfzeile, Pflichtspalte ist `nummer`:

```
nummer,betrieb,gewerk,ort,notiz
0208 1234567,Beispiel Fliesen GmbH,Fliesenleger,Mülheim an der Ruhr,keine Webseite
```

Die übrigen Spalten landen im Systemprompt, damit das Gespräch weiß, wen es
anruft. Fehlerhafte Zeilen werden gemeldet und übersprungen, nie geraten.

Eine Bestandsliste von Nummern, die nie angerufen werden sollen (Kunden,
Lieferanten, eigene Anschlüsse, Wettbewerber), lässt sich vorab einspielen:

```python
from pathlib import Path
import sperrliste
sperrliste.einlesen(Path("nicht-anrufen.txt"), grund="Bestandsliste")
```

## Was gesichert werden muss

`telefon/daten/` ist bewusst nicht im Repository — dort liegen Rufnummern, also
personenbezogene Daten. Zwei Dateien darin sind trotzdem wichtig:

- **`sperrliste.json`** — geht sie verloren, rufst du Leute an, die schon
  widersprochen haben. Das ist der Fall, der teuer wird. Eigenes Backup, und
  zwar eines, das den Server überlebt.
- **`anrufe.jsonl`** — dein Nachweis, wenn jemand behauptet, dreimal angerufen
  worden zu sein.

Löschfristen: Kontaktdaten aus abgelehnten Gesprächen gehören zeitnah gelöscht.
Die Sperrliste selbst bleibt — sie existiert gerade, um einen Widerspruch zu
erfüllen, und dafür darf die Nummer aufbewahrt werden.

## Wenn es sich falsch anhört

Das Gefühl „das ist ein Bot" entsteht fast immer an einer von drei Stellen:

- **Zu langsam.** Miss die Zeit vom Satzende bis zum ersten Ton. Über 1 Sekunde
  ist verloren. Kleineres Sprachmodell, `eleven_flash_v2_5` statt Turbo, und
  prüfen, ob der Server nah genug steht (europäische Region, nicht US-Ost).
- **Fällt ins Wort oder reagiert träge.** `stop_secs` in `agent.py` — 0,5 s ist
  der Ausgangswert, für langsame Sprecher 0,7.
- **Redet zu lang am Stück.** Ein Monolog ist am Telefon das sicherste
  Bot-Zeichen. Der Systemprompt begrenzt auf zwei Sätze; wenn das Modell sich
  nicht daran hält, die Anweisung schärfen statt das Modell zu vergrößern.

# Freigabe per Telegram einrichten

Einmalig, etwa 10 Minuten. Kosten: **0 €.**

Ohne diese Einrichtung läuft die Automatik unverändert vollautomatisch weiter
(wie bisher). Mit ihr bekommst du **vor jeder Veröffentlichung** das fertige
Bild im Telegram-Chat und entscheidest per Tastendruck: Freigeben oder
Ablehnen. Bei Ablehnen wird sofort ein neuer Kandidat gerendert und erneut
geschickt – so lange, bis dir einer gefällt oder das Material der Rubrik
aufgebraucht ist.

---

## Wie der Ablauf dann aussieht

1. **Ca. 17:00 Uhr** (anderthalb Stunden vor dem Posttermin): Der Bot schickt
   dir das fertige Bild + den vollständigen Text mit zwei Tasten:
   **✅ Freigeben** / **❌ Ablehnen**.
2. Tippst du **Ablehnen**, kommt innerhalb von rund 10 Minuten ein neuer
   Vorschlag – ein anderes Thema bzw. anderes Foto derselben Rubrik.
3. Tippst du **Freigeben**, wird das Bild veröffentlicht (Instagram und,
   falls eingerichtet, Facebook) – ebenfalls innerhalb von rund 10 Minuten.
4. Antwortest du gar nicht, passiert **nichts** – der planmäßige 18:30-Job
   postet dann nicht automatisch. Das ist Absicht: ohne deine Freigabe geht
   nichts raus.

Dienstags kommt ein Wissens-/Ratgeber-Post (Text), donnerstags ein echtes
Foto von der Baustelle (fällt automatisch auf einen Text-Post zurück, wenn im
Ordner `content/medien/` nichts Frisches liegt).

---

## Schritt 1 – Bot bei @BotFather anlegen

1. In Telegram nach **@BotFather** suchen (offizieller Bot von Telegram
   selbst, blaues Häkchen) und ein Chat öffnen.
2. `/newbot` senden.
3. Einen **Anzeigenamen** vergeben, z. B. `Berisa Bau Freigabe`.
4. Einen **Nutzernamen** vergeben, der auf `bot` enden muss, z. B.
   `BerisaBauFreigabe_bot` (frei wählbar, muss nur einzigartig sein).
5. BotFather antwortet mit einem **Token** – eine Zeichenkette wie
   `123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw`.

**Das ist `TELEGRAM_BOT_TOKEN`.** Wer diesen Token kennt, kann über den Bot
Nachrichten in deinem Namen verschicken – wie ein Passwort behandeln, nicht
weitergeben, nicht in Chat-Verläufe oder Screenshots packen, die geteilt
werden.

---

## Schritt 2 – Eigene Chat-ID herausfinden

Der Bot muss wissen, **wem** er die Vorschläge schicken soll.

1. Den neu angelegten Bot in Telegram suchen (der Nutzername aus Schritt 1)
   und **eine beliebige Nachricht** schicken, z. B. `Start`.
2. Im Browser diese Adresse öffnen (Token aus Schritt 1 einsetzen):

   ```
   https://api.telegram.org/botDEIN-TOKEN/getUpdates
   ```

3. In der Antwort nach `"chat":{"id":` suchen – die Zahl danach ist deine
   **Chat-ID**, z. B. `987654321`. Bei einer Privatperson ist das eine
   normale (positive) Zahl.

**Das ist `TELEGRAM_CHAT_ID`.**

Falls die Antwort leer aussieht (`"result":[]`): Erst nachdem der Bot
mindestens eine Nachricht bekommen hat, taucht hier etwas auf – Schritt 1
(Nachricht an den Bot schicken) nicht vergessen.

---

## Schritt 3 – Werte eintragen

### Lokal (für Tests auf dem eigenen Rechner)

In die `.env` im Projektordner eintragen (Datei existiert noch nicht? Dann
`env-vorlage.txt` kopieren und in `.env` umbenennen):

```
TELEGRAM_BOT_TOKEN=123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
TELEGRAM_CHAT_ID=987654321
```

### Für die Automatik (GitHub Actions)

Als **Secrets** im GitHub-Repository hinterlegen – entweder über die
Repository-Einstellungen (Settings → Secrets and variables → Actions → New
repository secret) oder per Kommandozeile, falls `gh` eingerichtet ist:

```bash
gh secret set TELEGRAM_BOT_TOKEN --body "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
gh secret set TELEGRAM_CHAT_ID --body "987654321"
```

---

## Schritt 4 – Prüfen

```bash
python src/main.py zugang
```

Zeigt jetzt zusätzlich eine Zeile `Telegram : OK  @DeinBotname`. Steht dort
stattdessen ein Fehler, meist einer von zwei Gründen:

- **`Unauthorized`** – Token falsch abgetippt (führende/nachfolgende
  Leerzeichen entfernen).
- **`chat not found`** – Chat-ID falsch, oder dem Bot wurde noch nie eine
  Nachricht geschickt (siehe Schritt 2).

Einen echten Vorschlag von Hand auslösen (postet noch nichts, schickt nur):

```bash
python src/main.py vorschlagen
```

Das Bild sollte innerhalb weniger Sekunden im Chat mit dem Bot ankommen.

---

## Was, wenn ich Telegram wieder abschalten will?

`TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` aus der `.env` und aus den
GitHub-Secrets entfernen (oder leer lassen). Die Automatik erkennt das
automatisch und postet wieder ohne Freigabeschleife – kein Code muss
geändert werden. Die beiden zusätzlichen GitHub-Workflows
(`vorschlagen.yml`, `telegram-abfragen.yml`) brechen dann jeweils mit einer
klaren Meldung ab, ohne etwas kaputtzumachen; sie lassen sich bei Bedarf
auch einfach löschen oder in den Repository-Einstellungen deaktivieren
(Actions → betroffener Workflow → „Disable workflow").

# Drei ungenutzte GitHub-Secrets aufräumen

Repo: `daiworld450/berisabau-socialmedial-automatik` (öffentlich)
Geprüft am: 01.09.2026
Ausführen darf das nur der Inhaber. Diese Datei löscht nichts.

---

## Warum überhaupt

Der Ads-Kanal ist am 28.08.2026 in ein eigenes, privates Repo umgezogen. Die
Python-Module dazu (`ads_news.py`, `ads_stats.py`, `ads_empfehlung.py`,
`ads_verlauf.py`, `google_ads_client.py`) liegen seitdem nicht mehr in
`src/`. Die Secrets von damals stehen aber weiter im öffentlichen Repo.

Ein Secret in einem öffentlichen Repo ist zwar nicht lesbar, aber jeder
Workflow-Lauf und jede Action mit `secrets`-Zugriff kommt daran. Was niemand
braucht, gehört weg.

---

## Befund je Secret

Geprüft mit `grep -rn "<NAME>" .github/workflows/ src/`.

### 1. `ANTHROPIC_API_KEY` — kein Workflow liest es

Kein Treffer in `.github/workflows/`.

Im Code lesen es `src/config.py:106`, `src/texter.py:147` und
`src/ki_schreiber.py`. Alle drei laufen aber ausschließlich von Hand am
eigenen Rechner (`main.py ki-thema`, KI-Captions), und dort kommt der
Schlüssel aus der lokalen `.env`, nicht aus dem Repo-Secret.

**Löschbar, ohne vorher etwas zu ändern.**

### 2. `TELEGRAM_CHAT_ID_ADS` — kein Workflow liest es

Kein Treffer in `.github/workflows/`.

`src/config.py:87` liest es, `telegram_bot.aktiv_ads()` hängt daran. Da kein
Workflow es setzt, ist `aktiv_ads()` in GitHub Actions immer falsch. Der
Ads-Zweig in `main.py telegram-abfragen` läuft dort also ohnehin nie an.

**Löschbar, ohne vorher etwas zu ändern.**

### 3. `TELEGRAM_BOT_TOKEN` — ein Workflow liest es noch

Treffer: `.github/workflows/telegram-abfragen.yml:55`

```yaml
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
```

`src/config.py:86` macht daraus `TELEGRAM_BOT_TOKEN_ADS` (historischer Name).
Wirkung hat das trotzdem keine: `aktiv_ads()` verlangt Token **und**
`TELEGRAM_CHAT_ID_ADS`, und letzteres setzt kein Workflow (siehe Punkt 2).
Der Ads-Abruf in `cmd_telegram_abfragen` startet damit nie.

**Erst die Zeile 55 entfernen, dann das Secret löschen.** Sonst zeigt der
Workflow bei jedem Lauf einen leeren Wert an einer Stelle, die dokumentiert,
dass dort etwas hingehört.

Die Instagram-Freigabe hängt an `TELEGRAM_BOT_TOKEN_BERISABAUSOCIALMEDIA`,
einem anderen Secret. Das bleibt.

---

## Schritte

**Schritt 1 — die Workflow-Zeile entfernen** (nur für Punkt 3 nötig)

In `.github/workflows/telegram-abfragen.yml` Zeile 55 löschen:

```yaml
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
```

Danach committen und pushen.

**Schritt 2 — die Secrets löschen**

```bash
cd ~/Desktop/mein-assistent/berisabau-social

# Vorher ansehen, was da liegt:
gh secret list --repo daiworld450/berisabau-socialmedial-automatik

gh secret delete ANTHROPIC_API_KEY   --repo daiworld450/berisabau-socialmedial-automatik
gh secret delete TELEGRAM_CHAT_ID_ADS --repo daiworld450/berisabau-socialmedial-automatik
gh secret delete TELEGRAM_BOT_TOKEN   --repo daiworld450/berisabau-socialmedial-automatik

# Nachher prüfen:
gh secret list --repo daiworld450/berisabau-socialmedial-automatik
```

**Schritt 3 — die Schlüssel selbst zurückziehen**

Löschen im Repo heißt nur, dass GitHub den Wert vergisst. Der Schlüssel bleibt
gültig. Wer ihn schon kopiert hat, kann ihn weiter benutzen. Also zusätzlich:

- `ANTHROPIC_API_KEY`: in der Anthropic-Konsole unter API Keys widerrufen.
- `TELEGRAM_BOT_TOKEN`: bei `@BotFather` über `/revoke` erneuern, falls der
  Bot noch läuft. Wird er nicht mehr gebraucht, `/deletebot`.
- `TELEGRAM_CHAT_ID_ADS` ist kein Geheimnis, nur eine Chat-Nummer. Nichts zu
  widerrufen.

---

## Was danach zu prüfen ist

Ein Lauf von `telegram-abfragen.yml` von Hand (`workflow_dispatch`). Er läuft
seit dem 01.09.2026 nicht mehr im Takt, also fällt ein Fehler dort sonst
niemandem auf. Erwartete Ausgabe unverändert: entweder „Keine neuen
Antworten." oder ein verarbeiteter Tastendruck.

---

## Stand 06.09.2026

**Schritt 1 erledigt.** Die Zeile `TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}`
ist aus `.github/workflows/telegram-abfragen.yml` entfernt und über die
GitHub-API live (Commit `800d642`). Der Befund oben wurde vorher neu geprüft:
`ANTHROPIC_API_KEY` und `TELEGRAM_CHAT_ID_ADS` haben weiterhin keinen Treffer
in `.github/workflows/`.

**Schritt 2 steht noch aus** — die Secrets sind bewusst nicht gelöscht, bis die
Ads-Sitzung bestätigt, dass sie den Bot-Token und die Chat-ID nicht mehr aus
diesem Repo bezieht. Bereichsgrenze vom 02.09.

**Nachtrag zur Prüfung am Ende dieser Datei:** Ein Lauf von
`telegram-abfragen.yml` von Hand endet seit dem 01.09. **rot**, und das ist
richtig so. Telegram lässt Webhook und `getUpdates` nicht gleichzeitig zu, und
den Webhook hält seit dem 30.08. der Cloudflare-Worker. Die Meldung lautet
`Conflict: can't use getUpdates method while webhook is active`. Bis zum 01.09.
wurde dieser Fehler verschluckt und der Lauf meldete Erfolg — genau deshalb
blieb der Konflikt wochenlang unbemerkt. Der Notweg ist nur nach einem
`deleteWebhook` benutzbar. Ein roter Lauf hier ist kein Defekt.

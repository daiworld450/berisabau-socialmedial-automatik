# Google-Ads-Update-Kanal einrichten

Einmalig, etwa 10 Minuten (die Google-Ads-Zugangsdaten liegen dank
google-ads-mcp schon vor). Kosten: **0 €** (der einzige laufende Posten ist
der tägliche Claude-Aufruf für den News-Filter, im Cent-Bereich pro Monat).

Ein separater privater Telegram-Kanal, der dich

- **täglich** über relevante Google-Ads-Neuerungen auf dem Laufenden hält
  (nur Originalquellen, gefiltert nach Relevanz für Suchkampagnen/Performance
  Max/Budget/lokale Anzeigen – siehe `src/ads_news.py`),
- **dienstags** eine Kampagnentabelle der letzten 7 Tage schickt,
- **donnerstags** einen einzelnen, zahlenbasierten Optimierungsvorschlag.

Die bestehende Instagram-Freigabe über Telegram bleibt komplett unberührt –
gleicher Bot, aber eine zweite, eigene Chat-ID.

---

## Schritt 1 – Kanal anlegen und Bot hinzufügen

1. Telegram-App → Menü → **Neuer Kanal**.
2. Namen vergeben (z. B. „Google Ads Update"), Sichtbarkeit **Privat**.
3. Kanal öffnen → Kanalname antippen → **Administratoren** →
   **Administrator hinzufügen** → den bestehenden Bot suchen (Name aus
   `docs/04-TELEGRAM-EINRICHTEN.md`, Schritt 1) → hinzufügen. Das Recht
   „Nachrichten posten" reicht.
4. Eine beliebige Testnachricht in den Kanal schreiben (nötig, damit der
   Bot überhaupt ein Update zu diesem Chat bekommt).

## Schritt 2 – Chat-ID herausfinden

Kanal-Chat-IDs sind negative Zahlen (z. B. `-1001234567890`), anders als bei
Privatchats. Im Browser (Token aus Schritt 1 der Telegram-Anleitung):

```
https://api.telegram.org/botDEIN-TOKEN/getUpdates
```

In der Antwort nach `"channel_post":{"chat":{"id":` suchen – die Zahl
danach (inklusive Minuszeichen) ist `TELEGRAM_CHAT_ID_ADS`.

## Schritt 3 – Werte eintragen

### Lokal (`.env`)

```
TELEGRAM_CHAT_ID_ADS=-1001234567890

GOOGLE_ADS_DEVELOPER_TOKEN=…
GOOGLE_ADS_CLIENT_ID=…
GOOGLE_ADS_CLIENT_SECRET=…
GOOGLE_ADS_REFRESH_TOKEN=…
GOOGLE_ADS_CUSTOMER_ID=…
GOOGLE_ADS_LOGIN_CUSTOMER_ID=…
```

Die sechs `GOOGLE_ADS_*`-Werte stehen schon in `google-ads-mcp/.env` –
einfach von dort herüberkopieren.

`ANTHROPIC_API_KEY` wird für den täglichen News-Filter mitverwendet (steht
vermutlich schon in der `.env`, siehe Abschnitt „KI schreibt Themen").

### Für die Automatik (GitHub Actions)

```bash
gh secret set TELEGRAM_CHAT_ID_ADS --body "-1001234567890"
gh secret set GOOGLE_ADS_DEVELOPER_TOKEN --body "…"
gh secret set GOOGLE_ADS_CLIENT_ID --body "…"
gh secret set GOOGLE_ADS_CLIENT_SECRET --body "…"
gh secret set GOOGLE_ADS_REFRESH_TOKEN --body "…"
gh secret set GOOGLE_ADS_CUSTOMER_ID --body "…"
gh secret set GOOGLE_ADS_LOGIN_CUSTOMER_ID --body "…"
```

`TELEGRAM_BOT_TOKEN` und `ANTHROPIC_API_KEY` sind vermutlich schon als
Secret hinterlegt (Instagram-Freigabe bzw. `ki-thema`).

---

## Schritt 4 – Prüfen

```bash
python src/main.py zugang
```

Zeigt jetzt zusätzlich `Ads-Kanal` und `Google Ads`. Danach von Hand
auslösen (postet in den neuen Kanal):

```bash
python src/main.py ads-news         # täglicher Neuigkeiten-Check
python src/main.py ads-kurzcheck    # Kampagnentabelle
python src/main.py ads-empfehlung   # Optimierungsvorschlag
```

Solange `python src/main.py telegram-abfragen` regelmäßig läuft (schon per
Cron aktiv, siehe `telegram-abfragen.yml`), funktionieren auch die drei
Tasten unter jeder Meldung:

- **📌 Merken** – merkt sich die Meldung, sonst keine Wirkung.
- **ℹ️ Mehr dazu** – schickt die ausführliche Fassung mit Originallink als
  eigene Nachricht.
- **🚫 Ignorieren** – das Thema kommt nicht wieder, auch nicht in
  abgewandelter Form über eine andere Quelle.

## Was die einzelnen Automatik-Läufe tun

| Workflow | Wann | Befehl |
|---|---|---|
| `ads-news-taeglich.yml` | täglich ca. 07:00 | `ads-news` |
| `ads-dienstag-kurzcheck.yml` | dienstags ca. 08:00 | `ads-kurzcheck` |
| `ads-donnerstag-empfehlung.yml` | donnerstags ca. 08:00 | `ads-empfehlung` |
| `telegram-abfragen.yml` (bestehend) | alle 10 Minuten | wertet u. a. die drei Tasten aus |

## Wichtig zu wissen

- **Nur lesend.** Keiner dieser Befehle ändert irgendetwas im Google-Ads-Konto
  – weder Budget noch Gebote noch Kampagnenstatus. Das ist bewusst so
  begrenzt (siehe `src/google_ads_client.py`).
- **Solange der Basic-Access-Antrag bei Google noch läuft** (siehe
  `google-ads-mcp/README.md`), liefert `ads-kurzcheck`/`ads-empfehlung` einen
  Testkonto-Fehler statt echter Zahlen. `ads-news` ist davon nicht betroffen
  – der News-Check braucht keinen Google-Ads-API-Zugriff, nur die
  öffentlichen Google-Quellen und den Claude-Schlüssel.
- **Richtlinienänderungen** werden aktuell nur über die Google-Ads-Hilfe-
  Ankündigungsseite miterfasst, nicht über eine eigene Richtlinien-Quelle –
  einzelne Policy-Updates haben keine stabile, vorhersagbare URL. Reicht das
  nicht, lässt sich `QUELLEN_SEITEN` in `src/ads_news.py` leicht um eine
  konkrete Policy-Update-URL ergänzen, sobald eine feststeht.

## Was, wenn ich den Kanal wieder abschalten will?

`TELEGRAM_CHAT_ID_ADS` aus der `.env` und aus den GitHub-Secrets entfernen.
Alle drei `ads-*`-Befehle melden dann klar „nicht eingerichtet" und brechen
sauber ab, ohne etwas kaputtzumachen. Die drei Workflow-Dateien lassen sich
bei Bedarf zusätzlich in den Repository-Einstellungen deaktivieren
(Actions → betroffener Workflow → „Disable workflow").

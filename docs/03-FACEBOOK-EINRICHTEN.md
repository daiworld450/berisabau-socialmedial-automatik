# Facebook dazuschalten

Einmalig, etwa 20 Minuten. Kosten: **0 €.**

Jeder Beitrag geht dann automatisch auch auf **facebook.com/BerisaBau** –
mit einem eigenen Text, nicht als Instagram-Kopie.

---

## Was anders ist als bei Instagram

| | Instagram | Facebook-Seite |
|---|---|---|
| Schnittstelle | `graph.instagram.com` | `graph.facebook.com` |
| Token | Instagram-Token | **eigener Seiten-Token** |
| Zugangsweg | Instagram-Login | Facebook-Login |
| Links im Text | nicht klickbar | **klickbar** |
| Hashtags | 12, bringen Reichweite | 2, mehr wirkt deplatziert |
| Privates Profil | – | **geht nicht**, nur Seiten |

Die beiden Zugänge sind unabhängig. Fällt einer aus, läuft der andere weiter.

---

## Zwei Wege zum Seiten-Token

| | Weg A – schnell | Weg B – Business Manager |
|---|---|---|
| Dauer | 10 Minuten | 20 Minuten |
| Token hängt an | deinem persönlichen Account | dem Business selbst |
| Läuft ab, wenn... | du die App-Berechtigung entziehst oder dein Account Probleme bekommt | praktisch nie – der System-User ist unabhängig von einer Person |
| Empfehlung | zum Ausprobieren | **für den Dauerbetrieb** |

Beide Wege liefern am Ende dieselben zwei Werte (`FB_PAGE_ID` und
`FB_PAGE_TOKEN`) – der Rest der Einrichtung ist identisch. Weg A steht in
Schritt 2 bis 4, Weg B direkt danach als Alternative.

---

## Schritt 1 – Voraussetzungen prüfen

Die Facebook-Seite gibt es bereits: **facebook.com/BerisaBau**.

Nötig ist außerdem, dass du dort **Administrator** bist. Prüfen unter
Seite → Einstellungen → Seitenzugriff.

Für Weg B zusätzlich: ein Business im
[Business Manager](https://business.facebook.com), mit der Facebook-Seite
als zugeordnetem Asset. Existiert noch keines, legt Meta es beim ersten
Aufruf von business.facebook.com in zwei Klicks an.

---

## Schritt 2 – Berechtigungen zur Meta-App hinzufügen

Du nutzt bereits eine Meta-App für Instagram (siehe
[02-INSTAGRAM-EINRICHTEN.md](02-INSTAGRAM-EINRICHTEN.md)). Dieselbe App wird
jetzt um die Facebook-Seite erweitert.

1. <https://developers.facebook.com/apps> → deine App öffnen
2. **Produkt hinzufügen → Facebook Login → Einrichten**
3. Unter **App-Rollen → Rollen** sicherstellen, dass dein Konto
   Administrator ist

Benötigte Berechtigungen:

- `pages_show_list` – die eigenen Seiten auflisten
- `pages_manage_posts` – Beiträge erstellen
- `pages_read_engagement` – Beiträge und Kennzahlen lesen

> **App-Prüfung ist auch hier nicht nötig**, solange du nur deine eigene Seite
> bespielst und in der App als Administrator eingetragen bist.

---

## Schritt 3 – Nutzer-Token holen

1. <https://developers.facebook.com/tools/explorer> öffnen
2. Oben rechts deine App auswählen
3. **User Token** wählen, die drei Berechtigungen oben anhaken
4. **Generate Access Token** → mit Facebook anmelden und bestätigen

Dieser Token ist kurzlebig. Er dient nur dazu, im nächsten Schritt den
Seiten-Token zu holen – und der ist dauerhaft.

---

## Schritt 4 – Seiten-Token holen

Im Projektordner:

```bash
python src/main.py fb-seiten --token DEIN_NUTZER_TOKEN
```

Ausgabe etwa:

```
Seiten an diesem Zugang:

  Berisa Bau
    FB_PAGE_ID    = 1234567890123456
    FB_PAGE_TOKEN = EAAG...
```

Beide Werte in die `.env` übernehmen:

```
FB_PAGE_ID=1234567890123456
FB_PAGE_TOKEN=EAAG...
```

> **Der Seiten-Token läuft normalerweise nicht ab**, solange er aus einem
> langlebigen Nutzer-Token stammt und du Administrator bleibst. Das ist der
> angenehme Unterschied zum Instagram-Token, der alle 60 Tage erneuert wird.

Verbindung prüfen:

```bash
python src/main.py zugang
```

Erwartet:

```
Instagram: OK  @berisabau · Kontotyp BUSINESS · 13 Beiträge
Facebook : OK  Berisa Bau · 42 Follower · https://www.facebook.com/BerisaBau
```

---

## Schritt 4b – Alternative: Business Manager / System-User (empfohlen)

Nur nötig, wenn du Weg B statt Weg A gehst – dann Schritt 3 und 4 überspringen.

Der Unterschied: Statt eines Tokens, der an deinem persönlichen
Facebook-Account hängt, erstellst du einen **System-User** im Business
Manager. Das ist der Weg, den Meta selbst für Server-zu-Server-Automatik
empfiehlt – der Token ist an das Business gebunden, nicht an eine Person,
und läuft praktisch nicht ab.

1. [business.facebook.com](https://business.facebook.com) öffnen →
   **Business-Einstellungen**
2. **Benutzer → System-User** → **Hinzufügen**
   Name z. B. `berisabau-automatik`, Rolle **Mitarbeiter** reicht.
3. Den System-User anklicken → **Assets zuweisen** → **Seiten** →
   die Facebook-Seite auswählen → Rolle **Inhalte verwalten**
4. **Neues Token generieren** beim System-User:
   - App: deine Meta-App aus Schritt 2
   - Berechtigungen: `pages_show_list`, `pages_manage_posts`,
     `pages_read_engagement`
   - **Nie ablaufend** ist hier Standard, keine zusätzliche Einstellung nötig
5. Das generierte Token direkt als `FB_PAGE_TOKEN` verwenden – es ist bereits
   ein Seiten-Token, der Umweg über `fb-seiten` entfällt.
6. Die Seiten-Kennung für `FB_PAGE_ID` steht auf der Seite selbst unter
   **Seiteneinstellungen → Seiteninformationen**, oder abrufen mit:

   ```bash
   python src/main.py fb-seiten --token DAS_SYSTEM_USER_TOKEN
   ```

Ab hier identisch mit Weg A: beide Werte in die `.env`, dann
`python src/main.py zugang` zum Prüfen.

---

## Schritt 5 – Automatik

Im GitHub-Repository unter **Settings → Secrets and variables → Actions**
zwei weitere Secrets anlegen:

| Name | Wert |
|---|---|
| `FB_PAGE_ID` | die Seiten-Kennung aus Schritt 4 |
| `FB_PAGE_TOKEN` | der Seiten-Token aus Schritt 4 |

Mehr ist nicht nötig. Der Workflow (zweimal wöchentlich, siehe
[README](../README.md)) erkennt selbst, ob Facebook eingerichtet ist, und
postet dann automatisch mit.

Einzelnen Tag bewusst nur auf Instagram:

```bash
python src/main.py heute --posten --kein-facebook
```

---

## Was auf Facebook wie ankommt

| Beitragsart auf Instagram | Auf Facebook |
|---|---|
| Einzelbild | Foto-Beitrag |
| Carousel | Beitrag mit mehreren Bildern |
| Reel | Video-Beitrag auf der Seite |

Der Text ist ein anderer: Auf Facebook steht die Website als **klickbarer
Link** und die Telefonnummer direkt im Beitrag – beides bringt auf Instagram
nichts, weil dort keine Links im Text funktionieren. Dafür entfällt der große
Hashtag-Block.

Ansehen lässt sich beides nebeneinander:

```bash
python src/main.py heute
```

Die Instagram-Fassung liegt in `out/*.txt`, die Facebook-Fassung daneben
in `out/*.facebook.txt`.

---

## Wenn etwas klemmt

| Meldung | Ursache |
|---|---|
| Code **190** | Token abgelaufen oder zurückgezogen → bei Weg A Schritt 3 und 4 wiederholen; bei Weg B (System-User) prüfen, ob die Seite noch als Asset zugewiesen ist |
| Code **200** | Berechtigung fehlt → `pages_manage_posts` prüfen. Steht dabei *„not available … need to be approved by App Review“*, liegt es nicht am Token, sondern am App-Modus – siehe unten |
| Code **803** | Falsche Seiten-Kennung |
| „(#100) No permission" | Du bist nicht Administrator der Seite |

Der Instagram-Beitrag geht unabhängig davon raus. Ein Facebook-Fehler lässt
den Tageslauf nicht scheitern – er wird gemeldet und protokolliert.

---

## Stand 03.09.2026: Facebook postet nicht, Instagram schon

Beim Freigabelauf um 19:32 Uhr meldete Facebook:

```
(#200) The permission(s) pages_manage_posts are not available.
It could because either they are deprecated or need to be approved
by App Review.
```

Die Meldung legt eine fehlende App-Überprüfung nahe. Gemessen wurde etwas
anderes. `debug_token` gibt für den hinterlegten Seiten-Token aus:

```
Typ           : PAGE
Gültig        : ja        (läuft ab am 27.10.2026)
Berechtigungen: pages_show_list, business_management, instagram_basic,
                instagram_content_publish, pages_read_engagement,
                public_profile
```

Es fehlt genau eine Berechtigung: **`pages_manage_posts`**. Der Token wurde
ohne sie erzeugt. Deshalb geht Instagram durch — `instagram_content_publish`
ist vorhanden — und Facebook nicht. Eine App-Überprüfung bei Meta ist dafür
nicht nötig: einem App-Administrator gibt Meta die Berechtigung auch im
Entwicklungsmodus, sie muss beim Erzeugen nur angehakt sein.

**Reparatur, ein Doppelklick:** `FACEBOOK-TOKEN-ERNEUERN.command` im
Projektordner. Das Skript öffnet den Zugangs-Tester, nimmt den neuen
Schlüssel verdeckt entgegen, prüft ihn gegen genau diese Berechtigung,
wandelt einen persönlichen Schlüssel bei Bedarf in den Seiten-Schlüssel um
und hinterlegt ihn in GitHub. Danach bietet es an, den liegengebliebenen
Beitrag nachzureichen.

**Einen Beitrag nachreichen**, der schon auf Instagram steht:

```bash
gh workflow run facebook-nachholen.yml -R daiworld450/berisabau-socialmedial-automatik -f datum=2026-09-03
```

Instagram wird dabei nicht angefasst. Ein zweiter Freigabelauf würde den
Beitrag dort ein zweites Mal veröffentlichen — deshalb dieser eigene Weg.

Prüfen, welche Berechtigungen der Token gerade trägt:

```bash
gh workflow run facebook-pruefen.yml -R daiworld450/berisabau-socialmedial-automatik
```

Bis zur Reparatur läuft Instagram allein weiter. Der Facebook-Fehler färbt
keinen Lauf rot, er wird nur gemeldet.

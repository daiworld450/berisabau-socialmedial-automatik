# Instagram einrichten – einmalig, danach läuft es allein

Geschätzte Dauer: **30–45 Minuten.** Kosten: **0 €.**

Wir nutzen die **offizielle Instagram Graph API**. Nicht die inoffiziellen
Bibliotheken wie instagrapi – die verstoßen gegen die Nutzungsbedingungen
und führen regelmäßig zu Kontosperren. Bei einem Konto, an dem Aufträge
hängen, ist das kein akzeptables Risiko.

---

## Wichtig vorab

**Für Ihr eigenes Konto brauchen Sie keine Meta-App-Prüfung.** Die
mehrwöchige „App Review" gilt nur, wenn eine App auf Konten *fremder*
Nutzer posten soll. Solange Sie nur @berisabau bespielen, reicht der
Entwicklermodus – und der ist sofort nutzbar.

**Was die API kann und was nicht:**

| | |
|---|---|
| Einzelbild in den Feed | ✅ |
| Carousel (mehrere Bilder) | ✅ |
| Reels (Video) | ✅ |
| Stories | ✅ |
| Beitrag posten, wenn @berisabau ein Profikonto ist | ✅ |
| Beiträge mit privatem Konto | ❌ – Umstellung nötig |
| Mehr als 25 API-Beiträge in 24 Stunden | ❌ – wir brauchen einen |

---

## Schritt 1 – Instagram auf Profikonto umstellen

@berisabau ist aktuell ein normales Konto. Ohne Umstellung geht gar nichts.

1. Instagram-App → Profil → Menü (☰) → **Konto­typ und Tools**
2. **Auf professionelles Konto umstellen**
3. Kategorie: **Bauunternehmen** oder **Lokales Unternehmen**
4. Typ: **Unternehmen** (nicht „Creator" – Unternehmen passt besser
   und schaltet die Kontaktschaltflächen frei)

Nebeneffekt, den Sie ohnehin wollen: Sie bekommen Statistiken, den
Kontakt-Button und die Möglichkeit, Anfragen sauber zu verwalten.

---

## Schritt 2 – Meta-App anlegen

1. <https://developers.facebook.com/> öffnen, mit Ihrem Facebook-Konto
   anmelden. Falls Sie noch kein Entwicklerkonto haben, wird es hier
   in zwei Klicks erstellt (kostenlos).
2. **Meine Apps → App erstellen**
3. Anwendungsfall: **Andere** → App-Typ: **Business**
4. Name z. B. `Berisa Bau Posting`, Kontakt-E-Mail eintragen.

---

## Schritt 3 – Instagram-Produkt hinzufügen

1. In der App-Übersicht: **Produkt hinzufügen → Instagram → Einrichten**
2. Variante **„Instagram API mit Instagram Login"** wählen.
   Diese Variante braucht **keine** verknüpfte Facebook-Seite.
3. Unter **API-Einrichtung mit Instagram-Login**:
   - **Instagram-Konto hinzufügen** → mit @berisabau anmelden und die
     Berechtigungen bestätigen
   - Berechtigungen, die aktiv sein müssen:
     `instagram_business_basic`, `instagram_business_content_publish`

---

## Schritt 4 – Zugangsdaten holen

Auf derselben Seite finden Sie:

- **Instagram-Konto-ID** – eine lange Zahl. Das ist Ihr `IG_USER_ID`.
- **Token generieren** – erzeugt einen Zugriffstoken.

Der so erzeugte Token ist bereits ein **langlebiger Token (60 Tage)**.
Das ist Ihr `IG_ACCESS_TOKEN`.

> Behandeln Sie den Token wie ein Passwort. Wer ihn hat, kann in Ihrem
> Namen posten. Er gehört in die `.env` bzw. in die GitHub-Secrets –
> niemals in eine Datei, die ins Git wandert.

---

## Schritt 5 – Bilder öffentlich erreichbar machen

Instagram lädt das Bild **selbst** von einer URL herunter. Ein Pfad auf
Ihrem Rechner funktioniert nicht. Das ist erfahrungsgemäß die häufigste
Fehlerquelle überhaupt.

Projekt in ein **öffentliches** GitHub-Repository hochladen, z. B.
`berisabau-social`. Dann haben Sie zwei Wege:

**Weg A – `raw.githubusercontent.com` (empfohlen).** Kein Einrichten, keine
Wartezeit: die Datei ist direkt nach dem Push abrufbar.

```
MEDIA_BASE_URL=https://raw.githubusercontent.com/IHR-NAME/berisabau-social/main/docs/posts
```

**Weg B – GitHub Pages.** Settings → Pages → Deploy from a branch,
Branch `main`, Ordner `/docs`. Braucht nach jedem Push 30–120 Sekunden
Bauzeit, dafür schönere Adressen.

```
MEDIA_BASE_URL=https://IHR-NAME.github.io/berisabau-social/posts
```

> **Wichtig:** Das Repository muss öffentlich sein, sonst kommt Instagram
> nicht an die Bilder. Ihre Zugangsdaten sind davon nicht betroffen – die
> liegen in GitHub-Secrets und in der gitignorierten `.env`, nie im Code.
> Legen Sie trotzdem nichts Vertrauliches in `docs/`.

---

## Schritt 6 – Lokal eintragen und testen

`env-vorlage.txt` als `.env` kopieren und ausfüllen:

```
IG_USER_ID=17841400000000000
IG_ACCESS_TOKEN=IGAAxxxxxxxxxxxxxxxx
MEDIA_BASE_URL=https://ihr-name.github.io/berisabau-social/posts
```

Verbindung prüfen:

```bash
python src/main.py zugang
```

Erwartete Ausgabe:

```
OK  @berisabau · Kontotyp BUSINESS · 13 Beiträge
Kontingent: 0 von 25 genutzt
```

Kommt hier ein Fehler, stimmt eine der drei Angaben nicht – posten Sie
noch nichts, sondern klären Sie erst das.

---

## Schritt 7 – Automatik scharf schalten

Im GitHub-Repository unter **Settings → Secrets and variables → Actions**
drei Secrets anlegen:

| Name | Wert |
|---|---|
| `IG_USER_ID` | Ihre Instagram-Konto-ID |
| `IG_ACCESS_TOKEN` | Ihr Token |
| `MEDIA_BASE_URL` | Ihre Pages-URL + `/posts` |

Optional, damit sich der Token selbst erneuert:

| Name | Wert |
|---|---|
| `GH_PAT` | Personal Access Token mit Recht „Secrets: Read and write" |

Optional unter **Variables** (nicht Secrets – das sind keine Geheimnisse):

| Name | Wirkung |
|---|---|
| `FREIGABE_PFLICHT` | `true` = nur freigegebene Themen werden gepostet |
| `MAX_POSTS_24H` | eigene Sicherheitsgrenze, Standard 5 |

Danach läuft `.github/workflows/taeglich-posten.yml` zweimal wöchentlich
(Dienstag/Donnerstag, 18:30 Uhr – siehe README).
Erster Test von Hand: **Actions → Zweiwöchentlicher Instagram-Post →
Run workflow**, dabei zuerst **„Nur Bild erzeugen"** anhaken. Erst wenn
das Ergebnis passt, ohne Haken laufen lassen.

---

## Token läuft ab – was dann?

Der Token gilt 60 Tage. Der Workflow `token-erneuern.yml` verlängert ihn
am 1. und 15. jeden Monats automatisch, solange er noch gültig ist.

Ist er doch einmal abgelaufen: Schritt 4 wiederholen, neuen Token in die
`.env` und in die GitHub-Secrets eintragen. Dauert zwei Minuten.

---

## Grenzen, die Sie kennen sollten

- **Veröffentlichungs-Kontingent.** Meta nennt je nach Doku-Stand 25 oder
  100 Beiträge je 24 Stunden. Das System fragt den tatsächlichen Wert vor
  jedem Post live ab und begrenzt zusätzlich auf `MAX_POSTS_24H` (Standard 5).
  Bei zwei Beiträgen pro Woche spielt das ohnehin keine Rolle.
- **200 API-Aufrufe pro Stunde.** Ebenfalls unkritisch.
- **Bildformat:** JPEG, Seitenverhältnis zwischen 4:5 und 1,91:1.
  Die Vorlagen liefern 1080×1350 (4:5) – das ist der Idealfall.
- **Keine Hashtags im ersten Kommentar per API.** Sie stehen deshalb
  direkt in der Bildunterschrift.
- **Kein Auto-Tagging von Orten oder Personen** über diesen Weg.

# Markenanalyse Berisa Bau

Stand: 16.08.2026 · Grundlage: berisabau.de, die Google-Ads-Landingpage und
das Instagram-Profil @berisabau.

---

## 1. Website berisabau.de

**Technik:** Laravel + Livewire, Bootstrap-Grundgerüst, Cookiebot,
Danova-Widget. Ein Ads-spezifischer Ableger liegt lokal unter
`berisabau-landingpage/index.html` (bewusst `noindex`).

**Struktur:** Startseite · `/services` (6 Leistungen) · `/projects`
(5 Referenzen) · `/about` · `/contact` · `/partnership` · Rechtstexte.

**Design-Tokens, ausgelesen aus `build/assets/app-BUxTJ3zJ.css`:**

| Element | Wert |
|---|---|
| Primärfarbe | `#D00000` (identisch mit dem Logo) |
| Zweitfarben | `#0071FF` / `#1032CF` (Blau), `#FDC448` (Gelb) |
| Dunkelflächen | `#0B0B0F`, `#101018`, `#141414` |
| Grautöne | `#5D6570`, `#2A2D31` |
| Signalgrün | `#38D17A` (Haken, Vertrauenspunkte) |
| Headline-Schrift | **Rajdhani** 500/600/700, kondensiert, Laufweite +0,5 px |
| Fließtext | **Rubik** 400/500/600, Zeilenhöhe 1,55 |
| Radien | 14 px Elemente, 22 px Karten, 500 px Pillen |
| Signatur-Element | roter, um 8° geschrägter Balken hinter einem Schlüsselwort |
| Hintergrund-Signatur | dunkler Verlauf + 56-px-Raster, radial ausmaskiert |

**Kontakt:** Heiermannstr. 5, 45475 Mülheim an der Ruhr ·
+49 1556 5535 408 · info@berisabau.de

**Leistungen:** Sanierung & Renovierung, Fliesen & Bodenleger, Maler &
Lackierarbeiten, Mikrozement, Sanitärtechnik, Smart Home. Dazu Trockenbau,
Elektro, Badsanierung, Heizung, Dach- und Außenanlagen.

**Tonalität:** sachlich, konkret, Sie-Anrede. Wiederkehrende Versprechen:
„aus einer Hand", „termintreu", „ein Ansprechpartner", „dokumentiert",
„Gewährleistung nach BGB/VOB", „Antwort in 24 Stunden". Keine Preisangaben,
keine Superlative.

---

## 2. Instagram @berisabau

| Kennzahl | Wert |
|---|---|
| Profilname | Damir Berisa |
| Follower | 61 |
| Beiträge | 13 |
| Highlights | FAQ, Erfolge |
| Letzter Beitrag | 17.07.2026 |

**Bio:**
```
🧱 Sanierung & Renovierung
🏠 Wohnungen • Häuser • Gewerbe
📍 Mülheim an der Ruhr
📞 Kostenlose Anfrage ↓
berisabau.de
```

**Beitragsverlauf:** Dez 2025 (2), Feb, Mär, Apr (3), Mai, Jun (2), Jul (2).
Überwiegend Reels, dazwischen Foto-Carousels.

### Befund

Das Profil zeigt gute Arbeit, aber es ist **nicht als Marke erkennbar**:

1. **Keine visuelle Klammer.** Rohe Handyfotos und -videos ohne Logo, ohne
   Farbe, ohne Typografie. Nichts verbindet die Kacheln miteinander –
   und nichts verbindet sie mit berisabau.de.
2. **Kein Absender im Bild.** Wer ein Reel über die Suche findet, sieht kein
   Logo, keinen Ort, keine Handlungsaufforderung. Der Weg zur Anfrage fehlt.
3. **Unregelmäßig.** Ein bis drei Beiträge im Monat, mit Lücken. Der
   Algorithmus belohnt Kontinuität; vier Wochen Pause kosten Reichweite.
4. **Gemischte Formate.** 9:16 neben 4:5 – im Raster wirkt das unruhig.
5. **Reine Ergebnisbilder.** Das Wissen dahinter – warum eine Abdichtung
   nach DIN 18534 zählt, warum Silikon eine Wartungsfuge ist – kommt nicht
   vor. Genau das erzeugt aber Vertrauen und Weiterempfehlung.

### Was gut ist und bleiben soll

- Die Arbeit selbst überzeugt: saubere Großformatflächen, klare Bäder.
- Der Screenshot mit echten Kundennachrichten war einer der stärksten Posts.
- Die Bio ist knapp, korrekt und hat einen Link.

---

## 3. Die Lücke, die das System schließt

Die Website ist präzise gestaltet. Instagram ist es nicht. Die Vorlagen in
`templates/` übertragen **exakt die Design-Sprache der Website** auf das
Instagram-Format:

- derselbe dunkle Verlauf mit 56-px-Raster wie im Hero
- dieselbe Schriftpaarung Rajdhani / Rubik
- derselbe rote Schrägbalken hinter dem Schlüsselwort
- dieselben Vertrauenspunkte mit grünem Haken
- dieselbe rote Pille als Handlungsaufforderung
- Logo oben links, `@berisabau` und Ort unten – in jedem Beitrag

**Ergebnis:** Wer die Website kennt, erkennt den Feed. Wer den Feed zuerst
sieht, erkennt die Website wieder.

---

## 4. Redaktionsplan

| Tag | Rubrik | Vorlage | Braucht Fotos |
|---|---|---|---|
| Mo | Profi-Tipp | `tipp.html` | nein |
| Di | Leistung im Fokus | `leistung.html` | nein |
| Mi | Projekt / Baustelle | `projekt.html` | **ja** |
| Do | Häufig gefragt | `faq.html` | nein |
| Fr | Vorher / Nachher | `vorher-nachher.html` | **ja** |
| Sa | Kundenstimme | `zitat.html` | nein |
| So | Handwerkswissen | `tipp.html` | nein |

Fünf der sieben Rubriken laufen ohne neues Bildmaterial. Fehlen Fotos,
weicht der Planer automatisch auf eine Textrubrik aus – der Kalender reißt
also nie ab.

**Aktueller Bestand:** über 70 fertige Themen. Bei zwei Posts pro Woche
(Dienstag/Donnerstag) und einer Sperrfrist von 30 Tagen deckt das den
laufenden Betrieb weit über ein Jahr ab; Themen lassen sich in
`content/themen.json` jederzeit ergänzen.

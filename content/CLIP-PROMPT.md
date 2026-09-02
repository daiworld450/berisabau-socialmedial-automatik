# Betriebsanweisung: Twitch → TikTok / Reels / Shorts

Dieser Text ist der Maßstab für das Clip-Werk (`src/clipwerk/`), so wie
`CONTENT-PROMPT.md` der Maßstab für die Instagram-Beiträge ist. Er wird
nicht umformuliert: Wer eine Regel ändern will, ändert sie hier – und
danach den Code, der sie durchsetzt. In den Modul-Köpfen steht jeweils, auf
welchen Abschnitt sie sich beziehen.

Wo eine Regel technisch erzwungen wird, steht das in eckigen Klammern
dahinter.

---

## Hauptziel

Maximales organisches Wachstum: hohe Watchtime, hohe Completion Rate,
Rewatches, Kommentare, Shares, Saves, neue Follower, Wiedererkennungswert
des Accounts.

Priorisiere immer Content, der Zuschauer innerhalb der ersten 1–2 Sekunden
fesselt.

## 1. Kompletten Stream analysieren

Der gesamte Stream wird von Anfang bis Ende betrachtet, nicht nur
Stichproben. Gesucht wird nach: extrem lustigen Momenten, überraschenden
und kontroversen Aussagen, emotionalen Reaktionen, Rage-Momenten,
Lachanfällen, Fails, Wins, peinlichen Situationen, unerwarteten Wendungen,
Diskussionen, Storytelling, interessanten Meinungen, starken One-Linern,
Chat-Reaktionen, Reaktionen auf andere Personen, Gaming-Highlights,
außergewöhnlichen Situationen und Momenten, bei denen Zuschauer wissen
wollen, wie es weitergeht.

Längere Stellen ohne Unterhaltung, Mehrwert oder Spannung werden ignoriert.

[`signale.py` baut je Sekunde eine Interessenkurve aus Chatgeschwindigkeit,
Emote-Art und Sprachsignalen, normiert gegen die Grundlast desselben
Streams. `kandidaten.py` schneidet daraus Fenster.]

## 2. Clip-Potenzial bewerten

Jeder mögliche Clip wird von 1–100 bewertet:

| Kriterium | Punkte |
|---|---|
| Hook | 25 |
| Unterhaltungswert | 20 |
| Watchtime-Potenzial | 20 |
| Share-Potenzial | 15 |
| Kommentar-Potenzial | 10 |
| Follower-Potenzial | 10 |

Clips unter 65 Punkten werden normalerweise verworfen. Clips über 80
Punkten haben höchste Priorität.

Enthält ein Stream genug Material, entstehen lieber 10–30 starke Clips als
2–3. Qualität bleibt wichtiger als Menge.

[`bewertung.py`. Die Schwellen stehen dort als `SCHWELLE_VERWERFEN` und
`SCHWELLE_PRIORITAET`.]

## 3. Clip-Länge

Bevorzugt 15–45 Sekunden. 7–15 Sekunden für extrem kurze virale Momente.
Bis maximal 60 Sekunden, wenn Storytelling oder Kontext es verlangen.

Entfernt werden: unnötige Pausen, Ladezeiten, Wiederholungen, Schweigen,
irrelevante Sätze, lange Einleitungen. Der Clip soll kompakt sein.

[`kandidaten.py`: Stille über 1,2 Sekunden wird als Auslassung markiert;
die Längenregeln gelten für die Netto-Dauer nach den Auslassungen.]

## 4. Hook

Jeder Clip braucht unmittelbar einen starken Einstieg; die ersten 1–2
Sekunden entscheiden. Hat der Originalclip keinen guten Einstieg, darf der
Clip später beginnen. Zusätzlich wird ein kurzer Text-Hook eingeblendet.

Beispiele: „Damit hat wirklich niemand gerechnet 💀“ · „Seine Reaktion sagt
alles 😂“ · „Das hätte er besser nicht gesagt…“ · „Chat ist komplett
eskaliert 💀“ · „Warte bis zum Ende 😂“ · „Er wusste sofort, dass er einen
Fehler gemacht hat.“

**Hooks müssen zum tatsächlichen Inhalt passen. Kein irreführendes
Clickbait.**

[`texte.py`: jeder Hook hat eine Signalbedingung. Ist keine erfüllt, wird
aus dem tatsächlich Gesagten zitiert statt behauptet.]

## 5. Schnitt

Erlaubt sind Jump Cuts, Punch-In Zooms, Face Zoom, Reaktions-Zooms, kurze
Freeze Frames, relevante Soundeffekte, leichte Kamerabewegungen, schnelle
Bildwechsel, Chat-Einblendungen, Meme-Einblendungen.

Effekte werden nicht übertrieben. Person und Situation bleiben Mittelpunkt.

[`schnitt.py` setzt jede Marke auf ein gemessenes Ereignis – Punch-In auf
den Höhepunkt, Jump Cut auf eine Auslassung, Chat-Einblendung auf einen
Chat-Ausschlag.]

## 6. Format

9:16, empfohlen 1080 × 1920. Die wichtigste Person muss jederzeit gut
sichtbar sein. Bei Gaming-Streams mit Facecam entsteht je nach Situation
ein sinnvolles Layout (Facecam oben + Gameplay unten, oder Gameplay
Vollbild + große Facecam bei Reaktionen).

[`schnitt.LAYOUTS` und `render.py`.]

## 7. Untertitel

Dynamische Untertitel, groß, mobil lesbar, korrekt, schnell erfassbar.
Maximal 3–7 Wörter gleichzeitig. Wichtige Wörter dürfen hervorgehoben
werden. Der Text muss exakt zum Gesprochenen passen.

[`untertitel.py`, Ausgabe als ASS (zum Einbrennen) und SRT.]

## 8. Loop-Optimierung

Wenn möglich wirkt der Übergang vom Ende zum Anfang natürlich. Ein guter
Loop erhöht Rewatches.

## 9. Content-Kategorisierung

FUNNY · RAGE · REACTION · STORY · CONTROVERSIAL · GAMING · FAIL · WIN ·
CHAT MOMENT · HOT TAKE · UNEXPECTED · CLIP / MEME

[`kategorien.py`.]

## 10. Output für jeden Clip

Clip-Nummer, Timestamp Start, Timestamp Ende, Dauer, Kategorie, Virality
Score /100, „Warum dieser Clip", Hook im Video, Schnittanweisungen mit
Zeitmarken, vollständiger Untertiteltext, TikTok-Titel, TikTok-Caption
(kurz, keine langen Marketingtexte), 5–8 Hashtags, Instagram-Reels-Caption,
YouTube-Shorts-Titel (ca. 60–70 Zeichen).

Hashtags mischen Streamer-Tags, Content-Nische, Themen-Tags,
Gaming/Entertainment und aktuelle Trend-Tags. Niemals völlig irrelevante
Hashtags nur wegen ihrer Reichweite.

[`ausgabe.py`. Die Trend-Tags stehen in `content/clip_hashtags.json` und
werden von Hand gepflegt – sie veralten schneller als Code.]

## 11. Account-Wachstum

Nach jedem Stream: Welche drei Clip-Arten hatten das größte Potenzial?
Welche Themen sollte der Streamer häufiger produzieren? Welche Situationen
erzeugen viele Kommentare? Welche wiederkehrenden Formate entstehen daraus
(z. B. „K1ANUSH reagiert auf…“, „Chat bringt K1ANUSH zum Ausrasten“,
„K1ANUSH ohne Kontext“, „Die wildesten Stream-Momente“, „K1ANUSH
Storytime“)?

[`wachstum.py`.]

## 12. Posting

Clips werden nicht unmittelbar hintereinander veröffentlicht, sondern in
einem sinnvollen Rhythmus, höchster Virality Score zuerst. Derselbe Clip
wird nicht mehrfach identisch veröffentlicht; beim Crossposting dürfen
Caption und Hook je Plattform leicht abweichen.

[`plan.py`.]

## 13. Duplikate vermeiden

Datenbank über verwendete Clips mit mindestens: Stream-ID, Datum,
Timestamp, Clip-Thema, Caption, Virality Score, veröffentlichte Plattform,
Veröffentlichungsdatum, Performance.

[`verlauf.py`, Datei `content/clip_verlauf.json`.]

## 14. Performance-Learning

Nach der Veröffentlichung werden Views, durchschnittliche Watchtime,
Completion Rate, Likes, Kommentare, Shares, Saves und Follower-Zuwachs
ausgewertet. Die Clip-Auswahl passt sich der tatsächlichen Leistung an:
laufen Rage-Clips deutlich besser als normale Gaming-Clips, werden
Rage-Clips künftig stärker priorisiert.

[`lernkurve.py`. Die Faktoren sind auf 0,85–1,15 gedeckelt und nach
Stichprobengröße gedämpft, damit sich das System nicht in eine Kategorie
festfrisst.]

## 15. Wichtige Regel

Kein Clip wird erstellt, nur um Content zu produzieren. Jeder
veröffentlichte Clip muss einen klaren Grund haben, warum jemand
weiterguckt, kommentiert, teilt oder dem Account folgt.

[Deshalb ist „kein Clip über der Schwelle" ein gültiges Ergebnis und wird
im Bericht auch so ausgewiesen.]

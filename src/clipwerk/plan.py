"""Veröffentlichungsrhythmus - Abschnitt 12.

„Veröffentliche nicht alle Clips unmittelbar hintereinander." Der Grund ist
handfest: TikTok spielt Videos desselben Kontos gegeneinander aus. Zwei
starke Clips innerhalb einer Stunde teilen sich dieselbe Erstausspielung,
statt zwei zu bekommen.

Der Plan hier hält deshalb drei Dinge auseinander:

* **Reihenfolge nach Score.** Was über 80 liegt, geht zuerst raus und in die
  beste Schiene. Ein 92er-Clip in Woche drei ist verschenkt.
* **Abstand.** Höchstens zwei TikToks am Tag, mindestens drei Stunden
  dazwischen.
* **Crossposting mit Versatz.** Derselbe Clip läuft auf Instagram und
  YouTube, aber ein bis zwei Tage später und mit abgewandeltem Hook -
  wortgleich nebeneinander sieht nach Automat aus, und das ist es zwar,
  soll aber nicht so aussehen.

Die Zeitschienen sind Vorgabewerte für einen deutschsprachigen
Unterhaltungskanal (Feierabend und später Abend) und über die Parameter
frei änderbar. Wer eigene Zahlen aus den Konto-Statistiken hat, nimmt die.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# plattform -> (Uhrzeiten je Tag, Höchstzahl je Tag)
SCHIENEN: dict[str, tuple[tuple[str, ...], int]] = {
    "tiktok": (("17:00", "20:30"), 2),
    "instagram": (("19:00",), 1),
    "youtube": (("18:00",), 1),
}

# Versatz in Tagen für das Crossposting nach dem TikTok-Start.
VERSATZ = {"instagram": 1, "youtube": 2}


@dataclass
class Eintrag:
    clip_id: str
    plattform: str
    datum: str
    uhrzeit: str
    score: int
    kategorie: str
    hook: str
    caption: str
    hashtags: list[str] = field(default_factory=list)
    titel: str = ""

    @property
    def zeitpunkt(self) -> datetime:
        return datetime.fromisoformat(f"{self.datum}T{self.uhrzeit}")


def _tage(start: date):
    tag = start
    while True:
        yield tag
        tag += timedelta(days=1)


def baue(clips: list[dict], ab: date | None = None,
         plattformen: tuple[str, ...] = ("tiktok", "instagram", "youtube"),
         schienen: dict | None = None) -> list[Eintrag]:
    """Aus bewerteten Clips einen datierten Veröffentlichungsplan machen.

    `clips` sind die Ausgabe-Datensätze aus `motor.analysiere` bzw. Einträge
    der Clip-Datenbank. Erwartet werden mindestens `clip_id`, `score`,
    `kategorie` und der Textblock unter `texte`.
    """
    schienen = schienen or SCHIENEN
    ab = ab or date.today()
    sortiert = sorted(clips, key=lambda c: -int(c.get("score", 0)))

    # Belegung je (Plattform, Tag) mitzählen, damit die Obergrenzen halten.
    belegt: dict[tuple[str, str], int] = {}
    plan: list[Eintrag] = []

    def naechster_platz(plattform: str, fruehestens: date) -> tuple[str, str]:
        zeiten, hoechstens = schienen[plattform]
        for tag in _tage(fruehestens):
            schluessel = (plattform, tag.isoformat())
            genutzt = belegt.get(schluessel, 0)
            if genutzt < hoechstens:
                belegt[schluessel] = genutzt + 1
                return tag.isoformat(), zeiten[genutzt % len(zeiten)]
        raise RuntimeError("unerreichbar")   # der Generator endet nie

    for clip in sortiert:
        texte = clip.get("texte", {})
        varianten = clip.get("hook_varianten", {})
        start_tag: date | None = None

        for plattform in plattformen:
            if plattform not in schienen:
                continue
            fruehestens = ab
            if plattform != "tiktok" and start_tag:
                fruehestens = start_tag + timedelta(days=VERSATZ.get(plattform, 1))
            tag, uhrzeit = naechster_platz(plattform, fruehestens)
            if plattform == "tiktok" or start_tag is None:
                start_tag = date.fromisoformat(tag)

            if plattform == "instagram":
                caption = texte.get("instagram_caption", "")
                titel = texte.get("tiktok_titel", "")
            elif plattform == "youtube":
                caption = texte.get("tiktok_caption", "")
                titel = texte.get("youtube_titel", "")
            else:
                caption = texte.get("tiktok_caption", "")
                titel = texte.get("tiktok_titel", "")

            plan.append(Eintrag(
                clip_id=clip.get("clip_id", ""),
                plattform=plattform,
                datum=tag,
                uhrzeit=uhrzeit,
                score=int(clip.get("score", 0)),
                kategorie=clip.get("kategorie", ""),
                hook=varianten.get(plattform) or texte.get("hook", ""),
                caption=caption,
                hashtags=list(texte.get("hashtags", [])),
                titel=titel,
            ))

    return sorted(plan, key=lambda e: (e.zeitpunkt, e.plattform))


def als_text(plan: list[Eintrag]) -> str:
    if not plan:
        return "Kein Clip im Plan."
    zeilen, letzter_tag = [], ""
    for eintrag in plan:
        if eintrag.datum != letzter_tag:
            zeilen.append("")
            zeilen.append(eintrag.datum)
            letzter_tag = eintrag.datum
        zeilen.append(f"  {eintrag.uhrzeit}  {eintrag.plattform:<10} "
                      f"{eintrag.clip_id:<18} {eintrag.score:>3}  "
                      f"{eintrag.kategorie:<14} {eintrag.hook}")
    return "\n".join(zeilen).strip()


def als_json(plan: list[Eintrag]) -> list[dict]:
    return [{
        "clip_id": e.clip_id, "plattform": e.plattform, "datum": e.datum,
        "uhrzeit": e.uhrzeit, "score": e.score, "kategorie": e.kategorie,
        "hook": e.hook, "titel": e.titel, "caption": e.caption,
        "hashtags": e.hashtags,
    } for e in plan]

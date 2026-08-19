"""Auswertung des eigenen Kontos über die offizielle Graph API.

Ersetzt die drei Routinen, für die üblicherweise kostenpflichtige Dienste
verkauft werden:
  1. Selbst-Audit    – was lief in den letzten N Tagen, was nicht
  2. Ausreißer       – welche eigenen Beiträge über dem eigenen Schnitt liegen
  3. Muster          – welche Säule, welcher Wochentag, welche Hook-Art trägt

Alles über Endpunkte, die im kostenlosen Zugang enthalten sind. Der Vergleich
mit fremden Konten (business_discovery) braucht den Weg über eine
Facebook-Seite und ist deshalb optional – siehe vergleiche_konto().
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

from config import IG_USER_ID, LOG_DATEI, THEMEN
from publisher import VeroeffentlichungsFehler, _anfrage

# Kennzahlen, die für einen Handwerksbetrieb wirklich zählen.
# 'saved' und 'shares' sind aussagekräftiger als Likes: Wer speichert, plant.
MEDIEN_FELDER = ("id,caption,media_type,media_product_type,permalink,"
                 "timestamp,like_count,comments_count")
INSIGHT_METRIKEN = "reach,saved,shares,total_interactions,views"


def _hole_medien(limit: int = 50) -> list[dict]:
    antwort = _anfrage("GET", f"{IG_USER_ID}/media",
                       fields=MEDIEN_FELDER, limit=limit)
    return antwort.get("data", [])


def _hole_insights(media_id: str) -> dict:
    """Insights je Beitrag. Nicht jede Metrik gibt es für jeden Medientyp."""
    try:
        antwort = _anfrage("GET", f"{media_id}/insights", metric=INSIGHT_METRIKEN)
    except VeroeffentlichungsFehler:
        # Ältere Beiträge oder bestimmte Typen liefern keine Insights.
        return {}
    werte = {}
    for eintrag in antwort.get("data", []):
        reihe = eintrag.get("values") or [{}]
        werte[eintrag["name"]] = reihe[0].get("value", 0)
    return werte


def _saeule_aus_verlauf() -> dict[str, str]:
    """Ordnet Instagram-Media-IDs der Säule zu, mit der sie geplant wurden."""
    if not LOG_DATEI.exists():
        return {}
    themen_saeule = {t["id"]: t["rubrik"] for t in THEMEN["themen"]}
    zuordnung = {}
    for zeile in LOG_DATEI.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(zeile)
        except ValueError:
            continue
        if e.get("media_id"):
            zuordnung[e["media_id"]] = themen_saeule.get(e.get("thema", ""), "unbekannt")
    return zuordnung


def sammle(tage: int = 30) -> list[dict]:
    """Beiträge der letzten N Tage samt Kennzahlen."""
    grenze = datetime.now().astimezone() - timedelta(days=tage)
    saeulen = _saeule_aus_verlauf()

    beitraege = []
    for m in _hole_medien():
        try:
            wann = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if wann < grenze:
            continue

        insights = _hole_insights(m["id"])
        reichweite = insights.get("reach", 0) or 0
        interaktionen = insights.get("total_interactions", 0) or 0
        beitraege.append({
            "id": m["id"],
            "datum": wann.date(),
            "wochentag": wann.weekday(),
            "typ": m.get("media_product_type") or m.get("media_type", ""),
            "permalink": m.get("permalink"),
            "hook": (m.get("caption") or "").split("\n")[0][:70],
            "saeule": saeulen.get(m["id"], "unbekannt"),
            "reichweite": reichweite,
            "aufrufe": insights.get("views", 0) or 0,
            "gespeichert": insights.get("saved", 0) or 0,
            "geteilt": insights.get("shares", 0) or 0,
            "likes": m.get("like_count", 0) or 0,
            "kommentare": m.get("comments_count", 0) or 0,
            "interaktionen": interaktionen,
            "quote": round(100 * interaktionen / reichweite, 1) if reichweite else 0.0,
        })
    return sorted(beitraege, key=lambda b: b["datum"], reverse=True)


def ausreisser(beitraege: list[dict], faktor: float = 1.3) -> list[dict]:
    """Beiträge, deren Reichweite deutlich über dem eigenen Median liegt.

    Median statt Mittelwert: ein einzelner viraler Beitrag würde den
    Mittelwert so verschieben, dass danach nichts mehr als Ausreißer gilt.
    """
    werte = [b["reichweite"] for b in beitraege if b["reichweite"] > 0]
    if len(werte) < 3:
        return []
    mitte = statistics.median(werte)
    return [dict(b, faktor=round(b["reichweite"] / mitte, 2))
            for b in beitraege if b["reichweite"] >= mitte * faktor]


def muster(beitraege: list[dict]) -> dict:
    """Welche Säule, welcher Wochentag und welches Format tragen."""
    def gruppiere(schluessel):
        eimer = defaultdict(list)
        for b in beitraege:
            eimer[b[schluessel]].append(b)
        return {
            k: {
                "anzahl": len(v),
                "reichweite_median": int(statistics.median(
                    [x["reichweite"] for x in v] or [0])),
                "gespeichert_schnitt": round(
                    sum(x["gespeichert"] for x in v) / len(v), 1),
                "quote_schnitt": round(sum(x["quote"] for x in v) / len(v), 1),
            }
            for k, v in eimer.items()
        }

    wochentage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    nach_tag = gruppiere("wochentag")
    return {
        "nach_saeule": gruppiere("saeule"),
        "nach_typ": gruppiere("typ"),
        "nach_wochentag": {wochentage[k]: v for k, v in sorted(nach_tag.items())},
    }


def vergleiche_konto(handle: str) -> dict:
    """Öffentliche Kennzahlen eines fremden Profikontos.

    Nur über den Weg 'Instagram API mit Facebook-Login' verfügbar. Auf dem
    hier genutzten Weg (graph.instagram.com) antwortet Meta mit einem Fehler –
    das wird sauber gemeldet statt zu raten.
    """
    feld = (f"business_discovery.username({handle})"
            "{username,followers_count,media_count,"
            "media.limit(25){caption,like_count,comments_count,timestamp,permalink}}")
    try:
        antwort = _anfrage("GET", IG_USER_ID, fields=feld)
    except VeroeffentlichungsFehler as fehler:
        return {"verfuegbar": False, "grund": str(fehler)}

    daten = antwort.get("business_discovery", {})
    posts = daten.get("media", {}).get("data", [])
    inter = [p.get("like_count", 0) + p.get("comments_count", 0) for p in posts]
    mitte = statistics.median(inter) if inter else 0

    return {
        "verfuegbar": True,
        "handle": daten.get("username"),
        "follower": daten.get("followers_count"),
        "beitraege": daten.get("media_count"),
        "median_interaktionen": mitte,
        "ausreisser": sorted(
            [{"hook": (p.get("caption") or "").split("\n")[0][:70],
              "interaktionen": p.get("like_count", 0) + p.get("comments_count", 0),
              "permalink": p.get("permalink")}
             for p in posts
             if (p.get("like_count", 0) + p.get("comments_count", 0)) > mitte * 1.5],
            key=lambda x: -x["interaktionen"])[:5],
    }


def bericht(tage: int = 30) -> str:
    beitraege = sammle(tage)
    if not beitraege:
        return (f"Keine Beiträge in den letzten {tage} Tagen gefunden.\n"
                "Entweder wurde noch nichts veröffentlicht, oder der Zugang "
                "steht noch nicht – prüfen mit: python src/main.py zugang")

    z = [f"Auswertung der letzten {tage} Tage · {len(beitraege)} Beiträge\n"]

    med_reichweite = int(statistics.median([b["reichweite"] for b in beitraege]))
    ges_gespeichert = sum(b["gespeichert"] for b in beitraege)
    z.append(f"  Reichweite im Median : {med_reichweite}")
    z.append(f"  Gespeichert gesamt   : {ges_gespeichert}")
    z.append(f"  Geteilt gesamt       : {sum(b['geteilt'] for b in beitraege)}")
    z.append(f"  Kommentare gesamt    : {sum(b['kommentare'] for b in beitraege)}\n")

    aus = ausreisser(beitraege)
    if aus:
        z.append(f"Über dem eigenen Median ({len(aus)}):")
        for b in sorted(aus, key=lambda x: -x["faktor"]):
            z.append(f"  {b['faktor']}x  {b['datum']}  {b['saeule']:<14} {b['hook']}")
    else:
        z.append("Keine klaren Ausreißer – die Beiträge liegen eng beieinander.")
    z.append("")

    m = muster(beitraege)
    for titel, schluessel in (("Nach Säule", "nach_saeule"),
                              ("Nach Wochentag", "nach_wochentag"),
                              ("Nach Format", "nach_typ")):
        werte = m[schluessel]
        if len(werte) < 2:
            continue
        z.append(f"{titel}:")
        for k, v in sorted(werte.items(), key=lambda x: -x[1]["reichweite_median"]):
            z.append(f"  {str(k):<14} n={v['anzahl']:<3} "
                     f"Reichweite {v['reichweite_median']:<6} "
                     f"gespeichert {v['gespeichert_schnitt']:<5} "
                     f"Quote {v['quote_schnitt']} %")
        z.append("")

    z.append("Hinweis: Bei kleiner Fallzahl sind das Anhaltspunkte, keine Beweise.")
    z.append("Aussagekräftig wird es ab etwa 20 Beiträgen je Säule.")
    return "\n".join(z)

"""Dienstags-Kurzcheck: eine kompakte Tabelle der laufenden Kampagnen.

Kosten, Impressionen, Klicks, Conversions, Conversion-Rate, Kosten je
Conversion - plus ein Hinweis, wenn eine Kampagne stark von der Vorwoche
abweicht. Höchstens 4 Kampagnenzeilen + Gesamtzeile, damit daraus eine
"Tabelle mit maximal 6 Zeilen" bleibt statt einer Zahlenwand.
"""
from __future__ import annotations

from datetime import date

import google_ads_client as ads

MAX_KAMPAGNEN = 4
AUFFAELLIG_SCHWELLE_PROZENT = 15.0


def _eur(betrag: float) -> str:
    return f"{betrag:,.0f}€".replace(",", ".")


def _kuerze(name: str, laenge: int = 16) -> str:
    return name if len(name) <= laenge else name[: laenge - 1] + "…"


def _auffaellig(zeilen: list[dict]) -> str:
    treffer = []
    for z in zeilen:
        for feld, bezeichnung in (("klicks_diff_prozent", "Klicks"),
                                  ("kosten_diff_prozent", "Kosten")):
            diff = z[feld]
            if diff is None or abs(diff) < AUFFAELLIG_SCHWELLE_PROZENT:
                continue
            richtung = "+" if diff > 0 else ""
            treffer.append(f"„{_kuerze(z['name'], 24)}" + '"' +
                           f" {bezeichnung} {richtung}{diff:.0f}% ggü. Vorwoche")
    return "; ".join(treffer[:2])


def baue_bericht(zeilen: list[dict] | None = None) -> str:
    """Baut die fertige Telegram-Nachricht (Markdown, Tabelle im Codeblock).
    zeilen als Parameter durchreichbar - macht das Modul ohne Netzwerkzugriff
    testbar."""
    zeilen = zeilen if zeilen is not None else ads.wochenvergleich()
    if not zeilen:
        return "📊 Kurzcheck – keine Kampagnendaten im Konto gefunden."

    zeitraum = f"{zeilen[0]['zeitraum_von']} – {zeilen[0]['zeitraum_bis']}"
    kopf = f"📊 Kurzcheck {date.today().strftime('%d.%m.%Y')} — letzte 7 Tage ({zeitraum})\n"

    tabelle = ["Kampagne         Kosten  Impr.  Klicks  Conv.  Conv-Rate  €/Conv."]
    gesamt = {"kosten": 0.0, "impressionen": 0, "klicks": 0, "conversions": 0.0}
    for z in zeilen[:MAX_KAMPAGNEN]:
        gesamt["kosten"] += z["kosten"]
        gesamt["impressionen"] += z["impressionen"]
        gesamt["klicks"] += z["klicks"]
        gesamt["conversions"] += z["conversions"]
        cpc = f"{z['kosten_je_conversion']:.0f}€" if z["kosten_je_conversion"] else "–"
        tabelle.append(
            f"{_kuerze(z['name']):<16} {_eur(z['kosten']):>6}  "
            f"{z['impressionen']:>5}  {z['klicks']:>5}   {z['conversions']:>4.0f}   "
            f"{z['conversion_rate_prozent']:>5.1f}%    {cpc:>6}"
        )

    gesamt_conv_rate = (round(gesamt["conversions"] / gesamt["klicks"] * 100, 1)
                        if gesamt["klicks"] else 0.0)
    gesamt_cpc = (f"{gesamt['kosten'] / gesamt['conversions']:.0f}€"
                 if gesamt["conversions"] else "–")
    tabelle.append("─" * 58)
    tabelle.append(
        f"{'Gesamt':<16} {_eur(gesamt['kosten']):>6}  {gesamt['impressionen']:>5}  "
        f"{gesamt['klicks']:>5}   {gesamt['conversions']:>4.0f}   "
        f"{gesamt_conv_rate:>5.1f}%    {gesamt_cpc:>6}"
    )

    ausreisser = _auffaellig(zeilen)
    fuss = f"\n⚠ Auffällig: {ausreisser}" if ausreisser else ""

    return kopf + "```\n" + "\n".join(tabelle) + "\n```" + fuss

"""Donnerstags-Optimierungsvorschlag: EIN konkreter Punkt, begründet mit den
eigenen Zahlen der Woche - keine allgemeine Checkliste.

Regelbasiert statt KI-generiert: bei echtem Geld soll nichts erfunden oder
schöngeredet werden können. Jeder Vorschlag zitiert nur Werte, die
tatsächlich aus der Google Ads API kamen. Reine Empfehlung - dieses Modul
ändert nie selbst etwas im Konto (siehe google-ads-mcp/server.py für dieselbe
Regel beim Chat-Assistenten).

Priorität bei mehreren Kandidaten (unterschiedliche Einheiten - Klicks,
Euro, Prozent - lassen sich nicht direkt vergleichen, deshalb feste
Reihenfolge statt Zahlenvergleich):
  1. Conversion-Tracking wirkt kaputt (etwas stimmt technisch nicht)
  2. Klar messbarer Geldverlust (Klicks ohne jede Conversion)
  3. Wachstumschance (Budget bremst eine gut laufende Kampagne aus)
"""
from __future__ import annotations

import logging
from datetime import date

import google_ads_client as ads

log = logging.getLogger(__name__)

MINDEST_BUDGET_VERLUST_PROZENT = 10.0
MINDEST_VERSCHWENDETE_KOSTEN_EUR = 20.0
MINDEST_KLICKS_OHNE_CONVERSION = 30


def _kandidat_conversion_tracking(zeilen: list[dict]) -> str | None:
    verdaechtig = [z for z in zeilen
                  if z["klicks"] >= MINDEST_KLICKS_OHNE_CONVERSION
                  and z["conversions"] == 0]
    if not verdaechtig:
        return None
    beste = max(verdaechtig, key=lambda z: z["klicks"])
    return (
        f"Conversion-Tracking prüfen: „{beste['name']}\"\n"
        f"{beste['klicks']} Klicks in den letzten 7 Tagen ({beste['kosten']:.0f}€ "
        f"Kosten), aber 0 gemessene Conversions – bei dieser Klickzahl "
        f"ungewöhnlich.\n"
        f"Vorschlag: Conversion-Aktion und Landingpage kontrollieren, bevor "
        f"an dieser Kampagne sonst etwas geändert wird."
    )


def _kandidat_negative_keywords(tage: int = 30) -> str | None:
    # Eigener API-Aufruf zusätzlich zu wochenvergleich() - ein Fehler hier
    # (z.B. Timeout) soll nicht den ganzen Donnerstags-Bericht kippen,
    # sondern nur diesen einen Kandidaten still überspringen.
    try:
        verschwender = ads.suchbegriffe_ohne_conversion(tage=tage)
    except Exception as fehler:  # noqa: BLE001
        log.warning("Suchbegriff-Abfrage übersprungen: %s", fehler)
        return None
    if not verschwender:
        return None
    gesamt = sum(v["kosten"] for v in verschwender)
    if gesamt < MINDEST_VERSCHWENDETE_KOSTEN_EUR:
        return None
    top = verschwender[:3]
    zeilen_text = "\n".join(
        f"  „{v['suchbegriff']}\" – {v['klicks']} Klicks, {v['kosten']:.0f}€, "
        "0 Conversions" for v in top
    )
    return (
        f"Negative Keywords ergänzen\n"
        f"In den letzten {tage} Tagen kamen {gesamt:.0f}€ Kosten von "
        f"Suchbegriffen ohne eine einzige Conversion, u.a.:\n{zeilen_text}\n"
        f"Vorschlag: diese Begriffe als negative Keywords ausschließen."
    )


def _kandidat_budget(zeilen: list[dict]) -> str | None:
    kandidaten = [z for z in zeilen
                 if z["budget_verlust_prozent"] >= MINDEST_BUDGET_VERLUST_PROZENT
                 and z["conversions"] > 0]
    if not kandidaten:
        return None
    beste = max(kandidaten, key=lambda z: z["budget_verlust_prozent"])
    return (
        f"Budget erhöhen: „{beste['name']}\"\n"
        f"Diese Kampagne verliert {beste['budget_verlust_prozent']:.0f}% "
        f"möglicher Impressionen, weil das Tagesbudget nicht reicht – bei "
        f"{beste['conversions']:.0f} Conversions aus {beste['klicks']} Klicks "
        f"in den letzten 7 Tagen ({beste['conversion_rate_prozent']:.1f}% "
        f"Conversion-Rate) lohnt sich mehr Volumen.\n"
        f"Vorschlag: Tagesbudget in kleinen Schritten (z.B. +20%) erhöhen "
        f"und die Conversion-Rate der nächsten Woche im Auge behalten."
    )


def baue_vorschlag(zeilen: list[dict] | None = None) -> str:
    """zeilen als Parameter durchreichbar - macht das Modul ohne
    Netzwerkzugriff testbar."""
    zeilen = zeilen if zeilen is not None else ads.wochenvergleich()
    kopf = f"💡 Optimierungsvorschlag {date.today().strftime('%d.%m.%Y')}\n\n"

    if not zeilen:
        return kopf + "Keine Kampagnendaten im Konto gefunden."

    for kandidat in (_kandidat_conversion_tracking(zeilen),
                     _kandidat_negative_keywords(),
                     _kandidat_budget(zeilen)):
        if kandidat:
            return kopf + kandidat

    return kopf + "Keine auffällige Stelle in den Zahlen dieser Woche – nichts zu tun."

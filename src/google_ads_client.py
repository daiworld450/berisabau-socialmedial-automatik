"""Nur-lesender Google-Ads-API-Zugang für den Update-Kanal.

Getrennt vom eigentlichen MCP-Server (google-ads-mcp/ im Projekt-Wurzel-
ordner), weil dieses Skript hier per GitHub Actions läuft statt als
MCP-Tool im Chat - gleiche Zugangsdaten, eigener schlanker Weg ohne die
FastMCP-Abhängigkeit. Es gibt hier absichtlich keine einzige schreibende
Funktion (kein pause/enable, kein Gebot setzen) - dieser Kanal berichtet,
er greift nicht ins Konto ein.
"""
from __future__ import annotations

from datetime import date, timedelta

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from config import (
    GOOGLE_ADS_CLIENT_ID,
    GOOGLE_ADS_CLIENT_SECRET,
    GOOGLE_ADS_CUSTOMER_ID,
    GOOGLE_ADS_DEVELOPER_TOKEN,
    GOOGLE_ADS_LOGIN_CUSTOMER_ID,
    GOOGLE_ADS_REFRESH_TOKEN,
)


class GoogleAdsNichtEingerichtet(RuntimeError):
    pass


def aktiv() -> bool:
    return bool(GOOGLE_ADS_DEVELOPER_TOKEN and GOOGLE_ADS_CLIENT_ID
                and GOOGLE_ADS_CLIENT_SECRET and GOOGLE_ADS_REFRESH_TOKEN
                and GOOGLE_ADS_CUSTOMER_ID)


def _client() -> GoogleAdsClient:
    konfig = {
        "developer_token": GOOGLE_ADS_DEVELOPER_TOKEN,
        "client_id": GOOGLE_ADS_CLIENT_ID,
        "client_secret": GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": GOOGLE_ADS_REFRESH_TOKEN,
        "use_proto_plus": True,
    }
    if GOOGLE_ADS_LOGIN_CUSTOMER_ID:
        konfig["login_customer_id"] = GOOGLE_ADS_LOGIN_CUSTOMER_ID
    return GoogleAdsClient.load_from_dict(konfig)


def _kunden_id() -> str:
    return GOOGLE_ADS_CUSTOMER_ID.replace("-", "")


def _abfrage(gaql: str) -> list:
    if not aktiv():
        raise GoogleAdsNichtEingerichtet(
            "Google-Ads-Zugangsdaten fehlen (.env bzw. GitHub Secrets "
            "GOOGLE_ADS_*).")
    dienst = _client().get_service("GoogleAdsService")
    try:
        return list(dienst.search(customer_id=_kunden_id(), query=gaql))
    except GoogleAdsException as fehler:
        meldung = "; ".join(f.message for f in fehler.failure.errors)
        raise RuntimeError(f"Google Ads API Fehler: {meldung}") from fehler


def _eur(micros: int) -> float:
    return round(micros / 1_000_000, 2)


def _diff_prozent(neu: float, alt: float) -> float | None:
    if not alt:
        return None
    return round((neu - alt) / alt * 100, 1)


def _kampagnen_im_zeitraum(von: date, bis: date) -> dict[int, dict]:
    gaql = f"""
        SELECT campaign.id, campaign.name, campaign.status,
               metrics.cost_micros, metrics.impressions, metrics.clicks,
               metrics.conversions,
               metrics.search_budget_lost_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{von.isoformat()}' AND '{bis.isoformat()}'
    """
    ergebnis: dict[int, dict] = {}
    for zeile in _abfrage(gaql):
        ergebnis[zeile.campaign.id] = {
            "kampagne_id": zeile.campaign.id,
            "name": zeile.campaign.name,
            "status": zeile.campaign.status.name,
            "kosten": _eur(zeile.metrics.cost_micros),
            "impressionen": zeile.metrics.impressions,
            "klicks": zeile.metrics.clicks,
            "conversions": round(zeile.metrics.conversions, 1),
            "budget_verlust_prozent": round(
                zeile.metrics.search_budget_lost_impression_share * 100, 1),
        }
    return ergebnis


def wochenvergleich(heute: date | None = None) -> list[dict]:
    """Kampagnen-Performance der letzten 7 Tage (bis gestern) vs. der 7 Tage
    davor. Für jede Kampagne: aktuelle Werte, Conversion-Rate, Kosten je
    Conversion, plus prozentuale Veränderung bei Klicks und Kosten ggü. der
    Vorwoche - Basis für den Dienstags-Kurzcheck und den Donnerstags-
    Optimierungsvorschlag. Nach Kosten absteigend sortiert.
    """
    heute = heute or date.today()
    bis = heute - timedelta(days=1)
    von = bis - timedelta(days=6)
    vorwoche_bis = von - timedelta(days=1)
    vorwoche_von = vorwoche_bis - timedelta(days=6)

    aktuell = _kampagnen_im_zeitraum(von, bis)
    vorwoche = _kampagnen_im_zeitraum(vorwoche_von, vorwoche_bis)

    zeilen = []
    for kid, daten in aktuell.items():
        alt = vorwoche.get(kid, {"kosten": 0, "impressionen": 0, "klicks": 0,
                                  "conversions": 0})
        conv_rate = (round(daten["conversions"] / daten["klicks"] * 100, 1)
                    if daten["klicks"] else 0.0)
        kosten_je_conversion = (round(daten["kosten"] / daten["conversions"], 2)
                                if daten["conversions"] else None)
        zeilen.append({
            **daten,
            "conversion_rate_prozent": conv_rate,
            "kosten_je_conversion": kosten_je_conversion,
            "klicks_diff_prozent": _diff_prozent(daten["klicks"], alt["klicks"]),
            "kosten_diff_prozent": _diff_prozent(daten["kosten"], alt["kosten"]),
            "zeitraum_von": von.isoformat(),
            "zeitraum_bis": bis.isoformat(),
        })

    zeilen.sort(key=lambda z: z["kosten"], reverse=True)
    return zeilen


def suchbegriffe_ohne_conversion(tage: int = 30, mindestklicks: int = 5) -> list[dict]:
    """Tatsächliche Suchbegriffe mit Klicks, aber ohne eine einzige
    Conversion - Grundlage für den Donnerstags-Vorschlag 'als negatives
    Keyword ausschließen'."""
    bis = date.today() - timedelta(days=1)
    von = bis - timedelta(days=tage - 1)
    gaql = f"""
        SELECT search_term_view.search_term, campaign.name, ad_group.id,
               metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{von.isoformat()}' AND '{bis.isoformat()}'
        ORDER BY metrics.cost_micros DESC
        LIMIT 200
    """
    treffer = []
    for zeile in _abfrage(gaql):
        if zeile.metrics.clicks < mindestklicks or zeile.metrics.conversions > 0:
            continue
        treffer.append({
            "suchbegriff": zeile.search_term_view.search_term,
            "kampagne": zeile.campaign.name,
            "ad_group_id": zeile.ad_group.id,
            "klicks": zeile.metrics.clicks,
            "kosten": _eur(zeile.metrics.cost_micros),
        })
    treffer.sort(key=lambda t: t["kosten"], reverse=True)
    return treffer

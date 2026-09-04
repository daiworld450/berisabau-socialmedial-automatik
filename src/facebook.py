"""Veröffentlicht denselben Beitrag zusätzlich auf der Facebook-Seite.

Andere Schnittstelle als Instagram, deshalb ein eigenes Modul:
Instagram läuft hier über graph.instagram.com ("Instagram API mit Instagram
Login"), Facebook-Seiten laufen zwingend über graph.facebook.com mit einem
Seiten-Token.

Wichtig: Ein privates Facebook-Profil lässt sich nicht per API bespielen.
Es muss eine Seite sein – bei Berisa Bau facebook.com/BerisaBau.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import requests

from config import FB_API_VERSION, FB_PAGE_ID, FB_TOKEN, MEDIA_BASE_URL

log = logging.getLogger(__name__)

HOST = "https://graph.facebook.com"
TIMEOUT = 60
MAX_VERSUCHE = 3

# Dieselbe Unterscheidung wie bei Instagram: wo Wiederholen hilft und wo nicht.
VORUEBERGEHEND = {1, 2, 4, 17, 32, 341, 368, 613}
ENDGUELTIG = {10, 100, 102, 190, 200, 803}


class FacebookFehler(RuntimeError):
    def __init__(self, meldung: str, code: int | None = None):
        super().__init__(meldung)
        self.code = code

    @property
    def token_problem(self) -> bool:
        return self.code in (190, 102, 10)


@dataclass
class Ergebnis:
    ok: bool
    id: str | None = None
    meldung: str = ""
    permalink: str | None = None


def aktiv() -> bool:
    """Facebook wird nur bespielt, wenn Seite und Token hinterlegt sind."""
    return bool(FB_PAGE_ID and FB_TOKEN)


def _pruefe_konfiguration() -> None:
    fehlend = [n for n, w in (("FB_PAGE_ID", FB_PAGE_ID),
                              ("FB_PAGE_TOKEN", FB_TOKEN),
                              ("MEDIA_BASE_URL", MEDIA_BASE_URL)) if not w]
    if fehlend:
        raise FacebookFehler("Fehlende Konfiguration: " + ", ".join(fehlend)
                             + ". Siehe docs/03-FACEBOOK-EINRICHTEN.md")


def medien_url(dateiname: str) -> str:
    return f"{MEDIA_BASE_URL}/{dateiname.lstrip('/')}"


def _anfrage(methode: str, pfad: str, **params) -> dict:
    params["access_token"] = FB_TOKEN
    url = f"{HOST}/{FB_API_VERSION}/{pfad.lstrip('/')}"
    pause = 2.0
    letzter: FacebookFehler | None = None

    for versuch in range(1, MAX_VERSUCHE + 1):
        try:
            if methode == "GET":
                antwort = requests.get(url, params=params, timeout=TIMEOUT)
            else:
                antwort = requests.post(url, data=params, timeout=TIMEOUT)
        except requests.RequestException as exc:
            letzter = FacebookFehler(f"Netzwerkfehler: {exc}")
            time.sleep(pause)
            pause *= 2
            continue

        try:
            inhalt = antwort.json()
        except ValueError:
            inhalt = {}

        if antwort.ok and "error" not in inhalt:
            return inhalt

        fehler = inhalt.get("error", {})
        code = fehler.get("code")
        meldung = fehler.get("message", f"HTTP {antwort.status_code}")
        problem = FacebookFehler(meldung, code)

        if code in ENDGUELTIG or (code not in VORUEBERGEHEND
                                  and antwort.status_code in (400, 401, 403)):
            raise problem

        letzter = problem
        log.warning("Facebook-Fehler (Versuch %s/%s), code=%s: %s",
                    versuch, MAX_VERSUCHE, code, meldung)
        time.sleep(pause)
        pause *= 2

    raise letzter or FacebookFehler("Unbekannter Fehler")


def _permalink(post_id: str) -> str | None:
    try:
        return _anfrage("GET", post_id, fields="permalink_url").get("permalink_url")
    except FacebookFehler:
        return None


# --------------------------------------------------------------------------- #
def veroeffentliche_bild(dateiname: str, text: str,
                         trockenlauf: bool = False) -> Ergebnis:
    url = medien_url(dateiname)
    if trockenlauf:
        return Ergebnis(True, None, f"Trockenlauf Facebook – Bild: {url}")

    _pruefe_konfiguration()
    antwort = _anfrage("POST", f"{FB_PAGE_ID}/photos", url=url, caption=text)
    post_id = antwort.get("post_id") or antwort.get("id")
    if not post_id:
        raise FacebookFehler(f"Keine Post-ID erhalten: {antwort}")
    return Ergebnis(True, post_id, "Auf Facebook veröffentlicht.", _permalink(post_id))


def veroeffentliche_album(dateinamen: list[str], text: str,
                          trockenlauf: bool = False) -> Ergebnis:
    """Mehrere Bilder als ein Beitrag.

    Zweistufig: jedes Bild wird unveröffentlicht hochgeladen, danach werden
    die Kennungen an einen Beitrag gehängt.
    """
    urls = [medien_url(n) for n in dateinamen]
    if trockenlauf:
        return Ergebnis(True, None,
                        f"Trockenlauf Facebook – {len(urls)} Bilder:\n  "
                        + "\n  ".join(urls))

    _pruefe_konfiguration()
    kennungen = []
    for nr, url in enumerate(urls, start=1):
        antwort = _anfrage("POST", f"{FB_PAGE_ID}/photos",
                           url=url, published="false")
        kennung = antwort.get("id")
        if not kennung:
            raise FacebookFehler(f"Bild {nr}: keine Kennung ({antwort})")
        kennungen.append(kennung)

    angehaengt = {f"attached_media[{i}]": json.dumps({"media_fbid": k})
                  for i, k in enumerate(kennungen)}
    antwort = _anfrage("POST", f"{FB_PAGE_ID}/feed", message=text, **angehaengt)
    post_id = antwort.get("id")
    if not post_id:
        raise FacebookFehler(f"Keine Post-ID erhalten: {antwort}")
    return Ergebnis(True, post_id,
                    f"Auf Facebook veröffentlicht ({len(urls)} Bilder).",
                    _permalink(post_id))


def veroeffentliche_video(dateiname: str, text: str, titel: str = "",
                          trockenlauf: bool = False) -> Ergebnis:
    url = medien_url(dateiname)
    if trockenlauf:
        return Ergebnis(True, None, f"Trockenlauf Facebook – Video: {url}")

    _pruefe_konfiguration()
    params = {"file_url": url, "description": text}
    if titel:
        params["title"] = titel
    antwort = _anfrage("POST", f"{FB_PAGE_ID}/videos", **params)
    post_id = antwort.get("id")
    if not post_id:
        raise FacebookFehler(f"Keine Post-ID erhalten: {antwort}")
    # Facebook verarbeitet das Video im Hintergrund; ein Permalink liegt oft
    # erst später vor. Kein Grund, den Lauf scheitern zu lassen.
    return Ergebnis(True, post_id, "Video an Facebook übergeben (wird verarbeitet).")


def pruefe_zugang() -> Ergebnis:
    _pruefe_konfiguration()
    try:
        daten = _anfrage("GET", FB_PAGE_ID, fields="id,name,link,fan_count")
    except FacebookFehler as fehler:
        hinweis = (" (Seiten-Token abgelaufen oder ungültig – Schritt 4 der "
                   "Anleitung)" if fehler.token_problem else "")
        return Ergebnis(False, meldung=f"{fehler}{hinweis}")
    return Ergebnis(True, daten.get("id"),
                    f"{daten.get('name')} · {daten.get('fan_count', '?')} "
                    f"Follower · {daten.get('link', '')}")


def seiten_auflisten(nutzer_token: str) -> list[dict]:
    """Hilfe bei der Einrichtung: welche Seiten hängen am Nutzer-Token?

    Liefert je Seite Kennung, Name und den dazugehörigen Seiten-Token – genau
    das, was in FB_PAGE_ID und FB_PAGE_TOKEN gehört.
    """
    antwort = requests.get(f"{HOST}/{FB_API_VERSION}/me/accounts",
                           params={"fields": "id,name,access_token",
                                   "access_token": nutzer_token},
                           timeout=TIMEOUT).json()
    if "error" in antwort:
        raise FacebookFehler(antwort["error"].get("message", "Unbekannter Fehler"))
    return antwort.get("data", [])


def token_zustand() -> dict:
    """Was der hinterlegte Seiten-Token gerade taugt.

    Angelegt am 03.09.2026, nachdem Facebook einen Beitrag abgelehnt hatte
    und niemand es bemerkte: Instagram lief weiter, der Fehler stand nur in
    einem Lauf-Protokoll, das keiner liest. Die Meldung von Facebook nannte
    ausserdem die falsche Ursache - eine angebliche App-Ueberpruefung, waehrend
    dem Token schlicht die Berechtigung pages_manage_posts fehlte.

    Diese Abfrage liefert den messbaren Zustand statt einer Vermutung:
    gilt der Token noch, darf er posten, wann laeuft er ab.
    """
    if not FB_TOKEN:
        return {"gueltig": False, "darf_posten": False, "laeuft_ab": None,
                "tage_uebrig": None, "rechte": [],
                "meldung": "Es ist gar kein Seiten-Token hinterlegt."}

    antwort = requests.get(f"{HOST}/{FB_API_VERSION}/debug_token",
                           params={"input_token": FB_TOKEN,
                                   "access_token": FB_TOKEN},
                           timeout=TIMEOUT)
    inhalt = antwort.json()
    if "error" in inhalt:
        return {"gueltig": False, "darf_posten": False, "laeuft_ab": None,
                "tage_uebrig": None, "rechte": [],
                "meldung": inhalt["error"].get("message", "Facebook lehnte die Abfrage ab.")}

    daten = inhalt.get("data", {})
    rechte = daten.get("scopes") or []
    # 0 heisst bei Facebook "laeuft nicht ab" - genau das ist das Ziel.
    ablauf = daten.get("expires_at") or 0
    tage = None if ablauf == 0 else int((ablauf - time.time()) // 86400)

    gueltig = bool(daten.get("is_valid"))
    darf = "pages_manage_posts" in rechte

    if not gueltig:
        meldung = "Der Seiten-Token gilt nicht mehr."
    elif not darf:
        meldung = ("Dem Seiten-Token fehlt pages_manage_posts. "
                   "Facebook nimmt damit keinen Beitrag an.")
    elif tage is not None and tage < 0:
        meldung = "Der Seiten-Token ist abgelaufen."
    elif tage is not None:
        meldung = f"Der Seiten-Token laeuft in {tage} Tagen ab."
    else:
        meldung = "Der Seiten-Token gilt unbefristet."

    return {"gueltig": gueltig, "darf_posten": darf, "laeuft_ab": ablauf or None,
            "tage_uebrig": tage, "rechte": rechte, "meldung": meldung}

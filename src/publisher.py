"""Veröffentlicht auf Instagram – über die offizielle Instagram Graph API.

Bewusst NICHT über inoffizielle Bibliotheken (instagrapi & Co.): die verstoßen
gegen die Nutzungsbedingungen und führen regelmäßig zu Kontosperren.

Der offizielle Weg ist zweistufig:
  1. POST /{ig-user-id}/media          -> Container anlegen (Bild-URL + Text)
  2. POST /{ig-user-id}/media_publish  -> Container veröffentlichen

Wichtig: Instagram lädt das Bild selbst herunter. Es muss also unter einer
öffentlich erreichbaren HTTPS-URL liegen (MEDIA_BASE_URL).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime

import requests

from config import (IG_HOST, IG_API_VERSION, IG_TOKEN, IG_USER_ID,
                    IG_UEBER_SEITE, LOG_DATEI, MAX_POSTS_24H, MEDIA_BASE_URL)

log = logging.getLogger(__name__)

TIMEOUT = 30
MAX_VERSUCHE = 4

# Fehler, bei denen ein erneuter Versuch sinnvoll ist (Netz, Auslastung, Timeout).
VORUEBERGEHEND = {1, 2, 4, 17, 32, 341, 368, 613}
# Fehler, bei denen Wiederholen nichts bringt (Token, Rechte, kaputtes Medium).
ENDGUELTIG = {10, 100, 102, 190, 200, 9004, 9007, 2207026, 2207032}


class VeroeffentlichungsFehler(RuntimeError):
    def __init__(self, meldung: str, code: int | None = None, subcode: int | None = None):
        super().__init__(meldung)
        self.code = code
        self.subcode = subcode

    @property
    def token_problem(self) -> bool:
        return self.code in (190, 102, 10)


class KontingentErschoepft(VeroeffentlichungsFehler):
    """Instagram-Limit erreicht. Kein Fehler im eigentlichen Sinn – morgen wieder."""


@dataclass
class Ergebnis:
    ok: bool
    id: str | None = None
    meldung: str = ""
    permalink: str | None = None


# --------------------------------------------------------------------------- #
# Grundlagen
# --------------------------------------------------------------------------- #
def _basis() -> str:
    return f"{IG_HOST}/{IG_API_VERSION}"


def _pruefe_konfiguration() -> None:
    fehlend = [name for name, wert in (
        ("IG_USER_ID", IG_USER_ID),
        ("IG_ACCESS_TOKEN", IG_TOKEN),
        ("MEDIA_BASE_URL", MEDIA_BASE_URL),
    ) if not wert]
    if fehlend:
        raise VeroeffentlichungsFehler(
            "Fehlende Konfiguration: " + ", ".join(fehlend)
            + ". Siehe docs/02-INSTAGRAM-EINRICHTEN.md"
        )


def bild_url(dateiname: str) -> str:
    return f"{MEDIA_BASE_URL}/{dateiname.lstrip('/')}"


def _anfrage(methode: str, pfad: str, **params) -> dict:
    """Graph-API-Aufruf mit Wiederholung – aber nur, wo Wiederholen hilft."""
    params["access_token"] = IG_TOKEN
    url = f"{_basis()}/{pfad.lstrip('/')}"
    pause = 2.0
    letzter: VeroeffentlichungsFehler | None = None

    for versuch in range(1, MAX_VERSUCHE + 1):
        try:
            if methode == "GET":
                antwort = requests.get(url, params=params, timeout=TIMEOUT)
            else:
                antwort = requests.post(url, data=params, timeout=TIMEOUT)
        except requests.RequestException as exc:
            letzter = VeroeffentlichungsFehler(f"Netzwerkfehler: {exc}")
            log.warning("Versuch %s/%s: %s", versuch, MAX_VERSUCHE, exc)
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
        if fehler.get("error_user_msg"):
            meldung = f"{meldung} | {fehler['error_user_msg']}"

        problem = VeroeffentlichungsFehler(meldung, code, fehler.get("error_subcode"))

        # Token- und Rechtefehler: sofort abbrechen, Wiederholen ist sinnlos.
        if code in ENDGUELTIG or (code not in VORUEBERGEHEND
                                  and antwort.status_code in (400, 401, 403)):
            raise problem

        letzter = problem
        log.warning("Graph-API-Fehler (Versuch %s/%s), code=%s: %s",
                    versuch, MAX_VERSUCHE, code, meldung)
        time.sleep(pause)
        pause *= 2

    raise letzter or VeroeffentlichungsFehler("Unbekannter Fehler")


# --------------------------------------------------------------------------- #
# Kontingent
# --------------------------------------------------------------------------- #
def kontingent() -> dict[str, int]:
    daten = _anfrage("GET", f"{IG_USER_ID}/content_publishing_limit",
                     fields="config,quota_usage")
    eintrag = (daten.get("data") or [{}])[0]
    return {
        "genutzt": int(eintrag.get("quota_usage", 0)),
        "gesamt": int((eintrag.get("config") or {}).get("quota_total", 0)),
    }


def verbleibendes_kontingent() -> str:
    try:
        k = kontingent()
        return f"{k['genutzt']} von {k['gesamt'] or MAX_POSTS_24H} genutzt"
    except Exception as fehler:                      # noqa: BLE001
        return f"nicht abrufbar ({fehler})"


def _pruefe_kontingent() -> None:
    """Vor dem Posten prüfen statt hinterher am Fehler zu scheitern."""
    try:
        k = kontingent()
    except VeroeffentlichungsFehler:
        log.warning("Kontingent nicht abrufbar – versuche trotzdem zu posten.")
        return
    grenze = min(MAX_POSTS_24H, k["gesamt"]) if k["gesamt"] else MAX_POSTS_24H
    if k["genutzt"] >= grenze:
        raise KontingentErschoepft(
            f"Kontingent erschöpft: {k['genutzt']}/{grenze} Beiträge in 24 Stunden."
        )
    log.info("Kontingent: %s/%s genutzt.", k["genutzt"], grenze)


# --------------------------------------------------------------------------- #
# Veröffentlichen
# --------------------------------------------------------------------------- #
def _warte_auf_container(container_id: str, max_sekunden: int = 60,
                         takt: int = 5) -> bool:
    """True, wenn fertig. False bei Zeitüberschreitung (Bilder gehen oft trotzdem)."""
    gewartet = 0
    while gewartet < max_sekunden:
        status = _anfrage("GET", container_id, fields="status_code,status")
        code = status.get("status_code", "UNKNOWN")
        if code == "FINISHED":
            return True
        if code in ("ERROR", "EXPIRED"):
            raise VeroeffentlichungsFehler(
                f"Container {container_id} im Status {code}: {status.get('status')}"
            )
        time.sleep(takt)
        gewartet += takt
    return False


def _permalink(media_id: str) -> str | None:
    try:
        return _anfrage("GET", media_id, fields="permalink").get("permalink")
    except VeroeffentlichungsFehler:
        return None


def veroeffentliche(bild_dateiname: str, caption: str,
                    alt_text: str | None = None,
                    trockenlauf: bool = False) -> Ergebnis:
    url = bild_url(bild_dateiname)

    if trockenlauf:
        if not MEDIA_BASE_URL:
            return Ergebnis(False, None,
                            "Trockenlauf: MEDIA_BASE_URL fehlt – im Echtbetrieb "
                            "könnte Instagram das Bild nicht laden.")
        return Ergebnis(True, None, f"Trockenlauf – würde posten: {url}")

    _pruefe_konfiguration()
    _pruefe_kontingent()

    params = {"image_url": url, "caption": caption}
    if alt_text:
        params["alt_text"] = alt_text[:1000]

    container = _anfrage("POST", f"{IG_USER_ID}/media", **params)
    container_id = container.get("id")
    if not container_id:
        raise VeroeffentlichungsFehler(f"Keine Container-ID erhalten: {container}")

    if not _warte_auf_container(container_id):
        log.warning("Container-Status unklar – Veröffentlichung wird trotzdem versucht.")

    ergebnis = _anfrage("POST", f"{IG_USER_ID}/media_publish", creation_id=container_id)
    media_id = ergebnis.get("id")
    if not media_id:
        raise VeroeffentlichungsFehler(f"Publish lieferte keine Media-ID: {ergebnis}")

    return Ergebnis(True, media_id, "Veröffentlicht.", _permalink(media_id))


def veroeffentliche_carousel(bild_dateinamen: list[str], caption: str,
                             alt_texte: list[str] | None = None,
                             trockenlauf: bool = False) -> Ergebnis:
    """Mehrere Bilder als ein Carousel-Beitrag.

    Dreistufig statt zweistufig:
      1. je Bild ein Container mit is_carousel_item=true
      2. ein Eltern-Container mit media_type=CAROUSEL und children=...
      3. Eltern-Container veröffentlichen
    """
    if not 2 <= len(bild_dateinamen) <= 10:
        raise VeroeffentlichungsFehler(
            f"Carousel braucht 2 bis 10 Bilder, bekommen: {len(bild_dateinamen)}"
        )

    urls = [bild_url(n) for n in bild_dateinamen]

    if trockenlauf:
        if not MEDIA_BASE_URL:
            return Ergebnis(False, None, "Trockenlauf: MEDIA_BASE_URL fehlt.")
        return Ergebnis(True, None,
                        f"Trockenlauf – würde {len(urls)} Slides posten:\n  "
                        + "\n  ".join(urls))

    _pruefe_konfiguration()
    _pruefe_kontingent()

    kinder = []
    for nr, url in enumerate(urls):
        params = {"image_url": url, "is_carousel_item": "true"}
        if alt_texte and nr < len(alt_texte) and alt_texte[nr]:
            params["alt_text"] = alt_texte[nr][:1000]
        antwort = _anfrage("POST", f"{IG_USER_ID}/media", **params)
        kind = antwort.get("id")
        if not kind:
            raise VeroeffentlichungsFehler(f"Slide {nr + 1}: keine Container-ID ({antwort})")
        kinder.append(kind)
        log.info("Slide %s/%s als Container %s", nr + 1, len(urls), kind)

    for kind in kinder:
        _warte_auf_container(kind, max_sekunden=60)

    eltern = _anfrage("POST", f"{IG_USER_ID}/media",
                      media_type="CAROUSEL",
                      children=",".join(kinder),
                      caption=caption)
    eltern_id = eltern.get("id")
    if not eltern_id:
        raise VeroeffentlichungsFehler(f"Kein Carousel-Container: {eltern}")

    if not _warte_auf_container(eltern_id):
        log.warning("Carousel-Status unklar – Veröffentlichung wird trotzdem versucht.")

    ergebnis = _anfrage("POST", f"{IG_USER_ID}/media_publish", creation_id=eltern_id)
    media_id = ergebnis.get("id")
    if not media_id:
        raise VeroeffentlichungsFehler(f"Publish lieferte keine Media-ID: {ergebnis}")

    return Ergebnis(True, media_id, f"Carousel mit {len(urls)} Slides veröffentlicht.",
                    _permalink(media_id))


def veroeffentliche_reel(video_dateiname: str, caption: str,
                         titelbild_dateiname: str | None = None,
                         trockenlauf: bool = False) -> Ergebnis:
    """Video als Reel. Instagram lädt auch das Video selbst herunter.

    Reels brauchen deutlich länger als Bilder – Instagram muss transkodieren.
    Deshalb wird hier bis zu fünf Minuten auf den Container gewartet.
    """
    url = bild_url(video_dateiname)
    cover = bild_url(titelbild_dateiname) if titelbild_dateiname else None

    if trockenlauf:
        if not MEDIA_BASE_URL:
            return Ergebnis(False, None, "Trockenlauf: MEDIA_BASE_URL fehlt.")
        text = f"Trockenlauf – würde Reel posten: {url}"
        return Ergebnis(True, None, text + (f"\n  Titelbild: {cover}" if cover else ""))

    _pruefe_konfiguration()
    _pruefe_kontingent()

    params = {"media_type": "REELS", "video_url": url, "caption": caption}
    if cover:
        params["cover_url"] = cover

    container = _anfrage("POST", f"{IG_USER_ID}/media", **params)
    container_id = container.get("id")
    if not container_id:
        raise VeroeffentlichungsFehler(f"Keine Container-ID erhalten: {container}")

    # Video-Transkodierung: Metas Empfehlung ist, höchstens 5 Minuten zu warten.
    if not _warte_auf_container(container_id, max_sekunden=300, takt=15):
        raise VeroeffentlichungsFehler(
            "Das Video wurde in 5 Minuten nicht verarbeitet. Meist ist die Datei "
            "zu groß oder das Format wird nicht unterstützt (MP4/MOV, H.264/AAC).")

    ergebnis = _anfrage("POST", f"{IG_USER_ID}/media_publish", creation_id=container_id)
    media_id = ergebnis.get("id")
    if not media_id:
        raise VeroeffentlichungsFehler(f"Publish lieferte keine Media-ID: {ergebnis}")

    return Ergebnis(True, media_id, "Reel veröffentlicht.", _permalink(media_id))


def pruefe_zugang() -> Ergebnis:
    """Selbsttest: Token gültig, Konto erreichbar?

    Die verfügbaren Felder hängen vom Weg ab: `account_type` gibt es nur auf
    graph.instagram.com. Geht der Zugriff über die Facebook-Seite, kennt die
    Graph API dieses Feld nicht und antwortet mit Fehler 100 – die Abfrage
    muss sich also nach dem Weg richten.
    """
    _pruefe_konfiguration()
    felder = ("id,username,media_count" if IG_UEBER_SEITE
              else "id,username,account_type,media_count")
    try:
        daten = _anfrage("GET", IG_USER_ID, fields=felder)
    except VeroeffentlichungsFehler as fehler:
        hinweis = " (Token abgelaufen oder ungültig – Schritt 4 der Anleitung)" \
            if fehler.token_problem else ""
        return Ergebnis(False, meldung=f"{fehler}{hinweis}")
    weg = "über die Facebook-Seite" if IG_UEBER_SEITE else f"Kontotyp {daten.get('account_type')}"
    return Ergebnis(
        True, daten.get("id"),
        f"@{daten.get('username')} · {weg} · {daten.get('media_count')} Beiträge",
    )


# --------------------------------------------------------------------------- #
# Protokoll
# --------------------------------------------------------------------------- #
def protokolliere(thema_id: str, bild: str, ergebnis: Ergebnis | None,
                  fehler: str | None = None) -> None:
    """Eine Zeile JSON je Versuch – auch bei Fehlschlag. Macht Störungen nachvollziehbar."""
    LOG_DATEI.parent.mkdir(parents=True, exist_ok=True)
    zeile = {
        "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
        "thema": thema_id,
        "bild": bild,
        "erfolg": bool(ergebnis and ergebnis.ok and ergebnis.id),
        "media_id": ergebnis.id if ergebnis else None,
        "permalink": ergebnis.permalink if ergebnis else None,
        "fehler": fehler,
    }
    with LOG_DATEI.open("a", encoding="utf-8") as f:
        f.write(json.dumps(zeile, ensure_ascii=False) + "\n")

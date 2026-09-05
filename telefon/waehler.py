"""Arbeitet eine Anrufliste ab - langsam, geprüft und abbrechbar.

Der Wähler ist bewusst dumm gehalten. Er entscheidet nichts: Ob eine Nummer
gewählt werden darf, sagt freigabe.darf_anrufen(), und zwar zweimal - einmal
beim Zusammenstellen und einmal in der Sekunde vor dem Wählen. Dazwischen
können Minuten liegen, in denen ein anderes Gespräch einen Widerspruch
erzeugt oder das Zeitfenster zugeht.

Tempo mit Absicht: eine Leitung, 45 Sekunden Pause. Wer parallel wählt und
hetzt, erzeugt genau das Muster, an dem Netzbetreiber und Bundesnetzagentur
Massenwerbung erkennen - und hat am Ende des Tages nicht mehr Termine,
sondern mehr Beschwerden.
"""
from __future__ import annotations

import argparse
import csv
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import einstellungen as e
import freigabe
import protokoll
import zeitfenster
from nummern import NummernFehler, normalisieren

log = logging.getLogger("telefon.waehler")

SPALTEN = ("nummer", "betrieb", "gewerk", "ort", "notiz")


@dataclass
class Kontakt:
    nummer: str
    betrieb: str = ""
    gewerk: str = ""
    ort: str = ""
    notiz: str = ""

    def als_dict(self) -> dict:
        return {"nummer": self.nummer, "betrieb": self.betrieb,
                "gewerk": self.gewerk, "ort": self.ort, "notiz": self.notiz}


def liste_lesen(pfad: Path) -> tuple[list[Kontakt], list[str]]:
    """CSV mit Kopfzeile einlesen. Gibt (Kontakte, Fehlerzeilen) zurück."""
    kontakte, fehler = [], []
    with pfad.open(encoding="utf-8-sig", newline="") as f:
        leser = csv.DictReader(f)
        if leser.fieldnames is None or "nummer" not in leser.fieldnames:
            raise ValueError(
                f"{pfad} braucht eine Kopfzeile mit mindestens 'nummer'. "
                f"Gefunden: {leser.fieldnames}"
            )
        for zeile_nr, zeile in enumerate(leser, start=2):
            roh = (zeile.get("nummer") or "").strip()
            if not roh:
                continue
            try:
                nummer = normalisieren(roh)
            except NummernFehler as f_:
                fehler.append(f"Zeile {zeile_nr}: {f_}")
                continue
            kontakte.append(Kontakt(
                nummer=nummer,
                betrieb=(zeile.get("betrieb") or "").strip(),
                gewerk=(zeile.get("gewerk") or "").strip(),
                ort=(zeile.get("ort") or "").strip(),
                notiz=(zeile.get("notiz") or "").strip(),
            ))
    return kontakte, fehler


def _twilio_client():
    from twilio.rest import Client
    return Client(e.TWILIO_SID, e.TWILIO_TOKEN)


def waehlen(kontakt: Kontakt, client=None) -> str | None:
    """Einen Anruf auslösen. Gibt die Twilio-Anruf-ID zurück, oder None.

    machine_detection lässt Twilio prüfen, ob ein Mensch oder eine Mailbox
    abnimmt. Bei einer Mailbox wird sofort aufgelegt: Ein Werbetext auf dem
    Anrufbeantworter ist derselbe Werbeanruf, nur dass niemand widersprechen
    kann.
    """
    urteil = freigabe.darf_anrufen(kontakt.nummer)
    if not urteil:
        protokoll.eintragen(kontakt.nummer, ereignis="uebersprungen",
                            grund=urteil.grund, betrieb=kontakt.betrieb)
        log.info("übersprungen %s: %s", kontakt.nummer, urteil.grund)
        return None

    if e.TROCKENLAUF:
        protokoll.eintragen(kontakt.nummer, ereignis="trockenlauf",
                            betrieb=kontakt.betrieb)
        log.info("TROCKENLAUF - würde wählen: %s (%s)",
                 kontakt.nummer, kontakt.betrieb or "ohne Namen")
        return None

    client = client or _twilio_client()
    anruf = client.calls.create(
        to=kontakt.nummer,
        from_=e.TWILIO_NUMMER,
        url=f"{e.OEFFENTLICHE_URL}/twiml",
        status_callback=f"{e.OEFFENTLICHE_URL}/status",
        status_callback_event=["completed"],
        machine_detection="Enable",
        # Nach 25 Sekunden ist klar, dass niemand rangeht. Länger klingeln
        # zu lassen ist reine Belästigung.
        timeout=25,
    )

    import server
    server.kontakt_hinterlegen(anruf.sid, kontakt.als_dict())
    protokoll.eintragen(kontakt.nummer, ereignis="gewaehlt",
                        call_sid=anruf.sid, betrieb=kontakt.betrieb,
                        gewerk=kontakt.gewerk, ort=kontakt.ort)
    log.info("gewählt %s (%s) -> %s", kontakt.nummer,
             kontakt.betrieb or "ohne Namen", anruf.sid)
    return anruf.sid


def lauf(pfad: Path, hoechstens: int | None = None) -> dict[str, int]:
    """Die Liste einmal durchgehen. Gibt eine Zählung zurück."""
    kontakte, fehler = liste_lesen(pfad)
    for zeile in fehler:
        log.warning("Liste fehlerhaft - %s", zeile)

    offen, grund = zeitfenster.erlaubt()
    if not offen:
        naechstes = zeitfenster.naechstes_fenster()
        log.warning("Kein Anruf: %s. Nächstes Fenster: %s",
                    grund, naechstes.strftime("%a %d.%m. %H:%M"))
        return {"gelesen": len(kontakte), "gewaehlt": 0,
                "uebersprungen": 0, "fehlerhafte_zeilen": len(fehler)}

    client = None if e.TROCKENLAUF else _twilio_client()
    zahlen = {"gelesen": len(kontakte), "gewaehlt": 0, "uebersprungen": 0,
              "fehlerhafte_zeilen": len(fehler)}
    grenze = hoechstens or e.MAX_ANRUFE_PRO_TAG

    for kontakt in kontakte:
        if zahlen["gewaehlt"] >= grenze:
            log.info("Grenze von %s Anrufen erreicht", grenze)
            break
        # Zweite Prüfung: Das Zeitfenster kann mitten im Lauf zugehen.
        if not zeitfenster.erlaubt()[0]:
            log.info("Zeitfenster geschlossen - Lauf beendet")
            break

        if waehlen(kontakt, client):
            zahlen["gewaehlt"] += 1
            time.sleep(e.PAUSE_ZWISCHEN_ANRUFEN)
        else:
            zahlen["uebersprungen"] += 1

    log.info("Lauf beendet: %s", zahlen)
    return zahlen


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")
    p = argparse.ArgumentParser(description="Anrufliste abarbeiten")
    p.add_argument("liste", type=Path, help="CSV mit Spalte 'nummer'")
    p.add_argument("--hoechstens", type=int,
                   help="Obergrenze für diesen Lauf")
    p.add_argument("--pruefen", action="store_true",
                   help="nur zeigen, welche Nummern durchkämen")
    args = p.parse_args()

    if args.pruefen:
        kontakte, fehler = liste_lesen(args.liste)
        for zeile in fehler:
            print("FEHLER  ", zeile)
        for kontakt in kontakte:
            urteil = freigabe.darf_anrufen(kontakt.nummer)
            marke = "JA  " if urteil else "nein"
            print(f"{marke} {kontakt.nummer:16} {kontakt.betrieb[:28]:28} "
                  f"{urteil.grund}")
        return 0

    fehlt = e.fehlende_zugaenge()
    if fehlt and not e.TROCKENLAUF:
        print("Es fehlen Zugänge: " + ", ".join(fehlt))
        return 1

    lauf(args.liste, args.hoechstens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

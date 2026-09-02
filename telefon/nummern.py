"""Rufnummern normalisieren und einordnen.

Eine Nummer taucht in Listen in einem Dutzend Schreibweisen auf:
"0208 1234567", "+49 (0)208 123-4567", "0049208...". Sperrliste und
Anrufprotokoll funktionieren nur, wenn beide dieselbe Schreibweise sehen.
Deshalb läuft jede Nummer, egal woher, zuerst durch normalisieren().

Zielformat ist E.164: führendes Plus, Ländervorwahl, keine Trennzeichen.
Das ist auch das Format, das Twilio erwartet.
"""
from __future__ import annotations

import re

# Vorwahlbereiche für deutsche Mobilfunknummern (Bundesnetzagentur-Plan 15x,
# 16x, 17x). Hinter ihnen steckt oft eine Privatperson - siehe MOBIL_ERLAUBT.
MOBIL_PREFIXE = ("15", "16", "17")

# Rufnummern, bei denen ein Werbeanruf von vornherein ausscheidet: Notrufe,
# Behördennummern, Sonderdienste, teure Servicerufnummern.
VERBOTENE_PREFIXE = ("110", "112", "115", "116", "118", "137", "700", "800",
                     "900", "1801", "1802", "1803", "1805", "1806")


class NummernFehler(ValueError):
    pass


def normalisieren(roh: str, land: str = "49") -> str:
    """Beliebige Schreibweise -> E.164, z. B. '+492081234567'.

    Wirft NummernFehler statt still etwas Falsches zurückzugeben - eine
    fehlerhaft geratene Nummer würde einen Fremden anklingeln lassen.
    """
    if not roh or not roh.strip():
        raise NummernFehler("leere Rufnummer")

    text = roh.strip()
    # Klammern um die verkehrte Null: "+49 (0)208" -> "+49 208".
    text = re.sub(r"\(0\)", "", text)
    plus = text.lstrip().startswith("+")
    ziffern = re.sub(r"\D", "", text)

    if not ziffern:
        raise NummernFehler(f"keine Ziffern in {roh!r}")

    if plus:
        rumpf = ziffern
    elif ziffern.startswith("00"):
        rumpf = ziffern[2:]
    elif ziffern.startswith("0"):
        # Nationale Schreibweise: führende Null durch Ländervorwahl ersetzen.
        rumpf = land + ziffern[1:]
    else:
        # Ohne Null und ohne Plus - vermutlich schon mit Ländervorwahl.
        # Sieht es nicht danach aus, ist die Nummer unbrauchbar.
        if not ziffern.startswith(land):
            raise NummernFehler(
                f"{roh!r} ist weder national (führende 0) noch international"
            )
        rumpf = ziffern

    if not 8 <= len(rumpf) <= 15:
        raise NummernFehler(f"{roh!r} ergibt {len(rumpf)} Stellen - unplausibel")

    return "+" + rumpf


def national(nummer: str, land: str = "49") -> str:
    """E.164 zurück in die nationale Form ('+492081234567' -> '02081234567')."""
    ziffern = nummer.lstrip("+")
    return "0" + ziffern[len(land):] if ziffern.startswith(land) else nummer


def ist_mobil(nummer: str, land: str = "49") -> bool:
    if not nummer.startswith("+" + land):
        return False
    rest = nummer[1 + len(land):]
    return rest.startswith(MOBIL_PREFIXE)


def ist_verboten(nummer: str, land: str = "49") -> bool:
    """Notruf-, Behörden- und Sonderrufnummern."""
    if not nummer.startswith("+" + land):
        return False
    rest = nummer[1 + len(land):]
    return rest.startswith(VERBOTENE_PREFIXE)

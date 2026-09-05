"""Wann darf gewählt werden.

Das UWG nennt keine Uhrzeiten. Die Rechtsprechung tut es indirekt: Ein Anruf
außerhalb der üblichen Geschäftszeiten ist eine zusätzliche Belästigung und
verschlechtert jede Bewertung nach § 7 UWG. Deshalb hier eng gefasst:
Werktags 9 bis 17 Uhr, freitags bis 15 Uhr, nie an Wochenenden, nie an
Feiertagen, und eine Mittagspause, in der kleine Betriebe essen.

Feiertage sind die von Nordrhein-Westfalen - dort sitzt der Betrieb und dort
liegt das Einzugsgebiet. Wer bundesweit anruft, muss das hier erweitern.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ZEITZONE = ZoneInfo("Europe/Berlin")

# Wochentag (0 = Montag) -> (Beginn, Ende). Freitagnachmittag ist auf dem Bau
# und im Handwerksbüro faktisch Feierabend.
FENSTER = {
    0: (time(9, 0), time(17, 0)),
    1: (time(9, 0), time(17, 0)),
    2: (time(9, 0), time(17, 0)),
    3: (time(9, 0), time(17, 0)),
    4: (time(9, 0), time(15, 0)),
}

MITTAGSPAUSE = (time(12, 30), time(13, 30))


def _ostersonntag(jahr: int) -> date:
    """Gaußsche Osterformel in der Fassung von Butcher - gilt ohne Ausnahme."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def feiertage(jahr: int) -> set[date]:
    """Gesetzliche Feiertage in Nordrhein-Westfalen."""
    ostern = _ostersonntag(jahr)
    return {
        date(jahr, 1, 1),                 # Neujahr
        ostern - timedelta(days=2),       # Karfreitag
        ostern + timedelta(days=1),       # Ostermontag
        date(jahr, 5, 1),                 # Tag der Arbeit
        ostern + timedelta(days=39),      # Christi Himmelfahrt
        ostern + timedelta(days=50),      # Pfingstmontag
        ostern + timedelta(days=60),      # Fronleichnam
        date(jahr, 10, 3),                # Tag der Deutschen Einheit
        date(jahr, 11, 1),                # Allerheiligen
        date(jahr, 12, 25),
        date(jahr, 12, 26),
    }


def erlaubt(zeitpunkt: datetime | None = None) -> tuple[bool, str]:
    """(darf gewählt werden, Begründung).

    Die Begründung wandert ins Protokoll, damit im Nachhinein nachvollziehbar
    ist, warum ein Lauf nichts getan hat.
    """
    jetzt = (zeitpunkt or datetime.now(ZEITZONE))
    if jetzt.tzinfo is None:
        jetzt = jetzt.replace(tzinfo=ZEITZONE)
    else:
        jetzt = jetzt.astimezone(ZEITZONE)

    tag = jetzt.date()
    if tag in feiertage(tag.year):
        return False, f"Feiertag in NRW ({tag.isoformat()})"

    fenster = FENSTER.get(jetzt.weekday())
    if fenster is None:
        return False, "Wochenende"

    beginn, ende = fenster
    uhrzeit = jetzt.time()
    if uhrzeit < beginn:
        return False, f"vor {beginn.strftime('%H:%M')} Uhr"
    if uhrzeit >= ende:
        return False, f"nach {ende.strftime('%H:%M')} Uhr"
    if MITTAGSPAUSE[0] <= uhrzeit < MITTAGSPAUSE[1]:
        return False, "Mittagspause"

    return True, "innerhalb der Geschäftszeit"


def naechstes_fenster(ab: datetime | None = None) -> datetime:
    """Wann darf frühestens wieder gewählt werden.

    Sucht in Viertelstundenschritten - grob genug, um schnell zu sein, fein
    genug für Fenstergrenzen, die alle auf der halben Stunde liegen.
    """
    zeitpunkt = (ab or datetime.now(ZEITZONE)).astimezone(ZEITZONE)
    # 4 Wochen reichen: Länger als ein Monat ist keine Feiertagskette in NRW.
    for _ in range(4 * 7 * 24 * 4):
        if erlaubt(zeitpunkt)[0]:
            return zeitpunkt
        zeitpunkt += timedelta(minutes=15)
    raise RuntimeError("in vier Wochen kein erlaubtes Zeitfenster gefunden")

"""Darf diese Nummer jetzt angerufen werden?

Ein einziges Nadelöhr. Sperrliste, Zeitfenster, Tageslimit, Wiederwahlabstand
und Nummernart werden nicht an fünf Stellen im Code geprüft, sondern hier -
verstreute Prüfungen sind der Weg, auf dem später eine davon vergessen wird.

darf_anrufen() wird zweimal aufgerufen: beim Zusammenstellen der Wahlliste
und noch einmal unmittelbar vor dem Wählen. Der zweite Aufruf fängt ab, was
sich seit dem ersten geändert hat - ein Widerspruch aus einem parallel
laufenden Gespräch etwa, oder das Ende des Zeitfensters mitten im Lauf.
"""
from __future__ import annotations

from dataclasses import dataclass

import einstellungen as e
import protokoll
import sperrliste
import zeitfenster
from nummern import NummernFehler, ist_mobil, ist_verboten, normalisieren


@dataclass(frozen=True)
class Urteil:
    erlaubt: bool
    grund: str
    nummer: str = ""

    def __bool__(self) -> bool:
        return self.erlaubt


def darf_anrufen(rohnummer: str, zeitpunkt=None) -> Urteil:
    """Alle Ausschlussgründe der Reihe nach. Erster Treffer gewinnt."""
    try:
        nummer = normalisieren(rohnummer)
    except NummernFehler as fehler:
        return Urteil(False, f"unbrauchbare Nummer: {fehler}")

    if ist_verboten(nummer):
        return Urteil(False, "Notruf-, Behörden- oder Sonderrufnummer", nummer)

    if sperrliste.gesperrt(nummer):
        eintrag = sperrliste.eintrag(nummer) or {}
        return Urteil(False, f"gesperrt ({eintrag.get('grund', 'ohne Grund')})",
                      nummer)

    if ist_mobil(nummer) and not e.MOBIL_ERLAUBT:
        return Urteil(False, "Mobilnummer - Verbraucherverdacht", nummer)

    offen, grund = zeitfenster.erlaubt(zeitpunkt)
    if not offen:
        return Urteil(False, f"außerhalb der Anrufzeit: {grund}", nummer)

    bisher = len(protokoll.versuche(nummer))
    if bisher >= e.MAX_VERSUCHE_JE_NUMMER:
        return Urteil(False, f"bereits {bisher} Versuche", nummer)

    if not protokoll.abstand_eingehalten(nummer, e.ABSTAND_TAGE):
        letzter = protokoll.zuletzt_gewaehlt(nummer)
        return Urteil(False,
                      f"zuletzt am {letzter:%d.%m.%Y}, Abstand "
                      f"{e.ABSTAND_TAGE} Tage nicht erreicht", nummer)

    heute = protokoll.anrufe_heute()
    if heute >= e.MAX_ANRUFE_PRO_TAG:
        return Urteil(False, f"Tageslimit erreicht ({heute})", nummer)

    return Urteil(True, "frei", nummer)

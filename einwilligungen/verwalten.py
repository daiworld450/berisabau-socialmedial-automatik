"""Einwilligungen erfassen und die Freigabeliste daraus erzeugen.

Aufruf:
    python einwilligungen/verwalten.py            Lage anzeigen
    python einwilligungen/verwalten.py --neu      Einwilligung eintragen
    python einwilligungen/verwalten.py --erneuern Freigabeliste neu schreiben

Zwei Dateien, mit Absicht getrennt:

    einwilligungen/register.json    Kundenname, Objekt, Datum, Nachweis.
                                    Personenbezogen - bleibt lokal, ist in
                                    .gitignore gesperrt.

    content/medien/freigabe.json    Nur Dateinamen. Keine Personendaten.
                                    Wird hier weiter geschrieben, aber seit
                                    dem 01.09.2026 von KEINEM Code mehr
                                    gelesen: planer.py filtert nicht mehr
                                    danach.

Wer diese Trennung aufhebt, veroeffentlicht Kundendaten.

Stand 01.09.2026: Die Codesperre in planer.py wurde auf Wunsch des Inhabers
entfernt (Commit f068b5a). Dieses Werkzeug fuehrt seitdem nur noch Buch,
damit nachvollziehbar bleibt, wer wofuer sein Einverstaendnis gegeben hat.
Es haelt kein Foto mehr zurueck. Die Pruefung liegt beim Menschen, vor dem
Druck auf Freigeben in Telegram.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HIER     = Path(__file__).resolve().parent
WURZEL   = HIER.parent
REGISTER = HIER / "register.json"
FREIGABE = WURZEL / "content" / "medien" / "freigabe.json"
MEDIEN   = WURZEL / "content" / "medien"

BILDENDUNGEN = {".jpg", ".jpeg", ".png"}
VIDEOENDUNGEN = {".mp4", ".mov", ".m4v"}


def _lies() -> dict:
    if REGISTER.exists():
        return json.loads(REGISTER.read_text(encoding="utf-8"))
    return {"_hinweis": "Personenbezogen. Nicht ins Repo. Siehe .gitignore.",
            "eintraege": []}


def _schreib(daten: dict) -> None:
    REGISTER.parent.mkdir(exist_ok=True)
    REGISTER.write_text(json.dumps(daten, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    REGISTER.chmod(0o600)


def alle_medien() -> list[Path]:
    if not MEDIEN.exists():
        return []
    return sorted(p for p in MEDIEN.rglob("*")
                  if p.is_file()
                  and p.suffix.lower() in BILDENDUNGEN | VIDEOENDUNGEN
                  and not p.name.startswith("."))


def freigabe_schreiben(daten: dict) -> int:
    """Aus dem Register die oeffentliche Freigabeliste erzeugen.

    Nur Dateinamen wandern hinueber. Der Kundenname bleibt im Register.
    """
    frei = sorted({name
                   for e in daten["eintraege"] if e.get("status") == "erteilt"
                   for name in e.get("dateien", [])})
    FREIGABE.parent.mkdir(parents=True, exist_ok=True)
    FREIGABE.write_text(json.dumps({
        "_hinweis": ("Erzeugt aus einwilligungen/register.json. Nicht von Hand "
                     "aendern. Enthaelt bewusst keine Kundendaten."),
        "stand": date.today().isoformat(),
        "freigegeben": frei,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(frei)


def lage() -> None:
    daten = _lies()
    medien = alle_medien()
    erfasst = {n for e in daten["eintraege"] for n in e.get("dateien", [])}
    frei = {n for e in daten["eintraege"] if e.get("status") == "erteilt"
            for n in e.get("dateien", [])}

    print(f"\n{len(medien)} Medien in content/medien/\n")
    print(f"  freigegeben  {len(frei)}")
    print(f"  angefragt    {len(erfasst) - len(frei)}")
    unerfasst = [m for m in medien if m.name not in erfasst]
    print(f"  gar nichts   {len(unerfasst)}")

    if unerfasst:
        print("\nOhne jeden Eintrag - diese Dateien sind gesperrt:")
        for m in unerfasst[:20]:
            print(f"  · {m.relative_to(WURZEL)}")
        if len(unerfasst) > 20:
            print(f"  … und {len(unerfasst) - 20} weitere")

    offen = [e for e in daten["eintraege"] if e.get("status") != "erteilt"]
    if offen:
        print("\nAngefragt, aber noch keine Antwort:")
        for e in offen:
            print(f"  · {e['kunde']} ({e['objekt']}) — gefragt am {e['gefragt_am']}")

    print(f"\nFreigabeliste: {FREIGABE.relative_to(WURZEL)}")


def neu() -> None:
    daten = _lies()
    medien = alle_medien()
    erfasst = {n for e in daten["eintraege"] for n in e.get("dateien", [])}
    offen = [m for m in medien if m.name not in erfasst]

    if not offen:
        print("Alle Medien sind bereits erfasst.")
        return

    print("\nNoch nicht erfasste Dateien:\n")
    for i, m in enumerate(offen, 1):
        print(f"  {i:2}  {m.relative_to(WURZEL)}")

    print("\nWelche Dateien gehoeren zu diesem Kunden?")
    print("Nummern mit Komma, oder 'alle'.")
    wahl = input("> ").strip()
    if wahl.lower() == "alle":
        gewaehlt = offen
    else:
        try:
            nummern = [int(x) for x in wahl.replace(" ", "").split(",") if x]
            gewaehlt = [offen[n - 1] for n in nummern]
        except (ValueError, IndexError):
            sys.exit("Ungueltige Auswahl, nichts geaendert.")
    if not gewaehlt:
        sys.exit("Nichts ausgewaehlt.")

    print(f"\n{len(gewaehlt)} Datei(en) gewaehlt.\n")
    kunde  = input("Kunde (Name)            : ").strip()
    objekt = input("Objekt (Ort/Strasse)    : ").strip()
    if not kunde:
        sys.exit("Ohne Kundennamen ergibt der Eintrag keinen Sinn.")

    print("\nWofuer gilt die Zustimmung? Leer = alles.")
    kanaele = input("Kanaele [Instagram, Facebook, Website]: ").strip() \
              or "Instagram, Facebook, Website"

    print("\nStatus:")
    print("  1  erteilt   — der Kunde hat zugestimmt")
    print("  2  gefragt   — Anfrage raus, Antwort steht aus")
    status = "erteilt" if input("> ").strip() == "1" else "gefragt"

    nachweis = ""
    if status == "erteilt":
        print("\nWie liegt die Zustimmung vor?")
        print("(z. B. 'WhatsApp 01.09.2026, Screenshot in nachweise/')")
        nachweis = input("> ").strip()
        if not nachweis:
            print("\nOhne Nachweisangabe ist der Eintrag wertlos —")
            print("genau dieser Beleg zaehlt im Streitfall.")
            if input("Trotzdem als erteilt eintragen? [j/N] ").lower() != "j":
                status = "gefragt"

    daten["eintraege"].append({
        "kunde": kunde,
        "objekt": objekt,
        "gefragt_am": date.today().isoformat(),
        "status": status,
        "kanaele": [k.strip() for k in kanaele.split(",") if k.strip()],
        "nachweis": nachweis,
        "dateien": [m.name for m in gewaehlt],
    })
    _schreib(daten)
    anzahl = freigabe_schreiben(daten)
    print(f"\nEingetragen. Freigabeliste: {anzahl} Datei(en) frei.")
    if status != "erteilt":
        print("Status 'gefragt' — die Dateien bleiben gesperrt, bis der Kunde antwortet.")


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--neu":
        neu()
    elif arg == "--erneuern":
        anzahl = freigabe_schreiben(_lies())
        print(f"Freigabeliste neu geschrieben: {anzahl} Datei(en).")
    else:
        lage()


if __name__ == "__main__":
    main()

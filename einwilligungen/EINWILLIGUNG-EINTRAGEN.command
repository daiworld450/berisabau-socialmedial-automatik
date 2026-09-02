#!/bin/zsh
# ---------------------------------------------------------------------------
# Traegt die Einwilligung eines Kunden ein und schreibt die Freigabeliste neu.
#
# Doppelklicken.
#
# ACHTUNG, geaendert am 01.09.2026: Frueher hat ein fehlender Eintrag hier ein
# Foto technisch gesperrt. Diese Sperre hat der Inhaber am selben Tag wieder
# entfernen lassen, Commit f068b5a. Das Werkzeug fuehrt also nur noch Buch.
# Es haelt kein Foto mehr zurueck.
#
# Die Pflicht bleibt: ohne Einverstaendnis des Kunden geht sein Foto nicht
# raus. Nur prueft das jetzt ein Mensch vor dem Druck auf Freigeben in
# Telegram, kein Code.
# ---------------------------------------------------------------------------
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

echo "═══════════════════════════════════════════"
echo "  Einwilligung eintragen"
echo "═══════════════════════════════════════════"

python3 einwilligungen/verwalten.py

echo
printf "Jetzt eine Einwilligung eintragen? [J/n] "
read -r A
if [ "$A" != "n" ] && [ "$A" != "N" ]; then
  python3 einwilligungen/verwalten.py --neu
fi

echo
echo "Text zum Verschicken: einwilligungen/VORLAGE-WHATSAPP.md"
echo "Antwort des Kunden als Screenshot in einwilligungen/nachweise/ ablegen."
echo
echo "Fenster kann geschlossen werden."
read -r

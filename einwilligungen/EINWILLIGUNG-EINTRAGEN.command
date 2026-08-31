#!/bin/zsh
# ---------------------------------------------------------------------------
# Traegt die Einwilligung eines Kunden ein und schreibt die Freigabeliste neu.
#
# Doppelklicken. Ohne Eintrag hier bleibt ein Foto gesperrt und kann nicht
# in einem Beitrag landen - das ist so gewollt.
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

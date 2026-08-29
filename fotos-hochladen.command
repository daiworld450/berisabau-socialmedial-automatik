#!/bin/zsh
# Lädt Baustellenfotos in den Eingang des Social-Repos.
#
# So geht es:
#   1. Fotos in den Ordner  ~/Desktop/Berisa Baufotos/HOCHLADEN  legen
#   2. Diese Datei doppelklicken
#   3. Fertig - die Automatik verarbeitet sie beim nächsten Lauf
#
# Der Zwischenordner ist Absicht: Das Repo ist öffentlich. Nur was du bewusst
# nach HOCHLADEN legst, geht raus. Der Rest der Fotosammlung bleibt privat.

export PATH="$HOME/.local/bin:$PATH"
REPO="daiworld450/berisabau-socialmedial-automatik"
QUELLE="$HOME/Desktop/Berisa Baufotos/HOCHLADEN"
ERLEDIGT="$HOME/Desktop/Berisa Baufotos/HOCHGELADEN"

mkdir -p "$QUELLE" "$ERLEDIGT"

if ! command -v gh >/dev/null 2>&1; then
  echo "Fehler: gh (GitHub CLI) nicht gefunden."; read -r; exit 1
fi

typeset -a DATEIEN
DATEIEN=("$QUELLE"/*.(jpg|jpeg|JPG|JPEG|png|PNG)(N))

if (( ${#DATEIEN} == 0 )); then
  echo "Keine Fotos in:"
  echo "  $QUELLE"
  echo
  echo "Leg die Bilder dort hinein und starte diese Datei erneut."
  echo "Erlaubt sind JPG und PNG. HEIC bitte vorher umwandeln"
  echo "(in der Fotos-App: Exportieren -> JPEG)."
  echo
  echo "Fenster kann geschlossen werden."
  read -r
  exit 0
fi

echo "${#DATEIEN} Foto(s) gefunden."
echo
echo "ACHTUNG: Das Repo ist öffentlich. Prüfe vorher:"
echo "  - keine erkennbaren Personen ohne Einverständnis"
echo "  - keine Klingelschilder, Hausnummern, Kennzeichen, Kundennamen"
echo
printf "Hochladen? [j/N] "
read -r ANTWORT
[[ "$ANTWORT" == "j" || "$ANTWORT" == "J" ]] || { echo "Abgebrochen."; read -r; exit 0; }
echo

STAMP=$(date +%Y%m%d)
N=0
for F in "${DATEIEN[@]}"; do
  BASIS=$(basename "$F")
  ENDUNG="${BASIS##*.}"
  # Sprechender, kollisionsfreier Name
  ZIEL="${STAMP}-$(printf '%02d' $((N+1))).${ENDUNG:l}"
  PFAD="content/medien/eingang/$ZIEL"

  GROESSE=$(( $(stat -f%z "$F") / 1024 ))
  printf "  %-28s %5s KB  -> %s ... " "$BASIS" "$GROESSE" "$ZIEL"

  if [ "$GROESSE" -gt 20480 ]; then
    echo "ZU GROSS (über 20 MB), übersprungen"
    continue
  fi

  SHA=$(gh api "repos/$REPO/contents/$PFAD" -q .sha 2>/dev/null)
  if [ -n "$SHA" ]; then ARG=(-f "sha=$SHA"); else ARG=(); fi

  if gh api --method PUT "repos/$REPO/contents/$PFAD" \
      -f message="Baustellenfoto $ZIEL in den Eingang gelegt" \
      -f content="$(base64 -i "$F" | tr -d '\n')" \
      -f branch=master "${ARG[@]}" >/dev/null 2>&1; then
    echo "ok"
    mv "$F" "$ERLEDIGT/$ZIEL"
    N=$((N+1))
  else
    echo "FEHLGESCHLAGEN"
  fi
done

echo
echo "$N Foto(s) hochgeladen."
echo "Die Originale liegen jetzt in: $ERLEDIGT"
echo
echo "Weiter geht es automatisch: Beim nächsten Lauf werden die Fotos"
echo "aufbereitet (ausrichten, Kontrast, Schärfe) und in den Pool gelegt."
echo "Der Donnerstags-Post greift dann darauf zu."
echo
echo "Fenster kann geschlossen werden."
read -r

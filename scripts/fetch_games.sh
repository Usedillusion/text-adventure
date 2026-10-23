#!/bin/sh
# Download freely redistributable Z-machine games into $GAMES_DIR (default ./games).
# Zork I-III: released by Microsoft under the MIT licence (github.com/historicalsource, Nov 2025).
# Advent.z5: Graham Nelson's Inform port of Crowther & Woods' Adventure, freeware on the IF Archive.
set -eu
DEST="${1:-${GAMES_DIR:-./games}}"
mkdir -p "$DEST"
get() { [ -s "$DEST/$2" ] && { echo "have $2"; return; }; echo "fetch $2"; curl -fsSL "$1" -o "$DEST/$2"; }
get https://raw.githubusercontent.com/historicalsource/zork1/master/COMPILED/zork1.z3 zork1.z3
get https://raw.githubusercontent.com/historicalsource/zork2/master/COMPILED/zork2.z3 zork2.z3
get https://raw.githubusercontent.com/historicalsource/zork3/master/COMPILED/zork3.z3 zork3.z3
get https://www.ifarchive.org/if-archive/games/zcode/Advent.z5 advent.z5
echo "Games in $DEST:"; ls -l "$DEST"

#!/usr/bin/env bash
# Rebuild the enclosure and drop the outputs into Google Drive.
#
# Usage (from anywhere):  meche/cad/push_gdrive.sh [--no-build]
#
# Copies into  My Drive/radio-project/print-files/<MM-DD>-<commit>/  through
# Google Drive for desktop, which uploads in the background. Override the
# parent folder with DRIVE_DIR=/some/path.
set -euo pipefail

BUILD=1
for arg in "$@"; do
    case "$arg" in
        --no-build) BUILD=0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/.."                         # meche/

if [[ -z "${DRIVE_DIR:-}" ]]; then
    MOUNT=$(ls -d "$HOME"/Library/CloudStorage/GoogleDrive-* 2>/dev/null | head -1)
    [[ -n "$MOUNT" ]] || { echo "Google Drive for desktop not found (is it running and signed in?)" >&2; exit 1; }
    DRIVE_DIR="$MOUNT/My Drive/radio-project/print-files"
fi
mkdir -p "$DRIVE_DIR"

# name the folder after date + commit; flag it if the design has uncommitted edits
SHA=$(git rev-parse --short HEAD)
DIRTY=""
if ! git diff --quiet HEAD -- cad ../radio-project/radio-project.step; then
    DIRTY=" (plus uncommitted changes)"
    SHA="$SHA-dirty"
    echo "warning: uncommitted changes in cad/ or the board STEP; uploading as $SHA" >&2
fi
DEST="$DRIVE_DIR/$(date +%m-%d)-$SHA"

if (( BUILD )); then
    echo "building parts..."
    .venv/bin/python cad/enclosure.py out ../radio-project/radio-project.step 2>/dev/null
    echo "building FreeCAD file (a FreeCAD window will flash)..."
    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD "$PWD/cad/to_fcstd.py" >/dev/null 2>&1
fi

mkdir -p "$DEST/print"
cp out/print/* "$DEST/print/"
cp out/tayloe_sdr_enclosure_assembly.step "$DEST/"
[[ -f out/enclosure.FCStd ]] && cp out/enclosure.FCStd "$DEST/"
{
    echo "commit: $(git rev-parse HEAD)$DIRTY"
    echo "branch: $(git branch --show-current)"
    echo "built:  $(date '+%Y-%m-%d %H:%M %Z')"
    echo "subject: $(git log -1 --format=%s)"
    echo
    echo "print/ holds bed-oriented parts; see meche/README.md for print settings."
} > "$DEST/VERSION.txt"

echo "copied to: $DEST"
echo "Google Drive for desktop uploads it in the background."

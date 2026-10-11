#!/usr/bin/env bash
# Rebuild the enclosure and upload the outputs to Google Drive.
#
# Usage (from anywhere):  meche/cad/push_gdrive.sh [--no-build] [--dry-run]
#
# Files land in a subfolder named after the commit, e.g. enclosure-92a886c,
# inside the shared Drive folder below, so every upload is traceable to the
# exact design that produced it.
#
# One-time setup:
#   brew install rclone
#   rclone config create gdrive drive scope=drive     # opens a browser to sign in
set -euo pipefail

FOLDER_ID="13Hm9unFtqh6zarxSVeAzXLbvdvOx-9Om"   # Drive folder from the share URL
REMOTE="${GDRIVE_REMOTE:-gdrive}"

BUILD=1
DRY=()
for arg in "$@"; do
    case "$arg" in
        --no-build) BUILD=0 ;;
        --dry-run)  DRY=(--dry-run) ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/.."                         # meche/

command -v rclone >/dev/null || { echo "rclone not found: brew install rclone" >&2; exit 1; }
rclone listremotes | grep -qx "$REMOTE:" || {
    echo "no rclone remote '$REMOTE:'. Run: rclone config create $REMOTE drive scope=drive" >&2
    exit 1
}

# name the upload after the commit; flag it if the design has uncommitted edits
SHA=$(git rev-parse --short HEAD)
DIRTY=""
if ! git diff --quiet HEAD -- cad ../radio-project/radio-project.step; then
    DIRTY=" (plus uncommitted changes)"
    SHA="$SHA-dirty"
    echo "warning: uncommitted changes in cad/ or the board STEP; uploading as $SHA" >&2
fi
DEST="enclosure-$SHA"

if (( BUILD )); then
    echo "building parts..."
    .venv/bin/python cad/enclosure.py out ../radio-project/radio-project.step 2>/dev/null
    echo "building FreeCAD file (a FreeCAD window will flash)..."
    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD "$PWD/cad/to_fcstd.py" >/dev/null 2>&1
fi

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir "$STAGE/print"
cp out/print/* "$STAGE/print/"
cp out/tayloe_sdr_enclosure_assembly.step "$STAGE/"
[[ -f out/enclosure.FCStd ]] && cp out/enclosure.FCStd "$STAGE/"
{
    echo "commit: $(git rev-parse HEAD)$DIRTY"
    echo "branch: $(git branch --show-current)"
    echo "built:  $(date '+%Y-%m-%d %H:%M %Z')"
    echo "subject: $(git log -1 --format=%s)"
    echo
    echo "print/ holds bed-oriented parts; see meche/README.md for print settings."
} > "$STAGE/VERSION.txt"

echo "uploading to Drive folder $FOLDER_ID/$DEST ..."
rclone copy "$STAGE" "$REMOTE:$DEST" --drive-root-folder-id "$FOLDER_ID" ${DRY[@]+"${DRY[@]}"} --progress
echo "done: https://drive.google.com/drive/folders/$FOLDER_ID"

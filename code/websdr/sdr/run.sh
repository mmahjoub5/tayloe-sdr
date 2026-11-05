#!/bin/sh
# Start the board bridge, the engine and the web server together; ctrl-c stops all three.
#
#   conda activate gr
#   ./run.sh [--key memagic]          # then open http://127.0.0.1:8090/#key=memagic
#
# Extra arguments go to server.py. The engine is regenerated from engine.grc on every start.

set -e
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD="$HERE/build"                    # grcc output; gitignored
mkdir -p "$BUILD"

grcc -o "$BUILD" "$HERE/engine.grc" >/dev/null

trap 'kill 0' INT TERM EXIT
python "$HERE/../../gnu-radio/iq_bridge.py" --no-tune &
sleep 2                                # let the bridge bind :5555/:5556 before the engine connects
python "$BUILD/engine.py" &
python "$HERE/server.py" "$@" &
wait

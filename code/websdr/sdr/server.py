"""Serve the WebSDR page and relay the GNU Radio engine to browsers over one WebSocket (see PROTOCOL.md)."""

import argparse
import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from xmlrpc.client import ServerProxy

import uvicorn
import zmq
import zmq.asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from diag import INTERVAL_S, Diagnostics

STATIC = Path(__file__).parent / "static"
LISTEN = "127.0.0.1:8090"
ENGINE = "http://127.0.0.1:8080"            # the flowgraph's XML-RPC Server block

# ZMQ PUB sinks in the flowgraph, and the type byte each stream gets in front.
STREAMS = {
    1: "tcp://127.0.0.1:5560",              # waterfall row, uint8[1024]
    2: "tcp://127.0.0.1:5561",              # audio, int16 LE, 12 kHz mono
}

# Flowgraph variables a browser may set; each is set_<name>/get_<name> on the engine.
CONTROLS = ("center", "mode", "offset", "volume")

QUEUE_FRAMES = 64                           # per listener; a slow one drops frames, not the others


class Hub:
    """The connected listeners and the engine they share."""

    def __init__(self, engine, key: str | None):
        """
        Start with nobody connected.

        Args:
            engine (object): has set_<name>/get_<name> for every name in CONTROLS, e.g. a ServerProxy
            key (str | None): needed to set controls; None lets anyone set them
        """
        self.engine = engine
        self.key = key
        self.queues: set[asyncio.Queue] = set()
        self.bytes = {kind: 0 for kind in STREAMS}      # received per stream, for the diagnostics page
        self.dropped = 0                                # frames dropped for slow listeners
        self.lock = asyncio.Lock()          # ServerProxy isn't thread-safe; one call at a time

    def broadcast(self, frame: bytes | str):
        """
        Queue a frame for every listener, dropping it for any whose queue is full.

        Args:
            frame (bytes | str): binary stream frame or JSON text
        """
        for q in self.queues:
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                self.dropped += 1

    async def call(self, method: str, *args):
        """
        Call the engine without blocking the event loop.

        Args:
            method (str): e.g. "get_mode", "set_offset"
            *args: the method's arguments

        Returns:
            object: what the engine returned
        """
        async with self.lock:
            return await asyncio.to_thread(getattr(self.engine, method), *args)

    async def state(self) -> str:
        """
        Read every control from the engine.

        Returns:
            str: JSON {"state": {...}}, or {"error": ...} if the engine isn't reachable
        """
        try:
            values = {name: await self.call(f"get_{name}") for name in CONTROLS}
        except Exception as e:
            return json.dumps({"error": f"engine not reachable: {e}"})
        return json.dumps({"state": values})

    async def handle(self, text: str) -> str | None:
        """
        Apply one browser command, {"set": name, "value": v, "key": k} or {"set": {name: v, ...}, "key": k}.

        Args:
            text (str): the WebSocket text frame

        Returns:
            str | None: a JSON error for this listener only, or None after a successful set
        """
        try:
            msg = json.loads(text)
            sets = msg["set"] if isinstance(msg["set"], dict) else {msg["set"]: msg["value"]}
        except (ValueError, KeyError, TypeError):
            return json.dumps({"error": "expected {\"set\": name, \"value\": v, \"key\": k}"})
        bad = [name for name in sets if name not in CONTROLS]
        if bad:
            return json.dumps({"error": f"{bad[0]!r} can't be set; one of {', '.join(CONTROLS)}"})
        if self.key is not None and msg.get("key") != self.key:
            return json.dumps({"error": "wrong or missing key; listen-only"})
        for name, value in sets.items():
            try:
                await self.call(f"set_{name}", value)
            except Exception as e:
                return json.dumps({"error": f"engine refused set_{name}: {e}"})
        self.broadcast(await self.state())
        return None


async def relay(hub: Hub, ctx: zmq.asyncio.Context, kind: int, endpoint: str):
    """
    Forward one ZMQ stream to every listener, with its type byte in front.

    Args:
        hub (Hub): the listeners
        ctx (zmq.asyncio.Context): shared ZMQ context
        kind (int): the type byte, a key of STREAMS
        endpoint (str): the flowgraph's PUB address
    """
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt(zmq.SUBSCRIBE, b"")
    sock.connect(endpoint)
    head = bytes([kind])
    try:
        while True:
            data = await sock.recv()
            hub.bytes[kind] = hub.bytes.get(kind, 0) + len(data)
            if hub.queues:
                hub.broadcast(head + data)
    finally:
        sock.close(linger=0)


async def sample(hub: Hub, diag: Diagnostics):
    """
    Add a diagnostics sample every INTERVAL_S, with the server's own stream rates and engine state.

    Args:
        hub (Hub): the listeners and engine
        diag (Diagnostics): where samples go
    """
    last, t0, dropped0 = dict(hub.bytes), asyncio.get_running_loop().time(), hub.dropped
    was_ok = None
    while True:
        await asyncio.sleep(INTERVAL_S)
        now = asyncio.get_running_loop().time()
        dt, t0 = now - t0, now
        rates = {k: (hub.bytes.get(k, 0) - last.get(k, 0)) / dt for k in hub.bytes}
        last = dict(hub.bytes)
        try:
            await hub.call("get_mode")
            engine_ok = True
        except Exception:
            engine_ok = False
        if engine_ok and was_ok is False:
            hub.broadcast(await hub.state())        # pages connected while it was down have no state yet
        was_ok = engine_ok
        app = {"listeners": len(hub.queues), "engine_ok": engine_ok,
               "waterfall_rows_s": round(rates.get(1, 0) / 1024, 1),
               "audio_sps": round(rates.get(2, 0) / 2),
               "dropped": hub.dropped - dropped0}
        dropped0 = hub.dropped
        await asyncio.to_thread(diag.sample, app)


def create_app(engine, key: str | None = None, streams: dict[int, str] = STREAMS) -> FastAPI:
    """
    Build the app around an engine.

    Args:
        engine (object): has set_<name>/get_<name> for every name in CONTROLS
        key (str | None): needed to set controls; None lets anyone set them
        streams (dict[int, str]): type byte -> ZMQ PUB address

    Returns:
        FastAPI: the app, serving /, /ws and /api/diag
    """
    hub = Hub(engine, key)
    diag = Diagnostics()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx = zmq.asyncio.Context()
        tasks = [asyncio.create_task(relay(hub, ctx, kind, ep)) for kind, ep in streams.items()]
        tasks.append(asyncio.create_task(sample(hub, diag)))
        yield
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        ctx.term()

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def revalidate(request, call_next):
        # Browsers otherwise keep running an old app.js after a deploy; unchanged files still come back as 304.
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response
    app.state.hub = hub

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        q = asyncio.Queue(QUEUE_FRAMES)
        await q.put(await hub.state())
        hub.queues.add(q)

        async def send():
            while True:
                frame = await q.get()
                if isinstance(frame, bytes):
                    await sock.send_bytes(frame)
                else:
                    await sock.send_text(frame)

        sender = asyncio.create_task(send())
        try:
            while True:
                reply = await hub.handle(await sock.receive_text())
                if reply:
                    await sock.send_text(reply)
        except WebSocketDisconnect:
            pass
        finally:
            hub.queues.discard(q)
            sender.cancel()

    @app.get("/api/diag")
    async def diagnostics(since: float = 0):
        return {"interval_s": INTERVAL_S, "samples": diag.since(since)}

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


def main():
    """Parse options and serve until interrupted."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--listen", default=LISTEN, help="host:port to serve on")
    ap.add_argument("--engine", default=ENGINE, help="the flowgraph's XML-RPC address")
    ap.add_argument("--key", default=os.environ.get("SDR_KEY"),
                    help="needed to tune (default $SDR_KEY); without one anyone can tune")
    args = ap.parse_args()
    if args.key is None:
        print("no --key: anyone who can open the page can tune")
    host, port = args.listen.rsplit(":", 1)
    uvicorn.run(create_app(ServerProxy(args.engine, allow_none=True), args.key),
                host=host, port=int(port), log_level="warning")


if __name__ == "__main__":
    sys.exit(main())

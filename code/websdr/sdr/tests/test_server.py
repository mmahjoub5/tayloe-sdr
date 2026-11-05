"""Tests for server.py against a fake engine and fake ZMQ publishers."""

import json
import sys
import threading
import time
from pathlib import Path

import pytest
import zmq
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


class FakeEngine:
    """Stands in for the flowgraph's XML-RPC server."""

    def __init__(self):
        """Start with the flowgraph's defaults."""
        self.values = {"center": 7069000, "mode": 1, "offset": 5000, "volume": -6}

    def __getattr__(self, method: str):
        """
        Answer get_<name> and set_<name> like GRC's generated top block.

        Args:
            method (str): e.g. "get_mode"

        Returns:
            callable: the getter or setter
        """
        verb, _, name = method.partition("_")
        if name not in self.values:
            raise AttributeError(method)
        if verb == "get":
            return lambda: self.values[name]
        return lambda v: self.values.__setitem__(name, v)


@pytest.fixture
def pub():
    """A ZMQ PUB socket on a free port, standing in for one flowgraph sink."""
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUB)
    port = sock.bind_to_random_port("tcp://127.0.0.1")
    yield sock, f"tcp://127.0.0.1:{port}"
    sock.close(linger=0)
    ctx.term()


def connect(engine, key=None, streams=None):
    """
    Start the app and open one WebSocket.

    Args:
        engine (FakeEngine): the engine
        key (str | None): the server's key
        streams (dict[int, str] | None): type byte -> PUB address

    Returns:
        TestClient: the running client, to use as a context manager
    """
    return TestClient(server.create_app(engine, key, streams or {}))


def test_state_on_connect():
    with connect(FakeEngine()) as client, client.websocket_connect("/ws") as ws:
        assert json.loads(ws.receive_text()) == {
            "state": {"center": 7069000, "mode": 1, "offset": 5000, "volume": -6}}


def test_set_updates_engine_and_broadcasts():
    engine = FakeEngine()
    with connect(engine) as client, client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        a.receive_text(), b.receive_text()
        a.send_text(json.dumps({"set": "mode", "value": 2}))
        assert json.loads(a.receive_text())["state"]["mode"] == 2
        assert json.loads(b.receive_text())["state"]["mode"] == 2
        assert engine.values["mode"] == 2


def test_key_required():
    engine = FakeEngine()
    with connect(engine, key="memagic") as client, client.websocket_connect("/ws") as ws:
        ws.receive_text()
        ws.send_text(json.dumps({"set": "mode", "value": 0, "key": "nope"}))
        assert "error" in json.loads(ws.receive_text())
        assert engine.values["mode"] == 1
        ws.send_text(json.dumps({"set": "mode", "value": 0, "key": "memagic"}))
        assert json.loads(ws.receive_text())["state"]["mode"] == 0


def test_unknown_control_refused():
    with connect(FakeEngine()) as client, client.websocket_connect("/ws") as ws:
        ws.receive_text()
        ws.send_text(json.dumps({"set": "samp_rate", "value": 1}))
        assert "can't be set" in json.loads(ws.receive_text())["error"]


def test_engine_down_reported():
    class Down:
        def __getattr__(self, method):
            def fail(*args):
                raise ConnectionRefusedError("refused")
            return fail

    with connect(Down()) as client, client.websocket_connect("/ws") as ws:
        assert "engine not reachable" in json.loads(ws.receive_text())["error"]


def test_stream_relayed_with_type_byte(pub):
    sock, endpoint = pub
    frame = b"\x01\x02" * 240
    stop = threading.Event()

    def publish():
        # PUB drops messages until the SUB has joined, so keep sending.
        while not stop.is_set():
            sock.send(frame)
            time.sleep(0.02)

    with connect(FakeEngine(), streams={2: endpoint}) as client, client.websocket_connect("/ws") as ws:
        ws.receive_text()
        t = threading.Thread(target=publish, daemon=True)
        t.start()
        try:
            assert ws.receive_bytes() == b"\x02" + frame
        finally:
            stop.set()
            t.join()


def test_page_served():
    with connect(FakeEngine()) as client:
        r = client.get("/")
        assert r.status_code == 200 and "WebSDR" in r.text


def test_diag_samples(monkeypatch):
    monkeypatch.setattr(server, "INTERVAL_S", 0.05)
    with connect(FakeEngine()) as client:
        time.sleep(0.3)
        samples = client.get("/api/diag").json()["samples"]
        assert samples and samples[-1]["engine_ok"] is True
        assert {"cpu", "mem_pct", "temp_c", "procs", "audio_sps", "listeners"} <= samples[-1].keys()
        assert client.get(f"/api/diag?since={samples[-1]['t']}").json()["samples"] == []


def test_multi_set_is_one_broadcast():
    engine = FakeEngine()
    with connect(engine) as client, client.websocket_connect("/ws") as ws:
        ws.receive_text()
        ws.send_text(json.dumps({"set": {"center": 1167000, "offset": 3000, "mode": 0}}))
        state = json.loads(ws.receive_text())["state"]
        assert (state["center"], state["offset"], state["mode"]) == (1167000, 3000, 0)


def test_multi_set_refuses_unknown_before_setting_any():
    engine = FakeEngine()
    with connect(engine) as client, client.websocket_connect("/ws") as ws:
        ws.receive_text()
        ws.send_text(json.dumps({"set": {"mode": 0, "samp_rate": 1}}))
        assert "can't be set" in json.loads(ws.receive_text())["error"]
        assert engine.values["mode"] == 1

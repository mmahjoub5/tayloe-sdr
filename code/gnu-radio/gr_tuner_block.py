"""
Embedded Python Blocks:

Each time this file is saved, GRC will instantiate the first class it finds
to get ports and parameters of your block. The arguments to __init__  will
be the parameters. All of them are required to have default values!
"""

import time

import numpy as np
import zmq
from gnuradio import gr

# Must match CONTROL in iq_bridge.py. Kept as a constant rather than a GRC
# parameter: an empty field there generates `endpoint=` and fails to compile,
# and a wrong one fails silently, since ZMQ PUB discards messages nobody is
# subscribed to.
CONTROL = 'tcp://127.0.0.1:5556'


class blk(gr.sync_block):
    """Tune the radio board from GRC.

    Samples pass through untouched; the block exists for its `freq` and
    `offset` parameters, which are forwarded to iq_bridge.py over ZMQ. Wire a
    QT GUI Range widget to a variable and set freq to that variable -- GRC
    calls the setter whenever the slider moves.

    Frequencies are the station, not the LO: the bridge applies the Tayloe
    divide-by-four itself, so 1170e3 means 1170 kHz.

    `offset` is where the bridge parks the station above DC. Set it from the
    same variable as the Frequency Xlating filter's centre, so the two cannot
    disagree.
    """

    def __init__(self, freq=1.17e6, offset=3000.0):
        """arguments to this function show up as parameters in GRC"""
        gr.sync_block.__init__(
            self,
            name='Board Tuner',             # will show up in GRC
            in_sig=[np.complex64],
            out_sig=[np.complex64]
        )
        self._ctx = zmq.Context()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.connect(CONTROL)

        # PUB silently discards anything sent before the subscriber has
        # connected, so the first request needs this pause to arrive.
        time.sleep(0.3)

        # Send the starting point once. The bridge drops a request for where
        # it already is, so this costs nothing when the two agree -- and when
        # they do not (say the flowgraph wants a different offset than the
        # bridge was started with), it is the only thing that fixes it.
        self._freq = float(freq)
        self._offset = float(offset)
        self._send()

    def _send(self):
        self._sock.send(f"{self._freq} {self._offset}".encode())

    # A property, so GRC registers a callback on the matching parameter name.
    @property
    def freq(self):
        return self._freq

    @freq.setter
    def freq(self, value):
        value = float(value)
        # Retuning costs a second of audio -- the bridge has to abort the
        # stream, send the command and restart -- so ignore no-op updates.
        if value != self._freq:
            self._freq = value
            self._send()

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, value):
        value = float(value)
        if value != self._offset:
            self._offset = value
            self._send()

    def work(self, input_items, output_items):
        output_items[0][:] = input_items[0]
        return len(output_items[0])

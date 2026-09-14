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

    Samples pass through untouched; the block exists for its `freq` parameter,
    which is forwarded to iq_bridge.py over ZMQ. Wire a QT GUI Range widget to
    a variable and set freq to that variable -- GRC calls the setter whenever
    the slider moves.

    Frequencies are the station, not the LO: the bridge applies the Tayloe
    divide-by-four and the tuning offset itself, so 1170e3 means 1170 kHz.
    """

    def __init__(self, freq=1.17e6):
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
        # connected, so a request sent immediately would vanish anyway.
        time.sleep(0.3)

        # Adopt the starting frequency WITHOUT transmitting it. The flowgraph
        # is constructed on every run, and sending here would abort the
        # bridge's stream and cost a second of audio at each start -- right
        # when you are listening for it to begin. The bridge already has a
        # frequency; nudge the slider if the two disagree.
        self._freq = float(freq)

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
            self._sock.send(str(value).encode())

    def work(self, input_items, output_items):
        output_items[0][:] = input_items[0]
        return len(output_items[0])

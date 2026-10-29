/*
 * center_freq: OpenWebRX+ receiver plugin.
 *
 * Adds a "Center MHz" box to the receiver panel that retunes the SDR center
 * frequency by sending the same "setfrequency" message as jumpBySteps() in
 * openwebrx.js. Shown only while the server reports
 * allow_center_freq_changes === true.
 */

// Accepted input range in MHz (R820T-based RTL-SDR tuning range).
var CENTER_FREQ_MIN_MHZ = 24;
var CENTER_FREQ_MAX_MHZ = 1766;

// How long to wait for the server to confirm a retune before reporting it was ignored.
var CENTER_FREQ_CONFIRM_MS = 3000;

Plugins.center_freq._version = 1.0;

Plugins.center_freq.init = function () {
    try {
        return Plugins.center_freq._setup();
    } catch (e) {
        console.error('center_freq plugin: setup failed, receiver page is unaffected.', e);
        // Returning true keeps the loader from logging a second, misleading error.
        return true;
    }
};

Plugins.center_freq._setup = function () {
    var self = Plugins.center_freq;
    var anchor = document.getElementById('openwebrx-sdr-profiles-listbox');
    if (!anchor || !anchor.parentElement) {
        console.warn('center_freq plugin: profile listbox not found, not installing.');
        return true;
    }

    var line = document.createElement('div');
    line.className = 'openwebrx-panel-line openwebrx-center-freq';
    line.style.display = 'none';
    line.innerHTML =
        '<form class="openwebrx-center-freq-form" novalidate>' +
            '<label for="openwebrx-center-freq-input">Center MHz</label>' +
            '<input id="openwebrx-center-freq-input" type="text" inputmode="decimal"' +
            ' autocomplete="off" spellcheck="false" title="SDR center frequency in MHz">' +
            '<button type="submit" class="openwebrx-button">Go</button>' +
        '</form>' +
        '<div class="openwebrx-center-freq-status" aria-live="polite"></div>';
    anchor.parentElement.insertAdjacentElement('afterend', line);

    self.line = line;
    self.input = line.querySelector('input');
    self.status = line.querySelector('.openwebrx-center-freq-status');
    self.allowed = null;
    self.pendingHz = null;
    self.pendingTimer = null;

    line.querySelector('form').addEventListener('submit', function (e) {
        e.preventDefault();
        try {
            self._submit();
        } catch (err) {
            console.error('center_freq plugin: submit failed.', err);
            self._setStatus('Could not send retune.', true);
        }
    });
    self.input.addEventListener('input', function () {
        self._setStatus('', false);
    });
    self.input.addEventListener('blur', function () {
        self._refreshValue();
    });

    self._hookMessages();
    return true;
};

// Observe server messages without altering them. Future sockets pick up the
// wrapped on_ws_recv; a socket that is already open gets a listener instead.
Plugins.center_freq._hookMessages = function () {
    var self = Plugins.center_freq;
    var onMessage = function (evt) {
        try {
            self._onMessage(evt);
        } catch (e) {
            console.error('center_freq plugin: message handling failed.', e);
        }
    };

    if (typeof window.on_ws_recv === 'function') {
        var original = window.on_ws_recv;
        window.on_ws_recv = function (evt) {
            var result = original.apply(this, arguments);
            onMessage(evt);
            return result;
        };
    }

    if (typeof ws !== 'undefined' && ws && typeof ws.addEventListener === 'function') {
        // Page connected before this plugin loaded; the initial config was missed,
        // so the box stays hidden until the server sends allow_center_freq_changes again.
        console.warn('center_freq plugin: loaded after the WebSocket opened.');
        ws.addEventListener('message', onMessage);
    }
};

Plugins.center_freq._onMessage = function (evt) {
    if (typeof evt.data !== 'string' || evt.data.charAt(0) !== '{') return;
    var json = JSON.parse(evt.data);
    if (json.type !== 'config' || !json.value) return;

    var config = json.value;
    if ('allow_center_freq_changes' in config) {
        this.allowed = config.allow_center_freq_changes === true;
        this.line.style.display = this.allowed ? '' : 'none';
    }
    if ('center_freq' in config) {
        this._onCenterChanged(config.center_freq);
    }
};

Plugins.center_freq._onCenterChanged = function (hz) {
    if (this.pendingHz !== null && hz === this.pendingHz) {
        this._clearPending();
        this._setStatus('', false);
    }
    this._refreshValue();
};

// Show the current center unless the user is typing in the box.
Plugins.center_freq._refreshValue = function () {
    if (document.activeElement === this.input) return;
    if (typeof center_freq !== 'number' || !isFinite(center_freq)) return;
    this.input.value = Plugins.center_freq._formatMHz(center_freq);
};

Plugins.center_freq._formatMHz = function (hz) {
    // Up to 6 decimals (1 Hz), trailing zeros trimmed.
    return (hz / 1e6).toFixed(6).replace(/\.?0+$/, '');
};

Plugins.center_freq._submit = function () {
    var text = this.input.value.trim();
    var mhz = Number(text);

    if (text === '' || !isFinite(mhz)) {
        this._setStatus('Enter a frequency in MHz.', true);
        return;
    }
    if (mhz <= 0 || mhz < CENTER_FREQ_MIN_MHZ || mhz > CENTER_FREQ_MAX_MHZ) {
        this._setStatus('Must be ' + CENTER_FREQ_MIN_MHZ + '-' + CENTER_FREQ_MAX_MHZ + ' MHz.', true);
        return;
    }
    if (typeof ws === 'undefined' || !ws || ws.readyState !== WebSocket.OPEN) {
        this._setStatus('Not connected to the receiver.', true);
        return;
    }

    var hz = Math.round(mhz * 1e6);
    var key = UI.getDemodulatorPanel().getMagicKey();
    ws.send(JSON.stringify({
        "type": "setfrequency", "params": { "frequency": hz, "key": key }
    }));
    if (typeof UI.toggleScanner === 'function') UI.toggleScanner(false);

    this.input.blur();
    this._clearPending();
    if (hz === center_freq) {
        this._setStatus('', false);
        return;
    }

    // The server ignores refused retunes silently, so watch for the new center.
    var self = this;
    this.pendingHz = hz;
    this._setStatus('Tuning…', false);
    this.pendingTimer = setTimeout(function () {
        self.pendingHz = null;
        self.pendingTimer = null;
        self._setStatus('Not retuned: the server refused it (magic key?).', true);
        self._refreshValue();
    }, CENTER_FREQ_CONFIRM_MS);
};

Plugins.center_freq._clearPending = function () {
    if (this.pendingTimer) clearTimeout(this.pendingTimer);
    this.pendingTimer = null;
    this.pendingHz = null;
};

Plugins.center_freq._setStatus = function (text, isError) {
    this.status.textContent = text;
    this.status.classList.toggle('error', !!isError);
};

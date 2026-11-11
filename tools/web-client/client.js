import RFB from '/novnc/core/rfb.js';

const el = id => document.getElementById(id);
let rfb = null;
let stopping = false;
let reconnectTimer = null;
let retry = 0;
let closed = false;
let generation = 0;
let statusTimer = null;
let pollTimer = null;
let csrf = null;
let controllerAvailable = false;
let cursor = null;
const pending = new Set();
const buttons = new Map();
const actions = {
    menu: ['MENU', 'Menu'], media: ['MEDIA', 'Media / radio'],
    telephone: ['PHONE', 'Phone'], navigation: ['NAV', 'Navigation'],
    counterclockwise: ['⟲', 'Rotate counterclockwise'],
    clockwise: ['⟳', 'Rotate clockwise'],
    up: ['↑', 'Up'], left: ['←', 'Left'], ok: ['OK', 'Confirm'],
    right: ['→', 'Right'], down: ['↓', 'Down'],
    back: ['BACK', 'Back'], voice: ['', 'Voice control'], options: ['OPTION', 'Options'],
};
const rotary = document.createElement('div');
rotary.className = 'rotary';
rotary.setAttribute('role', 'group');
rotary.setAttribute('aria-label', 'Rotary controller');
const rotaryKeys = new Set(['counterclockwise', 'clockwise', 'up', 'left', 'ok', 'right', 'down']);

function updateButtons() {
    for (const [key, button] of buttons) button.disabled = !csrf || !controllerAvailable || pending.has(key);
}
for (const [key, [label, accessibleLabel]] of Object.entries(actions)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `key-${key}`;
    button.dataset.key = key;
    button.textContent = label;
    button.setAttribute('aria-label', accessibleLabel);
    button.title = accessibleLabel;
    button.disabled = true;
    if (key === 'voice') {
        // A static icon only; all actual input is sent by the single click handler.
        button.innerHTML = '<svg viewBox="0 0 20 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="6" y="2" width="8" height="12" rx="4"/><path d="M3 10v2a7 7 0 0 0 14 0v-2M10 19v4M6 23h8"/></svg>';
    }
    button.addEventListener('click', async () => {
        if (!csrf || !controllerAvailable || pending.has(key)) return;
        const epoch = generation;
        pending.add(key);
        updateButtons();
        el('control-status').textContent = '';
        try {
            const response = await fetch('/api/control', {method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
                body: JSON.stringify({key}), signal: AbortSignal.timeout(3000)});
            if (generation === epoch && !response.ok) el('control-status').textContent = 'Command unavailable';
        } catch {
            if (generation === epoch) el('control-status').textContent = 'Could not send command';
        } finally {
            if (generation === epoch) { pending.delete(key); updateButtons(); }
        }
    });
    buttons.set(key, button);
    (rotaryKeys.has(key) ? rotary : el('controls')).append(button);
}
el('controls').append(rotary);

function showState(text) {
    el('vnc-status').textContent = text;
    el('display-state').textContent = text;
    el('display-state').hidden = !text;
    el('pointer').hidden = true;
}
function clearReconnect() {
    if (reconnectTimer !== null) clearTimeout(reconnectTimer);
    reconnectTimer = null;
}
function scheduleConnect(delay = 0) {
    if (closed || rfb || reconnectTimer !== null) return;
    reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, delay);
}
function stopConnection() {
    clearReconnect();
    if (rfb && !stopping) {
        stopping = true;
        rfb.disconnect();
    }
}
function connect() {
    if (closed || rfb) return;
    showState('Connecting…');
    let current;
    try {
        current = new RFB(el('screen'), `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/websockify`);
    } catch {
        showState('Display unavailable');
        scheduleConnect(Math.min(1000 * 2 ** Math.min(retry++, 4), 15000));
        return;
    }
    rfb = current;
    stopping = false;
    current.scaleViewport = true;
    current.resizeSession = false;
    current.viewOnly = false;
    current.addEventListener('connect', () => {
        if (rfb !== current || stopping) return;
        retry = 0;
        el('vnc-status').textContent = 'Connected';
        el('display-state').hidden = true;
    });
    current.addEventListener('disconnect', () => {
        if (rfb !== current) return;
        const intentional = stopping;
        rfb = null;
        stopping = false;
        if (closed) return;
        showState(intentional ? 'Connecting…' : 'Reconnecting…');
        scheduleConnect(intentional ? 0 : Math.min(1000 * 2 ** Math.min(retry++, 4), 15000));
    });
    current.addEventListener('credentialsrequired', () => {
        if (rfb !== current) return;
        showState('Display access required');
        current.disconnect();
    });
    current.addEventListener('securityfailure', () => {
        if (rfb === current) showState('Display unavailable');
    });
}
// Observe only: no preventDefault, synthetic input or interference with noVNC.
function trackPointer(event) {
    if (!el('display-state').hidden) return;
    const rect = el('viewport').getBoundingClientRect();
    const inside = event.clientX >= rect.left && event.clientX < rect.right &&
        event.clientY >= rect.top && event.clientY < rect.bottom;
    el('pointer').hidden = !inside;
    if (!inside) return;
    el('pointer').style.left = `${event.clientX - rect.left}px`;
    el('pointer').style.top = `${event.clientY - rect.top}px`;
}
// noVNC temporarily captures mouse input on an overlay outside the viewport.
// Observe at the window boundary so that capture does not hide or strand the ring.
for (const name of ['pointermove', 'pointerdown', 'pointerup']) {
    window.addEventListener(name, trackPointer, {passive: true, capture: true});
}
window.addEventListener('pointercancel', () => { el('pointer').hidden = true; }, {passive: true});
window.addEventListener('pointerout', event => {
    if (!event.relatedTarget) el('pointer').hidden = true;
}, {passive: true});

async function status(epoch = generation) {
    if (closed || generation !== epoch) return;
    try {
        const response = await fetch('/api/status', {signal: AbortSignal.timeout(3000)});
        if (!response.ok) throw Error();
        const data = await response.json();
        if (closed || generation !== epoch) return;
        csrf = data.csrf;
        controllerAvailable = Boolean(data.controller);
        el('control-status').textContent = controllerAvailable ? '' : 'Controls unavailable';
        updateButtons();
        scheduleConnect();
    } catch {
        if (closed || generation !== epoch) return;
        csrf = null;
        controllerAvailable = false;
        updateButtons();
        el('control-status').textContent = 'Server unavailable';
    }
    if (!closed && generation === epoch) statusTimer = setTimeout(() => status(epoch), 5000);
}
el('clear').onclick = () => { el('log').textContent = ''; };
async function poll(epoch = generation) {
    if (closed || generation !== epoch) return;
    try {
        const response = await fetch('/api/log' + (cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`),
            {signal: AbortSignal.timeout(4000)});
        if (!response.ok) throw Error();
        const data = await response.json();
        if (closed || generation !== epoch) return;
        cursor = data.cursor;
        el('log-status').textContent = data.available ? 'Serial log' : 'Log unavailable';
        if (data.reset) el('log').textContent = '';
        // Serial output is untrusted. Bound the DOM/string even over long runs.
        el('log').textContent = (el('log').textContent + data.text.slice(-65536)).slice(-262144);
        el('log').scrollTop = el('log').scrollHeight;
    } catch {
        if (closed || generation !== epoch) return;
        el('log-status').textContent = 'Log unavailable';
    }
    if (!closed && generation === epoch) pollTimer = setTimeout(() => poll(epoch), 1000);
}
window.addEventListener('pagehide', () => {
    if (closed) return;
    closed = true;
    generation++;
    clearTimeout(statusTimer);
    clearTimeout(pollTimer);
    pending.clear();
    csrf = null;
    controllerAvailable = false;
    updateButtons();
    stopConnection();
});
window.addEventListener('pageshow', event => {
    // A persisted document keeps this module's state instead of reloading it.
    if (!event.persisted || !closed) return;
    closed = false;
    retry = 0;
    status();
    poll();
    scheduleConnect();
});
status();
poll();
scheduleConnect();

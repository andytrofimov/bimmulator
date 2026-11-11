// Pending VM-start preferences only; never calls the controller or guest APIs.
const open = document.getElementById('settings-open');
const dialog = document.getElementById('settings-dialog');

if (open && dialog) {
    const make = (tag, text, className) => {
        const node = document.createElement(tag);
        if (text) node.textContent = text;
        if (className) node.className = className;
        return node;
    };
    const heading = make('h2', 'VM settings');
    heading.id = 'settings-title';
    dialog.setAttribute('aria-labelledby', heading.id);
    dialog.classList.add('vm-settings');
    const close = make('button', 'Close');
    close.type = 'button';
    close.onclick = () => dialog.close();
    const header = make('header');
    header.append(heading, close);
    const intro = make('p', 'Changes apply only at the next VM launch. ConnectedDrive mocks are unavailable in this release. Boot values show configuration, not verified native functionality.');
    const tabs = make('div', '', 'settings-tabs');
    tabs.setAttribute('role', 'tablist');
    tabs.setAttribute('aria-label', 'Settings section');
    const content = make('div');
    const status = make('p', '');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    const save = make('button', 'Save for next launch');
    save.type = 'button';
    save.disabled = true;
    dialog.replaceChildren(header, intro, tabs, content, status, save);
    let csrf = null;
    let fields = new Map();
    let schema = {};
    let selected = 'coding';
    let busy = false;
    const request = async (url, options = {}) => {
        const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store',
            signal: AbortSignal.timeout(4000), ...options});
        const data = await response.json();
        if (!response.ok) throw Error('request failed');
        return data;
    };
    function dependencies() {
        for (const [key, input] of fields) {
            const requirement = schema[key].requires;
            if (requirement && !fields.get(requirement)?.checked) input.checked = false;
            input.disabled = busy || schema[key].available === false || Boolean(requirement && !fields.get(requirement)?.checked);
        }
    }
    function savedStatus(data) {
        if (!data.active_known || !data.boot_values) {
            return data.pending_saved ? 'Saved for next launch. Boot config unavailable.' :
                'Boot config unavailable. Save these settings for the next launch.';
        }
        if (data.restart_required) {
            return data.pending_saved ? 'Saved for next launch. Changes apply at the next VM launch.' :
                'Settings differ from the current boot configuration. Save for next launch.';
        }
        return data.pending_saved ? 'Saved. No pending changes.' : 'No pending changes.';
    }
    function render(data) {
        fields = new Map();
        schema = data.schema;
        tabs.replaceChildren();
        content.replaceChildren();
        const buttons = [];
        const panels = [];
        const select = id => {
            selected = id;
            for (const button of buttons) {
                const active = button.dataset.group === id;
                button.setAttribute('aria-selected', String(active));
                button.tabIndex = active ? 0 : -1;
            }
            for (const panel of panels) panel.hidden = panel.dataset.group !== id;
        };
        for (const group of data.groups) {
            const tab = make('button', group.label);
            tab.type = 'button';
            tab.dataset.group = group.id;
            tab.id = `settings-tab-${group.id}`;
            tab.setAttribute('role', 'tab');
            tab.setAttribute('aria-controls', `settings-panel-${group.id}`);
            tab.onclick = () => select(group.id);
            tab.onkeydown = event => {
                if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();
                const index = buttons.indexOf(tab);
                const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
                    (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
                buttons[next].click();
                buttons[next].focus();
            };
            buttons.push(tab);
            tabs.append(tab);
            const panel = make('section');
            panel.id = `settings-panel-${group.id}`;
            panel.dataset.group = group.id;
            panel.setAttribute('role', 'tabpanel');
            panel.setAttribute('aria-labelledby', tab.id);
            const submenu = make('details');
            submenu.open = true;
            submenu.append(make('summary', group.submenu));
            const table = make('table', '', 'settings-values');
            const tableHead = make('thead');
            const headings = make('tr');
            for (const title of ['Setting', 'Current boot configuration', 'Saved for next launch']) {
                const cell = make('th', title);
                cell.scope = 'col';
                headings.append(cell);
            }
            tableHead.append(headings);
            const rows = make('tbody');
            table.append(tableHead, rows);
            submenu.append(table);
            for (const [key, item] of Object.entries(schema)) {
                if (item.group !== group.id || item.type !== 'boolean') continue;
                const row = make('tr');
                const name = make('th', item.label);
                name.scope = 'row';
                const boot = make('td', data.active_known && data.boot_values ?
                    (data.boot_values[key] ? 'On' : 'Off') : 'Unavailable');
                const pending = make('td');
                const input = make('input');
                input.type = 'checkbox';
                input.setAttribute('aria-label', `${item.label}: saved for next launch`);
                input.checked = data.values[key] === true;
                input.onchange = () => {
                    dependencies();
                    status.textContent = 'You have unsaved changes.';
                };
                fields.set(key, input);
                pending.append(input);
                row.append(name, boot, pending);
                rows.append(row);
            }
            panel.append(submenu);
            panels.push(panel);
            content.append(panel);
        }
        select(data.groups.some(group => group.id === selected) ? selected : data.groups[0].id);
        dependencies();
        status.textContent = savedStatus(data);
    }
    open.addEventListener('click', async () => {
        if (dialog.open) return;
        dialog.showModal();
        busy = true;
        save.disabled = true;
        for (const input of fields.values()) input.disabled = true;
        status.textContent = 'Loading settings…';
        try {
            const [data, auth] = await Promise.all([request('/api/settings'), request('/api/status')]);
            if (typeof auth.csrf !== 'string' || !auth.csrf) throw Error();
            csrf = auth.csrf;
            busy = false;
            render(data);
            save.disabled = false;
        } catch {
            csrf = null;
            status.textContent = 'Could not load settings. Close this dialog and try again.';
        } finally { busy = false; }
    });
    save.onclick = async () => {
        if (!csrf || busy) return;
        busy = true;
        save.disabled = true;
        dependencies();
        status.textContent = 'Saving…';
        const values = Object.fromEntries([...fields].map(([key, input]) => [key, input.checked]));
        try {
            const data = await request('/api/settings', {method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
                body: JSON.stringify({values})});
            busy = false;
            render(data);
            status.textContent = savedStatus(data);
        } catch { status.textContent = 'Could not confirm the save. Please try again.'; }
        finally { busy = false; save.disabled = false; dependencies(); }
    };
}

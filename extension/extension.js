// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 brunos3d
// This program comes with ABSOLUTELY NO WARRANTY. See LICENSE and the
// hardware disclaimer in README.md.

import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Slider} from 'resource:///org/gnome/shell/ui/slider.js';
import {
    QuickMenuToggle,
    SystemIndicator,
} from 'resource:///org/gnome/shell/ui/quickSettings.js';

const BUS_NAME = 'org.bruno.GpuPowerMode';
const OBJ_PATH = '/org/bruno/GpuPowerMode';

const IFACE_XML = `
<node>
  <interface name="org.bruno.GpuPowerMode">
    <method name="SetWatts">
      <arg type="u" direction="in" name="watts"/>
      <arg type="u" direction="out" name="applied"/>
    </method>
    <method name="SetMode">
      <arg type="s" direction="in" name="mode"/>
      <arg type="u" direction="out" name="applied"/>
    </method>
    <method name="GetStatus">
      <arg type="a{sv}" direction="out" name="status"/>
    </method>
    <signal name="Changed">
      <arg type="a{sv}" name="status"/>
    </signal>
  </interface>
</node>`;

const MODES = [
    {label: 'Performance', mode: 'performance', icon: 'power-profile-performance-symbolic'},
    {label: 'Balanced', mode: 'balanced', icon: 'power-profile-balanced-symbolic'},
    {label: 'Power Saver', mode: 'saver', icon: 'power-profile-power-saver-symbolic'},
];

const BASE_ICON = 'power-profile-performance-symbolic';
const POLL_INTERVAL = 2; // seconds while the menu is open

function modeLabel(mode) {
    const m = MODES.find(x => x.mode === mode);
    return m ? m.label : 'custom';
}

function modeIcon(mode) {
    const m = MODES.find(x => x.mode === mode);
    return m ? m.icon : BASE_ICON;
}

function unpackStatus(dict) {
    const out = {};
    for (const key in dict)
        out[key] = dict[key].deepUnpack();
    return out;
}

const GpuPowerToggle = GObject.registerClass(
class GpuPowerToggle extends QuickMenuToggle {
    _init() {
        super._init({
            title: 'GPU Power',
            iconName: BASE_ICON,
            toggleMode: false,
        });

        this._proxy = null;
        this._available = false;
        this._status = null;
        this._pollId = 0;
        this._sendId = 0;
        this._suppressSend = false;

        this.menu.setHeader(BASE_ICON, 'GPU Power', 'NVIDIA');

        // Mode rows with an ornament marking the active one.
        this._modeItems = [];
        const section = new PopupMenu.PopupMenuSection();
        for (const m of MODES) {
            const item = new PopupMenu.PopupImageMenuItem(m.label, m.icon);
            item.connect('activate', () => this._callMode(m.mode));
            item._mode = m.mode;
            section.addMenuItem(item);
            this._modeItems.push(item);
        }
        this.menu.addMenuItem(section);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Watts slider (min .. rated performance).
        const sliderItem = new PopupMenu.PopupBaseMenuItem({activate: false});
        const sliderIcon = new St.Icon({
            iconName: BASE_ICON,
            styleClass: 'popup-menu-icon',
        });
        this._slider = new Slider(0);
        this._sliderLabel = new St.Label({
            text: '--',
            styleClass: 'gpupower-slider-label',
            yAlign: Clutter.ActorAlign.CENTER,
        });
        this._slider.connect('notify::value', () => this._onSliderValue());
        this._slider.connect('drag-end', () => this._sendSliderNow());
        sliderItem.add_child(sliderIcon);
        sliderItem.add_child(this._slider);
        sliderItem.add_child(this._sliderLabel);
        this.menu.addMenuItem(sliderItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Live status line (limit + draw).
        this._statusItem = new PopupMenu.PopupMenuItem('', {
            reactive: false,
            can_focus: false,
        });
        this._statusItem.label.styleClass = 'gpupower-status';
        this.menu.addMenuItem(this._statusItem);

        this.connect('clicked', () => this._onClicked());
        this.menu.connect('open-state-changed', (_m, open) => {
            if (open)
                this._startPolling();
            else
                this._stopPolling();
        });

        this._setupProxy();
    }

    _range() {
        const s = this._status;
        if (!s)
            return {min: 0, max: 1};
        return {min: s.min, max: s.performance};
    }

    _wattsToValue(watts) {
        const {min, max} = this._range();
        if (max <= min)
            return 0;
        return Math.max(0, Math.min(1, (watts - min) / (max - min)));
    }

    _valueToWatts(value) {
        const {min, max} = this._range();
        return Math.round(min + value * (max - min));
    }

    _setupProxy() {
        const Proxy = Gio.DBusProxy.makeProxyWrapper(IFACE_XML);
        try {
            this._proxy = Proxy(Gio.DBus.system, BUS_NAME, OBJ_PATH,
                (proxy, error) => {
                    if (error) {
                        this._setAvailable(false);
                        logError(error, 'gpu-power-mode: proxy init failed');
                        return;
                    }
                    this._proxy.connectSignal('Changed', (_p, _s, [dict]) => {
                        this._status = unpackStatus(dict);
                        this._render();
                    });
                    this._proxy.connect('notify::g-name-owner',
                        () => this._refreshAvailability());
                    this._refreshAvailability();
                });
        } catch (e) {
            this._setAvailable(false);
            logError(e, 'gpu-power-mode: could not create proxy');
        }
    }

    _refreshAvailability() {
        const owner = this._proxy && this._proxy.g_name_owner;
        this._setAvailable(!!owner);
        if (owner)
            this._refreshStatus();
    }

    _setAvailable(available) {
        this._available = available;
        this.reactive = available;
        if (!available) {
            this.subtitle = 'daemon unavailable';
            this.checked = false;
        }
        for (const item of this._modeItems)
            item.setSensitive(available);
        this._slider.reactive = available;
    }

    _refreshStatus() {
        if (!this._proxy)
            return;
        this._proxy.GetStatusRemote((result, error) => {
            if (error || !result) {
                this._setAvailable(false);
                return;
            }
            this._status = unpackStatus(result[0]);
            this._render();
        });
    }

    _render() {
        if (!this._status)
            return;
        const s = this._status;

        this.iconName = modeIcon(s.mode);
        this.checked = s.mode !== 'saver';
        this.subtitle = `${modeLabel(s.mode)} · ${s.watts}W`;

        for (const item of this._modeItems) {
            item.setOrnament(item._mode === s.mode
                ? PopupMenu.Ornament.CHECK
                : PopupMenu.Ornament.NONE);
        }

        if (!this._slider._dragging) {
            this._suppressSend = true;
            this._slider.value = this._wattsToValue(s.watts);
            this._suppressSend = false;
            this._sliderLabel.text = `${s.watts}W`;
        }

        const draw = s.draw >= 0 ? `${s.draw}W` : '--';
        this._statusItem.label.text = `limit ${s.watts}W   •   draw ${draw}`;
    }

    _onClicked() {
        if (!this._available)
            return;
        this._callMode(this.checked ? 'saver' : 'performance');
    }

    _onSliderValue() {
        if (this._suppressSend || !this._status)
            return;
        const watts = this._valueToWatts(this._slider.value);
        this._sliderLabel.text = `${watts}W`;
        if (this._sendId)
            GLib.source_remove(this._sendId);
        this._sendId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
            this._sendId = 0;
            this._sendSliderNow();
            return GLib.SOURCE_REMOVE;
        });
    }

    _sendSliderNow() {
        if (!this._available || !this._status)
            return;
        if (this._sendId) {
            GLib.source_remove(this._sendId);
            this._sendId = 0;
        }
        this._callWatts(this._valueToWatts(this._slider.value));
    }

    _callWatts(watts) {
        if (!this._proxy)
            return;
        this._proxy.SetWattsRemote(watts, (_r, error) => {
            if (error)
                logError(error, 'gpu-power-mode: SetWatts failed');
            else
                this._refreshStatus();
        });
    }

    _callMode(mode) {
        if (!this._proxy)
            return;
        this._proxy.SetModeRemote(mode, (_r, error) => {
            if (error)
                logError(error, 'gpu-power-mode: SetMode failed');
            else
                this._refreshStatus();
        });
    }

    _startPolling() {
        this._refreshStatus();
        if (this._pollId)
            return;
        this._pollId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT,
            POLL_INTERVAL, () => {
                this._refreshStatus();
                return GLib.SOURCE_CONTINUE;
            });
    }

    _stopPolling() {
        if (this._pollId) {
            GLib.source_remove(this._pollId);
            this._pollId = 0;
        }
    }

    destroy() {
        this._stopPolling();
        if (this._sendId) {
            GLib.source_remove(this._sendId);
            this._sendId = 0;
        }
        this._proxy = null;
        super.destroy();
    }
});

const GpuPowerIndicator = GObject.registerClass(
class GpuPowerIndicator extends SystemIndicator {
    _init() {
        super._init();
        this._toggle = new GpuPowerToggle();
        this.quickSettingsItems.push(this._toggle);
    }

    destroy() {
        this._toggle.destroy();
        super.destroy();
    }
});

export default class GpuPowerModeExtension extends Extension {
    enable() {
        this._indicator = new GpuPowerIndicator();
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);
    }

    disable() {
        this._indicator.destroy();
        this._indicator = null;
    }
}

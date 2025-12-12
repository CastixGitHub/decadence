import pyglet
from pyglet.window import Window
from pyglet.text import Label
from pyglet.gui import TextEntry
from configparser import ConfigParser
from functools import partial
from subprocess import check_output, CalledProcessError
from multiprocessing import Process
from threading import Thread
from pathlib import Path
from os import access, F_OK, kill
from signal import SIGINT
from sys import stderr
import re


from glsl_button import SinScreens, SinButton

import dbus  # dbus-python on PyPi
from dbus.mainloop.glib import DBusGMainLoop
# gdbus introspect -e -d org.jackaudio.service -o /org/jackaudio/Controller
GDbus = None
d_jack = None
patchbay = None
jackcfg = None
a2jmidid = None
DBusGMainLoop(set_as_default=True)
def dbus_reconnect():
    global GDbus, d_jack, patchbay, jackcfg, jack_control, a2jmidid
    GDbus = dbus.bus.BusConnection()
    d_jack = GDbus.get_object(
        "org.jackaudio.service",
        "/org/jackaudio/Controller"
    )
    patchbay = dbus.Interface(d_jack, "org.jackaudio.JackPatchbay")
    jackcfg = dbus.Interface(d_jack, "org.jackaudio.Configure")
    # yea, all of them
    a2jmidid = dbus.Interface(
        GDbus.get_object("org.gna.home.a2jmidid", "/"),
        "org.gna.home.a2jmidid.control"
    )
dbus_reconnect()

class Graph:  # TODO: also map IDs and handle port renaming
    #                 but we don't need that, so...
    def __init__(self):
        self._version = 0
        self._graph = None
        self._server_started = False

    def ds_server_started(self,):
        self._server_started = True

    def ds_server_stopped(self):
        self._server_started = False

    @property
    def server_started(self):
        if not self._server_started:
            self._server_started = bool(d_jack.IsStarted())
        return self._server_started

    @property
    def graph(self):
        # one question... giving the last known means outputting the diff?
        # I don't think so...
        empty = [0, {}, {}]
        if not self.server_started:
            return self._graph or empty
        try:
            graph = patchbay.GetGraph(self._version)
        except dbus.exceptions.DBusException as exc:
            if 'org.jackaudio.Error.ServerNotRunning' in str(exc):
                return self._graph or empty
            elif 'org.jackaudio.Error.InvalidArgs' in str(exc):
                self._version = 0
                return self.graph
            raise
        if int(graph[0]) != self._version:
            self._version = int(graph[0])
            self._graph = graph
        return self._graph

    def get_connections(self):
        _connections = set()
        for connections_a in self.graph[2]:
            connections = connections_a[1::2]
            connections = [
                f'{client}:{port}'
                for client, port in zip(connections[::2], connections[1::2])
            ]
            _connections |= set(zip(connections[::2], connections[1::2]))
        connections = {}
        for conn in _connections:
            connections.setdefault(conn[0], []).append(conn[1])
        return connections

    def get_clients(self):
        return {
            str(client[1]): int(client[0])
            for client in self.graph[1]
        }


    def kill(self, client_id):
        if client_id:
            pid = patchbay.GetClientPID(dbus.UInt64(client_id))
            try:
                kill(pid, SIGINT)
                print(f'Killed {pid} with SIGINT')
            except ProcessLookupError: ...

    def get_client_id(self, client_name):
        return self.get_clients().get(client_name)
graph = Graph()
patchbay.connect_to_signal(
    'ServerStarted',
    graph.ds_server_started,
    "org.jackaudio.JackControl"
)
patchbay.connect_to_signal(
    'ServerStopped',
    graph.ds_server_stopped,
    "org.jackaudio.JackControl"
)

class MIDId:
    def start(self):
        if not a2jmidid.is_started():
            self.enforce_config()
            a2jmidid.start()
        return self.is_started

    def stop(self):
        if a2jmidid.is_started():
            a2jmidid.stop()
        return not self.is_started

    @property
    def is_started(self):
        res = a2jmidid.is_started()
        self.set_started_gui(res)
        return res

    def set_started_gui(self, val):
        global midid_started_btn
        midid_started_btn.toggle(val)

    def enforce_config(self):
        a2jmidid.set_disable_port_uniqueness(
            not global_config.getboolean('a2jmidid', 'port_uniqueness')
        )
        a2jmidid.set_hw_export(
            global_config.getboolean('a2jmidid', 'export_hw')
        )

    def ds_bridge_started(self):
        self.set_started_gui(True)

    def ds_bridge_stopped(self):
        self.set_started_gui(False)
midid = MIDId()
a2jmidid.connect_to_signal(
    'bridge_started',
    midid.ds_bridge_started,
    "org.gna.home.a2jmidid.control"
)
a2jmidid.connect_to_signal(
    'bridge_stopped',
    midid.ds_bridge_stopped,
    "org.gna.home.a2jmidid.control"
)

def dbus_gi_loop():
    from gi.repository import GLib  # pip install pygobject
    # ewww, must use gi? we got gtk bindings then...
    # maybe let's help dbus-python supporting more event loops
    loop = GLib.MainLoop()
    loop.run()
Thread(name='dbusloop', target=dbus_gi_loop).start()
# TODO: later make this a daemon?

global_config = ConfigParser()
config_path = Path('~/.config/decadence.ini').expanduser()
if access(config_path, F_OK):
    global_config.read(config_path)
else:
    global_config.read_dict({
        'a2j_bridge': {
            'autostart': False,
            'channels': 2,
            'tool': 'jack_examples',
        },
        'a2jmidid': {
            'autostart': False,
            'export_hw': False,
            'port_uniqueness': False,
            # 'note_filtering': ... # -n     do not filter note on
            # whut? not exposed through dbus anyway...
            # actually do we need to store them?
        }
    })
def write_global_config():
    with open(config_path.expanduser(), 'w') as config_file:
        global_config.write(config_file)

window = pyglet.window.Window(caption='decadence', width=600, height=500)
# i3wm users: $mod+Shift+space to toggle floating to tiling
#   autostarts with floating, not worth to change that

#wel = pyglet.window.event.WindowEventLogger()
#window.push_handlers(wel)

has_error = False

def error_dialog(msg, title='Error'):
    global has_error
    if has_error:
        print(msg, file=stderr)
        return # avoid infinite error msgs
    has_error = True
    w = Window(
        caption=title,
        style=Window.WINDOW_STYLE_DIALOG,
        width=800,
        height=200,
    )
    b = pyglet.graphics.Batch()

    @w.event
    def on_draw():
        w.clear()
        labels = []  # TODO: there's a pyglet text module that does this better
        cxline = 80
        for i in range(10):
            labels.append(Label(
                (line := msg[i * cxline : (i + 1) * cxline]),
                y=w.height - 20 * (i+1),
                font_name='monospace',
                batch=b
            ))
            if len(line) < cxline:
                break
        b.draw()

    @w.event
    def on_close():
        has_error = False

btn_w, btn_h = 60, 20
def welcome_x(): return window.width // 2
def welcome_y(): return window.height - 25
def status_y(i): return window.height - 50 - (btn_h + 5) * i
def status_btn_x(): return window.width - 15 - btn_w
def status_btn_y(i): return window.height - 50 - (btn_h + 5) * i
def status_btnl_x(): return window.width - 15 - btn_w + 6
def status_btnl_y(i): return window.height - 50 + 4 - (btn_h + 5) * i
def cfg_title_x(offset=0): return offset + 15
def cfg_title_y(offset=window.height - 50): return offset
def cfg_btn_x(i, offset=0): return offset + 15
def cfg_btn_y(i, offset=window.height - 75): return offset + 20 - 20 * i - 2 * i
def cfg_btnl_x(i, offset=0): return offset + 15 + 20 + 2
def cfg_btnl_y(i, offset=window.height - 75): return offset - 20 * i - 2 * i + 4
def cfg_int_x(_): return window.width - 15 - 50
def cfg_int_y(i): return window.height - 50 - 30 * i
def cfg_intl_x(_): return window.width - 15 - 50 - 5
def cfg_intl_y(i): return window.height - 50 - 30 * i - 2 + 10
def cfg_action_x(i): return 10 + btn_w * i + 5 * i
def cfg_action_y(): return 10 + btn_h

GREEN = (0x0c, 0xcc, 0x0b, 0xff)
RED = (0xcc, 0x0c, 0x0b, 0xff)
YELL = (0xcc, 0xca, 0x0b, 0xff)
BLACK = (0x00, 0x00, 0x00, 0xff)


'''
# mhhh, a pyglet bug, https://github.com/pyglet/pyglet/blob/f93b602ea3dde726c6661aa8aaf7400d132f445a/pyglet/gui/widgets.py#L268
# I'm keeping them but I'm not using them...
from inspect import getsource
for evt_name in ('on_mouse_leave', 'on_mouse_release'):
    _source = getsource(getattr(PushButton, evt_name))
    _source = '\n'.join(line[4:] for line in _source.replace(
        "self.dispatch_event('on_release')",
        "self.dispatch_event('on_release', self)",
        # wrong event? missing self?  # just missing self!
    ).replace(
        # did they ever run this?
        "if not self.enabled or not self._pressed",
        "if not self.enabled and not self._pressed",
    ).split('\n'))
    print('Needed to execute this:', file=stderr)
    print(_source, file=stderr)
    exec(_source, (_glo := {}), (_loc := {}))
    setattr(PushButton, evt_name, _loc[evt_name])
'''


# drawing disorder and order
batch_status = pyglet.graphics.Batch()
batch_status_btnl = pyglet.graphics.Batch()
configuring_what_label_batch = pyglet.graphics.Batch()
cfg_engine_labels = pyglet.graphics.Batch()
cfg_sin_cs_batch = pyglet.graphics.Batch()
cfg_engine_integers_batch = pyglet.graphics.Batch()
cfg_driver_labels = pyglet.graphics.Batch()
cfg_driver_integers_batch = pyglet.graphics.Batch()
cfg_driver_duplex_labels = pyglet.graphics.Batch()
cfg_driver_non_duplex_labels = pyglet.graphics.Batch()

btns = SinScreens(window)
class Navigation:
    def to_main(self):
        global window, btns, cfg_engine_integers
        self.name = 'main'
        btns.set_active('main')
        for feat in cfg_engine_integers.values():
            window.remove_handlers(feat['integer_entry'])

    def to_engine(self):
        global window, btns, cfg_engine_integers
        self.name = 'engine'
        btns.set_active('engine')
        configuring_engine.value = 'engine'
        for feat in cfg_engine_integers.values():
            window.push_handlers(feat['integer_entry'])

    def to_driver(self):
        global window, btns, cfg_engine_integers
        self.name = 'driver'
        btns.set_active('driver')
        for feat in cfg_engine_integers.values():
            window.remove_handlers(feat['integer_entry'])


navigation = Navigation()


# Home UI elements
welcome = Label(
    'Welcome to decadence',
    anchor_x='center', x=welcome_x(), y=welcome_y(),
    font_size=20,
)

status_x = 15
status_x2 = status_x + 150
server_status = Label(
    'Server Status:',
    x=status_x, y=status_y(0),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
server_status_val = Label(
    '---',
    x=status_x2, y=status_y(0),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
rt_status = Label(
    'Realtime:',
    x=status_x, y=status_y(1),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
rt_status_val = Label(
    '---',
    x=status_x2, y=status_y(1),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
dsp_status = Label(
    'DSP Load:',
    x=status_x, y=status_y(2),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
dsp_status_val = Label(
    '---',
    x=status_x2, y=status_y(2),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
xruns_status = Label(
    'Xruns:',
    x=status_x, y=status_y(3),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
xruns_status_val = Label(
    '---',
    x=status_x2, y=status_y(3),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
buffer_size_status = Label(
    'Buffer Size:',
    x=status_x, y=status_y(4),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
buffer_size_status_val = Label(
    '---',
    x=status_x2, y=status_y(4),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
sr_status = Label(
    'Sample Rate:',
    x=status_x, y=status_y(5),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
sr_status_val = Label(
    '---',
    x=status_x2, y=status_y(5),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
bl_status = Label(
    'Block Latency:',
    x=status_x, y=status_y(6),
    font_name='monospace', font_size=13,
    batch=batch_status,
)
bl_status_val = Label(
    '---',
    x=status_x2, y=status_y(6),
    font_name='monospace', font_size=13,
    batch=batch_status,
)


class MainButton(SinButton):
    def on_press(widget):
        print('on_press', widget)
        if configure_status_btn is widget:
            navigation.to_engine()
            return
        if action := dbus_buttons.get(widget):
            try:
                action()
            except BaseException as exc:
                error_dialog(str(exc))
        else:
            print(msg := 'UNKNOWN button pressed')
            error_dialog(msg)

start_status_btn = btns.add(
    'main',
    (start_status_btn_label := Label(
        'Start',
        x=status_btnl_x(), y=status_btnl_y(0),
        font_name='monospace', font_size=10, color=GREEN,
        batch=batch_status_btnl,
    )),
    x=status_btn_x(), y=status_btn_y(0),
    size=(btn_w, btn_h),
    is_on=False, is_radio=True, is_enabled=True,
    cls=MainButton,
)
stop_status_btn = btns.add(
    'main',
    (stop_status_btn_label := Label(
        'Stop',
        x=status_btnl_x(), y=status_btnl_y(1),
        font_name='monospace', font_size=10, color=YELL,
        batch=batch_status_btnl,
    )),
    x=status_btn_x(), y=status_btn_y(1),
    size=(btn_w, btn_h),
    is_on=False, is_radio=True, is_enabled=True,
    cls=MainButton,
)
force_restart_status_btn = btns.add(
    'main',
    (force_restart_status_btn_label := Label(
        'Kill',
        x=status_btnl_x(), y=status_btnl_y(2),
        font_name='monospace', font_size=10, color=RED,
        batch=batch_status_btnl,
    )),
    x=status_btn_x(), y=status_btn_y(2),
    size=(btn_w, btn_h),
    is_on=False, is_radio=True, is_enabled=True,
    cls=MainButton,
)
reset_xruns_status_btn = btns.add(
    'main',
    (reset_xruns_status_btn_label := Label(
        'X ok',
        x=status_btnl_x(), y=status_btnl_y(3),
        font_name='monospace', font_size=10,
        batch=batch_status_btnl,
    )),
    x=status_btn_x(), y=status_btn_y(3),
    size=(btn_w, btn_h),
    is_on=False, is_radio=True, is_enabled=True,
    cls=MainButton,
)
switch_master_status_btn = btns.add(
    'main',
    (switch_master_status_btn_label := Label(
        'S Mast',
        x=status_btnl_x(), y=status_btnl_y(4),
        font_name='monospace', font_size=10,
        batch=batch_status_btnl,
    )),
    x=status_btn_x(), y=status_btn_y(4),
    size=(btn_w, btn_h),
    is_on=False, is_radio=True, is_enabled=True,
    cls=MainButton,
)
configure_status_btn = btns.add(
    'main',
    (configure_status_btn_label := Label(
        'Config',
        x=status_btnl_x(), y=status_btnl_y(6),
        font_name='monospace', font_size=10,
        batch=batch_status_btnl,
    )),
    x=status_btn_x(), y=status_btn_y(6),
    size=(btn_w, btn_h),
    is_on=False, is_radio=False, is_enabled=True,
    cls=MainButton,
)

cfg_status_bridge_label = Label(
    'ALSA2JACK:',
    x=15, y=status_btn_y(7) - 15,
    font_name='monospace',
    batch=batch_status_btnl,
)
bridge_tool = btns.add(
    'main',
    (cfg_status_dridge_label0 := Label(
        'jack examples',
        x=140, y=status_btn_y(7) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    )),
    x=120, y=status_btn_y(7),
    size=20,
    is_on=global_config.get('a2j_bridge', 'tool') == 'jack_examples',
    is_radio='bridge-tool', is_enabled=True,
)
@bridge_tool.event
def after_press(btn):
    global_config.set('a2j_bridge', 'tool', 'jack_examples')
    write_global_config()
bridge_tool = btns.add(
    'main',
    (cfg_status_dridge_label0 := Label(
        'zita',
        x=320, y=status_btn_y(7) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    )),
    x=300, y=status_btn_y(7),
    size=20,
    is_on=global_config.get('a2j_bridge', 'tool') == 'zita_a2j',
    is_radio='bridge-tool', is_enabled=False,
    # TODO: Can i have a zita?
    #       Need to also kill alsa_in/out once checked
    #       Better do so after confirmation dialog
    #       Then uncheck started/connected
)
@bridge_tool.event
def after_press(btn):
    global_config.set('a2j_bridge', 'tool', 'zita_a2j')
    write_global_config()
bridge_autostart = btns.add(
    'main',
    (yet_another_label := Label(
        'On Start',
        x=120, y=status_btn_y(8) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    )),
    size=20,
    x=100, y=status_btn_y(8),
    is_on=global_config.getboolean('a2j_bridge', 'autostart'),
    is_radio=False, is_enabled=True,
)
@bridge_autostart.event
def after_press(btn):
    global_config.set('a2j_bridge', 'autostart', 'true' if btn._pressed else 'false')
    write_global_config()

def aloop_started(has_btn=True):
    def _toggle(val: bool):
        if has_btn:
            aloop_started_btn.toggle(val)
        return val
    if not graph.server_started:
        return _toggle(False)
    try:
        all_ports = patchbay.GetAllPorts()
    except Exception as exc:
        if 'org.jackaudio.Error.ServerNotRunning' in str(exc):
            return _toggle(False)
        raise
    in_started = [str(x) for x in all_ports if 'alsa2jack' in x]
    out_started = [str(x) for x in all_ports if 'jack2alsa' in x]
    return _toggle(in_started and out_started)

def aloop_connected(has_btn=True):
    connections = graph.get_connections()
    connected = (
        'alsa2jack:capture_1' in connections
        and 'jack2alsa:playback_1' in connections.get('system:capture_1', [])
    )
    if has_btn:
        aloop_connected_btn.toggle(connected)
    return connected

aloop_started_btn = btns.add(
    'main',
    (aloop_started_lbl := Label(
        'Started',
        x=250, y=status_btn_y(8) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    )),
    size=20,
    x=230, y=status_btn_y(8),
    is_on=aloop_started(False), is_radio=False, is_enabled=False,
)
aloop_connected_btn = btns.add(
    'main',
    (aloop_connected_lbl := Label(
        'Connected',
        x=350, y=status_btn_y(8) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    )),
    size=20,
    x=330, y=status_btn_y(8),
    is_on=aloop_connected(False), is_radio=False, is_enabled=False,
)

def check_kernel_SND_ALOOP():
    if check_output(['grep', '-l', '-e', "snd_aloop", '/proc/kallsyms']):
        return True # module loaded
    error_dialog('SND_ALOOP',
        'You need to check SND_ALOOP kernel config.\n'
        "Try `modprobe snd_aloop` if that's a module"
    )
    return False

aloop_in = None
aloop_out = None
def start_aloop():
    global aloop_in, aloop_out
    SR = d_jack.GetSampleRate()
    PS = d_jack.GetBufferSize()
    CH = global_config.getint("a2j_bridge", "channels")
    env = {
        'JACK_SAMPLE_RATE': f'{SR:d}',
        'JACK_PERIOD_SIZE': f'{PS:d}',
    }
    def target_in():
        try:
            check_output([
                '/usr/bin/alsa_in',
                '-d', 'cloop',  # capture loop
                f'{SR:d}',
                '-p',
                f'{PS:d}',
                "-j", "alsa2jack",
                "-c", f'{CH:d}',
            ], env=env)
        except CalledProcessError as exc:
            print('alsa_in died')
    (aloop_in := Process(target=target_in)).start()
    def target_out():
        try:
            check_output([
                '/usr/bin/alsa_out',
                '-d', 'ploop',  # playback loop
                f'{SR:d}',
                '-p',
                f'{PS:d}',
                "-j", "jack2alsa",
                "-c", f'{CH:d}',
            ], env=env)
        except CalledProcessError as exc:
            print('alsa_out died')
    (aloop_out := Process(target=target_out)).start()

def aloop_stop():
    global aloop_in, aloop_out
    if aloop_in:
        aloop_in.terminate()
    if aloop_out:
        aloop_out.terminate()
    # but that's not enough ofc
    graph.kill(graph.get_client_id('alsa2jack'))
    graph.kill(graph.get_client_id('jack2alsa'))

def connect_aloop():
    def _connect_aloop():
        while not aloop_started():
            pyglet.app.event_loop.sleep(0.05)
        for chan in range(1, global_config.getint('a2j_bridge', 'channels') + 1):
            try:
                patchbay.ConnectPortsByName(
                    'alsa2jack', f'capture_{chan}',
                    'system', f'playback_{chan}',
                )
            except dbus.exceptions.DBusException as exc:
                if 'failed with 17' not in str(exc):
                    raise  # 17 already connected
            try:
                patchbay.ConnectPortsByName(
                    'system', f'capture_{chan}',
                    'jack2alsa', f'playback_{chan}',
                )
            except dbus.exceptions.DBusException as exc:
                if 'failed with 17' not in str(exc):
                    raise  # 17 already connected
        aloop_connected_btn.toggle(True)
    Thread(target=_connect_aloop).start()

# next a2jmidid

cfg_status_a2jmidid_label = Label(
    'A2Jmidid:',
    x=15, y=status_btn_y(9) - 15,
    font_name='monospace',
    batch=batch_status_btnl,
)
class EHWBtn(SinButton):
    def on_press(btn):
        global_config.set('a2jmidid', 'export_hw', 'true' if not btn._pressed else 'false'),
        write_global_config()
        if not midid.is_started:
            a2jmidid.set_hw_export(not btn._pressed)
            super().on_press() # then the toggle ofc (hence not)
a2jmidid_export_hw_btn = btns.add(
    'main',
    Label(
        'Export HW',
        x=140, y=status_btn_y(9) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    ),
    x=120, y=status_btn_y(9),
    size=20,
    is_on=global_config.getboolean('a2jmidid', 'export_hw'),
    is_radio=False, is_enabled=True,
    cls=EHWBtn,
)

class PortUniqBtn(SinButton):
    def on_press(btn):
        global_config.set('a2jmidid', 'port_uniqueness', 'true' if not btn._pressed else 'false'),
        # not ofc
        write_global_config()
        if not midid.is_started:
            a2jmidid.set_disable_port_uniqueness(btn._pressed)
            super().on_press()
a2jmidid_uniqueness_btn = btns.add(
    'main',
    Label(
        'Port Uniqueness',
        x=270, y=status_btn_y(9) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    ),
    x=250, y=status_btn_y(9),
    size=20,
    is_on=global_config.getboolean('a2jmidid', 'port_uniqueness'),
    is_radio=False, is_enabled=True,
    cls=PortUniqBtn,
)
bridge_midid_autostart = btns.add(
    'main',
    Label(
        'On Start',
        x=120, y=status_btn_y(10) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    ),
    size=20,
    x=100, y=status_btn_y(10),
    is_on=global_config.getboolean('a2jmidid', 'autostart'),
    is_radio=False, is_enabled=True,
)
@bridge_midid_autostart.event
def after_press(btn):
    global_config.set('a2jmidid', 'autostart', 'true' if btn._pressed else 'false')
    write_global_config()
midid_started_btn = btns.add(
    'main',
    Label(
        'Started',
        x=250, y=status_btn_y(10) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    ),
    size=20,
    x=230, y=status_btn_y(10),
    is_on=a2jmidid.is_started(), is_radio=False, is_enabled=False,
)
midid_ehw_btn = btns.add(
    'main',
    Label(
        'E.HW',
        x=355, y=status_btn_y(10) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    ),
    size=15,
    x=340, y=status_btn_y(10),
    is_on=a2jmidid.get_hw_export(), is_radio=False, is_enabled=False,
)
midid_uniq_btn = btns.add(
    'main',
    Label(
        'Uniq',
        x=415, y=status_btn_y(10) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    ),
    size=15,
    x=400, y=status_btn_y(10),
    is_on=not a2jmidid.get_disable_port_uniqueness(),
    is_radio=False, is_enabled=False,
)

def come_on_start():
    d_jack.StartServer()
    # TODO: manage a2j pulse2j etc
    #      modprobe snd-aloop
    #      alsa_in -d cloop 44100 -p 1024 -j alsa2jack -q 1 -c 2
    #      alsa_out -d ploop 44100 -p 1024 -j jack2alsa -q 1 -c 2
    if global_config.getboolean('a2j_bridge', 'autostart'):
        if global_config.get('a2j_bridge', 'tool') == 'jack_examples':
            if not aloop_started():
                if check_kernel_SND_ALOOP():
                    start_aloop()
            connect_aloop()
    if global_config.getboolean('a2jmidid', 'autostart'):
        midid.start()

def now_stop_them():
    aloop_stop()
    midid.stop()
    d_jack.StopServer()

def force_restart():
    try:
        print('killing jack: ', d_jack.Exit())
        for _ in range(20):
            pyglet.app.event_loop.sleep(0.05)
    except dbus.exceptions.DBusException as exc:
        print('caught', exc)
        ...  # tells didn't answer
        ...  # doesn't tell it anymore...
    # so we can reconnect
    GDbus.close()
    dbus_reconnect()
    print('starting jack: ', come_on_start())


dbus_buttons = {
    start_status_btn: come_on_start,
    stop_status_btn: now_stop_them,
    force_restart_status_btn: force_restart,
    reset_xruns_status_btn: d_jack.ResetXruns,
    switch_master_status_btn: d_jack.SwitchMaster,
}


def get_info():  # through dbus
    try:
        msg = None
        dsp_status_val.text = f'{d_jack.GetLoad():.2f}%'
    except dbus.exceptions.DBusException as exc:
        msg = str(exc)
    if msg is None:
        server_status_val.text = 'Started'
        xruns_status_val.text = f'{d_jack.GetXruns()}'
        buffer_size_status_val.text = f'{d_jack.GetBufferSize()} samples'
        rt_status_val.text = 'Yes' if d_jack.IsRealtime() else 'No'
        sr_status_val.text = f'{d_jack.GetSampleRate()} Hz'
        bl_status_val.text = f'{d_jack.GetLatency():.2f} ms'
    else:
        dsp_status_val.text = msg
        server_status_val.text = 'Stopped'\
            if 'ServerNotRunning' in msg else 'Unknown'

# configure UI elements
configure_text = Label(
    'Configure',
    anchor_x='left', x=15, y=welcome_y(),
    font_size=20,
)


def outline_config(w):
    consts = None
    def hack_walrus(s):
        nonlocal consts
        consts = jackcfg.GetParameterConstraint([w, s])
        return consts[3]
    return {
        str(s): (o := {
            'description': str(jackcfg.GetParameterInfo([w, s])[2]),
            'constraints': {
                str(con[1]): con[0]
                for con in hack_walrus(s)
            },
            'getter': partial(
                (lambda s_: jackcfg.GetParameterValue([w, s_])),
                s
            ),
            'setter': partial(
                (lambda s_, v: jackcfg.SetParameterValue([w, s_], v)),
                s
            ),
            'retter': partial(
                (lambda s_: jackcfg.ResetParameterValue([w, s_])),
                s
            ),
        })
        and o['constraints'].update({'is_range': bool(consts[0])}) or True
        and o['constraints'].update({'is_strict': bool(consts[1])}) or True
        and o['constraints'].update({'is_fake_value': bool(consts[2])})
        or o
        for s in jackcfg.ReadContainer([w])[1]
    }
engine_features = outline_config('engine')
#for k, v in engine_features.items():
#    print(k, v)
#    if v['constraints']['is_strict']:
#        print(f'engine.{k}: {v["constraints"]}')
driver_features = outline_config('driver')
#for k, v in driver_features.items():
#    if v['constraints']['is_strict']:
#        print(f'driver.{k}: {v["constraints"]}')

# labels and values shown in GUI fetched from dbus
#print(engine_features.keys())
# get everything filtering for by type and also store defaults
for feat_name, feat in engine_features.items():
    is_set, default, value = feat['getter']()
    feat['default'] = default
    feat['is_bool'] = isinstance(value, dbus.Boolean)
    feat['is_uint32'] = isinstance(value, dbus.UInt32)
    feat['is_int32'] = isinstance(value, dbus.Int32)
for feat_name, feat in driver_features.items():
    is_set, default, value = feat['getter']()
    feat['default'] = default
    feat['is_bool'] = isinstance(value, dbus.Boolean)
    feat['is_uint32'] = isinstance(value, dbus.UInt32)
    feat['is_int32'] = isinstance(value, dbus.Int32)
cfg_engine_toggles = {}
i = 0

you_need_to_keep_a_ref_to_labels_somewhere = Label(
    'Engine Booleans:',
    x=cfg_title_x(), y=cfg_title_y(window.height - 120),
    font_name='monospace',
    batch=cfg_engine_labels,
)

relabeling = {
    'sync': 'Server Syncronous Mode',
    'replace-registry': 'Replace Shared Memory Registry',
}
for feat_name, feat in engine_features.items():
    if feat['is_bool']:
        i += 1
        cfg_engine_toggles[feat_name] = {
            'btn': (btn := btns.add(
                'engine',
                (lbl := Label(
                    relabeling.get(feat_name, feat_name.capitalize()),
                    x=cfg_btnl_x(i), y=cfg_btnl_y(i, window.height - 120),
                    font_name='monospace',
                    batch=cfg_engine_labels,
                )),
                x=cfg_btn_x(i), y=cfg_btn_y(i, window.height - 120),
                size=20,
                is_on=False, is_radio=False, is_enabled=True,
            )),
            'label': lbl,
        }
        btn.feat_name = feat_name

cfg_sin_clock_source_feat = engine_features['clock-source']
# ... 'Clocksource type : c(ycle) | h(pet) | s(ystem).'
cs_re = re.compile(r'\s*([a-zA-Z])(\([a-zA-z]*\))\s*')

cfg_sin_clock_source_cfg = {
    f'{mg[0]}{mg[1][1:-1]}'
    : ord(mg[0])
    for t in cfg_sin_clock_source_feat['description'].split(
        ':', 1)[1].split('|')
    if (matched := cs_re.match(t)) and (mg := matched.groups())
}
if 'cycle' in cfg_sin_clock_source_cfg:  # shouldn't be there anymore?
    del cfg_sin_clock_source_cfg['cycle']
cfg_title_cs = Label(
    'Clock Selection:',
    x=cfg_title_x(), y=cfg_title_y(),
    font_name='monospace',
    batch=cfg_engine_labels,
)
for i, v in enumerate(cfg_sin_clock_source_cfg.items()):
    txt, val = v
    # should be fine to lose radio buttons here
    clk_btn = btns.add(
        'engine',
        Label(
            txt,
            x=cfg_btnl_x(i), y=cfg_btnl_y(i),
            font_name='monospace',
            batch=cfg_engine_labels,
        ),
        x=cfg_btn_x(i), y=cfg_btn_y(i),
        size=20,
        is_on=False, is_radio='engine_clk', is_enabled=True,
        value=val,
    )

cfg_title_scm = Label(
    'Self Connect Mode:',
    x=cfg_title_x(), y=cfg_title_y(window.height - 260),
    font_name='monospace',
    batch=cfg_engine_labels,
)
self_connect_modes = engine_features['self-connect-mode']['constraints'].items()
for i, kv in enumerate(self_connect_modes):
    text, val = kv
    if text in ('is_range', 'is_strict', 'is_fake_value'):
        break  # break altogeter then, they're at the end

    scm_btn = btns.add(
        'engine',
        Label(
            text,
            x=cfg_btnl_x(i), y=cfg_btnl_y(i, window.height - 280),
            font_name='monospace',
            batch=cfg_engine_labels,
        ),
        x=cfg_btn_x(i), y=cfg_btn_y(i, window.height - 280),
        size=20,
        is_on=False, is_radio='engine_scm', is_enabled=True,
        value=val,
    )

class IntegerEntry(TextEntry):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.modified = False
    def on_text(self, text):
        super().on_text(text)
        if self._focus:
            self.modified = True
        # print('on_text', self, text)
        # this thing is called on all the instances

i = 0
cfg_engine_integers = {}
for feat_name, feat in engine_features.items():
    if (feat['is_uint32'] or feat['is_int32']) and feat_name != 'clock-source':
        i += 1
        cfg_engine_integers[feat_name] = {
            'integer_entry': IntegerEntry(
                str(int(feat['getter']()[2])),
                x=cfg_int_x(i), y=cfg_int_y(i),
                width=50,
                color=(0xcc, 0xcc, 0xcc, 0xff),
                text_color=(0x00, 0x00, 0x00, 0xff),
                caret_color=(0x00, 0x00, 0x00, 0xff),
                batch=cfg_engine_integers_batch,
            ),
            'label': Label(
                feat_name.replace('-', ' ').capitalize()
                if feat_name != 'client-timeout'
                else 'Client timeout (ms)',
                x=cfg_intl_x(i), y=cfg_intl_y(i), anchor_x='right',
                font_name='monospace',
                batch=cfg_engine_labels,
            ),
        }

# END of engine screen, start of driver one
cfg_driver_toggles = {}
i = 0
relabeling = {
    'softmode': 'Soft (no Xrun handling)',
    'monitor':  'Software Monitoring',
    'shorts':   'Force 16-bit mode',
}
for feat_name, feat in driver_features.items():
    if feat['is_bool']:
        i += 1
        cfg_driver_toggles[feat_name] = {
            'btn': (btn := btns.add(
                'driver',
                (lbl := Label(
                    relabeling.get(feat_name, feat_name.capitalize()),
                    x=cfg_btnl_x(i), y=cfg_btnl_y(i, window.height - 50),
                    font_name='monospace',
                    batch=cfg_driver_labels,
                )),
                x=cfg_btn_x(i), y=cfg_btn_y(i, window.height - 50),
                size=20,
                is_on=False, is_radio=False, is_enabled=True,
            )),
            'label': lbl,
        }
        btn.feat_name = feat_name
        if feat_name == 'duplex':
            lbl.color=GREEN

i += 1
j = 0
asdaishdoa = Label(
    'Dither:',
    x=cfg_btnl_x(i) - 20, y=cfg_btnl_y(i, window.height - 50),
    font_name='monospace',
    batch=cfg_driver_labels,
)
for con_txt, con_byte in driver_features['dither']['constraints'].items():
    if con_txt.startswith('is_'): continue
    xo = j * 80 - (0 if j == 0 else 20)
    dither_btn = btns.add(
        'driver',
        Label(
            con_txt.capitalize()[:6],
            x=cfg_btnl_x(i) + xo, y=cfg_btnl_y(i, window.height - 50) - 20,
            font_name='monospace',
            batch=cfg_driver_labels,
        ),
        x=cfg_btn_x(i) + xo, y=cfg_btn_y(i, window.height - 50) - 20,
        size=20,
        is_on=False, is_radio='dither', is_enabled=True,
        value=int(con_byte),
    )
    j += 1

i += 2
j = 0
ygsaugaysu = Label(
    'ALSA MIDI Driver:',
    x=cfg_btnl_x(i) - 20, y=cfg_btnl_y(i, window.height - 50),
    font_name='monospace',
    batch=cfg_driver_labels,
)
for con_txt, con_str in driver_features['midi-driver']['constraints'].items():
    if con_txt.startswith('is_'): continue
    xo = j * 80 - (0 if j == 0 else 20)
    midi_btn = btns.add(
        'driver',
        Label(
            str(con_str),
            x=cfg_btnl_x(i) + xo, y=cfg_btnl_y(i, window.height - 50) - 20,
            font_name='monospace',
            batch=cfg_driver_labels,
        ),
        x=cfg_btn_x(i) + xo, y=cfg_btn_y(i, window.height - 50) - 20,
        size=20,
        is_on=False, is_radio='midi-driver', is_enabled=True,
        value=str(con_str),
    )
    j += 1

i += 2

#print(driver_features['device']['constraints'])
#print(driver_features['capture']['constraints'])
#print(driver_features['playback']['constraints'])
# data is there yet...
# TODO: one needs to restart the application to see new soundcards
def _get_alsa_device_list(playback):
    result = [('none', 'none')]
    out = check_output([
        'aplay' if playback else 'arecord',
        '-l'
    ]).decode().split("\n")
    for line in out:
        if line.startswith('card '):
            card, device = line.split(',', 1)
            card_index, card_name = card.split(': ', 1)
            card_index = int(card_index[len('card '):])
            card_name_ = card_name.split(' [', 1)[0]
            card_name = card_name.split(' [', 1)[1][:-1]
            device_index, device_name = device.split(': ', 1)
            device_index = int(device_index[len('device '):])
            device_name = device_name.split(' [', 1)[1][:-1]
            if card_name == 'Loopback':
                continue
            result.append((
                f'hw:{card_name_},{device_index}',
                f'{device_index}: {card_name} [{device_name}]',
            ))
    return result
def get_alsa_device_list(playback):
    if playback is None:
        capture = _get_alsa_device_list(False)
        playback = _get_alsa_device_list(True)
        return set(capture) & set(playback)
    else:
        return _get_alsa_device_list(playback)

duplex_selection_label = Label(
    'Duplex Device:',
    x=cfg_btnl_x(i) - 20, y=cfg_btnl_y(i, window.height - 50),
    font_name='monospace',
    batch=cfg_driver_duplex_labels,
)

@(btn := cfg_driver_toggles['duplex']['btn']).event
def after_press(btn):
    btns.set_duplex_side_effect(btn._pressed)

devices_i = i
for dev in get_alsa_device_list(None):
    duplex_btn = btns.add(
        'duplex',
        Label(
            dev[1],
            x=cfg_btnl_x(i), y=cfg_btnl_y(i, window.height - 50) - 20,
            font_name='monospace',
            batch=cfg_driver_duplex_labels,
        ),
        x=cfg_btn_x(i), y=cfg_btn_y(i, window.height - 50) - 20,
        size=20,
        is_on=False, is_radio='duplex-device', is_enabled=True,
        value=dev[0],
    )
    i += 1

i = devices_i
capture_selection_label = Label(
    'Capture Device:',
    x=cfg_btnl_x(i) - 20, y=cfg_btnl_y(i, window.height - 50),
    font_name='monospace',
    batch=cfg_driver_non_duplex_labels,
)
for dev in get_alsa_device_list(False):
    capture_btn = btns.add(
        'non_duplex',
        Label(
            dev[1],
            x=cfg_btnl_x(i), y=cfg_btnl_y(i, window.height - 50) - 20,
            font_name='monospace',
            batch=cfg_driver_non_duplex_labels,
        ),
        x=cfg_btn_x(i), y=cfg_btn_y(i, window.height - 50) - 20,
        size=20,
        is_on=False, is_radio='capture-device', is_enabled=True,
        value=dev[0],
    )
    i += 1
i += 1
playback_selection_label = Label(
    'Playback Device:',
    x=cfg_btnl_x(i) - 20, y=cfg_btnl_y(i, window.height - 50),
    font_name='monospace',
    batch=cfg_driver_non_duplex_labels,
)
for dev in get_alsa_device_list(False):
    playback_btn = btns.add(
        'non_duplex',
        Label(
            dev[1],
            x=cfg_btnl_x(i), y=cfg_btnl_y(i, window.height - 50) - 20,
            font_name='monospace',
            batch=cfg_driver_non_duplex_labels,
        ),
        x=cfg_btn_x(i), y=cfg_btn_y(i, window.height - 50) - 20,
        size=20,
        is_on=False, is_radio='playback-device', is_enabled=True,
        value=dev[0],
    )
    i += 1

i = 0
cfg_driver_integers = {}
relabeling = {
    'output-latency': 'OUT latency (frames)',
    'input-latency': 'IN latency (frames)',
    'outchannels': 'OUT N chans',
    'inchannels': 'IN N chans',
    'nperiods': 'Playback latency (frames)',
    'period': 'Frame Size',
    'rate': 'Sample Rate',
}
for feat_name, feat in driver_features.items():
    if feat['is_uint32'] or feat['is_int32']:
        i += 1
        cfg_driver_integers[feat_name] = {
            'integer_entry': IntegerEntry(
                str(int(feat['getter']()[2])),
                x=cfg_int_x(i), y=cfg_int_y(i),
                width=50,
                color=(0xcc, 0xcc, 0xcc, 0xff),
                text_color=(0x00, 0x00, 0x00, 0xff),
                caret_color=(0x00, 0x00, 0x00, 0xff),
                batch=cfg_driver_integers_batch,
            ),
            'label': Label(
                relabeling.get(feat_name, feat_name.replace('-', ' ').capitalize()),
                x=cfg_intl_x(i), y=cfg_intl_y(i), anchor_x='right',
                font_name='monospace',
                batch=cfg_driver_labels,
            ),
        }

# Both engine screen and driver screen
class CancelBtn(SinButton):
    def on_press(_):
        navigation.to_main()

class ResetBtn(SinButton):
    def on_press(_):
        engine_features['clock-source']['retter']()
        engine_features['self-connect-mode']['retter']()
        for feat_name, thing in cfg_engine_toggles.items():
            engine_features[feat_name]['retter']()
            thing['btn'].modified = False
        for feat_name, thing in cfg_engine_integers.items():
            engine_features[feat_name]['retter']()
            thing['integer_entry'].modified = False
        clk_btn.mark_group_as_not_modified()
        scm_btn.mark_group_as_not_modified()
        # ok, driver now
        for feat_name, thing in cfg_driver_toggles.items():
            driver_features[feat_name]['retter']()
            thing['btn'].modified = False
        for feat_name, thing in cfg_driver_integers.items():
            driver_features[feat_name]['retter']()
            thing['integer_entry'].modified = False
        driver_features['dither']['retter']()
        dither_btn.mark_group_as_not_modified()
        driver_features['midi-driver']['retter']()
        midi_btn.mark_group_as_not_modified()
        driver_features['device']['retter']()
        duplex_btn.mark_group_as_not_modified()
        driver_features['capture']['retter']()
        capture_btn.mark_group_as_not_modified()
        driver_features['playback']['retter']()
        playback_btn.mark_group_as_not_modified()
        navigation.to_main()

class SaveBtn(SinButton):
    def on_press(_):
        if clk_btn.modified:
            try:
                engine_features['clock-source']['setter'](
                    dbus.UInt32(clk_btn.value)
                )
                clk_btn.mark_group_as_not_modified()
                print(f'set engine.clock-source: {clk_btn.value}')
            except dbus.exceptions.DBusException as exc:
                msg = f'Error setting up engine parameter "clock-source"\n{exc}'
                on_error(msg)
        if scm_btn.modified:
            #print(type(cfg_sin_self_connect_mode.value['value']))
            engine_features['self-connect-mode']['setter'](scm_btn.value)
            scm_btn.mark_group_as_not_modified()
            print(f'set engine.self-connect-mode: {scm_btn.value}')
        for feat_name, thing in cfg_engine_toggles.items():
            btn = thing['btn']
            if btn.modified:
                print(f'set engine.{feat_name}: {btn._pressed}')
                engine_features[feat_name]['setter'](dbus.Boolean(btn._pressed))
                btn.modified = False
        for feat_name, thing in cfg_engine_integers.items():
            if (te := thing['integer_entry']).modified:
                print(f'set (int) engine.{feat_name}: {te.value}')
                engine_features[feat_name]['setter'](dbus.UInt32(te.value))
                te.modified = False
        # ok, driver now
        for feat_name, thing in cfg_driver_toggles.items():
            btn = thing['btn']
            if btn.modified:
                print(f'set driver.{feat_name}: {btn._pressed}')
                driver_features[feat_name]['setter'](dbus.Boolean(btn._pressed))
                btn.modified = False
        for feat_name, thing in cfg_driver_integers.items():
            if (te := thing['integer_entry']).modified:
                print(f'set (int) driver.{feat_name}: {te.value}')
                driver_features[feat_name]['setter'](dbus.UInt32(te.value))
                te.modified = False
        if dither_btn.modified:
            driver_features['dither']['setter'](dither_btn.value)
            dither_btn.mark_group_as_not_modified()
            print(f'set driver.dither: {dither_btn.value}')
        if midi_btn.modified:
            driver_features['midi-driver']['setter'](midi_btn.value)
            midi_btn.mark_group_as_not_modified()
            print(f'set driver.midi-driver: {midi_btn.value}')
        if duplex_btn.modified:
            driver_features['device']['setter'](duplex_btn.value)
            duplex_btn.mark_group_as_not_modified()
            print(f'set driver.device: {duplex_btn.value}')
        if capture_btn.modified:
            driver_features['capture']['setter'](capture_btn.value)
            capture_btn.mark_group_as_not_modified()
            print(f'set driver.capture: {capture_btn.value}')
        if playback_btn.modified:
            driver_features['playback']['setter'](playback_btn.value)
            playback_btn.mark_group_as_not_modified()
            print(f'set driver.playback: {playback_btn.value}')
        navigation.to_main()

cancel_btn = btns.add(
    'engine|driver',
    Label(
        'Back',
        x=cfg_action_x(0) + 6, y=cfg_action_y() - btn_h + 4,
        font_name='monospace',
        batch=configuring_what_label_batch,
    ),
    x=cfg_action_x(0), y=cfg_action_y(),
    size=(btn_w, btn_h),
    is_on=False, is_radio=True, is_enabled=True,
    cls=CancelBtn,
)
reset_btn = btns.add(
    'engine|driver',
    Label(
        'Reset',
        x=cfg_action_x(1) + 6, y=cfg_action_y() - btn_h + 4,
        font_name='monospace',
        batch=configuring_what_label_batch,
    ),
    x=cfg_action_x(1), y=cfg_action_y(),
    size=(btn_w, btn_h),
    is_on=False, is_radio=True, is_enabled=True,
    cls=ResetBtn,
)
save_btn = btns.add(
    'engine|driver',
    Label(
        'Save',
        x=cfg_action_x(2) + 6, y=cfg_action_y() - btn_h + 4,
        font_name='monospace',
        batch=configuring_what_label_batch,
    ),
    x=cfg_action_x(2), y=cfg_action_y(),
    size=(btn_w, btn_h),
    is_on=False, is_radio=True, is_enabled=True,
    cls=SaveBtn,
)

configuring_engine = btns.add(
    'engine|driver',
    Label(
        'Jack Engine',
        x=150 + 25, y=welcome_y(),
        font_name='monospace',
        batch=configuring_what_label_batch,
    ),
    x=150, y=welcome_y() + btn_h,
    size=25,
    is_on=True, is_radio='configuring', is_enabled=True,
    value='engine',
)
@configuring_engine.event
def after_press(self):
    navigation.to_engine()

configuring_driver = btns.add(
    'engine|driver',
    Label(
        'ALSA Driver',
        x=300 + 25, y=welcome_y(),
        font_name='monospace',
        batch=configuring_what_label_batch,
    ),
    x=300, y=welcome_y() + btn_h,
    size=25,
    is_on=False, is_radio='configuring', is_enabled=True,
    value='driver',
)
@configuring_driver.event
def after_press(self):
    navigation.to_driver()

# monkeypatch set_active to share some buttons across screens
def patch_set_active(self, screen_name):
    for name, buttons in self._buttons.items():
        for btn in buttons:
            if btn in (save_btn, reset_btn, cancel_btn, configuring_engine, configuring_driver):
                btn.is_active = screen_name in ('engine', 'driver')
                continue
            btn.is_active = name == screen_name
    if screen_name == 'driver':
        update_driver_gui_booleans()  # quick hack
        duplex = cfg_driver_toggles['duplex']['btn']._pressed
        self.set_duplex_side_effect(duplex)
    else:
        self._cls_sin_buttons.populate(self.batch, self.group)
def set_duplex_side_effect(self, on):
    for btns in self._buttons.values():
        for btn in btns:
            if btn.is_radio == 'duplex-device':
                btn.is_active = on
            elif btn.is_radio in ('capture-device', 'playback-device'):
                btn.is_active = not on
    self._cls_sin_buttons.populate(self.batch, self.group)
btns.set_active = partial(patch_set_active, btns)
btns.set_duplex_side_effect = partial(set_duplex_side_effect, btns)

def update_engine_gui_state_clock_selection():
    # we receive 0 1 2 instead of c h s
    # so I did set hpet in cadence and dbus said it's 2
    # cadence is doing some dance and keeps using maps like so
    # system = 0, cycle = 1, hpet = 2
    # also... cycle got removed
    # https://github.com/jackaudio/jack2/commit/6ac255e0778a42926bc7acf30e9ce673af4cc223
    # this means cadence is broken here since 2014
    # cadence keeps using numbers if they already are on dbus
    # but, will jack break if i pass a 's'/'h'? letssee
    # Nope, isn't broken, and cadence disables the selection of clock
    # - jack_timer_type_t is not in jack2 include headers
    # - pyjacklib has no mention of timer ofc

    # we have to choose how to react...
    # - if it's "jack2<1.9.10" we disable clock selection
    # - we use s/h and you won't be able to change that from cadence anymore
    # - 0, 1 and 2 are all normalized to s (to fixup 1 is h instead of c)
    if not clk_btn.modified:
        clock = int(cfg_sin_clock_source_feat['getter']()[2])
        if clock in (0, 1, 2):
            clock_selection = 'broken'
        elif clock in (ord('s'), ord('h')):
            clock_selection = 'new'
        else:
            error_dialog('unknown clock selected')
            raise NotImplementedError('unknown clock selected')

        if clock_selection == 'broken' or clock == ord('s'):
            _clock = ord('s')
        elif clock == ord('h'):
            _clock = ord('h')
        clk_btn.value = _clock
        clk_btn.mark_group_as_not_modified()

def update_engine_gui_self_connect_mode():
    if not scm_btn.modified:
        actual = int(engine_features['self-connect-mode']['getter']()[2])
        scm_btn.value = actual
        scm_btn.mark_group_as_not_modified()

def update_engine_gui_booleans():
    for thing in cfg_engine_toggles.values():
        btn = thing['btn']
        if not btn.modified:
            actual = bool(engine_features[btn.feat_name]['getter']()[2])
            btn.toggle(actual)
            btn.modified = False

def update_engine_gui_integers():
    #return
    for feat_name, thing in cfg_engine_integers.items():
        if not thing['integer_entry'].modified and not thing['integer_entry'].focus:
            thing['integer_entry'].value = str(int(engine_features[feat_name]['getter']()[2]))

def update_engine_gui_state():
    # we poll dbus and update the GUI unless modified
    # modifying doesn't immediatly set the value on dbus
    # that's done through a save button
    # once a value is modified on the gui polling for that one stops
    # until save/reset/cancel is pressed
    update_engine_gui_state_clock_selection()
    update_engine_gui_self_connect_mode()
    update_engine_gui_booleans()
    update_engine_gui_integers()

def update_driver_gui_booleans():
    for thing in cfg_driver_toggles.values():
        btn = thing['btn']
        if not btn.modified:
            actual = bool(driver_features[btn.feat_name]['getter']()[2])
            btn.toggle(actual)
            btn.modified = False

def update_driver_gui_integers():
    for feat_name, thing in cfg_driver_integers.items():
        if not thing['integer_entry'].modified and not thing['integer_entry'].focus:
            thing['integer_entry'].value = str(int(driver_features[feat_name]['getter']()[2]))

def update_driver_gui_dither():
    if not dither_btn.modified:
        actual = int(driver_features['dither']['getter']()[2])
        dither_btn.value = actual
        dither_btn.mark_group_as_not_modified()

def update_driver_gui_midi():
    if not midi_btn.modified:
        actual = str(driver_features['midi-driver']['getter']()[2])
        midi_btn.value = actual
        midi_btn.mark_group_as_not_modified()

def update_driver_gui_devices():
    if cfg_driver_toggles['duplex']['btn']._pressed:
        if not duplex_btn.modified:
            actual = str(driver_features['device']['getter']()[2])
            duplex_btn.value = actual
            duplex_btn.mark_group_as_not_modified()
    else:
        if not capture_btn.modified:
            actual = str(driver_features['capture']['getter']()[2])
            capture_btn.value = actual
            capture_btn.mark_group_as_not_modified()
        if not playback_btn.modified:
            actual = str(driver_features['playback']['getter']()[2])
            playback_btn.value = actual
            playback_btn.mark_group_as_not_modified()

def update_driver_gui_state():
    update_driver_gui_booleans()
    update_driver_gui_integers()
    update_driver_gui_dither()
    update_driver_gui_midi()
    try:
        update_driver_gui_devices()
    except ValueError as exc:
        print(str(exc), file=stderr)

def midid_update():
    if midid.is_started:
        midid_ehw_btn.toggle(a2jmidid.get_hw_export())
        midid_uniq_btn.toggle(not a2jmidid.get_disable_port_uniqueness())
        a2jmidid_export_hw_btn.is_enabled = False
        a2jmidid_uniqueness_btn.is_enabled = False
    else:
        midid_ehw_btn.toggle(False)
        midid_uniq_btn.toggle(False)
        a2jmidid_export_hw_btn.is_enabled = True
        a2jmidid_uniqueness_btn.is_enabled = True

def draw_main():
    window.clear()
    welcome.draw()
    batch_status.draw()
    btns.batch.draw()
    batch_status_btnl.draw()

def draw_configure():
    window.clear()
    configure_text.draw()
    cfg_engine_integers_batch.draw()
    btns.batch.draw()
    cfg_engine_labels.draw()
    configuring_what_label_batch.draw()

def draw_configure_driver():
    window.clear()
    configure_text.draw()
    cfg_driver_integers_batch.draw()
    btns.batch.draw()
    cfg_driver_labels.draw()
    if cfg_driver_toggles['duplex']['btn']._pressed:
        cfg_driver_duplex_labels.draw()
    else:
        cfg_driver_non_duplex_labels.draw()
    configuring_what_label_batch.draw()

@window.event
def on_draw():
    match navigation.name:
        case 'main':
            get_info()
            aloop_started()
            aloop_connected()
            midid_update()
            draw_main()
        case 'engine':
            update_engine_gui_state()
            draw_configure()
        case 'driver':
            update_driver_gui_state()
            draw_configure_driver()
        case _:
            assert False, f'how to draw {navigation.name}?'

def on_dbus_error(msg):
    print(msg, file=stderr)
    error_dialog(msg)
    if 'org.freedesktop.DBus.Error.NoReply' in msg:
        dbus_reconnect()


@window.event
def on_resize(x, y):
    welcome.x = welcome_x()
    welcome.y = welcome_y()
    server_status.y = status_y(0)
    rt_status.y = status_y(1)
    dsp_status.y = status_y(2)
    xruns_status.y = status_y(3)
    buffer_size_status.y = status_y(4)
    sr_status.y = status_y(5)
    bl_status.y = status_y(6)
    server_status_val.y = status_y(0)
    rt_status_val.y = status_y(1)
    dsp_status_val.y = status_y(2)
    xruns_status_val.y = status_y(3)
    buffer_size_status_val.y = status_y(4)
    sr_status_val.y = status_y(5)
    bl_status_val.y = status_y(6)
    start_status_btn.position = status_btn_x(), status_btn_y(0)
    start_status_btn_label.position = status_btnl_x(), status_btnl_y(0), 1
    stop_status_btn.position = status_btn_x(), status_btn_y(1)
    stop_status_btn_label.position = status_btnl_x(), status_btnl_y(1), 1
    force_restart_status_btn.position = status_btn_x(), status_btn_y(2)
    force_restart_status_btn_label.position = status_btnl_x(), status_btnl_y(2), 1
    reset_xruns_status_btn.position = status_btn_x(), status_btn_y(3)
    reset_xruns_status_btn_label.position = status_btnl_x(), status_btnl_y(3), 1
    switch_master_status_btn.position = status_btn_x(), status_btn_y(4)
    switch_master_status_btn_label.position = status_btnl_x(), status_btnl_y(4), 1
    configure_status_btn.position = status_btn_x(), status_btn_y(6)
    configure_status_btn_label.position = status_btnl_x(), status_btnl_y(6), 1

once = True
while once:
    once = False
    try:
        # famerate is also for dbus polling
        #pyglet.app.run(.2)  # why should you redraw this thing @60Hz?
        navigation.to_main()
        pyglet.app.run(.05)  # why should you redraw this thing @60Hz?
        # a redraw each 100ms (10Hz) seems even too fast to me
        # actually changed to 5 times per second.
    except dbus.exceptions.DBusException as exc:
        print(str(exc), file=stderr)
        error_dialog(str(exc), title='Unexpected Error')
        server_status_val.text = 'DEAD'
        once = True
        if 'org.freedesktop.DBus.Error.ServiceUnknown' in str(exc):
            dbus_reconnect()

print("So you closed the window... Well i'm atexit")
print("SIGINT will kill any bridge, that's on you")


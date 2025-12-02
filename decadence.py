# TODO: manage a2j pulse2j etc
import pyglet
from pyglet.window import Window
from pyglet.text import Label
from pyglet.gui import Frame, PushButton, ToggleButton, TextEntry
from pyglet.image import ImageData
from functools import partial
from sys import stderr

import dbus  # dbus-python on PyPi
# gdbus introspect -e -d org.jackaudio.service -o /org/jackaudio/Controller
GDbus = None
d_jack = None
patchbay = None
jackcfg = None
def dbus_reconnect():
    global GDbus, d_jack, patchbay, jackcfg
    GDbus = dbus.bus.BusConnection()
    d_jack = GDbus.get_object(
        "org.jackaudio.service",
        "/org/jackaudio/Controller"
    )
    #patchbay = dbus.Interface(d_jack, "org.jackaudio.JackPatchbay")
    jackcfg = dbus.Interface(d_jack, "org.jackaudio.Configure")
dbus_reconnect()


window = pyglet.window.Window(caption='decadence', width=600, height=400)
# i3wm users: $mod+Shift+space to toggle floating to tiling
#   autostarts with floating, not worth to change that

#wel = pyglet.window.event.WindowEventLogger()
#window.push_handlers(wel)

def error_dialog(msg, title='Error'):
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

btn_w, btn_h = 50, 20
def welcome_x(): return window.width // 2
def welcome_y(): return window.height - 25
def status_y(i): return window.height - 50 - (btn_h + 5) * i
def status_btn_x(): return window.width - 15 - btn_w
def status_btn_y(i): return window.height - 50 - (btn_h + 5) * i
def status_btnl_x(): return window.width - 15 - btn_w + 2
def status_btnl_y(i): return window.height - 50 + 4 - (btn_h + 5) * i
def cfg_title_x(offset=0): return offset + 15
def cfg_title_y(offset=window.height - 50): return offset
def cfg_btn_x(i, offset=0): return offset + 15
def cfg_btn_y(i, offset=window.height - 75): return offset - 20 * i - 2 * i
def cfg_btnl_x(i, offset=0): return offset + 15 + 20 + 2
def cfg_btnl_y(i, offset=window.height - 75): return offset - 20 * i - 2 * i + 4
def cfg_int_x(_): return window.width - 15 - 50
def cfg_int_y(i): return window.height - 50 - 30 * i
def cfg_intl_x(_): return window.width - 15 - 50 - 5
def cfg_intl_y(i): return window.height - 50 - 30 * i - 2 * i + 10
def cfg_action_x(i): return 10 + btn_w * i + 5 * i
def cfg_action_y(): return 10

GREEN = (0x0c, 0xcc, 0x0b, 0xff)
RED = (0xcc, 0x0c, 0x0b, 0xff)
YELL = (0xcc, 0xca, 0x0b, 0xff)


# wants some image to use a button...
from struct import Struct
btn_unpressed_unpacked = []
btn_pressed_unpacked = []
btn_hover_unpacked = []
for _ in range(btn_w*btn_h):
    btn_unpressed_unpacked.extend((0x66, 0x66, 0x66))
    btn_pressed_unpacked.extend((0x33, 0x33, 0x33))
    btn_hover_unpacked.extend((0x44, 0x44, 0x44))
img_btn_unpressed = ImageData(
    width=btn_w, height=btn_h, fmt='RGB',
    data=Struct('BBB'*btn_w*btn_h).pack(*btn_unpressed_unpacked),
)
img_btn_pressed = ImageData(
    width=btn_w, height=btn_h, fmt='RGB',
    data=Struct('BBB'*btn_w*btn_h).pack(*btn_pressed_unpacked),
)
img_btn_hover = ImageData(
    width=btn_w, height=btn_h, fmt='RGB',
    data=Struct('BBB'*btn_w*btn_h).pack(*btn_hover_unpacked),
)
del btn_unpressed_unpacked, btn_pressed_unpacked, btn_hover_unpacked

sinbtn_w, sinbtn_h = 20, 20 # it's a nice solid color
sinbtn_unpressed_unpacked = [*([0x66] * 3), 0xff] * sinbtn_w * sinbtn_h
sinbtn_pressed_unpacked = [*([0x33] * 3), 0xff] * sinbtn_w * sinbtn_h
sinbtn_hover_unpacked = [*([0x44] * 3), 0xff] * sinbtn_w * sinbtn_h
img_sinbtn_unpressed = ImageData(
    width=sinbtn_w, height=sinbtn_h, fmt='RGBA',
    data=Struct('BBBB'*sinbtn_w*sinbtn_h).pack(*sinbtn_unpressed_unpacked),
)
img_sinbtn_pressed = ImageData(
    width=sinbtn_w, height=sinbtn_h, fmt='RGBA',
    data=Struct('BBBB'*sinbtn_w*sinbtn_h).pack(*sinbtn_pressed_unpacked),
)
img_sinbtn_hover = ImageData(
    width=sinbtn_w, height=sinbtn_h, fmt='RGBA',
    data=Struct('BBBB'*sinbtn_w*sinbtn_h).pack(*sinbtn_hover_unpacked),
)


# mhhh, a pyglet bug, https://github.com/pyglet/pyglet/blob/f93b602ea3dde726c6661aa8aaf7400d132f445a/pyglet/gui/widgets.py#L268
#breakpoint()
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

class Navigation:  # just frame (event) handling
    # ooooo, WidgetBase has enabled
    #         and Frame has enable
    class FakeFrame:  # Frame doesn't work with TextEntry
        def __init__(self, window, enable=False):
            self.window = window
            self.widgets = set()
            self._enable = enable
        def add_widget(self, widget):
            self.widgets.add(widget)
            if self._enable:
                for widget in self.widgets:
                    self.window.remove_handlers(widget)
                    self.window.push_handlers(widget)
        @property
        def enable(self):
            return self._enable
        @enable.setter
        def enable(self, enabled):
            self._enable = enabled
            for widget in self.widgets:
                if enabled:
                    self.window.remove_handlers(widget)
                    self.window.push_handlers(widget)
                else:
                    self.window.remove_handlers(widget)
    def __init__(self, window):
        # pyglet.gui.frame.Frame is WIP
        self.main_frame = Frame(window, enable=True)
        self.configure_frame = self.FakeFrame(window, enable=False)
        self.to_main()

    # TODO: pyglet bug: I have to push/pop event handlers, setting enable should do it
    def to_main(self):
        self.name = 'main'
        self.main_frame.enable = True
        window.push_handlers(self.main_frame)
        self.configure_frame.enable = False

    def to_engine(self):
        self.name = 'engine'
        self.main_frame.enable = False
        window.remove_handlers(self.main_frame)
        self.configure_frame.enable = 'engine'

navigation = Navigation(window)

class SinButtons:  # RadioButtonGroup
    def __init__(self, batch):
        self._sin = []
        self.frame = navigation.configure_frame
        self.batch = batch
        self.modified = False
    def __iadd__(self, obj):#btn: ToggleButton, label: Label):
        btn, label, extra = obj
        self._sin.append((btn, label))
        btn.set_handler('on_toggle', self.on_toggle)
        self.frame.add_widget(btn)
        btn.extra=extra
        # btn.batch = self.batch  # unavailable
        # label.batch = self.batch  # kinda works but
        return self
    def on_toggle(self, btn: ToggleButton, value):
        #print('toggle', self, value)
        if value is not None:
            self.modified = True
        for _btn, _ in self._sin:
            _btn._pressed = _btn is btn
            _btn._sprite.image = _btn._pressed_img\
                if _btn._pressed else _btn._unpressed_img
    def draw(self):
        self.batch.draw()
    @property
    def value(self):
        for _btn, _ in self._sin:
            if _btn._pressed:
                return _btn.extra

    def _set_value(self, value):
        for _btn, _ in self._sin:
            if _btn.extra['value'] == value:
                self.on_toggle(_btn, None)
                return


# drawing disorder and order
batch_status = pyglet.graphics.Batch()
GRP0 = pyglet.graphics.Group(0)
GRP1 = pyglet.graphics.Group(1)
GRP2 = pyglet.graphics.Group(2)


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
    batch=batch_status, group=GRP0,
)
server_status_val = Label(
    '---',
    x=status_x2, y=status_y(0),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
rt_status = Label(
    'Realtime:',
    x=status_x, y=status_y(1),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
rt_status_val = Label(
    '---',
    x=status_x2, y=status_y(1),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
dsp_status = Label(
    'DSP Load:',
    x=status_x, y=status_y(2),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
dsp_status_val = Label(
    '---',
    x=status_x2, y=status_y(2),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
xruns_status = Label(
    'Xruns:',
    x=status_x, y=status_y(3),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
xruns_status_val = Label(
    '---',
    x=status_x2, y=status_y(3),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
buffer_size_status = Label(
    'Buffer Size:',
    x=status_x, y=status_y(4),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
buffer_size_status_val = Label(
    '---',
    x=status_x2, y=status_y(4),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
sr_status = Label(
    'Sample Rate:',
    x=status_x, y=status_y(5),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
sr_status_val = Label(
    '---',
    x=status_x2, y=status_y(5),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
bl_status = Label(
    'Block Latency:',
    x=status_x, y=status_y(6),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)
bl_status_val = Label(
    '---',
    x=status_x2, y=status_y(6),
    font_name='monospace', font_size=13,
    batch=batch_status, group=GRP0,
)


start_status_btn = PushButton(
    x=status_btn_x(), y=status_btn_y(0),
    unpressed=img_btn_unpressed,
    pressed=img_btn_pressed,
    hover=img_btn_hover,
    batch=batch_status, group=GRP1,
)
start_status_btn_label = Label(
    'Start',
    x=status_btnl_x(), y=status_btnl_y(0),
    font_name='monospace', font_size=10, color=GREEN,
    batch=batch_status, group=GRP2,
)
stop_status_btn = PushButton(
    x=status_btn_x(), y=status_btn_y(1),
    unpressed=img_btn_unpressed,
    pressed=img_btn_pressed,
    hover=img_btn_hover,
    batch=batch_status, group=GRP1,
)
stop_status_btn_label = Label(
    'Stop',
    x=status_btnl_x(), y=status_btnl_y(1),
    font_name='monospace', font_size=10,
    batch=batch_status, group=GRP2,
)
force_restart_status_btn = PushButton(
    x=status_btn_x(), y=status_btn_y(2),
    unpressed=img_btn_unpressed,
    pressed=img_btn_pressed,
    hover=img_btn_hover,
    batch=batch_status, group=GRP1,
)
force_restart_status_btn_label = Label(
    'Kill',
    x=status_btnl_x(), y=status_btnl_y(2),
    font_name='monospace', font_size=10, color=RED,
    batch=batch_status, group=GRP2,
)
reset_xruns_status_btn = PushButton(
    x=status_btn_x(), y=status_btn_y(3),
    unpressed=img_btn_unpressed,
    pressed=img_btn_pressed,
    hover=img_btn_hover,
    batch=batch_status, group=GRP1,
)
reset_xruns_status_btn_label = Label(
    'X ok',
    x=status_btnl_x(), y=status_btnl_y(3),
    font_name='monospace', font_size=10,
    batch=batch_status, group=GRP2,
)
switch_master_status_btn = PushButton(
    x=status_btn_x(), y=status_btn_y(4),
    unpressed=img_btn_unpressed,
    pressed=img_btn_pressed,
    hover=img_btn_hover,
    batch=batch_status, group=GRP1,
)
switch_master_status_btn_label = Label(
    'S Mast',
    x=status_btnl_x(), y=status_btnl_y(4),
    font_name='monospace', font_size=10,
    batch=batch_status, group=GRP2,
)
configure_status_btn = PushButton(
    x=status_btn_x(), y=status_btn_y(6),
    unpressed=img_btn_unpressed,
    pressed=img_btn_pressed,
    hover=img_btn_hover,
    batch=batch_status, group=GRP1,
)
configure_status_btn_label = Label(
    'Config',
    x=status_btnl_x(), y=status_btnl_y(6),
    font_name='monospace', font_size=10,
    batch=batch_status, group=GRP2,
)

# configure UI elements
configure_text = Label(
    'Configure',
    anchor_x='center', x=welcome_x(), y=welcome_y(),
    font_size=20,
)
checkboxes = ('Realtime', 'Temporary', 'Verbose')
# better to get those strings from dbus
#sin_self_connect = (
#    "Don't restrict self connect requests",
#    "Fail self connect requests to external ports only",
#    "Ignore self connect requests to external ports only",
#    "Fail all self connect requests",
#    "Ignore all self connect requests",
#)

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
    print('starting jack: ', d_jack.StartServer())

dbus_buttons = {
    start_status_btn: (lambda: d_jack.StartServer()),
    stop_status_btn: (lambda: d_jack.StopServer()),
    force_restart_status_btn: force_restart,
    reset_xruns_status_btn: (lambda: d_jack.ResetXruns()),
    switch_master_status_btn: (lambda: d_jack.SwitchMaster()),
}

@start_status_btn.event
@stop_status_btn.event
@force_restart_status_btn.event
@reset_xruns_status_btn.event
@switch_master_status_btn.event
def on_press(widget):
    if action := dbus_buttons.get(widget):
        try:
            action()
        except BaseException as exc:
            error_dialog(str(exc))
    else:
        print(msg := 'UNKNOWN button pressed')
        error_dialog(msg)

@configure_status_btn.event
def on_press(_):
    navigation.to_engine()

navigation.main_frame.add_widget(start_status_btn)
navigation.main_frame.add_widget(stop_status_btn)
navigation.main_frame.add_widget(force_restart_status_btn)
navigation.main_frame.add_widget(reset_xruns_status_btn)
navigation.main_frame.add_widget(switch_master_status_btn)
navigation.main_frame.add_widget(configure_status_btn)

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
cfg_toggles_batch = pyglet.graphics.Batch()
cfg_toggles = {}
i = 0
you_need_to_keep_a_ref_to_labels_somewhere = Label(
    'Engine Booleans:',
    x=cfg_title_x(), y=cfg_title_y(window.height - 120),
    font_name='monospace',
    batch=cfg_toggles_batch,
),
def on_toggle_engine_bool(btn: ToggleButton, value: bool):
    btn.modified = True

relabeling = {
    'sync': 'Server Syncronous Mode',
    'replace-registry': 'Replace Shared Memory Registry',
}
for feat_name, feat in engine_features.items():
    if feat['is_bool']:
        i += 1
        cfg_toggles[feat_name] = {
            'btn': (btn := ToggleButton(
                x=cfg_btn_x(i), y=cfg_btn_y(i, window.height - 120),
                pressed=img_sinbtn_pressed,
                unpressed=img_sinbtn_unpressed,
                hover=img_sinbtn_hover,
                batch=cfg_toggles_batch,
            )),
            'label': Label(
                relabeling.get(feat_name, feat_name.capitalize()),
                x=cfg_btnl_x(i), y=cfg_btnl_y(i, window.height - 120),
                font_name='monospace',
                batch=cfg_toggles_batch,
            ),
        }
        navigation.configure_frame.add_widget(btn)
        btn.modified = False
        btn.feat_name = feat_name
        btn.set_handler('on_toggle', on_toggle_engine_bool)

cfg_sin_clock_source_feat = engine_features['clock-source']
# ... 'Clocksource type : c(ycle) | h(pet) | s(ystem).'
import re
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
cfg_sin_cs_batch = pyglet.graphics.Batch()
cfg_title_cs = Label(
    'Clock Selection:',
    x=cfg_title_x(), y=cfg_title_y(),
    font_name='monospace',
    batch=cfg_sin_cs_batch,
)
cfg_sin_clock_source = SinButtons(cfg_sin_cs_batch)
for i, v in enumerate(cfg_sin_clock_source_cfg.items()):
    txt, val = v
    cfg_sin_clock_source += (
        ToggleButton(
            x=cfg_btn_x(i), y=cfg_btn_y(i),
            pressed=img_sinbtn_pressed,
            unpressed=img_sinbtn_unpressed,
            hover=img_sinbtn_hover,
            batch=cfg_sin_cs_batch,
        ),
        Label(
            txt,
            x=cfg_btnl_x(i), y=cfg_btnl_y(i),
            font_name='monospace',
            batch=cfg_sin_cs_batch,
        ),
        {'value': val},
    )

cfg_sin_scm_batch = pyglet.graphics.Batch()
cfg_sin_self_connect_mode = SinButtons(cfg_sin_scm_batch)
cfg_title_scm = Label(
    'Self Connect Mode:',
    x=cfg_title_x(), y=cfg_title_y(window.height - 260),
    font_name='monospace',
    batch=cfg_sin_scm_batch,
)
self_connect_modes = engine_features['self-connect-mode']['constraints'].items()
for i, kv in enumerate(self_connect_modes):
    text, val = kv
    if text in ('is_range', 'is_strict', 'is_fake_value'):
        break  # break altogeter then, they're at the end
    cfg_sin_self_connect_mode += (
        ToggleButton(
            x=cfg_btn_x(i), y=cfg_btn_y(i, window.height - 280),
            pressed=img_sinbtn_pressed,
            unpressed=img_sinbtn_unpressed,
            hover=img_sinbtn_hover,
            batch=cfg_sin_scm_batch,
        ),
        Label(
            text,
            x=cfg_btnl_x(i), y=cfg_btnl_y(i, window.height - 280),
            font_name='monospace',
            batch=cfg_sin_scm_batch,
        ),
        {'value': val},
    )

cfg_integers_batch = pyglet.graphics.Batch()
i = 0
cfg_integers = {}
for feat_name, feat in engine_features.items():
    if (feat['is_uint32'] or feat['is_int32']) and feat_name != 'clock-source':
        i += 1
        cfg_integers[feat_name] = {
            'text_entry': (te := TextEntry(
                str(int(feat['getter']()[2])),
                x=cfg_int_x(i), y=cfg_int_y(i),
                width=50,
                color=(0xcc, 0xcc, 0xcc, 0xff),
                text_color=(0x00, 0x00, 0x00, 0xff),
                caret_color=(0x00, 0x00, 0x00, 0xff),
                batch=cfg_integers_batch,
            )),
            'label': Label(
                feat_name.replace('-', ' ').capitalize()
                if feat_name != 'client-timeout'
                else 'Client timeout (ms)',
                x=cfg_intl_x(i), y=cfg_intl_y(i), anchor_x='right',
                font_name='monospace',
                batch=cfg_integers_batch,
            ),
        }
        te.modified = False
        navigation.configure_frame.add_widget(te)

cfg_actions_batch = pyglet.graphics.Batch()
cancel_btn = PushButton(
    x=cfg_action_x(0), y=cfg_action_y(),
    pressed=img_btn_pressed,
    unpressed=img_btn_unpressed,
    hover=img_btn_hover,
    batch=cfg_actions_batch, group=GRP0,
)
cancel_btn._label = Label(
    'Back',
    x=cfg_action_x(0) + 2, y=cfg_action_y() + 4,
    font_name='monospace',
    batch=cfg_actions_batch, group=GRP1,
)
navigation.configure_frame.add_widget(cancel_btn)
reset_btn = PushButton(
    x=cfg_action_x(1), y=cfg_action_y(),
    pressed=img_btn_pressed,
    unpressed=img_btn_unpressed,
    hover=img_btn_hover,
    batch=cfg_actions_batch, group=GRP0,
)
reset_btn._label = Label(
    'Reset',
    x=cfg_action_x(1) + 2, y=cfg_action_y() + 4,
    font_name='monospace',
    batch=cfg_actions_batch, group=GRP1,
)
navigation.configure_frame.add_widget(reset_btn)
save_btn = PushButton(
    x=cfg_action_x(2), y=cfg_action_y(),
    pressed=img_btn_pressed,
    unpressed=img_btn_unpressed,
    hover=img_btn_hover,
    batch=cfg_actions_batch, group=GRP0,
)
save_btn._label = Label(
    'Save',
    x=cfg_action_x(2) + 2, y=cfg_action_y() + 4,
    font_name='monospace',
    batch=cfg_actions_batch, group=GRP1,
)
navigation.configure_frame.add_widget(save_btn)

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
    if not cfg_sin_clock_source.modified:
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
        cfg_sin_clock_source._set_value(_clock)

def update_engine_gui_self_connect_mode():
    if not cfg_sin_self_connect_mode.modified:
        actual = int(engine_features['self-connect-mode']['getter']()[2])
        cfg_sin_self_connect_mode._set_value(actual)

def update_engine_gui_booleans():
    for thing in cfg_toggles.values():
        btn = thing['btn']
        if not btn.modified:
            actual = bool(engine_features[btn.feat_name]['getter']()[2])
            btn._pressed = actual
            btn._sprite.image = btn._pressed_img if actual else btn._unpressed_img

def update_engine_gui_integers():
    #return
    for feat_name, thing in cfg_integers.items():
        if not thing['text_entry'].modified and not thing['text_entry'].focus:
            thing['text_entry'].value = str(int(engine_features[feat_name]['getter']()[2]))

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

def draw():
    window.clear()
    welcome.draw()
    batch_status.draw()

def draw_configure():
    window.clear()
    configure_text.draw()
    cfg_sin_clock_source.draw()
    cfg_toggles_batch.draw()
    cfg_sin_self_connect_mode.draw()
    cfg_integers_batch.draw()
    cfg_actions_batch.draw()

@window.event
def on_draw():
    match navigation.name:
        case 'main':
            get_info()
            draw()
        case 'engine':
            update_engine_gui_state()
            draw_configure()

def on_dbus_error(msg):
    print(msg, file=stderr)
    error_dialog(msg)
    if 'org.freedesktop.DBus.Error.NoReply' in msg:
        dbus_reconnect()

@cancel_btn.event
def on_press(btn, *args):
    navigation.to_main()
@reset_btn.event
def on_press(btn, *args):
    engine_features['clock-source']['retter']()
    engine_features['self-connect-mode']['retter']()
    for feat_name, thing in cfg_toggles.items():
        engine_features[feat_name]['retter']()
    # TODO: forget about all the .modified on reset
    navigation.to_main()
@save_btn.event
def on_press(btn, *args):
    if cfg_sin_clock_source.modified:
        try:
            engine_features['clock-source']['setter'](
                dbus.UInt32(cfg_sin_clock_source.value['value'])
            )
            cfg_sin_clock_source.modified = False
        except dbus.exceptions.DBusException as exc:
            msg = f'Error setting up engine parameter "clock-source"\n{exc}'
            on_error(msg)
    for feat_name, thing in cfg_toggles.items():
        btn = thing['btn']
        if btn.modified:
            print(f'set engine.{feat_name}: {btn._pressed}')
            engine_features[feat_name]['setter'](dbus.Boolean(btn._pressed))
    if cfg_sin_self_connect_mode.modified:
        #print(type(cfg_sin_self_connect_mode.value['value']))
        engine_features['self-connect-mode']['setter'](
            cfg_sin_self_connect_mode.value['value']
        )
        cfg_sin_self_connect_mode.modified = False
    navigation.to_main()

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
    start_status_btn.x = status_btn_x()
    start_status_btn.y = status_btn_y(0)
    start_status_btn_label.x = status_btnl_x()
    start_status_btn_label.y = status_btnl_y(0)
    stop_status_btn.x = status_btn_x()
    stop_status_btn.y = status_btn_y(1)
    stop_status_btn_label.x = status_btnl_x()
    stop_status_btn_label.y = status_btnl_y(1)
    force_restart_status_btn.x = status_btn_x()
    force_restart_status_btn.y = status_btn_y(2)
    force_restart_status_btn_label.x = status_btnl_x()
    force_restart_status_btn_label.y = status_btnl_y(2)
    reset_xruns_status_btn.x = status_btn_x()
    reset_xruns_status_btn.y = status_btn_y(3)
    reset_xruns_status_btn_label.x = status_btnl_x()
    reset_xruns_status_btn_label.y = status_btnl_y(3)
    switch_master_status_btn.x = status_btn_x()
    switch_master_status_btn.y = status_btn_y(4)
    switch_master_status_btn_label.x = status_btnl_x()
    switch_master_status_btn_label.y = status_btnl_y(4)
    configure_status_btn.x = status_btn_x()
    configure_status_btn.y = status_btn_y(6)
    configure_status_btn_label.x = status_btnl_x()
    configure_status_btn_label.y = status_btnl_y(6)

once = True
while once:
    once = False
    try:
        # famerate is also for dbus polling
        #pyglet.app.run(.2)  # why should you redraw this thing @60Hz?
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


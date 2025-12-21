import pyglet
from pyglet.window import Window
from pyglet.text import Label
from pyglet.gui import TextEntry
from dbus_next import DBusError, Variant
from functools import partial
from subprocess import check_output, CalledProcessError
from sys import stderr
import asyncio
import re

from glsl_button import SinScreens, SinButton

import dclients
from dclients import (
    main_dbus, features, get_info,
    global_config, write_global_config,
    diw, graph, midid,
    aloop_started, aloop_connected, start_aloop,
    midid_update,
    come_on_start, now_stop_them, force_restart, reset_xruns, switch_mast,
)

asyncio.run_coroutine_threadsafe(
    main_dbus(),
    asyncio.get_event_loop()
)


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
    # error_batch = pyglet.graphics.Batch()
    error_label = Label(
        msg,
        x=0,
        y=w.height - 20,
        width=w.width,
        height=w.height,
        font_name='monospace',
        multiline=True,
        #batch=error_batch,
    )
    print(msg, file=stderr)

    @w.event
    def on_draw():
        w.clear()
        # error_batch.draw()  # batch has vertices but doesn't appear
        # idk why...…                 ^ at least at the first on_draw…
        error_label.draw()

    @w.event
    def on_close():
        global has_error
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
        for feat in cfg_driver_integers.values():
            window.remove_handlers(feat['integer_entry'])

    def to_driver(self):
        global window, btns, cfg_engine_integers
        self.name = 'driver'
        btns.set_active('driver')
        for feat in cfg_engine_integers.values():
            window.remove_handlers(feat['integer_entry'])
        for feat in cfg_driver_integers.values():
            window.push_handlers(feat['integer_entry'])


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
        if configure_status_btn is widget:
            navigation.to_engine()
            return
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(widget.action())
        except DBusError as exc:
            #assert False, 'DEBUG: catch this one locally'
            breakpoint()
        except BaseException as exc:
            error_dialog(str(exc))

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

start_status_btn.action         = come_on_start
stop_status_btn.action          = now_stop_them
force_restart_status_btn.action = force_restart
reset_xruns_status_btn.action   = reset_xruns
switch_master_status_btn.action = switch_mast

# Bridges

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
    #is_on=aloop_started(False),
    is_on=False,
    is_radio=False, is_enabled=False,
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
    is_on=False, is_radio=False, is_enabled=False,
)

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
        if not midid.started:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                diw.a2j_midid.call_set_hw_export(not btn._pressed)
            )
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
        if not midid.started:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                diw.a2j_midid.call_set_disable_port_uniqueness(btn._pressed)
            )
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
    is_on=False, is_radio=False, is_enabled=False,
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
    is_on=False, is_radio=False, is_enabled=False,
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
    is_on=False, is_radio=False, is_enabled=False,
)

# next pulse2jack
cfg_status_p2j_label = Label(
    'Pulse2Jack:',
    x=15, y=status_btn_y(11) - 15,
    font_name='monospace',
    batch=batch_status_btnl,
)
p2j_autostart_btn = btns.add(
    'main',
    Label(
        'On Start',
        x=145, y=status_btn_y(11) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    ),
    size=20,
    x=125, y=status_btn_y(11),
    is_on=True, is_radio=False, is_enabled=False,
)
@p2j_autostart_btn.event
def after_press(btn):
    global_config.set('p2j', 'autostart', 'true' if btn._pressed else 'false')
    write_global_config()
p2j_started_btn = btns.add(
    'main',
    Label(
        'Started',
        x=250, y=status_btn_y(11) - 15,
        font_name='monospace',
        batch=batch_status_btnl,
    ),
    size=20,
    x=230, y=status_btn_y(11),
    is_on=True, is_radio=False, is_enabled=False,
)




# configure UI elements
configure_text = Label(
    'Configure',
    anchor_x='left', x=15, y=welcome_y(),
    font_size=20,
)


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
for feat_name, feat in features['engine'].items():
    if feat.variant == 'b':  # boolean
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

cfg_sin_clock_source_feat = features['engine']['clock-source']
# ... 'Clocksource type : c(ycle) | h(pet) | s(ystem).'
cs_re = re.compile(r'\s*([a-zA-Z])(\([a-zA-z]*\))\s*')

cfg_sin_clock_source_cfg = {
    f'{mg[0]}{mg[1][1:-1]}'
    : ord(mg[0])
    for t in cfg_sin_clock_source_feat.description.split(
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
self_connect_modes = features['engine']['self-connect-mode'].constraints.items()
for i, kv in enumerate(self_connect_modes):
    text, val = kv
    val = val.value
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
for feat_name, feat in features['engine'].items():
    if feat.variant in 'ui' and feat_name != 'clock-source':
        i += 1
        cfg_engine_integers[feat_name] = {
            'integer_entry': IntegerEntry(
                str(feat.value.value),
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
for feat_name, feat in features['driver'].items():
    if feat.variant == 'b':
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
for con_txt, con_byte in features['driver']['dither'].constraints.items():
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
        value=int(con_byte.value),
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
for con_txt, con_str in features['driver']['midi-driver'].constraints.items():
    xo = j * 80 - (0 if j == 0 else 20)
    midi_btn = btns.add(
        'driver',
        Label(
            con_str.value,
            x=cfg_btnl_x(i) + xo, y=cfg_btnl_y(i, window.height - 50) - 20,
            font_name='monospace',
            batch=cfg_driver_labels,
        ),
        x=cfg_btn_x(i) + xo, y=cfg_btn_y(i, window.height - 50) - 20,
        size=20,
        is_on=False, is_radio='midi-driver', is_enabled=True,
        value=con_str.value,
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
for feat_name, feat in features['driver'].items():
    if feat.variant in 'ui':
        i += 1
        cfg_driver_integers[feat_name] = {
            'integer_entry': IntegerEntry(
                str(int(feat.value.value)),
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
    def on_press(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._on_press())
        navigation.to_main()
    async def _on_press(_):
        await features['engine']['clock-source'].reset()
        await features['engine']['self-connect-mode'].reset()
        for feat_name, thing in cfg_engine_toggles.items():
            await features['engine'][feat_name].reset()
            thing['btn'].modified = False
        for feat_name, thing in cfg_engine_integers.items():
            await features['engine'][feat_name].reset()
            thing['integer_entry'].modified = False
        clk_btn.mark_group_as_not_modified()
        scm_btn.mark_group_as_not_modified()
        # ok, driver now
        for feat_name, thing in cfg_driver_toggles.items():
            await features['driver'][feat_name].reset()
            thing['btn'].modified = False
        for feat_name, thing in cfg_driver_integers.items():
            await features['driver'][feat_name].reset()
            thing['integer_entry'].modified = False
        await features['driver']['dither'].reset()
        dither_btn.mark_group_as_not_modified()
        await features['driver']['midi-driver'].reset()
        midi_btn.mark_group_as_not_modified()
        await features['driver']['device'].reset()
        duplex_btn.mark_group_as_not_modified()
        await features['driver']['capture'].reset()
        capture_btn.mark_group_as_not_modified()
        await features['driver']['playback'].reset()
        playback_btn.mark_group_as_not_modified()

class SaveBtn(SinButton):
    def on_press(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._on_press())
        navigation.to_main()
    async def _on_press(_):
        if clk_btn.modified:
            try:
                await features['engine']['clock-source'].set(Variant('i', clk_btn.value))
                clk_btn.mark_group_as_not_modified()
                print(f'set engine.clock-source: {clk_btn.value}')
            except DBusException as exc:
                msg = f'Error setting up engine parameter "clock-source"\n{exc}'
                error_dialog(msg, title='Failed')
        if scm_btn.modified:
            await features['engine']['self-connect-mode'].set(Variant('i', scm_btn.value))
            scm_btn.mark_group_as_not_modified()
            print(f'set engine.self-connect-mode: {scm_btn.value}')
        for feat_name, thing in cfg_engine_toggles.items():
            btn = thing['btn']
            if btn.modified:
                print(f'set engine.{feat_name}: {btn._pressed}')
                await features['engine'][feat_name].set(Variant('b', btn._pressed))
                btn.modified = False
        for feat_name, thing in cfg_engine_integers.items():
            if (te := thing['integer_entry']).modified:
                print(f'set (int) engine.{feat_name}: {te.value}')
                await features['engine'][feat_name].set(Variant('i', int(te.value)))
                te.modified = False
        # ok, driver now
        for feat_name, thing in cfg_driver_toggles.items():
            btn = thing['btn']
            if btn.modified:
                print(f'set driver.{feat_name}: {btn._pressed}')
                await features['driver'][feat_name].set(Variant('b', btn._pressed))
                btn.modified = False
        for feat_name, thing in cfg_driver_integers.items():
            if (te := thing['integer_entry']).modified:
                print(f'set (int) driver.{feat_name}: {te.value}')
                await features['driver'][feat_name].set(Variant('u', int(te.value)))
                te.modified = False
        if dither_btn.modified:
            await features['driver']['dither'].set(Variant('i', dither_btn.value))
            dither_btn.mark_group_as_not_modified()
            print(f'set driver.dither: {dither_btn.value}')
        if midi_btn.modified:
            await features['driver']['midi-driver'].set(Variant('i', midi_btn.value))
            midi_btn.mark_group_as_not_modified()
            print(f'set driver.midi-driver: {midi_btn.value}')
        if duplex_btn.modified:
            await features['driver']['device'].set(Variant('s', duplex_btn.value))
            duplex_btn.mark_group_as_not_modified()
            print(f'set driver.device: {duplex_btn.value}')
        if capture_btn.modified:
            await features['driver']['capture'].set(Variant('s', capture_btn.value))
            capture_btn.mark_group_as_not_modified()
            print(f'set driver.capture: {capture_btn.value}')
        if playback_btn.modified:
            await features['driver']['playback'].set(Variant('s', playback_btn.value))
            playback_btn.mark_group_as_not_modified()
            print(f'set driver.playback: {playback_btn.value}')

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
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            update_driver_gui_booleans()  # quick hack
        )
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

async def update_engine_gui_state_clock_selection():
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
        clock = int((await cfg_sin_clock_source_feat.get())[2].value)
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

async def update_engine_gui_self_connect_mode():
    if not scm_btn.modified:
        actual = int((await features['engine']['self-connect-mode'].get())[2].value)
        scm_btn.value = actual
        scm_btn.mark_group_as_not_modified()

async def update_engine_gui_booleans():
    for thing in cfg_engine_toggles.values():
        btn = thing['btn']
        if not btn.modified:
            actual = bool((await features['engine'][btn.feat_name].get())[2].value)
            btn.toggle(actual)
            btn.modified = False

async def update_engine_gui_integers():
    #return
    for feat_name, thing in cfg_engine_integers.items():
        if not thing['integer_entry'].modified and not thing['integer_entry'].focus:
            thing['integer_entry'].value = str(int(
                (await features['engine'][feat_name].get())[2].value
            ))

async def update_engine_gui_state():
    # we poll dbus and update the GUI unless modified
    # modifying doesn't immediatly set the value on dbus
    # that's done through a save button
    # once a value is modified on the gui polling for that one stops
    # until save/reset/cancel is pressed
    await update_engine_gui_state_clock_selection()
    await update_engine_gui_self_connect_mode()
    await update_engine_gui_booleans()
    await update_engine_gui_integers()

async def update_driver_gui_booleans():
    for thing in cfg_driver_toggles.values():
        btn = thing['btn']
        if not btn.modified:
            actual = bool((await features['driver'][btn.feat_name].get())[2].value)
            btn.toggle(actual)
            btn.modified = False

async def update_driver_gui_integers():
    for feat_name, thing in cfg_driver_integers.items():
        if not thing['integer_entry'].modified and not thing['integer_entry'].focus:
            thing['integer_entry'].value = str(int(
                (await features['driver'][feat_name].get())[2].value
            ))

async def update_driver_gui_dither():
    if not dither_btn.modified:
        actual = int((await features['driver']['dither'].get())[2].value)
        dither_btn.value = actual
        dither_btn.mark_group_as_not_modified()

async def update_driver_gui_midi():
    if not midi_btn.modified:
        actual = (await features['driver']['midi-driver'].get())[2].value
        midi_btn.value = actual
        midi_btn.mark_group_as_not_modified()

async def update_driver_gui_devices():
    if cfg_driver_toggles['duplex']['btn']._pressed:
        if not duplex_btn.modified:
            actual = (await features['driver']['device'].get())[2].value
            duplex_btn.value = actual
            duplex_btn.mark_group_as_not_modified()
    else:
        if not capture_btn.modified:
            actual = (await features['driver']['capture'].get())[2].value
            capture_btn.value = actual
            capture_btn.mark_group_as_not_modified()
        if not playback_btn.modified:
            actual = (await features['driver']['playback'].get())[2].value
            playback_btn.value = actual
            playback_btn.mark_group_as_not_modified()

async def update_driver_gui_state():
    await update_driver_gui_booleans()
    await update_driver_gui_integers()
    await update_driver_gui_dither()
    await update_driver_gui_midi()
    try:
        await update_driver_gui_devices()
    except ValueError as exc:
        print(str(exc), file=stderr)


async def update_main():
    match navigation.name:
        case 'main':
            await get_info()
            await aloop_started()
            await aloop_connected()
            await midid_update()
        case 'engine':
            await update_engine_gui_state()
        case 'driver':
            await update_driver_gui_state()
        case _:
            assert False, f'how to update {navigation.name}?'


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
            draw_main()
        case 'engine':
            draw_configure()
        case 'driver':
            draw_configure_driver()
        case _:
            assert False, f'how to draw {navigation.name}?'


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

# monkepatch gui to solve circular dependency
dclients.gui = type('GUI', tuple(), {
    'error_dialog': error_dialog,
    'midid_started_btn': midid_started_btn,
    'server_status_val': server_status_val,
    'dsp_status_val': dsp_status_val,
    'xruns_status_val': xruns_status_val,
    'buffer_size_status_val': buffer_size_status_val,
    'rt_status_val': rt_status_val,
    'sr_status_val': sr_status_val,
    'bl_status_val': bl_status_val,
    #
    'aloop_started_btn': aloop_started_btn,
    'aloop_connected_btn': aloop_connected_btn,
    'midid_ehw_btn': midid_ehw_btn,
    'midid_uniq_btn': midid_uniq_btn,
    'a2jmidid_export_hw_btn': a2jmidid_export_hw_btn,
    'a2jmidid_uniqueness_btn': a2jmidid_uniqueness_btn,
})

async def initialize_midid():
    midid.started = await diw.a2j_midid.call_is_started()
asyncio.get_event_loop().run_until_complete(initialize_midid())

def update_loop(dt):
    #asyncio.run_coroutine_threadsafe(
    #    update_main(),
    #    asyncio.get_event_loop()
    #)
    asyncio.get_event_loop().run_until_complete(update_main())

navigation.to_main()
pyglet.clock.schedule_interval(update_loop, 1)
pyglet.app.run(.05)  # why should you redraw this thing @60Hz?

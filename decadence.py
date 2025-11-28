# TODO: a2j
import pyglet
from pyglet.window import Window
from pyglet.text import Label
from pyglet.gui import PushButton
from pyglet.image import ImageData

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
    patchbay = dbus.Interface(d_jack, "org.jackaudio.JackPatchbay")
    jackcfg = dbus.Interface(d_jack, "org.jackaudio.Configure")
dbus_reconnect()


window = pyglet.window.Window(caption='decadence', width=400, height=400)
# i3wm users: $mod+Shift+space to toggle floating to tiling
#   autostarts with floating, not worth to change that

def error_dialog(msg):
    w = Window(
        caption='Error',
        style=Window.WINDOW_STYLE_DIALOG,
        width=800,
        height=200,
    )
    b = pyglet.graphics.Batch()
    @w.event
    def on_draw():
        w.clear()
        labels = []
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
    width=btn_w,
    height=btn_h,
    fmt='RGB',
    data=Struct('BBB'*btn_w*btn_h).pack(*btn_unpressed_unpacked),
)
img_btn_pressed = ImageData(
    width=btn_w,
    height=btn_h,
    fmt='RGB',
    data=Struct('BBB'*btn_w*btn_h).pack(*btn_pressed_unpacked),
)
img_btn_hover = ImageData(
    width=btn_w,
    height=btn_h,
    fmt='RGB',
    data=Struct('BBB'*btn_w*btn_h).pack(*btn_hover_unpacked),
)
del btn_unpressed_unpacked, btn_pressed_unpacked, btn_hover_unpacked
# also need checkbox and radio buttons
# but there should be a way to generate them using opengl instead...
'''
cbox_w, cbox_h = 20, 20
btn_checkbox_unpressed_unpacked = []
btn_checkbox_pressed_unpacked = []
btn_checkboxhover_unpacked = []
for x in range(cbox_w):
    for y in range(cbox_h):
        btn_checkbox_unpressed_unpacked.extend((0x66, 0x66, 0x66))
        btn_checkbox_pressed_unpacked.extend((0x33, 0x33, 0x33))
        btn_checkbox_hover_unpacked.extend((0x44, 0x44, 0x44))
'''


# app state
is_configuring = False

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
    font_name='monospace', font_size=10,
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
    font_name='monospace', font_size=10,
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
#radio_self_connect = (
#    "Don't restrict self connect requests",
#    "Fail self connect requests to external ports only",
#    "Ignore self connect requests to external ports only",
#    "Fail all self connect requests",
#    "Ignore all self connect requests",
#)
def open_configure(_):
    global is_configuring
    is_configuring = 'engine'
    print('is configuring now...')

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
def btn_released(widget):
    if action := dbus_buttons.get(widget):
        try:
            action()
        except BaseException as exc:
            error_dialog(str(exc))
    else:
        print(msg := 'UNKNOWN button released')
        error_dialog(msg)

start_status_btn.set_handler('on_release', btn_released)
stop_status_btn.set_handler('on_release', btn_released)
force_restart_status_btn.set_handler('on_release', btn_released)
reset_xruns_status_btn.set_handler('on_release', btn_released)
switch_master_status_btn.set_handler('on_release', btn_released)
configure_status_btn.set_handler('on_release', open_configure)
window.push_handlers(start_status_btn)
window.push_handlers(stop_status_btn)
window.push_handlers(force_restart_status_btn)
window.push_handlers(reset_xruns_status_btn)
window.push_handlers(switch_master_status_btn)
window.push_handlers(configure_status_btn)


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
            'getter': lambda: jackcfg.GetParameterValue([w, s]),
            'setter': lambda v: jackcfg.SetParameterValue([w, s], v),
            'retter': lambda: jackcfg.ResetParameterValue([w, s]),
        })
        and o['constraints'].update({'is_range': bool(consts[0])}) or True
        and o['constraints'].update({'is_strict': bool(consts[1])}) or True
        and o['constraints'].update({'is_fake_value': bool(consts[2])})
        or o
        for s in jackcfg.ReadContainer([w])[1]
    }
engine_features = outline_config('engine')
#for k, v in engine_features.items():
#    if v['constraints']['is_strict']:
#        print(f'engine.{k}: {v["constraints"]}')
driver_features = outline_config('driver')
#for k, v in driver_features.items():
#    if v['constraints']['is_strict']:
#        print(f'driver.{k}: {v["constraints"]}')



def draw():
    get_info()
    window.clear()
    welcome.draw()
    batch_status.draw()

def draw_configure():
    window.clear()
    configure_text.draw()

@window.event
def on_draw():
    if is_configuring:
        draw_configure()
    else:
        draw()

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


pyglet.app.run(.2)  # why should you redraw this thing @60Hz?
# a redraw each 100ms (10Hz) seems even too fast to me
# actually changed to 5 times per second.

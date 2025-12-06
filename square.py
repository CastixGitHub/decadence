
import pyglet
from pyglet.graphics.shader import Shader, ShaderProgram
from pyglet.gui.widgets import WidgetBase

RWidgetBase = WidgetBase
del RWidgetBase.on_key_press
del RWidgetBase.on_key_release
del RWidgetBase.on_mouse_release
del RWidgetBase.on_mouse_drag
del RWidgetBase.on_mouse_scroll
del RWidgetBase.on_mouse_motion
del RWidgetBase.on_text
del RWidgetBase.on_text_motion
del RWidgetBase.on_text_motion_select

class SinButton(RWidgetBase):
    def __init__(
        self,
        buttons: 'SinButtons',
        label: 'Label',
        x: float,
        y: float,
        size: float = 25.,
        is_on: bool = False,
        radio_group: 'str | False' = False,
        is_enabled: bool = True,
        value: 'Any' = None,
    ):
        self.buttons = buttons
        self.label = label
        self._x, self._y = x, y
        self.size = size
        self._width = size
        self._height = size
        self.is_on = is_on
        self.is_radio = radio_group
        self.is_enabled = is_enabled
        self.is_active = False  # render nothing by default
        # TODO: hover
        self._value = value
        self.buttons.add(self)
        self.modified = False

    @property
    def others(self):
        assert self.is_radio, 'missing is_radio (grouping)'
        return [btn for btn in self.buttons if btn.is_radio == self.is_radio]

    @property
    def value(self):
        """A Bipolar property...
        Getting/Setting through the property acts as usual on square buttons
        But if it's a radio group
        setting the value toggles the button with that _value
        and getting gets the value of the one in the group active
        To just populate, populate _value instead
        """
        if self.is_radio:
            if self.is_on:
                return self._value
            for btn in self.others:
                if btn.is_on:
                    return btn._value
            return
        return self._value

    @value.setter
    def value(self, new):
        if not self.is_radio:
            self._value = new
            return
        for btn in self.buttons.boxes:
            if (
                btn.is_radio
                and btn.is_radio == self.is_radio
                and btn._value == new
            ):
                btn.toggle(True)
                return

    @property
    def _pressed(self):  # mimic PushButton/ToggleButton
        return self.is_on

    def toggle(self, value: bool = None):
        self.modified = True
        if not self.is_radio:  # buffer size would change
            self.is_on = not self.is_on if value is None else value
            self.buttons.populate()
        else:  # radio btn, edit gpu memory in-place
            # TODO: toggle all the radio in is_radio "group"
            grouped = []
            for btn in self.buttons.boxes:
                if btn.is_radio == self.is_radio and btn.is_active:
                    grouped.append(btn)
            for btn in grouped:
                idx = self.buttons.idx_status(btn)
                assert idx is not None, 'toggling non-existing button'
                self.buttons.on_vertices.is_on[idx] = 0
                btn.is_on = 0
            idx = self.buttons.idx_status(self)
            self.buttons.on_vertices.is_on[idx] = 1
            self.is_on = not self.is_on if value is None else value

    def move(self, x, y):
        self._x, self._y = x, y
        if not self.is_active:
            return
        if not self.is_radio:
            idx_square = self.buttons.idx_square(self)
            assert idx_square, 'no idx found (square)'
            self.buttons.square_vertices.myposition[idx_square].x = x
            self.buttons.square_vertices.myposition[idx_square].y = y
        if self.is_radio or self.is_on:
            idx_status = self.buttons.idx_status(self)
            assert idx_status, 'no idx found (on)'
            self.buttons.on_vertices.myposition[idx_status].x = x
            self.buttons.on_vertices.myposition[idx_status].y = y

    def _update_position(self):
        # doing self.position = (x, y) calls this
        self.move(self._x, self._y)

    def on_press(self):
        assert self.is_active, 'how did u press a non active btn?'
        if self.is_radio:
            self.toggle(True)
        else:
            self.toggle(not self.is_on)
        self.dispatch_event('after_press', self)

SinButton.register_event_type('after_press')


class SinButtons():
    vertex_source = """
#version 330 core
in vec2 myposition;
in float mysize;

uniform WindowBlock
{
    mat4 projection;
    mat4 view;
} window;

out float geosize;

in float is_on;
in float is_radio;
in float is_enabled;
out float geo_on;
out float geo_radio;
out float geo_enabled;

void main()
{
    gl_Position = window.projection * window.view * vec4(myposition, 0.0, 1.0);
    geosize = mysize;
    geo_on = is_on;
    geo_radio = is_radio;
    geo_enabled = is_enabled;
}
    """
    geometry_source = """
#version 330 core
layout (points) in;
layout (line_strip, max_vertices = 5) out;

uniform WindowBlock
{
    mat4 projection;
    mat4 view;
} window;

in float geosize[];
in float geo_enabled[];

out vec3 vertex_color;
out float is_enabled;


void emit_origin(vec3 color) {
    gl_Position = gl_in[0].gl_Position;
    vertex_color = color;
    is_enabled = geo_enabled[0];
    EmitVertex();
}

void emit_offset(float x, float y, vec3 color) {
    gl_Position = gl_in[0].gl_Position
        + window.projection * vec4(x, y, .0, .0);
    vertex_color = color;
    is_enabled = geo_enabled[0];
    EmitVertex();
}

void main() {
    float mysize = geosize[0];
    emit_origin(vec3(1., .0, .0));
    emit_offset(mysize, 0., vec3(.0, 1.0, .0));
    emit_offset(mysize, mysize, vec3(.0, 1.0, .0));
    emit_offset(0., mysize, vec3(.0, .0, 1.0));
    emit_origin(vec3(1., .0, 1.0));
    EndPrimitive();
}
    """
    fragment_source = """
#version 330 core
uniform float time;
in vec3 vertex_color;
in float is_enabled;
void main()
{
    vec3 color = vertex_color;
    if (is_enabled == 0) {
        float n = (color.x + color.y + color.z) / 3;
        color = vec3(n);
    }
    gl_FragColor = vec4(color, 1.0);
}
    """

    geometry_source_on = """
#version 330 core
layout (points) in;
layout (triangle_strip, max_vertices=5) out;

uniform WindowBlock
{
    mat4 projection;
    mat4 view;
} window;

in float geosize[];
float mysize = geosize[0];
float hs = mysize/2;

in float geo_on[];
in float geo_radio[];
in float geo_enabled[];

out vec3 vertex_color;
out vec2 color_mult;
out float is_on;
out float is_radio;
out float is_enabled;

void emit_offset(float x, float y, vec3 color) {
    gl_Position = gl_in[0].gl_Position
        + window.projection * vec4(x - hs, y - hs, .0, .0);
    vertex_color = color;
    float mx = 0;
    float my = 0;
    if (color == vec3(1., 0, 0)) {
        mx = 0;
        my = 0;
    } else if (color == vec3(0., 1, 0)) {
        mx = 1;
        my = y == mysize ? 1 : 0;
    } else if (color == vec3(0., 0, 1)) {
        mx = 0;
        my = 1;
    } else if (color == vec3(1., 0, 1)) {
        mx = 0;
        my = 0;
    }
    color_mult = vec2(mx, my);
    is_on = geo_on[0];
    is_radio = geo_radio[0];
    is_enabled = geo_enabled[0];
    EmitVertex();
}
void main() {
    emit_offset(0., 0., vec3(1., 0., 0.));
    emit_offset(mysize, 0., vec3(0., 1., 0.));
    emit_offset(mysize, mysize, vec3(0., 1., 0.));  // RGG
    emit_offset(0, mysize, vec3(0., 0., 1.));  // GGB
    emit_offset(0, 0, vec3(1., 0., 1.));  // GBM
    EndPrimitive();
}
    """

    fragment_source_on = """
#version 330 core
in vec3 vertex_color;
in vec2 color_mult;
in float is_on;
in float is_radio;
in float is_enabled;
void main()
{
    float n = sin(color_mult[0] * 3.1415);
    n = n * sin(color_mult[1] * 3.1415);
    if (is_on == 1) {
        if (is_radio == 1) {
            if (n <= 0.1 || n <= 0.5 && n >= 0.25)    discard;
        } else {
            if (n <= 0.25)                            discard;
        }
    } else { // off
        if (is_radio == 1) {
            if (n >= .25 || n <= 0.1)                 discard;
        }
        /*else {
            if (n != 0.)                            discard;
        }*/
    }
    vec3 color = vertex_color;
    if (is_enabled == 0) {
        float m = (color.x + color.y + color.z) / 3;
        color = vec3(m);
    }
    gl_FragColor = vec4(color, 1.);
}
    """

    def __init__(self):
        self.program_square = pyglet.gl.current_context.create_program(
            (self.vertex_source, 'vertex'),
            (self.geometry_source, 'geometry'),
            (self.fragment_source, 'fragment'),
        )
        self.program_on = pyglet.gl.current_context.create_program(
            (self.vertex_source, 'vertex'),
            (self.geometry_source_on, 'geometry'),
            (self.fragment_source_on, 'fragment'),
        )
        self.boxes = []
        self.square_vertices = None
        self.on_vertices = None
        self.batch = None
        self.group = None

    def add(self, btn: 'SinButton'):
        self.boxes.append(btn)

    def idx_square(self, btn: 'SinButton'):
        count = 0
        for box in self.boxes:
            if not box.is_active:
                continue
            if box.is_radio:
                continue
            if box is btn:
                return count
            count += 1

    def idx_status(self, btn: 'SinButton'):
        count = 0
        for box in self.boxes:
            if not box.is_active:
                assert box is not btn, 'Reused is_radio name across screens'
                continue
            if box.is_on or box.is_radio:  # on or is_radio
                if box is btn:
                    return count
                count += 1
            elif box is btn:
                return count

    def populate(self, batch=None, group=None):
        if self.square_vertices:
            self.square_vertices.delete()
        if self.on_vertices:
            self.on_vertices.delete()

        if batch is not None:
            self.batch = batch
        else:
            batch = self.batch
        if group is not None:
            self.group = group
        else:
            group = self.group

        count = len(self.boxes)
        coords = ('f', (_coords := []))
        size = ('f', (_size := []))
        is_enabled = ('f', (_is_enabled := []))
        for box in self.boxes:
            if not box.is_active or box.is_radio:  # skip the border
                count -= 1
                continue
            _coords.extend((box.x, box.y))
            _size.append(box.size)
            _is_enabled.append(box.is_enabled)
        self.square_vertices = self.program_square.vertex_list(
            count,
            pyglet.gl.GL_POINTS,
            batch=batch, group=group,
            myposition=coords,
            mysize=size,
            is_enabled=is_enabled,
        )
        count = 0
        coords = ('f', (_coords := []))
        size = ('f', (_size := []))
        is_on = ('f', (_is_on := []))
        is_radio = ('f', (_is_radio := []))
        is_enabled = ('f', (_is_enabled := []))
        for box in self.boxes:
            if not box.is_active:
                continue
            if box.is_on or box.is_radio:  # on or is_radio
                count += 1
                hs = box.size / 2
                _coords.extend((box.x + hs, box.y + hs))
                _size.append(box.size)
                _is_on.append(1 if box.is_on else 0)
                _is_radio.append(1 if box.is_radio else 0)
                _is_enabled.append(box.is_enabled)
        self.on_vertices = self.program_on.vertex_list(
            count,
            pyglet.gl.GL_POINTS,
            batch=batch, group=group,
            myposition=coords,
            mysize=size,
            is_radio=is_radio,
            is_on=is_on,
            is_enabled=is_enabled,
        )


class SinScreens(RWidgetBase):
    _cls_sin_buttons = SinButtons()

    def __init__(self, window, batch=None, group=None):
        self._buttons = {}
        window.push_handlers(self)
        self.window = window
        self.batch = batch or pyglet.graphics.Batch()
        self.group = group

    def add(self, screen_name, *args, cls=SinButton, **kwargs):
        self._buttons.setdefault(screen_name, []).append(
            (ref := cls(self._cls_sin_buttons, *args, **kwargs))
        )
        return ref

    def set_active(self, screen_name):
        # provides exclusivity across screens
        for name, buttons in self._buttons.items():
            for btn in buttons:
                btn.is_active = name == screen_name
        self._cls_sin_buttons.populate(self.batch, self.group)

    def on_mouse_press(self, x, y, buttons, modifiers):
        for btn in self._cls_sin_buttons.boxes:
            if btn._check_hit(x, y) and btn.is_active and btn.is_enabled:
                print('pressing', btn)
                btn.on_press()
                return


if __name__ == '__main__':
    from pyglet.window import Window
    from pyglet.text import Label

    window = pyglet.window.Window(caption='decadence', width=600, height=400)
    #wel = pyglet.window.event.WindowEventLogger()
    #window.push_handlers(wel)

    class Sub(SinButton):
        def on_press(self):
            super().on_press()
            buttons.set_active('other')


    buttons = SinScreens(window)
    #                       x     y     size  is_on  is_radio  is_enabled value
    buttons.add('main', '', 1.0,  1.0,  20.,  False, 'a',      True,     1, cls=Sub)
    buttons.add('main', '', 1.0,  22.0, 20.,  False, False,    True)
    buttons.add('main', '', 25.,  1.0,  20.,  True,  'a',      False,      33)
    buttons.add('main', '', 25.,  22.0, 20.,  True,  False,    True)
    buttons.add('main', '', 50.,  1.0,  25.,  True,  'b',      True)
    buttons.add('main', '', 50.,  30.0, 25.,  True,  'b',      True)
    buttons.add('main', '', 50.,  60.0, 25.,  True,  'b',      True)
    back = buttons.add('other', '', 25., 22.0, 20.,  True,  False,    True)
    buttons.add('other', '', 50., 1.0,  25.,  True,  'c',      True)
    buttons.add('other', '', 50., 30.0, 25.,  True,  'c',      True)
    buttons.add('other', '', 50., 60.0, 25.,  True,  'c',      True)
    buttons.set_active('main')

    @back.event
    def after_press(self):
        print('after press', self)
        buttons.set_active('main')

    @window.event
    def on_draw():
        window.clear()
        buttons.batch.draw()


    #breakpoint()
    pyglet.app.run(.05)

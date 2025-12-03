import pyglet
from pyglet.window import Window
from pyglet.text import Label
from pyglet.graphics.shader import Shader, ShaderProgram

window = pyglet.window.Window(caption='decadence', width=600, height=400)
#wel = pyglet.window.event.WindowEventLogger()
#window.push_handlers(wel)

class SinButtons:
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
void main()
{
    gl_Position = window.projection * window.view * vec4(myposition, 0.0, 1.0);
    geosize = mysize;
}
    """
    geometry_source = """
#version 330 core
layout (points) in;
layout (line_strip, max_vertices = 255) out;

uniform WindowBlock
{
    mat4 projection;
    mat4 view;
} window;

in float geosize[];

out vec2 vertex_color;


void emit_line(float x, float y) {
    gl_Position = gl_in[0].gl_Position
        + window.projection * vec4(0, y, .0, .0);
    vertex_color = vec2(0., y / geosize[0]);
    EmitVertex();
    gl_Position = gl_in[0].gl_Position
        + window.projection * vec4(x, y, .0, .0);
    vertex_color = vec2(1., y/ geosize[0]);
    EmitVertex();
    EndPrimitive();
}

void main() {
    float mysize = geosize[0];
    int isize = int(mysize);
    float hsize = isize / 2;
    for (int line = 0; line < int(isize); line++) {
        emit_line(mysize, line);
    }
}
    """
    fragment_source = """
#version 330 core
uniform float time;
in vec2 vertex_color;
void main()
{
    float n = sin(vertex_color[0]  * 3.1415);
    n = n * sin(vertex_color[1]  * 3.1415);
    if (n <= 0.5) discard;
    gl_FragColor = vec4(vec3(n), 1.0);
}
    """

    def __init__(self):
        self.program = pyglet.gl.current_context.create_program(
            (self.vertex_source, 'vertex'),
            (self.geometry_source, 'geometry'),
            (self.fragment_source, 'fragment'),
        )
        self.boxes = []

    def add(self, x, y, size, on):
        self.boxes.append((x, y, size, on))

    def compile(self, batch):
        count = 0
        coords = ('f', (_coords := []))
        size = ('f', (_size := []))
        for box in self.boxes:
            if box[3]:  # on
                count += 1
                _coords.extend((box[0] + box[2] / 2, box[1] + box[2] / 2))
                _size.extend([box[2]])
        self.on_vertexes = self.program.vertex_list(
            count,
            pyglet.gl.GL_POINTS,
            batch=batch,
            myposition=coords,
            mysize=size,
        )

buttons = SinButtons()
buttons.add(20., 25., 20., False)
buttons.add(50., 50., 20., True)
buttons.add(200., 200., 20., False)
buttons.add(100., 25., 180., True)
buttons.add(200., 0., 60., True)
batch = pyglet.graphics.Batch()
buttons.compile(batch)


@window.event
def on_draw():
    window.clear()
    batch.draw()

pyglet.app.run(.05)

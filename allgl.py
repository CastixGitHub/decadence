
import pyglet
from pyglet.window import Window
from pyglet.text import Label
from pyglet.graphics.shader import Shader, ShaderProgram

window = pyglet.window.Window(caption='decadence', width=600, height=400)
#wel = pyglet.window.event.WindowEventLogger()
#window.push_handlers(wel)

class SquareButton:
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
out vec2 center;
void main()
{
    gl_Position = window.projection * window.view * vec4(myposition, 0.0, 1.0);
    center = gl_Position.xy;
    geosize = mysize;
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

out vec3 vertex_color;


void emit_origin(vec3 color) {
    gl_Position = gl_in[0].gl_Position;
    vertex_color = color;
    EmitVertex();
}

void emit_offset(float x, float y, vec3 color) {
    gl_Position = gl_in[0].gl_Position
        + window.projection * vec4(x, y, .0, .0);
    vertex_color = color;
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
void main()
{
    gl_FragColor = vec4(vertex_color, 1.0);
}
    """

    geometry_source_on = """
#version 330 core
layout (points) in;
layout (triangle_fan, max_vertices=5) out;

uniform WindowBlock
{
    mat4 projection;
    mat4 view;
} window;

in float geosize[];
float mysize = geosize[0] / 2;

out vec3 vertex_color;

void emit_offset(float x, float y, vec3 color) {
    gl_Position = gl_in[0].gl_Position
        + window.projection * vec4(x - mysize/2, y - mysize/2, .0, .0)
    vertex_color = color;
    EmitVertex();
}
void main() {
    emit_offset(0, 0, vec3(0.));  // center fan
    emit_offset(mysize, 0., vec3(0., 1., 0.));
    emit_offset(mysize, mysize, vec3(0., 1., 0.));
    emit_offset(0, mysize, vec3(0., 0., 1.));
    emit_offset(mysize, 0, vec3(0., 1., 0.));
    EndPrimitive();
}
    """

    fragment_source_on = """
#version 330 core

in vec2 center;
in vec3 vertex_color;
void main()
{
    gl_FragColor = vec4(vertex_color, 1.);
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

    def add(self, x, y, size, on):
        self.boxes.append((x, y, size, on))

    def compile(self, batch):
        count = len(self.boxes)
        coords = ('f', (_coords := []))
        size = ('f', (_size := []))
        for box in self.boxes:
            _coords.extend((box[0], box[1]))
            _size.extend([box[2]])
        self.square_vertexes = self.program_square.vertex_list(
            count,
            pyglet.gl.GL_POINTS,
            batch=batch,
            myposition=coords,
            mysize=size,
        )
        count = 0
        coords = ('f', (_coords := []))
        size = ('f', (_size := []))
        for box in self.boxes:
            if box[3]:  # on
                count += 1
                _coords.extend((box[0] + box[2] / 2, box[1] + box[2] / 2))
                _size.extend([box[2]])
        self.on_vertexes = self.program_on.vertex_list(
            count,
            pyglet.gl.GL_POINTS,
            batch=batch,
            myposition=coords,
            mysize=size,
        )

from time import time

square_button = SquareButton()
square_button.add(20., 25., 20., False)
square_button.add(50., 50., 20., True)
square_button.add(200., 200., 20., False)
square_button.add(100., 125., 180., True)
batch = pyglet.graphics.Batch()
square_button.compile(batch)


@window.event
def on_draw():
    window.clear()
    #vertex_list.time = time()
    batch.draw()
    #print(vertex_list.myposition[:])
    #vertex_list.myposition[:] = [*map(lambda x: x + 1, vertex_list.myposition[:])]
    #breakpoint()

pyglet.app.run(.05)

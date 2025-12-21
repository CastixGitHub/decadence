gui = {}

# gdbus introspect -e -d org.jackaudio.service -o /org/jackaudio/Controller
import asyncio
from dbus_next.aio import MessageBus
from dbus_next import DBusError, Message, Variant
from configparser import ConfigParser
from pathlib import Path
from os import access, F_OK, kill as os_kill
from signal import SIGINT
from subprocess import check_output, CalledProcessError

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


class DIW:  # dbus interface wrapper
    __slots__ = (
        'jack_ctrl', 'jack_conf', 'jack_pbay',
        'a2j_bridge', 'a2j_midid',
    )
    def __init__(self):
        for slot in self.__slots__:
            setattr(self, slot, None)


bus = None
diw = DIW()


async def dbus_reconnect():
    global bus
    bus = await MessageBus().connect()
    jack_controller = ('org.jackaudio.service', '/org/jackaudio/Controller')
    introspection = await bus.introspect(*jack_controller)
    jack_proxy = bus.get_proxy_object(*jack_controller, introspection)
    diw.jack_conf = jack_proxy.get_interface('org.jackaudio.Configure')
    diw.jack_ctrl = jack_proxy.get_interface('org.jackaudio.JackControl')
    diw.jack_pbay = jack_proxy.get_interface('org.jackaudio.JackPatchbay')
    a2j_bridging = ("just.bridging.Bridge", "/")
    diw.a2j_bridge = bus.get_proxy_object(
        *a2j_bridging, await bus.introspect(*a2j_bridging)
    ).get_interface("just.bridging.Bridge")
    a2jmidipath = ("org.gna.home.a2jmidid", "/")
    diw.a2j_midid = bus.get_proxy_object(
        *a2jmidipath, await bus.introspect(*a2jmidipath)
    ).get_interface("org.gna.home.a2jmidid.control")

# Signal handlers coroutines

async def ds_server_started():
    graph.server_started = True

async def ds_server_stopped():
    graph.server_started = False

async def ds_a2jmidi_started():
    midid.started = True

async def ds_a2jmidi_stopped():
    midid.started = False

async def ds_a2jbridge_died():
    if gui:
        gui.aloop_started_btn.toggle(False)

# Additional helper coroutines
async def aloop_started():
    if gui:
        clients = await graph.get_clients()
        gui.aloop_started_btn.toggle(
            'alsa_in' in clients
            and 'alsa_out' in clients
        )

async def aloop_connected():
    connections = await graph.get_connections()
    connected = (
        'alsa_in:capture_1' in connections
        and 'alsa_out:playback_1' in connections.get('system:capture_1', [])
    )
    if gui:
        gui.aloop_connected_btn.toggle(connected)
    return connected


async def midid_enforce_config():
    await diw.a2j_midid.call_set_disable_port_uniqueness(
        not global_config.getboolean('a2jmidid', 'port_uniqueness')
    )
    await diw.a2j_midid.call_set_hw_export(
        global_config.getboolean('a2jmidid', 'export_hw')
    )

async def a2jmidid_start(self):
    if not midid.started:
        await midid.enforce_config()
        await diw.a2j_midid.call_start()
    return self.started

async def a2jmidid_stop(self):
    if midid.started:
        await diw.a2j_midid.stop()
    return not self.started

def attach_signals():
    diw.jack_ctrl.on_server_started(ds_server_started)
    diw.jack_ctrl.on_server_stopped(ds_server_stopped)
    diw.a2j_midid.on_bridge_started(ds_a2jmidi_started)
    diw.a2j_midid.on_bridge_stopped(ds_a2jmidi_stopped)
    diw.a2j_bridge.on_in_died(ds_a2jbridge_died)
    diw.a2j_bridge.on_out_died(ds_a2jbridge_died)


class Graph:  # TODO: also map IDs and handle port renaming
    #                 but we don't need that, so...
    def __init__(self):
        self._version = 0
        self._recursion_oops = 0
        self._graph = None
        self._server_started = False  # signal should update this

    @property
    def server_started(self):
        return self._server_started

    @server_started.setter
    def server_started(self, true_or_msg):
        self._server_started = true_or_msg is True
        if gui:
            gui.server_status_val.text = (
                'Started'
                if true_or_msg is True
                else (true_or_msg if true_or_msg is not False
                      else 'Stopped')
            )

    @property
    async def graph(self):
        empty = [0, {}, {}]
        if not self.server_started or self._recursion_oops:
            return self._graph or empty
        try:
            graph = (await diw.jack_pbay.call_get_graph(self._version))
        except DBusError as exc:
            if 'org.jackaudio.Error.ServerNotRunning' in str(exc):
                return self._graph or empty
            elif 'known graph version' in str(exc):
                #elif 'org.jackaudio.Error.InvalidArgs' in str(exc):
                self._version = 0
                self._recursion_oops += 1
                if self._recursion_oops >= 2:
                    raise
                g = await self.graph
                self._recursion_oops = 0
                return g
            raise
        if graph[0] != self._version:
            self._version = graph[0]
            self._graph = graph
        return self._graph

    async def get_connections(self):
        import types
        _connections = set()
        for connections_a in (await self.graph)[2]:
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

    async def get_clients(self):
        return {
            str(client[1]): int(client[0])
            for client in (await self.graph)[1]
        }

    async def get_client_id(self, client_name):
        return (await self.get_clients()).get(client_name)

    async def kill(self, client_id):
        if client_id:
            try:
                pid = await diw.jack_pbay.call_get_client_pid(client_id)
            except BaseException as exc:
                raise
                assert 'InvalidArgs' in str(exc)
                return
            try:
                os_kill(pid, SIGINT)
                print(f'Killed {pid} with SIGINT')
            except ProcessLookupError: ...



class MIDId:
    def __init__(self):
        self.started = False

    @property
    def started(self):
        return self._started

    @started.setter
    def started(self, val):
        self._started = val
        if gui:
            gui.midid_started_btn.toggle(val)
            task = asyncio.create_task(self.just_started())

    async def just_started(self):
        gui.midid_ehw_btn.toggle(await diw.a2j_midid.call_get_hw_export())
        gui.midid_uniq_btn.toggle(not await diw.a2j_midid.call_get_disable_port_uniqueness())

    async def update(self):
        ...


graph = Graph()
midid = MIDId()


features = {'engine': {}, 'driver': {}}
class JackFeat:
    def __init__(self,
        where,
        setting,
        description,
        is_range,
        is_strict,
        is_fake_value,
        constraints,
    ):
        self.where = where
        self.setting = setting
        self.description = description
        self.constraints = constraints
    async def get(self):
        res = await diw.jack_conf.call_get_parameter_value(
            [self.where, self.setting])
        self.value = res[2]
        return res
    async def set(self, value):
        assert isinstance(value, Variant), f'not Variant {type(value)} {value}'
        try:
            await diw.jack_conf.call_set_parameter_value(
                [self.where, self.setting],
                value
            )
        except DBusError as exc:
            print(exc)
            breakpoint()
    async def reset(self):
        await diw.jack_conf.call_reset_parameter_value(
            [self.where, self.setting])
async def outline_config(where):
    container = await diw.jack_conf.call_read_container([where])
    for setting in container[1]:
        description = (await diw.jack_conf
            .call_get_parameter_info([where, setting]))[2]
        constraints = await diw.jack_conf\
            .call_get_parameter_constraint([where, setting])
        features[where][setting] = (feat := JackFeat(
            where,
            setting,
            description=description,
            is_range=constraints[0],
            is_strict=constraints[1],
            is_fake_value=constraints[2],
            constraints={str(con[1]): con[0] for con in constraints[3]},
        ))
        _is_set, default, value = await feat.get()
        # feat.is_set = is_set  # never used, bools use value
        feat.default = default.value
        feat.variant = default.signature
        feat.value = value

async def initialize_graph():
    graph.server_started = await diw.jack_ctrl.call_is_started()

# Hey I'm doing stuff here
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
asyncio.get_event_loop().run_until_complete(dbus_reconnect())
asyncio.get_event_loop().run_until_complete(outline_config('engine'))
asyncio.get_event_loop().run_until_complete(outline_config('driver'))
asyncio.get_event_loop().run_until_complete(initialize_graph())

async def main_dbus():
    attach_signals()
    await bus.wait_for_disconnect()


async def get_info():  # through dbus
    try:
        graph.server_started = await diw.jack_ctrl.call_is_started()
        if graph.server_started:
            gui.dsp_status_val.text = f'{await diw.jack_ctrl.call_get_load():.2f}%'
            gui.xruns_status_val.text = f'{await diw.jack_ctrl.call_get_xruns():d}'
            gui.buffer_size_status_val.text = f'{await diw.jack_ctrl.call_get_buffer_size():d} samples'
            gui.rt_status_val.text = 'Yes' if await diw.jack_ctrl.call_is_realtime() else 'No'
            gui.sr_status_val.text = f'{await diw.jack_ctrl.call_get_sample_rate():d} Hz'
            gui.bl_status_val.text = f'{await diw.jack_ctrl.call_get_latency():.2f} ms'
    except DBusError as exc:
        error_dialog(str(exc))


# Now Actions triggered from the user

async def start_aloop():
    SR = await diw.jack_ctrl.call_get_sample_rate()
    PS = await diw.jack_ctrl.call_get_buffer_size()
    CH = global_config.getint("a2j_bridge", "channels")
    await diw.a2j_bridge.call_configure(SR, PS, CH)
    try:
        await diw.a2j_bridge.call_start_in()
    except DBusError as exc:
        breakpoint()
    await diw.a2j_bridge.call_start_out()
    if gui:
        gui.aloop_started_btn.toggle(True)

def check_kernel_SND_ALOOP():
    try:
        if check_output(['grep', '-l', '-e', "snd_aloop", '/proc/kallsyms']):
            return True # module loaded
    except CalledProcessError:
        ...
    gui.error_dialog(
        'You need to check SND_ALOOP kernel config.\n'
        "Try `modprobe snd_aloop` if that's a module\n"
        "https://wiki.gentoo.org/wiki/JACK#ALSA explains\n\n"
        'mkdir -p /etc/modules-load.d && echo "snd-aloop" > /etc/modules-load.d/alsa.conf',
        title='SND_ALOOP',
    )
    #      modprobe snd-aloop
    #      alsa_in -d cloop 44100 -p 1024 -j alsa2jack -q 1 -c 2
    #      alsa_out -d ploop 44100 -p 1024 -j jack2alsa -q 1 -c 2
    return False

async def aloop_stop():
    await diw.a2j_bridge.call_stop(True, True)
    # but that's not enough ofc
    # well now it is, but doing so anyway
    await graph.kill(await graph.get_client_id('alsa_in'))
    await graph.kill(await graph.get_client_id('alsa_out'))

async def connect_aloop():
    await asyncio.sleep(0.2)  # missing signal from the example...
    complete = True
    for chan in range(1, global_config.getint('a2j_bridge', 'channels') + 1):
        for (cc, cp, pc, pp) in (
            ('alsa_in', f'capture_{chan}',
                'system', f'playback_{chan}'),
            ('system', f'capture_{chan}',
                'alsa_out', f'playback_{chan}'),
        ):
            try:
                await diw.jack_pbay.call_connect_ports_by_name(
                    cc, cp, pc, pp
                )
            except DBusError as exc:
                if 'failed with 17' in str(exc):
                    ...  # already connected
                elif 'cannot find port' in str(exc):
                    ...  # wasn't started?
                    complete = False
                else:
                    raise
    if gui:
        gui.aloop_connected_btn.toggle(complete)


async def midid_update():
    await midid.update()
    if midid.started:
        gui.a2jmidid_export_hw_btn.is_enabled = False
        gui.a2jmidid_uniqueness_btn.is_enabled = False
    else:
        gui.midid_ehw_btn.toggle(False)
        gui.midid_uniq_btn.toggle(False)
        gui.a2jmidid_export_hw_btn.is_enabled = True
        gui.a2jmidid_uniqueness_btn.is_enabled = True


# Such as the main Start button
async def come_on_start():
    try:
        await diw.jack_ctrl.call_start_server()
    except DBusError as exc:
        if 'Failed to open server' in str(exc):
            gui.error_dialog(f'{exc}\n\nRetry (if just stopped/killed) or check Config', title=str(exc))
            return
        raise
    if global_config.getboolean('a2j_bridge', 'autostart'):
        if global_config.get('a2j_bridge', 'tool') == 'jack_examples':
            if not await aloop_started():
                if check_kernel_SND_ALOOP():
                    await start_aloop()
            await connect_aloop()
    if global_config.getboolean('a2jmidid', 'autostart')\
        and not midid.started:
        try:
            await diw.a2j_midid.call_start()
        except DBusError as exc:
            gui.error_dialog(str(exc), title='error starting a2jmidid')

async def now_stop_them():
    print('stopping a2j, a2jmidid, jack')
    await aloop_stop()
    try:
        await diw.a2j_midid.call_stop()
    except DBusError as exc:
        ...  # a2j_stop() failed.
    try:
        await diw.jack_ctrl.call_stop_server()
    except DBusError as exc:
        ...

async def force_restart():
    await now_stop_them()
    print('stopped')
    try:
        await diw.a2j_bridge.call_kill()
    except DBusError: ...  # disconnects
    try:
        print('killing jack...')
        # this one isn't introspected
        res = await bus.call(Message(
            destination='org.jackaudio.service',
            path='/org/jackaudio/Controller',
            interface='org.jackaudio.JackControl',
            member='Exit',
        ))
        # res = await diw.jack_ctrl.call_exit()
        print('killing jack: ', res)
        #for _ in range(20):
        #    pyglet.app.event_loop.sleep(0.05)
    except DBusError as exc:
        print('caught', exc)
        assert 'Message recipient disconnected from message bus without replying' in str(exc)
        ...  # tells didn't answer
        ...  # doesn't tell it anymore...
    # so we can reconnect
    # fucc, we can't anymore
    #GDbus.close()
    # should we reconnect then?
    #dbus_reconnect()
    #await come_on_start()

async def reset_xruns():
    await diw.jack_ctrl.call_reset_xruns()
async def switch_mast():
    await diw.jack_ctrl.call_switch_master()

if __name__ == '__main__':  # not meant to run, just test
    asyncio.get_event_loop().run_until_complete(dbus_reconnect())
    asyncio.get_event_loop().run_until_complete(main_dbus())


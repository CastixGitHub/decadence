import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from multiprocessing import Process
from subprocess import check_output


class Bridge(dbus.service.Object):
    def __init__(self, bus, object_path='/'):
        print(path)
        dbus.service.Object.__init__(self, bus, '/')
        self.cloop = None
        self.ploop = None

    @dbus.service.method(dbus_interface='just.bridging.Bridge',
                         in_signature='uuu', out_signature='b')
    def configure(self, samplerate, buffer_size, nchans):
        if self.initialized:
            return False
        if self.cloop or self.ploop:
            return False
        self.initialized = True
        self.SR = samplerate
        self.PS = buffer_size
        self.CH = nchans
        self.cloop = Process(target=self.target_in)
        self.ploop = Process(target=self.target_out)
        return True

    @dbus.service.method(dbus_interface='just.bridging.Bridge',
                         in_signature='', out_signature='b')
    def start_in(self):
        if not self.initialized:
            return False
        if self.cloop and self.cloop.is_alive():
            return False
        cloop.start()
        return True

    @dbus.service.method(dbus_interface='just.bridging.Bridge',
                         in_signature='', out_signature='b')
    def start_out(self):
        if not self.initialized:
            return False
        if self.ploop and self.ploop.is_alive():
            return False
        ploop.start()
        return True
    @dbus.service.method(dbus_interface='just.bridging.Bridge',
                         in_signature='', out_signature='b')
    def start_both(self):
        return self.start_in() and self.start_out()

    @dbus.service.method(dbus_interface='just.bridging.Bridge',
                         in_signature='bb', out_signature='')
    def stop(self, capture, playback):
        if capture and self.cloop:
            self.cloop.terminate()
        if playback and self.ploop:
            self.ploop.terminate()

    @dbus.service.method(dbus_interface='just.bridging.Bridge',
                         in_signature='bb', out_signature='')
    def kill(self, capture, playback):
        global loop
        self.stop()
        loop.quit()
        exit(0)

    @dbus.service.signal(dbus_interface='just.bridging.Bridge',
                         signature='')
    def in_died(self):
        return

    @dbus.service.signal(dbus_interface='just.bridging.Bridge',
                         signature='')
    def out_died(self):
        return

    def target_in(self):
        env = {
            'JACK_SAMPLE_RATE': f'{self.SR:d}',
            'JACK_PERIOD_SIZE': f'{self.PS:d}',
        }
        try:
            check_output([
                '/usr/bin/alsa_in',
                '-d', 'cloop',  # capture loop
                f'{self.SR:d}',
                '-p',
                f'{self.PS:d}',
                "-j", "alsa2jack",
                "-c", f'{self.CH:d}',
            ], env=env)
        except CalledProcessError as exc:
            self.in_died()

    def target_out(SR, PS, CH):
        try:
            check_output([
                '/usr/bin/alsa_out',
                '-d', 'ploop',  # playback loop
                f'{SR:d}',
                '-p',
                f'{PS:d}',
                "-j", "jack2alsa",
                "-c", f'{CH:d}',
            ])
        except CalledProcessError as exc:
            self.out_died()

if __name__ == '__main__':
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    name = dbus.service.BusName('just.bridging.Bridge', bus)
    bridge = Bridge(bus)
    loop = GLib.MainLoop()
    loop.run()

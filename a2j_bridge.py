# no lockfile is held. expecting only one instance of this is running
from dbus_next.aio import MessageBus
from dbus_next.service import (ServiceInterface,
                               method, dbus_property, signal)
import asyncio


# For some reason, methods are global coroutines
async def check_in(self):
    assert self.configured and self.cloop
    checking = 'fast'  # faster crash report, then check slowly
    while checking:
        try:
            await asyncio.wait_for(self.cloop.wait(), timeout=0.02 if checking == 'fast' else 2)
        except TimeoutError:
            print('In Alive')
        checking = True
        if self.cloop.returncode is not None:
            print('InDied')
            self.InDied()
            checking = False

async def check_out(self):
    assert self.configured and self.ploop
    checking = 'fast'  # faster crash report, then check slowly
    while checking:
        try:
            await asyncio.wait_for(self.ploop.wait(), timeout=0.02 if checking == 'fast' else 2)
        except TimeoutError:
            print('Out Alive')
        checking = True
        if self.ploop.returncode is not None:
            print('OutDied')
            self.OutDied()
            checking = False

async def stop_them(self, capture, playback):
    print('stopping', capture, playback, self.cloop, self.ploop)
    if capture and self.cloop:
        self.cloop.kill()
        await self.cloop.wait()
        # assert self.cloop.errorcode is not None
        # well actually the signal puts None, can't assert
    if playback and self.ploop:
        self.ploop.kill()
        await self.ploop.wait()


class Bridge(ServiceInterface):
    def __init__(self):
        super().__init__('just.bridging.Bridge')
        self.cloop = None
        self.ploop = None
        self.configured = False
        self.watchers = [None, None]

    @method()
    def Configure(self, samplerate: 'u', buffer_size: 'u', nchans: 'u') -> 'b':
        if self.configured:
            return False
        if self.cloop or self.ploop:
            return False
        self.SR = samplerate
        self.PS = buffer_size
        self.CH = nchans
        self.configured = True
        return True

    @method()
    async def StartIn(self) -> 'b':
        if not self.configured:
            return False
        if self.cloop:
            return False
        self.cloop = await asyncio.create_subprocess_exec(
            '/usr/bin/alsa_in',
            '-d', 'cloop',  # capture loop
            '-r', f'{self.SR:d}',
            '-p', f'{self.PS:d}',
            "-c", f'{self.CH:d}',
            #"-j", "alsa2jack",
            executable='/usr/bin/alsa_in',
            env={
                'JACK_SAMPLE_RATE': f'{self.SR:d}',
                'JACK_PERIOD_SIZE': f'{self.PS:d}',
            },
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self.watchers[0] = asyncio.create_task(check_in(self))  # like call_soon
        # we keep a ref to tasks to ensure GC keeps them
        return True

    @method()
    async def StartOut(self) -> 'b':
        if not self.configured:
            return False
        if self.ploop:
            return False
        self.ploop = await asyncio.create_subprocess_exec(
            '/usr/bin/alsa_out',
            '-d', 'ploop',  # playback loop
            '-r', f'{self.SR:d}',
            '-p', f'{self.PS:d}',
            "-c", f'{self.CH:d}',
            #"-j", "jack2alsa",
            executable='/usr/bin/alsa_out',
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self.watchers[1] = asyncio.create_task(check_out(self))  # like call_soon
        # we keep a ref to tasks to ensure GC keeps them
        return True

    @method()
    async def Stop(self, capture: 'b', playback: 'b'):
        await asyncio.create_task(stop_them(self, capture, playback))

    @method()
    async def Kill(self):
        await asyncio.create_task(stop_them(self, True, True))
        for watcher in self.watchers:
            if watcher:
                watcher.cancel()
        loop.stop()

    @signal()
    def InDied(self):
        self.cloop = None

    @signal()
    def OutDied(self):
        self.ploop = None


async def main():
    bus = await MessageBus().connect()
    bridge = Bridge()
    bus.export('/', bridge)
    await bus.request_name('just.bridging.Bridge')
    await bus.wait_for_disconnect()

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.get_event_loop().run_until_complete(main())

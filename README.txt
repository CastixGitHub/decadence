Decadence
---------

Dbus Explained (to) Castix About Decentralized Efforts aNd Community Exchange

This ended up to be just a jackdbus frontend gui

History
-------

Gentoo masked cadence...
 What to do?
 remove pyqt5, and try make an alternative using pyglet?
 https://packages.gentoo.org/packages/media-sound/cadence
 Dead upstream, vulernabilities, depends on Qt5, no revdeps. Bugs #752042, #884041, #918096, #948092, #952542. Removal on 2025-12-02.
 Ok got to read those bugs, it's more complicated than it looked like from a community point of view


Ouch, QUOTING from https://github.com/falkTX/ README.md
 """
        Over time Cadence small parts have moved into other projects:

            patchbay canvas code was integrated in Carla, where it received many updates
            Carla's canvas was branched off into RaySession, which uses the same code as base but with its own style (external project, not my own)
            pyjacklib became its own project (external project I am helping maintain)
            qjackcapture from the jack render tool (another external project)
            bigmeter and xycontrollers were added as internal plugins in Carla
            wineasio settings panel

        The only big remaining part to still be split off is the jack2/jackdbus settings tool and then Cadence can really die as a project.
 """

This means this little toy of mine will be the only one? okay...
 Why did I go with pyglet instead of pygobject then? mehhh

I'd like the CV stuff to also work (maybe that's not a thing for pipewire? idk)
also, didn't yet check how the CV have been implemented in jack2 since
https://linuxmusicians.com/viewtopic.php?f=1&t=20701
talks like they were properties through metadata api
but https://github.com/surge-synthesizer/surge/issues/1321 confused me
As I'm thinking also about pipewire,
https://gitlab.freedesktop.org/search?group_id=10138&project_id=4753&repository_ref=master&scope=blobs&search=voltage
There's one mention about CV through metadata
I'm not sure if helvum or some other pipewire-specific supports it
I guess the way to go is carla even on pipewire.
(I need to package carla for gentoo then)

User Guide
----------

When to kill? When as a developer you modified jack, stop/start won't reload your changes

When to Switch Master? I don't know…

When to Reset Xruns? when you want to, helps keeping an eye on your load and latency

Cadence now shows clock sources disabled… That's expected and fine (if that somehow broke something for you, reset from cadence). Cadence clock selection is for jack2<1.9.10 (~2014)

Where is alsa_in / alsa_out ? (Bridging ALSA 2 JACK)
 - install media-sound/jack-example-tools with alsa USE flag
   REPO: https://github.com/jackaudio/jack-example-tools

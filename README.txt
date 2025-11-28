 Gentoo masked cadence...
 What to do?
 remove pyqt5, and try make an alternative using pyglet?
 I'm mostly using the main cadence app and catia

jacklib.py, copied that out, it's ctypes binding to the jack server API

 I'm kinda used to JACK-Client on pypi that is cffi to jackclient

(If you didn't know jacklient.so is shipped with jack2)

The think should also work with pipewire

I'd like the CV stuff to also work (maybe that's not a thing for pipewire? idk)
also, didn't yet check how the CV have been implemented in jack2 since
https://linuxmusicians.com/viewtopic.php?f=1&t=20701
talks like they were properties through metadata api
but https://github.com/surge-synthesizer/surge/issues/1321 confused me

#!/usr/bin/python3

from __future__ import print_function

__version__ = '0.0.1'

import os
import shlex
import subprocess
import sys
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk
from gi.repository import Gtk


def find_file(name):
    if os.path.exists(name):
        return name
    path = os.path.abspath(os.path.dirname(__file__))
    while path != '/':
        p = os.path.join(path, 'share', name)
        if os.path.exists(p):
            return p
        path = os.path.dirname(path)
    raise KeyError(name)


def received(w, drag_context, x, y, data, info, time):
    uris = data.get_uris() + data.get_text().replace("\n", " ").split()
    if not uris:
        return
    cmd = ['youtube-dl', '--'] + uris
    cmd = ' '.join(shlex.quote(x) for x in cmd)
    cmd += ' && exit || { ret=$? ; >&2 echo There were errors.  Hit ENTER or close this window. ; read ; exit $ret ; }'
    command = ['gnome-terminal', '--', 'bash', '-c', cmd]

    def reap(child):
        ret = child.wait()
        if ret != 0:
            print("The GNOME terminal process running youtube-dl terminated with status code %s" % ret, file=sys.stderr)

    p = subprocess.Popen(command)
    t = threading.Thread(target=reap, args=(p,))
    t.setDaemon(True)
    t.start()


def main():
    builder = Gtk.Builder()
    builder.add_from_file(find_file('youtube-dl-helper/youtube-dl-helper.glade'))

    main = builder.get_object('main')
    logo = builder.get_object('logo')
    logo.set_from_file(find_file('pixmaps/youtube-dl-helper.png'))
    label = builder.get_object('vbox')

    for w in [label]:
        w.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        w.drag_dest_add_text_targets()
        w.drag_dest_add_uri_targets()
        w.connect('drag-data-received', received)

    main.connect("destroy", Gtk.main_quit)
    main.show_all()
    Gtk.main()


if __name__ == '__main__':
    main()

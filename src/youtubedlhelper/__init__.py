#!/usr/bin/python3

from __future__ import print_function

__version__ = '0.0.5'

import os
import pickle
import shlex
import subprocess
import sys
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import Gtk


cfgdir = os.path.expanduser("~/.config/youtube-dl-helper")
cfgfile = os.path.join(cfgdir, "config.pickle")


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


def download(uris, destdir):
    cmd = ['youtube-dl', '--'] + uris
    cmd = ' '.join(shlex.quote(x) for x in cmd)
    cmd += ' && exit || { ret=$? ; >&2 echo There were errors.  Hit ENTER or close this window. ; read ; exit $ret ; }'

    if subprocess.call(["which", "gnome-terminal"]) == 0:
        command = ['gnome-terminal', '--', 'bash', '-c', cmd]
    else:
        command = ['konsole', '-e', 'bash', '-c', cmd]

    def reap(child):
        ret = child.wait()
        if ret != 0:
            print("The GNOME terminal process running youtube-dl terminated with status code %s" % ret, file=sys.stderr)

    p = subprocess.Popen(command, cwd=destdir)
    t = threading.Thread(target=reap, args=(p,))
    t.setDaemon(True)
    t.start()
    

def received(fcdb, w, drag_context, x, y, data, info, time):
    destdir = fcdb.get_filename()
    uris = data.get_uris() + data.get_text().replace("\n", " ").split()
    if not uris:
        return
    return download(uris, destdir)


def load_config():
    global cfgfile
    try:
        return pickle.load(open(cfgfile, "rb"))
    except Exception:
        return {}


def save_config(cfg):
    global cfgdir
    global cfgfile
    if not os.path.isdir(cfgdir): os.makedirs(cfgdir)
    pickle.dump(cfg, open(cfgfile, "wb"))


def main():
    cfg = load_config()
    download_dir = cfg.get("download_dir", os.path.expanduser("~"))

    builder = Gtk.Builder()
    builder.add_from_file(find_file('youtube-dl-helper/youtube-dl-helper.glade'))

    main = builder.get_object('main')
    logo = builder.get_object('logo')
    logo.set_from_file(find_file('pixmaps/youtube-dl-helper.png'))
    vbox = builder.get_object('vbox')
    download_dir_fcdb = builder.get_object('download_dir')
    download_dir_fcdb.set_filename(download_dir)

    received_with_fcdb = lambda *a, **kw: received(download_dir_fcdb, *a, **kw)

    for w in [vbox]:
        w.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        w.drag_dest_add_text_targets()
        w.drag_dest_add_uri_targets()
        w.connect('drag-data-received', received_with_fcdb)

    def quit(*unused_a, **unused_kw):
        cfg["download_dir"] = download_dir_fcdb.get_filename()
        if cfg["download_dir"] == os.path.expanduser("~"):
            del cfg["download_dir"]
        save_config(cfg)
        Gtk.main_quit()

    args = sys.argv[1:]
    if args:
        GObject.idle_add(lambda *a, **kw: download(args, download_dir_fcdb.get_filename()))
        GObject.idle_add(quit)

    main.connect("destroy", quit)
    main.show_all()
    Gtk.main()


if __name__ == '__main__':
    main()

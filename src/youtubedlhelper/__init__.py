#!/usr/bin/python3

from __future__ import print_function

__version__ = "0.0.15"

import contextlib
import errno
import os
import pickle
import shlex
import subprocess
import sys
import tempfile
import threading
import time

import gi

gi.require_version("GLib", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import Gtk
from gi.repository import Notify


GLib.threads_init()
Notify.init("youtube-dl-helper")


class Notification(object):
    def __init__(self, link):
        self.link = link
        self.n = None
        try:
            self.n = Notify.Notification.new(
                "Downloading video", "Inspecting %s" % self.link, "youtube-dl-helper"
            )
            self.n.show()
        except GLib.Error:
            pass

    def downloading(self):
        if not self.n:
            return
        try:
            self.n.update(
                "Downloading video", "Downloading %s" % self.link, "youtube-dl-helper"
            )
            self.n.show()
        except GLib.Error:
            pass

    def succeeded(self):
        if not self.n:
            return
        try:
            self.n.update(
                "Video downloaded",
                "%s was successfully downloaded" % self.link,
                "youtube-dl-helper",
            )
            self.n.show()
        except GLib.Error:
            pass

    def error(self, msg=""):
        if not self.n:
            return
        try:
            self.n.update(
                "Error downloading video",
                msg or "Downloading %s failed" % self.link,
                "youtube-dl-helper",
            )
            self.n.set_timeout(Notify.EXPIRES_NEVER)
            self.n.show()
        except GLib.Error:
            pass


cfgdir = os.path.expanduser("~/.config/youtube-dl-helper")
cfgfile = os.path.join(cfgdir, "config.pickle")
download_params = ["--console-title"]


def find_file(name):
    if os.path.exists(name):
        return name
    path = os.path.abspath(os.path.dirname(__file__))
    while path != "/":
        p = os.path.join(path, "share", name)
        if os.path.exists(p):
            return p
        path = os.path.dirname(path)
    raise KeyError(name)


def error_dialog(parent, message):
    print(message, file=sys.stderr)
    m = Gtk.MessageDialog(
        parent,
        Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
        Gtk.MessageType.ERROR,
        Gtk.ButtonsType.CLOSE,
        str(message),
    )
    m.run()
    m.destroy()


def filenames_too_long(filenames):
    too_long = False
    for f in filenames:
        try:
            with open(f + ".part"):
                pass
        except OSError as e:
            if e.errno == errno.ENAMETOOLONG:
                too_long = True
        except Exception:
            pass
    return too_long


def display_in_terminal(pathname):
    cmd = "cat %s ; >&2 echo Hit ENTER or close this window. ; read" % (
        shlex.quote(pathname),
    )
    with open(os.devnull, "w") as f:
        if subprocess.call(["which", "gnome-terminal"], stdout=f, stderr=f) == 0:
            command = ["gnome-terminal", "--", "bash", "-c", cmd]
        else:
            command = ["konsole", "-e", "bash", "-c", cmd]
    p2 = subprocess.Popen(command)
    x = threading.Thread(target=lambda: time.sleep(5) or p2.wait())
    x.setDaemon(True)
    x.start()


@contextlib.contextmanager
def fifocontext():
    tmpdir = tempfile.mkdtemp()
    fifo = os.path.join(tmpdir, "fifo")
    try:
        os.mkfifo(fifo)
    except Exception:
        os.rmdir(tmpdir)
        raise
    try:
        yield fifo
    finally:
        os.unlink(fifo)
        os.rmdir(tmpdir)


class Downloader(GObject.GObject):

    __gsignals__ = {
        "download-succeeded": (GObject.SIGNAL_RUN_FIRST, None, ()),
        "download-failed": (GObject.SIGNAL_RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.program = shutil.which("yt-dlp") or shutil.which("youtube-dl")

    def _threaded_download(self, uris, destdir):
        n = Notification(", ".join(uris))
        if not self.program:
            msg = "Neither yt-dlp nor youtube-dl are installed.\n"
            n.error(msg)
            GLib.idle_add(
                lambda *a: self.emit("download-failed", msg),
                priority=GLib.PRIORITY_HIGH,
            )
            return

        try:
            filenames = subprocess.check_output(
                [self.program, "--get-filename", "--"] + uris,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                cwd=destdir,
            )
            filenames = [s for s in filenames.splitlines() if s]
        except subprocess.CalledProcessError as e:
            msg = f"{self.program} experienced an error.\n\n" + e.stderr
            n.error(msg)
            GLib.idle_add(
                lambda *a: self.emit("download-failed", msg),
                priority=GLib.PRIORITY_HIGH,
            )
            raise

        filename_format = (
            ["-o", "%(id)s.%(ext)s"] if filenames_too_long(filenames) else []
        )

        with fifocontext() as fifo:

            try:
                display_in_terminal(fifo)

            except Exception as eee:
                msg = "Terminal failed to execute.\n\n%s" % eee
                n.error(msg)
                GLib.idle_add(
                    lambda *a: self.emit("download-failed", msg),
                    priority=GLib.PRIORITY_HIGH,
                )
                raise

            try:
                cmd = [self.program] + download_params + filename_format + ["--"] + uris
                with open(fifo, "wb") as fifofd:
                    p = subprocess.Popen(
                        cmd, cwd=destdir, stdout=fifofd, stderr=subprocess.STDOUT
                    )

            except Exception:
                msg = f"{self.program} failed to execute.\n\n{eee}"
                n.error(msg)
                GLib.idle_add(
                    lambda *a: self.emit("download-failed", msg),
                    priority=GLib.PRIORITY_HIGH,
                )
                raise

            n.downloading()
            ret = p.wait()

            if ret != 0:
                msg = "{self.program} failed with return code {ret}."
                n.error(msg)
                GLib.idle_add(
                    lambda *a: self.emit("download-failed", msg,),
                    priority=GLib.PRIORITY_HIGH,
                )
            else:
                n.succeeded()
                GLib.idle_add(
                    lambda *a: self.emit("download-succeeded"),
                    priority=GLib.PRIORITY_HIGH,
                )

    def download(self, uris, destdir):
        t = threading.Thread(target=self._threaded_download, args=(uris, destdir),)
        t.start()


def received(downloader, fcdb, w, drag_context, x, y, data, info, time):
    destdir = fcdb.get_filename()
    uris = data.get_uris() + data.get_text().replace("\n", " ").split()
    if not uris:
        return
    return downloader.download(uris, destdir)


def open_dir(dir_):
    p = subprocess.Popen(["xdg-open", dir_])
    t = threading.Thread(target=reap, args=(p, "xdg-open terminated unexpectedly"))
    t.setDaemon(True)
    t.start()


def load_config():
    global cfgfile
    try:
        return pickle.load(open(cfgfile, "rb"))
    except Exception:
        return {}


def save_config(cfg):
    global cfgdir
    global cfgfile
    if not os.path.isdir(cfgdir):
        os.makedirs(cfgdir)
    pickle.dump(cfg, open(cfgfile, "wb"))


def main():
    cfg = load_config()
    download_dir = cfg.get("download_dir", os.path.expanduser("~"))

    builder = Gtk.Builder()
    builder.add_from_file(find_file("youtube-dl-helper/youtube-dl-helper.glade"))

    main_window = builder.get_object("main_window")
    logo = builder.get_object("logo")

    logo_pixbuf = GdkPixbuf.Pixbuf.new_from_file(
        find_file("pixmaps/youtube-dl-helper.png")
    )
    logo.set_size_request(logo_pixbuf.get_width(), logo_pixbuf.get_height())
    logo_size_requested = [False]

    def draw_scaled_logo(w, cairo_t, size_requested):
        if not logo_size_requested[0]:
            logo.set_size_request(64, 64)
            logo_size_requested[0] = True
        logo_allocation = w.get_allocation()
        size = max([min([logo_allocation.height, logo_allocation.width]), 64])
        logo_pixbuf_scaled = logo_pixbuf.scale_simple(
            size, size, GdkPixbuf.InterpType.BILINEAR
        )
        # Center the image by doing this little bit of math.
        x = (logo_allocation.width / 2) - (size / 2)
        Gdk.cairo_set_source_pixbuf(cairo_t, logo_pixbuf_scaled, x, 0)
        cairo_t.paint()

    logo.connect(
        "draw", lambda w, cairo_t: draw_scaled_logo(w, cairo_t, logo_size_requested)
    )

    vbox = builder.get_object("vbox")
    download_dir_fcdb = builder.get_object("download_dir")
    download_dir_fcdb.set_filename(download_dir)

    global_action_group = Gio.SimpleActionGroup()
    main_window.insert_action_group("global_action_group", global_action_group)

    open_download_dir_action = Gio.SimpleAction.new("open_download_dir", None)
    open_download_dir_action.connect(
        "activate", lambda *a, **kw: open_dir(download_dir_fcdb.get_filename())
    )
    global_action_group.add_action(open_download_dir_action)

    open_download_dir = builder.get_object("open_download_dir")
    open_download_dir.set_action_name("global_action_group.open_download_dir")

    global_accel_group = Gtk.AccelGroup()
    main_window.add_accel_group(global_accel_group)
    open_download_dir.add_accelerator(
        "clicked",
        global_accel_group,
        ord("o"),
        Gdk.ModifierType.CONTROL_MASK,
        Gtk.AccelFlags.VISIBLE,
    )

    downloader = Downloader()
    downloader.connect("download-failed", lambda _, msg: error_dialog(main_window, msg))

    received_with_fcdb = lambda *a, **kw: received(
        downloader, download_dir_fcdb, *a, **kw
    )

    for w in [vbox]:
        w.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        w.drag_dest_add_text_targets()
        w.drag_dest_add_uri_targets()
        w.connect("drag-data-received", received_with_fcdb)

    def quit(*unused_a, **unused_kw):
        cfg["download_dir"] = download_dir_fcdb.get_filename()
        if cfg["download_dir"] == os.path.expanduser("~"):
            del cfg["download_dir"]
        save_config(cfg)
        Gtk.main_quit()

    args = sys.argv[1:]
    if args:
        downloader.download(args, download_dir_fcdb.get_filename())
        downloader.connect("download-failed", lambda *a: [quit(), sys.exit(1)])
        downloader.connect("download-succeeded", quit)

    main_window.connect("destroy", quit)
    main_window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()

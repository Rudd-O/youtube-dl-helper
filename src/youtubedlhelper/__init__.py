#!/usr/bin/python3

from __future__ import print_function

__version__ = "0.0.17"

import errno
import os
import pickle
import shutil
import subprocess
import sys
import threading
import re

import gi

gi.require_version("GLib", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Notify", "0.7")
gi.require_version("Vte", "2.91")

from importlib.resources import files

from gi.repository import GLib  # noqa: E402
from gi.repository import Gio  # noqa: E402
from gi.repository import GObject  # noqa: E402
from gi.repository import Gdk  # noqa: E402
from gi.repository import GdkPixbuf  # noqa: E402
from gi.repository import Gtk  # noqa: E402
from gi.repository import Notify  # noqa: E402
from gi.repository import Vte  # noqa: E402


GLib.threads_init()
Notify.init("youtube-dl-helper")


class Notification(object):
    def __init__(self, link):
        self.link = link
        self.title = None
        self.n = None
        try:
            self.n = Notify.Notification.new(
                "Downloading video",
                "Inspecting %s" % self.link,
                "youtube-dl-helper",
            )
            self.n.show()
        except GLib.Error:
            pass

    def downloading(self, title=None):
        self.title = title or self.link
        if not self.n:
            return
        try:
            self.n.update(
                "Downloading video",
                "Downloading %s" % self.title,
                "youtube-dl-helper",
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
                "%s was successfully downloaded" % self.title,
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
                msg or "Downloading %s failed" % self.title,
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
    return str(files("youtubedlhelper").joinpath(name))


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

        def eval_result(retval):
            if not isinstance(retval, int):
                msg = f"{self.program} did not run: {retval}"
                n.error(msg)
                GLib.idle_add(
                    lambda *a: self.emit(
                        "download-failed",
                        msg,
                    ),
                    priority=GLib.PRIORITY_HIGH,
                )
            elif retval != 0:
                msg = f"{self.program} failed with return code {retval}."
                n.error(msg)
                GLib.idle_add(
                    lambda *a: self.emit(
                        "download-failed",
                        msg,
                    ),
                    priority=GLib.PRIORITY_HIGH,
                )
            else:
                n.succeeded()
                GLib.idle_add(
                    lambda *a: self.emit("download-succeeded"),
                    priority=GLib.PRIORITY_HIGH,
                )

        if len(filenames) == 1:
            title = filenames[0]
        else:
            title = "%s downloads" % len(filenames)
        cmd = [self.program] + download_params + filename_format + ["--"]
        cmd.extend(uris)
        n.downloading(title)
        GLib.idle_add(
            lambda *_: self.spawn_vte(
                title,
                cmd,
                destdir,
                eval_result,
            ),
        )

    def spawn_vte(self, title, cmd, destdir, retval_cb):
        w = Gtk.Window()
        w.set_title(title)

        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
        )

        v = Vte.Terminal()
        box.add(v)

        scrollbar = Gtk.Scrollbar(
            orientation=Gtk.Orientation.VERTICAL,
            adjustment=v.get_vadjustment(),
        )
        box.add(scrollbar)

        hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        progressbar = Gtk.ProgressBar()
        progressbar.set_show_text(True)
        hbox.add(progressbar)
        hbox.add(box)

        w.add(hbox)
        w.show_all()

        pty_flags = Vte.PtyFlags.DEFAULT
        wd = destdir
        env = None
        gspawnflags = GLib.SpawnFlags.DEFAULT
        child_setup = None
        child_setup_data_destroy = None
        timeout = -1
        cancellable = None

        finished = []

        def update_progress(message=None):
            if finished:
                return
            text = v.get_text()[0]
            lns = text.splitlines()

            def qualifies(i):
                if i.startswith("[download]"):
                    return True
                if i.startswith("[Merger]") or i.startswith("merger"):
                    return True

            lns = [i for i in lns if i.strip() and qualifies(i)]
            if lns:
                lastline = lns[-1]
            else:
                lastline = ""
            m = re.match("\\[download] +([0-9.]+)%.*", lastline)
            w = re.match(".*has already been downloaded.*", lastline)
            mrg = re.match("\\[.erger].*", lastline)
            if m:
                percent = float(m.groups(1)[0]) / 100.0
            elif w:
                percent = 1.0
            elif mrg:
                percent = "pulse"
            else:
                percent = "pulse"
            if percent == "pulse":
                progressbar.pulse()
            else:
                progressbar.set_fraction(percent)
            return True

        def child_exited(vte, retval):
            finished.append(True)
            w.set_title(w.get_title() + " (exited)")
            if retval == 0:
                progressbar.set_fraction(1.0)
                progressbar.set_text("Finished")
                vte.set_color_foreground(Gdk.RGBA(0, 0.9, 0, 0))
            else:
                progressbar.set_text(f"Failed with return code {retval}")
                vte.set_color_foreground(Gdk.RGBA(0.9, 0, 0, 0))
            retval_cb(retval)

        def cb(vte, unused_pid, error):
            if error:
                w.set_title(w.get_title() + " (never ran)")
                progressbar.set_text("Could not run")
                vte.set_color_foreground(Gdk.RGBA(0.9, 0, 0, 0))
                retval_cb(error)
                return

            GLib.timeout_add(100, update_progress)
            vte.connect(
                "child-exited",
                child_exited,
            )
            vte.connect(
                "destroy",
                lambda *_: finished.append(True),
            )

        v.spawn_async(
            pty_flags,
            wd,
            cmd,
            env,
            gspawnflags,
            child_setup,
            child_setup_data_destroy,
            timeout,
            cancellable,
            cb,
        )

    def download(self, uris, destdir):
        t = threading.Thread(
            target=self._threaded_download,
            args=(uris, destdir),
        )
        t.start()


def received(
    downloader,
    fcdb,
    w,
    drag_context,
    x,
    y,
    data,
    info,
    unused_time,
):
    destdir = fcdb.get_filename()
    uris = data.get_uris() + data.get_text().replace("\n", " ").split()
    if not uris:
        return
    return downloader.download(uris, destdir)


def open_dir(dir_):
    p = subprocess.Popen(["xdg-open", dir_])
    t = threading.Thread(target=lambda: p.wait())  # FIXME handle error
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
    builder.add_from_file(
        find_file("youtube-dl-helper.glade"),
    )

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
        "draw",
        lambda w, cairo_t: draw_scaled_logo(
            w,
            cairo_t,
            logo_size_requested,
        ),
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
    downloader.connect(
        "download-failed",
        lambda _, msg: error_dialog(main_window, msg),
    )

    def received_with_fcdb(*a, **kw):
        return received(downloader, download_dir_fcdb, *a, **kw)

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
        # downloader.connect("download-failed", lambda *_: print("failed"))
        # downloader.connect("download-succeeded", lambda *_: print("succeeded"))
        downloader.connect("download-failed", lambda *a: [quit(), sys.exit(1)])
        downloader.connect("download-succeeded", quit)

    main_window.connect("destroy", quit)
    main_window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()

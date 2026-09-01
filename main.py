# -*- coding: utf-8 -*-
"""
VidSnap - Android app (Kivy) - English UI
Video downloader for YouTube/Facebook/Instagram/TikTok/Twitter
"""

import os
import sys
import threading
import re
import traceback

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.window import Window

# --- Safe save location that needs no special Android permission ---
try:
    from android.permissions import request_permissions, Permission
    request_permissions([
        Permission.INTERNET,
        Permission.WRITE_EXTERNAL_STORAGE,
        Permission.READ_EXTERNAL_STORAGE,
    ])
    # Use the app's EXTERNAL files dir (visible in a normal file manager
    # under Android/data/<package>/files), not the internal one
    # (app_storage_path) which is truly private and invisible even
    # without root.
    from jnius import autoclass
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    context = PythonActivity.mActivity
    ext_dir = context.getExternalFilesDir(None).getAbsolutePath()
    SAVE_DIR = os.path.join(ext_dir, "VidSnap_Downloads")
except Exception:
    SAVE_DIR = os.path.expanduser("~")

try:
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR, exist_ok=True)
except Exception:
    SAVE_DIR = os.path.expanduser("~")


def log_crash(exc):
    """Writes any unexpected error to a text file inside the app folder,
    so you can find it later with a file manager even without a PC."""
    try:
        crash_path = os.path.join(SAVE_DIR, "last_error.txt")
        with open(crash_path, "w", encoding="utf-8") as f:
            f.write(str(exc) + "\n\n" + traceback.format_exc())
    except Exception:
        pass


def checkpoint(msg):
    """Writes a timestamped progress line to a log file, so even if the
    app gets force-killed mid-download, we can see the last thing that
    happened by opening the file afterward."""
    try:
        import datetime
        log_path = os.path.join(SAVE_DIR, "debug_log.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()}  {msg}\n")
    except Exception:
        pass


# Single combined stream formats (no ffmpeg merge needed -> simpler on Android)
QUALITIES = {
    "144p - smallest": "worst[height<=144][ext=mp4]/worst",
    "360p - normal": "best[height<=360][ext=mp4]/best[height<=360]",
    "480p - medium": "best[height<=480][ext=mp4]/best[height<=480]",
    "720p - HD": "best[height<=720][ext=mp4]/best[height<=720]",
    "1080p - best available": "best[height<=1080][ext=mp4]/best[height<=1080]",
}


class VidSnapUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=20, spacing=12, **kwargs)
        Window.clearcolor = (0.07, 0.07, 0.1, 1)

        self.add_widget(Label(
            text="[b]VidSnap[/b]", markup=True, font_size=30,
            size_hint=(1, 0.12), color=(0.85, 0.4, 1, 1)
        ))

        self.url_input = TextInput(
            hint_text="Paste video link here...",
            multiline=False, size_hint=(1, 0.1), font_size=18
        )
        self.add_widget(self.url_input)

        self.quality_spinner = Spinner(
            text="Select quality",
            values=list(QUALITIES.keys()),
            size_hint=(1, 0.1), font_size=16
        )
        self.add_widget(self.quality_spinner)

        self.download_btn = Button(
            text="Download", size_hint=(1, 0.1), font_size=20,
            background_color=(0.6, 0.2, 0.9, 1)
        )
        self.download_btn.bind(on_press=self.start_download)
        self.add_widget(self.download_btn)

        self.progress = ProgressBar(max=100, value=0, size_hint=(1, 0.05))
        self.add_widget(self.progress)

        self.status_label = Label(
            text=f"Save folder: {SAVE_DIR}",
            size_hint=(1, 0.15), font_size=13, color=(0.7, 0.7, 0.7, 1),
            halign="center"
        )
        self.status_label.bind(size=self._update_status_wrap)
        self.add_widget(self.status_label)

        self.history_label = Label(
            text="Download history will appear here",
            size_hint_y=None, font_size=14, halign="left", valign="top"
        )
        self.history_label.bind(texture_size=self.history_label.setter("size"))
        scroll = ScrollView(size_hint=(1, 0.4))
        scroll.add_widget(self.history_label)
        self.add_widget(scroll)

        self.history = []

    def _update_status_wrap(self, instance, value):
        instance.text_size = (instance.width, None)

    def start_download(self, instance):
        try:
            url = self.url_input.text.strip()
            quality_key = self.quality_spinner.text

            if not url:
                self.status_label.text = "Please paste a link first"
                return
            if quality_key not in QUALITIES:
                self.status_label.text = "Please select a quality first"
                return

            self.download_btn.disabled = True
            self.status_label.text = "Analyzing and downloading..."
            self.progress.value = 0

            thread = threading.Thread(
                target=self.run_download, args=(url, QUALITIES[quality_key])
            )
            thread.daemon = True
            thread.start()
        except Exception as e:
            log_crash(e)
            self.status_label.text = "Unexpected error, check last_error.txt"

    def run_download(self, url, fmt):
        checkpoint("run_download started")
        try:
            import yt_dlp
            import certifi
            checkpoint("yt_dlp and certifi imported OK")
        except Exception as e:
            log_crash(e)
            checkpoint(f"IMPORT FAILED: {e}")
            Clock.schedule_once(lambda dt: self.set_status(f"Library load error: {e}"))
            return

        # Fix: on Android, Python's ssl module sometimes can't find the
        # system CA bundle, causing HTTPS requests to hang indefinitely
        # with no error. Point it at certifi's bundled certificates instead.
        try:
            os.environ["SSL_CERT_FILE"] = certifi.where()
            checkpoint("SSL_CERT_FILE set to " + certifi.where())
        except Exception as e:
            checkpoint(f"SSL_CERT_FILE setup failed: {e}")

        def hook(d):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                pct = int(done / total * 100) if total else 0
                Clock.schedule_once(lambda dt: self.set_progress(pct))
            elif d.get("status") == "finished":
                checkpoint("download hook: finished")
                Clock.schedule_once(lambda dt: self.set_progress(100))

        class QuietLogger:
            """yt-dlp normally writes progress/warnings to stdout/stderr.
            On Android, Kivy replaces those with something that isn't a
            real file object, which breaks yt-dlp's internal .write()
            calls. Giving it this custom logger bypasses that entirely."""
            def debug(self, msg):
                checkpoint(f"[yt-dlp debug] {msg}")

            def warning(self, msg):
                checkpoint(f"[yt-dlp warning] {msg}")

            def error(self, msg):
                checkpoint(f"[yt-dlp error] {msg}")

        opts = {
            "format": fmt,
            "outtmpl": os.path.join(SAVE_DIR, "%(title).60s.%(ext)s"),
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 20,  # fail fast instead of hanging until Android kills the app
            "logger": QuietLogger(),
        }

        try:
            checkpoint(f"extract_info starting for url={url}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                checkpoint("extract_info finished OK")
                title = re.sub(r'[\\/*?:"<>|]', "", info.get("title", "video"))[:60]

            Clock.schedule_once(lambda dt: self.on_success(title))
        except Exception as e:
            log_crash(e)
            checkpoint(f"DOWNLOAD FAILED: {e}")
            Clock.schedule_once(lambda dt: self.set_status(f"Download failed: {e}"))
        finally:
            Clock.schedule_once(lambda dt: setattr(self.download_btn, "disabled", False))

    def set_progress(self, pct):
        self.progress.value = pct
        self.status_label.text = f"Downloading... {pct}%"

    def on_success(self, title):
        self.status_label.text = f"Saved: {title}"
        self.history.insert(0, title)
        self.history_label.text = "\n".join(f"- {t}" for t in self.history)

    def set_status(self, text):
        self.status_label.text = text


class VidSnapApp(App):
    def build(self):
        self.title = "VidSnap"
        return VidSnapUI()


if __name__ == "__main__":
    def _excepthook(exc_type, exc_value, exc_tb):
        """Catches any error we didn't anticipate before it silently
        kills the app, and writes it to a file we can inspect."""
        try:
            log_crash(exc_value)
        except Exception:
            pass
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
    VidSnapApp().run()

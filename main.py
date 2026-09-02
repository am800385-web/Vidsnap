# -*- coding: utf-8 -*-
"""
VidSnap - Android app (Kivy) - English UI
Video downloader for YouTube/Facebook/Instagram/TikTok/Twitter and any
other site yt-dlp supports. Checks real available qualities first,
then downloads the one the user picks.
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
    app gets force-killed mid-operation, we can see the last thing that
    happened by opening the file afterward."""
    try:
        import datetime
        log_path = os.path.join(SAVE_DIR, "debug_log.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()}  {msg}\n")
    except Exception:
        pass


class QuietLogger:
    """yt-dlp normally writes progress/warnings to stdout/stderr. On
    Android, Kivy replaces those with something that isn't a real file
    object, which breaks yt-dlp's internal .write() calls. Giving it
    this custom logger bypasses that entirely."""
    def debug(self, msg):
        checkpoint(f"[yt-dlp debug] {msg}")

    def warning(self, msg):
        checkpoint(f"[yt-dlp warning] {msg}")

    def error(self, msg):
        checkpoint(f"[yt-dlp error] {msg}")


def setup_ssl():
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
        checkpoint("SSL_CERT_FILE set to " + certifi.where())
    except Exception as e:
        checkpoint(f"SSL_CERT_FILE setup failed: {e}")


class VidSnapUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=20, spacing=10, **kwargs)
        Window.clearcolor = (0.07, 0.07, 0.1, 1)

        self.add_widget(Label(
            text="[b]VidSnap[/b]", markup=True, font_size=28,
            size_hint=(1, 0.1), color=(0.85, 0.4, 1, 1)
        ))

        self.url_input = TextInput(
            hint_text="Paste video link here...",
            multiline=False, size_hint=(1, 0.09), font_size=17
        )
        self.add_widget(self.url_input)

        self.check_btn = Button(
            text="1) Check available qualities", size_hint=(1, 0.09), font_size=16,
            background_color=(0.3, 0.3, 0.35, 1)
        )
        self.check_btn.bind(on_press=self.start_check)
        self.add_widget(self.check_btn)

        self.quality_spinner = Spinner(
            text="Check a link first",
            values=[],
            size_hint=(1, 0.09), font_size=15, disabled=True
        )
        self.add_widget(self.quality_spinner)

        self.download_btn = Button(
            text="2) Download", size_hint=(1, 0.09), font_size=18,
            background_color=(0.6, 0.2, 0.9, 1), disabled=True
        )
        self.download_btn.bind(on_press=self.start_download)
        self.add_widget(self.download_btn)

        self.progress = ProgressBar(max=100, value=0, size_hint=(1, 0.04))
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
        scroll = ScrollView(size_hint=(1, 0.35))
        scroll.add_widget(self.history_label)
        self.add_widget(scroll)

        self.history = []
        self.format_map = {}   # label -> format_id
        self.last_url = None

    def _update_status_wrap(self, instance, value):
        instance.text_size = (instance.width, None)

    # ---------------- STEP 1: check available qualities ----------------

    def start_check(self, instance):
        try:
            url = self.url_input.text.strip()
            if not url:
                self.status_label.text = "Please paste a link first"
                return

            self.check_btn.disabled = True
            self.download_btn.disabled = True
            self.quality_spinner.disabled = True
            self.quality_spinner.text = "Checking..."
            self.status_label.text = "Reading available qualities..."
            self.progress.value = 0

            thread = threading.Thread(target=self.run_check, args=(url,))
            thread.daemon = True
            thread.start()
        except Exception as e:
            log_crash(e)
            self.status_label.text = "Unexpected error, check last_error.txt"

    def run_check(self, url):
        checkpoint("run_check started")
        try:
            import yt_dlp
        except Exception as e:
            log_crash(e)
            checkpoint(f"IMPORT FAILED: {e}")
            Clock.schedule_once(lambda dt: self.set_status(f"Library load error: {e}"))
            Clock.schedule_once(lambda dt: setattr(self.check_btn, "disabled", False))
            return

        setup_ssl()

        opts = {
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 20,
            "logger": QuietLogger(),
        }

        try:
            checkpoint(f"extract_info (no download) starting for url={url}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            checkpoint("extract_info (no download) finished OK")

            formats = info.get("formats") or []

            # Video options: combined video+audio in a single file only
            # (no ffmpeg on this build, so we can't merge separate streams)
            video_by_height = {}
            for f in formats:
                if f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none"):
                    h = f.get("height") or 0
                    if h and (h not in video_by_height or
                              (f.get("tbr") or 0) > (video_by_height[h].get("tbr") or 0)):
                        video_by_height[h] = f

            # Best audio-only option (original format, e.g. m4a/webm - no mp3
            # conversion since that needs ffmpeg too)
            audio_formats = [
                f for f in formats
                if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")
            ]
            best_audio = None
            if audio_formats:
                best_audio = max(audio_formats, key=lambda f: f.get("abr") or 0)

            format_map = {}
            for h in sorted(video_by_height.keys(), reverse=True):
                f = video_by_height[h]
                ext = f.get("ext", "mp4")
                size = f.get("filesize") or f.get("filesize_approx")
                size_txt = f"~{size / 1024 / 1024:.0f}MB" if size else ""
                label = f"{h}p ({ext}) {size_txt}".strip()
                format_map[label] = f["format_id"]

            if best_audio:
                ext = best_audio.get("ext", "m4a")
                abr = best_audio.get("abr")
                abr_txt = f"{int(abr)}kbps" if abr else ""
                label = f"Audio only ({ext}) {abr_txt}".strip()
                format_map[label] = best_audio["format_id"]

            if not format_map:
                checkpoint("No combined/audio formats found for this URL")
                Clock.schedule_once(lambda dt: self.set_status(
                    "No downloadable single-file quality found for this link"))
                Clock.schedule_once(lambda dt: setattr(self.check_btn, "disabled", False))
                return

            title = info.get("title", "video")
            Clock.schedule_once(lambda dt: self.on_check_success(url, format_map, title))

        except Exception as e:
            log_crash(e)
            checkpoint(f"CHECK FAILED: {e}")
            Clock.schedule_once(lambda dt: self.set_status(f"Check failed: {e}"))
            Clock.schedule_once(lambda dt: setattr(self.check_btn, "disabled", False))

    def on_check_success(self, url, format_map, title):
        self.last_url = url
        self.format_map = format_map
        self.quality_spinner.values = list(format_map.keys())
        self.quality_spinner.text = list(format_map.keys())[0]
        self.quality_spinner.disabled = False
        self.download_btn.disabled = False
        self.check_btn.disabled = False
        self.status_label.text = f"Found: {title}"

    # ---------------- STEP 2: download the chosen quality ----------------

    def start_download(self, instance):
        try:
            if not self.last_url:
                self.status_label.text = "Check a link first"
                return
            label = self.quality_spinner.text
            format_id = self.format_map.get(label)
            if not format_id:
                self.status_label.text = "Please select a quality first"
                return

            self.download_btn.disabled = True
            self.check_btn.disabled = True
            self.status_label.text = "Downloading..."
            self.progress.value = 0

            thread = threading.Thread(
                target=self.run_download, args=(self.last_url, format_id)
            )
            thread.daemon = True
            thread.start()
        except Exception as e:
            log_crash(e)
            self.status_label.text = "Unexpected error, check last_error.txt"

    def run_download(self, url, format_id):
        checkpoint("run_download started")
        try:
            import yt_dlp
        except Exception as e:
            log_crash(e)
            checkpoint(f"IMPORT FAILED: {e}")
            Clock.schedule_once(lambda dt: self.set_status(f"Library load error: {e}"))
            Clock.schedule_once(lambda dt: self._reset_buttons())
            return

        setup_ssl()

        def hook(d):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                pct = int(done / total * 100) if total else 0
                Clock.schedule_once(lambda dt: self.set_progress(pct))
            elif d.get("status") == "finished":
                checkpoint("download hook: finished")
                Clock.schedule_once(lambda dt: self.set_progress(100))

        opts = {
            "format": format_id,
            "outtmpl": os.path.join(SAVE_DIR, "%(title).60s.%(ext)s"),
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 20,
            "logger": QuietLogger(),
        }

        try:
            checkpoint(f"download starting for url={url} format={format_id}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                checkpoint("download finished OK")
                title = re.sub(r'[\\/*?:"<>|]', "", info.get("title", "video"))[:60]

            Clock.schedule_once(lambda dt: self.on_success(title))
        except Exception as e:
            log_crash(e)
            checkpoint(f"DOWNLOAD FAILED: {e}")
            Clock.schedule_once(lambda dt: self.set_status(f"Download failed: {e}"))
        finally:
            Clock.schedule_once(lambda dt: self._reset_buttons())

    def _reset_buttons(self):
        self.download_btn.disabled = False
        self.check_btn.disabled = False

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

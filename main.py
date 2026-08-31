# -*- coding: utf-8 -*-
"""
VidSnap - نسخة تطبيق أندرويد (Kivy)
محمّل فيديوهات من يوتيوب/فيسبوك/انستغرام/تيك توك/تويتر
"""

import os
import threading
import re

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

# --- طلب صلاحيات أندرويد (يشتغل بس داخل التطبيق المبني، يتجاهله لو تجرب على PC) ---
try:
    from android.permissions import request_permissions, Permission
    request_permissions([
        Permission.INTERNET,
        Permission.WRITE_EXTERNAL_STORAGE,
        Permission.READ_EXTERNAL_STORAGE,
    ])
    from android.storage import primary_external_storage_path
    SAVE_DIR = os.path.join(primary_external_storage_path(), "Download")
except Exception:
    SAVE_DIR = os.path.expanduser("~")

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR, exist_ok=True)

# صيغ بدون الحاجة لـ ffmpeg (بث واحد مدموج مسبقًا) عشان يشتغل على أندرويد بدون تعقيد
QUALITIES = {
    "144p - أصغر حجم": "worst[height<=144][ext=mp4]/worst",
    "360p - عادية": "best[height<=360][ext=mp4]/best[height<=360]",
    "480p - متوسطة": "best[height<=480][ext=mp4]/best[height<=480]",
    "720p - HD": "best[height<=720][ext=mp4]/best[height<=720]",
    "1080p - أفضل جودة متاحة": "best[height<=1080][ext=mp4]/best[height<=1080]",
}


class VidSnapUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=20, spacing=12, **kwargs)
        Window.clearcolor = (0.07, 0.07, 0.1, 1)

        self.add_widget(Label(
            text="[b]⚡ VidSnap[/b]", markup=True, font_size=30,
            size_hint=(1, 0.12), color=(0.85, 0.4, 1, 1)
        ))

        self.url_input = TextInput(
            hint_text="الصق رابط الفيديو هنا...",
            multiline=False, size_hint=(1, 0.1), font_size=18
        )
        self.add_widget(self.url_input)

        self.quality_spinner = Spinner(
            text="اختر الجودة",
            values=list(QUALITIES.keys()),
            size_hint=(1, 0.1), font_size=16
        )
        self.add_widget(self.quality_spinner)

        self.download_btn = Button(
            text="⬇️  تحميل", size_hint=(1, 0.1), font_size=20,
            background_color=(0.6, 0.2, 0.9, 1)
        )
        self.download_btn.bind(on_press=self.start_download)
        self.add_widget(self.download_btn)

        self.progress = ProgressBar(max=100, value=0, size_hint=(1, 0.05))
        self.add_widget(self.progress)

        self.status_label = Label(
            text=f"📁 مجلد الحفظ: {SAVE_DIR}",
            size_hint=(1, 0.15), font_size=14, color=(0.7, 0.7, 0.7, 1)
        )
        self.add_widget(self.status_label)

        self.history_label = Label(
            text="سجل التنزيلات يظهر هنا", size_hint_y=None, font_size=14,
            halign="right", valign="top"
        )
        self.history_label.bind(texture_size=self.history_label.setter("size"))
        scroll = ScrollView(size_hint=(1, 0.4))
        scroll.add_widget(self.history_label)
        self.add_widget(scroll)

        self.history = []

    def start_download(self, instance):
        url = self.url_input.text.strip()
        quality_key = self.quality_spinner.text

        if not url:
            self.status_label.text = "⚠️ الصق رابط أولاً"
            return
        if quality_key not in QUALITIES:
            self.status_label.text = "⚠️ اختر الجودة أولاً"
            return

        self.download_btn.disabled = True
        self.status_label.text = "🔍 جارٍ التحليل والتحميل..."
        self.progress.value = 0

        thread = threading.Thread(
            target=self.run_download, args=(url, QUALITIES[quality_key])
        )
        thread.daemon = True
        thread.start()

    def run_download(self, url, fmt):
        try:
            import yt_dlp
        except Exception as e:
            Clock.schedule_once(lambda dt: self.set_status(f"❌ خطأ تحميل المكتبة: {e}"))
            return

        def hook(d):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                pct = int(done / total * 100) if total else 0
                Clock.schedule_once(lambda dt: self.set_progress(pct))
            elif d.get("status") == "finished":
                Clock.schedule_once(lambda dt: self.set_progress(100))

        title_holder = {"title": "video"}

        def get_title_hook(info_dict):
            title_holder["title"] = info_dict.get("title", "video")

        opts = {
            "format": fmt,
            "outtmpl": os.path.join(SAVE_DIR, "%(title).60s.%(ext)s"),
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = re.sub(r'[\\/*?:"<>|]', "", info.get("title", "video"))[:60]

            Clock.schedule_once(lambda dt: self.on_success(title))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.set_status(f"❌ فشل التحميل: {e}"))
        finally:
            Clock.schedule_once(lambda dt: setattr(self.download_btn, "disabled", False))

    def set_progress(self, pct):
        self.progress.value = pct
        self.status_label.text = f"⬇️ جارٍ التحميل... {pct}%"

    def on_success(self, title):
        self.status_label.text = f"✅ تم الحفظ: {title}"
        self.history.insert(0, title)
        self.history_label.text = "\n".join(f"• {t}" for t in self.history)

    def set_status(self, text):
        self.status_label.text = text


class VidSnapApp(App):
    def build(self):
        self.title = "VidSnap"
        return VidSnapUI()


if __name__ == "__main__":
    VidSnapApp().run()

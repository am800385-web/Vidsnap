# -*- coding: utf-8 -*-
"""
VidSnap - نسخة تطبيق أندرويد (Kivy)
محمّل فيديوهات من يوتيوب/فيسبوك/انستغرام/تيك توك/تويتر
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
from kivy.core.text import LabelBase
from kivy.resources import resource_add_path

# --- تسجيل خط يدعم العربي (بدون هذا تطلع الحروف كمربعات) ---
FONT_DIR = os.path.join(os.path.dirname(__file__), "assets")
resource_add_path(FONT_DIR)
ARABIC_FONT = os.path.join(FONT_DIR, "NotoNaskhArabic-Regular.ttf")
try:
    LabelBase.register(name="Arabic", fn_regular=ARABIC_FONT)
    LabelBase.register(name="Roboto", fn_regular=ARABIC_FONT)  # يجعله الخط الافتراضي لكل النصوص
    FONT_NAME = "Arabic"
except Exception:
    FONT_NAME = None

# --- إعادة تشكيل الحروف العربية (بدونها تطلع منفصلة/بترتيب غلط) ---
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def ar(text):
        return get_display(arabic_reshaper.reshape(text))
except Exception:
    def ar(text):
        return text

# --- مكان حفظ آمن ما يحتاج صلاحيات خاصة على أندرويد الحديث ---
try:
    from android.permissions import request_permissions, Permission
    request_permissions([
        Permission.INTERNET,
        Permission.WRITE_EXTERNAL_STORAGE,
        Permission.READ_EXTERNAL_STORAGE,
    ])
    from android.storage import app_storage_path
    SAVE_DIR = os.path.join(app_storage_path(), "VidSnap_Downloads")
except Exception:
    SAVE_DIR = os.path.expanduser("~")

try:
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR, exist_ok=True)
except Exception:
    SAVE_DIR = os.path.expanduser("~")


def log_crash(exc):
    """يكتب أي خطأ غير متوقع بملف نصي جوا مجلد التطبيق، عشان تقدر تشوفه من مدير الملفات"""
    try:
        crash_path = os.path.join(SAVE_DIR, "last_error.txt")
        with open(crash_path, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
    except Exception:
        pass

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
            size_hint=(1, 0.12), color=(0.85, 0.4, 1, 1), font_name=FONT_NAME
        ))

        self.url_input = TextInput(
            hint_text=ar("الصق رابط الفيديو هنا..."),
            multiline=False, size_hint=(1, 0.1), font_size=18,
            font_name=FONT_NAME, base_direction="rtl"
        )
        self.add_widget(self.url_input)

        # نخزن أسماء الجودة الأصلية (بدون تشكيل) كمفاتيح، ونعرض نسخة مُشكّلة للعرض بس
        self.quality_display_map = {ar(k): k for k in QUALITIES.keys()}

        self.quality_spinner = Spinner(
            text=ar("اختر الجودة"),
            values=list(self.quality_display_map.keys()),
            size_hint=(1, 0.1), font_size=16, font_name=FONT_NAME
        )
        self.add_widget(self.quality_spinner)

        self.download_btn = Button(
            text=ar("⬇️  تحميل"), size_hint=(1, 0.1), font_size=20,
            background_color=(0.6, 0.2, 0.9, 1), font_name=FONT_NAME
        )
        self.download_btn.bind(on_press=self.start_download)
        self.add_widget(self.download_btn)

        self.progress = ProgressBar(max=100, value=0, size_hint=(1, 0.05))
        self.add_widget(self.progress)

        self.status_label = Label(
            text=ar(f"📁 مجلد الحفظ: {SAVE_DIR}"),
            size_hint=(1, 0.15), font_size=14, color=(0.7, 0.7, 0.7, 1),
            font_name=FONT_NAME, halign="center"
        )
        self.add_widget(self.status_label)

        self.history_label = Label(
            text=ar("سجل التنزيلات يظهر هنا"), size_hint_y=None, font_size=14,
            halign="right", valign="top", font_name=FONT_NAME
        )
        self.history_label.bind(texture_size=self.history_label.setter("size"))
        scroll = ScrollView(size_hint=(1, 0.4))
        scroll.add_widget(self.history_label)
        self.add_widget(scroll)

        self.history = []

    def start_download(self, instance):
        try:
            url = self.url_input.text.strip()
            quality_key = self.quality_display_map.get(self.quality_spinner.text)

            if not url:
                self.status_label.text = ar("⚠️ الصق رابط أولاً")
                return
            if quality_key not in QUALITIES:
                self.status_label.text = ar("⚠️ اختر الجودة أولاً")
                return

            self.download_btn.disabled = True
            self.status_label.text = ar("🔍 جارٍ التحليل والتحميل...")
            self.progress.value = 0

            thread = threading.Thread(
                target=self.run_download, args=(url, QUALITIES[quality_key])
            )
            thread.daemon = True
            thread.start()
        except Exception:
            log_crash(traceback.format_exc())
            self.status_label.text = ar("❌ صار خطأ غير متوقع، شوف ملف last_error.txt")

    def run_download(self, url, fmt):
        try:
            import yt_dlp
        except Exception as e:
            log_crash(e)
            Clock.schedule_once(lambda dt: self.set_status(ar(f"❌ خطأ تحميل المكتبة: {e}")))
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
            log_crash(e)
            Clock.schedule_once(lambda dt: self.set_status(ar(f"❌ فشل التحميل: {e}")))
        finally:
            Clock.schedule_once(lambda dt: setattr(self.download_btn, "disabled", False))

    def set_progress(self, pct):
        self.progress.value = pct
        self.status_label.text = ar(f"⬇️ جارٍ التحميل... {pct}%")

    def on_success(self, title):
        self.status_label.text = ar(f"✅ تم الحفظ: {title}")
        self.history.insert(0, title)
        self.history_label.text = "\n".join(ar(f"• {t}") for t in self.history)

    def set_status(self, text):
        self.status_label.text = text


class VidSnapApp(App):
    def build(self):
        self.title = "VidSnap"
        return VidSnapUI()


if __name__ == "__main__":
    def _excepthook(exc_type, exc_value, exc_tb):
        """يمسك أي خطأ ما توقعناه قبل ما يقفل التطبيق بصمت، ويكتبه بملف"""
        try:
            log_crash(exc_value)
        except Exception:
            pass
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
    VidSnapApp().run()

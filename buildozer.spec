[app]
title = VidSnap
package.name = vidsnap
package.domain = org.vidsnap

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0

requirements = python3,kivy==2.3.0,yt-dlp,certifi,requests,urllib3,chardet,idna,charset-normalizer,arabic_reshaper,python-bidi

p4a.branch = v2024.01.21

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1

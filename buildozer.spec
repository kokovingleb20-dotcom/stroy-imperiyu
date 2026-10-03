[app]

title = Строй Империю
package.name = stroyimperiyu
package.domain = org.stroyimperiyu

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_dirs = tests, bin, .buildozer, .github, __pycache__

version = 1.0.0

requirements = python3,kivy==2.3.1

orientation = portrait
fullscreen = 0

# Игра работает офлайн, особые разрешения не нужны
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]

log_level = 2
warn_on_root = 1

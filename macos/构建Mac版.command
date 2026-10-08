#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${LIGHTFLIP_PYTHON:-python3.12}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo '请先安装 python.org 的 Python 3.12（带 Tkinter），然后再次打开此文件。'
  open 'https://www.python.org/downloads/macos/'
  read -r -p '按回车关闭…'
  exit 1
fi
"$PYTHON" -c 'import tkinter; import sys; assert sys.version_info[:2] == (3,12), "Please use Python 3.12"'
"$PYTHON" -m venv .venv-macos
.venv-macos/bin/python -m pip install -r requirements.txt -r requirements-ocr.txt 'pyinstaller>=6.15,<7'
.venv-macos/bin/python tools/cache_ocr_models.py
.venv-macos/bin/python tools/build_macos.py
open macos-dist
read -r -p '构建完成，按回车关闭…'

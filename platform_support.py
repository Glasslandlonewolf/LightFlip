"""Small OS boundary for GUI, subprocesses and optional Office rendering."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def process_options():
    return {'creationflags': 0x08000000} if os.name == 'nt' else {}


def data_directory():
    if sys.platform == 'darwin':
        return Path.home()/'Library/Application Support/LightFlip'
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'LightFlip'


def open_folder(path):
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])


def libreoffice():
    choices = [Path('/Applications/LibreOffice.app/Contents/MacOS/soffice'),
               Path.home()/'Applications/LibreOffice.app/Contents/MacOS/soffice']
    executable = shutil.which('soffice') or shutil.which('libreoffice')
    return next((str(p) for p in choices if p.is_file()), executable)


def office_to_pdf(source, destination):
    engine=libreoffice()
    if not engine:
        raise RuntimeError('此转换需要 LibreOffice。请安装后重新打开轻转；PDF、图片直接转 Word/PPT 不需要它。')
    source, destination = Path(source).resolve(), Path(destination).resolve()
    # Use an isolated user profile and staged input, preserving open documents,
    # original files, and the user's normal Office profile/macro settings.
    with tempfile.TemporaryDirectory(prefix='.lightflip-office-', dir=destination.parent) as temp:
        folder=Path(temp); profile=folder/'profile'; profile.mkdir()
        staged=folder/('input'+source.suffix);shutil.copy2(source,staged)
        (profile/'registrymodifications.xcu').write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
            '</item></oor:items>',encoding='utf-8')
        result=subprocess.run([engine, '-env:UserInstallation='+profile.as_uri(),
                              '--headless','--nologo','--nodefault','--norestore',
                              '--convert-to','pdf','--outdir',str(folder),str(staged)],
                             capture_output=True,text=True,timeout=240,**process_options())
        output=folder/'input.pdf'
        if result.returncode or not output.is_file() or output.stat().st_size<5:
            raise RuntimeError('Office 文件未能转换为 PDF。请检查文件是否损坏或有密码保护。')
        with output.open('rb') as file:
            if file.read(5)!=b'%PDF-':raise RuntimeError('Office 转换没有生成有效 PDF。')
        shutil.copy2(output,destination)

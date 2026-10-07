"""Assemble an offline Windows x64 preview from dedicated Python environments."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APP_FILES = ('app.py', 'core.py', 'file_tools.py', 'office_export.py',
             'pdf_layout.py', 'pdf_ocr.py', 'ocr_layout.py', 'image_layout.py', 'paragraph_layout.py', 'tool_dialogs.py', 'ai_worker.py',
             'launcher.py', 'offline_installer.py')

def ignored(directory, names):
    return [name for name in names if name == '__pycache__' or name.endswith(('.pyc', '.pyo'))]

def environment(interpreter):
    code = ('import json,sys,sysconfig,struct;print(json.dumps(dict('
            'base=sys.base_prefix,site=sysconfig.get_path("purelib"),'
            'version=str(sys.version_info.major)+str(sys.version_info.minor),'
            'bits=struct.calcsize("P")*8)))')
    result = subprocess.run([str(Path(interpreter).resolve()), '-I', '-c', code],
                            capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    if info['bits'] != 64:
        raise ValueError('Both Python environments must be 64 bit.')
    return info

def copy_runtime(info, target, excluded):
    base, site = Path(info['base']), Path(info['site'])
    target.mkdir(parents=True)
    for name in ('python.exe', 'pythonw.exe', 'python3.dll',
                 'python' + info['version'] + '.dll', 'vcruntime140.dll',
                 'vcruntime140_1.dll', 'LICENSE.txt'):
        source = base / name
        if source.exists():
            shutil.copy2(source, target / name)
        elif name in ('python.exe', 'pythonw.exe'):
            raise FileNotFoundError(source)
    for name in ('DLLs', 'tcl'):
        if (base / name).is_dir():
            shutil.copytree(base / name, target / name, ignore=ignored)
    def std_ignore(directory, names):
        return ignored(directory, names) + [n for n in names if n in
                {'site-packages', 'test', 'tests', 'idlelib', 'ensurepip'}]
    shutil.copytree(base / 'Lib', target / 'Lib', ignore=std_ignore)
    packages = target / 'Lib/site-packages'
    packages.mkdir()
    for child in site.iterdir():
        name = child.name.lower()
        if child.name in ignored(site, [child.name]) or any(
                name == x or name.startswith(x + '-') or name.startswith(x + '.')
                for x in excluded):
            continue
        if child.is_dir():
            shutil.copytree(child, packages / child.name, ignore=ignored)
        else:
            shutil.copy2(child, packages / child.name)
    # PyWin32 needs these paths when using an isolated portable interpreter.
    paths = ['.', 'DLLs', 'Lib', 'Lib/site-packages',
             'Lib/site-packages/win32', 'Lib/site-packages/win32/lib',
             'Lib/site-packages/pythonwin', 'Lib/site-packages/pywin32_system32',
             'import site']
    (target / ('python' + info['version'] + '._pth')).write_text(
        '\n'.join(paths) + '\n', encoding='utf-8')
    system = Path(os.environ['WINDIR']) / 'System32'
    for name in ('msvcp140.dll', 'msvcp140_1.dll'):
        if (system / name).is_file():
            shutil.copy2(system / name, target / name)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-python', required=True)
    parser.add_argument('--ocr-python', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Build on Windows.')
    main_info, ocr_info = environment(args.main_python), environment(args.ocr_python)
    if not any((Path(ocr_info['site']) / 'rapidocr/models').glob('*.onnx')):
        parser.error('Prepare OCR models first: use the OCR interpreter to run tools/cache_ocr_models.py')
    destination = args.output.resolve()
    package = destination / 'LightFlip-offline-0.4.0-win-x64'
    if package.exists():
        parser.error('Package directory already exists. Choose another --output directory.')
    destination.mkdir(parents=True, exist_ok=True)
    package.mkdir()
    copy_runtime(main_info, package / 'runtime', ('pip', 'adodbapi', 'isapi'))
    copy_runtime(ocr_info, package / 'ocr-runtime', ('pip', 'rembg', 'pymatting',
                 'numba', 'llvmlite', 'networkx', 'scipy', 'skimage', 'scikit_image',
                 'imageio', 'tifffile', 'pooch', 'lazy_loader', 'pydevd_plugins'))
    for name in APP_FILES:
        shutil.copy2(ROOT / name, package / name)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.md'):
        shutil.copy2(ROOT / name, package / name)
    shutil.copytree(ROOT / 'licenses', package / 'licenses')
    for name, script in (('安装轻转.cmd', 'offline_installer.py'), ('启动轻转.cmd', 'launcher.py')):
        text = '@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0runtime\\pythonw.exe" -I -X utf8 "%~dp0' + script + '"\r\n'
        (package / name).write_bytes(text.encode('ascii'))
    (package / '先看这里.txt').write_text(
        '轻转离线测试版：先完整解压，再双击“安装轻转.cmd”。\n'
        '无需另装 Python；也可以双击“启动轻转.cmd”直接运行。\n'
        '使用说明、限制与第三方组件许可见 README.md 和 THIRD_PARTY_NOTICES.md。\n',
        encoding='utf-8-sig')
    ffmpeg_candidates = list((package / 'runtime/Lib/site-packages/imageio_ffmpeg/binaries').glob('ffmpeg*.exe'))
    if not ffmpeg_candidates:
        raise RuntimeError('No bundled FFmpeg executable found.')
    for option in ('version', 'buildconf', 'L'):
        result = subprocess.run([str(ffmpeg_candidates[0]), '-' + option], capture_output=True,
                                creationflags=0x08000000, check=True)
        (package / 'licenses' / ('ffmpeg-' + option + '.txt')).write_bytes(result.stdout + result.stderr)
    files = {}
    for file in sorted(package.rglob('*')):
        if file.is_file():
            files[file.relative_to(package).as_posix()] = {
                'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
    (package / 'package-manifest.json').write_text(json.dumps(
        {'name': 'LightFlip', 'version': '0.4.0', 'files': files}, indent=2), encoding='utf-8')
    archive = destination / '轻转-离线测试版-0.4.0-Windows64位.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as output:
        for file in sorted(package.rglob('*')):
            if file.is_file():
                output.write(file, Path(package.name) / file.relative_to(package))
    print(archive)

if __name__ == '__main__':
    main()

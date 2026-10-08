"""Build and test a native, self-contained app on macOS (never cross-compile)."""
import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('macos-dist'))
    args=parser.parse_args()
    if sys.platform!='darwin':
        parser.error('This app must be built on macOS.')
    root=Path(__file__).resolve().parents[1]
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    arch=platform.machine()
    build=output/('build-'+arch)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed',
             '--onedir','--name','LightFlip','--osx-bundle-identifier','org.lightflip.desktop',
             '--target-architecture',arch,'--distpath',str(build/'dist'),
             '--workpath',str(build/'work'),'--specpath',str(build),
             '--paths',str(root),'--additional-hooks-dir',str(root/'tools/macos-hooks')]
    # OpenCV's bootstrap replaces its own module. Its dedicated PyInstaller
    # hook controls source/binary placement; generic collect-all interferes.
    for package in ('rapidocr','onnxruntime','imageio_ffmpeg','pypdfium2','markitdown'):
        command+=['--collect-all',package]
    for module in ('app','core','office_export','file_tools','tool_dialogs','ai_worker',
                   'ocr_layout','paragraph_layout','image_layout','pdf_layout','pdf_ocr','platform_support','macos_smoke'):
        command+=['--hidden-import',module]
    command.append(str(root/'launcher.py'))
    subprocess.run(command,cwd=root,check=True)
    app=build/'dist/LightFlip.app'
    report=output/('self-test-'+arch+'.json')
    subprocess.run([str(app/'Contents/MacOS/LightFlip'),'--lightflip-self-test',str(report)],check=True,timeout=360)
    import json
    if not json.loads(report.read_text())['passed']:
        raise RuntimeError('Packaged application failed its native self-test.')
    release=output/('LightFlip-0.4.0-macOS-'+arch)
    release.mkdir(exist_ok=True)
    subprocess.run(['ditto',str(app),str(release/'LightFlip.app')],check=True)
    shutil.copy2(root/'macos/使用说明.md',release/'使用说明.md')
    shutil.copy2(root/'LICENSE',release/'LICENSE')
    shutil.copy2(root/'THIRD_PARTY_NOTICES.md',release/'THIRD_PARTY_NOTICES.md')
    shutil.copytree(root/'licenses',release/'licenses',dirs_exist_ok=True)
    source=release/'source';source.mkdir(exist_ok=True)
    for file in root.glob('*.py'):
        shutil.copy2(file,source/file.name)
    for name in ('README.md','LICENSE','requirements.txt','requirements-ocr.txt'):
        shutil.copy2(root/name,source/name)
    shutil.copytree(root/'tools',source/'tools',ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    shutil.copytree(root/'macos',source/'macos',dirs_exist_ok=True)
    shutil.copy2(report,release/'self-test.json')
    # Record the actual native runtime and bundled FFmpeg build, which differ
    # from the Windows portable package.
    manifest=release/'build-info';manifest.mkdir(exist_ok=True)
    from imageio_ffmpeg import get_ffmpeg_exe
    for name,command in [('python-packages.txt',[sys.executable,'-m','pip','freeze']),
                         ('ffmpeg-version.txt',[get_ffmpeg_exe(),'-version']),
                         ('ffmpeg-buildconf.txt',[get_ffmpeg_exe(),'-buildconf']),
                         ('ffmpeg-license.txt',[get_ffmpeg_exe(),'-L'])]:
        result=subprocess.run(command,check=True,capture_output=True,text=True)
        (manifest/name).write_text(result.stdout+result.stderr,encoding='utf-8')
    archive=output/(release.name+'.zip')
    subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(release),str(archive)],check=True)
    print(archive)

if __name__=='__main__':
    main()

from pathlib import Path
import os
import runpy
import sys
import traceback

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
os.environ['PYTHONUTF8']='1'
os.environ['PYTHONIOENCODING']='utf-8'
try:
    runpy.run_path(str(ROOT/'app.py'),run_name='__main__')
except Exception:
    log=Path(os.environ.get('LOCALAPPDATA',str(ROOT)))/'LightFlipPreview/startup-error.txt'
    log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text(traceback.format_exc(),encoding='utf-8')
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,'启动失败，检查信息已保存到：\n'+str(log),'轻转测试版',16)

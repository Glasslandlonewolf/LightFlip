from pathlib import Path
import os
import json
import sys
import traceback

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
os.environ['PYTHONUTF8']='1'
os.environ['PYTHONIOENCODING']='utf-8'
def main():
    if len(sys.argv)>1 and sys.argv[1]=='--lightflip-ocr':
        from ai_worker import main as recognize
        request,response=map(Path,sys.argv[2:4])
        try:
            result=recognize(json.loads(request.read_text(encoding='utf-8')))
            response.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        except Exception as error:
            response.write_text(json.dumps({'error':str(error)},ensure_ascii=False),encoding='utf-8')
            raise SystemExit(1)
        return
    if len(sys.argv)>1 and sys.argv[1]=='--lightflip-self-test':
        from macos_smoke import main as smoke
        smoke(Path(sys.argv[2]))
        return
    from app import run_app
    run_app()

if __name__=='__main__':
    try:
        main()
    except Exception:
        from platform_support import data_directory
        log=data_directory()/'startup-error.txt'
        log.parent.mkdir(parents=True,exist_ok=True)
        log.write_text(traceback.format_exc(),encoding='utf-8')
        if len(sys.argv)>1 and sys.argv[1].startswith('--lightflip-'):
            raise
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'启动失败，检查信息已保存到：\n'+str(log),'轻转',16)
        else:
            from tkinter import messagebox
            messagebox.showerror('轻转','启动失败，检查信息已保存到：\n'+str(log))
        raise SystemExit(1)

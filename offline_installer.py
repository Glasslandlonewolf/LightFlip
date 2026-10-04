from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox,ttk

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
DEFAULT=Path(os.environ['LOCALAPPDATA'])/'Programs/LightFlipPreview'

def install(destination,shortcuts=True):
    destination=Path(destination).resolve()
    if destination==ROOT or ROOT.is_relative_to(destination) or destination.is_relative_to(ROOT):
        raise ValueError('安装目录不能与解压目录重叠。')
    if destination.exists() and any(destination.iterdir()) and not (destination/'lightflip-install.json').is_file():
        raise ValueError('此目录已有其他文件，请选择空目录。')
    destination.mkdir(parents=True,exist_ok=True)
    shutil.copytree(ROOT,destination,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (destination/'lightflip-install.json').write_text(json.dumps({'name':'LightFlipPreview','version':'0.1.0','offline':True}),encoding='utf-8')
    if shortcuts:
        import win32com.client
        shell=win32com.client.Dispatch('WScript.Shell')
        desktop=Path(shell.SpecialFolders('Desktop'))
        programs=Path(shell.SpecialFolders('Programs'))
        for directory in [desktop,programs]:
            link=shell.CreateShortcut(str(directory/'轻转测试版.lnk'))
            link.TargetPath=str(destination/'runtime/pythonw.exe')
            link.Arguments='-I -X utf8 "'+str(destination/'launcher.py')+'"'
            link.WorkingDirectory=str(destination)
            link.Description='轻转离线文件转换测试版'
            link.Save()
    return destination

if len(sys.argv)>1 and sys.argv[1]=='--test-install':
    print(str(install(sys.argv[2],shortcuts=False)),flush=True)
    sys.exit(0)

root=tk.Tk()
root.title('安装轻转 · 离线测试版')
root.geometry('570x320')
root.resizable(False,False)
root.configure(bg='#f3f5fa')
tk.Label(root,text='轻转 · 离线测试版',font=('Microsoft YaHei UI',20,'bold'),bg='#f3f5fa',fg='#25314d').pack(pady=(24,12))
tk.Label(root,text='无需联网，无需安装 Python，无需管理员权限。\n安装后会创建桌面和开始菜单快捷方式。',bg='#f3f5fa',fg='#65708a').pack()
tk.Label(root,text='安装位置：'+str(DEFAULT),wraplength=520,bg='#f3f5fa',fg='#65708a').pack(pady=12)
status=tk.StringVar(value='点击安装，稍等文件复制完成。')
tk.Label(root,textvariable=status,bg='#f3f5fa').pack(pady=5)
progress=ttk.Progressbar(root,mode='indeterminate',length=420)
progress.pack(pady=8)
def start():
    button.configure(state='disabled')
    progress.start()
    status.set('正在安装，请稍候…')
    def work():
        try:
            destination=install(DEFAULT)
            def done():
                progress.stop()
                status.set('安装完成，正在打开轻转。')
                subprocess.Popen([str(destination/'runtime/pythonw.exe'),'-I','-X','utf8',str(destination/'launcher.py')],cwd=destination,creationflags=0x08000000)
                root.after(1200,root.destroy)
            root.after(0,done)
        except Exception as error:
            text=str(error)
            def failed():
                progress.stop()
                button.configure(state='normal')
                status.set('安装未完成。')
                messagebox.showerror('安装未完成',text,parent=root)
            root.after(0,failed)
    threading.Thread(target=work,daemon=True).start()
button=tk.Button(root,text='安装轻转',width=18,command=start,font=('Microsoft YaHei UI',12))
button.pack(pady=12)
root.mainloop()


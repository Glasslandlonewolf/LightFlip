import ctypes
import os
from pathlib import Path
import queue
import threading
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES
from core import formats, convert, document_has_pages, DOCUMENTS, OFFICE_INPUTS, IMAGE_TARGETS
from file_tools import available_tools, execute_tool, TOOL_MAP
from tool_dialogs import choose_options

class App:
    def __init__(self, reopen_event=None):
        self.reopen_event = reopen_event
        self.root = TkinterDnD.Tk()
        self.root.title('轻转 0.2.0 · Windows 文件转换')
        self.root.geometry('720x650')
        self.root.minsize(680, 630)
        self.root.configure(bg='#f3f5fa')
        self.files = []
        self.busy = False
        self.results = queue.Queue()
        self.output = None
        self.popup = None
        self.gesture = False
        self.tool_wheel = False
        self.tray = None
        tk.Label(self.root, text='轻转', font=('Microsoft YaHei UI', 28, 'bold'), bg='#f3f5fa', fg='#25314d').pack(pady=(22, 2))
        tk.Label(self.root, text='一个入口，转换图片、文档、音频和视频', bg='#f3f5fa', fg='#65708a').pack()
        self.drop = tk.Label(self.root, text='把文件拖到这里\n或点击选择文件', bg='white', fg='#425bdb', font=('Microsoft YaHei UI', 15), height=4, cursor='hand2')
        self.drop.pack(fill='x', padx=26, pady=18)
        self.drop.bind('<Button-1>', lambda e: self.select(filedialog.askopenfilenames()))
        self.register_drop(self.drop, self.dropped)
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill='x', padx=26)
        self.buttons = tk.Frame(self.tabs, bg='#f3f5fa', height=145)
        self.tool_buttons = tk.Frame(self.tabs, bg='#f3f5fa', height=145)
        self.tabs.add(self.buttons, text='  格式转换  ')
        self.tabs.add(self.tool_buttons, text='  文件工具  ')
        self.tool_hint = tk.Label(self.root, text='拖入图片、PDF 或视频后，切换“文件工具”查看适用操作。', bg='#f3f5fa', fg='#65708a', wraplength=620)
        self.tool_hint.pack(pady=(10, 0))
        self.status = tk.StringVar(value='转换后的文件放在原文件旁边，保留原文件。')
        tk.Label(self.root, textvariable=self.status, wraplength=620, bg='#f3f5fa', fg='#65708a').pack(pady=12)
        self.progress_bar = ttk.Progressbar(self.root, mode='indeterminate', length=360)
        self.progress_bar.pack(pady=(0, 10))
        tk.Button(self.root, text='打开输出文件夹', command=self.open_output).pack()
        tk.Label(self.root, text='拖动文件＋Shift：格式轮盘；Shift＋Alt：工具轮盘。\n合并时请一起选择多个文件；输出放在原文件旁边，保留原文件。', bg='#f3f5fa', fg='#65708a', font=('Microsoft YaHei UI', 9)).pack(side='bottom', pady=12)
        self.root.after(100, self.poll)
        self.root.protocol('WM_DELETE_WINDOW', self.hide)
        self.start_tray()

    def hide(self):
        self.root.withdraw()

    def start_tray(self):
        import pystray
        from PIL import Image, ImageDraw
        icon = Image.new('RGB', (64, 64), '#425bdb')
        draw = ImageDraw.Draw(icon)
        draw.ellipse((10, 10, 54, 54), outline='white', width=5)
        draw.line((22, 32, 42, 32), fill='white', width=5)
        self.tray = pystray.Icon('LightFlip', icon, '轻转：拖文件＋Shift', pystray.Menu(
            pystray.MenuItem('打开轻转', lambda: self.results.put('show'), default=True),
            pystray.MenuItem('退出', lambda: self.results.put('quit'))))
        threading.Thread(target=self.tray.run, daemon=True).start()

    def register_drop(self, widget, handler):
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind('<<Drop>>', handler)

    def dropped(self, event):
        self.select(self.root.tk.splitlist(event.data))
        return 'copy'

    def select(self, files):
        if self.busy or not files:
            return
        self.files = [str(Path(f)) for f in files]
        choices = set(formats(self.files[0]))
        for f in self.files[1:]:
            choices &= set(formats(f))
        self.drop.configure(text=f'已选 {len(self.files)} 个文件\n' + Path(self.files[0]).name)
        for child in self.buttons.winfo_children():
            child.destroy()
        for index, fmt in enumerate(sorted(choices)):
            button = tk.Button(self.buttons, text=self.format_label(fmt), width=10, bg='white', fg='#25314d', command=lambda f=fmt: self.start(self.files, f))
            button.grid(row=index//5, column=index%5, padx=3, pady=3)
        for child in self.tool_buttons.winfo_children():
            child.destroy()
        tools = available_tools(self.files)
        for index, tool in enumerate(tools):
            tk.Button(self.tool_buttons, text=tool.label, width=16, bg='white', fg='#25314d', command=lambda key=tool.key: self.start_tool(self.files, key)).grid(row=index//3, column=index%3, padx=5, pady=5, sticky='ew')
        for column in range(3):
            self.tool_buttons.columnconfigure(column, weight=1)
        if not tools:
            tk.Label(self.tool_buttons, text='所选文件没有共同适用的工具。\n请一起选择图片、PDF 或视频。', bg='#f3f5fa', fg='#65708a').pack(padx=20, pady=20)
        suffix = Path(self.files[0]).suffix.lower()
        if suffix == '.pdf':
            self.tool_hint.configure(text='OCR 在本机识别中英文；合并 PDF 时一起选择多份文件。')
        elif suffix[1:] in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tif', 'tiff'}:
            self.tool_hint.configure(text='裁剪可以框选预览；多图合并 PDF 时一起选择图片，并可调整顺序。')
        else:
            self.tool_hint.configure(text='选择文件工具即可处理。720p 保持比例，不放大小视频；没有音轨的视频无法提取音频。')
        if not choices:
            self.status.set('这些文件没有共同的转换格式，请分开选择。')
        elif any(document_has_pages(f) for f in self.files):
            self.status.set('直接选择最终格式即可；转图片时，每页保存一张。')
        elif any(Path(f).suffix.lower()[1:] in DOCUMENTS-OFFICE_INPUTS-{'pdf'} for f in self.files):
            self.status.set('直接选择最终格式；文字类文件转 PDF / 图片时按提取的内容排版。')
        else:
            self.status.set('点一个格式即可转换。')

    def start(self, files, fmt):
        if self.busy:
            return
        self.close_popup()
        self.root.deiconify()
        mode = 'pages'
        if fmt in {'docx', 'pptx'} and any(document_has_pages(f) or Path(f).suffix.lower()[1:] in {'png','jpg','jpeg','gif','webp','bmp','tif','tiff'} for f in files):
            mode = self.choose_pdf_mode(fmt, files)
            if mode is None:
                return
        self.busy = True
        self.progress_bar.start(12)
        self.status.set('正在转换，请稍候…' + ('多页文件会按页输出图片。' if fmt in IMAGE_TARGETS and any(document_has_pages(f) for f in files) else ''))
        def worker():
            good, errors = [], []
            for source in list(files):
                try:
                    good.extend(convert(source, fmt, mode=mode, progress=lambda text:self.results.put({'progress':text})))
                except Exception as e:
                    errors.append(Path(source).name + ': ' + str(e))
            self.results.put((good, errors))
        threading.Thread(target=worker, daemon=True).start()

    def start_tool(self, files, key):
        if self.busy:
            return
        files = list(files)
        self.close_popup()
        self.root.deiconify()
        self.root.lift()
        self.select(files)
        self.tabs.select(self.tool_buttons)
        if key not in {tool.key for tool in available_tools(files)}:
            messagebox.showinfo('请选择适用文件', '这个工具不适用所选文件。合并需要至少两个同类文件。', parent=self.root)
            return
        try:
            options = choose_options(self.root, files, key)
        except Exception as error:
            messagebox.showerror('无法开始处理', str(error), parent=self.root)
            return
        if options is None:
            return
        files = options.pop('files', files)
        self.busy = True
        self.progress_bar.start(12)
        self.status.set('正在' + TOOL_MAP[key].label + '…')
        def worker():
            try:
                good, notes, errors = execute_tool(files, key, options, lambda text: self.results.put({'progress': text}))
                self.results.put({'complete': True, 'files': good, 'notes': notes, 'errors': errors})
            except Exception as error:
                self.results.put({'complete': True, 'files': [], 'notes': [], 'errors': [str(error)]})
        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def format_label(fmt):
        return {'docx': 'Word', 'pptx': 'PPT'}.get(fmt, fmt.upper())

    def choose_pdf_mode(self, fmt, files=None):
        dialog = tk.Toplevel(self.root)
        source_label = ('图片' if files and all(Path(f).suffix.lower()[1:] in {'png','jpg','jpeg','gif','webp','bmp','tif','tiff'} for f in files)
                        else '文档' if files and any(Path(f).suffix.lower()!='.pdf' for f in files) else 'PDF')
        dialog.title(source_label + ' 转 ' + self.format_label(fmt))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        selected = [None]
        def choose(value):
            selected[0] = value
            dialog.destroy()
        tk.Label(dialog, text='选择转换方式', font=('Microsoft YaHei UI', 14, 'bold')).pack(padx=24, pady=(18, 12))
        tk.Button(dialog, text='保留布局并编辑（文字＋图片）', width=34, command=lambda: choose('layout')).pack(padx=24, pady=4)
        hint='自动识别图片页文字并重建文字框；尽量保留位置、字号和颜色。\n扫描页的图片和装饰保留为背景，识别结果请校对。'
        tk.Label(dialog,text=hint).pack(padx=24,pady=(0,12))
        tk.Button(dialog,text='识别图片文字并编辑（OCR）',width=34,command=lambda:choose('ocr')).pack(padx=24,pady=4)
        tk.Label(dialog,text='适用于扫描件，或图片中有文字的混合 PDF；每页都做文字识别。').pack(padx=24,pady=(0,12))
        tk.Button(dialog, text='保留页面外观（图纸推荐）', width=34, command=lambda: choose('pages')).pack(padx=24, pady=4)
        tk.Label(dialog, text='每页放入一张图片；文字和图形不能单独编辑。').pack(padx=24, pady=(0, 12))
        tk.Button(dialog, text='提取可编辑文字', width=34, command=lambda: choose('text')).pack(padx=24, pady=4)
        tk.Label(dialog,text='重新排版文字；图片和扫描页自动识别，不保留原图和原版式。').pack(padx=24,pady=(0,12))
        tk.Button(dialog, text='取消', command=lambda: choose(None)).pack(pady=(0, 16))
        dialog.grab_set()
        self.root.wait_window(dialog)
        return selected[0]

    def close_popup(self):
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None

    def show_popup(self, tools=False):
        self.tool_wheel = tools
        self.popup = tk.Toplevel(self.root)
        self.popup.overrideredirect(True)
        self.popup.attributes('-topmost', True)
        self.popup.configure(bg='#25314d')
        x, y = self.root.winfo_pointerxy()
        x = max(0, min(x-210, self.root.winfo_screenwidth()-420))
        y = max(0, min(y-210, self.root.winfo_screenheight()-420))
        self.popup.geometry(f'420x420+{x}+{y}')
        canvas = tk.Canvas(self.popup, width=420, height=420, bg='#25314d', highlightthickness=0)
        canvas.pack()
        canvas.create_oval(60, 60, 360, 360, outline='#65708a', width=2)
        canvas.create_text(210, 205, text='轻转\n松手到工具上\n中间松手取消' if tools else '轻转\n松手到格式上\n中间松手取消', fill='white', justify='center', font=('Microsoft YaHei UI', 12))
        choices = ['crop', 'image_compress', 'half', 'rotate', 'images_pdf', 'pdf_merge', 'ocr', 'video_compress'] if tools else ['png', 'jpg', 'gif', 'webp', 'pdf', 'docx', 'pptx', 'md', 'txt', 'mp4', 'mp3', 'wav']
        for index, fmt in enumerate(choices):
            angle = 2*math.pi*index/len(choices) - math.pi/2
            label = tk.Label(canvas, text=TOOL_MAP[fmt].label if tools else self.format_label(fmt), bg='#edf0ff', fg='#25314d', width=9 if tools else 7, height=2, font=('Microsoft YaHei UI', 9, 'bold'))
            canvas.create_window(210+150*math.cos(angle), 210+150*math.sin(angle), window=label)
            self.register_drop(label, lambda e, f=fmt: self.quick_tool(e, f) if tools else self.quick_drop(e, f))
            label.dnd_bind('<<DropEnter>>', lambda e, w=label: self.highlight(w, True))
            label.dnd_bind('<<DropLeave>>', lambda e, w=label: self.highlight(w, False))
        more = tk.Label(canvas, text='全部工具' if tools else '更多格式', bg='#edf0ff', fg='#25314d', width=10, height=2)
        canvas.create_window(210, 270, window=more)
        self.register_drop(more, lambda event: self.quick_select(event, tools))
        more.dnd_bind('<<DropEnter>>', lambda e: self.highlight(more, True))
        more.dnd_bind('<<DropLeave>>', lambda e: self.highlight(more, False))

    def quick_select(self, event, tools=False):
        files = self.root.tk.splitlist(event.data)
        def show_choices():
            if self.busy:
                return
            self.close_popup()
            self.root.deiconify()
            self.root.lift()
            self.select(files)
            self.tabs.select(self.tool_buttons if tools else self.buttons)
        self.root.after_idle(show_choices)
        return 'copy'

    def highlight(self, widget, active):
        widget.configure(bg='#ffb45b' if active else '#edf0ff')
        return 'copy'

    def quick_drop(self, event, fmt):
        files = self.root.tk.splitlist(event.data)
        self.root.after_idle(lambda: self.start(files, fmt))
        return 'copy'

    def quick_tool(self, event, key):
        files = self.root.tk.splitlist(event.data)
        self.root.after_idle(lambda: self.start_tool(files, key))
        return 'copy'

    def open_output(self):
        if self.output:
            os.startfile(str(self.output.parent))

    def poll(self):
        if self.reopen_event and ctypes.windll.kernel32.WaitForSingleObject(ctypes.c_void_p(self.reopen_event), 0) == 0:
            self.root.deiconify()
            self.root.lift()
        try:
            result = self.results.get_nowait()
            if result == 'show':
                self.root.deiconify()
                self.root.after(100, self.poll)
                return
            if result == 'quit':
                self.tray.stop()
                self.root.destroy()
                return
            if isinstance(result, dict) and 'progress' in result:
                self.status.set(result['progress'])
                self.root.after(100, self.poll)
                return
            notes = []
            if isinstance(result, dict):
                good, errors, notes = result['files'], result['errors'], result['notes']
            else:
                good, errors = result
            self.busy = False
            self.progress_bar.stop()
            if good:
                self.output = good[0]
            self.status.set(f'完成 {len(good)} 个输出文件' + (f'，失败 {len(errors)} 个。' if errors else '。'))
            if notes:
                self.status.set(self.status.get() + '\n' + '\n'.join(notes[:2]))
                if len(notes) > 2:
                    messagebox.showinfo('处理结果', '\n'.join(notes), parent=self.root)
            if errors:
                messagebox.showerror('部分文件未完成', '\n\n'.join(errors))
        except queue.Empty:
            pass
        user = ctypes.windll.user32
        mouse_down = bool(user.GetAsyncKeyState(0x01) & 0x8000)
        held = bool(user.GetAsyncKeyState(0x10) & 0x8000 and mouse_down)
        tools = bool(user.GetAsyncKeyState(0x12) & 0x8000)
        interaction_blocked = self.busy or self.root.grab_current() is not None
        if held and not self.gesture and not interaction_blocked:
            self.gesture = True
            self.show_popup(tools)
        elif held and self.gesture and self.popup is not None and not interaction_blocked and tools != self.tool_wheel:
            self.close_popup()
            self.show_popup(tools)
        if not mouse_down and self.gesture:
            self.gesture = False
            self.root.after(500, self.close_popup)
        self.root.after(100, self.poll)

if __name__ == '__main__':
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.SetEvent.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, 'Local\\LightFlip.SingleInstance')
    already_running = ctypes.get_last_error() == 183
    event = kernel.CreateEventW(None, False, False, 'Local\\LightFlip.Reopen')
    if already_running:
        kernel.SetEvent(event)
    else:
        App(event).root.mainloop()

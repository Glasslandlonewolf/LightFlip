"""Small, user-facing option dialogs for file tools."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox


class OptionsDialog:
    def __init__(self, parent, title, explanation=''):
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.result = None
        self.body = ttk.Frame(self.window, padding=20)
        self.body.pack(fill='both', expand=True)
        ttk.Label(self.body, text=title, font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w', pady=(0, 12))
        if explanation:
            ttk.Label(self.body, text=explanation, wraplength=480, justify='left').pack(anchor='w', pady=(0, 12))
        self.actions = ttk.Frame(self.window, padding=(20, 6, 20, 16))
        self.actions.pack(fill='x')
        ttk.Button(self.actions, text='取消', command=self.window.destroy).pack(side='right', padx=(8, 0))
        self.confirm = ttk.Button(self.actions, text='开始处理')
        self.confirm.pack(side='right')
        self.window.bind('<Escape>', lambda event: self.window.destroy())

    def finish(self, value):
        self.result = value
        self.window.destroy()

    def wait(self):
        self.window.grab_set()
        self.window.wait_window()
        return self.result


def crop_options(parent, files):
    from PIL import Image, ImageOps, ImageTk
    with Image.open(files[0]) as original:
        image = ImageOps.exif_transpose(original).convert('RGBA')
    image.thumbnail((650, 400), Image.Resampling.LANCZOS)
    dialog = OptionsDialog(parent, '图片裁剪', '在图片上拖动框选范围。多张图片按相同比例裁剪；保存为新文件。')
    width, height = image.size
    canvas = tk.Canvas(dialog.body, width=width, height=height, bg='#e5e7eb', highlightthickness=0, cursor='crosshair')
    canvas.pack()
    photo = ImageTk.PhotoImage(image, master=dialog.window)
    canvas.create_image(0, 0, image=photo, anchor='nw')
    rectangle = canvas.create_rectangle(0, 0, width, height, outline='#425bdb', width=3)
    box = [0, 0, width, height]
    start = [0, 0]
    info = tk.StringVar(value='默认保留整张图片，请拖动选择裁剪范围。')
    ttk.Label(dialog.body, textvariable=info).pack(pady=(8, 0))
    def clamp(event):
        return max(0, min(event.x, width)), max(0, min(event.y, height))
    def begin(event):
        start[:] = clamp(event)
    def move(event):
        x, y = clamp(event)
        box[:] = [min(start[0], x), min(start[1], y), max(start[0], x), max(start[1], y)]
        canvas.coords(rectangle, *box)
        info.set(f'保留宽度 {100*(box[2]-box[0])/width:.0f}% · 高度 {100*(box[3]-box[1])/height:.0f}%')
    def apply():
        if box[2]-box[0] < 2 or box[3]-box[1] < 2:
            messagebox.showerror('范围太小', '请框选一个有效的裁剪范围。', parent=dialog.window)
            return
        dialog.finish({'box': (box[0]/width, box[1]/height, box[2]/width, box[3]/height)})
    canvas.bind('<Button-1>', begin)
    canvas.bind('<B1-Motion>', move)
    canvas.bind('<ButtonRelease-1>', move)
    dialog.confirm.configure(command=apply)
    return dialog.wait()


def order_options(parent, files, title):
    dialog = OptionsDialog(parent, title, '按下面的顺序合并。点击文件后可上移、下移或移除；输出保存在第一份文件旁边。')
    ordered = list(files)
    listing = tk.Listbox(dialog.body, width=62, height=min(10, max(4, len(ordered))), exportselection=False, font=('Microsoft YaHei UI', 10))
    listing.pack(fill='x')
    def refresh(index=0):
        listing.delete(0, 'end')
        for number, file in enumerate(ordered):
            listing.insert('end', f'{number+1}. {Path(file).name}')
        if ordered:
            listing.selection_set(max(0, min(index, len(ordered)-1)))
    def move(delta):
        selection = listing.curselection()
        if selection and 0 <= selection[0]+delta < len(ordered):
            index = selection[0]
            ordered[index], ordered[index+delta] = ordered[index+delta], ordered[index]
            refresh(index+delta)
    def remove():
        selection = listing.curselection()
        if selection:
            del ordered[selection[0]]
            refresh(selection[0])
    actions = ttk.Frame(dialog.body)
    actions.pack(pady=10)
    ttk.Button(actions, text='上移', command=lambda: move(-1)).pack(side='left', padx=4)
    ttk.Button(actions, text='下移', command=lambda: move(1)).pack(side='left', padx=4)
    ttk.Button(actions, text='移除', command=remove).pack(side='left', padx=4)
    def apply():
        if len(ordered) < 2:
            messagebox.showerror('需要多个文件', '请保留至少两个文件。', parent=dialog.window)
            return
        dialog.finish({'files': ordered})
    refresh()
    dialog.confirm.configure(command=apply)
    return dialog.wait()


def choose_options(parent, files, key):
    from file_tools import TOOL_MAP, open_pdf, page_groups, parse_time
    if key == 'crop':
        return crop_options(parent, files)
    if key in {'pdf_merge', 'images_pdf'}:
        return order_options(parent, files, TOOL_MAP[key].label)
    explanations = {
        'image_compress': '保留原格式。JPEG / WebP 降低编码质量；PNG 可减少颜色数量，保留透明背景。原文件不会覆盖。',
        'pdf_compress': '保留可选择的文字、图形和页面布局。均衡 / 强力模式降低大图的分辨率和质量；无损模式只整理文件结构。',
        'pdf_split': '每页保存为一份 PDF，或指定分段。例如 1-3,5,7-9 会输出三份 PDF。对多份文件使用相同页码范围。',
        'rotate': '对所选图片应用相同的旋转方向。GIF / WebP 动画保留各帧。',
        'mirror': '水平镜像相当于左右翻转；垂直镜像相当于上下翻转。',
        'frame': '输入截取时间，输出一张 PNG。秒数、分:秒、时:分:秒均可；多份视频使用相同时间。',
        'audio': '提取视频中的音轨。没有音轨的视频会提示无法提取。',
        'video_compress': '输出 MP4，保留画面比例和声音。已压缩的视频不一定会进一步变小。',
    }
    if key not in explanations:
        return {}
    dialog = OptionsDialog(parent, TOOL_MAP[key].label, explanations[key])
    choice = tk.StringVar()
    if key == 'image_compress':
        quality = tk.IntVar(value=80)
        value = tk.StringVar(value='质量 80')
        ttk.Label(dialog.body, textvariable=value).pack(anchor='w')
        scale = tk.Scale(dialog.body, from_=40, to=95, orient='horizontal', variable=quality, length=400, command=lambda v: value.set('质量 ' + str(round(float(v)))))
        scale.pack(fill='x')
        lossy = tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog.body, text='PNG 允许减少颜色以减小体积（可能略损细节）', variable=lossy).pack(anchor='w', pady=8)
        collect = lambda: {'quality': quality.get(), 'lossy': lossy.get()}
    elif key in {'rotate', 'mirror', 'pdf_compress', 'video_compress', 'audio'}:
        choices = {
            'rotate': [('顺时针 90°', 90), ('逆时针 90°', -90), ('旋转 180°', 180)],
            'mirror': [('左右翻转', 'horizontal'), ('上下翻转', 'vertical')],
            'pdf_compress': [('均衡：适合一般分享', 'balanced'), ('强力：进一步压缩大图', 'strong'), ('无损：保留图片质量', 'lossless')],
            'video_compress': [('均衡：体积与画质兼顾', 28), ('画质优先', 23), ('体积优先', 32)],
            'audio': [('MP3', 'mp3'), ('WAV', 'wav'), ('FLAC', 'flac'), ('M4A', 'm4a')],
        }[key]
        choice.set(str(choices[0][1]))
        for label, value in choices:
            ttk.Radiobutton(dialog.body, text=label, variable=choice, value=str(value)).pack(anchor='w', pady=4)
        field = {'rotate': 'angle', 'mirror': 'direction', 'pdf_compress': 'level', 'video_compress': 'crf', 'audio': 'format'}[key]
        collect = lambda: {field: int(choice.get()) if key in {'rotate', 'video_compress'} else choice.get()}
    else:
        choice.set('0' if key == 'frame' else '')
        ttk.Entry(dialog.body, textvariable=choice, width=48).pack(fill='x')
        if key == 'pdf_split':
            counts = []
            for source in files:
                with open_pdf(source) as document:
                    counts.append(len(document))
            ttk.Label(dialog.body, text='文件页数：' + '、'.join(map(str, counts)) + '；留空表示逐页拆分。', wraplength=480).pack(anchor='w', pady=8)
            collect = lambda: {'ranges': choice.get()}
        else:
            collect = lambda: {'time': choice.get()}
    def apply():
        try:
            options = collect()
            if key == 'pdf_split':
                for count in counts:
                    page_groups(options['ranges'], count)
            elif key == 'frame':
                parse_time(options['time'])
            dialog.finish(options)
        except ValueError as error:
            messagebox.showerror('请检查输入', str(error), parent=dialog.window)
    dialog.confirm.configure(command=apply)
    return dialog.wait()

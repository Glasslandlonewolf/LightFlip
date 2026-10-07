from pathlib import Path
import os
import subprocess
import tempfile

IMAGES = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tif', 'tiff', 'gif'}
AUDIO = {'mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'}
VIDEO = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'flv'}
DOCUMENTS = {'pdf', 'docx', 'pptx', 'xlsx', 'xls', 'html', 'htm', 'txt', 'md', 'csv', 'json', 'xml', 'epub'}
IMAGE_TARGETS = ('png', 'jpg', 'webp', 'bmp', 'tiff', 'gif')
AUDIO_TARGETS = ('mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a')
VIDEO_TARGETS = ('mp4', 'webm', 'mov', 'avi', 'mkv', 'wmv', 'flv')
OFFICE_INPUTS = {'docx', 'pptx', 'xlsx', 'xls'}

def normalized_format(ext):
    return {'jpeg': 'jpg', 'tif': 'tiff'}.get(ext.lower(), ext.lower())

def document_has_pages(path):
    ext = Path(path).suffix.lower()[1:]
    return ext == 'pdf' or (ext in OFFICE_INPUTS and office_available(ext))

def conversion_route(path, target):
    """Use explicit, meaningful routes, without lossy image/text cycles."""
    ext = normalized_format(Path(path).suffix[1:])
    target = normalized_format(target)
    if ext == target:
        return None
    if ext in IMAGES and target in {*IMAGE_TARGETS, 'pdf', 'docx', 'pptx', 'md', 'txt'}:
        return 'direct'
    if ext in AUDIO and target in AUDIO_TARGETS:
        return 'direct'
    if ext in VIDEO and target in {*VIDEO_TARGETS, *AUDIO_TARGETS}:
        return 'direct'
    if ext not in DOCUMENTS:
        return None
    if target in {'md', 'txt', 'docx', 'pptx'}:
        return 'direct'
    if ext == 'pdf' and target in IMAGE_TARGETS:
        return 'pdf-images'
    if target == 'pdf' or target in IMAGE_TARGETS:
        if ext in OFFICE_INPUTS:
            return 'office-pdf' if office_available(ext) else None
        if office_available('docx'):
            return 'text-word-pdf'
    return None

def formats(path):
    candidates = (*IMAGE_TARGETS, 'pdf', 'docx', 'pptx', 'md', 'txt', *VIDEO_TARGETS, *AUDIO_TARGETS)
    return [target for target in candidates if conversion_route(path, target)]

def office_available(ext):
    import winreg
    app = 'Word' if ext == 'docx' else 'PowerPoint' if ext == 'pptx' else 'Excel'
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, app + '.Application\\CLSID'):
            return True
    except OSError:
        return False

def convert(source, target_format, mode='pages', progress=None):
    src = Path(source).resolve()
    target_format = normalized_format(target_format)
    if not src.is_file():
        raise ValueError('文件不存在，或拖入的是文件夹。')
    if target_format not in formats(src):
        raise ValueError('这个文件不支持所选格式。')
    ext = src.suffix.lower()[1:]
    route = conversion_route(src, target_format)
    with tempfile.TemporaryDirectory(prefix='.fileflip-', dir=src.parent) as folder:
        temp = Path(folder) / ('output.' + target_format)
        work = Path(folder)
        if route in {'pdf-images', 'office-pdf', 'text-word-pdf'}:
            pdf = src
            if route != 'pdf-images':
                pdf = work / 'intermediate.pdf'
                if route == 'text-word-pdf':
                    from office_export import export_office
                    document = work / 'intermediate.docx'
                    export_office(src, document, 'docx', 'text')
                    office_pdf(document, pdf, 'docx')
                else:
                    office_pdf(src, pdf, ext)
            if target_format in IMAGE_TARGETS:
                outputs = pdf_images(pdf, work, target_format)
                return [publish(p, src.parent, src.stem + f'-第{index+1}页', target_format) for index, p in enumerate(outputs)]
            temp = pdf
        elif target_format in {'docx', 'pptx'}:
            from office_export import export_office
            if ext in OFFICE_INPUTS and document_has_pages(src) and mode in {'pages', 'layout', 'ocr'}:
                pdf = work / 'intermediate.pdf'
                office_pdf(src, pdf, ext)
                export_office(pdf, temp, target_format, mode, progress=progress)
            else:
                export_office(src, temp, target_format, mode, progress=progress)
        elif target_format in {'txt','md'} and (ext in IMAGES or ext=='pdf'):
            from office_export import extract_text
            temp.write_text(extract_text(src,progress),encoding='utf-8')
        elif ext in IMAGES:
            from PIL import Image, ImageOps
            with Image.open(src) as original:
                image = ImageOps.exif_transpose(original)
                if target_format in {'gif', 'webp'} and getattr(original, 'is_animated', False):
                    from PIL import ImageSequence
                    frames, durations = [], []
                    for frame in ImageSequence.Iterator(original):
                        frames.append(frame.convert('RGBA'))
                        durations.append(frame.info.get('duration', 100))
                    frames[0].save(temp, save_all=True, append_images=frames[1:], duration=durations, loop=original.info.get('loop', 0))
                else:
                    save_image(image, temp, target_format)
        elif ext in AUDIO | VIDEO:
            import imageio_ffmpeg
            command = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-i', str(src)]
            if target_format in AUDIO:
                command += ['-vn']
            else:
                video_codec, audio_codec, sample_rate = {
                    'mp4': ('libx264', 'aac', '44100'),
                    'mov': ('libx264', 'aac', '44100'),
                    'mkv': ('libx264', 'aac', '44100'),
                    'webm': ('libvpx-vp9', 'libopus', '48000'),
                    'avi': ('mpeg4', 'libmp3lame', '44100'),
                    'wmv': ('wmv2', 'wmav2', '44100'),
                    'flv': ('libx264', 'aac', '44100'),
                }[target_format]
                command += ['-c:v', video_codec, '-pix_fmt', 'yuv420p', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:a', audio_codec, '-ar', sample_rate]
                if target_format in {'avi', 'wmv'}:
                    command += ['-ac', '2']
            command += ['-y', str(temp)]
            result = subprocess.run(command, capture_output=True, creationflags=0x08000000)
            if result.returncode:
                raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-1200:])
        else:
            if ext in {'txt', 'md'}:
                text = src.read_text(encoding='utf-8-sig')
            else:
                from office_export import extract_text
                text = extract_text(src,progress)
                if not text.strip():
                    raise ValueError('没有提取到文字。扫描件可能需要 OCR。')
            temp.write_text(text, encoding='utf-8')
        return [publish(temp, src.parent, src.stem, target_format)]

def save_image(image, output, fmt):
    from PIL import Image
    if fmt in {'jpg', 'pdf', 'bmp'}:
        rgba = image.convert('RGBA')
        background = Image.new('RGB', image.size, 'white')
        background.paste(rgba, mask=rgba.getchannel('A'))
        image = background
    elif fmt == 'gif':
        image = image.convert('RGBA')
    image.save(output, quality=95)

def pdf_images(src, folder, fmt):
    import pypdfium2 as pdfium
    outputs = []
    with pdfium.PdfDocument(str(src)) as document:
        if not len(document):
            raise ValueError('PDF 没有页面。')
        for index in range(len(document)):
            page = document[index]
            bitmap = None
            try:
                width, height = page.get_size()
                # Bound large drawing sizes while retaining ordinary-page quality.
                bitmap = page.render(scale=min(2, 4000/max(width, height)))
                output = folder / f'page-{index+1}.{fmt}'
                save_image(bitmap.to_pil(), output, fmt)
                outputs.append(output)
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
    return outputs

def publish(temp, folder, stem, ext):
    index = 0
    while True:
        dest = folder / (stem + (f'-{index}' if index else '') + '.' + ext)
        try:
            os.rename(temp, dest)  # Windows refuses an existing destination.
            return dest
        except FileExistsError:
            index += 1

def office_pdf(src, dst, ext):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = document = None
    collection = None
    previous_settings = {}
    try:
        if ext == 'docx':
            collection = 'Documents'
            app = win32com.client.DispatchEx('Word.Application')
            previous_settings['DisplayAlerts'] = app.DisplayAlerts
            previous_settings['AutomationSecurity'] = app.AutomationSecurity
            app.DisplayAlerts = 0
            app.AutomationSecurity = 3
            document = app.Documents.Open(str(src), ReadOnly=True)
            document.ExportAsFixedFormat(str(dst), 17)
        elif ext == 'pptx':
            collection = 'Presentations'
            app = win32com.client.DispatchEx('PowerPoint.Application')
            previous_settings['AutomationSecurity'] = app.AutomationSecurity
            app.AutomationSecurity = 3
            document = app.Presentations.Open(str(src), ReadOnly=True, WithWindow=False)
            document.SaveAs(str(dst), 32)
        else:
            collection = 'Workbooks'
            app = win32com.client.DispatchEx('Excel.Application')
            previous_settings['DisplayAlerts'] = app.DisplayAlerts
            previous_settings['AutomationSecurity'] = app.AutomationSecurity
            app.DisplayAlerts = False
            app.AutomationSecurity = 3
            document = app.Workbooks.Open(str(src), UpdateLinks=0, ReadOnly=True)
            document.ExportAsFixedFormat(0, str(dst))
    finally:
        if document is not None:
            try:
                if ext == 'pptx':
                    document.Close()
                else:
                    document.Close(SaveChanges=False)
            except Exception:
                # Cleanup must not replace an export error or close other files
                # in an Office instance that DispatchEx may have reused.
                pass
        if app is not None:
            try:
                remaining = getattr(app, collection).Count
            except Exception:
                remaining = None
            if remaining == 0:
                try:
                    app.Quit()
                except Exception:
                    pass
            else:
                for property_name, value in previous_settings.items():
                    try:
                        setattr(app, property_name, value)
                    except Exception:
                        pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

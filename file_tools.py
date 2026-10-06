"""Local image, PDF and video tools. Originals are never overwritten."""
from pathlib import Path
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from core import IMAGES, VIDEO, normalized_format, publish


@dataclass(frozen=True)
class Tool:
    key: str
    label: str
    kind: str
    minimum: int = 1


TOOLS = (
    Tool('crop', '图片裁剪', 'image'),
    Tool('image_compress', '图片压缩', 'image'),
    Tool('privacy', '清除隐私信息', 'image'),
    Tool('half', '缩小 50%', 'image'),
    Tool('rotate', '旋转', 'image'),
    Tool('mirror', '镜像', 'image'),
    Tool('grayscale', '黑白', 'image'),
    Tool('images_pdf', '多图合并 PDF', 'image', 2),
    Tool('pdf_compress', 'PDF 压缩', 'pdf'),
    Tool('pdf_split', 'PDF 拆分', 'pdf'),
    Tool('pdf_merge', 'PDF 合并', 'pdf', 2),
    Tool('ocr', 'OCR 提取文字', 'pdf'),
    Tool('video_compress', '视频压缩', 'video'),
    Tool('720p', '视频转 720p', 'video'),
    Tool('mute', '视频静音', 'video'),
    Tool('audio', '提取音频', 'video'),
    Tool('frame', '视频截帧', 'video'),
)
TOOL_MAP = {tool.key: tool for tool in TOOLS}


def available_tools(files):
    if not files:
        return []
    extensions = {Path(f).suffix.lower()[1:] for f in files}
    kind = ('image' if extensions <= IMAGES else 'video' if extensions <= VIDEO
            else 'pdf' if extensions == {'pdf'} else None)
    return [tool for tool in TOOLS if (tool.kind == kind or (tool.key=='ocr' and kind=='image')) and len(files) >= tool.minimum]


def tool_runtime():
    local = Path(__file__).resolve().parent
    if (local / 'tools-venv/Scripts/python.exe').is_file() or (local / 'ocr-runtime/python.exe').is_file():
        return local
    return Path(os.environ['LOCALAPPDATA']) / 'Programs/LightFlip'


def ai_job(job, work, progress):
    runtime = tool_runtime()
    interpreter = runtime / 'tools-venv/Scripts/python.exe'
    if not interpreter.is_file():
        interpreter = runtime / 'ocr-runtime/python.exe'
    if not interpreter.is_file():
        raise RuntimeError('OCR 组件未安装，请修复轻转安装。')
    request = work / 'job.json'
    response = work / 'result.json'
    request.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['OMP_NUM_THREADS'] = '4'
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    command = [str(interpreter), '-I', '-X', 'utf8', str(Path(__file__).with_name('ai_worker.py')), str(request), str(response)]
    # Line events only; model diagnostics go to a private temporary log.
    with (work / 'ai.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log,
                                   text=True, encoding='utf-8', env=env, creationflags=0x08000000)
        for line in process.stdout:
            try:
                event = json.loads(line)
                if 'progress' in event:
                    progress(event['progress'])
            except (ValueError, TypeError):
                pass
        code = process.wait()
    if not response.is_file():
        raise RuntimeError('本地识别组件未能启动。请重新打开轻转后再试。')
    result = json.loads(response.read_text(encoding='utf-8'))
    if code or 'error' in result:
        raise RuntimeError(result.get('error', '本地识别未完成。'))
    return result


def execute_tool(files, key, options=None, progress=None):
    files = [Path(f).resolve() for f in files]
    options = options or {}
    progress = progress or (lambda message: None)
    if key not in {tool.key for tool in available_tools(files)}:
        raise ValueError('所选文件不适用这个工具。合并需要至少两个同类文件。')
    for source in files:
        if not source.is_file():
            raise ValueError(f'文件不存在：{source.name}')
    outputs, notes, errors = [], [], []
    if key in {'pdf_merge', 'images_pdf'}:
        with tempfile.TemporaryDirectory(prefix='.lightflip-', dir=files[0].parent) as folder:
            target = Path(folder) / 'merged.pdf'
            merge_files(files, target, key, progress)
            outputs.append(publish(target, files[0].parent, files[0].stem + '-合并', 'pdf'))
        return outputs, notes, errors
    for index, source in enumerate(files):
        progress(f'正在{TOOL_MAP[key].label} · {index+1}/{len(files)}：{source.name}')
        try:
            with tempfile.TemporaryDirectory(prefix='.lightflip-', dir=source.parent) as folder:
                work = Path(folder)
                if key=='ocr':
                    from pdf_ocr import extract_document_text
                    temporary=work/'ocr.txt'
                    temporary.write_text(extract_document_text(source,progress)+'\n',encoding='utf-8')
                    destinations=[(temporary,source.stem+'-OCR文字')]
                    note='已识别文字，按页输出 TXT。'
                elif TOOL_MAP[key].kind == 'image':
                    temporary, note = image_tool(source, work, key, options)
                    destinations = [(temporary, source.stem + '-' + TOOL_MAP[key].label)]
                elif TOOL_MAP[key].kind == 'pdf':
                    destinations, note = pdf_tool(source, work, key, options, progress)
                else:
                    temporary, note = video_tool(source, work, key, options)
                    destinations = [(temporary, source.stem + '-' + TOOL_MAP[key].label)]
                for temporary, stem in destinations:
                    outputs.append(publish(temporary, source.parent, stem, temporary.suffix[1:]))
                if note:
                    notes.append(source.name + '：' + note)
        except Exception as error:
            errors.append(source.name + ': ' + str(error))
    return outputs, notes, errors


def size_note(source, result):
    before, after = source.stat().st_size, result.stat().st_size
    if after < before:
        return f'体积减小 {(1-after/max(1,before))*100:.1f}%'
    return '原文件已较精简，本次没有进一步减小体积。'


def image_tool(source, work, key, options):
    from PIL import Image, ImageOps, ImageSequence
    fmt = normalized_format(source.suffix[1:])
    with Image.open(source) as original:
        animated = getattr(original, 'is_animated', False)
        # Preserve GIF/WebP animations and all TIFF pages for these pixel operations.
        all_frames = getattr(original, 'n_frames', 1) > 1 and fmt in {'gif', 'webp', 'tiff'}
        frames, durations = [], []
        for frame in ImageSequence.Iterator(original):
            image = ImageOps.exif_transpose(frame).convert('RGBA')
            if key == 'crop':
                x0, y0, x1, y1 = options['box']
                if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                    raise ValueError('裁剪范围无效。')
                left, top = int(x0*image.width), int(y0*image.height)
                right, bottom = min(image.width, max(left+1, round(x1*image.width))), min(image.height, max(top+1, round(y1*image.height)))
                image = image.crop((left, top, right, bottom))
            elif key == 'half':
                image = image.resize((max(1, image.width//2), max(1, image.height//2)), Image.Resampling.LANCZOS)
            elif key == 'rotate':
                image = image.transpose({90: Image.Transpose.ROTATE_270, -90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180}[int(options.get('angle', 90))])
            elif key == 'mirror':
                image = ImageOps.flip(image) if options.get('direction') == 'vertical' else ImageOps.mirror(image)
            elif key == 'grayscale':
                alpha = image.getchannel('A')
                image = ImageOps.grayscale(image).convert('RGBA')
                image.putalpha(alpha)
            # Copy only pixels; exclude EXIF, GPS, comments, XMP and ICC metadata.
            clean = Image.new('RGBA', image.size)
            clean.paste(image)
            frames.append(clean)
            durations.append(frame.info.get('duration', 100))
            if not all_frames:
                break
        destination = work / ('output.' + fmt)
        quality = int(options.get('quality', 80)) if key == 'image_compress' else 95
        if fmt in {'jpg', 'bmp'}:
            rgb = Image.new('RGB', frames[0].size, 'white')
            rgb.paste(frames[0], mask=frames[0].getchannel('A'))
            frames = [rgb]
        elif fmt == 'png' and key == 'image_compress' and options.get('lossy', True):
            frames = [frames[0].quantize(colors=256 if quality >= 75 else 128, method=Image.Quantize.FASTOCTREE)]
        save_options = {'quality': quality, 'optimize': True}
        if fmt == 'webp' and key != 'image_compress':
            save_options['lossless'] = True
        if fmt == 'tiff':
            save_options = {'compression': 'tiff_deflate'}
        if all_frames:
            save_options.update(save_all=True, append_images=frames[1:])
            if animated:
                save_options.update(duration=durations, loop=original.info.get('loop', 0))
                if fmt == 'gif':
                    save_options['disposal'] = 2
        frames[0].save(destination, **save_options)
        note = ''
        if key == 'image_compress':
            if destination.stat().st_size >= source.stat().st_size:
                shutil.copyfile(source, destination)
            note = size_note(source, destination)
        return destination, note


def open_pdf(path):
    import pymupdf as fitz
    document = fitz.open(path)
    if document.needs_pass:
        document.close()
        raise ValueError('PDF 需要密码，请先解锁后再处理。')
    if not len(document):
        document.close()
        raise ValueError('PDF 没有页面。')
    return document


def merge_files(files, destination, key, progress):
    import pymupdf as fitz
    from PIL import Image, ImageOps, ImageSequence
    with fitz.open() as merged:
        for index, source in enumerate(files):
            progress(f'正在合并 · {index+1}/{len(files)}：{source.name}')
            if key == 'pdf_merge':
                with open_pdf(source) as document:
                    merged.insert_pdf(document, links=True, annots=True, widgets=True)
            else:
                with Image.open(source) as original:
                    # An animated input contributes its first frame; TIFF contributes all pages.
                    for frame in ImageSequence.Iterator(original):
                        image = ImageOps.exif_transpose(frame).convert('RGBA')
                        rgb = Image.new('RGB', image.size, 'white')
                        rgb.paste(image, mask=image.getchannel('A'))
                        data = io.BytesIO()
                        rgb.save(data, 'PNG')
                        page = merged.new_page(width=image.width*.75, height=image.height*.75)
                        page.insert_image(page.rect, stream=data.getvalue())
                        if getattr(original, 'is_animated', False):
                            break
        merged.save(destination, garbage=4, deflate=True)


def page_groups(expression, count):
    if not expression or expression.strip().lower() in {'all', '每页'}:
        return [[number] for number in range(count)]
    groups = []
    for token in expression.replace('，', ',').split(','):
        token = token.strip()
        if not re.fullmatch(r'\d+(?:\s*-\s*\d+)?', token):
            raise ValueError('页码请写成 1-3,5,7-9；每段保存为一个 PDF。')
        numbers = [int(n) for n in re.split(r'\s*-\s*', token)]
        first, last = numbers[0], numbers[-1]
        if not 1 <= first <= last <= count:
            raise ValueError(f'页码超出范围，文件共有 {count} 页。')
        groups.append(list(range(first-1, last)))
    return groups


def pdf_tool(source, work, key, options, progress):
    import pymupdf as fitz
    destinations, note = [], ''
    with open_pdf(source) as document:
        if key == 'pdf_split':
            for index, pages in enumerate(page_groups(options.get('ranges', ''), len(document))):
                destination = work / f'part-{index+1}.pdf'
                with fitz.open() as part:
                    part.insert_pdf(document, from_page=pages[0], to_page=pages[-1], links=True, annots=True, widgets=True)
                    part.save(destination, garbage=4, deflate=True)
                name = f'第{pages[0]+1}页' if len(pages) == 1 else f'第{pages[0]+1}-{pages[-1]+1}页'
                destinations.append((destination, source.stem + '-' + name))
        elif key == 'pdf_compress':
            destination = work / 'output.pdf'
            level = options.get('level', 'balanced')
            if level != 'lossless':
                from PIL import Image
                quality, bound = (80, 2400) if level == 'balanced' else (60, 1600)
                seen = set()
                for page in document:
                    for item in page.get_images(full=True):
                        xref, mask = item[:2]
                        if xref in seen or mask or item[4] not in {1, 3}:
                            continue  # Keep transparency and CMYK profiles intact.
                        seen.add(xref)
                        extracted = document.extract_image(xref)
                        if not extracted or len(extracted['image']) < 20000:
                            continue
                        try:
                            with Image.open(io.BytesIO(extracted['image'])) as image:
                                if 'A' in image.getbands() or 'transparency' in image.info:
                                    continue
                                image = image.convert('RGB')
                                image.thumbnail((bound, bound), Image.Resampling.LANCZOS)
                                data = io.BytesIO()
                                image.save(data, 'JPEG', quality=quality, optimize=True)
                                if len(data.getvalue()) < len(extracted['image']):
                                    page.replace_image(xref, stream=data.getvalue())
                        except (OSError, ValueError):
                            continue
            # Retain native text, links, annotations and form fields.
            document.save(destination, garbage=4, deflate=True)
            if destination.stat().st_size >= source.stat().st_size:
                shutil.copyfile(source, destination)
            note = size_note(source, destination)
            destinations.append((destination, source.stem + '-压缩'))
        elif key == 'ocr':
            images = []
            for number, page in enumerate(document):
                progress(f'正在准备文字识别 · 第 {number+1}/{len(document)} 页')
                scale = min(300/72, 4000/max(page.rect.width, page.rect.height))
                output = work / f'ocr-{number+1}.png'
                page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(output)
                images.append(str(output))
            result = ai_job({'kind': 'ocr', 'files': images}, work, progress)
            if not any(page['text'].strip() for page in result['items']):
                raise ValueError('未识别到文字。请检查 PDF 是否空白或分辨率过低。')
            text = '\n\n'.join(f'===== 第 {index+1} 页 =====\n' + page['text'] for index, page in enumerate(result['items']))
            destination = work / 'ocr.txt'
            destination.write_text(text + '\n', encoding='utf-8')
            destinations.append((destination, source.stem + '-OCR文字'))
            note = '已识别中英文文字，按页输出 TXT。'
    return destinations, note


def parse_time(value):
    value = str(value).strip()
    if re.fullmatch(r'\d+(?:\.\d+)?', value):
        seconds = float(value)
    elif re.fullmatch(r'\d+:\d{1,2}(?::\d{1,2})?(?:\.\d+)?', value):
        parts = [float(n) for n in value.split(':')]
        if any(n >= 60 for n in parts[1:]):
            raise ValueError('分钟和秒应小于 60。')
        seconds = sum(n*60**index for index, n in enumerate(reversed(parts)))
    else:
        raise ValueError('时间请填秒数、分:秒或时:分:秒，例如 12.5 或 01:20。')
    if seconds < 0 or seconds > 8640000:
        raise ValueError('截帧时间超出范围。')
    return seconds


def video_tool(source, work, key, options):
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    fmt = 'png' if key == 'frame' else options.get('format', 'mp3') if key == 'audio' else source.suffix[1:] if key == 'mute' else 'mp4'
    if key == 'audio' and fmt not in {'mp3', 'wav', 'flac', 'm4a'}:
        raise ValueError('请选择 MP3、WAV、FLAC 或 M4A。')
    destination = work / ('output.' + fmt)
    command = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y']
    if key == 'frame':
        command += ['-ss', str(parse_time(options.get('time', '0')))]
    command += ['-i', str(source)]
    if key == 'frame':
        command += ['-map', '0:v:0', '-frames:v', '1', '-update', '1']
    elif key == 'mute':
        command += ['-map', '0:v:0', '-c:v', 'copy', '-an']
    elif key == 'audio':
        command += ['-map', '0:a:0', '-vn']
        if fmt in {'mp3', 'm4a'}:
            command += ['-b:a', '192k']
    else:
        command += ['-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libx264', '-preset', 'medium', '-crf', str(options.get('crf', 28) if key == 'video_compress' else 22), '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart']
        if key == '720p':
            command += ['-vf', "scale=w='if(gte(iw,ih),min(iw,1280),min(iw,720))':h='if(gte(iw,ih),min(ih,720),min(ih,1280))':force_original_aspect_ratio=decrease:force_divisible_by=2,pad=ceil(iw/2)*2:ceil(ih/2)*2"]
        else:
            command += ['-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2']
    command.append(str(destination))
    result = subprocess.run(command, capture_output=True, creationflags=0x08000000)
    if result.returncode or not destination.is_file() or destination.stat().st_size == 0:
        diagnostic = result.stderr.decode('utf-8', errors='replace')
        if key == 'audio' and ('matches no streams' in diagnostic or 'Stream map' in diagnostic):
            raise ValueError('这个视频没有音轨，无法提取音频。')
        if key == 'frame' and not destination.is_file():
            raise ValueError('这个时间没有画面，请填写视频时长内的时间。')
        raise RuntimeError('视频处理未完成：' + diagnostic[-600:])
    return destination, size_note(source, destination) if key == 'video_compress' else ''

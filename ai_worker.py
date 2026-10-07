"""Isolated CPU-only OCR worker (Python 3.12)."""
import json
from pathlib import Path
import sys

# Portable Python uses an isolated search path; sibling modules stay local.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def progress(message):
    print(json.dumps({'progress': message}, ensure_ascii=False), flush=True)


def main(job):
    items = []
    if job['kind'] == 'ocr_text':
        import cv2
        import numpy as np
        from ocr_layout import make_engine,recognize
        progress('正在加载本地文字识别组件…')
        engine=make_engine()
        for index,source in enumerate(job['files']):
            progress(f'正在识别文字 · 第 {index+1}/{len(job["files"])} 页')
            image=cv2.imdecode(np.fromfile(source,dtype='uint8'),cv2.IMREAD_COLOR)
            if image is None:raise ValueError('无法读取文字识别图片。')
            lines=recognize(engine,image)
            items.append({'text':'\n'.join(row['text'] for row in lines),'lines':lines})
    elif job['kind'] == 'ocr_layout':
        from ocr_layout import make_engine, process_layout
        progress('正在加载本地文字识别和版式重建组件…')
        engine = make_engine()
        for index, source in enumerate(job['files']):
            progress(f'正在重建文字并分离图片 · 第 {index+1}/{len(job["files"])} 页')
            items.append(process_layout(engine, source, job['output_dir']))
    elif job['kind'] == 'ocr':
        import cv2
        import numpy as np
        from ocr_layout import make_engine,recognize
        progress('正在加载本地中英文识别模型…')
        engine = make_engine()
        for index, source in enumerate(job['files']):
            progress(f'正在识别文字 · 第 {index+1}/{len(job["files"])} 页')
            image=cv2.imdecode(np.fromfile(source,dtype='uint8'),cv2.IMREAD_COLOR)
            if image is None:raise ValueError('无法读取文字识别图片。')
            lines=recognize(engine,image)
            text = '\n'.join(row['text'] for row in lines)
            items.append({'text': text})
    else:
        raise ValueError('未知的识别任务。')
    return {'items': items}


if __name__ == '__main__':
    request, response = map(Path, sys.argv[1:3])
    try:
        response.write_text(json.dumps(main(json.loads(request.read_text(encoding='utf-8'))), ensure_ascii=False), encoding='utf-8')
    except Exception as error:
        response.write_text(json.dumps({'error': str(error)}, ensure_ascii=False), encoding='utf-8')
        sys.exit(1)

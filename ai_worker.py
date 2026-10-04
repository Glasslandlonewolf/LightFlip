"""Isolated CPU-only OCR worker (Python 3.12)."""
import json
from pathlib import Path
import sys


def progress(message):
    print(json.dumps({'progress': message}, ensure_ascii=False), flush=True)


def main(job):
    items = []
    if job['kind'] == 'ocr':
        from rapidocr import RapidOCR
        progress('正在加载本地中英文识别模型…')
        engine = RapidOCR()
        for index, source in enumerate(job['files']):
            progress(f'正在识别文字 · 第 {index+1}/{len(job["files"])} 页')
            result = engine(source)
            text = '\n'.join(result.txts or [])
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


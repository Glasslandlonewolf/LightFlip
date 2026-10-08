"""Local OCR geometry and conservative text-background reconstruction.

Runs in the OCR environment; no cloud services or additional model downloads.
Recognised glyphs become text; bounded artwork becomes independent raster assets.
"""
from pathlib import Path
import math
import os
import re
import sys
from functools import lru_cache


def make_engine():
    from rapidocr import RapidOCR
    return RapidOCR(params={'Global.log_level': 'error',
                           'Global.max_side_len': 4000,
                           'Det.limit_side_len': 1400,
                           'Det.limit_type': 'max'})


def overlap(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    area = max(0, min(ax1, bx1)-max(ax0, bx0))*max(0, min(ay1, by1)-max(ay0, by0))
    return area/max(1, min((ax1-ax0)*(ay1-ay0), (bx1-bx0)*(by1-by0)))


def recognize(engine, image):
    """Full page plus overlapping tiles, retaining original image coordinates."""
    import numpy as np
    height, width = image.shape[:2]
    candidates = []
    windows = [(0, 0, width, height)]
    if max(width, height) > 1800:
        tile, step = 1400, 1160
        xs = list(range(0, max(1, width-tile+1), step))
        ys = list(range(0, max(1, height-tile+1), step))
        xs.append(max(0, width-tile))
        ys.append(max(0, height-tile))
        windows += [(x, y, min(width, x+tile), min(height, y+tile))
                    for y in sorted(set(ys)) for x in sorted(set(xs))]
    for n, (x, y, right, bottom) in enumerate(windows):
        result = engine(image[y:bottom, x:right], use_det=True, use_cls=True,
                        use_rec=True, text_score=0.50)
        if result.boxes is None:
            continue
        for points, text, score in zip(result.boxes, result.txts, result.scores):
            if not text.strip():
                continue
            points = np.asarray(points, dtype=float)
            bx0, by0 = points.min(axis=0)
            bx1, by1 = points.max(axis=0)
            # A tile-boundary fragment must never replace a complete page line.
            if n and ((x and bx0 < 8) or (y and by0 < 8) or
                      (right < width and bx1 > right-x-8) or
                      (bottom < height and by1 > bottom-y-8)):
                continue
            points += [x, y]
            bbox = [float(v) for v in (*points.min(axis=0), *points.max(axis=0))]
            candidates.append({'text': text.strip(), 'confidence': float(score),
                               'points': points.tolist(), 'bbox': bbox, 'tile': bool(n)})
    # Duplicate detections from different scales describe the same line.
    # Keep the more confident complete string; ordering does not change layout.
    candidates.sort(key=lambda row: (row['confidence'], len(row['text'])), reverse=True)
    lines = []
    for row in candidates:
        if any(overlap(row['bbox'], previous['bbox']) > .60 for previous in lines):
            continue
        lines.append(row)
    # Page-wide resizing can lose thin, pale characters on long lines. Retry
    # uncertain lines at their original resolution without running detection.
    for row in lines:
        if row['confidence'] >= .93:
            continue
        from rapidocr.utils.process_img import get_rotate_crop_image
        crop = get_rotate_crop_image(image, np.asarray(row['points'], dtype=np.float32))
        for variant in (crop, 255-crop):
            result = engine(variant, use_det=False, use_cls=False, use_rec=True)
            if result.txts and result.scores and float(result.scores[0]) > row['confidence']+.02:
                row['text'] = result.txts[0].strip()
                row['confidence'] = float(result.scores[0])
            if row['confidence'] >= .93:
                break
    return sorted(lines, key=lambda row: (round(row['bbox'][1]/12), row['bbox'][0]))


@lru_cache(maxsize=1)
def fonts():
    if sys.platform=='darwin':
        from PIL import ImageFont
        roots=[Path('/System/Library/Fonts'),Path('/Library/Fonts'),Path.home()/'Library/Fonts']
        # Some macOS releases store Chinese font collections in system assets.
        assets=Path('/System/Library/AssetsV2')
        if assets.is_dir():roots+=list(assets.glob('com_apple_MobileAsset_Font*'))
        candidates=[]
        for root in roots:
            for path in sorted(root.rglob('*')) if root.is_dir() else []:
                if path.suffix.lower() not in {'.ttf','.ttc','.otf'}:continue
                try:
                    family,style=ImageFont.truetype(str(path),20).getname()
                    if not any(name in family.lower() for name in ('arial','times','helvetica','avenir','georgia','palatino','pingfang','songti','heiti','hiragino','noto')):continue
                    candidates.append((family,str(path),'bold' in style.lower(),'italic' in style.lower() or 'oblique' in style.lower()))
                except (OSError,ValueError):pass
        return candidates
    root = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    choices = [('Arial', 'arial.ttf', False, False), ('Arial', 'arialbd.ttf', True, False),
               ('Times New Roman', 'times.ttf', False, False), ('Times New Roman', 'timesbd.ttf', True, False),
               ('Calibri', 'calibri.ttf', False, False), ('Calibri', 'calibrib.ttf', True, False),
               ('Cambria', 'cambria.ttc', False, False), ('Cambria', 'cambriab.ttf', True, False),
               ('Microsoft YaHei', 'msyh.ttc', False, False), ('Microsoft YaHei', 'msyhbd.ttc', True, False),
               ('SimSun', 'simsun.ttc', False, False), ('Times New Roman', 'timesi.ttf', False, True),
               ('Arial', 'ariali.ttf', False, True)]
    choices += [('Georgia','georgia.ttf',False,False),('Georgia','georgiab.ttf',True,False),
                ('Garamond','gara.ttf',False,False),('Garamond','garabd.ttf',True,False),
                ('Trebuchet MS','trebuc.ttf',False,False),('Trebuchet MS','trebucbd.ttf',True,False),
                ('Arial Narrow','arialn.ttf',False,False),('Arial Narrow','arialnb.ttf',True,False)]
    return [(family, str(root/file), bold, italic) for family, file, bold, italic in choices if (root/file).is_file()]


def dominant_color(pixels):
    import numpy as np
    if not len(pixels):
        return np.array([255, 255, 255], dtype=np.float32)
    quantized = pixels.astype(int)//16
    values, counts = np.unique(quantized, axis=0, return_counts=True)
    selected = np.all(quantized == values[counts.argmax()], axis=1)
    return np.median(pixels[selected], axis=0)


def fit_font(text, glyph_mask, font_choices):
    """Compare local installed fonts to glyph height, width and silhouette."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    ys, xs = np.nonzero(glyph_mask)
    if not len(xs):
        return {'family': 'Arial', 'size_px': 16., 'bold': False, 'italic': False, 'fit': 0.}
    target = glyph_mask[ys.min():ys.max()+1, xs.min():xs.max()+1]
    th, tw = target.shape
    options = []
    chinese = bool(re.search(r'[\u3400-\u9fff]', text))
    for family, path, bold, italic in font_choices:
        if chinese and family not in {'Microsoft YaHei', 'SimSun'} and not any(token in family.lower() for token in ('pingfang','songti','heiti','hiragino','cjk','han')):
            continue
        base = ImageFont.truetype(path, 100)
        box = base.getbbox(text)
        size = max(5, min(400, 100*th/max(1, box[3]-box[1])))
        font = ImageFont.truetype(path, max(5, round(size)))
        box = font.getbbox(text)
        rw, rh = max(1, box[2]-box[0]), max(1, box[3]-box[1])
        rendered = Image.new('L', (rw, rh))
        ImageDraw.Draw(rendered).text((-box[0], -box[1]), text, font=font, fill=255)
        mask = cv2.resize(np.asarray(rendered), (tw, th), interpolation=cv2.INTER_AREA) > 100
        union = np.logical_or(mask, target > 0).sum()
        shape_fit = np.logical_and(mask, target > 0).sum()/max(1, union)
        width_fit = math.exp(-abs(math.log(rw/max(1, tw))))
        options.append((shape_fit*.70+width_fit*.30, family, size, bold, italic, rw/max(1, tw)))
    if not options:
        return {'family': 'Arial', 'size_px': float(th*1.25), 'bold': False, 'italic': False, 'fit': 0.}
    score, family, size, bold, italic, ratio = max(options)
    if ratio > 1.12 and score < .55:
        # Texture around small captions can inflate the measured glyph height.
        # Prefer the recognised line's width to an oversized substituted font.
        size /= ratio
        ratio = 1.
    # DrawingML run spacing corrects the small width mismatch without raster text.
    return {'family': family, 'size_px': size, 'bold': bold, 'italic': italic,
            'fit': score, 'width_ratio': ratio}


def reconstruct(image, lines, background_path):
    """Remove recognised glyphs, preserving circles, lines and picture edges."""
    import cv2
    import numpy as np
    from PIL import Image
    cleaned = image.copy()
    font_choices = fonts()
    output_lines = []
    height, width = image.shape[:2]
    for line in lines:
        x0, y0, x1, y1 = line['bbox']
        # OCR rectangles can cut through a descender by several pixels. A
        # little context preserves its complete silhouette before removal.
        # Single numbers retain the strict crop that protects numbered circles.
        context_pad=max(2,min(12,round((y1-y0)*.08))) if len(line['text'])>3 else 0
        # The top is deliberately kept at the detector boundary: extending it
        # can pick up the preceding line's descenders in a tightly set heading.
        ix0, iy0 = max(0, int(x0)-context_pad), max(0, int(y0))
        ix1, iy1 = min(width, math.ceil(x1)+context_pad), min(height, math.ceil(y1)+context_pad)
        crop = image[iy0:iy1, ix0:ix1]
        if not crop.size:
            continue
        ch, cw = crop.shape[:2]
        border = np.concatenate((crop[:2].reshape(-1,3), crop[-2:].reshape(-1,3),
                                 crop[:, :2].reshape(-1,3), crop[:, -2:].reshape(-1,3)))
        # Detectors sometimes include the edge of a numbered circle. Its
        # centre panel, not the exterior border, is the text's background.
        centre=crop[max(0,ch//6):max(1,ch-ch//6),max(0,cw//10):max(1,cw-cw//10)]
        bg = dominant_color(centre.reshape(-1,3))
        distance = np.linalg.norm(crop.astype(float)-bg, axis=2)
        flat=float((distance<12).mean())>.65
        mask = (distance > max(28, float(np.percentile(distance,90))*.30)).astype('uint8')*255
        # Exclude long background lines and large components crossing the box.
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        glyphs = np.zeros_like(mask)
        for label in range(1, count):
            left, top, bw, bh, area = stats[label]
            if area < max(3, ch*.10) or (bw > ch*4 and bh < ch*.18):
                continue
            if area > ch*cw*.70:
                continue
            touches_edge=left==0 or top==0 or left+bw==cw or top+bh==ch
            ordinary_letter=flat and len(line['text'])>3 and bw<ch*2.5 and bh>ch*.30 and area<ch*cw*.18
            if touches_edge and not ordinary_letter:
                continue
            glyphs[labels == label] = 255
        yy, xx = np.nonzero(glyphs)
        if len(xx) < 4:
            continue
        fg = dominant_color(crop[glyphs > 0])
        style = fit_font(line['text'], glyphs, font_choices)
        glyph_box = [ix0+int(xx.min()), iy0+int(yy.min()), ix0+int(xx.max())+1, iy0+int(yy.max())+1]
        line.update(style=style, color=[int(v) for v in fg], glyph_bbox=glyph_box,
                    background_color=[int(v) for v in bg])
        # A dilation covers antialiasing but does not blank a rectangular area.
        radius = max(1,min(3,round(ch/35)))
        lx0,ly0=max(0,ix0-radius),max(0,iy0-radius)
        lx1,ly1=min(width,ix1+radius),min(height,iy1+radius)
        local=np.zeros((ly1-ly0,lx1-lx0),dtype='uint8')
        local[iy0-ly0:iy1-ly0,ix0-lx0:ix1-lx0]=glyphs
        local = cv2.dilate(local, np.ones((radius*2+1,radius*2+1),dtype='uint8'))
        # On flat template panels, exact background fill beats inpainting halos.
        line['background_flat'] = bool(flat)
        region=cleaned[ly0:ly1,lx0:lx1]
        if flat:
            region[local > 0] = np.round(bg).astype('uint8')
        else:
            # Surrounding context is needed when the scan has texture or a photo.
            # Texture can join a letter to the crop edge; repair the detected
            # text region to prevent leaving the old raster letters underneath.
            if len(line['text'])>10:
                local[iy0-ly0:iy1-ly0,ix0-lx0:ix1-lx0]=255
            pad=max(8,ch//2)
            px0,py0=max(0,lx0-pad),max(0,ly0-pad)
            px1,py1=min(width,lx1+pad),min(height,ly1+pad)
            context=np.zeros((py1-py0,px1-px0),dtype='uint8')
            context[ly0-py0:ly1-py0,lx0-px0:lx1-px0]=local
            cleaned[py0:py1,px0:px1]=cv2.inpaint(cleaned[py0:py1,px0:px1],context,3,cv2.INPAINT_TELEA)
        output_lines.append(line)
    # Repeated labels should not alternate fonts due to subpixel rasterisation.
    for line in output_lines:
        peers=[other for other in output_lines if other['text']==line['text'] and
               .85<(other['glyph_bbox'][3]-other['glyph_bbox'][1])/
               max(1,line['glyph_bbox'][3]-line['glyph_bbox'][1])<1.18]
        if len(peers)>1:
            best=max(peers,key=lambda other:other['style']['fit'])
            line['style']=dict(best['style'])
    numbers=[row for row in output_lines if re.fullmatch(r'\d{2}',row['text'])]
    for row in numbers:
        peers=[other for other in numbers if .72<(other['glyph_bbox'][3]-other['glyph_bbox'][1])/
               max(1,row['glyph_bbox'][3]-row['glyph_bbox'][1])<1.4]
        if len(peers)>=3:
            family=max({p['style']['family'] for p in peers},key=lambda name:sum(p['style']['family']==name for p in peers))
            best=max((p for p in peers if p['style']['family']==family),key=lambda p:p['style']['fit'])
            row['style']=dict(best['style'])
    ok,data=cv2.imencode('.png',cleaned)
    if not ok:
        raise ValueError('无法保存重建背景。')
    data.tofile(str(background_path))
    return output_lines


def process_layout(engine, source, output_dir):
    import cv2
    import numpy as np
    image = cv2.imdecode(np.fromfile(str(source),dtype='uint8'),cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('无法读取 OCR 页面图片。')
    lines = recognize(engine, image)
    background = Path(output_dir)/('clean-'+Path(source).stem+'.png')
    lines = reconstruct(image, lines, background)
    from image_layout import separate_artwork
    lines, images, shapes = separate_artwork(image, lines, background, output_dir)
    # All colors in the protocol are RGB, not OpenCV's BGR.
    for line in lines:
        line['color'] = line['color'][::-1]
        line['background_color'] = line['background_color'][::-1]
    return {'width':image.shape[1], 'height':image.shape[0], 'lines':lines,
            'background':str(background), 'text':'\n'.join(row['text'] for row in lines),
            'images':images, 'shapes':shapes}

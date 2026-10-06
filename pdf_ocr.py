"""Detect image PDFs and create native PowerPoint text from local OCR."""
from pathlib import Path
import io
import math
import tempfile


def image_page(page):
    """Full image pages may still contain a native footer or watermark."""
    images=page.get_image_info()
    if not images:
        return False
    if not page.get_text().strip():
        return True
    area=page.rect.width*page.rect.height
    return any(max(0,min(page.rect.x1,item['bbox'][2])-max(page.rect.x0,item['bbox'][0]))*
               max(0,min(page.rect.y1,item['bbox'][3])-max(page.rect.y0,item['bbox'][1]))/area>=.50
               for item in images)


def prepare_pages(src, folder, progress, force=False):
    import pymupdf as fitz
    from file_tools import ai_job
    sources, numbers, sizes = [], [], []
    with fitz.open(src) as document:
        if document.needs_pass:
            raise ValueError('PDF 有密码保护，请先解锁。')
        for index, original in enumerate(document):
            with fitz.open() as normalized:
                normalized.insert_pdf(document,from_page=index,to_page=index)
                page=normalized[0]
                page.remove_rotation()
                if not force and not image_page(page):
                    continue
                progress(f'正在准备图片页文字识别 · 第 {index+1}/{len(document)} 页')
                factor=min(3,3200/max(page.rect.width,page.rect.height))
                image=folder/f'page-{index+1}.png'
                page.get_pixmap(matrix=fitz.Matrix(factor,factor),alpha=False,annots=False).save(image)
                sources.append(str(image))
                numbers.append(index)
                sizes.append((page.rect.width,page.rect.height))
    if not sources:
        return {}
    result=ai_job({'kind':'ocr_layout','files':sources,'output_dir':str(folder)},folder,progress)
    pages={}
    for index,size,item in zip(numbers,sizes,result['items']):
        if item['lines']:
            item['page_width'],item['page_height']=size
            pages[index]=item
        else:
            progress(f'第 {index+1} 页未识别到文字，保留原页面图片。')
    if force and not pages:
        raise ValueError('没有识别到可编辑文字。请检查清晰度，或选择“保留页面外观”。')
    return pages


def text_objects(page):
    """Translate OCR geometry into the native layout writer's object protocol."""
    from PIL import ImageFont
    from ocr_layout import fonts
    factor=page['page_width']/page['width']
    choices=fonts()
    objects=[]
    for index,row in enumerate(page['lines']):
        x0,y0,x1,y1=row['glyph_bbox']
        style=row['style']
        size=style['size_px']*factor
        match=next((path for family,path,bold,italic in choices if
                    (family,bold,italic)==(style['family'],style['bold'],style['italic'])),None)
        top=y0*factor
        if match:
            font=ImageFont.truetype(match,max(5,round(style['size_px'])))
            box=font.getbbox(row['text'])
            ascent,_=font.getmetrics()
            top-=(box[1]-ascent)*factor+size*.92
        red,green,blue=row['color']
        objects.append({'kind':'text','bbox':tuple(v*factor for v in (x0,y0,x1,y1)),
                        'origin':(x0*factor,top+size*.92),'size':size,
                        'font':style['family'],'flags':(16 if style['bold'] else 0)|(2 if style['italic'] else 0),
                        'color':(red<<16)|(green<<8)|blue,'text':row['text'],'seq':index,
                        'width_ratio':style.get('width_ratio',1),
                        'angle':math.degrees(math.atan2(row['points'][1][1]-row['points'][0][1],
                                                       row['points'][1][0]-row['points'][0][0]))})
    return objects


def add_ocr_slide(presentation,page,scale,ox,oy):
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR,MSO_AUTO_SIZE
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.oxml.ns import qn
    slide=presentation.slides.add_slide(presentation.slide_layouts[6])
    image=slide.shapes.add_picture(page['background'],Pt(ox),Pt(oy),
                                  width=Pt(page['page_width']*scale),height=Pt(page['page_height']*scale))
    image.name='图形背景（OCR 文字已移除）'
    image.line.fill.background()
    factor=page['page_width']/page['width']*scale
    for row in page['lines']:
        x0,y0,x1,y1=row['glyph_bbox']
        style=row['style']
        # Font bbox and ascender determine the glyph's actual baseline. Textbox
        # coordinates are not the same as the black-pixel bounds in a scan.
        font_size=style['size_px']*factor
        from PIL import ImageFont
        from ocr_layout import fonts
        match=next((p for family,p,bold,italic in fonts() if (family,bold,italic)==
                    (style['family'],style['bold'],style['italic'])),None)
        top_offset=0
        if match:
            font=ImageFont.truetype(match,max(5,round(style['size_px'])))
            box=font.getbbox(row['text'])
            ascent,_=font.getmetrics()
            top_offset=(box[1]-ascent)*factor+font_size*.92
        top=oy+y0*factor-top_offset
        width=max((x1-x0)*factor+font_size*.18,font_size)
        height=max((y1-y0)*factor+font_size*.6,font_size*1.6)
        shape=slide.shapes.add_textbox(Pt(ox+x0*factor),Pt(top),Pt(width),Pt(height))
        shape.name=f'OCR 可编辑文字（置信度 {row["confidence"]:.0%}）'
        shape.rotation=math.degrees(math.atan2(row['points'][1][1]-row['points'][0][1],
                                              row['points'][1][0]-row['points'][0][0]))
        frame=shape.text_frame
        frame.margin_left=frame.margin_right=frame.margin_top=frame.margin_bottom=0
        frame.word_wrap=False
        frame.auto_size=MSO_AUTO_SIZE.NONE
        frame.vertical_anchor=MSO_ANCHOR.TOP
        paragraph=frame.paragraphs[0]
        paragraph.space_before=paragraph.space_after=Pt(0)
        run=paragraph.add_run()
        run.text=''.join(c for c in row['text'] if c in '\t\n' or ord(c)>=32)
        run.font.name=style['family']
        run.font.size=Pt(max(1,font_size))
        run.font.bold=style['bold']
        run.font.italic=style['italic']
        run.font.color.rgb=RGBColor(*row['color'])
        props=run._r.get_or_add_rPr()
        for name in ['a:ea','a:cs']:
            element=OxmlElement(name)
            element.set('typeface',style['family'])
            props.append(element)
        # Keep each line's original width even when substituting the font.
        spacing=(x1-x0)*(1-style.get('width_ratio',1))*factor/max(1,len(row['text'])-1)
        props.set('spc',str(round(max(-font_size*.15,min(font_size*.3,spacing))*100)))
    slide.notes_slide.notes_text_frame.text=(
        '本页文字由本机 OCR 重建，可直接编辑。图片和装饰保留为背景；字体为相近匹配。'
        '识别结果和复杂背景修复请校对。\n'+page['text'])
    return slide


def image_pdf(src,dst):
    """Normalise oriented/multipage images without uploading or JPEG recompression."""
    import pymupdf as fitz
    from PIL import Image,ImageOps,ImageSequence
    with fitz.open() as document,Image.open(src) as original:
        for frame in ImageSequence.Iterator(original):
            image=ImageOps.exif_transpose(frame).convert('RGBA')
            factor=min(.75,2800/max(image.size))
            page=document.new_page(width=image.width*factor,height=image.height*factor)
            stream=io.BytesIO()
            image.save(stream,'PNG')
            page.insert_image(page.rect,stream=stream.getvalue())
            if Path(src).suffix.lower() not in {'.tif','.tiff'}:
                break
        document.save(dst)


def layout_with_ocr(src,dst,fmt='pptx',progress=None,force=False):
    from pdf_layout import layout_slides,layout_word
    with tempfile.TemporaryDirectory(prefix='.lightflip-ocr-',dir=Path(dst).resolve().parent) as temp:
        folder=Path(temp)
        progress=progress or (lambda message:None)
        if Path(src).suffix.lower()!='.pdf':
            normalised=folder/'images.pdf'
            image_pdf(src,normalised)
            src=normalised
        pages=prepare_pages(src,folder,progress,force)
        if fmt=='pptx':layout_slides(src,dst,ocr_pages=pages,progress=progress)
        else:layout_word(src,dst,ocr_pages=pages,progress=progress)


def extract_document_text(src,progress=None):
    """Use native PDF text when present, local OCR otherwise; images always OCR."""
    import pymupdf as fitz
    from file_tools import ai_job
    progress=progress or (lambda message:None)
    with tempfile.TemporaryDirectory(prefix='.lightflip-text-',dir=Path(src).resolve().parent) as temp:
        folder=Path(temp)
        if Path(src).suffix.lower()!='.pdf':
            normalized=folder/'images.pdf'
            image_pdf(src,normalized)
            src=normalized
        texts,sources,numbers=[],[],[]
        with fitz.open(src) as document:
            if document.needs_pass:raise ValueError('PDF 有密码保护，请先解锁。')
            for index,page in enumerate(document):
                text=page.get_text().strip()
                texts.append(text)
                if image_page(page):
                    factor=min(3,3200/max(page.rect.width,page.rect.height))
                    file=folder/f'page-{index+1}.png'
                    page.get_pixmap(matrix=fitz.Matrix(factor,factor),alpha=False).save(file)
                    sources.append(str(file))
                    numbers.append(index)
        if sources:
            result=ai_job({'kind':'ocr_text','files':sources},folder,progress)
            for index,item in zip(numbers,result['items']):
                # Preserve small native annotations that were too faint to OCR.
                recognised=item['text']
                import re
                normalize=lambda value:re.sub(r'\W','',value).lower()
                native=[line for line in texts[index].splitlines()
                        if normalize(line) and normalize(line) not in normalize(recognised)]
                texts[index]='\n'.join([recognised,*native]).strip()
        if not any(text.strip() for text in texts):
            raise ValueError('未识别到文字。请检查文件清晰度或选择保留页面外观。')
        return '\n\n'.join(f'===== 第 {index+1} 页 =====\n'+text for index,text in enumerate(texts))

"""Windows integration check: run with the prepared main Python environment."""
from pathlib import Path
import sys,zipfile,json,io
import xml.etree.ElementTree as ET
import pymupdf as fitz
from PIL import Image,ImageDraw,ImageFont
import tempfile,atexit,argparse
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from core import convert
from file_tools import execute_tool
from office_export import extract_text
from pdf_ocr import image_pdf
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime',type=Path,help='Optional prepared directory containing tools-venv or ocr-runtime')
args=parser.parse_args()
if args.runtime:
    import file_tools
    file_tools.tool_runtime=lambda:args.runtime.resolve()
temporary=tempfile.TemporaryDirectory(prefix='.lightflip-test-',dir=root)
atexit.register(temporary.cleanup)
folder=Path(temporary.name)
image=folder/'中文图片.png'
canvas=Image.new('RGB',(1200,675),'#f8f6f0')
draw=ImageDraw.Draw(canvas)
draw.text((60,65),'轻转文字识别测试',font=ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc',48),fill='#56302d')
draw.text((60,165),'Editable conversion 2026',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',42),fill='#56302d')
canvas.save(image)
def text(path):
    if path.suffix in {'.txt','.md'}:return path.read_text(encoding='utf-8')
    with zipfile.ZipFile(path) as z:
        return '\n'.join(''.join(n.text or '' for n in ET.fromstring(z.read(name)).iter()
                               if n.tag.endswith('}t')) for name in z.namelist()
                         if name=='word/document.xml' or name.startswith('ppt/slides/slide') and name.endswith('.xml'))
def assert_chinese(path):assert '轻转文字识别测试' in text(path),str(path)
image_pdf(image,folder/'scan.pdf')
with fitz.open(folder/'scan.pdf') as doc:
    doc[0].insert_text((30,470),'Native footer survives',fontsize=12)
    page=doc.new_page(width=600,height=400)
    page.insert_text((40,80),'Native PDF text stays editable',fontsize=24)
    doc.save(folder/'mixed.pdf')
for fmt,mode in [('docx','layout'),('pptx','ocr'),('txt','pages'),('md','pages')]:
    print('Mixed PDF ->',fmt,mode,flush=True)
    path=convert(folder/'mixed.pdf',fmt,mode=mode)[0]
    assert_chinese(path)
    assert 'Native PDF text stays editable' in text(path)
    assert 'Native footer survives' in text(path)
with fitz.open(folder/'scan.pdf') as doc:
    doc[0].set_rotation(90)
    doc.save(folder/'rotated.pdf')
assert_chinese(convert(folder/'rotated.pdf','pptx',mode='layout')[0])
with Image.open(image) as original:
    original.save(folder/'two-pages.tiff',save_all=True,append_images=[original.copy()])
path=convert(folder/'two-pages.tiff','pptx',mode='layout')[0]
from pptx import Presentation
assert len(Presentation(path).slides)==2
assert_chinese(path)
results,notes,errors=execute_tool([image],'ocr')
assert not errors,errors
assert_chinese(results[0])
with fitz.open(folder/'scan.pdf') as doc:
    doc.save(folder/'locked.pdf',encryption=fitz.PDF_ENCRYPT_AES_256,user_pw='test')
try:extract_text(folder/'locked.pdf')
except ValueError as error:assert '密码' in str(error)
else:raise AssertionError('Encrypted PDF should report password protection')
print('PASS: mixed PDF, native footer, force OCR, Chinese TXT/MD/Word/PPT, rotation, multipage TIFF, OCR tool, password handling',flush=True)

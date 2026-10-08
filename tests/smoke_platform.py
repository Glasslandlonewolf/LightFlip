"""Exercise Mac-specific boundaries on any host without changing global OS state."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
import platform_support as support

with patch.object(support,'os',SimpleNamespace(name='posix')):
    assert support.process_options()=={}
with patch.object(core,'os',SimpleNamespace(name='posix')):
    with patch.object(support,'libreoffice',return_value=None):
        assert not core.office_available('docx')
    with patch.object(support,'libreoffice',return_value='/Applications/LibreOffice.app/Contents/MacOS/soffice'):
        assert core.office_available('pptx')
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1],prefix='.platform-test-') as directory:
        folder=Path(directory)
        original=folder/'sample.txt';original.write_text('original')
        staged=folder/'temporary.txt';staged.write_text('new')
        output=core.publish(staged,folder,'sample','txt')
        assert output!=original and original.read_text()=='original' and output.read_text()=='new'
        staged.write_text('retry')
        import shutil
        with patch.object(shutil,'copyfileobj',side_effect=OSError('disk full')):
            try:core.publish(staged,folder,'failed','txt')
            except OSError:pass
            else:raise AssertionError('Expected failed copy')
        assert staged.read_text()=='retry' and not (folder/'failed.txt').exists()

with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1],prefix='.platform-test-') as directory:
    folder=Path(directory);source=folder/'input.docx';source.write_bytes(b'private original')
    destination=folder/'output.pdf';commands=[]
    def render(command,**kwargs):
        commands.append(command)
        out=Path(command[command.index('--outdir')+1])/'input.pdf'
        out.write_bytes(b'%PDF-test')
        return SimpleNamespace(returncode=0)
    with patch.object(support,'libreoffice',return_value='soffice'),patch.object(support.subprocess,'run',side_effect=render):
        support.office_to_pdf(source,destination)
    assert destination.read_bytes()==b'%PDF-test' and source.read_bytes()==b'private original'
    assert any(c.startswith('-env:UserInstallation=') for c in commands[0])
    assert not list(folder.glob('.lightflip-office-*'))
print('PASS: Mac Office route, isolated rendering, original preservation and failed-copy cleanup')

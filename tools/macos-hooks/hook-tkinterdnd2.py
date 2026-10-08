"""Include only this Mac's tkdnd binaries, avoiding incompatible architectures."""
import platform
from pathlib import Path
import tkinterdnd2

package=Path(tkinterdnd2.__file__).parent
native='osx-arm64' if platform.machine()=='arm64' else 'osx-x64'
datas=[]
for name in (native,native+'-tcl9'):
    folder=package/'tkdnd'/name
    if folder.is_dir():
        for file in folder.rglob('*'):
            if file.is_file():
                datas.append((str(file),str(Path('tkinterdnd2/tkdnd')/name/file.relative_to(folder).parent)))
hiddenimports=['tkinterdnd2.TkinterDnD']

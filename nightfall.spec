# Build the desktop tool with only the public runtime assets and example.
from pathlib import Path
import sys

root = Path(SPECPATH)
data = [(str(root/'assets'), 'assets')]
for name in ['house.json', 'house-day.png', 'house-night.png', 'layout.png']:
    data.append((str(root/'examples'/name), 'examples'))
# The render cache and export manifest fingerprint these source files at runtime.
for name in ['renderer.py', 'effects.py', 'animation.py', 'atmosphere.py', 'routes.py', 'tone.py', 'spectacle.py']:
    data.append((str(root/'nightfall'/name), 'nightfall'))

a = Analysis(
    [str(root/'nightfall/__main__.py')],
    pathex=[str(root)],
    binaries=[],
    datas=data,
    hiddenimports=['nightfall.export', 'nightfall.smoke_test', 'nightfall.parallel_render'],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtPdf', 'cv2', 'PIL'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='nightfall',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=True,
          hide_console='hide-early' if sys.platform == 'win32' else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='nightfall')

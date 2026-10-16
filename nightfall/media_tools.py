"""Allow Windows FFmpeg executables next to the app, without editing PATH."""
import shutil
import sys
from pathlib import Path
from .model import ROOT

def executable(name):
    directories = [ROOT/'bin']
    if getattr(sys, 'frozen', False):
        directories.insert(0, Path(sys.executable).resolve().parent/'bin')
    for directory in directories:
        for filename in [name+'.exe',name]:
            bundled=directory/filename
            if bundled.is_file():return str(bundled)
    return shutil.which(name)

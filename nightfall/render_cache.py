"""Keep a video tied to its exact house geometry, effects and bitmap assets."""
import hashlib,json
from pathlib import Path
from .model import ROOT, WORK_ROOT

SOURCES=['renderer.py','effects.py','animation.py','atmosphere.py','routes.py','tone.py','spectacle.py']

def folder(data):
    digest=hashlib.sha256(json.dumps({k:data.get(k) for k in ['regions','exclusions','effects','output']},sort_keys=True).encode())
    for name in SOURCES:
        digest.update((ROOT/'nightfall'/name).read_bytes().replace(b'\r\n',b'\n'))
    for image in sorted((ROOT/'assets').rglob('*.png')):
        digest.update(image.relative_to(ROOT).as_posix().encode());digest.update(image.read_bytes())
    return WORK_ROOT/'renders'/digest.hexdigest()[:20]

def video(data,mode):
    return folder(data)/f'halloween-{mode}-800x1280.mp4'


def exported_video(data,mode,mapping_path):
    """Find completed portable shows only when geometry and renderer match."""
    if not mapping_path:return None
    base=Path(mapping_path).resolve().parent;key=folder(data).name
    for directory in (base/'videos',base):
        try:
            manifest=json.loads((directory/'render-manifest.json').read_text())
        except (OSError,ValueError):continue
        if manifest.get('cache_key')!=key or not manifest.get('full_loop'):continue
        movie=directory/f'halloween-{mode}-800x1280.mp4'
        if movie.name in manifest.get('files',[]) and movie.is_file():return movie
    return None

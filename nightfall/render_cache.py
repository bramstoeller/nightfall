"""Keep a video tied to its exact house geometry, effects and bitmap assets."""
import hashlib,json
from .model import ROOT, WORK_ROOT

SOURCES=['renderer.py','effects.py','animation.py','atmosphere.py','routes.py','tone.py']

def folder(data):
    digest=hashlib.sha256(json.dumps({k:data.get(k) for k in ['regions','exclusions','effects','output']},sort_keys=True).encode())
    for name in SOURCES:
        digest.update((ROOT/'nightfall'/name).read_bytes())
    for image in sorted((ROOT/'assets').rglob('*.png')):
        digest.update(image.relative_to(ROOT).as_posix().encode());digest.update(image.read_bytes())
    return WORK_ROOT/'renders'/digest.hexdigest()[:20]

def video(data,mode):
    return folder(data)/f'halloween-{mode}-800x1280.mp4'

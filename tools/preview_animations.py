"""Export six complete 5-second/60-fps character loops and a video contact sheet."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile, ZIP_STORED

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from nightfall.spectacle import actor_frame, ACTOR_FPS, ACTOR_FRAMES, ACTOR_SECONDS
from nightfall.media_tools import executable

CHARACTERS=['skeleton','bat','owl','spider','pumpkin','wisp']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'dist/previews/expanded-effects')
    parser.add_argument('--frames',action='store_true',help='Keep all 1,800 transparent PNG frames and a ZIP.')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    movie=args.out/'characters-5s-60fps.mp4'
    if movie.exists():parser.error(f'{movie} already exists; choose a new output folder.')
    ffmpeg=executable('ffmpeg')
    if not ffmpeg:parser.error('FFmpeg is required for the preview video.')
    app=QApplication.instance() or QApplication([])
    command=[ffmpeg,'-v','error','-f','rawvideo','-pixel_format','rgb24','-video_size','768x576',
             '-framerate',str(ACTOR_FPS),'-i','pipe:0','-an','-c:v','libx264','-threads','2',
             '-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(movie)]
    if args.frames:
        for name in CHARACTERS:(args.out/'frames'/name).mkdir(parents=True,exist_ok=True)
    process=subprocess.Popen(command,stdin=subprocess.PIPE)
    try:
        for index in range(ACTOR_FRAMES):
            sheet=QImage(768,576,QImage.Format_RGB888);sheet.fill(QColor('#10131c'))
            p=QPainter(sheet)
            for i,name in enumerate(CHARACTERS):
                image=actor_frame(name,index)
                x,y=(i%3)*256,(i//3)*288
                p.drawImage(x,y,image);p.setPen(QColor('#e6edf8'))
                p.drawText(QRectF(x,y+252,256,32),Qt.AlignCenter,name+' · 60 fps')
                if args.frames and not image.save(str(args.out/'frames'/name/f'{index:03}.png')):
                    raise OSError('Could not save an animation frame.')
            p.end();process.stdin.write(sheet.constBits())
        process.stdin.close()
        if process.wait():raise RuntimeError('FFmpeg could not encode the animation preview.')
    except BaseException:
        process.kill();process.wait();raise
    manifest={'fps':ACTOR_FPS,'seconds':ACTOR_SECONDS,'frames_per_character':ACTOR_FRAMES,
              'characters':CHARACTERS,'png_frames':bool(args.frames),'video':movie.name}
    (args.out/'animation-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if args.frames:
        with ZipFile(args.out/'character-loops-300-frames.zip','w',ZIP_STORED) as archive:
            archive.write(args.out/'animation-manifest.json','animation-manifest.json')
            for path in sorted((args.out/'frames').rglob('*.png')):archive.write(path,path.relative_to(args.out))
    print(f'Created {len(CHARACTERS)} × {ACTOR_FRAMES} frames at {ACTOR_FPS} fps: {movie}')


if __name__=='__main__':main()

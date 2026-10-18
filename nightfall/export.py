#!/usr/bin/env python3
"""Frame-exact offline rendering from a saved 800×1280 portrait projector map."""
import argparse, hashlib, json, os, subprocess, sys, tempfile, time
from contextlib import nullcontext
from multiprocessing import freeze_support
from pathlib import Path
if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from nightfall import model
from nightfall.renderer import render
from nightfall.effects import STYLES
from nightfall.media_tools import executable
from nightfall.parallel_render import FrameRenderer
from nightfall.render_cache import SOURCES, folder as cache_folder

class RenderCancelled(Exception):
    pass

def check_cancel(cancel_file):
    if cancel_file is not None and cancel_file.exists():raise RenderCancelled()

def encode(data,show,dest,seconds,overwrite,start=0,cancel_file=None,workers=None,frame_renderer=None):
    check_cancel(cancel_file)
    if dest.exists() and not overwrite: raise FileExistsError(f'{dest.name} already exists. Choose an empty output folder or use --overwrite.')
    fps=data['output']['fps'];frames=round(seconds*fps);tmp=dest.with_name(dest.stem+'.partial.mp4')
    if tmp.exists() and not overwrite: raise FileExistsError(f'{tmp.name} already exists; remove it only if a previous render was interrupted.')
    program=executable('ffmpeg') or 'ffmpeg'
    print('Encoder: CPU · libx264',flush=True)
    context=nullcontext(frame_renderer) if frame_renderer is not None else FrameRenderer(data,workers)
    with context as renderer, tempfile.TemporaryFile() as log:
        print(f'Render workers: {renderer.workers}',flush=True)
        cpus=getattr(os,'process_cpu_count',os.cpu_count)() or 1
        encoder_threads=max(1,min(2,cpus-renderer.workers-1))
        print(f'Encoder threads: {encoder_threads}',flush=True)
        cmd=[program,'-hide_banner','-loglevel','error','-y','-filter_threads','1','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{model.WIDTH}x{model.HEIGHT}','-framerate',str(fps),'-i','pipe:0','-an','-c:v','libx264','-threads',str(encoder_threads),'-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(tmp)]
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log,creationflags=flags)
        try:
            began=time.monotonic()
            for i,pixels in enumerate(renderer.frames(show,frames,fps,start,lambda:check_cancel(cancel_file))):
                check_cancel(cancel_file)
                proc.stdin.write(pixels)
                if i==0 or (i+1)%300==0 or i==frames-1:
                    speed=(i+1)/max(.01,time.monotonic()-began)
                    print(f'{show}: {(i+1)/frames:.0%} · {speed:.1f} renderfps',flush=True)
            check_cancel(cancel_file);proc.stdin.close();code=proc.wait()
            if code:
                log.seek(0);raise RuntimeError(log.read().decode(errors='replace')[-6000:])
            check_cancel(cancel_file);os.replace(tmp,dest);print(f'Done: {dest}',flush=True)
        except BaseException:
            if proc.poll() is None:proc.kill();proc.wait()
            tmp.unlink(missing_ok=True);raise

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mapping',type=Path);ap.add_argument('--out',type=Path,default=Path('videos'));ap.add_argument('--show',choices=[*STYLES,'both'],default='both');ap.add_argument('--seconds',type=float,default=120,help='120 for a complete loop; shorter for previews');ap.add_argument('--overwrite',action='store_true');ap.add_argument('--patterns-only',action='store_true');ap.add_argument('--cancel-file',type=Path,help='Stop cleanly when this file exists.');ap.add_argument('--workers',type=int,help='CPU render workers; defaults to 1–2 depending on available CPUs and memory.');args=ap.parse_args()
    if not 0<args.seconds<=120:ap.error('--seconds must be greater than 0 and at most 120.')
    if args.workers is not None and not 1<=args.workers<=32:ap.error('--workers must be between 1 and 32.')
    if not args.patterns_only and not executable('ffmpeg'):ap.error('FFmpeg is missing. Put ffmpeg.exe in bin or install FFmpeg with libx264 on PATH.')
    check_cancel(args.cancel_file)
    app=QApplication.instance() or QApplication([]);data=model.load(args.mapping);args.out.mkdir(parents=True,exist_ok=True)
    names=['alignment.png','wireframe.png','mapping-used.json','render-manifest.json']+([] if args.patterns_only else [f'halloween-{s}-{model.WIDTH}x{model.HEIGHT}.mp4' for s in (['young','older'] if args.show=='both' else [args.show])])
    if not args.overwrite:
        existing=[n for n in names if (args.out/n).exists()]
        if existing:ap.error('Output already exists: '+', '.join(existing)+'. Choose an empty folder or --overwrite.')
    model.save(data,args.out/'mapping-used.json')
    for mode in ['alignment','wireframe']:
        if not render(data,mode=mode).save(str(args.out/(mode+'.png'))):raise OSError('Could not save PNG.')
    render_workers=0
    if not args.patterns_only:
        with FrameRenderer(data,args.workers) as renderer:
            render_workers=renderer.workers
            for show in ['young','older'] if args.show=='both' else [args.show]:encode(data,show,args.out/f'halloween-{show}-{model.WIDTH}x{model.HEIGHT}.mp4',args.seconds,args.overwrite,cancel_file=args.cancel_file,frame_renderer=renderer)
    raw=(args.out/'mapping-used.json').read_bytes();manifest={'mapping_sha256':hashlib.sha256(raw).hexdigest(),'resolution':[model.WIDTH,model.HEIGHT],'fps':data['output']['fps'],'duration':args.seconds,'full_loop':args.seconds==120,'renderer':'nightfall-coloured-smoke-5','renderer_sha256':hashlib.sha256((model.ROOT/'nightfall/renderer.py').read_bytes()).hexdigest(),'animation_sha256':hashlib.sha256((model.ROOT/'nightfall/animation.py').read_bytes()).hexdigest(),'asset_sha256':{str(p.relative_to(model.ROOT/'assets')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (model.ROOT/'assets').rglob('*.png')},'files':[n for n in names if n!='render-manifest.json']}
    manifest.update(renderer='nightfall-flowing-smoke-cpu',cpu_render_processes=render_workers,encoder='libx264',cache_key=cache_folder(data).name,source_sha256={name:hashlib.sha256((model.ROOT/'nightfall'/name).read_bytes()).hexdigest() for name in SOURCES})
    (args.out/'render-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Keep the mapping and matching alignment pattern with this render.',flush=True)

def run():
    freeze_support()
    try:main()
    except RenderCancelled:print('Render stopped. Completed videos have been kept.',flush=True);sys.exit(130)
    except (ValueError,OSError,RuntimeError) as e:print(f'Error: {e}',file=sys.stderr);sys.exit(1)


if __name__ == "__main__":
    run()

"""Exercise bundled data, the GUI, child rendering and real video playback."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from PySide6.QtWidgets import QApplication
from . import model
from .effects import STYLES
from .gui import MainWindow
from .media_tools import executable
from .renderer import render
from .runtime import render_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--require-bundled-media', action='store_true')
    args = parser.parse_args()
    if args.require_bundled_media:
        os.environ['PATH'] = ''
        expected = Path(sys.executable).resolve().parent/'bin'
        for name in ['ffmpeg', 'ffprobe']:
            program = executable(name)
            assert program and Path(program).resolve().parent == expected, f'{name} must be bundled beside the app'
    app = QApplication.instance() or QApplication([])
    data = model.default_project()
    window = MainWindow(data)
    window.simplify()
    window.preview_check.setChecked(True)
    window.show()
    try:
        app.processEvents()
        for photo in ['day', 'night']:
            window.data['editor_photo'] = photo
            window.read_reference()
            assert not window.reference.isNull(), f'Missing {photo} reference'
        for style in STYLES:
            frame = render(data, 8.03, style)
            assert (frame.width(), frame.height()) == (800, 1280)
        with tempfile.TemporaryDirectory() as output:
            command = [str(model.ROOT/'examples/house.json'), '--out', output]
            has_media = bool(executable('ffmpeg'))
            command += ['--show', 'both', '--seconds', '0.2', '--workers', '2'] if has_media else ['--patterns-only']
            subprocess.run([sys.executable, *render_command(*command)], check=True, timeout=120)
            assert (Path(output)/'render-manifest.json').is_file()
            if has_media:
                video = Path(output)/'halloween-young-800x1280.mp4'
                probe = executable('ffprobe')
                if probe:
                    report = json.loads(subprocess.check_output([
                        probe, '-v', 'error', '-show_entries', 'stream=width,height,r_frame_rate', '-of', 'json', str(video)]))
                    stream = report['streams'][0]
                    assert (stream['width'], stream['height'], stream['r_frame_rate']) == (800, 1280, '60/1')
                received = []
                window.video.frame_ready.connect(lambda frame: received.append(frame.cacheKey()))
                window.play_animation(str(video))
                deadline = time.monotonic()+15
                while len(received)<6 and time.monotonic()<deadline:
                    app.processEvents()
                    time.sleep(.01)
                assert len(set(received))>=6, 'Decoder did not deliver video frames to the GUI'
                assert not window.projector.isVisible(), 'Main-screen preview should keep the projector closed'
                window.stop_video()
        print('Smoke test passed: references, effects, GUI, child rendering and video playback.', flush=True)
    finally:
        window.stop_video()
        window.dirty = False
        window.close()

"""Decode looping MP4s off the UI thread; present the newest complete frame."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QImage
from .model import WIDTH, HEIGHT
from .media_tools import executable


class Decoder(QThread):
    def __init__(self, program, filename, parent):
        super().__init__(parent)
        self.program=program;self.filename=filename
        self.cancelled=threading.Event();self.lock=threading.Lock()
        self.process=None;self.latest=None;self.error=''

    def run(self):
        # Native Qt pixels avoid a separate RGB24 conversion for each screen.
        pixel_format='bgra' if sys.byteorder=='little' else 'argb'
        cmd=[self.program,'-hide_banner','-loglevel','error','-filter_threads','1',
             '-re','-stream_loop','-1','-threads','2','-i',str(self.filename),
             '-an','-vf',f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2',
             '-f','rawvideo','-pix_fmt',pixel_format,'pipe:1']
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        process=None
        try:
            with tempfile.TemporaryFile() as log:
                process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=log,creationflags=flags)
                with self.lock:self.process=process
                if self.cancelled.is_set():process.kill()
                size=WIDTH*HEIGHT*4
                while not self.cancelled.is_set():
                    pixels=process.stdout.read(size)
                    if len(pixels)!=size:break
                    image=QImage(pixels,WIDTH,HEIGHT,WIDTH*4,QImage.Format_RGB32).copy()
                    with self.lock:self.latest=image
                if process.poll() is None:process.kill()
                code=process.wait()
                if code and not self.cancelled.is_set():
                    log.seek(0);self.error=log.read().decode(errors='replace')[-1200:] or 'Video playback failed.'
        except (OSError,ValueError) as exc:
            if not self.cancelled.is_set():self.error=str(exc)
        finally:
            if process is not None:
                if process.poll() is None:process.kill()
                process.wait();process.stdout.close()
            with self.lock:self.process=None

    def take_frame(self):
        with self.lock:
            frame=self.latest;self.latest=None
        return frame

    def cancel(self):
        self.cancelled.set()
        with self.lock:process=self.process
        if process is not None and process.poll() is None:
            try:process.kill()
            except OSError:pass


class VideoPlayer(QObject):
    frame_ready=Signal(QImage)
    failed=Signal(str)
    stopped=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.active=False;self.filename=None;self.decoder=None
        self.timer=QTimer(self);self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(16);self.timer.timeout.connect(self.read_frame)

    def start(self,filename):
        program=executable('ffmpeg')
        if not program:raise RuntimeError('FFmpeg is missing. Put ffmpeg.exe in bin or install FFmpeg on PATH.')
        if not Path(filename).is_file():raise RuntimeError('The selected video does not exist.')
        self.stop();self.filename=Path(filename);self.active=True
        self.decoder=Decoder(program,self.filename,self)
        self.decoder.finished.connect(self.finished)
        self.decoder.start();self.timer.start()

    def read_frame(self):
        if not self.active or self.decoder is None:return
        frame=self.decoder.take_frame()
        if frame is not None:self.frame_ready.emit(frame)

    def finished(self):
        decoder=self.sender()
        if decoder is None or decoder is not self.decoder:return
        self.timer.stop();self.decoder=None
        if self.active:
            self.active=False
            if decoder.error:self.failed.emit(decoder.error)
            self.stopped.emit()
        decoder.deleteLater()

    def stop(self):
        was_active=self.active;self.active=False;self.timer.stop()
        decoder=self.decoder;self.decoder=None
        if decoder is not None:
            decoder.cancel();decoder.wait();decoder.deleteLater()
        if was_active:self.stopped.emit()

"""Run a private VLC instance without piping decoded pixels through Python."""
import os
from pathlib import Path
import shutil
import sys
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal
from .model import ROOT


def find_vlc(preferred=None):
    candidates=[Path(preferred)] if preferred else []
    base=Path(sys.executable).parent if getattr(sys,'frozen',False) else ROOT
    names=('vlc.exe','VLC/vlc.exe','vlc/vlc.exe','bin/vlc.exe') if os.name=='nt' else ('vlc','bin/vlc')
    candidates.extend(base/name for name in names)
    if os.name=='nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\vlc.exe',0,winreg.KEY_READ|view) as key:
                        candidates.append(Path(winreg.QueryValue(key,None).strip('"')))
                except OSError:pass
        for name in ('ProgramW6432','ProgramFiles','ProgramFiles(x86)'):
            if os.environ.get(name):candidates.append(Path(os.environ[name])/'VideoLAN/VLC/vlc.exe')
    program=shutil.which('vlc')
    if program:candidates.append(Path(program))
    return next((str(p.resolve()) for p in candidates if p.is_file()),None)


def vlc_arguments(filename,screen_index):
    if screen_index<0:raise ValueError('Choose a projector display first.')
    # Keep video embedded: VLC's Qt interface selects this fullscreen screen.
    # A private instance avoids forwarding the movie to an existing VLC window.
    return ['--ignore-config','--intf=qt','--no-one-instance','--no-one-instance-when-started-from-file',
            '--embedded-video','--fullscreen',f'--qt-fullscreen-screennumber={screen_index}',
            '--loop','--no-video-title-show','--no-osd','--no-qt-fs-controller',
            '--no-qt-privacy-ask','--no-qt-updates-notif','--no-qt-video-autoresize',
            '--qt-continue=0','--no-qt-recentplay','--no-video-deco',
            '--avcodec-hw=any',str(Path(filename).resolve())]


class VLCPlayer(QObject):
    started=Signal()
    stopped=Signal()
    failed=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.process=None;self.filename=None;self.screen=None;self.program=None;self.log=b''

    @property
    def active(self):return self.process is not None and self.process.state()!=QProcess.NotRunning

    def start(self,filename,screen,screen_index,preferred=None):
        program=find_vlc(preferred)
        if not program:raise RuntimeError('VLC was not found. Install VLC or select vlc.exe using Choose VLC application… .')
        filename=Path(filename).resolve()
        if not filename.is_file():raise RuntimeError('The selected video does not exist.')
        args=vlc_arguments(filename,screen_index)
        self.stop();self.filename=filename;self.screen=screen;self.program=program;self.log=b''
        process=QProcess(self);self.process=process
        process.setProgram(program);process.setArguments(args)
        # A packaged PySide app supplies its own Qt plugin paths. VLC must load
        # its own Qt/plugins instead. Keep all other environment settings.
        env=QProcessEnvironment.systemEnvironment()
        for name in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QT_QPA_PLATFORM','QML2_IMPORT_PATH','QML_IMPORT_PATH'):
            env.remove(name)
        process.setProcessEnvironment(env);process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda:self.read_output(process))
        process.started.connect(self.started)
        process.errorOccurred.connect(lambda error:self.launch_error(process,error))
        process.finished.connect(lambda code,status:self.finished(process,code))
        process.start()

    def read_output(self,process):
        output=bytes(process.readAllStandardOutput())
        if process is self.process:self.log=(self.log+output)[-4000:]

    def launch_error(self,process,error):
        if process is self.process and error==QProcess.FailedToStart:
            self.process=None;message=process.errorString();process.deleteLater()
            self.stopped.emit();self.failed.emit('VLC could not start: '+message)

    def finished(self,process,code):
        if process is not self.process:return
        self.read_output(process);self.process=None;process.deleteLater();self.stopped.emit()
        if code:self.failed.emit('VLC stopped unexpectedly. '+self.log.decode(errors='replace')[-1200:])

    def stop(self):
        process=self.process;self.process=None
        if process is None:return
        # Only this QProcess is ours; never stop other VLC sessions.
        if process.state()!=QProcess.NotRunning:
            process.terminate()
            if not process.waitForFinished(700):process.kill();process.waitForFinished(700)
        process.deleteLater();self.stopped.emit()

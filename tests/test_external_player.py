"""Exercise owned VLC subprocesses, screen arguments and portable show selection."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QProcess,QTime
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from nightfall import model,render_cache
from nightfall.external_player import VLCPlayer,find_vlc,vlc_arguments
from nightfall.gui import MainWindow

APP=QApplication.instance() or QApplication([])


class ExternalPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.movie=self.root/'show with spaces.mp4';self.movie.write_bytes(b'fixture')
        settings=MagicMock();settings.value.side_effect=lambda key,default:default
        self.settings=patch('nightfall.gui.QSettings',return_value=settings);self.settings.start()
        self.program=patch('nightfall.external_player.find_vlc',return_value=sys.executable);self.program.start()
        self.gui_program=patch('nightfall.gui.find_vlc',return_value=sys.executable);self.gui_program.start()
        # Use a real child process to test ownership and lifecycle without VLC
        # or physical projectors on CI. Display arguments have a separate test.
        self.args=patch('nightfall.external_player.vlc_arguments',return_value=['-c','import time; print("ready",flush=True); time.sleep(120)'])
        self.args.start()
        self.w=MainWindow(model.default_project());self.w.simplify();self.w.player_backend='vlc'
        self.warning=patch('nightfall.gui.QMessageBox.warning');self.warning.start()

    def tearDown(self):
        self.w.stop_video();self.w.dirty=False;self.w.close();APP.processEvents()
        self.warning.stop();self.args.stop();self.gui_program.stop();self.program.stop();self.settings.stop();self.temp.cleanup()

    def started(self):
        self.w.play_animation(str(self.movie))
        process=self.w.external_video.process
        self.assertIsNotNone(process)
        self.assertTrue(process.waitForStarted(3000))
        QTest.qWait(30)
        self.assertTrue(self.w.external_video.active)
        return process

    def test_vlc_owns_playback_and_does_not_decode_or_render_hidden_frames(self):
        process=self.started()
        self.assertFalse(self.w.video.active);self.assertIsNone(self.w.video.decoder)
        self.assertEqual(self.w.video_button.text(),'Stop video')
        self.assertIn('VLC',self.w.playback_status.text());self.assertNotIn('fps',self.w.playback_status.text())
        self.assertEqual(self.w.external_video.screen,self.w.screens.currentData())
        self.assertTrue(self.w.projector.blacked_out)
        for name in ('QT_QPA_PLATFORM','QT_PLUGIN_PATH'):
            self.assertFalse(process.processEnvironment().contains(name))
        self.w.playing=True;self.w.mode='young'
        with patch('nightfall.gui.render') as renderer:
            self.w.tick();renderer.assert_not_called()
        self.w.playing=False;self.w.stop_video()
        self.assertFalse(self.w.external_video.active);self.assertIsNone(self.w.external_filename)
        self.assertEqual(process.state(),QProcess.NotRunning)
        self.assertTrue(self.w.projector.blacked_out)

    def test_blackout_stops_only_our_instance_and_on_restarts(self):
        first=self.started();self.w.toggle_projector()
        self.assertFalse(self.w.external_video.active);self.assertTrue(self.w.external_blackout)
        self.assertTrue(self.w.projector.blacked_out)
        self.assertIsNotNone(self.w.external_filename)
        self.w.toggle_projector()
        second=self.w.external_video.process
        self.assertIsNot(first,second);self.assertTrue(second.waitForStarted(3000))
        self.assertFalse(self.w.external_blackout)
        self.assertEqual(self.w.projector_button.text(),'Projector off')

    def test_screen_change_restarts_on_the_selected_display_and_unplug_stops(self):
        first=self.started();self.w.projector_screen_selected()
        second=self.w.external_video.process;self.assertIsNot(first,second)
        self.assertTrue(second.waitForStarted(3000))
        with patch('nightfall.gui.QApplication.screens',return_value=[]):self.w.scan_screens()
        self.assertFalse(self.w.external_video.active);self.assertIsNone(self.w.external_filename)

    def test_tour_can_switch_vlc_shows_and_preserves_blackout(self):
        self.w.filename=self.root/'house.json';directory=self.root/'videos';directory.mkdir()
        files=[f'halloween-{mode}-800x1280.mp4' for mode in ('young','older')]
        for name in files:(directory/name).write_bytes(b'fixture')
        (directory/'render-manifest.json').write_text(json.dumps({'cache_key':render_cache.folder(self.w.data).name,'full_loop':True,'files':files}))
        self.w.data.setdefault('show_schedule',{})['switch_time']='19:00'
        with patch('nightfall.gui.QTime.currentTime',return_value=QTime(18,0)):self.w.start_tour()
        self.assertTrue(self.w.external_video.process.waitForStarted(3000))
        self.assertTrue(self.w.tour_active);self.assertEqual(self.w.tour_stage,'young')
        self.w.toggle_projector();self.w.check_tour_time(QTime(19,1))
        self.assertTrue(self.w.tour_active);self.assertEqual(self.w.tour_stage,'older')
        self.assertTrue(self.w.external_blackout);self.assertFalse(self.w.external_video.active)
        self.w.toggle_projector();self.assertTrue(self.w.external_video.process.waitForStarted(3000))
        self.assertIn('older',self.w.external_filename);self.assertTrue(self.w.tour_active)
        self.w.stop_video();self.assertFalse(self.w.tour_active)

    def test_failed_start_and_existing_vlc_process_are_handled_independently(self):
        other=QProcess();other.start(sys.executable,['-c','import time;time.sleep(120)'])
        self.assertTrue(other.waitForStarted(3000))
        try:
            self.started();self.w.stop_video();self.assertEqual(other.state(),QProcess.Running)
            with patch('nightfall.external_player.find_vlc',return_value=str(self.root/'missing-vlc.exe')):
                self.w.play_animation(str(self.movie))
                for _ in range(30):
                    QTest.qWait(20)
                    if self.w.external_video.process is None:break
            self.assertFalse(self.w.external_video.active);self.assertIsNone(self.w.external_filename)
            self.assertEqual(self.w.video_button.text(),'Video');self.assertEqual(other.state(),QProcess.Running)
        finally:
            other.kill();other.waitForFinished(3000)

    def test_portable_videos_require_matching_geometry_effects_and_renderer(self):
        directory=self.root/'videos';directory.mkdir();name='halloween-young-800x1280.mp4'
        (directory/name).write_bytes(b'fixture')
        manifest={'cache_key':render_cache.folder(self.w.data).name,'full_loop':True,'files':[name]}
        (directory/'render-manifest.json').write_text(json.dumps(manifest))
        self.assertEqual(render_cache.exported_video(self.w.data,'young',self.root/'house.json'),directory/name)
        changed=copy.deepcopy(self.w.data);changed['effects']['brightness_gain']=1.7
        self.assertIsNone(render_cache.exported_video(changed,'young',self.root/'house.json'))
        changed=copy.deepcopy(self.w.data);changed['regions'][0]['projector_points'][0][0]+=1
        self.assertIsNone(render_cache.exported_video(changed,'young',self.root/'house.json'))
        manifest['cache_key']='old-renderer'
        (directory/'render-manifest.json').write_text(json.dumps(manifest))
        self.assertIsNone(render_cache.exported_video(self.w.data,'young',self.root/'house.json'))


class VLCArgumentsTests(unittest.TestCase):
    def test_screen_loop_fullscreen_and_no_shell_or_forced_aspect_ratio(self):
        args=vlc_arguments('movie with spaces.mp4',2)
        self.assertIn('--qt-fullscreen-screennumber=2',args);self.assertIn('--embedded-video',args)
        self.assertIn('--fullscreen',args);self.assertIn('--loop',args)
        self.assertIn('--no-one-instance',args);self.assertIn('--no-osd',args)
        self.assertEqual(args[-1],str(Path('movie with spaces.mp4').resolve()))
        self.assertFalse(any('aspect-ratio=' in a or 'transform=' in a for a in args))
        with self.assertRaises(ValueError):vlc_arguments('movie.mp4',-1)

    def test_preferred_executable_and_portable_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);chosen=base/'custom VLC.exe';chosen.write_bytes(b'fixture')
            self.assertEqual(find_vlc(chosen),str(chosen.resolve()))
            portable=base/('vlc.exe' if os.name=='nt' else 'vlc');portable.write_bytes(b'fixture')
            with patch('nightfall.external_player.ROOT',base):
                self.assertEqual(find_vlc(base/'missing'),str(portable.resolve()))

"""Exercise real Qt windows on multiple virtual displays in isolated processes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent.parent


class ProjectorDisplayTests(unittest.TestCase):
    def check_displays(self,projector,extra=()):
        screens=[{'name':'Laptop','width':1920,'height':1080,'logicalDpi':144},
                 {'name':'Projector',**projector},*extra]
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'screens.json').write_text(json.dumps({'screens':screens}))
            env={**os.environ,'PYTHONPATH':str(ROOT),'QT_QPA_PLATFORM':'offscreen'}
            # Keep the config path relative: Qt's platform arguments use ':' as
            # a separator, which conflicts with absolute Windows drive paths.
            result=subprocess.run([sys.executable,'-m','tests.test_projector','--probe'],
                                  cwd=tmp,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_portrait_projector_with_scaled_laptop(self):
        self.check_displays({'x':1920,'width':800,'height':1280})

    def test_scaled_portrait_projector(self):
        self.check_displays({'x':1920,'width':1000,'height':1600,'logicalDpi':120})

    def test_projector_left_of_laptop_with_another_monitor(self):
        self.check_displays({'x':-800,'y':100,'width':800,'height':1280},
                            [{'name':'Monitor','x':1920,'width':1920,'height':1080}])


def probe():
    from unittest.mock import patch
    from PySide6.QtCore import QObject, QEvent, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from nightfall.gui import MainWindow

    app=QApplication(['projector-test','-platform','offscreen:configfile=screens.json'])
    checks=unittest.TestCase()
    screens=app.screens()
    laptop=next(s for s in screens if s.name()=='Laptop')
    target=next(s for s in screens if s.name()=='Projector')
    window=MainWindow();window.simplify();window.show();app.processEvents()
    output=window.projector
    try:
        checks.assertTrue(window.screens.isVisible())
        checks.assertIn('Projector',window.screens.currentText())
        # Use an asymmetric portrait frame to detect rotation, cropping and
        # uncovered areas at the bottom of the output window.
        frame=QImage(800,1280,QImage.Format_RGB32);frame.fill(QColor('blue'))
        painter=QPainter(frame);painter.fillRect(0,640,800,640,QColor('red'))
        painter.fillRect(300,540,200,200,QColor('lime'));painter.end()
        window.frame=frame

        class ShowObserver(QObject):
            def __init__(self):super().__init__();self.shows=[]
            def eventFilter(self,watched,event):
                if event.type()==QEvent.Show:self.shows.append((watched.screen(),watched.geometry()))
                return False
        observer=ShowObserver();output.installEventFilter(observer)

        def check_output():
            QTest.qWait(20)
            checks.assertTrue(output.isVisible());checks.assertTrue(output.isFullScreen())
            checks.assertEqual(output.screen(),target)
            checks.assertEqual(output.geometry(),target.geometry())
            checks.assertEqual(output.windowHandle().geometry(),target.geometry())
            checks.assertEqual(output.frameGeometry(),target.geometry())
            checks.assertEqual(window.projector_button.text(),'Projector off')
            image=output.grab().toImage();w,h=image.width(),image.height()
            checks.assertAlmostEqual(w/h,800/1280,places=3)
            for x in (1,w//2,w-2):
                checks.assertEqual(image.pixelColor(x,1),QColor('blue'))
                checks.assertEqual(image.pixelColor(x,h-2),QColor('red'))
            # A square in the source must remain square at the target's DPI.
            green_width=sum(image.pixelColor(x,h//2).green()>200 for x in range(w))
            green_height=sum(image.pixelColor(w//2,y).green()>200 for y in range(h))
            checks.assertAlmostEqual(green_width,green_height,delta=1)

        window.toggle_projector();check_output()
        checks.assertEqual(observer.shows[0],(target,target.geometry()))
        for _ in range(2):
            window.toggle_projector();app.processEvents()
            checks.assertTrue(output.blacked_out)
            checks.assertEqual(output.geometry(),target.geometry())
            black=output.grab().toImage()
            for x,y in [(1,1),(black.width()-2,black.height()-2)]:
                checks.assertEqual(black.pixelColor(x,y),QColor('black'))
            window.toggle_projector();check_output()

        # Selecting a different monitor while fullscreen must also resize the
        # output, preserve blackout, and work when returning to portrait.
        window.toggle_projector()
        for screen in (laptop,target):
            index=next(i for i in range(window.screens.count()) if screen.name() in window.screens.itemText(i))
            window.screens.setCurrentIndex(index);window.screens.activated.emit(index)
            app.processEvents()
            checks.assertEqual(output.screen(),screen)
            checks.assertEqual(output.geometry(),screen.geometry())
            checks.assertTrue(output.blacked_out)
        window.toggle_projector();check_output()

        # Windows can renumber displays. Keep the chosen physical display.
        with patch('nightfall.gui.QApplication.screens',return_value=list(reversed(screens))):
            window.scan_screens()
            checks.assertIn('Projector',window.screens.currentText())
            window.show_projector();check_output()
        window.scan_screens()

        output.hide();app.processEvents();window.toggle_projector();check_output()
        # Recover from an existing fullscreen window left on the laptop.
        output.hide();output.setWindowState(Qt.WindowNoState)
        output.setScreen(laptop);output.setGeometry(laptop.geometry())
        output.showFullScreen();app.processEvents()
        window.show_projector();check_output()
        # A delayed native resize/DPI event can leave stale landscape bounds.
        output.setWindowState(Qt.WindowNoState);output.setGeometry(laptop.geometry())
        output.geometry_timer.start(0);check_output()
        # A queued placement check must not reopen output after Esc/unplugging.
        window.show_projector();output.screen_removed(target);app.processEvents()
        checks.assertFalse(output.isVisible())
        checks.assertEqual(window.projector_button.text(),'Projector on')
    finally:
        window.dirty=False;window.close();app.processEvents()


if __name__=='__main__':
    if '--probe' in sys.argv:probe()
    else:unittest.main()

"""Regression checks for the new live polygon application, run offscreen."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtTest import QTest,QSignalSpy
from PySide6.QtGui import QImageReader, QTransform
from nightfall import model
from nightfall.gui import MainWindow, edit_corner
from nightfall.renderer import render, uv_transform, alignment_shapes, excluded_surfaces, glass_mask, path
from nightfall.animation import skeleton_frame
from nightfall.effects import STYLES

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parent.parent

class PolygonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        cls.media = tempfile.TemporaryDirectory()
        cls.movie = Path(cls.media.name)/'example.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x256:rate=60', '-t', '1', '-c:v',
                        'libx264', '-pix_fmt', 'yuv420p', str(cls.movie)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):self.data=model.load(ROOT/'tests/fixtures/polygon-draft.json')

    def test_dancer_changes_pose_and_repeats(self):
        poses=[bytes(skeleton_frame(t).constBits()) for t in [0,.25,.5,.75]]
        self.assertEqual(len(set(poses)),4)
        self.assertEqual(bytes(skeleton_frame(0).constBits()),bytes(skeleton_frame(5).constBits()))
        # Changing pose must be visible in the mapped stage itself.
        only_stage=copy.deepcopy(self.data)
        for r in only_stage['regions']:r['enabled']=r['type']=='stage'
        only_stage['effects']['architecture_strength']=0
        a=render(only_stage,0,'young');b=render(only_stage,.5,'young')
        self.assertNotEqual(bytes(a.constBits()),bytes(b.constBits()))

    def test_window_symmetry_is_preserved_in_start_map(self):
        inv,ok=uv_transform(model.region(self.data,'right')['projector_points']).inverted()
        attic=uv_transform(model.region(self.data,'attic')['projector_points']).map(QPointF(.5,.5))
        axis=inv.map(attic).x()
        for left,right in [('left','right'),('frame-left','frame-right'),('frame-left-middle','frame-right-middle')]:
            a=model.region(self.data,left)['projector_points']
            b=model.region(self.data,right)['projector_points']
            for l,r in zip(a,b):
                l=inv.map(QPointF(*l));r=inv.map(QPointF(*r))
                self.assertAlmostEqual(l.x(),2*axis-r.x(),delta=.001)
                self.assertAlmostEqual(l.y(),r.y(),delta=.001)
        # The hidden left-hand window must be separate from the right window.
        left=model.region(self.data,'left')['projector_points']
        right=model.region(self.data,'right')['projector_points']
        self.assertLess(max(p[0] for p in left),min(p[0] for p in right))

    def test_simple_editor_keyboard_keeps_window_frame_attached(self):
        w=MainWindow(copy.deepcopy(self.data));w.simplify();w.show();APP.processEvents()
        w.select('right');w.editor.vertex=0;w.editor.setFocus()
        before=w.current()['projector_points'][0][:]
        QTest.keyClick(w.editor,Qt.Key_Right,Qt.ControlModifier)
        self.assertAlmostEqual(w.current()['projector_points'][0][0],before[0]+.25)
        for a,b in zip(w.current()['projector_points'],model.region(w.data,'frame-right')['projector_points']):
            for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=8)
        QTest.keyClick(w.editor,Qt.Key_Tab);self.assertEqual(w.editor.vertex,1)
        w.undo();self.assertEqual(w.current()['projector_points'][0],before)
        self.assertEqual(w.mode,'mapping');self.assertTrue(w.photo_check.isChecked())
        self.assertFalse(w.list.isVisible());self.assertFalse(w.mode_box.isVisible())
        self.assertEqual(w.data['reference']['filename'],'../../examples/house-night.png')
        w.dirty=False;w.close()

    def test_projector_blackout_keeps_laptop_lines_and_edits(self):
        w=MainWindow(copy.deepcopy(self.data));w.simplify();w.show()
        w.projector.resize(400,640);w.projector.show();APP.processEvents()
        before=bytes(w.frame.constBits());photo=bytes(w.reference.constBits())
        QTest.mouseClick(w.blackout_button,Qt.LeftButton);APP.processEvents()
        self.assertEqual(w.mode,'mapping')
        laptop=w.editor.grab().toImage()
        self.assertEqual(bytes(w.frame.constBits()),before)
        self.assertEqual(bytes(w.reference.constBits()),photo)
        self.assertTrue(w.photo_check.isChecked())
        # The selected cyan contour remains painted over the laptop photo.
        a,b=w.current()['projector_points'][:2]
        q=w.editor.view_transform().map(QPointF((a[0]+b[0])/2,(a[1]+b[1])/2)).toPoint()
        self.assertTrue(any(laptop.pixelColor(q.x()+dx,q.y()+dy).blue()>180 for dx in range(-2,3) for dy in range(-2,3)))
        blackout=w.projector.grab().toImage()
        for x in range(0,400,17):
            for y in range(0,640,19):self.assertEqual(blackout.pixelColor(x,y).lightness(),0)
        w.editor.vertex=0;QTest.keyClick(w.editor,Qt.Key_Right)
        self.assertTrue(w.projector.blacked_out)
        current=bytes(w.frame.constBits())
        QTest.mouseClick(w.blackout_button,Qt.LeftButton);APP.processEvents()
        self.assertFalse(w.projector.blacked_out)
        self.assertEqual(bytes(w.frame.constBits()),current)
        projection=w.projector.grab().toImage()
        self.assertNotEqual(bytes(projection.constBits()),bytes(blackout.constBits()))
        w.projector.close();w.dirty=False;w.close()

    def test_photo_view_centres_origin_and_levels_window(self):
        w=MainWindow(copy.deepcopy(self.data));w.simplify();w.show();APP.processEvents()
        tr=w.editor.view_transform();origin=model.origin_point(w.data)
        centre=tr.map(QPointF(*origin))
        self.assertAlmostEqual(centre.x(),w.editor.width()/2)
        self.assertAlmostEqual(centre.y(),w.editor.height()/2)
        a,b=[tr.map(QPointF(*p)) for p in w.current()['projector_points'][:2]]
        self.assertAlmostEqual(a.y(),b.y(),places=7)
        q=w.editor.to_pixel(centre)
        self.assertAlmostEqual(q[0],origin[0]);self.assertAlmostEqual(q[1],origin[1])
        native=render(w.data,0,'mapping','right')
        self.assertEqual(bytes(w.frame.constBits()),bytes(native.constBits()))
        w.dirty=False;w.close()

    def test_working_house_contours_and_roof_tip(self):
        d=model.load(ROOT/'examples/house.json');visible={r['id'] for r in alignment_shapes(d)}
        self.assertIn('left',visible)
        self.assertFalse(any(r.get('parent')=='left' and r['id'] in visible for r in d['regions']))
        self.assertTrue({'right','right-pane-left','right-pane-right','curtain-r1','curtain-r2','right-sill','attic','attic-inner','roof-tip'}<=visible)
        self.assertNotIn('frame-right-middle',visible)
        self.assertEqual({rid for rid in visible if rid.startswith('bay')},{'bay-trim','bay-trim-left','bay-trim-right'})
        self.assertFalse(any(r['id'] in {'bay-platform','bay-stage'} for r in d['regions']))
        tip=copy.deepcopy(model.region(d,'roof-tip')['projector_points'])
        model.move(d,'roof',3,2)
        for a,b in zip(model.region(d,'roof-tip')['projector_points'],tip):self.assertEqual(a,[b[0]+3,b[1]+2])



    def test_working_house_excluded_surfaces_stay_black(self):
        d=model.load(ROOT/'examples/house.json');mask=excluded_surfaces(d);bounds=mask.boundingRect()
        samples=[(x,y) for x in range(int(bounds.left())+3,int(bounds.right())-3,5) for y in range(int(bounds.top())+3,int(bounds.bottom())-3,5) if mask.contains(QRectF(x-2,y-2,4,4))]
        self.assertGreater(len(samples),100)
        # Tree illumination and flashes must not re-light excluded regions.
        for mode in ['young','older']:
            im=render(d,8.03,mode)
            for x,y in samples:self.assertEqual(im.pixelColor(x,y).lightness(),0)

    def test_shared_facade_corners_and_bay_cutout_survive_save(self):
        d=model.load(ROOT/'examples/house.json')
        self.assertIn('facade',{r['id'] for r in alignment_shapes(d)})
        p=model.region(d,'facade')['projector_points'][1]
        edit_corner(d,'facade',1,[p[0]+2,p[1]+1])
        self.assertEqual(model.region(d,'facade')['projector_points'][1],model.region(d,'exclusion-roof-inner')['projector_points'][4])
        p=model.region(d,'bay-trim')['projector_points'][3]
        edit_corner(d,'bay-trim',3,[p[0]+1,p[1]+1])
        link=next(link for link in d['vertex_links'] if ['bay-trim',3] in link['members'])
        i=next(i for rid,i in link['members'] if rid=='exclusion-bay-front')
        self.assertEqual(model.region(d,'bay-trim')['projector_points'][3],model.region(d,'exclusion-bay-front')['projector_points'][i])
        model.validate(d)
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'house.json';model.save(d,dest);self.assertEqual(model.load(dest),d)

    def test_bay_cutout_attaches_to_every_lower_fascia_corner(self):
        d=model.load(ROOT/'examples/house.json')
        for rid,index in [('bay-trim-left',3),('bay-trim',3),('bay-trim',2),('bay-trim-right',2)]:
            link=next(link for link in d['vertex_links'] if [rid,index] in link['members'])
            hole_index=next(i for other,i in link['members'] if other=='exclusion-bay-front')
            p=model.region(d,rid)['projector_points'][index]
            edit_corner(d,rid,index,[p[0]+.25,p[1]+.25])
            self.assertEqual(model.region(d,rid)['projector_points'][index],model.region(d,'exclusion-bay-front')['projector_points'][hole_index])
            model.validate(d)

    def test_shared_pane_and_curtain_deform_together(self):
        d=model.load(ROOT/'examples/house.json');before=copy.deepcopy(d)
        p=model.region(d,'right-pane-left')['projector_points'][2]
        edit_corner(d,'right-pane-left',2,[p[0]+2,p[1]+1])
        self.assertEqual(model.region(d,'right-pane-left')['projector_points'][2],model.region(d,'curtain-r1')['projector_points'][2])
        self.assertNotEqual(model.region(d,'curtain-r1')['projector_points'][0],model.region(before,'curtain-r1')['projector_points'][0])
        model.validate(d)
        model.move(d,'right-pane-left',1,1);model.validate(d)
        self.assertEqual(model.region(d,'right-pane-left')['projector_points'][3],model.region(d,'curtain-r1')['projector_points'][3])

    def test_shared_corner_indices_survive_point_insertion_and_deletion(self):
        d=model.load(ROOT/'examples/house.json');p=model.region(d,'facade')['projector_points'][0][:]
        model.insert_vertex(d,'facade',0,[p[0]-1,p[1]+1])
        model.validate(d)
        p=model.region(d,'facade')['projector_points'][2]
        edit_corner(d,'facade',2,[p[0]+1,p[1]+1])
        self.assertEqual(model.region(d,'facade')['projector_points'][2],model.region(d,'exclusion-roof-inner')['projector_points'][4])
        model.delete_vertex(d,'facade',0);model.validate(d)
        self.assertEqual(model.region(d,'facade')['projector_points'][1],model.region(d,'exclusion-roof-inner')['projector_points'][4])

    def test_hierarchy_origin_and_pivot(self):
        before=copy.deepcopy(self.data);origin=model.origin_point(before)
        model.region(self.data,'right')['alignment_status']='aligned'
        model.move(self.data,'right',3,2)
        for rid in ['right','frame-right','frame-right-middle','curtain-r1','curtain-r2']:
            a=model.region(self.data,rid)['projector_points'][0];b=model.region(before,rid)['projector_points'][0]
            self.assertAlmostEqual(a[0]-b[0],3);self.assertAlmostEqual(a[1]-b[1],2)
        self.assertEqual(model.origin_point(self.data),[origin[0]+3,origin[1]+2])
        self.assertEqual(model.region(self.data,'right')['alignment_status'],'needs-alignment')
        transformed=model.transform_all(before,scale=.97)
        self.assertEqual(model.origin_point(transformed),origin)
        model.move(self.data,'roof',2,1)
        p=model.region(self.data,'exclusion-roof-inner')['projector_points'][0]
        q=model.region(before,'exclusion-roof-inner')['projector_points'][0]
        self.assertEqual(p,[q[0]+2,q[1]+1])

    def test_gui_coordinates_save_and_live_frame(self):
        w=MainWindow(copy.deepcopy(self.data));w.select('right');w.editor.vertex=1;w.sync_coordinates()
        origin=model.origin_point(w.data);point=w.current()['projector_points'][1][:]
        self.assertAlmostEqual(w.x.value(),point[0]-origin[0],places=2)
        previous=bytes(w.frame.constBits());w.x.setValue(w.x.value()+2);w.coordinates_changed()
        self.assertAlmostEqual(w.current()['projector_points'][1][0],point[0]+2,places=2)
        self.assertNotEqual(bytes(w.frame.constBits()),previous)
        # Projector paint uses owner.frame; the exact current pixels also export.
        self.assertIs(w.projector.owner,w)
        exported=render(w.data,w.t,w.mode,w.selected)
        self.assertEqual(bytes(w.frame.constBits()),bytes(exported.constBits()))
        calibration=copy.deepcopy(w.data['calibration'])
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'saved.json'
            with patch('nightfall.gui.QFileDialog.getSaveFileName',return_value=(str(dest),'')):
                self.assertTrue(w.save_map())
            saved=model.load(dest)
            for key,value in calibration.items():self.assertEqual(saved['calibration'][key],value)
            self.assertEqual(saved['alignment']['origin'],w.data['alignment']['origin'])
            self.assertTrue(dest.with_suffix('.alignment.png').exists())
        w.dirty=False;w.close()

    def test_loop_and_absolute_blackout(self):
        for mode in ['young','older']:
            first=render(self.data,0,mode);last=render(self.data,120,mode)
            self.assertEqual(bytes(first.constBits()),bytes(last.constBits()))
        im=render(self.data,8,'black')
        for x in range(0,800,17):
            for y in range(0,1280,19):self.assertEqual(im.pixelColor(x,y).lightness(),0)

    def test_all_animation_styles_loop_and_respect_masks(self):
        d=model.load(ROOT/'examples/house.json');blocked=excluded_surfaces(d).united(glass_mask(d))
        for mode in STYLES:
            a=render(d,0,mode);b=render(d,120,mode)
            self.assertEqual(bytes(a.constBits()),bytes(b.constBits()))
            im=render(d,18,mode)
            for x in range(20,780,13):
                for y in range(20,1260,13):
                    if blocked.contains(QRectF(x-2,y-2,4,4)):self.assertEqual(im.pixelColor(x,y).lightness(),0)
        self.assertFalse(model.region(d,'attic')['paper_screen'])
        self.assertFalse(model.region(d,'right')['paper_screen'])

    def test_entire_ghost_route_avoids_window_with_clearance(self):
        from PySide6.QtGui import QPainterPath
        from nightfall.routes import flight_route,flight_position
        shape=QPainterPath();shape.addRect(QRectF(0,0,400,600))
        hole=QPainterPath();hole.addRect(QRectF(170,240,100,150));shape=shape.subtracted(hole)
        for old in [False,True]:
            route=flight_route(shape,shape.boundingRect(),1.5,old,7)
            self.assertIsNotNone(route)
            for i in range(600):
                x,y,w=flight_position(route,i/5,0);height=w*1.5
                self.assertTrue(shape.contains(QRectF(x-w*.6-7,y-height*.5-7,w*1.2+14,height*1.1+14)))

    def test_smoke_has_clear_blue_red_green_colour(self):
        d=model.load(ROOT/'examples/house.json')
        from nightfall.renderer import surface_path,box
        facade=surface_path(d,model.region(d,'facade'))
        for mode,channel in [('older',2),('embers',0),('aurora',1)]:
            im=render(d,5,mode);count=0
            for x in range(200,650,7):
                for y in range(200,800,7):
                    if not facade.contains(QPointF(x,y)):continue
                    c=im.pixelColor(x,y);rgb=[c.red(),c.green(),c.blue()]
                    if rgb[channel]>35 and rgb[channel]>max(rgb[(channel+1)%3],rgb[(channel+2)%3])*1.3:count+=1
            self.assertGreater(count,100,mode)

    def test_smoke_brightness_reduces_clipping_without_changing_geometry(self):
        from nightfall.renderer import facade_shape
        d=model.default_project();before=copy.deepcopy(d['regions'])
        shape=facade_shape(d,model.region(d,'facade')).subtracted(path(model.region(d,'tree')['projector_points']))
        samples=[(x,y) for x in range(100,650,7) for y in range(250,850,7) if shape.contains(QPointF(x,y))]
        clipped=[]
        for strength in [1,.5]:
            with patch('nightfall.effects.SMOKE_STRENGTH',strength):image=render(d,5,'older')
            clipped.append(sum(max(image.pixelColor(x,y).getRgb()[:3])>=250 for x,y in samples))
        self.assertLess(clipped[1],clipped[0]*.3)
        self.assertEqual(d['regions'],before)


    def test_brightness_limits_all_channels_together(self):
        from PySide6.QtGui import QImage,QColor
        from nightfall.tone import brighten
        original=QImage(5,1,QImage.Format_RGB32)
        colours=[(0,0,0),(200,100,0),(40,160,80),(25,25,25),(128,64,255)]
        for x,rgb in enumerate(colours):original.setPixelColor(x,0,QColor(*rgb))
        image=brighten(original.copy(),2)
        expected=[(0,0,0),(255,128,0),(64,255,128),(50,50,50),(128,64,255)]
        for x,rgb in enumerate(expected):self.assertEqual(image.pixelColor(x,0).getRgb(),(*rgb,255))
        for x,rgb in enumerate(colours):self.assertEqual(original.pixelColor(x,0).getRgb(),(*rgb,255))

    def test_fast_brightness_matches_rgb_ratio_formula_for_varied_colours(self):
        from PySide6.QtGui import QImage,QColor
        from nightfall.tone import brighten
        import math,random
        colours=[(random.Random(i).randrange(256),random.Random(i+11).randrange(256),random.Random(i+21).randrange(256)) for i in range(1024)]
        original=QImage(len(colours),1,QImage.Format_RGB32)
        for x,rgb in enumerate(colours):original.setPixelColor(x,0,QColor(*rgb))
        for gain in (1.5,3):
            image=brighten(original.copy(),gain)
            for x,rgb in enumerate(colours):
                peak=max(rgb)
                expected=tuple((c*255+peak//2)//peak if peak*gain>255 else math.floor(c*gain+.5) for c in rgb)
                self.assertEqual(image.pixelColor(x,0).getRgb(),(*expected,255))

    def test_render_button_produces_real_60fps_video_from_snapshot(self):
        import json,subprocess,time
        from nightfall import render_cache
        from PySide6.QtCore import QProcess
        d=model.load(ROOT/'examples/house.json')
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            w=MainWindow(copy.deepcopy(d));w.simplify();w.show();APP.processEvents()
            w.animation_mode='young'
            original=QProcess.setArguments
            def short_job(process,args):
                args=list(args)
                if '--seconds' in args:args[args.index('--seconds')+1]='2'
                original(process,args)
            with patch.object(render_cache,'folder',return_value=output),patch.object(QProcess,'setArguments',short_job),patch('nightfall.gui.QMessageBox.warning'):
                QTest.mouseClick(w.render_button,Qt.LeftButton)
                finished=QSignalSpy(w.process.finished)
                self.assertTrue(w.render_button.isEnabled())
                self.assertTrue(w.render_button.text().startswith('Stop render'))
                deadline=time.monotonic()+90
                while finished.count()==0 and time.monotonic()<deadline:QTest.qWait(100)
                self.assertEqual(finished.count(),1,w.render_log)
                self.assertEqual(finished.at(0)[0],0,w.render_log)
                self.assertTrue(w.render_button.isEnabled())
                for mode in ['young','older']:
                    film=output/f'halloween-{mode}-800x1280.mp4'
                    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=r_frame_rate:format=duration','-of','json',str(film)]))
                    self.assertEqual(info['streams'][0]['r_frame_rate'],'60/1')
                    self.assertEqual(float(info['format']['duration']),2)
                snapshot=model.load(output/'render-input.json');self.assertEqual(snapshot['regions'],d['regions'])
                w.play_house_animation('young');self.assertTrue(w.video.active);w.stop_video()
            w.dirty=False;w.close()

    def test_parallel_frames_match_serial_in_order_across_both_shows(self):
        import hashlib
        from nightfall.parallel_render import FrameRenderer
        d=model.load(ROOT/'examples/house.json')
        def fingerprints(renderer,mode,start):
            return [hashlib.sha256(frame).digest()
                    for frame in renderer.frames(mode,6,60,start)]
        with FrameRenderer(d,1) as serial:
            expected={mode:fingerprints(serial,mode,start)
                      for mode,start in [('young',3),('older',18)]}
        with FrameRenderer(d,2) as parallel:
            pids=[child.pid for child,_,_ in parallel.children]
            for mode,start in [('young',3),('older',18)]:
                self.assertEqual(fingerprints(parallel,mode,start),expected[mode])
            self.assertEqual(len(set(pids)),2)
        import multiprocessing
        self.assertFalse(set(pids)&{p.pid for p in multiprocessing.active_children()})

    def test_parallel_worker_error_cleans_processes_and_pixel_buffers(self):
        from nightfall.parallel_render import FrameRenderer
        import multiprocessing
        d=model.load(ROOT/'examples/house.json');d['effects']['brightness_gain']='invalid'
        with self.assertRaisesRegex(RuntimeError,'Render worker failed'):
            with FrameRenderer(d,2) as parallel:
                directory=Path(parallel.directory.name)
                pids={child.pid for child,_,_ in parallel.children}
                next(parallel.frames('older',8,60,5))
        self.assertFalse(directory.exists())
        self.assertFalse(pids&{p.pid for p in multiprocessing.active_children()})

    def test_bay_mask_leaves_brickwork_above_fascia_for_smoke_and_figures(self):
        from nightfall.renderer import facade_shape,figure_shape
        d=model.load(ROOT/'examples/house.json');facade=model.region(d,'facade')
        wall=facade_shape(d,facade)
        for x,y in [(350,550),(450,840),(450,879)]:
            self.assertTrue(wall.contains(QPointF(x,y)))
            self.assertFalse(excluded_surfaces(d).contains(QPointF(x,y)))
        # The old bay top was at ~870px; the actual fascia starts at ~888px.
        fog=render(d,5,'older')
        for x,y in [(450,840),(450,879)]:
            self.assertGreater(fog.pixelColor(x,y).lightness(),10)
        self.assertEqual(fog.pixelColor(450,940).lightness(),0)
        actors=figure_shape(d,wall)
        self.assertTrue(actors.contains(QPointF(350,550)))
        self.assertFalse(actors.contains(QPointF(450,895)))
        # A ghost on the wall must not vanish along with the duplicated cutout.
        image=render(d,5,'young')
        self.assertGreater(sum(image.pixelColor(x,y).lightness()>70
            for x in range(340,600,3) for y in range(510,630,3)),5)

    def test_flowing_smoke_is_continuous_and_loops_without_strip_edges(self):
        from nightfall.atmosphere import flowing_smoke
        from PySide6.QtCore import QRect
        import numpy as np
        rect=QRect(50,190,650,810)
        images=[flowing_smoke('blue-purple',rect,t) for t in (0,1/60,120)]
        arrays=[np.frombuffer(im.constBits(),np.uint8).copy() for im in images]
        self.assertTrue(np.array_equal(arrays[0],arrays[2]))
        self.assertFalse(np.array_equal(arrays[0],arrays[1]))
        self.assertLess(np.abs(arrays[0].astype(float)-arrays[1]).mean(),1)

    def test_stop_render_cleans_partial_and_preserves_existing_video(self):
        import time
        from nightfall import render_cache
        from PySide6.QtCore import QProcess
        d=model.load(ROOT/'examples/house.json')
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);film=output/'halloween-young-800x1280.mp4'
            film.write_bytes(b'previous completed export')
            w=MainWindow(copy.deepcopy(d));w.simplify();w.show();APP.processEvents()
            with patch.object(render_cache,'folder',return_value=output),patch('nightfall.gui.QMessageBox.warning') as warning:
                QTest.mouseClick(w.render_button,Qt.LeftButton)
                finished=QSignalSpy(w.process.finished);deadline=time.monotonic()+90
                partial=output/'halloween-young-800x1280.partial.mp4'
                while not partial.exists() and finished.count()==0 and time.monotonic()<deadline:QTest.qWait(50)
                self.assertTrue(partial.exists(),w.render_log)
                QTest.mouseClick(w.render_button,Qt.LeftButton)
                self.assertTrue(w.render_cancelled)
                while finished.count()==0 and time.monotonic()<deadline:QTest.qWait(50)
                self.assertEqual(finished.count(),1,w.render_log)
                self.assertEqual(finished.at(0)[0],130,w.render_log)
                self.assertFalse(partial.exists());self.assertFalse(w.render_cancel_file.exists())
                self.assertEqual(film.read_bytes(),b'previous completed export')
                self.assertFalse((output/'halloween-older-800x1280.mp4').exists())
                self.assertTrue(w.render_button.isEnabled());self.assertEqual(w.render_button.text(),'Render video')
                warning.assert_not_called()
            w.dirty=False;w.close()

    def test_cached_video_changes_with_geometry(self):
        from nightfall import render_cache
        d=model.load(ROOT/'examples/house.json');before=render_cache.folder(d)
        d['regions'][0]['projector_points'][0][0]+=.25
        self.assertNotEqual(before,render_cache.folder(d))

    def test_tour_switches_at_local_start_time_and_stop_cancels(self):
        from PySide6.QtCore import QTime
        from nightfall import render_cache
        d=model.load(ROOT/'examples/house.json')
        w=MainWindow(copy.deepcopy(d));w.simplify();w.timer.stop()
        w.switch_time.setTime(QTime(19,0));frame=bytes(w.frame.constBits())
        cache=render_cache.folder(w.data);geometry=copy.deepcopy(w.data['regions'])
        with tempfile.TemporaryDirectory() as tmp,patch.object(render_cache,'video',return_value=Path(tmp)/'missing.mp4'):
            with patch('nightfall.gui.QTime.currentTime',return_value=QTime(18,59,59)):
                w.play_house_animation('tour')
            self.assertTrue(w.tour_active);self.assertEqual(w.live_mode,'young')
            w.projector.blacked_out=True
            with patch('nightfall.gui.QTime.currentTime',return_value=QTime(19,0)):
                w.tick()
            self.assertTrue(w.tour_active);self.assertEqual(w.live_mode,'older')
            self.assertEqual(w.animation_mode,'tour');self.assertTrue(w.projector.blacked_out)
            origin=w.live_play_origin
            w.check_tour_time(QTime(19,1));self.assertEqual(w.live_play_origin,origin)
            w.check_tour_time(QTime(0,1));self.assertEqual(w.live_mode,'older')
            self.assertEqual(w.data['regions'],geometry);self.assertEqual(bytes(w.frame.constBits()),frame)
            w.stop_video();w.check_tour_time(QTime(20,0))
            self.assertFalse(w.tour_active);self.assertIsNone(w.live_mode)
            w.switch_time.setTime(QTime(19,15))
            self.assertEqual(w.data['show_schedule']['switch_time'],'19:15')
            self.assertEqual(render_cache.folder(w.data),cache)
            model.save(w.data,Path(tmp)/'saved.json')
            restored=model.load(Path(tmp)/'saved.json')
            self.assertEqual(restored['show_schedule']['switch_time'],'19:15')
            with patch('nightfall.gui.QTime.currentTime',return_value=QTime(19,15)):
                w.play_house_animation('tour')
            self.assertEqual(w.live_mode,'older')
            w.play_house_animation('aurora');w.check_tour_time(QTime(21,0))
            self.assertFalse(w.tour_active);self.assertEqual(w.live_mode,'aurora')
        w.stop_video();w.dirty=False;w.close()

    def test_video_starts_inside_projector_and_leaves_editor_unchanged(self):
        w=MainWindow(model.load(ROOT/'examples/house.json'));w.simplify();w.show();APP.processEvents()
        before=bytes(w.frame.constBits())
        movie=self.movie
        frames=QSignalSpy(w.video.frame_ready)
        w.play_animation(str(movie))
        for _ in range(80):
            QTest.qWait(50)
            if frames.count()>0:break
        self.assertGreater(frames.count(),0)
        self.assertTrue(w.video.active)
        self.assertEqual((w.video_frame.width(),w.video_frame.height()),(800,1280))
        self.assertEqual(bytes(w.frame.constBits()),before)
        self.assertEqual(w.video_button.text(),'Stop video')
        from PySide6.QtGui import QImage,QPainter,QColor
        # The laptop blits the same decoded frame; no second renderer/decoder.
        captured=w.editor.grab().toImage().convertToFormat(QImage.Format_RGB32)
        expected=QImage(captured.size(),QImage.Format_RGB32);expected.fill(QColor('#101216'))
        painter=QPainter(expected);painter.setRenderHint(QPainter.SmoothPixmapTransform);k=min(expected.width()/800,expected.height()/1280)
        painter.drawImage(QRectF((expected.width()-800*k)/2,(expected.height()-1280*k)/2,800*k,1280*k),w.video_frame);painter.end()
        self.assertEqual(bytes(captured.constBits()),bytes(expected.constBits()))
        w.toggle_projector();self.assertTrue(w.projector.blacked_out)
        self.assertEqual(bytes(w.frame.constBits()),before)
        w.stop_video();self.assertFalse(w.video.active);self.assertEqual(w.video_button.text(),'Video')
        w.dirty=False;w.close()

    def test_mp4_playback_replaces_live_and_never_renders_hidden_effects(self):
        w=MainWindow(model.load(ROOT/'examples/house.json'));w.simplify()
        w.play_live_animation('young');self.assertEqual(w.live_mode,'young')
        w.play_animation(str(self.movie))
        self.assertIsNone(w.live_mode)
        self.assertFalse(w.playing)
        # Even a stale legacy playback flag must not render effects behind MP4.
        w.playing=True;w.mode='young'
        with patch('nightfall.gui.render') as renderer:
            w.tick();renderer.assert_not_called()
        w.playing=False;w.stop_video();w.dirty=False;w.close()

    def test_main_screen_preview_keeps_fps_visible_without_projector(self):
        w=MainWindow(model.default_project());w.simplify();w.show()
        try:
            w.preview_check.setChecked(True)
            w.play_animation(str(self.movie))
            self.assertFalse(w.projector.isVisible())
            for _ in range(40):
                QTest.qWait(50)
                if 'Main screen:' in w.playback_status.text():break
            self.assertIn('Main screen:',w.playback_status.text())
            self.assertIn('Projector: off',w.playback_status.text())
            self.assertGreater(len(w.display_times['laptop']),0)
            label=w.playback_status.text();w.refresh()
            self.assertEqual(w.playback_status.text(),label)
            w.stop_video();self.assertEqual(w.playback_status.text(),'')
        finally:
            w.stop_video();w.dirty=False;w.close()

    def test_fps_counter_counts_new_frames_in_a_rolling_window(self):
        from collections import deque
        from PySide6.QtGui import QImage
        w=MainWindow(model.default_project());w.simplify()
        try:
            w.display_start=8;w.display_update=8
            w.video_frame=QImage(1,1,QImage.Format_RGB32)
            with patch('nightfall.gui.time.monotonic',return_value=9):
                w.record_video_paint('laptop');w.record_video_paint('laptop')
            self.assertEqual(len(w.display_times['laptop']),1)
            w.display_times['laptop']=deque([7.9]+[8+i/60 for i in range(120)])
            with patch('nightfall.gui.time.monotonic',return_value=10):w.update_display_rate()
            self.assertIn('Main screen: 60 fps',w.playback_status.text())
            self.assertEqual(len(w.display_times['laptop']),120)
        finally:
            w.dirty=False;w.close()

    def test_decoder_keeps_reading_while_ui_waits_and_stops_cleanly(self):
        import time
        w=MainWindow(model.load(ROOT/'examples/house.json'));w.simplify()
        w.play_animation(str(self.movie))
        deadline=time.monotonic()+5
        first=None
        while first is None and time.monotonic()<deadline:
            QTest.qWait(20);first=w.video.decoder.take_frame()
        # The UI poll may consume the first image; the last displayed frame is valid too.
        if first is None and not w.video_frame.isNull():first=w.video_frame
        self.assertIsNotNone(first)
        decoder=w.video.decoder
        time.sleep(.12)  # No Qt events: QProcess-on-UI would stop receiving here.
        later=decoder.take_frame()
        self.assertIsNotNone(later)
        self.assertNotEqual(later.cacheKey(),first.cacheKey())
        w.stop_video();self.assertFalse(decoder.isRunning())
        # Pending finished events from stopped threads must not stop a new player.
        w.play_animation(str(self.movie))
        QTest.qWait(80);self.assertTrue(w.video.active)
        w.stop_video();w.dirty=False;w.close()

    def test_cat_is_in_both_shows_and_faces_have_no_fur_patch(self):
        from nightfall.effects import cat_face_layers
        from PySide6.QtCore import Qt
        eyes=cat_face_layers()['eyes'];mouth=cat_face_layers()['mouth']
        # Source-image locations of iris centres and central teeth survive;
        # nose, forehead and cheeks never become residual eye/mouth cutouts.
        self.assertGreater(eyes.pixelColor(round(420/1254*320),round(612/1254*320)).alpha(),240)
        self.assertGreater(mouth.pixelColor(round(575/1254*320),round(880/1254*320)).alpha(),240)
        for x,y in [(627,710),(400,500),(430,750),(620,960)]:
            self.assertEqual(eyes.pixelColor(round(x/1254*320),round(y/1254*320)).alpha(),0)
            self.assertEqual(mouth.pixelColor(round(x/1254*320),round(y/1254*320)).alpha(),0)
        d=model.load(ROOT/'examples/house.json')
        for mode,t in [('young',24),('older',16)]:
            actual=render(d,t,mode)
            with patch('nightfall.effects.cheshire'):
                without=render(d,t,mode)
            self.assertNotEqual(bytes(actual.constBits()),bytes(without.constBits()),mode)

    def test_attic_stays_dark_even_with_old_paper_flag(self):
        d=model.load(ROOT/'examples/house.json');model.region(d,'attic')['paper_screen']=True
        tr=uv_transform(model.region(d,'attic')['projector_points'])
        for mode in ['young','older','cheshire']:
            image=render(d,8,mode)
            for u in [.25,.5,.75]:
                for v in [.25,.5,.75]:
                    q=tr.map(QPointF(u,v))
                    self.assertEqual(image.pixelColor(round(q.x()),round(q.y())).lightness(),0)

    def test_video_button_can_start_live_animation_without_export(self):
        w=MainWindow(model.load(ROOT/'examples/house.json'));w.simplify();w.show();APP.processEvents()
        before=bytes(w.frame.constBits());w.play_live_animation('aurora')
        self.assertEqual(w.live_mode,'aurora');self.assertEqual(w.mode,'mapping')
        first=bytes(w.video_frame.constBits());QTest.qWait(150);w.tick()
        self.assertNotEqual(bytes(w.video_frame.constBits()),first)
        self.assertEqual(bytes(w.frame.constBits()),before)
        self.assertEqual(w.video_button.text(),'Stop video')
        w.stop_video();self.assertIsNone(w.live_mode);self.assertEqual(w.video_button.text(),'Video')
        w.dirty=False;w.close()

    def test_generated_reference_loads_and_cycles_are_rejected(self):
        w=MainWindow(self.data)
        for photo in ('day', 'night'):
            self.data['editor_photo']=photo;w.read_reference()
            reference=(self.data['reference_photos']['day'] if photo=='day' else self.data)['reference']
            self.assertEqual((w.reference.width(),w.reference.height()),(reference['width'],reference['height']))
        self.assertNotIn('observations',self.data['calibration'])
        d=copy.deepcopy(self.data);model.region(d,'right')['parent']='curtain-r1'
        with self.assertRaises(ValueError):model.validate(d)
        w.dirty=False;w.close()

if __name__=='__main__':unittest.main()

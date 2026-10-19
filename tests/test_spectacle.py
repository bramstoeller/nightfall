"""Check real in-between frames, repeatable cues, and physical surface masks."""
import copy
import hashlib
import os
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QColor,QImage,QPainterPath,QTransform
from PySide6.QtWidgets import QApplication
from nightfall import model
from nightfall.renderer import render,render_scene,surface_path,SHOW_SCENES,facade_cast,box,facade_shape,figure_shape
from nightfall.spectacle import actor_frame, ACTOR_FRAMES, ACTOR_BOUNDS, STYLES,character_slots,flying_parts
from nightfall.routes import performance_slots,performer_pose

APP=QApplication.instance() or QApplication([])


class SpectacleTests(unittest.TestCase):
    def test_bat_wings_are_mirrored_and_do_not_contain_a_second_face(self):
        left,right,body=flying_parts('bat')
        mirrored=left.flipped(Qt.Horizontal)
        self.assertEqual(bytes(mirrored.constBits()),bytes(right.constBits()))
        for x in range(110,145):
            for y in range(75,135):self.assertEqual(left.pixelColor(x,y).alpha(),0)

    def test_eight_characters_have_complete_300_frame_loops(self):
        for name in ACTOR_BOUNDS:
            with self.subTest(character=name):
                hashes={hashlib.sha256(actor_frame(name,i).constBits()).digest() for i in range(ACTOR_FRAMES)}
                self.assertGreater(len(hashes),275,'Motion must contain real evaluated in-betweens.')
                first=actor_frame(name,0)
                self.assertTrue(first.hasAlphaChannel())
                self.assertEqual(bytes(first.constBits()),bytes(actor_frame(name,ACTOR_FRAMES).constBits()))
                for index in [0,75,150,225]:
                    image=actor_frame(name,index)
                    for x,y in [(0,0),(128,0),(255,128),(128,255),(0,128)]:
                        self.assertEqual(image.pixelColor(x,y).alpha(),0,'Keep room around every pose.')
                last=actor_frame(name,ACTOR_FRAMES-1)
                a=np.frombuffer(first.constBits(),np.uint8).astype(np.int16)
                b=np.frombuffer(last.constBits(),np.uint8).astype(np.int16)
                self.assertLess(float(np.abs(a-b).mean()),6,'The five-second loop must close smoothly.')

    def test_architectural_motion_stays_inside_the_original_contour(self):
        for rid in ['roof','frame-attic','frame-right','bay-trim']:
            data=model.default_project();original=copy.deepcopy(data['regions'])
            data['effects'].update(architecture_strength=0,tree_strength=0,brightness_gain=1)
            for r in data['regions']:r['enabled']=r['id']==rid
            shape=surface_path(data,model.region(data,rid))
            for mode in ['haunted','waves','clockwork','electric']:
                with self.subTest(region=rid,mode=mode):
                    image=render(data,2.35,mode)
                    # Sample either side of every narrow architectural strip.
                    bounds=shape.boundingRect().adjusted(-8,-8,8,8).toAlignedRect()
                    for x in range(max(0,bounds.left()),min(800,bounds.right()+1),3):
                        for y in range(max(0,bounds.top()),min(1280,bounds.bottom()+1),3):
                            if not shape.intersects(QRectF(x-1,y-1,2,2)):
                                self.assertEqual(image.pixelColor(x,y).lightness(),0)
            for before,after in zip(original,data['regions']):
                self.assertEqual(before['projector_points'],after['projector_points'])

    def test_both_exported_shows_include_the_new_scenes(self):
        seen=set();data=model.default_project()
        blank=QImage(800,1280,QImage.Format_RGB32);blank.fill(0)
        with patch('nightfall.renderer.render_scene',return_value=blank) as scene:
            for show in ['young','older']:
                for start,_,_ in SHOW_SCENES[show]:render(data,start+2,show)
            seen={call.args[2] for call in scene.call_args_list}
        self.assertTrue(set(STYLES)<=seen)

    def test_complete_casts_remain_clear_of_windows_and_each_other_for_120s(self):
        data=model.default_project();facade=model.region(data,'facade')
        safe=figure_shape(data,facade_shape(data,facade));bounds=box(facade['projector_points'])
        casts=[('legacy',facade_cast(data)[1])]
        casts.append(('shadow-bats',performance_slots(safe,bounds,[(144,112,3,4,3)]*2)))
        for kind,count in [('skeleton',3),('bat',4),('pumpkin',3),('spider',4),('wisp',3),('owl',3),('young-ghost',2),('young-skeleton',2)]:
            casts.append((kind,character_slots(safe,bounds,kind,count)))
        for name,cast in casts:
            slots=[s for s in cast if s is not None]
            self.assertGreaterEqual(len(slots),1,name)
            self.assertTrue(all(max(s.size)>=100 for s in slots),'Brickwork needs large readable silhouettes.')
            for frame in range(120*60):
                boxes=[]
                for slot in slots:
                    rect,angle=performer_pose(slot,frame/60)
                    tr=QTransform();tr.translate(rect.center().x(),rect.center().y());tr.rotate(angle)
                    actual=tr.mapRect(QRectF(-rect.width()/2,-rect.height()/2,rect.width(),rect.height()))
                    self.assertTrue(QRectF(*slot.envelope).contains(actual),(name,frame))
                    self.assertTrue(safe.contains(actual.adjusted(-6,-6,6,6)),(name,frame))
                    self.assertFalse(any(actual.adjusted(-6,-6,6,6).intersects(other) for other in boxes),(name,frame))
                    boxes.append(actual)

    def test_a_small_wall_omits_performers_instead_of_clipping_them(self):
        safe=QPainterPath();safe.addRect(QRectF(0,0,80,80))
        cast=performance_slots(safe,safe.boundingRect(),[(100,100,15,15,12)]*3)
        self.assertEqual(cast,(None,None,None))

    def test_character_viewports_contain_all_poses_and_preserve_proportions(self):
        for kind,bounds in ACTOR_BOUNDS.items():
            x,y,w,h=bounds
            for variant in range(3):
                for index in range(ACTOR_FRAMES):
                    image=actor_frame(kind,index,variant)
                    alpha=np.frombuffer(image.constBits(),np.uint8).reshape(256,256,4)[:,:,3]
                    self.assertFalse(alpha[:y].any() or alpha[y+h:].any() or alpha[:,:x].any() or alpha[:,x+w:].any(),(kind,variant,index))
                    self.assertFalse(alpha[0].any() or alpha[-1].any() or alpha[:,0].any() or alpha[:,-1].any(),(kind,variant,index))

    def test_scene_transitions_never_superimpose_two_casts(self):
        blank=QImage(800,1280,QImage.Format_RGB32);blank.fill(0)
        with patch('nightfall.renderer.render_scene',return_value=blank) as scene:
            for show,scenes in SHOW_SCENES.items():
                for start,_,_ in scenes:
                    for frame in range(60):
                        scene.reset_mock();render({},start+frame/60,show)
                        self.assertEqual(len(scene.call_args_list),2)
                        strengths=[c.kwargs.get('actor_strength',1) for c in scene.call_args_list]
                        self.assertFalse(all(s>.001 for s in strengths),(show,start,frame))

    def test_loop_join_starts_with_the_last_scene_instead_of_black(self):
        for show in ['young','older']:
            last_start,last_mode,last_offset=SHOW_SCENES[show][-1]
            image=QImage(800,1280,QImage.Format_RGB32);image.fill(QColor('#71422a'))
            with patch('nightfall.renderer.render_scene',return_value=image) as scene:
                first=render({},0,show)
                previous=scene.call_args_list[1]
                self.assertEqual(previous.args[2],last_mode)
                self.assertEqual(previous.args[1],120-last_start+last_offset)
                self.assertEqual(first.pixelColor(400,600),QColor('#71422a'))

    def test_outgoing_scene_does_not_launch_a_new_lightning_flash(self):
        data=model.default_project()
        with patch('nightfall.renderer.lightning') as flash:
            for frame in range(60):render(data,24+frame/60,'older')
            flash.assert_not_called()
            render(data,8,'older')
            flash.assert_called_once()

    def test_architecture_scenes_do_not_send_bands_behind_windows(self):
        data=model.default_project();data['effects'].update(architecture_strength=0,tree_strength=0)
        for r in data['regions']:r['enabled']=r['id']=='facade'
        for mode in ['haunted','waves']:
            image=render_scene(data,2.35,mode).convertToFormat(QImage.Format_RGB888)
            self.assertFalse(any(image.constBits()),mode)

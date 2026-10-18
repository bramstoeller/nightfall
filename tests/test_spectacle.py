"""Check real in-between frames, repeatable cues, and physical surface masks."""
import copy
import hashlib
import os
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from nightfall import model
from nightfall.renderer import render, surface_path, SHOW_SCENES
from nightfall.spectacle import actor_frame, ACTOR_FRAMES, STYLES

APP=QApplication.instance() or QApplication([])


class SpectacleTests(unittest.TestCase):
    def test_six_characters_have_complete_300_frame_loops(self):
        for name in ['skeleton','bat','owl','spider','pumpkin','wisp']:
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

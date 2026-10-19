"""Window orbits and expressive silhouettes for the house-specific scenes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import math
import unittest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from nightfall.house_show import window_circuit,circuit_rect,simple_ghost
from nightfall.renderer import facade_shape,figure_shape

APP=QApplication.instance() or QApplication([])


class HouseStoryTests(unittest.TestCase):
    def test_full_window_orbits_keep_the_complete_figure_on_brick(self):
        facade={'id':'facade','type':'surface','projector_points':[[50,50],[750,50],[750,1150],[50,1150]]}
        for rid,points in [('attic',[[270,230],[330,230],[330,330],[270,330]]),
                           ('right',[[425,630],[575,630],[575,770],[425,770]])]:
            data={'regions':[facade,{'id':rid,'type':'window','projector_points':points}],'exclusions':[]}
            route=window_circuit(data,rid,(44,52));self.assertIsNotNone(route)
            safe=figure_shape(data,facade_shape(data,facade))
            center=(sum(p[0] for p in points)/4,sum(p[1] for p in points)/4)
            winding=sum(math.atan2((a[0]-center[0])*(b[1]-center[1])-(a[1]-center[1])*(b[0]-center[0]),
                                  (a[0]-center[0])*(b[0]-center[0])+(a[1]-center[1])*(b[1]-center[1]))
                        for a,b in zip(route.points,route.points[1:]))
            self.assertAlmostEqual(abs(winding),math.tau,places=5)
            for frame in range(1800):self.assertTrue(safe.contains(circuit_rect(route,frame/60).adjusted(-3,-3,3,3)))
            self.assertEqual(circuit_rect(route,0),circuit_rect(route,30))

    def test_dark_ghost_eyes_survive_an_additive_light_painter(self):
        image=QImage(100,100,QImage.Format_RGB32);image.fill(0)
        p=QPainter(image);p.setCompositionMode(QPainter.CompositionMode_Screen)
        simple_ghost(p,QRectF(10,10,80,80),0,'#fff4d9');p.end()
        self.assertGreater(image.pixelColor(50,27).red(),230)
        self.assertLess(image.pixelColor(40,40).red(),20)
        self.assertLess(image.pixelColor(61,40).red(),20)

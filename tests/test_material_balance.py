"""White painted trim must not overpower characters projected on brick."""
import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor,QImage
from nightfall.tone import brighten,balance_materials

APP=QApplication.instance() or QApplication([])


class MaterialBalanceTests(unittest.TestCase):
    def data(self):
        regions=[]
        for rid,kind,left in [('frame-right','frame',0),('curtain-r1','curtain',20),('bay-trim','edge',40)]:
            regions.append({'id':rid,'type':kind,'projector_points':[[left,0],[left+20,0],[left+20,20],[left,20]]})
        return {'regions':regions,'effects':{}}

    def test_white_surface_compensation_follows_global_gain_and_preserves_brick(self):
        image=QImage(80,20,QImage.Format_RGB32);image.fill(QColor(100,100,100))
        result=balance_materials(brighten(image,3),self.data(),'pumpkins',3)
        self.assertGreaterEqual(max(result.pixelColor(10,10).getRgb()[:3]),45)
        self.assertLessEqual(max(result.pixelColor(10,10).getRgb()[:3]),110)
        self.assertGreaterEqual(max(result.pixelColor(50,10).getRgb()[:3]),15)
        self.assertLessEqual(max(result.pixelColor(50,10).getRgb()[:3]),45)
        self.assertGreater(result.pixelColor(10,10).saturationF(),.95)
        self.assertGreater(result.pixelColor(50,10).saturationF(),.95)
        self.assertEqual(result.pixelColor(30,10).getRgb(),(115,115,115,255))
        self.assertEqual(result.pixelColor(70,10).getRgb(),(255,255,255,255))

    def test_occupied_bay_ledge_keeps_colour_but_gives_priority_to_pumpkins(self):
        source=QImage(80,20,QImage.Format_RGB32);source.fill(QColor(255,60,20))
        full=balance_materials(source.copy(),self.data(),'wisps',3)
        quiet=balance_materials(source.copy(),self.data(),'pumpkins',3)
        self.assertLess(quiet.pixelColor(50,10).red(),full.pixelColor(50,10).red()*.5)
        self.assertGreater(quiet.pixelColor(50,10).red(),quiet.pixelColor(50,10).green()*3)
        self.assertEqual(quiet.pixelColor(70,10),source.pixelColor(70,10))

    def test_material_mask_follows_geometry_edits(self):
        data=self.data();image=QImage(80,20,QImage.Format_RGB32);image.fill(QColor(255,255,255))
        first=balance_materials(image.copy(),data,'pumpkins',3)
        data['regions'][0]['projector_points']=[[60,0],[80,0],[80,20],[60,20]]
        moved=balance_materials(image.copy(),data,'pumpkins',3)
        self.assertLess(first.pixelColor(10,10).red(),100)
        self.assertEqual(moved.pixelColor(10,10).red(),255)
        self.assertLess(moved.pixelColor(70,10).red(),100)

    def test_ledge_light_does_not_jump_when_young_performers_enter_or_leave(self):
        image=QImage(80,20,QImage.Format_RGB32);image.fill(QColor(255,255,255))
        for time in [10,19,24]:
            before=balance_materials(image.copy(),self.data(),'young',time-.001)
            after=balance_materials(image.copy(),self.data(),'young',time+.001)
            self.assertLessEqual(abs(before.pixelColor(50,10).red()-after.pixelColor(50,10).red()),1)

    def test_dimming_changes_light_level_without_turning_trim_grey(self):
        image=QImage(80,20,QImage.Format_RGB32);image.fill(QColor(220,160,190))
        data=self.data();full=balance_materials(image.copy(),data,'waves',2).pixelColor(10,10)
        data['effects']['white_trim_level']=.19
        dim=balance_materials(image.copy(),data,'waves',2).pixelColor(10,10)
        self.assertGreater(full.saturationF(),.98);self.assertGreater(dim.saturationF(),.98)
        self.assertLessEqual(abs(full.hue()-dim.hue()),2)
        self.assertAlmostEqual(dim.valueF()/full.valueF(),.5,delta=.02)

    def test_two_pixel_strips_stay_visible_across_moving_effects(self):
        from nightfall import model
        from nightfall.renderer import render_scene
        data=model.default_project();data['effects'].update(architecture_strength=0,tree_strength=0)
        for r in data['regions']:r['enabled']=r['id']=='frame-attic'
        r=model.region(data,'frame-attic');r['projector_points']=[[100,100],[300,100],[300,102],[100,102]]
        r.pop('inner_region',None);r.pop('inner_regions',None)
        for mode in ['waves','electric','clockwork','haunted']:
            for t in [0,.125,1,2.5,4]:
                image=render_scene(data,t,mode)
                for x in range(120,280,4):
                    for y in [100,101]:
                        self.assertGreaterEqual(max(image.pixelColor(x,y).getRgb()[:3]),20,(mode,t,x,y))

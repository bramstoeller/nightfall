"""Run with QT_QPA_PLATFORM=offscreen python test_mapping.py."""
import copy, json, os, tempfile, unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from nightfall import model
from nightfall.renderer import render, uv_transform, glass_mask, path, box
from nightfall.gui import MainWindow
APP=QApplication.instance() or QApplication([])

class MappingTests(unittest.TestCase):
    def test_mapping_round_trip_and_snapshot(self):
        d=model.default_project();before=copy.deepcopy(d);model.move(d,'right',13,-4)
        for id in ['right','curtain-r1','curtain-r2']:
            p=model.region(d,id)['projector_points'][0];q=model.region(before,id)['projector_points'][0]
            self.assertAlmostEqual(p[0]-q[0],13);self.assertAlmostEqual(p[1]-q[1],-4)
        roof=copy.deepcopy(model.region(d,'roof')['projector_points']);d['alignment']['anchors'][0]['point'][0]+=2
        self.assertEqual(model.region(d,'roof')['projector_points'],roof,'anchor must not mutate geometry')
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'mapping.json';model.save(d,f);self.assertEqual(model.load(f),d)
    def test_invalid_geometry(self):
        d=model.default_project();model.region(d,'right')['projector_points']=[[0,0],[30,30],[30,0],[0,30]]
        with self.assertRaises(ValueError):model.validate(d)
    def test_paper_and_tree_occlusion(self):
        from PySide6.QtCore import QPointF
        from nightfall.renderer import glass_mask,path
        d=model.default_project();sample=uv_transform(model.region(d,'right')['projector_points']).map(QPointF(.7,.25))
        self.assertTrue(glass_mask(d).contains(sample));model.region(d,'right')['paper_screen']=True
        self.assertFalse(glass_mask(d).contains(sample))
        shape=path(model.region(d,'right')['projector_points']);im=render(d,10,'young')
        b=shape.boundingRect();self.assertTrue(any(im.pixelColor(x,y).lightness()>80 for x in range(int(b.left())+3,int(b.right())-3,2) for y in range(int(b.top())+3,int(b.bottom())-3,2) if shape.contains(QPointF(x,y))))
        model.region(d,'tree')['enabled']=False
        for show in ['young','older']:
            im=render(d,8.03,show);tree=path(model.region(d,'tree')['projector_points'])
            # The foreground boundary must block the wall as fully as its
            # centre; a feathered leaf effect cannot reveal blue wall light.
            b=tree.boundingRect()
            for x in range(int(b.left())+3,int(b.right())-3,5):
                for y in range(int(b.top())+3,int(b.bottom())-3,5):
                    if tree.contains(QRectF(x-2,y-2,4,4)):self.assertEqual(im.pixelColor(x,y).lightness(),0)
    def test_loop_and_glass(self):
        d=model.default_project()
        for show in ['young','older']:
            a=render(d,0,show);b=render(d,120,show);self.assertEqual(bytes(a.constBits()),bytes(b.constBits()))
            a=render(d,119.9999,show);b=render(d,0,show)
            # Rounded sprite strip edges have a tiny rasterization tolerance.
            diff=sum(abs(x-y) for x,y in zip(bytes(a.constBits()),bytes(b.constBits())))
            self.assertLess(diff,12000)
            for r in d['regions']:
                if r['type']=='window':r['enabled']=False
            for t in [0,2,8,8.03,8.2,24.05,39.05,69,115.03,119.97]:
                im=render(d,t,show)
                for r in d['regions']:
                    if r['type']!='window' or r['id']=='left':continue
                    for u in [.25,.75]:
                        q=uv_transform(r['projector_points']).map(QPointF(u,.25));color=im.pixelColor(round(q.x()),round(q.y()));self.assertEqual(color.red()+color.green()+color.blue(),0)
    def test_gui_move_undo_and_lock(self):
        w=MainWindow();w.show();APP.processEvents();w.select('right');original=copy.deepcopy(w.current()['projector_points']);w.editor.vertex=0;w.editor.setFocus();QTest.keyClick(w.editor,Qt.Key_Right);self.assertEqual(w.current()['projector_points'][0][0],original[0][0]+1);w.undo();self.assertEqual(w.current()['projector_points'],original)
        w.lock.setChecked(True);QTest.keyClick(w.editor,Qt.Key_Right);self.assertEqual(w.current()['projector_points'],original);self.assertFalse(w.x.isEnabled())
        # Real pointer drag of an entire window must move both curtains.
        w.lock.setChecked(False);w.select('right');pts=w.current()['projector_points'];center=QPointF(sum(p[0] for p in pts)/4,sum(p[1] for p in pts)/4);k,off=w.editor.transform();pos=(center*k+off).toPoint();before=copy.deepcopy(w.data)
        QTest.mousePress(w.editor,Qt.LeftButton,pos=pos);QTest.mouseMove(w.editor,pos+QPoint(10,5));QTest.mouseRelease(w.editor,Qt.LeftButton,pos=pos+QPoint(10,5))
        for id in ['right','curtain-r1','curtain-r2']:
            a=model.region(w.data,id)['projector_points'][0];b=model.region(before,id)['projector_points'][0];self.assertAlmostEqual(a[0]-b[0],10/k,places=4)
        w.projector.show();APP.processEvents();QTest.keyClick(w.projector,Qt.Key_Escape);self.assertFalse(w.projector.isVisible());w.dirty=False;w.close()

if __name__=='__main__':unittest.main()

class CompatibilityTests(unittest.TestCase):
    def test_old_project_schema_loads_without_changing_geometry(self):
        raw=json.loads((model.ROOT/'examples/house.json').read_text())
        raw['schema']='nachtwerk.projector-map'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'legacy.json';path.write_text(json.dumps(raw))
            loaded=model.load(path)
        self.assertEqual(loaded['schema'],model.SCHEMA)
        self.assertEqual(loaded['regions'],raw['regions'])
        self.assertEqual(loaded['exclusions'],raw['exclusions'])

    def test_obsolete_offscreen_lamp_mask_is_removed_from_older_projects(self):
        raw=json.loads((model.ROOT/'examples/house.json').read_text())
        original=copy.deepcopy(raw['exclusions'])
        raw['schema']='nachtwerk.projector-map'
        raw['exclusions'].append({'id':'exclusion-lamp','type':'exclusion','color':'#ff657b',
                                  'projector_points':[[70,630],[74,630],[88,980],[84,980]]})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'legacy.json';path.write_text(json.dumps(raw))
            loaded=model.load(path)
        self.assertEqual(loaded['exclusions'],original)
        self.assertEqual(loaded['regions'],raw['regions'])

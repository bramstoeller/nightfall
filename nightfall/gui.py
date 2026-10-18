from __future__ import annotations
import base64, copy, json, sys, time, uuid
from collections import deque
from pathlib import Path
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, QProcess, QEvent, QTime
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPen, QKeySequence, QShortcut, QTransform
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QComboBox, QPushButton, QCheckBox, QLabel, QFileDialog, QMessageBox, QDoubleSpinBox, QSlider, QInputDialog, QSplitter, QFormLayout, QScrollArea, QMenu, QTimeEdit)
from . import model
from .renderer import render, path, alignment_shapes, uv_transform
from .video import VideoPlayer
from .effects import STYLES
from . import render_cache
from .runtime import render_command

def edit_corner(data,rid,index,point):
    """Keep the window's frame and fabric attached when its quad changes."""
    r=model.region(data,rid);before=copy.deepcopy(r['projector_points'])
    r['projector_points'][index]=point
    if len(before)==4:
        inv,ok=uv_transform(before).inverted();after=uv_transform(r['projector_points'])
        ids={rid}
        while True:
            expanded=ids|{q['id'] for q in model.editable_shapes(data) if q.get('parent') in ids or q.get('deform_parent') in ids}
            if expanded==ids:break
            ids=expanded
        for child in model.editable_shapes(data):
            if child['id'] in ids and child['id']!=rid:
                child['projector_points']=[[q.x(),q.y()] for q in (after.map(inv.map(QPointF(*p))) for p in child['projector_points'])]
        model.invalidate_alignment(data,ids)
        model.sync_vertices(data,[(rid,index)]+[(child['id'],i) for child in model.editable_shapes(data) if child['id'] in ids for i in range(len(child['projector_points']))])
    else:
        affected={rid};dx,dy=point[0]-before[index][0],point[1]-before[index][1]
        for child in model.editable_shapes(data):
            if child.get('parent')==rid and child.get('anchor_vertex')==index:
                child['projector_points']=[[x+dx,y+dy] for x,y in child['projector_points']];affected.add(child['id'])
        model.invalidate_alignment(data,affected);model.sync_vertices(data,[(rid,index)])

MODES=[('Contour lines','wireframe'),('Filled regions','fills'),('Selection only','selected'),('Rotation and tilt reference','alignment'),('Younger children','young'),('Older children','older'),('Black','black')]

class Projector(QWidget):
    def __init__(self,owner):
        super().__init__(None,Qt.Window|Qt.FramelessWindowHint)
        self.owner=owner;self.blacked_out=False;self.target_screen=None
        self.setWindowTitle('Nightfall — projector output');self.setCursor(Qt.BlankCursor)
        self.geometry_timer=QTimer(self);self.geometry_timer.setSingleShot(True)
        self.geometry_timer.timeout.connect(self.ensure_screen_geometry)
        QApplication.instance().screenRemoved.connect(self.screen_removed)
    def show_on(self,screen):
        self.target_screen=screen
        # Place the entire window before its first native show. Moving a window
        # while it is already fullscreen can retain the previous monitor's size
        # on Windows, especially when the monitors have different DPI settings.
        if not self.isVisible() or not self.isFullScreen() or self.screen()!=screen or self.geometry()!=screen.geometry():
            self.place_on_screen()
        self.geometry_timer.start(0)
        self.update()
    def place_on_screen(self):
        screen=self.target_screen
        self.hide();self.setWindowState(Qt.WindowNoState)
        # QWidget.setScreen also works before a native window exists; winId()
        # would create that window on the laptop first.
        self.setScreen(screen);self.setGeometry(screen.geometry())
        self.showFullScreen()
        handle=self.windowHandle()
        if handle!=getattr(self,'_observed_window',None):
            handle.screenChanged.connect(self.schedule_geometry_check)
            self._observed_window=handle
        self.raise_()
    def schedule_geometry_check(self,*args):
        if self.isVisible() and self.target_screen is not None:self.geometry_timer.start(0)
    def resizeEvent(self,e):
        super().resizeEvent(e)
        self.schedule_geometry_check()
    def ensure_screen_geometry(self):
        screen=self.target_screen
        if not self.isVisible() or screen not in QApplication.screens():return
        # Recheck after queued native screen/DPI events have been processed.
        if not self.isFullScreen() or self.screen()!=screen or self.geometry()!=screen.geometry():self.place_on_screen()
    def screen_removed(self,screen):
        if screen==self.target_screen:
            self.hide();self.target_screen=None
    def paintEvent(self,e):
        p=QPainter(self);p.setRenderHint(QPainter.SmoothPixmapTransform);p.fillRect(self.rect(),Qt.black)
        im=self.owner.video_frame if self.owner.video.active or self.owner.live_mode else self.owner.frame
        if not self.blacked_out and not im.isNull():
            k=min(self.width()/model.WIDTH,self.height()/model.HEIGHT);r=QRectF((self.width()-model.WIDTH*k)/2,(self.height()-model.HEIGHT*k)/2,model.WIDTH*k,model.HEIGHT*k);p.drawImage(r,im)
            if self.owner.video.active or self.owner.live_mode:self.owner.record_video_paint('projector')
    def keyPressEvent(self,e):
        if e.key()==Qt.Key_Escape:self.owner.stop_video();self.hide()
        else:self.owner.editor.keyPressEvent(e)
    def showEvent(self,e):
        if hasattr(self.owner,'projector_button'):self.owner.projector_button.setText('Projector on' if self.blacked_out else 'Projector off')
        super().showEvent(e)
    def hideEvent(self,e):
        self.geometry_timer.stop()
        if hasattr(self.owner,'projector_button'):self.owner.projector_button.setText('Projector on')
        super().hideEvent(e)

class Editor(QWidget):
    def __init__(self,owner):
        super().__init__();self.o=owner;self.zoom=1.;self.pan=QPointF();self.drag=None;self.vertex=-1;self.setFocusPolicy(Qt.StrongFocus);self.setMinimumSize(400,280)
    def transform(self):
        k=min(self.width()/model.WIDTH,self.height()/model.HEIGHT)*self.zoom
        return k,QPointF((self.width()-model.WIDTH*k)/2,(self.height()-model.HEIGHT*k)/2)+self.pan
    def view_transform(self):
        k,off=self.transform();view=self.o.data.get('editor_view',{})
        if self.o.mode=='mapping' and view.get('centre_origin'):
            x,y=model.origin_point(self.o.data) or [model.WIDTH/2,model.HEIGHT/2]
            tr=QTransform();tr.translate(self.width()/2+self.pan.x(),self.height()/2+self.pan.y())
            tr.scale(k,k);tr.rotate(view.get('rotation_degrees',0));tr.translate(-x,-y)
            return tr
        return QTransform(k,0,0,k,off.x(),off.y())
    def event(self,e):
        if e.type()==QEvent.KeyPress and e.key()==Qt.Key_Tab:
            self.keyPressEvent(e);return True
        return super().event(e)
    def to_pixel(self,pos):
        inv,ok=self.view_transform().inverted();q=inv.map(pos);return [q.x(),q.y()]
    def paintEvent(self,e):
        p=QPainter(self);p.setRenderHint(QPainter.SmoothPixmapTransform);p.fillRect(self.rect(),QColor('#101216'))
        if (self.o.video.active or self.o.live_mode) and not self.o.video_frame.isNull():
            # Mirror the exact decoded/rendered frame; never render it twice.
            k=min(self.width()/model.WIDTH,self.height()/model.HEIGHT)
            target=QRectF((self.width()-model.WIDTH*k)/2,(self.height()-model.HEIGHT*k)/2,model.WIDTH*k,model.HEIGHT*k)
            p.drawImage(target,self.o.video_frame);self.o.record_video_paint('laptop');return
        k,off=self.transform();p.setTransform(self.view_transform())
        if self.o.photo_check.isChecked() and not self.o.reference.isNull():
            p.save();p.setOpacity(1 if self.o.mode=='mapping' else .45)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            h=self.o.reference_transform
            if h:
                tr=QTransform(h[0][0],h[1][0],h[2][0],h[0][1],h[1][1],h[2][1],h[0][2],h[1][2],h[2][2])
                p.setTransform(tr,True);p.drawImage(0,0,self.o.reference)
            else:
                b=self.o.reference_placement;p.drawImage(QRectF(b.get('x',370),b.get('y',0),b.get('width',540),b.get('height',model.HEIGHT)),self.o.reference)
            p.restore()
        if self.o.photo_check.isChecked():p.setCompositionMode(QPainter.CompositionMode_Screen)
        p.drawImage(0,0,self.o.frame);p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        if self.o.data.get('locked'):return
        p.setRenderHint(QPainter.Antialiasing)
        if self.o.mode=='alignment':
            handles=[a['point'] for a in self.o.data['alignment']['anchors']];color='#ffffff'
        else:handles=self.o.current()['projector_points'];color=self.o.current()['color']
        for i,(x,y) in enumerate(handles):
            p.setPen(QPen(QColor('#ffffff' if i==self.vertex else color),1.5/k));p.setBrush(QColor('#101216'));p.drawEllipse(QPointF(x,y),5/k,5/k)
        if self.o.mode!='mapping':
            p.setPen(QPen(QColor('#eeeeee'),1/k));p.setBrush(Qt.NoBrush);p.drawRect(QRectF(0,0,model.WIDTH,model.HEIGHT))
    def wheelEvent(self,e):
        if self.o.video.active or self.o.live_mode:return
        old=self.to_pixel(e.position());self.zoom=max(.5,min(10,self.zoom*(1.2 if e.angleDelta().y()>0 else 1/1.2)));self.pan+=e.position()-self.view_transform().map(QPointF(*old));self.update()
    def mousePressEvent(self,e):
        self.setFocus();self.o.note('')
        if self.o.video.active or self.o.live_mode:
            if e.button()==Qt.LeftButton:self.o.stop_video()
            return
        if e.button()==Qt.MiddleButton:self.drag=('pan',e.position(),QPointF(self.pan));return
        if e.button()!=Qt.LeftButton or self.o.data.get('locked'):return
        pos=self.to_pixel(e.position());k,_=self.transform();handles=[a['point'] for a in self.o.data['alignment']['anchors']] if self.o.mode=='alignment' else self.o.current()['projector_points']
        if self.o.mode=='mapping':
            choices=[]
            for r in alignment_shapes(self.o.data):
                for i,q in enumerate(r['projector_points']):
                    d=((q[0]-pos[0])**2+(q[1]-pos[1])**2)**.5*k
                    choices.append((d,r['id']!=self.o.selected,r['id'],i))
            best=min(choices)
            if best[0]<12:
                self.o.select(best[2]);handles=self.o.current()['projector_points']
                self.vertex=best[3];self.o.checkpoint();self.drag=('edit',pos,copy.deepcopy(self.o.data));self.o.sync_coordinates();self.o.refresh();return
            # Select by distance to a line, rather than the large filled mask.
            edges=[]
            for r in alignment_shapes(self.o.data):
                pts=r['projector_points']
                for i,a in enumerate(pts):
                    b=pts[(i+1)%len(pts)];dx,dy=b[0]-a[0],b[1]-a[1]
                    v=max(0,min(1,((pos[0]-a[0])*dx+(pos[1]-a[1])*dy)/(dx*dx+dy*dy or 1)))
                    d=((pos[0]-a[0]-v*dx)**2+(pos[1]-a[1]-v*dy)**2)**.5*k
                    edges.append((d,r['id']!=self.o.selected,r['id']))
            edge=min(edges)
            if edge[0]>12:return
            self.o.select(edge[2]);self.vertex=-1;self.o.checkpoint();self.drag=('edit',pos,copy.deepcopy(self.o.data));self.o.sync_coordinates();self.update();return
        self.vertex=next((i for i,q in enumerate(handles) if ((q[0]-pos[0])**2+(q[1]-pos[1])**2)**.5*k<12),-1)
        if self.o.mode=='alignment':
            if self.vertex<0:return
        elif self.vertex<0 and not path(self.o.current()['projector_points']).contains(QPointF(*pos)):
            found=next((r for r in reversed(model.editable_shapes(self.o.data)) if path(r['projector_points']).contains(QPointF(*pos))),None)
            if not found:return
            self.o.select(found['id'])
        self.o.checkpoint();self.drag=('edit',pos,copy.deepcopy(self.o.data));self.o.sync_coordinates();self.update()
    def mouseMoveEvent(self,e):
        if not self.drag:return
        kind,start,base=self.drag
        if kind=='pan':self.pan=base+e.position()-start;self.update();return
        pos=self.to_pixel(e.position());candidate=copy.deepcopy(base)
        if self.o.mode=='alignment':
            candidate['alignment']['anchors'][self.vertex]['point']=[max(0,min(model.WIDTH,pos[0])),max(0,min(model.HEIGHT,pos[1]))]
        elif self.vertex>=0:
            edit_corner(candidate,self.o.selected,self.vertex,[max(0,min(model.WIDTH,pos[0])),max(0,min(model.HEIGHT,pos[1]))])
        else:model.move(candidate,self.o.selected,pos[0]-start[0],pos[1]-start[1])
        try:model.validate(candidate)
        except ValueError:return
        self.o.data=candidate;self.o.dirty=True;self.o.sync_coordinates();self.o.refresh()
    def mouseReleaseEvent(self,e):
        self.drag=None;self.o.update_title()
    def mouseDoubleClickEvent(self,e):
        if self.o.data.get('locked') or self.o.mode=='alignment':return
        r=self.o.current()
        if r['type'] in ('curtain','window','stage') or r.get('role')=='window-inner' or r.get('shape')=='ellipse':
            self.o.note('Window and curtain regions keep four corners.');return
        q=self.to_pixel(e.position());pts=r['projector_points'];best=(float('inf'),None);k,_=self.transform()
        for i,a in enumerate(pts):
            b=pts[(i+1)%len(pts)];dx,dy=b[0]-a[0],b[1]-a[1];v=max(0,min(1,((q[0]-a[0])*dx+(q[1]-a[1])*dy)/(dx*dx+dy*dy or 1)));d=((q[0]-a[0]-v*dx)**2+(q[1]-a[1]-v*dy)**2)**.5
            if d<best[0]:best=(d,i)
        if best[0]*k>18:return
        self.o.checkpoint();model.insert_vertex(self.o.data,r['id'],best[1]+1,[max(0,min(model.WIDTH,q[0])),max(0,min(model.HEIGHT,q[1]))]);self.vertex=best[1]+1;self.o.dirty=True;self.o.sync_coordinates();self.o.refresh()
    def keyPressEvent(self,e):
        if self.o.data.get('locked'):return
        steps={Qt.Key_Left:(-1,0),Qt.Key_Right:(1,0),Qt.Key_Up:(0,-1),Qt.Key_Down:(0,1)}
        if e.key() in steps:
            if self.o.video.active or self.o.live_mode:self.o.stop_video()
            dx,dy=steps[e.key()];step=10 if e.modifiers()&Qt.ShiftModifier else .25 if e.modifiers()&Qt.ControlModifier else 1
            self.o.checkpoint();candidate=copy.deepcopy(self.o.data)
            if self.o.mode=='alignment' and self.vertex>=0:
                p=candidate['alignment']['anchors'][self.vertex]['point'];p[0]=max(0,min(model.WIDTH,p[0]+dx*step));p[1]=max(0,min(model.HEIGHT,p[1]+dy*step))
            elif self.vertex>=0:
                p=model.region(candidate,self.o.selected)['projector_points'][self.vertex]
                edit_corner(candidate,self.o.selected,self.vertex,[max(0,min(model.WIDTH,p[0]+dx*step)),max(0,min(model.HEIGHT,p[1]+dy*step))])
            elif self.o.mode!='alignment':model.move(candidate,self.o.selected,dx*step,dy*step)
            try:model.validate(candidate)
            except ValueError:return
            self.o.data=candidate;self.o.dirty=True;self.o.sync_coordinates();self.o.refresh()
        elif e.key()==Qt.Key_Delete and self.vertex>=0 and self.o.mode!='alignment':
            r=self.o.current()
            if r['type'] in ('window','curtain','stage') or r.get('role')=='window-inner' or r.get('shape')=='ellipse' or len(r['projector_points'])<=3:return
            self.o.checkpoint();model.delete_vertex(self.o.data,r['id'],self.vertex);self.vertex=-1;self.o.dirty=True;self.o.sync_coordinates();self.o.refresh()
        elif e.key()==Qt.Key_0:self.zoom=1;self.pan=QPointF();self.update()
        elif e.key()==Qt.Key_Tab:
            self.vertex=(self.vertex+1)%len(self.o.current()['projector_points']);self.o.sync_coordinates();self.o.refresh()
        else:super().keyPressEvent(e)

class MainWindow(QMainWindow):
    def simplify(self):
        # Keep existing save/undo/projector mechanics; show one alignment canvas.
        old=self.takeCentralWidget();old.hide();old.setParent(self);self._old_controls=old
        panel=QWidget();layout=QVBoxLayout(panel);bar=QHBoxLayout();layout.addLayout(bar)
        for label,fn in [('Open',self.open_map),('Save',self.save_map),('Projector on',self.toggle_projector),('Video',self.choose_video),('Render video',self.render_animation)]:
            button=QPushButton(label);button.clicked.connect(fn);bar.addWidget(button)
            if label=='Projector on':self.projector_button=button;self.blackout_button=button
            if label=='Video':self.video_button=button
            if label=='Render video':self.render_button=button
        self.photo_button=QPushButton();self.photo_button.clicked.connect(self.toggle_reference_photo);bar.addWidget(self.photo_button)
        self.update_photo_button()
        bar.addWidget(QLabel('Brave visitors at'))
        self.switch_time=QTimeEdit();self.switch_time.setDisplayFormat('HH:mm');self.switch_time.setKeyboardTracking(False)
        self.switch_time.setToolTip('Local laptop time. Start automatic switching via Video → Halloween tour.')
        self.sync_switch_time();self.switch_time.timeChanged.connect(self.set_switch_time);bar.addWidget(self.switch_time)
        bar.addStretch();self.simple_status=QLabel();bar.addWidget(self.simple_status)
        playback_bar=QHBoxLayout();layout.addLayout(playback_bar)
        self.playback_status=QLabel();self.playback_status.setStyleSheet('font-size:18px;font-weight:bold;color:#8fe4bb;padding:8px')
        self.playback_status.setToolTip('Unique video frames painted by this app, averaged over two seconds. This does not measure the physical display refresh rate.')
        playback_bar.addWidget(self.playback_status,1)
        self.preview_check=QCheckBox('Preview on this screen only');self.preview_check.setChecked(self.preview_only)
        self.preview_check.setToolTip('Keep the video and FPS visible in the editor without opening fullscreen projector output.')
        self.preview_check.toggled.connect(self.set_preview_only);playback_bar.addWidget(self.preview_check)
        display_bar=QHBoxLayout();layout.addLayout(display_bar)
        display_bar.addWidget(QLabel('Projector display'));display_bar.addWidget(self.screens,1)
        self.editor.setParent(panel);layout.addWidget(self.editor,1)
        hint=QLabel('Click a corner or edge · arrows: 1 px · Shift: 10 px · Ctrl: ¼ px · Tab: next corner · Ctrl+Z: undo · wheel: zoom · 0: fit')
        layout.addWidget(hint);self.setCentralWidget(panel)
        self.photo_check.setChecked(True);self.mode='mapping';self.editor.vertex=-1
        self.data['locked']=False;self.lock.setChecked(False);self.dirty=False
        self.select('right');self.refresh();self.editor.setFocus()
    def update_photo_button(self):
        if not hasattr(self,'photo_button'):return
        self.photo_button.setVisible('day' in self.data.get('reference_photos',{}))
        self.photo_button.setText('Reference: day' if self.data.get('editor_photo')=='day' else 'Reference: night')
        self.photo_button.setToolTip('Switch between day and night references. Projector points stay fixed.')
    def toggle_reference_photo(self):
        if 'day' not in self.data.get('reference_photos',{}):return
        self.data['editor_photo']='night' if self.data.get('editor_photo')=='day' else 'day'
        self.read_reference();self.dirty=True;self.update_title();self.editor.update();self.editor.setFocus()
    def tour_switch_time(self):
        value=QTime.fromString(self.data.get('show_schedule',{}).get('switch_time','19:00'),'HH:mm')
        return value if value.isValid() else QTime(19,0)
    def sync_switch_time(self):
        if not hasattr(self,'switch_time'):return
        self.switch_time.blockSignals(True);self.switch_time.setTime(self.tour_switch_time());self.switch_time.blockSignals(False)
    def set_switch_time(self,value):
        self.data.setdefault('show_schedule',{})['switch_time']=value.toString('HH:mm')
        self.dirty=True;self.update_title();self.tour_switched=False;self.check_tour_time()
    def start_tour(self):
        self.stop_video();self.animation_mode='tour';self.tour_active=True;self.tour_stage=None;self.tour_switched=False
        self.check_tour_time()
    def check_tour_time(self,now=None):
        if not self.tour_active:return
        now=QTime.currentTime() if now is None else now
        if now>=self.tour_switch_time():self.tour_switched=True
        stage='older' if self.tour_switched else 'young'
        if stage==self.tour_stage:return
        preserve_blackout=self.tour_stage is not None and self.projector.blacked_out
        self.tour_stage=stage;self.play_house_animation(stage,automatic=True)
        if preserve_blackout:
            self.projector.blacked_out=True;self.projector.update()
            if hasattr(self,'projector_button'):self.projector_button.setText('Projector on')
        self.tour_active=bool(self.video.active or self.live_mode)
        name='Brave visitors' if stage=='older' else 'Children'
        self.note(name+' · switch time '+self.tour_switch_time().toString('HH:mm'))
    def simple_blackout(self):
        self.toggle_projector()
    def toggle_projector(self):
        if not self.projector.isVisible() or self.projector.blacked_out:self.show_projector()
        else:
            self.projector.blacked_out=True;self.projector_button.setText('Projector on');self.projector.update()
        self.editor.setFocus()
    def choose_video(self):
        if self.video.active or self.live_mode:self.stop_video();return
        menu=QMenu(self)
        menu.addAction('Open video file…').setData('file')
        menu.addSeparator()
        menu.addAction('Halloween tour · children → brave visitors at '+self.tour_switch_time().toString('HH:mm')).setData('tour')
        menu.addSeparator()
        for mode in ['show']+[key for key in STYLES if key!='show']:
            name=STYLES[mode][0]
            menu.addAction(name).setData(mode)
        chosen=menu.exec(self.video_button.mapToGlobal(QPoint(0,self.video_button.height())))
        if chosen:
            if chosen.data()=='file':self.open_video()
            else:self.play_house_animation(chosen.data())
    def open_video(self):
        filename,_=QFileDialog.getOpenFileName(self,'Play video','','Videos (*.mp4 *.mkv *.mov)')
        if filename:self.play_animation(filename)
    def set_preview_only(self,enabled):
        self.preview_only=enabled
        if self.video.active or self.live_mode:
            if enabled:self.projector.hide()
            else:self.show_projector()
    def show_playback_output(self):
        if self.preview_only:self.projector.hide()
        else:self.show_projector()
    def play_house_animation(self,mode,automatic=False):
        if mode=='tour':self.start_tour();return
        if not automatic:self.tour_active=False;self.animation_mode=mode
        cached=render_cache.video(self.data,mode)
        if cached.exists():self.play_animation(str(cached));return
        self.play_live_animation(mode)
        self.note('Live preview · click Render video to export the current effects at 60 fps.')
    def render_animation(self):
        if self.process and self.process.state()!=QProcess.NotRunning:
            self.stop_render();return
        title='Gentle and spooky shows'
        folder=render_cache.folder(self.data)
        folder.mkdir(parents=True,exist_ok=True)
        model.save(copy.deepcopy(self.data),folder/'render-input.json')
        self.stop_video()
        self.render_cancelled=False;self.render_cancel_file=folder/('.stop-render-'+uuid.uuid4().hex)
        self.process=QProcess(self);self.process.setProgram(sys.executable)
        self.process.setArguments(render_command(str(folder/'render-input.json'),'--out',str(folder),'--show','both','--seconds','120','--overwrite','--cancel-file',str(self.render_cancel_file)))
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.render_button.setEnabled(True);self.render_button.setText('Stop render · 0%')
        self.render_log=''
        def output():
            self.render_log+=bytes(self.process.readAllStandardOutput()).decode(errors='replace')
            import re
            stages=re.findall(r'(young|older): (\d+)%',self.render_log)
            workers=re.findall(r'Render workers: (\d+)',self.render_log)
            speeds=re.findall(r'([\d.]+) renderfps',self.render_log)
            if (stages or workers) and not self.render_cancelled:
                percent=(50 if stages[-1][0]=='older' else 0)+int(stages[-1][1])//2 if stages else 0
                label=(' · CPU ×'+workers[-1]) if workers else ''
                self.render_button.setText('Stop render'+label+' · '+str(percent)+'%')
                if speeds:self.render_button.setToolTip('Render speed: '+speeds[-1]+' frames/s. The exported video remains 60 fps.')
        def done(code,status):
            output();self.render_button.setEnabled(True);self.render_button.setText('Render video')
            self.render_cancel_file.unlink(missing_ok=True)
            if self.render_cancelled:self.note('Render stopped · completed videos have been kept.')
            elif code==0:self.note(title+' ready · start via Video → Halloween tour')
            else:QMessageBox.warning(self,'Render failed',self.render_log[-1800:] or 'FFmpeg could not be started.')
        self.process.readyReadStandardOutput.connect(output);self.process.finished.connect(done)
        self.process.errorOccurred.connect(lambda error:done(1,None) if error==QProcess.FailedToStart else None)
        self.process.start();self.note('Render: '+title+' · 60 fps · 2 × 120 s')
    def stop_render(self):
        if not self.process or self.process.state()==QProcess.NotRunning or getattr(self,'render_cancelled',False):return
        if not hasattr(self,'render_cancel_file'):return
        self.render_cancel_file.write_text('stop\n')
        self.render_cancelled=True;self.render_button.setEnabled(False);self.render_button.setText('Stopping render…')
        self.note('Stopping render · removing the incomplete video.')
    def play_live_animation(self,mode):
        self.stop_video(cancel_tour=False);self.playing=False;self.live_mode=mode;self.live_play_origin=time.monotonic()
        self.video_frame=render(self.data,0,mode);self.video_button.setText('Stop video');self.show_playback_output()
        if hasattr(self,'playback_status'):self.playback_status.setText('Live preview · measuring FPS…')
    def play_animation(self,filename):
        try:
            self.stop_video(cancel_tour=False);self.playing=False
            self.video.start(filename);self.video_frame=QImage(model.WIDTH,model.HEIGHT,QImage.Format_RGB32);self.video_frame.fill(Qt.black)
            self.video_button.setText('Stop video');self.show_playback_output();self.note('Video loops until you click Stop video.')
            if hasattr(self,'playback_status'):self.playback_status.setText('Video playback · measuring FPS…')
        except RuntimeError as e:QMessageBox.warning(self,'Video',str(e))
    def receive_video(self,frame):self.video_frame=frame;self.projector.update();self.editor.update()
    def record_video_paint(self,screen):
        key=self.video_frame.cacheKey()
        if self.display_keys.get(screen)==key:return
        self.display_keys[screen]=key;self.display_times[screen].append(time.monotonic())
    def update_display_rate(self):
        now=time.monotonic()
        if now-self.display_update<1 or not hasattr(self,'playback_status'):return
        self.display_update=now;elapsed=min(2,max(.01,now-self.display_start));rates={}
        for screen,times in self.display_times.items():
            while times and times[0]<now-2:times.popleft()
            rates[screen]=round(len(times)/elapsed)
        kind='Live preview' if self.live_mode else 'Video'
        projector=f"{rates['projector']} fps" if self.projector.isVisible() and not self.projector.blacked_out else 'off'
        self.playback_status.setText(f"{kind} · Main screen: {rates['laptop']} fps · Projector: {projector}")
    def stop_video(self,cancel_tour=True):
        if cancel_tour:self.tour_active=False;self.tour_stage=None
        self.live_mode=None;self.video.stop();self.video_stopped()
    def video_stopped(self):
        if hasattr(self,'video_button'):self.video_button.setText('Video')
        self.video_frame=QImage();self.projector.update();self.editor.update()
        self.display_times={'projector':deque(),'laptop':deque()};self.display_keys={}
        self.display_start=time.monotonic();self.display_update=self.display_start
        if hasattr(self,'playback_status'):self.playback_status.clear()
        if hasattr(self,'simple_status'):self.refresh();self.simple_status.setToolTip('')
    def __init__(self,data=None):
        super().__init__();self.data=data or model.default_project();self.selected='roof';self.mode='wireframe';self.filename=None;self.dirty=False;self.undo_stack=[];self.redo_stack=[];self.t=0.;self.playing=False;self.process=None;self.frame=QImage();self.reference=QImage();self.setWindowTitle('Nightfall — projection mapping');self.resize(1360,900)
        self.preview_only=False
        self.live_mode=None;self.live_play_origin=0.;self.video_frame=QImage();self.video=VideoPlayer(self);self.video.frame_ready.connect(self.receive_video);self.video.stopped.connect(self.video_stopped)
        self.tour_active=False;self.tour_stage=None;self.tour_switched=False
        self.display_times={'projector':deque(),'laptop':deque()};self.display_keys={}
        self.display_start=time.monotonic();self.display_update=self.display_start
        self.video.failed.connect(lambda message:QMessageBox.warning(self,'Video',message))
        root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root);bar=QHBoxLayout();outer.addLayout(bar)
        for text,fn in [('Open mapping',self.open_map),('Save mapping',self.save_map),('Grid calibration',self.import_calibration),('Load reference',self.load_photo),('Setup',self.setup_notes),('Render both MP4s',self.export)]:
            b=QPushButton(text);b.clicked.connect(fn);bar.addWidget(b)
        self.lock=QCheckBox('Lock alignment');self.lock.setChecked(self.data.get('locked',False));self.lock.toggled.connect(self.set_locked);bar.addWidget(self.lock)
        body=QSplitter();outer.addWidget(body,1);side=QWidget();sl=QVBoxLayout(side);self.list=QListWidget();self.list.setMinimumHeight(250);sl.addWidget(self.list);self.list.currentRowChanged.connect(self.select_row)
        row=QHBoxLayout();sl.addLayout(row)
        for text,fn in [('Undo',lambda:self.undo()),('Redo',lambda:self.undo(True))]:b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        self.global_button=QPushButton('Move / scale everything');self.global_button.clicked.connect(self.global_fit);sl.addWidget(self.global_button);self.enabled=QCheckBox('Enable effect');self.enabled.toggled.connect(self.set_enabled);sl.addWidget(self.enabled)
        self.paper=QCheckBox('Use window as a projection screen');self.paper.toggled.connect(self.set_paper);sl.addWidget(self.paper)
        self.note_label=QLabel();self.note_label.setWordWrap(True);sl.addWidget(self.note_label)
        self.aligned=QPushButton('Mark region aligned');self.aligned.clicked.connect(self.mark_aligned);sl.addWidget(self.aligned)
        form=QFormLayout();sl.addLayout(form);self.vertex_box=QComboBox();self.vertex_box.currentIndexChanged.connect(self.choose_vertex);form.addRow('Point',self.vertex_box)
        self.x=QDoubleSpinBox();self.y=QDoubleSpinBox()
        for spin,maximum in [(self.x,model.WIDTH),(self.y,model.HEIGHT)]:spin.setRange(0,maximum);spin.setDecimals(2);spin.setSingleStep(.25);spin.editingFinished.connect(self.coordinates_changed)
        form.addRow('X (projector pixel)',self.x);form.addRow('Y (projector pixel)',self.y)
        self.relative=QCheckBox('Coordinates from window corner');self.relative.setChecked(model.origin_point(self.data) is not None);self.relative.toggled.connect(self.sync_coordinates);sl.addWidget(self.relative)
        self.origin_label=QLabel();self.origin_label.setWordWrap(True);sl.addWidget(self.origin_label)
        self.origin_button=QPushButton('Use this window corner as origin');self.origin_button.clicked.connect(self.set_origin);sl.addWidget(self.origin_button)
        self.gain=QDoubleSpinBox();self.gain.setRange(0,100);self.gain.setSuffix(' %');self.gain.editingFinished.connect(self.gain_changed);form.addRow('Region brightness',self.gain)
        self.frame_width=QDoubleSpinBox();self.frame_width.setRange(.25,100);self.frame_width.setSingleStep(.25);self.frame_width.editingFinished.connect(self.frame_width_changed);form.addRow('Frame width (px)',self.frame_width)
        self.tree_strength=QDoubleSpinBox();self.tree_strength.setRange(0,100);self.tree_strength.setDecimals(0);self.tree_strength.setSuffix(' %');self.tree_strength.setValue(self.data.get('effects',{}).get('tree_strength',.22)*100);self.tree_strength.editingFinished.connect(self.tree_changed);form.addRow('Tree pattern',self.tree_strength)
        self.architecture=QDoubleSpinBox();self.architecture.setRange(0,100);self.architecture.setDecimals(0);self.architecture.setSuffix(' %');self.architecture.setValue(self.data.get('effects',{}).get('architecture_strength',.10)*100);self.architecture.editingFinished.connect(self.architecture_changed);form.addRow('Base illumination',self.architecture)
        help=QLabel('Drag a point or region. Moving a region moves its children too.\nArrows: 1 px · Shift: 10 px · Ctrl: ¼ px.\nWheel: zoom · middle button: pan.\n0: fit to view.\nDouble-click an edge to add a vertex.');help.setWordWrap(True);sl.addWidget(help);sl.addStretch();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(side);scroll.setMaximumWidth(365);scroll.setMinimumWidth(320);body.addWidget(scroll)
        self.editor=Editor(self);body.addWidget(self.editor);body.setStretchFactor(1,1)
        bottom=QHBoxLayout();outer.addLayout(bottom);self.mode_box=QComboBox()
        for label,value in MODES:self.mode_box.addItem(label,value)
        self.mode_box.currentIndexChanged.connect(self.change_mode);bottom.addWidget(self.mode_box)
        self.flash_check=QCheckBox('Bliksemflitsen');self.flash_check.setChecked(self.data.get('effects',{}).get('lightning_strength',.85)>0);self.flash_check.toggled.connect(self.set_flashes);bottom.addWidget(self.flash_check);self.photo_check=QCheckBox('Show reference on laptop');self.photo_check.toggled.connect(lambda _:self.editor.update());bottom.addWidget(self.photo_check)
        self.screens=QComboBox();self.screens.setToolTip('Choose the extended desktop display connected to the projector.')
        bottom.addWidget(self.screens,1);self.scan_screens();self.screens.activated.connect(self.projector_screen_selected)
        QApplication.instance().screenAdded.connect(self.scan_screens);QApplication.instance().screenRemoved.connect(self.scan_screens)
        for text,fn in [('Projector on',self.show_projector),('Projector black',self.blackout),('Save PNG',self.save_pattern)]:b=QPushButton(text);b.clicked.connect(fn);bottom.addWidget(b)
        row=QHBoxLayout();outer.addLayout(row);self.play_button=QPushButton('Play');self.play_button.clicked.connect(self.play);row.addWidget(self.play_button);self.seek=QSlider(Qt.Horizontal);self.seek.setRange(0,self.data['output']['fps']*120-1);self.seek.valueChanged.connect(self.seek_to);row.addWidget(self.seek,1);self.clock=QLabel('00:00 / 02:00');row.addWidget(self.clock)
        self.projector=Projector(self);self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.setTimerType(Qt.PreciseTimer);self.timer.start(16);self.play_origin=time.monotonic();self.flash_check.setEnabled(not self.data.get('locked'));self.global_button.setEnabled(not self.data.get('locked'));self.tree_strength.setEnabled(not self.data.get('locked'));self.read_reference();self.rebuild_list();self.refresh();self.statusBar().showMessage('Draft mapping. Align on site, then save the final mapping.');
        QShortcut(QKeySequence.Save,self,activated=self.save_map);QShortcut(QKeySequence.Undo,self,activated=lambda:self.undo());QShortcut(QKeySequence.Redo,self,activated=lambda:self.undo(True))
        self.setStyleSheet('QWidget{background:#171b22;color:#eeeeee;font-size:14px} QPushButton,QComboBox,QDoubleSpinBox{padding:7px;border:1px solid #444b58;border-radius:4px} QPushButton:hover{background:#343b45} QListWidget::item:selected{background:#67513d} QCheckBox{padding:6px} QLabel{padding:3px}')
    def note(self,s):self.statusBar().showMessage(s)
    def update_title(self):self.setWindowTitle('Nightfall — '+(str(self.filename.name) if self.filename else 'new mapping')+(' *' if self.dirty else ''))
    def current(self):return model.region(self.data,self.selected)
    def checkpoint(self):self.undo_stack.append(copy.deepcopy(self.data));self.undo_stack=self.undo_stack[-80:];self.redo_stack=[]
    def undo(self,redo=False):
        if self.data.get('locked'):return
        source,target=(self.redo_stack,self.undo_stack) if redo else (self.undo_stack,self.redo_stack)
        if not source:return
        target.append(copy.deepcopy(self.data));self.data=source.pop();self.dirty=True;self.editor.vertex=-1;self.read_reference();self.rebuild_list();self.refresh()
    def select(self,id):self.list.setCurrentRow(next(i for i,r in enumerate(model.editable_shapes(self.data)) if r['id']==id))
    def select_row(self,i):
        if i<0:return
        self.selected=model.editable_shapes(self.data)[i]['id'];self.editor.vertex=-1;self.sync_coordinates();self.enabled.blockSignals(True);self.enabled.setChecked(self.current().get('enabled',True));self.enabled.blockSignals(False);self.enabled.setEnabled(not self.data.get('locked') and self.current()['type'] not in ('window','exclusion'));self.note_label.setText('Glass mask: always active.' if self.current()['type']=='window' else self.current().get('note',''));self.refresh()
        self.paper.blockSignals(True);self.paper.setChecked(self.current().get('paper_screen',False));self.paper.blockSignals(False);self.paper.setVisible(self.current()['type']=='window');self.paper.setEnabled(not self.data.get('locked'))
        self.architecture.setEnabled(not self.data.get('locked'));self.architecture.setValue(self.data.get('effects',{}).get('architecture_strength',.10)*100);self.tree_strength.setValue(self.data.get('effects',{}).get('tree_strength',.22)*100)
        detail=self.current().get('note','')
        if self.current()['type']=='window':detail='A window can receive projection when backed by a reflective screen, paper or fabric. Otherwise glass and curtains remain separate. '+detail
        state={'photo-measured':'Measured from reference · verify on projector','needs-alignment':'Initial estimate · align on site','aligned':'Marked as aligned by you'}.get(self.current().get('alignment_status'),'Draft · alignment required')
        self.note_label.setText(state+'\n'+detail);self.aligned.setEnabled(not self.data.get('locked'));self.gain.setValue(self.current().get('gain',1)*100);self.gain.setEnabled(not self.data.get('locked') and self.current()['type']!='exclusion');self.frame_width.setValue(self.current().get('border_width',3));self.frame_width.setEnabled('border_width' in self.current() and not self.data.get('locked'))
    def rebuild_list(self):
        self.list.blockSignals(True);self.list.clear()
        for r in model.editable_shapes(self.data):
            prefix='  ↳ ' if r.get('parent') else ''
            marker=' ✓' if r.get('alignment_status')=='aligned' else (' ≈' if r.get('uncertain') else '')
            self.list.addItem(prefix+r['name']+marker)
        self.list.blockSignals(False);self.select(self.selected)
    def sync_coordinates(self):
        pts=[a['point'] for a in self.data['alignment']['anchors']] if self.mode=='alignment' else self.current()['projector_points']
        self.vertex_box.blockSignals(True);self.vertex_box.clear();self.vertex_box.addItem('Entire region',-1)
        for i in range(len(pts)):self.vertex_box.addItem(('Anchor ' if self.mode=='alignment' else 'Point ')+str(i+1),i)
        self.vertex_box.setCurrentIndex(self.editor.vertex+1);self.vertex_box.blockSignals(False)
        for spin in [self.x,self.y]:spin.setEnabled(self.editor.vertex>=0 and not self.data.get('locked'))
        origin=model.origin_point(self.data)
        offset=origin if origin and self.relative.isChecked() else [0,0]
        self.relative.setEnabled(origin is not None)
        self.origin_label.setText(('Origin: '+self.data['alignment']['origin'].get('name','window corner')+f'\nProjector pixel ({origin[0]:.2f}, {origin[1]:.2f})') if origin else 'Choose a window corner as the origin.')
        self.origin_button.setEnabled(self.mode!='alignment' and self.current()['type']=='window' and self.editor.vertex>=0 and not self.data.get('locked'))
        for axis,spin,maximum in [(0,self.x,model.WIDTH),(1,self.y,model.HEIGHT)]:
            spin.setRange(-offset[axis],maximum-offset[axis])
            if self.editor.vertex>=0:spin.setValue(pts[self.editor.vertex][axis]-offset[axis])
    def choose_vertex(self,i):self.editor.vertex=i-1;self.sync_coordinates();self.editor.update()
    def coordinates_changed(self):
        i=self.editor.vertex
        if i<0 or self.data.get('locked'):return
        offset=(model.origin_point(self.data) or [0,0]) if self.relative.isChecked() else [0,0]
        candidate=copy.deepcopy(self.data);point=[self.x.value()+offset[0],self.y.value()+offset[1]]
        if self.mode=='alignment':candidate['alignment']['anchors'][i]['point']=point
        else:edit_corner(candidate,self.selected,i,point)
        try:model.validate(candidate)
        except ValueError as e:self.note(str(e));self.sync_coordinates();return
        self.checkpoint();self.data=candidate;self.dirty=True;self.sync_coordinates();self.refresh()
    def set_origin(self):
        if self.data.get('locked') or self.current()['type']!='window' or self.editor.vertex<0 or self.mode=='alignment':return
        self.checkpoint();self.data.setdefault('alignment',{})['origin']={'region_id':self.selected,'vertex_index':self.editor.vertex,'name':self.current()['name']+f' · corner {self.editor.vertex+1}'};self.relative.setChecked(True);self.dirty=True;self.sync_coordinates();self.refresh()
    def mark_aligned(self):
        if self.data.get('locked'):return
        self.checkpoint();self.current()['alignment_status']='aligned';self.current()['uncertain']=False;self.dirty=True;self.rebuild_list();self.refresh()
    def gain_changed(self):
        if self.data.get('locked') or self.current()['type']=='exclusion':return
        self.checkpoint();self.current()['gain']=self.gain.value()/100;self.dirty=True;self.refresh()
    def frame_width_changed(self):
        if self.data.get('locked') or 'border_width' not in self.current():return
        self.checkpoint();self.current()['border_width']=self.frame_width.value();model.invalidate_alignment(self.data,{self.selected});self.dirty=True;self.refresh()
    def set_enabled(self,value):
        if self.data.get('locked') or self.current()['type'] in ('window','exclusion'):return
        self.checkpoint();self.current()['enabled']=value;self.dirty=True;self.refresh()
    def global_fit(self):
        if self.data.get('locked'):return
        values=[]
        pivot='the origin' if model.origin_point(self.data) else 'the image center'
        for label,value,minimum,maximum in [('Horizontal offset (pixels)',0,-model.WIDTH,model.WIDTH),('Vertical offset (pixels)',0,-model.HEIGHT,model.HEIGHT),('Scale around '+pivot,1,.1,4),('Rotate around '+pivot+' (degrees)',0,-180,180)]:
            v,ok=QInputDialog.getDouble(self,'Global alignment',label,value,minimum,maximum,2)
            if not ok:return
            values.append(v)
        try:new=model.transform_all(self.data,*values)
        except ValueError as e:QMessageBox.warning(self,'Transformation exceeds the canvas',str(e));return
        self.checkpoint();self.data=new;self.dirty=True;self.editor.vertex=-1;self.sync_coordinates();self.refresh();self.note('All regions and anchors updated. Check the individual contours.')
    def tree_changed(self):
        if self.data.get('locked'):return
        self.checkpoint();self.data.setdefault('effects',{})['tree_strength']=self.tree_strength.value()/100;self.dirty=True;self.refresh()
    def architecture_changed(self):
        if self.data.get('locked'):return
        self.checkpoint();self.data.setdefault('effects',{})['architecture_strength']=self.architecture.value()/100;self.dirty=True;self.refresh()
    def set_paper(self,value):
        if self.data.get('locked') or self.current()['type'] not in ('window','exclusion') or self.current()['id']=='attic':return
        self.checkpoint();self.current()['paper_screen']=value;self.dirty=True;self.refresh()
    def set_flashes(self,value):
        if self.data.get('locked'):return
        self.checkpoint();self.data.setdefault('effects',{})['lightning_strength']=.85 if value else 0;self.dirty=True;self.refresh()
    def set_locked(self,value):
        self.data['locked']=value;self.dirty=True;self.flash_check.setEnabled(not value);self.global_button.setEnabled(not value);self.tree_strength.setEnabled(not value);self.select_row(self.list.currentRow());self.note('Alignment locked. Use the reference pattern to restore the projector position.' if value else 'Alignment unlocked.');self.refresh()
    def change_mode(self,i):self.mode=self.mode_box.itemData(i);self.editor.vertex=-1;self.sync_coordinates();self.refresh()
    def refresh(self):
        self.frame=render(self.data,self.t,self.mode,self.selected);self.editor.update();self.projector.update();self.update_title();self.clock.setText(f'{int(self.t)//60:02d}:{int(self.t)%60:02d} / 02:00')
        if hasattr(self,'simple_status'):
            i=self.editor.vertex;name=self.current()['name']
            if i>=0:
                x,y=self.current()['projector_points'][i];name+=f' · corner {i+1} · {x:.2f}, {y:.2f} px'
            self.simple_status.setText(name)
    def scan_screens(self,*args):
        previous=self.screens.currentData();screens=QApplication.screens()
        for screen in screens:
            if screen not in getattr(self,'_observed_screens',[]):
                screen.geometryChanged.connect(self.scan_screens)
                screen.logicalDotsPerInchChanged.connect(self.scan_screens)
                screen.physicalDotsPerInchChanged.connect(self.scan_screens)
        self._observed_screens=screens
        self.screens.clear()
        for i,s in enumerate(screens):
            size=s.geometry().size();scale=s.devicePixelRatio()
            self.screens.addItem(f'{i+1}: {s.name()} · {round(size.width()*scale)}×{round(size.height()*scale)} · scale {scale:g}',s)
        external=[s for s in screens if s!=self.screen()]
        candidates=[s for s in external or screens if s.size().width()==model.WIDTH and s.size().height()==model.HEIGHT and s.devicePixelRatio()==1]
        preferred=previous if previous in screens else candidates[0] if len(candidates)==1 else external[0] if len(external)==1 else screens[0] if len(screens)==1 else None
        self.screens.setPlaceholderText('Choose the projector display')
        self.screens.setCurrentIndex(screens.index(preferred) if preferred is not None else -1)
        if hasattr(self,'projector'):self.projector.ensure_screen_geometry()
    def projector_screen_selected(self,*args):
        if self.projector.isVisible():
            screen=self.screens.currentData()
            if screen in QApplication.screens():
                self.projector.show_on(screen)
                if hasattr(self,'projector_button'):self.projector_button.setText('Projector on' if self.projector.blacked_out else 'Projector off')
    def show_projector(self):
        s=self.screens.currentData()
        if s not in QApplication.screens():
            self.scan_screens();self.note('Select the projector display from the display list first.');return
        self.projector.show_on(s)
        self.projector.blacked_out=False
        if hasattr(self,'projector_button'):self.projector_button.setText('Projector off')
        if s.size().width()!=model.WIDTH or s.size().height()!=model.HEIGHT or s.devicePixelRatio()!=1:self.note('Set the projector display to 800×1280 at 100% scaling. The image is currently scaled to fit.')
    def blackout(self):self.mode_box.setCurrentIndex(next(i for i,m in enumerate(MODES) if m[1]=='black'))
    def play(self):self.playing=not self.playing;self.play_origin=time.monotonic()-self.t;self.play_button.setText('Pause' if self.playing else 'Play')
    def tick(self):
        self.check_tour_time()
        if self.live_mode:
            self.video_frame=render(self.data,(time.monotonic()-self.live_play_origin)%120,self.live_mode);self.projector.update();self.editor.update();self.update_display_rate();return
        if self.video.active:self.update_display_rate();return
        if not self.playing or self.mode not in ('young','older'):return
        self.t=(time.monotonic()-self.play_origin)%120;self.seek.blockSignals(True);self.seek.setValue(int(self.t*self.data['output']['fps']));self.seek.blockSignals(False);self.refresh()
    def seek_to(self,v):self.t=v/self.data['output']['fps'];self.play_origin=time.monotonic()-self.t;self.refresh()
    def read_reference(self):
        settings=self.data.get('reference_photos',{}).get(self.data.get('editor_photo'),self.data)
        raw=settings.get('reference',{}).get('dataUrl','');self.reference=QImage()
        self.reference_transform=settings.get('reference_transform')
        self.reference_placement=settings.get('reference_placement',{})
        if raw.startswith('data:image/'):
            try:self.reference=QImage.fromData(base64.b64decode(raw.split(',',1)[1],validate=True))
            except (ValueError,IndexError):pass
        filename=settings.get('reference',{}).get('filename','')
        if self.reference.isNull() and filename:
            candidate=Path(filename)
            if not candidate.is_absolute():
                base=self.filename.parent if self.filename else model.ROOT/'examples'
                candidate=base/candidate
            self.reference=QImage(str(candidate))
        self.update_photo_button()
        self.sync_switch_time()
    def abandon_ok(self):
        if not self.dirty:return True
        return QMessageBox.question(self,'Unsaved changes','Discard unsaved changes?',QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes
    def open_map(self):
        filename,_=QFileDialog.getOpenFileName(self,'Open mapping','','Nightfall (*.json)')
        if not filename or not self.abandon_ok():return
        try:data=model.load(filename)
        except Exception as e:QMessageBox.warning(self,'Could not open mapping',str(e));return
        self.data=data;self.filename=Path(filename);self.dirty=False;self.undo_stack=[];self.redo_stack=[];self.lock.blockSignals(True);self.lock.setChecked(data.get('locked',False));self.lock.blockSignals(False);self.flash_check.blockSignals(True);self.flash_check.setChecked(data.get('effects',{}).get('lightning_strength',.85)>0);self.flash_check.blockSignals(False);self.flash_check.setEnabled(not data.get('locked'));self.global_button.setEnabled(not data.get('locked'));self.tree_strength.setEnabled(not data.get('locked'));self.tree_strength.setValue(data.get('effects',{}).get('tree_strength',.22)*100);self.read_reference();self.rebuild_list();self.refresh()
    def save_map(self):
        filename,_=QFileDialog.getSaveFileName(self,'Save final mapping',str(self.filename or 'mapping.json'),'Nightfall (*.json)')
        if not filename:return False
        if not filename.endswith('.json'):filename+='.json'
        try:
            calibration=self.data.setdefault('calibration',{});calibration.setdefault('method','manual-projector-pixels');calibration['edit_status']='locked' if self.data.get('locked') else 'editable';model.save(self.data,filename)
            png=Path(filename).with_suffix('.alignment.png')
            if not render(self.data,mode='alignment').save(str(png)):raise OSError('Could not save the alignment PNG.')
        except Exception as e:QMessageBox.warning(self,'Save failed',str(e));return False
        self.filename=Path(filename);self.dirty=False;self.update_title();self.note('Mapping and matching alignment pattern saved.');return True
    def save_pattern(self):
        filename,_=QFileDialog.getSaveFileName(self,'Save projector image',self.mode+'.png','PNG (*.png)')
        if filename and not self.frame.save(filename if filename.endswith('.png') else filename+'.png'):QMessageBox.warning(self,'Export failed','Could not save PNG.')
    def load_photo(self):
        if self.data.get('locked'):self.note('Unlock alignment before loading another reference.');return
        filename,_=QFileDialog.getOpenFileName(self,'Reference image','','Images (*.jpg *.jpeg *.png *.webp)')
        if not filename:return
        reader=QImageReader(filename);reader.setAutoTransform(True);im=reader.read()
        if im.isNull():QMessageBox.warning(self,'Reference','Could not read the reference image. Export RAW files to JPEG or PNG first.');return
        if Path(filename).stat().st_size>25000000:QMessageBox.warning(self,'Reference','Use a reference image smaller than 25 MB.');return
        from .calibration import image_reference
        self.checkpoint();self.data['reference']=image_reference(im,Path(filename).name)
        for key in ['reference_transform','photo_registration','reference_photos','editor_photo']:self.data.pop(key,None)
        k=min(model.WIDTH/im.width(),model.HEIGHT/im.height());self.data['reference_placement']={'x':(model.WIDTH-im.width()*k)/2,'y':(model.HEIGHT-im.height()*k)/2,'width':im.width()*k,'height':im.height()*k};self.read_reference();self.dirty=True;self.refresh();self.note('Reference loaded. Existing projector points stay fixed; align them again.')
    def import_calibration(self):
        if self.data.get('locked'):self.note('Unlock alignment first.');return
        filename,_=QFileDialog.getOpenFileName(self,'Load grid calibration — solution.json','','Grid calibration (*.json)')
        if not filename:return
        from .calibration import load_solution
        try:data=load_solution(self.data,filename)
        except (ValueError,OSError,KeyError,TypeError) as e:QMessageBox.warning(self,'Could not load calibration',str(e));return
        self.checkpoint();self.data=data;self.dirty=True;self.selected='right';self.editor.vertex=-1;self.relative.setChecked(True);self.read_reference();self.rebuild_list();self.photo_check.setChecked(True);self.mode_box.setCurrentIndex(2);self.refresh();self.note('Measured facade contours loaded. Other regions remain estimates; align them separately.')
    def setup_notes(self):
        if self.data.get('locked'):self.note('Unlock the mapping before editing setup notes.');return
        labels={'lens_position':'Projector lens: position and height','tripod':'Tripod and floor markings','zoom':'Zoom / setting','focus':'Focus / setting','keystone':'Keystone (exact setting)','lens_shift':'Lens shift','notes':'Other details (including projector roll)'}
        for key,label in labels.items():
            value,ok=QInputDialog.getText(self,'Record setup',label,text=self.data['setup'].get(key,''))
            if not ok:break
            self.data['setup'][key]=value;self.dirty=True
        self.update_title()
    def export(self):
        if self.process and self.process.state()!=QProcess.NotRunning:self.note('A render is already running.');return
        if not self.save_map():return
        folder=QFileDialog.getExistingDirectory(self,'Folder for the two new videos')
        if not folder:return
        self.process=QProcess(self);self.process.setProgram(sys.executable);self.process.setArguments(render_command(str(self.filename),'--out',folder,'--show','both'));self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(lambda:self.note(bytes(self.process.readAllStandardOutput()).decode(errors='replace').strip()[-300:]));self.process.finished.connect(lambda code,status:self.note('Both videos and the mapping snapshot are ready.' if code==0 else 'Render failed. Check the output folder and FFmpeg; existing videos are preserved.'));self.process.start();self.note('Rendering videos from the saved mapping…')
    def closeEvent(self,e):
        if self.process and self.process.state()!=QProcess.NotRunning:QMessageBox.information(self,'Render active','Wait for rendering to finish before closing the app.');e.ignore();return
        if not self.abandon_ok():e.ignore();return
        self.video.stop()
        self.projector.close();e.accept()

def main():
    import argparse
    parser=argparse.ArgumentParser(description='Desktop editor and alignment patterns for 800×1280 projection mapping.')
    parser.add_argument('mapping',nargs='?',help='Saved mapping.json or exported web project')
    parser.add_argument('--alignment',action='store_true',help='Start with the alignment pattern')
    parser.add_argument('--screen',type=int,default=None,help='Projector display index: 0 for the first display, 1 for the second')
    parser.add_argument('--projector',action='store_true',help='Open the separate projector output immediately')
    parser.add_argument('--locked',action='store_true',help='Start with alignment locked')
    parser.add_argument('--video',type=Path,help='Start playback of an existing video')
    parser.add_argument('--preview-only',action='store_true',help='Show playback and FPS on the main screen without fullscreen projector output')
    args=parser.parse_args()
    if not args.mapping:args.mapping=str(model.ROOT/'examples/house.json')
    app=QApplication(sys.argv);data=model.load(args.mapping) if args.mapping else None;w=MainWindow(data)
    w.filename=Path(args.mapping)
    w.read_reference()
    w.preview_only=args.preview_only
    w.simplify()
    if data and data.get('calibration',{}).get('solution'):w.photo_check.setChecked(True)
    if args.mapping:w.filename=Path(args.mapping)
    if args.locked:
        w.lock.blockSignals(True);w.lock.setChecked(True);w.lock.blockSignals(False);w.data['locked']=True;w.flash_check.setEnabled(False);w.global_button.setEnabled(False);w.tree_strength.setEnabled(False);w.select_row(w.list.currentRow())
    if args.alignment:w.mode_box.setCurrentIndex(3)
    if args.screen is not None:
        if not 0<=args.screen<w.screens.count():parser.error('Display index does not exist. Start without --screen to see available displays.')
        w.screens.setCurrentIndex(args.screen)
    w.dirty=False;w.update_title();w.show()
    if args.projector:QTimer.singleShot(0,w.show_projector)
    if args.video:QTimer.singleShot(0,lambda:w.play_animation(str(args.video)))
    sys.exit(app.exec())

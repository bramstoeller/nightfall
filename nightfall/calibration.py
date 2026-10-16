"""Load a measured facade solution into the existing polygon editor.

Only the measured contours are replaced. Other shapes remain visibly marked
as drafts; a facade homography must not silently calibrate different depths.
The photograph is rectified once, so the editor's rectangular photo background
remains valid. The original observations and transform remain in the map.
"""
import base64
import copy
import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, Qt
from PySide6.QtGui import QImage, QImageReader, QPainter, QPolygonF, QTransform

from . import model


def image_reference(image, filename):
    encoded=QByteArray();buffer=QBuffer(encoded);buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer,'PNG'):raise ValueError('Could not save the reference image.')
    return {'width':image.width(),'height':image.height(),'filename':filename,
            'dataUrl':'data:image/png;base64,'+base64.b64encode(bytes(encoded)).decode()}


def load_solution(data, filename):
    filename=Path(filename)
    solution=json.loads(filename.read_text(encoding='utf8'))
    observation_path=filename.with_name('observations.json')
    observations=json.loads(observation_path.read_text(encoding='utf8'))
    photo_path=observation_path.parent/observations['photo']
    if observations.get('projector_size')!=[model.WIDTH,model.HEIGHT]:
        raise ValueError('Grid calibration must be 800 × 1280.')
    for path,key in [(photo_path,'photo_sha256'),(observation_path,'observations_sha256')]:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=solution.get(key):
            raise ValueError(f'{path.name} does not match the saved calibration. Recalculate the calibration.')
    h=solution['photo_to_projector']
    if len(h)!=3 or any(len(row)!=3 or not all(model.finite(x) for x in row) for row in h):
        raise ValueError('Invalid reference transformation.')
    tr=QTransform(h[0][0],h[1][0],h[2][0],h[0][1],h[1][1],h[2][1],h[0][2],h[1][2],h[2][2])
    if not tr.isInvertible():raise ValueError('Reference transformation is not invertible.')
    reader=QImageReader(str(photo_path));reader.setAutoTransform(True);photo=reader.read()
    if photo.isNull() or [photo.width(),photo.height()]!=observations['photo_size_after_exif']:
        raise ValueError('Could not read the grid reference in the expected orientation.')
    rectified=QImage(model.WIDTH,model.HEIGHT,QImage.Format_RGB32);rectified.fill(Qt.black)
    painter=QPainter(rectified);painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setTransform(tr);painter.drawImage(0,0,photo);painter.end()
    result=copy.deepcopy(data)
    measured=solution['contours_projector']
    if not measured or set(measured)-{'facade','roof','attic','right','left'}:
        raise ValueError('Facade calibration contains unknown contours or surfaces at other depths.')
    # Preserve the curtains' position within a newly measured window as a draft.
    # The curtains themselves have not been measured or physically verified.
    for rid,points in measured.items():
        current=model.region(result,rid)
        if current['type']=='window':
            old=QPolygonF([QPointF(*p) for p in current['projector_points']])
            new=QPolygonF([QPointF(*p) for p in points]);window_tr=QTransform()
            if len(points)!=4 or not QTransform.quadToQuad(old,new,window_tr):
                raise ValueError('Invalid measured window contour.')
            for child in result['regions']:
                if child.get('parent')==rid:
                    mapped=[window_tr.map(QPointF(*p)) for p in child['projector_points']]
                    child['projector_points']=[[p.x(),p.y()] for p in mapped]
        current['projector_points']=copy.deepcopy(points)
        current.pop('source_points',None)
    for shape in model.editable_shapes(result):
        shape['uncertain']=True
        shape['alignment_status']='photo-measured' if shape['id'] in measured else 'needs-alignment'
    result['reference']=image_reference(rectified,photo_path.stem+'-facade-warp.png')
    result['reference']['note']='Facade perspective correction; align tree, lamp and bay separately.'
    result['reference_placement']={'x':0,'y':0,'width':model.WIDTH,'height':model.HEIGHT}
    result['calibration']={**result.get('calibration',{}),'method':'raster-photo-facade',
                           'status':'provisional','physical_alignment_verified':False,
                           'solution':solution,'observations':observations}
    result['locked']=False
    result['alignment']['anchors']=[]
    if 'right' in measured:
        result['alignment']['origin']={'region_id':'right','vertex_index':0,
                                      'name':'Upper-left corner of right upper window'}
        result['alignment']['anchors'].append({'name':'Window corner','point':list(measured['right'][0]),'color':'#00ffff'})
    if 'roof' in measured:
        for name,index,color in [('Roof apex',1,'#ff8070'),('Right roof edge',2,'#7fffa8')]:
            result['alignment']['anchors'].append({'name':name,'point':list(measured['roof'][index]),'color':color})
    result['title']='Grid calibration — refine polygon alignment'
    return model.validate(result)

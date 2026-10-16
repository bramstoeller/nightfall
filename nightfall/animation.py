"""A small articulated puppet for this house's bay stage.

The existing ivory-bone texture is drawn as separate head, torso and jointed
limbs. Time selects an exact pose, shared by live playback, GIF and MP4 export.
"""
import math
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath
from .model import ROOT

FPS = 60
PERIOD = 2
_frames = {}
_source = None
_pieces = {}

# Masks follow the photographed puppet's joints in its 1024 × 1536 texture.
PIECES = {
    'head': [(351,83),(619,83),(621,338),(530,374),(388,352)],
    'body': [(348,370),(545,337),(586,376),(608,439),(632,663),
             (657,737),(657,818),(580,880),(431,858),(397,759),
             (378,695),(304,652),(314,548),(339,436)],
    'arm-l': [(279,380),(357,397),(225,589),(181,615),(144,574),(160,529)],
    'forearm-l': [(112,331),(176,322),(193,558),(154,581),(125,527)],
    'hand-l': [(14,146),(243,146),(245,311),(174,385),(105,387)],
    'arm-r': [(539,349),(620,361),(737,536),(714,579),(650,550),(557,433)],
    'forearm-r': [(695,502),(881,540),(880,613),(713,584)],
    'hand-r': [(824,478),(1022,474),(1022,690),(901,681),(826,617)],
    'thigh-l': [(405,750),(491,807),(363,1092),(311,1105),(269,1066),(306,1006)],
    'shin-l': [(291,1033),(368,1061),(264,1304),(214,1324),(195,1284)],
    'foot-l': [(205,1280),(271,1301),(284,1407),(237,1450),(125,1430),(145,1365)],
    'thigh-r': [(605,756),(670,768),(837,994),(821,1055),(765,1065),(719,975)],
    'shin-r': [(765,984),(836,1005),(765,1255),(732,1316),(651,1317),(667,1264)],
    'foot-r': [(668,1277),(748,1283),(794,1328),(889,1360),(876,1421),(759,1423),(637,1361)],
}

def piece(name):
    global _source
    if name not in _pieces:
        if _source is None:
            _source = QImage(str(ROOT / 'assets/young-skeleton.png'))
            if _source.isNull():
                raise RuntimeError('assets/young-skeleton.png is missing.')
        im = QImage(1024,1536,QImage.Format_ARGB32_Premultiplied)
        im.fill(Qt.transparent)
        p = QPainter(im)
        clip = QPainterPath()
        clip.moveTo(QPointF(*PIECES[name][0]))
        for xy in PIECES[name][1:]: clip.lineTo(QPointF(*xy))
        clip.closeSubpath()
        p.setClipPath(clip)
        p.drawImage(0,0,_source)
        p.end()
        _pieces[name] = im
    return _pieces[name]

def turn(p, joint, degrees):
    p.translate(*joint)
    p.rotate(degrees)
    p.translate(-joint[0],-joint[1])

def limb(p, names, joints, angles):
    p.save()
    for name,joint,angle in zip(names,joints,angles):
        turn(p,joint,angle)
        p.drawImage(0,0,piece(name))
    p.restore()

def skeleton_frame(t):
    index = round((t % PERIOD)*FPS) % (PERIOD*FPS)
    if index in _frames: return _frames[index]
    a = 2*math.pi*index/(PERIOD*FPS)
    im = QImage(480,720,QImage.Format_ARGB32_Premultiplied)
    im.fill(Qt.transparent)
    p = QPainter(im)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    # Side steps, a knee bend, opposite arm swings, head nod and a heel kick.
    p.translate(240+13*math.sin(a),388-12*(1-math.cos(2*a)))
    p.scale(.36,.36)
    p.rotate(5*math.sin(a))
    p.translate(-520,-785)
    limb(p,['thigh-l','shin-l','foot-l'],[(438,799),(331,1063),(228,1301)],
         [14*math.sin(a),-24*max(0,math.sin(a)),10*math.sin(a)])
    limb(p,['thigh-r','shin-r','foot-r'],[(643,802),(799,1018),(704,1296)],
         [-14*math.sin(a),24*max(0,-math.sin(a)),-10*math.sin(a)])
    limb(p,['arm-l','forearm-l','hand-l'],[(321,411),(178,563),(148,354)],
         [22*math.sin(a),-27*math.sin(a+.6),12*math.sin(2*a)])
    limb(p,['arm-r','forearm-r','hand-r'],[(585,397),(710,544),(851,584)],
         [-28*math.sin(a),25*math.sin(a+.6),-15*math.sin(2*a)])
    p.drawImage(0,0,piece('body'))
    p.save()
    turn(p,(446,357),9*math.sin(a+.4))
    p.drawImage(0,0,piece('head'))
    p.restore()
    p.end()
    _frames[index] = im
    return im

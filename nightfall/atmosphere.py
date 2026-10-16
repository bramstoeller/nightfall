"""Coloured, billowing smoke and curtain fire; cached Qt textures only."""
import math
import numpy as np
from PySide6.QtCore import QRectF,QPointF,Qt
from PySide6.QtGui import QPixmap,QImage,QPainter,QPainterPathStroker,QColor,QPen
from .model import ROOT

TAU=math.pi*2
_textures={};_masks={};_insets={};_colours={};_smoke_pixels={};_smoke_grids={}

def shape_key(shape):
    return tuple((round(e.x,4),round(e.y,4),e.type.value) for e in (shape.elementAt(i) for i in range(shape.elementCount())))

def texture(name):
    if name not in _textures:
        pix=QPixmap(str(ROOT/'assets/atmosphere'/(name+'.png')))
        if pix.isNull():raise RuntimeError('Smoke textures are missing. Reinstall the complete application.')
        _textures[name]=pix
    return _textures[name]

def inset(shape,pixels):
    if pixels<=0:return shape
    key=(shape_key(shape),pixels)
    if key in _insets:return _insets[key]
    stroke=QPainterPathStroker();stroke.setWidth(pixels*2)
    result=shape.subtracted(stroke.createStroke(shape))
    if len(_insets)>200:_insets.clear()
    _insets[key]=result;return result

def outset(shape,pixels):
    """A small paint margin; forbidden surfaces are masked separately."""
    key=(shape_key(shape),-pixels)
    if key not in _insets:
        stroke=QPainterPathStroker();stroke.setWidth(pixels*2)
        if len(_insets)>200:_insets.clear()
        _insets[key]=shape.united(stroke.createStroke(shape))
    return _insets[key]

def feather_mask(shape,softness=6,opaque_interior=False):
    poly=shape.toFillPolygon();key=(tuple((round(q.x(),2),round(q.y(),2)) for q in poly),softness,opaque_interior)
    if key not in _masks:
        b=shape.boundingRect().adjusted(-2,-2,2,2).toAlignedRect()
        im=QImage(b.size(),QImage.Format_ARGB32_Premultiplied);im.fill(Qt.transparent)
        p=QPainter(im);p.translate(-b.left(),-b.top());p.setPen(Qt.NoPen)
        if opaque_interior:
            p.setRenderHint(QPainter.Antialiasing)
            p.setCompositionMode(QPainter.CompositionMode_Source)
        for k in range(softness+1):
            u=k/max(1,softness)
            alpha=round(255*u*u*(3-2*u)) if opaque_interior and softness else 255 if opaque_interior else int(255/(softness+1))
            p.setBrush(QColor(255,255,255,alpha));p.drawPath(inset(shape,k))
        p.end();im=im.scaled(max(1,b.width()//2),max(1,b.height()//2),Qt.IgnoreAspectRatio,Qt.SmoothTransformation).scaled(b.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        if len(_masks)>24:_masks.clear()
        _masks[key]=(im,b)
    return _masks[key]

def flowing_smoke(name,rect,t):
    """Continuous two-dimensional flow, sampled smoothly instead of in strips.

    Work at half resolution and interpolate for soft volumetric detail.
    Independent rising fields curl in both directions, repeating at 120 s.
    """
    if name not in _smoke_pixels:
        source=texture(name).toImage().convertToFormat(QImage.Format_RGBA8888_Premultiplied)
        _smoke_pixels[name]=np.frombuffer(source.constBits(),np.uint8).reshape(source.height(),source.width(),4).copy()
    width=max(1,math.ceil(rect.width()/2));height=max(1,math.ceil(rect.height()/2))
    key=(rect.x(),rect.y(),rect.width(),rect.height())
    if key not in _smoke_grids:
        x=np.linspace(rect.left(),rect.right(),width,dtype=np.float32)[None,:]
        y=np.linspace(rect.top(),rect.bottom(),height,dtype=np.float32)[:,None]
        if len(_smoke_grids)>24:_smoke_grids.clear()
        _smoke_grids[key]=(x,y)
    x,y=_smoke_grids[key];t=t%120;source=_smoke_pixels[name]
    sh,sw=source.shape[:2]
    result=QImage(width,height,QImage.Format_RGBA8888_Premultiplied);result.fill(Qt.transparent)
    q=QPainter(result)
    for layer in range(2):
        scale=.78 if layer==0 else .52
        u=x*scale+48*np.sin(y*.017-TAU*t/30+layer*2.1)+24*np.sin(x*.012+TAU*t/40)+sw*t/120+layer*151
        v=y*scale+38*np.cos(x*.015+TAU*t/20+layer)+19*np.sin(y*.013-TAU*t/60)+sh*t/(60 if layer==0 else 40)+layer*97
        u=u%sw;v=v%sh;ix=np.minimum(u.astype(np.int32),sw-1);iy=np.minimum(v.astype(np.int32),sh-1)
        fx=(u-ix.astype(np.float32))[...,None];fy=(v-iy.astype(np.float32))[...,None]
        ix1=(ix+1)%sw;iy1=(iy+1)%sh
        top=source[iy,ix]*(1-fx)+source[iy,ix1]*fx
        bottom=source[iy1,ix]*(1-fx)+source[iy1,ix1]*fx
        rgba=np.rint(top*(1-fy)+bottom*fy).astype(np.uint8)
        image=QImage(rgba.data,width,height,width*4,QImage.Format_RGBA8888_Premultiplied)
        q.setOpacity(.78 if layer==0 else .53);q.drawImage(0,0,image)
    q.end();return result

def clouds(p,shape,b,t,name,strength=.8):
    mask,rect=feather_mask(shape)
    im=QImage(rect.size(),QImage.Format_ARGB32_Premultiplied);im.fill(Qt.transparent);q=QPainter(im)
    q.setRenderHint(QPainter.SmoothPixmapTransform)
    q.drawImage(QRectF(im.rect()),flowing_smoke(name,rect,t))
    q.setCompositionMode(QPainter.CompositionMode_DestinationIn);q.setOpacity(1);q.drawImage(0,0,mask);q.end()
    p.save();p.setOpacity(p.opacity()*strength);p.drawImage(rect.topLeft(),im);p.restore()

def curtain_fire(p,r,t):
    from .renderer import uv_transform,path
    shape=path(r['projector_points']);mask,rect=feather_mask(shape,3)
    im=QImage(rect.size(),QImage.Format_ARGB32_Premultiplied);im.fill(Qt.transparent)
    q=QPainter(im);q.setRenderHint(QPainter.SmoothPixmapTransform)
    q.translate(-rect.x(),-rect.y());q.save();q.setTransform(uv_transform(r['projector_points']),True);tex=texture('fire')
    for layer in range(2):
        stretch=1.35+.18*math.sin(TAU*t/2+layer*1.9)+.10*math.sin(TAU*t/3-layer)
        dx=.07*math.sin(TAU*t/3+layer*2)
        q.setOpacity(1 if layer==0 else .55)
        q.drawPixmap(QRectF(-.1+dx,1-stretch,1.2,stretch),tex,QRectF(tex.rect()))
    q.restore();q.resetTransform();q.setCompositionMode(QPainter.CompositionMode_DestinationIn);q.drawImage(0,0,mask);q.end()
    p.save();p.setOpacity(p.opacity()*.95);p.drawImage(rect.topLeft(),im)
    p.restore()

def soft_colour(p,shape,c,amount=1):
    key=(shape_key(shape),c)
    if key not in _colours:
        b=shape.boundingRect().adjusted(-1,-1,1,1).toAlignedRect()
        im=QImage(b.size(),QImage.Format_ARGB32_Premultiplied);im.fill(Qt.transparent)
        q=QPainter(im);q.translate(-b.x(),-b.y())
        for k,alpha in [(0,.07),(1,.12),(2,.22),(3,.32)]:
            q.setOpacity(alpha);q.fillPath(inset(shape,k),QColor(c))
        q.end()
        if len(_colours)>100:_colours.clear()
        _colours[key]=(im,b)
    im,b=_colours[key]
    p.save();p.setOpacity(p.opacity()*amount);p.drawImage(b.topLeft(),im)
    p.restore()

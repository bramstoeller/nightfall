"""Continuous five-second character rigs and light confined to real surfaces."""
import math
from functools import lru_cache
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QImage, QPainter, QPainterPath, QPen, QRadialGradient,
                          QPolygonF, QTransform)
from .model import ROOT
from .atmosphere import soft_colour
from .routes import performance_slots, performer_pose

TAU=2*math.pi
ACTOR_FPS=60
ACTOR_SECONDS=5
ACTOR_FRAMES=ACTOR_FPS*ACTOR_SECONDS
STYLES={
    'young-skeletons':('Friendly skeleton dance · 4–8','#ffe6a6','#8af8e7','The original smiling skeleton waves, nods and steps through a five-second dance.'),
    'young-ghosts':('Friendly ghost greeting · 4–8','#fff5d8','#98eaff','The original cloth ghost floats, waves its sleeves, ripples and winks.'),
    'bones':('Skeleton dance','#ffdf99','#84ffe8','A large friendly skeleton waves, heel-kicks and dances in five-second phrases.'),
    'bats':('Vampire bat ballet','#885cff','#ef6cde','Articulated wings carry glowing bats around the real windows.'),
    'pumpkins':('Pumpkin parade','#ff8b22','#b3ed52','Floating jack-o-lanterns wink, bob and squash to the beat.'),
    'spiders':('Moon spiders','#b350ff','#ffac4b','Eight jointed legs, hanging threads and spiders exploring the brickwork.'),
    'wisps':('Dancing will-o-the-wisps','#56f7da','#80caff','Ribbon-tailed spirits weave between the windows.'),
    'owls':('Enchanted owl flight','#63cfff','#ffd579','Barn owls flap, glide and bank through the gable.'),
    'haunted':('The breathing house','#a268ff','#59f3ce','Window frames and roof outlines breathe inside their fixed masks.'),
    'waves':('Architectural light waves','#27d9ff','#fa62bf','Traveling sine waves follow every turn of the roof and frames.'),
    'clockwork':('Clockwork windows','#ffb85a','#80dfff','Rotating diamonds, spirals and shutters stay inside each surface.'),
    'electric':('Haunted electric frames','#ad83ff','#59e8ff','Local flicker, chasing sparks and alternating illuminated edges.'),
}
ATLAS_NAMES={name:f'{name}-atlas-v1' for name in ['bat','pumpkin','spider','wisp','owl']}
# Union of every pose and all three variants, with a transparent safety border.
# These fixed source viewports preserve each character's original proportions.
ACTOR_BOUNDS={'skeleton':(60,6,136,212),'bat':(10,39,237,200),
              'owl':(18,58,216,173),'pumpkin':(22,16,196,208),
              'spider':(24,32,209,180),'wisp':(11,27,224,205),
              'young-skeleton':(32,14,192,228),'young-ghost':(32,14,192,228)}


def colour(value,alpha=255):
    result=QColor(value);result.setAlpha(max(0,min(255,round(alpha))));return result


@lru_cache(maxsize=24)
def atlas_cell(name,index):
    source=QImage(str(ROOT/'assets'/(ATLAS_NAMES[name]+'.png')))
    if source.isNull():raise RuntimeError(f'Missing {name} animation atlas. Install the complete app.')
    w,h=source.width()//2,source.height()//2
    return source.copy((index%2)*w,(index//2)*h,w,h).scaled(256,256,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)


def polygon(points):
    result=QPainterPath();result.addPolygon(QPolygonF([QPointF(*p) for p in points]));result.closeSubpath();return result


def masked(source,shape):
    result=QImage(256,256,QImage.Format_ARGB32_Premultiplied);result.fill(Qt.transparent)
    p=QPainter(result);p.setRenderHint(QPainter.Antialiasing);p.scale(256,256)
    p.setClipPath(shape);p.drawImage(QRectF(0,0,1,1),source);p.end();return result


@lru_cache(maxsize=2)
def flying_parts(kind):
    source=atlas_cell(kind,1)
    # The generated spread-wing pose supplies the texture. Each wing rotates
    # about its shoulder on every frame; there is no four-frame flipbook.
    left=polygon([(0,0),(.30,0),(.34,.40),(.40,.54),(.36,.72),(.24,1),(0,1)]) if kind=='bat' else polygon([(0,0),(.34,0),(.44,.43),(.53,.54),(.43,.76),(.30,1),(0,1)])
    right=QTransform(-1,0,0,1,1,0).map(left)
    body=QPainterPath();body.addEllipse(QRectF(.31,.22 if kind=='bat' else .34,.38,.76 if kind=='bat' else .64))
    left_image=masked(source,left)
    right_image=left_image.flipped(Qt.Horizontal) if kind=='bat' else masked(source,right)
    return left_image,right_image,masked(source,body)


@lru_cache(maxsize=9)
def bone_piece(index):
    source=QImage(str(ROOT/'assets/skeleton-rig-v1.png'))
    if source.isNull():raise RuntimeError('Missing skeleton puppet parts. Install the complete app.')
    w,h=source.width()//3,source.height()//3
    part=source.copy((index%3)*w,(index//3)*h,w,h).convertToFormat(QImage.Format_RGBA8888)
    pixels=np.frombuffer(part.constBits(),np.uint8).reshape(part.height(),part.width(),4)
    yy,xx=np.nonzero(pixels[:,:,3]>24)
    if len(xx)==0:raise RuntimeError('An empty skeleton puppet part was found.')
    return part.copy(int(xx.min()),int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1))


def draw_bone(p,index,a,b,width):
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
    p.save();p.translate(*a);p.rotate(math.degrees(math.atan2(dy,dx))-90)
    p.drawImage(QRectF(-width/2,-width*.12,width,length+width*.24),bone_piece(index));p.restore()


def skeleton(p,t,variant):
    phase=TAU*t/5;step=phase*5+variant*.65
    bob=3*(1-math.cos(step*2));sway=5*math.sin(step)
    p.save();p.translate(128+sway,124-bob);p.rotate(4*math.sin(step+variant))
    # Joint positions describe a five-second dance phrase with changing arm
    # gestures, alternating high knees, heel kicks and a final overhead wave.
    gesture=.5-.5*math.cos(phase)
    shoulders=[(-22,-28),(22,-28)];hips=[(-13,27),(13,27)]
    for side in (-1,1):
        i=(side+1)//2;s=shoulders[i];hip=hips[i]
        beat=step+(math.pi if side<0 else 0)
        knee=(hip[0]+side*(9+9*math.sin(beat)),61-19*max(0,math.sin(beat)))
        ankle=(knee[0]+side*13*math.cos(beat),99-25*max(0,math.sin(beat)))
        draw_bone(p,6,hip,knee,17);draw_bone(p,7,knee,ankle,13)
        p.save();p.translate(*ankle);p.scale(side,1);p.rotate(12*math.sin(beat))
        p.drawImage(QRectF(-8,-4,31,15),bone_piece(8));p.restore()
        elbow=(s[0]+side*(22+8*math.cos(beat)),s[1]+12-37*gesture+12*math.sin(beat))
        hand=(elbow[0]+side*15*math.cos(phase),elbow[1]-25-18*gesture+12*math.sin(beat+.8))
        draw_bone(p,3,s,elbow,12);draw_bone(p,4,elbow,hand,11)
        p.save();p.translate(*hand);p.rotate(side*18+15*math.sin(step*2))
        p.drawImage(QRectF(-10,-20,20,26),bone_piece(5));p.restore()
    p.drawImage(QRectF(-24,-40,48,63),bone_piece(1))
    p.drawImage(QRectF(-23,14,46,32),bone_piece(2))
    p.save();p.translate(0,-46);p.rotate(8*math.sin(phase*2+variant))
    p.drawImage(QRectF(-30,-47,60,58),bone_piece(0));p.restore();p.restore()


def flyer(p,kind,t,variant):
    a=TAU*t/5;beat=(5 if kind=='bat' else 3)*a+variant*.7
    left,right,body=flying_parts(kind)
    p.save();p.translate(128,128+3*math.sin(beat));p.rotate(5*math.sin(a+variant));p.translate(-128,-128)
    for sign,image in [(-1,left),(1,right)]:
        shoulder=QPointF(128+sign*18,145 if kind=='owl' else 139)
        p.save();p.translate(shoulder);p.rotate(sign*24*math.sin(beat))
        p.scale(.88+.10*math.cos(beat),.70+.30*math.cos(beat))
        p.translate(-shoulder);p.drawImage(0,0,image);p.restore()
    p.drawImage(0,0,body);p.restore()


def walking_spider(p,t,variant):
    a=TAU*t/5;beat=a*5+variant
    p.save();p.translate(128,134+2*math.sin(beat*2))
    # Eight independently articulated legs; textured body comes from imagegen.
    for sign in (-1,1):
        for leg in range(4):
            phase=beat+leg*math.pi/2+(math.pi if sign<0 else 0)
            root=(sign*25,-23+leg*19)
            knee=(sign*(67+10*math.cos(phase)),-64+leg*38+12*math.sin(phase))
            foot=(sign*(100+8*math.cos(phase)),-83+leg*47+18*math.sin(phase))
            path=QPainterPath(QPointF(*root))
            path.quadTo((root[0]+knee[0])*.5,root[1]-12,*knee)
            path.quadTo(knee[0]+sign*12,(knee[1]+foot[1])*.5,*foot)
            for width,c in [(19,'#542070'),(12,'#bd7df1'),(4,'#ffe0ff')]:
                p.setPen(QPen(QColor(c),width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.drawPath(path)
            p.setPen(Qt.NoPen);p.setBrush(QColor('#d4a2ff'))
            p.drawEllipse(QPointF(*knee),5,5)
    p.restore()
    p.drawImage(QRectF(9,8,238,238),masked_spider_body())


@lru_cache(maxsize=1)
def masked_spider_body():
    body=QPainterPath();body.addEllipse(QRectF(.28,.19,.44,.74))
    return masked(atlas_cell('spider',0),body)


@lru_cache(maxsize=96)
def actor_frame(kind,index,variant=0):
    """300 individually evaluated frames, wrapping exactly at five seconds."""
    t=(index%ACTOR_FRAMES)/ACTOR_FPS;a=TAU*t/5
    result=QImage(256,256,QImage.Format_ARGB32_Premultiplied);result.fill(Qt.transparent)
    p=QPainter(result);p.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
    if kind in {'young-ghost','young-skeleton'}:
        from .animation import skeleton_frame,young_ghost_frame
        source=(young_ghost_frame if kind=='young-ghost' else skeleton_frame)(t)
        bounds=QRectF(47,70,305,365) if kind=='young-ghost' else QRectF(24,102,435,529)
        scale=220/bounds.height();w,h=bounds.width()*scale,bounds.height()*scale
        p.drawImage(QRectF(128-w/2,128-h/2,w,h),source,bounds);p.end();return result
    # Room for the most extended pose in every variant, including raised hands
    # and wing tips. The stage drawing trims only the common transparent border.
    p.translate(128,128);p.scale(.8,.8);p.translate(-128,-128)
    if kind=='skeleton':skeleton(p,t,variant)
    elif kind in {'bat','owl'}:flyer(p,kind,t,variant)
    elif kind=='spider':
        p.translate(128,128);p.rotate(6*math.sin(a+.4));p.scale(1+.025*math.cos(a),1)
        p.translate(-128,-128);walking_spider(p,t,variant)
    elif kind=='pumpkin':
        p.translate(128,128+9*math.sin(a));p.rotate(7*math.sin(a+.4+variant))
        p.scale(.87+.055*math.cos(2*a),.87-.055*math.cos(2*a))
        # A short blink blends facial poses; body motion is continuous.
        blink=math.exp(-((t-3.2)/.14)**2)
        p.setOpacity(1-blink);p.drawImage(QRectF(-128,-128,256,256),atlas_cell(kind,0))
        if blink>.001:p.setOpacity(blink);p.drawImage(QRectF(-128,-128,256,256),atlas_cell(kind,1))
    elif kind=='wisp':
        source=atlas_cell(kind,0)
        p.translate(128,128);p.rotate(3*math.sin(a+.7));p.translate(-128,-128)
        for row in range(32):
            y=row*8;offset=11*math.sin(a*2-row*.17)*(row/32)**1.5
            p.drawImage(QRectF(offset,6*math.sin(a)+y,256,8.4),source,QRectF(0,y,256,8.4))
    else:raise ValueError(f'Unknown character: {kind}')
    p.end();return result


def draw_actor(p,kind,t,rect,variant=0,rotation=0):
    image=actor_frame(kind,round(t*ACTOR_FPS)%ACTOR_FRAMES,variant)
    source=QRectF(*ACTOR_BOUNDS[kind])
    scale=min(rect.width()/source.width(),rect.height()/source.height())
    w,h=source.width()*scale,source.height()*scale
    p.save();p.translate(rect.center());p.rotate(rotation)
    # One constant viewport per whole animation keeps proportions and the
    # position stable as wings close or limbs move; no per-frame auto-cropping.
    p.drawImage(QRectF(-w/2,-h/2,w,h),image,source);p.restore()


def dance_stages(shape,b):
    return [performer_pose(slot,0)[0] for slot in character_slots(shape,b,'skeleton',3) if slot is not None]


def character_slots(shape,b,kind,count):
    width,height=(110,158) if kind in {'skeleton','young-skeleton','young-ghost'} else (150,130) if kind in {'bat','owl'} else (144,144)
    # Large readable silhouettes suit distant brickwork. A cramped patch omits
    # another performer instead of turning it into a tiny floating copy.
    if kind=='spider':spec=(116,105,0,24,0)
    elif kind=='bat':spec=(144,104,10,10,0)
    else:spec=(width,height,3,4,0 if kind=='skeleton' else 3)
    return performance_slots(shape,b,[spec]*count)


def character_swarm(p,shape,b,t,kind,count,data=None):
    p.save();p.setClipPath(shape,Qt.IntersectClip)
    for i,slot in enumerate(character_slots(shape,b,kind,count)):
        if slot is None:continue
        rect,turn=performer_pose(slot,t)
        if kind=='spider':
            p.setPen(QPen(colour('#dfbcff',180),2))
            top=slot.envelope[1]
            if data is not None:
                facade=next(r for r in data['regions'] if r['id']=='facade')
                pts=facade['projector_points'];x=rect.center().x()
                hits=[a[1]+(c[1]-a[1])*(x-a[0])/(c[0]-a[0]) for a,c in zip(pts,pts[1:]+pts[:1])
                      if abs(c[0]-a[0])>.001 and min(a[0],c[0])<=x<=max(a[0],c[0])]
                if hits:top=min(hits)+4
            p.drawLine(QPointF(rect.center().x(),top),rect.center())
        draw_actor(p,kind,t+i*.4,rect,i%3,turn)
    p.restore()


_guides={}


def guide(r):
    pts=r['projector_points'];key=tuple(tuple(p) for p in pts)
    if key not in _guides:
        if r['id']=='roof' and len(pts)==6:
            points=[[(pts[i][0]+pts[5-i][0])/2,(pts[i][1]+pts[5-i][1])/2] for i in range(3)]
            closed=False
        else:
            cx=sum(x for x,y in pts)/len(pts);cy=sum(y for x,y in pts)/len(pts)
            points=[[cx+(x-cx)*.97,cy+(y-cy)*.97] for x,y in pts];closed=True
        route=QPainterPath(QPointF(*points[0]))
        for point in points[1:]:route.lineTo(*point)
        if closed:route.closeSubpath()
        length=route.length();steps=max(16,min(180,math.ceil(length/7)))
        samples=[route.pointAtPercent(route.percentAtLength(length*i/steps)) for i in range(steps+1)]
        if len(_guides)>100:_guides.clear()
        _guides[key]=(route,length,samples)
    return _guides[key]


def architecture_lights(p,r,shape,t,mode,c1,c2):
    """The clip stays fixed while light moves, breathes or rotates inside it."""
    p.save();p.setClipPath(shape,Qt.IntersectClip);base=p.opacity()
    p.setCompositionMode(QPainter.CompositionMode_Screen)
    route,length,samples=guide(r);b=shape.boundingRect();phase=(sum(ord(c) for c in r['id'])%31)/5
    motion={'haunted':'breath','waves':'wave','clockwork':'rotate','electric':'flicker'}.get(mode)
    if motion is None:motion=['chase','breath','wave'][int(t//10)%3]
    soft_colour(p,shape,c2,.32)
    if motion=='breath':
        breath=.5-.5*math.cos(TAU*t/5+phase)
        p.setOpacity(base*(.45+.5*breath));p.fillPath(shape,colour(c1,210))
        for i in range(2):
            scale=1-(i+breath)*.012
            tr=QTransform();tr.translate(b.center().x(),b.center().y());tr.scale(scale,scale);tr.translate(-b.center().x(),-b.center().y())
            p.setPen(QPen(colour(c1 if i%2 else c2,235),3));p.setBrush(Qt.NoBrush);p.drawPath(tr.map(route))
    elif motion=='wave':
        p.setBrush(Qt.NoBrush)
        for strand in range(2):
            wave=QPainterPath()
            for i,q in enumerate(samples):
                prev=samples[max(0,i-1)];nxt=samples[min(len(samples)-1,i+1)]
                dx,dy=nxt.x()-prev.x(),nxt.y()-prev.y();d=max(.001,math.hypot(dx,dy))
                offset=3.2*math.sin(i*.3-TAU*t/5+strand*TAU/3+phase)
                point=QPointF(q.x()-dy/d*offset,q.y()+dx/d*offset)
                if i==0:wave.moveTo(point)
                else:wave.lineTo(point)
            c=c1 if strand%2 else c2
            p.setPen(QPen(colour(c,75),7));p.drawPath(wave)
            p.setPen(QPen(colour(c,235),3));p.drawPath(wave)
    elif motion=='rotate':
        p.translate(b.center());p.rotate(360*t/10+phase*30)
        radius=math.hypot(b.width(),b.height())*.65
        for i in range(6):
            p.rotate(60);p.setPen(QPen(colour(c1 if i%2 else c2,220),max(4,b.width()*.10)))
            p.drawLine(QPointF(0,0),QPointF(radius,0))
    else:
        for i,q in enumerate(samples):
            travel=(i/max(1,len(samples)-1)-t/5+phase)%1
            brightness=.20+.80*(.5+.5*math.cos(TAU*travel*2))**3
            if motion=='flicker':brightness*=.3+.7*max(0,math.sin(TAU*t*.65+i*.12+phase))**2
            p.setOpacity(base*brightness);p.setPen(QPen(colour(c1 if (i//5)%2 else c2),7,Qt.SolidLine,Qt.RoundCap))
            if i:p.drawLine(samples[i-1],q)
    p.restore()


def panel_lights(p,r,t,mode,c1,c2):
    from .renderer import uv_transform
    p.save();p.setTransform(uv_transform(r['projector_points']),True)
    p.setPen(QPen(colour(c2,230),.06));p.setBrush(Qt.NoBrush)
    if mode=='clockwork':
        p.translate(.5,.5);p.rotate(360*t/10)
        for i in range(2):
            size=.35+i*.40;p.rotate(25);p.drawRect(QRectF(-size/2,-size/2,size,size))
    elif mode=='haunted':
        size=.65+.18*math.sin(TAU*t/5)
        p.setBrush(colour(c1,185));p.drawRoundedRect(QRectF(.5-size/2,.5-size/2,size,size),.1,.1)
    else:
        centre=QPointF(.5+.2*math.sin(TAU*t/10),.5+.18*math.cos(TAU*t/10))
        glow=QRadialGradient(centre,.7);glow.setColorAt(0,colour(c1,240));glow.setColorAt(1,colour(c2,40))
        p.fillRect(QRectF(0,0,1,1),glow)
    p.restore()


def draw_spectacle(p,data,r,t,mode,shape,b,c1,c2,actor_strength=1):
    from .renderer import facade_shape, figure_shape, surface_path
    p.save();p.setClipPath(surface_path(data,r),Qt.IntersectClip)
    if r['id']=='facade':
        safe=figure_shape(data,facade_shape(data,r));p.setClipPath(safe,Qt.IntersectClip)
        if mode=='pumpkins':
            from .house_show import ledge_pumpkins
            p.setOpacity(p.opacity()*actor_strength);ledge_pumpkins(p,data,t);p.restore();return
        if mode=='owls':
            from .house_show import ledge_slots,grounded_actor_rect
            slots=ledge_slots(data,1,(120,76))
            if slots:
                p.setOpacity(p.opacity()*actor_strength)
                target,_=grounded_actor_rect('owl',t,slots[0])
                draw_actor(p,'owl',t,target);p.restore();return
        kind,count={'young-skeletons':('young-skeleton',2),'young-ghosts':('young-ghost',2),
                    'bones':('skeleton',3),'bats':('bat',4),'pumpkins':('pumpkin',3),
                    'spiders':('spider',4),'wisps':('wisp',3),'owls':('owl',3)}.get(mode,(None,0))
        if kind and actor_strength>.001:
            p.setOpacity(p.opacity()*actor_strength);character_swarm(p,safe,b,t,kind,count,data)
            # The house actions receive the same fade, once, as the main cast.
            if mode in {'bones','bats','spiders'}:
                from .house_show import older_house
                older_house(p,data,t,mode,1)
        elif mode in {'electric','clockwork'}:
            from .house_show import older_house
            older_house(p,data,t,mode,actor_strength)
    elif r['id']=='roof' or r['type'] in {'frame','edge'}:
        architecture_lights(p,r,surface_path(data,r),t,mode,c1,c2)
    elif r['type']=='curtain' or (r['type']=='window' and r.get('paper_screen',False)):
        panel_lights(p,r,t,mode,c1,c2)
    p.restore()

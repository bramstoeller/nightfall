"""House scenes: performers use the windows, curtain cloth and bay ledge."""
from dataclasses import dataclass
from functools import lru_cache
import heapq
import math
import numpy as np
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen,QPolygonF
from . import model
from .atmosphere import shape_key

TAU=2*math.pi
_circuits={}
_ledges={}


@dataclass(frozen=True)
class Circuit:
    points: tuple
    lengths: tuple
    total: float
    size: tuple


def window_circuit(data,rid,size):
    """A full silhouette follows a closed walk around the physical window."""
    from .renderer import facade_shape,figure_shape,surface_path
    facade=model.region(data,'facade');safe=figure_shape(data,facade_shape(data,facade))
    window=surface_path(data,model.region(data,rid)).boundingRect()
    key=(shape_key(safe),rid,tuple(window.getRect()),size)
    if key in _circuits:return _circuits[key]
    width,height=size;hw,hh=width/2+7,height/2+7
    bounds=safe.boundingRect();step=6
    def fits(x,y):return safe.contains(QRectF(x-hw,y-hh,hw*2,hh*2))
    nodes={(x,y) for x in range(math.ceil(bounds.left()+hw),math.floor(bounds.right()-hw)+1,step)
           for y in range(math.ceil(bounds.top()+hh),math.floor(bounds.bottom()-hh)+1,step) if fits(x,y)}
    if not nodes:_circuits[key]=None;return None
    cx,cy=window.center().x(),window.center().y()
    left,right=window.left()-hw-5,window.right()+hw+5
    top,bottom=window.top()-hh-5,window.bottom()+hh+5
    targets=[(cx,top),(right,top),(right,cy),(right,bottom),(cx,bottom),(left,bottom),(left,cy),(left,top)]
    anchors=[min(nodes,key=lambda q:(q[0]-x)**2+(q[1]-y)**2) for x,y in targets]
    points=[]
    for start,end in zip(anchors,anchors[1:]+anchors[:1]):
        queue=[(0,start)];parents={start:None};cost={start:0}
        while queue:
            _,q=heapq.heappop(queue)
            if q==end:break
            for n in [(q[0]+step,q[1]),(q[0]-step,q[1]),(q[0],q[1]+step),(q[0],q[1]-step)]:
                if n not in nodes:continue
                distance=cost[q]+step
                if distance>=cost.get(n,math.inf):continue
                # Check the swept rectangle between neighbouring grid nodes.
                connector=QRectF(min(n[0],q[0])-hw,min(n[1],q[1])-hh,2*hw+abs(n[0]-q[0]),2*hh+abs(n[1]-q[1]))
                if not safe.contains(connector):continue
                parents[n]=q;cost[n]=distance
                heapq.heappush(queue,(distance+abs(n[0]-end[0])+abs(n[1]-end[1]),n))
        if end not in parents:_circuits[key]=None;return None
        route=[];q=end
        while q is not None:route.append(q);q=parents[q]
        points.extend(route[::-1][:-1])
    if len(points)<8:_circuits[key]=None;return None
    points.append(points[0])
    # A loop that merely backtracks on one side of a window is not an orbit.
    winding=sum(math.atan2((a[0]-cx)*(b[1]-cy)-(a[1]-cy)*(b[0]-cx),
                          (a[0]-cx)*(b[0]-cx)+(a[1]-cy)*(b[1]-cy)) for a,b in zip(points,points[1:]))
    if abs(winding)<math.pi:_circuits[key]=None;return None
    # Remove the staircase with straight, fully checked wall segments.
    smooth=[points[0]];i=0
    while i<len(points)-1:
        far=i+1
        for j in range(i+2,min(len(points),i+18)):
            a,b=points[i],points[j];samples=max(2,math.ceil(math.dist(a,b)/2))
            if all(fits(a[0]+(b[0]-a[0])*k/samples,a[1]+(b[1]-a[1])*k/samples) for k in range(samples+1)):far=j
        smooth.append(points[far]);i=far
    lengths=tuple(math.dist(a,b) for a,b in zip(smooth,smooth[1:]))
    result=Circuit(tuple(smooth),lengths,sum(lengths),size)
    if len(_circuits)>24:_circuits.clear()
    _circuits[key]=result;return result


def circuit_rect(circuit,t,phase=0,period=30):
    distance=((t/period+phase)%1)*circuit.total
    for a,b,length in zip(circuit.points,circuit.points[1:],circuit.lengths):
        if distance<=length:
            u=distance/max(length,.001);x=a[0]+(b[0]-a[0])*u;y=a[1]+(b[1]-a[1])*u
            return QRectF(x-circuit.size[0]/2,y-circuit.size[1]/2,*circuit.size)
        distance-=length
    x,y=circuit.points[0];return QRectF(x-circuit.size[0]/2,y-circuit.size[1]/2,*circuit.size)


def ghost_circuits(data):
    # The upper-right corner is narrow between the real window and roof.
    # Coarse, solid cloth silhouettes stay readable while fitting that passage.
    return (window_circuit(data,'attic',(44,52)),window_circuit(data,'right',(36,46)))


def simple_ghost(p,rect,t,tint,variant=0):
    """Broad luminous cloth, expressive eyes and a continuous, waving hem."""
    p.save();p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    p.translate(rect.x(),rect.y());p.scale(rect.width(),rect.height())
    p.setPen(Qt.NoPen);p.setBrush(QColor(tint))
    a=TAU*t/5+variant
    body=QPainterPath();body.moveTo(.14,.43)
    body.cubicTo(.11,.03,.85,.01,.85,.43)
    body.lineTo(.94,.79)
    for i in range(5):
        x=.94-i*.176;y=.82+.05*math.sin(a+i*1.6)
        body.quadTo(x-.088,y+.07,x-.176,y)
    body.lineTo(.06,.79);body.closeSubpath();p.drawPath(body)
    p.setBrush(QColor('#040208'));look=.026*math.sin(a)
    p.drawEllipse(QRectF(.32+look,.31,.105,.14));p.drawEllipse(QRectF(.59+look,.31,.105,.14))
    smile=QPainterPath();smile.moveTo(.43,.53);smile.quadTo(.51,.64,.59,.53)
    p.setPen(QPen(QColor('#65435d'),.035,Qt.SolidLine,Qt.RoundCap));p.setBrush(Qt.NoBrush);p.drawPath(smile)
    p.restore()


def ledge_slots(data,count=2,size=(78,78)):
    from .renderer import facade_shape,figure_shape
    safe=figure_shape(data,facade_shape(data,model.region(data,'facade')))
    trims=[r for r in data['regions'] if r['id'].startswith('bay-trim') and r.get('enabled',True)]
    if not trims:return ()
    key=(shape_key(safe),tuple(tuple(tuple(p) for p in r['projector_points']) for r in trims),count,size)
    if key in _ledges:return _ledges[key]
    segments=[r['projector_points'][:2] for r in trims]
    left=min(p[0] for segment in segments for p in segment);right=max(p[0] for segment in segments for p in segment)
    slots=[]
    targets=[.52] if count==1 else [.25,.75]
    for u in targets[:count]:
        wanted=left+(right-left)*u;choices=[]
        for x in range(math.ceil(left+size[0]/2),math.floor(right-size[0]/2)+1,3):
            for a,b in segments:
                if not min(a[0],b[0])<=x<=max(a[0],b[0]):continue
                y=a[1]+(b[1]-a[1])*(x-a[0])/max(.001,b[0]-a[0])
                rect=QRectF(x-size[0]/2,y-size[1]-6,*size)
                if safe.contains(rect.adjusted(-5,-5,5,5)) and all(not rect.adjusted(-8,-8,8,8).intersects(other) for other in slots):choices.append(rect)
        if choices:slots.append(min(choices,key=lambda r:abs(r.center().x()-wanted)))
    result=tuple(slots);_ledges[key]=result;return result


def grounded_actor_rect(kind,t,rect,variant=0,hop=0):
    from .spectacle import actor_frame,ACTOR_BOUNDS
    image=actor_frame(kind,round(t*60)%300,variant)
    alpha=np.frombuffer(image.constBits(),np.uint8).reshape(256,256,4)[:,:,3]
    yy,xx=np.where(alpha>4);source=QRectF(*ACTOR_BOUNDS[kind])
    scale=min(rect.width()/source.width(),rect.height()/source.height())
    w,h=source.width()*scale,source.height()*scale
    origin=QPointF(rect.center().x()-w/2,rect.center().y()-h/2)
    foot=origin.y()+(int(yy.max())+1-source.y())*scale
    # The actual lowest foot/skin pixel stays two pixels above the measured
    # top edge. Internal sprite bobbing must not make a perched actor float.
    dy=rect.bottom()+4-hop-foot
    actual=QRectF(origin.x()+(int(xx.min())-source.x())*scale,
                  origin.y()+dy+(int(yy.min())-source.y())*scale,
                  (int(xx.max())-int(xx.min())+1)*scale,
                  (int(yy.max())-int(yy.min())+1)*scale)
    return rect.translated(0,dy),actual


def ledge_pumpkins(p,data,t):
    from .spectacle import draw_actor
    slots=ledge_slots(data)
    for i,rect in enumerate(slots):
        # Each takes its turn to hop; both return to their real support line.
        phase=(t-i*2.5)%5
        hop=6*math.sin(math.pi*phase/.9)**2 if phase<.9 else 0
        target,_=grounded_actor_rect('pumpkin',t+i*.6,rect,i,hop)
        draw_actor(p,'pumpkin',t+i*.6,target,i)


def curtain_candles(p,r,t):
    from .renderer import uv_transform
    p.save();p.setTransform(uv_transform(r['projector_points']),True);p.setPen(Qt.NoPen)
    for i,x in enumerate([.28,.72]):
        height=.47 if i==0 else .64;top=.96-height
        p.setBrush(QColor('#ffe6a1'));p.drawRoundedRect(QRectF(x-.105,top,.21,height),.045,.045)
        p.setBrush(QColor('#fffbd4'));p.drawRect(QRectF(x-.075,top,.045,height))
        p.setPen(QPen(QColor('#302239'),.025));p.drawLine(QPointF(x,top+.02),QPointF(x,top-.055));p.setPen(Qt.NoPen)
        lean=.025*math.sin(TAU*t*1.2+i*2);flame=QPainterPath(QPointF(x,top-.025))
        flame.cubicTo(x-.14,top-.12,x+.02+lean,top-.20,x+lean,top-.28)
        flame.cubicTo(x+.15,top-.14,x+.10,top-.04,x,top-.025)
        p.setBrush(QColor('#ffab24'));p.drawPath(flame)
        p.setBrush(QColor('#fffbd1'));p.drawEllipse(QRectF(x-.04,top-.14,.08,.115))
    p.restore()


def young_house(p,data,t,strength):
    """A 30-second miniature play; the house supplies routes and supports."""
    from .renderer import facade_shape,figure_shape
    from .spectacle import draw_actor
    from .effects import envelope,cheshire
    safe=figure_shape(data,facade_shape(data,model.region(data,'facade')))
    p.save();p.setClipPath(safe,Qt.IntersectClip);p.setCompositionMode(QPainter.CompositionMode_SourceOver);base=p.opacity()*strength
    local=t%30;attic,right=ghost_circuits(data)
    if local<10:
        for rect in ledge_slots(data,1,(70,86)):
            target,_=grounded_actor_rect('young-skeleton',t,rect)
            p.setOpacity(base*envelope(local,0,10,30));draw_actor(p,'young-skeleton',t,target)
    if local<24 and attic is not None:
        p.setOpacity(base*envelope(local,0,24,30));simple_ghost(p,circuit_rect(attic,t,period=24),t,'#fff4d9')
    if 10<=local<20 and right is not None:
        p.setOpacity(base*envelope(local,10,10,30));simple_ghost(p,circuit_rect(right,t,period=10),t,'#bbfff1',1)
    if 19<=local<24:
        p.setOpacity(base*envelope(local,19,5,30));ledge_pumpkins(p,data,t)
    if local>=23:
        from .renderer import facade_cast
        from .routes import performer_pose
        slot=facade_cast(data)[1][0]
        if slot is not None:
            p.setOpacity(base*envelope(local,23,7,30));cheshire(p,performer_pose(slot,t)[0],local-22)
    p.restore()

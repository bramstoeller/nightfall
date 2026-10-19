"""Find a closed flight route with room for the entire ghost, not just its centre."""
import math
from collections import deque
from dataclasses import dataclass
from PySide6.QtCore import QRectF
from .atmosphere import shape_key

_cache={}
_performances={}
_rooms={}


@dataclass(frozen=True)
class PerformerSlot:
    center: tuple
    size: tuple
    motion: tuple
    rotation: float
    envelope: tuple
    index: int


def performance_slots(shape,b,specs,gap=12):
    """Reserve disjoint rooms containing each complete animated silhouette.

    A spec is (width, height, horizontal motion, vertical motion, max angle).
    Rooms include rotation, movement and twelve pixels of mask clearance.
    Disconnected patches of brickwork are useful stages too; squeezing every
    actor onto one shared route made the old swarms overtake and pile up.
    """
    specs=tuple(tuple(s) for s in specs);shape_id=shape_key(shape)
    key=(shape_id,specs,gap)
    if key in _performances:return _performances[key]
    targets=[(.51,.46),(.84,.80),(.56,.81),(.29,.32),(.41,.16),(.72,.43)]
    slots=[];occupied=[]
    for index,(width,height,rx,ry,angle) in enumerate(specs):
        slot=None;u,v=targets[index%len(targets)];target=(b.x()+u*b.width(),b.y()+v*b.height())
        for scale in (1,.9,.8):
            w,h=width*scale,height*scale
            radians=math.radians(angle)
            ew=w*math.cos(radians)+h*math.sin(radians)+2*rx+24
            eh=h*math.cos(radians)+w*math.sin(radians)+2*ry+24
            room_key=(shape_id,round(ew,5),round(eh,5))
            if room_key not in _rooms:
                candidates=[QRectF(x-ew/2,y-eh/2,ew,eh)
                            for x in range(math.ceil(b.left()+ew/2),math.floor(b.right()-ew/2)+1,12)
                            for y in range(math.ceil(b.top()+eh/2),math.floor(b.bottom()-eh/2)+1,12)]
                candidates=[rect for rect in candidates if shape.contains(rect)]
                if len(_rooms)>100:_rooms.clear()
                _rooms[room_key]=candidates
            choices=[rect for rect in _rooms[room_key]
                     if all(not rect.adjusted(-gap/2,-gap/2,gap/2,gap/2).intersects(other) for other in occupied)]
            if not choices:continue
            room=min(choices,key=lambda r:(r.center().x()-target[0])**2+(r.center().y()-target[1])**2)
            occupied.append(room)
            slot=PerformerSlot((room.center().x(),room.center().y()),(w,h),(rx,ry),angle,
                               (room.x(),room.y(),room.width(),room.height()),index)
            break
        slots.append(slot)
    if len(_performances)>48:_performances.clear()
    result=tuple(slots);_performances[key]=result;return result


def performer_pose(slot,t):
    """Smooth motion stays inside the reserved room for the entire 120s loop."""
    phase=slot.index*2.399963
    x=slot.center[0]+slot.motion[0]*math.sin(2*math.pi*t/12+phase)
    y=slot.center[1]+slot.motion[1]*math.sin(2*math.pi*t/20+phase*.7)
    scale=.97+.03*math.cos(2*math.pi*t/30+phase)
    w,h=slot.size[0]*scale,slot.size[1]*scale
    return QRectF(x-w/2,y-h/2,w,h),slot.rotation*math.sin(2*math.pi*t/10+phase)

def flight_route(shape,b,ratio,old=False,margin=7,width=None):
    width=(48 if old else 40) if width is None else width
    poly=shape.toFillPolygon();key=(tuple((round(q.x(),2),round(q.y(),2)) for q in poly),round(ratio,3),old,margin,width)
    if key in _cache:return _cache[key]
    step=10;height=width*ratio
    clearance=margin+2  # extra room between the sampled route positions
    def fits(x,y):return shape.contains(QRectF(x-width*.6-clearance,y-height*.5-clearance,width*1.2+clearance*2,height*1.1+clearance*2))
    nodes={(x,y) for x in range(int(b.left())+step,int(b.right()),step) for y in range(int(b.top())+step,int(b.bottom()),step) if fits(x,y)}
    best=set();remaining=set(nodes)
    def neighbours(q):
        x,y=q
        return [(x+step,y),(x-step,y),(x,y+step),(x,y-step)]
    while remaining:
        first=remaining.pop();component={first};queue=deque([first])
        while queue:
            q=queue.popleft()
            for n in neighbours(q):
                if n in remaining and fits((n[0]+q[0])/2,(n[1]+q[1])/2):remaining.remove(n);component.add(n);queue.append(n)
        if len(component)>len(best):best=component
    if len(best)<3:return None
    targets=[(.57,.28),(.45,.55),(.68,.76),(.82,.48)]
    anchors=[min(best,key=lambda q:(q[0]-b.x()-u*b.width())**2+(q[1]-b.y()-v*b.height())**2) for u,v in targets]
    points=[]
    for start,end in zip(anchors,anchors[1:]+anchors[:1]):
        queue=deque([start]);parents={start:None}
        while queue and end not in parents:
            q=queue.popleft()
            for n in neighbours(q):
                if n in best and n not in parents and fits((n[0]+q[0])/2,(n[1]+q[1])/2):parents[n]=q;queue.append(n)
        route=[];q=end
        while q is not None:route.append(q);q=parents[q]
        points.extend(route[::-1][:-1])
    if not points:return None
    points.append(points[0])
    # Replace the staircase with straight, fully checked wall segments.
    smooth=[points[0]];index=0
    while index<len(points)-1:
        far=index+1
        for end in range(index+2,min(len(points),index+20)):
            a,c=points[index],points[end];samples=max(2,int(math.dist(a,c)/2))
            if all(fits(a[0]+(c[0]-a[0])*j/samples,a[1]+(c[1]-a[1])*j/samples) for j in range(samples+1)):far=end
            else:break
        smooth.append(points[far]);index=far
    points=smooth;lengths=[math.dist(a,b) for a,b in zip(points,points[1:])];total=sum(lengths)
    result=(points,lengths,total,width,height)
    if len(_cache)>24:_cache.clear()
    _cache[key]=result;return result

def flight_position(route,t,actor):
    points,lengths,total,width,height=route
    distance=((t/[20,24,30][actor%3]+actor/3)%1)*total
    for a,b,length in zip(points,points[1:],lengths):
        if distance<=length:
            u=distance/max(length,.001);return a[0]+u*(b[0]-a[0]),a[1]+u*(b[1]-a[1]),width
        distance-=length
    return *points[0],width

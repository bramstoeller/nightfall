"""Find a closed flight route with room for the entire ghost, not just its centre."""
import math
from collections import deque
from PySide6.QtCore import QRectF

_cache={}

def flight_route(shape,b,ratio,old=False,margin=7):
    poly=shape.toFillPolygon();key=(tuple((round(q.x(),2),round(q.y(),2)) for q in poly),round(ratio,3),old,margin)
    if key in _cache:return _cache[key]
    step=10;width=48 if old else 40;height=width*ratio
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

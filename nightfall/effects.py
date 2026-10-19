"""Halloween effects mapped to the configured house surfaces."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient,QImage,QTransform
from .model import region
from .animation import skeleton_frame
from .atmosphere import clouds,curtain_fire,soft_colour,inset
from .spectacle import STYLES as SPECTACLE_STYLES, draw_spectacle, architecture_lights,architecture_palette
from .routes import performance_slots,performer_pose

TAU=2*math.pi
SMOKE_STRENGTH=.5
STYLES={
    'young':('Children 4–8 · 2 minutes','#fff0ad','#c0f9ff','Friendly dancing skeletons, smiling pumpkins, magic lights, owls and a playful house.'),
    'older':('Children 8–12 · 2 minutes','#74a6ff','#ca96ff','Mysterious spirits, bats, a large crawling spider, haunted frames and disappearing Cheshire.'),
    'aurora':('Green magic smoke','#32ec78','#13cadf','Green smoke, yellow-green fireflies and a breathing tree.'),
    'embers':('Red fire glow','#ff3824','#ffac20','Red-orange clouds, glowing embers and curtain flames.'),
    'moonlight':('Blue moon mist','#46aaff','#7449ed','Calm blue clouds with a soft purple glow.'),
    'shadowplay':('Purple night wings','#c83eff','#f4479e','Purple smoke, pink glow, bats and attic eyes.'),
    'cheshire':('Cheshire · vanishing cat','#b942f5','#ff67b9','A striped cat fades into purple smoke, leaving its grin behind.'),
    'show':('Complete show · 2 minutes','#b942f5','#32ec78','Twelve scenes with character animation, architectural motion, fire and Cheshire.'),
}
STYLES.update(SPECTACLE_STYLES)
OLD={'older','moonlight','shadowplay'}

def envelope(t,start,length,period=30):
    v=(t-start)%period
    return max(0,min(1,v/.8,(length-v)/.8)) if v<length else 0

def color(value,alpha=255):
    c=QColor(value);c.setAlpha(max(0,min(255,int(alpha))));return c

def halo(p,x,y,r,c,alpha):
    g=QRadialGradient(QPointF(x,y),r)
    g.setColorAt(0,color(c,alpha));g.setColorAt(.3,color(c,alpha*.5));g.setColorAt(1,color(c,0))
    p.fillRect(QRectF(x-r,y-r,2*r,2*r),g)

def fireflies(p,shape,b,t,count=36):
    """Wandering yellow-green lights, with slow asynchronous bioluminescent pulses."""
    safe=inset(shape,9)
    p.save();base=p.opacity();p.setPen(Qt.NoPen)
    for i in range(count):
        phase=i*2.399963
        a=TAU*t/[12,20,24,30][i%4]
        x=b.x()+b.width()*(.5+.42*math.sin(phase+a)+.035*math.sin(3*a+phase))
        y=b.y()+b.height()*(.5+.40*math.sin(phase*1.7-a)+.04*math.cos(2*a+phase))
        if not safe.contains(QPointF(x,y)):continue
        pulse=(.5+.5*math.sin(TAU*t/[4,6,8,10][i%4]+phase))**4
        brightness=.06+.94*pulse
        p.setOpacity(base*brightness)
        c='#cefa43' if i%3 else '#8aff4c'
        halo(p,x,y,6+(i%3),c,150)
        p.setBrush(color(c,235));p.drawEllipse(QPointF(x,y),1.2,1.2)
        p.setBrush(color('#efffa0',220));p.drawEllipse(QPointF(x,y),.55,.55)
    p.restore()

def ribbons(p,b,t,c1,c2):
    p.save();p.setBrush(Qt.NoBrush)
    for strand in range(3):
        curve=QPainterPath()
        for j in range(45):
            u=j/44
            v=.42+.20*math.sin(u*TAU+TAU*t/20+strand*1.5)+.055*math.sin(u*TAU*3-TAU*t/12)
            q=QPointF(b.x()+b.width()*u,b.y()+b.height()*v)
            if j==0:curve.moveTo(q)
            else:curve.lineTo(q)
        c=c1 if strand%2==0 else c2
        p.setPen(QPen(color(c,24),10));p.drawPath(curve)
        p.setPen(QPen(color(c,165),1.6));p.drawPath(curve)
    p.restore()

def comet_swarm(p,b,t,c1,c2,count=38):
    p.save();base=p.opacity();p.setPen(Qt.NoPen)
    for i in range(count):
        period=[6,8,10,12,15,20][i%6]
        a=TAU*t/period+i*2.39996
        v=((t/period+i*.618)%1)
        x=b.x()+b.width()*(.5+.43*math.sin(a))
        y=b.y()+b.height()*(.16+.66*v)
        brightness=math.sin(math.pi*v)**2
        c=c1 if i%2 else c2;radius=1.3+(i%4)*.55
        p.setOpacity(base*brightness*.9)
        if i%5==0:halo(p,x,y,8,c,100)
        p.setBrush(color(c));p.drawEllipse(QPointF(x,y),radius,radius)
        p.setPen(QPen(color(c,150),.8));p.drawLine(QPointF(x,y),QPointF(x-10*math.cos(a),y-6));p.setPen(Qt.NoPen)
    p.restore()

def dancer(p,data,t):
    # Alternate the dancer and cat on their shared patch of clear brickwork.
    visible=envelope(t,1,9,40)
    if visible<.001 or p.opacity()<.001:return
    from .renderer import facade_cast
    safe,slots=facade_cast(data);slot=slots[0]
    if slot is None:return
    area,_=performer_pose(slot,t);height=area.height()*.9;width=height*480/550
    rect=QRectF(area.center().x()-width/2,area.center().y()-height/2,width,height)
    p.save();p.setClipPath(safe,Qt.IntersectClip);p.setOpacity(p.opacity()*visible)
    actor=skeleton_frame(t)
    p.drawImage(rect,actor,QRectF(0,100,480,550))
    p.setCompositionMode(QPainter.CompositionMode_Screen);p.setOpacity(p.opacity()*.65)
    p.drawImage(rect,actor,QRectF(0,100,480,550))
    p.restore()

def bat(p,x,y,size,t,phase,c):
    p.save();p.translate(x,y);p.rotate(10*math.sin(TAU*t/4+phase));p.setPen(QPen(color(c),1))
    p.setBrush(color(c,190));flap=.45+.45*math.sin(TAU*t*2+phase)
    wing=QPainterPath();wing.moveTo(0,-size*.15)
    for sign in [-1,1]:
        wing.moveTo(0,-size*.15)
        wing.lineTo(sign*size,-size*flap)
        wing.quadTo(sign*size*.78,-size*.02,sign*size*.72,size*.2)
        wing.quadTo(sign*size*.5,-size*.02,sign*size*.35,size*.22)
        wing.lineTo(0,size*.1);wing.closeSubpath()
    p.drawPath(wing);p.setBrush(color('#ffffff'));p.drawEllipse(QPointF(0,0),size*.11,size*.22)
    p.restore()

def bats(p,b,t,c,shape=None):
    if shape is not None:
        from .spectacle import character_swarm
        character_swarm(p,shape,b,t,'bat',2)
        return
    for i in range(5):
        a=TAU*t/[12,15,20][i%3]+i*1.7
        x=b.x()+b.width()*(.5+.39*math.sin(a));y=b.y()+b.height()*(.4+.24*math.sin(a*2+i))
        bat(p,x,y,10+i%3*4,t,i,c)

def spider(p,data,t,c):
    attic=region(data,'attic')['projector_points']
    x=max(q[0] for q in attic)+30;top=min(q[1] for q in attic)-35
    y=top+65*(.5-.5*math.cos(TAU*t/30))
    p.save();p.setPen(QPen(color(c,120),.65));p.drawLine(QPointF(x,top),QPointF(x,y))
    p.setPen(QPen(color(c,240),1.4));p.setBrush(color(c,220));p.drawEllipse(QPointF(x,y),4,6)
    for sign in [-1,1]:
        for i in range(4):
            a=math.sin(TAU*t*2+i)*1.5
            leg=QPainterPath(QPointF(x,y-3+i*2));leg.lineTo(x+sign*(8+i),y-10+i*5+a);leg.lineTo(x+sign*(13+i),y-3+i*5+a);p.drawPath(leg)
    p.restore()

def chaser(p,r,t,c1,c2):
    pts=r['projector_points']
    if r['id']=='roof' and len(pts)==6:
        points=[[(pts[0][0]+pts[5][0])/2,(pts[0][1]+pts[5][1])/2],
                [(pts[1][0]+pts[4][0])/2,(pts[1][1]+pts[4][1])/2],
                [(pts[2][0]+pts[3][0])/2,(pts[2][1]+pts[3][1])/2]]
    else:points=[pts[0],pts[1]]
    lengths=[math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(points,points[1:])];total=sum(lengths)
    if total<1:return
    def position(distance):
        for a,b,length in zip(points,points[1:],lengths):
            if distance<=length:
                u=distance/max(length,.001);return QPointF(a[0]+u*(b[0]-a[0]),a[1]+u*(b[1]-a[1]))
            distance-=length
        return QPointF(*points[-1])
    p.save();base=p.opacity();p.setPen(Qt.NoPen)
    for runner in range(2):
        a=TAU*t/24+runner*math.pi;head=(.5-.5*math.cos(a))*total
        direction=1 if math.sin(a)>=0 else -1
        c=c1 if runner==0 else c2;speed=abs(math.sin(a));tail=10+38*speed
        for j in range(17):
            q=position(max(0,min(total,head-direction*j*tail/16)))
            p.setOpacity(base*(1-j/17)**2*(1 if j==0 else speed))
            halo(p,q.x(),q.y(),5,c,90)
        # Local shutter samples smooth the moving head, without blurring a frame.
        for sample in range(5):
            phase=TAU*(t-sample/240)/24+runner*math.pi
            q=position((.5-.5*math.cos(phase))*total)
            p.setOpacity(base/5);halo(p,q.x(),q.y(),2.8,c,230)
        q=position(head);p.setOpacity(base);p.setBrush(color(c));p.drawEllipse(q,1.1,1.1)
    p.restore()

def attic_magic(p,r,t,c1,c2,style):
    # Paper is the only full glass canvas. No colour spill onto upper glazing.
    if not r.get('paper_screen',False):return
    from .renderer import uv_transform
    p.save();p.setTransform(uv_transform(r['projector_points']),True)
    if style=='cheshire':
        cheshire(p,QRectF(.07,.08,.86,.84),t)
    elif style in {'aurora','embers'}:
        for i in range(5):
            a=TAU*t/8+i*TAU/5
            x=.5+.29*math.cos(a);y=.5+.32*math.sin(a)
            p.setPen(QPen(color(c1 if i%2 else c2,180),.018));p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(x,y),.12,.10)
        p.setPen(Qt.NoPen);p.setBrush(color('#fff7de'));p.drawEllipse(QPointF(.5,.5),.035,.045)
    elif style=='shadowplay':
        a=envelope(t,5,10,20);p.setOpacity(a)
        for x in [.30,.70]:
            p.setBrush(color(c1));p.setPen(Qt.NoPen);p.drawEllipse(QPointF(x,.32),.13,.09)
            p.setBrush(color('#050609'));p.drawEllipse(QPointF(x+.025*math.sin(TAU*t/4),.32),.045,.075)
        p.setBrush(color(c2));p.drawEllipse(QPointF(.5,.63),.11,.20)
    p.restore()

def cheshire(p,b,t):
    # Build the facial layers before adding the character to the smoke. A wink
    # must cover the open iris, rather than add light on top of the open eye.
    size=min(b.width(),b.height());pixels=max(32,min(320,math.ceil(size)))
    image=QImage(pixels,pixels,QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
    q=QPainter(image);q.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
    _cheshire_layers(q,QRectF(0,0,pixels,pixels),t);q.end()
    p.drawImage(QRectF(b.center().x()-size/2,b.center().y()-size/2,size,size),image)

_cat_faces=None
_cat_mips={}

def cat_image(name,size):
    """Area-filter before sampling a tiny face, preserving fine teeth and fur."""
    from .renderer import sprite
    width=320 if size>160 else 160 if size>80 else 80 if size>40 else 40
    key=(name,width)
    if key not in _cat_mips:
        source=sprite('cheshire-head-v1') if name=='head' else cat_face_layers()[name]
        _cat_mips[key]=source.scaled(width,width,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    return _cat_mips[key]

def cat_face_layers():
    """Trace the actual iris and grin contours of the 1254px generated sprite."""
    global _cat_faces
    if _cat_faces is not None:return _cat_faces
    from .renderer import sprite
    eye=QPainterPath();eye.moveTo(344,580)
    eye.cubicTo(357,538,410,527,443,552)
    eye.cubicTo(475,574,493,620,510,657)
    eye.cubicTo(477,677,415,680,379,652)
    eye.cubicTo(350,632,336,605,344,580);eye.closeSubpath()
    normalize=QTransform.fromScale(1/1254,1/1254);left=normalize.map(eye)
    right=QTransform(-1,0,0,1,1,0).map(left)
    eyes=left.united(right)
    mouth=QPainterPath();mouth.moveTo(310,758)
    mouth.cubicTo(377,795,470,839,565,829)
    mouth.cubicTo(593,831,608,817,627,819)
    mouth.cubicTo(646,817,661,831,689,829)
    mouth.cubicTo(784,839,877,795,944,758)
    mouth.cubicTo(909,863,795,924,627,927)
    mouth.cubicTo(459,924,345,863,310,758);mouth.closeSubpath()
    mouth=normalize.map(mouth)
    _cat_faces={}
    for name,shape,source in [('eyes',eyes,'cheshire-head-v1'),('mouth',mouth,'cheshire-head-v1'),('wink',right,'cheshire-wink-v1')]:
        layer=QImage(320,320,QImage.Format_ARGB32_Premultiplied);layer.fill(Qt.transparent)
        q=QPainter(layer);q.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
        q.scale(320,320);q.setClipPath(shape);q.drawImage(QRectF(0,0,1,1),sprite(source));q.end()
        _cat_faces[name]=layer
    return _cat_faces

def _cheshire_layers(p,b,t):
    """Generated fur sprite, with eyes and grin surviving the fading head."""
    from .renderer import sprite
    p.save();base=p.opacity();size=min(b.width(),b.height())*.94
    image=cat_image('head',size)
    p.translate(b.center().x()+size*.018*math.sin(TAU*t/4),b.center().y())
    p.rotate(2*math.sin(TAU*t/10));scale=1+.025*math.sin(TAU*t/12)
    p.scale(size*scale,size*scale);p.translate(-.5,-.5)
    target=QRectF(0,0,1,1)
    body=envelope(t,1,12,20);eyes=envelope(t,1,16,20);grin=envelope(t,1,18,20)
    p.setOpacity(base*body);p.drawImage(target,image)
    p.setOpacity(base*eyes);p.drawImage(target,cat_image('eyes',size))
    wink=math.exp(-((t%20-7.7)/.24)**2)
    if wink>.001:
        p.setOpacity(base*eyes*wink);p.drawImage(target,cat_image('wink',size))
    p.setOpacity(base*grin);p.drawImage(target,cat_image('mouth',size));p.restore()


def draw_extras(p,data,r,t,mode,shape,b,actor_strength=1,allow_events=True):
    if mode not in STYLES:return
    _,c1,c2,_=STYLES[mode]
    if mode in SPECTACLE_STYLES:
        draw_spectacle(p,data,r,t,mode,shape,b,c1,c2,actor_strength);return
    if r['id'] in {'roof','roof-tip'} or r['id'].startswith('bay-trim') or r['type']=='frame':
        c1,c2=architecture_palette(mode)
    p.save();gain=p.opacity()
    if r['id']=='facade':
        p.setCompositionMode(QPainter.CompositionMode_Screen)
        mist={'older':'blue-purple','aurora':'green-smoke','embers':'red-fire','moonlight':'blue-purple','shadowplay':'purple-smoke','cheshire':'purple-smoke'}
        if mode in mist:
            clouds(p,shape,b,t,mist[mode],SMOKE_STRENGTH*(.95 if mode!='moonlight' else .72))
        if mode=='aurora':fireflies(p,shape,b,t,55)
        elif mode=='embers':p.setOpacity(gain*.8);comet_swarm(p,b,t,c1,c2,65)
        elif mode=='shadowplay':
            from .renderer import facade_shape,figure_shape
            p.setOpacity(gain*.9*actor_strength);bats(p,b,t,c1,figure_shape(data,facade_shape(data,r)))
        if mode=='young':
            from .house_show import young_house
            p.setOpacity(gain);young_house(p,data,t,actor_strength,allow_restart=allow_events)
            p.setOpacity(gain);fireflies(p,shape,b,t,10)
        if mode in {'cheshire','older'}:
            # The clear brickwork between attic and upper windows is the stage.
            from .renderer import facade_cast
            safe,slots=facade_cast(data);slot=slots[0]
            cat_time=t if mode=='cheshire' else t-8
            appearance=1 if mode=='cheshire' else envelope(t,8,20,40)
            if slot is not None:
                area,_=performer_pose(slot,t)
                p.save();p.setClipPath(safe,Qt.IntersectClip)
                p.setOpacity(gain*appearance*actor_strength);cheshire(p,area,cat_time);p.restore()
        if mode in {'older','embers','shadowplay','cheshire'}:
            from .house_show import older_house
            p.setOpacity(gain);older_house(p,data,t,mode,actor_strength,allow_restart=allow_events)
    elif r['id']=='roof' or r['id'].startswith('bay-trim'):
        pulse=.55+.35*math.sin(TAU*t/12+b.x()*.01)
        soft_colour(p,shape,c1,pulse)
        p.setClipPath(inset(shape,2),Qt.IntersectClip);p.setOpacity(gain*.65);chaser(p,r,t,c1,c2)
    elif r['type']=='frame':
        soft_colour(p,shape,c1,.45+.25*math.sin(TAU*t/12))
    elif r['id']=='roof-tip':
        pulse=.25+.75*(.5+.5*math.sin(TAU*t/4))**3
        p.setOpacity(gain*pulse);p.fillPath(shape,color(c1))
        halo(p,b.center().x(),b.center().y(),b.height()*.6,c2,190)
    elif r['id']=='attic':
        p.setOpacity(gain);attic_magic(p,r,t,c1,c2,mode)
    elif r['type']=='curtain' and r.get('enabled',True) and mode=='young':
        from .house_show import curtain_candles
        curtain_candles(p,r,t)
    elif r['type']=='curtain' and r.get('enabled',True) and mode in {'aurora','embers'}:
        if mode=='embers':
            curtain_fire(p,r,t);p.restore();return
        from .renderer import uv_transform
        p.setTransform(uv_transform(r['projector_points']),True)
        p.setPen(Qt.NoPen)
        for i in range(7):
            y=((t/4+i/7)%1);p.setOpacity(gain*.75*math.sin(math.pi*y)**2)
            p.setBrush(color(c1 if i%2 else c2));p.drawEllipse(QPointF(.5+.32*math.sin(TAU*y+i),y),.035,.075)
    p.restore()
    if r['id']=='roof' or r['type']=='frame':
        from .renderer import surface_path
        architecture_lights(p,r,surface_path(data,r),t,mode,c1,c2)

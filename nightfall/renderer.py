"""The desktop preview, calibration PNG and exported video use this renderer."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF, QTransform, QRadialGradient, QPixmap
from .model import WIDTH, HEIGHT, ROOT, origin_point, region
from .animation import skeleton_frame, young_ghost_frame
from .effects import draw_extras, OLD,fireflies,STYLES
from .routes import flight_route,flight_position,performance_slots,performer_pose
from .atmosphere import texture,soft_colour,feather_mask,outset
from .tone import brighten

TAU=2*math.pi
SHOW_SCENES={
    'young':[(0,'young',0),(30,'young-skeletons',0),(42,'pumpkins',0),(54,'waves',0),
             (66,'young-ghosts',0),(78,'owls',0),(90,'haunted',0),(102,'wisps',2),(114,'cheshire',3)],
    'older':[(0,'older',0),(24,'bats',0),(36,'electric',0),(42,'spiders',0),
             (60,'clockwork',0),(66,'embers',0),(78,'bones',0),(96,'cheshire',1),(108,'shadowplay',0)],
    'show':[(0,'bones',0),(10,'pumpkins',0),(20,'waves',0),(30,'wisps',0),
            (40,'owls',0),(50,'haunted',0),(60,'bats',0),(70,'spiders',0),
            (80,'clockwork',0),(90,'electric',0),(100,'embers',0),(110,'cheshire',1)],
}

def render_show(data,t,show='show'):
    """Two-minute programmes with one-second dissolves and a clean loop seam."""
    t=t%120;scenes=SHOW_SCENES[show]
    index=max(i for i,(start,_,_) in enumerate(scenes) if start<=t)
    start,mode,offset=scenes[index]
    if index and t-start<1:
        age=t-start
        # Exchange performers through a brief empty stage. Dissolving two full
        # casts put the outgoing and incoming silhouettes on top of each other.
        current=render_scene(data,t-start+offset,mode,actor_strength=smooth(max(0,2*age-1)))
        previous_start,previous_mode,previous_offset=scenes[index-1]
        result=render_scene(data,t-previous_start+previous_offset,previous_mode,actor_strength=smooth(max(0,1-2*age)))
        p=QPainter(result);p.setOpacity(smooth(t-start));p.drawImage(0,0,current);p.end();current=result
    else:current=render_scene(data,t-start+offset,mode)
    fade=min(smooth(t/.8),smooth((120-t)/.8))
    if fade<1:
        result=QImage(WIDTH,HEIGHT,QImage.Format_RGB32);result.fill(Qt.black)
        p=QPainter(result);p.setOpacity(fade);p.drawImage(0,0,current);p.end();current=result
    return current

def clamp(v,a=0,b=1): return max(a,min(b,v))
def smooth(v): v=clamp(v);return v*v*(3-2*v)
def cycle(t,start,duration,fade=.8):
    a=(t-start)%120
    return smooth(a/fade)*smooth((duration-a)/fade) if a<duration else 0

def rnd(n): return (math.sin(n*127.1+311.7)*43758.5453)%1

def polygon(pts): return QPolygonF([QPointF(x,y) for x,y in pts])
def path(pts):
    p=QPainterPath();p.addPolygon(polygon(pts));p.closeSubpath();return p

def box(pts): return polygon(pts).boundingRect()
def alignment_shapes(data):
    """Only traceable physical edges in the simple alignment view."""
    return [r for r in data['regions'] if r['type']!='stage'
            and not r.get('alignment_hidden',False) and r.get('role')!='group' and not (r['type']=='frame' and r.get('border_width'))
            and not (r['type']=='curtain' and not r.get('enabled',True))] + list(data.get('exclusions',[]))
def surface_path(data,r):
    if r.get('shape')=='ellipse':
        ellipse=QPainterPath();ellipse.addEllipse(QRectF(0,0,1,1))
        shape=uv_transform(r['projector_points']).map(ellipse)
    else:shape=path(r['projector_points'])
    if r.get('inner_region'):shape=shape.subtracted(path(region(data,r['inner_region'])['projector_points']))
    elif r.get('inner_regions'):
        for rid in r['inner_regions']:shape=shape.subtracted(path(region(data,rid)['projector_points']))
    elif r['type']=='frame' and r.get('border_width'):
        stroke=QPainterPathStroker();stroke.setWidth(2*r['border_width']);shape=stroke.createStroke(shape).intersected(shape)
    return shape

def draw_origin(p,data):
    point=origin_point(data)
    if point is None:return
    x,y=point;p.setOpacity(1);p.setPen(QPen(QColor('#00ffff'),1.5));p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(x-9,y),QPointF(x+9,y));p.drawLine(QPointF(x,y-9),QPointF(x,y+9));p.drawText(QPointF(x+12,y-9),'0,0')
def uv_transform(pts):
    tr=QTransform()
    if not QTransform.quadToQuad(polygon([[0,0],[1,0],[1,1],[0,1]]),polygon(pts),tr): return QTransform()
    return tr

def eye(p,tr,x,y,rx,ry,color):
    poly=[tr.map(QPointF(x+rx*math.cos(i*TAU/48),y+ry*math.sin(i*TAU/48))) for i in range(48)]
    p.setPen(Qt.NoPen);p.setBrush(QColor(color));p.drawPolygon(QPolygonF(poly))

_sprites={}

def sprite(kind):
    if kind not in _sprites:
        im=QImage(str(ROOT/'assets'/(kind+'.png')))
        if im.isNull():raise RuntimeError(f'assets/{kind}.png is missing. Install the complete application.')
        _sprites[kind]=im
    return _sprites[kind]

def ghost(p,x,y,size,beat,old=False,kind=None):
    kind=kind or ('older-wraith' if old else 'young-ghost')
    if p.opacity()<.001:return
    im=skeleton_frame(beat*4/TAU) if kind=='young-skeleton' else young_ghost_frame(beat*4/TAU) if kind=='young-ghost' else sprite(kind)
    p.save();base=p.opacity();p.translate(x,y)
    tilt=0 if kind=='young-ghost' else .065 if kind=='young-skeleton' else .008 if kind=='young-candle' else .035
    p.rotate(math.degrees(math.sin(beat*(2 if kind=='young-skeleton' else .5))*tilt))
    width=size*1.1;height=width*im.height()/im.width();segments=24
    for i in range(segments):
        src_y=i*im.height()/segments;src_h=im.height()/segments
        amplitude=0 if kind=='young-ghost' else .007 if kind=='young-candle' else .015 if kind=='young-skeleton' else .035
        offset=math.sin(beat+i*.45)*(i/segments)**1.6*width*amplitude
        target=QRectF(-width/2+offset,-height*.45+i*height/segments,width,height/segments+.2)
        source=QRectF(0,src_y,im.width(),src_h+.5)
        local_alpha=1
        if kind=='young-candle' and i<7:local_alpha=.75+.25*math.sin(beat*3+i*.2)**2
        p.setOpacity(base*local_alpha);p.drawImage(target,im,source)
        # Optical high-contrast lift: brighten the sprite without lifting black.
        p.setCompositionMode(QPainter.CompositionMode_Screen);p.setOpacity(base*local_alpha*.65);p.drawImage(target,im,source);p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    p.restore()

def fly(p,shape,b,t,actor,old=False,opacity=1,kind=None,slot=None):
    # House-specific sweeping routes: cross the wall between windows, rise
    # towards the gable, then swoop down. Surface masks occlude the performers.
    if opacity<.001 or p.opacity()<.001:return
    kind=kind or ('older-wraith' if old else 'young-ghost')
    if slot is not None:
        rect,_=performer_pose(slot,t)
        actor_image=young_ghost_frame(t) if kind=='young-ghost' else sprite(kind)
        ratio=actor_image.height()/actor_image.width()
        width=min(rect.width(),rect.height()/ratio);height=width*ratio
        x,y=rect.center().x(),rect.center().y()-.05*height
    else:
        ratio=sprite(kind).height()/sprite(kind).width();route=flight_route(shape,b,ratio,old,7)
        if route is None:return
        x,y,width=flight_position(route,t,actor)
    p.save();p.setOpacity(p.opacity()*opacity);p.setClipPath(shape,Qt.IntersectClip)
    ghost(p,x,y,width/1.1,TAU*t/4+actor,old,kind)
    p.restore()

def stars(p,b,t,count,color):
    p.save();base=p.opacity();p.setPen(Qt.NoPen);p.setBrush(QColor(color))
    for i in range(count):
        period=[6,8,10,12,15][i%5];v=(rnd(i+31)+t/period)%1
        x=b.x()+b.width()*(.5+.43*math.sin(TAU*v+i*.9));y=b.y()+(.12+.80*v)*b.height()
        p.setOpacity(base*math.sin(math.pi*v)**2*(.45+.3*math.sin(TAU*t/4+i)**2));rad=1.6+2*rnd(i+99)
        p.drawEllipse(QPointF(x,y),rad,rad)
        p.setPen(QPen(QColor(color),max(.5,rad*.4)))
        p.drawLine(QPointF(x,y),QPointF(x-5*math.cos(TAU*v+i*.9),y-7))
        p.setPen(Qt.NoPen)
    p.restore()

def smoke(p,b,t,alpha):
    if alpha<.001:return
    # Bright local wisps on black; the flow and its envelope repeat over 120 s.
    p.save();base=p.opacity();p.setCompositionMode(QPainter.CompositionMode_Screen)
    for i in range(7):
        phase=TAU*t/[12,15,20][i%3]+i*.9
        x=b.x()+b.width()*(.42+.19*math.sin(phase));y=b.y()+b.height()*(.43+.10*math.cos(phase*.0+TAU*t/20+i))
        radius=b.width()*(.065+.018*(.5+.5*math.sin(TAU*t/10+i)))
        fog=QRadialGradient(QPointF(x,y),radius);fog.setColorAt(0,QColor(235,241,255,125));fog.setColorAt(.45,QColor(193,215,245,62));fog.setColorAt(1,QColor(183,207,239,0));p.setOpacity(base*alpha);p.fillRect(QRectF(x-radius,y-radius,2*radius,2*radius),fog)
    p.restore()

_leaf=None

def living_tree(p,b,t,strength,breathing=False):
    global _leaf
    if strength<=0:return
    if breathing:
        tex=texture('camouflage-net');breath=.5-.5*math.cos(TAU*t/12)
        p.save();p.setOpacity(p.opacity()*min(1,strength*(1.25+.7*breath)))
        p.translate(b.center());p.scale(.92+.16*breath,.92+.16*breath);p.translate(-b.center())
        # Overscan keeps the shrinking texture covered right up to the soft mask.
        paint_box=b.adjusted(-b.width()*.12,-b.height()*.12,b.width()*.12,b.height()*.12)
        for layer in range(2):
            p.setOpacity(strength*(.75 if layer else 1.2)*(.7+.3*breath))
            for row in range(math.floor(paint_box.top()),math.ceil(paint_box.bottom()),22):
                dx=12*math.sin(TAU*t/20+row*.013+layer*1.9);dy=8*math.cos(TAU*t/30+layer)
                p.drawTiledPixmap(QRectF(paint_box.x(),row,paint_box.width(),22),tex,QPointF(paint_box.x()-dx+layer*130,row-dy))
        p.restore();return
    if _leaf is None:
        _leaf=QPixmap(str(ROOT/'assets/tree-pattern.png'))
        if _leaf.isNull():raise RuntimeError('assets/tree-pattern.png is missing.')
        _leaf=_leaf.scaled(132,132,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    p.save();p.setOpacity(p.opacity()*strength)
    rows=math.ceil(b.height()/10)
    for i in range(rows):
        y=b.y()+i*10;flow=TAU*t/30+i*.18
        dx=2.1*math.sin(flow)+.6*math.sin(TAU*t/40+i*.12);dy=.8*math.sin(TAU*t/60+i*.13)
        p.drawTiledPixmap(QRectF(b.x(),y,b.width(),min(10,b.bottom()-y)),_leaf,QPointF(b.x()-dx,y-dy))
    p.restore()

def draw_tree(p,data,r,t):
    """Feather the foreground and its blackout together, preserving leaf detail."""
    shape=path(r['projector_points']);b=box(r['projector_points'])
    # A soft tree texture must never act as a translucent wall blackout.
    # The physical foreground blocks the wall completely, including its edge.
    p.save();p.setOpacity(1);p.fillPath(shape,Qt.black);p.restore()
    from .atmosphere import inset
    effect_shape=inset(shape,r.get('effect_inset',0))
    mask,rect=feather_mask(effect_shape,24,opaque_interior=True)
    layer=QImage(rect.size(),QImage.Format_ARGB32_Premultiplied);layer.fill(Qt.black)
    q=QPainter(layer);q.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
    q.translate(-rect.x(),-rect.y());q.setOpacity(r.get('gain',1)*.35)
    effects=data.get('effects',{})
    if r.get('enabled',True):
        living_tree(q,b,t,effects.get('tree_strength',.22)*.35,effects.get('tree_breathing',False))
        fireflies(q,effect_shape,b,t,12)
    q.resetTransform();q.setOpacity(1)
    q.setCompositionMode(QPainter.CompositionMode_DestinationIn);q.drawImage(0,0,mask);q.end()
    p.save();p.setOpacity(1);p.drawImage(rect.topLeft(),layer);p.restore()

def lightning(p,b,t,strength):
    # One crisp, seeded branched discharge with a short secondary flash.
    starts=[8,24,39,55,70,87,103,115]
    elapsed=min(((t-start)%120,i) for i,start in enumerate(starts))
    age,index=elapsed
    if age>.9 or strength<=0:return
    pulse=(math.exp(-age/.075) if age<.35 else 0)
    if .17<=age<.5:pulse+=.70*math.exp(-(age-.17)/.065)
    pulse=min(1,pulse)*strength
    after=math.exp(-age/.24)*strength*.25
    trunk=QPainterPath();x=b.x()+b.width()*(.43+.10*rnd(index+72));y=b.y()+b.height()*.15;trunk.moveTo(x,y);branches=[]
    for j in range(19):
        x+=b.width()*(rnd(index*60+j)-.5)*.052;y+=b.height()*.026;trunk.lineTo(x,y)
        if j in [3,7,12,15]:
            q=QPainterPath();q.moveTo(x,y);bx,by=x,y;direction=-1 if rnd(j+index)>.5 else 1
            for k in range(5):
                bx+=direction*b.width()*(.016+.020*rnd(j*30+k));by+=b.height()*(.008+.012*rnd(k+index));q.lineTo(bx,by)
            branches.append(q)
    p.save();base=p.opacity()
    if pulse>.003:
        glow=QRadialGradient(QPointF(b.x()+b.width()*.5,b.y()+b.height()*.45),b.width()*.7)
        glow.setColorAt(0,QColor(163,184,255,160));glow.setColorAt(1,QColor(80,106,179,0));p.setOpacity(base*pulse);p.fillRect(b,glow)
    p.setOpacity(base*max(pulse,after));p.setBrush(Qt.NoBrush)
    for width,color in [(9,QColor(117,120,255,28)),(4,QColor(147,170,255,95)),(2,QColor('#ffffff'))]:
        p.setPen(QPen(color,width));p.drawPath(trunk)
        p.setPen(QPen(color,max(.6,width*.6)))
        for branch in branches:p.drawPath(branch)
    p.restore()

def glass_mask(data):
    mask=QPainterPath()
    for r in data['regions']:
        if r['type']!='window' or (r['id']!='attic' and r.get('paper_screen',False)):continue
        hole=path(r['projector_points'])
        for q in data['regions']:
            if q['type']=='curtain' and q.get('enabled',True) and q.get('parent')==r['id']:
                hole=hole.subtracted(path(q['projector_points']))
            if q['type']=='frame' and q.get('parent')==r['id']:
                hole=hole.subtracted(surface_path(data,q))
        mask=mask.united(hole)
    # A foreground tree intercepts the ray before it could reach the glass.
    for r in data['regions']:
        if r['type']=='occluder':mask=mask.subtracted(path(r['projector_points']))
    return mask

def excluded_surfaces(data):
    mask=QPainterPath()
    for r in data['regions']:
        if not r.get('projection_excluded',False) or r['id']=='right-sill':continue
        bay_front=next((e for e in data.get('exclusions',[]) if e['id']=='exclusion-bay-front'),None)
        # The linked front mask starts at the lower fascia corners. The old
        # hidden bay outline also covered brickwork above the fascia.
        hole=path((bay_front if r['id']=='bay' and bay_front else r)['projector_points'])
        for rid in r.get('projection_allow_ids',[]):
            hole=hole.subtracted(surface_path(data,region(data,rid)))
        if r['id']=='left':
            for tree in data['regions']:
                if tree['type']=='occluder':hole=hole.subtracted(path(tree['projector_points']))
        mask=mask.united(hole)
    return mask

def facade_shape(data,r,margin=0):
    shape=path(r['projector_points'])
    if margin:shape=outset(shape,margin)
    for rid in r.get('cutout_ids',[]):shape=shape.subtracted(path(region(data,rid)['projector_points']))
    has_bay_front=any(e['id']=='exclusion-bay-front' for e in data.get('exclusions',[]))
    for q in data['regions']:
        # Smoke may meet the fascia; subtracting it here feathers a needless
        # black band into the brickwork above it. Its own glow is drawn later.
        if (q['type'] in ('window','frame','stage') and not q['id'].startswith('bay-trim')) or (q['id']=='bay' and not has_bay_front):shape=shape.subtracted(surface_path(data,q))
        if q['type']=='occluder':shape=shape.subtracted(outset(path(q['projector_points']),3))
    return shape

def figure_shape(data,shape):
    """Glass/foreground and the sill constrain actors, independently of smoke."""
    for r in data['regions']:
        if r['type']=='occluder' or r['id']=='right-sill' or r['id'].startswith('bay-trim') or r.get('figures_excluded',False):
            shape=shape.subtracted(path(r['projector_points']))
    for exclusion in data.get('exclusions',[]):
        if not exclusion.get('enabled',True):continue
        forbidden=path(exclusion['projector_points'])
        if exclusion['id']=='exclusion-roof-inner':forbidden=outset(forbidden,3)
        shape=shape.subtracted(forbidden)
    # Use the same final material masks that are applied after all painting.
    # A planned performer must fit before that final masking pass, too.
    return shape.subtracted(glass_mask(data)).subtracted(excluded_surfaces(data))

def facade_cast(data):
    facade=region(data,'facade');safe=figure_shape(data,facade_shape(data,facade))
    specs=[(144,144,3,4,0)]
    return safe,performance_slots(safe,box(facade['projector_points']),specs)

def render(data,t=0,mode='wireframe',selected=None):
    if mode in SHOW_SCENES:return render_show(data,t,mode)
    return render_scene(data,t,mode,selected)

def render_scene(data,t=0,mode='wireframe',selected=None,actor_strength=1):
    """Render a native-resolution QImage; nothing from the editor enters output."""
    im=QImage(WIDTH,HEIGHT,QImage.Format_RGB32);im.fill(Qt.black)
    p=QPainter(im);p.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
    if mode=='black':p.end();return im
    if mode=='mapping':
        for r in sorted(alignment_shapes(data),key=lambda r:r['id']==selected):
            p.setPen(QPen(QColor('#56eaff' if r['id']==selected else '#ffffff'),2 if r['id']==selected else 1))
            p.setBrush(Qt.NoBrush);p.drawPath(surface_path(data,r))
            p.setBrush(QColor('#56eaff' if r['id']==selected else '#ffffff'))
            for x,y in r['projector_points']:p.drawEllipse(QPointF(x,y),2,2)
        p.end();return im
    if mode=='alignment':
        p.setPen(QPen(Qt.white,2));p.setBrush(Qt.NoBrush)
        for rid in ('attic','right'):
            frame=next((r for r in data['regions'] if r['id']=='frame-'+rid),region(data,rid))
            p.drawPath(path(frame['projector_points']))
        roof=region(data,'roof')['projector_points']
        p.drawPolyline(polygon(roof[:3] if len(roof)==6 else roof))
        p.end();return im
    debug=mode in ('wireframe','fills','selected')
    visible={r['id'] for r in alignment_shapes(data)} if mode=='wireframe' else None
    t=t%120;old=mode in OLD;beat=TAU*t/4
    for r in data['regions']:
        if r.get('role')=='group' and mode!='selected':continue
        if debug:
            if visible is not None and r['id'] not in visible:continue
            if mode=='selected' and r['id']!=selected:continue
            col=QColor(r['color']);p.setOpacity(1);p.setPen(QPen(col,2 if r['id']!=selected else 3))
            p.setBrush(Qt.NoBrush)
            if mode in ('fills','selected') and r['type']!='window':
                fill=QColor(col);fill.setAlpha(55);p.setBrush(fill)
            p.drawPath(surface_path(data,r));continue
        if not r.get('enabled',True) or (r['type']=='window' and (r['id']=='attic' or not r.get('paper_screen',False))):continue
        if r['type']=='occluder':continue
        b=box(r['projector_points']);shape=surface_path(data,r)
        if r['id']=='facade':shape=facade_shape(data,r)
        flight_shape=QPainterPath(shape)
        if r['id']=='facade':flight_shape=figure_shape(data,flight_shape)
        main_painter=p
        paint_shape=shape
        if r['id']=='facade':
            paint_shape=facade_shape(data,r)
            for exclusion in data.get('exclusions',[]):
                if not exclusion.get('enabled',True):continue
                if exclusion['id'] not in r.get('cutout_ids',[]):
                    forbidden=path(exclusion['projector_points'])
                    # Shared roof/wall vertices need the same clearance used
                    # by the final blackout, avoiding coincident-edge booleans.
                    if exclusion['id']=='exclusion-roof-inner':forbidden=outset(forbidden,3)
                    paint_shape=paint_shape.subtracted(forbidden)
            # Fade every wall effect together, including sparks and lightning.
            wall_mask,wall_rect=feather_mask(paint_shape,14,opaque_interior=True)
            wall_layer=QImage(wall_rect.size(),QImage.Format_ARGB32_Premultiplied);wall_layer.fill(Qt.transparent)
            p=QPainter(wall_layer);p.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
            p.translate(-wall_rect.x(),-wall_rect.y())
        p.save();p.setClipPath(paint_shape);gain=r.get('gain',1);p.setOpacity(gain)
        x,y,w,h=b.x(),b.y(),b.width(),b.height()
        if r['id']=='facade':
            cast=facade_cast(data)[1] if mode in {'young','older','moonlight'} else ()
            if old:
                if mode=='older':lightning(p,b,t,data.get('effects',{}).get('lightning_strength',.85))
                reveal=max(cycle(t,s,8,1.2) for s in [0,28,40,68,80,108])
                if mode in {'older','moonlight'} and cast and cast[0] is not None:
                    p.setOpacity(gain*.85*reveal*actor_strength);fly(p,flight_shape,b,t,1,True,kind='older-wraith',slot=cast[0])
            elif mode=='young':
                p.setOpacity(gain*.8);stars(p,b,t,10,'#ffe89a')
        elif r['type']=='edge':
            phase=t%30;a=sum(cycle(t,s,3) for s in [11,41,71,101]);p.setOpacity(gain*a);p.fillRect(QRectF(x+clamp((phase-11)/3)*w-12,y,24,h),QColor('#ba91dd' if old else '#ffca80'))
        elif r['type']=='stage' and mode in {'young','older','moonlight','shadowplay'}:
            # The bottom edge is the feet/support line on the bay platform.
            p.setTransform(uv_transform(r['projector_points']),True)
            dance=math.sin(TAU*t/2);hop=.045*(1-math.cos(TAU*t))
            actor=sprite('older-wraith') if old else skeleton_frame(t)
            source_rect=QRectF(actor.rect()) if old else QRectF(0,100,480,550)
            actor_width=min(.9,.92*source_rect.width()/source_rect.height()*h/max(w,1))
            # Larger side steps and animated joints make the tiny stage readable.
            shift=min(.10,max(0,(1-actor_width)/2-.04))
            p.setOpacity(gain*actor_strength);p.drawImage(QRectF((1-actor_width)/2+shift*dance,.12-hop,actor_width,.84),actor,source_rect)
        elif r['type']=='window' and mode in {'young','older','moonlight'}:
            # Explicit physical-paper mode: map the whole sprite into this quad.
            idx={'attic':0,'left':1,'right':2}.get(r['id'],3);a=max(cycle(t,s+idx*3,14,1.5) for s in [0,30,60,90]);p.setOpacity(gain*a*actor_strength)
            p.setTransform(uv_transform(r['projector_points']),True)
            im_sprite=sprite('older-wraith') if old else young_ghost_frame(t)
            float_y=.012*math.sin(TAU*t/10+idx)
            physical_ratio=im_sprite.width()/im_sprite.height()*h/max(w,1)
            height=min(.90,.76/max(physical_ratio,.01));width=height*physical_ratio
            p.drawImage(QRectF((1-width)/2,(1-height)/2+float_y,width,height),im_sprite)
        elif r['type']=='curtain' and mode in {'older','moonlight','shadowplay'}:
            if any(q['id']==r.get('parent') and q.get('paper_screen',False) for q in data['regions']):p.restore();continue
            idx=0 if r['id']=='curtain-left' else 1 if r['id']=='curtain-r1' else 2;a=max(cycle(t,s+idx*2,7) for s in [2,22,42,62,82,102]);p.setOpacity(gain*a)
            if a>.001:
                tr=uv_transform(r['projector_points']);blink=.32+.68*(.5+.5*math.cos(TAU*t/3+idx));look=.04*math.sin(TAU*t/4)
                for cx in [.28,.72]:
                    eye(p,tr,cx,.4,.14,.17*blink,'#ceff9d' if old else '#ccfaff');eye(p,tr,cx+look,.4,.046,.14*blink,'#050909')
                if not old:
                    pts=[tr.map(QPointF(.5+.18*math.cos(math.pi*i/24),.63+.16*math.sin(math.pi*i/24))) for i in range(25)]
                    p.setPen(QPen(QColor('#a6f5f2'),1.4));p.setBrush(Qt.NoBrush);p.drawPolyline(QPolygonF(pts))
        elif r['id']=='bay':
            a=max(cycle(t,s,4) for s in [25,55,85,115]);p.setOpacity(gain*a);p.setPen(Qt.NoPen);p.setBrush(QColor('#91d8a4' if old else '#ffe0a4'))
            for i in range(5):p.drawEllipse(QPointF(x+((t/4+i*.13)%1)*w,y+h*.5),2,2)
        p.setOpacity(gain);draw_extras(p,data,r,t,mode,paint_shape,b,actor_strength)
        p.restore()
        if r['id']=='facade':
            p.resetTransform();p.setOpacity(1);p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            p.drawImage(0,0,wall_mask);p.end();p=main_painter
            p.save();p.setOpacity(1);p.drawImage(wall_rect.topLeft(),wall_layer);p.restore()
    if not debug:
        # Low warm-white accents establish the real architecture between cues.
        p.setOpacity(data.get('effects',{}).get('architecture_strength',.10));p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor('#fff2dc'),1.8))
        for r in data['regions']:
            if r.get('role')=='group':continue
            if r['id']=='roof' or r.get('shape')=='ellipse':
                glow=surface_path(data,r)
                soft_colour(p,glow,STYLES.get(mode,('', '#fff2dc'))[1])
            elif r['type']=='frame' and r.get('enabled',True):
                p.setOpacity(data.get('effects',{}).get('architecture_strength',.10)*r.get('gain',1));soft_colour(p,surface_path(data,r),'#fff2dc');p.setOpacity(data.get('effects',{}).get('architecture_strength',.10))
        for r in data['regions']:
            if r['type']!='occluder':continue
            draw_tree(p,data,r,t)
        p.setOpacity(1);p.fillPath(glass_mask(data),Qt.black)
        p.fillPath(excluded_surfaces(data),Qt.black)
    for exclusion in data.get('exclusions',[]):
        p.setOpacity(1)
        if debug:
            if mode=='selected' and exclusion['id']!=selected:continue
            p.setPen(QPen(QColor('#ff657b'),1.5,Qt.DashLine));p.setBrush(Qt.NoBrush);p.drawPath(path(exclusion['projector_points']))
        else:
            if not exclusion.get('enabled',True):continue
            forbidden=path(exclusion['projector_points'])
            if exclusion['id']=='exclusion-roof-inner':forbidden=outset(forbidden,3)
            p.fillPath(forbidden,Qt.black)
    if debug:draw_origin(p,data)
    p.end()
    return im if debug else brighten(im,data.get('effects',{}).get('brightness_gain',3))

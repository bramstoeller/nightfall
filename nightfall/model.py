"""Portable projector-pixel map. No Qt needed for loading or validation."""
from __future__ import annotations
import base64, copy, json, math, mimetypes, os, tempfile, sys
from pathlib import Path

SCHEMA = 'nightfall.projector-map'
LEGACY_SCHEMA = 'nachtwerk.projector-map'
WIDTH, HEIGHT = 800, 1280
ROOT = Path(__file__).resolve().parent.parent
if getattr(sys, 'frozen', False):
    _data = Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local')) if sys.platform == 'win32' else Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))
    WORK_ROOT = _data/'Nightfall'
else:
    WORK_ROOT = ROOT

def finite(n):
    return isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n)

def validate(data):
    if data.get('schema') not in (SCHEMA,LEGACY_SCHEMA) or data.get('version') != 1:
        raise ValueError('Unknown mapping format. Open a Nightfall map or web project.')
    out = data.get('output', {})
    if out.get('width') != WIDTH or out.get('height') != HEIGHT or out.get('fps') not in (30,50,60) or out.get('duration') != 120:
        raise ValueError('Output must be 800 × 1280, 30/50/60 fps, 120 seconds.')
    regions = data.get('regions')
    required = {'facade', 'roof', 'attic', 'left', 'right', 'curtain-left', 'curtain-r1', 'curtain-r2', 'bay', 'tree'}
    if not isinstance(regions, list) or not required.issubset({r.get('id') for r in regions}) or len({r.get('id') for r in regions})!=len(regions):
        raise ValueError('The ten required regions are missing or duplicated.')
    types = {'facade':'surface','roof':'edge','attic':'window','left':'window','right':'window', 'curtain-left':'curtain','curtain-r1':'curtain','curtain-r2':'curtain','bay':'surface','tree':'occluder'}
    parents = {'curtain-left':'left','curtain-r1':'right','curtain-r2':'right'}
    for r in regions:
        if r.get('type') != types.get(r['id'],r.get('type')) or r.get('type') not in set(types.values())|{'frame','stage','platform'}:
            raise ValueError('Invalid region type or curtain relationship.')
        if r['id'] in parents and r.get('parent')!=parents[r['id']]:raise ValueError('Invalid curtain parent.')
        if r.get('inner_region') and (r['type']!='frame' or r['inner_region'] not in {q['id'] for q in regions}):raise ValueError('Invalid inner frame contour.')
        if r.get('inner_regions') and (r['type']!='frame' or not isinstance(r['inner_regions'],list) or any(rid not in {q['id'] for q in regions} for rid in r['inner_regions'])):raise ValueError('Invalid frame pane contours.')
        pts = r.get('projector_points')
        if not isinstance(pts,list) or not 3 <= len(pts) <= 200:
            raise ValueError('Each region requires 3–200 points.')
        if any(not isinstance(p,list) or len(p)!=2 or not all(finite(v) for v in p) or not 0<=p[0]<=WIDTH or not 0<=p[1]<=HEIGHT for p in pts):
            raise ValueError('Vertex lies outside the 800×1280 projector output.')
        if r['type'] in ('window','curtain','stage') or r.get('role')=='window-inner':
            if len(pts)!=4: raise ValueError('Window and curtain regions must have four corners.')
            signs=[]
            for i,a in enumerate(pts):
                b,c=pts[(i+1)%4],pts[(i+2)%4]
                cross=(b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
                if abs(cross)<.001: raise ValueError('Window corner is degenerate.')
                signs.append(cross>0)
            if len(set(signs))!=1: raise ValueError('Window edges must not cross.')
        if not finite(r.get('gain',1)) or not 0<=r.get('gain',1)<=1: raise ValueError('Brightness must be between 0 and 1.')
        if 'border_width' in r and (r['type']!='frame' or not finite(r['border_width']) or not 0<r['border_width']<=100):raise ValueError('Frame width must be greater than 0 and at most 100 pixels.')
        if 'paper_screen' in r and (r['type']!='window' or not isinstance(r['paper_screen'],bool)):raise ValueError('Paper screen must be a boolean window setting.')
        color=r.get('color','')
        if not isinstance(color,str) or len(color)!=7 or not color.startswith('#'):
            raise ValueError('Color must use #RRGGBB format.')
        try: int(color[1:],16)
        except ValueError: raise ValueError('Invalid color.') from None
    for a in data.get('alignment',{}).get('anchors',[]):
        p=a.get('point',[])
        if len(p)!=2 or not all(finite(v) for v in p) or not 0<=p[0]<=WIDTH or not 0<=p[1]<=HEIGHT:
            raise ValueError('Invalid alignment anchor.')
    origin=data.get('alignment',{}).get('origin')
    if origin is not None:
        matches=[r for r in regions if r['id']==origin.get('region_id') and r['type']=='window']
        index=origin.get('vertex_index')
        if not matches or type(index) is not int or not 0<=index<4:
            raise ValueError('The origin must refer to an existing window corner.')
    exclusions=data.get('exclusions',[])
    if not isinstance(exclusions,list) or len(exclusions)>20:raise ValueError('Invalid exclusion masks.')
    for exclusion in exclusions:
        if 'enabled' in exclusion and not isinstance(exclusion['enabled'],bool):raise ValueError('Exclusion enabled must be true or false.')
        if not isinstance(exclusion.get('id'),str) or not exclusion['id'].startswith('exclusion-') or exclusion.get('type')!='exclusion':raise ValueError('Invalid exclusion mask type.')
        pts=exclusion.get('projector_points',[])
        if not 3<=len(pts)<=200 or any(not isinstance(p,list) or len(p)!=2 or not all(finite(v) for v in p) or not 0<=p[0]<=WIDTH or not 0<=p[1]<=HEIGHT for p in pts):raise ValueError('Exclusion mask lies outside the projector output.')
    shapes=regions+exclusions;by_id={r['id']:r for r in shapes}
    if len(by_id)!=len(shapes):raise ValueError('Duplicate region ID.')
    for shape in shapes:
        if shape.get('deform_parent') and (shape['deform_parent'] not in by_id or shape['deform_parent']==shape['id']):raise ValueError('Invalid pane/curtain relationship.')
        if any(rid not in by_id or rid==shape['id'] for rid in shape.get('cutout_ids',[])):raise ValueError('Invalid facade cutout.')
        seen={shape['id']};parent=shape.get('parent')
        while parent:
            if parent not in by_id or parent in seen:raise ValueError('Invalid or circular region group.')
            seen.add(parent);parent=by_id[parent].get('parent')
    linked=set()
    for link in data.get('vertex_links',[]):
        members=link.get('members',[])
        if len(members)<2:raise ValueError('A shared vertex requires at least two members.')
        points=[]
        for rid,index in members:
            if rid not in by_id or type(index) is not int or not 0<=index<len(by_id[rid]['projector_points']) or (rid,index) in linked:raise ValueError('Invalid vertex link.')
            linked.add((rid,index));points.append(by_id[rid]['projector_points'][index])
        if any(abs(p[axis]-points[0][axis])>1e-6 for p in points for axis in [0,1]):raise ValueError('Linked vertices must share the same position.')
    if not finite(data.get('effects',{}).get('architecture_strength',.10)) or not 0<=data.get('effects',{}).get('architecture_strength',.10)<=1:raise ValueError('Base illumination must be between 0 and 1.')
    if not finite(data.get('effects',{}).get('tree_strength',.22)) or not 0<=data.get('effects',{}).get('tree_strength',.22)<=1:raise ValueError('Tree strength must be between 0 and 1.')
    if not finite(data.get('effects',{}).get('lightning_strength',.85)) or not 0<=data.get('effects',{}).get('lightning_strength',.85)<=1: raise ValueError('Lightning strength must be between 0 and 1.')
    gain=data.get('effects',{}).get('brightness_gain',3)
    if not finite(gain) or not 1<=gain<=4:raise ValueError('Brightness gain must be between 1 and 4.')
    for name,default in [('white_trim_level',.22),('white_curtain_level',.30),('occupied_ledge_level',.08)]:
        level=data.get('effects',{}).get(name,default)
        if not finite(level) or not 0<=level<=1:raise ValueError('White surface levels must be between 0 and 1.')
    return data

def from_web(web):
    if web.get('schema') not in ('nightfall.mapping','nachtwerk.mapping') or web.get('version')!=1: raise ValueError('Unknown web project.')
    ref,out=web['reference'],web['output'];w,h=ref['width'],ref['height']
    sw,sh=out.get('width',WIDTH),out.get('height',HEIGHT)
    if (sw,sh) not in ((1280,720),(1280,800),(WIDTH,HEIGHT)):raise ValueError('Web map must be 1280×720, 1280×800 or 800×1280.')
    factor=min(WIDTH/sw,HEIGHT/sh)
    k=min(sw/w,sh/h)*out.get('scale',1)*factor
    dx=(WIDTH-w*k)/2+out.get('offsetX',0)*sw*factor;dy=(HEIGHT-h*k)/2+out.get('offsetY',0)*sh*factor
    regs=copy.deepcopy(web['regions'])
    for r in regs:
        r['source_points']=r.pop('points')
        r['projector_points']=[[max(0,min(WIDTH,dx+x*w*k)),max(0,min(HEIGHT,dy+y*h*k))] for x,y in r['source_points']]
    data={'schema':SCHEMA,'version':1,'title':web.get('title','Halloween'),'output':{'width':WIDTH,'height':HEIGHT,'fps':30,'duration':120},'reference':copy.deepcopy(ref),'reference_placement':{'x':dx,'y':dy,'width':w*k,'height':h*k},'regions':regs,'alignment':{'anchors':[]},'setup':{'lens_position':'','tripod':'','zoom':'','focus':'','keystone':'','lens_shift':'','notes':''},'locked':False,'effects':{'lightning_strength':.85,'tree_strength':.22}}
    top=regs[1]['projector_points'][1]
    data['alignment']['anchors']=[{'name':'Roof apex','point':list(top),'color':'#ff8070'}, {'name':'Right roof edge','point':list(regs[1]['projector_points'][2]),'color':'#7fffa8'}, {'name':'Left bay edge','point':list(regs[8]['projector_points'][0]),'color':'#80c8ff'}]
    data['effects']['architecture_strength']=.10
    for r in regs:
        if r['type']=='window':r['paper_screen']=False
    return validate(data)

def default_project():
    return load(ROOT/'examples/house.json')

def load(path):
    data=json.loads(Path(path).read_text(encoding='utf8'))
    data.get('effects',{}).pop('smoke_strength',None)
    # The old lamp-post placeholder is outside the projector coverage.
    # Remove it from imported projects as well as from the shipped example.
    if any(e.get('id')=='exclusion-lamp' for e in data.get('exclusions',[])):
        data['exclusions']=[e for e in data['exclusions'] if e.get('id')!='exclusion-lamp']
        for shape in data.get('regions',[]):
            if 'cutout_ids' in shape:shape['cutout_ids']=[rid for rid in shape['cutout_ids'] if rid!='exclusion-lamp']
        links=[]
        for link in data.get('vertex_links',[]):
            if any(m[0]=='exclusion-lamp' for m in link.get('members',[])):
                link['members']=[m for m in link['members'] if m[0]!='exclusion-lamp']
                if len(link['members'])<2:continue
            links.append(link)
        if 'vertex_links' in data:data['vertex_links']=links
    if data.get('schema')==LEGACY_SCHEMA:data['schema']=SCHEMA
    if data.get('schema') in ('nightfall.mapping','nachtwerk.mapping'): data=from_web(data)
    elif data.get('schema')==SCHEMA and (data.get('output',{}).get('width'),data.get('output',{}).get('height')) in ((1280,720),(1280,800)):
        sw,sh=data['output']['width'],data['output']['height'];factor=min(WIDTH/sw,HEIGHT/sh);dx,dy=(WIDTH-sw*factor)/2,(HEIGHT-sh*factor)/2
        for r in editable_shapes(data):
            r['projector_points']=[[x*factor+dx,y*factor+dy] for x,y in r['projector_points']]
        for anchor in data.get('alignment',{}).get('anchors',[]):
            x,y=anchor['point'];anchor['point']=[x*factor+dx,y*factor+dy]
        if 'reference_placement' in data:
            ref=data['reference_placement'];ref.update(x=ref['x']*factor+dx,y=ref['y']*factor+dy,width=ref['width']*factor,height=ref['height']*factor)
        data['output'].update(width=WIDTH,height=HEIGHT);data['conversion']={'from':[sw,sh],'to':[WIDTH,HEIGHT],'method':'scale-to-fit-and-center','scale':factor,'offset':[dx,dy]}
    # Resolve external references on load so subsequent saves remain portable.
    # Images already embedded in a personal project remain local to that project.
    for settings in [data, *data.get('reference_photos', {}).values()]:
        reference = settings.get('reference', {})
        if reference.get('filename') and not reference.get('dataUrl'):
            image_path = Path(reference['filename'])
            if not image_path.is_absolute():
                image_path = Path(path).resolve().parent/image_path
            if image_path.is_file():
                mime = mimetypes.guess_type(image_path.name)[0] or 'image/png'
                reference['dataUrl'] = 'data:'+mime+';base64,'+base64.b64encode(image_path.read_bytes()).decode('ascii')
    # The attic is always masked, including when opening older saved maps.
    for r in data.get('regions',[]):
        if r.get('id')=='attic':r['paper_screen']=False
    return validate(data)

def save(data,path):
    validate(data);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:
            json.dump(data,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def editable_shapes(data): return data['regions']+data.get('exclusions',[])

def region(data,id): return next(r for r in editable_shapes(data) if r['id']==id)

def origin_point(data):
    """A window corner remains the origin when that window is edited or moved."""
    origin=data.get('alignment',{}).get('origin')
    return list(region(data,origin['region_id'])['projector_points'][origin['vertex_index']]) if origin else None

def invalidate_alignment(data,ids):
    for shape in editable_shapes(data):
        if shape['id'] in ids and shape.get('alignment_status')=='aligned':
            shape['alignment_status']='needs-alignment';shape['uncertain']=True
    if 'calibration' in data:data['calibration']['physical_alignment_verified']=False

def sync_vertices(data,changed):
    """Propagate a changed shared corner without translating its neighbours."""
    changed=list(changed);affected=set()
    for link in data.get('vertex_links',[]):
        members=[tuple(m) for m in link['members']]
        source=next((m for m in changed if m in members),None)
        if source is None:continue
        rid,index=source;p=region(data,rid)['projector_points'][index]
        for other,i in members:
            region(data,other)['projector_points'][i]=list(p);affected.add(other)
    invalidate_alignment(data,affected)

def insert_vertex(data,rid,index,point):
    for child in editable_shapes(data):
        if child.get('parent')==rid and child.get('anchor_vertex',-1)>=index:child['anchor_vertex']+=1
    for link in data.get('vertex_links',[]):
        for member in link['members']:
            if member[0]==rid and member[1]>=index:member[1]+=1
    region(data,rid)['projector_points'].insert(index,point)
    invalidate_alignment(data,{rid})

def delete_vertex(data,rid,index):
    for child in editable_shapes(data):
        if child.get('parent')!=rid or 'anchor_vertex' not in child:continue
        if child['anchor_vertex']==index:child.pop('anchor_vertex')
        elif child['anchor_vertex']>index:child['anchor_vertex']-=1
    for link in data.get('vertex_links',[]):
        link['members']=[m for m in link['members'] if m!=[rid,index]]
        for member in link['members']:
            if member[0]==rid and member[1]>index:member[1]-=1
    data['vertex_links']=[link for link in data.get('vertex_links',[]) if len(link['members'])>=2]
    region(data,rid)['projector_points'].pop(index)
    invalidate_alignment(data,{rid})

def move(data,id,dx,dy):
    ids={id}
    while True:
        expanded=ids|{r['id'] for r in editable_shapes(data) if r.get('parent') in ids or r.get('deform_parent') in ids}
        if expanded==ids:break
        ids=expanded
    pts=[p for r in editable_shapes(data) if r['id'] in ids for p in r['projector_points']]
    dx=max(-min(p[0] for p in pts),min(dx,WIDTH-max(p[0] for p in pts)))
    dy=max(-min(p[1] for p in pts),min(dy,HEIGHT-max(p[1] for p in pts)))
    for r in editable_shapes(data):
        if r['id'] in ids: r['projector_points']=[[x+dx,y+dy] for x,y in r['projector_points']]
    if dx or dy:
        invalidate_alignment(data,ids)
        sync_vertices(data,[(r['id'],i) for r in editable_shapes(data) if r['id'] in ids for i in range(len(r['projector_points']))])
    return data


def transform_all(data,dx=0,dy=0,scale=1,angle=0):
    """Coarse fit before detailed edits; validate all coordinates atomically."""
    if not all(finite(v) for v in [dx,dy,scale,angle]) or scale<=0:raise ValueError('Invalid global transformation.')
    candidate=copy.deepcopy(data);a=math.radians(angle);cs,sn=math.cos(a),math.sin(a)
    cx,cy=origin_point(data) or [WIDTH/2,HEIGHT/2]
    def trans(p):
        x,y=(p[0]-cx)*scale,(p[1]-cy)*scale
        return [cx+dx+cs*x-sn*y,cy+dy+sn*x+cs*y]
    for r in candidate['regions']:r['projector_points']=[trans(p) for p in r['projector_points']]
    for exclusion in candidate.get('exclusions',[]):exclusion['projector_points']=[trans(p) for p in exclusion['projector_points']]
    for anchor in candidate['alignment']['anchors']:anchor['point']=trans(anchor['point'])
    invalidate_alignment(candidate,{r['id'] for r in editable_shapes(candidate)})
    return validate(candidate)

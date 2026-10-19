"""Brighten opaque RGB32 frames without changing RGB ratios at highlight limits."""
import numpy as np

_tables={}
_materials={}


def balance_materials(image,data,mode,t,allow_restart=True):
    """White trim reflects far more than brick: attenuate after wall gain.

    Keep trim fully saturated at a separate light level, and leave
    the occupied bay ledge especially quiet so its performers stay dominant.
    Calibration patterns deliberately bypass this video-only correction.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor,QImage,QPainter,QPainterPath
    from .renderer import surface_path
    from .spectacle import architecture_palette
    regions=data['regions'];effects=data.get('effects',{})
    key=(image.width(),image.height(),tuple((r['id'],r['type'],r.get('enabled',True),
         r.get('border_width'),r.get('shape'),r.get('inner_region'),tuple(r.get('inner_regions',[])),
         tuple(tuple(point) for point in r['projector_points'])) for r in regions))
    if key not in _materials:
        paths={name:QPainterPath() for name in ('trim','ledge','cloth')}
        for r in regions:
            if not r.get('enabled',True) or r.get('role')=='group':continue
            name=('ledge' if r['id'].startswith('bay-trim') else
                  'trim' if r['type'] in {'frame','edge'} or r['id']=='roof-tip' else
                  'cloth' if r['type']=='curtain' else None)
            if name:paths[name]=paths[name].united(surface_path(data,r))
        paths['trim']=paths['trim'].subtracted(paths['ledge'])
        paths['cloth']=paths['cloth'].subtracted(paths['trim']).subtracted(paths['ledge'])
        masks={}
        for name,shape in paths.items():
            mask=QImage(image.size(),QImage.Format_ARGB32_Premultiplied);mask.fill(Qt.transparent)
            p=QPainter(mask);p.setRenderHint(QPainter.Antialiasing);p.fillPath(shape,Qt.white);p.end()
            alpha=np.frombuffer(mask.constBits(),np.uint8).reshape(-1,4)[:,3]
            indices=np.flatnonzero(alpha)
            masks[name]=(indices,alpha[indices].astype(np.float32)[:,None]/255)
        if len(_materials)>=4:_materials.clear()
        _materials[key]=masks
    occupied=float(mode in {'older','pumpkins','owls','bones','spiders','bats','embers','clockwork','electric','cheshire','shadowplay'})
    if mode=='young':
        from .effects import envelope
        local=t%30 if allow_restart else min(t,30-1e-6)
        occupied=max(envelope(local,0,10,30),envelope(local,19,5,30))
    trim=effects.get('white_trim_level',.38)
    levels={'trim':min(1,trim*1.35) if mode in {'waves','haunted'} else trim,
            'ledge':trim+(effects.get('occupied_ledge_level',.16)-trim)*occupied,
            'cloth':effects.get('white_curtain_level',.45)}
    pixels=np.frombuffer(image.bits(),np.uint8).reshape(-1,4)
    fallback=QColor(architecture_palette(mode)[1])
    fallback=np.array([fallback.blue(),fallback.green(),fallback.red()],np.float32)/255
    for name,(indices,coverage) in _materials[key].items():
        if not len(indices):continue
        original=pixels[indices,:3].astype(np.float32)
        target=original
        if name!='cloth':
            peak=original.max(axis=1)[:,None];low=original.min(axis=1)[:,None]
            chroma=peak-low
            # Preserve peak intensity while increasing colour saturation.
            # Neutral pixels take the scene's trim hue instead of dull grey.
            vivid=(original-low)*peak/np.maximum(chroma,1)
            target=np.where(chroma>=np.maximum(1,peak*.05),vivid,peak*fallback)
        target=target*levels[name]
        pixels[indices,:3]=np.rint(original+(target-original)*coverage).clip(0,255).astype(np.uint8)
    return image

def brighten(image,gain):
    if gain<=1:return image
    if gain not in _tables:
        maximum=np.arange(256,dtype=np.uint32)[:,None]
        value=np.arange(256,dtype=np.uint32)[None,:]
        # Integer rounding makes 100/200 * 255 exactly 128, even at half steps.
        limited=(value*255+maximum//2)//np.maximum(maximum,1)
        amplified=np.floor(value*gain+.5)
        table=np.where(maximum*gain>255,limited,amplified)
        channels=np.clip(table,0,255).astype(np.uint8).ravel()
        blue=np.arange(256,dtype=np.uint16)[None,:]
        green=np.arange(256,dtype=np.uint16)[:,None]
        maximum=np.maximum(green,blue)
        # 64MB per gain replaces three strided per-channel frame passes with
        # one native RGB32 lookup. Build in small rows, not huge temporary arrays.
        colours=np.empty(1<<24,np.uint32)
        for red in range(256):
            rows=np.maximum(maximum,red)<<8
            rgb=channels[rows|blue].astype(np.uint32)
            rgb|=channels[rows|green].astype(np.uint32)<<8
            rgb|=channels[rows|red].astype(np.uint32)<<16
            rgb|=0xff000000
            colours[red*65536:(red+1)*65536]=rgb.ravel()
        if len(_tables)>=2:_tables.pop(next(iter(_tables)))
        _tables[gain]=colours
    pixels=np.frombuffer(image.bits(),dtype=np.uint32)
    np.take(_tables[gain],pixels&0xffffff,out=pixels,mode='clip')
    return image

"""Brighten opaque RGB32 frames without changing RGB ratios at highlight limits."""
import numpy as np

_tables={}

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

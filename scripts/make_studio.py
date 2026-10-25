"""Procedural HDR studio illumination. No photographic environment input."""
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[1]
w,h=1024,512
u,v=np.meshgrid((np.arange(w)+.5)/w,(np.arange(h)+.5)/h)
rgb=np.zeros((h,w,3))+np.array([.012,.018,.028])
for uc,vc,su,sv,power,colour in [(0.20,.43,.055,.21,9,[.70,.83,1]),(.72,.43,.07,.18,12,[1,.66,.34]),(.48,.18,.22,.06,6,[.88,.94,1])]:
    du=np.minimum(abs(u-uc),1-abs(u-uc))
    panel=np.exp(-((du/su)**4+((v-vc)/sv)**4))
    rgb+=power*panel[...,None]*np.array(colour)
mantissa,exponent=np.frexp(rgb.max(axis=2))
scale=np.ldexp(np.ones_like(mantissa),8-exponent)
rgbe=np.empty((h,w,4),np.uint8);rgbe[:,:,:3]=np.minimum(rgb*scale[...,None],255).astype(np.uint8);rgbe[:,:,3]=(exponent+128).astype(np.uint8)
with (root/'geometry/studio.hdr').open('wb') as f:
    f.write(f'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {h} +X {w}\n'.encode())
    for row in rgbe:
        f.write(bytes([2,2,w>>8,w&255]))
        for channel in range(4):
            for i in range(0,w,128):
                chunk=row[i:i+128,channel].tobytes();f.write(bytes([len(chunk)]));f.write(chunk)
print(root/'geometry/studio.hdr')

"""Check the completed local film package; fail on missing/blank/cropped media."""
import hashlib,json,subprocess
import os
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
frames=Path(os.environ.get('AUREOLE_RENDER_DIR', str(ROOT/'renders/example')))
expected=[frames/f'Aureole.{i:04d}.png' for i in range(120)]
assert sorted(frames.glob('Aureole.*.png'))==expected, 'Expected exactly frames 0..119'
stats=[];previous=None;hashes=[]
for i,p in enumerate(expected):
    image=Image.open(p).convert('RGB');assert image.size==(1600,900)
    a=np.asarray(image);mask=a.max(2)>20
    y,x=np.where(mask);assert len(x)>15000, f'Blank frame {i}'
    bounds=[int(x.min()),int(y.min()),int(x.max()),int(y.max())]
    assert bounds[0]>4 and bounds[1]>4 and bounds[2]<1595 and bounds[3]<895, f'Clipped frame {i}: {bounds}'
    sample=a[::4,::4].astype(np.float32)
    delta=float(np.abs(sample-previous).mean()) if previous is not None else None
    if delta is not None: assert delta>0.01, f'Duplicate frame {i}'
    stats.append({'frame':i,'bounds':bounds,'mean_rgb':float(a.mean()),'mean_abs_step':delta})
    previous=sample;hashes.append(hashlib.sha256(p.read_bytes()).hexdigest())

movies={}
for name,duration,count in [('clean.mp4',5,120),('reveal.mp4',20,480)]:
    p=ROOT/name
    q=subprocess.run(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=width,height,avg_frame_rate,nb_read_frames,duration','-of','json',str(p)],capture_output=True,text=True,check=True)
    info=json.loads(q.stdout)['streams'][0]
    assert info['width']==1600 and info['height']==900
    assert info['avg_frame_rate']=='24/1' and int(info['nb_read_frames'])==count
    assert abs(float(info['duration'])-duration)<0.001
    subprocess.run(['ffmpeg','-v','error','-i',str(p),'-f','null','-'],check=True,capture_output=True)
    movies[name]={'probe':info,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'full_decode':'PASS'}
for name in ['MATH_CHECK','SEQUENCE_CHECK']:
    assert json.loads((ROOT/f'proof/{name}.json').read_text())['status']=='PASS'
render=json.loads((ROOT/'proof/RENDER_RESULT.json').read_text())
assert render['success'] is True
if (ROOT/'proof/ENGINE_LOG.txt').is_file():
    log=(ROOT/'proof/ENGINE_LOG.txt').read_text()
    assert 'Failed to compile Material' not in log
receipt={'status':'PASS','frames':120,'movies':movies,'frame_checks':stats,'frame_sha256':hashes,'render_seconds':render.get('elapsed_seconds'),'limits':'Media integrity, frame bounds, changing images, mathematical normals and evaluated sequence state verified. No cross-device pixel-identity or physical-simulation claim.'}
if (ROOT/'proof/POST_EXPORT_SHUTDOWN.json').is_file():
    receipt['engine_shutdown']=json.loads((ROOT/'proof/POST_EXPORT_SHUTDOWN.json').read_text())
(ROOT/'VERIFICATION.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({'status':'PASS','frames':120,'movies':list(movies),'render_seconds':receipt['render_seconds']},indent=2))

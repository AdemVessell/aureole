(() => {
  'use strict';
  const $=s=>document.querySelector(s);
  const video=$('#film'), cover=$('#film-cover'), overlay=$('#play-overlay');
  const play=$('#play-film'), replay=$('#replay-film'), timeline=$('#film-time'), clock=$('#film-clock');
  const videoStatus=$('#video-status'), modeLabel=$('#mode-label');
  const manifestState=$('#manifest-state'),equationList=$('#equation-list'),claimValue=$('#claim-value'),receiptState=$('#receipt-state');
  const modeButtons=[...document.querySelectorAll('[data-mode]')];
  const root=new URL(document.body.dataset.assetRoot||'../',location.href);
  const modes={film:{src:'clean.mp4?v=2e865e2f07157cdc',label:'five-second film',duration:5},math:{src:'reveal.mp4?v=a54f760cc9d50e84',label:'math reveal',duration:20}};
  const blobs=new Map();
  let currentMode='film',selection=0,action=0,readyJob=null,loadedMode=null;
  function setStatus(message,kind=''){
    videoStatus.querySelector('span:last-child').textContent=message;
    videoStatus.classList.toggle('is-error',kind==='error');
    videoStatus.classList.toggle('is-hidden',!message||kind==='hidden');
  }
  function update(){
    const duration=modes[currentMode].duration;
    timeline.max=duration;timeline.value=Math.min(video.currentTime||0,duration);
    clock.textContent=`${Number(timeline.value).toFixed(1)} / ${duration.toFixed(1)} s`;
    const atEnd=video.ended;
    play.textContent=atEnd?'Replay':video.paused?'Play':'Pause';
    overlay.querySelector('span:last-child').textContent=atEnd?'Replay film':'Play film';
    overlay.setAttribute('aria-label',atEnd?'Replay film':'Play film');
    overlay.hidden=!(video.paused&&(atEnd||!video.currentTime));
    if(atEnd) cover.hidden=false;
    modeButtons.forEach(b=>{const on=b.dataset.mode===currentMode;b.classList.toggle('is-active',on);b.setAttribute('aria-pressed',String(on));});
    modeLabel.textContent=modes[currentMode].label+' · silent';
  }
  function mediaError(){cover.hidden=false;setStatus('Playback unavailable. Try Replay or download the film below.','error');play.textContent='Retry';overlay.hidden=false;}
  // Complete same-origin downloads avoid relying on byte-range seeking. A
  // content hash also prevents old video chunks surviving a media replacement.
  function ensureVideo(){
    if(loadedMode===currentMode&&video.readyState>=2)return Promise.resolve(true);
    if(readyJob)return readyJob;
    const epoch=selection,name=currentMode;
    setStatus('Loading film…');cover.hidden=false;timeline.disabled=true;
    readyJob=(async()=>{
      if(!blobs.has(name))blobs.set(name,fetch(new URL(modes[name].src,root)).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.blob();}).then(b=>URL.createObjectURL(b)).catch(e=>{blobs.delete(name);throw e;}));
      const url=await blobs.get(name);if(epoch!==selection)return false;
      await new Promise((resolve,reject)=>{
        const cleanup=()=>{clearTimeout(timer);video.removeEventListener('loadeddata',done);video.removeEventListener('error',failed);};
        const done=()=>{cleanup();resolve();};const failed=()=>{cleanup();reject(Error('Media decode failed'));};
        const timer=setTimeout(failed,20000);
        video.addEventListener('loadeddata',done);video.addEventListener('error',failed);
        video.src=url;video.load();
      });
      if(epoch!==selection)return false;
      loadedMode=name;timeline.disabled=false;setStatus('');return true;
    })().finally(()=>{if(epoch===selection)readyJob=null;});
    return readyJob;
  }
  async function activate(time,shouldPlay){
    const request=++action;
    try{
      if(!await ensureVideo()||request!==action)return;
      if(time!==null)video.currentTime=time;
      if(shouldPlay)await video.play();
      else cover.hidden=video.currentTime>0;
      update();
    }catch(e){if(request===action)mediaError();}
  }
  function toggle(){if(!video.paused){++action;video.pause();}else activate(video.ended?0:null,true);}
  function selectMode(mode){
    if(mode===currentMode)return;
    ++selection;++action;readyJob=null;loadedMode=null;video.pause();
    currentMode=mode;video.removeAttribute('src');video.load();
    cover.hidden=false;timeline.disabled=true;setStatus('');update();
  }
  function renderEquations(equations) {
    if (!Array.isArray(equations) || equations.length === 0) return;
    const plainNotation = (value) => String(value)
      .replace(/\\left|\\right/g, '')
      .replace(/\\sqrt\{([^{}]+)\}/g, '√($1)')
      .replace(/\\(?:mathrm|text)\{([^{}]+)\}/g, '$1')
      .replace(/\\sin/g, 'sin').replace(/\\cos/g, 'cos').replace(/\\tan/g, 'tan')
      .replace(/\\cdot/g, '·').replace(/\\times/g, '×').replace(/\\pi/g, 'π')
      .replace(/\\leq?/g, '≤').replace(/\\geq?/g, '≥').replace(/\\infty/g, '∞')
      .replace(/\^\{([^{}]+)\}/g, '^$1').replace(/[{}]/g, '');
    equationList.replaceChildren(...equations.map((equation, index) => {
      const card = document.createElement('article');
      card.className = 'equation-card';
      const indexLine = document.createElement('p');
      indexLine.className = 'card-index';
      indexLine.innerHTML = `${String(index + 1).padStart(2, '0')} <span>equation</span>`;
      const title = document.createElement('h2');
      title.textContent = equation.label || 'Untitled equation';
      const notation = document.createElement('p');
      notation.className = 'notation';
      notation.textContent = plainNotation(equation.latex || 'Notation pending');
      const explanation = document.createElement('p');
      explanation.textContent = equation.explanation || 'No explanation supplied in the render receipt.';
      card.append(indexLine, title, notation, explanation);
      return card;
    }));
    manifestState.textContent = `${equations.length} equation${equations.length === 1 ? '' : 's'} loaded`;
  }

  function applyManifest(manifest) {
    if (!manifest || typeof manifest !== 'object') throw new Error('Invalid SHOT.json');
    if (manifest.title) document.title = `${manifest.title} — equation cinema`;
    if (manifest.title) document.querySelector('#page-title').textContent = manifest.title;
    if (Number.isFinite(manifest.duration)) document.querySelector('#duration-value').textContent = `${manifest.duration.toFixed(1).padStart(4, '0')} s`;
    if (Number.isFinite(manifest.fps)) document.querySelector('#fps-value').textContent = `${manifest.fps} fps`;
    if (Number.isFinite(manifest.width) && Number.isFinite(manifest.height)) document.querySelector('#raster-value').textContent = `${manifest.width} × ${manifest.height}`;
    if (manifest.claim_boundary) claimValue.textContent = manifest.claim_boundary;
    if (manifest.render_description) {
      const description = document.createElement('p');
      description.className = 'render-description';
      description.textContent = manifest.render_description;
      claimValue.insertAdjacentElement('beforebegin', description);
    }
    renderEquations(manifest.equations);
    manifestState.textContent = Array.isArray(manifest.equations) && manifest.equations.length ? `${manifest.equations.length} equations loaded` : 'Receipt loaded · no equations listed';
    receiptState.textContent = manifest.verification?.status ? `Receipt: ${manifest.verification.status}` : 'Render receipt loaded';
  }


  overlay.addEventListener('click',toggle);play.addEventListener('click',toggle);
  replay.addEventListener('click',()=>activate(0,true));
  modeButtons.forEach(b=>b.addEventListener('click',()=>selectMode(b.dataset.mode)));
  timeline.addEventListener('input',()=>{const t=Number(timeline.value);video.pause();activate(t,false);});
  $('#fullscreen-film').addEventListener('click',()=>{
    if(video.webkitEnterFullscreen){video.webkitEnterFullscreen();return;}
    const frame=$('.screen');
    if(document.fullscreenElement)document.exitFullscreen();
    else frame.requestFullscreen?.().catch(()=>setStatus('Use the download link to watch full screen.'));
  });
  video.addEventListener('playing',()=>{cover.hidden=true;setStatus('');update();});
  video.addEventListener('pause',update);video.addEventListener('timeupdate',update);
  video.addEventListener('seeked',()=>{cover.hidden=video.currentTime>0&&!video.ended;update();});
  video.addEventListener('ended',()=>{cover.hidden=false;setStatus('');update();});
  video.addEventListener('error',()=>{if(video.getAttribute('src'))mediaError();});
  document.addEventListener('keydown',e=>{
    if(e.target.matches('input,textarea,select,button,a,[contenteditable="true"]'))return;
    if(e.key===' '){e.preventDefault();toggle();}
    if(e.key.toLowerCase()==='r')activate(0,true);
    if(e.key==='1')selectMode('film');if(e.key==='2')selectMode('math');
  });
  fetch(new URL('SHOT.json',root),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Missing manifest');return r.json();}).then(applyManifest).catch(()=>{manifestState.textContent='Equations unavailable';receiptState.textContent='Source remains available below';});
  update();
})();

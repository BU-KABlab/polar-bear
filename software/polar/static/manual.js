'use strict';

async function manualReview(rid) {
 const j=state.job, r=j.results.find(x=>x.id===rid);
 let sources;
 try {sources=(await api(`/api/jobs/${j.id}/manual-sources/${rid}`)).sources;}
 catch(e){toast(e.message);return;}
 if(!sources.length){toast('No source image with a readable height belongs to this result. Check the filename settings.');return;}
 showDialog(`Manual LED pairs · ${r.label}`,`
  <p class="field-help">Choose the best-focused image. Click the center of one LED reflection, then its opposite reflection to draw a line. Drag endpoints to refine them. Mark up to 12 distinct opposite pairs.</p>
  <label>Source image<select id="manual-source">${sources.map(s=>`<option value="${esc(s.file_id)}">Z ${fmt(s.zg)} mm · ${esc(s.filename)}</option>`).join('')}</select></label>
  <div class="manual-toolbar"><label>Zoom<select id="manual-zoom"><option value="1">Fit</option><option value="2">2×</option><option value="4">4×</option><option value="8">8×</option></select></label><button class="button secondary" id="manual-undo">Undo endpoint</button><button class="button secondary" id="manual-clear">Clear lines</button><button class="button secondary" id="manual-back">Back to review</button></div>
  <div class="manual-image-wrap" id="manual-image-wrap"><canvas id="manual-canvas" aria-label="Draw opposite LED pair endpoints on the original image"></canvas></div>
  <p id="manual-count" class="field-help" role="status"></p><div id="manual-distances" class="manual-distances"></div>
  <p class="field-help">Distances use original pixels at every zoom level. One pair gives an angle only; at least two are needed for directional SD and combined error. Manual placement error is not included. Changing the source clears unsaved lines.</p>
  <p id="manual-message" class="inline-warning" role="status"></p>
  <button id="manual-save" class="button primary full" disabled>${j.settings.mode==='outline'?'Save pairs & fit outline':'Calculate & save manual measurement'}</button>`);
 const canvas=$('manual-canvas'),ctx=canvas.getContext('2d'),wrap=$('manual-image-wrap');
 let img=null, points=[],drag=-1,revision=0,baseWidth=1,saving=false;
 const selected=sources.find(s=>s.stored===r.stored)||sources.find(s=>s.filename.includes('after_dispense'))||sources[0];
 $('manual-source').value=selected.file_id;
 function controls(){
  const n=Math.floor(points.length/2),pending=points.length%2;
  $('manual-count').textContent=`${n} / 12 pairs${pending?' · click the opposite LED to finish this line.':' · click an LED to start the next pair.'}`;
  $('manual-save').disabled=saving||!img||pending||n<(j.settings.mode==='outline'?2:1);
  $('manual-distances').textContent=Array.from({length:n},(_,i)=>`Pair ${i+1}: ${fmt(Math.hypot(points[2*i][0]-points[2*i+1][0],points[2*i][1]-points[2*i+1][1]),2)} px`).join(' · ');
 }
 function draw(){
  if(!img)return;
  ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0);
  const unit=canvas.width/(baseWidth*Number($('manual-zoom').value));
  ctx.lineWidth=1.5*unit;ctx.font=`${12*unit}px Arial`;ctx.strokeStyle='#00d8bd';ctx.fillStyle='#ffd16e';
  for(let i=0;i<points.length;i++){
   const [x,y]=points[i];ctx.beginPath();ctx.arc(x,y,4*unit,0,2*Math.PI);ctx.stroke();
   if(i%2){const a=points[i-1];ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(x,y);ctx.stroke();ctx.fillText(String((i+1)/2),(a[0]+x)/2+4*unit,(a[1]+y)/2-4*unit);}
  }
  controls();
 }
 function zoom(){if(!img)return;canvas.style.width=`${baseWidth*Number($('manual-zoom').value)}px`;draw();}
 async function loadSource(){
  const ticket=++revision;img=null;points=[];controls();canvas.width=1;canvas.height=1;$('manual-message').textContent='Loading original image…';
  try {
   const blob=await api(`/api/jobs/${j.id}/manual-image/${rid}/${$('manual-source').value}`,{blob:true});
   if(ticket!==revision||!canvas.isConnected)return;
   const url=URL.createObjectURL(blob),next=new Image();
   next.onload=()=>{URL.revokeObjectURL(url);if(ticket!==revision||!canvas.isConnected)return;img=next;canvas.width=next.naturalWidth;canvas.height=next.naturalHeight;baseWidth=Math.min(next.naturalWidth,wrap.clientWidth-2);
    if(sources.find(s=>s.file_id===$('manual-source').value)?.stored===r.stored&&r.manual_pairs)points=r.manual_pairs.flat().map(p=>[...p]);
    $('manual-message').textContent='';zoom();};
   next.onerror=()=>{URL.revokeObjectURL(url);if(ticket===revision)$('manual-message').textContent='Cannot display this image.';};next.src=url;
  }catch(e){if(ticket===revision)$('manual-message').textContent=e.message;}
 }
 function at(e){const b=canvas.getBoundingClientRect();return [Math.max(0,Math.min(canvas.width-1,(e.clientX-b.left)/b.width*canvas.width)),Math.max(0,Math.min(canvas.height-1,(e.clientY-b.top)/b.height*canvas.height))];}
 canvas.onpointerdown=e=>{
  if(!img||saving)return;e.preventDefault();const p=at(e),scale=canvas.getBoundingClientRect().width/canvas.width;
  drag=points.findIndex(q=>Math.hypot(q[0]-p[0],q[1]-p[1])*scale<8);
  if(drag<0){if(points.length>=24)return;points.push(p);drag=points.length-1;}
  canvas.setPointerCapture(e.pointerId);draw();
 };
 canvas.onpointermove=e=>{if(drag>=0&&!saving){points[drag]=at(e);draw();}};
 canvas.onpointerup=canvas.onpointercancel=()=>{drag=-1;};
 $('manual-zoom').onchange=zoom;
 $('manual-undo').onclick=()=>{points.pop();draw();};
 $('manual-clear').onclick=()=>{points=[];draw();};
 $('manual-source').onchange=loadSource;
 $('manual-back').onclick=()=>{revision++;review(rid);};
 $('manual-save').onclick=async()=>{
  saving=true;controls();['manual-source','manual-undo','manual-clear','manual-back'].forEach(id=>$(id).disabled=true);
  const pairs=Array.from({length:points.length/2},(_,i)=>[points[2*i],points[2*i+1]]);
  try {
   const result=await post(`/api/jobs/${j.id}/manual-pairs/${rid}`,{file_id:$('manual-source').value,pairs});
   Object.keys(r).forEach(k=>delete r[k]);Object.assign(r,result);renderResults();refreshHistory();revision++;await review(rid);
  }catch(e){if($('manual-message')){$('manual-message').textContent=e.message;saving=false;['manual-source','manual-undo','manual-clear','manual-back'].forEach(id=>$(id).disabled=false);controls();}}
 };
 await loadSource();
}

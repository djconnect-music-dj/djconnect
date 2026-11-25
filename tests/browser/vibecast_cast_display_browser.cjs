/* Real browser composition against declared fixture wires and a synthetic CAF
 * channel. Does not qualify actual HA, Google's SDK or physical TV acceptance. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium,webkit}=require(process.env.DJC_PLAYWRIGHT);
const root=path.resolve(__dirname,'../..');
const html=fs.readFileSync(process.argv[2],'utf8');
const output=process.argv[3];fs.mkdirSync(output,{recursive:true});
const receiver='https://receiver.djconnect.dev',ha='https://ha.example.net';
const id='a'.repeat(32),cap='djccb_'+'S'.repeat(43),grant='djcd_'+'G'.repeat(43);
const binding={issuer_epoch:'E'.repeat(43),display_id:'D'.repeat(43),share_id:'H'.repeat(43),share_generation:1,session_id:'declared-render-fixture-session'};
const sdk=`(()=>{let ready=false,receive;const callbacks={};window.__cafSent=[];window.__cafReceive=(data,senderId='declared-sdk-sender')=>receive({data,senderId});
window.cast={framework:{CastReceiverContext:{getInstance:()=>({isSystemReady:()=>ready,addEventListener(t,cb){callbacks[t]=cb;},addCustomMessageListener(ns,cb){receive=cb;},sendCustomMessage(ns,sender,data){window.__cafSent.push({sender,data});},start(options){window.__cafOptions=options;setTimeout(()=>{ready=true;callbacks.ready?.();},0);}})},system:{EventType:{READY:'ready',SENDER_DISCONNECTED:'disconnected'},MessageType:{JSON:'JSON'}}}};})();`;
async function run(name,engine){
 const browser=await engine.launch({headless:true,...(engine===chromium?(process.env.DJC_CHROMIUM_EXECUTABLE?{executablePath:process.env.DJC_CHROMIUM_EXECUTABLE}:{channel:"chromium"}):{})});
 const page=await browser.newPage({viewport:{width:1920,height:1080},reducedMotion:'reduce',locale:'nl-NL'});
 await page.addInitScript(()=>{
  window.__castStorageAccesses=0;
  Object.defineProperty(window,'localStorage',{get(){
   window.__castStorageAccesses++;
   throw new Error('Cast receiver must not access local storage');
  }});
 });
 const errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(7000);
 let claimCalls=0,collectCalls=0,leaveCalls=0,approved=false,socket,preflights=0;
 const calls=[];
 const cors={'Access-Control-Allow-Origin':receiver,'Access-Control-Allow-Methods':'POST','Access-Control-Allow-Headers':'Content-Type, Authorization','Vary':'Origin','Cache-Control':'no-store'};
 await page.route('https://www.gstatic.com/**',r=>r.fulfill({body:sdk,contentType:'application/javascript'}));
 await page.route(receiver+'/**',r=>r.fulfill({body:html,contentType:'text/html'}));
 await page.route(ha+'/**',async route=>{
  const request=route.request(),url=new URL(request.url());calls.push(url.pathname);
  assert.ok(url.pathname.startsWith('/api/djconnect/v1/cast/'));
  if(request.method()==='OPTIONS'){preflights++;return route.fulfill({status:204,headers:cors});}
  assert.equal(request.headers().origin,receiver);
  const body=request.postDataJSON();assert.equal(body.contract_version,1);
  const endpoint=url.pathname.split('/').at(-1);
  const respond=json=>route.fulfill({json,headers:cors});
  if(endpoint==='claim'){
   claimCalls++;assert.equal(request.headers().authorization,'Bearer '+cap);
   assert.deepEqual(Object.keys(body).sort(),['browser_nonce','contract_version']);
   assert.match(body.browser_nonce,/^[A-Za-z0-9_-]{43}$/);
   return respond({success:true,contract_version:1,issuer_epoch:binding.issuer_epoch,claim_id:'C'.repeat(43),claim_secret:'Q'.repeat(43),browser_generation:'B'.repeat(43),code:'123456',expires_in:120,expires_at:new Date(Date.now()+120000).toISOString()});
  }
  if(endpoint==='collect'){
   collectCalls++;assert.equal(body.claim_secret,'Q'.repeat(43));
   if(!approved)return respond({success:true,contract_version:1,state:'pending'});
   return respond({success:true,contract_version:1,state:'admitted',...binding,grant_token:grant,
    lease_revision:0,lease_expires_in:60,share_expires_in:14400,session_locale:'nl',capabilities:{view_display:true,owner_controls:false,session_end:false}});
  }
  if(endpoint==='cancel')return respond({success:true,contract_version:1});
  assert.equal(request.headers().authorization,'Bearer '+grant);
  if(endpoint==='focus')return respond({success:true,contract_version:1,focused_moment_id:null,expires_in:0,live_enabled:true,guest_count:0});
  if(endpoint==='invitation'){
   const svg='<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" fill="white"/><path d="M8 8h32v32H8zM88 8h32v32H88zM8 88h32v32H8z" fill="black"/></svg>';
   return respond({success:true,contract_version:1,invitation_id:'declared-render-only-fixture',expires_in:30,
    manual_code:'ABCD-EFGH-JKLM',manual_origin:ha,qr_data_uri:'data:image/svg+xml;base64,'+Buffer.from(svg).toString('base64')});
  }
  if(endpoint==='leave'){leaveCalls++;return respond({success:true,contract_version:1});}
  throw new Error('Unexpected endpoint '+endpoint);
 });
 await page.routeWebSocket('wss://ha.example.net/api/djconnect/v1/cast/live',ws=>{socket=ws;ws.onMessage(raw=>{
  const auth=JSON.parse(raw);assert.equal(auth.grant_token,grant);assert.equal(auth.display_id,binding.display_id);
  ws.send(JSON.stringify({type:'snapshot',contract_version:1,connection_generation:3,snapshot:{contract_version:1,...binding,
   session:{session_id:binding.session_id,runtime_state:'active',locale:'nl'},session_presentation:{mood:'calm',persona:'relaxed',presence:'soft'},
   view:{mode:'flow',revision:0,dynamics:.5},
   playback:{state:'playing',item_id:'declared-fixture-track',title:'Declared fixture recording',artist:'Declared fixture performer',duration_ms:240000,position_ms:210000},
   horizon_preview:{current_item_id:'declared-fixture-track',expires_at:new Date(Date.now()+20000).toISOString(),
    text:'Hierna staat het volgende nummer klaar.',track:{item_id:'declared-next',title:'Declared next recording',
     artist:'Declared next performer',source_url:'https://open.spotify.com/track/'+'A'.repeat(22)}},
   shared_flow:[{moment_id:'declared-fixture-moment',type:'track',content:'Declared software renderer contribution.',playback_item_id:'declared-fixture-track',flow_expires_at:new Date(Date.now()+30000).toISOString(),display_expires_at:new Date(Date.now()-1000).toISOString()}],dj_moments:[]}}));
 });});
 try{
  await page.goto(receiver+'/');await page.waitForFunction(()=>typeof window.__cafReceive==='function');
  async function verifyIdleLayout(hasCode){
   for(const [width,height] of [[960,540],[1280,720],[1920,1080]]){
    await page.setViewportSize({width,height});
    const waiting=await page.locator('.waiting-status').boundingBox();
    const stage=await page.locator('.stage').boundingBox();
    const footer=await page.locator('.renderer-footer').boundingBox();
    const brand=await page.locator('.waiting-brand').boundingBox();
    const handoff=await page.locator('#handoff').boundingBox();
    assert.equal(Boolean(handoff),hasCode);
    assert.ok(waiting.y>=brand.y+brand.height);
    if(handoff)assert.ok(waiting.y>=handoff.y+handoff.height);
    assert.ok(waiting.y+waiting.height<=stage.y+stage.height+1,`Waiting row clipped at ${width}x${height}`);
    assert.ok(waiting.y+waiting.height<footer.y);
    assert.equal(await page.locator('.renderer-footer').evaluate(node=>getComputedStyle(node).backgroundColor),'rgba(0, 0, 0, 0)');
   }
   await page.screenshot({path:path.join(output,name+(hasCode?'-waiting-code.png':'-waiting.png'))});
  }
  await verifyIdleLayout(false);
  assert.equal(claimCalls,0); // SDK discovery alone cannot mint a claim.
  await page.evaluate(data=>window.__cafReceive(data),{kind:'vibecast_display_bootstrap',version:1,handoff_id:id,ha_origin:ha,bootstrap_token:cap,expires_in:30});
  await page.waitForFunction(()=>window.__cafSent.some(x=>x.data.kind==='vibecast_display_claim'));
  await page.locator('#handoff .handoff-code strong').waitFor();
  await verifyIdleLayout(true);
  const languagePicker=page.locator('#display-language');
  await languagePicker.selectOption('nl');
  assert.equal(claimCalls,1);assert.equal(approved,false);
  assert.equal(await page.evaluate(()=>window.__cafSent.some(x=>x.data.state==='presenting')),false);
  approved=true;
  await page.waitForFunction(()=>window.__cafSent.some(x=>x.data.state==='presenting'));
  assert.equal(await page.locator('#title').textContent(),'Declared fixture recording');
  const horizonPreview=page.locator('.horizon-panel #horizon-preview');
  await horizonPreview.waitFor({state:'visible'});
  assert.equal(await horizonPreview.locator('h2').textContent(),'Hierna');
  assert.equal(await horizonPreview.locator('strong').textContent(),'Declared next recording');
  assert.equal(await page.locator('#display-view-status').textContent(),'Flow');
  assert.equal(await languagePicker.isVisible(),false);
  assert.equal(await page.evaluate(()=>window.__castStorageAccesses),0);
  await page.locator('#flow-cards .flow-card').waitFor();await page.locator('.guest-participation img').waitFor();
  assert.equal(await page.locator('#receiver-brand-label').innerText(),'VibeCast Party');
  assert.equal((await page.locator('#live-indicator').innerText()).trim(),'');
  assert.equal(await page.locator('#live-indicator svg').evaluate(icon=>getComputedStyle(icon).stroke),'rgb(255, 255, 255)');
  assert.equal(await page.locator('.session-status #state').isVisible(),false);
  assert.equal(await page.locator('.guest-manual-entry strong').innerText(),'ABCD-EFGH-JKLM');
  assert.equal(await page.locator('.guest-manual-entry span').innerText(),'ha.example.net');
  const qr=await page.locator('.guest-participation img').boundingBox();
  const code=await page.locator('.guest-manual-entry').boundingBox();
  assert.ok(code.x+code.width<qr.x);
  const footer=await page.locator('.renderer-footer').boundingBox();
  assert.ok(qr.x+qr.width>page.viewportSize().width-40 && qr.y+qr.height>footer.y-30);
  assert.ok(qr.y+qr.height<=footer.y,'Guest QR must stay above the footer');
  assert.equal(await page.locator('#end-session').isVisible(),false);
  const sent=await page.evaluate(()=>window.__cafSent);
  assert.ok(sent.every(x=>x.sender==='declared-sdk-sender'));
  assert.ok(!JSON.stringify(sent).includes(cap)&&!JSON.stringify(sent).includes(grant)&&!JSON.stringify(sent).includes('claim_secret'));
  const last=sent.filter(x=>x.data.state==='presenting').at(-1).data;
  assert.equal(last.display_id,binding.display_id);assert.equal(last.connection_generation,3);
  await page.screenshot({path:path.join(output,name+'-B-canvas.png')});
  await page.evaluate(data=>window.__cafReceive(data,'unrelated-sender'),{kind:'vibecast_display_stop',version:1,handoff_id:id});
  assert.equal(leaveCalls,0);
  await page.evaluate(data=>window.__cafReceive(data),{kind:'vibecast_display_stop',version:1,handoff_id:id});
  await page.waitForFunction(()=>document.querySelector('#title').textContent!=='Declared fixture recording');
  assert.equal(await page.locator('#live-indicator').isVisible(),false);
  assert.equal(await page.locator('#receiver-brand-label').innerText(),'DJConnect VibeCast');
  assert.equal(await horizonPreview.isVisible(),false);
  assert.equal(await page.locator('.guest-participation').isVisible(),false);
  assert.equal(await page.locator('.guest-manual-entry strong').textContent(),'');
  for(let i=0;leaveCalls===0&&i<50;i++)await new Promise(resolve=>setTimeout(resolve,20));
  assert.equal(leaveCalls,1);assert.equal(claimCalls,1);assert.deepEqual(errors,[]);
  return{engine:name,claim_calls:claimCalls,collect_calls:collectCalls,leave_calls:leaveCalls,preflights,actual_route_paths:[...new Set(calls)],page_errors:errors,passed:true};
 }finally{await browser.close();}
}
(async()=>{const receipts=[];for(const [name,engine] of [['chromium',chromium],['webkit',webkit]]){if(process.env.DJC_BROWSER_ONLY && process.env.DJC_BROWSER_ONLY!==name)continue;receipts.push(await run(name,engine));}
const receipt={scope:'REAL_BROWSER_SHARED_RENDERER_WITH_DECLARED_FIXTURE_WIRES_AND_SYNTHETIC_CAF_NOT_ACTUAL_HA_SDK_OR_TV',results:receipts};fs.writeFileSync(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));})().catch(e=>{console.error(e);process.exitCode=1;});

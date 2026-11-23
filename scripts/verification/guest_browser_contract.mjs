/* Execute the maintained guest UI with declared DOM/HTTP fixtures, not browser/device acceptance. */
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {webcrypto,randomUUID} from 'node:crypto';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const source=await readFile(new URL('../../custom_components/djconnect/vibecast_renderer/guest.js',import.meta.url),'utf8');
class Element{
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.hidden=false;this.disabled=false;this.value='';this.textContent='';this.checked=false;}
  append(...children){for(const child of children){child.parent=this;this.children.push(child);}}
  replaceChildren(...children){this.children=[];this.append(...children);this.textContent='';}
  setAttribute(){} focus(){} get firstChild(){return this.children[0];}
  remove(){if(this.parent)this.parent.children.splice(this.parent.children.indexOf(this),1);}
}
const nodes=new Map(),history=[],requests=[],timers=new Map();let timerId=0,lost=true,withdrawn=false,reloads=0;const listeners=new Map();
const el=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
const location={pathname:'/djconnect/vibecast/guest',hash:'#issuer_epoch='+('e'.repeat(32))+'&invitation_id='+('i'.repeat(32))+'&invitation_secret='+('s'.repeat(43))};
location.reload=()=>{reloads++;};
const response=(body,status=200)=>({ok:status<400,status,headers:{get:()=>null},text:async()=>JSON.stringify(body)});
const fetch=async(path,options)=>{
  const body=JSON.parse(options.body);requests.push({path,options,body});
  assert.equal(options.credentials,'omit');assert.equal(options.redirect,'error');assert.equal(options.cache,'no-store');
  assert.ok(path.startsWith('/api/djconnect/v1/participation/'));
  if(path.endsWith('/redeem'))return response({guest_id:'unit-guest',issuer_epoch:'unit-epoch',guest_token:'djcg_synthetic-only',
    lease_expires_in:60,capabilities:{request_song:true,screen_focus:true}});
  assert.equal(options.headers.Authorization,'Bearer djcg_synthetic-only');
  assert.equal(body.guest_id,'unit-guest');assert.equal(body.issuer_epoch,'unit-epoch');
  for(const forbidden of ['identity','profile_id','session_id','device_id'])assert.ok(!(forbidden in body));
  if(path.endsWith('/context'))return withdrawn?response({success:false,error:'guest_grant_invalid'},401):response({
    playback:{title:'Public track',artist:'Public artist'},moments:[]});
  if(path.endsWith('/request')){
    if(lost){lost=false;throw new Error('synthetic response lost');}
    return response({success:true,text:'Received',guest_request:{request_id:'unit-request',title:'Selected recording',state:'received'}});
  }
  if(path.endsWith('/request/status'))return response({request:{request_id:'unit-request',title:'Selected recording',state:'received'}});
  throw new Error('Unexpected source UI request');
};
const context=vm.createContext({document:{getElementById:el,createElement:tag=>new Element(tag),documentElement:{}},
  window:{addEventListener(name,handler){listeners.set(name,handler);}},navigator:{language:'en'},location,history:{replaceState:(_state,_title,url)=>{
    history.push(url);location.hash='';}},performance:{now:()=>100},URLSearchParams,URL,crypto:{randomUUID,subtle:webcrypto.subtle},
  fetch,AbortController,setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id;},
  clearTimeout:id=>timers.delete(id),setInterval:()=>0,console:{log:()=>{throw new Error('Unexpected UI log');}}});
vm.runInContext(source,context,{filename:fileURLToPath(new URL('../../custom_components/djconnect/vibecast_renderer/guest.js',import.meta.url))});
assert.deepEqual(history,['/djconnect/vibecast/guest']);assert.equal(location.hash,'');assert.equal(requests.length,0);
assert.equal(el('join').hidden,false);
const settle=async()=>{for(let i=0;i<12;i++)await new Promise(setImmediate);};
await el('join').onclick();await settle();
assert.equal(el('conversation').hidden,false);assert.equal(el('join').hidden,true);
el('question').value='Request the selected recording';el('request-mode').checked=true;
el('form').onsubmit({preventDefault(){}});await settle();
assert.equal(el('retry').hidden,false);
const original=requests.find(row=>row.path.endsWith('/request'));
el('retry').onclick();await settle();
const retries=requests.filter(row=>row.path.endsWith('/request'));
assert.equal(retries.length,2);assert.deepEqual(retries[0].body,retries[1].body);
assert.equal(retries[0].body.client_message_id,original.body.client_message_id);
assert.equal(el('retry').hidden,true);
withdrawn=true;
const refresh=[...timers.values()].find(row=>row.delay===10000);assert.ok(refresh);refresh.fn();await settle();
assert.equal(el('conversation').hidden,true);assert.equal(el('messages').children.length,0);
assert.equal(el('question').value,'');
const before=requests.length;el('form').onsubmit({preventDefault(){}});await settle();assert.equal(requests.length,before);
for(const node of nodes.values())assert.ok(!node.textContent.includes('djcg_synthetic-only'));
// A new invitation in an already active document must not retain the old scope.
nodes.clear();listeners.clear();withdrawn=false;
location.hash='#issuer_epoch='+('n'.repeat(32))+'&invitation_id='+('j'.repeat(32))+'&invitation_secret='+('t'.repeat(43));
vm.runInContext(source,context);await el('join').onclick();await settle();
assert.equal(el('conversation').hidden,false);
el('question').value='Old draft must not cross an invitation';
location.hash='#issuer_epoch='+('n'.repeat(32))+'&invitation_id='+('k'.repeat(32))+'&invitation_secret='+('u'.repeat(43));
const beforeRotation=requests.length;
assert.equal(typeof listeners.get('hashchange'),'function','fresh same-document invitation must have a navigation handler');
listeners.get('hashchange')();await settle();
assert.equal(reloads,1);assert.equal(el('conversation').hidden,true);assert.equal(el('messages').children.length,0);
assert.equal(el('question').value,'');el('form').onsubmit({preventDefault(){}});await settle();assert.equal(requests.length,beforeRotation);
// A real reload executes this same bootstrap; malformed invitation stays closed.
nodes.clear();listeners.clear();location.hash='#invitation_secret=invalid';vm.runInContext(source,context);
assert.equal(location.hash,'');assert.equal(el('join').hidden,true);assert.equal(el('conversation').hidden,true);
assert.equal(requests.length,beforeRotation);
console.log(JSON.stringify({status:'PASS',scope:'SOURCE_DOM_AND_HTTP_FIXTURES_NOT_REAL_BROWSER',checks:[
  'invitation_fragment_erased_before_admission','memory_only_separate_guest_token','same_body_and_client_id_after_lost_response',
  'no_owner_identity_fields_or_cookies','withdrawal_discards_transcript_and_prevents_dispatch',
  'fresh_same_document_invitation_closes_scope_and_reloads_without_post',
  'malformed_invitation_after_reload_stays_closed']}));

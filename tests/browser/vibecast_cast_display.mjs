/* Closed CAF envelope/retention tests with explicit synthetic host callbacks.
 * This is not a Core grant, actual CAF SDK, HA/provider or physical TV proof. */
import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../../custom_components/djconnect/vibecast_renderer/cast-host.js',import.meta.url),'utf8');
function harness(){
 const events=new Map(),cafEvents=new Map(),sent=[],timers=new Map();let ready=false,receiver,options,host,stops=0,id=0,now=0;
 class CustomEvent{constructor(type,value={}){this.type=type;this.detail=value.detail;}}
 const context={isSystemReady:()=>ready,start(value){options=value;},addEventListener(type,cb){cafEvents.set(type,cb);},
  addCustomMessageListener(namespace,cb){assert.ok(ready);receiver=cb;},
  sendCustomMessage(namespace,sender,data){assert.equal(namespace,'urn:x-cast:com.djconnect.vibecast.v1');assert.ok(sender);sent.push({sender,data});}};
 const window={cast:{framework:{CastReceiverContext:{getInstance:()=>context},system:{EventType:{READY:'ready',SENDER_DISCONNECTED:'disconnected'},MessageType:{JSON:'JSON'}}}},
  addEventListener(type,cb){if(!events.has(type))events.set(type,[]);events.get(type).push(cb);},dispatchEvent(event){for(const cb of events.get(event.type)||[])cb(event);},
  clearTimeout(key){timers.delete(key);},setTimeout(cb,ms){timers.set(++id,{cb,ms});return id;},
  DJCDisplayHost(value){host=value;delete value.bootstrapToken;return{stop(){stops++;}};}};
 const sandbox={window,document:{documentElement:{lang:'en'},getElementById:()=>({})},URL,CustomEvent,
  performance:{now:()=>now},setTimeout:window.setTimeout,clearTimeout:window.clearTimeout};
 vm.runInNewContext(source,sandbox);
 return{sent,timers,options,host:()=>host,stops:()=>stops,ready(){ready=true;cafEvents.get('ready')();},
  message(data,senderId='actual-sdk-sender-fixture'){receiver({data,senderId});},
  event(type,detail){window.dispatchEvent(new CustomEvent(type,{detail}));},advance(ms){now+=ms;}};
}
const bootstrap=(id='a'.repeat(32))=>({kind:'vibecast_display_bootstrap',version:1,handoff_id:id,
 ha_origin:'https://ha.example.net',bootstrap_token:'djccb_'+'s'.repeat(43),expires_in:30});
const claim=()=>({issuer_epoch:'e'.repeat(43),claim_id:'c'.repeat(43),browser_generation:'b'.repeat(43),code:'123456',expires_in:120,expires_at:'2099-01-01T00:00:00Z'});
const binding=()=>({issuer_epoch:'e'.repeat(43),display_id:'d'.repeat(43),share_id:'h'.repeat(43),share_generation:1,session_id:'declared-unit-session'});
const states=h=>h.sent.filter(x=>x.data.kind==='vibecast_display_status').map(x=>x.data.state);
test('new bootstrap cannot report presenting without real host snapshot/render callbacks',()=>{
 const h=harness();assert.equal(h.options.disableIdleTimeout,true);h.ready();h.message(bootstrap());
 assert.deepEqual(states(h),['receiver_ready']);assert.equal(h.host().apiOrigin,'https://ha.example.net');
 h.host().onClaim(claim());assert.equal(states(h).at(-1),'claim_ready');
 const lookup=h.sent.find(x=>x.data.kind==='vibecast_display_claim');
 assert.equal(lookup.sender,'actual-sdk-sender-fixture');assert.equal(lookup.data.code,'123456');
 h.host().onAdmitted(binding());assert.equal(states(h).at(-1),'approved');
 h.event('djconnect-display-rendered',{...binding(),presentation:'moment'});
 assert.equal(states(h).includes('presenting'),false);
 h.host().onSnapshot({...binding(),connection_generation:7});
 h.event('djconnect-display-rendered',{...binding(),display_id:'wrong',presentation:'moment'});
 assert.equal(states(h).includes('presenting'),false);
 h.event('djconnect-display-rendered',{...binding(),presentation:'moment'});
 assert.equal(states(h).at(-1),'presenting');assert.equal(h.sent.at(-1).data.connection_generation,7);
 assert.ok(h.sent.every(x=>!JSON.stringify(x).includes('djccb_')&&!JSON.stringify(x).includes('claim_secret')&&!JSON.stringify(x).includes('grant_token')));
});
test('retries preserve original claim expiry and cannot reinitialize or replace active channel',()=>{
 const h=harness();h.ready();h.message(bootstrap());const original=h.host();original.onClaim(claim());
 h.advance(20000);h.message(bootstrap());assert.equal(h.host(),original);
 assert.equal(h.sent.at(-1).data.expires_in,100);
 h.message(bootstrap('b'.repeat(32)),'unrelated-sdk-sender');assert.equal(h.host(),original);assert.equal(h.stops(),0);
 h.message({kind:'vibecast_display_stop',version:1,handoff_id:'a'.repeat(32)},'unrelated-sdk-sender');assert.equal(h.stops(),0);
 h.message({kind:'vibecast_display_stop',version:1,handoff_id:'a'.repeat(32)});assert.equal(h.stops(),1);
 h.message(bootstrap());assert.equal(h.host(),original);assert.equal(h.stops(),1);
});
test('legacy view token cannot stop or acquire active B; loss clears positive status',()=>{
 const h=harness();h.ready();h.message(bootstrap());h.host().onAdmitted(binding());h.host().onSnapshot({...binding(),connection_generation:1});
 h.event('djconnect-display-rendered',{...binding(),presentation:'silence'});assert.equal(states(h).at(-1),'presenting');
 h.message({kind:'vibecast_stop',version:1,handoff_id:'a'.repeat(32),session_id:'declared-unit-session'});assert.equal(h.stops(),0);
 h.event('djconnect-display-clear');assert.equal(states(h).at(-1),'recovering');assert.equal(h.sent.at(-1).data.presentation,undefined);
 assert.ok(![...h.timers.values()].some(x=>x.ms===5000));
 h.host().onTerminal('expired');assert.equal(h.stops(),1);assert.equal(states(h).at(-1),'error');
});
test('closed bootstrap validation never constructs a host from legacy/unknown/invalid input',()=>{
 for(const delta of [{version:true},{expires_in:0},{expires_in:31},{ha_origin:'http://ha.example.net'},
 {ha_origin:'https://127.0.0.1'},{ha_origin:'https://ha.example.net/path'},{bootstrap_token:'legacy-view-token'},
 {extra:'unrecognized'}]){const h=harness();h.ready();h.message({...bootstrap(),...delta});assert.equal(h.host(),undefined);assert.deepEqual(states(h),[]);}
});

test('malformed other sender cannot clear active B and owning malformed input fails closed',()=>{
 const h=harness();h.ready();h.message(bootstrap());
 h.message('not-json','unrelated-sdk-sender');assert.equal(h.stops(),0);
 h.message('not-json');assert.equal(h.stops(),1);assert.equal(states(h).at(-1),'error');
});

"""Causal browser-host races; deterministic JS time, not HA acceptance."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


class DisplayHostRaceTests(unittest.TestCase):
    def test_display_lifecycle_and_party_invitation_timing(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js required")
        source = Path(__file__).resolve().parents[1] / "custom_components/djconnect/vibecast_renderer/display-host.js"
        script = r'''
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const source=fs.readFileSync(SOURCE_PATH,"utf8");
for(const scenario of ["late-pending","late-admitted","revoked","disconnected","expired","renew-denied","reload","refresh","capacity","language","party-qr"]){
  let time=0, resolveCollect, claims=0, socket, serial=0, clears=0, partyEnabled=true;
  const timers=new Map();
  const handlers=new Map();
  const cancellations=[];
  const clipboard=[];
  const history={state:null,replaceState(value){this.state=value}};
  let randomCalls=0;
  function element(tag="span"){
    const value={tag,children:[],hidden:false,classList:new Set(),append(...children){this.children.push(...children)},setAttribute(){},getAttribute(key){return this[key]},removeAttribute(key){delete this[key]}};
    Object.defineProperty(value,"textContent",{get(){return this._text || ""},set(text){this._text=text;this.children=[]}});
    return value;
  }
  const panel=element(),header=element(),body=element(),selector=element("select"),localeStore=new Map();
  let changeLanguage;
  selector.addEventListener=(type,handler)=>{assert.equal(type,"change");changeLanguage=handler};
  const codeBlock=()=>panel.children.find(child=>child.className==="handoff-code");
  const code=()=>codeBlock()?.children.find(child=>child.tag==="strong");
  const response=value=>({ok:true,status:200,text:async()=>JSON.stringify({success:true,...value})});
  const context={navigator:{language:"en",onLine:true,clipboard:{writeText:async value=>clipboard.push(value)}},performance:{now:()=>time},
    location:{protocol:"https:",origin:"https://ha.example.test",search:"",hash:""},
    crypto:{getRandomValues:bytes=>bytes.fill(scenario==="refresh"?++randomCalls:claims+1)},btoa:value=>Buffer.from(value,"binary").toString("base64"),
    AbortController,Event,URL,CustomEvent:class{},WebSocket:class{
      constructor(){socket=this}
      close(){}
    },
    setTimeout:(fn,delay)=>{timers.set(++serial,{fn,delay,due:time+delay});return serial},clearTimeout:id=>timers.delete(id),
    document:{body,getElementById:id=>id==="display-language"?selector:panel,createElement:element,querySelector:()=>header,addEventListener(){}},
    window:{localStorage:{getItem:key=>localeStore.get(key),setItem:(key,value)=>localeStore.set(key,value)},history:scenario==="refresh"?history:undefined,addEventListener(type,handler){handlers.set(type,handler)},dispatchEvent(event){if(event.type==="djconnect-display-clear")clears++}},
    fetch:async (path,options)=>{
      if(path.endsWith("/claim")){
        assert.equal(options.headers.Authorization,undefined);
        const body=JSON.parse(options.body);
        if(scenario==="refresh"){
          assert.equal(body.request_id,Buffer.alloc(32,1).toString("base64url"));
          assert.equal(body.browser_nonce,Buffer.alloc(32,claims+2).toString("base64url"));
          return response({contract_version:1,code:"123456",expires_in:claims++===0?120:75,
            issuer_epoch:"epoch",claim_id:"claim",claim_secret:"secret",browser_generation:"generation"});
        }
        assert.equal(body.browser_nonce,Buffer.alloc(32,claims+1).toString("base64url"));
        if(scenario==="capacity" && claims===0){
          claims++;
          return {ok:false,status:429,text:async()=>JSON.stringify({error:"display_capacity"})};
        }
        return response({contract_version:1,code:++claims===1?"123456":"654321",expires_in:120,
        issuer_epoch:"epoch",claim_id:"claim",claim_secret:"secret",browser_generation:"generation"});}
      if(path.endsWith("/cancel")){cancellations.push(options);return response({});}
      if(path.endsWith("/focus"))return response({live_enabled:partyEnabled});
      if(path.endsWith("/invitation"))return response({expires_in:30,qr_data_uri:"data:image/svg+xml;base64,QQ=="});
      if(path.endsWith("/renew") && scenario==="party-qr"){
        return response({lease_revision:JSON.parse(options.body).renew_sequence,lease_expires_in:60});
      }
      if(path.endsWith("/renew"))return {ok:false,status:401,text:async()=>JSON.stringify({error:"display_grant_invalid"})};
      return new Promise(resolve=>{resolveCollect=resolve});
    }};
  vm.runInNewContext(source,context);
  assert.equal(panel.hidden,false);
  assert.deepEqual(panel.children.map(child=>child.className),["handoff-placeholder","handoff-code handoff-placeholder"]);
  assert.equal(panel.children[1].children[0].textContent.trim(),"");
  await new Promise(setImmediate);
  if(scenario==="capacity"){
    assert.equal(claims,1);
    [...timers.values()].find(timer=>timer.delay===800).fn();
    await new Promise(setImmediate);
    assert.equal(claims,2);
    assert.equal(code().textContent,"654321");
    continue;
  }
  assert.equal(Boolean(code()),true);
  assert.equal(header.children.length,0);
  if(scenario==="refresh"){
    handlers.get("pagehide")();
    assert.equal(cancellations.length,0);
    assert.deepEqual(Object.keys(history.state),["vibeCastClaimRequestId"]);
    time=45000;
    await handlers.get("pageshow")({persisted:true});
    assert.equal(claims,2);
    assert.equal(code().textContent,"123456");
    assert.ok([...timers.values()].some(timer=>timer.delay===75000));
    continue;
  }
  if(scenario==="language"){
    assert.equal(selector.value,"en");
    selector.value="nl";
    changeLanguage();
    assert.match(panel.children[0].textContent,/Kies 'VibeCast sessie starten'/);
    assert.equal(code().textContent,"123456");
    assert.equal(claims,1);
    assert.equal(cancellations.length,0);
    assert.deepEqual([...localeStore],[["djconnect-vibecast-language","nl"]]);
    continue;
  }
  if(scenario==="reload"){
    const copy=codeBlock().children.find(child=>child.className==="handoff-copy");
    await copy.onclick();
    assert.deepEqual(clipboard,["123456"]);
    assert.equal(copy.title,"Code copied");
    handlers.get("pagehide")({persisted:false});
    assert.equal(cancellations.length,1);
    const cancellation=cancellations[0];
    assert.equal(cancellation.keepalive,true);
    assert.equal(cancellation.credentials,"omit");
    assert.deepEqual(JSON.parse(cancellation.body),{contract_version:1,issuer_epoch:"epoch",claim_id:"claim",
      claim_secret:"secret",browser_generation:"generation",browser_nonce:Buffer.alloc(32,1).toString("base64url")});
    assert.equal(panel.hidden,true);
    await handlers.get("pageshow")({persisted:true});
    assert.equal(claims,2);
    continue;
  }
  if(!scenario.startsWith("late-")){
    resolveCollect(response({state:"admitted",grant_token:"djcd_"+"A".repeat(43),lease_expires_in:60,session_locale:"nl",
      capabilities:{owner_controls:false,session_end:false}}));
    await new Promise(setImmediate);
    assert.equal(panel.children[0].textContent,"Opnieuw verbinden…");
    if(scenario==="party-qr"){
      const snapshot=async (state,item_id,position_ms)=>{
        socket.onmessage({data:JSON.stringify({type:"snapshot",contract_version:1,connection_generation:1,
          snapshot:{playback:{state,item_id,position_ms}}})});
        await new Promise(setImmediate);
      };
      const advance=async until=>{
        while(true){
          const next=[...timers].sort((a,b)=>a[1].due-b[1].due)[0];
          if(!next || next[1].due>until)break;
          time=next[1].due;timers.delete(next[0]);next[1].fn();
          await new Promise(setImmediate);
        }
        time=until;
      };
      await snapshot("playing","already-playing",60000);
      const qr=body.children[0];
      assert.equal(qr.hidden,true,"opening midway through a track does not show the QR");
      await snapshot("paused","already-playing",60000);
      assert.equal(qr.hidden,false);
      await advance(21000);
      assert.equal(qr.hidden,false,"the invitation stays visible while paused across polls");
      await snapshot("playing","already-playing",60000);
      assert.equal(qr.hidden,true,"resuming an older track does not start a new intro");
      await snapshot("idle");
      assert.equal(qr.hidden,false);
      await advance(30000);
      assert.equal(qr.hidden,false);
      await snapshot("playing","first",0);
      assert.equal(qr.hidden,false);
      await advance(42000);
      await snapshot("playing","first",12000);
      await advance(49999);
      assert.equal(qr.hidden,false);
      await advance(50000);
      assert.equal(qr.hidden,true,"the QR hides exactly at 20 seconds without another frame");
      await advance(51000);
      assert.equal(qr.hidden,true,"invitation rotation does not restart the window");
      await snapshot("playing","next",2000);
      assert.equal(qr.hidden,false);
      await advance(69000);
      assert.equal(qr.hidden,true,"the known track position counts toward the 20 seconds");
      await snapshot("paused","next",20000);
      assert.equal(qr.hidden,false);
      partyEnabled=false;
      await advance(72000);
      assert.equal(qr.hidden,true);
      assert.equal(qr.children[1].src,undefined);
      partyEnabled=true;
      await advance(75000);
      assert.equal(qr.hidden,false);
      socket.onclose({code:1006});
      assert.equal(qr.hidden,true,"disconnect clears the invitation immediately");
      continue;
    }
    const previousClears=clears;
    if(scenario==="disconnected"){
      socket.onclose({code:1006});
      assert.equal(claims,1);
      assert.equal(panel.children[0].textContent,"Opnieuw verbinden…");
      [...timers.values()].find(timer=>timer.delay===1500).fn();
    }
    const previousSocket=socket, previousClose=socket.onclose;
    if(scenario==="revoked" || scenario==="disconnected")previousClose({code:1008});
    if(scenario==="expired"){
      time=60000;
      [...timers.values()].find(timer=>timer.delay===1000).fn();
    }
    if(scenario==="renew-denied"){
      time=20000;
      [...timers.values()].find(timer=>timer.delay===20000).fn();
    }
    await new Promise(setImmediate);
    assert.ok(clears>previousClears);
    assert.equal(socket,previousSocket);
    assert.equal(claims,2);
    assert.equal(code().textContent,"654321");
    assert.match(panel.children[0].textContent,/Choose ‘Share VibeCast Screen’ in the app/);
    assert.equal(panel.children.some(child=>child.tag==="button"),false);
    previousClose({code:1008});
    assert.equal(claims,2);
    continue;
  }
  const previousCollect=resolveCollect;
  time=120000;
  [...timers.values()].find(timer=>timer.delay===120000).fn();
  await new Promise(setImmediate);
  assert.equal(claims,2);
  assert.equal(code().textContent,"654321");
  previousCollect(response({state:scenario.slice(5),grant_token:"djcd_"+"A".repeat(43),lease_expires_in:60}));
  await new Promise(setImmediate);
  assert.equal(socket,undefined);
  assert.equal(code().textContent,"654321");
}
'''.replace("SOURCE_PATH", json.dumps(str(source)))
        result = subprocess.run([node, "--input-type=module", "--eval", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_generated_hosts_preserve_retired_receiver_end_authority(self):
        from scripts.build_vibecast import render
        root=Path(__file__).resolve().parents[1]
        for host in ('local','cast','display'):
            html=render(root,host)
            for retired in ('endGrant','end_grant','/broadcast/control/end','id="end-session"'):
                self.assertNotIn(retired,html,(host,retired))
            if host in ('local','display'):
                name='vibecast.html' if host=='local' else 'vibecast_display.html'
                self.assertEqual((root/'custom_components/djconnect'/name).read_text(),html)

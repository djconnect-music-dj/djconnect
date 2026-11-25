// Exercise the shared renderer in WebKit with a closed display transport fixture.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {chromium,webkit} = require(process.env.DJC_PLAYWRIGHT);
const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root,"custom_components/djconnect/vibecast_display.html"),"utf8");
const origin = "https://ha.example.test";
const cover = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAANUlEQVR4nO3QsQ0AMAzDsLT//9yeoCkbeYAN6LzZdZf3x0GSKEmUJEoSJYmSREmiJFGSaMoHo8QBPwYSAhsAAAAASUVORK5CYII=", "base64");
const grant = "djcd_" + "A".repeat(43);
const binding = {issuer_epoch:"epoch",display_id:"display",share_id:"share",share_generation:1,session_id:"session"};

async function main(engine) {
  const chromiumOptions = process.env.DJC_CHROMIUM_PATH
    ? {executablePath:process.env.DJC_CHROMIUM_PATH}
    : {channel:"chromium"};
  const browser = await engine.launch({timeout:12000,...(engine===chromium ? chromiumOptions : {})});
  let page;
  try {
    page = await browser.newPage({viewport:{width:1280,height:720},reducedMotion:"reduce",locale:"en-US",timezoneId:"Europe/Amsterdam"});
    page.on("pageerror",error=>console.error("Renderer page error:",error.message));
    page.setDefaultTimeout(5000);
    let socket, allowAdmission=true;
    const artworkReads=[];
    await page.route(origin+"/**",route=>{
      const endpoint = new URL(route.request().url()).pathname.split("/").pop();
      if(endpoint==="display") return route.fulfill({body:html,contentType:"text/html"});
      if(endpoint==="claim") return route.fulfill({json:{success:true,contract_version:1,code:"123456",
        expires_in:120,issuer_epoch:"epoch",claim_id:"claim",claim_secret:"secret",browser_generation:"generation"}});
      if(endpoint==="artwork") {
        artworkReads.push(route.request().postDataJSON().reference);
        assert.equal(route.request().headers().authorization,"Bearer "+grant);
        assert.ok(["a","b","c"].map(value=>value.repeat(64)).includes(route.request().postDataJSON().reference));
        return route.fulfill({body:cover,contentType:"image/png",
          headers:{"Content-Length":String(cover.length)}});
      }
      if(endpoint==="focus")return route.fulfill({json:{success:true,focused_moment_id:null,expires_in:0}});
      if(endpoint==="invitation")return route.fulfill({status:403,json:{success:false,error:"guest_share_unavailable"}});
      assert.equal(endpoint,"collect");
      if(!allowAdmission)return route.fulfill({json:{success:true,state:"pending"}});
      return route.fulfill({json:{success:true,state:"admitted",...binding,grant_token:grant,lease_expires_in:60,
        capabilities:{owner_controls:false,session_end:false}}});
    });
    await page.routeWebSocket("wss://ha.example.test/api/djconnect/v1/display/live",ws=>{
      socket=ws;
      ws.onMessage(data=>assert.equal(JSON.parse(data).grant_token,grant));
    });
    const music = [
      "Listen for the bass line in the second verse. It leaves space for the lead guitar.",
      "The opening riff comes back in the outro, this time with the rhythm section stripped back.",
      "That soft keyboard chord under the chorus gives the vocal room to carry.",
      "The mix puts the drums up front, with the backing vocals just behind them."
    ];
    const cards=Array.from({length:11},(_,index)=>({
      moment_id:"published-"+index,type:index===5 ? "genre" : index===6 ? "music_announcement" : "album",
      playback_item_id:index===6 ? "previous" : "current",
      content:index===10 ? music[0].repeat(15) : music[index%music.length],
      display_expires_at:new Date(Date.now()-1000).toISOString(),
      flow_expires_at:new Date(Date.now()+40000).toISOString()
    }));
    cards[7].created_at="2026-01-01T23:05:00Z";
    const previousTrack="https://open.spotify.com/track/"+"B".repeat(22);
    cards[6].artwork={item_id:"previous",reference:"b".repeat(64),source_url:previousTrack,
      expires_at:cards[6].flow_expires_at};
    function snapshot(count, itemId="current", state="playing", output={output_label:"Living room",volume_percent:37}, spotlight={}) {
      socket.send(JSON.stringify({type:"snapshot",contract_version:1,connection_generation:1,snapshot:{
        ...binding,contract_version:1,session:{session_id:"session",runtime_state:"active",locale:"en"},
        playback:{state,item_id:itemId,title:"Current recording",artist:"Artist",album:"Album",
          duration_ms:240000,position_ms:60000,...output},
        artwork:{item_id:"current",reference:"a".repeat(64),
          expires_at:cards[0].flow_expires_at},
        shared_flow:cards.slice(0,count),dj_moments:[{content:"Legacy card must stay out of the Flow"}],...spotlight}}));
    }
    await page.goto(origin+"/djconnect/vibecast/display");
    await page.evaluate(()=>document.fonts.ready);
    await page.waitForFunction(()=>document.querySelector("#handoff")?.textContent.includes("Reconnecting") ||
      document.querySelector("#handoff")?.textContent.includes("Connecting")).catch(()=>{});
    for(let i=0;!socket && i<50;i++) await new Promise(resolve=>setTimeout(resolve,50));
    assert.ok(socket);
    const waitingBrand=page.locator(".waiting-brand");
    await waitingBrand.waitFor({state:"visible"});
    snapshot(0,"","idle",{title:"",artist:"",album:"",duration_ms:null,position_ms:null},{
      view:{mode:"flow",dynamics:.5},artwork:null
    });
    await page.waitForFunction(()=>document.querySelector("#title").textContent==="Waiting for music");
    await waitingBrand.waitFor({state:"hidden"});
    assert.equal(await page.locator("#handoff").isVisible(),false);
    assert.equal(await page.locator("#display-view-status").textContent(),"Flow");
    snapshot(8, "current", "playing", undefined, {
      session_presentation:{mood:"chill",persona:"home_dj",presence:"presenter"},
      artwork:null
    });
    const languagePicker = page.locator("#display-language");
    const moodIcon = page.locator("#session-mood-icon");
    await moodIcon.waitFor();
    await languagePicker.waitFor({state:"hidden"});
    const modeStatus=page.locator("#display-view-status");
    assert.equal(await modeStatus.textContent(),"Flow");
    assert.equal(await page.locator(".session-status .spotlight-avatar").count(), 0);
    for (const [name,label] of [["mood","Mood: Chill"],["persona","DJ character: Home DJ"],["presence","DJ presence: Presenter"]]) {
      const icon = page.locator("#session-"+name+"-icon");
      assert.equal(await icon.locator("title").textContent(), label);
      assert.equal(await icon.getAttribute("aria-label"), label);
    }
    snapshot(8,"current","playing",undefined,{
      session_presentation:{mood:"groove",persona:"home_dj",presence:"presenter"},artwork:null
    });
    const sessionToast=page.locator("#session-change-popup");
    await sessionToast.waitFor({state:"visible"});
    assert.equal(await sessionToast.locator("span").textContent(),"Session updated");
    const toastBox=await sessionToast.boundingBox(), footerBox=await page.locator(".renderer-footer").boundingBox();
    const {width,height}=page.viewportSize();
    assert.ok(toastBox && footerBox && toastBox.y+toastBox.height<=footerBox.y);
    assert.ok(toastBox.y>height-80 && toastBox.height<40 && toastBox.width<220);
    assert.ok(Math.abs(toastBox.x+toastBox.width/2-width/2)<1);
    assert.equal(await sessionToast.evaluate(node=>getComputedStyle(node).pointerEvents),"none");
    const viewport=page.locator("#flow-viewport"), rows=page.locator("#flow-cards > .flow-card");
    const placeholder = page.locator("#artwork-placeholder"), title = page.locator("#title");
    await placeholder.waitFor();
    const recordBox = await placeholder.boundingBox(), missingArtTitle = await title.boundingBox();
    assert.ok(recordBox && missingArtTitle && recordBox.x + recordBox.width <= missingArtTitle.x);
    assert.equal(await placeholder.locator(".vinyl-record").evaluate(element=>getComputedStyle(element).animationName), "none");
    assert.equal(await page.locator(".spotlight-avatar-back, .waiting-avatar circle[fill='#000']").count(), 0);
    snapshot(8);
    const atEdge=()=>viewport.evaluate(e=>e.scrollTop<=4);
    await rows.nth(7).waitFor();
    const timestamp=rows.first().locator("time");
    assert.equal(await timestamp.getAttribute("datetime"),cards[7].created_at);
    assert.equal(await timestamp.textContent(),"00:05");
    assert.equal(await rows.nth(2).locator("time").count(),0);
    const albumCover=page.locator("#artwork");
    await page.waitForFunction(()=>document.querySelector("#artwork").naturalWidth>0);
    await placeholder.waitFor({state:"hidden"});
    const loadedArtTitle = await title.boundingBox();
    assert.ok(loadedArtTitle && Math.abs(loadedArtTitle.x - missingArtTitle.x) < 1);
    const coverUrl=await albumCover.getAttribute("src");
    assert.match(coverUrl,/^blob:/);
    const contributionCover=rows.first().locator(".flow-artwork");
    await contributionCover.waitFor();
    const thumbnailFrame = rows.first().locator(".flow-artwork-link");
    assert.ok(parseFloat(await thumbnailFrame.evaluate(element=>getComputedStyle(element).borderTopLeftRadius)) > 0);
    assert.ok(parseFloat(await thumbnailFrame.evaluate(element=>getComputedStyle(element).paddingLeft)) > 0);
    assert.equal(await contributionCover.getAttribute("src"),coverUrl);
    assert.equal(await rows.nth(2).locator(".flow-artwork").getAttribute("src"),coverUrl);
    const previousCover=rows.nth(1).locator(".flow-artwork");
    await previousCover.waitFor();
    const previousUrl=await previousCover.getAttribute("src");
    assert.match(previousUrl,/^blob:/);
    assert.notEqual(previousUrl,coverUrl);
    assert.equal(await rows.nth(1).locator(".flow-artwork-link").getAttribute("href"),previousTrack);
    const initialReads=artworkReads.length;
    await albumCover.evaluate(image=>{
      window.artworkRefreshChanges=[];
      new MutationObserver(records=>window.artworkRefreshChanges.push(...records.map(r=>r.attributeName)))
        .observe(image,{attributes:true,attributeFilter:["src","hidden"]});
    });
    // Each fresh snapshot can renew the qualified reference's deadline. It
    // must not revoke and fetch the exact same artwork again.
    for(let refresh=1;refresh<=3;refresh++){
      snapshot(8,"current","playing",{output_label:"Refresh "+refresh,volume_percent:37},{
        artwork:{item_id:"current",reference:"a".repeat(64),
          expires_at:new Date(Date.now()+45000+refresh*1000).toISOString()}});
      await page.waitForFunction(label=>document.querySelector("#display-speaker-label").textContent===label,"Refresh "+refresh);
      assert.equal(await albumCover.getAttribute("src"),coverUrl);
      assert.equal(artworkReads.length,initialReads);
    }
    assert.deepEqual(await page.evaluate(()=>window.artworkRefreshChanges.filter(name=>name==="src")),[]);
    snapshot(8);
    await page.waitForFunction(()=>document.querySelector("#display-speaker-label").textContent==="Living room");
    assert.equal(await rows.count(),8);
    assert.equal(await atEdge(),true);
    assert.equal(await page.locator(".now-playing").evaluate(node=>getComputedStyle(node).backgroundColor),"rgba(0, 0, 0, 0)");
    assert.equal(await page.locator("#display-speaker-label").textContent(),"Living room");
    assert.equal(await page.locator("#display-volume-label").count(),0);
    assert.equal(await page.locator("#display-output :is(button,input)").count(),0);
    assert.equal(await page.locator("#display-meter progress").count(),1);
    assert.equal(await page.locator("#time").textContent(),"1:00 / 4:00");
    const equalizer=page.locator("#display-equalizer i").first();
    assert.equal(await equalizer.evaluate(node=>getComputedStyle(node).animationName),"none");
    await page.emulateMedia({reducedMotion:"no-preference"});
    assert.equal(await equalizer.evaluate(node=>getComputedStyle(node).animationName),"display-equalize");
    snapshot(8,"current","paused",{volume_percent:0});
    await page.locator("#display-output").waitFor({state:"hidden"});
    assert.equal(await equalizer.evaluate(node=>getComputedStyle(node).animationName),"none");
    await page.emulateMedia({reducedMotion:"reduce"});
    snapshot(8);
    assert.equal(await viewport.getAttribute("tabindex"),"0");
    const top=await page.locator("#title").boundingBox();
    const styles=await rows.evaluateAll(items=>items.slice(0,4).map(row=>{
      const style=getComputedStyle(row);
      return {font:parseFloat(style.fontSize),radius:style.borderTopLeftRadius,border:style.borderTopColor};
    }));
    assert.deepEqual(styles.map(item=>item.radius),["32px","18px","18px","18px"]);
    assert.ok(styles.every(item=>item.font===styles[0].font && item.font>=24));
    assert.match(styles[0].border,/255, 255, 255, 0.32/);
    const coverBounds=await albumCover.boundingBox();
    const viewportBounds=await viewport.boundingBox();
    assert.ok(coverBounds.width>=170 && viewportBounds.height>=180);
    assert.ok((await rows.nth(1).boundingBox()).y < viewportBounds.y+viewportBounds.height);
    await viewport.focus();
    await page.keyboard.press("ArrowDown");
    await page.waitForFunction(()=>!document.querySelector("#flow-live").hidden);
    const readingRow=await viewport.evaluateHandle(e=>[...e.querySelectorAll("#flow-cards > .flow-card")]
      .find(row=>row.getBoundingClientRect().bottom>e.getBoundingClientRect().top));
    const readingTop=await readingRow.evaluate(row=>row.getBoundingClientRect().top);
    const live=page.getByRole("button",{name:"Back to live"});
    await live.waitFor();
    assert.equal(await atEdge(),false);
    await page.emulateMedia({reducedMotion:"no-preference"});
    const spotlight=page.locator("#moment-card");
    const readingScroll=await viewport.evaluate(node=>node.scrollTop);
    const moment={moment_id:"active-spotlight",type:"album",content:"Current DJ spotlight",
      created_at:new Date(Date.now()-10000).toISOString(),display_expires_at:new Date(Date.now()+2200).toISOString(),
      presentation_intent:{maximum_duration_seconds:1}};
    snapshot(8,"current","playing",undefined,{current_moment_id:moment.moment_id,dj_moments:[moment],session_presentation:{mood:"groove"}});
    await spotlight.waitFor();
    const avatar=spotlight.locator("#spotlight-avatar");
    await avatar.waitFor();
    assert.equal(await spotlight.getAttribute("data-mood"),"groove");
    assert.equal(await avatar.locator("stop").first().evaluate(node=>getComputedStyle(node).stopColor),"rgb(6, 199, 173)");
    const wave=avatar.locator(".spotlight-wave rect").first();
    assert.equal(await wave.evaluate(node=>getComputedStyle(node).animationName),"spotlight-pulse");
    await page.emulateMedia({reducedMotion:"reduce"});
    assert.equal(await wave.evaluate(node=>getComputedStyle(node).animationName),"none");
    await page.emulateMedia({reducedMotion:"no-preference"});
    assert.equal(await spotlight.locator("#moment").textContent(),"Current DJ spotlight");
    if(process.env.DJC_SPOTLIGHT_SCREENSHOT) await page.screenshot({path:process.env.DJC_SPOTLIGHT_SCREENSHOT});
    await viewport.waitFor({state:"hidden"});
    const nowPlaying=await page.locator(".now-playing").boundingBox();
    const spotlightGap=(await spotlight.boundingBox()).y-nowPlaying.y-nowPlaying.height;
    assert.ok(spotlightGap>=0 && spotlightGap<30);
    assert.equal((await page.locator("#title").boundingBox()).y,top.y);
    await spotlight.waitFor({state:"hidden"});
    await viewport.waitFor({state:"visible"});
    assert.equal(await viewport.evaluate(node=>getComputedStyle(node).transitionDuration),"0.35s");
    assert.equal(await viewport.evaluate(node=>node.scrollTop),readingScroll);
    const nextMoment={...moment,moment_id:"next-spotlight",display_expires_at:new Date(Date.now()+10000).toISOString()};
    snapshot(8,"current","playing",undefined,{current_moment_id:nextMoment.moment_id,dj_moments:[nextMoment]});
    await spotlight.waitFor();
    snapshot(8,"current","playing",undefined,{current_moment_id:null,dj_moments:[nextMoment]});
    await spotlight.waitFor({state:"hidden"});
    await viewport.waitFor({state:"visible"});
    assert.equal(await viewport.evaluate(node=>node.scrollTop),readingScroll);
    await page.emulateMedia({reducedMotion:"reduce"});
    snapshot(9);
    await rows.nth(8).waitFor({state:"attached"});
    assert.equal(await atEdge(),false);
    assert.ok(Math.abs(await readingRow.evaluate(row=>row.getBoundingClientRect().top)-readingTop)<=2);
    assert.equal((await page.locator("#title").boundingBox()).y,top.y);
    assert.equal(await albumCover.getAttribute("src"),coverUrl);
    await live.click();
    assert.equal(await atEdge(),true);
    snapshot(10);
    await rows.nth(9).waitFor();
    assert.equal(await atEdge(),true);
    assert.equal(await page.getByText("Legacy card must stay out of the Flow").count(),0);
    await viewport.hover();
    await page.mouse.wheel(0,220);
    await live.waitFor();
    assert.equal(await atEdge(),false);
    await viewport.focus();
    await page.keyboard.press("Home");
    await live.waitFor({state:"hidden"});
    assert.equal(await atEdge(),true);
    if(process.env.DJC_FLOW_SCREENSHOT) await page.screenshot({path:process.env.DJC_FLOW_SCREENSHOT});
    snapshot(11);
    await rows.nth(10).waitFor();
    const newestTop=(await rows.first().boundingBox()).y;
    const paneTop=(await viewport.boundingBox()).y;
    assert.ok(newestTop>=paneTop && newestTop<paneTop+12);
    cards[0].flow_expires_at=new Date(Date.now()-1000).toISOString();
    snapshot(11);
    await page.waitForFunction(()=>document.querySelectorAll("#flow-cards > .flow-card").length===10);
    snapshot(11,"next-recording");
    await contributionCover.waitFor({state:"detached"});
    const retainedCover=rows.locator('a[href="'+previousTrack+'"] img');
    assert.equal(await retainedCover.getAttribute("src"),previousUrl);
    assert.equal(await rows.locator(".flow-artwork").count(),1);
    cards[6].flow_expires_at=new Date(Date.now()-1000).toISOString();
    snapshot(11,"next-recording");
    await retainedCover.waitFor({state:"detached"});

    const horizon={valid_until:new Date(Date.now()+10000).toISOString(),
      sections:[{title:"Direction",text:"Keep the musical thread steady."}]};
    const session={session_id:"session",runtime_state:"active",locale:"es"};
    snapshot(11,"next-recording","playing",undefined,{session,horizon});
    const horizonCard=page.locator("#horizon-card");
    await horizonCard.waitFor({state:"visible"});
    assert.equal(await horizonCard.locator("h2,h3,#horizon-notice").count(),0);
    assert.equal(await horizonCard.locator("#horizon-sections p").textContent(),horizon.sections[0].text);
    const horizonText=await horizonCard.locator("#horizon-sections p").elementHandle();
    snapshot(11,"next-recording","playing",{output_label:"Stable horizon",volume_percent:37},
      {session,horizon:{...horizon,valid_until:new Date(Date.now()+12000).toISOString()}});
    await page.waitForFunction(()=>document.querySelector("#display-speaker-label").textContent==="Stable horizon");
    assert.equal(await horizonText.evaluate(node=>node===document.querySelector("#horizon-sections p")),true);
    assert.equal(await page.locator("#renderer-build-label").textContent(),"Versión de VibeCast");
    assert.equal(await rows.first().locator(".flow-kind").textContent(),"Álbum");
    assert.equal(await rows.first().locator("p").textContent(),cards[10].content);
    const horizonPreview={current_item_id:"next-recording",expires_at:new Date(Date.now()+3000).toISOString(),
      text:"A continuación en el programa: “Upcoming recording” de Next artist.",
      track:{item_id:"upcoming",title:"Upcoming recording",artist:"Next artist",source_url:previousTrack},
      artwork:{item_id:"upcoming",reference:"c".repeat(64),expires_at:new Date(Date.now()+6000).toISOString()}};
    const previewCard=page.locator("#horizon-preview");
    snapshot(11,"next-recording","playing",undefined,{session,horizon,horizon_preview:horizonPreview});
    await previewCard.waitFor({state:"visible"});
    const previewCover=previewCard.locator("#horizon-preview-art");
    await previewCover.waitFor({state:"visible"});
    assert.match(await previewCover.getAttribute("src"),/^blob:/);
    const artworkCard=previewCard.locator("#horizon-preview-artwork");
    const artworkStyle=await artworkCard.evaluate(node=>{
      const {backgroundImage,borderTopWidth}=getComputedStyle(node);
      return {backgroundImage,borderTopWidth};
    });
    assert.notEqual(artworkStyle.backgroundImage,"none");
    assert.ok(parseFloat(artworkStyle.borderTopWidth)>0);
    const artworkBounds=await artworkCard.boundingBox(), previewBounds=await previewCover.boundingBox();
    assert.ok(previewBounds.x>artworkBounds.x && previewBounds.y>artworkBounds.y);
    assert.ok(Math.abs(previewBounds.width-previewBounds.height)<1);
    assert.equal(await previewCard.locator("h2").textContent(),"A continuación");
    assert.equal(await previewCard.locator("strong").textContent(),"Upcoming recording");
    assert.equal(await previewCard.locator("#horizon-preview-text").textContent(),horizonPreview.text);
    assert.equal(await previewCard.locator("a img").getAttribute("alt"),"Spotify");
    assert.equal(await rows.getByText("Upcoming recording").count(),0);
    await previewCard.waitFor({state:"hidden"});
    assert.equal(await artworkCard.evaluate(node=>node.hidden),true);
    assert.equal(await previewCover.getAttribute("src"),null);
    const freshPreview={...horizonPreview,expires_at:new Date(Date.now()+10000).toISOString()};
    snapshot(11,"next-recording","playing",undefined,{session,horizon_preview:freshPreview});
    await previewCard.waitFor({state:"visible"});
    snapshot(11,"different-recording","playing",undefined,{session,horizon_preview:freshPreview});
    await previewCard.waitFor({state:"hidden"});
    snapshot(11,"next-recording","playing",undefined,{session,
      horizon:{...horizon,valid_until:new Date(Date.now()-1000).toISOString()}});
    await horizonCard.waitFor({state:"hidden"});
    assert.equal(await horizonCard.locator("#horizon-sections").textContent(),"");
    // These declared status events test rendering, independently of the
    // authenticated guest-count/lease producer tests. They grant no authority.
    const liveStatus=detail=>page.evaluate(detail=>window.dispatchEvent(new CustomEvent(
      "djconnect-live-status",{detail:{live_enabled:true,guest_count:3,...detail}})),detail);
    const view=dynamics=>({mode:"vibescape",mood:"groove",persona:"radio_dj",dynamics});
    await liveStatus({view:view(0)});
    const receiverBrand=page.locator("#receiver-brand-label");
    assert.equal(await receiverBrand.textContent(),"VibeCast Party");
    assert.equal((await page.locator("#live-indicator").innerText()).trim(),"");
    assert.equal(await page.locator(".session-panels").evaluate(node=>getComputedStyle(node).display),"none");
    const firstScene=await page.locator("#vibescape-scene").evaluate(node=>node.toDataURL());
    await liveStatus({view:view(1)});
    const secondScene=await page.locator("#vibescape-scene").evaluate(node=>node.toDataURL());
    assert.notEqual(firstScene,secondScene,"Confirmed dynamics must affect the scene even with reduced motion");
    const frames=new Set();
    for(const persona of ["home_dj","radio_dj","club_dj","festival_dj"]){
      await liveStatus({view:{...view(.5),persona}});
      frames.add(await page.locator("#vibescape-scene").evaluate(node=>node.toDataURL()));
    }
    assert.equal(frames.size,4,"DJ characters must render four distinct scenes under the same mood");
    await liveStatus({view:{...view(.5),mode:"flow"}});
    await viewport.waitFor({state:"visible"});
    assert.equal(await page.locator("#time").textContent(),"1:00 / 4:00");
    await page.evaluate(()=>{
      window.originalCanvasContext=HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext=function(){return null;};
    });
    await liveStatus({view:view(.5)});
    await viewport.waitFor({state:"visible"});
    assert.equal(await page.locator("#vibescape-scene").isHidden(),true);
    await page.evaluate(()=>{HTMLCanvasElement.prototype.getContext=window.originalCanvasContext;});
    await liveStatus({view:{...view(.5),mode:"flow"}});
    const reaction={event_id:"declared-reaction",playback_item_id:"next-recording",emotion:"heart",
      expires_at:new Date(Date.now()+5000).toISOString()};
    await liveStatus({reactions:[reaction]});
    assert.equal(await page.locator(".live-reaction").count(),1);
    await liveStatus({reactions:[reaction]});
    assert.equal(await page.locator(".live-reaction").count(),1);
    await liveStatus({live_enabled:false,reactions:[]});
    assert.equal(await receiverBrand.textContent(),"DJConnect VibeCast");
    assert.equal(await page.locator(".live-reaction").count(),0);
    assert.equal(await page.locator("#live-guest-count").isHidden(),true);
    await viewport.waitFor({state:"visible"});
    await liveStatus({reactions:[reaction]});
    assert.equal(await page.locator(".live-reaction").count(),1);
    const presentation={session,session_presentation:{mood:"groove",persona:"radio_dj",presence:"presenter"}};
    snapshot(11,"next-recording","playing",undefined,{...presentation,view:{...view(.5),mode:"flow",revision:3}});
    await page.waitForFunction(()=>document.querySelector("#display-view-status").textContent==="Flow");
    const [statusBox,moodBox]=await Promise.all([modeStatus,moodIcon].map(control=>control.boundingBox()));
    assert.ok(statusBox && moodBox && statusBox.x+statusBox.width<=moodBox.x);
    assert.ok(statusBox.y < moodBox.y + moodBox.height && moodBox.y < statusBox.y + statusBox.height);
    assert.equal(await page.getByRole("button",{name:/^(Flow|VibeScape)$/}).count(),0);
    snapshot(11,"next-recording","playing",undefined,{...presentation,view:{...view(.5),revision:4}});
    await page.waitForFunction(()=>document.querySelector("#display-view-status").textContent==="VibeScape");
    await liveStatus({view:{...view(.5),mode:"flow",revision:3}});
    assert.equal(await modeStatus.textContent(),"VibeScape");
    await liveStatus({view:{...view(.5),mode:"flow",revision:5}});
    assert.equal(await modeStatus.textContent(),"Flow");
    const returnToLive=page.getByRole("button",{name:"Volver al directo"});
    await page.clock.install();
    await viewport.hover();
    await page.mouse.wheel(0,220);
    await returnToLive.waitFor();
    await page.clock.fastForward(10000);
    await viewport.press("ArrowDown");
    await page.clock.fastForward(14500);
    assert.equal(await returnToLive.isVisible(),true);
    await page.clock.fastForward(650);
    await returnToLive.waitFor({state:"hidden"});
    assert.equal(await atEdge(),true);

    await page.evaluate(()=>window.dispatchEvent(new Event("djconnect-display-clear")));
    await liveStatus({});
    assert.equal(await receiverBrand.textContent(),"DJConnect VibeCast");
    assert.equal(await page.locator("#live-guest-count").textContent(),"");
    assert.equal(await page.locator("#live-guest-count").isHidden(),true);
    assert.equal(await page.locator(".live-reaction").count(),0);
    allowAdmission=false;
    socket.close({code:1008});
    await viewport.waitFor({state:"hidden"});
    await modeStatus.waitFor({state:"hidden"});
    await waitingBrand.waitFor({state:"visible"});
    await languagePicker.waitFor({state:"visible"});
    assert.equal(await rows.count(),0);
    await albumCover.waitFor({state:"hidden"});
    assert.equal(await albumCover.getAttribute("src"),null);
    console.log(engine.name()+": Flow, artwork stability, Horizon, Vibescape fallback/dynamics, reactions and withdrawal PASS");
  } catch(error) {
    console.error("Original browser failure:",error.message);
    if(page && process.env.DJC_FLOW_FAILURE) {
      await page.screenshot({path:process.env.DJC_FLOW_FAILURE+"-"+engine.name()+".png",timeout:1000}).catch(()=>{});
      console.error(await page.evaluate(()=>({state:document.querySelector("#state")?.textContent,
        rows:document.querySelectorAll("#flow-cards > .flow-card").length,
        bodyClass:document.body.className,flowHidden:document.querySelector("#shared-flow")?.hidden})));
    }
    throw error;
  } finally {
    await browser.close();
  }
}
(async()=>{for(const engine of [chromium,webkit].filter(e=>!process.env.DJC_BROWSER || e.name()===process.env.DJC_BROWSER))await main(engine);})()
  .catch(error=>{console.error(error);process.exitCode=1;});

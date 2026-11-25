/* One B host lifecycle with explicit same-origin and closed Cast transports. */
window.DJCDisplayHost=function(transport){
  "use strict";
  transport=transport || {};
  const cast=transport.mode==="cast";
  const apiOrigin=cast ? transport.apiOrigin : location.origin;
  const displayURL=action=>apiOrigin+"/api/djconnect/v1/"+(cast?"cast/":"display/")+action;
  const participationURL=action=>apiOrigin+"/api/djconnect/v1/"+(cast?"cast/participation/display/":"participation/display/")+action;
  let bootstrapToken=cast ? transport.bootstrapToken : "";
  const bootstrapDeadline=performance.now()+(cast ? Math.min(30,transport.expiresIn)*1000 : 0);
  if(cast)delete transport.bootstrapToken;
  const listeners=[];
  function listen(target,type,callback){target.addEventListener(type,callback);listeners.push([target,type,callback]);}
  function notify(type,value){if(cast && typeof transport[type]==="function")transport[type](value);}

  const language=(navigator.language || "en").slice(0,2);
  const words={
    en:{approve:"Choose ‘Share VibeCast Screen’ in the app.",retry:"Try again",expired:"This screen’s access has expired. Approve it again in DJConnect.",unavailable:"Cannot reach DJConnect. Check the external HTTPS address and connection.",denied:"Screen access was withdrawn or the session ended.",reconnect:"Reconnecting…",capacity:"Too many screens or requests. Try again shortly."},
    nl:{approve:"Kies 'VibeCast sessie starten' in de app.",retry:"Opnieuw proberen",expired:"De toegang van dit scherm is verlopen. Keur het opnieuw goed in DJConnect.",unavailable:"DJConnect is niet bereikbaar. Controleer het externe HTTPS-adres en de verbinding.",denied:"De schermtoegang is ingetrokken of de sessie is beëindigd.",reconnect:"Opnieuw verbinden…",capacity:"Te veel schermen of verzoeken. Probeer het zo opnieuw."},
    de:{approve:"Wähle in der App „VibeCast-Bildschirm teilen“.",retry:"Erneut versuchen",expired:"Der Zugriff dieses Bildschirms ist abgelaufen. Genehmige ihn erneut in DJConnect.",unavailable:"DJConnect ist nicht erreichbar. Prüfe die externe HTTPS-Adresse und die Verbindung.",denied:"Der Bildschirmzugriff wurde entzogen oder die Session beendet.",reconnect:"Verbindung wird wiederhergestellt…",capacity:"Zu viele Bildschirme oder Anfragen. Versuche es gleich erneut."},
    fr:{approve:"Choisis « Partager l’écran VibeCast » dans l’app.",retry:"Réessayer",expired:"L’accès de cet écran a expiré. Autorisez-le à nouveau dans DJConnect.",unavailable:"DJConnect est inaccessible. Vérifiez l’adresse HTTPS externe et la connexion.",denied:"L’accès de l’écran a été retiré ou la session est terminée.",reconnect:"Reconnexion…",capacity:"Trop d’écrans ou de demandes. Réessayez dans un instant."},
    es:{approve:"Elige «Compartir pantalla VibeCast» en la app.",retry:"Volver a intentar",expired:"El acceso de esta pantalla ha caducado. Autorízala de nuevo en DJConnect.",unavailable:"No se puede acceder a DJConnect. Comprueba la dirección HTTPS externa y la conexión.",denied:"Se ha retirado el acceso de la pantalla o ha terminado la sesión.",reconnect:"Reconectando…",capacity:"Demasiadas pantallas o solicitudes. Vuelve a intentarlo en un momento."}
  };
  const outcomes={
    en:{newcode:"Access could not be confirmed. Request a new code and approve this screen again.",configuration:"Check the external HTTPS address in Home Assistant and reopen this screen from your paired DJConnect app."},
    nl:{newcode:"De toegang kon niet worden bevestigd. Vraag een nieuwe code aan en keur dit scherm opnieuw goed.",configuration:"Controleer het externe HTTPS-adres in Home Assistant en open dit scherm opnieuw vanuit je gekoppelde DJConnect-app."},
    de:{newcode:"Der Zugriff konnte nicht bestätigt werden. Fordere einen neuen Code an und genehmige den Bildschirm erneut.",configuration:"Prüfe die externe HTTPS-Adresse in Home Assistant und öffne den Bildschirm erneut über deine gekoppelte DJConnect-App."},
    fr:{newcode:"L’accès n’a pas pu être confirmé. Demandez un nouveau code et autorisez à nouveau cet écran.",configuration:"Vérifiez l’adresse HTTPS externe dans Home Assistant et rouvrez cet écran depuis votre app DJConnect associée."},
    es:{newcode:"No se ha podido confirmar el acceso. Solicita un código nuevo y vuelve a autorizar esta pantalla.",configuration:"Comprueba la dirección HTTPS externa en Home Assistant y vuelve a abrir esta pantalla desde tu app DJConnect vinculada."}
  };
  const copyLabels={
    en:["Copy pairing code","Code copied","Could not copy code"],
    nl:["Koppelcode kopiëren","Code gekopieerd","Kopiëren is niet gelukt"],
    de:["Kopplungscode kopieren","Code kopiert","Code konnte nicht kopiert werden"],
    fr:["Copier le code d’association","Code copié","Impossible de copier le code"],
    es:["Copiar el código de vinculación","Código copiado","No se pudo copiar el código"]
  };
  const panel=document.getElementById("handoff");
  const selector=document.getElementById("display-language");
  const localeKey="djconnect-vibecast-language";
  const languageLabels={en:"Language",nl:"Taal",de:"Sprache",fr:"Langue",es:"Idioma"};
  const validLocale=value=>typeof value==="string" && /^(en|nl|de|fr|es)$/.test(value);
  let preference="", sessionLocale="", effectiveLocale="", text, handoff;
  if(!cast){
    try {
      const saved=window.localStorage.getItem(localeKey);
      if(validLocale(saved))preference=saved;
    }catch(_){ /* Keep this page usable when browser storage is blocked. */ }
  }
  function selectLocale(locale){
    sessionLocale=validLocale(locale) ? locale : "";
    const selected=preference || sessionLocale || (validLocale(language) ? language : "en");
    if(selected===effectiveLocale)return;
    effectiveLocale=selected;
    text={...words[selected],...outcomes[selected]};
    selector.value=selected;
    selector.setAttribute("aria-label",languageLabels[selected]);
    window.dispatchEvent(new CustomEvent("djconnect-display-locale",{detail:selected}));
    if(handoff && !panel.hidden)show(...handoff);
  }
  listen(selector,"change",()=>{
    if(selector.hidden){selector.value=effectiveLocale;return;}
    if(!validLocale(selector.value))return;
    preference=selector.value;
    if(!cast){
      try{window.localStorage.setItem(localeKey,preference);}catch(_){ /* Memory-only preference. */ }
    }
    selectLocale(sessionLocale);
  });
  selectLocale("");
  selector.hidden=false;
  function failureText(error,collecting=false){
    if(error.status===429)return "capacity";
    if(error.code==="display_external_url_unavailable" || error.code==="display_tls_required" || error.code==="display_origin_denied")return "configuration";
    if(error.status===410 || error.code==="display_lease_expired")return "expired";
    if(collecting && (error.status===404 || !error.status))return "newcode";
    if([401,403,404,409].includes(error.status))return "denied";
    return "unavailable";
  }
  let generation=0, claim=null, grant=null, socket=null, stopped=false, sequence=0;
  let lease=0, claimDeadline=0, renewalBusy=false, connectionGeneration=0;
  const timers=new Set(), requests=new Set();
  const now=()=>performance.now();
  const nonce=()=>{
    const bytes=new Uint8Array(32); crypto.getRandomValues(bytes);
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
  };
  function claimRequestId(){
    try{
      const state=window.history.state;
      const previous=state?.vibeCastClaimRequestId;
      if(typeof previous==="string" && /^[A-Za-z0-9_-]{43}$/.test(previous))return previous;
      const id=nonce();
      window.history.replaceState({...state,vibeCastClaimRequestId:id},"");
      return id;
    }catch(_){return null;}
  }
  function later(fn,delay){const timer=setTimeout(()=>{timers.delete(timer);fn();},delay);timers.add(timer);return timer;}
  function clearContent(){clearParticipation();clearArtwork();window.dispatchEvent(new Event("djconnect-display-clear"));}
  let claimCanResume=false;
  const artwork=new Map();
  let wantedArtwork=new Map(), artworkBusy=false;
  function publishArtwork(){
    window.dispatchEvent(new CustomEvent("djconnect-display-artwork",{
      detail:[...artwork.values()].filter(cover=>cover.url)}));
  }
  function removeArtwork(reference){
    const cover=artwork.get(reference);
    if(!cover)return;
    artwork.delete(reference);
    cover.controller.abort();clearTimeout(cover.timer);
    if(cover.url)URL.revokeObjectURL(cover.url);
  }
  function clearArtwork(){
    wantedArtwork.clear();
    for(const reference of artwork.keys())removeArtwork(reference);
    publishArtwork();
  }
  const participationLabels={en:"Scan to join the music conversation",nl:"Scan om mee te praten over de muziek",de:"Scannen und über die Musik mitreden",fr:"Scanne pour parler de la musique",es:"Escanea para hablar de la música"};
  const guestTrackIntroMs=20000;
  let guestPanel=null,guestQR=null,guestManual=null,guestCode=null,guestAddress=null,guestPollGeneration=-1;
  let guestQRDeadline=0,guestQRTimer=null,guestPlayback=null,guestTrackDeadline=0,participationRevision=0;
  let sharedPhoto=null,sharedPhotoWanted=null,failedSharedPhotoRevision=null;
  function clearSharedPhoto(){
    sharedPhotoWanted=null;
    if(sharedPhoto){sharedPhoto.controller.abort();clearTimeout(sharedPhoto.timer);if(sharedPhoto.url)URL.revokeObjectURL(sharedPhoto.url);sharedPhoto=null;}
    window.dispatchEvent(new CustomEvent("djconnect-shared-photo",{detail:null}));
  }
  async function updateSharedPhoto(focus,g,started){
    const photo=focus.photo;
    if(!focus.focus_revision || !photo || !/^[a-f0-9]{64}$/.test(photo.revision)){clearSharedPhoto();return;}
    if(failedSharedPhotoRevision===focus.focus_revision || (sharedPhoto && sharedPhoto.revision===focus.focus_revision))return;
    clearSharedPhoto();
    const controller=new AbortController(), pending={revision:focus.focus_revision,controller,url:null,timer:null};
    sharedPhoto=pending;sharedPhotoWanted=focus.focus_revision;requests.add(controller);
    const until=Math.min(lease,started+Math.min(30,focus.expires_in)*1000);
    pending.timer=setTimeout(clearSharedPhoto,Math.max(1,until-now()));
    const timeout=setTimeout(()=>controller.abort(),20000);
    try{
      const response=await fetch(participationURL("focus-photo"),{method:"POST",credentials:"omit",cache:"no-store",redirect:"error",
        headers:{"Content-Type":"application/json",Authorization:"Bearer "+grant.grant_token},
        body:JSON.stringify({contract_version:1,...binding(),focus_revision:focus.focus_revision}),signal:controller.signal});
      const size=Number(response.headers.get("Content-Length")),mime=response.headers.get("Content-Type");
      if(!response.ok || !(size>0 && size<=2097152) || !["image/jpeg","image/png"].includes(mime))throw new Error("photo unavailable");
      const bytes=await response.arrayBuffer();if(bytes.byteLength!==size)throw new Error("photo size");
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(b=>b.toString(16).padStart(2,"0")).join("");
      if(hash!==photo.revision || g!==generation || expired() || now()>=until || sharedPhoto!==pending || sharedPhotoWanted!==focus.focus_revision)return;
      pending.url=URL.createObjectURL(new Blob([bytes],{type:mime}));
      window.dispatchEvent(new CustomEvent("djconnect-shared-photo",{detail:{focus_revision:focus.focus_revision,
        url:pending.url,photo,locale:effectiveLocale}}));
    }catch(_){if(sharedPhoto===pending){failedSharedPhotoRevision=focus.focus_revision;clearSharedPhoto();}}
    finally{clearTimeout(timeout);requests.delete(controller);}
  }
  function hideGuestInvitation(){
    guestQRDeadline=0;
    clearTimeout(guestQRTimer);
    guestQRTimer=null;
    if(!guestPanel)return;
    guestPanel.hidden=true;guestQR.removeAttribute("src");
    guestCode.textContent="";guestAddress.textContent="";guestManual.hidden=true;
  }
  function renderGuestInvitation(){
    clearTimeout(guestQRTimer);
    guestQRTimer=null;
    if(!guestPanel || !guestQRDeadline)return;
    const time=now();
    if(expired() || time>=guestQRDeadline){hideGuestInvitation();return;}
    const playing=guestPlayback?.state==="playing" && guestPlayback.item_id;
    const visibleUntil=Math.min(guestQRDeadline,playing ? guestTrackDeadline : Infinity);
    guestPanel.hidden=!guestPlayback || time>=visibleUntil;
    const nextDeadline=guestPanel.hidden ? guestQRDeadline : visibleUntil;
    guestQRTimer=setTimeout(renderGuestInvitation,Math.max(1,nextDeadline-time));
  }
  function updateGuestPlayback(snapshot){
    const next=snapshot.playback || {};
    if(next.state==="playing" && next.item_id){
      if(guestPlayback?.item_id!==next.item_id || guestPlayback.state!=="playing"){
        const position=Number.isFinite(next.position_ms) ? Math.max(0,next.position_ms) : 0;
        guestTrackDeadline=now()+Math.max(0,guestTrackIntroMs-position);
      }
    }
    guestPlayback=next;
    renderGuestInvitation();
  }
  function clearParticipation(){
    participationRevision++;
    guestPlayback=null;
    guestTrackDeadline=0;
    failedSharedPhotoRevision=null;clearSharedPhoto();
    hideGuestInvitation();
    window.dispatchEvent(new CustomEvent("djconnect-shared-focus",{detail:{focused_moment_id:null}}));
  }
  async function participationPost(action, fields={}){
    const controller=new AbortController();requests.add(controller);
    const timeout=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch(participationURL(action),{method:"POST",credentials:"omit",cache:"no-store",redirect:"error",
        headers:{"Content-Type":"application/json",Authorization:"Bearer "+grant.grant_token},
        body:JSON.stringify({contract_version:1,...binding(),...fields}),signal:controller.signal});
      if(!response.ok)throw new Error("participation unavailable");
      const raw=await response.text();if(raw.length>96000)throw new Error("size");return JSON.parse(raw);
    }finally{clearTimeout(timeout);requests.delete(controller);}
  }
  listen(window,"djconnect-display-return",()=>{if(!expired())void participationPost("return").catch(()=>{});});
  async function participationPoll(g){
    if(g!==generation || expired())return;
    const started=now(), revision=participationRevision;
    const current=()=>g===generation && revision===participationRevision && !expired() && guestPlayback!==null;
    try{
      if(!current())return;
      const focus=await participationPost("focus");
      if(!current())return;
      window.dispatchEvent(new CustomEvent("djconnect-shared-focus",{detail:focus}));
      window.dispatchEvent(new CustomEvent("djconnect-live-status",{detail:focus}));
      void updateSharedPhoto(focus,g,started);
      if(focus.live_enabled!==true){hideGuestInvitation();return;}
      const invitation=await participationPost("invitation");
      if(!current() || !(invitation.expires_in>0))return;
      if(!/^data:image\/svg\+xml;base64,[A-Za-z0-9+/=]+$/.test(invitation.qr_data_uri))return;
      if(!guestPanel){
        guestPanel=document.createElement("aside");guestPanel.className="guest-participation";guestPanel.hidden=true;
        guestQR=document.createElement("img");guestQR.width=128;guestQR.height=128;
        guestManual=document.createElement("div");guestManual.className="guest-manual-entry";guestManual.hidden=true;
        guestCode=document.createElement("strong");guestAddress=document.createElement("span");
        guestManual.append(guestCode,guestAddress);
        guestPanel.append(guestManual,guestQR);document.body.append(guestPanel);
      }
      let manualAddress="";
      if(/^[2-9A-HJ-NP-Z]{4}(?:-[2-9A-HJ-NP-Z]{4}){2}$/.test(invitation.manual_code)){
        try{
          const address=new URL(invitation.manual_origin);
          if(address.protocol==="https:" && address.origin===invitation.manual_origin)manualAddress=address.host;
        }catch(_){}
      }
      guestCode.textContent=manualAddress?invitation.manual_code:"";
      guestAddress.textContent=manualAddress;guestManual.hidden=!manualAddress;
      guestQR.alt=participationLabels[effectiveLocale]||participationLabels.en;
      if(guestQR.getAttribute("src")!==invitation.qr_data_uri)guestQR.src=invitation.qr_data_uri;
      guestQRDeadline=started+invitation.expires_in*1000;
      renderGuestInvitation();
    }catch(_){if(current())hideGuestInvitation();}
    finally{if(g===generation && !expired())later(()=>participationPoll(g),3000);}
  }
  function updateArtwork(snapshot){
    const wanted=new Map();
    function add(cover,itemId,deadline=Infinity){
      const until=Math.min(Date.parse(cover?.expires_at),deadline);
      if(!cover || !itemId || cover.item_id!==itemId ||
         !/^[a-f0-9]{64}$/.test(cover.reference) || !(until>Date.now()))return;
      const existing=wanted.get(cover.reference);
      if(!existing || existing.until<until)wanted.set(cover.reference,{...cover,until});
    }
    add(snapshot.artwork,snapshot.playback?.item_id);
    const preview=snapshot.horizon_preview;
    if(preview && snapshot.playback?.state==="playing" && preview.current_item_id===snapshot.playback.item_id){
      add(preview.artwork,preview.track?.item_id,Date.parse(preview.expires_at));
    }
    if(Array.isArray(snapshot.shared_flow)){
      for(const item of snapshot.shared_flow.slice(-12).reverse()){
        if(item)add(item.artwork,item.playback_item_id,Date.parse(item.flow_expires_at));
      }
    }
    if(Array.isArray(snapshot.observed_playback)){
      for(const item of snapshot.observed_playback.slice(-12).reverse()){
        if(item)add(item.artwork,item.playback_item_id,Date.parse(item.expires_at));
      }
    }
    wantedArtwork=wanted;
    let changed=false;
    for(const [reference,cover] of artwork){
      if(!wanted.has(reference) || wanted.get(reference).item_id!==cover.item_id){
        removeArtwork(reference);
        changed=true;
      }else if(wanted.get(reference).until!==cover.until){
        // A fresh qualified deadline for the same image is not a pixel change.
        // Keep both the in-flight read and the decoded blob; only re-arm expiry.
        cover.until=wanted.get(reference).until;
        scheduleArtworkExpiry(cover);
      }
    }
    if(changed)publishArtwork();
    void fetchArtwork();
  }
  function scheduleArtworkExpiry(cover){
    clearTimeout(cover.timer);
    cover.timer=setTimeout(()=>{
      if(artwork.get(cover.reference)!==cover)return;
      removeArtwork(cover.reference);
      publishArtwork();
    },Math.max(0,cover.until-Date.now()));
  }
  async function fetchArtwork(){
    if(artworkBusy)return;
    artworkBusy=true;
    try{
      const attempted=new Set();
      let desired=wantedArtwork;
      while(!expired()){
        if(desired!==wantedArtwork){desired=wantedArtwork;attempted.clear();}
        const cover=[...desired.values()].find(value=>
          !attempted.has(value.reference) && !artwork.has(value.reference) && value.until>Date.now());
        if(!cover)break;
        attempted.add(cover.reference);
        const controller=new AbortController();
        const pending={...cover,controller,url:null};
        artwork.set(cover.reference,pending);
        scheduleArtworkExpiry(pending);
        const timeout=setTimeout(()=>controller.abort(),10000);
        try{
          const response=await fetch(displayURL("artwork"),{method:"POST",credentials:"omit",cache:"no-store",redirect:"error",
            headers:{"Content-Type":"application/json",Authorization:"Bearer "+grant.grant_token},
            body:JSON.stringify({contract_version:1,...binding(),reference:cover.reference}),signal:controller.signal});
          const size=Number(response.headers.get("Content-Length")),mime=response.headers.get("Content-Type");
          if(!response.ok || !(size>0 && size<=256000) || !["image/jpeg","image/png"].includes(mime))throw new Error("artwork");
          const blob=await response.blob();
          if(artwork.get(cover.reference)!==pending || expired() || pending.until<=Date.now())continue;
          if(blob.size!==size)throw new Error("artwork");
          pending.url=URL.createObjectURL(blob);
          publishArtwork();
        }catch(_){
          if(artwork.get(cover.reference)===pending)removeArtwork(cover.reference);
        }finally{clearTimeout(timeout);}
      }
    }finally{artworkBusy=false;}
  }
  function show(message,code="",retry=false){
    handoff=[message,code,retry];
    const pending=code===null;
    panel.textContent="";
    const caption=document.createElement("span");
    caption.textContent=text[message];
    if(pending)caption.className="handoff-placeholder";
    panel.append(caption);
    if(code || pending){
      const block=document.createElement("div");
      block.className=pending?"handoff-code handoff-placeholder":"handoff-code";
      const value=document.createElement("strong");
      value.textContent=code ?? "\u00a0";
      if(code)value.setAttribute("aria-label",code.split("").join(" "));
      block.append(value);
      if(code && navigator.clipboard?.writeText){
        const [copy,copied,failed]=copyLabels[effectiveLocale];
        const button=document.createElement("button");
        button.type="button";
        button.className="handoff-copy";
        button.title=copy;
        button.setAttribute("aria-label",copy);
        button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 6H7a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-2M9 4h6v4H9z"/><path class="copy-check" d="m9 14 2 2 4-4"/></svg>';
        button.onclick=async()=>{
          if(!claim || now()>=claimDeadline)return;
          try{
            await navigator.clipboard.writeText(code);
            button.classList.add("copied");
            button.title=copied;
          }catch(_){button.title=failed;}
          button.setAttribute("aria-label",button.title);
        };
        block.append(button);
      }
      panel.append(block);
    }
    if(retry){
      const button=document.createElement("button");
      button.type="button";button.className="handoff-retry";button.textContent=text.retry;
      button.onclick=()=>begin();panel.append(button);
    }
    panel.hidden=false;
  }
  function cancelWork(){
    generation++; timers.forEach(clearTimeout);timers.clear();requests.forEach(c=>c.abort());requests.clear();
    if(socket){const old=socket;socket=null;old.onclose=null;old.close();}
    renewalBusy=false;clearContent();
  }
  function releaseClaim(){
    if(!claim)return;
    const body=JSON.stringify({contract_version:1,...claim});
    claim=null;
    // Let HA release the code even when a reload destroys this page.
    void fetch(displayURL("cancel"),{method:"POST",credentials:"omit",cache:"no-store",
      redirect:"error",keepalive:true,headers:{"Content-Type":"application/json"},body}).catch(()=>{});
  }
  function terminal(message){if(cast)stop();else{cancelWork();releaseClaim();grant=null;lease=0;selector.hidden=false;}show(message,"",!cast);notify("onTerminal",message);}
  async function post(action,body,bearer=""){
    const controller=new AbortController(), started=now();requests.add(controller);
    // Bounds the whole browser DNS/TLS/request path, distinct from HA's fixed
    // five-second send budget. Original authority deadlines never move for it.
    const timeout=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch(displayURL(action),{method:"POST",credentials:"omit",cache:"no-store",redirect:"error",
        headers:{"Content-Type":"application/json",...(bearer?{Authorization:"Bearer "+bearer}:{})},
        body:JSON.stringify({contract_version:1,...body}),signal:controller.signal});
      const bytes=await response.text();if(bytes.length>131072)throw new Error("oversized");
      const value=JSON.parse(bytes);
      if(!response.ok || value.success!==true){const failure=new Error("display_unavailable");failure.status=response.status;failure.code=value.error;throw failure;}
      return {value,started};
    }finally{clearTimeout(timeout);requests.delete(controller);}
  }
  function binding(){return {issuer_epoch:grant.issuer_epoch,display_id:grant.display_id};}
  function expired(){return !grant || now()>=lease;}
  function watchLease(g){
    later(()=>{if(g!==generation || !grant)return;if(expired())void begin();else watchLease(g);},Math.max(1,Math.min(1000,lease-now())));
  }
  async function renew(g,renewSequence){
    if(g!==generation || expired() || renewalBusy)return;
    if(navigator.onLine===false){later(()=>renew(g,renewSequence),2000);return;}
    renewalBusy=true;
    try{
      const {value,started}=await post("renew",{...binding(),renew_sequence:renewSequence},grant.grant_token);
      if(g!==generation || expired() || navigator.onLine===false)return;
      if(value.lease_revision!==renewSequence || !(value.lease_expires_in>0 && value.lease_expires_in<=60))return terminal("denied");
      sequence=renewSequence;lease=started+value.lease_expires_in*1000;
      later(()=>renew(g,sequence+1),20000);
    }catch(error){
      if(g!==generation)return;
      if(error.code==="display_grant_invalid" || error.code==="display_lease_expired")return begin();
      if([401,403,404,409,410].includes(error.status))return terminal(failureText(error));
      clearContent();show("reconnect");later(()=>renew(g,renewSequence),2000);
    }finally{if(g===generation)renewalBusy=false;}
  }
  function connect(g){
    if(g!==generation || expired() || document.hidden || navigator.onLine===false)return;
    const current=new WebSocket(apiOrigin.replace(/^https:/,"wss:")+"/api/djconnect/v1/"+(cast?"cast/live":"display/live"));socket=current;
    current.onopen=()=>{
      if(g!==generation || expired()){current.close();return;}
      current.send(JSON.stringify({type:"authenticate",contract_version:1,...binding(),grant_token:grant.grant_token,connection_nonce:nonce()}));
    };
    current.onmessage=({data})=>{
      if(g!==generation || current!==socket || expired() || document.hidden || navigator.onLine===false)return;
      try{
        if(typeof data!=="string" || data.length>131072)throw new Error("frame");
        const frame=JSON.parse(data), snapshot=frame.snapshot;
        if(frame.type!=="snapshot" || frame.contract_version!==1 || !snapshot || snapshot.issuer_epoch!==grant.issuer_epoch
            || snapshot.display_id!==grant.display_id || snapshot.share_id!==grant.share_id || snapshot.share_generation!==grant.share_generation
            || snapshot.session_id!==grant.session_id || !Number.isSafeInteger(frame.connection_generation)
            || frame.connection_generation<connectionGeneration)throw new Error("binding");
        connectionGeneration=frame.connection_generation;
        if(snapshot.session && snapshot.session.session_id===grant.session_id
            && snapshot.session.runtime_state==="active")selectLocale(snapshot.session.locale);
        // The renderer receives only the Core's explicit shared allowlist.
        notify("onSnapshot",{issuer_epoch:snapshot.issuer_epoch,display_id:snapshot.display_id,
          share_id:snapshot.share_id,share_generation:snapshot.share_generation,session_id:snapshot.session_id,
          connection_generation:frame.connection_generation});
        window.dispatchEvent(new CustomEvent("djconnect-display-snapshot",{detail:snapshot}));
        updateGuestPlayback(snapshot);
        void updateArtwork(snapshot);panel.hidden=true;
        if(guestPollGeneration!==g){guestPollGeneration=g;void participationPoll(g);}
      }catch(_){terminal("denied");}
    };
    current.onclose=event=>{
      if(g!==generation || socket!==current)return;socket=null;
      if(expired() || event.code===1008)return begin();
      clearContent();
      show("reconnect");later(()=>connect(g),1500);
    };
    current.onerror=()=>{if(current===socket)current.close();};
  }
  async function collect(g){
    if(g!==generation || !claim)return;
    if(now()>=claimDeadline)return begin();
    try{
      const {value,started}=await post("collect",claim);
      if(g!==generation || !claim)return;
      if(now()>=claimDeadline)return begin();
      if(value.state==="pending"){later(()=>collect(g),1000);return;}
      if(value.state!=="admitted" || typeof value.grant_token!=="string" || !/^djcd_[A-Za-z0-9_-]{43}$/.test(value.grant_token)
          || !(value.lease_expires_in>0 && value.lease_expires_in<=60) || !value.capabilities || value.capabilities.owner_controls!==false
          || value.capabilities.session_end!==false)throw new Error("contract");
      grant=value;claim=null;
      selector.hidden=true;
      lease=started+value.lease_expires_in*1000;sequence=0;connectionGeneration=0;
      if(expired())return terminal("expired");
      notify("onAdmitted",{issuer_epoch:value.issuer_epoch,display_id:value.display_id,
        share_id:value.share_id,share_generation:value.share_generation,session_id:value.session_id});
      selectLocale(value.session_locale);
      show("reconnect");watchLease(g);connect(g);later(()=>renew(g,1),20000);
    }catch(error){
      if(g!==generation)return;
      if(now()>=claimDeadline)return begin();
      terminal(failureText(error,true));
    }
  }
  async function begin(allowCapacityRetry=true){
    if(cast && (!bootstrapToken || !(performance.now()<bootstrapDeadline)))return terminal("newcode");
    stopped=false;selectLocale("");cancelWork();
    // The server decides when the original window ends, even if our timer fires early.
    if(claimCanResume)claim=null;else releaseClaim();
    grant=null;lease=0;selector.hidden=false;const g=generation;
    if(location.protocol!=="https:" || location.search || location.hash || !crypto.getRandomValues)return show("unavailable","",true);
    show("approve",null);
    try{
      const requestId=cast ? null : claimRequestId();
      claimCanResume=Boolean(requestId);
      const browser_nonce=nonce();
      const bearer=bootstrapToken;bootstrapToken="";
      const {value,started}=await post("claim",requestId ? {browser_nonce,request_id:requestId} : {browser_nonce},cast?bearer:"");
      if(g!==generation || stopped)return;
      if(value.contract_version!==1 || !/^[0-9]{6}$/.test(value.code) || !(value.expires_in>0 && value.expires_in<=120))throw new Error("contract");
      claim={issuer_epoch:value.issuer_epoch,claim_id:value.claim_id,claim_secret:value.claim_secret,
        browser_generation:value.browser_generation,browser_nonce};claimDeadline=started+value.expires_in*1000;
      if(cast && ["issuer_epoch","claim_id","claim_secret","browser_generation"].some(key=>
          typeof value[key]!=="string" || !/^[A-Za-z0-9_-]{43}$/.test(value[key])))throw new Error("contract");
      notify("onClaim",{issuer_epoch:value.issuer_epoch,claim_id:value.claim_id,
        browser_generation:value.browser_generation,code:value.code,expires_in:Math.max(0,(claimDeadline-now())/1000),expires_at:value.expires_at});
      show("approve",value.code);
      later(()=>{if(g===generation && claim)void begin();},Math.max(0,claimDeadline-now()));
      void collect(g);
    }catch(error){
      if(g!==generation)return;
      // On reload, the previous page's cancellation can arrive just after the claim.
      if(!cast && allowCapacityRetry && error.code==="display_capacity"){
        later(()=>begin(false),800);
      }else {show(failureText(error),"",!cast);notify("onTerminal",failureText(error));}
    }
  }
  function stop(preserveClaim=false){
    if(cast && grant){
      const body=JSON.stringify({contract_version:1,...binding()});
      void fetch(displayURL("leave"),{method:"POST",credentials:"omit",cache:"no-store",redirect:"error",keepalive:true,
        headers:{"Content-Type":"application/json",Authorization:"Bearer "+grant.grant_token},body}).catch(()=>{});
    }
    stopped=true;selectLocale("");cancelWork();
    if(preserveClaim && claimCanResume)claim=null;else releaseClaim();
    grant=null;lease=0;selector.hidden=false;panel.hidden=true;panel.textContent="";
  }
  listen(window,"pagehide",()=>stop(true));
  listen(window,"djconnect-host-stop",()=>stop());
  listen(window,"offline",()=>{if(grant){clearContent();show("reconnect");requests.forEach(c=>c.abort());if(socket)socket.close();}});
  listen(window,"online",()=>{if(grant && !expired() && !socket)connect(generation);});
  listen(window,"pageshow",event=>{if(event.persisted && stopped)return begin();if(grant){clearContent();if(expired())void begin();else if(socket)socket.close();else connect(generation);}});
  listen(document,"visibilitychange",()=>{if(document.hidden){clearContent();if(socket)socket.close();}else if(grant){if(expired())void begin();else if(!socket)connect(generation);}});
  begin();
  return {stop(){stop();bootstrapToken="";for(const [target,type,callback] of listeners)target.removeEventListener(type,callback);}};
};
if(window.DJC_VIBECAST_MODE!=="cast")window.DJCDisplayHost();

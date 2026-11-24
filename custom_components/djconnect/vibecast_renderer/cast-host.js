/* CAF supplies temporary authority and directed status; Core owns content. */
(() => {
  const namespace="urn:x-cast:com.djconnect.vibecast.v1";
  const errors={en:"Cannot connect this display. Check the secure Home Assistant connection and session version.",nl:"Dit scherm kan niet verbinden. Controleer de beveiligde Home Assistant-verbinding en sessieversie.",de:"Dieses Display kann keine Verbindung herstellen. Prüfe die sichere Home-Assistant-Verbindung und Session-Version.",fr:"Connexion impossible. Vérifiez la connexion sécurisée à Home Assistant et la version de session.",es:"No se puede conectar esta pantalla. Comprueba la conexión segura a Home Assistant y la versión de sesión."};
  if (!window.cast || !window.cast.framework) return;
  const context=window.cast.framework.CastReceiverContext.getInstance();
  const system=window.cast.framework.system;
  let active=null, generation=0, deadline, heartbeat, listening=false;
  const retired=new Set();
  function cancelTimers() {
    if (deadline) window.clearTimeout(deadline); deadline=null;
    if (heartbeat) window.clearTimeout(heartbeat); heartbeat=null;
  }
  function status(state,reason,presentation) {
    if (!active || !active.status || !context.isSystemReady()) return;
    if (state===active.last && presentation===active.presentation && state!=="presenting") return;
    active.last=state; active.presentation=presentation;
    const data={kind:"vibecast_status",version:1,handoff_id:active.id,session_id:active.session,sequence:++active.sequence,state,lease_ms:15000};
    if (reason) data.reason=reason;
    if (presentation) data.presentation=presentation;
    try { context.sendCustomMessage(namespace,active.sender,data); } catch (_) { /* Sender must expire missing status, never assume success. */ }
  }
  function stop(state,reason) {
    status(state || "stopped",reason);
    cancelTimers();
    if (active && active.id) { retired.add(active.id); if (retired.size>32) retired.delete(retired.values().next().value); }
    active=null;
    window.dispatchEvent(new CustomEvent("djconnect-host-stop"));
  }
  function awaitSnapshot() {
    if (!active || !active.status) return;
    if (deadline) window.clearTimeout(deadline);
    const current=active;
    deadline=window.setTimeout(()=>{deadline=null;if(active===current)stop("error","snapshot_timeout");},15000);
  }
  function keepAlive() {
    if (!active || !active.status) return;
    if (heartbeat) window.clearTimeout(heartbeat);
    const current=active;
    heartbeat=window.setTimeout(()=>{heartbeat=null;if(active!==current || !active || active.last!=="presenting")return;status("presenting",null,active.presentation);keepAlive();},5000);
  }
  // New B bridge: the SDK selects a destination; only Core creates authority.
  let displayActive=null;
  function displayStatus(state,reason){
    const current=displayActive;
    if(!current || !context.isSystemReady())return;
    current.state=state;
    if(current.heartbeat){clearTimeout(current.heartbeat);current.heartbeat=null;}
    const {presentation,...binding}=current.binding||{};
    const value={kind:"vibecast_display_status",version:1,handoff_id:current.id,
      sequence:++current.sequence,state,lease_ms:15000,...binding};
    if(state==="presenting" && presentation)value.presentation=presentation;
    if(reason)value.reason=reason;
    try{context.sendCustomMessage(namespace,current.sender,value);}catch(_){/* Missing status must expire. */}
    if(state==="presenting")current.heartbeat=setTimeout(()=>{
      if(displayActive===current && current.state==="presenting")displayStatus("presenting");
    },5000);
  }
  function stopDisplay(state="stopped",reason="host_stop"){
    const current=displayActive;if(!current)return;
    displayStatus(state,reason);displayActive=null;
    if(current.heartbeat)clearTimeout(current.heartbeat);
    if(current.timeout)clearTimeout(current.timeout);
    retired.add(current.id);if(retired.size>32)retired.delete(retired.values().next().value);
    if(current.host)current.host.stop();
    window.dispatchEvent(new CustomEvent("djconnect-display-clear"));
  }
  function displayTimeout(current,seconds){
    if(current.timeout)clearTimeout(current.timeout);
    current.timeout=setTimeout(()=>{if(displayActive===current)stopDisplay("error","snapshot_timeout");},Math.max(1,seconds*1000));
  }
  function sendClaim(current){
    if(displayActive!==current || !current.claim || performance.now()>=current.claimUntil)return;
    try{context.sendCustomMessage(namespace,current.sender,{kind:"vibecast_display_claim",version:1,
      handoff_id:current.id,...current.claim,expires_in:(current.claimUntil-performance.now())/1000});}catch(_){}
  }
  function displayMessage(message,value){
    if(value && value.kind==="vibecast_display_stop"){
      if(displayActive && message.senderId===displayActive.sender && value.version===1
          && value.handoff_id===displayActive.id && Object.keys(value).sort().join(",")==="handoff_id,kind,version")stopDisplay();
      return true;
    }
    if(!value || value.kind!=="vibecast_display_bootstrap")return false;
    if(displayActive){
      if(message.senderId===displayActive.sender && value.handoff_id===displayActive.id)sendClaim(displayActive);
      return true; // Another sender/late bootstrap cannot replace this display.
    }
    if(active && message.senderId!==active.sender)return true;
    try{
      if(Object.keys(value).sort().join(",")!=="bootstrap_token,expires_in,ha_origin,handoff_id,kind,version"
          || value.version!==1 || typeof message.senderId!=="string" || !message.senderId || message.senderId.length>128
          || typeof value.handoff_id!=="string" || !/^[a-f0-9]{32}$/.test(value.handoff_id)
          || retired.has(value.handoff_id) || typeof value.bootstrap_token!=="string"
          || !/^djccb_[A-Za-z0-9_-]{43}$/.test(value.bootstrap_token)
          || typeof value.expires_in!=="number" || !Number.isFinite(value.expires_in)
          || !(value.expires_in>0 && value.expires_in<=30))throw new Error("invalid_bootstrap");
      const origin=new URL(value.ha_origin);
      if(origin.protocol!=="https:" || origin.origin!==value.ha_origin || origin.username || origin.password
          || origin.port || !/^[a-z0-9.-]+$/.test(origin.hostname) || !origin.hostname.includes(".")
          || /^[0-9.]+$/.test(origin.hostname) || origin.hostname.split(".").some(label=>label.startsWith("xn--")))throw new Error("invalid_bootstrap");
      if(active)stop("stopped","superseded");
      const current={id:value.handoff_id,sender:message.senderId,sequence:0,binding:null,
        claim:null,claimUntil:0,heartbeat:null,timeout:null,host:null};
      displayActive=current;
      window.dispatchEvent(new CustomEvent("djconnect-cast-display-mode"));
      displayStatus("receiver_ready");displayTimeout(current,15);
      current.host=window.DJCDisplayHost({mode:"cast",apiOrigin:origin.origin,
        bootstrapToken:value.bootstrap_token,expiresIn:value.expires_in,
        onClaim:claim=>{
          if(displayActive!==current)return;
          current.claim={issuer_epoch:claim.issuer_epoch,claim_id:claim.claim_id,
            browser_generation:claim.browser_generation,code:claim.code,expires_at:claim.expires_at};
          current.claimUntil=performance.now()+Math.min(120,claim.expires_in)*1000;
          displayTimeout(current,Math.min(120,claim.expires_in));
          displayStatus("claim_ready");sendClaim(current);
        },
        onAdmitted:binding=>{
          if(displayActive!==current)return;
          current.claim=null;current.binding=binding;
          displayTimeout(current,15);displayStatus("approved");
        },
        onSnapshot:binding=>{
          if(displayActive!==current)return;
          current.binding=binding;displayStatus("snapshot_accepted");
        },
        onTerminal:reason=>{if(displayActive===current)stopDisplay("error",reason);}
      });
    }catch(_){
      // No active B/legacy view is torn down by an unrelated malformed envelope.
      if(displayActive && displayActive.sender===message.senderId)stopDisplay("error","invalid_bootstrap");
    }
    return true;
  }
  window.addEventListener("djconnect-display-rendered",({detail})=>{
    const current=displayActive,binding=current && current.binding;
    if(!binding || !detail || !Number.isSafeInteger(binding.connection_generation)
        || !["issuer_epoch","display_id","share_id","share_generation","session_id"].every(key=>detail[key]===binding[key]))return;
    if(current.timeout){clearTimeout(current.timeout);current.timeout=null;}
    current.binding={...binding,presentation:detail.presentation==="moment"?"moment":"silence"};
    displayStatus("presenting");
  });
  window.addEventListener("djconnect-display-clear",()=>{
    if(displayActive && displayActive.binding)displayStatus("recovering");
  });
  function receive(message) {
    try {
      const value=typeof message.data === "string" ? JSON.parse(message.data) : message.data;
      if(displayMessage(message,value))return;
      if(displayActive)return; // A legacy view token can never replace/adopt B.
      if (value && value.kind==="vibecast_stop") {
        if (active && active.status && value.version===1 && message.senderId===active.sender && value.handoff_id===active.id && value.session_id===active.session) stop("stopped","host_stop");
        return;
      }
      if (!value || value.kind !== "vibecast_handoff" || value.version !== 1 || typeof value.session_id !== "string" || !value.session_id || value.session_id.length > 128 || typeof value.broadcast_token !== "string" || value.broadcast_token.length < 24 || value.broadcast_token.length > 256) throw new Error("invalid_handoff");
      const ha=new URL(value.ha_url);
      if (ha.protocol !== "https:" || ha.username || ha.password || ha.pathname !== "/" || ha.search || ha.hash) throw new Error("invalid_handoff");
      const wantsStatus=value.status_version!==undefined || value.handoff_id!==undefined;
      if (wantsStatus && (value.status_version!==1 || typeof value.handoff_id!=="string" || !/^[a-f0-9]{32}$/.test(value.handoff_id) || typeof message.senderId!=="string" || !message.senderId || message.senderId.length>128)) throw new Error("invalid_handoff");
      if (wantsStatus && (retired.has(value.handoff_id) || (active && active.id===value.handoff_id))) return;
      if (active) stop("stopped","superseded");
      active={sender:message.senderId,session:value.session_id,id:value.handoff_id,status:wantsStatus,generation:++generation,sequence:0};
      status("receiver_ready"); awaitSnapshot();
      // No sender end-grant or other owner authority crosses this boundary.
      window.dispatchEvent(new CustomEvent("djconnect-cast-legacy-mode"));
      window.dispatchEvent(new CustomEvent("djconnect-handoff", {detail:{ha_url:ha.origin,session_id:value.session_id,broadcast_token:value.broadcast_token,status_generation:generation}}));
    } catch (_) {
      if(displayActive){
        if(message.senderId===displayActive.sender)stopDisplay("error","invalid_bootstrap");
        return;
      }
      // An unrelated sender's malformed message cannot tear down the active view.
      if (active && message.senderId!==active.sender) return;
      stop("error","invalid_handoff");
      document.getElementById("state").textContent=errors[document.documentElement.lang] || errors.en;
    }
  }
  window.addEventListener("djconnect-renderer-status",({detail})=>{
    if (!active || !detail || detail.generation!==active.generation || detail.session_id!==active.session) return;
    if (detail.state==="connecting" || detail.state==="recovering") {
      if (heartbeat) window.clearTimeout(heartbeat); heartbeat=null;
      status(detail.state); if (!deadline) awaitSnapshot();
    } else if (detail.state==="snapshot_accepted") status("snapshot_accepted");
    else if (detail.state==="presenting") {
      if (deadline) window.clearTimeout(deadline); deadline=null;
      const presentation=detail.presentation==="moment" ? "moment" : "silence";
      if (active.last!=="presenting" || active.presentation!==presentation) status("presenting",null,presentation);
      // Rendering frequent updates must not indefinitely postpone the lease heartbeat.
      if (!heartbeat) keepAlive();
    } else if (detail.state==="error" || detail.state==="ended" || detail.state==="stopped") stop(detail.state,detail.reason);
  });
  function ready() {
    if (listening || !context.isSystemReady()) return;
    context.addCustomMessageListener(namespace,receive); listening=true;
  }
  context.addEventListener(system.EventType.READY,ready);
  context.addEventListener(system.EventType.SENDER_DISCONNECTED,event=>{if(active && event.senderId===active.sender)stop("stopped","sender_disconnected");});
  const namespaces={}; namespaces[namespace]=system.MessageType.JSON;
  // Visual-only B has no media playback to keep CAF alive. Core's actual
  // share/lease/owner fences remain the only viewing authority and deadlines.
  context.start({disableIdleTimeout:true,customNamespaces:namespaces});
  ready();
  window.addEventListener("beforeunload",()=>{stopDisplay();stop("stopped","host_stop");});
})();

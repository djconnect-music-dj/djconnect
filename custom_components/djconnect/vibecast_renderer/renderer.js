(() => {
  const params = new URLSearchParams(window.location.search);
  const staticHost = window.DJC_VIBECAST_MODE === "cast";
  let displayHost = window.DJC_VIBECAST_MODE === "display";
  let haOrigin = "", sessionId = staticHost || displayHost ? null : params.get("session_id"), broadcastToken = staticHost || displayHost ? null : params.get("broadcast_token");
  const endpoint = path => haOrigin + path;
  let displayArtwork=new Map(), displayLocale="";
  const asset = value => haOrigin && String(value || "").startsWith("/") ? haOrigin + value : value;
  const read = (value, path) => path.reduce((current,key) => current && current[key],value);
  function togglePlacement(below) { const stage=document.querySelector && document.querySelector(".stage"); if (stage && stage.classList) stage.classList.toggle("bubble-below",below); }
  const e = id => document.getElementById(id), root = document.documentElement;
  if(document.addEventListener){
    const visibility=()=>document.body.classList.toggle("renderer-hidden",document.hidden);
    document.addEventListener("visibilitychange",visibility);
    visibility();
  }
  const browserTheme = e("browser-theme-color");
  let browserTint;
  function setBrowserTheme(color) {
    if (browserTheme && browserTheme.content !== color) {
      browserTheme.content = color;
      root.style.setProperty("--browser-edge",color);
    }
  }
  const compatibility={en:"This display needs a compatible DJConnect session",nl:"Dit scherm vereist een compatibele DJConnect-sessie",de:"Dieses Display benötigt eine kompatible DJConnect-Session",fr:"Cet écran nécessite une session DJConnect compatible",es:"Esta pantalla necesita una sesión DJConnect compatible"};
  const copy = {
    en:{idle:"Idle",connecting:"Connecting",live:"Live",unavailable:"No active session",waiting:"Waiting for a session",ambient:"Ambient session",types:{music_announcement:"Music announcement",dj_bulletin:"DJ Bulletin",track:"Track",artist:"Artist",album:"Album",genre:"Genre",recommendation:"Recommendation",transition:"Transition",session:"Session"}},
    nl:{idle:"Inactief",connecting:"Verbinden",live:"Live",unavailable:"Geen actieve sessie",waiting:"Wachten op een sessie",ambient:"Ambient sessie",types:{music_announcement:"Muziekaankondiging",dj_bulletin:"DJ Bulletin",track:"Nummer",artist:"Artiest",album:"Album",genre:"Genre",recommendation:"Aanbeveling",transition:"Overgang",session:"Sessie"}},
    de:{idle:"Inaktiv",connecting:"Verbinden",live:"Live",unavailable:"Keine aktive Session",waiting:"Warten auf eine Session",ambient:"Ambient-Session",types:{music_announcement:"Musikansage",dj_bulletin:"DJ-Bulletin",track:"Titel",artist:"Künstler",album:"Album",genre:"Genre",recommendation:"Empfehlung",transition:"Übergang",session:"Session"}},
    fr:{idle:"Inactif",connecting:"Connexion",live:"En direct",unavailable:"Aucune session active",waiting:"En attente d’une session",ambient:"Session d’ambiance",types:{music_announcement:"Annonce musicale",dj_bulletin:"Bulletin du DJ",track:"Titre",artist:"Artiste",album:"Album",genre:"Genre",recommendation:"Suggestion",transition:"Transition",session:"Session"}},
    es:{idle:"Inactivo",connecting:"Conectando",live:"En directo",unavailable:"No hay sesión activa",waiting:"Esperando una sesión",ambient:"Sesión ambiental",types:{music_announcement:"Anuncio musical",dj_bulletin:"Boletín del DJ",track:"Canción",artist:"Artista",album:"Álbum",genre:"Género",recommendation:"Recomendación",transition:"Transición",session:"Sesión"}}
  };
  let language = (navigator.language || "en").slice(0,2), text = copy[language] || copy.en;
  let projection = {}, socket, reconnectTimer, expiryTimer, scrollTimer, exitTimer, attempts = 0, ended = false;
  let statusGeneration=null, snapshotAccepted=false;
  function reportStatus(state,reason,presentation) {
    if (staticHost && statusGeneration!==null) window.dispatchEvent(new CustomEvent("djconnect-renderer-status",{detail:{generation:statusGeneration,session_id:sessionId,state,reason,presentation}}));
  }
  function reportPresentation() {
    if(displayHost && snapshotAccepted && !ended){
      const captured=projection, presentation=current ? "moment" : "silence";
      const painted=()=>{if(displayHost && snapshotAccepted && !ended && projection===captured)
        window.dispatchEvent(new CustomEvent("djconnect-display-rendered",{detail:{
          issuer_epoch:captured.issuer_epoch,display_id:captured.display_id,share_id:captured.share_id,
          share_generation:captured.share_generation,session_id:sessionId,presentation}}));};
      if(typeof requestAnimationFrame==="function")requestAnimationFrame(painted);else setTimeout(painted,0);
    }
    if (!displayHost && snapshotAccepted && !ended) reportStatus("presenting",null,current ? "moment" : "silence");
  }
  let placementCount=0, lastPlacedKey="";
  let playbackItem = "", current = null, previous = null, lastShownAt = -Infinity, lastArtwork = "", lastSequence = 0, snapshotSequence = 0, fieldSequences = {};
  const firstSeen = new Map();
  const waitingMusicLabels={en:"Waiting for music",nl:"Wachten op muziek",de:"Warten auf Musik",fr:"En attente de musique",es:"Esperando música"};
  const previousSourceLabels={en:"MusicBrainz · earlier recording",nl:"MusicBrainz · eerdere opname",de:"MusicBrainz · frühere Aufnahme",fr:"MusicBrainz · enregistrement précédent",es:"MusicBrainz · grabación anterior"};
  const nextLabels={en:"Up next",nl:"Hierna",de:"Als Nächstes",fr:"À suivre",es:"A continuación"};
  const buildLabels={en:"VibeCast version",nl:"VibeCast versie",de:"VibeCast-Version",fr:"Version de VibeCast",es:"Versión de VibeCast"};
  const makerLabels={en:"Show your DJ session on this screen.",nl:"Toon je DJ-sessie op dit scherm.",de:"Zeige deine DJ-Session auf diesem Bildschirm.",fr:"Affiche ta session DJ sur cet écran.",es:"Muestra tu sesión DJ en esta pantalla."};
  const artistWebsiteLabels={en:"Artist website",nl:"Artiestenwebsite",de:"Künstlerwebsite",fr:"Site de l’artiste",es:"Sitio del artista"};
  function updateClock() {
    const now=new Date();
    const clock=e("clock"), date=e("clock-date");
    if (clock) clock.textContent=now.toLocaleTimeString(root.lang,{hour:"2-digit",minute:"2-digit",hour12:false});
    if (date) {
      const label=now.toLocaleDateString(root.lang,{weekday:"long",day:"numeric",month:"long"});
      if (date.textContent!==label) date.textContent=label;
    }
    const expiry=Date.parse(read(projection,["playback","up_next","expires_at"]) || "");
    if (e("up-next") && Number.isFinite(expiry) && Date.now() >= expiry) e("up-next").hidden=true;
  }
  window.setInterval && window.setInterval(updateClock,1000);
  useLanguage();
  const playback = () => projection.playback && typeof projection.playback === "object" ? projection.playback : {};
  const theme = mood => ({chill:"#7d8dff",groove:"#c07dff",energy:"#ff806b",party:"#ffce55"}[mood] || "#9f7cff");
  const format = value => Number.isFinite(value) && value >= 0 ? `${Math.floor(value/60000)}:${String(Math.floor(value/1000)%60).padStart(2,"0")}` : "";
  const reduceMotion = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  let sceneCanvas=null, sceneFrame=0, sceneLastFrame=0;
  const scenePalettes={chill:["#4da3ff","#7b61ff","#d184ff"],groove:["#06c7ad","#169bc8","#10b981"],
    energy:["#ddff00","#00b8ff","#39ff78"],party:["#ff287f","#aa38f5","#f43dce"]};
  let displayViewRevision=-1;
  function confirmedDisplayView(view){
    if(!view || (view.mode!=="flow" && view.mode!=="vibescape"))return projection.view;
    if(Number.isSafeInteger(view.revision)){
      if(view.revision<displayViewRevision)return projection.view;
      displayViewRevision=view.revision;
    }else if(displayViewRevision>=0)return projection.view;
    return view;
  }
  function renderDisplayViewStatus(){
    if(!displayHost)return;
    const status=e("display-view-status");
    if(!status)return;
    const view=snapshotAccepted && !ended && projection.view;
    const label=view ? (view.mode==="vibescape" ? "VibeScape" : "Flow") : "";
    if(status.textContent!==label)status.textContent=label;
    status.hidden=!label;
  }
  function sceneActive(){return snapshotAccepted && !ended && projection.view && projection.view.mode==="vibescape";}
  function hideScene(){
    document.body.classList.toggle("vibescape-mode",false);
    if(sceneCanvas)sceneCanvas.hidden=true;
    if(sceneFrame)window.cancelAnimationFrame(sceneFrame);
    sceneFrame=0;
  }
  const vibeScapeScenes = (() => {
    const tau = Math.PI * 2;
    const homeOrbs = [
      [.18, -.48, .29, .94, -.4, .8],
      [-.11, -.23, .24, .86, .6, 1.7],
      [.14, .04, .166, .85, -.35, 2.8],
      [-.31, .57, .34, .82, -.5, 3.3],
      [.27, -.21, .047, .88, .5, 4.1],
      [-.31, .12, .038, .87, -.4, 4.8],
      [.28, .36, .072, .86, .2, 5.9],
    ];

    function gradient(ctx, x1, y1, x2, y2, stops) {
      const paint = ctx.createLinearGradient(x1, y1, x2, y2);
      for (const [offset, color] of stops) paint.addColorStop(offset, color);
      return paint;
    }

    function orb(ctx, x, y, radius, shape, rotation, colors, metal) {
      const [primary, secondary, accent] = colors;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(rotation);
      ctx.scale(radius, radius * shape);
      ctx.beginPath();
      ctx.arc(0, 0, 1, 0, tau);
      ctx.clip();
      const body = ctx.createRadialGradient(-.32, -.42, .05, 0, 0, 1.03);
      body.addColorStop(0, metal ? "#d5dedd" : "#087969");
      body.addColorStop(.44, metal ? "#586365" : "#103743");
      body.addColorStop(.84, "#0b191e");
      body.addColorStop(1, metal ? "#c9d4d4" : primary + "d4");
      ctx.fillStyle = body;
      ctx.fillRect(-1, -1, 2, 2);

      ctx.globalCompositeOperation = "screen";
      for (const [hx, hy, opacity, tint] of [
        [-.42, -.35, "bd", primary], [.47, .08, "d0", secondary], [.16, -.76, "8a", accent],
      ]) {
        ctx.save();
        ctx.translate(hx, hy);
        ctx.rotate(-.55);
        ctx.scale(1, .45);
        const light = ctx.createRadialGradient(0, 0, 0, 0, 0, .62);
        light.addColorStop(0, tint + opacity);
        light.addColorStop(1, tint + "00");
        ctx.fillStyle = light;
        ctx.fillRect(-.62, -.62, 1.24, 1.24);
        ctx.restore();
      }
      for (const [angle, thickness, tint] of [[1.05, .095, primary], [-.72, .065, secondary]]) {
        ctx.beginPath();
        ctx.ellipse(0, 0, .98, .46, angle, 0, Math.PI);
        ctx.strokeStyle = tint + "48";
        ctx.lineWidth = thickness * 1.7;
        ctx.stroke();
        ctx.strokeStyle = tint + "d4";
        ctx.lineWidth = thickness;
        ctx.stroke();
      }
      ctx.restore();
    }

    function home(ctx, aspect, t, dynamics, colors) {
      const [primary, secondary, accent] = colors;
      const waves = gradient(ctx, -aspect / 2, 0, aspect / 2, 0,
        [[0, accent], [.48, primary], [1, secondary]]);
      ctx.strokeStyle = waves;
      for (let lane = 0; lane < 23; lane++) {
        ctx.beginPath();
        for (let point = 0; point <= 75; point++) {
          const x = (point / 75 - .5) * aspect;
          const wave = Math.sin(x * 5.3 + t) * .12 + Math.sin(x * 10.2 - t * .55) * .047;
          const y = .11 + lane * .018 + wave * (.65 + dynamics * .6);
          if (point === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.globalAlpha = .09 + Math.sin(lane / 22 * Math.PI) * .46;
        ctx.lineWidth = .0016;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      for (const [x, y, radius, shape, rotation, phase] of homeOrbs) {
        const drift = .036 + dynamics * .044;
        orb(ctx, x + Math.sin(t * .67 + phase) * drift, y + Math.cos(t * .53 + phase) * drift,
          radius * (.96 + dynamics * .1), shape + Math.sin(t + phase) * .075,
          rotation + Math.sin(t * .75 + phase) * .38, colors, false);
      }
    }

    function chrome(ctx, length, colors) {
      const [primary, secondary] = colors;
      return gradient(ctx, -length, -length * .38, length, length * .55,
        [[0, "#263032"], [.15, "#a1acad"], [.29, primary], [.38, "#e4e9e5"],
          [.54, secondary], [.68, "#323c40"], [.84, "#cbd5cc"], [1, "#273034"]]);
    }

    function disk(ctx, x, y, radius, tilt, rotation, colors) {
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(rotation);
      const edge = chrome(ctx, radius, colors);
      ctx.fillStyle = edge;
      ctx.beginPath();
      ctx.ellipse(.003, .019, radius + .004, radius * tilt + .004, 0, 0, tau);
      ctx.fill();
      ctx.fillStyle = gradient(ctx, -radius, -radius * .3, radius, radius * .14,
        [[0, "#273032"], [.25, "#1b262b"], [.42, colors[1] + "b8"], [.52, colors[1]],
          [.63, "#293940"], [.86, "#202729"], [1, "#464d4c"]]);
      ctx.strokeStyle = edge;
      ctx.lineWidth = .003;
      ctx.beginPath();
      ctx.ellipse(0, 0, radius, radius * tilt, 0, 0, tau);
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }

    function orbit(ctx, radius, tilt, rotation, start, colors) {
      ctx.save();
      ctx.rotate(rotation);
      ctx.beginPath();
      ctx.ellipse(0, 0, radius, radius * tilt, 0, start, start + 4.9);
      ctx.strokeStyle = "#293335";
      ctx.lineWidth = .022;
      ctx.stroke();
      ctx.strokeStyle = chrome(ctx, radius, colors);
      ctx.lineWidth = .014;
      ctx.stroke();
      ctx.restore();
    }

    function radio(ctx, aspect, t, dynamics, colors) {
      const amplitude = .14 + .3 * dynamics;
      ctx.translate(.018, .016);
      orbit(ctx, .455, .62, .85 + Math.sin(t * .57) * amplitude, .6 + t * .3, colors);
      disk(ctx, .18, -.105, .191, .39 + Math.sin(t + .9) * amplitude * .4, -.25 + t * .19, colors);
      disk(ctx, -.13, -.19, .294, .55 + Math.sin(t * .79 + .3) * amplitude * .43, .55 + t * .22, colors);
      orbit(ctx, .423, .76, -.48 + Math.cos(t * .53) * amplitude, 2.65 - t * .45, colors);
      disk(ctx, .235, .198, .212, .57 + Math.cos(t * .93) * amplitude * .35, .71 - t * .25, colors);
      orbit(ctx, .43, .23, -.99 + Math.sin(t * .45) * amplitude, 1.1 - t * .21, colors);
      orb(ctx, .49 + Math.sin(t) * .064, -.09 + Math.cos(t * .73) * .05, .06, .96, t, colors, true);
      orb(ctx, -.39 + Math.cos(t) * .042, .18, .033, .97, -t, colors, true);
    }

    function box(ctx, x, y, width, height, depth, yaw, roll, colors) {
      const [primary, secondary, accent] = colors;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(roll);
      const cosine = Math.cos(yaw), sine = Math.sin(yaw);
      const vertices = [];
      for (const z of [-depth / 2, depth / 2]) {
        for (const [px, py] of [[-width/2,-height/2],[width/2,-height/2],
          [width/2,height/2],[-width/2,height/2]]) {
          const viewDepth = z * cosine - px * sine;
          const scale = 1 / (1 - viewDepth * .36);
          vertices.push([(px * cosine + z * sine) * scale, (py - viewDepth * .25) * scale, viewDepth]);
        }
      }
      const faces = [[0,1,2,3],[4,5,6,7],[0,4,7,3],[1,5,6,2],[0,1,5,4],[2,3,7,6]];
      faces.sort((a,b) => depthSum(a) - depthSum(b));
      function depthSum(face) {
        return face.reduce((total, vertex) => total + vertices[vertex][2], 0);
      }
      for (const [index, face] of faces.entries()) {
        const [start, , end] = face.map(i => vertices[i]);
        ctx.beginPath();
        for (const [corner, i] of face.entries()) {
          if (corner === 0) ctx.moveTo(vertices[i][0], vertices[i][1]);
          else ctx.lineTo(vertices[i][0], vertices[i][1]);
        }
        ctx.closePath();
        ctx.fillStyle = "#101916";
        ctx.fill();
        ctx.fillStyle = gradient(ctx, start[0], start[1], end[0], end[1],
          [[0, accent + "a8"], [.11, "#222b25"], [.53, index === 4 ? secondary + "58" : primary + "55"],
            [.91, "#0c1718"], [1, primary + "da"]]);
        ctx.fill();
        ctx.strokeStyle = gradient(ctx, start[0], start[1], end[0], end[1],
          [[0, accent], [.5, "#273a36"], [1, primary]]);
        ctx.lineWidth = .003;
        ctx.stroke();
      }
      ctx.restore();
    }

    function club(ctx, aspect, t, dynamics, colors) {
      const [primary, secondary, accent] = colors;
      ctx.fillStyle = gradient(ctx, 0, .25, 0, .5,
        [[0, primary + "1e"], [.84, secondary + "0a"], [1, "#030709"]]);
      ctx.fillRect(-aspect / 2, .25, aspect, .25);
      const swing = (.1 + dynamics * .44) * Math.sin(t * .76);
      for (const [x, y, size, phase] of [[.24, -.07, .47, .7], [-.03, .12, .59, -.17], [.38, -.18, .33, .51]]) {
        const angle = phase + Math.sin(t + x * 6) * (.12 + dynamics * .28);
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(angle);
        ctx.scale(1 - Math.abs(swing) * .35, 1);
        ctx.strokeStyle = gradient(ctx, -size, size, size, -size,
          [[0, primary], [.4, "#394a3c"], [.72, accent], [1, primary + "a8"]]);
        ctx.lineWidth = .016;
        ctx.strokeRect(-size / 2, -size * .56, size, size * 1.12);
        ctx.strokeStyle = primary + "90";
        ctx.lineWidth = .002;
        ctx.strokeRect(-size / 2, -size * .56, size, size * 1.12);
        ctx.restore();
      }
      for (let index = 0; index < 3; index++) {
        box(ctx, -.13 + index * .13, -.1, .022, .34, .035, .4 + swing, .42 + swing, colors);
      }
      box(ctx, .01, -.36, .66, .056, .114, .45 + swing, -.13 + swing * .45, colors);
      box(ctx, -.38, .078, .21, .77, .18, -.58 + swing, -.04 + swing * .2, colors);
      box(ctx, .32, .22, .225, .4, .17, .47 - swing, .08 - swing * .24, colors);
    }

    function festival(ctx, aspect, t, dynamics, colors) {
      const strands = 52, points = 74;
      const pitch = 2.55 + dynamics * .22;
      const radius = .21 + dynamics * .047;
      ctx.globalCompositeOperation = "screen";
      for (let layer = 0; layer < 2; layer++) {
        for (let band = 0; band < colors.length; band++) {
          ctx.fillStyle = colors[band] + (layer ? "e6" : "70");
          ctx.beginPath();
          for (let strand = band; strand < strands; strand += colors.length) {
            const offset = strand / strands * tau;
            for (let point = 1; point < points; point++) {
              const height = point / points;
              const angle = height * tau * pitch + offset + t * 1.7;
              const wave = 1 + .24 * Math.sin(3 * angle - 2 * offset + t);
              const depth = Math.sin(angle) * wave;
              if (Number(depth > 0) !== layer) continue;
              const taper = .44 + .56 * Math.pow(Math.sin(Math.PI * height), .65);
              const glint = (strand * 11 + point * 17) % 109 === 0;
              const size = (.00136 + .00047 * (1 + depth)) * taper * (glint ? 1.8 : 1);
              const bend = (height - .5) * .24 + .038 * Math.sin(height * 10 - t * .4);
              const x = Math.cos(angle) * radius * taper * wave + bend;
              const y = (height - .49) * .94 + depth * (.067 + dynamics * .034);
              ctx.rect(x - size, y - size, 2 * size, 2 * size);
            }
          }
          ctx.fill();
        }
      }
    }

    const scenes = { home_dj: home, radio_dj: radio, club_dj: club, festival_dj: festival };
    const backdrops = { home_dj: "#041315", radio_dj: "#0c1110", club_dj: "#0a1110", festival_dj: "#020505" };
    return function drawVibeScape(ctx, width, height, settings, elapsed) {
      const { persona, colors, dynamics, mood } = settings;
      const unit = Math.min(height, width * .95);
      const aspect = width / unit;
      const speed = ({ chill: .66, energy: 1.16, party: 1.32 })[mood] || 1;
      const time = elapsed * speed * (.19 + dynamics * .51);
      ctx.save();
      ctx.fillStyle = backdrops[persona] || backdrops.home_dj;
      ctx.fillRect(0, 0, width, height);
      ctx.translate(width / 2, height / 2);
      ctx.scale(unit, unit);
      (scenes[persona] || home)(ctx, aspect, time, dynamics, colors);
      ctx.restore();
    };
  })();
  function drawScene(stamp=0){
    sceneFrame=0;
    if(!sceneActive() || document.hidden || !sceneCanvas)return;
    const still=reduceMotion();
    if(still || !document.body.classList.contains("vibescape-mode") || stamp-sceneLastFrame>=33){
      sceneLastFrame=stamp;
      const scale=Math.min(1,1280/window.innerWidth,720/window.innerHeight);
      const width=Math.max(1,Math.round(window.innerWidth*scale));
      const height=Math.max(1,Math.round(window.innerHeight*scale));
      if(sceneCanvas.width!==width || sceneCanvas.height!==height){sceneCanvas.width=width;sceneCanvas.height=height;}
      const ctx=sceneCanvas.getContext("2d");
      if(!ctx){hideScene();return;}
      const settings=projection.view || {};
      const colors=scenePalettes[settings.mood] || ["#3285ff","#843df5","#cb27f5"];
      const dynamics=Number.isFinite(settings.dynamics) ? Math.max(0,Math.min(1,settings.dynamics)) : .5;
      vibeScapeScenes(ctx,width,height,{persona:settings.persona,mood:settings.mood,colors,dynamics},still ? 0 : stamp/1000);
      sceneCanvas.hidden=false;
      document.body.classList.add("vibescape-mode");
    }
    if(!still)sceneFrame=window.requestAnimationFrame(drawScene);
  }
  function renderScene(){
    const active=sceneActive();
    if(!active){hideScene();return;}
    if(!sceneCanvas){
      sceneCanvas=document.createElement("canvas");sceneCanvas.id="vibescape-scene";
      sceneCanvas.setAttribute("aria-hidden","true");document.body.appendChild(sceneCanvas);
    }
    if(document.hidden){if(sceneFrame)window.cancelAnimationFrame(sceneFrame);sceneFrame=0;return;}
    if(!sceneFrame)drawScene(performance.now());
  }
  if(document.addEventListener)document.addEventListener("visibilitychange",renderScene);
  const sceneMedia=window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  if(sceneMedia && sceneMedia.addEventListener)sceneMedia.addEventListener("change",()=>{
    if(sceneFrame)window.cancelAnimationFrame(sceneFrame);sceneFrame=0;renderScene();
  });
  const reactionEmoji={heart:"❤️",fire:"🔥",applause:"👏",love:"😍",dance:"💃"};
  const seenReactions=new Map();
  const reactionTimers=new Map();
  let guestCounter=null;
  function renderReceiverBrand(partyEnabled){
    const label=e("receiver-brand-label");
    const title=partyEnabled ? "VibeCast Party" : "DJConnect VibeCast";
    if(label.textContent!==title)label.textContent=title;
    document.body.classList.toggle("receiver-mark-is-party",partyEnabled);
  }
  function clearLiveStatus(){
    renderReceiverBrand(false);
    if(guestCounter){guestCounter.hidden=true;guestCounter.textContent="";guestCounter.removeAttribute("aria-label");}
    for(const [node,timer] of reactionTimers){window.clearTimeout(timer);node.remove();}
    reactionTimers.clear();seenReactions.clear();
  }
  let sessionChange=null,sessionChangeTimer=0,lastSessionPresentation="";
  function avatarCopy(identifier){
    const original=e("spotlight-avatar");
    if(!original)return null;
    const copy=original.cloneNode(true);copy.id=identifier;
    const gradient=copy.querySelector("linearGradient"),oldId=gradient.id;
    gradient.id=identifier+"-gradient";
    for(const node of copy.querySelectorAll("[fill],[stroke]"))for(const attr of ["fill","stroke"])
      if(node.getAttribute(attr)==="url(#"+oldId+")")node.setAttribute(attr,"url(#"+gradient.id+")");
    return copy;
  }
  function clearSessionChange(){
    lastSessionPresentation="";
    if(sessionChange)sessionChange.hidden=true;
    if(sessionChangeTimer)window.clearTimeout(sessionChangeTimer);sessionChangeTimer=0;
  }
  function renderSessionChange(){
    if(!displayHost)return;
    if(!snapshotAccepted || ended){clearSessionChange();return;}
    const settings=projection.session_presentation || {};
    const signature=JSON.stringify([settings.mood || "",settings.persona || "",settings.presence || ""]);
    if(lastSessionPresentation && signature!==lastSessionPresentation){
      if(!sessionChange){
        sessionChange=document.createElement("div");sessionChange.id="session-change-popup";
        sessionChange.className="mood-palette";sessionChange.setAttribute("role","status");
        const svg=avatarCopy("session-change-dj-avatar");if(svg)sessionChange.appendChild(svg);
        sessionChange.appendChild(document.createElement("span"));document.body.appendChild(sessionChange);
      }
      const labels={en:"Session updated",nl:"Sessie bijgewerkt",de:"Session aktualisiert",fr:"Session mise à jour",es:"Sesión actualizada"};
      sessionChange.lastElementChild.textContent=labels[root.lang] || labels.en;
      sessionChange.dataset.mood=settings.mood || "";sessionChange.hidden=false;
      if(sessionChangeTimer)window.clearTimeout(sessionChangeTimer);
      sessionChangeTimer=window.setTimeout(()=>{sessionChange.hidden=true;sessionChangeTimer=0;},4000);
    }
    lastSessionPresentation=signature;
  }
  function renderLiveStatus(detail){
    if(!displayHost || !snapshotAccepted || ended || !detail)return;
    const enabled=detail.live_enabled===true;
    if(enabled)renderReceiverBrand(true);
    else clearLiveStatus();
    if(!guestCounter){
      guestCounter=document.createElement("span");guestCounter.id="live-guest-count";
      e("receiver-brand-label").after(guestCounter);
    }
    const count=Number.isInteger(detail.guest_count) && detail.guest_count>=0 && detail.guest_count<=64 ? detail.guest_count : 0;
    guestCounter.hidden=!enabled;
    const labels={en:"Connected guests",nl:"Verbonden gasten",de:"Verbundene Gäste",fr:"Invités connectés",es:"Invitados conectados"};
    const guestIcon=document.createElement("span");
    guestIcon.className="live-guest-icon";guestIcon.textContent="👥";guestIcon.setAttribute("aria-hidden","true");
    guestCounter.replaceChildren(guestIcon,String(count));
    guestCounter.setAttribute("aria-label",(labels[root.lang] || labels.en)+": "+count);
    const view=confirmedDisplayView(detail.view);
    if(view!==projection.view){
      projection.view=view;
      renderDisplayViewStatus();
      renderScene();
    }
    const now=Date.now();
    for(const [id,until] of seenReactions)if(until<=now)seenReactions.delete(id);
    if(!enabled)return;
    for(const event of (Array.isArray(detail.reactions) ? detail.reactions : []).slice(-64)){
      const until=Date.parse(event.expires_at),emoji=reactionEmoji[event.emotion];
      if(!emoji || typeof event.event_id!=="string" || event.event_id.length>128 || seenReactions.has(event.event_id) ||
        event.playback_item_id!==playback().item_id || !(until>now && until<=now+6000))continue;
      seenReactions.set(event.event_id,until);
      const node=document.createElement("span");node.className="live-reaction";node.textContent=emoji;
      node.setAttribute("aria-hidden","true");node.style.left=(12+event.event_id.charCodeAt(0)%76)+"%";
      document.body.appendChild(node);
      reactionTimers.set(node,window.setTimeout(()=>{node.remove();reactionTimers.delete(node);},Math.min(5000,until-now)));
    }
  }
  function clearTimer(name) {
    const timer = name === "expiry" ? expiryTimer : scrollTimer;
    if (timer && window.clearTimeout) window.clearTimeout(timer);
    if (name === "expiry") expiryTimer = undefined; else scrollTimer = undefined;
  }
  function useLanguage() {
    const requested = String(read(projection,["session","locale"]) || "").slice(0,2).toLowerCase();
    const selected = displayLocale || (copy[requested] ? requested : (copy[language] ? language : "en"));
    const changed=root.lang!==selected;
    text = copy[selected]; root.lang = selected;
    const buildLabel=e("renderer-build-label");
    if (buildLabel) buildLabel.textContent=buildLabels[selected];
    const maker=e("waiting-maker-label");
    if (maker) maker.textContent=makerLabels[selected];
    return changed;
  }
  function keyFor(item) {
    return String(item.moment_id || `${item.playback_item_id || ""}|${item.type || ""}|${item.created_at || ""}|${item.summary || item.content || item.title || ""}`);
  }
  function qualifiedCitations(citations) {
    if (!Array.isArray(citations) || citations.length < 1 || citations.length > 3) return null;
    const valid=citations.every(s => s && typeof s.title === "string" && s.title.length <= 240 && (
        s.provider === "Wikipedia" && s.license === "CC-BY-SA-4.0" &&
          /^https:\/\/(?:en|nl|de|fr|es)\.wikipedia\.org\/wiki\/[^\s?#]+$/.test(s.url) &&
          /^https:\/\/(?:en|nl|de|fr|es)\.wikipedia\.org\/w\/index\.php\?oldid=[0-9]+$/.test(s.revision_url) &&
          new URL(s.url).origin === new URL(s.revision_url).origin ||
        s.provider === "MusicBrainz" && s.license === "CC0-1.0" && !s.revision_url && /^https:\/\/musicbrainz\.org\/(?:artist|release-group)\/[0-9a-f-]{36}$/.test(s.url) ||
        s.provider === "Public web" && s.usage_basis === "public_page_short_reference" &&
          s.license === "public_page_short_reference" && !s.revision_url && !s.wikidata_id &&
          s.author_status === "publication_byline_not_independent_identity" &&
          typeof s.attributed_author === "string" && s.attributed_author.length > 1 &&
          s.work_reference && typeof s.work_reference.title === "string" &&
          typeof s.work_reference.artist === "string" &&
          /^https:\/\/musicbrainz\.org\/release-group\/[0-9a-f-]{36}$/.test(s.work_reference.url) &&
          publicCitationURL(s.url) ||
        s.provider === "Artist website" && s.usage_basis === "public_page_short_reference" &&
          s.license === "public_page_short_reference" && !s.revision_url && publicCitationURL(s.url) &&
          s.publisher === new URL(s.url).hostname && /^Q[1-9][0-9]*$/.test(s.wikidata_id) &&
          s.official_site_reference && s.official_site_reference.basis === "wikidata_p856_v1" &&
          s.official_site_reference.entity_id === s.wikidata_id &&
          typeof s.official_site_reference.claim_id === "string" &&
          new RegExp(`^${s.wikidata_id}\\$[0-9a-fA-F-]{36}$`).test(s.official_site_reference.claim_id) &&
          Number.isSafeInteger(s.official_site_reference.revision) && s.official_site_reference.revision > 0 ||
        s.provider === "Wikidata" && s.license === "CC0-1.0" && !s.revision_url && /^https:\/\/www\.wikidata\.org\/wiki\/Q[1-9][0-9]*$/.test(s.url)));
    return valid ? citations : null;
  }
  function publicCitationURL(value) {
    try {
      const url = new URL(value), host = url.hostname;
      return url.protocol === "https:" && !url.username && !url.password &&
        (!url.port || url.port === "443") && host.includes(".") &&
        !/^(?:[0-9.]+|\[.*\])$/.test(host) && !/\.(?:local|localhost|internal)$/.test(host);
    } catch { return false; }
  }
  function bulletinCitations(citations) {
    // Same closed publisher metadata as the Core intake; never fetch an article.
    const publishers = {
      CBS:{hosts:["www.cbs.nl"],license:"CC-BY-4.0"},
      KNMI:{hosts:["www.knmi.nl"],license:"CC0-1.0"},
      NASA:{hosts:["www.nasa.gov","science.nasa.gov"],license:"NASA-media-guidelines"},
      "European Environment Agency":{hosts:["www.eea.europa.eu"],license:"CC-BY-4.0"},
      Eurostat:{hosts:["ec.europa.eu"],license:"CC-BY-4.0"}
    };
    if (!Array.isArray(citations) || citations.length !== 2) return null;
    const urls = new Set(), providers = new Set();
    for (const source of citations) {
      if (!source || typeof source !== "object" || !Object.prototype.hasOwnProperty.call(publishers,source.provider)) return null;
      const publisher=publishers[source.provider], published=Date.parse(source.published_at || "");
      if (typeof source.title !== "string" || !source.title || source.title.length > 240 ||
          source.license !== publisher.license || !publicCitationURL(source.url) ||
          !publisher.hosts.includes(new URL(source.url).hostname) ||
          !Number.isFinite(published) || published > Date.now() || Date.now()-published >= 7200000 ||
          source.revision_url || urls.has(source.url) || providers.has(source.provider)) return null;
      urls.add(source.url); providers.add(source.provider);
    }
    return citations;
  }
  function cardFor(item) {
    if (!item || typeof item !== "object" || item.type === "silence") return null;
    const bulletin=item.type === "dj_bulletin";
    const citations=bulletin ? bulletinCitations(item.sources) : item.sources === undefined ? [] : qualifiedCitations(item.sources);
    if (!citations) return null;
    if (bulletin && (typeof item.content !== "string" || item.summary || Array.from(item.content).length > 1200)) return null;
    const summary = bulletin ? item.content : String(item.summary || item.content || item.title || "").slice(0,1200);
    if (!summary) return null;
    const key = keyFor(item), now = Date.now();
    if (!firstSeen.has(key)) {
      firstSeen.set(key, now);
      if (firstSeen.size > 32) firstSeen.delete(firstSeen.keys().next().value);
    }
    const created = Date.parse(item.created_at || ""), stamped = Number.isFinite(created);
    if (stamped && created > now + 10000) return null;
    const rawDuration = Number(read(item,["presentation_intent","maximum_duration_seconds"]));
    const seconds = Number.isFinite(rawDuration) && rawDuration > 0 ? Math.min(90, rawDuration) : 25;
    const admission=bulletin && read(projection,["native_delivery","admissions"]);
    const original=Array.isArray(admission) ? admission.find(a=>a.moment_id === item.moment_id) : null;
    if (bulletin && !displayHost && (!original || original.qualification !== "qualified" ||
        !(original.current_display_allowed || original.active_flow_display_allowed))) return null;
    const explicitExpiry = Date.parse((bulletin && !displayHost ? original.display_expires_at : item.display_expires_at) || "");
    if (bulletin && (!stamped || !Number.isFinite(explicitExpiry))) return null;
    const sourceExpiry = item.source_expires_at == null ? Infinity : Date.parse(item.source_expires_at);
    const expiry = displayHost ? Math.min(explicitExpiry,sourceExpiry) :
      Math.min((stamped ? created : firstSeen.get(key)) + seconds*1000,
      Number.isFinite(explicitExpiry) ? explicitExpiry : Infinity,
      bulletin ? Math.min(...citations.map(s=>Date.parse(s.published_at)+7200000)) : Infinity);
    return now < expiry ? {key, created:stamped ? created : firstSeen.get(key), expiry, summary,
      detail:bulletin ? item.content : String(item.content || "").slice(0,1200), attribution:item.source_attribution, sources:citations, type:item.type || "", itemId:item.playback_item_id || "", stamped} : null;
  }
  function eligibleCards() {
    const p = playback(), items = Array.isArray(projection.dj_moments) ? projection.dj_moments : [];
    const cards = [];
    for (const item of items.slice(-24)) {
      if (!item || (p.item_id ? item.playback_item_id !== p.item_id : !!item.playback_item_id)) continue;
      const card = cardFor(item);
      if (card) cards.push(card);
    }
    cards.sort((a,b) => a.created - b.created);
    return cards;
  }
  function clearChildren(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }
  function clearCards() {
    clearTimer("expiry"); clearTimer("scroll"); current = null; previous = null;
    const card = e("moment-card"), history = e("moment-history"), detail = e("moment-detail"), kind = e("moment-type");
    if (exitTimer) window.clearTimeout(exitTimer); exitTimer=undefined;
    if (card) { card.hidden = true; card.classList && card.classList.remove("exiting"); }
    if (history) history.hidden = true;
    history && history.classList && history.classList.remove("leaving");
    if (detail) detail.textContent = "";
    if (kind) kind.textContent = "";
    e("moment").textContent = "";
    const researchSources=e("moment-research-sources");
    if (researchSources) { clearChildren(researchSources); researchSources.hidden=true; }
  }
  function scheduleCardExpiry() {
    clearTimer("expiry");
    const now = Date.now();
    const deadlines = [current,previous].filter(card => card && card.expiry > now).map(card => card.expiry);
    if (deadlines.length) expiryTimer = window.setTimeout(
      () => { if (displayHost) renderSpotlight(); else renderCards(false); reportPresentation(); },
      Math.max(0,Math.min(...deadlines)-Date.now()+(displayHost ? 0 : 25))
    );
  }
  function showPrevious(card, animate=false) {
    const history = e("moment-history");
    if (!history) return;
    if (!card || Date.now() >= card.expiry) { history.hidden = true; history.classList && history.classList.remove("leaving"); return; }
    const label = text.types[card.type] || "";
    history.textContent = label && !card.summary.toLocaleLowerCase().startsWith(label.toLocaleLowerCase())
      ? `${label} · ${card.summary}` : card.summary;
    history.hidden = false;
    if (animate && !reduceMotion()) {
      history.classList && history.classList.remove("leaving");
      void history.offsetWidth;
      history.classList && history.classList.add("leaving");
    }
  }
  function fitBubble() {
    if (displayHost) return;
    const stage=document.querySelector && document.querySelector(".stage"), now=document.querySelector && document.querySelector(".now-playing"), shell=e("moment-card"), detail=e("moment-detail");
    if (!stage || !now || !shell || shell.hidden) return;
    const region=stage.getBoundingClientRect(), content=now.getBoundingClientRect();
    const portrait=window.innerHeight>=window.innerWidth;
    let available=portrait ? Math.max(0,(stage.classList.contains("bubble-below") ? region.bottom-content.bottom : content.top-region.top)-24) : region.height*.7;
    if (current && current.type === "dj_bulletin" && shell.parentElement) {
      const holderLimit=parseFloat(getComputedStyle(shell.parentElement).maxHeight);
      if (Number.isFinite(holderLimit)) available=Math.min(available,holderLimit);
    }
    shell.style.maxHeight=`${available}px`;
    if (detail) {
      detail.style.maxHeight=portrait ? "12vh" : "30vh";
      const overhead=shell.scrollHeight-detail.offsetHeight;
      detail.style.maxHeight=`${Math.max(0,available-overhead)}px`;
    }
  }
  function showCurrent(card, animate, afterExit=false) {
    const shell = e("moment-card"), kind = e("moment-type"), detail = e("moment-detail");
    if (animate && !afterExit && shell && !shell.hidden && lastPlacedKey !== card.key && !reduceMotion()) {
      if (exitTimer) window.clearTimeout(exitTimer);
      shell.classList && shell.classList.remove("fresh"); shell.classList && shell.classList.add("exiting");
      exitTimer=window.setTimeout(()=>{
        exitTimer=undefined;
        if ((current && current.key) !== card.key) return;
        const stillEligible=eligibleCards().find(item=>item.key === card.key);
        if (stillEligible) showCurrent(stillEligible,true,true);
        else { clearCards(); renderCards(false); }
      },800);
      return;
    }
    e("moment").textContent = card.type === "dj_bulletin" ? "" : card.summary;
    const source=card.attribution;
    const safeSource=source && ({Spotify:"https://open.spotify.com/",MusicBrainz:"https://musicbrainz.org/",Wikidata:"https://www.wikidata.org/wiki/"}[source.provider]) && String(source.url || "").startsWith({Spotify:"https://open.spotify.com/",MusicBrainz:"https://musicbrainz.org/",Wikidata:"https://www.wikidata.org/wiki/"}[source.provider]);
    const sourceLink=e("moment-source");
    const spotifyLogo=safeSource && card.type==="music_announcement" && source.provider==="Spotify"
      ? e("spotify-source").querySelector("img") : null;
    sourceLink.hidden=!safeSource;
    if (spotifyLogo) {
      if (!sourceLink.firstElementChild) {
        sourceLink.textContent="";
        sourceLink.appendChild(spotifyLogo.cloneNode());
      }
    } else {
      sourceLink.textContent=safeSource ? source.provider : "";
    }
    if (safeSource) sourceLink.href=source.url; else sourceLink.removeAttribute("href");
    const researchSources=e("moment-research-sources");
    if (researchSources) {
      clearChildren(researchSources);
      const citations=Array.isArray(card.sources) && card.sources.length <= 3 ? card.sources : [];
      const valid=citations.length > 0;
      researchSources.hidden=!valid;
      if (valid) {
        sourceLink.hidden=true;
        for (const citation of citations) {
          const link=document.createElement("a");
          const provider=citation.provider === "Artist website" ? (artistWebsiteLabels[root.lang] || artistWebsiteLabels.en) : citation.provider;
          const attribution=citation.provider === "Artist website" ? citation.publisher : citation.usage_basis ? citation.attributed_author : citation.license;
          const published=card.type === "dj_bulletin" ? ` · ${new Date(citation.published_at).toLocaleString(root.lang)}` : "";
          link.textContent=`${citation.title} · ${provider}${citation.language ? ` (${citation.language})` : ""} · ${attribution}${published}`;
          link.href=citation.revision_url || citation.url;
          link.target="_blank"; link.rel="noopener noreferrer";
          researchSources.appendChild(link);
        }
      }
    }
    const previousSource=e("moment-source-previous");
    if (previousSource) {
      const safePrevious=safeSource && source.provider === "MusicBrainz" && /^https:\/\/musicbrainz\.org\/recording\/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(String(source.url_previous || "")) && source.url_previous !== source.url;
      previousSource.hidden=!safePrevious;
      previousSource.textContent=safePrevious ? (previousSourceLabels[root.lang] || previousSourceLabels.en) : "";
      if (safePrevious) previousSource.href=source.url_previous; else previousSource.removeAttribute("href");
    }
    if (kind) kind.textContent = text.types[card.type] || "";
    if (detail) {
      detail.textContent = card.type === "dj_bulletin" ? card.detail : card.detail && card.detail !== card.summary ? card.detail : "";
      detail.scrollTop = 0;
      detail.classList && detail.classList.remove("scrolled");
    }
    if (shell) {
      shell.hidden = false;
      if (exitTimer) window.clearTimeout(exitTimer); exitTimer=undefined;
      shell.classList && shell.classList.remove("fresh","exiting");
      if (lastPlacedKey !== card.key) { placementCount++; lastPlacedKey=card.key; }
      if (!displayHost) togglePlacement(placementCount % 2 === 0);
      if (animate && !reduceMotion()) {
        void shell.offsetWidth;
        shell.classList && shell.classList.add("fresh");
      }
    }
    fitBubble();
    clearTimer("scroll");
    if (!displayHost && (detail && detail.textContent) && !reduceMotion() && detail.scrollHeight > detail.clientHeight) {
      const step = Math.max(24,parseFloat(getComputedStyle(detail).lineHeight) || 28);
      const advance = () => {
        if ((current && current.key) !== card.key) return;
        const limit = detail.scrollHeight-detail.clientHeight;
        if (detail.scrollTop >= limit-1) return;
        detail.classList && detail.classList.add("scrolled");
        detail.scrollTo ? detail.scrollTo({top:Math.min(limit,detail.scrollTop+step),behavior:"smooth"}) : (detail.scrollTop=Math.min(limit,detail.scrollTop+step));
        scrollTimer = window.setTimeout(advance,2600);
      };
      scrollTimer = window.setTimeout(advance,5000);
    }
    scheduleCardExpiry();
  }
  function renderCards(animate, languageChanged) {
    const p = playback(), item = p.item_id || "";
    if (item !== playbackItem) {
      playbackItem = item; lastShownAt = -Infinity; clearCards();
    }
    if (current && Date.now() >= current.expiry) {
      if (!exitTimer && !reduceMotion()) {
        const expiredKey=current.key;
        e("moment-card").classList && e("moment-card").classList.add("exiting");
        exitTimer=window.setTimeout(() => { if ((current && current.key)===expiredKey) clearCards(); exitTimer=undefined; },800);
      } else if (reduceMotion()) clearCards();
    }
    const cards = eligibleCards(), latest = cards[cards.length-1];
    if (current && current.type === "dj_bulletin" && !cards.some(card=>card.key === current.key)) clearCards();
    if (previous && previous.type === "dj_bulletin" && !cards.some(card=>card.key === previous.key)) {
      previous=null; showPrevious(null);
    }
    if (!latest) { if (!exitTimer) clearCards(); return; }
    if ((current && current.key) === latest.key) {
      showPrevious(previous);
      if (languageChanged) showCurrent(latest,false); else scheduleCardExpiry();
      return;
    }
    if (latest.created < lastShownAt) return;
    previous = animate && current && current.itemId === latest.itemId && cards.some(card=>card.key === current.key) ? current : null;
    current = latest; lastShownAt = latest.created;
    showPrevious(previous, animate); showCurrent(latest, animate);
  }
  function renderSpotlight(languageChanged=false) {
    const id = projection.current_moment_id;
    const item = playback().state === "playing" && typeof id === "string"
      && Array.isArray(projection.dj_moments) && projection.dj_moments.find(moment=>moment && moment.moment_id === id);
    const card = item ? cardFor(item) : null;
    document.body.classList.toggle("display-spotlight",!!card);
    if (!card) {
      if (current) clearCards();
      return;
    }
    e("moment-card").dataset.mood=read(projection,["session","selected_mood"]) || "";
    if (!current || current.key !== card.key || languageChanged) {
      current = card;
      showCurrent(card,false);
    } else {
      current = card;
      scheduleCardExpiry();
    }
  }
  const flowLabels = {
    en:["Session Flow", "Back to live"],
    nl:["Sessieflow", "Terug naar live"],
    de:["Session-Flow", "Zurück zu Live"],
    fr:["Fil de la session", "Revenir au direct"],
    es:["Flujo de la sesión", "Volver al directo"]
  };
  let horizonExpiry, horizonContentKey;
  let horizonPreviewExpiry;
  function renderHorizonPreview(active) {
    const card=e("horizon-preview");
    if (!card) return;
    window.clearTimeout(horizonPreviewExpiry);
    const p=playback(), preview=active && !sceneActive() && projection.horizon_preview;
    const track=preview && preview.track;
    const expires=Date.parse(preview && preview.expires_at);
    const visible=!!(track && p.state==="playing" && p.item_id && preview.current_item_id===p.item_id
      && expires>Date.now() && typeof preview.text==="string" && preview.text
      && typeof track.title==="string" && track.title && typeof track.artist==="string" && track.artist
      && /^https:\/\/open\.spotify\.com\/track\/[A-Za-z0-9]{22}$/.test(track.source_url));
    card.hidden=!visible;
    e("horizon-preview-label").textContent=visible ? nextLabels[root.lang] || nextLabels.en : "";
    e("horizon-preview-title").textContent=visible ? track.title : "";
    e("horizon-preview-artist").textContent=visible ? track.artist : "";
    e("horizon-preview-text").textContent=visible ? preview.text : "";
    const source=e("horizon-preview-source"), image=e("horizon-preview-art");
    const artwork=e("horizon-preview-artwork");
    const cover=visible && preview.artwork && displayArtwork.get(preview.artwork.reference);
    if (cover && cover.item_id===track.item_id) {
      if(image.getAttribute("src")!==cover.url)image.src=cover.url;
      artwork.hidden=false;
    } else {
      artwork.hidden=true;
      image.removeAttribute("src");
    }
    if (!visible) {
      source.removeAttribute("href");
      return;
    }
    card.dataset.mood=read(projection,["session","selected_mood"]) || "";
    source.href=track.source_url;
    if (!source.firstChild) {
      const logo=e("spotify-source").querySelector("img");
      if(logo)source.appendChild(logo.cloneNode());
    }
    horizonPreviewExpiry=window.setTimeout(()=>renderHorizonPreview(active),Math.max(0,expires-Date.now()));
  }
  function renderHorizon(active) {
    const panels=e("session-panels"), card=e("horizon-card"), sections=e("horizon-sections");
    if (!panels || !card || !sections) return;
    panels.hidden=!active;
    renderHorizonPreview(active);
    if (horizonExpiry) window.clearTimeout(horizonExpiry);
    const horizon=active && projection.horizon;
    const expires=Date.parse(horizon && horizon.valid_until);
    const items=horizon && Array.isArray(horizon.sections) ? horizon.sections.slice(0,3).filter(section=>
      section && typeof section.title==="string" && typeof section.text==="string" && section.text) : [];
    card.hidden=!(expires>Date.now() && items.length);
    if (card.hidden) {
      if(horizonContentKey!==undefined)clearChildren(sections);
      horizonContentKey=undefined;
      return;
    }
    card.dataset.mood=read(projection,["session","selected_mood"]) || "";
    const key=JSON.stringify(items.map(item=>item.text));
    if(key!==horizonContentKey){
      clearChildren(sections);
      for (const item of items) {
        const section=document.createElement("section"), text=document.createElement("p");
        text.textContent=item.text;
        section.appendChild(text);
        sections.appendChild(section);
      }
      horizonContentKey=key;
    }
    horizonExpiry=window.setTimeout(()=>renderHorizon(active),Math.max(0,expires-Date.now()));
  }
  const flowRows = new Map();
  let followFlow = true, manualFlowScroll = false, flowExpiry, flowReturnTimer;
  function atLiveEdge(viewport) {
    return viewport.scrollTop <= 4;
  }
  function renderFlow() {
    if (!displayHost) return false;
    const section = e("shared-flow"), viewport = e("flow-viewport"), list = e("flow-cards"), live = e("flow-live");
    if (!section || !viewport || !list || !live) return false;
    if (flowExpiry) window.clearTimeout(flowExpiry);
    const active = Array.isArray(projection.shared_flow);
    section.hidden = !active;
    document.body.classList.toggle("shared-flow-live",active);
    if (!active) {
      clearChildren(list);
      flowRows.clear();
      clearFlowReturn();
      followFlow=true;
      manualFlowScroll=false;
      live.hidden=true;
      return false;
    }
    const labels = flowLabels[root.lang] || flowLabels.en;
    viewport.setAttribute("aria-label",labels[0]);
    live.textContent=labels[1];
    const time=Date.now();
    const observedLabels={en:"Observed playback",nl:"Waargenomen playback",de:"Beobachtete Wiedergabe",fr:"Lecture observée",es:"Reproducción observada"};
    const observations=(Array.isArray(projection.observed_playback) ? projection.observed_playback : []).slice(-12)
      .filter(item=>item && typeof item.entry_id==="string" && item.entry_id.length<=128
        && typeof item.title==="string" && item.title && typeof item.artist==="string"
        && /^https:\/\/open\.spotify\.com\/track\/[A-Za-z0-9]{22}$/.test(item.source_url)
        && Date.parse(item.expires_at)>time)
      .map(item=>({...item,moment_id:"observed:"+item.entry_id,type:"playback_observed",
        content:[item.title,item.artist].filter(Boolean).join(" — "),published_at:item.observed_at,
        flow_expires_at:item.expires_at,source_attribution:{provider:"Spotify",url:item.source_url}}));
    const combined=projection.shared_flow.slice(-12).concat(observations);
    if(observations.length)combined.sort((a,b)=>(Date.parse(a.published_at||a.created_at)||0)-(Date.parse(b.published_at||b.created_at)||0));
    const items=combined.slice(-12).filter(item=>item && typeof item.moment_id==="string"
      && typeof item.content==="string" && item.content && Date.parse(item.flow_expires_at == null ? item.display_expires_at : item.flow_expires_at)>time).reverse();
    const firstVisible = followFlow ? null : Array.from(list.children).find(row=>
      row.getBoundingClientRect().bottom > viewport.getBoundingClientRect().top);
    const priorTop=firstVisible ? firstVisible.getBoundingClientRect().top : 0;
    const currentKeys=new Set(items.map(item=>item.moment_id));
    for (const [id,row] of flowRows) {
      if (!currentKeys.has(id)) { row.remove();flowRows.delete(id); }
    }
    const currentCover = displayArtwork.get(read(projection,["artwork","reference"]));
    items.forEach((item,index)=>{
      let row=flowRows.get(item.moment_id);
      if (!row) {
        row=document.createElement("li");
        const meta=document.createElement("div"), label=document.createElement("span");
        const content=document.createElement("p"), body=document.createElement("div");
        meta.className="flow-meta";
        label.className="flow-kind";
        meta.appendChild(label);
        const publishedAt=item.published_at || item.created_at;
        const published=new Date(Date.parse(publishedAt || ""));
        if (Number.isFinite(published.getTime())) {
          const stamp=document.createElement("time");
          stamp.dateTime=publishedAt;
          stamp.textContent=`${String(published.getHours()).padStart(2,"0")}:${String(published.getMinutes()).padStart(2,"0")}`;
          meta.appendChild(stamp);
        }
        content.textContent=item.content;
        body.append(meta,content);
        row.appendChild(body);
        const citations = item.type==="dj_bulletin" ? bulletinCitations(item.sources) : qualifiedCitations(item.sources);
        const attribution = item.source_attribution;
        const sources = citations || (attribution && attribution.provider && publicCitationURL(attribution.url) ? [attribution] : []);
        if (sources.length) {
          const links = document.createElement("div");
          links.className="flow-sources";
          for (const source of sources) {
            const link=document.createElement("a");
            link.href=source.revision_url || source.url;
            const spotifyLogo=e("spotify-source").querySelector("img");
            if(source.provider==="Spotify" && spotifyLogo){
              const logo=document.createElement("img");logo.src=spotifyLogo.src;logo.alt="Spotify";
              link.appendChild(logo);link.setAttribute("aria-label","Spotify");
            }else link.textContent=[source.title,source.provider,source.attributed_author || source.license].filter(Boolean).join(" · ");
            link.target="_blank";
            link.rel="noopener noreferrer";
            links.appendChild(link);
          }
          body.appendChild(links);
        }
        flowRows.set(item.moment_id,row);
      }
      row.querySelector(".flow-kind").textContent=item.type==="playback_observed" ? observedLabels[root.lang] || observedLabels.en : text.types[item.type] || item.title || "";
      const cover = item.artwork ? displayArtwork.get(item.artwork.reference) : currentCover;
      const source = read(item,["artwork","source_url"]) || read(item,["source_attribution","url"]) || playback().source_url || "";
      const showCover = cover && item.playback_item_id === cover.item_id
        && (!item.artwork || /^https:\/\/open\.spotify\.com\/track\/[A-Za-z0-9]{22}$/.test(source));
      let artLink = row.querySelector(".flow-artwork-link");
      if (showCover) {
        if (!artLink) {
          artLink = document.createElement("a");
          artLink.className = "flow-artwork-link";
          artLink.target = "_blank";
          artLink.rel = "noopener noreferrer";
          artLink.setAttribute("aria-label","Spotify");
          const image = document.createElement("img");
          image.className = "flow-artwork";
          image.alt = "";
          artLink.appendChild(image);
          row.insertBefore(artLink,row.firstElementChild);
        }
        if (/^https:\/\/open\.spotify\.com\/track\/[A-Za-z0-9]{22}$/.test(source))artLink.href = source;
        else artLink.removeAttribute("href");
        const image = artLink.firstElementChild;
        if (image.getAttribute("src") !== cover.url) image.src = cover.url;
      } else if (artLink) {
        artLink.remove();
      }
      row.className="flow-card flow-age-"+Math.min(3,index)+(showCover ? " flow-with-artwork" : "");
      if (list.children[index] !== row) list.insertBefore(row,list.children[index] || null);
    });
    if (followFlow) viewport.scrollTop=0;
    if (firstVisible && firstVisible.isConnected) {
      viewport.scrollTop+=firstVisible.getBoundingClientRect().top-priorTop;
    }
    live.hidden=followFlow || !items.length;
    if (items.length) {
      const expiry=Math.min(...items.map(item=>Date.parse(item.flow_expires_at == null ? item.display_expires_at : item.flow_expires_at)));
      flowExpiry=window.setTimeout(renderFlow,Math.max(0,expiry-Date.now()));
    }
    return true;
  }
  function clearFlowReturn() {
    if(flowReturnTimer!==undefined)window.clearTimeout(flowReturnTimer);
    flowReturnTimer=undefined;
  }
  function connectFlowControls() {
    const viewport=e("flow-viewport"), live=e("flow-live");
    if (!viewport || !live) return;
    const returnToLive=focus=>{
      clearFlowReturn();
      followFlow=true;
      manualFlowScroll=false;
      viewport.scrollTo({top:0,behavior:"auto"});
      if(focus)viewport.focus({preventScroll:true});
      live.hidden=true;
    };
    const scheduleReturn=()=>{
      clearFlowReturn();
      flowReturnTimer=window.setTimeout(()=>returnToLive(false),15000);
    };
    const startManual=()=>{
      manualFlowScroll=true;
      if (followFlow && !atLiveEdge(viewport)) {
        viewport.scrollTo({top:viewport.scrollTop,behavior:"auto"});
        followFlow=false;
        live.hidden=false;
      }
      if(!followFlow)scheduleReturn();
    };
    for (const event of ["wheel","touchstart","touchmove","pointerdown"]) viewport.addEventListener(event,startManual,{passive:true});
    viewport.addEventListener("pointermove",event=>{if(event.buttons)startManual();},{passive:true});
    viewport.addEventListener("keydown",event=>{
      const page = viewport.clientHeight;
      const steps = {ArrowUp:-48, ArrowDown:48, PageUp:-page, PageDown:page,
        Home:-viewport.scrollHeight, End:viewport.scrollHeight, " ":event.shiftKey ? -page : page};
      if (!Object.prototype.hasOwnProperty.call(steps,event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
      event.preventDefault();
      startManual();
      viewport.scrollTop+=steps[event.key];
    });
    viewport.addEventListener("scroll",()=>{
      if (!manualFlowScroll) return;
      const wasFollowing=followFlow;
      followFlow=atLiveEdge(viewport);
      live.hidden=followFlow;
      if (followFlow) {
        clearFlowReturn();
        manualFlowScroll=false;
      } else if(wasFollowing) scheduleReturn();
    },{passive:true});
    live.addEventListener("click",()=>returnToLive(true));
  }
  const outputLabels = {
    en:["Speaker","Playback progress"], nl:["Speaker","Voortgang"],
    de:["Lautsprecher","Wiedergabefortschritt"],
    fr:["Enceinte","Progression de la lecture"],
    es:["Altavoz","Progreso de reproducción"]
  };
  function renderDisplayPlayback(p, hasProgress) {
    const [speakerLabel, progressLabel] = outputLabels[root.lang] || outputLabels.en;
    const active = !!p.title && (p.state==="playing" || p.state==="paused");
    const output = active && typeof p.output_label==="string" ? p.output_label : "";
    e("display-meter").hidden=!active;
    e("display-timing").hidden=!active || e("spotify-source").hidden;
    e("time").hidden=!active || !hasProgress;
    e("display-equalizer").classList.toggle("playing",active && p.state==="playing");
    e("progress").setAttribute("aria-label",progressLabel);
    e("display-output").hidden=!output;
    e("display-speaker").hidden=!output;
    e("display-speaker-label").textContent=output;
    e("display-speaker").setAttribute("aria-label",speakerLabel+": "+output);
  }
  const sessionIconGroups = [
    ["mood","selected_mood",{
      chill:"M15 16a8 8 0 0 1-7-11 8 8 0 1 0 11 11z M16 3v4m-2-2h4m2 4v2m-1-1h2",
      groove:"M3 10v4m4-7v10m5-14v18m5-14v10m4-7v4",
      energy:"m13 2-9 12h7l-1 8 10-12h-7z",
      party:"m4 20 4-12 8 8z M10 10l2-5m2 7 6-3m-2 7 3 1M17 3v4m-2-2h4"
    }],
    ["persona","dj_persona",{
      home_dj:"m3 11 9-8 9 8M5 10v10h14V10m-9 10v-6h4v6",
      radio_dj:"M5 8l13-5M5 8h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2zm4 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm6-4h3m-3 4h3",
      club_dj:"M21 12a9 9 0 1 0-18 0 9 9 0 0 0 18 0zm-7 0a2 2 0 1 0-4 0 2 2 0 0 0 4 0zm2-6 2 2",
      festival_dj:"M7 14a4 4 0 1 1 6-5l-6 5zm0 0-4 6 2 1 6-7m6-8 4-1v9m0 0a2 1.5 0 1 0-4 0 2 1.5 0 0 0 4 0z"
    }],
    ["presence","selected_presence",{
      music_only:"M10 17V6l9-2v11m-9 2a3 2 0 1 0-6 0 3 2 0 0 0 6 0zm9-2a3 2 0 1 0-6 0 3 2 0 0 0 6 0z",
      occasional:"M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-8l-6 4v-4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z",
      balanced:"M4 4h10a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H8l-4 3v-3a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm14 5h2a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2v3l-4-3h-4a2 2 0 0 1-2-2",
      presenter:"M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zm-6 7v1a6 6 0 0 0 12 0v-1m-6 7v4m-3 0h6"
    }]
  ];
  // Labels follow the four glyph choices in each group, in Apple UI order.
  const sessionIconCopy = {
    en:[["Mood","Chill","Groove","Energy","Party"],["DJ character","Home DJ","Radio DJ","Club DJ","Festival DJ"],["DJ presence","Music only","Occasionally","Balanced","Presenter"]],
    nl:[["Stemming","Rustig","Groove","Energie","Feest"],["DJ karakter","Thuis-dj","Radio-dj","Club-dj","Festival-dj"],["DJ aanwezigheid","Alleen muziek","Af en toe","Gebalanceerd","Presentator"]],
    de:[["Stimmung","Entspannt","Groove","Energie","Party"],["DJ-Charakter","DJ zu Hause","Radio-DJ","Club-DJ","Festival-DJ"],["DJ-Präsenz","Nur Musik","Gelegentlich","Ausgewogen","Moderator"]],
    fr:[["Ambiance","Détente","Groove","Énergie","Fête"],["Caractère du DJ","DJ à la maison","DJ radio","DJ de club","DJ de festival"],["Présence du DJ","Musique uniquement","De temps en temps","Équilibré","Présentateur"]],
    es:[["Ambiente","Tranquilo","Groove","Energía","Fiesta"],["Carácter del DJ","DJ en casa","DJ de radio","DJ de club","DJ de festival"],["Presencia del DJ","Solo música","De vez en cuando","Equilibrado","Presentador"]]
  };
  function renderSessionIcons() {
    const group=e("session-icons");
    if (!group) return;
    const labels=sessionIconCopy[root.lang] || sessionIconCopy.en;
    let visible=false;
    sessionIconGroups.forEach(([name,key,glyphs],index)=>{
      const icon=e("session-"+name+"-icon");
      const path=icon && icon.lastElementChild, tooltip=e("session-"+name+"-tooltip");
      if (!path || !tooltip) return;
      const value=snapshotAccepted && !ended ? read(projection,["session",key]) : null;
      const glyphIndex=Object.keys(glyphs).indexOf(value);
      if (glyphIndex<0) {
        icon.setAttribute("hidden","");
        path.removeAttribute("d");
        tooltip.textContent="";
        icon.removeAttribute("aria-label");
        return;
      }
      icon.removeAttribute("hidden");
      visible=true;
      path.setAttribute("d",glyphs[value]);
      const label=labels[index][0]+": "+labels[index][glyphIndex+1];
      tooltip.textContent=label;
      icon.setAttribute("aria-label",label);
    });
    group.hidden=!visible;
  }
  function updateArtworkPlaceholder() {
    const image=e("artwork"), placeholder=e("artwork-placeholder");
    if (!placeholder) return;
    const loaded=lastArtwork && image.complete && image.naturalWidth > 0;
    image.hidden=!loaded;
    placeholder.hidden=!playback().title || !!loaded;
    placeholder.classList.toggle("playing",playback().state==="playing");
  }
  function render(animate=false) {
    const languageChanged=useLanguage(); updateClock();
    const sessionActive=snapshotAccepted && !ended;
    e("state").hidden=sessionActive;
    if (sessionActive) e("state").textContent=text.live;
    renderSessionIcons();
    renderSessionChange();
    renderDisplayViewStatus();
    renderScene();
    const p = playback(), mood = read(projection,["session","selected_mood"]);
    document.body.classList.toggle("idle",!sessionActive && !p.title);
    e("mood").textContent = mood || text.ambient;
    e("title").textContent = p.title || (sessionActive ? waitingMusicLabels[root.lang] || waitingMusicLabels.en : text.waiting);
    e("artist").textContent = p.artist || "";
    e("album").textContent = p.album || "";
    const next=p.up_next;
    const safeNext=next && typeof next === "object" && next.title && next.artist && p.item_id && next.current_item_id === p.item_id && Date.parse(next.expires_at || "") > Date.now();
    e("up-next").hidden=!safeNext;
    e("next-label").textContent=nextLabels[root.lang] || nextLabels.en;
    e("next-title").textContent=safeNext ? next.title : "";
    e("next-artist").textContent=safeNext ? next.artist : "";
    e("next-art").hidden=!(safeNext && next.artwork_url);
    if (safeNext && next.artwork_url) e("next-art").src=asset(next.artwork_url);
    else e("next-art").removeAttribute("src");
    const validSpotify=String(p.source_url || "").startsWith("https://open.spotify.com/track/");
    e("spotify-source").hidden=!validSpotify;
    if (validSpotify) e("spotify-source").href=p.source_url; else e("spotify-source").removeAttribute("href");
    const cover = displayArtwork.get(read(projection,["artwork","reference"]));
    const art = displayHost
      ? (cover && cover.item_id === p.item_id ? cover.url : "")
      : asset(p.artwork_url || "");
    e("artwork").hidden = !art;
    const artworkCard = e("artwork-card");
    if (artworkCard) artworkCard.hidden = !p.title && !art;
    if (art !== lastArtwork) {
      browserTint=undefined;
      if (root.removeAttribute) root.removeAttribute("data-art-palette");
      for (const key of ["--tone1","--tone2","--tone3","--track-background"]) root.style.removeProperty && root.style.removeProperty(key);
      root.style.setProperty("--accent",theme(mood));
      if (art) e("artwork").src = art;
      else e("artwork").removeAttribute("src");
      lastArtwork = art;
    }
    updateArtworkPlaceholder();
    setBrowserTheme(p.title ? browserTint || "#141222" : "#191b3a");
    e("artwork").alt = art ? (p.album || p.title || "") : "";
    root.style.setProperty("--art",art ? `url("${art.split('"').join('%22')}")` : "none");
    if (!art) root.style.setProperty("--accent",theme(mood));
    const active = Number.isFinite(p.duration_ms) && Number.isFinite(p.position_ms) && p.duration_ms > 0;
    e("progress").hidden = !active;
    if (active) { e("progress").max=p.duration_ms; e("progress").value=p.position_ms; e("time").textContent=`${format(p.position_ms)} / ${format(p.duration_ms)}`; }
    else e("time").textContent="";
    if (displayHost) {
      renderDisplayPlayback(p,active);
      renderHorizon(renderFlow());
      renderSpotlight(languageChanged);
    } else renderCards(animate,languageChanged);
    reportPresentation();
  }
  function apply(snapshot) {
    const watermark = Number(read(snapshot,["broadcast","snapshot_watermark"]));
    if (Number.isFinite(watermark) && watermark < lastSequence) return;
    if (Number.isFinite(watermark)) lastSequence = snapshotSequence = watermark;
    fieldSequences = {};
    projection = snapshot && typeof snapshot === "object" ? snapshot : {};
    render(false);
  }
  function event(frame) {
    const p = (frame && frame.payload);
    if (ended || !p || typeof p !== "object" || (frame.session_id && frame.session_id !== sessionId)) return;
    const sequence = Number(frame.delivery_sequence);
    const ordered = Number.isFinite(sequence) && sequence > 0;
    if (ordered && sequence <= snapshotSequence) return;
    if (ordered) lastSequence = Math.max(lastSequence,sequence);
    if (frame.event_type === "runtime_ended" || frame.event_type === "broadcast_stopped") {
      snapshotAccepted=false; reportStatus("ended","runtime_end"); ended=true; broadcastToken=null; apply({}); e("state").textContent=text.idle; if (socket) socket.close(); return;
    }
    for (const key of ["session","playback","planner","session_flow","audience","broadcast","native_delivery"])
      if (p[key] && (!ordered || sequence > (fieldSequences[key] || snapshotSequence))) {
        projection[key]=p[key];
        if (ordered) fieldSequences[key]=sequence;
      }
    if (p.dj_moment) {
      const items = Array.isArray(projection.dj_moments) ? projection.dj_moments : [];
      const key = keyFor(p.dj_moment);
      if (!items.some(item => item && keyFor(item) === key)) projection.dj_moments = [...items.slice(-23),p.dj_moment];
      render(true);
    } else render(false);
  }
  window.addEventListener("resize",fitBubble);
  e("artwork").addEventListener("error",updateArtworkPlaceholder);
  e("artwork").addEventListener("load",()=>{
    updateArtworkPlaceholder();
    fitBubble();
    // Sample colors only; never display cropped/blurred Spotify artwork.
    const image=e("artwork"), identity=lastArtwork;
    if (!identity || !image.naturalWidth) return;
    try {
      const canvas=document.createElement("canvas"); canvas.width=24; canvas.height=24;
      const ctx=canvas.getContext("2d",{willReadFrequently:true}); ctx.drawImage(image,0,0,24,24);
      const pixels=ctx.getImageData(0,0,24,24).data, buckets=new Map();
      for (let i=0;i<pixels.length;i+=4) {
        if (pixels[i+3] < 128) continue;
        const channels=[pixels[i],pixels[i+1],pixels[i+2]];
        const key=channels.map(c=>Math.round(c/32)*32).join(",");
        const bucket=buckets.get(key) || {count:0,total:[0,0,0]}; bucket.count++;
        channels.forEach((c,index)=>bucket.total[index]+=c); buckets.set(key,bucket);
      }
      const tones=[...buckets.values()].sort((a,b)=>b.count-a.count).slice(0,3).map(b=>b.total.map(c=>Math.round(c/b.count)));
      if (identity !== lastArtwork) return;
      if (!tones.length) return;
      for (let index=0; index<3; index++) {
        const rgb=tones[index] || tones[0];
        root.style.setProperty(`--tone${index+1}`,`rgb(${rgb.map(c=>Math.round(c*.5)).join(" ")})`);
      }
      // Keep the cover hue while limiting the luminance behind light text.
      const dominant=tones[0];
      const luminance=dominant.reduce((sum,channel,index)=>
        sum+[.2126,.7152,.0722][index]*Math.pow(channel/255,2.2),0);
      const shade=Math.min(.68,Math.pow(.11/luminance,1/2.2));
      const trackBackground=dominant.map(channel=>Math.round(channel*shade));
      root.style.setProperty("--track-background",`rgb(${trackBackground.join(", ")})`);
      browserTint=`rgb(${trackBackground.map(channel=>Math.round(channel*.48)).join(", ")})`;
      setBrowserTheme(browserTint);
      root.style.setProperty("--accent",`rgb(${tones[0].map(c=>Math.max(100,c)).join(" ")})`);
      root.setAttribute("data-art-palette","");
    } catch (_) { /* Same-origin proxy unavailable: keep the neutral palette. */ }
  });
  const url = () => `${haOrigin ? haOrigin.replace(/^https:/,"wss:").replace(/^http:/,"ws:") : (window.location.protocol === "https:" ? "wss:" : "ws:")+"//"+window.location.host}/api/djconnect/v1/session/broadcast/ws/${encodeURIComponent(sessionId)}?broadcast_token=${encodeURIComponent(broadcastToken)}`;
  function connect() {
    if (ended) return;
    snapshotAccepted=false; reportStatus("connecting");
    e("state").hidden=false;
    e("state").textContent=text.connecting;
    const active = new WebSocket(url()); socket=active;
    active.onopen=() => { if (active !== socket || ended) return; attempts=0; };
    active.onmessage=({data}) => {
      if (active !== socket || ended) return;
      try {
        const f=JSON.parse(data);
        if (f.type === "snapshot" && (!f.session_id || f.session_id === sessionId)) {
          if (staticHost && (!f.capabilities || f.capabilities.view_broadcast !== true || f.capabilities.owner_controls !== false || !f.snapshot || !f.snapshot.session || f.snapshot.session.session_id !== sessionId || (f.snapshot.schema_version !== undefined && f.snapshot.schema_version !== 1))) { reportStatus("error","incompatible_snapshot"); stopHost(); e("state").textContent=compatibility[root.lang] || compatibility.en; return; }
          const watermark=Number(read(f.snapshot,["broadcast","snapshot_watermark"]));
          if (Number.isFinite(watermark) && watermark<lastSequence) return;
          snapshotAccepted=true; reportStatus("snapshot_accepted");
          apply(f.snapshot);
        }
        else if (f.type === "event") event(f.data);
        else if (f.type === "error") { snapshotAccepted=false; reportStatus("error","access_rejected"); ended=true; broadcastToken=null; apply({}); e("state").textContent=text.unavailable; if (socket) socket.close(); }
      } catch (_) { /* Ignore malformed receiver frames. */ }
    };
    active.onclose=() => {
      if (active !== socket || ended || reconnectTimer) return;
      snapshotAccepted=false; reportStatus("recovering");
      renderSessionIcons();
      reconnectTimer=window.setTimeout(() => { reconnectTimer=undefined; attempts++; connect(); },Math.min(1000*2**attempts,5000));
    };
    active.onerror=() => active.close();
  }
  updateClock();
  e("state").textContent=text.idle;
  e("title").textContent=text.waiting;
  e("mood").textContent=text.ambient;
  if (sessionId && broadcastToken) connect(); else if (!displayHost) e("state").textContent=text.unavailable;
  window.addEventListener("djconnect-handoff",({detail}) => {
    if (displayHost) return;
    if (!(detail && detail.session_id) || !(detail && detail.broadcast_token)) return;
    stopHost();
    haOrigin=detail.ha_url || ""; sessionId=detail.session_id; broadcastToken=detail.broadcast_token;
    statusGeneration=detail.status_generation === undefined ? null : detail.status_generation;
    snapshotAccepted=false; ended=false; projection={}; playbackItem=""; lastShownAt=-Infinity;
    lastSequence=0; snapshotSequence=0; fieldSequences={}; clearCards(); render(false);
    e("handoff").hidden=true; connect();
  });
  function stopHost() {
    clearLiveStatus();
    clearSessionChange();
    displayViewRevision=-1;
    reportStatus("stopped","host_stop"); snapshotAccepted=false; statusGeneration=null;
    ended=true; broadcastToken=null;
    if (reconnectTimer) window.clearTimeout(reconnectTimer); reconnectTimer=undefined;
    const old=socket; socket=null; if (old) old.close();
    firstSeen.clear(); placementCount=0; lastPlacedKey=""; lastShownAt=-Infinity;
    projection={}; clearCards(); render(false); e("state").textContent=text.idle;
  }
  window.addEventListener("djconnect-host-stop",stopHost);
  window.addEventListener("beforeunload",stopHost);
  if (displayHost || staticHost) {
    const originalSlots=["moment-cards","progress","time","spotify-source"].map(id=>{
      const node=e(id);return {node,parent:node.parentNode,next:node.nextSibling};});
    let controlsConnected=false;
    function layoutDisplay(enabled){
      if(enabled){
        e("shared-flow").appendChild(e("moment-cards"));
        e("display-meter").append(e("progress"),e("time"));
        e("display-timing").appendChild(e("spotify-source"));
        if(!controlsConnected){connectFlowControls();controlsConnected=true;}
      }else{
        for(const {node,parent,next} of originalSlots.slice().reverse())parent.insertBefore(node,next);
      }
    }
    if(displayHost)layoutDisplay(true);
    if(staticHost){
      window.addEventListener("djconnect-cast-display-mode",()=>{stopHost();displayHost=true;layoutDisplay(true);});
      window.addEventListener("djconnect-cast-legacy-mode",()=>{const wasDisplay=displayHost;stopHost();displayHost=false;if(wasDisplay)layoutDisplay(false);});
    }
    window.addEventListener("djconnect-live-status",({detail})=>renderLiveStatus(detail));
    window.addEventListener("djconnect-display-locale",({detail}) => {
      displayLocale=typeof detail==="string" && /^(en|nl|de|fr|es)$/.test(detail) ? detail : "";
      const state=e("state");
      const status=["idle","connecting","unavailable","live"].find(key=>text[key]===state.textContent);
      render(false);
      if (!snapshotAccepted && status) state.textContent=text[status];
    });
    window.addEventListener("djconnect-display-clear",stopHost);
    window.addEventListener("djconnect-display-artwork",({detail}) => {
      if(!displayHost)return;
      displayArtwork=new Map((Array.isArray(detail) ? detail : []).filter(cover=>String(cover.url).startsWith("blob:"))
        .map(({reference,item_id,url})=>[reference,{item_id,url}]));
      if(focusedOverlay){
        const old=Array.from(focusedOverlay.children).find(node=>node.tagName==="IMG");
        const item=(projection.shared_flow||[]).concat(projection.dj_moments||[]).find(value=>value.moment_id===focusedMomentId);
        if(old && (!item || !displayArtwork.has((item.artwork||{}).reference)))old.remove();
      }
      render(false);
    });
    let focusedOverlay=null,focusTimer=null,focusedMomentId=null,focusedRevision=null;
    function clearSharedFocus(){
      if(focusTimer)clearTimeout(focusTimer);focusTimer=null;
      if(focusedOverlay)focusedOverlay.remove();focusedOverlay=null;focusedMomentId=focusedRevision=null;
    }
    window.addEventListener("djconnect-display-clear",clearSharedFocus);
    window.addEventListener("djconnect-shared-focus",({detail})=>{
      if(!displayHost)return;
      if(focusedOverlay && focusedRevision===(detail && detail.focus_revision))return;
      clearSharedFocus();
      const item=(projection.shared_flow||[]).concat(projection.dj_moments||[]).find(value=>value.moment_id===(detail && detail.focused_moment_id));
      const deadline=Math.min(Date.now()+Number((detail && detail.expires_in)||0)*1000,Date.parse((item && item.flow_expires_at)||(item && item.display_expires_at)||""));
      if(!item || !item.content || !(deadline>Date.now()))return;
      const overlay=document.createElement("section"),title=document.createElement("h2"),body=document.createElement("p");
      overlay.className="shared-moment-focus";overlay.setAttribute("role","region");
      title.textContent=item.title||"";body.textContent=item.content;overlay.append(title,body);
      const cover=displayArtwork.get((item.artwork && item.artwork.reference));
      if(item.type!=="live_impression" && cover && cover.item_id===item.playback_item_id && String(cover.url).startsWith("blob:")){
        const img=document.createElement("img");img.src=cover.url;img.alt="";overlay.prepend(img);
      }
      const close=document.createElement("button");close.type="button";close.textContent=(flowLabels[root.lang]||flowLabels.en)[1];
      close.onclick=()=>{clearSharedFocus();window.dispatchEvent(new Event("djconnect-display-return"));};overlay.append(close);document.body.append(overlay);focusedOverlay=overlay;focusedMomentId=item.moment_id;focusedRevision=detail.focus_revision;
      focusTimer=setTimeout(clearSharedFocus,deadline-Date.now());
    });
    window.addEventListener("djconnect-shared-photo",({detail})=>{
      if(!focusedOverlay)return;
      const previous=focusedOverlay.querySelector("figure");if(previous)previous.remove();
      if(!detail || detail.focus_revision!==focusedRevision || !String(detail.url).startsWith("blob:"))return;
      const photo=detail.photo||{},figure=document.createElement("figure"),img=document.createElement("img"),caption=document.createElement("figcaption");
      img.src=detail.url;img.alt=(photo.alt_text||{})[detail.locale] || (photo.alt_text||{}).en || "";
      caption.textContent=[photo.caption,photo.author,photo.credit,photo.license].filter(Boolean).join(" — ");
      if(/^https:\/\/commons\.wikimedia\.org\/wiki\/File:/.test(photo.source_url)){
        const link=document.createElement("a");link.href=photo.source_url;link.textContent=photo.source_url;link.target="_blank";link.rel="noreferrer noopener";caption.append(document.createElement("br"),link);
      }
      if(/^https:\/\/creativecommons\.org\//.test(photo.license_url)){
        const link=document.createElement("a");link.href=photo.license_url;link.textContent=photo.license;link.target="_blank";link.rel="noreferrer noopener";caption.append(document.createElement("br"),link);
      }
      figure.append(img,caption);focusedOverlay.prepend(figure);
    });
    window.addEventListener("djconnect-display-snapshot",({detail}) => {
      if (!displayHost || !detail || detail.contract_version !== 1 || !detail.session || detail.session.runtime_state !== "active") return;
      const labels=detail.session_presentation || {};
      sessionId=detail.session.session_id; ended=false; snapshotAccepted=true;
      if(focusedOverlay && !(detail.shared_flow||[]).concat(detail.dj_moments||[]).some(item=>item.moment_id===focusedMomentId))clearSharedFocus();
      apply({...detail,view:confirmedDisplayView(detail.view),session:{...detail.session,selected_mood:labels.mood,dj_persona:labels.persona,selected_presence:labels.presence}});
      e("state").textContent=text.live;
    });
  }
})()

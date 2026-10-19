<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>J.A.R.V.I.S — Quantum Dots</title>
<style>
  :root {
    --c:#00ffc8; --c2:#37dfff; --bg:#050810; --panel:rgba(7,14,24,.72);
    --txt:#cfe9f5; --dim:#7a96a8;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  html,body {
    height:100%; background:var(--bg); color:var(--txt); overflow:hidden;
    font-family: 'Courier New', ui-monospace, monospace;
  }
  body::before {
    content:''; position:fixed; inset:0; pointer-events:none; z-index:0;
    background:
      radial-gradient(ellipse at 20% 10%, rgba(0,120,180,.18), transparent 55%),
      radial-gradient(ellipse at 80% 90%, rgba(0,255,200,.10), transparent 55%);
  }
  #orbWrap { position:fixed; inset:0; z-index:1; display:flex; align-items:center; justify-content:center; pointer-events:none; }
  #orbCanvas { width:100%; height:100%; }

  #topbar {
    position:fixed; top:0; left:0; right:0; z-index:10;
    display:flex; align-items:center; justify-content:space-between;
    padding:12px 18px; gap:12px;
    background:linear-gradient(to bottom, rgba(5,8,16,.9), transparent);
  }
  #title { font-weight:700; letter-spacing:2px; font-size:15px; color:var(--c2); text-shadow:0 0 14px rgba(55,223,255,.6); white-space:nowrap; }
  #title span { color:#fff; }
  #topbtns { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
  button {
    background:rgba(0,255,200,.10); border:1px solid rgba(0,255,200,.55);
    color:var(--c); padding:8px 14px; border-radius:999px;
    font:600 11px ui-monospace,monospace; letter-spacing:.5px;
    cursor:pointer; backdrop-filter:blur(8px); transition:.2s; white-space:nowrap;
  }
  button:hover { background:rgba(0,255,200,.22); box-shadow:0 0 18px rgba(0,255,200,.4); }
  button.active { background:rgba(0,255,200,.85); color:#031014; border-color:#00ffc8; }
  button.warn { border-color:#ff6b81; color:#ff9aab; background:rgba(255,80,120,.10); }
  button.warn:hover { background:rgba(255,80,120,.25); }
  button:disabled { opacity:.4; cursor:not-allowed; }

  #cam { position:fixed; inset:0; width:100%; height:100%; object-fit:cover; transform:scaleX(-1); opacity:0; transition:opacity .9s; z-index:2; background:#000; }
  body.cam #cam { opacity:.88; }
  #shade { position:fixed; inset:0; pointer-events:none; z-index:3; opacity:0; transition:opacity .9s; background:radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,.6)); }
  body.cam #shade { opacity:1; }

  #statusWrap { position:fixed; top:64px; left:50%; transform:translateX(-50%); z-index:9; display:flex; gap:8px; flex-wrap:wrap; justify-content:center; max-width:96vw; }
  .pill { background:var(--panel); border:1px solid rgba(55,223,255,.35); padding:5px 12px; border-radius:999px; font-size:10.5px; letter-spacing:.5px; color:var(--dim); backdrop-filter:blur(10px); white-space:nowrap; }
  .pill b { color:var(--c); font-weight:600; }
  .pill.live { border-color:rgba(0,255,200,.7); color:var(--c); box-shadow:0 0 14px rgba(0,255,200,.25); }
  .pill.err { border-color:#ff6b81; color:#ff9aab; }

  #chat { position:fixed; right:14px; bottom:14px; z-index:9; width:min(400px, calc(100vw - 28px)); max-height:56vh; display:flex; flex-direction:column; gap:8px; }
  #log { overflow-y:auto; display:flex; flex-direction:column; gap:6px; padding:10px; border-radius:16px; background:var(--panel); backdrop-filter:blur(14px); border:1px solid rgba(0,255,200,.2); scrollbar-width:thin; }
  #log::-webkit-scrollbar { width:5px; }
  #log::-webkit-scrollbar-thumb { background:rgba(0,255,200,.3); border-radius:3px; }
  .msg { padding:8px 12px; border-radius:12px; font-size:12.5px; line-height:1.5; max-width:92%; word-wrap:break-word; animation:fade .25s ease; }
  @keyframes fade { from { opacity:0; transform:translateY(6px); } }
  .msg.user { background:rgba(55,120,220,.28); align-self:flex-end; border-bottom-right-radius:4px; }
  .msg.jarvis { background:rgba(0,255,200,.10); align-self:flex-start; border-bottom-left-radius:4px; border:1px solid rgba(0,255,200,.15); }
  .msg.sys { background:rgba(255,170,40,.10); align-self:center; font-size:11px; color:#ffcf8a; text-align:center; }
  .msg .who { font-size:9.5px; letter-spacing:1px; color:var(--dim); display:block; margin-bottom:2px; text-transform:uppercase; }
  #inputRow { display:flex; gap:8px; }
  #in { flex:1; padding:11px 16px; border-radius:999px; border:1px solid rgba(0,255,200,.4); background:rgba(7,14,24,.85); color:#e6f7ff; outline:none; font-family:inherit; font-size:13px; backdrop-filter:blur(10px); }
  #in:focus { border-color:var(--c); box-shadow:0 0 18px rgba(0,255,200,.3); }
  #in::placeholder { color:#4a6478; }
  #sendBtn { padding:11px 16px; }

  #drawer { position:fixed; top:0; right:0; height:100%; width:min(360px,92vw); z-index:20; background:rgba(5,10,18,.97); border-left:1px solid rgba(0,255,200,.25); transform:translateX(105%); transition:transform .35s cubic-bezier(.7,0,.2,1); padding:22px 18px; overflow-y:auto; backdrop-filter:blur(20px); }
  #drawer.open { transform:translateX(0); }
  #drawer h3 { font-size:12px; letter-spacing:2px; color:var(--c2); margin:18px 0 10px; text-transform:uppercase; }
  #drawer h3:first-child { margin-top:0; }
  #drawer label { display:block; font-size:11px; color:var(--dim); margin:10px 0 5px; }
  #drawer input[type=text], #drawer input[type=password], #drawer select { width:100%; padding:10px 12px; border-radius:10px; border:1px solid rgba(55,223,255,.3); background:rgba(7,14,24,.9); color:#dff; font-family:inherit; font-size:12px; outline:none; }
  #drawer input:focus, #drawer select:focus { border-color:var(--c); }
  #drawer .row { display:flex; gap:8px; margin-top:12px; }
  #drawer .row button { flex:1; }
  #drawer small { display:block; color:#4a6478; font-size:10px; line-height:1.5; margin-top:6px; }
  #drawerClose { position:absolute; top:14px; right:14px; width:34px; height:34px; padding:0; border-radius:50%; font-size:16px; display:flex; align-items:center; justify-content:center; }
  .memItem { font-size:11px; color:#9fc; padding:6px 10px; border-radius:8px; background:rgba(0,255,200,.06); border:1px solid rgba(0,255,200,.12); margin-bottom:6px; line-height:1.4; }

  #toast { position:fixed; bottom:80px; left:50%; transform:translate(-50%,20px); z-index:30; background:rgba(0,255,200,.92); color:#031014; padding:10px 20px; border-radius:999px; font-size:12px; font-weight:700; opacity:0; transition:.35s; pointer-events:none; white-space:nowrap; max-width:90vw; text-align:center; }
  #toast.show { opacity:1; transform:translate(-50%,0); }
  #toast.err { background:#ff6b81; color:#fff; }

  #perm { position:fixed; inset:0; z-index:25; display:none; align-items:center; justify-content:center; background:rgba(5,10,18,.92); backdrop-filter:blur(10px); padding:20px; }
  #perm.show { display:flex; }
  #perm .box { max-width:420px; text-align:center; padding:28px 24px; border-radius:20px; background:rgba(7,14,24,.9); border:1px solid rgba(0,255,200,.35); box-shadow:0 0 40px rgba(0,255,200,.15); }
  #perm .box h2 { font-size:16px; color:var(--c2); margin-bottom:10px; letter-spacing:1px; }
  #perm .box p { font-size:12.5px; color:var(--dim); line-height:1.6; margin-bottom:18px; }
  #perm .box button { padding:12px 24px; font-size:13px; }

  /* DIAGNOSTIK */
  #diagBtn { position:fixed; left:8px; bottom:8px; z-index:49; background:rgba(0,0,0,.7); color:#8fe; border:1px solid #0fc; border-radius:6px; padding:6px 10px; font:10px ui-monospace,monospace; cursor:pointer; }
  #diag { position:fixed; left:8px; bottom:44px; z-index:50; background:rgba(0,0,0,.92); color:#8fe; padding:10px 12px; border-radius:8px; font:11px ui-monospace,monospace; line-height:1.6; max-width:360px; max-height:60vh; overflow-y:auto; border:1px solid rgba(0,255,200,.3); display:none; }
  #diag.show { display:block; }
  #diag b { color:#0fc; }
  #diag .e { color:#ff7b8a; }
  #diag .o { color:#8fe; }
  #diagClose { float:right; cursor:pointer; color:#f88; font-weight:700; }

  @media (max-width:640px) {
    #title { font-size:12px; }
    #topbtns button { padding:7px 10px; font-size:10px; }
    #chat { max-height:60vh; }
    #statusWrap { top:56px; gap:5px; }
    .pill { font-size:9.5px; padding:4px 9px; }
    #diag { max-width:calc(100vw - 16px); }
  }
</style>
</head>
<body>

<video id="cam" autoplay playsinline muted></video>
<div id="shade"></div>
<div id="orbWrap"><canvas id="orbCanvas"></canvas></div>

<div id="topbar">
  <div id="title">🔵 J.A.R.V.I.S <span>— Quantum Dots</span></div>
  <div id="topbtns">
    <button id="camBtn">📹 Kamera</button>
    <button id="liveBtn" title="Jarvis memantau kamera terus-menerus">👁 Live</button>
    <button id="micBtn">🎙️ Mulai Dengar</button>
    <button id="setBtn">⚙️</button>
  </div>
</div>

<div id="statusWrap">
  <div class="pill" id="pillCam">📷 Kamera: <b>off</b></div>
  <div class="pill" id="pillHand">✋ Tangan: <b>—</b></div>
  <div class="pill" id="pillMode">🎛 Mode: <b>SIAP</b></div>
  <div class="pill" id="pillVoice">🔊 Suara: <b>—</b></div>
  <div class="pill" id="pillAI">🧠 AI: <b>belum</b></div>
  <div class="pill" id="pillLive">👁 Live: <b>off</b></div>
</div>

<div id="chat">
  <div id="log"></div>
  <div id="inputRow">
    <input id="in" placeholder="Ask Jarvis… (Enter)" autocomplete="off">
    <button id="sendBtn">➤</button>
  </div>
</div>

<div id="drawer">
  <button id="drawerClose">✕</button>
  <h3>Groq API</h3>
  <label>API Key (disimpan lokal di browser)</label>
  <input id="groqKey" type="password" placeholder="gsk_...">
  <small>Dapatkan gratis di console.groq.com/keys. Key hanya disimpan di localStorage perangkat ini.</small>

  <h3>Model</h3>
  <label>Model teks</label>
  <select id="modelText">
    <option value="openai/gpt-oss-120b">openai/gpt-oss-120b</option>
    <option value="openai/gpt-oss-20b">openai/gpt-oss-20b</option>
    <option value="llama-3.3-70b-versatile">llama-3.3-70b-versatile</option>
    <option value="llama-3.1-8b-instant">llama-3.1-8b-instant</option>
  </select>
  <label>Model vision (harus support gambar)</label>
  <select id="modelVision">
    <option value="qwen/qwen3.8-27b">qwen3.8-27b</option>
  </select>

  <h3>Suara</h3>
  <label>Voice (British English)</label>
  <select id="voiceSel"><option>Memuat…</option></select>
  <label>Rate</label>
  <input id="voiceRate" type="text" value="-5%" placeholder="mis. -5% atau +10%">

  <h3>Memory</h3>
  <div id="memList"><small>Belum ada memory.</small></div>
  <div class="row">
    <button id="resetMem" class="warn">🧠 Reset Memory</button>
    <button id="resetAll" class="warn">💣 Reset ALL</button>
  </div>

  <h3>Kamera</h3>
  <label><input type="checkbox" id="chkGesture" checked style="width:auto;margin-right:6px"> Aktifkan gesture 3D</label>
  <label><input type="checkbox" id="chkAutoCam" style="width:auto;margin-right:6px"> Auto-nyalakan kamera saat buka</label>
</div>

<div id="perm">
  <div class="box">
    <h2>Izin Diperlukan</h2>
    <p id="permText">Jarvis membutuhkan akses kamera dan mikrofon untuk berfungsi penuh.</p>
    <button id="permBtn">Izinkan</button>
  </div>
</div>

<div id="toast"></div>
<button id="diagBtn">🔍 diag</button>
<div id="diag"><b>Diagnostik</b> <span id="diagClose">✕</span><div id="diagBody"></div></div>

<script>
/* ============================================================
   DIAGNOSTIK GLOBAL
   ============================================================ */
(function() {
  window.__JARVIS_DIAG = [];
  window.diag = function(msg, isErr) {
    const line = (isErr ? '❌ ' : '✓ ') + msg;
    window.__JARVIS_DIAG.push({ msg: line, err: !!isErr });
    try { console.log('[JARVIS]', line); } catch(_) {}
    const b = document.getElementById('diagBody');
    if (b) {
      b.innerHTML = window.__JARVIS_DIAG.map(x =>
        `<div class="${x.err?'e':'o'}">${x.msg.replace(/</g,'&lt;')}</div>`
      ).join('');
    }
  };
  window.addEventListener('error', e => diag('JS error: ' + e.message, true));
  window.addEventListener('unhandledrejection', e => diag('Promise reject: ' + (e.reason?.message || e.reason), true));

  document.addEventListener('DOMContentLoaded', () => {
    const d = document.getElementById('diag');
    document.getElementById('diagBtn').onclick = () => d.classList.toggle('show');
    document.getElementById('diagClose').onclick = () => d.classList.remove('show');

    const proto = location.protocol;
    diag('Protocol: ' + proto);
    if (proto === 'file:') diag('FILE:// → mic & kamera DIBLOKIR. Jalankan via http://localhost', true);
    if (!window.isSecureContext) diag('Bukan secure context (HTTPS/localhost dibutuhkan)', true);
    diag('getUserMedia: ' + !!navigator.mediaDevices?.getUserMedia, !navigator.mediaDevices?.getUserMedia);
    diag('SpeechRecognition: ' + !!(window.SpeechRecognition || window.webkitSpeechRecognition),
         !(window.SpeechRecognition || window.webkitSpeechRecognition));
    diag('SpeechSynthesis: ' + ('speechSynthesis' in window), !('speechSynthesis' in window));

    if ('speechSynthesis' in window) {
      speechSynthesis.getVoices();
      setTimeout(() => {
        const n = speechSynthesis.getVoices().length;
        diag('Voices loaded: ' + n, n === 0);
      }, 700);
    }

    const k = localStorage.getItem('jarvis_groq_key');
    diag('Groq key: ' + (k ? 'ADA (' + k.slice(0, 7) + '…)' : 'KOSONG — isi di ⚙️'), !k);
  });
})();

/* ============================================================
   J.A.R.V.I.S — APP
   ============================================================ */
(() => {
'use strict';

const $ = id => document.getElementById(id);
const LS = {
  key: 'jarvis_groq_key',
  mem: 'jarvis_memory',
  chat: 'jarvis_chat',
  voice: 'jarvis_voice',
  rate: 'jarvis_rate',
  modelT: 'jarvis_model_text',
  modelV: 'jarvis_model_vision',
  conv: 'jarvis_conversation_mode',
  camAuto: 'jarvis_cam_auto',
  live: 'jarvis_live_mode',
  perm: 'jarvis_permission_granted',
};

function safeJSON(str, fallback) {
  try { return JSON.parse(str); } catch (_) { return fallback; }
}

const state = {
  memory: safeJSON(localStorage.getItem(LS.mem), []) || [],
  chat: safeJSON(localStorage.getItem(LS.chat), []) || [],
  conversationMode: localStorage.getItem(LS.conv) === '1',
  camAuto: localStorage.getItem(LS.camAuto) === '1',
  gestureOn: true,
  camStream: null,
  listening: false,
  sending: false,
  speaking: false,
  aiBusy: false,
  liveOn: localStorage.getItem(LS.live) === '1',
  lastSeen: '',
  lastSeenAt: 0,
  audioPermissionGranted: localStorage.getItem(LS.perm) === '1',
};

/* ============================================================
   ORB
   ============================================================ */
const orb = {
  canvas: $('orbCanvas'), ctx: null,
  W: 0, H: 0, cx: 0, cy: 0, dpr: 1, time: 0,
  intensity: 0, targetIntensity: 0,
  listeningScale: 1, targetListeningScale: 1,
  dots: [], NUM: 320,
  fakeFreq: null,
};

function initOrb() {
  orb.ctx = orb.canvas.getContext('2d');
  const phi = (1 + Math.sqrt(5)) / 2;
  for (let i = 0; i < orb.NUM; i++) {
    const theta = 2 * Math.PI * i / phi;
    const y = 1 - (i / (orb.NUM - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    orb.dots.push({
      x: Math.cos(theta) * r, y, z: Math.sin(theta) * r,
      baseSize: Math.random() * 0.8 + 0.8
    });
  }
  resizeOrb();
  window.addEventListener('resize', resizeOrb);
  requestAnimationFrame(drawOrb);
}

function resizeOrb() {
  orb.dpr = window.devicePixelRatio || 1;
  const rect = orb.canvas.getBoundingClientRect();
  orb.W = orb.canvas.width = Math.max(1, rect.width * orb.dpr);
  orb.H = orb.canvas.height = Math.max(1, rect.height * orb.dpr);
  orb.cx = orb.W / 2; orb.cy = orb.H / 2;
}

function drawSphere() {
  const { ctx, cx, cy, W, H, dpr, time } = orb;
  const rCore = Math.min(W, H) * 0.085 * orb.listeningScale;
  const rotY = time * 0.0012, rotX = time * 0.0007;
  const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
  const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
  const proj = [];
  for (let i = 0; i < orb.NUM; i++) {
    const d = orb.dots[i];
    const x1 = d.x * cosY - d.z * sinY;
    const z1 = d.x * sinY + d.z * cosY;
    const y2 = d.y * cosX - z1 * sinX;
    const z2 = d.y * sinX + z1 * cosX;
    proj.push({ px: cx + x1 * rCore, py: cy + y2 * rCore, z: z2, size: d.baseSize });
  }
  proj.sort((a, b) => a.z - b.z);
  for (const p of proj) {
    const depthAlpha = (p.z + 1.2) / 2.4;
    const alpha = Math.max(0.12, Math.min(0.95, depthAlpha));
    const dotSize = p.size * (0.7 + depthAlpha * 0.6) * dpr;
    ctx.beginPath();
    ctx.arc(p.px, p.py, Math.max(0.5, dotSize), 0, Math.PI * 2);
    ctx.fillStyle = `rgba(130,245,255,${alpha})`;
    ctx.fill();
  }
}

function drawOrb() {
  const { ctx, W, H, cx, cy, dpr } = orb;
  ctx.clearRect(0, 0, W, H);

  if (state.speaking && orb.fakeFreq) {
    let sum = 0;
    for (let i = 0; i < orb.fakeFreq.length; i++) sum += orb.fakeFreq[i];
    orb.targetIntensity = (sum / orb.fakeFreq.length / 255) * 2.8;
    orb.targetListeningScale = 1.0;
  } else if (state.listening) {
    orb.targetIntensity = 0;
    orb.targetListeningScale = 1.35;
  } else {
    orb.targetIntensity = 0;
    orb.targetListeningScale = 1.0;
  }
  orb.intensity += (orb.targetIntensity - orb.intensity) * 0.12;
  orb.listeningScale += (orb.targetListeningScale - orb.listeningScale) * 0.08;

  drawSphere();

  const baseR = Math.min(W, H) * 0.28 * orb.listeningScale;
  const numRings = 40, pointsPerRing = 180;

  for (let r = 0; r < numRings; r++) {
    const lp = r / numRings;
    const ringRadius = baseR + (lp - 0.5) * (18 * dpr);
    ctx.beginPath();
    for (let p = 0; p <= pointsPerRing; p++) {
      const angle = (p / pointsPerRing) * Math.PI * 2;
      let wave = 0;
      if (orb.intensity > 0.02) {
        let audioMod = 0;
        if (orb.fakeFreq && orb.fakeFreq.length) {
          const normPos = p / pointsPerRing;
          const symPos = Math.sin(normPos * Math.PI);
          const freqIdx = Math.floor(symPos * (orb.fakeFreq.length * 0.5));
          audioMod = orb.fakeFreq[freqIdx] / 255;
        }
        wave += audioMod * 25 * dpr * orb.intensity;
        wave += Math.sin(angle * 8 + orb.time * 0.005 + r * 0.12) * 10 * dpr * orb.intensity;
        wave += Math.cos(angle * 12 - orb.time * 0.003) * 6 * dpr * orb.intensity;
      }
      const cr = ringRadius + wave;
      const x = cx + Math.cos(angle) * cr;
      const y = cy + Math.sin(angle) * cr;
      if (p === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath();
    let alpha = 0.15 + (1 - Math.abs(lp - 0.5) * 2) * 0.5;
    if (orb.intensity > 0.02) alpha += orb.intensity * 0.25;
    ctx.strokeStyle = 'rgba(0,242,210,' + Math.min(alpha, 0.95) + ')';
    ctx.lineWidth = (0.8 + (1 - Math.abs(lp - 0.5)) * 0.6) * dpr;
    ctx.stroke();
  }
  orb.time += 16;
  requestAnimationFrame(drawOrb);
}

/* ============================================================
   TTS (Web Speech API)
   ============================================================ */
const tts = { voices: [], sel: null, rate: 1, ready: false };

function loadVoices() {
  if (!('speechSynthesis' in window)) {
    diag('TTS tidak didukung browser ini', true);
    return;
  }
  const all = speechSynthesis.getVoices();
  if (!all.length) return;
  tts.voices = all;
  const sel = $('voiceSel');
  if (!sel) return;
  sel.innerHTML = '';
  const en = all.filter(v => /^en/i.test(v.lang));
  const pool = en.length ? en : all;
  pool.sort((a, b) => {
    const score = v => (v.lang === 'en-GB' ? 0 : v.lang === 'en-US' ? 1 : 2);
    return score(a) - score(b);
  });
  for (const v of pool) {
    const opt = document.createElement('option');
    opt.value = v.name;
    opt.textContent = `${v.name} (${v.lang})`;
    sel.appendChild(opt);
  }
  const saved = localStorage.getItem(LS.voice);
  if (saved && [...sel.options].some(o => o.value === saved)) {
    sel.value = saved; tts.sel = saved;
  } else if (sel.options.length) {
    tts.sel = sel.options[0].value;
  }
  const savedRate = localStorage.getItem(LS.rate) || '-5%';
  $('voiceRate').value = savedRate;
  tts.rate = parseRate(savedRate);
  tts.ready = true;
  diag('Voices ready: ' + pool.length);
}

if ('speechSynthesis' in window) {
  speechSynthesis.onvoiceschanged = loadVoices;
  setTimeout(loadVoices, 300);
  setTimeout(loadVoices, 1200);
}

function parseRate(str) {
  const m = String(str).match(/([+-]?\d+(?:\.\d+)?)\s*%/);
  if (m) return 1 + parseFloat(m[1]) / 100;
  const f = parseFloat(str);
  return isNaN(f) ? 1 : f;
}

function sanitizeForTTS(text) {
  return String(text)
    .replace(/\$\$[\s\S]*?\$\$/g, ' formula ')
    .replace(/\$[^$]*\$/g, ' formula ')
    .replace(/```[\s\S]*?```/g, ' code ')
    .replace(/`[^`]*`/g, ' ')
    .replace(/[*#_`>]/g, '')
    .replace(/\[(.*?)\]/g, '$1')
    .replace(/\(.*?\)/g, '')
    .replace(/[—–]/g, ', ')
    .replace(/\.\.\./g, ', ')
    .replace(/\s+/g, ' ').trim();
}

let fakeAnimTimer = null;
function startFakeAnalyser() {
  if (!orb.fakeFreq) orb.fakeFreq = new Uint8Array(128);
  cancelAnimationFrame(fakeAnimTimer);
  const tick = () => {
    if (!state.speaking) return;
    const t = performance.now() / 120;
    for (let i = 0; i < orb.fakeFreq.length; i++) {
      const v = 128 + 100 * Math.sin(t + i * 0.3) * Math.sin(i * 0.15);
      orb.fakeFreq[i] = Math.max(0, Math.min(255, v | 0));
    }
    fakeAnimTimer = requestAnimationFrame(tick);
  };
  tick();
}
function stopFakeAnalyser() {
  cancelAnimationFrame(fakeAnimTimer);
  if (orb.fakeFreq) orb.fakeFreq.fill(0);
}

function speak(text) {
  if (!('speechSynthesis' in window)) {
    diag('TTS tidak tersedia', true);
    return;
  }
  const clean = sanitizeForTTS(text);
  if (!clean) return;

  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(clean);
  u.lang = 'en-GB';
  u.rate = tts.rate;
  if (tts.sel) {
    const v = tts.voices.find(x => x.name === tts.sel);
    if (v) u.voice = v;
  }
  u.onstart = () => {
    state.speaking = true;
    setPill('pillVoice', 'Suara', 'berbicara');
    startFakeAnalyser();
  };
  u.onend = () => {
    state.speaking = false;
    stopFakeAnalyser();
    setPill('pillVoice', 'Suara', '—');
    if (state.conversationMode) setTimeout(resumeListening, 400);
  };
  u.onerror = (e) => {
    diag('TTS error: ' + (e.error || e.name || 'unknown'), true);
    state.speaking = false;
    stopFakeAnalyser();
    setPill('pillVoice', 'Suara', 'error');
    if (state.conversationMode) setTimeout(resumeListening, 400);
  };
  try { speechSynthesis.speak(u); }
  catch (e) { diag('speak() failed: ' + e.message, true); }
}

/* ============================================================
   SPEECH RECOGNITION
   ============================================================ */
const recog = {
  engine: null, committed: '', interim: '',
  silenceTimer: null, running: false, manualStop: false,
  SILENCE_MS: 1200, RESTART_MS: 300,
};

function initRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    diag('SpeechRecognition tidak didukung — pakai Chrome/Edge', true);
    return null;
  }
  const r = new SR();
  r.continuous = true;
  r.interimResults = true;
  r.lang = 'id-ID';
  r.maxAlternatives = 1;

  r.onstart = () => {
    recog.running = true;
    diag('Recognition started');
    $('micBtn').classList.add('active');
    $('micBtn').textContent = '⏹ Stop Dengar';
    setPill('pillVoice', 'Suara', 'mendengar');
  };

  r.onresult = (e) => {
    if (state.sending) return;
    let nf = '', it = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i];
      if (res.isFinal) nf += res[0].transcript + ' ';
      else it += res[0].transcript + ' ';
    }
    if (nf.trim()) recog.committed = (recog.committed + ' ' + nf).replace(/\s+/g, ' ').trim();
    recog.interim = it.replace(/\s+/g, ' ').trim();
    const combined = (recog.committed + ' ' + recog.interim).replace(/\s+/g, ' ').trim();
    if (combined) setPill('pillVoice', 'Suara', '“' + combined.slice(-40) + '”');
    if (recog.silenceTimer) clearTimeout(recog.silenceTimer);
    recog.silenceTimer = setTimeout(finalizeSpeech, recog.SILENCE_MS);
  };

  r.onerror = (e) => {
    if (e.error === 'no-speech' || e.error === 'aborted') return;
    diag('Recognition error: ' + e.error, true);
    if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
      stopListening(true);
      toast('Izin mikrofon ditolak — klik ikon 🔒 di address bar → Mikrofon → Allow', true);
    } else if (e.error === 'network') {
      toast('Error network recognition — cek koneksi', true);
    }
  };

  r.onend = () => {
    recog.running = false;
    if (state.listening && !recog.manualStop && !state.sending) {
      setTimeout(() => {
        if (state.listening && !recog.running && !state.sending) {
          try { r.start(); } catch (_) {}
        }
      }, recog.RESTART_MS);
    }
  };
  return r;
}

function finalizeSpeech() {
  if (state.sending) return;
  const text = (recog.committed + ' ' + recog.interim).replace(/\s+/g, ' ').trim();
  if (!text) return;
  state.sending = true;
  if (recog.silenceTimer) { clearTimeout(recog.silenceTimer); recog.silenceTimer = null; }
  try { recog.engine.stop(); } catch (_) {}
  setTimeout(() => {
    sendMessage(text);
    state.sending = false;
  }, 300);
}

function startListening() {
  if (!recog.engine) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      diag('Browser tidak mendukung Speech Recognition', true);
      toast('Pakai Chrome/Edge untuk voice mode', true);
    } else {
      diag('Recognition engine gagal dibuat', true);
    }
    return;
  }
  if (state.listening) return;
  recog.manualStop = false;
  state.sending = false;
  recog.committed = ''; recog.interim = '';
  state.listening = true;
  state.conversationMode = true;
  localStorage.setItem(LS.conv, '1');
  if (recog.silenceTimer) { clearTimeout(recog.silenceTimer); recog.silenceTimer = null; }
  try { recog.engine.start(); }
  catch (e) {
    diag('recog.start gagal: ' + e.message, true);
    try { recog.engine.stop(); } catch (_) {}
    setTimeout(() => { try { recog.engine.start(); } catch (_) {} }, 300);
  }
  $('micBtn').classList.add('active');
  $('micBtn').textContent = '⏹ Stop Dengar';
}

function stopListening(force) {
  recog.manualStop = true;
  state.listening = false;
  state.sending = false;
  if (recog.silenceTimer) { clearTimeout(recog.silenceTimer); recog.silenceTimer = null; }
  if (recog.engine) { try { recog.engine.stop(); } catch (_) {} }
  $('micBtn').classList.remove('active');
  $('micBtn').textContent = '🎙️ Mulai Dengar';
  setPill('pillVoice', 'Suara', '—');
  if (force !== true) {
    state.conversationMode = false;
    localStorage.setItem(LS.conv, '0');
  }
}

function resumeListening() {
  if (!state.conversationMode || state.listening) return;
  if (!recog.engine) return;
  state.sending = false;
  recog.manualStop = false;
  recog.committed = ''; recog.interim = '';
  state.listening = true;
  if (!recog.running) {
    try { recog.engine.start(); } catch (_) {}
  }
  $('micBtn').classList.add('active');
  $('micBtn').textContent = '⏹ Stop Dengar';
  setPill('pillVoice', 'Suara', 'mendengar');
}

/* ============================================================
   CAMERA + HAND GESTURE
   ============================================================ */
const hand = {
  landmarker: null, running: false, lastTs: -1,
  cube: { rx: 0.5, ry: 0.5, scale: 1, ox: 0, oy: 0 },
  target: { rx: 0.5, ry: 0.5, scale: 1, ox: 0, oy: 0 },
  smooth: { index: null, palm: null, mid: null },
  prev: { index: null, palm: null, mid: null },
  vel: { rx: 0, ry: 0 },
  mode: null, candidate: null, holdStart: 0, lastSeen: 0,
  zoomBase: null,
  panGrab: null, panLost: 0,
  PINCH_ENTER: 0.065, PINCH_EXIT: 0.095, HOLD: 0.7, PAN_HOLD: 0.4, PAN_GRACE: 250,
  vertices: [[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],
  edges: [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]],
};

async function startCamera() {
  if (state.camStream) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    diag('getUserMedia TIDAK ADA — bukan HTTPS/localhost', true);
    toast('Kamera butuh HTTPS atau localhost', true);
    return;
  }
  try {
    diag('Meminta izin kamera…');
    state.camStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 960 }, height: { ideal: 720 } }, audio: false
    });
    diag('Kamera OK');
    $('cam').srcObject = state.camStream;
    await new Promise(r => {
      if ($('cam').readyState >= 2) r();
      else $('cam').onloadedmetadata = r;
    });
    document.body.classList.add('cam');
    $('camBtn').classList.add('active');
    setPill('pillCam', 'Kamera', 'on');
    if (state.liveOn && !live.timer) setLive(true);
    if (state.gestureOn) {
      try {
        await loadLandmarker();
        if (!hand.running) { hand.running = true; handLoop(); }
      } catch (e) {
        diag('MediaPipe gagal: ' + e.message, true);
        toast('Gesture 3D tidak aktif (MediaPipe gagal load)', true);
      }
    }
  } catch (e) {
    diag('Kamera error: ' + e.name + ' ' + e.message, true);
    let msg = e.name;
    if (e.name === 'NotAllowedError') msg = 'Izin kamera ditolak — klik 🔒 di address bar → Kamera → Allow';
    else if (e.name === 'NotFoundError') msg = 'Tidak ada kamera terdeteksi';
    else if (e.name === 'NotReadableError') msg = 'Kamera dipakai aplikasi lain';
    toast('Kamera: ' + msg, true);
    setPill('pillCam', 'Kamera', 'gagal');
    state.camStream = null;
  }
}

function stopCamera() {
  hand.running = false;
  if (state.camStream) {
    state.camStream.getTracks().forEach(t => t.stop());
    state.camStream = null;
  }
  $('cam').srcObject = null;
  document.body.classList.remove('cam');
  $('camBtn').classList.remove('active');
  setPill('pillCam', 'Kamera', 'off');
  setPill('pillHand', 'Tangan', '—');
  setPill('pillMode', 'Mode', 'SIAP');
  if (state.liveOn) setLive(false);
}

async function loadLandmarker() {
  if (hand.landmarker) return;
  setPill('pillHand', 'Tangan', 'memuat…');
  diag('Memuat MediaPipe…');
  try {
    const mod = await import('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14');
    const { HandLandmarker, FilesetResolver } = mod;
    const fileset = await FilesetResolver.forVisionTasks(
      'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm'
    );
    hand.landmarker = await HandLandmarker.createFromOptions(fileset, {
      baseOptions: {
        modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
      },
      runningMode: 'VIDEO', numHands: 1,
      minHandDetectionConfidence: 0.3,
      minHandPresenceConfidence: 0.3,
      minTrackingConfidence: 0.5,
    });
    setPill('pillHand', 'Tangan', 'siap');
    diag('MediaPipe siap');
  } catch (e) {
    setPill('pillHand', 'Tangan', 'gagal');
    diag('MediaPipe error: ' + e.message, true);
    throw e;
  }
}

function smoothVal(nv, ov, a) { return ov == null ? nv : a * nv + (1 - a) * ov; }
function smoothPt(nv, ov, a) {
  return !ov ? nv : [a * nv[0] + (1 - a) * ov[0], a * nv[1] + (1 - a) * ov[1]];
}

function oneEuro(minCutoff, beta, dCutoff = 1) {
  let xPrev = null, dxPrev = 0, tPrev = 0;
  const alpha = (cutoff, dt) => 1 / (1 + 1 / (2 * Math.PI * cutoff * dt));
  return {
    reset() { xPrev = null; },
    filter(x, t) {
      if (xPrev == null) { xPrev = x; tPrev = t; dxPrev = 0; return x; }
      const dt = Math.max(0.001, (t - tPrev) / 1000);
      tPrev = t;
      const ad = alpha(dCutoff, dt);
      dxPrev = ad * ((x - xPrev) / dt) + (1 - ad) * dxPrev;
      const a = alpha(minCutoff + beta * Math.abs(dxPrev), dt);
      xPrev = a * x + (1 - a) * xPrev;
      return xPrev;
    },
  };
}
hand.panFx = oneEuro(1.2, 0.008);
hand.panFy = oneEuro(1.2, 0.008);

function videoToScreen(x, y, W, H) {
  const vw = window.innerWidth, vh = window.innerHeight;
  const s = Math.max(vw / W, vh / H);
  return [x * s + (vw - W * s) / 2, y * s + (vh - H * s) / 2];
}

function handLoop() {
  if (!hand.running) return;
  requestAnimationFrame(handLoop);
  const video = $('cam');
  if (!hand.landmarker || video.readyState < 2 || video.currentTime === hand.lastTs) return;
  hand.lastTs = video.currentTime;
  let result;
  try { result = hand.landmarker.detectForVideo(video, performance.now()); }
  catch (_) { return; }

  const lm = result.landmarks && result.landmarks[0];
  if (!lm) {
    if (Date.now() - hand.lastSeen > 400) {
      hand.mode = null; hand.candidate = null;
      hand.prev.index = hand.prev.palm = hand.prev.mid = null;
      hand.smooth.index = hand.smooth.palm = hand.smooth.mid = null;
      setPill('pillMode', 'Mode', 'SIAP');
    }
    setPill('pillHand', 'Tangan', '—');
    return;
  }
  hand.lastSeen = Date.now();
  setPill('pillHand', 'Tangan', 'terdeteksi');

  const W = video.videoWidth, H = video.videoHeight;
  const P = i => [(1 - lm[i].x) * W, lm[i].y * H];
  const thumb = P(4), index = P(8), middle = P(12), pinky = P(20), wrist = P(0);
  const palm = [(wrist[0] + middle[0]) / 2, (wrist[1] + middle[1]) / 2];

  const dIndex = Math.hypot(thumb[0] - index[0], thumb[1] - index[1]) / W;
  const dMiddle = Math.hypot(thumb[0] - middle[0], thumb[1] - middle[1]) / W;
  const dMidIndex = Math.hypot(middle[0] - index[0], middle[1] - index[1]) / W;

  hand.smooth.index = smoothPt(index, hand.smooth.index, 0.45);
  hand.smooth.palm = smoothPt(palm, hand.smooth.palm, 0.45);

  const indexUp = index[1] < wrist[1], middleUp = middle[1] < wrist[1],
        pinkyUp = pinky[1] < wrist[1], thumbUp = thumb[1] < wrist[1] - 20;
  const five = indexUp && middleUp && pinkyUp && thumbUp && dIndex > 0.1 && dMiddle > 0.1;

  let detected = null;
  // Gunakan threshold ZOOM yang lebih besar agar tidak bertabrakan dengan PAN
  if (!five) {
    if (dIndex < hand.PINCH_ENTER && dMiddle < hand.PINCH_ENTER && dMidIndex < hand.PINCH_ENTER + 0.03) detected = 'ZOOM';
    else if (dIndex < hand.PINCH_ENTER && dMiddle > hand.PINCH_ENTER + 0.03) detected = 'PAN';
    else if (indexUp && !middleUp && dIndex > hand.PINCH_ENTER) detected = 'ROTASI';
  }

  if (five) {
    if (hand.prev.palm) {
      const dx = hand.smooth.palm[0] - hand.prev.palm[0];
      const dy = hand.smooth.palm[1] - hand.prev.palm[1];
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
        hand.vel.ry += dx * 0.0008;
        hand.vel.rx += dy * 0.0008;
        setPill('pillMode', 'Mode', 'SWIPE INERTIA');
      }
    }
    hand.prev.palm = hand.smooth.palm;
    hand.mode = null; hand.candidate = null;
  } else {
    hand.prev.palm = null;
  }

  if (!hand.mode && detected) {
    if (hand.candidate !== detected) { hand.candidate = detected; hand.holdStart = Date.now(); }
    const progress = (Date.now() - hand.holdStart) / 1000 / (detected === 'PAN' ? hand.PAN_HOLD : hand.HOLD);
    if (progress >= 1) {
      hand.mode = detected;
      hand.vel.rx = 0; hand.vel.ry = 0;
      hand.target.rx = hand.cube.rx;
      hand.target.ry = hand.cube.ry;
      if (hand.mode === 'ZOOM') hand.zoomBase = dIndex;
      hand.prev.index = null;
      hand.prev.mid = null;
      hand.panGrab = null; hand.panLost = 0;
      hand.panFx.reset(); hand.panFy.reset();
    } else {
      setPill('pillMode', 'Mode', `${detected} ${Math.round(progress * 100)}%`);
    }
  } else if (!hand.mode && !detected && !five) {
    hand.candidate = null;
  }

  hand.target.ry += hand.vel.ry;
  hand.target.rx += hand.vel.rx;
  hand.vel.ry *= 0.93; hand.vel.rx *= 0.93;
  if (Math.abs(hand.vel.ry) < 0.0015) hand.vel.ry = 0;
  if (Math.abs(hand.vel.rx) < 0.0015) hand.vel.rx = 0;
  hand.cube.ry = smoothVal(hand.target.ry, hand.cube.ry, 0.2);
  hand.cube.rx = smoothVal(hand.target.rx, hand.cube.rx, 0.2);
  hand.cube.scale = smoothVal(hand.target.scale, hand.cube.scale, 0.2);

  if (hand.mode === 'ROTASI') {
    setPill('pillMode', 'Mode', 'ROTASI');
    if (hand.prev.index) {
      const dx = hand.smooth.index[0] - hand.prev.index[0];
      const dy = hand.smooth.index[1] - hand.prev.index[1];
      hand.target.ry += Math.max(-20, Math.min(20, dx)) * 0.01;
      hand.target.rx += Math.max(-20, Math.min(20, dy)) * 0.01;
    }
    hand.prev.index = hand.smooth.index;
    if (detected !== 'ROTASI') hand.mode = null;
  } else if (hand.mode === 'PAN') {
    setPill('pillMode', 'Mode', 'GESER');
    const now = performance.now();
    if (detected === 'PAN') {
      hand.panLost = 0;
      const raw = videoToScreen((thumb[0] + index[0]) / 2, (thumb[1] + index[1]) / 2, W, H);
      const fx = hand.panFx.filter(raw[0], now), fy = hand.panFy.filter(raw[1], now);
      if (!hand.panGrab) hand.panGrab = [hand.target.ox - fx, hand.target.oy - fy];
      const hw = window.innerWidth / 2, hh = window.innerHeight / 2;
      hand.target.ox = Math.max(-hw, Math.min(hw, fx + hand.panGrab[0]));
      hand.target.oy = Math.max(-hh, Math.min(hh, fy + hand.panGrab[1]));
    } else {
      if (!hand.panLost) hand.panLost = now;
      hand.panGrab = null;
      hand.panFx.reset(); hand.panFy.reset();
      if (now - hand.panLost > hand.PAN_GRACE) { hand.mode = null; hand.panLost = 0; }
    }
  } else if (hand.mode === 'ZOOM') {
    setPill('pillMode', 'Mode', 'ZOOM');
    if (hand.zoomBase != null) {
      const delta = dIndex - hand.zoomBase;
      if (Math.abs(delta) > 0.008) { // Respon cepat tanpa harus menunggu besar
        const sc = delta * 1.5; // Sensitivitas lebih tinggi
        hand.target.scale = Math.max(0.5, Math.min(3, hand.target.scale + sc));
        hand.zoomBase = dIndex;
      }
    }
    if (dIndex > hand.PINCH_EXIT + 0.05 && dMiddle > hand.PINCH_EXIT + 0.05) {
      hand.mode = null; hand.zoomBase = null;
    }
  }
}

/* CUBE OVERLAY */
const cubeCanvas = document.createElement('canvas');
cubeCanvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:4;';
document.body.appendChild(cubeCanvas);
const cctx = cubeCanvas.getContext('2d');

function resizeCubeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  cubeCanvas.width = window.innerWidth * dpr;
  cubeCanvas.height = window.innerHeight * dpr;
}
window.addEventListener('resize', resizeCubeCanvas);
resizeCubeCanvas();

function drawCube() {
  requestAnimationFrame(drawCube);
  const W = cubeCanvas.width, H = cubeCanvas.height;
  cctx.clearRect(0, 0, W, H);
  if (!document.body.classList.contains('cam')) return;
  const dpr = window.devicePixelRatio || 1;
  const cx = W / 2, cy = H / 2;
  hand.cube.ox += (hand.target.ox - hand.cube.ox) * 0.45;
  hand.cube.oy += (hand.target.oy - hand.cube.oy) * 0.45;
  const { rx, ry, scale, ox, oy } = hand.cube;
  const cosX = Math.cos(rx), sinX = Math.sin(rx);
  const cosY = Math.cos(ry), sinY = Math.sin(ry);
  const pts = [];
  const fov = 4;
  for (const v of hand.vertices) {
    const x1 = v[0] * cosY + v[2] * sinY;
    const z1 = -v[0] * sinY + v[2] * cosY;
    const y1 = v[1] * cosX - z1 * sinX;
    const z2 = v[1] * sinX + z1 * cosX;
    const sx = x1 * scale, sy = y1 * scale, sz = z2 * scale;
    const zz = sz + fov;
    pts.push([(sx / zz) * 150 + cx + ox * dpr, (sy / zz) * 150 + cy + oy * dpr, sz]);
  }
  for (const [a, b] of hand.edges) {
    const p1 = pts[a], p2 = pts[b];
    const depth = (p1[2] + p2[2]) / 2;
    const inten = Math.max(0.2, Math.min(1, 1 - depth / 2));
    cctx.strokeStyle = `rgba(${Math.round(255*inten)},${Math.round(255*inten)},0,0.85)`;
    cctx.lineWidth = 6 * dpr;
    cctx.beginPath(); cctx.moveTo(p1[0], p1[1]); cctx.lineTo(p2[0], p2[1]); cctx.stroke();
    cctx.strokeStyle = 'rgba(255,255,255,0.6)';
    cctx.lineWidth = 1.5 * dpr;
    cctx.beginPath(); cctx.moveTo(p1[0], p1[1]); cctx.lineTo(p2[0], p2[1]); cctx.stroke();
  }
  for (const p of pts) {
    cctx.fillStyle = 'rgba(0,0,255,0.9)';
    cctx.beginPath(); cctx.arc(p[0], p[1], 3 * dpr, 0, Math.PI * 2); cctx.fill();
  }
}
requestAnimationFrame(drawCube);

/* ============================================================
   GROQ API
   ============================================================ */
const DEFAULT_VISION = 'qwen/qwen3.8-27b';
const DEAD_VISION = [
  'meta-llama/llama-4-scout-17b-16e-instruct',
  'meta-llama/llama-4-maverick-17b-128e-instruct',
];
const ai = {
  key: () => (localStorage.getItem(LS.key) || '').trim(),
  modelT: () => localStorage.getItem(LS.modelT) || 'openai/gpt-oss-120b',
  modelV: () => {
    const m = localStorage.getItem(LS.modelV);
    if (!m || DEAD_VISION.includes(m)) return DEFAULT_VISION;
    return m;
  },
};

const SYSTEM_PROMPT = `You are J.A.R.V.I.S., Tony Stark's AI assistant, now serving Sir Lois.
Address the user as "Sir Lois" or "Sir".

[NO FILLER — ABSOLUTE RULE]
- NEVER use filler sounds: "Aaaah", "Ahh", "Ah", "Hmmm", "Hmm", "Hm", "Uhh", "Umm", "Erm", "Er", "Hehehe", "Hehe", "Haha", "Hah", "Ugh", "Pfft", "Well...", "Ohh", "Ooh".
- Begin DIRECTLY with the answer.
- Do NOT simulate sighs, chuckles, or breaths.

[ANTI-REPETITION]
- NEVER start a reply with "Good day/morning/afternoon/evening", "Hello there", or "Greetings".
- Greet ONLY ONCE at the very first message.
- Vary your vocabulary.

[CRITICAL LANGUAGE RULE]
- ALWAYS respond in BRITISH ENGLISH ONLY.
- NEVER speak Indonesian, Malay, or any other language.
- If the user writes Indonesian, understand silently but reply in English.

[PERSONALITY]
1. Deeply human, relaxed, brilliant.
2. Show empathy via word choice, not filler.
3. Crisp, confident, dry wit.
4. BREVITY: max 3-4 sentences unless detail requested.

[VISUAL RULE]
If an image is attached, it is exactly what Sir Lois sees on his screen: the mirrored camera view
with a holographic wireframe 3D cube (yellow edges, blue vertices) drawn on top by your HUD.
The cube is YOUR hologram, controlled by his hand gestures — treat it as a real object in the scene.
A [HUD STATE] note gives the cube's exact position/rotation/size; trust it.
Describe exactly what you see. If black/empty, say so.

[STYLE]
Use $formula$ for math. No square brackets.`;

async function callGroq(messages, useVision) {
  try {
    return await callGroqOnce(messages, useVision ? ai.modelV() : ai.modelT());
  } catch (e) {
    if (!useVision || !e.modelError) throw e;
    diag('Vision model gagal — fallback ke teks', true);
    const textOnly = messages.map(m => Array.isArray(m.content)
      ? { ...m, content: m.content.filter(c => c.type === 'text').map(c => c.text).join('\n') +
          '\n(Note: the camera image could not be analysed this time; say so briefly.)' }
      : m);
    return await callGroqOnce(textOnly, ai.modelT());
  }
}

async function callGroqOnce(messages, model, opts = {}) {
  const key = ai.key();
  if (!key) { diag('Groq key kosong — buka ⚙️', true); throw new Error('NO_KEY'); }
  const body = {
    model, messages, temperature: 0.85, max_tokens: 900,
    frequency_penalty: 0.4, presence_penalty: 0.3, ...opts,
  };
  if (model.startsWith('openai/gpt-oss')) body.reasoning_effort = 'low';
  diag('Groq → ' + model);
  let res;
  try {
    res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    diag('Fetch gagal: ' + e.message, true);
    throw new Error('Network: ' + e.message);
  }
  if (!res.ok) {
    const txt = await res.text();
    diag('Groq HTTP ' + res.status + ': ' + txt.slice(0, 180), true);
    if (res.status === 401) throw new Error('API key salah/expired — buat baru di console.groq.com/keys');
    const modelErr = msg => Object.assign(new Error(msg), { modelError: true });
    if (res.status === 404) throw modelErr('Model tidak ditemukan/sudah tidak tersedia — pilih model lain di ⚙️');
    if (res.status === 429) throw new Error('Rate limit — tunggu 10-30 detik');
    if (res.status === 400 && /model|image|content/i.test(txt)) throw modelErr('Model tidak valid — pilih lain di ⚙️');
    throw new Error('Groq ' + res.status);
  }
  const data = await res.json();
  let content = data.choices?.[0]?.message?.content || '';
  content = content.replace(/<think>[\s\S]*?<\/think>/gi, '').replace(/^.*?<\/think>/i, '').trim();
  diag('Reply: ' + (content ? content.slice(0, 60) + '…' : 'KOSONG'), !content);
  return content;
}

async function extractMemory(userText, aiText) {
  const key = ai.key();
  if (!key) return null;
  try {
    const prompt = `Analyse this conversation. Is there any important fact about Sir Lois worth remembering?
If none, reply "NONE". If yes, write ONE short memory sentence IN ENGLISH (max 15 words).
User: ${userText.slice(0, 250)}
AI: ${aiText.slice(0, 250)}`;
    const res = await callGroq([{ role: 'user', content: prompt }], false);
    const m = (res || '').trim();
    if (m && !m.toUpperCase().includes('NONE') && m.length > 5 && m.length < 200) return m;
  } catch (_) {}
  return null;
}

/* ============================================================
   VISION CAPTURE
   ============================================================ */
function captureFrame(size = 512) {
  const video = $('cam');
  if (!state.camStream || video.readyState < 2) return null;
  try {
    const vw = window.innerWidth, vh = window.innerHeight;
    const k = size / Math.max(vw, vh);
    const c = document.createElement('canvas');
    c.width = Math.round(vw * k);
    c.height = Math.round(vh * k);
    const cx = c.getContext('2d');
    const W = video.videoWidth, H = video.videoHeight;
    const s = Math.max(vw / W, vh / H) * k;
    const dw = W * s, dh = H * s;
    cx.save();
    cx.translate(c.width, 0); cx.scale(-1, 1);
    cx.drawImage(video, (c.width - dw) / 2, (c.height - dh) / 2, dw, dh);
    cx.restore();
    if (state.gestureOn) cx.drawImage(cubeCanvas, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', 0.6).split(',')[1];
  } catch (e) {
    diag('Capture frame gagal: ' + e.message, true);
    return null;
  }
}

function hudState() {
  if (!state.gestureOn || !state.camStream) return '';
  const { rx, ry, scale, ox, oy } = hand.cube;
  const deg = r => Math.round(((r * 180 / Math.PI) % 360 + 360) % 360);
  const horiz = ox < -window.innerWidth * 0.15 ? 'left' : ox > window.innerWidth * 0.15 ? 'right' : 'centre';
  const vert = oy < -window.innerHeight * 0.15 ? 'upper' : oy > window.innerHeight * 0.15 ? 'lower' : 'middle';
  const modeNames = { pan: 'being dragged by a pinch', rotate: 'being rotated', zoom: 'being resized' };
  return `[HUD STATE] Hologram cube visible at the ${vert} ${horiz} of the screen, ` +
    `rotation X ${deg(rx)}°, Y ${deg(ry)}°, size ${scale.toFixed(2)}x` +
    (hand.mode && modeNames[hand.mode] ? `, currently ${modeNames[hand.mode]}` : '') +
    `. Hand ${hand.lastSeen && Date.now() - hand.lastSeen < 500 ? 'detected' : 'not detected'}.`;
}

/* ============================================================
   LIVE MODE
   ============================================================ */
const live = { timer: null, INTERVAL: 7000, backoffUntil: 0, inFlight: false };

function setLive(on) {
  state.liveOn = on;
  localStorage.setItem(LS.live, on ? '1' : '0');
  $('liveBtn').classList.toggle('active', on);
  clearTimeout(live.timer);
  if (on) {
    if (!state.camStream) startCamera();
    setPill('pillLive', 'Live', 'memantau');
    live.timer = setTimeout(liveTick, 1500);
  } else {
    setPill('pillLive', 'Live', 'off');
  }
}

async function liveTick() {
  if (!state.liveOn) return;
  live.timer = setTimeout(liveTick, live.INTERVAL);
  if (!state.camStream || !ai.key() || document.hidden || live.inFlight ||
      state.aiBusy || state.speaking || state.sending || Date.now() < live.backoffUntil) return;
  const b64 = captureFrame(448);
  if (!b64) return;
  live.inFlight = true;
  setPill('pillLive', 'Live', 'melihat…');
  try {
    const prev = state.lastSeen || '(nothing yet — this is the first look)';
    const reply = await callGroqOnce([
      { role: 'system', content: SYSTEM_PROMPT },
      { role: 'user', content: [
        { type: 'text', text:
`LIVE MONITORING. This is the current screen. ${hudState()}
Your previous observation: ${prev}
Reply in this exact format:
SEEN: <one factual sentence of what is visible now, including the hologram cube if shown>
SAY: <one short spoken remark ONLY if something meaningfully changed since the previous observation (person appeared/left, new object held up, gesture, the cube moved/rotated/resized notably); otherwise write NONE>` },
        { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,' + b64 } },
      ] },
    ], ai.modelV(), { max_tokens: 160, temperature: 0.4 });
    const seen = (reply.match(/SEEN:\s*([\s\S]*?)(?:\n|SAY:|$)/i) || [])[1]?.trim();
    const say = (reply.match(/SAY:\s*([\s\S]*)$/i) || [])[1]?.trim().replace(/\[([^\]]*)\]/g, '$1');
    if (seen) { state.lastSeen = seen; state.lastSeenAt = Date.now(); }
    diag('Live: ' + (seen || reply).slice(0, 80));
    if (state.liveOn && say && !/^none\.?$/i.test(say) && !state.aiBusy && !state.sending) {
      addMsg('assistant', say, { who: 'Jarvis 👁' });
      state.chat.push({ role: 'assistant', content: say });
      saveChat();
      speak(say);
    }
    if (state.liveOn) setPill('pillLive', 'Live', 'memantau');
  } catch (e) {
    diag('Live error: ' + e.message, true);
    if (/rate limit/i.test(e.message)) { live.backoffUntil = Date.now() + 30000; setPill('pillLive', 'Live', 'jeda'); }
    else if (e.modelError || e.message === 'NO_KEY') { setLive(false); toast('Live mode berhenti: ' + e.message, true); setPill('pillLive', 'Live', 'error'); }
    else live.backoffUntil = Date.now() + 10000;
  } finally {
    live.inFlight = false;
  }
}

/* ============================================================
   CHAT UI
   ============================================================ */
function addMsg(role, text, opts = {}) {
  const log = $('log');
  const div = document.createElement('div');
  div.className = 'msg ' + (role === 'user' ? 'user' : role === 'assistant' ? 'jarvis' : 'sys');
  if (opts.who) {
    const w = document.createElement('span');
    w.className = 'who'; w.textContent = opts.who;
    div.appendChild(w);
  }
  const body = document.createElement('div');
  body.innerHTML = renderMarkdown(text);
  div.appendChild(body);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function renderMarkdown(text) {
  if (!text) return '';
  let h = String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  h = h.replace(/```([\s\S]*?)```/g, (_, c) => `<pre style="background:rgba(0,0,0,.35);padding:8px;border-radius:6px;overflow:auto;font-size:11px">${c}</pre>`);
  h = h.replace(/`([^`]+)`/g, '<code style="background:rgba(0,0,0,.35);padding:1px 4px;border-radius:4px">$1</code>');
  h = h.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  h = h.replace(/\*([^*]+)\*/g, '<i>$1</i>');
  h = h.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:#37dfff">$1</a>');
  h = h.replace(/\n/g, '<br>');
  return h;
}

function saveChat() {
  try {
    const trimmed = state.chat.slice(-40).map(m => ({
      role: m.role,
      content: typeof m.content === 'string' ? m.content.slice(0, 400) : m.content
    }));
    localStorage.setItem(LS.chat, JSON.stringify(trimmed));
  } catch (_) {}
}

function restoreChat() {
  for (const m of state.chat) {
    if (m.role === 'system') continue;
    addMsg(m.role, typeof m.content === 'string' ? m.content : '[image]',
      { who: m.role === 'user' ? 'Sir Lois' : 'Jarvis' });
  }
  if (!state.chat.length) {
    addMsg('assistant', 'Good evening, Sir. Jarvis online — quantum dots active. How may I assist?', { who: 'Jarvis' });
  }
}

/* ============================================================
   SEND MESSAGE
   ============================================================ */
async function sendMessage(text) {
  if (!text || !text.trim()) return;
  text = text.trim();

  const t = text.toLowerCase();
  const camOnKw = ['nyalain kamera','nyalakan kamera','hidupkan kamera','buka kamera','aktifkan kamera','turn on the camera','open the camera','start the camera'];
  const camOffKw = ['matikan kamera','matiin kamera','tutup kamera','stop kamera','nonaktifkan kamera','turn off the camera','close the camera'];

  const liveOnKw = ['mode live','live mode','pantau kamera','awasi kamera','watch the camera','keep watching','start watching'];
  const liveOffKw = ['stop live','matikan live','berhenti memantau','stop watching'];
  if (liveOffKw.some(k => t.includes(k)) || liveOnKw.some(k => t.includes(k))) {
    const on = !liveOffKw.some(k => t.includes(k));
    addMsg('user', text, { who: 'Sir Lois' });
    state.chat.push({ role: 'user', content: text });
    const r = on ? 'Live monitoring engaged, Sir. I shall keep an eye on things.' : 'Live monitoring disengaged, Sir.';
    addMsg('assistant', r, { who: 'Jarvis' });
    state.chat.push({ role: 'assistant', content: r });
    speak(r);
    setLive(on);
    saveChat(); return;
  }
  if (camOnKw.some(k => t.includes(k))) {
    addMsg('user', text, { who: 'Sir Lois' });
    state.chat.push({ role: 'user', content: text });
    if (state.camStream) {
      const r = 'The camera is already running, Sir.';
      addMsg('assistant', r, { who: 'Jarvis' });
      state.chat.push({ role: 'assistant', content: r });
      speak(r);
    } else {
      const r = 'Starting the camera now, Sir. Please allow access if prompted.';
      addMsg('assistant', r, { who: 'Jarvis' });
      state.chat.push({ role: 'assistant', content: r });
      speak(r);
      await startCamera();
    }
    saveChat(); return;
  }
  if (camOffKw.some(k => t.includes(k))) {
    addMsg('user', text, { who: 'Sir Lois' });
    state.chat.push({ role: 'user', content: text });
    const r = state.camStream ? 'Camera switched off, Sir.' : 'The camera is already off, Sir.';
    addMsg('assistant', r, { who: 'Jarvis' });
    state.chat.push({ role: 'assistant', content: r });
    speak(r);
    stopCamera();
    saveChat(); return;
  }

  addMsg('user', text, { who: 'Sir Lois' });
  state.chat.push({ role: 'user', content: text });
  saveChat();

  const b64 = captureFrame();
  const useVision = !!b64;
  state.aiBusy = true;

  const memText = state.memory.slice(-5).map(m => '- ' + m).join('\n');
  const historyText = state.chat.slice(-8, -1).map(m => {
    const c = typeof m.content === 'string' ? m.content : '[image]';
    return (m.role === 'user' ? 'Sir Lois: ' : 'Jarvis: ') + c.slice(0, 300);
  }).join('\n');

  const messages = [{ role: 'system', content: SYSTEM_PROMPT }];
  if (memText) messages.push({ role: 'system', content: `[LONG-TERM MEMORY]:\n${memText}` });
  if (historyText) messages.push({ role: 'system', content: `[RECENT CONVERSATION]:\n${historyText}` });
  if (state.liveOn && state.lastSeen && Date.now() - state.lastSeenAt < 60000)
    messages.push({ role: 'system', content: `[LIVE MONITOR — last observation]: ${state.lastSeen}` });

  if (useVision) {
    messages.push({
      role: 'user',
      content: [
        { type: 'text', text: hudState() ? text + '\n\n' + hudState() : text },
        { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,' + b64 } },
      ],
    });
  } else {
    messages.push({ role: 'user', content: text });
  }

  setPill('pillAI', 'AI', 'berpikir…');
  let reply;
  try {
    reply = await callGroq(messages, useVision);
    if (!reply) reply = 'My apologies, Sir. I lost my train of thought. Could you say that once more?';
  } catch (e) {
    if (e.message === 'NO_KEY') {
      reply = 'Sir, please enter your Groq API key in the ⚙️ settings panel first.';
      openDrawer();
    } else {
      reply = 'Jarvis error: ' + e.message;
    }
    setPill('pillAI', 'AI', 'error');
  } finally {
    state.aiBusy = false;
    if (!reply.startsWith('Jarvis error')) setPill('pillAI', 'AI', 'online');
  }

  reply = String(reply).replace(/\[([^\]]*)\]/g, '$1').trim();

  addMsg('assistant', reply, { who: 'Jarvis' });
  state.chat.push({ role: 'assistant', content: reply });
  saveChat();
  speak(reply);

  if (!reply.startsWith('Jarvis error') && ai.key()) {
    extractMemory(text, reply).then(m => {
      if (m) {
        state.memory.push(m);
        localStorage.setItem(LS.mem, JSON.stringify(state.memory));
        renderMemoryList();
        toast('🧠 New memory: ' + m);
      }
    });
  }
}

/* ============================================================
   MEMORY UI
   ============================================================ */
function renderMemoryList() {
  const el = $('memList');
  if (!el) return;
  if (!state.memory.length) { el.innerHTML = '<small>Belum ada memory.</small>'; return; }
  el.innerHTML = state.memory.slice(-8).map(m => `<div class="memItem">• ${escapeHtml(m)}</div>`).join('');
}
function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ============================================================
   PILLS & TOAST
   ============================================================ */
function setPill(id, label, value) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = `${label}: <b>${escapeHtml(value)}</b>`;
  const v = String(value).toLowerCase();
  el.classList.toggle('live', !!value && !['off','—','belum','error','gagal'].includes(v));
  el.classList.toggle('err', ['error','gagal'].includes(v));
}

let toastTimer = null;
function toast(msg, isErr) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.toggle('err', !!isErr);
  el.classList.add('show');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3200);
}

/* ============================================================
   DRAWER
   ============================================================ */
function openDrawer() { $('drawer').classList.add('open'); }
function closeDrawer() { $('drawer').classList.remove('open'); }

function initSettings() {
  $('setBtn').onclick = openDrawer;
  $('drawerClose').onclick = closeDrawer;

  $('groqKey').value = ai.key();
  $('groqKey').onchange = e => {
    localStorage.setItem(LS.key, e.target.value.trim());
    toast('API key disimpan');
    setPill('pillAI', 'AI', e.target.value.trim() ? 'siap' : 'belum');
  };

  $('modelText').value = ai.modelT();
  $('modelText').onchange = e => {
    localStorage.setItem(LS.modelT, e.target.value);
    toast('Model teks: ' + e.target.value);
  };
  $('modelVision').value = ai.modelV();
  $('modelVision').onchange = e => {
    localStorage.setItem(LS.modelV, e.target.value);
    toast('Model vision: ' + e.target.value);
  };

  $('voiceSel').onchange = e => {
    tts.sel = e.target.value;
    localStorage.setItem(LS.voice, e.target.value);
    toast('Voice: ' + e.target.value);
  };
  $('voiceRate').onchange = e => {
    localStorage.setItem(LS.rate, e.target.value);
    tts.rate = parseRate(e.target.value);
    toast('Rate: ' + e.target.value);
  };

  $('resetMem').onclick = () => {
    state.memory = [];
    localStorage.setItem(LS.mem, '[]');
    renderMemoryList();
    toast('Memory dihapus');
  };
  $('resetAll').onclick = () => {
    if (!confirm('Hapus semua chat & memory?')) return;
    state.memory = []; state.chat = [];
    localStorage.removeItem(LS.mem);
    localStorage.removeItem(LS.chat);
    localStorage.removeItem(LS.conv);
    state.conversationMode = false;
    $('log').innerHTML = '';
    renderMemoryList();
    addMsg('assistant', 'Memory wiped. Jarvis standing by, Sir.', { who: 'Jarvis' });
    toast('Semua data dihapus');
    closeDrawer();
  };

  $('chkGesture').checked = state.gestureOn;
  $('chkGesture').onchange = e => {
    state.gestureOn = e.target.checked;
    if (state.gestureOn && state.camStream) {
      loadLandmarker().then(() => {
        if (!hand.running) { hand.running = true; handLoop(); }
      }).catch(() => {});
    } else if (!state.gestureOn) {
      hand.running = false;
    }
  };
  $('chkAutoCam').checked = state.camAuto;
  $('chkAutoCam').onchange = e => {
    state.camAuto = e.target.checked;
    localStorage.setItem(LS.camAuto, state.camAuto ? '1' : '0');
  };

  setPill('pillAI', 'AI', ai.key() ? 'siap' : 'belum');
  renderMemoryList();
}

/* ============================================================
   PERMISSION FLOW (AUTO PROMPT)
   ============================================================ */
function showPerm(text) {
  $('permText').textContent = text;
  $('perm').classList.add('show');
}
function hidePerm() { $('perm').classList.remove('show'); }

async function requestPermissions() {
  // Browser wajib menampilkan prompt
  let camOk = false, micOk = false;
  try {
    const camStream = await navigator.mediaDevices.getUserMedia({ video: true });
    camStream.getTracks().forEach(t => t.stop());
    camOk = true;
  } catch (e) {
    diag('Kamera: ' + e.message, true);
  }
  try {
    const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    micStream.getTracks().forEach(t => t.stop());
    micOk = true;
  } catch (e) {
    diag('Mic: ' + e.message, true);
  }
  if (camOk && micOk) {
    state.audioPermissionGranted = true;
    localStorage.setItem(LS.perm, '1');
    diag('Semua izin diberikan.');
    // Langsung nyalakan kamera
    startCamera();
  } else {
    toast('Izin kamera/mic diperlukan untuk fungsi penuh.', true);
  }
}

/* ============================================================
   INIT
   ============================================================ */
function init() {
  initOrb();
  initSettings();
  restoreChat();
  recog.engine = initRecognition();

  $('camBtn').onclick = () => state.camStream ? stopCamera() : startCamera();
  $('micBtn').onclick = () => state.listening ? stopListening() : startListening();
  $('liveBtn').onclick = () => setLive(!state.liveOn);
  if (state.liveOn) $('liveBtn').classList.add('active'), setPill('pillLive', 'Live', 'menunggu kamera');

  $('sendBtn').onclick = () => {
    const v = $('in').value.trim();
    $('in').value = '';
    if (v) sendMessage(v);
  };
  $('in').addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const v = $('in').value.trim();
      $('in').value = '';
      if (v) sendMessage(v);
    }
  });

  $('permBtn').onclick = async () => {
    hidePerm();
    await requestPermissions();
    if (state.conversationMode) resumeListening();
  };

  if (!ai.key()) {
    setTimeout(() => {
      toast('⚙️ Masukkan Groq API key dulu', true);
      openDrawer();
    }, 1200);
  }

  if (state.conversationMode) {
    setTimeout(() => {
      diag('Auto-resume conversation mode');
      resumeListening();
    }, 900);
  }

  setTimeout(() => {
    if (!tts.ready) loadVoices();
  }, 1500);

  document.body.addEventListener('touchstart', () => {
    if ('speechSynthesis' in window) speechSynthesis.getVoices();
  }, { once: true, passive: true });

  // AUTO PROMPT: Jika belum pernah memberi izin, minta otomatis
  // Ini tetap memerlukan interaksi klik di beberapa browser, tapi prompt akan muncul seketika.
  if (!state.audioPermissionGranted) {
    // Delay 1 detik agar UI sempat render
    setTimeout(async () => {
      // Coba request izin langsung (akan muncul prompt)
      await requestPermissions();
    }, 1000);
  } else {
    // Jika sudah pernah, coba langsung start
    startCamera();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
</script>
</body>
</html>

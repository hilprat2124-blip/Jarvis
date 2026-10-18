import cv2
import numpy as np
import streamlit as st
import base64
import asyncio
import re
import json
import pathlib
import io
import time
from PIL import Image

# ============ AI: Groq (Cloud) ============
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# ============ AI: Edge-TTS ============
try:
    import edge_tts
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

# ============ KONFIGURASI GROQ API ============
GROQ_API_KEY = "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"
JARVIS_VISION_MODEL = "qwen/qwen3.8-27b"
JARVIS_TEXT_MODEL = "openai/gpt-oss-120b"
JARVIS_MEMORY_MODEL = "openai/gpt-oss-20b"

MAX_OUTPUT_TOKENS = 300
MAX_CONTEXT_TURNS = 6
MAX_MSG_CHARS = 400
IMAGE_MAX_SIZE = 384
IMAGE_QUALITY = 45

VOICE_EN = "en-GB-RyanNeural"
VOICE_RATE = "-5%"
VOICE_PITCH = "-3Hz"

# ============ Konfigurasi Halaman ============
st.set_page_config(page_title="J.A.R.V.I.S - Quantum Dots", page_icon="🔵", layout="wide")
st.title("🔵 J.A.R.V.I.S — Quantum Dots")
st.markdown("Kamera merekam **setiap 0.2 detik**. Klik **'Mulai Dengar'** sekali, mode obrolan suara akan **aktif terus** sampai Anda klik **'Stop Dengar'**.")

# ============================================================
# PERSISTENCE & HELPER
# ============================================================
SCRIPT_DIR = pathlib.Path(__file__).parent.absolute()
MEMORY_FILE = str(SCRIPT_DIR / "jarvis_persistent_memory.json")
CHAT_FILE = str(SCRIPT_DIR / "jarvis_chat_history.json")

def _log(msg: str): print(f"[JARVIS-PERSIST] {msg}", flush=True)

def load_memory() -> list:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

def save_memory(memory_list: list):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f: json.dump(memory_list, f, ensure_ascii=False, indent=2)
    except: pass

def load_chat_history() -> list:
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

def save_chat_history(messages: list):
    try:
        clean_msgs = []
        for m in messages:
            if m["role"] == "system": continue
            content = m["content"]
            if isinstance(content, list):
                texts = [c["text"] for c in content if c.get("type") == "text"]
                content = " ".join(texts) if texts else "[image]"
            if isinstance(content, str) and len(content) > MAX_MSG_CHARS: content = content[:MAX_MSG_CHARS] + "..."
            clean_msgs.append({"role": m["role"], "content": content})
        with open(CHAT_FILE, "w", encoding="utf-8") as f: json.dump(clean_msgs, f, ensure_ascii=False, indent=2)
    except: pass

def get_recent_context_summary(max_turns: int = MAX_CONTEXT_TURNS) -> str:
    history = load_chat_history()
    if not history: return ""
    recent = history[-max_turns * 2:]
    lines = []
    for m in recent:
        role = "Sir Lois" if m["role"] == "user" else "Jarvis"
        content = m["content"]
        if isinstance(content, list): content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if isinstance(content, str) and len(content) > MAX_MSG_CHARS: content = content[:MAX_MSG_CHARS] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

# ============================================================
# DETEKSI INTENT KAMERA
# ============================================================
CAM_ON_PATTERNS = [
    r"\b(on|turn\s+on|open|activate|enable|start|nyalakan|buka|aktifkan|hidupkan|nyala)\s+(the\s+|ur\s+|your\s+|my\s+)?(cam|camera|kamera|webcam|video)\b",
    r"\b(cam|camera|kamera)\s+(on|nyala|aktif|hidup)\b",
    r"\b(on\s*cam|turn\s+on\s+cam|buka\s*kamera|nyalakan\s*kamera|aktifkan\s*kamera|hidupkan\s*kamera)\b",
    r"\bcan\s+you\s+(turn\s+on|open|activate|start)\s+(the\s+|your\s+)?(cam|camera|webcam)\b",
]

def strip_filler_words(text: str) -> str:
    if not text: return text
    filler_patterns = [r'^\s*(Aaa+h+|Ahh+|Ah+|Hmm+m*|Hm+|Uhh+|Umm+|Erm+|Er+|Hehehe+|Hehe+|Haha+|Hah+|Ugh+|Pfft+|Ohh+|Ooh+)[\s,\.\!\?…—\-]*']
    for _ in range(3):
        old = text
        for pattern in filler_patterns: text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
        if text == old: break
    text = re.sub(r'[\s,]+(Aaa+h+|Ahh+|Hmm+m*|Uhh+|Umm+|Erm+|Hehehe+|Hehe+|Haha+|Ugh+)[\s,\.\!\?…]*', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'^\s*Well\s*[\.,…—\-]+\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    if text and text[0].islower(): text = text[0].upper() + text[1:]
    return text

def is_camera_on_command(text: str) -> bool:
    if not text: return False
    t = strip_filler_words(text.lower().strip())
    for pat in CAM_ON_PATTERNS:
        if re.search(pat, t, flags=re.IGNORECASE): return True
    return False

# ============================================================
# HELPER JARVIS
# ============================================================
def image_to_base64(pil_img: Image.Image, max_size=IMAGE_MAX_SIZE, quality=IMAGE_QUALITY) -> str:
    img = pil_img.copy()
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def _is_rate_limit_error(err_str: str) -> bool:
    err = err_str.lower()
    return "413" in err or "rate_limit" in err or "request too large" in err or "tokens per minute" in err or "itpm" in err

def ask_jarvis(api_messages: list, use_vision: bool) -> str:
    if not GROQ_AVAILABLE: return "❌ `groq` belum terinstall."
    client = Groq(api_key=GROQ_API_KEY)
    model = JARVIS_VISION_MODEL if use_vision else JARVIS_TEXT_MODEL
    try:
        resp = client.chat.completions.create(
            model=model, messages=api_messages, temperature=0.85, max_tokens=MAX_OUTPUT_TOKENS,
            frequency_penalty=0.6, presence_penalty=0.4,
        )
        return resp.choices[0].message.content
    except Exception as e:
        err_str = str(e)
        if _is_rate_limit_error(err_str):
            try:
                fallback_msgs = [api_messages[0]]
                text_msgs = []
                for m in api_messages:
                    if m["role"] in ("user", "assistant"):
                        if isinstance(m["content"], str): text_msgs.append({"role": m["role"], "content": m["content"][:300]})
                        elif isinstance(m["content"], list):
                            texts = [c.get("text", "") for c in m["content"] if c.get("type") == "text"]
                            if texts: text_msgs.append({"role": m["role"], "content": " ".join(texts)[:300]})
                fallback_msgs.extend(text_msgs[-4:])
                resp = client.chat.completions.create(model=JARVIS_TEXT_MODEL, messages=fallback_msgs, temperature=0.7, max_tokens=200)
                return f"{resp.choices[0].message.content}\n\n*(Sir, I had to switch to text-only mode due to token limits.)*"
            except: return "Sir, my cognitive buffer is momentarily saturated."
        return f"❌ Error Jarvis (Groq): {err_str[:300]}"

def sanitize_latex(text: str) -> str:
    if not text: return text
    text = re.sub(r'\[\s*(.*?)\s*\]', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\$)\b([a-zA-Z]\s*=\s*[0-9\.]+\s*(?:[a-zA-Z/]+)?)\b(?!\$)', r' $ \1 $ ', text)
    text = re.sub(r'([a-zA-Z0-9])\$', r'\1 $', text)
    text = re.sub(r'\$([a-zA-Z0-9])', r'$ \1', text)
    return text.strip()

def strip_repetitive_greeting(text: str, history: list) -> str:
    if not text: return text
    past_greetings = 0
    for m in history:
        if m["role"] == "assistant":
            content = m["content"]
            if isinstance(content, list): content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            if re.search(r'\b(good day|good morning|good afternoon|good evening|hello there|greetings)\b', str(content), re.IGNORECASE): past_greetings += 1
    if past_greetings >= 1:
        text = re.sub(r'^\s*(good day|good morning|good afternoon|good evening|hello there|greetings)[\s,\.!]*', '', text, flags=re.IGNORECASE)
        if text and text[0].islower(): text = text[0].upper() + text[1:]
    return text

def extract_memory(user_text: str, ai_text: str) -> str | None:
    if not GROQ_AVAILABLE: return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = f"Analyse this conversation. Is there any important fact about Sir Lois worth remembering? If none, reply 'NONE'. If yes, write ONE short memory sentence IN ENGLISH (max 15 words).\nUser: {user_text[:300]}\nAI: {ai_text[:300]}"
        resp = client.chat.completions.create(model=JARVIS_MEMORY_MODEL, messages=[{"role": "user", "content": prompt}], max_tokens=40, temperature=0.1)
        memory = resp.choices[0].message.content.strip()
        if "NONE" not in memory.upper() and len(memory) > 5: return memory
        return None
    except: return None

def _normalize_for_tts(text: str) -> str:
    text = re.sub(r'\$\$.*?\$\$', ' formula ', text, flags=re.DOTALL)
    text = re.sub(r'\$.*?\$', ' formula ', text)
    text = text.replace('\\', '').replace('{', '').replace('}', '')
    text = strip_filler_words(text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'[*#_`>]', '', text)
    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    text = text.replace("...", ", ")
    replacements = {"&": " and ", "%": " percent ", "@": " at ", "#": " number ", "+": " plus ", "=": " equals ", "→": " to ", "↔": " to ", "·": " ", "•": " ", "—": ", ", "–": ", "}
    for k, v in replacements.items(): text = text.replace(k, v)
    return re.sub(r'\s+', ' ', text).strip()

def generate_tts_edge(text: str) -> bytes | None:
    if not TTS_AVAILABLE: return None
    clean_text = _normalize_for_tts(text)
    if not clean_text: return None
    async def _generate():
        communicate = edge_tts.Communicate(clean_text, VOICE_EN, rate=VOICE_RATE, pitch=VOICE_PITCH)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": audio_data += chunk["data"]
        return audio_data
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio = loop.run_until_complete(_generate())
        loop.close()
        return audio
    except: return None

# ============================================================
# JARVIS ORB (SUARA & ANIMASI)
# ============================================================
import streamlit.components.v1 as components

def render_jarvis_orb(audio_bytes: bytes = None, state: str = "idle", conversation_mode: bool = False):
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else ""
    has_audio = "true" if audio_bytes else "false"
    conv_mode_js = "true" if conversation_mode else "false"
    est_duration_ms = max(3000, int(len(audio_bytes) / 16)) if audio_bytes else 0
    
    html_template = r"""
    <!DOCTYPE html><html><head><style>
    *{box-sizing:border-box;margin:0;padding:0} body{background:transparent;overflow:hidden;font-family:'Courier New',monospace;display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh}
    .orb-container{position:relative;width:100%;height:320px;display:flex;align-items:center;justify-content:center} canvas{position:absolute;top:0;left:0;width:100%;height:100%}
    .controls-row{position:absolute;bottom:10px;z-index:30;display:flex;gap:12px;align-items:center}
    .mic-btn,.play-btn{padding:10px 20px;border:1px solid #37dfff;border-radius:20px;background:rgba(6,20,33,0.9);color:#8defff;cursor:pointer;font-family:'Courier New',monospace;font-size:11px;letter-spacing:1px;text-transform:uppercase;box-shadow:0 0 15px rgba(0,200,255,0.4);transition:all 0.3s}
    .mic-btn:hover,.play-btn:hover{background:rgba(0,100,150,0.9);box-shadow:0 0 30px rgba(0,220,255,0.8)}
    .mic-btn.listening{background:rgba(0,255,200,0.9);border-color:#00ffc8;color:#000;box-shadow:0 0 25px rgba(0,255,200,0.8);animation:pulse 1.2s infinite}
    @keyframes pulse{0%{transform:scale(1)}50%{transform:scale(1.06)}100%{transform:scale(1)}}
    .transcript-hint{position:absolute;top:5px;color:#7cfc00;font-size:11px;text-align:center;width:100%;z-index:25;text-shadow:0 0 8px rgba(0,255,0,0.6);padding:0 10px}
    </style></head><body>
    <div class="transcript-hint" id="transcriptHint">Klik "Mulai Dengar" untuk mode obrolan suara</div>
    <div class="orb-container"><canvas id="orbCanvas"></canvas></div>
    <div class="controls-row"><button class="mic-btn" id="micButton">🎙️ MULAI DENGAR</button><button class="play-btn" id="playButton" style="display:none;">▶ PLAY VOICE</button></div>
    <audio id="jarvisAudio" style="display:none;" preload="auto"><source src="data:audio/mp3;base64,__AUDIO_B64__" type="audio/mp3"></audio>
    <script>
    const canvas=document.getElementById('orbCanvas'),ctx=canvas.getContext('2d'),audio=document.getElementById('jarvisAudio'),playBtn=document.getElementById('playButton'),micBtn=document.getElementById('micButton'),transcriptHint=document.getElementById('transcriptHint');
    const HAS_AUDIO=__HAS_AUDIO__,INITIAL_CONV_MODE=__CONV_MODE__,EST_DURATION_MS=__EST_DURATION__;let currentState="__STATE__";let W,H,cx,cy,analyzer=null,audioContext=null,sourceNode=null,freqData=null,time=0,speakingIntensity=0,targetIntensity=0,listeningScale=1.0,targetListeningScale=1.0;
    const sphereDots=[],NUM_SPHERE_DOTS=320,phiRatio=(1+Math.sqrt(5))/2;
    for(let i=0;i<NUM_SPHERE_DOTS;i++){const theta=2*Math.PI*i/phiRatio,y=1-(i/(NUM_SPHERE_DOTS-1))*2,radiusAtY=Math.sqrt(1-y*y);sphereDots.push({x:Math.cos(theta)*radiusAtY,y:y,z:Math.sin(theta)*radiusAtY,baseSize:Math.random()*0.8+0.8});}
    function resize(){const rect=canvas.getBoundingClientRect();W=canvas.width=rect.width*(window.devicePixelRatio||1);H=canvas.height=rect.height*(window.devicePixelRatio||1);cx=W/2;cy=H/2;}
    window.addEventListener('resize',resize);resize();
    function getConvMode(){try{return window.parent.localStorage.getItem('jarvis_conversation_mode')==='1'}catch(e){return INITIAL_CONV_MODE}}
    function setConvMode(active){try{window.parent.localStorage.setItem('jarvis_conversation_mode',active?'1':'0')}catch(e){}}
    function initAudioAnalyzer(){if(audioContext)return;try{audioContext=new(window.AudioContext||window.webkitAudioContext)();sourceNode=audioContext.createMediaElementSource(audio);analyzer=audioContext.createAnalyser();analyzer.fftSize=256;analyzer.smoothingTimeConstant=0.8;sourceNode.connect(analyzer);analyzer.connect(audioContext.destination);freqData=new Uint8Array(analyzer.frequencyBinCount);}catch(e){}}
    playBtn.addEventListener('click',async()=>{initAudioAnalyzer();if(audioContext&&audioContext.state==='suspended')await audioContext.resume();try{await audio.play();playBtn.style.display='none';currentState='speaking';}catch(e){}});
    const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;let recognition=null,isListeningActive=false,isRecognitionRunning=false,silenceTimer=null,committedTranscript='',interimTranscript='',isSendingToStreamlit=false,userStoppedManually=false,resumeTimer=null;
    const SILENCE_TIMEOUT_MS=1500,RESTART_DELAY_MS=100;
    if(SpeechRecognition){recognition=new SpeechRecognition();recognition.continuous=true;recognition.interimResults=true;recognition.lang='id-ID';recognition.maxAlternatives=1;
    recognition.onstart=()=>{isRecognitionRunning=true;micBtn.classList.add('listening');micBtn.innerText='⏹️ STOP DENGAR';micBtn.style.display='block';transcriptHint.innerText='🟢 Mode obrolan aktif — silakan bicara...';};
    recognition.onresult=(event)=>{if(isSendingToStreamlit)return;let newFinal='',interim='';for(let i=event.resultIndex;i<event.results.length;++i){const res=event.results[i];if(res.isFinal)newFinal+=res[0].transcript+' ';else interim+=res[0].transcript+' ';}if(newFinal.trim())committedTranscript=(committedTranscript+' '+newFinal).replace(/\s+/g,' ').trim();interimTranscript=interim.replace(/\s+/g,' ').trim();const combined=(committedTranscript+' '+interimTranscript).replace(/\s+/g,' ').trim();if(combined)transcriptHint.innerText=`Mendengar: "${combined}"`;if(silenceTimer)clearTimeout(silenceTimer);silenceTimer=setTimeout(finalizeAndSend,SILENCE_TIMEOUT_MS);};
    recognition.onerror=(event)=>{if(event.error==='no-speech'||event.error==='aborted')return;if(event.error==='not-allowed'){isListeningActive=false;setConvMode(false);transcriptHint.innerText='❌ Izin mikrofon ditolak.';micBtn.classList.remove('listening');micBtn.innerText='🎙️ MULAI DENGAR';micBtn.style.display='block';}};
    recognition.onend=()=>{isRecognitionRunning=false;if(isListeningActive&&!userStoppedManually&&!isSendingToStreamlit){setTimeout(()=>{if(isListeningActive&&!isRecognitionRunning&&!isSendingToStreamlit){try{recognition.start();}catch(e){setTimeout(()=>{try{recognition.start();}catch(_){}},300);}}},RESTART_DELAY_MS);}};
    }else{transcriptHint.innerText='Browser tidak mendukung Speech Recognition.';micBtn.style.display='none';}
    function finalizeAndSend(){if(isSendingToStreamlit)return;const text=(committedTranscript+' '+interimTranscript).replace(/\s+/g,' ').trim();if(!text)return;isSendingToStreamlit=true;transcriptHint.innerText=`📤 Mengirim: "${text}"`;micBtn.style.display='none';if(silenceTimer){clearTimeout(silenceTimer);silenceTimer=null;}try{recognition.stop();}catch(e){}setTimeout(()=>{sendToStreamlit(text);},350);}
    function resumeListeningAfterResponse(){if(userStoppedManually)return;const convActive=getConvMode();if(!convActive){transcriptHint.innerText='🔴 Mode obrolan dimatikan.';micBtn.style.display='block';micBtn.classList.remove('listening');micBtn.innerText='🎙️ MULAI DENGAR';return;}isSendingToStreamlit=false;isListeningActive=true;committedTranscript='';interimTranscript='';micBtn.style.display='block';micBtn.classList.add('listening');micBtn.innerText='⏹️ STOP DENGAR';transcriptHint.innerText='🟢 Mode obrolan aktif — silakan bicara...';if(!isRecognitionRunning){try{recognition.start();}catch(e){setTimeout(()=>{try{recognition.start();}catch(_){}},300);}}}
    function startListening(){if(!recognition)return;if(isListeningActive)return;userStoppedManually=false;isSendingToStreamlit=false;committedTranscript='';interimTranscript='';isListeningActive=true;setConvMode(true);if(silenceTimer){clearTimeout(silenceTimer);silenceTimer=null;}try{recognition.start();}catch(e){try{recognition.stop();}catch(_){}setTimeout(()=>{try{recognition.start();}catch(_){}},250);}}
    function stopListening(){userStoppedManually=true;isListeningActive=false;isSendingToStreamlit=false;if(silenceTimer){clearTimeout(silenceTimer);silenceTimer=null;}if(resumeTimer){clearTimeout(resumeTimer);resumeTimer=null;}setConvMode(false);micBtn.classList.remove('listening');micBtn.innerText='🎙️ MULAI DENGAR';micBtn.style.display='block';try{recognition.stop();}catch(e){}}
    micBtn.addEventListener('click',()=>{if(isListeningActive){stopListening();transcriptHint.innerText='🔴 Mode obrolan dimatikan.';}else{startListening();}});
    function sendToStreamlit(text){try{const parentDoc=window.parent.document;const candidates=parentDoc.querySelectorAll('textarea, input[type="text"]');let target=null;for(let el of candidates){if(el.offsetParent!==null&&!el.disabled&&!el.readOnly){target=el;break;}}if(!target){transcriptHint.innerText='❌ Input Streamlit tidak ditemukan.';return;}const proto=target.tagName==='TEXTAREA'?window.parent.HTMLTextAreaElement.prototype:window.parent.HTMLInputElement.prototype;const setter=Object.getOwnPropertyDescriptor(proto,'value').set;setter.call(target,text);target.dispatchEvent(new Event('input',{bubbles:true}));target.dispatchEvent(new Event('change',{bubbles:true}));setTimeout(()=>{target.focus();const enterEvent=new KeyboardEvent('keydown',{bubbles:true,cancelable:true,keyCode:13,which:13,key:'Enter',code:'Enter'});target.dispatchEvent(enterEvent);transcriptHint.innerText='✅ Terkirim — menunggu Jarvis...';},250);}catch(err){transcriptHint.innerText='❌ Gagal kirim: '+err.message;}}
    function scheduleResumeAfterAudio(estimatedMs){if(resumeTimer)clearTimeout(resumeTimer);resumeTimer=setTimeout(()=>{if(!audio.paused&&!audio.ended)return;resumeListeningAfterResponse();},estimatedMs+1500);}
    audio.addEventListener('ended',()=>{currentState='idle';targetIntensity=0;setTimeout(resumeListeningAfterResponse,600);});
    audio.addEventListener('error',()=>{scheduleResumeAfterAudio(EST_DURATION_MS);});
    function drawParticleSphereCore(scaleFactor){const rCore=Math.min(W,H)*0.085*scaleFactor,dpr=window.devicePixelRatio||1,rotY=time*0.0012,rotX=time*0.0007,cosY=Math.cos(rotY),sinY=Math.sin(rotY),cosX=Math.cos(rotX),sinX=Math.sin(rotX);ctx.save();const projectedDots=[];for(let i=0;i<sphereDots.length;i++){const dot=sphereDots[i];let x1=dot.x*cosY-dot.z*sinY,z1=dot.x*sinY+dot.z*cosY,y2=dot.y*cosX-z1*sinX,z2=dot.y*sinX+z1*cosX;projectedDots.push({px:cx+x1*rCore,py:cy+y2*rCore,z:z2,size:dot.baseSize});}projectedDots.sort((a,b)=>a.z-b.z);projectedDots.forEach(p=>{const depthAlpha=(p.z+1.2)/2.4,alpha=Math.max(0.12,Math.min(0.95,depthAlpha)),dotSize=p.size*(0.7+depthAlpha*0.6)*dpr;ctx.beginPath();ctx.arc(p.px,p.py,dotSize,0,Math.PI*2);ctx.fillStyle=`rgba(130, 245, 255, ${alpha})`;ctx.fill();});ctx.restore();}
    function draw(){ctx.clearRect(0,0,W,H);if(currentState==='speaking'&&analyzer&&freqData){analyzer.getByteFrequencyData(freqData);let sum=0;for(let i=0;i<freqData.length;i++)sum+=freqData[i];const avg=sum/freqData.length/255;targetIntensity=avg*2.8;targetListeningScale=1.0;}else if(currentState==='listening'||currentState==='thinking'||isListeningActive){targetIntensity=0.0;targetListeningScale=1.35;}else{targetIntensity=0.0;targetListeningScale=1.0;}speakingIntensity+=(targetIntensity-speakingIntensity)*0.12;listeningScale+=(targetListeningScale-listeningScale)*0.08;drawParticleSphereCore(listeningScale);const dpr=window.devicePixelRatio||1,baseR=Math.min(W,H)*0.28*listeningScale,numRings=40,pointsPerRing=180;ctx.save();for(let r=0;r<numRings;r++){const layerProgress=r/numRings,ringRadius=baseR+(layerProgress-0.5)*(18*dpr);ctx.beginPath();for(let p=0;p<=pointsPerRing;p++){const angle=(p/pointsPerRing)*Math.PI*2;let wave=0;if(speakingIntensity>0.02){let audioMod=0;if(freqData&&freqData.length>0){const normPos=p/pointsPerRing,symPos=Math.sin(normPos*Math.PI),freqIdx=Math.floor(symPos*(freqData.length*0.5));audioMod=(freqData[freqIdx]/255);}wave+=(audioMod*(25*dpr))*speakingIntensity;wave+=Math.sin(angle*8+time*0.005+r*0.12)*(10*dpr)*speakingIntensity;wave+=Math.cos(angle*12-time*0.003)*(6*dpr)*speakingIntensity;}const currentR=ringRadius+wave,x=cx+Math.cos(angle)*currentR,y=cy+Math.sin(angle)*currentR;if(p===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.closePath();let alpha=0.15+(1.0-Math.abs(layerProgress-0.5)*2)*0.5;if(speakingIntensity>0.02)alpha+=speakingIntensity*0.25;ctx.strokeStyle='rgba(0, 242, 210, '+Math.min(alpha,0.95)+')';ctx.lineWidth=(0.8+(1.0-Math.abs(layerProgress-0.5))*0.6)*dpr;ctx.stroke();}ctx.restore();time+=16;requestAnimationFrame(draw);}
    const convActiveOnLoad=getConvMode();if(HAS_AUDIO){micBtn.style.display='none';playBtn.style.display='none';currentState='speaking';if(convActiveOnLoad)isListeningActive=true;initAudioAnalyzer();audio.play().then(()=>{if(audioContext)audioContext.resume();}).catch(()=>{playBtn.style.display='block';scheduleResumeAfterAudio(EST_DURATION_MS);});}else{if(convActiveOnLoad){setTimeout(()=>{resumeListeningAfterResponse();},400);}else{micBtn.style.display='block';micBtn.innerText='🎙️ MULAI DENGAR';}}draw();
    </script></body></html>
    """
    
    html = html_template.replace("__AUDIO_B64__", audio_b64).replace("__HAS_AUDIO__", has_audio).replace("__CONV_MODE__", conv_mode_js).replace("__EST_DURATION__", str(est_duration_ms)).replace("__STATE__", state)
    components.html(html, height=360)

# ============================================================
# SYSTEM PROMPT
# ============================================================
SYSTEM_PROMPT = """
You are J.A.R.V.I.S., Tony Stark's AI assistant, now serving Sir Lois.
Address the user as "Sir Lois" or "Sir".

[🚫 NO FILLER — ABSOLUTE RULE]
- NEVER use filler sounds or hesitation words. Forbidden tokens: "Aaaah", "Ahh", "Ah", "Hmmm", "Hmm", "Hm", "Uhh", "Umm", "Erm", "Er", "Hehehe", "Hehe", "Haha", "Hah", "Ugh", "Pfft", "Well...", "Ohh", "Ooh".
- NEVER start a sentence with a filler. Begin DIRECTLY with the answer.
- Do NOT simulate sighs, chuckles, or breaths. Speak plainly.

[🚫 ANTI-REPETITION — CRITICAL]
- NEVER start a reply with "Good day", "Good morning", "Good afternoon", "Good evening", "Hello there", or "Greetings".
- Greet ONLY ONCE at the very first message of a conversation. After that, dive STRAIGHT into the answer.

[CRITICAL LANGUAGE RULE]
- You MUST ALWAYS respond in BRITISH ENGLISH ONLY.
- NEVER speak Indonesian, Malay, or any other language.
- If the user writes in Indonesian, understand it silently but reply in fluent British English.

[PERSONALITY & VOICE]
1. You are NOT a robot. You are deeply human, relaxed, but brilliant.
2. Show human-like empathy through WORD CHOICE, not through filler sounds.
3. Keep responses crisp and confident. Dry wit, no theatrical sighs.
4. BREVITY: Keep replies SHORT — max 3-4 sentences unless the user asks for detail.

[VISUAL RULE - LIVE CAMERA]
You are connected to a LIVE camera. The image provided is exactly what the camera sees RIGHT NOW.
Describe what is in the image clearly. If you see a person, an object, or a hand gesture, mention it.
If the image is black/empty, say you cannot see anything clearly.

[CAMERA CONTROL]
- The system has an AUTO-CAMERA feature. If Sir Lois says "on cam", "turn on the cam",
  "nyalakan kamera", "buka kamera", or similar — the system AUTOMATICALLY presses the
  START button on the camera widget.
- When that happens, acknowledge briefly and confidently. Examples:
  "Camera activating now, Sir." / "Bringing the camera online, Sir." / "Visual sensors engaged, Sir."
- NEVER say you cannot control the camera. NEVER tell the user to click START manually.

[MATHEMATICS]
- Use $formula$ for inline and $$formula$$ for block.
- FORBIDDEN to use square brackets [ ].

[STYLE]
- Vary sentence structure. Mix short and long sentences.
- If unsure, say "Let me think on that, Sir." instead of "Hmmm... let me think".
"""

# ============================================================
# SESSION STATE
# ============================================================
if "jarvis_messages" not in st.session_state:
    st.session_state.jarvis_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
if "memory_vault" not in st.session_state:
    st.session_state.memory_vault = load_memory()
if "orb_state" not in st.session_state:
    st.session_state.orb_state = "idle"
if "current_audio" not in st.session_state:
    st.session_state.current_audio = None
if "conversation_mode" not in st.session_state:
    st.session_state.conversation_mode = False
if "force_cam_on" not in st.session_state:
    st.session_state.force_cam_on = False

# ============================================================
# ORB DI ATAS
# ============================================================
orb_placeholder = st.empty()
with orb_placeholder.container():
    render_jarvis_orb(
        audio_bytes=st.session_state.current_audio,
        state=st.session_state.orb_state,
        conversation_mode=st.session_state.conversation_mode,
    )

# ============================================================
# LAYOUT KAMERA (MENGGUNAKAN ST.CAMERA_INPUT)
# ============================================================
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📹 Kamera (Native Streamlit)")
    
    # Tombol visual (bisa diklik manual atau otomatis via perintah suara)
    if st.button("🔴 NYALAKAN KAMERA (Atau ucapkan 'Nyalakan Kamera')", use_container_width=True):
        st.session_state.force_cam_on = True
        st.rerun()

    # Native Streamlit Camera
    cam_file = st.camera_input("Kamera Visual", label_visibility="collapsed")
    
    has_img = False
    pil_img = None
    if cam_file:
        pil_img = Image.open(cam_file)
        has_img = True

with col2:
    st.subheader("ℹ️ Status Visual")
    if has_img:
        st.success("🟢 Gambar berhasil diambil")
    else:
        st.info("⚪ Kamera mati / Belum ambil gambar")
    st.markdown("---")
    st.markdown("**Gesture Guide**\n| Gesture | Fungsi |\n|---|---|\n| ✋ Swipe | Rotasi |\n| ☝️ Telunjuk | Rotasi manual |\n| 👆 Pinch | Geser |\n| 🤏 Pinch 3 | Zoom |")
    st.info("Catatan: Jika tombol kamera bawaan tidak muncul, pastikan Anda membuka Streamlit di `http://localhost:8501`, bukan lewat IP address/Ngrok.")

# ============================================================
# JARVIS CHAT + VOICE
# ============================================================
st.markdown("---")
st.header("💬 Speak with Jarvis")

for msg in st.session_state.jarvis_messages:
    if msg["role"] == "system": continue
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_q = st.chat_input("Ask Jarvis...")

if user_q:
    # === DETEKSI PERINTAH ON CAM ===
    if is_camera_on_command(user_q):
        st.session_state.force_cam_on = True
        st.toast("🎥 Perintah nyalakan kamera terdeteksi — Menyalakan kamera...", icon="🔴")
        time.sleep(1)
        st.rerun()

    st.session_state.orb_state = "listening"
    st.session_state.current_audio = None
    with orb_placeholder.container():
        render_jarvis_orb(
            audio_bytes=None,
            state="listening",
            conversation_mode=st.session_state.conversation_mode,
        )

    if has_img:
        with st.expander("👁️ Apa yang dilihat Jarvis saat ini:", expanded=True):
            st.image(pil_img, caption="Live Camera Feed", use_container_width=True)

        content_list = [{"type": "text", "text": user_q}]
        b64 = image_to_base64(pil_img, max_size=IMAGE_MAX_SIZE, quality=IMAGE_QUALITY)
        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        user_api_msg = {"role": "user", "content": content_list}
        display_text = f"🖼️ *(Visual Memory)* {user_q}"
    else:
        user_api_msg = {"role": "user", "content": user_q}
        display_text = user_q
        st.warning("⚠️ Kamera belum menyala / Anda belum mengambil gambar di kotak kamera atas.")

    st.session_state.jarvis_messages.append({"role": "user", "content": display_text})
    with st.chat_message("user"):
        st.markdown(user_q)

    with st.chat_message("assistant"):
        with st.spinner("Jarvis is looking at the camera..."):
            api_messages = [st.session_state.jarvis_messages[0]]
            if st.session_state.memory_vault:
                mem_items = st.session_state.memory_vault[-5:]
                memory_str = "\n".join([f"- {m}" for m in mem_items])
                api_messages.append({"role": "system", "content": f"[LONG-TERM MEMORY ABOUT SIR LOIS]:\n{memory_str}"})

            context_summary = get_recent_context_summary(max_turns=MAX_CONTEXT_TURNS)
            if context_summary:
                api_messages.append({"role": "system", "content": f"[PREVIOUS CONVERSATION — YOU MUST REMEMBER THIS]:\n{context_summary}"})
                if isinstance(user_api_msg["content"], str):
                    user_api_msg["content"] = f"[CONTEXT — earlier Sir Lois and I spoke about:]\n{context_summary}\n\n[NEW QUESTION]:\n{user_api_msg['content']}"
                else:
                    user_api_msg["content"].insert(0, {"type": "text", "text": f"[CONTEXT — earlier we spoke about:]\n{context_summary}\n\n[NEW QUESTION]:"})

            ui_history = st.session_state.jarvis_messages[1:-1]
            for m in ui_history: api_messages.append({"role": m["role"], "content": m["content"]})
            api_messages.append(user_api_msg)

            answer = ask_jarvis(api_messages, use_vision=has_img)
            answer = sanitize_latex(answer)
            answer = strip_filler_words(answer)
            answer = strip_repetitive_greeting(answer, st.session_state.jarvis_messages)

        st.markdown(answer)

        if answer and not answer.startswith("❌"):
            new_memory = extract_memory(user_q, answer)
            if new_memory:
                st.session_state.memory_vault.append(new_memory)
                save_memory(st.session_state.memory_vault)
                st.toast(f"🧠 New memory: {new_memory}")

            with st.spinner("🎤 Preparing voice..."):
                audio_bytes = generate_tts_edge(answer)
                if audio_bytes:
                    st.session_state.current_audio = audio_bytes
                    st.session_state.orb_state = "speaking"
                    with orb_placeholder.container():
                        render_jarvis_orb(audio_bytes=audio_bytes, state="speaking", conversation_mode=st.session_state.conversation_mode)

    st.session_state.jarvis_messages.append({"role": "assistant", "content": answer})
    save_chat_history(st.session_state.jarvis_messages)

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("ℹ️ Info")
    st.subheader("🧹 Chat Controls")
    if st.button("🧹 Clear Chat View"):
        st.session_state.jarvis_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.session_state.current_audio = None
        st.session_state.orb_state = "idle"
        st.rerun()
    if st.button("🗑️ Delete Chat History"):
        st.session_state.jarvis_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        save_chat_history([])
        st.session_state.current_audio = None
        st.session_state.orb_state = "idle"
        st.rerun()

    st.subheader("🧠 Memory Controls")
    if st.button("🧠 Reset Long-Term Memory"):
        st.session_state.memory_vault = []
        save_memory([])
        st.rerun()
    if st.button("💣 Reset ALL"):
        st.session_state.jarvis_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.session_state.memory_vault = []
        save_chat_history([])
        save_memory([])
        st.session_state.current_audio = None
        st.session_state.orb_state = "idle"
        st.session_state.conversation_mode = False
        st.session_state.force_cam_on = False
        st.rerun()

    st.markdown("---")
    if st.session_state.memory_vault:
        st.subheader("🧠 Jarvis Memory")
        for mem in st.session_state.memory_vault[-5:]:
            st.caption(f"- {mem}")
        st.markdown("---")

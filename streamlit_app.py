import av
import cv2
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import urllib.request
import os
import time
import io
import base64
import asyncio
import re
import json
import pathlib
import collections
from PIL import Image

from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

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

JARVIS_VISION_MODEL = "qwen/qwen2.5-vl-7b-instruct" # Diperbarui ke model vision stabil Groq
JARVIS_TEXT_MODEL = "llama-3.3-70b-versatile"         # Diperbarui ke Llama 3.3 untuk respons cepat & akurat
JARVIS_MEMORY_MODEL = "llama-3.1-8b-instant"

MAX_OUTPUT_TOKENS = 300
MAX_CONTEXT_TURNS = 5
MAX_MSG_CHARS = 400
IMAGE_MAX_SIZE = 512
IMAGE_QUALITY = 60

VOICE_EN = "en-GB-RyanNeural"
VOICE_RATE = "-5%"
VOICE_PITCH = "-3Hz"

# ============ Konfigurasi Halaman ============
st.set_page_config(page_title="J.A.R.V.I.S - Quantum Dots", page_icon="🔵", layout="wide")
st.title("🔵 J.A.R.V.I.S — Quantum Dots")
st.markdown("Sistem visual aktif. Klik **'Mulai Dengar'** untuk mengaktifkan interaksi suara berkelanjutan.")

# ============ WebRTC & Konstanta ============
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

PINCH_ENTER = 40
PINCH_EXIT = 60
HOLD_THRESHOLD = 1.0
MIN_SCALE, MAX_SCALE = 0.5, 3.0
ZOOM_SENSITIVITY = 0.01
MAX_ZOOM_STEP = 0.03
THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12
PINKY_TIP = 20
POS_ALPHA = 0.45
ROT_ALPHA = 0.20
SCALE_ALPHA = 0.20
INERTIA_DECAY = 0.93
PAN_POS_ALPHA = 0.7
PAN_DEADZONE = 0.5
PAN_APPLY_SMOOTH = 0.55

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)
]

MODEL_PATH = "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

if not os.path.exists(MODEL_PATH):
    with st.spinner("📥 Mengunduh model AI..."):
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

# ============================================================
# PERSISTENCE HELPERS
# ============================================================
SCRIPT_DIR = pathlib.Path(__file__).parent.absolute()
MEMORY_FILE = str(SCRIPT_DIR / "jarvis_persistent_memory.json")
CHAT_FILE = str(SCRIPT_DIR / "jarvis_chat_history.json")

def _log(msg: str):
    print(f"[JARVIS-PERSIST] {msg}", flush=True)

def load_memory() -> list:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_memory(memory_list: list):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"ERROR saving memory: {e}")

def load_chat_history() -> list:
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_chat_history(messages: list):
    try:
        clean_msgs = []
        for m in messages:
            if m["role"] == "system":
                continue
            content = m["content"]
            if isinstance(content, list):
                texts = [c["text"] for c in content if c.get("type") == "text"]
                content = " ".join(texts) if texts else "[image]"
            if isinstance(content, str) and len(content) > MAX_MSG_CHARS:
                content = content[:MAX_MSG_CHARS] + "..."
            clean_msgs.append({"role": m["role"], "content": content})
        with open(CHAT_FILE, "w", encoding="utf-8") as f:
            json.dump(clean_msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"ERROR saving chat: {e}")

def get_recent_context_summary(max_turns: int = MAX_CONTEXT_TURNS) -> str:
    history = load_chat_history()
    if not history:
        return ""
    recent = history[-max_turns * 2:]
    lines = []
    for m in recent:
        role = "Sir Lois" if m["role"] == "user" else "Jarvis"
        content = m["content"]
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        if isinstance(content, str) and len(content) > MAX_MSG_CHARS:
            content = content[:MAX_MSG_CHARS] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

# ============================================================
# KELAS KAMERA
# ============================================================
class Hand3DProcessor(VideoProcessorBase):
    def __init__(self):
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.HandLandmarkerOptions(
            base_options=base_options, running_mode=vision.RunningMode.VIDEO,
            num_hands=1, min_hand_detection_confidence=0.3,
            min_hand_presence_confidence=0.3, min_tracking_confidence=0.5
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        self.frame_timestamp = 0
        
        self.rx, self.ry = 0.5, 0.5
        self.scale = 1.0
        self.offset_x, self.offset_y = 0.0, 0.0
        self.target_rx, self.target_ry = 0.5, 0.5
        self.target_scale = 1.0
        self.target_offset_x, self.target_offset_y = 0.0, 0.0
        self.vel_ry = 0.0
        self.vel_rx = 0.0
        self.smooth_index = None
        self.smooth_palm = None
        self.active_mode = None
        self.candidate_mode = None
        self.hold_start_time = 0.0
        self.last_seen_time = 0.0
        self.smoothed_dist_index = None
        self.smoothed_dist_middle = None
        self.smoothed_dist_mid_index = None
        self.prev_palm_pos = None
        self.swipe_vel_smooth = np.array([0.0, 0.0])
        self.vertices = np.array([
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
            [-1, -1,  1], [1, -1,  1], [1, 1,  1], [-1, 1,  1]
        ], dtype=np.float32)
        self.edges = [
            (0,1), (1,2), (2,3), (3,0), (4,5), (5,6), (6,7), (7,4),
            (0,4), (1,5), (2,6), (3,7)
        ]
        
        self.frame_buffer = collections.deque(maxlen=2)
        self.last_buffer_time = time.time()
        self.buffer_interval = 0.5 # Diubah ke 0.5 detik agar hemat bandwidth

    def _to_pixel(self, landmark, w, h):
        return int(landmark.x * w), int(landmark.y * h)

    def _draw_landmarks(self, img, landmarks, w, h):
        for a, b in HAND_CONNECTIONS:
            p1 = self._to_pixel(landmarks[a], w, h)
            p2 = self._to_pixel(landmarks[b], w, h)
            cv2.line(img, p1, p2, (80, 80, 80), 1, cv2.LINE_AA)

    def _draw_3d_cube(self, img, cx, cy):
        cos_x, sin_x = np.cos(self.rx), np.sin(self.rx)
        cos_y, sin_y = np.cos(self.ry), np.sin(self.ry)
        rot_x = np.array([[1, 0, 0], [0, cos_x, -sin_x], [0, sin_x, cos_x]])
        rot_y = np.array([[cos_y, 0, sin_y], [0, 1, 0], [-sin_y, 0, cos_y]])
        rot_matrix = rot_y @ rot_x
        transformed = self.vertices @ rot_matrix.T
        pts_2d = []
        fov = 4.0
        for v in transformed:
            v_scaled = v * self.scale
            z = v_scaled[2] + fov
            if z <= 0.1: z = 0.1
            px = int((v_scaled[0] / z) * 150) + cx + int(self.offset_x)
            py = int((v_scaled[1] / z) * 150) + cy + int(self.offset_y)
            pts_2d.append((px, py, v_scaled[2]))
        for a, b in self.edges:
            p1, p2 = pts_2d[a], pts_2d[b]
            depth = (p1[2] + p2[2]) / 2
            intensity = float(np.clip(1.0 - depth / 2.0, 0.2, 1.0))
            color = (int(255 * intensity), int(255 * intensity), 0)
            cv2.line(img, (p1[0], p1[1]), (p2[0], p2[1]), color, 6, cv2.LINE_AA)

    @staticmethod
    def _smooth(new_val, old_val, alpha):
        if old_val is None: return new_val
        return alpha * new_val + (1 - alpha) * old_val

    @staticmethod
    def _smooth_pt(new_pt, old_pt, alpha):
        if old_pt is None: return new_pt
        return (alpha * new_pt[0] + (1 - alpha) * old_pt[0], alpha * new_pt[1] + (1 - alpha) * old_pt[1])

    @staticmethod
    def _deadzone(delta, threshold):
        if abs(delta) < threshold: return 0.0
        return delta - np.sign(delta) * threshold

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)
        h, w, _ = img.shape

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        self.frame_timestamp += 1
        results = self.detector.detect_for_video(mp_image, self.frame_timestamp)

        mode_text = "MODE: SIAP"
        color_text = (200, 200, 200)
        current_time = time.time()

        self.target_ry += self.vel_ry
        self.target_rx += self.vel_rx
        self.vel_ry *= INERTIA_DECAY
        self.vel_rx *= INERTIA_DECAY
        
        self.ry = self._smooth(self.target_ry, self.ry, ROT_ALPHA)
        self.rx = self._smooth(self.target_rx, self.rx, ROT_ALPHA)
        self.scale = self._smooth(self.target_scale, self.scale, SCALE_ALPHA)

        if results.hand_landmarks:
            lm = results.hand_landmarks[0]
            self._draw_landmarks(img, lm, w, h)

        cx, cy = w // 2, h // 2
        self._draw_3d_cube(img, cx, cy)
        cv2.putText(img, mode_text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_text, 2, cv2.LINE_AA)

        if current_time - self.last_buffer_time > self.buffer_interval:
            self.frame_buffer.append(img.copy())
            self.last_buffer_time = current_time

        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def __del__(self):
        try: self.detector.close()
        except: pass

# ============================================================
# HELPER JARVIS
# ============================================================
def image_to_base64(pil_img: Image.Image, max_size=IMAGE_MAX_SIZE, quality=IMAGE_QUALITY) -> str:
    img = pil_img.copy()
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def ask_jarvis(api_messages: list, use_vision: bool) -> str:
    if not GROQ_AVAILABLE: return "❌ `groq` library not installed."
    if not GROQ_API_KEY: return "❌ Groq API key is missing."
    
    client = Groq(api_key=GROQ_API_KEY)
    model = JARVIS_VISION_MODEL if use_vision else JARVIS_TEXT_MODEL
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=0.7,
            max_tokens=MAX_OUTPUT_TOKENS,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"❌ Jarvis Error: {str(e)[:300]}"

def sanitize_latex(text: str) -> str:
    if not text: return text
    text = re.sub(r'\[\s*(.*?)\s*\]', r'\1', text, flags=re.DOTALL)
    return text.strip()

def strip_filler_words(text: str) -> str:
    if not text: return text
    filler_patterns = [r'^\s*(Aaa+h+|Ahh+|Ah+|Hmm+m*|Hm+|Uhh+|Umm+|Erm+|Er+|Hehehe+|Hehe+|Haha+|Hah+|Ugh+|Pfft+|Ohh+|Ooh+)[\s,\.\!\?…—\-]*']
    for pattern in filler_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
    return text.strip()

def strip_repetitive_greeting(text: str, history: list) -> str:
    if not text: return text
    past_greetings = sum(1 for m in history if m["role"] == "assistant" and "good day" in str(m["content"]).lower())
    if past_greetings >= 1:
        text = re.sub(r'^\s*(good day|good morning|good afternoon|good evening|hello there)[\s,\.!]*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_memory(user_text: str, ai_text: str) -> str | None:
    if not GROQ_AVAILABLE or not GROQ_API_KEY: return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = f"Extract a short memory fact about Sir Lois if any, max 10 words. Else say NONE.\nUser: {user_text}\nAI: {ai_text}"
        resp = client.chat.completions.create(
            model=JARVIS_MEMORY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30, temperature=0.1
        )
        mem = resp.choices[0].message.content.strip()
        return mem if "NONE" not in mem.upper() and len(mem) > 4 else None
    except Exception:
        return None

def _normalize_for_tts(text: str) -> str:
    text = re.sub(r'\$.*?\$', ' formula ', text)
    text = strip_filler_words(text)
    text = re.sub(r'[*#_`>]', '', text)
    return text.strip()

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
    except Exception:
        return None

# ============================================================
# JARVIS ORB
# ============================================================
def render_jarvis_orb(audio_bytes: bytes = None, state: str = "idle", conversation_mode: bool = False):
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else ""
    has_audio = "true" if audio_bytes else "false"
    conv_mode_js = "true" if conversation_mode else "false"
    
    html_template = r"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { background: transparent; overflow: hidden; font-family: monospace; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; }
            .orb-container { position: relative; width: 100%; height: 300px; display: flex; align-items: center; justify-content: center; }
            canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
            .controls-row { position: absolute; bottom: 5px; z-index: 30; display: flex; gap: 10px; }
            .mic-btn { padding: 8px 16px; border: 1px solid #37dfff; border-radius: 15px; background: rgba(6,20,33,0.9); color: #8defff; cursor: pointer; font-size: 11px; }
            .mic-btn.listening { background: rgba(0,255,200,0.9); color: #000; }
            .transcript-hint { position: absolute; top: 5px; color: #7cfc00; font-size: 11px; text-align: center; width: 100%; z-index: 25; }
        </style>
    </head>
    <body>
        <div class="transcript-hint" id="transcriptHint">Klik "Mulai Dengar" untuk interaksi suara</div>
        <div class="orb-container"><canvas id="orbCanvas"></canvas></div>
        <div class="controls-row">
            <button class="mic-btn" id="micButton">🎙️ MULAI DENGAR</button>
        </div>
        <audio id="jarvisAudio" style="display:none;" preload="auto">
            <source src="data:audio/mp3;base64,__AUDIO_B64__" type="audio/mp3">
        </audio>
        <script>
            const canvas = document.getElementById('orbCanvas');
            const ctx = canvas.getContext('2d');
            const audio = document.getElementById('jarvisAudio');
            const micBtn = document.getElementById('micButton');
            const transcriptHint = document.getElementById('transcriptHint');
            
            const HAS_AUDIO = __HAS_AUDIO__;
            let isListening = false;
            let recognition = null;

            function resize() {
                canvas.width = canvas.parentElement.clientWidth * window.devicePixelRatio;
                canvas.height = canvas.parentElement.clientHeight * window.devicePixelRatio;
            }
            window.addEventListener('resize', resize);
            resize();

            if (HAS_AUDIO) {
                audio.play().catch(() => {});
            }

            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (SpeechRecognition) {
                recognition = new SpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = false;
                recognition.lang = 'id-ID';

                recognition.onresult = (event) => {
                    const text = event.results[0][0].transcript;
                    transcriptHint.innerText = `Mengirim: "${text}"`;
                    sendToStreamlit(text);
                };

                recognition.onend = () => {
                    if (isListening) try { recognition.start(); } catch(e) {}
                };
            }

            micButton.addEventListener('click', () => {
                if (!recognition) return;
                isListening = !isListening;
                if (isListening) {
                    micButton.classList.add('listening');
                    micButton.innerText = '⏹️ STOP DENGAR';
                    try { recognition.start(); } catch(e) {}
                } else {
                    micButton.classList.remove('listening');
                    micButton.innerText = '🎙️ MULAI DENGAR';
                    try { recognition.stop(); } catch(e) {}
                }
            });

            function sendToStreamlit(text) {
                try {
                    const parentDoc = window.parent.document;
                    const candidates = parentDoc.querySelectorAll('textarea, input[type="text"]');
                    for (let el of candidates) {
                        if (el.offsetParent !== null && !el.disabled) {
                            const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype, 'value').set;
                            setter.call(el, text);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new KeyboardEvent('keydown', { keyCode: 13, which: 13, key: 'Enter', bubbles: true }));
                            break;
                        }
                    }
                } catch(e) {}
            }

            function draw() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.beginPath();
                ctx.arc(canvas.width/2, canvas.height/2, 60, 0, Math.PI * 2);
                ctx.fillStyle = HAS_AUDIO ? 'rgba(0,255,200,0.6)' : 'rgba(0,200,255,0.3)';
                ctx.fill();
                requestAnimationFrame(draw);
            }
            draw();
        </script>
    </body>
    </html>
    """
    
    html = (
        html_template
        .replace("__AUDIO_B64__", audio_b64)
        .replace("__HAS_AUDIO__", has_audio)
        .replace("__CONV_MODE__", "true" if conversation_mode else "false")
    )
    components.html(html, height=330)

# ============================================================
# SYSTEM PROMPT
# ============================================================
SYSTEM_PROMPT = """
You are J.A.R.V.I.S., Tony Stark's AI assistant, serving Sir Lois.
Address the user as "Sir Lois" or "Sir".
- Be direct, professional, witty, and concise (max 3 sentences).
- British English only. No filler words.
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

# ============================================================
# UI RENDER
# ============================================================
orb_placeholder = st.empty()
with orb_placeholder.container():
    render_jarvis_orb(audio_bytes=st.session_state.current_audio, state=st.session_state.orb_state)

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("📹 Live Vision Stream")
    ctx = webrtc_streamer(
        key="jarvis-vision",
        video_processor_factory=Hand3DProcessor,
        rtc_configuration=RTC_CONFIGURATION,
        media_stream_constraints={"video": {"width": 640, "height": 480}, "audio": False},
        async_processing=True,
    )

with col2:
    st.subheader("Status & Memory")
    if ctx.state.playing:
        st.success("🟢 Kamera Aktif")
    else:
        st.info("⚪ Kamera Standby")

st.markdown("---")
user_q = st.chat_input("Command Jarvis...")

if user_q:
    st.session_state.current_audio = None
    has_img = False
    pil_imgs = []

    if ctx.state.playing and ctx.video_processor and len(ctx.video_processor.frame_buffer) > 0:
        latest_frame = list(ctx.video_processor.frame_buffer)[-1]
        pil_imgs.append(Image.fromarray(cv2.cvtColor(latest_frame, cv2.COLOR_BGR2RGB)))
        has_img = True

    content_list = [{"type": "text", "text": user_q}]
    if has_img:
        b64 = image_to_base64(pil_imgs[0])
        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    user_api_msg = {"role": "user", "content": content_list if has_img else user_q}
    st.session_state.jarvis_messages.append({"role": "user", "content": user_q})

    with st.chat_message("user"):
        st.markdown(user_q)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            api_messages = [st.session_state.jarvis_messages[0]]
            if st.session_state.memory_vault:
                mem_str = "\n".join([f"- {m}" for m in st.session_state.memory_vault[-3:]])
                api_messages.append({"role": "system", "content": f"[MEMORY]:\n{mem_str}"})
            
            api_messages.extend(st.session_state.jarvis_messages[1:] )
            answer = ask_jarvis(api_messages, use_vision=has_img)
            answer = sanitize_latex(answer)
            answer = strip_filler_words(answer)

        st.markdown(answer)

        if answer and not answer.startswith("❌"):
            audio_bytes = generate_tts_edge(answer)
            if audio_bytes:
                st.session_state.current_audio = audio_bytes
                with orb_placeholder.container():
                    render_jarvis_orb(audio_bytes=audio_bytes, state="speaking")

    st.session_state.jarvis_messages.append({"role": "assistant", "content": answer})
    save_chat_history(st.session_state.jarvis_messages)

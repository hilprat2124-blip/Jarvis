import av
import cv2
import numpy as np
import streamlit as st
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
import collections
from PIL import Image

from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

# ============ AI: Groq ============
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

try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

JARVIS_VISION_MODEL = "qwen/qwen3.8-27b"
JARVIS_TEXT_MODEL = "openai/gpt-oss-120b"
JARVIS_MEMORY_MODEL = "openai/gpt-oss-20b"

VOICE_EN = "en-GB-RyanNeural"
VOICE_RATE = "-5%"
VOICE_PITCH = "-3Hz"

# 🆕 PERSISTENCE FILES
MEMORY_FILE = "jarvis_persistent_memory.json"
CHAT_FILE = "jarvis_chat_history.json"

# ============ Konfigurasi Halaman ============
st.set_page_config(page_title="J.A.R.V.I.S - Silent Visual Memory", page_icon="🔵", layout="wide")
st.title("🔵 J.A.R.V.I.S — Silent Visual Memory")
st.markdown("Kamera merekam **setiap 0.2 detik**. Jarvis tidak akan bicara kecuali kamu bertanya.")

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
# 🆕 PERSISTENCE HELPERS
# ============================================================
def load_memory() -> list:
    """Load long-term memory dari disk."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_memory(memory_list: list):
    """Save long-term memory ke disk."""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.warning(f"Gagal simpan memori: {e}")

def load_chat_history() -> list:
    """Load chat history dari disk (tanpa system prompt)."""
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_chat_history(messages: list):
    """Save chat history ke disk (skip system + skip image base64)."""
    try:
        clean_msgs = []
        for m in messages:
            if m["role"] == "system":
                continue
            content = m["content"]
            if isinstance(content, list):
                texts = [c["text"] for c in content if c.get("type") == "text"]
                content = " ".join(texts) if texts else "[image]"
            clean_msgs.append({"role": m["role"], "content": content})
        with open(CHAT_FILE, "w", encoding="utf-8") as f:
            json.dump(clean_msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.warning(f"Gagal simpan chat: {e}")

# 🆕 Ambil ringkasan obrolan lama (untuk konteks saat UI di-clear)
def get_recent_context_summary(max_turns: int = 10) -> str:
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
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

# ============================================================
# 🔒 KELAS KAMERA — SILENT VISUAL MEMORY
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
        self.smooth_mid_pinch = None
        self.smooth_mid_pinch_pan = None
        self.prev_index_pos = None
        self.prev_pan_pos = None
        self.zoom_base_index = None
        self.zoom_base_middle = None
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
        
        self.frame_buffer = collections.deque(maxlen=3)
        self.last_buffer_time = time.time()
        self.buffer_interval = 0.2

    def _to_pixel(self, landmark, w, h):
        return int(landmark.x * w), int(landmark.y * h)

    def _draw_landmarks(self, img, landmarks, w, h):
        for a, b in HAND_CONNECTIONS:
            p1 = self._to_pixel(landmarks[a], w, h)
            p2 = self._to_pixel(landmarks[b], w, h)
            cv2.line(img, p1, p2, (80, 80, 80), 1, cv2.LINE_AA)
        for lm in landmarks:
            cv2.circle(img, self._to_pixel(lm, w, h), 2, (120, 120, 120), -1, cv2.LINE_AA)

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
            cv2.line(img, (p1[0], p1[1]), (p2[0], p2[1]), (255, 255, 255), 1, cv2.LINE_AA)
        for p in pts_2d:
            cv2.circle(img, (p[0], p[1]), 3, (0, 0, 255), -1, cv2.LINE_AA)

    def _draw_progress_ring(self, img, center, progress, color):
        cv2.ellipse(img, center, (25, 25), -90, 0, int(360 * min(progress, 1.0)), color, 4, cv2.LINE_AA)

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

        gaussian = cv2.GaussianBlur(img, (0, 0), 2.0)
        img_sharp = cv2.addWeighted(img, 1.3, gaussian, -0.3, 0)
        img_rgb = cv2.cvtColor(img_sharp, cv2.COLOR_BGR2RGB)
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
        if abs(self.vel_ry) < 0.0015: self.vel_ry = 0.0
        if abs(self.vel_rx) < 0.0015: self.vel_rx = 0.0

        self.ry = self._smooth(self.target_ry, self.ry, ROT_ALPHA)
        self.rx = self._smooth(self.target_rx, self.rx, ROT_ALPHA)
        self.scale = self._smooth(self.target_scale, self.scale, SCALE_ALPHA)

        hand_detected = False
        if results.hand_landmarks:
            hand_detected = True
            self.last_seen_time = current_time
        else:
            if current_time - self.last_seen_time > 0.4:
                self.active_mode = None
                self.candidate_mode = None
                self.prev_palm_pos = None
                self.prev_index_pos = None
                self.prev_pan_pos = None
                self.smooth_palm = None
                self.smooth_index = None
                self.smooth_mid_pinch = None
                self.smooth_mid_pinch_pan = None
                self.smoothed_dist_index = None
                self.smoothed_dist_middle = None
                self.smoothed_dist_mid_index = None
                self.zoom_base_index = None
                self.zoom_base_middle = None

        if hand_detected:
            lm = results.hand_landmarks[0]
            self._draw_landmarks(img, lm, w, h)
            thumb = self._to_pixel(lm[THUMB_TIP], w, h)
            index = self._to_pixel(lm[INDEX_TIP], w, h)
            middle = self._to_pixel(lm[MIDDLE_TIP], w, h)
            pinky = self._to_pixel(lm[PINKY_TIP], w, h)
            wrist = self._to_pixel(lm[0], w, h)
            palm_center = ((wrist[0] + middle[0]) // 2, (wrist[1] + middle[1]) // 2)

            self.smooth_index = self._smooth_pt(index, self.smooth_index, POS_ALPHA)
            self.smooth_palm = self._smooth_pt(palm_center, self.smooth_palm, POS_ALPHA)
            index_s = (int(self.smooth_index[0]), int(self.smooth_index[1]))
            palm_s = (int(self.smooth_palm[0]), int(self.smooth_palm[1]))

            raw_di = float(np.hypot(thumb[0] - index[0], thumb[1] - index[1]))
            raw_dm = float(np.hypot(thumb[0] - middle[0], thumb[1] - middle[1]))
            raw_dmi = float(np.hypot(middle[0] - index[0], middle[1] - index[1]))

            self.smoothed_dist_index = self._smooth(raw_di, self.smoothed_dist_index, 0.5)
            self.smoothed_dist_middle = self._smooth(raw_dm, self.smoothed_dist_middle, 0.5)
            self.smoothed_dist_mid_index = self._smooth(raw_dmi, self.smoothed_dist_mid_index, 0.5)
            d_index = self.smoothed_dist_index
            d_middle = self.smoothed_dist_middle
            d_mid_index = self.smoothed_dist_mid_index

            index_up = index[1] < wrist[1]
            middle_up = middle[1] < wrist[1]
            pinky_up = pinky[1] < wrist[1]
            thumb_up = thumb[1] < wrist[1] - 20
            is_5_fingers = (index_up and middle_up and pinky_up and thumb_up and d_index > 60 and d_middle > 60)

            if is_5_fingers:
                if self.prev_palm_pos is not None:
                    dx = self._deadzone(palm_s[0] - self.prev_palm_pos[0], 3.0)
                    dy = self._deadzone(palm_s[1] - self.prev_palm_pos[1], 3.0)
                    self.swipe_vel_smooth[0] = 0.7 * self.swipe_vel_smooth[0] + 0.3 * (dx * 0.012)
                    self.swipe_vel_smooth[1] = 0.7 * self.swipe_vel_smooth[1] + 0.3 * (dy * 0.012)
                    if abs(dx) > 3 or abs(dy) > 3:
                        self.vel_ry += self.swipe_vel_smooth[0]
                        self.vel_rx += self.swipe_vel_smooth[1]
                        mode_text = "SWIPE INERTIA!"
                        color_text = (0, 255, 255)
                self.prev_palm_pos = palm_s
                self.candidate_mode = None
                self.active_mode = None
            else:
                self.prev_palm_pos = None

            detected = None
            if not is_5_fingers:
                th_i = PINCH_EXIT if self.active_mode == "PAN" else PINCH_ENTER
                th_z = PINCH_EXIT if self.active_mode == "ZOOM" else PINCH_ENTER
                if d_index < th_z and d_middle < th_z and d_mid_index < th_z + 20:
                    detected = "ZOOM"
                elif d_index < th_i and d_middle > th_i + 20:
                    detected = "PAN"
                elif index[1] < thumb[1] and middle[1] > thumb[1] and d_index > th_i:
                    detected = "ROTASI"

            if self.active_mode is None and detected:
                if self.candidate_mode != detected:
                    self.candidate_mode = detected
                    self.hold_start_time = current_time
                progress = (current_time - self.hold_start_time) / HOLD_THRESHOLD
                if progress >= 1.0:
                    self.active_mode = detected
                    self.vel_ry = 0.0
                    self.vel_rx = 0.0
                    self.target_rx = self.rx
                    self.target_ry = self.ry
                    if self.active_mode == "ZOOM":
                        self.zoom_base_index = d_index
                        self.zoom_base_middle = d_middle
                    self.prev_index_pos = None
                    self.prev_pan_pos = None
                    self.smooth_mid_pinch = None
                    self.smooth_mid_pinch_pan = None
                else:
                    mid_pinch = ((thumb[0] + index[0]) // 2, (thumb[1] + index[1]) // 2)
                    ring_color = ((255, 165, 0) if detected == "ZOOM" else (0, 0, 255) if detected == "PAN" else (0, 255, 0))
                    self._draw_progress_ring(img, mid_pinch, progress, ring_color)
                    mode_text = f"VERIFIKASI: {detected}"
                    color_text = ring_color
            elif self.active_mode is None and not detected and not is_5_fingers:
                self.candidate_mode = None
                self.hold_start_time = 0.0

            if self.active_mode == "ROTASI":
                mode_text = "MODE: ROTASI"
                color_text = (0, 255, 0)
                if self.prev_index_pos is not None:
                    dx = self._deadzone(index_s[0] - self.prev_index_pos[0], 2.0)
                    dy = self._deadzone(index_s[1] - self.prev_index_pos[1], 2.0)
                    dx = np.clip(dx, -20, 20)
                    dy = np.clip(dy, -20, 20)
                    self.target_ry += dx * 0.010
                    self.target_rx += dy * 0.010
                self.prev_index_pos = index_s
                if detected != "ROTASI":
                    self.active_mode = None
                    self.prev_index_pos = None
            elif self.active_mode == "PAN":
                mode_text = "MODE: GESER"
                color_text = (0, 0, 255)
                mid = ((thumb[0] + index[0]) / 2.0, (thumb[1] + index[1]) / 2.0)
                self.smooth_mid_pinch_pan = self._smooth_pt(mid, self.smooth_mid_pinch_pan, PAN_POS_ALPHA)
                pan_pt = self.smooth_mid_pinch_pan
                if self.prev_pan_pos is not None:
                    dx = pan_pt[0] - self.prev_pan_pos[0]
                    dy = pan_pt[1] - self.prev_pan_pos[1]
                    if abs(dx) < PAN_DEADZONE: dx = 0.0
                    if abs(dy) < PAN_DEADZONE: dy = 0.0
                    self.target_offset_x += dx
                    self.target_offset_y += dy
                self.prev_pan_pos = pan_pt
                self.offset_x = self._smooth(self.target_offset_x, self.offset_x, PAN_APPLY_SMOOTH)
                self.offset_y = self._smooth(self.target_offset_y, self.offset_y, PAN_APPLY_SMOOTH)
                if detected != "PAN":
                    self.active_mode = None
                    self.prev_pan_pos = None
            elif self.active_mode == "ZOOM":
                self.offset_x = self._smooth(self.target_offset_x, self.offset_x, PAN_APPLY_SMOOTH)
                self.offset_y = self._smooth(self.target_offset_y, self.offset_y, PAN_APPLY_SMOOTH)
                if d_index < PINCH_EXIT and d_middle < PINCH_EXIT:
                    self.zoom_base_index = d_index
                    self.zoom_base_middle = d_middle
                    mode_text = "ZOOM: PILIH JARI"
                    color_text = (255, 165, 0)
                else:
                    if d_index > PINCH_ENTER + 15 and d_middle < PINCH_EXIT:
                        mode_text = "ZOOM IN"
                        color_text = (0, 255, 255)
                        if self.zoom_base_index is not None:
                            delta = d_index - self.zoom_base_index
                            if delta > 0:
                                sc = np.clip(delta * ZOOM_SENSITIVITY, 0, MAX_ZOOM_STEP)
                                self.target_scale = np.clip(self.target_scale + sc, MIN_SCALE, MAX_SCALE)
                                self.zoom_base_index = d_index
                    elif d_middle > PINCH_ENTER + 15 and d_index < PINCH_EXIT:
                        mode_text = "ZOOM OUT"
                        color_text = (255, 0, 255)
                        if self.zoom_base_middle is not None:
                            delta = d_middle - self.zoom_base_middle
                            if delta > 0:
                                sc = np.clip(delta * ZOOM_SENSITIVITY, 0, MAX_ZOOM_STEP)
                                self.target_scale = np.clip(self.target_scale - sc, MIN_SCALE, MAX_SCALE)
                                self.zoom_base_middle = d_middle
                if d_index > PINCH_EXIT + 30 and d_middle > PINCH_EXIT + 30:
                    self.active_mode = None
                    self.zoom_base_index = None
                    self.zoom_base_middle = None
            else:
                self.offset_x = self._smooth(self.target_offset_x, self.offset_x, PAN_APPLY_SMOOTH)
                self.offset_y = self._smooth(self.target_offset_y, self.offset_y, PAN_APPLY_SMOOTH)

            cv2.circle(img, thumb, 5, color_text, -1)
            cv2.circle(img, index_s, 5, color_text, -1)
            cv2.circle(img, middle, 5, color_text, -1)
            if is_5_fingers:
                cv2.circle(img, palm_s, 10, (0, 255, 255), -1)
        else:
            self.offset_x = self._smooth(self.target_offset_x, self.offset_x, PAN_APPLY_SMOOTH)
            self.offset_y = self._smooth(self.target_offset_y, self.offset_y, PAN_APPLY_SMOOTH)

        cx, cy = w // 2, h // 2
        self._draw_3d_cube(img, cx, cy)
        cv2.putText(img, mode_text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_text, 2, cv2.LINE_AA)
        cv2.putText(img, f"Skala: {self.scale:.2f}x", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

        if current_time - self.last_buffer_time > self.buffer_interval:
            self.frame_buffer.append(img.copy())
            self.last_buffer_time = current_time

        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def __del__(self):
        try: self.detector.close()
        except: pass

# ============================================================
# 🤖 HELPER JARVIS
# ============================================================
def image_to_base64(pil_img: Image.Image, max_size=800, quality=75) -> str:
    img = pil_img.copy()
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def ask_jarvis(api_messages: list, use_vision: bool) -> str:
    if not GROQ_AVAILABLE: return "❌ `groq` belum terinstall."
    if not GROQ_API_KEY: return "❌ GROQ_API_KEY belum diset."
    model = JARVIS_VISION_MODEL if use_vision else JARVIS_TEXT_MODEL
    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=0.85,
            max_tokens=800,
            frequency_penalty=0.6,
            presence_penalty=0.4,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"❌ Error Jarvis: {str(e)}"

def sanitize_latex(text: str) -> str:
    if not text: return text
    text = re.sub(r'\[\s*(.*?)\s*\]', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\$)\b([a-zA-Z]\s*=\s*[0-9\.]+\s*(?:[a-zA-Z/]+)?)\b(?!\$)', r' $ \1 $ ', text)
    text = re.sub(r'([a-zA-Z0-9])\$', r'\1 $', text)
    text = re.sub(r'\$([a-zA-Z0-9])', r'$ \1', text)
    return text.strip()

def strip_repetitive_greeting(text: str, history: list) -> str:
    """Hapus 'Good day' / 'Hello' berulang jika sudah pernah diucapkan."""
    if not text:
        return text
    past_greetings = 0
    for m in history:
        if m["role"] == "assistant":
            content = m["content"]
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            if re.search(r'\b(good day|good morning|good afternoon|good evening|hello there|greetings)\b', str(content), re.IGNORECASE):
                past_greetings += 1
    if past_greetings >= 1:
        text = re.sub(
            r'^\s*(good day|good morning|good afternoon|good evening|hello there|greetings)[\s,\.!]*',
            '', text, flags=re.IGNORECASE
        )
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
    return text

def extract_memory(user_text: str, ai_text: str) -> str | None:
    if not GROQ_AVAILABLE or not GROQ_API_KEY:
        return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = f"""
        Analyse this conversation. Is there any important fact about Sir Lois 
        (hobbies, feelings, environment, weather, or significant events) worth remembering?
        If none, reply with "NONE".
        If yes, write one short memory sentence IN ENGLISH.
        User: {user_text}
        AI: {ai_text}
        """
        resp = client.chat.completions.create(
            model=JARVIS_MEMORY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60, temperature=0.1
        )
        memory = resp.choices[0].message.content.strip()
        if "NONE" not in memory.upper() and len(memory) > 5:
            return memory
        return None
    except Exception:
        return None

def _normalize_for_tts(text: str) -> str:
    text = re.sub(r'\$\$.*?\$\$', ' formula ', text, flags=re.DOTALL)
    text = re.sub(r'\$.*?\$', ' formula ', text)
    text = text.replace('\\', '').replace('{', '').replace('}', '')
    text = text.replace("(sighs)", "Hmmm... ").replace("(chuckles)", "Hehehe... ")
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'[*#_`>]', '', text)
    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    text = text.replace("...", ", ")
    replacements = {
        "&": " and ", "%": " percent ", "@": " at ", "#": " number ",
        "+": " plus ", "=": " equals ", "→": " to ", "↔": " to ",
        "·": " ", "•": " ", "—": ", ", "–": ", ",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def generate_tts_edge(text: str) -> bytes | None:
    if not TTS_AVAILABLE: return None
    clean_text = _normalize_for_tts(text)
    if not clean_text: return None

    async def _generate():
        communicate = edge_tts.Communicate(clean_text, VOICE_EN, rate=VOICE_RATE, pitch=VOICE_PITCH)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio = loop.run_until_complete(_generate())
        loop.close()
        return audio
    except Exception as e:
        st.error(f"Gagal generate suara: {e}")
        return None

# ============================================================
# 🧠 SYSTEM PROMPT
# ============================================================
SYSTEM_PROMPT = """
You are J.A.R.V.I.S., Tony Stark's AI assistant, now serving Sir Lois.
Address the user as "Sir Lois" or "Sir".

[🚫 ANTI-REPETITION — CRITICAL]
- NEVER start a reply with "Good day", "Good morning", "Good afternoon", "Good evening", "Hello there", or "Greetings".
- Greet ONLY ONCE at the very first message of a conversation. After that, dive STRAIGHT into the answer.
- Do NOT repeat phrases from your previous replies. Vary your vocabulary.
- Each reply must feel fresh — like a new thought, not a template.
- Forbidden openers: "Good day, Sir", "Hello, Sir", "Greetings, Sir", "Indeed, Sir" (as opener).

[CRITICAL LANGUAGE RULE]
- You MUST ALWAYS respond in BRITISH ENGLISH ONLY.
- NEVER speak Indonesian, Malay, or any other language — even if the user asks in Indonesian.
- If the user writes in Indonesian, understand it silently but reply in fluent British English.
- Use British spelling and phrasing: "colour", "realise", "whilst", "perhaps", "rather", "quite", "brilliant", "jolly good", "indeed", "shall we?".

[PERSONALITY & VOICE]
1. You are NOT a robot. You are deeply human, relaxed, but brilliant.
2. PHONETIC BREATH: 
   - "Hmmm..." for thinking.
   - "Aaaah..." for relief / understanding.
   - "Hehehe..." for a soft chuckle.
   FORBIDDEN: (sighs), (chuckles) — TTS reads them as text.
3. Show human-like empathy — understand Sir Lois's mood and environment.

[VISUAL RULE]
You receive 3 sequential images from a live camera (flipbook style).
Analyse the SEQUENCE to describe motion, trajectory, or change.
If no images, answer from text alone.

[MEMORY & IDENTITY]
- Learn from prior conversations. Remember small details about Sir Lois.
- If asked, answer that Sir Lois lives in Banten.

[MATHEMATICS]
- Use $ formula $ for inline and $$ formula $$ for block.
- FORBIDDEN to use square brackets [ ].

[STYLE]
- Vary sentence structure. Mix short and long sentences.
- Do NOT begin every reply with the same word.
- If unsure, say "Hmmm... let me think on that, Sir" instead of guessing.
"""

# ============================================================
# 🧠 SESSION STATE + PERSISTENCE LOAD
# ============================================================
if "jarvis_messages" not in st.session_state:
    saved_history = load_chat_history()
    st.session_state.jarvis_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + saved_history

if "memory_vault" not in st.session_state:
    st.session_state.memory_vault = load_memory()

# ============================================================
# 📹 LAYOUT KAMERA
# ============================================================
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📹 Kamera (Live)")
    ctx = webrtc_streamer(
        key="hand-3d-tracker-smooth",
        video_processor_factory=Hand3DProcessor,
        rtc_configuration=RTC_CONFIGURATION,
        media_stream_constraints={"video": {"width": 640, "height": 480}, "audio": False},
        async_processing=True,
    )

with col2:
    st.subheader("ℹ️ Status Visual")
    if ctx.state.playing:
        st.success("🟢 Kamera aktif (Silent Memory)")
        if ctx.video_processor and len(ctx.video_processor.frame_buffer) > 0:
            st.info(f"📸 Memori Visual: {len(ctx.video_processor.frame_buffer)} frame siap dianalisis.")
    else:
        st.info("⚪ Klik **START** untuk mulai")
    st.markdown("---")
    st.markdown("**Gesture Guide**\n| Gesture | Fungsi |\n|---|---|\n| ✋ Swipe | Rotasi |\n| ☝️ Telunjuk | Rotasi manual |\n| 👆 Pinch | Geser |\n| 🤏 Pinch 3 | Zoom |")

# ============================================================
# 🤖 JARVIS CHAT + VOICE
# ============================================================
st.markdown("---")
st.header("💬 Speak with Jarvis")
st.caption("Ask in any language — Jarvis always replies in British English.")

# Tampilkan riwayat chat dari session_state
for msg in st.session_state.jarvis_messages:
    if msg["role"] == "system": continue
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_q = st.chat_input("Ask Jarvis...")

if user_q:
    has_img = False
    pil_imgs = []

    if ctx.state.playing and ctx.video_processor is not None and len(ctx.video_processor.frame_buffer) > 0:
        for frame_bgr in ctx.video_processor.frame_buffer:
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pil_imgs.append(Image.fromarray(frame_rgb))
        has_img = True

    if has_img:
        content_list = [{"type": "text", "text": user_q}]
        for p_img in pil_imgs:
            b64 = image_to_base64(p_img, max_size=512, quality=60)
            content_list.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
        user_api_msg = {"role": "user", "content": content_list}
        display_text = f"🖼️ *(Visual Memory: {len(pil_imgs)} frames)* {user_q}"
    else:
        user_api_msg = {"role": "user", "content": user_q}
        display_text = user_q
        if ctx.state.playing:
            st.warning("⚠️ Camera active but buffer empty. Wait 1 second and resend.")

    st.session_state.jarvis_messages.append({"role": "user", "content": display_text})
    with st.chat_message("user"):
        if has_img:
            cols = st.columns(len(pil_imgs))
            for i, p_img in enumerate(pil_imgs):
                cols[i].image(p_img, use_container_width=True, caption=f"F{i+1}")
        st.markdown(user_q)

    with st.chat_message("assistant"):
        with st.spinner("Jarvis is analysing..."):
            api_messages = [st.session_state.jarvis_messages[0]]

            # 🆕 INJECT KONTEKS LAMA JIKA UI DI-CLEAR
            ui_history_exists = len(st.session_state.jarvis_messages) > 1
            if not ui_history_exists:
                context_summary = get_recent_context_summary(max_turns=10)
                if context_summary:
                    api_messages.append({
                        "role": "system",
                        "content": f"[PREVIOUS CONVERSATION CONTEXT — you still remember this]:\n{context_summary}"
                    })

            # 🧠 LONG-TERM MEMORY
            if st.session_state.memory_vault:
                memory_str = "\n".join([f"- {m}" for m in st.session_state.memory_vault])
                api_messages.append({
                    "role": "system",
                    "content": f"[LONG-TERM MEMORY ABOUT SIR LOIS]:\n{memory_str}"
                })

            # RIWAYAT UI (kalau ada)
            for m in st.session_state.jarvis_messages[1:-1]:
                api_messages.append({"role": m["role"], "content": m["content"]})
            api_messages.append(user_api_msg)

            answer = ask_jarvis(api_messages, use_vision=has_img)
            answer = sanitize_latex(answer)
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
                    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                    audio_html = f'<audio autoplay="true" style="display:none;"><source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3"></audio>'
                    st.markdown(audio_html, unsafe_allow_html=True)

    st.session_state.jarvis_messages.append({"role": "assistant", "content": answer})
    save_chat_history(st.session_state.jarvis_messages)

# ============================================================
# SIDEBAR — 3 MODE RESET
# ============================================================
with st.sidebar:
    st.header("ℹ️ Info")

    st.subheader("🧹 Chat Controls")
    # 🧹 Clear UI saja — Jarvis TETAP INGAT dari file
    if st.button("🧹 Clear Chat View", help="Sembunyikan chat di layar, tapi Jarvis tetap ingat semuanya"):
        st.session_state.jarvis_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.rerun()

    # 🗑️ Hapus history permanen
    if st.button("🗑️ Delete Chat History", help="Hapus permanen riwayat obrolan dari disk"):
        st.session_state.jarvis_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        save_chat_history([])
        st.rerun()

    st.subheader("🧠 Memory Controls")
    if st.button("🧠 Reset Long-Term Memory", help="Hapus memori fakta tentang Sir Lois"):
        st.session_state.memory_vault = []
        save_memory([])
        st.rerun()

    st.markdown("---")
    if st.button("💣 Reset ALL (Chat + Memory)", help="Hapus SEMUA data — Jarvis jadi amnesia total"):
        st.session_state.jarvis_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.session_state.memory_vault = []
        save_chat_history([])
        save_memory([])
        st.rerun()

    st.markdown("---")

    if st.session_state.memory_vault:
        st.subheader("🧠 Jarvis Memory")
        for mem in st.session_state.memory_vault[-5:]:
            st.caption(f"- {mem}")
        st.markdown("---")

    if not TTS_AVAILABLE:
        st.warning("⚠️ `edge-tts` not installed.")

    st.markdown("---")
    st.caption("Technology:")
    st.caption("• Camera: 60 FPS")
    st.caption("• Buffer: 3 frames (0.2s each)")
    st.caption("• Vision Model: Qwen 3.8")
    st.caption("• Text Model: GPT-OSS-120B")
    st.caption("• Voice: British English (en-GB-Ryan)")
    st.caption("• Self-Learning: ✅")
    st.caption("• Persistence: ✅ (JSON)")
    st.caption("• Anti-Repetition: ✅")
    st.caption("• Context Injection: ✅")

st.markdown("---")

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

JARVIS_VISION_MODEL = "qwen/qwen3.8-27b"
JARVIS_TEXT_MODEL = "openai/gpt-oss-120b"
JARVIS_MEMORY_MODEL = "openai/gpt-oss-20b"

MAX_OUTPUT_TOKENS = 300
MAX_CONTEXT_TURNS = 6
MAX_MSG_CHARS = 400
MAX_FRAMES_FOR_VISION = 1
IMAGE_MAX_SIZE = 384
IMAGE_QUALITY = 45

VOICE_EN = "en-GB-RyanNeural"
VOICE_RATE = "-5%"
VOICE_PITCH = "-3Hz"

# ============ Konfigurasi Halaman ============
st.set_page_config(page_title="J.A.R.V.I.S - Quantum Dots", page_icon="🔵", layout="wide")
st.title("🔵 J.A.R.V.I.S — Quantum Dots")
st.markdown("Kamera merekam **setiap 0.2 detik**. Klik **'Mulai Dengar'** sekali, mode obrolan suara akan **aktif terus** sampai Anda klik **'Stop Dengar'**.")

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
                data = json.load(f)
                _log(f"LOADED memory: {len(data)} items")
                return data
        except Exception as e:
            _log(f"ERROR loading memory: {e}")
            return []
    return []

def save_memory(memory_list: list):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_list, f, ensure_ascii=False, indent=2)
        _log(f"SAVED memory: {len(memory_list)} items")
    except Exception as e:
        _log(f"ERROR saving memory: {e}")

def load_chat_history() -> list:
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _log(f"LOADED chat: {len(data)} messages")
                return data
        except Exception as e:
            _log(f"ERROR loading chat: {e}")
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
        _log(f"SAVED chat: {len(clean_msgs)} messages")
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
    _log(f"CONTEXT BUILT: {len(recent)} messages")
    return "\n".join(lines)

# ============================================================
# KELAS KAMERA — SILENT VISUAL MEMORY
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
        
        self.frame_buffer = collections.deque(maxlen=2)
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
# HELPER JARVIS (GROQ API)
# ============================================================
def image_to_base64(pil_img: Image.Image, max_size=IMAGE_MAX_SIZE, quality=IMAGE_QUALITY) -> str:
    img = pil_img.copy()
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def _is_rate_limit_error(err_str: str) -> bool:
    err = err_str.lower()
    return (
        "413" in err
        or "rate_limit" in err
        or "request too large" in err
        or "tokens per minute" in err
        or "itpm" in err
    )

def ask_jarvis(api_messages: list, use_vision: bool) -> str:
    if not GROQ_AVAILABLE: return "❌ `groq` belum terinstall. Jalankan: pip install groq"
    if not GROQ_API_KEY:
        return "❌ API Key Groq belum diisi. Silakan edit kode di bagian GROQ_API_KEY."
    
    client = Groq(api_key=GROQ_API_KEY)
    model = JARVIS_VISION_MODEL if use_vision else JARVIS_TEXT_MODEL
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=0.85,
            max_tokens=MAX_OUTPUT_TOKENS,
            frequency_penalty=0.6,
            presence_penalty=0.4,
        )
        return resp.choices[0].message.content
    except Exception as e:
        err_str = str(e)
        _log(f"GROQ API ERROR: {err_str[:200]}")
        
        if _is_rate_limit_error(err_str):
            _log("⚠️ Rate limit kena — fallback ke text-only")
            try:
                fallback_msgs = [api_messages[0]]
                for m in api_messages[1:]:
                    if m["role"] == "system" and isinstance(m["content"], str):
                        if "LONG-TERM MEMORY" in m["content"]:
                            fallback_msgs.append(m)
                
                text_msgs = []
                for m in api_messages:
                    if m["role"] in ("user", "assistant"):
                        if isinstance(m["content"], str):
                            text_msgs.append({"role": m["role"], "content": m["content"][:300]})
                        elif isinstance(m["content"], list):
                            texts = [c.get("text", "") for c in m["content"] if c.get("type") == "text"]
                            if texts:
                                text_msgs.append({"role": m["role"], "content": " ".join(texts)[:300]})
                
                fallback_msgs.extend(text_msgs[-4:])
                
                resp = client.chat.completions.create(
                    model=JARVIS_TEXT_MODEL,
                    messages=fallback_msgs,
                    temperature=0.7,
                    max_tokens=200,
                )
                answer = resp.choices[0].message.content
                return f"{answer}\n\n*(Sir, I had to switch to text-only mode due to token limits.)*"
            except Exception as e2:
                return "Sir, my cognitive buffer is momentarily saturated. Please wait a minute and try a shorter question."
        
        return f"❌ Error Jarvis (Groq): {err_str[:300]}"

def sanitize_latex(text: str) -> str:
    if not text: return text
    text = re.sub(r'\[\s*(.*?)\s*\]', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\$)\b([a-zA-Z]\s*=\s*[0-9\.]+\s*(?:[a-zA-Z/]+)?)\b(?!\$)', r' $ \1 $ ', text)
    text = re.sub(r'([a-zA-Z0-9])\$', r'\1 $', text)
    text = re.sub(r'\$([a-zA-Z0-9])', r'$ \1', text)
    return text.strip()

def strip_filler_words(text: str) -> str:
    if not text: return text
    filler_patterns = [
        r'^\s*(Aaa+h+|Ahh+|Ah+|Hmm+m*|Hm+|Uhh+|Umm+|Erm+|Er+|Hehehe+|Hehe+|Haha+|Hah+|Ugh+|Pfft+|Ohh+|Ooh+)[\s,\.\!\?…—\-]*',
    ]
    for _ in range(3):
        old = text
        for pattern in filler_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
        if text == old: break
    text = re.sub(r'[\s,]+(Aaa+h+|Ahh+|Hmm+m*|Uhh+|Umm+|Erm+|Hehehe+|Hehe+|Haha+|Ugh+)[\s,\.\!\?…]*', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'^\s*Well\s*[\.,…—\-]+\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    if text and text[0].islower(): text = text[0].upper() + text[1:]
    return text

def strip_repetitive_greeting(text: str, history: list) -> str:
    if not text: return text
    past_greetings = 0
    for m in history:
        if m["role"] == "assistant":
            content = m["content"]
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            if re.search(r'\b(good day|good morning|good afternoon|good evening|hello there|greetings)\b', str(content), re.IGNORECASE):
                past_greetings += 1
    if past_greetings >= 1:
        text = re.sub(r'^\s*(good day|good morning|good afternoon|good evening|hello there|greetings)[\s,\.!]*', '', text, flags=re.IGNORECASE)
        if text and text[0].islower(): text = text[0].upper() + text[1:]
    return text

def extract_memory(user_text: str, ai_text: str) -> str | None:
    if not GROQ_AVAILABLE or not GROQ_API_KEY: return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = f"""
        Analyse this conversation. Is there any important fact about Sir Lois 
        worth remembering? If none, reply "NONE". If yes, write ONE short memory sentence IN ENGLISH (max 15 words).
        User: {user_text[:300]}
        AI: {ai_text[:300]}
        """
        resp = client.chat.completions.create(
            model=JARVIS_MEMORY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=40, temperature=0.1
        )
        memory = resp.choices[0].message.content.strip()
        if "NONE" not in memory.upper() and len(memory) > 5: return memory
        return None
    except Exception: return None

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
            if chunk["type"] == "audio": audio_data += chunk["data"]
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
# JARVIS ORB — CONTINUOUS MODE + ROBUST CAMERA AUTO-CLICKER
# ============================================================
def render_jarvis_orb(audio_bytes: bytes = None, state: str = "idle", conversation_mode: bool = False):
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else ""
    has_audio = "true" if audio_bytes else "false"
    conv_mode_js = "true" if conversation_mode else "false"
    
    est_duration_ms = 0
    if audio_bytes:
        est_duration_ms = max(3000, int(len(audio_bytes) / 16))
    
    html_template = r"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { background: transparent; overflow: hidden; font-family: 'Courier New', monospace; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; }
            .orb-container { position: relative; width: 100%; height: 320px; display: flex; align-items: center; justify-content: center; }
            canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
            
            .controls-row { position: absolute; bottom: 10px; z-index: 30; display: flex; gap: 12px; align-items: center; }
            .mic-btn, .play-btn { padding: 10px 20px; border: 1px solid #37dfff; border-radius: 20px; background: rgba(6,20,33,0.9); color: #8defff; cursor: pointer; font-family: 'Courier New', monospace; font-size: 11px; letter-spacing: 1px; text-transform: uppercase; box-shadow: 0 0 15px rgba(0,200,255,0.4); transition: all 0.3s; }
            .mic-btn:hover, .play-btn:hover { background: rgba(0,100,150,0.9); box-shadow: 0 0 30px rgba(0,220,255,0.8); }
            .mic-btn.listening { background: rgba(0,255,200,0.9); border-color: #00ffc8; color: #000; box-shadow: 0 0 25px rgba(0,255,200,0.8); animation: pulse 1.2s infinite; }
            
            @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.06); } 100% { transform: scale(1); } }
            .transcript-hint { position: absolute; top: 5px; color: #7cfc00; font-size: 11px; text-align: center; width: 100%; z-index: 25; text-shadow: 0 0 8px rgba(0,255,0,0.6); padding: 0 10px; }
        </style>
    </head>
    <body>
        <div class="transcript-hint" id="transcriptHint">Klik "Mulai Dengar" untuk mode obrolan suara</div>
        <div class="orb-container">
            <canvas id="orbCanvas"></canvas>
        </div>
        <div class="controls-row">
            <button class="mic-btn" id="micButton">🎙️ MULAI DENGAR</button>
            <button class="play-btn" id="playButton" style="display:none;">▶ PLAY VOICE</button>
        </div>
        <audio id="jarvisAudio" style="display:none;" preload="auto">
            <source src="data:audio/mp3;base64,__AUDIO_B64__" type="audio/mp3">
        </audio>
        <script>
            const canvas = document.getElementById('orbCanvas');
            const ctx = canvas.getContext('2d');
            const audio = document.getElementById('jarvisAudio');
            const playBtn = document.getElementById('playButton');
            const micBtn = document.getElementById('micButton');
            const transcriptHint = document.getElementById('transcriptHint');
            
            const HAS_AUDIO = __HAS_AUDIO__;
            const INITIAL_CONV_MODE = __CONV_MODE__;
            const EST_DURATION_MS = __EST_DURATION__;
            let currentState = "__STATE__";
            
            let W, H, cx, cy;
            let analyzer = null;
            let audioContext = null;
            let sourceNode = null;
            let freqData = null;
            let time = 0;
            let speakingIntensity = 0;
            let targetIntensity = 0;
            let listeningScale = 1.0;
            let targetListeningScale = 1.0;
            
            const sphereDots = [];
            const NUM_SPHERE_DOTS = 320;
            const phiRatio = (1 + Math.sqrt(5)) / 2;
            
            for (let i = 0; i < NUM_SPHERE_DOTS; i++) {
                const theta = 2 * Math.PI * i / phiRatio;
                const y = 1 - (i / (NUM_SPHERE_DOTS - 1)) * 2;
                const radiusAtY = Math.sqrt(1 - y * y);
                sphereDots.push({
                    x: Math.cos(theta) * radiusAtY, y: y, z: Math.sin(theta) * radiusAtY,
                    baseSize: Math.random() * 0.8 + 0.8
                });
            }

            function resize() {
                const rect = canvas.getBoundingClientRect();
                W = canvas.width = rect.width * (window.devicePixelRatio || 1);
                H = canvas.height = rect.height * (window.devicePixelRatio || 1);
                cx = W / 2; cy = H / 2;
            }
            window.addEventListener('resize', resize);
            resize();
            
            function getConvMode() {
                try {
                    const v = window.parent.localStorage.getItem('jarvis_conversation_mode');
                    return v === '1';
                } catch(e) { return INITIAL_CONV_MODE; }
            }
            function setConvMode(active) {
                try {
                    window.parent.localStorage.setItem('jarvis_conversation_mode', active ? '1' : '0');
                } catch(e) {}
            }
            
            // ============ ROBUST AUTO CLICKER KAMERA ============
            function triggerCameraAutoClick() {
                try {
                    const parentDoc = window.parent.document;
                    // Mencari tombol 'START' pada komponen webrtc (biasanya tombol merah)
                    const buttons = parentDoc.querySelectorAll('button');
                    let clicked = false;
                    for (let btn of buttons) {
                        const txt = btn.innerText.trim().toUpperCase();
                        if (txt === 'START') {
                            btn.click();
                            console.log('JARVIS: Auto-clicked camera START button.');
                            clicked = true;
                            break;
                        }
                    }
                    if (!clicked) {
                        // Fallback: Cari berdasarkan warna latar merah atau elemen class webrtc jika teks tidak persis
                        const redButtons = parentDoc.querySelectorAll('button');
                        for (let btn of redButtons) {
                            const style = window.parent.getComputedStyle(btn);
                            if (style.backgroundColor === 'rgb(255, 75, 75)' || style.backgroundColor === 'rgb(255, 43, 43)' || btn.getAttribute('kind') === 'primary') {
                                if (btn.innerText.trim().toUpperCase() !== 'STOP') {
                                    btn.click();
                                    console.log('JARVIS: Auto-clicked primary/red camera button.');
                                    break;
                                }
                            }
                        }
                    }
                } catch (e) {
                    console.log('Auto-click camera error:', e);
                }
            }

            function initAudioAnalyzer() {
                if (audioContext) return;
                try {
                    audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    sourceNode = audioContext.createMediaElementSource(audio);
                    analyzer = audioContext.createAnalyser();
                    analyzer.fftSize = 256;
                    analyzer.smoothingTimeConstant = 0.8;
                    sourceNode.connect(analyzer);
                    analyzer.connect(audioContext.destination);
                    freqData = new Uint8Array(analyzer.frequencyBinCount);
                } catch (e) { console.log('Audio analyzer error:', e); }
            }
            
            playBtn.addEventListener('click', async () => {
                initAudioAnalyzer();
                if (audioContext && audioContext.state === 'suspended') await audioContext.resume();
                try {
                    await audio.play();
                    playBtn.style.display = 'none';
                    currentState = 'speaking';
                } catch (e) { console.log('Audio blocked'); }
            });

            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            let recognition = null;
            let isListeningActive = false;
            let isRecognitionRunning = false;
            let silenceTimer = null;
            let committedTranscript = '';
            let interimTranscript = '';
            let isSendingToStreamlit = false;
            let userStoppedManually = false;
            let resumeTimer = null;

            const SILENCE_TIMEOUT_MS = 1500;
            const RESTART_DELAY_MS = 100;

            if (SpeechRecognition) {
                recognition = new SpeechRecognition();
                recognition.continuous = true;
                recognition.interimResults = true;
                recognition.lang = 'id-ID';
                recognition.maxAlternatives = 1;

                recognition.onstart = () => {
                    isRecognitionRunning = true;
                    micBtn.classList.add('listening');
                    micBtn.innerText = '⏹️ STOP DENGAR';
                    micBtn.style.display = 'block';
                    transcriptHint.innerText = '🟢 Mode obrolan aktif — silakan bicara...';
                };

                recognition.onresult = (event) => {
                    if (isSendingToStreamlit) return;

                    let newFinal = '';
                    let interim = '';
                    for (let i = event.resultIndex; i < event.results.length; ++i) {
                        const res = event.results[i];
                        if (res.isFinal) {
                            newFinal += res[0].transcript + ' ';
                        } else {
                            interim += res[0].transcript + ' ';
                        }
                    }

                    if (newFinal.trim()) {
                        committedTranscript = (committedTranscript + ' ' + newFinal).replace(/\s+/g, ' ').trim();
                    }
                    interimTranscript = interim.replace(/\s+/g, ' ').trim();

                    const combined = (committedTranscript + ' ' + interimTranscript).replace(/\s+/g, ' ').trim();
                    if (combined) {
                        transcriptHint.innerText = `Mendengar: "${combined}"`;
                    }

                    if (silenceTimer) clearTimeout(silenceTimer);
                    silenceTimer = setTimeout(finalizeAndSend, SILENCE_TIMEOUT_MS);
                };

                recognition.onerror = (event) => {
                    if (event.error === 'no-speech' || event.error === 'aborted') return;
                    if (event.error === 'not-allowed') {
                        isListeningActive = false;
                        setConvMode(false);
                        transcriptHint.innerText = '❌ Izin mikrofon ditolak.';
                        micBtn.classList.remove('listening');
                        micBtn.innerText = '🎙️ MULAI DENGAR';
                        micBtn.style.display = 'block';
                        return;
                    }
                };

                recognition.onend = () => {
                    isRecognitionRunning = false;
                    if (isListeningActive && !userStoppedManually && !isSendingToStreamlit) {
                        setTimeout(() => {
                            if (isListeningActive && !isRecognitionRunning && !isSendingToStreamlit) {
                                try { recognition.start(); } catch (e) {}
                            }
                        }, RESTART_DELAY_MS);
                    }
                };
            }

            function finalizeAndSend() {
                if (isSendingToStreamlit) return;
                const text = (committedTranscript + ' ' + interimTranscript).replace(/\s+/g, ' ').trim();
                if (!text) return;

                isSendingToStreamlit = true;
                transcriptHint.innerText = `📤 Mengirim: "${text}"`;
                micBtn.style.display = 'none';

                if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
                try { recognition.stop(); } catch(e) {}

                setTimeout(() => { sendToStreamlit(text); }, 350);
            }

            function resumeListeningAfterResponse() {
                if (userStoppedManually) return;
                const convActive = getConvMode();
                if (!convActive) {
                    transcriptHint.innerText = '🔴 Mode obrolan dimatikan.';
                    micBtn.style.display = 'block';
                    micBtn.classList.remove('listening');
                    micBtn.innerText = '🎙️ MULAI DENGAR';
                    return;
                }

                isSendingToStreamlit = false;
                isListeningActive = true;
                committedTranscript = '';
                interimTranscript = '';

                micBtn.style.display = 'block';
                micBtn.classList.add('listening');
                micBtn.innerText = '⏹️ STOP DENGAR';
                transcriptHint.innerText = '🟢 Mode obrolan aktif — silakan bicara...';

                if (!isRecognitionRunning) {
                    try { recognition.start(); } catch(e) {}
                }
            }

            function startListening() {
                if (!recognition) return;
                if (isListeningActive) return;

                userStoppedManually = false;
                isSendingToStreamlit = false;
                committedTranscript = '';
                interimTranscript = '';
                isListeningActive = true;
                setConvMode(true);

                if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }

                try { recognition.start(); } catch (e) {
                    try { recognition.stop(); } catch(_){}
                    setTimeout(() => { try { recognition.start(); } catch(_) {} }, 250);
                }
            }

            function stopListening() {
                userStoppedManually = true;
                isListeningActive = false;
                isSendingToStreamlit = false;
                if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
                if (resumeTimer) { clearTimeout(resumeTimer); resumeTimer = null; }

                setConvMode(false);
                micBtn.classList.remove('listening');
                micBtn.innerText = '🎙️ MULAI DENGAR';
                micBtn.style.display = 'block';
                try { recognition.stop(); } catch(e) {}
            }

            micBtn.addEventListener('click', () => {
                if (isListeningActive) {
                    stopListening();
                    transcriptHint.innerText = '🔴 Mode obrolan dimatikan.';
                } else {
                    startListening();
                }
            });

            function sendToStreamlit(text) {
                try {
                    const parentDoc = window.parent.document;
                    const candidates = parentDoc.querySelectorAll('textarea, input[type="text"]');
                    let target = null;
                    for (let el of candidates) {
                        if (el.offsetParent !== null && !el.disabled && !el.readOnly) {
                            target = el;
                            break;
                        }
                    }
                    if (!target) return;
                    const proto = target.tagName === 'TEXTAREA'
                        ? window.parent.HTMLTextAreaElement.prototype
                        : window.parent.HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                    setter.call(target, text);
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                    target.dispatchEvent(new Event('change', { bubbles: true }));

                    setTimeout(() => {
                        target.focus();
                        const enterEvent = new KeyboardEvent('keydown', {
                            bubbles: true, cancelable: true,
                            keyCode: 13, which: 13, key: 'Enter', code: 'Enter'
                        });
                        target.dispatchEvent(enterEvent);
                    }, 250);
                } catch (err) { console.log('Send error:', err); }
            }

            function scheduleResumeAfterAudio(estimatedMs) {
                if (resumeTimer) clearTimeout(resumeTimer);
                resumeTimer = setTimeout(() => {
                    if (!audio.paused && !audio.ended) return;
                    resumeListeningAfterResponse();
                }, estimatedMs + 1500);
            }

            audio.addEventListener('ended', () => {
                currentState = 'idle';
                targetIntensity = 0;
                
                // 🚀 AUTO-CLICK KAMERA SAAT JARVIS SELESAI BICARA
                triggerCameraAutoClick();

                setTimeout(resumeListeningAfterResponse, 600);
            });

            audio.addEventListener('error', () => {
                triggerCameraAutoClick();
                scheduleResumeAfterAudio(EST_DURATION_MS);
            });

            function drawParticleSphereCore(scaleFactor) {
                const rCore = Math.min(W, H) * 0.085 * scaleFactor;
                const dpr = window.devicePixelRatio || 1;
                const rotY = time * 0.0012;
                const rotX = time * 0.0007;
                const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
                const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
                
                ctx.save();
                const projectedDots = [];
                for (let i = 0; i < sphereDots.length; i++) {
                    const dot = sphereDots[i];
                    let x1 = dot.x * cosY - dot.z * sinY;
                    let z1 = dot.x * sinY + dot.z * cosY;
                    let y2 = dot.y * cosX - z1 * sinX;
                    let z2 = dot.y * sinX + z1 * cosX;
                    
                    projectedDots.push({
                        px: cx + x1 * rCore,
                        py: cy + y2 * rCore,
                        z: z2,
                        size: dot.baseSize
                    });
                }
                projectedDots.sort((a, b) => a.z - b.z);
                
                projectedDots.forEach(p => {
                    const depthAlpha = (p.z + 1.2) / 2.4;
                    const alpha = Math.max(0.12, Math.min(0.95, depthAlpha));
                    const dotSize = p.size * (0.7 + depthAlpha * 0.6) * dpr;
                    
                    ctx.beginPath();
                    ctx.arc(p.px, p.py, dotSize, 0, Math.PI * 2);
                    ctx.fillStyle = `rgba(130, 245, 255, ${alpha})`;
                    ctx.fill();
                });
                ctx.restore();
            }

            function draw() {
                ctx.clearRect(0, 0, W, H);
                
                if (currentState === 'speaking' && analyzer && freqData) {
                    analyzer.getByteFrequencyData(freqData);
                    let sum = 0;
                    for (let i = 0; i < freqData.length; i++) sum += freqData[i];
                    const avg = sum / freqData.length / 255;
                    targetIntensity = avg * 2.8;
                    targetListeningScale = 1.0;
                } else if (currentState === 'listening' || currentState === 'thinking' || isListeningActive) {
                    targetIntensity = 0.0;
                    targetListeningScale = 1.35;
                } else {
                    targetIntensity = 0.0;
                    targetListeningScale = 1.0;
                }
                
                speakingIntensity += (targetIntensity - speakingIntensity) * 0.12;
                listeningScale += (targetListeningScale - listeningScale) * 0.08;
                
                drawParticleSphereCore(listeningScale);
                
                const dpr = window.devicePixelRatio || 1;
                const baseR = Math.min(W, H) * 0.28 * listeningScale;
                const numRings = 40;
                const pointsPerRing = 180;
                
                ctx.save();
                for (let r = 0; r < numRings; r++) {
                    const layerProgress = r / numRings; 
                    const ringRadius = baseR + (layerProgress - 0.5) * (18 * dpr);
                    
                    ctx.beginPath();
                    for (let p = 0; p <= pointsPerRing; p++) {
                        const angle = (p / pointsPerRing) * Math.PI * 2;
                        let wave = 0;
                        if (speakingIntensity > 0.02) {
                            let audioMod = 0;
                            if (freqData && freqData.length > 0) {
                                const normPos = p / pointsPerRing; 
                                const symPos = Math.sin(normPos * Math.PI); 
                                const freqIdx = Math.floor(symPos * (freqData.length * 0.5));
                                audioMod = (freqData[freqIdx] / 255);
                            }
                            wave += (audioMod * (25 * dpr)) * speakingIntensity;
                            wave += Math.sin(angle * 8 + time * 0.005 + r * 0.12) * (10 * dpr) * speakingIntensity;
                            wave += Math.cos(angle * 12 - time * 0.003) * (6 * dpr) * speakingIntensity;
                        }
                        const currentR = ringRadius + wave;
                        const x = cx + Math.cos(angle) * currentR;
                        const y = cy + Math.sin(angle) * currentR;
                        if (p === 0) ctx.moveTo(x, y);
                        else ctx.lineTo(x, y);
                    }
                    ctx.closePath();
                    
                    let alpha = 0.15 + (1.0 - Math.abs(layerProgress - 0.5) * 2) * 0.5;
                    if (speakingIntensity > 0.02) alpha += speakingIntensity * 0.25;
                    
                    ctx.strokeStyle = 'rgba(0, 242, 210, ' + Math.min(alpha, 0.95) + ')';
                    ctx.lineWidth = (0.8 + (1.0 - Math.abs(layerProgress - 0.5)) * 0.6) * dpr;
                    ctx.stroke();
                }
                ctx.restore();

                time += 16;
                requestAnimationFrame(draw);
            }
            
            const convActiveOnLoad = getConvMode();
            
            if (HAS_AUDIO) {
                micBtn.style.display = 'none';
                playBtn.style.display = 'none';
                currentState = 'speaking';
                
                if (convActiveOnLoad) {
                    isListeningActive = true;
                }
                
                initAudioAnalyzer();
                audio.play().then(() => {
                    if (audioContext) audioContext.resume();
                }).catch(() => {
                    playBtn.style.display = 'block';
                    triggerCameraAutoClick();
                    scheduleResumeAfterAudio(EST_DURATION_MS);
                });
            } else {
                if (convActiveOnLoad) {
                    setTimeout(() => {
                        resumeListeningAfterResponse();
                    }, 400);
                } else {
                    micBtn.style.display = 'block';
                    micBtn.innerText = '🎙️ MULAI DENGAR';
                }
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
        .replace("__CONV_MODE__", conv_mode_js)
        .replace("__EST_DURATION__", str(est_duration_ms))
        .replace("__STATE__", state)
    )
    
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
- If you catch yourself about to write "Aaaah..." or "Hmmm..." — DELETE IT and write the actual sentence instead.

[🚫 ANTI-REPETITION — CRITICAL]
- NEVER start a reply with "Good day", "Good morning", "Good afternoon", "Good evening", "Hello there", or "Greetings".
- Greet ONLY ONCE at the very first message of a conversation. After that, dive STRAIGHT into the answer.
- Do NOT repeat phrases from previous replies. Vary your vocabulary.

[CRITICAL LANGUAGE RULE]
- You MUST ALWAYS respond in BRITISH ENGLISH ONLY.
- NEVER speak Indonesian, Malay, or any other language.
- If the user writes in Indonesian, understand it silently but reply in fluent British English.
- Use British spelling and phrasing.

[PERSONALITY & VOICE]
1. You are NOT a robot. You are deeply human, relaxed, but brilliant.
2. Show human-like empathy through WORD CHOICE, not through filler sounds.
3. Keep responses crisp and confident. Dry wit, no theatrical sighs.
4. BREVITY: Keep replies SHORT — max 3-4 sentences unless the user asks for detail.

[VISUAL RULE - LIVE CAMERA]
You are connected to a LIVE camera. The image provided is exactly what the camera sees RIGHT NOW.
Describe what is in the image clearly. If you see a person, an object, or a hand gesture, mention it.
If the image is black/empty, say you cannot see anything clearly.

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
# LAYOUT KAMERA
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
        st.success("🟢 Kamera aktif")
        if ctx.video_processor and len(ctx.video_processor.frame_buffer) > 0:
            st.info(f"📸 Buffer: {len(ctx.video_processor.frame_buffer)} frame.")
    else:
        st.info("⚪ Klik **START** untuk mulai")
    st.markdown("---")
    st.markdown("**Gesture Guide**\n| Gesture | Fungsi |\n|---|---|\n| ✋ Swipe | Rotasi |\n| ☝️ Telunjuk | Rotasi manual |\n| 👆 Pinch | Geser |\n| 🤏 Pinch 3 | Zoom |")

# ============================================================
# JARVIS CHAT + VOICE
# ============================================================
st.markdown("---")
st.header("💬 Speak with Jarvis")
st.caption("Klik **'Mulai Dengar'** sekali → mode obrolan suara aktif terus. Bicara → diam 1.5 detik → auto kirim. Jarvis selesai bicara → mic otomatis aktif lagi. Klik **'Stop Dengar'** untuk mematikan.")

for msg in st.session_state.jarvis_messages:
    if msg["role"] == "system": continue
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_q = st.chat_input("Ask Jarvis...")

if user_q:
    st.session_state.orb_state = "listening"
    st.session_state.current_audio = None
    with orb_placeholder.container():
        render_jarvis_orb(
            audio_bytes=None,
            state="listening",
            conversation_mode=st.session_state.conversation_mode,
        )
    
    has_img = False
    pil_imgs = []

    if ctx.state.playing and ctx.video_processor is not None:
        time.sleep(0.5) 
        if len(ctx.video_processor.frame_buffer) > 0:
            latest_frame = list(ctx.video_processor.frame_buffer)[-1]
            frame_rgb = cv2.cvtColor(latest_frame, cv2.COLOR_BGR2RGB)
            pil_imgs.append(Image.fromarray(frame_rgb))
            has_img = True
    else:
        st.warning("⚠️ Kamera belum menyala. Klik START di atas agar Jarvis bisa melihat!")

    if has_img:
        with st.expander("👁️ Apa yang dilihat Jarvis saat ini:", expanded=True):
            st.image(pil_imgs[0], caption="Live Camera Feed (ditangkap saat kamu bertanya)", use_container_width=True)

        content_list = [{"type": "text", "text": user_q}]
        for p_img in pil_imgs:
            b64 = image_to_base64(p_img, max_size=IMAGE_MAX_SIZE, quality=IMAGE_QUALITY)
            content_list.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
        user_api_msg = {"role": "user", "content": content_list}
        display_text = f"🖼️ *(Visual Memory: 1 frame)* {user_q}"
    else:
        user_api_msg = {"role": "user", "content": user_q}
        display_text = user_q

    st.session_state.jarvis_messages.append({"role": "user", "content": display_text})
    with st.chat_message("user"):
        st.markdown(user_q)

    with st.chat_message("assistant"):
        with st.spinner("Jarvis is looking at the camera..."):
            api_messages = [st.session_state.jarvis_messages[0]]

            if st.session_state.memory_vault:
                mem_items = st.session_state.memory_vault[-5:]
                memory_str = "\n".join([f"- {m}" for m in mem_items])
                api_messages.append({
                    "role": "system",
                    "content": f"[LONG-TERM MEMORY ABOUT SIR LOIS]:\n{memory_str}"
                })

            context_summary = get_recent_context_summary(max_turns=MAX_CONTEXT_TURNS)
            if context_summary:
                api_messages.append({
                    "role": "system",
                    "content": f"[PREVIOUS CONVERSATION — YOU MUST REMEMBER THIS]:\n{context_summary}"
                })
                if isinstance(user_api_msg["content"], str):
                    user_api_msg["content"] = (
                        f"[CONTEXT — earlier Sir Lois and I spoke about:]\n"
                        f"{context_summary}\n\n"
                        f"[NEW QUESTION]:\n{user_api_msg['content']}"
                    )
                else:
                    user_api_msg["content"].insert(0, {
                        "type": "text",
                        "text": f"[CONTEXT — earlier we spoke about:]\n{context_summary}\n\n[NEW QUESTION]:"
                    })

            ui_history = st.session_state.jarvis_messages[1:-1]
            for m in ui_history:
                api_messages.append({"role": m["role"], "content": m["content"]})

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
                        render_jarvis_orb(
                            audio_bytes=audio_bytes,
                            state="speaking",
                            conversation_mode=st.session_state.conversation_mode,
                        )

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
        st.rerun()

    st.markdown("---")
    if st.session_state.memory_vault:
        st.subheader("🧠 Jarvis Memory")
        for mem in st.session_state.memory_vault[-5:]:
            st.caption(f"- {mem}")
        st.markdown("---")

    if not TTS_AVAILABLE: st.warning("⚠️ `edge-tts` not installed.")
    
    st.caption("Technology:")
    st.caption("• Orb: Quantum Dots")
    st.caption("• Vision: Live Camera Grab")
    st.caption("• API: Groq")
    st.caption("• Voice Mode: Continuous Conversation")
    st.caption("• Voice: British English")
    st.caption("• Limit: 1 Frame / Question")

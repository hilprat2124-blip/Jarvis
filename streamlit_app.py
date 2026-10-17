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
from PIL import Image

from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

# ============ AI: Groq (Jarvis) ============
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# ============ AI: Edge-TTS (Suara Natural) ============
try:
    import edge_tts
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Model Groq untuk mata & otak Jarvis
JARVIS_VISION_MODEL = "qwen/qwen3.8-27b"
JARVIS_TEXT_MODEL = "openai/gpt-oss-120b"

# Konfigurasi Suara Edge-TTS (Bahasa Indonesia)
JARVIS_TTS_VOICE = "id-ID-ArdiNeural"  # Pria Indonesia. Bisa ganti: "id-ID-GadisNeural" untuk Wanita

# ============ Konfigurasi Halaman ============
st.set_page_config(
    page_title="Hand Tracking + Jarvis (Voice)",
    page_icon="🧊",
    layout="wide"
)

st.title("🧊 3D Hand Tracking + 🤖 Jarvis (Live Eyes + Voice)")
st.markdown("""
**Fitur Spesial:** Jarvis punya **"Mata Live"** dan **"Suara Indonesia Natural"**. 
Ketik chat (misal: *"Apa yang kamu lihat?"*), Jarvis akan melihat kamera dan **menjawab dengan suara otomatis**.
""")

# ============ WebRTC & Konstanta ============
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}, {"urls": ["stun:stun1.l.google.com:19302"]}]}
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

# ============ Download Model ============
MODEL_PATH = "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

if not os.path.exists(MODEL_PATH):
    with st.spinner("📥 Mengunduh model AI..."):
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    st.success("✅ Model siap!")

# ============================================================
# 🔒 KELAS KAMERA — TIDAK DIUBAH SAMA SEKALI
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
        self.latest_frame_bgr = None

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

        self.latest_frame_bgr = img.copy()
        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def __del__(self):
        try: self.detector.close()
        except: pass

# ============================================================
# 🤖 HELPER JARVIS (Vision + Edge-TTS)
# ============================================================
def image_to_base64(pil_img: Image.Image, max_size=1024, quality=85) -> str:
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
            model=model, messages=api_messages, temperature=0.7, max_tokens=1024,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"❌ Error Jarvis: {str(e)}"

def generate_tts_edge(text: str) -> bytes or None:
    """Generate audio dari teks menggunakan Edge-TTS."""
    if not TTS_AVAILABLE: 
        return None
    
    async def _generate():
        communicate = edge_tts.Communicate(text, JARVIS_TTS_VOICE)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    try:
        # Jalankan asyncio event loop di dalam thread Streamlit
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(_generate())
        loop.close()
        return audio_bytes
    except Exception as e:
        st.error(f"Gagal generate suara Edge-TTS: {e}")
        return None

# ============================================================
# 🧠 SESSION STATE
# ============================================================
if "jarvis_messages" not in st.session_state:
    st.session_state.jarvis_messages = [
        {
            "role": "system",
            "content": "Kamu adalah Jarvis, asisten AI cerdas yang terintegrasi dengan kamera. Jawab dalam Bahasa Indonesia natural. Jika user bertanya tentang apa yang kamu lihat, jelaskan objek di gambar kamera dengan detail."
        }
    ]

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
    st.subheader("ℹ️ Status")
    if ctx.state.playing:
        st.success("🟢 Kamera aktif (Jarvis bisa melihat)")
    else:
        st.info("⚪ Klik **START** untuk mulai")
    st.markdown("---")
    st.markdown("**Gesture Guide**\n| Gesture | Fungsi |\n|---|---|\n| ✋ Swipe | Rotasi |\n| ☝️ Telunjuk | Rotasi manual |\n| 👆 Pinch | Geser |\n| 🤏 Pinch 3 | Zoom |")

# ============================================================
# 🤖 JARVIS CHAT + VOICE
# ============================================================
st.markdown("---")
st.header("💬 Ngobrol dengan Jarvis (dengan Suara)")

st.caption("Ketik pertanyaanmu. Jarvis akan melihat kamera dan **menjawab dengan suara otomatis**.")

for msg in st.session_state.jarvis_messages:
    if msg["role"] == "system": continue
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_q = st.chat_input("Tanya Jarvis...")

if user_q:
    has_img = False
    pil_img = None

    if ctx.state.playing and ctx.video_processor is not None and ctx.video_processor.latest_frame_bgr is not None:
        frame_bgr = ctx.video_processor.latest_frame_bgr.copy()
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        has_img = True

    if has_img:
        b64 = image_to_base64(pil_img)
        user_api_msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": user_q},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }
        display_text = f"🖼️ *(Live Kamera)* {user_q}"
    else:
        user_api_msg = {"role": "user", "content": user_q}
        display_text = user_q
        if ctx.state.playing:
            st.warning("⚠️ Kamera aktif tapi belum ada frame. Tunggu 1 detik lalu kirim lagi.")

    st.session_state.jarvis_messages.append({"role": "user", "content": display_text})
    with st.chat_message("user"):
        if has_img:
            st.image(pil_img, width=250, caption="Frame yang dikirim ke Jarvis")
        st.markdown(user_q)

    with st.chat_message("assistant"):
        with st.spinner("Jarvis sedang menganalisis gambar..."):
            api_messages = [st.session_state.jarvis_messages[0]]
            for m in st.session_state.jarvis_messages[1:-1]:
                api_messages.append({"role": m["role"], "content": m["content"]})
            api_messages.append(user_api_msg)

            answer = ask_jarvis(api_messages, use_vision=has_img)
            st.markdown(answer)

    st.session_state.jarvis_messages.append({"role": "assistant", "content": answer})

    # ===============================================
    # 🔥 PUTAR SUARA OTOMATIS DENGAN EDGE-TTS
    # ===============================================
    if answer and not answer.startswith("❌"):
        with st.spinner("Menyiapkan suara Jarvis..."):
            audio_bytes = generate_tts_edge(answer)
            
            if audio_bytes:
                b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                
                audio_html = f"""
                    <audio autoplay="true" style="display:none;">
                        <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
                    </audio>
                """
                st.markdown(audio_html, unsafe_allow_html=True)

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("ℹ️ Info")
    if st.button("🔄 Reset Chat Jarvis"):
        st.session_state.jarvis_messages = [
            {
                "role": "system",
                "content": "Kamu adalah Jarvis, asisten AI ramah. Jawab dalam Bahasa Indonesia."
            }
        ]
        st.rerun()

    st.markdown("---")
    if not GROQ_AVAILABLE: st.error("❌ `groq` belum terinstall.")
    elif not GROQ_API_KEY: st.warning("⚠️ GROQ_API_KEY belum diset.")
    else: st.success("✅ Jarvis siap!")

    if not TTS_AVAILABLE:
        st.warning("⚠️ `edge-tts` belum terinstall. Suara nonaktif.")
        st.code("pip install edge-tts")

    st.markdown("---")
    st.caption(f"Vision: `{JARVIS_VISION_MODEL}`")
    st.caption(f"TTS: `Edge-TTS` • Voice: `{JARVIS_TTS_VOICE}`")

st.markdown("---")
st.caption("💡 Jika suara tidak muncul, pastikan tab browser tidak di-mute dan kamu sudah berinteraksi dengan halaman.")

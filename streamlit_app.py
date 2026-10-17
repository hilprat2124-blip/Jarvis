import av
import cv2
import numpy as np
import streamlit as st
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import urllib.request
import os

from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

# ============ Konfigurasi Halaman ============
st.set_page_config(page_title="Hand Tracking Drawing", layout="wide")
st.title("✌️ Hand Tracking - Futuristic Drawing")
st.write("Lakukan *pinch* antara Jempol dengan jari lainnya untuk memunculkan garis neon. Lakukan *pinch* lagi untuk menghilangkannya.")

# ============ Konfigurasi WebRTC ============
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# ============ Konstanta ============
PINCH_THRESHOLD = 45      # Jarak (px) untuk mendeteksi pinch

THUMB_TIP = 4
FINGER_TIPS = {
    "Telunjuk":    (8,  (255, 255, 0)),   # Cyan Neon
    "Jari Tengah": (12, (0, 255, 255)),   # Kuning Neon
    "Jari Manis":  (16, (255, 0, 255)),   # Magenta Neon
    "Kelingking":  (20, (0, 255, 0)),     # Hijau Neon
}

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        
    (0, 5), (5, 6), (6, 7), (7, 8),        
    (5, 9), (9, 10), (10, 11), (11, 12),   
    (9, 13), (13, 14), (14, 15), (15, 16), 
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17)                                
]

# ============ Fungsi Download Model Otomatis ============
MODEL_PATH = "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

if not os.path.exists(MODEL_PATH):
    with st.spinner("Mengunduh model AI..."):
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)


class HandInteractionProcessor(VideoProcessorBase):
    def __init__(self):
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
            min_tracking_confidence=0.7
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        self.frame_timestamp = 0
        
        # State untuk logika toggle per jari
        # Menyimpan status boolean (True/False) untuk masing-masing jari
        self.is_drawing = {name: False for name in FINGER_TIPS}
        self.prev_pinching = {name: False for name in FINGER_TIPS}

    def _to_pixel(self, landmark, w, h):
        return int(landmark.x * w), int(landmark.y * h)

    def _draw_landmarks(self, img, landmarks, w, h):
        # Skeleton warna redup (abu-abu gelap)
        for connection in HAND_CONNECTIONS:
            start = self._to_pixel(landmarks[connection[0]], w, h)
            end = self._to_pixel(landmarks[connection[1]], w, h)
            cv2.line(img, start, end, (80, 80, 80), 1, cv2.LINE_AA)
        
        for lm in landmarks:
            px = self._to_pixel(lm, w, h)
            cv2.circle(img, px, 2, (120, 120, 120), -1, cv2.LINE_AA)

    def _draw_neon_line(self, img, pt1, pt2, color):
        # 1. Efek Glow (Garis tebal transparan)
        overlay = img.copy()
        cv2.line(overlay, pt1, pt2, color, 12, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
        
        # 2. Garis Utama (Tipis dan tajam)
        cv2.line(img, pt1, pt2, color, 2, cv2.LINE_AA)
        
        # 3. Titik Ujung (Lingkaran kecil putih)
        cv2.circle(img, pt1, 4, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(img, pt2, 4, (255, 255, 255), -1, cv2.LINE_AA)

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)  
        h, w, _ = img.shape

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        
        self.frame_timestamp += 1
        results = self.detector.detect_for_video(mp_image, self.frame_timestamp)

        if results.hand_landmarks:
            for hand_landmarks in results.hand_landmarks:
                self._draw_landmarks(img, hand_landmarks, w, h)

                thumb = self._to_pixel(hand_landmarks[THUMB_TIP], w, h)

                for name, (idx, color) in FINGER_TIPS.items():
                    tip = self._to_pixel(hand_landmarks[idx], w, h)

                    # Deteksi jarak jempol dan ujung jari terkait
                    dist = float(np.hypot(thumb[0] - tip[0], thumb[1] - tip[1]))
                    is_currently_pinching = dist < PINCH_THRESHOLD

                    # === LOGIKA TOGGLE PINCH (Per Jari) ===
                    if is_currently_pinching and not self.prev_pinching[name]:
                        # Jika jari melakukan pinch, ubah status gambar (Nyala -> Mati, Mati -> Nyala)
                        self.is_drawing[name] = not self.is_drawing[name]

                    self.prev_pinching[name] = is_currently_pinching

                    # Jika mode gambar untuk jari ini sedang AKTIF
                    if self.is_drawing[name]:
                        self._draw_neon_line(img, thumb, tip, color)
                        
                        # Teks kecil di tengah garis
                        mid = ((thumb[0] + tip[0]) // 2, (thumb[1] + tip[1]) // 2)
                        cv2.putText(img, "ON", (mid[0] - 10, mid[1] - 10), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)

                    # Indikator visual saat jari mendekat (pinch)
                    if is_currently_pinching:
                        mid = ((thumb[0] + tip[0]) // 2, (thumb[1] + tip[1]) // 2)
                        cv2.circle(img, mid, 15, (255, 255, 255), 2, cv2.LINE_AA)

        else:
            # Jika tangan hilang dari frame, reset state pinch
            for name in FINGER_TIPS:
                self.prev_pinching[name] = False

        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def __del__(self):
        try:
            self.detector.close()
        except:
            pass

# ============ Streamlit WebRTC ============
webrtc_streamer(
    key="hand-gesture-tracker",
    video_processor_factory=HandInteractionProcessor,
    rtc_configuration=RTC_CONFIGURATION,
    media_stream_constraints={"video": True, "audio": False},
    async_processing=True,
)

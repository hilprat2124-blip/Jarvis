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

from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

# ============ Konfigurasi Halaman ============
st.set_page_config(page_title="Interactive 3D Hand Tracking", layout="wide")
st.title("🧊 3D Free View - Hand Tracking")
st.write("""
**Panduan Gestur (Verifikasi Diperlukan):**
- ☝️ **Telunjuk Berdiri:** Tahan **1 Detik** untuk memutar objek (Rotasi).
- 👆 **Jempol + Telunjuk:** Tahan **1 Detik** -> Jauhkan **Telunjuk** untuk **ZOOM IN**.
- 🖕 **Jempol + Jari Tengah:** Tahan **1 Detik** -> Jauhkan **Jari Tengah** untuk **ZOOM OUT**.
- 🤏 **Pinch (Cubit):** Tahan **2 Detik** -> Geser tangan untuk **PAN (Geser)**.
""")

# ============ Konfigurasi WebRTC ============
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# ============ Konstanta ============
PINCH_THRESHOLD = 40      
HOLD_TIME_ZOOM_ROTATE = 1.0  # 1 detik untuk Zoom & Rotasi
HOLD_TIME_PAN = 2.0          # 2 detik untuk Pan (Geser)
MIN_SCALE, MAX_SCALE = 0.5, 3.0
ZOOM_SENSITIVITY = 0.01
MAX_ZOOM_STEP = 0.03

THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        
    (0, 5), (5, 6), (6, 7), (7, 8),        
    (5, 9), (9, 10), (10, 11), (11, 12),   
    (9, 13), (13, 14), (14, 15), (15, 16), 
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17)                                
]

# ============ Download Model ============
MODEL_PATH = "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

if not os.path.exists(MODEL_PATH):
    with st.spinner("Mengunduh model AI..."):
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)


class Hand3DProcessor(VideoProcessorBase):
    def __init__(self):
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.6
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        self.frame_timestamp = 0
        
        # State 3D
        self.rx, self.ry = 0.5, 0.5
        self.scale = 1.0
        self.offset_x, self.offset_y = 0, 0
        
        self.prev_index_pos = None
        self.prev_zoom_dist = None
        
        # State Verifikasi (Hold)
        self.active_mode = None    # "ZOOM_IN", "ZOOM_OUT", "PAN", "ROTASI"
        self.candidate_mode = None 
        self.hold_start_time = 0.0
        self.verified = False      

        # Vertex Kubus 3D
        self.vertices = np.array([
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], 
            [-1, -1,  1], [1, -1,  1], [1, 1,  1], [-1, 1,  1]  
        ], dtype=np.float32)

        self.edges = [
            (0,1), (1,2), (2,3), (3,0), 
            (4,5), (5,6), (6,7), (7,4), 
            (0,4), (1,5), (2,6), (3,7)  
        ]

    def _to_pixel(self, landmark, w, h):
        return int(landmark.x * w), int(landmark.y * h)

    def _draw_landmarks(self, img, landmarks, w, h):
        for connection in HAND_CONNECTIONS:
            start = self._to_pixel(landmarks[connection[0]], w, h)
            end = self._to_pixel(landmarks[connection[1]], w, h)
            cv2.line(img, start, end, (80, 80, 80), 1, cv2.LINE_AA)
        for lm in landmarks:
            px = self._to_pixel(lm, w, h)
            cv2.circle(img, px, 2, (120, 120, 120), -1, cv2.LINE_AA)

    def _draw_3d_cube(self, img, cx, cy):
        cos_x, sin_x = np.cos(self.rx), np.sin(self.rx)
        cos_y, sin_y = np.cos(self.ry), np.sin(self.ry)
        
        rot_x = np.array([[1, 0, 0], [0, cos_x, -sin_x], [0, sin_x, cos_x]])
        rot_y = np.array([[cos_y, 0, sin_y], [0, 1, 0], [-sin_y, 0, cos_y]])
        rot_matrix = np.dot(rot_y, rot_x)
        transformed = np.dot(self.vertices, rot_matrix.T)
        
        pts_2d = []
        fov = 4.0
        for v in transformed:
            v_scaled = v * self.scale
            z = v_scaled[2] + fov
            if z <= 0.1: z = 0.1
            
            px = int((v_scaled[0] / z) * 150) + cx + self.offset_x
            py = int((v_scaled[1] / z) * 150) + cy + self.offset_y
            pts_2d.append((px, py, v_scaled[2]))

        for edge in self.edges:
            p1, p2 = pts_2d[edge[0]], pts_2d[edge[1]]
            depth_avg = (p1[2] + p2[2]) / 2
            intensity = np.clip(1.0 - (depth_avg / 2.0), 0.2, 1.0)
            color = (int(255 * intensity), int(255 * intensity), 0)
            
            cv2.line(img, (p1[0], p1[1]), (p2[0], p2[1]), color, 6, cv2.LINE_AA)
            cv2.line(img, (p1[0], p1[1]), (p2[0], p2[1]), (255, 255, 255), 1, cv2.LINE_AA)

        for p in pts_2d:
            cv2.circle(img, (p[0], p[1]), 3, (0, 0, 255), -1, cv2.LINE_AA)

    def _draw_progress_ring(self, img, center, progress, color, radius=30):
        cv2.ellipse(img, center, (radius, radius), -90, 0, int(360 * min(progress, 1.0)), color, 4, cv2.LINE_AA)

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

        if results.hand_landmarks:
            hand_landmarks = results.hand_landmarks[0]
            self._draw_landmarks(img, hand_landmarks, w, h)

            thumb = self._to_pixel(hand_landmarks[THUMB_TIP], w, h)
            index = self._to_pixel(hand_landmarks[INDEX_TIP], w, h)
            middle = self._to_pixel(hand_landmarks[MIDDLE_TIP], w, h)

            dist_pinch_index = float(np.hypot(thumb[0] - index[0], thumb[1] - index[1]))
            dist_pinch_middle = float(np.hypot(thumb[0] - middle[0], thumb[1] - middle[1]))

            # ==========================================
            # DETEKSI KANDIDAT GESTUR
            # ==========================================
            detected_gesture = None
            
            # Cek Gestur Rotasi (Telunjuk berdiri, jari tengah menekuk)
            if index[1] < thumb[1] and middle[1] > thumb[1] and dist_pinch_index > PINCH_THRESHOLD:
                detected_gesture = "ROTASI"
            
            # Cek Gestur Pinch
            elif dist_pinch_index < PINCH_THRESHOLD:
                if dist_pinch_middle < PINCH_THRESHOLD:
                    detected_gesture = "ZOOM_IN"
                else:
                    detected_gesture = "PAN"
                    
            elif dist_pinch_middle < PINCH_THRESHOLD:
                detected_gesture = "ZOOM_OUT"

            # ==========================================
            # LOGIKA VERIFIKASI (1 atau 2 DETIK)
            # ==========================================
            
            if self.active_mode is None:
                if detected_gesture:
                    if self.candidate_mode != detected_gesture:
                        self.candidate_mode = detected_gesture
                        self.hold_start_time = current_time
                        self.verified = False
                    
                    # Tentukan waktu tunggu berdasarkan gestur
                    required_time = HOLD_TIME_PAN if detected_gesture == "PAN" else HOLD_TIME_ZOOM_ROTATE
                    progress = (current_time - self.hold_start_time) / required_time
                    
                    if progress >= 1.0:
                        self.active_mode = detected_gesture
                        self.verified = True
                        self.prev_zoom_dist = None 
                        self.prev_index_pos = None 
                    else:
                        mid_pinch = ((thumb[0] + index[0]) // 2, (thumb[1] + index[1]) // 2)
                        # Warna ring beda: Merah untuk Pan (2s), Kuning untuk lainnya (1s)
                        ring_color = (0, 0, 255) if detected_gesture == "PAN" else (0, 255, 255)
                        self._draw_progress_ring(img, mid_pinch, progress, ring_color, radius=35 if detected_gesture=="PAN" else 25)
                        
                        mode_text = f"VERIFIKASI: {detected_gesture} ({required_time}s)"
                        color_text = ring_color
                else:
                    self.candidate_mode = None
                    self.hold_start_time = 0.0

            # ==========================================
            # EKSEKUSI MODE YANG SUDAH TERVERIFIKASI
            # ==========================================
            if self.active_mode == "ROTASI":
                mode_text = "MODE: ROTASI (Aktif)"
                color_text = (0, 255, 0)
                
                if self.prev_index_pos is not None:
                    dx = np.clip(index[0] - self.prev_index_pos[0], -20, 20)
                    dy = np.clip(index[1] - self.prev_index_pos[1], -20, 20)
                    self.ry += dx * 0.015
                    self.rx += dy * 0.015
                self.prev_index_pos = index
                
                if detected_gesture != "ROTASI":
                    self.active_mode = None

            elif self.active_mode in ["ZOOM_IN", "ZOOM_OUT"]:
                mode_text = f"MODE: {self.active_mode} (Aktif)"
                color_text = (255, 165, 0)
                
                dist_to_track = dist_pinch_index if self.active_mode == "ZOOM_IN" else dist_pinch_middle
                
                if self.prev_zoom_dist is not None:
                    delta = dist_to_track - self.prev_zoom_dist
                    if delta > 0: 
                        scale_change = np.clip(delta * ZOOM_SENSITIVITY, 0, MAX_ZOOM_STEP)
                        if self.active_mode == "ZOOM_IN":
                            self.scale = np.clip(self.scale + scale_change, MIN_SCALE, MAX_SCALE)
                        else:
                            self.scale = np.clip(self.scale - scale_change, MIN_SCALE, MAX_SCALE)
                self.prev_zoom_dist = dist_to_track

                if (self.active_mode == "ZOOM_IN" and dist_pinch_index < PINCH_THRESHOLD + 10) or \
                   (self.active_mode == "ZOOM_OUT" and dist_pinch_middle < PINCH_THRESHOLD + 10):
                    self.active_mode = None

            elif self.active_mode == "PAN":
                mode_text = "MODE: GESER (Aktif)"
                color_text = (0, 0, 255)
                
                mid = ((thumb[0] + index[0]) // 2, (thumb[1] + index[1]) // 2)
                if self.prev_index_pos is not None:
                    dx = np.clip(mid[0] - self.prev_index_pos[0], -20, 20)
                    dy = np.clip(mid[1] - self.prev_index_pos[1], -20, 20)
                    self.offset_x += dx
                    self.offset_y += dy
                self.prev_index_pos = mid

                if dist_pinch_index > PINCH_THRESHOLD + 10:
                    self.active_mode = None

            # Indikator titik
            cv2.circle(img, thumb, 5, color_text, -1)
            cv2.circle(img, index, 5, color_text, -1)
            cv2.circle(img, middle, 5, color_text, -1)

        # --- RENDER 3D ---
        cx, cy = w // 2, h // 2
        self._draw_3d_cube(img, cx, cy)

        # --- UI INDIKATOR ---
        cv2.putText(img, mode_text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_text, 2, cv2.LINE_AA)
        cv2.putText(img, f"Skala: {self.scale:.2f}x", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def __del__(self):
        try:
            self.detector.close()
        except:
            pass

# ============ Streamlit WebRTC ============
webrtc_streamer(
    key="hand-3d-tracker",
    video_processor_factory=Hand3DProcessor,
    rtc_configuration=RTC_CONFIGURATION,
    media_stream_constraints={"video": {"width": 640, "height": 480}, "audio": False},
    async_processing=True,
)

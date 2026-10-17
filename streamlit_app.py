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
**Panduan Gestur:**
- ✋ **Swipe 5 Jari:** Gerakkan tangan cepat ke kiri/kanan untuk memutar objek sekilas.
- ☝️ **Telunjuk Berdiri:** Tahan 1 Detik -> Putar objek secara perlahan (Rotasi).
- 👆 **Jempol + Telunjuk Pinch:** Tahan 1 Detik -> Geser objek (Pan).
- 🤏 **Pinch 3 Jari (Jempol+Telunjuk+Tengah):** Tahan 1 Detik -> **ZOOM AKTIF**.
  - Jauhkan **hanya Telunjuk** untuk **ZOOM IN**.
  - Jauhkan **hanya Jari Tengah** untuk **ZOOM OUT**.
""")

# ============ Konfigurasi WebRTC ============
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# ============ Konstanta ============
PINCH_THRESHOLD = 45      
HOLD_THRESHOLD = 1.0      # Waktu tahan verifikasi (1 detik)
MIN_SCALE, MAX_SCALE = 0.5, 3.0
ZOOM_SENSITIVITY = 0.01
MAX_ZOOM_STEP = 0.03

THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12
PINKY_TIP = 20

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
        self.zoom_base_index = None
        self.zoom_base_middle = None
        
        # State Verifikasi (Hold)
        self.active_mode = None    # "ZOOM", "PAN", "ROTASI"
        self.candidate_mode = None 
        self.hold_start_time = 0.0

        # State Swipe 5 Jari
        self.prev_palm_pos = None
        self.swipe_velocity = 0

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

    def _draw_progress_ring(self, img, center, progress, color):
        cv2.ellipse(img, center, (25, 25), -90, 0, int(360 * min(progress, 1.0)), color, 4, cv2.LINE_AA)

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
            pinky = self._to_pixel(hand_landmarks[PINKY_TIP], w, h)
            
            # Palm center (titik tengah telapak tangan)
            wrist = self._to_pixel(hand_landmarks[0], w, h)
            palm_center = ((wrist[0] + middle[0]) // 2, (wrist[1] + middle[1]) // 2)

            dist_index = float(np.hypot(thumb[0] - index[0], thumb[1] - index[1]))
            dist_middle = float(np.hypot(thumb[0] - middle[0], thumb[1] - middle[1]))
            dist_mid_index = float(np.hypot(middle[0] - index[0], middle[1] - index[1]))

            # ==========================================
            # DETEKSI 5 JARI TERBUKA (SWIPE)
            # ==========================================
            # Cek apakah kelima jari berdiri (koordinat Y lebih kecil dari telapak)
            index_up = index[1] < wrist[1]
            middle_up = middle[1] < wrist[1]
            pinky_up = pinky[1] < wrist[1]
            thumb_up = thumb[1] < wrist[1] - 20
            
            is_5_fingers = index_up and middle_up and pinky_up and thumb_up and (dist_index > 60) and (dist_middle > 60)
            
            if is_5_fingers:
                if self.prev_palm_pos is not None:
                    dx = palm_center[0] - self.prev_palm_pos[0]
                    
                    # Deteksi Swipe Cepat (threshold kecepatan)
                    if abs(dx) > 15:  # Jika bergerak lebih dari 15px per frame
                        self.ry += dx * 0.05  # Putar kubus secara instan
                        mode_text = "SWIPE ROTASI!"
                        color_text = (0, 255, 255)
                        
                self.prev_palm_pos = palm_center
                # Matikan mode hold lain jika sedang swipe
                self.candidate_mode = None
                self.active_mode = None
            else:
                self.prev_palm_pos = None

            # ==========================================
            # DETEKSI GESTUR UNTUK VERIFIKASI (HOLD)
            # ==========================================
            detected_gesture = None
            
            # Jika bukan swipe 5 jari, cek mode hold
            if not is_5_fingers:
                if dist_index < PINCH_THRESHOLD and dist_middle < PINCH_THRESHOLD and dist_mid_index < PINCH_THRESHOLD + 20:
                    detected_gesture = "ZOOM"
                elif dist_index < PINCH_THRESHOLD and dist_middle > PINCH_THRESHOLD + 20:
                    detected_gesture = "PAN"
                elif index[1] < thumb[1] and middle[1] > thumb[1] and dist_index > PINCH_THRESHOLD:
                    detected_gesture = "ROTASI"

            # ==========================================
            # VERIFIKASI TAHAN 1 DETIK
            # ==========================================
            if self.active_mode is None and detected_gesture:
                if self.candidate_mode != detected_gesture:
                    self.candidate_mode = detected_gesture
                    self.hold_start_time = current_time
                
                progress = (current_time - self.hold_start_time) / HOLD_THRESHOLD
                
                if progress >= 1.0:
                    self.active_mode = detected_gesture
                    if self.active_mode == "ZOOM":
                        self.zoom_base_index = dist_index
                        self.zoom_base_middle = dist_middle
                    self.prev_index_pos = None
                else:
                    mid_pinch = ((thumb[0] + index[0]) // 2, (thumb[1] + index[1]) // 2)
                    ring_color = (255, 165, 0) if detected_gesture == "ZOOM" else ((0, 0, 255) if detected_gesture == "PAN" else (0, 255, 0))
                    self._draw_progress_ring(img, mid_pinch, progress, ring_color)
                    mode_text = f"VERIFIKASI: {detected_gesture}"
                    color_text = ring_color
            elif self.active_mode is None and not detected_gesture and not is_5_fingers:
                self.candidate_mode = None
                self.hold_start_time = 0.0

            # ==========================================
            # EKSEKUSI MODE
            # ==========================================
            if self.active_mode == "ROTASI":
                mode_text = "MODE: ROTASI"
                color_text = (0, 255, 0)
                
                if self.prev_index_pos is not None:
                    dx = np.clip(index[0] - self.prev_index_pos[0], -20, 20)
                    dy = np.clip(index[1] - self.prev_index_pos[1], -20, 20)
                    self.ry += dx * 0.015
                    self.rx += dy * 0.015
                self.prev_index_pos = index
                
                if detected_gesture != "ROTASI":
                    self.active_mode = None

            elif self.active_mode == "PAN":
                mode_text = "MODE: GESER"
                color_text = (0, 0, 255)
                
                mid = ((thumb[0] + index[0]) // 2, (thumb[1] + index[1]) // 2)
                if self.prev_index_pos is not None:
                    dx = np.clip(mid[0] - self.prev_index_pos[0], -20, 20)
                    dy = np.clip(mid[1] - self.prev_index_pos[1], -20, 20)
                    self.offset_x += dx
                    self.offset_y += dy
                self.prev_index_pos = mid
                
                if detected_gesture != "PAN":
                    self.active_mode = None

            elif self.active_mode == "ZOOM":
                if dist_index < PINCH_THRESHOLD and dist_middle < PINCH_THRESHOLD:
                    self.zoom_base_index = dist_index
                    self.zoom_base_middle = dist_middle
                    mode_text = "ZOOM: PILIH JARI"
                    color_text = (255, 165, 0)
                else:
                    if dist_index > PINCH_THRESHOLD + 15 and dist_middle < PINCH_THRESHOLD:
                        mode_text = "ZOOM IN (Telunjuk Jauh)"
                        color_text = (0, 255, 255)
                        if self.zoom_base_index is not None:
                            delta = dist_index - self.zoom_base_index
                            if delta > 0:
                                scale_change = np.clip(delta * ZOOM_SENSITIVITY, 0, MAX_ZOOM_STEP)
                                self.scale = np.clip(self.scale + scale_change, MIN_SCALE, MAX_SCALE)
                                self.zoom_base_index = dist_index
                    
                    elif dist_middle > PINCH_THRESHOLD + 15 and dist_index < PINCH_THRESHOLD:
                        mode_text = "ZOOM OUT (Jari Tengah Jauh)"
                        color_text = (255, 0, 255)
                        if self.zoom_base_middle is not None:
                            delta = dist_middle - self.zoom_base_middle
                            if delta > 0:
                                scale_change = np.clip(delta * ZOOM_SENSITIVITY, 0, MAX_ZOOM_STEP)
                                self.scale = np.clip(self.scale - scale_change, MIN_SCALE, MAX_SCALE)
                                self.zoom_base_middle = dist_middle

                if dist_index > PINCH_THRESHOLD + 30 and dist_middle > PINCH_THRESHOLD + 30:
                    self.active_mode = None
                    self.zoom_base_index = None
                    self.zoom_base_middle = None

            # Indikator titik
            cv2.circle(img, thumb, 5, color_text, -1)
            cv2.circle(img, index, 5, color_text, -1)
            cv2.circle(img, middle, 5, color_text, -1)
            if is_5_fingers:
                cv2.circle(img, palm_center, 10, (0, 255, 255), -1)

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

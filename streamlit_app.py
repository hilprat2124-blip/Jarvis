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
- **Rotasi:** Pinch cepat (sentuh jempol+telunjuk) lalu lepaskan, gerakkan tangan.
- **Zoom In:** Mulai dari posisi Pinch -> **Tahan 1 detik** -> Jauhkan jari.
- **Zoom Out:** Mulai dari posisi Jari Terbuka -> **Tahan 1 detik** -> Dekatkan jari (sampai pinch).
- **Geser (Pan):** Tahan pinch >1 detik, lalu geser tangan tanpa melepas pinch.
""")

# ============ Konfigurasi WebRTC ============
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# ============ Konstanta ============
PINCH_THRESHOLD = 40      # Jarak (px) deteksi pinch
HOLD_THRESHOLD = 1.0      # Waktu tahan (detik) untuk memicu aksi
ZOOM_SENSITIVITY = 0.015  # Kecepatan zoom

MIN_SCALE, MAX_SCALE = 0.5, 3.0

THUMB_TIP = 4
INDEX_TIP = 8

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
        
        # --- State Latch / Timer ---
        self.is_pinching = False
        self.pinch_start_time = 0.0
        self.open_start_time = 0.0
        
        # Mode: "IDLE", "ROTATE", "PAN", "ZOOM_IN", "ZOOM_OUT"
        self.mode = "IDLE" 
        
        # Timer untuk mendeteksi tahanan (hold)
        self.hold_start_time = 0.0
        self.hold_candidate = None # "PINCH" atau "OPEN"
        
        self.prev_index_pos = None
        self.prev_dist = None

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
        # Menggambar lingkaran loading di sekitar jari
        cv2.ellipse(img, center, (25, 25), -90, 0, int(360 * min(progress, 1.0)), color, 3, cv2.LINE_AA)

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)  
        h, w, _ = img.shape

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        
        self.frame_timestamp += 1
        results = self.detector.detect_for_video(mp_image, self.frame_timestamp)

        currently_pinching = False
        dist = 0
        current_time = time.time()

        if results.hand_landmarks:
            hand_landmarks = results.hand_landmarks[0]
            self._draw_landmarks(img, hand_landmarks, w, h)

            thumb = self._to_pixel(hand_landmarks[THUMB_TIP], w, h)
            index = self._to_pixel(hand_landmarks[INDEX_TIP], w, h)
            mid = ((thumb[0] + index[0]) // 2, (thumb[1] + index[1]) // 2)
            
            dist = float(np.hypot(thumb[0] - index[0], thumb[1] - index[1]))
            currently_pinching = dist < PINCH_THRESHOLD

            # ==========================================
            # LOGIKA LATCH (KUNCI LEPAS)
            # ==========================================
            
            # 1. Cek Kandidat Hold (Mau ngapain nih?)
            if self.mode == "IDLE":
                if currently_pinching:
                    if self.hold_candidate != "PINCH":
                        self.hold_candidate = "PINCH"
                        self.hold_start_time = current_time
                else:
                    # Jari terbuka
                    if self.hold_candidate != "OPEN":
                        self.hold_candidate = "OPEN"
                        self.hold_start_time = current_time
                
                # Jika sudah tahan 1 detik, aktifkan mode
                if current_time - self.hold_start_time > HOLD_THRESHOLD:
                    if self.hold_candidate == "PINCH":
                        self.mode = "ZOOM_IN"
                    elif self.hold_candidate == "OPEN":
                        self.mode = "ZOOM_OUT"
            
            # 2. Aksi Berdasarkan Mode
            if self.mode == "ZOOM_IN":
                # Zoom in: Jari menjauh (dist membesar)
                if currently_pinching:
                    self.prev_dist = dist # update baseline
                else:
                    if self.prev_dist is not None:
                        delta = dist - self.prev_dist
                        if delta > 0:
                            self.scale = np.clip(self.scale + delta * ZOOM_SENSITIVITY, MIN_SCALE, MAX_SCALE)
                        self.prev_dist = dist
                
                # Stop jika jari kembali mendekat / pinch
                if currently_pinching:
                    self.mode = "IDLE"
                    self.hold_candidate = None

            elif self.mode == "ZOOM_OUT":
                # Zoom out: Jari mendekat (dist mengecil)
                if not currently_pinching:
                    if self.prev_dist is not None:
                        delta = self.prev_dist - dist
                        if delta > 0:
                            self.scale = np.clip(self.scale - delta * ZOOM_SENSITIVITY, MIN_SCALE, MAX_SCALE)
                        self.prev_dist = dist
                else:
                    # Stop jika sudah pinch
                    self.mode = "IDLE"
                    self.hold_candidate = None

            # 3. Rotasi & Pan (Hanya jika tidak sedang Zoom)
            if self.mode == "IDLE" and currently_pinching and current_time - self.pinch_start_time < HOLD_THRESHOLD:
                if self.prev_index_pos is not None:
                    dx = np.clip(index[0] - self.prev_index_pos[0], -20, 20)
                    dy = np.clip(index[1] - self.prev_index_pos[1], -20, 20)
                    self.ry += dx * 0.015
                    self.rx += dy * 0.015
                self.prev_index_pos = index
            elif currently_pinching:
                 if self.mode == "IDLE":
                     # Mode PAN (Tahan >1s)
                     self.mode = "PAN"
            elif not currently_pinching:
                self.prev_index_pos = None

            if self.mode == "PAN" and currently_pinching:
                if self.prev_index_pos is not None:
                    dx = np.clip(index[0] - self.prev_index_pos[0], -20, 20)
                    dy = np.clip(index[1] - self.prev_index_pos[1], -20, 20)
                    self.offset_x += dx
                    self.offset_y += dy
                self.prev_index_pos = index
            elif not currently_pinching and self.mode == "PAN":
                self.mode = "IDLE"

            # Update state pinch dasar
            if currently_pinching and not self.is_pinching:
                self.pinch_start_time = current_time
            self.is_pinching = currently_pinching
            
            # Sinkronisasi prev_dist untuk mode IDLE
            if self.mode == "IDLE":
                self.prev_dist = dist
                if self.hold_candidate == "OPEN":
                    progress = (current_time - self.hold_start_time) / HOLD_THRESHOLD
                    self._draw_progress_ring(img, mid, progress, (255, 165, 0))
                elif self.hold_candidate == "PINCH":
                    progress = (current_time - self.hold_start_time) / HOLD_THRESHOLD
                    self._draw_progress_ring(img, mid, progress, (0, 255, 0))


        # --- RENDER 3D ---
        cx, cy = w // 2, h // 2
        self._draw_3d_cube(img, cx, cy)

        # --- UI INDIKATOR ---
        if self.mode == "PAN":
            status, color = "GESER (PAN)", (0, 0, 255)
        elif self.mode == "ZOOM_IN":
            status, color = "ZOOM IN (Jauhkan Jari)", (0, 255, 255)
        elif self.mode == "ZOOM_OUT":
            status, color = "ZOOM OUT (Dekatkan Jari)", (255, 0, 255)
        elif self.is_pinching:
            status, color = "ROTASI", (0, 255, 0)
        else:
            status, color = "SIAP (Tahan 1 Detik)", (200, 200, 200)
            
        cv2.putText(img, f"MODE: {status}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
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

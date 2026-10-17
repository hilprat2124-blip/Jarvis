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
**Cara Menggunakan:**
- **Rotasi:** Pinch cepat (jempol+telunjuk) lalu lepaskan, gerakkan tangan untuk memutar.
- **Zoom In/Out:** Pinch lalu jauhkan/dekatkan jari (seperti mencubit).
- **Geser (Pan):** Tahan pinch >1 detik, lalu gerakkan tangan.
""")

# ============ Konfigurasi WebRTC ============
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# ============ Konstanta ============
PINCH_THRESHOLD = 45      # Jarak (px) deteksi pinch
HOLD_THRESHOLD = 1.0      # Waktu (detik) untuk mendeteksi Pan/Geser

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

# ============ Fungsi Download Model Otomatis ============
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
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
            min_tracking_confidence=0.7
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        self.frame_timestamp = 0
        
        # --- State 3D Model ---
        self.rx, self.ry = 0.0, 0.0       # Rotasi X, Y
        self.scale = 1.0                  # Skala Zoom
        self.offset_x, self.offset_y = 0, 0 # Posisi Geser
        
        # --- State Gestur ---
        self.is_pinching = False
        self.pinch_start_time = 0.0
        self.is_panning = False
        
        self.prev_index_pos = None

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
        """Menggambar Kubus 3D Wireframe dengan Proyeksi Perspektif"""
        # Titik-titik vertex kubus (-1 sampai 1)
        vertices = np.array([
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], # Belakang
            [-1, -1,  1], [1, -1,  1], [1, 1,  1], [-1, 1,  1]  # Depan
        ], dtype=np.float32)

        # Edge yang menghubungkan vertex
        edges = [
            (0,1), (1,2), (2,3), (3,0), # Belakang
            (4,5), (5,6), (6,7), (7,4), # Depan
            (0,4), (1,5), (2,6), (3,7)  # Penghubung
        ]

        # 1. Rotasi Matrix (X dan Y)
        cos_x, sin_x = np.cos(self.rx), np.sin(self.rx)
        cos_y, sin_y = np.cos(self.ry), np.sin(self.ry)
        
        rot_x = np.array([[1, 0, 0], [0, cos_x, -sin_x], [0, sin_x, cos_x]])
        rot_y = np.array([[cos_y, 0, sin_y], [0, 1, 0], [-sin_y, 0, cos_y]])
        rot_matrix = np.dot(rot_y, rot_x)

        # 2. Transformasi Titik
        transformed = np.dot(vertices, rot_matrix.T)
        
        # 3. Skala & Translasi (Proyeksi Perspektif sederhana)
        pts_2d = []
        for v in transformed:
            # Skala zoom
            v = v * self.scale
            # Proyeksi (semakin jauh Z, semakin kecil)
            fov = 4.0
            z = v[2] + fov
            if z == 0: z = 0.001
            
            # Konversi ke koordinat layar
            px = int((v[0] / z) * 150) + cx + self.offset_x
            py = int((v[1] / z) * 150) + cy + self.offset_y
            pts_2d.append((px, py, v[2])) # Simpan Z untuk efek glow

        # 4. Gambar Garis (Edge) dengan efek Neon
        for edge in edges:
            p1 = pts_2d[edge[0]]
            p2 = pts_2d[edge[1]]
            
            # Warna berdasarkan kedalaman (Z) - Futuristik
            depth_avg = (p1[2] + p2[2]) / 2
            # Semakin dekat ke kamera (Z negatif), semakin terang
            intensity = np.clip(1.0 - (depth_avg / 2.0), 0.3, 1.0)
            color = (int(255 * intensity), int(255 * intensity), 0) # Cyan Neon
            
            # Efek Glow
            overlay = img.copy()
            cv2.line(overlay, (p1[0], p1[1]), (p2[0], p2[1]), color, 8, cv2.LINE_AA)
            cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            
            # Garis Utama
            cv2.line(img, (p1[0], p1[1]), (p2[0], p2[1]), color, 2, cv2.LINE_AA)

        # 5. Gambar Vertex (Titik Ujung)
        for p in pts_2d:
            cv2.circle(img, (p[0], p[1]), 3, (255, 255, 255), -1, cv2.LINE_AA)

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)  
        h, w, _ = img.shape

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        
        self.frame_timestamp += 1
        results = self.detector.detect_for_video(mp_image, self.frame_timestamp)

        hand_detected = False
        
        if results.hand_landmarks:
            hand_detected = True
            hand_landmarks = results.hand_landmarks[0]
            self._draw_landmarks(img, hand_landmarks, w, h)

            thumb = self._to_pixel(hand_landmarks[THUMB_TIP], w, h)
            index = self._to_pixel(hand_landmarks[INDEX_TIP], w, h)
            
            dist = float(np.hypot(thumb[0] - index[0], thumb[1] - index[1]))
            currently_pinching = dist < PINCH_THRESHOLD

            # --- LOGIKA GESTUR ---
            if currently_pinching:
                if not self.is_pinching:
                    # Pinch baru dimulai
                    self.is_pinching = True
                    self.pinch_start_time = time.time()
                    self.is_panning = False
                
                # Hitung durasi pinch
                duration = time.time() - self.pinch_start_time
                
                # Jika ditahan > 1 detik, aktifkan mode PAN (Geser)
                if duration > HOLD_THRESHOLD:
                    self.is_panning = True
                
                # --- PROSES GERAKAN ---
                if self.prev_index_pos is not None:
                    dx = index[0] - self.prev_index_pos[0]
                    dy = index[1] - self.prev_index_pos[1]
                    
                    if self.is_panning:
                        # Geser objek
                        self.offset_x += dx * 2
                        self.offset_y += dy * 2
                    else:
                        # Rotasi objek (Free View)
                        self.ry += dx * 0.01
                        self.rx += dy * 0.01
                
                self.prev_index_pos = index
            
            else:
                # Jari lepas (tidak pinch)
                if self.is_pinching:
                    # Jika baru saja lepas, dan tidak dalam mode panning
                    # Maka tidak ada aksi khusus (rotasi berhenti)
                    pass
                
                self.is_pinching = False
                self.is_panning = False
                self.prev_index_pos = None
                
                # --- FITUR ZOOM (Berdasarkan jarak jari saat tidak pinch) ---
                # Jika jarak membesar (menjauh), Zoom In. Jika mengecil, Zoom Out.
                # Kita gunakan jarak 50-150 px sebagai range
                if dist > 50 and dist < 150:
                    # Normalisasi jarak ke skala 0.5 - 2.5
                    normalized_dist = (dist - 50) / 100.0
                    target_scale = 0.5 + (normalized_dist * 2.0)
                    # Smoothing (transisi halus)
                    self.scale += (target_scale - self.scale) * 0.1

        # --- RENDER VISUAL ---
        # Gambar kubus 3D di tengah layar
        cx, cy = w // 2, h // 2
        self._draw_3d_cube(img, cx, cy)

        # UI Indikator Status
        status = "GESER (PAN)" if self.is_panning else ("ROTASI" if self.is_pinching else "ZOOM (Jauhkan/Dekatkan Jari)")
        status_color = (0, 0, 255) if self.is_panning else ((0, 255, 255) if self.is_pinching else (0, 255, 0))
        
        cv2.putText(img, f"MODE: {status}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2, cv2.LINE_AA)
        cv2.putText(img, f"Skala: {self.scale:.2f}x", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

        # Indikator Pinch
        if currently_pinching:
            mid = ((thumb[0] + index[0]) // 2, (thumb[1] + index[1]) // 2)
            cv2.circle(img, mid, 15, status_color, 2, cv2.LINE_AA)
            
            # Loading bar untuk Pan
            if not self.is_panning:
                prog = (time.time() - self.pinch_start_time) / HOLD_THRESHOLD
                cv2.ellipse(img, mid, (20, 20), -90, 0, int(360 * min(prog, 1.0)), (0, 0, 255), 3, cv2.LINE_AA)

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
    media_stream_constraints={"video": True, "audio": False},
    async_processing=True,
)

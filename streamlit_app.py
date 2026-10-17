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
st.set_page_config(page_title="Stable 3D Hand Tracking", layout="wide")
st.title("🧊 3D Free View - Stable Controls")
st.write("""
**Cara Menggunakan:**
1. Gunakan ujung **Telunjuk** Anda untuk menyentuh tombol di layar.
2. **[ROTASI]**: Sentuh tombol, lalu gerakkan tangan Anda.
3. **[ZOOM IN / OUT]**: Sentuh tombol, lalu gerakkan tangan Anda **maju (dekat kamera)** atau **mundur (jauh dari kamera)**.
""")

# ============ Konfigurasi WebRTC ============
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

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
        
        # State Tracking
        self.active_mode = None  # "ROTASI", "ZOOM_IN", "ZOOM_OUT", None
        self.prev_index_pos = None
        self.prev_scale_z = None # Untuk deteksi maju/mundur (Zoom)

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
            cv2.line(img, start, end, (60, 60, 60), 1, cv2.LINE_AA)
        for lm in landmarks:
            px = self._to_pixel(lm, w, h)
            cv2.circle(img, px, 2, (100, 100, 100), -1, cv2.LINE_AA)

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

    def _draw_ui_button(self, img, text, x, y, w, h, is_active):
        # Gambar kotak tombol
        color = (0, 255, 0) if is_active else (150, 150, 150)
        thickness = 3 if is_active else 1
        cv2.rectangle(img, (x, y), (x+w, y+h), color, thickness, cv2.LINE_AA)
        
        # Gambar teks
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
        text_x = x + (w - text_size[0]) // 2
        text_y = y + (h + text_size[1]) // 2
        cv2.putText(img, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)  
        h, w, _ = img.shape

        # --- DEFINISI TOMBOL UI ---
        btn_w, btn_h = 140, 50
        btn_y = h - 70
        btn_rotate = (20, btn_y, btn_w, btn_h)
        btn_zoom_in = (w//2 - btn_w//2, btn_y, btn_w, btn_h)
        btn_zoom_out = (w - btn_w - 20, btn_y, btn_w, btn_h)

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        
        self.frame_timestamp += 1
        results = self.detector.detect_for_video(mp_image, self.frame_timestamp)

        # Reset mode setiap frame
        self.active_mode = None
        mode_text = "MODE: SIAP"
        color_text = (200, 200, 200)

        if results.hand_landmarks:
            hand_landmarks = results.hand_landmarks[0]
            self._draw_landmarks(img, hand_landmarks, w, h)

            index = self._to_pixel(hand_landmarks[INDEX_TIP], w, h)
            index_z = hand_landmarks[INDEX_TIP].z # Nilai Z untuk Zoom (maju/mundur)

            # Cek tabrakan ujung telunjuk dengan tombol
            if btn_rotate[0] < index[0] < btn_rotate[0]+btn_rotate[2] and btn_rotate[1] < index[1] < btn_rotate[1]+btn_rotate[3]:
                self.active_mode = "ROTASI"
            elif btn_zoom_in[0] < index[0] < btn_zoom_in[0]+btn_zoom_in[2] and btn_zoom_in[1] < index[1] < btn_zoom_in[1]+btn_zoom_in[3]:
                self.active_mode = "ZOOM_IN"
            elif btn_zoom_out[0] < index[0] < btn_zoom_out[0]+btn_zoom_out[2] and btn_zoom_out[1] < index[1] < btn_zoom_out[1]+btn_zoom_out[3]:
                self.active_mode = "ZOOM_OUT"

            # Eksekusi berdasarkan tombol yang disentuh
            if self.active_mode == "ROTASI":
                mode_text = "MODE: ROTASI"
                color_text = (0, 255, 0)
                
                if self.prev_index_pos is not None:
                    dx = np.clip(index[0] - self.prev_index_pos[0], -20, 20)
                    dy = np.clip(index[1] - self.prev_index_pos[1], -20, 20)
                    self.ry += dx * 0.015
                    self.rx += dy * 0.015
                self.prev_index_pos = index
                self.prev_scale_z = None

            elif self.active_mode in ["ZOOM_IN", "ZOOM_OUT"]:
                color_text = (255, 165, 0)
                mode_text = f"MODE: {self.active_mode} (GESER TANGAN MAJU/MUNDUR)"
                
                if self.prev_scale_z is not None:
                    delta_z = index_z - self.prev_scale_z
                    # Jika tangan maju (z mengecil), perbesar
                    scale_change = -delta_z * 1.5
                    if self.active_mode == "ZOOM_IN":
                        self.scale = np.clip(self.scale + scale_change, 0.5, 3.0)
                    else:
                        self.scale = np.clip(self.scale - scale_change, 0.5, 3.0)
                
                self.prev_scale_z = index_z
                self.prev_index_pos = None
            else:
                self.prev_index_pos = None
                self.prev_scale_z = None

            # Indikator ujung telunjuk
            cv2.circle(img, index, 8, color_text, -1)
            cv2.circle(img, index, 12, color_text, 2)

        # --- GAMBAR TOMBOL UI ---
        self._draw_ui_button(img, "[1] ROTASI", *btn_rotate, self.active_mode == "ROTASI")
        self._draw_ui_button(img, "[2] ZOOM IN", *btn_zoom_in, self.active_mode == "ZOOM_IN")
        self._draw_ui_button(img, "[3] ZOOM OUT", *btn_zoom_out, self.active_mode == "ZOOM_OUT")

        # --- RENDER 3D KUBUS ---
        cx, cy = w // 2, h // 2 - 50 # Posisi agak ke atas agar tidak tertutup tombol
        self._draw_3d_cube(img, cx, cy)

        # --- UI INDIKATOR TEKS ---
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

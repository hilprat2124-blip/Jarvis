import av
import cv2
import numpy as np
import streamlit as st
import mediapipe as mp
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

# ============ Konfigurasi Halaman ============
st.set_page_config(page_title="Hand Tracking Drawing - Streamlit", layout="wide")

st.title("✌️ Hand Tracking - Visualisasi Garis Antar Jari")
st.write(
    "Aktifkan kamera di bawah. Aplikasi akan mendeteksi ketika ujung jari "
    "(misal Jempol & Telunjuk) saling berdekatan / berinteraksi, lalu menarik "
    "garis dinamis saat jari bergerak menjauh."
)

# ============ Inisialisasi MediaPipe ============
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# ============ Konfigurasi WebRTC ============
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# ============ Konstanta ============
TOUCH_THRESHOLD = 45      # Jarak (px) dianggap "pinch"/sentuhan
MAX_LINE_DIST = 300       # Jarak (px) maksimum untuk menggambar garis
MIN_THICKNESS = 2
MAX_THICKNESS = 8

# Indeks landmark ujung jari MediaPipe
THUMB_TIP = 4
FINGER_TIPS = {
    "Telunjuk":    (8,  (0, 255, 255)),   # Kuning
    "Jari Tengah": (12, (255, 0, 255)),   # Magenta
    "Jari Manis":  (16, (255, 255, 0)),   # Cyan
    "Kelingking":  (20, (0, 255, 0)),     # Hijau
}


class HandInteractionProcessor(VideoProcessorBase):
    def __init__(self):
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        )

    def _to_pixel(self, landmark, w, h):
        return int(landmark.x * w), int(landmark.y * h)

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)  # mirror
        h, w, _ = img.shape

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_rgb.flags.writeable = False
        results = self.hands.process(img_rgb)
        img_rgb.flags.writeable = True

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # Skeleton tangan
                mp_drawing.draw_landmarks(
                    img,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(200, 200, 200), thickness=1, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(240, 240, 240), thickness=1),
                )

                # Koordinat pixel ujung jari
                thumb = self._to_pixel(hand_landmarks.landmark[THUMB_TIP], w, h)

                # Gambar jempol sekali saja (efisiensi)
                cv2.circle(img, thumb, 8, (0, 0, 255), -1)

                for name, (idx, color) in FINGER_TIPS.items():
                    tip = self._to_pixel(hand_landmarks.landmark[idx], w, h)

                    # Lingkaran ujung jari
                    cv2.circle(img, tip, 8, color, -1)

                    # Jarak Euclidean
                    dist = float(np.hypot(thumb[0] - tip[0], thumb[1] - tip[1]))

                    # Garis dinamis jika dalam batas
                    if dist < MAX_LINE_DIST:
                        # Ketebalan proporsional (clamp agar tidak negatif)
                        thickness = int(
                            np.interp(dist, [0, MAX_LINE_DIST], [MAX_THICKNESS, MIN_THICKNESS])
                        )
                        thickness = max(MIN_THICKNESS, thickness)
                        cv2.line(img, thumb, tip, color, thickness)

                        mid = ((thumb[0] + tip[0]) // 2, (thumb[1] + tip[1]) // 2)

                        if dist < TOUCH_THRESHOLD:
                            cv2.circle(img, mid, 12, (0, 255, 0), -1)
                            cv2.putText(
                                img, f"Pinch! ({name})", (mid[0] - 40, mid[1] - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2,
                            )
                        else:
                            cv2.putText(
                                img, f"{int(dist)}px", (mid[0] - 15, mid[1] - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1,
                            )

        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def __del__(self):
        try:
            self.hands.close()
        except Exception:
            pass


# ============ Streamlit WebRTC ============
webrtc_streamer(
    key="hand-gesture-tracker",
    video_processor_factory=HandInteractionProcessor,
    rtc_configuration=RTC_CONFIGURATION,
    media_stream_constraints={"video": True, "audio": False},
    async_processing=True,   # lebih responsif
)

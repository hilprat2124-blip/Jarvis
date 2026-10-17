import time
import cv2
import numpy as np
import streamlit as st
import mediapipe as mp
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

# Set konfigurasi halaman Streamlit
st.set_page_config(page_title="Hand Tracking Drawing - Streamlit", layout="wide")

st.title("✌️ Hand Tracking - Visualisasi Garis dengan Jeda Verifikasi (1 Detik)")
st.write(
    "Jempol dan telunjuk/jari lain harus berinteraksi dan bertahan stabil selama 1 detik "
    "sebelum garis dinamis zoom aktif, agar tidak bentrok dengan gestur lainnya."
)

# Inisialisasi MediaPipe Hands
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# Konfigurasi RTC untuk koneksi WebRTC yang stabil
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)


class HandInteractionProcessor(VideoProcessorBase):
    def __init__(self):
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        )
        # Variabel untuk melacak waktu verifikasi gestur
        self.pinch_start_time = None
        self.is_gesture_verified = False

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)  # Efek cermin
        
        h, w, c = img.shape
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        results = self.hands.process(img_rgb)

        # Status default jika tidak ada interaksi terdeteksi
        pinch_detected_in_frame = False

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # Gambarkan skeleton tangan tipis
                mp_drawing.draw_landmarks(
                    img, 
                    hand_landmarks, 
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(200, 200, 200), thickness=1, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(240, 240, 240), thickness=1)
                )

                thumb = (int(hand_landmarks.landmark[4].x * w), int(hand_landmarks.landmark[4].y * h))
                index = (int(hand_landmarks.landmark[8].x * w), int(hand_landmarks.landmark[8].y * h))
                middle = (int(hand_landmarks.landmark[12].x * w), int(hand_landmarks.landmark[12].y * h))
                ring = (int(hand_landmarks.landmark[16].x * w), int(hand_landmarks.landmark[16].y * h))
                pinky = (int(hand_landmarks.landmark[20].x * w), int(hand_landmarks.landmark[20].y * h))

                finger_tips = [
                    ("Telunjuk", index, (0, 255, 255)),  
                    ("Jari Tengah", middle, (255, 0, 255)),  
                    ("Jari Manis", ring, (255, 255, 0)),  
                    ("Kelingking", pinky, (0, 255, 0)),  
                ]

                # Ambang batas jarak untuk mulai menghitung timer (misal < 50 piksel)
                TOUCH_THRESHOLD = 50 
                current_time = time.time()

                for name, tip_coords, color in finger_tips:
                    dist = np.hypot(thumb[0] - tip_coords[0], thumb[1] - tip_coords[1])

                    cv2.circle(img, thumb, 8, (0, 0, 255), -1)
                    cv2.circle(img, tip_coords, 8, color, -1)

                    # Cek apakah jari sedang berdekatan (posisi inisiasi pinch)
                    if dist < TOUCH_THRESHOLD:
                        pinch_detected_in_frame = True
                        
                        # Jika baru pertama kali mendekat, catat waktunya
                        if self.pinch_start_time is None:
                            self.pinch_start_time = current_time
                        
                        elapsed_time = current_time - self.pinch_start_time
                        
                        # Hitung mundur / progress 1 detik
                        if elapsed_time < 1.0:
                            # Tampilkan indikator loading verifikasi (warna Oranye)
                            mid_x = (thumb[0] + tip_coords[0]) // 2
                            mid_y = (thumb[1] + tip_coords[1]) // 2
                            cv2.putText(
                                img, f"Verifikasi... {int((1.0 - elapsed_time) * 10)}") + "s", 
                                (mid_x - 40, mid_y - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2
                            )
                        else:
                            # Jika sudah lewat 1 detik, verifikasi berhasil!
                            self.is_gesture_verified = True

                    # Jika gestur sudah terverifikasi (lolos jeda 1 detik), render garis dinamis
                    if self.is_gesture_verified:
                        thickness = max(2, int(8 - (dist / 40)))
                        cv2.line(img, thumb, tip_coords, color, thickness)
                        
                        mid_x = (thumb[0] + tip_coords[0]) // 2
                        mid_y = (thumb[1] + tip_coords[1]) // 2
                        
                        cv2.putText(
                            img, f"Zoom Mode: {int(dist)}px", (mid_x - 30, mid_y - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2
                        )

        # Jika jari dilepas atau tidak memenuhi syarat pinch, reset status verifikasi
        if not pinch_detected_in_frame:
            self.pinch_start_time = None
            self.is_gesture_verified = False

        return frame.from_ndarray(img, format="bgr24")


# Tampilkan Streaming Webcam di Streamlit
webrtc_streamer(
    key="hand-gesture-zoom-verifier",
    video_processor_factory=HandInteractionProcessor,
    rtc_configuration=RTC_CONFIGURATION,
    media_stream_constraints={"video": True, "audio": False},
)

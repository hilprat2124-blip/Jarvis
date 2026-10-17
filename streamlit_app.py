import cv2
import numpy as np
import streamlit as st
import mediapipe as mp
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

# Set konfigurasi halaman Streamlit
st.set_page_config(page_title="Hand Tracking Drawing - Streamlit", layout="wide")

st.title("✌️ Hand Tracking - Visualisasi Garis Antar Jari")
st.write(
    "Aktifkan kamera di bawah. Aplikasi akan mendeteksi ketika ujung jari (misal Jempol & Telunjuk) "
    "saling berdekatan / berinteraksi, lalu menarik garis dinamis saat jari bergerak menjauh."
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
        # Inisialisasi model MediaPipe Hands
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        )

    def recv(self, frame):
        # Ambil frame gambar dari webcam
        img = frame.to_ndarray(format="bgr24")
        
        # Mirror / balik gambar horizontal agar seperti cermin
        img = cv2.flip(img, 1)
        
        h, w, c = img.shape
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Proses deteksi tangan
        results = self.hands.process(img_rgb)

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # Gambarkan skeleton tangan secara halus (opsional)
                mp_drawing.draw_landmarks(
                    img, 
                    hand_landmarks, 
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(200, 200, 200), thickness=1, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(240, 240, 240), thickness=1)
                )

                # Ambil koordinat pixel untuk setiap ujung jari:
                # 4: Ujung Jempol (Thumb Tip)
                # 8: Ujung Telunjuk (Index Tip)
                # 12: Ujung Jari Tengah (Middle Tip)
                # 16: Ujung Jari Manis (Ring Tip)
                # 20: Ujung Kelingking (Pinky Tip)
                
                thumb = (int(hand_landmarks.landmark[4].x * w), int(hand_landmarks.landmark[4].y * h))
                index = (int(hand_landmarks.landmark[8].x * w), int(hand_landmarks.landmark[8].y * h))
                middle = (int(hand_landmarks.landmark[12].x * w), int(hand_landmarks.landmark[12].y * h))
                ring = (int(hand_landmarks.landmark[16].x * w), int(hand_landmarks.landmark[16].y * h))
                pinky = (int(hand_landmarks.landmark[20].x * w), int(hand_landmarks.landmark[20].y * h))

                # Daftar pasangan jari yang ingin dihubungkan dengan jempol
                finger_tips = [
                    ("Telunjuk", index, (0, 255, 255)),  # Kuning
                    ("Jari Tengah", middle, (255, 0, 255)),  # Magenta
                    ("Jari Manis", ring, (255, 255, 0)),  # Cyan
                    ("Kelingking", pinky, (0, 255, 0)),  # Hijau
                ]

                # Threshold jarak (piksel) untuk mendeteksi interaksi/sentuhan awal
                TOUCH_THRESHOLD = 45 

                for name, tip_coords, color in finger_tips:
                    # Hitung jarak Euclidean antara Jempol dan Ujung Jari lainnya
                    dist = np.hypot(thumb[0] - tip_coords[0], thumb[1] - tip_coords[1])

                    # 1. Gambar lingkaran di ujung jari jempol & jari pasangan
                    cv2.circle(img, thumb, 8, (0, 0, 255), -1)
                    cv2.circle(img, tip_coords, 8, color, -1)

                    # 2. Jika jari berinteraksi (berdekatan atau sedang direntangkan)
                    # Kita hubungkan dengan garis yang panjangnya fleksibel sesuai jarak jari
                    if dist < 300: # Batas jarak maksimum garis tetap dirender
                        # Ketebalan garis menyesuaikan dekat/jauhnya jari
                        thickness = max(2, int(8 - (dist / 40)))
                        
                        # Gambar garis penghubung antar jari
                        cv2.line(img, thumb, tip_coords, color, thickness)
                        
                        # Tampilkan titik tengah dan teks jarak/status interaksi
                        mid_x = (thumb[0] + tip_coords[0]) // 2
                        mid_y = (thumb[1] + tip_coords[1]) // 2
                        
                        # Indikator visual saat jari sangat dekat (berinteraksi/pinching)
                        if dist < TOUCH_THRESHOLD:
                            cv2.circle(img, (mid_x, mid_y), 12, (0, 255, 0), -1)
                            cv2.putText(
                                img, "Pinch!", (mid_x - 20, mid_y - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2
                            )
                        else:
                            # Menampilkan panjang jarak dinamis
                            cv2.putText(
                                img, f"{int(dist)}px", (mid_x - 15, mid_y - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
                            )

        return frame.from_ndarray(img, format="bgr24")


# Tampilkan Streaming Webcam di Streamlit
webrtc_streamer(
    key="hand-gesture-tracker",
    video_processor_factory=HandInteractionProcessor,
    rtc_configuration=RTC_CONFIGURATION,
    media_stream_constraints={"video": True, "audio": False},
)

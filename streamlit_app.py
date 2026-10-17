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

# Konfigurasi Halaman
st.set_page_config(page_title="Hand Tracking Drawing", layout="wide")
st.title("✌️ Hand Tracking - Visualisasi Garis Antar Jari")

# Konfigurasi WebRTC
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# Konstanta
TOUCH_THRESHOLD = 45      
MAX_LINE_DIST = 300       
MIN_THICKNESS = 2
MAX_THICKNESS = 8

THUMB_TIP = 4
FINGER_TIPS = {
    "Telunjuk":    (8,  (0, 255, 255)),   
    "Jari Tengah": (12, (255, 0, 255)),   
    "Jari Manis":  (16, (255, 255, 0)),   
    "Kelingking":  (20, (0, 255, 0)),     
}

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        
    (0, 5), (5, 6), (6, 7), (7, 8),        
    (5, 9), (9, 10), (10, 11), (11, 12),   
    (9, 13), (13, 14), (14, 15), (15, 16), 
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17)                                
]

# Download Model Otomatis
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

    def _to_pixel(self, landmark, w, h):
        return int(landmark.x * w), int(landmark.y * h)

    def _draw_landmarks(self, img, landmarks, w, h):
        for connection in HAND_CONNECTIONS:
            start = self._to_pixel(landmarks[connection[0]], w, h)
            end = self._to_pixel(landmarks[connection[1]], w, h)
            cv2.line(img, start, end, (240, 240, 240), 1)
        for lm in landmarks:
            px = self._to_pixel(lm, w, h)
            cv2.circle(img, px, 2, (200, 200, 200), -1)

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
                cv2.circle(img, thumb, 8, (0, 0, 255), -1)

                for name, (idx, color) in FINGER_TIPS.items():
                    tip = self._to_pixel(hand_landmarks[idx], w, h)
                    cv2.circle(img, tip, 8, color, -1)
                    dist = float(np.hypot(thumb[0] - tip[0], thumb[1] - tip[1]))

                    if dist < MAX_LINE_DIST:
                        thickness = int(np.interp(dist, [0, MAX_LINE_DIST], [MAX_THICKNESS, MIN_THICKNESS]))
                        thickness = max(MIN_THICKNESS, thickness)
                        cv2.line(img, thumb, tip, color, thickness)
                        mid = ((thumb[0] + tip[0]) // 2, (thumb[1] + tip[1]) // 2)

                        if dist < TOUCH_THRESHOLD:
                            cv2.circle(img, mid, 12, (0, 255, 0), -1)
                            cv2.putText(img, f"Pinch! ({name})", (mid[0] - 40, mid[1] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
                        else:
                            cv2.putText(img, f"{int(dist)}px", (mid[0] - 15, mid[1] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

    def __del__(self):
        try:
            self.detector.close()
        except:
            pass

webrtc_streamer(
    key="hand-gesture-tracker",
    video_processor_factory=HandInteractionProcessor,
    rtc_configuration=RTC_CONFIGURATION,
    media_stream_constraints={"video": True, "audio": False},
    async_processing=True,
)

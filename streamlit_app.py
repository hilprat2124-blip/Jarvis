"""
==============================================================
🤖 JARVIS WEB AI - Versi Groq + Suara Interaktif
==============================================================
"""

import streamlit as st
import io
import os
import json
import base64
import requests
from gtts import gTTS
from openai import OpenAI

# ============================================================
# KONFIGURASI
# ============================================================
st.set_page_config(
    page_title="Jarvis Web AI",
    page_icon="🎙️",
    layout="centered"
)

STT_LANGUAGE = "id-ID"
TTS_LANGUAGE = "id"
AI_MODEL = "openai/gpt-oss-20b"  # Model Groq yang aktif
AI_MAX_TOKENS = 200
AI_TEMPERATURE = 0.7

SYSTEM_PROMPT = (
    "Anda adalah Jarvis, asisten AI yang cerdas, efisien, ramah, dan sedikit formal. "
    "Anda menjawab dalam Bahasa Indonesia dengan gaya ringkas, jelas, dan profesional. "
    "Batasi jawaban maksimal 3-4 kalimat agar cocok untuk diucapkan."
)

# ============================================================
# API KEY MANAGEMENT
# ============================================================
def get_api_key():
    if "groq_api_key" in st.session_state and st.session_state.groq_api_key:
        return st.session_state.groq_api_key
    try:
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY", "")

# ============================================================
# STT (Speech-to-Text)
# ============================================================
def transcribe_audio(audio_bytes):
    try:
        url = "http://www.google.com/speech-api/v2/recognize"
        params = {
            "client": "chromium",
            "lang": STT_LANGUAGE,
            "key": "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw", 
        }
        headers = {"Content-Type": "audio/l16; rate=16000"}
        
        response = requests.post(url, params=params, headers=headers, data=audio_bytes, timeout=15)
        
        for line in response.text.split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if "result" in data and data["result"]:
                    return data["result"][0]["alternative"][0]["transcript"], "ok"
            except json.JSONDecodeError:
                continue
                
        return "Suara tidak terdeteksi atau terlalu pelan. Coba lagi.", "no_speech"
    except Exception as e:
        return f"Error STT: {e}", "error"

# ============================================================
# AI (Groq API)
# ============================================================
def get_ai_response(user_message, chat_history, api_key):
    if not api_key:
        return "API Key Groq belum diisi di sidebar.", "error"
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS,
        )
        return response.choices[0].message.content.strip(), "ok"
    except Exception as e:
        err_msg = str(e)
        if "401" in err_msg:
            return "API Key Groq tidak valid. Periksa kembali.", "error"
        return f"Error AI: {err_msg}", "error"

# ============================================================
# TTS (Text-to-Speech) + Fitur Suara
# ============================================================
def text_to_speech(text, speed="normal"):
    try:
        # Atur kecepatan bicara (slow=True untuk lambat, False untuk normal)
        is_slow = True if speed == "lambat" else False
        tts = gTTS(text=text, lang=TTS_LANGUAGE, slow=is_slow)
        
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return audio_buffer.read()
    except Exception as e:
        st.error(f"Error TTS: {e}")
        return None

def autoplay_audio(audio_bytes):
    """Memutar audio secara otomatis di background."""
    if not audio_bytes:
        return
    try:
        b64 = base64.b64encode(audio_bytes).decode()
        # Menggunakan autoplay dan loop=False
        md = f'''
        <audio autoplay="true" id="jarvis-audio">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
        <script>
            // Script untuk memastikan audio diputar
            var audio = document.getElementById("jarvis-audio");
            if (audio) {{
                audio.play().catch(function(error) {{
                    console.log("Autoplay diblokir browser, butuh interaksi user.");
                }});
            }}
        </script>
        '''
        st.markdown(md, unsafe_allow_html=True)
    except Exception:
        pass

# ============================================================
# MAIN UI & LOGIC
# ============================================================
def main():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_audio_id" not in st.session_state:
        st.session_state.last_audio_id = None
    if "last_tts_audio" not in st.session_state:
        st.session_state.last_tts_audio = None

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Pengaturan Suara")
        
        # Fitur Tambahan: Pengaturan Kecepatan Suara
        tts_speed = st.radio(
            "Kecepatan Bicara Jarvis:",
            ["normal", "lambat"],
            horizontal=True
        )

        st.divider()
        
        st.header("🔑 API Key Groq")
        st.markdown("Dapatkan gratis di [console.groq.com](https://console.groq.com)")
        
        api_key_input = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if api_key_input:
            st.session_state.groq_api_key = api_key_input
        
        api_key = get_api_key()
        if not api_key:
            st.warning("⚠️ API Key Groq wajib diisi!")
            
        st.divider()
        if st.button("🗑️ Hapus Riwayat Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.session_state.last_tts_audio = None
            st.rerun()

    # --- HEADER ---
    st.title("🤖 Jarvis: Asisten Suara AI")
    st.caption("Bicara langsung dengan Jarvis. Jarvis akan otomatis merespon setelah Anda selesai bicara.")

    if not api_key:
        st.info("👈 Silakan isi Groq API Key di sidebar kiri terlebih dahulu.")

    # --- RIWAYAT CHAT ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    st.divider()

    # --- INDIKATOR MIKROFON ---
    st.markdown("### 🎤 Rekam Suara Anda")
    st.caption("Klik mikrofon, bicara, lalu **klik ⏹️ (Stop)**. Jarvis akan langsung merespon dengan suara.")
    
    audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # --- LOGIKA PROSES AUDIO OTOMATIS ---
    if audio_value is not None and api_key:
        current_id = getattr(audio_value, "file_id", None) or getattr(audio_value, "name", None) or id(audio_value)

        if current_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = current_id
            
            audio_bytes = audio_value.read()
            
            # 1. PROSES STT
            with st.spinner("👂 Mendengarkan dan memproses suara..."):
                user_text, stt_status = transcribe_audio(audio_bytes)
                
            if stt_status != "ok":
                st.warning(user_text)
                return

            # Tampilkan Pesan User
            with st.chat_message("user", avatar="🧑"):
                st.markdown(user_text)
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            # 2. PROSES AI
            with st.spinner("🧠 Jarvis sedang berpikir..."):
                history_for_ai = st.session_state.messages[:-1]
                ai_text, ai_status = get_ai_response(user_text, history_for_ai, api_key)
                
            if ai_status != "ok":
                st.error(ai_text)
                return

            # Tampilkan Pesan AI
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(ai_text)
            st.session_state.messages.append({"role": "assistant", "content": ai_text})
            
            # 3. PROSES TTS & AUTOPLAY
            with st.spinner("🔊 Jarvis sedang berbicara..."):
                # Gunakan pengaturan kecepatan dari sidebar
                audio_reply = text_to_speech(ai_text, speed=tts_speed)
                if audio_reply:
                    st.session_state.last_tts_audio = audio_reply
                    autoplay_audio(audio_reply)
            
            st.rerun()

    # --- FITUR TOMBOL ULANGI SUARA ---
    if st.session_state.last_tts_audio:
        st.divider()
        st.markdown("#### 🔊 Kontrol Suara Jarvis")
        col1, col2 = st.columns([1, 1])
        
        with col1:
            # Tombol untuk memutar ulang jika autoplay diblokir browser
            if st.button("▶️ Putar Ulang Suara", use_container_width=True):
                st.audio(st.session_state.last_tts_audio, format="audio/mp3", autoplay=True)
                
        with col2:
            # Menampilkan player manual sebagai cadangan
            st.audio(st.session_state.last_tts_audio, format="audio/mp3")

if __name__ == "__main__":
    main()

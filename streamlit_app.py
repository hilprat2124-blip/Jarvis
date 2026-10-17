"""
==============================================================
🤖 JARVIS WEB AI - Asisten Suara Berbasis Streamlit
==============================================================
Versi: 3.0 (Stabil & Ringan - Tanpa SpeechRecognition)
Fitur:
- Input suara wajib via mikrofon
- STT: Menggunakan HTTP Request langsung ke Google Speech API (Anti Error)
- AI: OpenAI GPT
- TTS: gTTS
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
    page_icon="🤖",
    layout="centered"
)

STT_LANGUAGE = "id-ID"
TTS_LANGUAGE = "id"
AI_MODEL = "gpt-3.5-turbo"
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
    if "openai_api_key" in st.session_state and st.session_state.openai_api_key:
        return st.session_state.openai_api_key
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY", "")

# ============================================================
# SIDEBAR
# ============================================================
def render_sidebar():
    with st.sidebar:
        st.header("⚙️ Pengaturan")
        st.subheader("🔑 OpenAI API Key")
        api_key_input = st.text_input(
            "Masukkan API Key",
            type="password",
            placeholder="sk-...",
            key="api_key_widget"
        )
        if api_key_input:
            st.session_state.openai_api_key = api_key_input
            st.success("✅ API Key tersimpan")

        current_key = get_api_key()
        if current_key:
            st.caption(f"Status: ✅ ({current_key[:8]}...)")
        else:
            st.warning("⚠️ API Key wajib diisi")

        st.divider()
        st.subheader("🔄 Kontrol")
        if st.button("🗑️ Hapus Riwayat Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.rerun()

        st.divider()
        st.subheader("📖 Cara Pakai")
        st.markdown("""
        1. Isi **OpenAI API Key**
        2. Klik tombol **mikrofon** 🎤
        3. Bicara dalam Bahasa Indonesia
        4. Klik **stop** untuk mengirim
        """)

# ============================================================
# STT (Speech-to-Text) - VIA HTTP REQUEST (ANTI ERROR)
# ============================================================
def transcribe_audio(uploaded_audio):
    """
    Transkripsi audio menggunakan Google Speech API via HTTP.
    Tidak memerlukan library SpeechRecognition atau PyAudio.
    """
    try:
        # Baca audio bytes dari streamlit
        audio_bytes = uploaded_audio.read()
        
        # Google Speech API endpoint (gratis, tidak butuh API key pribadi)
        url = "http://www.google.com/speech-api/v2/recognize"
        params = {
            "client": "chromium",
            "lang": STT_LANGUAGE,
            "key": "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw", # Public key Google
        }
        
        # Streamlit audio_input biasanya menghasilkan format WAV
        headers = {"Content-Type": "audio/l16; rate=16000"}
        
        response = requests.post(url, params=params, headers=headers, data=audio_bytes, timeout=15)
        
        # Parsing respons (format JSON per baris)
        for line in response.text.split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if "result" in data and data["result"]:
                    transcript = data["result"][0]["alternative"][0]["transcript"]
                    return transcript, "ok"
            except json.JSONDecodeError:
                continue
                
        return "Maaf, suara tidak terdeteksi atau terlalu pelan. Coba lagi.", "no_speech"

    except requests.exceptions.RequestException as e:
        return f"Error koneksi STT: {e}", "error"
    except Exception as e:
        return f"Error memproses audio: {e}", "error"

# ============================================================
# AI (OpenAI)
# ============================================================
def get_ai_response(user_message, chat_history, api_key):
    if not api_key:
        return "API Key OpenAI belum diisi.", "error"
    try:
        client = OpenAI(api_key=api_key)
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
        return f"Error OpenAI: {e}", "error"

# ============================================================
# TTS (Text-to-Speech)
# ============================================================
def text_to_speech(text):
    try:
        tts = gTTS(text=text, lang=TTS_LANGUAGE, slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return audio_buffer.read()
    except Exception as e:
        st.error(f"Error TTS: {e}")
        return None

def autoplay_audio(audio_bytes):
    if not audio_bytes:
        return
    try:
        b64 = base64.b64encode(audio_bytes).decode()
        md = f'<audio autoplay="true" style="display:none;"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'
        st.markdown(md, unsafe_allow_html=True)
    except Exception:
        pass

# ============================================================
# SESSION STATE
# ============================================================
def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_audio_id" not in st.session_state:
        st.session_state.last_audio_id = None
    if "last_ai_audio" not in st.session_state:
        st.session_state.last_ai_audio = None

# ============================================================
# UI
# ============================================================
def render_chat_history():
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

def main():
    init_session_state()
    render_sidebar()

    st.title("🤖 Jarvis: Asisten Suara AI")
    st.caption("Bicara langsung dengan Jarvis menggunakan mikrofon Anda")
    st.divider()

    api_key = get_api_key()
    if not api_key:
        st.warning("⚠️ **OpenAI API Key belum diisi.** Buka sidebar (⟵) dan isi API Key.")

    if st.session_state.messages:
        render_chat_history()

    st.divider()
    st.markdown("### 🎤 Rekam Suara Anda")
    st.caption("Klik tombol mikrofon, bicara, lalu klik ⏹️ untuk berhenti.")

    # Komponen Mikrofon Wajib
    audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # Proses audio
    if audio_value is not None and api_key:
        # Deteksi audio baru
        current_id = getattr(audio_value, "file_id", None) or getattr(audio_value, "name", None) or id(audio_value)

        if current_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = current_id

            # 1. STT
            with st.spinner("🎧 Mendengarkan..."):
                user_text, stt_status = transcribe_audio(audio_value)

            if stt_status != "ok":
                st.warning(user_text)
                return

            with st.chat_message("user", avatar="🧑"):
                st.markdown(user_text)
            st.session_state.messages.append({"role": "user", "content": user_text})

            # 2. AI
            with st.spinner("🧠 Jarvis berpikir..."):
                history_for_ai = st.session_state.messages[:-1]
                ai_text, ai_status = get_ai_response(user_text, history_for_ai, api_key)

            if ai_status != "ok":
                st.error(ai_text)
                return

            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(ai_text)
            st.session_state.messages.append({"role": "assistant", "content": ai_text})

            # 3. TTS
            with st.spinner("🔊 Menyiapkan suara..."):
                audio_bytes = text_to_speech(ai_text)

            if audio_bytes:
                st.session_state.last_ai_audio = audio_bytes

            # 4. Autoplay
            autoplay_audio(audio_bytes)
            st.rerun()

    # Tombol putar ulang
    if st.session_state.last_ai_audio:
        with st.expander("🔁 Putar ulang suara Jarvis terakhir"):
            st.audio(st.session_state.last_ai_audio, format="audio/mp3")

if __name__ == "__main__":
    main()

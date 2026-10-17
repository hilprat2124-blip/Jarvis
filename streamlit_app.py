"""
==============================================================
🤖 JARVIS WEB AI - Asisten Suara Berbasis Streamlit
==============================================================
Fitur:
- Input suara wajib via mikrofon (st.audio_input)
- Speech-to-Text (STT) via Google Web Speech API
- Otak AI via OpenAI (GPT-3.5/GPT-4)
- Text-to-Speech (TTS) via gTTS (bahasa Indonesia)
- Riwayat percakapan (chat history)
- Auto-play balasan suara Jarvis
==============================================================

Cara menjalankan:
    streamlit run app.py

Syarat:
- Python 3.9+
- Koneksi internet (untuk Google STT & OpenAI API)
- OpenAI API Key
- Browser modern (Chrome/Edge/Firefox)
- HTTPS jika deploy ke server (mikrofon wajib secure context)

==============================================================
"""

import streamlit as st
import speech_recognition as sr
from gtts import gTTS
import io
import os
import tempfile
import base64
from datetime import datetime
from openai import OpenAI

# ============================================================
# 🔧 KONFIGURASI GLOBAL
# ============================================================

# --- Konfigurasi halaman Streamlit (HARUS paling atas) ---
st.set_page_config(
    page_title="Jarvis Web AI",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- Konstanta aplikasi ---
APP_TITLE = "🤖 Jarvis: Asisten Suara AI"
APP_SUBTITLE = "Bicara langsung dengan Jarvis menggunakan mikrofon Anda"

# --- Model & bahasa ---
STT_LANGUAGE = "id-ID"           # Bahasa untuk Speech-to-Text (Indonesia)
TTS_LANGUAGE = "id"              # Bahasa untuk Text-to-Speech
AI_MODEL = "gpt-3.5-turbo"       # Bisa ganti: "gpt-4o", "gpt-4o-mini", "gpt-4-turbo"
AI_MAX_TOKENS = 200
AI_TEMPERATURE = 0.7

# --- System prompt untuk karakter Jarvis ---
SYSTEM_PROMPT = (
    "Anda adalah Jarvis, asisten AI yang cerdas, efisien, ramah, dan sedikit formal. "
    "Anda menjawab dalam Bahasa Indonesia dengan gaya ringkas, jelas, dan profesional. "
    "Jika pertanyaan tidak jelas, ajukan pertanyaan balik yang membantu. "
    "Batasi jawaban maksimal 3-4 kalimat agar cocok untuk diucapkan."
)

# ============================================================
# 🔐 SETUP API KEY (dari sidebar / env / secrets)
# ============================================================

def get_api_key():
    """
    Mengambil OpenAI API Key dengan prioritas:
    1. st.session_state (input user di sidebar)
    2. Streamlit Secrets (untuk deploy)
    3. Environment variable OPENAI_API_KEY
    """
    # 1. Dari session state (input user)
    if "openai_api_key" in st.session_state and st.session_state.openai_api_key:
        return st.session_state.openai_api_key

    # 2. Dari Streamlit Secrets
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass

    # 3. Dari environment variable
    return os.environ.get("OPENAI_API_KEY", "")

# ============================================================
# 🎨 SIDEBAR - Konfigurasi & Info
# ============================================================

def render_sidebar():
    """Menampilkan sidebar untuk konfigurasi API Key dan info."""
    with st.sidebar:
        st.header("⚙️ Pengaturan")

        # --- Input API Key ---
        st.subheader("🔑 OpenAI API Key")
        api_key_input = st.text_input(
            "Masukkan API Key Anda",
            type="password",
            placeholder="sk-...",
            help="Dapatkan API Key di https://platform.openai.com/api-keys",
            key="api_key_widget"
        )

        if api_key_input:
            st.session_state.openai_api_key = api_key_input
            st.success("✅ API Key tersimpan di sesi ini")

        # Cek apakah API Key tersedia
        current_key = get_api_key()
        if current_key:
            st.caption(f"Status: ✅ Terkonfigurasi ({current_key[:8]}...)")
        else:
            st.caption("Status: ❌ Belum dikonfigurasi")
            st.warning("⚠️ API Key wajib diisi untuk menggunakan Jarvis.")

        st.divider()

        # --- Info Model ---
        st.subheader("🧠 Model AI")
        st.caption(f"Model: `{AI_MODEL}`")
        st.caption(f"Bahasa STT: `{STT_LANGUAGE}`")
        st.caption(f"Bahasa TTS: `{TTS_LANGUAGE}`")

        st.divider()

        # --- Tombol Reset ---
        st.subheader("🔄 Kontrol")
        if st.button("🗑️ Hapus Riwayat Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.rerun()

        st.divider()

        # --- Petunjuk ---
        st.subheader("📖 Cara Pakai")
        st.markdown("""
        1. Isi **OpenAI API Key** di atas
        2. Klik tombol **mikrofon** 🎤 di halaman utama
        3. Bicara dalam Bahasa Indonesia
        4. Klik **stop** untuk mengirim
        5. Tunggu Jarvis merespons dengan suara
        """)

        st.divider()
        st.caption("⚠️ **Catatan Deploy:**")
        st.caption(
            "Jika di-deploy ke server, wajib pakai **HTTPS** "
            "agar mikrofon berfungsi (kebijakan browser)."
        )

# ============================================================
# 🎙️ FUNGSI STT (Speech-to-Text)
# ============================================================

def transcribe_audio(uploaded_audio):
    """
    Mengubah audio dari mikrofon menjadi teks.
    
    Args:
        uploaded_audio: File audio dari st.audio_input (UploadedFile/BytesIO)
    
    Returns:
        tuple: (teks_hasil, status) 
               status: "ok" | "no_speech" | "error"
    """
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    tmp_path = None
    try:
        # Streamlit audio_input menghasilkan file audio (WAV biasanya)
        # Kita perlu simpan ke temp file karena SpeechRecognition butuh path
        audio_bytes = uploaded_audio.read()

        # Reset pointer agar bisa dibaca ulang
        try:
            uploaded_audio.seek(0)
        except Exception:
            pass

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # Proses audio
        with sr.AudioFile(tmp_path) as source:
            audio_data = recognizer.record(source)

        # Transkripsi via Google Web Speech API
        text = recognizer.recognize_google(audio_data, language=STT_LANGUAGE)
        return text, "ok"

    except sr.UnknownValueError:
        return "Maaf, saya tidak bisa memahami suara tersebut. Coba bicara lebih jelas.", "no_speech"
    except sr.RequestError as e:
        return f"Layanan STT error: {e}. Periksa koneksi internet Anda.", "error"
    except Exception as e:
        return f"Terjadi kesalahan saat memproses audio: {e}", "error"
    finally:
        # Bersihkan file temp
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

# ============================================================
# 🧠 FUNGSI AI (OpenAI)
# ============================================================

def get_ai_response(user_message, chat_history, api_key):
    """
    Mendapatkan respons dari OpenAI.
    
    Args:
        user_message (str): Pesan user
        chat_history (list): Riwayat percakapan [{"role":..., "content":...}]
        api_key (str): OpenAI API Key
    
    Returns:
        tuple: (respons_teks, status)  status: "ok" | "error"
    """
    if not api_key:
        return "API Key OpenAI belum diisi. Silakan isi di sidebar.", "error"

    try:
        client = OpenAI(api_key=api_key)

        # Susun messages: system + history + pesan baru
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
        err_str = str(e).lower()
        if "api key" in err_str or "authentication" in err_str or "401" in err_str:
            return "❌ API Key tidak valid. Periksa kembali di sidebar.", "error"
        if "quota" in err_str or "insufficient" in err_str or "429" in err_str:
            return "❌ Kuota OpenAI habis atau rate-limit. Cek billing Anda.", "error"
        if "timeout" in err_str or "connection" in err_str:
            return "❌ Gagal terhubung ke OpenAI. Cek koneksi internet.", "error"
        return f"❌ Error OpenAI: {e}", "error"

# ============================================================
# 🔊 FUNGSI TTS (Text-to-Speech)
# ============================================================

def text_to_speech(text):
    """
    Mengubah teks menjadi audio MP3 dengan gTTS.
    
    Returns:
        bytes: audio MP3 bytes, atau None jika error
    """
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
    """
    Memutar audio secara otomatis di browser menggunakan base64 embed.
    Ini trick agar audio autoplay tanpa tombol play manual.
    """
    if not audio_bytes:
        return
    try:
        b64 = base64.b64encode(audio_bytes).decode()
        md = f"""
            <audio autoplay="true" style="display:none;">
                <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
            </audio>
        """
        st.markdown(md, unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Autoplay gagal: {e}")

# ============================================================
# 💬 INISIALISASI SESSION STATE
# ============================================================

def init_session_state():
    """Inisialisasi variabel session state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []      # Riwayat chat
    if "last_audio_id" not in st.session_state:
        st.session_state.last_audio_id = None  # Untuk deteksi audio baru
    if "last_ai_audio" not in st.session_state:
        st.session_state.last_ai_audio = None  # Audio balasan AI terakhir

# ============================================================
# 🖥️ FUNGSI UI UTAMA
# ============================================================

def render_chat_history():
    """Menampilkan riwayat percakapan dengan bubble chat."""
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

def render_header():
    """Menampilkan header aplikasi."""
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)
    st.divider()

def render_mic_widget():
    """Menampilkan widget mikrofon wajib."""
    st.markdown("### 🎤 Rekam Suara Anda")
    st.caption("Klik tombol mikrofon di bawah, bicara, lalu klik ⏹️ untuk berhenti.")
    audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")
    return audio_value

# ============================================================
# 🚀 MAIN FUNCTION
# ============================================================

def main():
    init_session_state()
    render_sidebar()
    render_header()

    # --- Cek API Key ---
    api_key = get_api_key()
    if not api_key:
        st.warning(
            "⚠️ **OpenAI API Key belum diisi.** "
            "Buka sidebar (⟵) dan isi API Key terlebih dahulu."
        )

    # --- Riwayat chat ---
    if st.session_state.messages:
        render_chat_history()

    # --- Widget mikrofon ---
    st.divider()
    audio_value = render_mic_widget()

    # ============================================================
    # PROSES AUDIO BARU
    # ============================================================
    if audio_value is not None:
        # Deteksi apakah ini audio baru (bandingkan id)
        current_id = getattr(audio_value, "file_id", None) or getattr(audio_value, "name", None) or id(audio_value)

        # Hanya proses jika audio berbeda dari yang terakhir & API Key ada
        if current_id != st.session_state.last_audio_id and api_key:
            st.session_state.last_audio_id = current_id

            # --- 1. STT ---
            with st.spinner("🎧 Mendengarkan..."):
                user_text, stt_status = transcribe_audio(audio_value)

            if stt_status != "ok":
                st.warning(user_text)
                return

            # Tampilkan & simpan pesan user
            with st.chat_message("user", avatar="🧑"):
                st.markdown(user_text)
            st.session_state.messages.append({"role": "user", "content": user_text})

            # --- 2. AI Response ---
            with st.spinner("🧠 Jarvis sedang berpikir..."):
                # Ambil history tanpa pesan user terbaru (karena sudah ditambahkan)
                history_for_ai = st.session_state.messages[:-1]
                ai_text, ai_status = get_ai_response(user_text, history_for_ai, api_key)

            if ai_status != "ok":
                st.error(ai_text)
                return

            # Tampilkan & simpan pesan AI
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(ai_text)
            st.session_state.messages.append({"role": "assistant", "content": ai_text})

            # --- 3. TTS ---
            with st.spinner("🔊 Menyiapkan suara Jarvis..."):
                audio_bytes = text_to_speech(ai_text)

            if audio_bytes:
                st.session_state.last_ai_audio = audio_bytes

            # --- 4. Autoplay ---
            autoplay_audio(audio_bytes)

            # --- 5. Rerun agar riwayat tampil rapi ---
            st.rerun()

    # --- Putar ulang audio balasan terakhir (opsional) ---
    if st.session_state.last_ai_audio:
        with st.expander("🔁 Putar ulang suara Jarvis terakhir"):
            st.audio(st.session_state.last_ai_audio, format="audio/mp3")

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()

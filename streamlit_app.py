import streamlit as st
import streamlit.components.v1 as components
import io
import os
import json
import base64
import asyncio
import re
import requests
import edge_tts
from openai import OpenAI

# ============================================================
# KONFIGURASI
# ============================================================
st.set_page_config(page_title="J.A.R.V.I.S", page_icon="🤖", layout="centered")

# Pengaturan Suara
VOICE_EN = "en-GB-RyanNeural"   # Pria British (JARVIS Style)
VOICE_ID = "id-ID-ArdiNeural"   # Pria Indonesia
VOICE_RATE = "-10%"             # Lebih tenang
VOICE_PITCH = "-15Hz"           # Lebih berat (Iron Man style)

AI_MODEL = "openai/gpt-oss-20b"

SYSTEM_PROMPT = (
    "Anda adalah J.A.R.V.I.S, asisten AI dari Iron Man. Anda sangat cerdas, tenang, formal, dan efisien. "
    "ATURAN BAHASA: Anda harus merespon menggunakan bahasa yang sama dengan yang digunakan user. "
    "Jika user bertanya dalam Bahasa Inggris, jawab dalam Bahasa Inggris dengan gaya British formal. "
    "Jika user bertanya dalam Bahasa Indonesia, jawab dalam Bahasa Indonesia dengan gaya formal. "
    "Batasi jawaban maksimal 3-4 kalimat."
)

# ============================================================
# API KEY & STT
# ============================================================
def get_api_key():
    if "groq_api_key" in st.session_state and st.session_state.groq_api_key:
        return st.session_state.groq_api_key
    return os.environ.get("GROQ_API_KEY", "")

def transcribe_audio(audio_bytes):
    try:
        url = "http://www.google.com/speech-api/v2/recognize"
        # Gunakan deteksi bahasa otomatis atau set ke 'en-US' untuk default lebih baik
        # Google API butuh spesifik bahasa, jadi kita set 'id-ID' dulu, 
        # jika gagal kita bisa fallback. (Catatan: Google API gratis tidak mendukung auto-detect murni)
        params = {"client": "chromium", "lang": "id-ID", "key": "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"}
        headers = {"Content-Type": "audio/l16; rate=16000"}
        response = requests.post(url, params=params, headers=headers, data=audio_bytes, timeout=15)
        
        for line in response.text.split("\n"):
            if not line.strip(): continue
            try:
                data = json.loads(line)
                if "result" in data and data["result"]:
                    return data["result"][0]["alternative"][0]["transcript"], "ok"
            except json.JSONDecodeError:
                continue
        return "Suara tidak terdeteksi.", "no_speech"
    except Exception as e:
        return f"Error STT: {e}", "error"

# ============================================================
# AI (Groq)
# ============================================================
def get_ai_response(user_message, chat_history, api_key):
    if not api_key: return "API Key Groq belum diisi.", "error"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=AI_MODEL, messages=messages, temperature=0.7, max_tokens=200,
        )
        return response.choices[0].message.content.strip(), "ok"
    except Exception as e:
        return f"Error AI: {e}", "error"

# ============================================================
# TTS (Deteksi Bahasa Otomatis)
# ============================================================
def detect_language(text):
    """
    Deteksi sederhana apakah teks berbahasa Inggris atau Indonesia.
    Menggunakan pencocokan kata umum (stopwords).
    """
    text_lower = text.lower()
    
    # Kata-kata umum bahasa Inggris
    en_words = ["the", "and", "is", "to", "in", "you", "that", "it", "for", "on", "with", "as", "i", "am", "your"]
    # Kata-kata umum bahasa Indonesia
    id_words = ["yang", "dan", "di", "itu", "ini", "dengan", "untuk", "saya", "kamu", "adalah", "tidak", "bisa", "akan"]

    en_count = sum(1 for word in re.findall(r'\b\w+\b', text_lower) if word in en_words)
    id_count = sum(1 for word in re.findall(r'\b\w+\b', text_lower) if word in id_words)

    # Jika lebih banyak kata Inggris, anggap Inggris
    if en_count > id_count:
        return "en"
    return "id"

def text_to_speech(text):
    try:
        # Deteksi bahasa dari teks balasan AI
        lang = detect_language(text)
        
        # Pilih suara dan logat berdasarkan bahasa
        if lang == "en":
            voice = VOICE_EN
            # Logat British (sudah otomatis dari voice)
        else:
            voice = VOICE_ID
            # Logat Indonesia (sudah otomatis dari voice)

        async def _generate_audio():
            # Inisialisasi Edge TTS dengan pengaturan Pitch & Rate khusus
            communicate = edge_tts.Communicate(text, voice, rate=VOICE_RATE, pitch=VOICE_PITCH)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data

        # Jalankan async loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(_generate_audio())
        loop.close()
        return audio_bytes, lang
    except Exception as e:
        st.error(f"Error TTS: {e}")
        return None, "id"

# ============================================================
# 🔥 AUTO-PLAY AUDIO
# ============================================================
def play_audio_auto(audio_bytes):
    if not audio_bytes: return
    b64 = base64.b64encode(audio_bytes).decode()
    
    html = f"""
    <audio id="jarvis-audio" autoplay>
        <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
    </audio>
    <script>
        var audio = document.getElementById("jarvis-audio");
        var playPromise = audio.play();
        if (playPromise !== undefined) {{
            playPromise.catch(function(error) {{
                document.body.addEventListener('click', function() {{
                    audio.play();
                }}, {{ once: true }});
            }});
        }}
    </script>
    """
    components.html(html, height=0)

# ============================================================
# MAIN UI
# ============================================================
def main():
    if "messages" not in st.session_state: st.session_state.messages = []
    if "last_audio_id" not in st.session_state: st.session_state.last_audio_id = None

    # SIDEBAR
    with st.sidebar:
        st.header("⚙️ Sistem J.A.R.V.I.S")
        api_key_input = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if api_key_input: st.session_state.groq_api_key = api_key_input
        api_key = get_api_key()
        if not api_key: st.warning("⚠️ API Key dibutuhkan.")
        
        st.divider()
        st.caption("Mode: Poliglot (Auto-Detect)")
        st.caption("Logat EN: British (Ryan)")
        st.caption("Logat ID: Indonesia (Ardi)")
        
        if st.button("🗑️ Hapus Memori", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.rerun()

    # HEADER
    st.title("🤖 J.A.R.V.I.S")
    st.caption("Silakan bicara dalam Bahasa Indonesia atau Bahasa Inggris.")

    if not api_key:
        st.info("👈 Silakan isi Groq API Key di panel kiri.")

    # RIWAYAT CHAT
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    st.divider()

    # MIKROFON
    st.markdown("### 🎤 Meminta Perintah")
    audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # LOGIKA
    if audio_value is not None and api_key:
        current_id = getattr(audio_value, "file_id", None) or id(audio_value)

        if current_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = current_id
            audio_bytes = audio_value.read()
            
            # 1. STT (Sementara kita set ke id-ID karena Google API gratis susah auto-detect murni)
            with st.spinner("👂 Memproses suara..."):
                user_text, stt_status = transcribe_audio(audio_bytes)
                
            if stt_status != "ok":
                st.warning(user_text)
                return

            with st.chat_message("user", avatar="🧑"):
                st.markdown(user_text)
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            # 2. AI
            with st.spinner("🧠 Menganalisis..."):
                history_for_ai = st.session_state.messages[:-1]
                ai_text, ai_status = get_ai_response(user_text, history_for_ai, api_key)
                
            if ai_status != "ok":
                st.error(ai_text)
                return

            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(ai_text)
            st.session_state.messages.append({"role": "assistant", "content": ai_text})
            
            # 3. TTS & AUTO-PLAY (Deteksi bahasa otomatis)
            with st.spinner("🔊 Merespon..."):
                audio_reply, detected_lang = text_to_speech(ai_text)
                if audio_reply:
                    # Tampilkan bahasa yang terdeteksi (untuk memastikan logatnya pas)
                    st.toast(f"Jarvis merespon dalam bahasa: {'Inggris (British)' if detected_lang == 'en' else 'Indonesia'}")
                    play_audio_auto(audio_reply)

if __name__ == "__main__":
    main()

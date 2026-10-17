import streamlit as st
import streamlit.components.v1 as components
import io
import os
import json
import base64
import asyncio
import requests
import edge_tts
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
VOICE_MODEL = "id-ID-ArdiNeural" # Suara Pria Indonesia
VOICE_RATE = "+5%"
AI_MODEL = "openai/gpt-oss-20b"  

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
            if not line.strip(): continue
            try:
                data = json.loads(line)
                if "result" in data and data["result"]:
                    return data["result"][0]["alternative"][0]["transcript"], "ok"
            except json.JSONDecodeError:
                continue
        return "Suara tidak terdeteksi atau terlalu pelan.", "no_speech"
    except Exception as e:
        return f"Error STT: {e}", "error"

# ============================================================
# AI (Groq API)
# ============================================================
def get_ai_response(user_message, chat_history, api_key):
    if not api_key:
        return "API Key Groq belum diisi.", "error"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip(), "ok"
    except Exception as e:
        return f"Error AI: {e}", "error"

# ============================================================
# TTS (Text-to-Speech) - EDGE TTS
# ============================================================
def text_to_speech(text):
    try:
        async def _generate_audio():
            communicate = edge_tts.Communicate(text, VOICE_MODEL, rate=VOICE_RATE)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data

        # Jalankan async loop dengan aman
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop and loop.is_running():
            # Jika loop sudah jalan (jarang terjadi di Streamlit), buat task baru
            import nest_asyncio
            nest_asyncio.apply()
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(_generate_audio())
        loop.close()
        return audio_bytes
    except Exception as e:
        st.error(f"Error TTS: {e}")
        return None

# ============================================================
# AUTOPLAY AUDIO (TRIK AMPUH STREAMLIT)
# ============================================================
def play_audio_auto(audio_bytes):
    """Memaksa browser memutar audio via komponen HTML murni."""
    if not audio_bytes:
        return
    
    # Encode base64
    b64 = base64.b64encode(audio_bytes).decode()
    
    # HTML + JS yang memaksa autoplay
    html_code = f"""
    <script>
        // Trik membangunkan audio context browser
        var audio = new Audio("data:audio/mp3;base64,{b64}");
        audio.play().catch(function(error) {{
            console.log("Autoplay dicegah browser. Menunggu interaksi user...");
            // Jika dicegah, pasang listener agar begitu user klik layar, suara langsung bunyi
            document.body.addEventListener('click', function() {{
                audio.play();
            }}, {{ once: true }});
        }});
    </script>
    """
    # Render komponen dengan tinggi 0 agar tidak merusak UI
    components.html(html_code, height=0)

# ============================================================
# MAIN UI & LOGIC
# ============================================================
def main():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_audio_id" not in st.session_state:
        st.session_state.last_audio_id = None

    # SIDEBAR
    with st.sidebar:
        st.header("⚙️ Pengaturan")
        api_key_input = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if api_key_input:
            st.session_state.groq_api_key = api_key_input
        api_key = get_api_key()
        if not api_key:
            st.warning("⚠️ API Key Groq wajib diisi!")
            
        if st.button("🗑️ Hapus Riwayat Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.rerun()

    # HEADER
    st.title("🤖 Jarvis: Asisten Suara AI")
    st.caption("Bicara langsung. Jarvis akan otomatis merespon dengan suara.")

    if not api_key:
        st.info("👈 Silakan isi Groq API Key di sidebar.")

    # RIWAYAT CHAT
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    st.divider()

    # MIKROFON
    st.markdown("### 🎤 Rekam Suara Anda")
    st.caption("Klik mikrofon, bicara, lalu **klik ⏹️ (Stop)** untuk mengirim.")
    
    # Widget audio
    audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # LOGIKA
    if audio_value is not None and api_key:
        current_id = getattr(audio_value, "file_id", None) or getattr(audio_value, "name", None) or id(audio_value)

        if current_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = current_id
            audio_bytes = audio_value.read()
            
            # 1. STT
            with st.spinner("👂 Mendengarkan..."):
                user_text, stt_status = transcribe_audio(audio_bytes)
                
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
            
            # 3. TTS & AUTOPLAY
            with st.spinner("🔊 Jarvis menjawab..."):
                audio_reply = text_to_speech(ai_text)
                if audio_reply:
                    play_audio_auto(audio_reply)
            
            # Tampilkan tombol cadangan jika user ingin mendengar ulang
            if audio_reply:
                with st.expander("🔈 Suara tidak otomatis keluar? Klik di sini"):
                    st.audio(audio_reply, format="audio/mp3")
            
            st.rerun()

if __name__ == "__main__":
    main()

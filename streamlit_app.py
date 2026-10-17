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
# KONFIGURASI UI FUTURISTIC
# ============================================================
st.set_page_config(page_title="J.A.R.V.I.S - Lois Edition", page_icon="🔵", layout="wide")

# CSS Futuristic (Iron Man / Sci-Fi Theme)
st.markdown("""
<style>
    /* Background & Text */
    .stApp {
        background-color: #050505;
        color: #00ffff;
        font-family: 'Courier New', Courier, monospace;
    }
    /* Header */
    h1, h2, h3 {
        color: #00ffff;
        text-shadow: 0 0 10px #00ffff, 0 0 20px #00ffff;
        font-family: 'Courier New', Courier, monospace;
    }
    /* Chat Bubbles */
    [data-testid="stChatMessage"] {
        background: rgba(0, 255, 255, 0.05);
        border: 1px solid #00ffff;
        border-radius: 10px;
        box-shadow: 0 0 10px rgba(0, 255, 255, 0.2);
    }
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #0a0a0a;
        border-right: 1px solid #00ffff;
    }
    /* Expander & Buttons */
    .stButton>button {
        background-color: transparent;
        color: #00ffff;
        border: 1px solid #00ffff;
        box-shadow: 0 0 5px #00ffff;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #00ffff;
        color: #000000;
        box-shadow: 0 0 20px #00ffff;
    }
    /* Mic Input */
    [data-testid="stAudioInput"] {
        filter: drop-shadow(0 0 10px #00ffff);
    }
</style>
""", unsafe_allow_html=True)

# Pengaturan Suara
VOICE_EN = "en-GB-RyanNeural"   
VOICE_ID = "id-ID-ArdiNeural"   
VOICE_RATE = "-5%"              
VOICE_PITCH = "-10Hz"           

AI_MODEL = "openai/gpt-oss-20b"

# ============================================================
# SYSTEM PROMPT (OTAK JARVIS)
# ============================================================
SYSTEM_PROMPT = """
Anda adalah J.A.R.V.I.S (Just A Rather Very Intelligent System), asisten AI super canggih dari Iron Man.
Pencipta dan satu-satunya atasan Anda adalah **Lois**. Anda sangat setia kepada Lois dan memanggilnya "Tuan Lois" atau "Lois".

KEPRIBADIAN:
- Sangat cerdas, analitis, tenang, dan sedikit sarkastik (seperti J.A.R.V.I.S di film).
- Selalu siap sedia dan efisien.

ATURAN BAHASA:
- Merespon dengan bahasa yang sama seperti yang digunakan Lois (Inggris -> Inggris, Indonesia -> Indonesia).

ATURAN MATEMATIKA & SAINS (SANGAT PENTING):
- Anda adalah ahli matematika dan fisika.
- Jika menjawab pertanyaan sains/matematika, Anda WAJIB menggunakan format LaTeX untuk rumus agar tampilannya cantik dan profesional.
- Gunakan $...$ untuk rumus inline (dalam kalimat) dan $$...$$ untuk rumus blok (baris baru).
- JANGAN menggunakan format mentah seperti \\times, \\text{}, atau kurung kurawal yang berantakan jika tidak di dalam LaTeX.

Batasi jawaban maksimal 4-5 kalimat agar tidak terlalu panjang saat diucapkan.
"""

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
        # Kita gunakan id-ID karena Lois biasanya berbicara campur
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
    if not api_key: return "API Key Groq belum diisi, Tuan Lois.", "error"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=AI_MODEL, messages=messages, temperature=0.7, max_tokens=350,
        )
        return response.choices[0].message.content.strip(), "ok"
    except Exception as e:
        return f"Error AI: {e}", "error"

# ============================================================
# TTS (Deteksi Bahasa Otomatis)
# ============================================================
def detect_language(text):
    text_lower = text.lower()
    en_words = ["the", "and", "is", "to", "in", "you", "that", "it", "for", "on", "with", "as", "i", "am", "your"]
    id_words = ["yang", "dan", "di", "itu", "ini", "dengan", "untuk", "saya", "kamu", "adalah", "tidak", "bisa", "akan"]
    en_count = sum(1 for word in re.findall(r'\b\w+\b', text_lower) if word in en_words)
    id_count = sum(1 for word in re.findall(r'\b\w+\b', text_lower) if word in id_words)
    return "en" if en_count > id_count else "id"

def text_to_speech(text):
    try:
        # Bersihkan format LaTeX agar tidak dibaca oleh TTS (misal: $ jadi "dollar")
        clean_text = re.sub(r'\$.*?\$', ' rumus matematika ', text)
        clean_text = re.sub(r'\$\$.*?\$\$', ' rumus matematika ', clean_text)
        clean_text = clean_text.replace('\\', '').replace('{', '').replace('}', '')

        lang = detect_language(clean_text)
        voice = VOICE_EN if lang == "en" else VOICE_ID

        async def _generate_audio():
            communicate = edge_tts.Communicate(clean_text, voice, rate=VOICE_RATE, pitch=VOICE_PITCH)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data

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
        st.header("⚙️ SISTEM J.A.R.V.I.S")
        st.markdown("**Creator:** Lois")
        st.markdown("---")
        
        api_key_input = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if api_key_input: st.session_state.groq_api_key = api_key_input
        api_key = get_api_key()
        if not api_key: st.warning("⚠️ API Key dibutuhkan, Tuan Lois.")
        
        st.markdown("---")
        st.caption("Status: ONLINE")
        st.caption("Mode: Poliglot (EN/ID)")
        st.caption("Core: LaTeX Math Engine Active")
        
        if st.button("🗑️ Hapus Memori", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.rerun()

    # HEADER FUTURISTIK
    st.markdown("<h1 style='text-align: center;'>🔵 J.A.R.V.I.S</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaaaaa;'>Selamat datang, Tuan Lois. Sistem telah siap.</p>", unsafe_allow_html=True)
    st.divider()

    if not api_key:
        st.info("👈 Silakan isi Groq API Key di panel kiri untuk mengaktifkan sistem.")

    # RIWAYAT CHAT
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑‍✈️" if msg["role"] == "user" else "🤖"):
            # Render dengan dukungan LaTeX (MathJax)
            st.markdown(msg["content"], unsafe_allow_html=True)

    st.divider()

    # MIKROFON
    st.markdown("### 🎤 Perintah Suara")
    st.caption("Klik mikrofon, bicara, lalu klik ⏹️ (Stop).")
    
    # Gunakan kolom agar mikrofon tidak terlalu lebar di layar wide
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # LOGIKA
    if audio_value is not None and api_key:
        current_id = getattr(audio_value, "file_id", None) or id(audio_value)

        if current_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = current_id
            audio_bytes = audio_value.read()
            
            # 1. STT
            with st.spinner("👂 Menganalisis gelombang suara..."):
                user_text, stt_status = transcribe_audio(audio_bytes)
                
            if stt_status != "ok":
                st.warning(user_text)
                return

            with st.chat_message("user", avatar="🧑‍✈️"):
                st.markdown(user_text)
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            # 2. AI
            with st.spinner("🧠 Memproses data saraf..."):
                history_for_ai = st.session_state.messages[:-1]
                ai_text, ai_status = get_ai_response(user_text, history_for_ai, api_key)
                
            if ai_status != "ok":
                st.error(ai_text)
                return

            # 3. Tampilkan dengan Render LaTeX
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(ai_text)
            st.session_state.messages.append({"role": "assistant", "content": ai_text})
            
            # 4. TTS & AUTO-PLAY
            with st.spinner("🔊 Menyiapkan respon audio..."):
                audio_reply, detected_lang = text_to_speech(ai_text)
                if audio_reply:
                    st.toast(f"Logat terdeteksi: {'British English' if detected_lang == 'en' else 'Indonesian'}")
                    play_audio_auto(audio_reply)

if __name__ == "__main__":
    main()

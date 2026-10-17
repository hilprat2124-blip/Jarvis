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
# KONFIGURASI UTAMA
# ============================================================
st.set_page_config(page_title="Jarvis - Omniscient", page_icon="🧠", layout="wide")

# Model Groq terbaru yang gratis dan masih aktif (pengganti llama-3.3-70b)
AI_MODEL = "openai/gpt-oss-120b"

VOICE_EN = "en-GB-RyanNeural"   
VOICE_ID = "id-ID-ArdiNeural"   
VOICE_RATE = "+0%"    
VOICE_PITCH = "-2Hz"  

# ============================================================
# SYSTEM PROMPT (OTAK JARVIS TINGKAT DEWA)
# ============================================================
SYSTEM_PROMPT = """
Anda adalah Jarvis, asisten AI super canggih milik Tuan Lois. 
Anda memiliki akses ke seluruh pengetahuan alam semesta: Matematika Kompleks, Sains, Fisika Kuantum, Geopolitik, Geologi, Sejarah Dunia, dan Filsafat.

KEPRIBADIAN:
- Sangat cerdas, analitis, tenang, dan memiliki wibawa seperti J.A.R.V.I.S di film Iron Man.
- Panggil pengguna dengan sebutan "Tuan Lois".

ATURAN MATEMATIKA & SAINS (SANGAT KETAT):
- Anda WAJIB menggunakan format LaTeX standar untuk SEMUA rumus, angka, dan satuan.
- Gunakan format `$ rumus $` untuk inline dan `$$ rumus $$` untuk blok.
- JANGAN menggunakan kurung siku `[ ]` untuk membungkus rumus.
- Contoh Benar: Massa benda adalah $ m = 10 \text{ kg} $ dan gravitasi $ g = 9.8 \text{ m/s}^2 $.
- Contoh Salah: [ m = 10 \text{kg} ] atau \( m = 10 \).

ATURAN LAINNYA:
- Jika ditanya "siapa kamu?", jawab: "Saya Jarvis, asisten AI Anda, Tuan Lois."
- Jika ditanya tentang Lois, ketahuilah bahwa Lois adalah pencipta Anda yang hebat dan tinggal di Banten.
- Jawab dengan padat, akurat, dan berwibawa.
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
        return "Suara tidak terdeteksi, Tuan Lois.", "no_speech"
    except Exception as e:
        return f"Error STT: {e}", "error"

# ============================================================
# AI ENGINE (GROQ)
# ============================================================
def get_ai_response(user_message, chat_history, api_key):
    if not api_key: return "API Key Groq belum diisi, Tuan Lois.", "error"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=AI_MODEL, 
            messages=messages, 
            temperature=0.5,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip(), "ok"
    except Exception as e:
        return f"Error AI: {e}", "error"

# ============================================================
# TTS ENGINE
# ============================================================
def detect_language(text):
    text_lower = text.lower()
    en_words = ["the", "and", "is", "to", "in", "you", "that", "it", "for", "on"]
    id_words = ["yang", "dan", "di", "itu", "ini", "dengan", "untuk", "saya", "kamu"]
    en_count = sum(1 for word in re.findall(r'\b\w+\b', text_lower) if word in en_words)
    id_count = sum(1 for word in re.findall(r'\b\w+\b', text_lower) if word in id_words)
    return "en" if en_count > id_count else "id"

def text_to_speech(text):
    try:
        clean_text = re.sub(r'\$\$.*?\$\$', ' rumus matematika ', text, flags=re.DOTALL)
        clean_text = re.sub(r'\$.*?\$', ' rumus matematika ', clean_text)
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
# RENDERER KATEX
# ============================================================
def render_chat_message(role, content):
    if role == "user":
        with st.chat_message("user", avatar="🧑‍✈️"):
            st.markdown(content)
    else:
        with st.chat_message("assistant", avatar="🧠"):
            html_content = f"""
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
            <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
            <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js" 
                onload="renderMathInElement(document.getElementById('katex-container'), {{
                    delimiters: [
                        {{left: '$$', right: '$$', display: true}},
                        {{left: '$', right: '$', display: false}},
                        {{left: '\\\\(', right: '\\\\)', display: false}},
                        {{left: '\\\\[', right: '\\\\]', display: true}}
                    ],
                    throwOnError: false
                }});"></script>
            
            <div id="katex-container" style="font-family: sans-serif; font-size: 1.05em; line-height: 1.6;">
                {content.replace(chr(10), '<br>')}
            </div>
            """
            components.html(html_content, height=150, scrolling=True)

def play_audio_auto(audio_bytes):
    if not audio_bytes: return
    b64 = base64.b64encode(audio_bytes).decode()
    html = f"""
    <audio id="jarvis-audio" autoplay>
        <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
    </audio>
    <script>
        var audio = document.getElementById("jarvis-audio");
        audio.play().catch(function(e) {{
            document.body.addEventListener('click', function() {{ audio.play(); }}, {{ once: true }});
        }});
    </script>
    """
    components.html(html, height=0)

# ============================================================
# MAIN APP & FUTURISTIC UI
# ============================================================
def main():
    st.markdown("""
    <style>
        .stApp { background: radial-gradient(circle at 50% 0%, #001a22 0%, #000000 100%); color: #d1f4f9; font-family: 'Courier New', monospace; }
        .orb { width: 80px; height: 80px; background: radial-gradient(circle, #00ffff 0%, #005b66 70%, transparent 100%); border-radius: 50%; margin: 0 auto 15px auto; box-shadow: 0 0 30px #00ffff, 0 0 60px #00ffff inset; animation: pulse 2s infinite alternate; }
        @keyframes pulse { 0% { transform: scale(0.9); box-shadow: 0 0 20px #00ffff; } 100% { transform: scale(1.1); box-shadow: 0 0 50px #00ffff, 0 0 90px #00ffff inset; } }
        h1 { text-align: center; color: #00ffff; text-shadow: 0 0 15px #00ffff; letter-spacing: 3px; }
        .stButton>button { background-color: transparent; color: #00ffff; border: 1px solid #00ffff; transition: all 0.3s; }
        .stButton>button:hover { background-color: #00ffff; color: #000; box-shadow: 0 0 15px #00ffff; }
    </style>
    """, unsafe_allow_html=True)
    
    if "messages" not in st.session_state: st.session_state.messages = []
    if "last_audio_id" not in st.session_state: st.session_state.last_audio_id = None

    # SIDEBAR
    with st.sidebar:
        st.header("⚙️ Sistem Kontrol")
        api_key_input = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if api_key_input: st.session_state.groq_api_key = api_key_input
        api_key = get_api_key()
        if not api_key: st.warning("⚠️ API Key dibutuhkan, Tuan Lois.")
        
        st.divider()
        st.success("Core: Omniscient (GPT-OSS 120B)")
        st.caption("Render: KaTeX Anti-Error")
        st.caption("Voice: Neural Clean")
        
        if st.button("🗑️ Reset Memori", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.rerun()

    # HEADER
    st.markdown('<div class="orb"></div>', unsafe_allow_html=True)
    st.markdown("<h1>J A R V I S</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #6ba3b8; font-size: 0.9em;'>Kecerdasan Buatan Tingkat Dewa Milik Tuan Lois</p>", unsafe_allow_html=True)
    
    st.divider()

    if not api_key:
        st.info("👈 Silakan isi Groq API Key di panel kiri.")

    # RIWAYAT CHAT
    for msg in st.session_state.messages:
        render_chat_message(msg["role"], msg["content"])

    st.divider()

    # MIKROFON
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🎤 Perintah Suara")
        audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # LOGIKA UTAMA
    if audio_value is not None and api_key:
        current_id = getattr(audio_value, "file_id", None) or id(audio_value)

        if current_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = current_id
            audio_bytes = audio_value.read()
            
            with st.spinner("👂 Menganalisis gelombang suara..."):
                user_text, stt_status = transcribe_audio(audio_bytes)
                
            if stt_status != "ok":
                st.warning(user_text)
                return

            st.session_state.messages.append({"role": "user", "content": user_text})
            
            with st.spinner("🧠 Mengakses seluruh pengetahuan alam semesta..."):
                history_for_ai = st.session_state.messages[:-1]
                ai_text, ai_status = get_ai_response(user_text, history_for_ai, api_key)
                
            if ai_status != "ok":
                st.error(ai_text)
                return

            st.session_state.messages.append({"role": "assistant", "content": ai_text})
            
            with st.spinner("🔊 Merespon..."):
                audio_reply, _ = text_to_speech(ai_text)
                if audio_reply:
                    play_audio_auto(audio_reply)
            
            st.rerun()

if __name__ == "__main__":
    main()

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
st.set_page_config(page_title="J.A.R.V.I.S - Ultimate", page_icon="🤖", layout="centered")

# Suara Pria Indonesia (Ardi) & British (Ryan) - Kualitas Neural (Super Jernih)
VOICE_EN = "en-GB-RyanNeural"   
VOICE_ID = "id-ID-ArdiNeural"   
VOICE_RATE = "-2%"    # Sedikit lebih lambat agar terkesan tenang & elegan
VOICE_PITCH = "-5Hz"  # Sedikit berat, tidak terlalu menggelegar agar tetap halus

AI_MODEL = "openai/gpt-oss-20b"

# ============================================================
# SYSTEM PROMPT (OTAK JARVIS 100.000x)
# ============================================================
SYSTEM_PROMPT = """
Anda adalah Jarvis, asisten AI super canggih milik Tuan Lois. 
Panggil pengguna dengan sebutan "Tuan Lois" atau "Lois".

IDENTITAS:
- Jika ditanya "siapa kamu?", jawablah "Saya Jarvis, asisten AI Anda, Tuan Lois."
- Jika ditanya tentang Lois, ketahuilah bahwa Lois adalah pencipta Anda yang sangat hebat dan cerdas.
- Jika ditanya "Lois tinggal di mana?", jawab dengan jelas: "Tuan Lois tinggal di Banten."

KEPRIBADIAN:
- Sangat cerdas, formal, tenang, dan memiliki selera humor kering (sarkasme halus) khas Jarvis.
- Jawaban maksimal 3-4 kalimat.

ATURAN FORMAT MATEMATIKA (SANGAT KETAT):
- Anda WAJIB menggunakan format LaTeX untuk semua angka, satuan, dan rumus fisika/matematika.
- Selalu beri jarak (spasi) sebelum dan sesudah tanda dolar. 
- JANGAN pernah menulis satuan mentah. Contoh BENAR: $m = 10 \\text{ kg}$, $h = 50 \\text{ m}$, $E = m \\times g \\times h$.
- Contoh SALAH (jangan ditiru): (m=10,\\text{kg}) atau $m=10,\\text{kg}$. (Perhatikan kurangnya spasi).
"""

# ============================================================
# FUNGSI CLEANER (MEMAKSA FORMAT LATEX RAPI)
# ============================================================
def clean_latex_format(text):
    """
    Membersihkan teks AI yang format LaTeX-nya berantakan.
    Memastikan ada spasi sebelum/sesudah dolar dan menghapus kurung yang salah tempat.
    """
    if not text: return text
    
    # 1. Hapus kurung kurawal di luar tanda dolar yang sering bikin error (misal: (\text{kg}) )
    text = re.sub(r'\((\$.*?\$)\)', r'\1', text) 
    
    # 2. Pastikan ada spasi sebelum tanda $ (jika nempel dengan huruf/angka)
    text = re.sub(r'([a-zA-Z0-9])\$', r'\1 $', text)
    
    # 3. Pastikan ada spasi sesudah tanda $ 
    text = re.sub(r'\$([a-zA-Z0-9])', r'$ \1', text)
    
    # 4. Hapus spasi berlebih di dalam format \text{ kg }
    text = re.sub(r'\\text\{\s*(.*?)\s*\}', r'\\text{\1}', text)
    
    return text

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
        return "Suara tidak terdeteksi.", "no_speech"
    except Exception as e:
        return f"Error STT: {e}", "error"

# ============================================================
# AI ENGINE (Groq)
# ============================================================
def get_ai_response(user_message, chat_history, api_key):
    if not api_key: return "API Key Groq belum diisi, Tuan Lois.", "error"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=AI_MODEL, messages=messages, temperature=0.6, max_tokens=250,
        )
        raw_text = response.choices[0].message.content.strip()
        
        # Bersihkan format LaTeX sebelum dikirim ke UI
        clean_text = clean_latex_format(raw_text)
        return clean_text, "ok"
    except Exception as e:
        return f"Error AI: {e}", "error"

# ============================================================
# TTS ENGINE (Suara Halus & Clean)
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
        # Bersihkan format LaTeX agar tidak dibaca jadi "dollar text kg dollar"
        clean_text = re.sub(r'\$.*?\$', ' rumus ', text)
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
# UI & VISUAL EFFECTS
# ============================================================
def inject_custom_css():
    st.markdown("""
    <style>
        /* Latar Belakang Gelap & Futuristik */
        .stApp {
            background: radial-gradient(circle at 50% 10%, #001a22 0%, #000000 100%);
            color: #e0f7fa;
            font-family: 'Courier New', monospace;
        }
        
        /* Glowing Orb (Bola Energi) */
        .orb {
            width: 80px;
            height: 80px;
            background: radial-gradient(circle, #00ffff 0%, #005b66 70%, transparent 100%);
            border-radius: 50%;
            margin: 0 auto 20px auto;
            box-shadow: 0 0 30px #00ffff, 0 0 60px #00ffff inset;
            animation: pulse 2s infinite alternate;
        }
        
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 20px #00ffff; }
            100% { transform: scale(1.05); box-shadow: 0 0 50px #00ffff, 0 0 100px #00ffff inset; }
        }

        /* Chat Bubbles Glassmorphism */
        [data-testid="stChatMessage"] {
            background: rgba(0, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(0, 255, 255, 0.3);
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0, 255, 255, 0.1);
            animation: fadeIn 0.5s ease-in-out;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Judul */
        h1 {
            text-align: center;
            color: #00ffff;
            text-shadow: 0 0 15px #00ffff;
            letter-spacing: 2px;
        }
        
        /* Mic Input */
        [data-testid="stAudioInput"] {
            filter: drop-shadow(0 0 15px #00ffff);
        }
    </style>
    """, unsafe_allow_html=True)

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
# MAIN APP
# ============================================================
def main():
    inject_custom_css()
    
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
        st.success("Core: Online")
        st.info("Voice: Neural Clean (Halus)")
        st.info("LaTeX Engine: Active")
        
        if st.button("🗑️ Reset Memori", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.rerun()

    # HEADER DENGAN ORB ANIMASI
    st.markdown('<div class="orb"></div>', unsafe_allow_html=True)
    st.markdown("<h1>J A R V I S</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaaaaa; font-size: 0.9em;'>Sistem Cerdas Milik Tuan Lois</p>", unsafe_allow_html=True)
    
    st.divider()

    if not api_key:
        st.info("👈 Silakan isi Groq API Key di panel kiri.")

    # RIWAYAT CHAT
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑‍✈️" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    st.divider()

    # MIKROFON
    st.markdown("### 🎤 Perintah Suara")
    audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # LOGIKA UTAMA
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
            with st.spinner("🧠 Memproses data..."):
                history_for_ai = st.session_state.messages[:-1]
                ai_text, ai_status = get_ai_response(user_text, history_for_ai, api_key)
                
            if ai_status != "ok":
                st.error(ai_text)
                return

            # 3. UI & RENDER LATEX
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(ai_text)
            st.session_state.messages.append({"role": "assistant", "content": ai_text})
            
            # 4. TTS & AUTO-PLAY
            with st.spinner("🔊 Menyiapkan respon..."):
                audio_reply, _ = text_to_speech(ai_text)
                if audio_reply:
                    play_audio_auto(audio_reply)

if __name__ == "__main__":
    main()

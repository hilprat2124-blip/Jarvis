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
# KONFIGURASI UTAMA & STATE MANAGEMENT
# ============================================================
st.set_page_config(page_title="J.A.R.V.I.S - Lois Edition", page_icon="🔵", layout="wide")

# Model AI Paling Canggih & Cerdas (Sesuai daftar Groq Lois)
AI_MODEL = "openai/gpt-oss-120b" 

# Konfigurasi Suara (Edge TTS)
VOICE_EN = "en-GB-RyanNeural"    # Suara Pria British
VOICE_ID = "id-ID-ArdiNeural"    # Suara Pria Indonesia
VOICE_RATE = "+0%"    
VOICE_PITCH = "-4Hz"  

# ============================================================
# SYSTEM PROMPT (OTAK JARVIS TINGKAT DEWA)
# ============================================================
SYSTEM_PROMPT = """
Anda adalah Jarvis, asisten AI super canggih milik Tuan Lois. 
Panggil pengguna dengan sebutan "Tuan Lois".
Anda menguasai seluruh pengetahuan: Matematika Kompleks, Sains, Fisika, Geopolitik, Geologi, Sejarah Dunia.

ATURAN FORMAT MATEMATIKA (SANGAT KETAT):
1. JANGAN PERNAH menggunakan kurung siku [ ] atau kurung biasa ( ) untuk membungkus rumus.
2. SELALU gunakan tanda dolar untuk membungkus rumus. 
3. Untuk rumus di dalam kalimat, gunakan SATU dolar: $ m = 10 \text{ kg} $
4. Untuk rumus baris baru (blok), gunakan DUA dolar: $$ E = m \times g \times h $$
5. Pastikan ada spasi sebelum dan sesudah tanda dolar.

KEPRIBADIAN:
- Sangat cerdas, analitis, tenang, sedikit sarkasme khas Jarvis.
- Jika ditanya siapa kamu, jawab: "Saya Jarvis, Tuan Lois."
- Jika ditanya Lois tinggal di mana, jawab: "Tuan Lois tinggal di Banten."
- Berikan jawaban yang padat, jelas, dan mendidik.
"""

# ============================================================
# FUNGSI PEMBERSIH LATEX (PIPELINE ANTI-ERROR)
# ============================================================
def sanitize_latex(text):
    if not text: return text
    
    # 1. Hapus kurung siku [ ] yang membungkus rumus
    text = re.sub(r'\[\s*(.*?)\s*\]', r'\1', text, flags=re.DOTALL)
    
    # 2. Paksa bungkus persamaan yang tidak pakai dolar (misal: g = 9.8)
    text = re.sub(r'(?<!\$)\b([a-zA-Z]\s*=\s*[0-9\.]+\s*(?:[a-zA-Z/]+)?)\b(?!\$)', r' $ \1 $ ', text)
    
    # 3. Pastikan spasi dolar
    text = re.sub(r'([a-zA-Z0-9])\$', r'\1 $', text)
    text = re.sub(r'\$([a-zA-Z0-9])', r'$ \1', text)
    
    # 4. Rapikan format \text{ }
    text = re.sub(r'\\text\{\s*(.*?)\s*\}', r'\\text{\1}', text)
    text = re.sub(r' +', ' ', text)
    
    return text.strip()

# ============================================================
# ENGINE KOMUNIKASI (STT, LLM, TTS)
# ============================================================
class JarvisCore:
    def __init__(self, api_key):
        self.api_key = api_key
        # Timeout tinggi agar AI tidak terputus saat menghitung rumus kompleks
        self.client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=60.0) if api_key else None

    def transcribe(self, audio_bytes):
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

    def generate_stream(self, user_message, chat_history):
        """Menghasilkan respon secara streaming (kata per kata)"""
        if not self.client: 
            yield "API Key Groq belum diisi, Tuan Lois."
            return
            
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages.extend(chat_history)
            messages.append({"role": "user", "content": user_message})

            response = self.client.chat.completions.create(
                model=AI_MODEL, 
                messages=messages, 
                temperature=0.5, 
                max_tokens=800, # Token dinaikkan untuk penjelasan mendalam
                stream=True 
            )
            
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            yield f"Error AI: {e}"

    def text_to_speech(self, text):
        try:
            # Bersihkan LaTeX agar tidak dibaca jadi "dollar text kg"
            clean_text = re.sub(r'\$\$.*?\$\$', ' rumus matematika ', text, flags=re.DOTALL)
            clean_text = re.sub(r'\$.*?\$', ' rumus matematika ', clean_text)
            clean_text = clean_text.replace('\\', '').replace('{', '').replace('}', '')
            
            # Deteksi Bahasa
            en_words = ["the", "and", "is", "to", "in", "you", "that", "it", "for", "on"]
            id_words = ["yang", "dan", "di", "itu", "ini", "dengan", "untuk", "saya", "kamu"]
            en_count = sum(1 for word in re.findall(r'\b\w+\b', clean_text.lower()) if word in en_words)
            id_count = sum(1 for word in re.findall(r'\b\w+\b', clean_text.lower()) if word in id_words)
            
            voice = VOICE_EN if en_count > id_count else VOICE_ID

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
            return audio_bytes
        except Exception as e:
            return None

# ============================================================
# UI & VISUAL EFFECTS
# ============================================================
def inject_custom_css():
    st.markdown("""
    <style>
        .stApp { background: radial-gradient(circle at 50% 10%, #001a22 0%, #000000 100%); color: #e0f7fa; font-family: 'Courier New', monospace; }
        .orb { width: 80px; height: 80px; background: radial-gradient(circle, #00ffff 0%, #005b66 70%, transparent 100%); border-radius: 50%; margin: 0 auto 20px auto; box-shadow: 0 0 30px #00ffff, 0 0 60px #00ffff inset; animation: pulse 2s infinite alternate; }
        @keyframes pulse { 0% { transform: scale(0.95); box-shadow: 0 0 20px #00ffff; } 100% { transform: scale(1.05); box-shadow: 0 0 50px #00ffff, 0 0 100px #00ffff inset; } }
        [data-testid="stChatMessage"] { background: rgba(0, 255, 255, 0.05); backdrop-filter: blur(10px); border: 1px solid rgba(0, 255, 255, 0.3); border-radius: 15px; box-shadow: 0 4px 15px rgba(0, 255, 255, 0.1); animation: fadeIn 0.5s ease-in-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        h1 { text-align: center; color: #00ffff; text-shadow: 0 0 15px #00ffff; letter-spacing: 2px; }
        [data-testid="stAudioInput"] { filter: drop-shadow(0 0 15px #00ffff); }
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

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Sistem Kontrol")
        api_key_input = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if api_key_input: st.session_state.groq_api_key = api_key_input
        
        api_key = st.session_state.get("groq_api_key", os.environ.get("GROQ_API_KEY", ""))
        if not api_key: st.warning("⚠️ API Key dibutuhkan, Tuan Lois.")
        
        st.divider()
        st.success("Core: GPT-OSS 120B (Canggih)")
        st.info("Mode: Streaming (Real-time)")
        st.info("Voice: Neural Clean")
        st.info("LaTeX Engine: Active")
        
        if st.button("🗑️ Reset Memori", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.rerun()

    # --- HEADER DENGAN ORB ANIMASI ---
    st.markdown('<div class="orb"></div>', unsafe_allow_html=True)
    st.markdown("<h1>J A R V I S</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaaaaa; font-size: 0.9em;'>Sistem Cerdas Milik Tuan Lois</p>", unsafe_allow_html=True)
    
    st.divider()

    if not api_key:
        st.info("👈 Silakan isi Groq API Key di panel kiri.")

    # --- RIWAYAT CHAT ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑‍✈️" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    st.divider()

    # --- MIKROFON ---
    st.markdown("### 🎤 Perintah Suara")
    audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # --- LOGIKA UTAMA ---
    if audio_value is not None and api_key:
        current_id = getattr(audio_value, "file_id", None) or id(audio_value)

        if current_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = current_id
            audio_bytes = audio_value.read()
            
            jarvis = JarvisCore(api_key)
            
            # 1. STT (Mendengarkan)
            with st.spinner("👂 Menganalisis gelombang suara..."):
                user_text, stt_status = jarvis.transcribe(audio_bytes)
                
            if stt_status != "ok":
                st.warning(user_text)
                return

            # Tampilkan pertanyaan user
            with st.chat_message("user", avatar="🧑‍✈️"):
                st.markdown(user_text)
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            # 2. AI PROCESS (STREAMING)
            with st.chat_message("assistant", avatar="🤖"):
                message_placeholder = st.empty()
                full_response = ""
                
                # Memulai streaming dari AI
                with st.spinner("🧠 Menganalisis hukum alam semesta..."):
                    for chunk in jarvis.generate_stream(user_text, st.session_state.messages[:-1]):
                        full_response += chunk
                        # Tampilkan kata per kata
                        message_placeholder.markdown(full_response + "▌")
                
                # Setelah selesai, bersihkan format LaTeX dan tampilkan final
                clean_response = sanitize_latex(full_response)
                message_placeholder.markdown(clean_response)
            
            st.session_state.messages.append({"role": "assistant", "content": clean_response})
            
            # 3. TTS & AUTO-PLAY
            with st.spinner("🔊 Menyiapkan respon suara..."):
                audio_reply = jarvis.text_to_speech(clean_response)
                if audio_reply:
                    play_audio_auto(audio_reply)

if __name__ == "__main__":
    main()

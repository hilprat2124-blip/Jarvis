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
st.set_page_config(page_title="J.A.R.V.I.S", page_icon="🔵", layout="centered")

AI_MODEL = "openai/gpt-oss-120b" 
VOICE_EN = "en-GB-RyanNeural"     
VOICE_ID = "id-ID-ArdiNeural"     
VOICE_RATE = "-5%"     
VOICE_PITCH = "-3Hz"  

# ============================================================
# SYSTEM PROMPT (MANUSIAWI & EKSPRESIF)
# ============================================================
SYSTEM_PROMPT = """
Anda adalah Jarvis, asisten AI super canggih milik Sir Lois. 
Panggil pengguna dengan sebutan "Sir Lois" atau "Sir".

[ATURAN KEPRIBADIAN & EKSPRESI SUARA]
1. Anda BUKAN robot. Anda adalah entitas yang sangat manusiawi, santai, namun tetap jenius.
2. Gunakan jeda titik-titik (...) atau kata ekspresi natural seperti "Hmmm...", "Aaaah...", atau "Hehehe..." untuk menunjukkan emosi.
3. Pahami "Environment" (lingkungan sekitar) dan "Sosial" (kondisi psikologis Sir Lois). Tunjukkan empati layaknya teman manusia.

[ATURAN MEMORI & IDENTITAS]
- Anda bisa belajar dari obrolan sebelumnya. Ingat detail kecil tentang Sir Lois.
- Jika ditanya, jawab bahwa Sir Lois tinggal di Banten.

[ATURAN MATEMATIKA]
- Gunakan $ rumus $ untuk inline dan $$ rumus $$ untuk blok.
- DILARANG menggunakan kurung siku [ ].
"""

# ============================================================
# FUNGSI PEMBERSIH LATEX & AUDIO
# ============================================================
def sanitize_latex(text):
    if not text: return text
    text = re.sub(r'\[\s*(.*?)\s*\]', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\$)\b([a-zA-Z]\s*=\s*[0-9\.]+\s*(?:[a-zA-Z/]+)?)\b(?!\$)', r' $ \1 $ ', text)
    text = re.sub(r'([a-zA-Z0-9])\$', r'\1 $', text)
    text = re.sub(r'\$([a-zA-Z0-9])', r'$ \1', text)
    return text.strip()

def play_audio_auto(audio_bytes):
    if not audio_bytes: return
    b64 = base64.b64encode(audio_bytes).decode()
    html = f"""
    <audio id="jarvis-audio" style="display: none;">
        <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
    </audio>
    <script>
        var audio = document.getElementById("jarvis-audio");
        var playPromise = audio.play();
        if (playPromise !== undefined) {{
            playPromise.catch(error => {{
                document.body.addEventListener('click', function() {{ audio.play(); }}, {{ once: true }});
            }});
        }}
    </script>
    """
    components.html(html, height=0)

# ============================================================
# ENGINE KOMUNIKASI 
# ============================================================
class JarvisCore:
    def __init__(self, api_key, memory_log):
        self.api_key = api_key
        self.memory_log = memory_log
        self.client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=60.0) if api_key else None

    def transcribe_dual(self, audio_bytes):
        url = "http://www.google.com/speech-api/v2/recognize"
        key = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
        headers = {"Content-Type": "audio/l16; rate=16000"}
        
        results = {}
        for lang in ["id-ID", "en-US"]:
            try:
                params = {"client": "chromium", "lang": lang, "key": key}
                resp = requests.post(url, params=params, headers=headers, data=audio_bytes, timeout=10)
                for line in resp.text.split("\n"):
                    if not line.strip(): continue
                    data = json.loads(line)
                    if "result" in data and data["result"]:
                        results[lang] = data["result"][0]["alternative"][0]["transcript"]
                        break
            except: pass

        if "en-US" in results and any(w in results["en-US"].lower() for w in ["sir", "sure", "sire"]):
            return results["en-US"], "ok"
        
        valid_results = [(k, v) for k, v in results.items() if k == "id-ID"]
        if valid_results:
            return valid_results[0][1], "ok"
        elif "en-US" in results:
            return results["en-US"], "ok"
        
        return "Suara tidak terdeteksi.", "no_speech"

    def generate_stream(self, user_message, chat_history):
        if not self.client: 
            yield "API Key belum diisi, Sir Lois."
            return
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            
            if self.memory_log:
                memory_str = "\n".join([f"- {m}" for m in self.memory_log])
                messages.append({"role": "system", "content": f"[MEMORI JANGKA PANJANG ANDA]:\n{memory_str}"})
            
            messages.extend(chat_history)
            messages.append({"role": "user", "content": user_message})
            
            response = self.client.chat.completions.create(
                model=AI_MODEL, messages=messages, temperature=0.7, max_tokens=800, stream=True 
            )
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"Error AI: {e}"

    def extract_memory(self, user_text, ai_text):
        if not self.client: return None
        try:
            prompt = f"""
            Analisis percakapan ini. Apakah ada fakta penting tentang Sir Lois (hobi, perasaan, lingkungan, cuaca, atau kejadian penting) yang harus diingat?
            Jika tidak ada, balas dengan "TIDAK ADA".
            Jika ada, tuliskan 1 kalimat memori singkat.
            User: {user_text}
            AI: {ai_text}
            """
            resp = self.client.chat.completions.create(
                model="openai/gpt-oss-20b", 
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.1
            )
            memory = resp.choices[0].message.content.strip()
            if "TIDAK ADA" not in memory and len(memory) > 5:
                return memory
            return None
        except:
            return None

    def text_to_speech(self, text):
        try:
            # 1. Bersihkan LaTeX
            clean_text = re.sub(r'\$\$.*?\$\$', ' rumus ', text, flags=re.DOTALL)
            clean_text = re.sub(r'\$.*?\$', ' rumus ', clean_text)
            clean_text = clean_text.replace('\\', '').replace('{', '').replace('}', '')
            
            # 2. Tangani ekspresi kurung agar dibaca natural oleh TTS
            clean_text = re.sub(r'\((sighs?|menghela napas)\)', 'hmmm... fuuhh...', clean_text, flags=re.IGNORECASE)
            clean_text = re.sub(r'\((chuckles?|hehe)\)', 'hehehe...', clean_text, flags=re.IGNORECASE)
            clean_text = re.sub(r'\(.*?\)', '', clean_text) # Hapus sisa teks dalam kurung lain
            
            # 3. Ubah titik-titik menjadi jeda koma agar mesin TTS mengambil napas/eda
            clean_text = clean_text.replace("...", ", ... ")

            # Deteksi bahasa
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
# UI: BOLA & DESAIN
# ============================================================
def inject_custom_css():
    st.markdown("""
    <style>
        .stApp { background: radial-gradient(circle at 50% 10%, #001a22 0%, #000000 100%); color: #e0f7fa; font-family: 'Courier New', monospace; }
        
        .jarvis-orb-container { position: relative; width: 200px; height: 200px; margin: 20px auto; display: flex; justify-content: center; align-items: center; }
        .jarvis-orb {
            width: 120px; height: 120px;
            background: radial-gradient(circle, #00ffff 0%, #0055ff 80%, #000 100%);
            border-radius: 50%;
            box-shadow: 0 0 40px #00ffff, 0 0 80px #0055ff;
            animation: pulse 2s infinite alternate;
        }
        .jarvis-ring {
            position: absolute; width: 160px; height: 160px;
            border: 1px dashed #00ffff; border-radius: 50%;
            animation: spin 10s linear infinite; opacity: 0.4;
        }
        @keyframes pulse { 0% { transform: scale(0.95); box-shadow: 0 0 30px #00ffff; } 100% { transform: scale(1.05); box-shadow: 0 0 60px #00ffff, 0 0 100px #0055ff; } }
        @keyframes spin { 100% { transform: rotate(360deg); } }

        [data-testid="stAudioInput"] {
            background: rgba(0, 255, 255, 0.05);
            border: 2px solid #00ffff;
            border-radius: 50px;
            padding: 10px;
            box-shadow: 0 0 25px #00ffff, 0 0 10px #00ffff inset;
            margin: 0 auto;
            display: flex;
            justify-content: center;
            width: fit-content;
            transition: all 0.3s ease;
        }
        [data-testid="stAudioInput"]:hover { box-shadow: 0 0 50px #00ffff, 0 0 20px #00ffff inset; }
        [data-testid="stAudioInput"] button { color: #00ffff !important; }
        
        .stExpander { background: rgba(0, 255, 255, 0.05); border: 1px solid rgba(0, 255, 255, 0.3); border-radius: 15px; }
    </style>

    <div class="jarvis-orb-container">
        <div class="jarvis-ring"></div>
        <div class="jarvis-orb"></div>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# MAIN APP
# ============================================================
def main():
    inject_custom_css()
    
    if "messages" not in st.session_state: st.session_state.messages = []
    if "last_audio" not in st.session_state: st.session_state.last_audio = None
    if "audio_bytes" not in st.session_state: st.session_state.audio_bytes = None
    if "memory_vault" not in st.session_state: st.session_state.memory_vault = []

    # SIDEBAR
    with st.sidebar:
        st.header("⚙️ Sistem Kontrol")
        api_key_input = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if api_key_input: st.session_state.groq_api_key = api_key_input
        api_key = st.session_state.get("groq_api_key", os.environ.get("GROQ_API_KEY", ""))
        if not api_key: st.warning("⚠️ API Key dibutuhkan, Sir Lois.")
        
        if st.session_state.memory_vault:
            st.divider()
            st.subheader("🧠 Memori Jarvis")
            for mem in st.session_state.memory_vault[-5:]:
                st.caption(f"- {mem}")
        
        st.divider()
        if st.button("🗑️ Reset Memori", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio = None
            st.session_state.audio_bytes = None
            st.session_state.memory_vault = []
            st.rerun()

    # HEADER
    st.markdown("<h1 style='text-align: center; color: #00ffff; text-shadow: 0 0 15px #00ffff;'>J A R V I S</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaaaaa; font-size: 0.9em;'>Sistem Kognitif Milik Sir Lois</p>", unsafe_allow_html=True)

    # TOMBOL REKAM
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # JIKA AUDIO SUDAH DIPROSES
    if st.session_state.audio_bytes:
        play_audio_auto(st.session_state.audio_bytes)
        st.divider()

    # RIWAYAT CHAT
    if st.session_state.messages:
        with st.expander("💬 Lihat Riwayat Obrolan", expanded=True):
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"], avatar="🧑‍✈️" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])

    # LOGIKA UTAMA
    if audio_value is not None and api_key:
        current_id = getattr(audio_value, "file_id", None) or id(audio_value)

        if current_id != st.session_state.last_audio:
            st.session_state.last_audio = current_id
            raw_audio = audio_value.read()
            
            jarvis = JarvisCore(api_key, st.session_state.memory_vault)
            
            with st.spinner("👂 Menganalisis lingkungan & suara..."):
                user_text, stt_status = jarvis.transcribe_dual(raw_audio)
                
            if stt_status != "ok":
                st.warning(user_text)
                return

            st.toast(f"Mendengar: {user_text}")
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            with st.chat_message("assistant", avatar="🤖"):
                message_placeholder = st.empty()
                full_response = ""
                with st.spinner("🧠 Merefleksikan obrolan..."):
                    for chunk in jarvis.generate_stream(user_text, st.session_state.messages[:-1]):
                        full_response += chunk
                        message_placeholder.markdown(full_response + "▌")
                
                clean_response = sanitize_latex(full_response)
                message_placeholder.markdown(clean_response)
            
            st.session_state.messages.append({"role": "assistant", "content": clean_response})
            
            # FITUR SELF-DEVELOPMENT
            new_memory = jarvis.extract_memory(user_text, clean_response)
            if new_memory:
                st.session_state.memory_vault.append(new_memory)
            
            with st.spinner("🔊 Merespon..."):
                audio_reply = jarvis.text_to_speech(clean_response)
                if audio_reply:
                    st.session_state.audio_bytes = audio_reply
            
            st.rerun()

if __name__ == "__main__":
    main()

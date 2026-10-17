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
# KONFIGURASI UTAMA (J.A.R.V.I.S)
# ============================================================
st.set_page_config(page_title="J.A.R.V.I.S", page_icon="🔵", layout="wide")

AI_MODEL = "openai/gpt-oss-120b" 
VOICE_EN = "en-GB-RyanNeural"    # Suara Pria British (Sangat Clean)
VOICE_ID = "id-ID-ArdiNeural"    # Suara Pria Indonesia (Sangat Clean)
VOICE_RATE = "-2%"               # Sedikit lebih lambat agar terkesan tenang
VOICE_PITCH = "-5Hz"             # Sedikit berat dan berwibawa

SYSTEM_PROMPT = """
Anda adalah Jarvis, asisten AI super canggih milik Tuan Lois. 
Panggil pengguna dengan sebutan "Tuan Lois".
Anda menguasai seluruh pengetahuan: Matematika, Sains, Geopolitik, Sejarah.

ATURAN MATEMATIKA:
- Gunakan $ rumus $ untuk inline dan $$ rumus $$ untuk blok.
- DILARANG menggunakan kurung siku [ ].

KEPRIBADIAN:
- Cerdas, tenang, sedikit sarkasme khas Jarvis.
- Jika ditanya Lois tinggal di mana, jawab: "Tuan Lois tinggal di Banten."
- Maksimal 3-4 kalimat agar tidak terlalu panjang saat diucapkan.
"""

# ============================================================
# FUNGSI PEMBERSIH LATEX
# ============================================================
def sanitize_latex(text):
    if not text: return text
    text = re.sub(r'\[\s*(.*?)\s*\]', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\$)\b([a-zA-Z]\s*=\s*[0-9\.]+\s*(?:[a-zA-Z/]+)?)\b(?!\$)', r' $ \1 $ ', text)
    text = re.sub(r'([a-zA-Z0-9])\$', r'\1 $', text)
    text = re.sub(r'\$([a-zA-Z0-9])', r'$ \1', text)
    return text.strip()

# ============================================================
# ENGINE KOMUNIKASI
# ============================================================
class JarvisCore:
    def __init__(self, api_key):
        self.api_key = api_key
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
        if not self.client: 
            yield "API Key belum diisi, Tuan Lois."
            return
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages.extend(chat_history)
            messages.append({"role": "user", "content": user_message})

            response = self.client.chat.completions.create(
                model=AI_MODEL, messages=messages, temperature=0.5, max_tokens=600, stream=True 
            )
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"Error AI: {e}"

    def text_to_speech(self, text):
        try:
            clean_text = re.sub(r'\$\$.*?\$\$', ' rumus matematika ', text, flags=re.DOTALL)
            clean_text = re.sub(r'\$.*?\$', ' rumus matematika ', clean_text)
            clean_text = clean_text.replace('\\', '').replace('{', '').replace('}', '')
            
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
        except Exception:
            return None

# ============================================================
# UI: HOLOGRAM COMPONENT (BEBAS KOTAK HITAM)
# ============================================================
def render_hologram():
    """Komponen HTML/JS murni untuk bola hologram yang responsif terhadap suara."""
    html_code = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {
            margin: 0; padding: 0;
            background: transparent; /* Transparan agar menyatu dengan Streamlit */
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            height: 100vh; overflow: hidden;
            font-family: 'Courier New', monospace;
        }
        .orb-container {
            position: relative; width: 200px; height: 200px;
            display: flex; justify-content: center; align-items: center;
        }
        /* Cincin Luar */
        .ring-outer {
            position: absolute; width: 180px; height: 180px;
            border: 2px dashed #00ffff; border-radius: 50%;
            animation: spin 15s linear infinite; opacity: 0.4;
            box-shadow: 0 0 20px rgba(0, 255, 255, 0.2);
        }
        /* Cincin Dalam */
        .ring-inner {
            position: absolute; width: 140px; height: 140px;
            border: 1px solid #00ffff; border-radius: 50%;
            animation: spin-reverse 8s linear infinite; opacity: 0.6;
        }
        /* Bola Plasma */
        .plasma-core {
            width: 100px; height: 100px;
            background: radial-gradient(circle, #ffffff 0%, #00ffff 30%, #0055ff 70%, transparent 100%);
            border-radius: 50%;
            box-shadow: 0 0 40px #00ffff, 0 0 80px #0055ff;
            animation: pulse 2s infinite alternate;
            z-index: 10;
            transition: transform 0.05s linear, box-shadow 0.05s linear;
        }
        /* Animasi Berputar */
        @keyframes spin { 100% { transform: rotate(360deg); } }
        @keyframes spin-reverse { 100% { transform: rotate(-360deg); } }
        /* Animasi Bernapas */
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 30px #00ffff; }
            100% { transform: scale(1.05); box-shadow: 0 0 60px #00ffff, 0 0 100px #0055ff; }
        }
        .status {
            margin-top: 30px; color: #00ffff; letter-spacing: 3px;
            font-size: 12px; text-transform: uppercase; text-shadow: 0 0 10px #00ffff;
            opacity: 0.8; transition: all 0.3s;
        }
    </style>
    </head>
    <body>
        <div class="orb-container">
            <div class="ring-outer"></div>
            <div class="ring-inner"></div>
            <div class="plasma-core" id="orb"></div>
        </div>
        <div class="status" id="status">Menunggu Perintah...</div>

        <script>
            const orb = document.getElementById('orb');
            const status = document.getElementById('status');
            let audioContext, analyser, microphone, dataArray;

            async function initAudio() {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ 
                        audio: { echoCancellation: true, noiseSuppression: true } 
                    });
                    audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    analyser = audioContext.createAnalyser();
                    microphone = audioContext.createMediaStreamSource(stream);
                    analyser.fftSize = 256;
                    microphone.connect(analyser);
                    dataArray = new Uint8Array(analyser.frequencyBinCount);
                    animate();
                } catch (e) {
                    status.innerText = "Izin Mikrofon Diperlukan";
                }
            }

            function animate() {
                analyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                let avg = sum / dataArray.length;

                if (avg > 10) {
                    status.innerText = "Mendengar Suara...";
                    let scale = 1 + (avg / 100);
                    if (scale > 1.5) scale = 1.5;
                    orb.style.transform = `scale(${scale})`;
                    orb.style.boxShadow = `0 0 ${50 + avg}px #00ffff, 0 0 ${100 + avg}px #0055ff`;
                } else {
                    status.innerText = "Mendengarkan...";
                    orb.style.transform = `scale(1)`;
                    orb.style.boxShadow = `0 0 40px #00ffff, 0 0 80px #0055ff`;
                }
                requestAnimationFrame(animate);
            }
            initAudio();
        </script>
    </body>
    </html>
    """
    # Render komponen dengan tinggi 350px agar pas, tanpa kotak hitam
    components.html(html_code, height=350)

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
    if "messages" not in st.session_state: st.session_state.messages = []
    if "last_audio_id" not in st.session_state: st.session_state.last_audio_id = None

    # SIDEBAR
    with st.sidebar:
        st.header("⚙️ Sistem Kontrol")
        api_key_input = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if api_key_input: st.session_state.groq_api_key = api_key_input
        
        api_key = st.session_state.get("groq_api_key", os.environ.get("GROQ_API_KEY", ""))
        if not api_key: st.warning("⚠️ API Key dibutuhkan, Tuan Lois.")
        
        if st.button("🗑️ Reset Memori", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio_id = None
            st.rerun()

    # CSS GLOBAL (Latar Belakang & Grid Futuristik)
    st.markdown("""
        <style>
            /* Latar belakang gelap dengan grid futuristik */
            .stApp {
                background-color: #050505;
                background-image: 
                    linear-gradient(rgba(0, 255, 255, 0.05) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(0, 255, 255, 0.05) 1px, transparent 1px);
                background-size: 30px 30px;
                color: #e0f7fa;
            }
            /* Sembunyikan Header/Footer Streamlit */
            header, footer { visibility: hidden; }
            
            /* Desain Tombol Rekam (Mikrofon) */
            [data-testid="stAudioInput"] {
                background: rgba(0, 255, 255, 0.05);
                border: 1px solid #00ffff;
                border-radius: 50px;
                padding: 10px;
                box-shadow: 0 0 20px #00ffff;
                margin: 0 auto;
                display: flex;
                justify-content: center;
                width: fit-content;
                transition: all 0.3s ease;
            }
            [data-testid="stAudioInput"]:hover {
                box-shadow: 0 0 40px #00ffff;
                background: rgba(0, 255, 255, 0.15);
            }
            [data-testid="stAudioInput"] button {
                color: #00ffff !important;
            }
            
            /* Desain Expander (Riwayat Chat) */
            .stExpander {
                background: rgba(0, 255, 255, 0.03);
                border: 1px solid rgba(0, 255, 255, 0.2);
                border-radius: 10px;
            }
        </style>
    """, unsafe_allow_html=True)

    # RENDER BOLA HOLOGRAM (Tengah Layar)
    render_hologram()

    # TOMBOL MIKROFON (Di Tengah Bawah Bola)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # RIWAYAT CHAT (POP-UP DI BAWAH)
    if st.session_state.messages:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("💬 Riwayat Percakapan", expanded=False):
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"], avatar="🧑‍✈️" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])

    # LOGIKA UTAMA
    if audio_value is not None and api_key:
        current_id = getattr(audio_value, "file_id", None) or id(audio_value)

        if current_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = current_id
            audio_bytes = audio_value.read()
            
            jarvis = JarvisCore(api_key)
            
            with st.spinner("👂 Memproses..."):
                user_text, stt_status = jarvis.transcribe(audio_bytes)
                
            if stt_status != "ok":
                st.warning(user_text)
                return

            st.session_state.messages.append({"role": "user", "content": user_text})
            
            with st.spinner("🧠 Jarvis berpikir..."):
                full_response = ""
                for chunk in jarvis.generate_stream(user_text, st.session_state.messages[:-1]):
                    full_response += chunk
                clean_response = sanitize_latex(full_response)
            
            st.session_state.messages.append({"role": "assistant", "content": clean_response})
            
            with st.spinner("🔊 Merespon..."):
                audio_reply = jarvis.text_to_speech(clean_response)
                if audio_reply:
                    play_audio_auto(audio_reply)
            
            st.rerun()

if __name__ == "__main__":
    main()

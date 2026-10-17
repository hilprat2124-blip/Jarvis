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
st.set_page_config(page_title="J.A.R.V.I.S - Lois Edition", page_icon="🔵", layout="centered")

AI_MODEL = "openai/gpt-oss-120b" 
VOICE_EN = "en-GB-RyanNeural"    
VOICE_ID = "id-ID-ArdiNeural"    
VOICE_RATE = "+0%"    
VOICE_PITCH = "-4Hz"  

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
    text = re.sub(r'\\text\{\s*(.*?)\s*\}', r'\\text{\1}', text)
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
            yield "API Key Groq belum diisi, Tuan Lois."
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
            clean_text = re.sub(r'\$\$.*?\$\$', ' rumus ', text, flags=re.DOTALL)
            clean_text = re.sub(r'\$.*?\$', ' rumus ', clean_text)
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
# UI: BOLA FUTURISTIK & ANIMASI
# ============================================================
def render_futuristic_ui():
    # HTML + JS ini mengurus animasi bola, deteksi suara, dan menampilkan UI
    html_code = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {
                margin: 0;
                background: #000; /* Latar hitam pekat */
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                overflow: hidden;
                font-family: 'Courier New', monospace;
                color: #00ffff;
            }
            /* Container Bola */
            .orb-container {
                position: relative;
                width: 200px;
                height: 200px;
                display: flex;
                justify-content: center;
                align-items: center;
                transition: all 0.1s ease;
            }
            /* Bola Utama */
            .orb {
                width: 120px;
                height: 120px;
                background: radial-gradient(circle, #00ffff 0%, #0088cc 40%, #000 100%);
                border-radius: 50%;
                box-shadow: 0 0 40px #00ffff, 0 0 80px #00ffff inset;
                animation: breathe 3s infinite alternate;
                transition: transform 0.05s linear;
            }
            /* Animasi Napas (Idle) */
            @keyframes breathe {
                0% { transform: scale(1); box-shadow: 0 0 30px #00ffff; }
                100% { transform: scale(1.05); box-shadow: 0 0 60px #00ffff, 0 0 100px #00ffff inset; }
            }
            /* Teks Status */
            .status {
                margin-top: 30px;
                font-size: 14px;
                letter-spacing: 2px;
                text-transform: uppercase;
                color: #00ffff;
                opacity: 0.8;
                animation: blink 2s infinite;
            }
            @keyframes blink {
                0%, 100% { opacity: 0.8; }
                50% { opacity: 0.3; }
            }
            /* Mic Indicator */
            .mic-icon {
                margin-top: 10px;
                font-size: 24px;
                color: #ff4b4b;
            }
        </style>
    </head>
    <body>
        <div class="orb-container" id="orbContainer">
            <div class="orb" id="orb"></div>
        </div>
        <div class="status" id="statusText">Menunggu Perintah Suara...</div>
        
        <script>
            // Web Audio API untuk mendeteksi volume suara secara real-time
            const orb = document.getElementById('orb');
            const statusText = document.getElementById('statusText');
            let audioContext;
            let analyser;
            let microphone;
            let isListening = false;

            async function startListening() {
                if (isListening) return;
                isListening = true;
                statusText.innerText = "Mendengarkan...";

                try {
                    // Minta akses mikrofon dengan filter noise (Voice Isolation)
                    const stream = await navigator.mediaDevices.getUserMedia({
                        audio: {
                            echoCancellation: true,
                            noiseSuppression: true, // Isolasi suara
                            autoGainControl: true
                        }
                    });

                    audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    analyser = audioContext.createAnalyser();
                    microphone = audioContext.createMediaStreamSource(stream);
                    
                    analyser.fftSize = 256;
                    microphone.connect(analyser);
                    
                    const dataArray = new Uint8Array(analyser.frequencyBinCount);

                    function updateOrb() {
                        analyser.getByteFrequencyData(dataArray);
                        let sum = 0;
                        for (let i = 0; i < dataArray.length; i++) {
                            sum += dataArray[i];
                        }
                        let average = sum / dataArray.length;
                        
                        // Jika ada suara yang cukup keras (di atas threshold)
                        if (average > 10) { 
                            statusText.innerText = "Mendengar suara...";
                            // Bola membesar (efek suara)
                            let scale = 1 + (average / 100); 
                            orb.style.transform = `scale(${scale})`;
                            orb.style.boxShadow = `0 0 ${40 + average}px #00ffff, 0 0 ${80 + average}px #00ffff inset`;
                        } else {
                            statusText.innerText = "Mendengarkan...";
                            orb.style.transform = `scale(1)`;
                            orb.style.boxShadow = `0 0 30px #00ffff, 0 0 60px #00ffff inset`;
                        }
                        
                        requestAnimationFrame(updateOrb);
                    }
                    updateOrb();
                } catch (err) {
                    statusText.innerText = "Akses Mikrofon Gagal!";
                }
            }

            // Mulai mendeteksi saat halaman dimuat
            startListening();
        </script>
    </body>
    </html>
    """
    # Tampilkan UI HTML penuh
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

    # SIDEBAR (Sembunyikan default, buka jika butuh API Key)
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

    # Sembunyikan CSS Streamlit bawaan agar lebih bersih
    st.markdown("""
        <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        </style>
    """, unsafe_allow_html=True)

    # 1. RENDER BOLA ANIMASI
    render_futuristic_ui()

    # 2. INPUT MIKROFON (Disembunyikan via CSS, tapi tetap berfungsi)
    # Kita sembunyikan tombol rekam bawaan Streamlit, karena kita sudah punya bola.
    st.markdown("""
        <style>
            [data-testid="stAudioInput"] {
                opacity: 0;
                height: 0;
                position: absolute;
                pointer-events: none;
            }
        </style>
    """, unsafe_allow_html=True)
    
    # Audio Input yang berfungsi secara background
    audio_value = st.audio_input("Rekam suara", label_visibility="collapsed")

    # 3. HISTORY CHAT SEBAGAI POP-UP DI BAWAH
    if st.session_state.messages:
        with st.expander("💬 Riwayat Percakapan (Klik untuk melihat)", expanded=False):
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"], avatar="🧑‍✈️" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])

    # 4. LOGIKA UTAMA
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

import streamlit as st
import streamlit.components.v1 as components
from streamlit_mic_recorder import mic_recorder
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
            return "Suara tidak terdeteksi.", "no_speech"
        except Exception as e:
            return f"Error STT: {e}", "error"

    def generate_stream(self, user_message, chat_history):
        if not self.client: 
            yield "API Key belum diisi."
            return
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages.extend(chat_history)
            messages.append({"role": "user", "content": user_message})
            response = self.client.chat.completions.create(
                model=AI_MODEL, messages=messages, temperature=0.5, max_tokens=800, stream=True 
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
# UI: REAL-TIME ORB DENGAN AUDIO ANALYZER (JAVASCRIPT)
# ============================================================
def inject_custom_css():
    st.markdown("""
    <style>
        .stApp { background: radial-gradient(circle at 50% 10%, #001a22 0%, #000000 100%); color: #e0f7fa; font-family: 'Courier New', monospace; }
        
        /* Desain Bola */
        .jarvis-orb-container { position: relative; width: 200px; height: 200px; margin: 20px auto; display: flex; justify-content: center; align-items: center; }
        .jarvis-orb {
            width: 120px; height: 120px;
            background: radial-gradient(circle, #00ffff 0%, #0055ff 80%, #000 100%);
            border-radius: 50%;
            box-shadow: 0 0 40px #00ffff, 0 0 80px #0055ff;
            transition: transform 0.05s ease-out; /* Transisi cepat agar responsif */
        }
        .jarvis-ring {
            position: absolute; width: 160px; height: 160px;
            border: 1px dashed #00ffff; border-radius: 50%;
            animation: spin 10s linear infinite; opacity: 0.4;
        }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        
        /* Sembunyikan Tombol Streamlit */
        [data-testid="stAudioInput"] { display: none; }
        .stExpander { background: rgba(0, 255, 255, 0.05); border: 1px solid rgba(0, 255, 255, 0.3); border-radius: 15px; }
    </style>

    <div class="jarvis-orb-container">
        <div class="jarvis-ring"></div>
        <div class="jarvis-orb" id="orb"></div>
    </div>
    """, unsafe_allow_html=True)

    # Script JS untuk mendeteksi mikrofon secara real-time
    js_audio = """
    <script>
        const orb = document.getElementById("orb");
        let audioContext, analyser, microphone, dataArray;

        async function startMic() {
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
                console.log("Microphone access denied or unavailable.");
            }
        }

        function animate() {
            if(!analyser) return;
            analyser.getByteFrequencyData(dataArray);
            let sum = 0;
            for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
            let avg = sum / dataArray.length;

            // Jika ada suara, perbesar bola (maksimal 1.8x)
            if (avg > 5) {
                let scale = 1 + (avg / 100); 
                if (scale > 1.8) scale = 1.8; 
                orb.style.transform = `scale(${scale})`;
                orb.style.boxShadow = `0 0 ${50 + avg}px #00ffff, 0 0 ${100 + avg}px #0055ff`;
            } else {
                // Kembali normal jika hening
                orb.style.transform = `scale(1)`;
                orb.style.boxShadow = `0 0 40px #00ffff, 0 0 80px #0055ff`;
            }
            requestAnimationFrame(animate);
        }
        
        // Mulai mendeteksi suara
        startMic();
    </script>
    """
    # Tinggi 0 agar tidak memakan tempat
    components.html(js_audio, height=0)

# ============================================================
# MAIN APP
# ============================================================
def main():
    inject_custom_css()
    
    if "messages" not in st.session_state: st.session_state.messages = []
    if "last_audio" not in st.session_state: st.session_state.last_audio = None

    # SIDEBAR
    with st.sidebar:
        st.header("⚙️ Sistem Kontrol")
        api_key_input = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        if api_key_input: st.session_state.groq_api_key = api_key_input
        api_key = st.session_state.get("groq_api_key", os.environ.get("GROQ_API_KEY", ""))
        if not api_key: st.warning("⚠️ API Key dibutuhkan, Tuan Lois.")
        
        if st.button("🗑️ Reset Memori", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_audio = None
            st.rerun()

    # HEADER
    st.markdown("<h1 style='text-align: center; color: #00ffff; text-shadow: 0 0 15px #00ffff;'>J A R V I S</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaaaaa; font-size: 0.9em;'>Sistem Cerdas Milik Tuan Lois</p>", unsafe_allow_html=True)

    # KOMPONEN MIKROFON (Start / Stop)
    # Saat tombol ini diklik, browser otomatis mengizinkan akses mikrofon,
    # dan script JS di atas akan langsung bereaksi menggerakkan bola.
    audio_info = mic_recorder(
        start_prompt="🎤 Mulai Bicara",
        stop_prompt="⏹️ Selesai Bicara",
        just_once=True,
        use_container_width=True,
        key='recorder'
    )

    # RIWAYAT CHAT
    if st.session_state.messages:
        with st.expander("💬 Lihat Riwayat Obrolan", expanded=False):
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"], avatar="🧑‍✈️" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])

    # LOGIKA UTAMA
    if audio_info and api_key:
        audio_bytes = audio_info['bytes']
        
        if st.session_state.last_audio != audio_bytes:
            st.session_state.last_audio = audio_bytes
            jarvis = JarvisCore(api_key)
            
            with st.spinner("👂 Menganalisis gelombang suara..."):
                user_text, stt_status = jarvis.transcribe(audio_bytes)
                
            if stt_status != "ok":
                st.warning(user_text)
                return

            st.session_state.messages.append({"role": "user", "content": user_text})
            
            with st.chat_message("assistant", avatar="🤖"):
                message_placeholder = st.empty()
                full_response = ""
                with st.spinner("🧠 Jarvis berpikir..."):
                    for chunk in jarvis.generate_stream(user_text, st.session_state.messages[:-1]):
                        full_response += chunk
                        message_placeholder.markdown(full_response + "▌")
                
                clean_response = sanitize_latex(full_response)
                message_placeholder.markdown(clean_response)
            
            st.session_state.messages.append({"role": "assistant", "content": clean_response})
            
            with st.spinner("🔊 Menyiapkan suara..."):
                audio_reply = jarvis.text_to_speech(clean_response)
                if audio_reply:
                    play_audio_auto(audio_reply)
            
            st.rerun()

if __name__ == "__main__":
    main()

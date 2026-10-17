"""
==============================================================
🤖 JARVIS WEB AI - Auto Voice Detection (Hands-Free)
==============================================================
Fitur:
- Deteksi suara otomatis (VAD) tanpa perlu klik tombol kirim
- Otomatis kirim saat berhenti bicara
- Langsung merespon dengan suara Jarvis
- Bebas error encode (ASCII/Emoji dibersihkan)
==============================================================
"""

import streamlit as st
import io
import os
import json
import base64
import requests
from gtts import gTTS
from openai import OpenAI
from streamlit_js_eval import streamlit_js_eval

# ============================================================
# KONFIGURASI (Emoji dihapus dari area kode agar aman)
# ============================================================
st.set_page_config(
    page_title="Jarvis Web AI",
    page_icon="🎙️",
    layout="centered"
)

STT_LANGUAGE = "id-ID"
TTS_LANGUAGE = "id"
AI_MODEL = "gpt-3.5-turbo"
AI_MAX_TOKENS = 200
AI_TEMPERATURE = 0.7

SYSTEM_PROMPT = (
    "Anda adalah Jarvis, asisten AI yang cerdas, efisien, ramah, dan sedikit formal. "
    "Anda menjawab dalam Bahasa Indonesia dengan gaya ringkas, jelas, dan profesional. "
    "Batasi jawaban maksimal 3-4 kalimat agar cocok untuk diucapkan."
)

# ============================================================
# API KEY MANAGEMENT
# ============================================================
def get_api_key():
    if "openai_api_key" in st.session_state and st.session_state.openai_api_key:
        return st.session_state.openai_api_key
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY", "")

# ============================================================
# JAVASCRIPT UNTUK AUTO-RECORD (Voice Activity Detection)
# ============================================================
# Script ini akan merekam suara. Jika user diam selama 1.5 detik, 
# audio akan otomatis dikirim ke Streamlit.
JS_RECORDER = """
<div id="status" style="font-weight:bold; color: #ff4b4b;">🔴 Silakan bicara... (Mendengarkan)</div>
<button id="stopBtn" style="display:none;">Stop</button>
<script>
    let mediaRecorder;
    let audioChunks = [];
    let audioContext;
    let silenceTimeout;
    const SILENCE_DELAY = 1500; // 1.5 detik diam = kirim

    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
            mediaRecorder = new MediaRecorder(stream);
            audioContext = new AudioContext();
            const source = audioContext.createMediaStreamSource(stream);
            const analyser = audioContext.createAnalyser();
            analyser.fftSize = 512;
            source.connect(analyser);
            
            const dataArray = new Uint8Array(analyser.frequencyBinCount);
            
            function checkSilence() {
                if(mediaRecorder.state === "inactive") return;
                analyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for(let i = 0; i < dataArray.length; i++) {
                    sum += dataArray[i];
                }
                let average = sum / dataArray.length;
                
                if (average > 5) { // Suara terdeteksi
                    document.getElementById("status").innerText = "🟢 Suara terdeteksi...";
                    document.getElementById("status").style.color = "green";
                    clearTimeout(silenceTimeout);
                    silenceTimeout = setTimeout(stopAndSend, SILENCE_DELAY);
                } else { // Hening
                    if(!silenceTimeout) {
                        silenceTimeout = setTimeout(stopAndSend, SILENCE_DELAY);
                    }
                }
                requestAnimationFrame(checkSilence);
            }
            checkSilence();

            mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const reader = new FileReader();
                reader.readAsDataURL(audioBlob);
                reader.onloadend = () => {
                    const base64data = reader.result;
                    // Kirim data ke Streamlit
                    window.parent.postMessage({
                        isStreamlitMessage: true,
                        type: "streamlit:setComponentValue",
                        value: base64data
                    }, "*");
                }
            };
            mediaRecorder.start();
        } catch (err) {
            document.getElementById("status").innerText = "Error mic: " + err.message;
        }
    }

    function stopAndSend() {
        if(mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
            document.getElementById("status").innerText = "⏳ Memproses suara...";
            document.getElementById("status").style.color = "orange";
        }
    }

    startRecording();
</script>
"""

def auto_voice_input():
    """Menampilkan perekam suara otomatis dengan deteksi hening."""
    st.components.v1.html(JS_RECORDER, height=50)
    
    # Fungsi untuk menerima data dari JavaScript
    def on_data_change():
        if st.session_state.audio_data:
            return st.session_state.audio_data
        return None

# ============================================================
# STT (Speech-to-Text) VIA HTTP REQUEST
# ============================================================
def transcribe_audio(base64_string):
    """Mengubah base64 audio menjadi teks via Google Speech API."""
    try:
        # Decode base64 menjadi bytes
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]
        audio_bytes = base64.b64decode(base64_string)
        
        url = "http://www.google.com/speech-api/v2/recognize"
        params = {
            "client": "chromium",
            "lang": STT_LANGUAGE,
            "key": "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw", 
        }
        headers = {"Content-Type": "audio/l16; rate=16000"}
        
        response = requests.post(url, params=params, headers=headers, data=audio_bytes, timeout=15)
        
        for line in response.text.split("\n"):
            if not line.strip():
                continue
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
# AI (OpenAI)
# ============================================================
def get_ai_response(user_message, chat_history, api_key):
    if not api_key:
        return "API Key OpenAI belum diisi di sidebar.", "error"
    try:
        client = OpenAI(api_key=api_key)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS,
        )
        return response.choices[0].message.content.strip(), "ok"
    except Exception as e:
        return f"Error OpenAI: {e}", "error"

# ============================================================
# TTS (Text-to-Speech)
# ============================================================
def text_to_speech(text):
    try:
        tts = gTTS(text=text, lang=TTS_LANGUAGE, slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return audio_buffer.read()
    except Exception as e:
        st.error(f"Error TTS: {e}")
        return None

def autoplay_audio(audio_bytes):
    if not audio_bytes:
        return
    try:
        b64 = base64.b64encode(audio_bytes).decode()
        md = f'<audio autoplay="true" style="display:none;"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'
        st.markdown(md, unsafe_allow_html=True)
    except Exception:
        pass

# ============================================================
# UI & LOGIC
# ============================================================
def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "audio_data" not in st.session_state:
        st.session_state.audio_data = None
    if "processing" not in st.session_state:
        st.session_state.processing = False

def main():
    init_session_state()
    
    # Sidebar
    with st.sidebar:
        st.header("Pengaturan")
        api_key_input = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
        if api_key_input:
            st.session_state.openai_api_key = api_key_input
        
        api_key = get_api_key()
        if not api_key:
            st.warning("API Key wajib diisi!")
            
        if st.button("Hapus Riwayat Chat"):
            st.session_state.messages = []
            st.session_state.audio_data = None
            st.rerun()

    # Header
    st.title("Jarvis: Asisten Suara AI")
    st.caption("Cukup bicara, dan Jarvis akan otomatis merespon saat Anda selesai bicara.")
    
    if not api_key:
        st.info("Silakan isi OpenAI API Key di sidebar kiri.")

    # Tampilkan Riwayat Chat
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    st.divider()

    # Area Mikrofon
    st.markdown("### Mikrofon Otomatis")
    
    # Kustom komponen menggunakan JS
    rec_data = streamlit_js_eval(
        js_expressions=JS_RECORDER, 
        key="voice_recorder",
        want_output=True
    )

    # Jika JS mengirim data audio baru
    if rec_data and rec_data != st.session_state.audio_data and api_key:
        st.session_state.audio_data = rec_data
        
        # 1. Transkripsi
        with st.spinner("Mendengarkan..."):
            user_text, stt_status = transcribe_audio(rec_data)
            
        if stt_status == "ok":
            # Tampilkan User Chat
            with st.chat_message("user"):
                st.markdown(user_text)
            st.session_state.messages.append({"role": "user", "content": user_text})
            
            # 2. AI Response
            with st.spinner("Jarvis berpikir..."):
                history = st.session_state.messages[:-1]
                ai_text, ai_status = get_ai_response(user_text, history, api_key)
                
            if ai_status == "ok":
                # Tampilkan AI Chat
                with st.chat_message("assistant"):
                    st.markdown(ai_text)
                st.session_state.messages.append({"role": "assistant", "content": ai_text})
                
                # 3. Suara Jarvis (TTS)
                with st.spinner("Menyiapkan suara..."):
                    audio_bytes = text_to_speech(ai_text)
                    autoplay_audio(audio_bytes)
            else:
                st.error(ai_text)
        else:
            st.warning(user_text)
            
        # Reset data agar siap menerima suara berikutnya
        st.session_state.audio_data = None
        st.rerun()

if __name__ == "__main__":
    main()

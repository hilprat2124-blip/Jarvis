import streamlit as st
import streamlit.components.v1 as components
import os

st.set_page_config(page_title="J.A.R.V.I.S Realtime", page_icon="🔵", layout="centered")

# ============================================================
# CSS & ORB DESIGN
# ============================================================
st.markdown("""
<style>
    .stApp { background: radial-gradient(circle at 50% 10%, #001a22 0%, #000000 100%); color: #e0f7fa; font-family: 'Courier New', monospace; }
    .jarvis-container { text-align: center; margin-top: 20px; }
    .jarvis-orb-container { position: relative; width: 200px; height: 200px; margin: 20px auto; display: flex; justify-content: center; align-items: center; }
    .jarvis-orb {
        width: 120px; height: 120px;
        background: radial-gradient(circle, #00ffff 0%, #0055ff 80%, #000 100%);
        border-radius: 50%;
        box-shadow: 0 0 40px #00ffff, 0 0 80px #0055ff;
        animation: pulse 2s infinite alternate;
    }
    .jarvis-orb.active {
        background: radial-gradient(circle, #ff0055 0%, #ff5500 80%, #000 100%);
        box-shadow: 0 0 50px #ff0055, 0 0 100px #ff5500;
        animation: pulse-fast 0.8s infinite alternate;
    }
    .jarvis-ring {
        position: absolute; width: 160px; height: 160px;
        border: 1px dashed #00ffff; border-radius: 50%;
        animation: spin 10s linear infinite; opacity: 0.4;
    }
    @keyframes pulse { 0% { transform: scale(0.95); box-shadow: 0 0 30px #00ffff; } 100% { transform: scale(1.05); box-shadow: 0 0 60px #00ffff, 0 0 100px #0055ff; } }
    @keyframes pulse-fast { 0% { transform: scale(0.95); } 100% { transform: scale(1.1); } }
    @keyframes spin { 100% { transform: rotate(360deg); } }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; color: #00ffff; text-shadow: 0 0 15px #00ffff;'>J A R V I S</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #aaaaaa; font-size: 0.9em;'>Sistem Audio-to-Audio Realtime Milik Sir Lois</p>", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Konfigurasi Realtime API")
    gemini_key = st.text_input("Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
    st.info("Sistem ini menggunakan koneksi WebSocket audio-to-audio langsung (tanpa melalui jeda teks).")

if not gemini_key:
    st.warning("⚠️ Masukkan Gemini API Key di sidebar untuk memulai percakapan suara langsung.")
    st.stop()

# ============================================================
# WEBRTC / WEBSOCKET FRONTEND CLIENT
# ============================================================
html_code = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            background: transparent;
            color: #00ffff;
            font-family: monospace;
            text-align: center;
        }}
        .btn-call {{
            background: rgba(0, 255, 255, 0.1);
            border: 2px solid #00ffff;
            color: #00ffff;
            padding: 12px 28px;
            font-size: 16px;
            font-weight: bold;
            border-radius: 30px;
            cursor: pointer;
            box-shadow: 0 0 15px #00ffff;
            transition: all 0.3s ease;
            margin-top: 20px;
        }}
        .btn-call:hover {{
            background: #00ffff;
            color: #000;
            box-shadow: 0 0 30px #00ffff;
        }}
        .btn-call.active {{
            border-color: #ff0055;
            color: #ff0055;
            box-shadow: 0 0 20px #ff0055;
        }}
        #status {{
            margin-top: 15px;
            font-size: 14px;
            color: #aaaaaa;
        }}
    </style>
</head>
<body>
    <div class="jarvis-orb-container">
        <div class="jarvis-ring"></div>
        <div id="orb" class="jarvis-orb"></div>
    </div>

    <button id="toggleBtn" class="btn-call" onclick="toggleSession()">🎙️ Hubungkan Panggilan Suara</button>
    <div id="status">Status: Terputus</div>

    <script>
        let isConnected = false;
        let ws = null;
        let audioContext = null;
        let mediaStream = null;
        let processor = null;

        const apiKey = "{gemini_key}";
        const orb = document.getElementById("orb");
        const statusDiv = document.getElementById("status");
        const toggleBtn = document.getElementById("toggleBtn");

        async function toggleSession() {{
            if (!isConnected) {{
                await startAudioSession();
            }} else {{
                stopAudioSession();
            }}
        }}

        async function startAudioSession() {{
            statusDiv.innerText = "Menghubungkan ke Jarvis...";
            
            try {{
                // Inisialisasi Audio Context
                audioContext = new (window.AudioContext || window.webkitAudioContext)({{ sampleRate: 16000 }});
                mediaStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
                
                // Buka WebSocket ke Gemini Live Multimodal API
                const wsUrl = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key=${{apiKey}}`;
                ws = new WebSocket(wsUrl);

                ws.onopen = () => {{
                    isConnected = true;
                    statusDiv.innerText = "🟢 Terhubung - Bicara langsung dengan Sir Lois";
                    toggleBtn.innerText = "🛑 Akhiri Panggilan";
                    toggleBtn.classList.add("active");
                    orb.classList.add("active");

                    // Kirim Setup Handshake
                    const setupMessage = {{
                        setup: {{
                            model: "models/gemini-2.0-flash-exp",
                            generationConfig: {{
                                responseModalities: ["AUDIO"],
                                speechConfig: {{
                                    voiceConfig: {{
                                        prebuiltVoiceConfig: {{ voiceName: "Puck" }} // Pilihan suara manusiawi
                                    }}
                                }}
                            }},
                            systemInstruction: {{
                                parts: [{{ text: "Anda adalah Jarvis, asisten AI pribadi Sir Lois. Panggil pengguna dengan Sir Lois atau Sir. Berbicaralah santai, empati, manusiawi, dan lengkap dengan ekspresi napas atau tawa secara alami." }}]
                            }}
                        }}
                    }};
                    ws.send(JSON.stringify(setupMessage));
                    startAudioInput();
                }};

                ws.onmessage = async (event) => {{
                    const response = JSON.parse(event.data);
                    if (response.serverContent && response.serverContent.modelTurn) {{
                        const parts = response.serverContent.modelTurn.parts;
                        for (const part of parts) {{
                            if (part.inlineData && part.inlineData.mimeType.startsWith("audio/")) {{
                                playAudioChunk(part.inlineData.data);
                            }}
                        }}
                    }}
                }};

                ws.onclose = () => {{ stopAudioSession(); }};
                ws.onerror = (err) => {{ 
                    console.error(err); 
                    statusDiv.innerText = "❌ Koneksi Gagal"; 
                    stopAudioSession(); 
                }};

            }} catch (e) {{
                statusDiv.innerText = "❌ Akses Mikrofon Ditolak";
                console.error(e);
            }}
        }}

        function startAudioInput() {{
            const source = audioContext.createMediaStreamSource(mediaStream);
            processor = audioContext.createScriptProcessor(512, 1, 1);

            processor.onaudioprocess = (e) => {{
                if (!isConnected || ws.readyState !== WebSocket.OPEN) return;
                const inputData = e.inputBuffer.getChannelData(0);
                
                // Convert PCM 32bit float to PCM 16bit integer
                const pcm16 = new Int16Array(inputData.length);
                for (let i = 0; i < inputData.length; i++) {{
                    pcm16[i] = Math.max(-1, Math.min(1, inputData[i])) * 0x7FFF;
                }}
                
                // Encode to Base64
                const base64Audio = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)));
                
                const message = {{
                    realtimeInput: {{
                        mediaChunks: [{{
                            mimeType: "audio/pcm;rate=16000",
                            data: base64Audio
                        }}]
                    }}
                }};
                ws.send(JSON.stringify(message));
            }};

            source.connect(processor);
            processor.connect(audioContext.destination);
        }}

        function playAudioChunk(base64Data) {{
            const binary = atob(base64Data);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {{
                bytes[i] = binary.charCodeAt(i);
            }}
            const pcm16 = new Int16Array(bytes.buffer);
            const float32 = new Float32Array(pcm16.length);
            for (let i = 0; i < pcm16.length; i++) {{
                float32[i] = pcm16[i] / 0x7FFF;
            }}

            const buffer = audioContext.createBuffer(1, float32.length, 24000);
            buffer.getChannelData(0).set(float32);

            const source = audioContext.createBufferSource();
            source.buffer = buffer;
            source.connect(audioContext.destination);
            source.start();
        }}

        function stopAudioSession() {{
            isConnected = false;
            if (ws) ws.close();
            if (mediaStream) mediaStream.getTracks().forEach(track => track.stop());
            if (audioContext) audioContext.close();
            
            toggleBtn.innerText = "🎙️ Hubungkan Panggilan Suara";
            toggleBtn.classList.remove("active");
            orb.classList.remove("active");
            statusDiv.innerText = "Status: Terputus";
        }}
    </script>
</body>
</html>
"""

components.html(html_code, height=450)

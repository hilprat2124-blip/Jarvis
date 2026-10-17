import streamlit as st
import cv2
import numpy as np
from PIL import Image
import base64
import io
import os
from groq import Groq

# ============ Konfigurasi ============
st.set_page_config(page_title="AI Ngobrol + Lihat Kamera", page_icon="🤖", layout="wide")

st.title("🤖 AI Ngobrol + Bisa Lihat Objek di Kamera")
st.markdown("""
**Cara pakai:**
1. **Ketik pertanyaan** di kolom chat (bisa tanpa gambar)
2. **Ambil foto** lewat kamera, lalu tanya apa saja tentang isi foto
3. AI akan menjawab berdasarkan **teks + gambar** yang kamu kirim
""")

# ============ API Key ============
# Prioritas: Streamlit secrets > environment variable
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

if not GROQ_API_KEY:
    st.error("❌ GROQ_API_KEY belum diset.")
    st.info("""
    **Cara set API key:**
    - Lokal: `export GROQ_API_KEY='gsk_...'` atau buat file `.streamlit/secrets.toml`
    - Streamlit Cloud: Settings → Secrets → tambahkan `GROQ_API_KEY = "gsk_..."`
    
    Dapatkan API key gratis di [console.groq.com](https://console.groq.com)
    """)
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

# Model vision Groq (bisa teks + gambar)
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
TEXT_MODEL = "llama-3.3-70b-versatile"

# ============ Session State ============
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "Kamu adalah asisten AI yang ramah dan membantu. Jawab dalam Bahasa Indonesia yang natural. Jika user mengirim gambar, jelaskan apa yang kamu lihat dengan detail."}
    ]

if "pending_image" not in st.session_state:
    st.session_state.pending_image = None

# ============ Helper: Encode Gambar ============
def encode_image_to_base64(image: Image.Image) -> str:
    """Konversi PIL Image ke base64 string."""
    buffered = io.BytesIO()
    # Resize agar tidak terlalu besar (max 1024px sisi terpanjang)
    image.thumbnail((1024, 1024))
    image.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# ============ Helper: Panggil Groq ============
def ask_groq(messages: list, use_vision: bool = False) -> str:
    """Kirim pesan ke Groq, kembalikan respons teks."""
    model = VISION_MODEL if use_vision else TEXT_MODEL

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ============ Layout ============
col_cam, col_chat = st.columns([1, 1.2])

# ---------- Kolom Kamera ----------
with col_cam:
    st.subheader("📷 Kamera")

    camera_image = st.camera_input("Ambil foto objek", key="cam")

    if camera_image is not None:
        # Simpan sebagai pending image
        st.session_state.pending_image = Image.open(camera_image)
        st.image(st.session_state.pending_image, caption="Foto siap dikirim", use_container_width=True)
        st.success("✅ Foto siap! Ketik pertanyaan di chat, lalu kirim.")

    if st.session_state.pending_image is not None:
        if st.button("🗑️ Hapus foto"):
            st.session_state.pending_image = None
            st.rerun()

# ---------- Kolom Chat ----------
with col_chat:
    st.subheader("💬 Ngobrol dengan AI")

    # Tampilkan riwayat chat (skip system)
    for msg in st.session_state.messages:
        if msg["role"] == "system":
            continue
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input chat
    user_input = st.chat_input("Ketik pertanyaan... (misal: 'Apa yang kamu lihat?' atau 'Halo, apa kabar?')")

    if user_input:
        # Siapkan pesan user
        has_image = st.session_state.pending_image is not None

        if has_image:
            # Encode gambar
            b64 = encode_image_to_base64(st.session_state.pending_image)

            # Format pesan multimodal Groq
            user_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_input},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                    }
                ]
            }
            # Untuk history, kita simpan versi teks + penanda gambar
            display_content = f"🖼️ *(dengan gambar)* {user_input}"
        else:
            user_message = {"role": "user", "content": user_input}
            display_content = user_input

        # Tambah ke session state (untuk ditampilkan)
        st.session_state.messages.append({"role": "user", "content": display_content})

        # Tampilkan pesan user
        with st.chat_message("user"):
            if has_image:
                st.image(st.session_state.pending_image, width=200)
            st.markdown(user_input)

        # Panggil AI
        with st.chat_message("assistant"):
            with st.spinner("AI sedang berpikir..."):
                # Siapkan messages untuk API
                # Konversi history ke format yang sesuai
                api_messages = [st.session_state.messages[0]]  # system
                for m in st.session_state.messages[1:-1]:  # skip system & pesan user terbaru
                    api_messages.append({"role": m["role"], "content": m["content"]})

                # Tambahkan pesan user terbaru (dengan gambar jika ada)
                api_messages.append(user_message)

                response_text = ask_groq(api_messages, use_vision=has_image)
                st.markdown(response_text)

        # Simpan respons AI
        st.session_state.messages.append({"role": "assistant", "content": response_text})

        # Reset pending image setelah dikirim
        if has_image:
            st.session_state.pending_image = None
            st.rerun()

# ============ Sidebar ============
with st.sidebar:
    st.header("ℹ️ Info")

    if st.button("🔄 Reset Chat"):
        st.session_state.messages = [
            {"role": "system", "content": "Kamu adalah asisten AI yang ramah dan membantu. Jawab dalam Bahasa Indonesia yang natural. Jika user mengirim gambar, jelaskan apa yang kamu lihat dengan detail."}
        ]
        st.session_state.pending_image = None
        st.rerun()

    st.markdown("---")
    st.markdown(f"**Model Vision:** `{VISION_MODEL}`")
    st.markdown(f"**Model Teks:** `{TEXT_MODEL}`")
    st.markdown("""
    **Tips:**
    - Foto objek dengan pencahayaan cukup
    - Tanya spesifik: "Apa warna benda ini?", "Berapa jumlah orang?"
    - Bisa ngobrol tanpa gambar juga
    - Gambar otomatis di-resize max 1024px agar hemat token
    """)

    st.markdown("---")
    st.caption("Ditenagai Groq API • Llama 4 Scout (Vision)")

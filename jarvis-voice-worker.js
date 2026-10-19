// Jarvis Neural Voice — sintesis suara lokal (model Kokoro 82M) di luar thread UI,
// jadi animasi, notifikasi, dan kamera tidak pernah membuat suara tersendat.
import { KokoroTTS } from 'https://cdn.jsdelivr.net/npm/kokoro-js@1.2.1/dist/kokoro.web.js';

const MODEL = 'onnx-community/Kokoro-82M-v1.0-ONNX';
let backend = '', wasmOnly = false, tts = null, loading = null, queue = [], busy = false, cancelBefore = 0;

async function load() {
  if (tts) return tts;
  if (!loading) {
    let last = -1;
    const cb = p => {
      if (p.status !== 'progress' || !/\.onnx$/.test(p.file || '')) return;
      const pct = Math.round(p.progress || 0);
      if (pct !== last) { last = pct; postMessage({ type: 'progress', pct }); }
    };
    loading = (async () => {
      // WebGPU (kartu grafis) jauh lebih cepat dari CPU; kalau tidak ada / gagal → WASM
      if (!wasmOnly && self.navigator && navigator.gpu) {
        try {
          const g = await KokoroTTS.from_pretrained(MODEL, { dtype: 'fp32', device: 'webgpu', progress_callback: cb });
          await g.generate('Ready.', { voice: 'bm_george' });
          backend = 'webgpu'; postMessage({ type: 'backend', device: 'webgpu' });
          return g;
        } catch (_) { last = -1; }
      }
      const g = await KokoroTTS.from_pretrained(MODEL, { dtype: 'q8', device: 'wasm', progress_callback: cb });
      backend = 'wasm'; postMessage({ type: 'backend', device: 'wasm' });
      return g;
    })().catch(e => { loading = null; throw e; });
  }
  tts = await loading;
  // pemanasan: kalimat pertama yang sungguhan langsung cepat
  try { await tts.generate('Ready.', { voice: 'bm_george' }); } catch (_) {}
  return tts;
}

/* Poles tiap kalimat: buang hening di ujung, fade halus (anti klik),
   dan samakan kekerasan suara supaya volume selalu stabil, tidak mengecil */
function polish(pcm, sr) {
  const gate = 0.006;
  let a = 0, b = pcm.length - 1;
  while (a < b && Math.abs(pcm[a]) < gate) a++;
  while (b > a && Math.abs(pcm[b]) < gate) b--;
  a = Math.max(0, a - Math.round(sr * 0.02));
  b = Math.min(pcm.length - 1, b + Math.round(sr * 0.06));
  const out = pcm.slice(a, b + 1);
  let sum = 0, peak = 0;
  for (let i = 0; i < out.length; i++) {
    const v = out[i]; sum += v * v;
    const m = v < 0 ? -v : v; if (m > peak) peak = m;
  }
  const rms = Math.sqrt(sum / Math.max(1, out.length));
  let g = rms > 1e-4 ? 0.1 / rms : 1;          // target ±-20 dBFS
  if (peak * g > 0.9) g = 0.9 / peak;
  const fade = Math.min(out.length >> 2, Math.round(sr * 0.008));
  const n = out.length;
  for (let i = 0; i < n; i++) {
    let k = g;
    if (i < fade) k *= i / fade;
    else if (i > n - 1 - fade) k *= (n - 1 - i) / fade;
    out[i] *= k;
  }
  return out;
}

/* Satu kalimat gagal tidak boleh merusak jawaban: WebGPU error → pindah ke WASM lalu ulangi; WASM → ulangi sekali */
async function gen(model, job) {
  const o = { voice: job.voice, speed: job.speed };
  try { return await model.generate(job.text, o); }
  catch (e) {
    if (backend === 'webgpu') { wasmOnly = true; tts = null; loading = null; return await (await load()).generate(job.text, o); }
    return await model.generate(job.text, o);
  }
}

async function pump() {
  if (busy) return;
  busy = true;
  while (queue.length) {
    const job = queue.shift();
    if (job.id < cancelBefore) continue;
    try {
      const model = await load();
      if (job.id < cancelBefore) continue;
      const audio = await gen(model, job);
      if (job.id < cancelBefore) continue;
      const pcm = polish(audio.audio, audio.sampling_rate);
      postMessage({ type: 'audio', id: job.id, idx: job.idx, sr: audio.sampling_rate, pcm }, [pcm.buffer]);
    } catch (e) {
      postMessage({ type: 'fail', id: job.id, idx: job.idx, msg: String(e?.message || e) });
    }
  }
  busy = false;
}

self.onmessage = async ({ data: m }) => {
  if (m.type === 'load') {
    try { await load(); postMessage({ type: 'ready' }); }
    catch (e) { postMessage({ type: 'error', msg: String(e?.message || e) }); }
  } else if (m.type === 'speak') {
    queue.push(m); pump();
  } else if (m.type === 'cancel') {
    cancelBefore = Math.max(cancelBefore, m.before);
    queue = queue.filter(j => j.id >= cancelBefore);
  }
};

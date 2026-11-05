import json
import re
import tempfile
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median

import streamlit as st
from faster_whisper import WhisperModel

st.set_page_config(page_title="Sincronizador de canciones", page_icon="🎵", layout="centered")
st.title("🎵 Sincronizador de canciones")
st.write("Alinea la letra original con el audio y estima el instante en que empieza cada verso.")

@st.cache_resource
def load_model(model_name):
    return WhisperModel(model_name, device="cpu", compute_type="int8")

def normalize_token(token):
    token = unicodedata.normalize("NFD", token.lower())
    token = "".join(ch for ch in token if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", token)

def tokenize_line(line):
    return re.findall(r"[\wÀ-ÿ]+(?:['’][\wÀ-ÿ]+)?", line, flags=re.UNICODE)

def similarity(a, b):
    return SequenceMatcher(None, normalize_token(a), normalize_token(b)).ratio()

def align_lyrics_to_words(lines, words, onset_advance=0.18, estimate_missing=True):
    expected, ranges = [], []
    for line_index, line in enumerate(lines):
        tokens = tokenize_line(line)
        if tokens:
            start = len(expected)
            expected.extend((token, line_index) for token in tokens)
            ranges.append((line_index, start, len(expected)))

    observed = [w.word.strip() for w in words]
    n, m = len(expected), len(observed)
    if not n or not m:
        return [], list(range(len(lines)))

    gap = 0.82
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0], back[i][0] = i * gap, 1
    for j in range(1, m + 1):
        dp[0][j], back[0][j] = j * gap, 2

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sim = similarity(expected[i - 1][0], observed[j - 1])
            choices = (
                (dp[i - 1][j - 1] + 1.0 - sim, 0),
                (dp[i - 1][j] + gap, 1),
                (dp[i][j - 1] + gap, 2),
            )
            dp[i][j], back[i][j] = min(choices, key=lambda x: x[0])

    token_to_word = {}
    i, j = n, m
    while i > 0 or j > 0:
        move = back[i][j]
        if i > 0 and j > 0 and move == 0:
            if similarity(expected[i - 1][0], observed[j - 1]) >= 0.42:
                token_to_word[i - 1] = j - 1
            i -= 1
            j -= 1
        elif i > 0 and (j == 0 or move == 1):
            i -= 1
        else:
            j -= 1

    # Estimate a local speaking/singing rate from adjacent recognized words.
    rates = []
    for w in words:
        duration = max(0.0, float(w.end) - float(w.start))
        chars = max(1, len(normalize_token(w.word)))
        if duration > 0.03:
            rates.append(duration / chars)
    seconds_per_char = median(rates) if rates else 0.055
    seconds_per_char = min(0.12, max(0.025, seconds_per_char))

    output, unmatched = [], []
    for line_index, start, end in ranges:
        matched_pairs = [(k, token_to_word[k]) for k in range(start, end) if k in token_to_word]
        if not matched_pairs:
            unmatched.append(line_index)
            continue

        first_expected, first_word_idx = min(matched_pairs, key=lambda pair: pair[1])
        first_word = words[first_word_idx]
        estimated_leading = 0.0

        # If the recognizer missed the first word(s) of a line, estimate their
        # duration from the local word rate rather than starting mid-line.
        if estimate_missing and first_expected > start:
            missing_text = "".join(expected[k][0] for k in range(start, first_expected))
            estimated_leading = min(0.9, len(normalize_token(missing_text)) * seconds_per_char)

        timestamp = max(0.0, float(first_word.start) - estimated_leading - onset_advance)
        output.append({"text": lines[line_index].strip(), "time": round(timestamp, 2)})

    output.sort(key=lambda item: item["time"])
    return output, unmatched

with st.sidebar:
    st.header("Configuración")
    model_name = st.selectbox("Modelo de reconocimiento", ["small", "medium", "large-v3"], index=1)
    language_choice = st.selectbox("Idioma", ["Español", "Detectar automáticamente", "Inglés", "Francés", "Alemán", "Italiano", "Portugués"])
    language_map = {
        "Detectar automáticamente": None, "Español": "es", "Inglés": "en",
        "Francés": "fr", "Alemán": "de", "Italiano": "it", "Portugués": "pt"
    }
    st.subheader("Ajuste del inicio")
    onset_advance = st.slider(
        "Adelantar marca respecto a la primera palabra detectada",
        min_value=0.0, max_value=0.7, value=0.18, step=0.02,
        help="Prueba 0,18 s inicialmente. Aumenta el valor si las marcas siguen apareciendo tarde."
    )
    estimate_missing = st.checkbox("Estimar palabras iniciales no reconocidas", value=True)
    st.caption("Python 3.12 de 64 bits. El procesamiento es local.")

uploaded = st.file_uploader("1. Selecciona la canción", type=["mp3", "wav", "m4a", "flac", "ogg", "aac"])
lyrics = st.text_area("2. Pega la letra original (un verso por línea)", height=300,
    placeholder="Una línea por verso, respetando los saltos de línea.")
st.caption("Cada línea no vacía de la letra se convertirá en una entrada del JSON.")

if uploaded and lyrics.strip():
    st.audio(uploaded)
    if st.button("✨ Alinear letra y generar JSON", type="primary", use_container_width=True):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix or ".audio") as tmp:
                tmp.write(uploaded.getbuffer())
                temp_path = tmp.name

            with st.spinner("Cargando el modelo…"):
                model = load_model(model_name)

            progress = st.progress(0, text="Reconociendo palabras y sus tiempos…")
            segments, info = model.transcribe(
                temp_path,
                language=language_map[language_choice],
                beam_size=5,
                word_timestamps=True,
                vad_filter=False,
                condition_on_previous_text=False
            )
            words = []
            for segment in segments:
                if segment.words:
                    words.extend(segment.words)
                progress.progress(min(80, 5 + len(words) // 3), text="Calculando el inicio de cada verso…")

            lyric_lines = [line for line in lyrics.splitlines() if line.strip()]
            result, unmatched = align_lyrics_to_words(
                lyric_lines, words, onset_advance=onset_advance, estimate_missing=estimate_missing
            )
            progress.progress(100, text="Alineación terminada")

            if not words:
                st.error("No se han reconocido palabras. Prueba otro modelo o comprueba el audio.")
            elif not result:
                st.error("No se ha podido alinear ninguna línea. Prueba con medium o large-v3.")
            else:
                data = json.dumps(result, ensure_ascii=False, indent=2)
                st.success(f"{len(result)} de {len(lyric_lines)} versos alineados. Idioma detectado: {info.language}.")
                st.subheader("JSON generado")
                st.code(data, language="json")
                st.download_button("⬇️ Descargar JSON", data=data.encode("utf-8"),
                    file_name=Path(uploaded.name).stem + ".json", mime="application/json",
                    use_container_width=True)
                if unmatched:
                    st.warning(f"{len(unmatched)} líneas no encontraron coincidencia fiable.")
                    with st.expander("Ver líneas sin tiempo asignado"):
                        for idx in unmatched:
                            st.write(f"• {lyric_lines[idx]}")
                st.info(
                    f"Se ha aplicado un adelanto de {onset_advance:.2f} s y "
                    + ("una estimación de palabras iniciales omitidas." if estimate_missing else "sin estimar palabras omitidas.")
                    + " Son estimaciones: escucha los puntos dudosos y ajusta el adelanto si hace falta."
                )
        except Exception as error:
            st.error(f"No se pudo procesar el audio: {error}")
        finally:
            if temp_path and Path(temp_path).exists():
                Path(temp_path).unlink()
elif uploaded:
    st.info("Pega también la letra original para asignar los tiempos a cada verso.")

st.divider()
st.caption("Formato de salida: una entrada por verso, con text y time. Los tiempos son estimaciones basadas en el reconocimiento de audio.")

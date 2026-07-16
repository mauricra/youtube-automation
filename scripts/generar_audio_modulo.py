"""
Módulo 2 — Audio con ElevenLabs + verificación de +10 min.

Si el audio EN queda corto, borra el archivo, marca 'necesita_extension'
con las palabras faltantes estimadas, y NO genera ES ni short.
Claude Code lee ese flag del reporte y extiende el guion.
"""

import os
import sys
import json
import time
import logging
import subprocess
import requests

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "config"))
from config import (
    ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID_EN, ELEVENLABS_VOICE_ID_ES,
    ELEVENLABS_MODEL_ID, ELEVENLABS_VOICE_SETTINGS,
    DURACION_MINIMA_AUDIO_SEGUNDOS, WORK_DIR, LOG_DIR
)

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "02_audio.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
MAX_CHARS_POR_REQUEST = 4500


def obtener_duracion_audio(audio_path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", audio_path]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def _trocear_texto(texto: str, max_chars: int) -> list[str]:
    if len(texto) <= max_chars:
        return [texto]
    bloques = []
    actual = ""
    for oracion in texto.replace("\n", " ").split(". "):
        oracion = oracion.strip()
        if not oracion:
            continue
        candidato = (actual + ". " + oracion).strip() if actual else oracion
        if len(candidato) > max_chars:
            bloques.append(actual.strip() + ".")
            actual = oracion
        else:
            actual = candidato
    if actual:
        bloques.append(actual.strip() + ".")
    return bloques


def generar_audio_elevenlabs(texto: str, voice_id: str, output_path: str, idioma: str) -> str:
    bloques = _trocear_texto(texto, MAX_CHARS_POR_REQUEST)
    audio_bytes = b""
    for idx, bloque in enumerate(bloques):
        logger.info(f"Audio {idioma} bloque {idx+1}/{len(bloques)} ({len(bloque)} chars)")
        resp = requests.post(
            ELEVENLABS_TTS_URL.format(voice_id=voice_id),
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={"text": bloque, "model_id": ELEVENLABS_MODEL_ID, "voice_settings": ELEVENLABS_VOICE_SETTINGS},
            timeout=180,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs API error: {resp.status_code} - {resp.text}")
        audio_bytes += resp.content
        time.sleep(0.5)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    return output_path


def procesar_audios_de_video(item: dict) -> dict:
    fecha = item["fecha"]
    work_today = os.path.join(WORK_DIR, fecha, item["video_id"])
    os.makedirs(work_today, exist_ok=True)

    audio_en_path = os.path.join(work_today, "audio_en.mp3")
    audio_es_path = os.path.join(work_today, "audio_es.mp3")
    audio_short_path = os.path.join(work_today, "audio_short_en.mp3")

    generar_audio_elevenlabs(item["guion_en"], ELEVENLABS_VOICE_ID_EN, audio_en_path, "EN")
    duracion = obtener_duracion_audio(audio_en_path)
    logger.info(f"{item['video_id']}: audio EN = {duracion:.0f}s")

    if duracion < DURACION_MINIMA_AUDIO_SEGUNDOS:
        palabras_actuales = len(item["guion_en"].split())
        factor = DURACION_MINIMA_AUDIO_SEGUNDOS / max(duracion, 1)
        palabras_faltantes = int(palabras_actuales * (factor - 1)) + 100
        os.remove(audio_en_path)
        item["necesita_extension"] = True
        item["palabras_faltantes"] = palabras_faltantes
        item["duracion_obtenida"] = round(duracion)
        return item

    generar_audio_elevenlabs(item["guion_es"], ELEVENLABS_VOICE_ID_ES, audio_es_path, "ES")
    generar_audio_elevenlabs(item["hook_short_en"], ELEVENLABS_VOICE_ID_EN, audio_short_path, "EN-short")

    item["audio_en_path"] = audio_en_path
    item["audio_es_path"] = audio_es_path
    item["audio_short_path"] = audio_short_path
    item["duracion_audio_en"] = duracion
    item.pop("necesita_extension", None)
    item.pop("palabras_faltantes", None)
    return item


def correr_modulo_audio(items: list[dict]) -> list[dict]:
    resultado = []
    for item in items:
        try:
            resultado.append(procesar_audios_de_video(item))
        except Exception as e:
            logger.error(f"Fallo audio {item['video_id']}: {e}")
            resultado.append(item)
    return resultado

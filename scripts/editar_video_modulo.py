"""
Módulo 3 — Edición de video.

Toma el gameplay de disco local (Claude Code ya lo descargó vía conector
Drive antes de invocar el pipeline), lo recorta a la duración del audio EN,
agrega subtítulos TikTok y exporta video largo + short vertical.

Ruta esperada: /tmp/fuente_gameplays/[GTA|Minecraft|Subway Surfers]/*.mp4
"""

import os
import sys
import glob
import random
import logging
import subprocess
import json

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "config"))
from config import (
    VIDEO_RESOLUTION, VIDEO_FPS, SHORT_DURACION_SEGUNDOS,
    SUBTITULOS_FUENTE, SUBTITULOS_TAMANO, SUBTITULOS_TAMANO_SHORT,
    SUBTITULOS_COLOR, SUBTITULOS_BORDE_COLOR,
    SUBTITULOS_PALABRAS_POR_GRUPO, SUBTITULOS_PALABRAS_POR_GRUPO_SHORT,
    WORK_DIR, LOG_DIR, CHANNELS,
    GAMEPLAYS_DIR,
)

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "03_video.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def obtener_duracion_media(path: str) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def elegir_clips_para_duracion(gameplay_subcarpeta: str, duracion_objetivo: float, margen: float = 45.0) -> list[str]:
    """
    Elige clips aleatorios y va sumando sus duraciones reales (medidas con
    ffprobe) hasta cubrir duracion_objetivo + margen. Así no importa si los
    clips duran 45s o 90s: se toman los que hagan falta para cubrir el audio
    completo (10-15 min) sin loops visibles.

    Prioriza clips únicos (sin repetir); si el banco no alcanza, vuelve a
    barajar y repite clips (mejor una repetición lejana que fallar).
    """
    carpeta = os.path.join(GAMEPLAYS_DIR, gameplay_subcarpeta)
    if not os.path.isdir(carpeta):
        raise RuntimeError(
            f"No existe {carpeta}. Claude Code debe descargar clips "
            f"de fuente_gameplays/{gameplay_subcarpeta} en Drive a esa ruta ANTES "
            f"de correr el pipeline."
        )

    archivos = []
    for ext in ("*.mp4", "*.mov", "*.mkv"):
        archivos.extend(glob.glob(os.path.join(carpeta, ext)))

    if not archivos:
        raise RuntimeError(
            f"No hay clips en {carpeta}. Claude Code debe descargar clips "
            f"de fuente_gameplays/{gameplay_subcarpeta} en Drive."
        )

    objetivo = duracion_objetivo + margen
    elegidos = []
    acumulado = 0.0
    pool = archivos[:]
    random.shuffle(pool)

    while acumulado < objetivo:
        if not pool:
            # Se acabaron los clips únicos: rebarajar todo y seguir (repite)
            pool = archivos[:]
            random.shuffle(pool)
            logger.warning(
                f"{gameplay_subcarpeta}: el banco no alcanza para {objetivo:.0f}s "
                f"sin repetir; se repiten clips."
            )
        clip = pool.pop()
        try:
            dur = obtener_duracion_media(clip)
        except Exception as e:
            logger.warning(f"Clip ilegible, se saltea: {os.path.basename(clip)} ({e})")
            continue
        elegidos.append(clip)
        acumulado += dur

    logger.info(
        f"Gameplays elegidos ({gameplay_subcarpeta}): {len(elegidos)} clips, "
        f"{acumulado:.0f}s acumulados para {duracion_objetivo:.0f}s de audio — "
        f"{[os.path.basename(e) for e in elegidos]}"
    )
    return elegidos


def concatenar_clips(clips: list[str], output_path: str) -> str:
    """
    Concatena varios clips en un único video, normalizando resolución y fps
    para evitar problemas al unirlos (los clips originales pueden tener
    distinta resolución, codec o framerate).
    """
    escala = (
        f"scale={VIDEO_RESOLUTION[0]}:{VIDEO_RESOLUTION[1]}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_RESOLUTION[0]}:{VIDEO_RESOLUTION[1]},setsar=1"
    )

    # Armar el filter_complex para normalizar cada clip y luego concatenarlos
    inputs = []
    filter_parts = []
    for i, clip in enumerate(clips):
        inputs.extend(["-i", clip])
        filter_parts.append(f"[{i}:v]{escala},fps={VIDEO_FPS},format=yuv420p[v{i}]")

    concat_inputs = "".join(f"[v{i}]" for i in range(len(clips)))
    filter_complex = ";".join(filter_parts) + f";{concat_inputs}concat=n={len(clips)}:v=1:a=0[outv]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-an",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"Concatenados {len(clips)} clips → {output_path}")
    return output_path


def recortar_clip_a_duracion(clip_path: str, duracion_objetivo: float, output_path: str) -> str:
    duracion_fuente = obtener_duracion_media(clip_path)
    escala = (
        f"scale={VIDEO_RESOLUTION[0]}:{VIDEO_RESOLUTION[1]}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_RESOLUTION[0]}:{VIDEO_RESOLUTION[1]}"
    )

    if duracion_fuente >= duracion_objetivo + 5:
        inicio = random.uniform(0, duracion_fuente - duracion_objetivo - 2)
        cmd = [
            "ffmpeg", "-y", "-ss", str(inicio), "-i", clip_path,
            "-t", str(duracion_objetivo),
            "-vf", escala, "-r", str(VIDEO_FPS), "-an",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", clip_path,
            "-t", str(duracion_objetivo),
            "-vf", escala, "-r", str(VIDEO_FPS), "-an",
            output_path,
        ]

    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def generar_subtitulos_srt(texto: str, duracion_audio: float, output_srt_path: str,
                           palabras_por_grupo: int = SUBTITULOS_PALABRAS_POR_GRUPO) -> str:
    """Subtítulos TikTok: grupos de N palabras, sincronizados proporcionalmente."""
    palabras = texto.split()
    grupos = [palabras[i:i + palabras_por_grupo]
              for i in range(0, len(palabras), palabras_por_grupo)]
    tiempo_por_palabra = duracion_audio / max(len(palabras), 1)

    def fmt(s: float) -> str:
        h = int(s // 3600); m = int((s % 3600) // 60); ss = s % 60
        return f"{h:02d}:{m:02d}:{ss:06.3f}".replace(".", ",")

    lineas = []
    t = 0.0
    for idx, grupo in enumerate(grupos, start=1):
        dur = tiempo_por_palabra * len(grupo)
        lineas.extend([str(idx), f"{fmt(t)} --> {fmt(t + dur)}", " ".join(grupo), ""])
        t += dur

    with open(output_srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    return output_srt_path


def quemar_subtitulos_y_audio(video_path: str, audio_path: str, srt_path: str, output_path: str) -> str:
    # BorderStyle=1 = texto con borde fino y sombra (sin caja negra de fondo).
    # MarginV=25 en escala ASS = pegado abajo, deja ver el gameplay.
    style = (
        f"FontName={SUBTITULOS_FUENTE},FontSize={SUBTITULOS_TAMANO},Bold=1,"
        f"PrimaryColour={SUBTITULOS_COLOR},OutlineColour={SUBTITULOS_BORDE_COLOR},"
        f"BorderStyle=1,Outline=1.3,Shadow=0.6,Alignment=2,MarginV=25"
    )
    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
        "-vf", f"subtitles={srt_path}:force_style='{style}'",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-shortest", output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def armar_short_vertical(gameplay_path: str, audio_short_path: str, srt_short_path: str, output_path: str) -> str:
    duracion_short = min(obtener_duracion_media(audio_short_path), SHORT_DURACION_SEGUNDOS)
    # Tamaño moderado para vertical, centrado abajo pero por encima de la UI
    # de YouTube Shorts (MarginV=55). Sin caja negra.
    style = (
        f"FontName={SUBTITULOS_FUENTE},FontSize={SUBTITULOS_TAMANO_SHORT},Bold=1,"
        f"PrimaryColour={SUBTITULOS_COLOR},OutlineColour={SUBTITULOS_BORDE_COLOR},"
        f"BorderStyle=1,Outline=1.5,Shadow=0.6,Alignment=2,MarginV=55"
    )
    cmd = [
        "ffmpeg", "-y", "-i", gameplay_path, "-i", audio_short_path,
        "-t", str(duracion_short),
        "-vf", f"crop=ih*9/16:ih,scale=1080:1920,subtitles={srt_short_path}:force_style='{style}'",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def procesar_video_de_item(item: dict) -> dict:
    fecha = item["fecha"]
    work_dir = os.path.join(WORK_DIR, fecha, item["video_id"])
    os.makedirs(work_dir, exist_ok=True)

    canal_config = CHANNELS[item["canal_key"]]
    duracion_audio_en = obtener_duracion_media(item["audio_en_path"])

    # Elegimos clips aleatorios hasta cubrir la duración del audio (+margen):
    # con clips de 45-90s y audio de 10-15 min, salen ~8-16 clips distintos.
    # Así el gameplay cambia constantemente y no hay loops visibles.
    clips_fuente = elegir_clips_para_duracion(
        canal_config["gameplay_subcarpeta"], duracion_audio_en
    )
    gameplay_combinado = concatenar_clips(
        clips_fuente, os.path.join(work_dir, "gameplay_combinado.mp4")
    )
    clip_recortado = recortar_clip_a_duracion(
        gameplay_combinado, duracion_audio_en, os.path.join(work_dir, "gameplay_recortado.mp4")
    )

    srt_largo = generar_subtitulos_srt(
        item["guion_en"], duracion_audio_en, os.path.join(work_dir, "subs_largo.srt")
    )
    video_final_path = os.path.join(work_dir, f"{item['video_id']}_FINAL.mp4")
    quemar_subtitulos_y_audio(clip_recortado, item["audio_en_path"], srt_largo, video_final_path)

    duracion_short = obtener_duracion_media(item["audio_short_path"])
    srt_short = generar_subtitulos_srt(
        item["hook_short_en"], duracion_short, os.path.join(work_dir, "subs_short.srt"),
        palabras_por_grupo=SUBTITULOS_PALABRAS_POR_GRUPO_SHORT,
    )
    short_final_path = os.path.join(work_dir, f"{item['video_id']}_SHORT.mp4")
    armar_short_vertical(clip_recortado, item["audio_short_path"], srt_short, short_final_path)

    # Copiar audio_es al mismo dir con nombre limpio para Claude Code
    audio_es_final = os.path.join(work_dir, f"{item['video_id']}_AUDIO_ES.mp3")
    import shutil
    shutil.copy(item["audio_es_path"], audio_es_final)

    item["video_final_path"] = video_final_path
    item["short_final_path"] = short_final_path
    item["audio_es_final_path"] = audio_es_final
    return item


def correr_modulo_video(items: list[dict]) -> list[dict]:
    resultado = []
    for item in items:
        try:
            resultado.append(procesar_video_de_item(item))
            logger.info(f"Video listo: {item['video_id']}")
        except Exception as e:
            logger.error(f"Fallo video {item['video_id']}: {e}")
            resultado.append(item)
    return resultado

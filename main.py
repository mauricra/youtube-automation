#!/usr/bin/env python3
"""
ORQUESTADOR — YouTube Automation Pipeline

Flujo:
  0. Claude Code (con conector Drive) descarga los gameplays a /tmp/fuente_gameplays/
     y escribe los guiones como JSON en work/[fecha]/
  1. Este script carga y valida los guiones
  2. ElevenLabs: audio EN (verificado +10 min), ES, y short
  3. Edición: gameplay local + subtítulos TikTok
  4. Deja los archivos finales en work/[fecha]/[video_id]/ con nombres claros:
       [video_id]_FINAL.mp4       -> subir a Videos/[canal]/
       [video_id]_AUDIO_ES.mp3    -> subir a Videos/[canal]/
       [video_id]_SHORT.mp4       -> subir a Videos/[canal]/
     Claude Code (con conector Drive) los sube después.

USO:
  python main.py                        # pipeline completo
  python main.py --solo-audio           # corta después del audio
  python main.py --regenerar VIDEO_ID   # limpia un video puntual y lo reprocesa
  python main.py --desde-fecha 2026-07-13

CÓDIGOS DE SALIDA:
  0 = todos los videos listos en disco para que Claude Code los suba
  2 = guiones faltantes o inválidos (Claude Code debe corregir JSONs)
  3 = uno o más audios cortos (Claude Code debe extender guiones)
  4 = error de infraestructura (ElevenLabs, ffmpeg, gameplays faltantes)
"""

import os
import sys
import json
import shutil
import logging
import argparse
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
sys.path.insert(0, os.path.join(BASE_DIR, "config"))

from config import WORK_DIR, LOG_DIR, TOTAL_VIDEOS_DIA

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(WORK_DIR, exist_ok=True)

logging.basicConfig(
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "pipeline_main.log")),
        logging.StreamHandler(sys.stdout),
    ],
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(module)s] %(message)s",
)
logger = logging.getLogger(__name__)

import cargar_guiones_modulo
import generar_audio_modulo
import editar_video_modulo


def _estado_path(fecha: str) -> str:
    return os.path.join(WORK_DIR, fecha, "_estado_pipeline.json")


def guardar_estado(fecha: str, items: list[dict]):
    os.makedirs(os.path.join(WORK_DIR, fecha), exist_ok=True)
    with open(_estado_path(fecha), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def cargar_estado(fecha: str) -> list[dict]:
    path = _estado_path(fecha)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fusionar_guiones_frescos(items_estado: list[dict], items_json: list[dict]) -> list[dict]:
    """Combina progreso guardado con el contenido fresco de los JSON."""
    progreso = {i["video_id"]: i for i in items_estado}
    resultado = []
    for item in items_json:
        previo = progreso.get(item["video_id"], {})
        combinado = {**previo, **item}
        resultado.append(combinado)
    return resultado


def regenerar_video(fecha: str, video_id: str):
    carpeta_video = os.path.join(WORK_DIR, fecha, video_id)
    if os.path.isdir(carpeta_video):
        shutil.rmtree(carpeta_video)
        logger.info(f"Limpiado trabajo de {video_id}")

    items = cargar_estado(fecha)
    items = [i for i in items if i["video_id"] != video_id]
    guardar_estado(fecha, items)


def correr_pipeline(fecha: str, solo_audio: bool = False) -> int:
    logger.info("=" * 60)
    logger.info(f"PIPELINE — {fecha} — {TOTAL_VIDEOS_DIA} videos objetivo")
    logger.info("=" * 60)

    # ── MÓDULO 1: cargar guiones ──
    try:
        items_json = cargar_guiones_modulo.cargar_guiones_del_dia(fecha)
    except RuntimeError as e:
        logger.error(str(e))
        return 2

    items = fusionar_guiones_frescos(cargar_estado(fecha), items_json)
    guardar_estado(fecha, items)
    logger.info(f"✓ Módulo 1: {len(items)} guiones cargados y validados")

    # ── MÓDULO 2: audio ──
    pendientes = [i for i in items if not os.path.exists(i.get("audio_en_path", ""))]
    listos = [i for i in items if i not in pendientes]
    if pendientes:
        try:
            procesados = generar_audio_modulo.correr_modulo_audio(pendientes)
            items = listos + procesados
            guardar_estado(fecha, items)
        except Exception as e:
            logger.error(f"Error crítico en módulo audio: {e}")
            return 4

    con_audio = [i for i in items if "audio_en_path" in i]
    cortos = [i for i in items if i.get("necesita_extension")]

    if solo_audio:
        _reporte_final(items, fecha)
        return 3 if cortos else 0

    # ── MÓDULO 3: video ──
    pendientes = [i for i in con_audio if not os.path.exists(i.get("video_final_path", ""))]
    listos = [i for i in con_audio if i not in pendientes]
    if pendientes:
        try:
            procesados = editar_video_modulo.correr_modulo_video(pendientes)
            con_video = listos + procesados
        except Exception as e:
            logger.error(f"Error crítico en módulo video: {e}")
            return 4
    else:
        con_video = con_audio

    items = cortos + con_video
    guardar_estado(fecha, items)
    completos = [i for i in items if "video_final_path" in i]
    logger.info(f"✓ Módulo 3: {len(completos)} videos listos en disco")

    _reporte_final(items, fecha)

    if cortos:
        return 3
    if len(completos) < len(items):
        return 4
    return 0


def _reporte_final(items: list[dict], fecha: str):
    logger.info("=" * 60)
    logger.info(f"REPORTE FINAL — {fecha}")

    completos = [i for i in items if "video_final_path" in i]
    cortos = [i for i in items if i.get("necesita_extension")]
    otros = [i for i in items if i not in completos and i not in cortos]

    logger.info(f"\n{'='*60}\nARCHIVOS LISTOS PARA SUBIR A DRIVE:\n{'='*60}")
    for i in completos:
        from config import CHANNELS
        canal_drive = CHANNELS[i["canal_key"]]["nombre_carpeta_drive"]
        dur = i.get("duracion_audio_en", 0)
        vid = i["video_id"]
        work_dir = os.path.join(WORK_DIR, fecha, vid)
        logger.info(f"\n  Video: {i['titulo'][:60]}  ({dur/60:.1f} min)")
        logger.info(f"  Canal destino en Drive: Videos/{canal_drive}/")
        logger.info(f"  Archivos a subir:")
        logger.info(f"    - {work_dir}/{vid}_FINAL.mp4")
        logger.info(f"    - {work_dir}/{vid}_AUDIO_ES.mp3")
        logger.info(f"    - {work_dir}/{vid}_SHORT.mp4")

    for i in cortos:
        logger.info(
            f"\n  ✗ GUION CORTO: {i['video_id']} duró {i.get('duracion_obtenida', '?')}s, "
            f"faltan ~{i.get('palabras_faltantes', '?')} palabras."
        )
        logger.info(
            f"    → Extender guion_en y guion_es en work/{fecha}/{i['video_id']}.json, "
            f"luego: python main.py --regenerar {i['video_id']} && python main.py"
        )

    for i in otros:
        logger.info(f"  ✗ INCOMPLETO: {i['video_id']} — revisar logs/")

    logger.info(f"\n  Total: {len(completos)}/{len(items)} listos para subir a Drive")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de automatización YouTube")
    parser.add_argument("--solo-audio", action="store_true")
    parser.add_argument("--regenerar", type=str, metavar="VIDEO_ID")
    parser.add_argument("--desde-fecha", type=str)
    args = parser.parse_args()

    fecha = args.desde_fecha or datetime.now().strftime("%Y-%m-%d")

    if args.regenerar:
        regenerar_video(fecha, args.regenerar)
        sys.exit(0)

    sys.exit(correr_pipeline(fecha, solo_audio=args.solo_audio))

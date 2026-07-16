"""
Módulo 1 (nuevo) — Carga y validación de guiones.

Los guiones ya NO se generan llamando a la API de Anthropic. Los escribe
Claude Code directamente (cubierto por la suscripción Max) siguiendo las
instrucciones de ROUTINE_CLAUDE_CODE.md, y los guarda como archivos JSON en:

    work/[fecha]/[video_id].json

Este módulo solo los carga, valida el formato y el largo mínimo, y los
pasa al resto del pipeline. Si falta algo o un guion está corto, corta
con un mensaje claro para que Claude Code lo corrija.
"""

import os
import sys
import json
import glob
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "config"))
from config import CHANNELS, GUION_MIN_PALABRAS, TOTAL_VIDEOS_DIA, WORK_DIR, LOG_DIR

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "01_guiones.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

CAMPOS_REQUERIDOS = ["video_id", "canal_key", "titulo", "guion_en", "guion_es", "hook_short_en", "fecha"]


def cargar_guiones_del_dia(fecha: str) -> list[dict]:
    """
    Carga todos los JSON de guiones de work/[fecha]/ y valida:
    - que estén los campos requeridos
    - que el canal exista en la config
    - que el guion EN cumpla el mínimo de palabras (garantía de +10 min)
    """
    carpeta = os.path.join(WORK_DIR, fecha)
    archivos = sorted(glob.glob(os.path.join(carpeta, "*.json")))
    archivos = [a for a in archivos if not os.path.basename(a).startswith("_")]

    if not archivos:
        raise RuntimeError(
            f"No hay guiones en {carpeta}. Claude Code debe generarlos primero "
            f"siguiendo ROUTINE_CLAUDE_CODE.md (se esperan {TOTAL_VIDEOS_DIA} archivos JSON)."
        )

    items = []
    errores = []

    for path in archivos:
        try:
            with open(path, encoding="utf-8") as f:
                item = json.load(f)
        except json.JSONDecodeError as e:
            errores.append(f"{os.path.basename(path)}: JSON inválido ({e})")
            continue

        faltantes = [c for c in CAMPOS_REQUERIDOS if c not in item or not item[c]]
        if faltantes:
            errores.append(f"{os.path.basename(path)}: faltan campos {faltantes}")
            continue

        if item["canal_key"] not in CHANNELS:
            errores.append(
                f"{os.path.basename(path)}: canal_key '{item['canal_key']}' no existe. "
                f"Válidos: {list(CHANNELS.keys())}"
            )
            continue

        palabras = len(item["guion_en"].split())
        if palabras < GUION_MIN_PALABRAS:
            errores.append(
                f"{os.path.basename(path)}: guion EN corto ({palabras} palabras, "
                f"mínimo {GUION_MIN_PALABRAS}). Claude Code debe EXTENDERLO "
                f"(profundizar la historia, no rellenar) y guardar el JSON de nuevo."
            )
            continue

        items.append(item)
        logger.info(f"Guion válido: {item['video_id']} ({palabras} palabras EN)")

    if errores:
        mensaje = "GUIONES CON PROBLEMAS:\n" + "\n".join(f"  - {e}" for e in errores)
        logger.error(mensaje)
        raise RuntimeError(mensaje)

    if len(items) < TOTAL_VIDEOS_DIA:
        logger.warning(f"Se esperaban {TOTAL_VIDEOS_DIA} guiones, hay {len(items)}. Se procesa lo que hay.")

    return items

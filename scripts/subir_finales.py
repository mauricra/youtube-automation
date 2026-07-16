#!/usr/bin/env python3
"""
Sube los videos finales del día a Drive (vía service account, sin límite
de tamaño), organizados en Videos/[canal]/ y renombrados con el título.

USO:
  python scripts/subir_finales.py                     # sube lo de hoy
  python scripts/subir_finales.py --fecha 2026-07-15
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CHANNELS, WORK_DIR
import drive_sa

CARPETA_RAIZ = "Videos"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _nombre_seguro(titulo: str) -> str:
    seguro = "".join(c for c in titulo if c.isalnum() or c in " -_").strip()
    return seguro[:80] if seguro else "video"


def main(fecha: str):
    estado_path = os.path.join(WORK_DIR, fecha, "_estado_pipeline.json")
    if not os.path.exists(estado_path):
        logger.error(f"No existe {estado_path}. ¿Corriste main.py primero?")
        sys.exit(1)

    with open(estado_path, encoding="utf-8") as f:
        items = json.load(f)

    raiz_id = drive_sa.buscar_carpeta(CARPETA_RAIZ, crear=True)
    subidos, fallidos = [], []

    for item in items:
        video_path = item.get("video_final_path", "")
        if not video_path or not os.path.exists(video_path):
            continue  # incompleto: no se sube

        try:
            canal_cfg = CHANNELS[item["canal_key"]]
            canal_id = drive_sa.buscar_carpeta(
                canal_cfg["nombre_carpeta_drive"], parent_id=raiz_id, crear=True
            )
            nombre = _nombre_seguro(item["titulo"])

            drive_sa.subir(video_path, f"{nombre}_EN.mp4", canal_id)
            drive_sa.subir(item["audio_es_final_path"], f"{nombre}_AUDIO_ES.mp3", canal_id)
            drive_sa.subir(item["short_final_path"], f"{nombre}_SHORT.mp4", canal_id)

            subidos.append(item["titulo"])
            logger.info(f"✓ Subido completo: {item['titulo'][:60]}")
        except Exception as e:
            fallidos.append((item["video_id"], str(e)))
            logger.error(f"✗ Fallo subiendo {item['video_id']}: {e}")

    logger.info(f"Subida terminada: {len(subidos)} videos OK, {len(fallidos)} fallidos.")
    if fallidos:
        for vid, err in fallidos:
            logger.error(f"  {vid}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fecha", type=str, default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    main(args.fecha)

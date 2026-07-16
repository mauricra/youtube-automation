#!/usr/bin/env python3
"""
Descarga clips de gameplay desde Drive (vía service account, sin límite
de tamaño) a /tmp/fuente_gameplays/ para la corrida del día.

USO:
  python scripts/descargar_gameplays.py            # 15 clips random por canal
  python scripts/descargar_gameplays.py --cantidad 10
"""

import os
import sys
import random
import logging
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CHANNELS, GAMEPLAYS_DIR
import drive_sa

CARPETA_BANCO = "fuente_gameplays"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main(cantidad: int):
    banco_id = drive_sa.buscar_carpeta(CARPETA_BANCO)
    total_ok = 0

    for canal_key, cfg in CHANNELS.items():
        sub = cfg["gameplay_subcarpeta"]
        sub_id = drive_sa.buscar_carpeta(sub, parent_id=banco_id)
        clips = drive_sa.listar_videos(sub_id)

        if not clips:
            logger.error(f"{sub}: carpeta vacía en Drive. Frenando.")
            sys.exit(1)

        elegidos = random.sample(clips, min(cantidad, len(clips)))
        if len(clips) < cantidad:
            logger.warning(f"{sub}: solo hay {len(clips)} clips (se pidieron {cantidad}), se bajan todos.")

        destino_dir = os.path.join(GAMEPLAYS_DIR, sub)
        for clip in elegidos:
            destino = os.path.join(destino_dir, clip["name"])
            drive_sa.descargar(clip["id"], destino)
            total_ok += 1

        logger.info(f"{sub}: {len(elegidos)} clips descargados a {destino_dir}")

    logger.info(f"Descarga completa: {total_ok} clips en total.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cantidad", type=int, default=15)
    args = parser.parse_args()
    main(args.cantidad)

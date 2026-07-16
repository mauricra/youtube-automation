"""
Configuración central del pipeline.
Los guiones los escribe Claude Code. Drive lo maneja Claude Code vía conector.
El script Python solo hace: audio (ElevenLabs), edición (ffmpeg), y deja
los archivos finales en OUTPUTS_DIR para que Claude Code los suba a Drive.
"""

import os

# ============================================================
# API KEYS
# ============================================================
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "TU_API_KEY_ACA")

# Credenciales del service account de Google Drive (para descargas/subidas
# de archivos grandes, que el conector nativo no soporta). El setup script
# del entorno decodifica el secret GDRIVE_SA_B64 a este archivo.
GOOGLE_DRIVE_CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_DRIVE_CREDENTIALS_PATH", "/workspace/sa.json"
)

# ============================================================
# CANALES
# ============================================================
CHANNELS = {
    "confesiones_reddit": {
        "nombre_carpeta_drive": "Confesiones Reddit",
        "gameplay_subcarpeta": "GTA",
        "videos_por_dia": 1,
        "tono": "conversacional, primera persona, tipo confesión anónima",
        "fuente_temas": "confesiones estilo r/AmItheAsshole, r/confession, r/tifu, dilemas morales, secretos familiares, traiciones, giros inesperados",
    },
    "misterios_sin_resolver": {
        "nombre_carpeta_drive": "Misterios Sin Resolver",
        "gameplay_subcarpeta": "Minecraft",
        "videos_por_dia": 1,
        "tono": "narrador investigativo, tono serio y misterioso, construye tensión",
        "fuente_temas": "casos sin resolver, desapariciones, sucesos inexplicables (sin nombres reales)",
    },
    "historias_increibles": {
        "nombre_carpeta_drive": "Historias Increibles",
        "gameplay_subcarpeta": "Subway Surfers",
        "videos_por_dia": 1,
        "tono": "inspirador, dramático, contra todo pronóstico, ritmo ascendente",
        "fuente_temas": "supervivencia, superación, hazañas contra todo pronóstico, resiliencia",
    },
}

TOTAL_VIDEOS_DIA = sum(c["videos_por_dia"] for c in CHANNELS.values())  # 3

# ============================================================
# GUION — mínimos para garantizar +10 min
# ============================================================
GUION_MIN_PALABRAS = 1700
GUION_MAX_PALABRAS = 2300
DURACION_MINIMA_AUDIO_SEGUNDOS = 610

# ============================================================
# ELEVENLABS
# ============================================================
ELEVENLABS_VOICE_ID_EN = "ZSNL4hPqCnqoMPaI4jGX"
ELEVENLABS_VOICE_ID_ES = "spPXlKT5a4JMfbhPRAzA"
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
ELEVENLABS_VOICE_SETTINGS = {
    "stability": 0.55,
    "similarity_boost": 0.75,
    "style": 0.35,
    "use_speaker_boost": True,
}

# ============================================================
# VIDEO
# ============================================================
VIDEO_RESOLUTION = (1920, 1080)
VIDEO_FPS = 30
SHORT_DURACION_SEGUNDOS = 58

# ============================================================
# SUBTÍTULOS ESTILO TIKTOK
# (Los tamaños son en escala ASS de 288pt de alto, NO píxeles:
#  16 ≈ 6% de la altura de pantalla. Nunca usar valores tipo 60+.)
# ============================================================
SUBTITULOS_FUENTE = "Montserrat-Bold"
SUBTITULOS_TAMANO = 16              # video largo: discreto, abajo
SUBTITULOS_TAMANO_SHORT = 20        # short vertical: un poco más grande
SUBTITULOS_COLOR = "&HFFFFFF&"      # blanco
SUBTITULOS_BORDE_COLOR = "&H000000&"  # borde negro fino
SUBTITULOS_PALABRAS_POR_GRUPO = 5   # líneas más largas en el video largo
SUBTITULOS_PALABRAS_POR_GRUPO_SHORT = 3  # pantalla angosta, menos palabras

# ============================================================
# RUTAS LOCALES (dentro del contenedor)
# ============================================================
# Claude Code descarga los gameplays acá antes de correr el script
GAMEPLAYS_DIR = "/tmp/fuente_gameplays"
# ...esperando esta estructura:
#   /tmp/fuente_gameplays/GTA/*.mp4
#   /tmp/fuente_gameplays/Minecraft/*.mp4
#   /tmp/fuente_gameplays/Subway Surfers/*.mp4

WORK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")

# Los archivos finales que Claude Code tiene que subir a Drive:
# work/[fecha]/[video_id]/[video_id]_FINAL.mp4       -> Videos/[canal]/
# work/[fecha]/[video_id]/[video_id]_AUDIO_ES.mp3    -> Videos/[canal]/
# work/[fecha]/[video_id]/[video_id]_SHORT.mp4       -> Videos/[canal]/

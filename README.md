# YouTube Automation Pipeline — 3 videos/día

Genera automáticamente 3 videos por día (1 por canal):
guion +10 min (Claude API) → audio EN + ES (ElevenLabs) → video con gameplay propio + subtítulos TikTok (ffmpeg) → subida organizada a Drive.

Por cada video recibís en Drive:
- `[titulo]_EN.mp4` → video 10-15 min, audio inglés, subtítulos estilo TikTok
- `[titulo]_AUDIO_ES.mp3` → pista en español para agregar al subir a YouTube
- `[titulo]_SHORT.mp4` → short vertical (hasta 58s) con el momento más enganchador

---

## CHECKLIST DE SETUP (lo que tenés que hacer, en orden)

### ☐ 1. Guiones: los genera Claude Code con tu Max (sin costo extra)
Ya NO se necesita API key de Anthropic. Los guiones los escribe Claude Code
directamente como parte de la Routine diaria, siguiendo las instrucciones de
**ROUTINE_CLAUDE_CODE.md** (ese archivo es el texto que pegás como instrucción
de la Routine). Claude Code los guarda como JSON en work/[fecha]/ y después
corre el pipeline.

### ☐ 2. ElevenLabs
1. Cuenta en https://elevenlabs.io
2. Plan: **Creator ($22/mes) para testear** → **Scale cuando esté en producción**
   (3 videos/día × 2 idiomas ≈ 1.7M caracteres/mes; Creator no alcanza para
   producción completa, pero sí para probar todo el pipeline unos días)
3. Profile → API Keys → generar key
4. Voice Library → elegir una voz EN y una ES (narrativas, estables)
5. Copiar los dos Voice IDs en `config/config.py`:
   - `ELEVENLABS_VOICE_ID_EN`
   - `ELEVENLABS_VOICE_ID_ES`

### ☐ 3. Google Drive (service account)
1. https://console.cloud.google.com → crear proyecto
2. Habilitar "Google Drive API"
3. IAM & Admin → Service Accounts → crear → descargar JSON de credenciales
4. Guardar el JSON y apuntar `GOOGLE_DRIVE_CREDENTIALS_PATH` a esa ruta
5. **IMPORTANTE**: en Drive, compartir con el `client_email` del JSON
   (rol Editor) TANTO:
   - la carpeta `fuente_gameplays`
   - la ubicación donde va a crearse la carpeta `Videos`

### ☐ 4. Banco de gameplay en Drive
Verificar que exista esta estructura (los nombres importan):
```
fuente_gameplays/
    GTA/              ← clips .mp4 de tu gameplay (canal Confesiones Reddit)
    Minecraft/        ← (canal Misterios Sin Resolver)
    Subway Surfers/   ← (canal Historias Increibles)
```
Con 1-2 clips largos (30+ min) por carpeta alcanza para arrancar:
el script recorta un segmento aleatorio distinto cada vez.

### ☐ 5. Máquina donde corre
- Python 3.10+
- `pip install -r requirements.txt`
- ffmpeg instalado (`sudo apt install ffmpeg` / `brew install ffmpeg`)
- Variables de entorno:
```bash
export ELEVENLABS_API_KEY="..."
export GOOGLE_DRIVE_CREDENTIALS_PATH="/ruta/a/drive_credentials.json"
```
- Espacio en disco: ~10-15 GB libres (los clips de gameplay se descargan
  temporalmente y se borran después de cada video)

### ☐ 6. Claude Code Routine (automatización diaria a las 8:00)
Crear una Routine en Claude Code y pegar como instrucción el contenido
completo de **ROUTINE_CLAUDE_CODE.md** (Claude Code genera los guiones,
corre `python main.py`, y corrige automáticamente si algo sale corto).
Schedule: Daily 08:00

---

## USO

```bash
python main.py                       # pipeline completo (requiere JSONs en work/[fecha]/)
python main.py --solo-audio          # corta después del audio (test)
python main.py --regenerar VIDEO_ID  # limpia un video puntual para reprocesarlo
python main.py --desde-fecha 2026-07-13
```

**Orden recomendado la primera vez:**
1. Pedile a Claude Code que genere los 3 JSON de guiones (paso 1 de ROUTINE_CLAUDE_CODE.md) → revisalos en `work/[fecha]/`
2. `python main.py --solo-audio` → escuchá un audio, verificá voz y ritmo
3. `python main.py` completo → revisá el primer video antes de subirlo

---

## GARANTÍA DE +10 MINUTOS

El requisito de duración se verifica en dos capas:
1. Los guiones se validan con piso de 1,700 palabras antes de gastar
   créditos de ElevenLabs; si uno está corto, el pipeline corta con un
   mensaje claro para que Claude Code lo extienda.
2. Después de generar el audio EN, se mide la duración real; si quedó
   bajo 10:10 min, el pipeline lo reporta (salida 3) y Claude Code
   extiende el guion y regenera solo ese video con --regenerar.

---

## PROBLEMAS COMUNES

| Error | Solución |
|-------|----------|
| `ElevenLabs API error: 401` | API key incorrecta o plan sin acceso API |
| `Carpeta 'fuente_gameplays' no encontrada` | Compartir la carpeta con el client_email del service account |
| `No se encontraron clips en fuente_gameplays/GTA` | Subir al menos un .mp4 a esa subcarpeta |
| `ffmpeg: command not found` | Instalar ffmpeg en el sistema |
| Corrida se cortó a mitad | `python main.py --retomar` (no repite lo ya hecho) |

# AI Video Factory

Pipeline automático para generar videos faceless:

1. Genera guion (`GPT`/`Ollama`/fallback local)
2. Genera voz (`Edge-TTS`/`ElevenLabs`/local)
3. Descarga clips de Pexels
4. Crea subtítulos con Whisper
5. Renderiza video final con FFmpeg (CFR 30fps)

## Requisitos

- Python 3.9+
- FFmpeg y FFprobe en `PATH`

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Variables `.env`

```env
PEXELS_API_KEY=...

# Script generation
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

# ElevenLabs (opcional)
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_MODEL=eleven_multilingual_v2
```

## Uso recomendado

```bash
python generate_video.py "AI wedding templates on Etsy" --minutes 8 --clips 20 --script-provider auto --tts-provider gtts --voice en
```

## Edición manual de clips (web)

Si quieres revisar y limpiar clips incongruentes antes del render final:

```bash
python generate_video.py "AI wedding templates on Etsy" --minutes 8 --clips 20 --edit-ui
```

Esto genera `work/timeline.json` y abre un editor web local donde puedes:

- eliminar clips,
- desactivar/activar segmentos,
- ajustar `start` y `duration`,
- añadir clips de la librería descargada,
- renderizar el `output/final.mp4` con tu selección.

## Proveedores

- `--script-provider auto|gpt|ollama`
	- `auto`: usa GPT si hay `OPENAI_API_KEY`; si falla, Ollama; si falla, fallback local.
- `--tts-provider gtts|edge|elevenlabs|local`
	- `gtts`: calidad buena y estable (recomendado por defecto).
	- `edge`: calidad alta, puede fallar según región/bloqueo de servicio.
	- `elevenlabs`: requiere cuota y API key.
	- `local`: fallback offline con voces del sistema.

## UI / despliegue (único)

La app web se sirve directamente desde Flask usando [web/editor.html](web/editor.html) vía [`create_app`](src/editor_web.py).  
No se usa build de Vite para producción local.

Inicio recomendado:

```bash
python generate_video.py "tu temática" --minutes 8
```

Esto abre el editor local y todo el flujo se hace desde ahí.

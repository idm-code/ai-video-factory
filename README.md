# AI Video Factory

Editor y pipeline para montar vídeos con clips stock, voz generada, subtítulos y render final con FFmpeg.

## Estado actual

- La UI activa es **React**.
- Flask sirve la build de React en `/`.
- La generación de audio usa únicamente [`tts_to_mp3_gtts`](src/tts_gtts.py).
- El parámetro `--voice` se usa como pista de idioma para gTTS, por ejemplo: `en`, `es`, `fr`.
- El modo por defecto abre la UI web.
- El modo `--batch` ejecuta el pipeline automático completo desde CLI.

## Requisitos

- Python 3.9+
- Node.js 18+
- FFmpeg y FFprobe en `PATH`

## Instalación

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Frontend React

```bash
npm --prefix web install
npm --prefix web run build
```

## Variables `.env`

```env
PEXELS_API_KEY=
PIXABAY_API_KEY=

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

## Audio

La generación de audio usa únicamente [`tts_to_mp3_gtts`](src/tts_gtts.py).
El parámetro `--voice` funciona como pista de idioma para gTTS, por ejemplo: `en`, `es`, `fr`.

## Uso recomendado

Arranca la UI React local:

```bash
python generate_video.py "tu temática" --minutes 8
```

Esto:

1. prepara o recupera `work/timeline.json`,
2. abre la app web en `http://127.0.0.1:8765/`,
3. permite buscar clips, añadirlos al timeline, generar audio, generar subtítulos y renderizar.

## Flujo en la UI

1. Buscar clips/imágenes.
2. Añadir clips al timeline.
3. Editar `start` y `duration`.
4. Pulsar **Generar audio**.
5. Pulsar **Generar subs**.
6. Pulsar **Render video**.

## Modo batch

Para ejecutar el pipeline automático completo sin abrir la UI:

```bash
python generate_video.py "tu temática" --minutes 8 --batch
```

## Estructura relevante

- [`generate_video.py`](generate_video.py): entrada CLI
- [`src/editor_web.py`](src/editor_web.py): servidor Flask + API
- [`src/video_edit.py`](src/video_edit.py): render final con FFmpeg
- [`src/timeline.py`](src/timeline.py): carga y persistencia del timeline
- [`web/src/App.jsx`](web/src/App.jsx): app React principal
- [`web/src/api.js`](web/src/api.js): cliente HTTP del frontend

## Notas

- Si la UI devuelve `React build not found`, ejecutar:

```bash
npm --prefix web install
npm --prefix web run build
```

- Los clips del timeline son la fuente de verdad visual para el render.
- Si cambias clips o duraciones, regenera audio/subtítulos antes de renderizar.

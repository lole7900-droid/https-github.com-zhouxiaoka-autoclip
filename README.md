# AutoClip Shorts Studio

AutoClip is a **local-first** Shorts workflow: upload an MP4, create a transcript
with Faster-Whisper on your computer, let Ollama select highlights locally, then
render a vertical captioned MP4 with local FFmpeg.

## Architecture

The repository originally contained no AutoClip backend, AI pipeline, FFmpeg
integration, subtitle implementation, or API. `server.py` is therefore the
smallest backend required to make the React/Vite UI operational; it does not
replace an existing backend. It does not use OpenAI or any paid cloud API.

- **React/Vite (`src/main.jsx`)**: upload, job configuration, polling progress,
  suggestions, export and visible API errors.
- **Local API (`server.py`)**: persists uploads, runs background jobs, invokes
  Faster-Whisper and Ollama on `localhost`, then runs FFmpeg to render 1080×1920
  video with ASS captions.
- **Local models**: Faster-Whisper downloads the selected Whisper model on first
  use; Ollama serves a model already pulled onto the same computer. No API key is
  required and the video never leaves the computer.

## Run locally

### Windows setup

1. Install **Python 3.10–3.12**, **Node.js 20+**, [FFmpeg](https://ffmpeg.org/),
   and [Ollama for Windows](https://ollama.com/download). Ensure `ffmpeg` and
   `ffprobe` are available in a new PowerShell window (`ffmpeg -version`).
2. In PowerShell at the project directory, create and activate a virtual env:
   `py -3.12 -m venv .venv` then `.\.venv\Scripts\Activate.ps1`.
3. Install the local transcription runtime: `py -m pip install -r requirements.txt`.
4. Pull a local LLM once: `ollama pull llama3.2`. Start the service with
   `ollama serve` if it is not already running.
5. Install the browser UI dependencies: `npm install`.
6. Start the local API in one terminal: `py server.py`.
7. Start the web UI in a second terminal: `npm run dev`, then open the URL Vite
   prints (normally `http://localhost:5173`).

Choose a video MP4, upload it, select the local Whisper/Ollama models, and click
**Phân tích local**. Once the suggestions appear, choose **Tạo Short**; the MP4
is written to `data/outputs/` and can be downloaded in the browser.

The health API (`GET /api/health`) reports Faster-Whisper, Ollama, FFmpeg and
FFprobe availability. If any local dependency, upload, transcription, Ollama or
FFmpeg action fails, the job enters `error` with a user-visible message instead
of falsely reporting completion.

## API lifecycle

1. `POST /api/uploads` (`multipart/form-data`, field `video`)
2. `POST /api/jobs` with `video_id` and language/provider/model/9:16/length/count
3. `GET /api/jobs/:id` until `ready`; inspect `highlights`
4. `POST /api/jobs/:id/export` with `highlight_id`
5. `GET /api/jobs/:id` until `complete`; download `output`

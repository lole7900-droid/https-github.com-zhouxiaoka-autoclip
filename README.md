# AutoClip Shorts Studio

AutoClip is now a Shorts workflow: upload a source video, configure transcription,
review AI-selected highlights, then render a vertical, captioned MP4.

## Architecture

The repository originally contained no AutoClip backend, AI pipeline, FFmpeg
integration, subtitle implementation, or API. `server.py` is therefore the
smallest backend required to make the React/Vite UI operational; it does not
replace an existing backend.

- **React/Vite (`src/main.jsx`)**: upload, job configuration, polling progress,
  suggestions, export and visible API errors.
- **Local API (`server.py`)**: persists uploads, runs background jobs, calls the
  selected transcription provider, builds highlight suggestions, and invokes
  FFmpeg to render 1080×1920 video with ASS captions.
- **OpenAI transcription**: uses `OPENAI_API_KEY` only on the server. The key is
  never sent to or stored by the browser.

## Run locally

1. Install Node dependencies and start the Vite UI: `npm install && npm run dev`.
2. In another terminal, set `OPENAI_API_KEY` and start the API:
   `OPENAI_API_KEY=... python3 server.py`.
3. Configure Vite's development proxy for `/api` to `http://127.0.0.1:8000`, or
   serve the compiled Vite `dist/` directory through the backend/reverse proxy.

For actual export, install `ffmpeg` and `ffprobe` on the API host. The health API
(`GET /api/health`) reports whether those binaries are available. If a provider,
API key, upload, transcription or FFmpeg action fails, the job enters `error`
with a user-visible message instead of falsely reporting completion.

## API lifecycle

1. `POST /api/uploads` (`multipart/form-data`, field `video`)
2. `POST /api/jobs` with `video_id` and language/provider/model/9:16/length/count
3. `GET /api/jobs/:id` until `ready`; inspect `highlights`
4. `POST /api/jobs/:id/export` with `highlight_id`
5. `GET /api/jobs/:id` until `complete`; download `output`

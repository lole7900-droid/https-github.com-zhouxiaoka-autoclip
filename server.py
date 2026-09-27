#!/usr/bin/env python3
"""AutoClip's dependency-free local API server.

It serves the Vite frontend and exposes durable upload/job/export endpoints.  The
actual media work is delegated to installed ffmpeg and an opted-in transcription
provider; missing tooling is reported as a job error rather than hidden.
"""
from __future__ import annotations

import json, mimetypes, os, re, shutil, subprocess, threading, time, uuid
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent.resolve()
DATA = ROOT / "data"
UPLOADS, OUTPUTS = DATA / "uploads", DATA / "outputs"
for directory in (UPLOADS, OUTPUTS): directory.mkdir(parents=True, exist_ok=True)
JOBS: dict[str, dict] = {}
UPLOADS_INDEX: dict[str, dict] = {}
LOCK = threading.Lock()

STEPS = ["queued", "transcribing", "analysing", "ready", "rendering", "complete"]

def command_available(name: str) -> bool:
    return shutil.which(name) is not None

def save_state():
    (DATA / "jobs.json").write_text(json.dumps(JOBS, ensure_ascii=False, indent=2), encoding="utf-8")

def duration(path: Path) -> float | None:
    if not command_available("ffprobe"): return None
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try: return float(result.stdout.strip())
    except ValueError: return None

def update(job: dict, status: str, progress: int, **extra):
    with LOCK:
        job.update(status=status, progress=progress, updated_at=time.time(), **extra)
        save_state()

def transcribe_openai(video: Path, language: str, model: str) -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key: raise RuntimeError("OPENAI_API_KEY chưa được cấu hình. Thêm khóa vào môi trường server để dùng OpenAI transcription.")
    boundary = f"----AutoClip{uuid.uuid4().hex}"
    fields = [("model", model), ("language", language), ("response_format", "verbose_json")]
    chunks = []
    for name, value in fields:
        chunks.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])
    mime = mimetypes.guess_type(video.name)[0] or "application/octet-stream"
    chunks.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="file"; filename="{video.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode(), video.read_bytes(), b"\r\n", f"--{boundary}--\r\n".encode()])
    request = Request("https://api.openai.com/v1/audio/transcriptions", data=b"".join(chunks), headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urlopen(request, timeout=240) as response: payload = json.loads(response.read())
    except HTTPError as error: raise RuntimeError(f"OpenAI transcription thất bại ({error.code}): {error.read().decode(errors='replace')[:300]}")
    except URLError as error: raise RuntimeError(f"Không thể kết nối transcription provider: {error.reason}")
    return payload.get("text", "")

def suggestions(text: str, total: float, wanted: int, clip_length: int):
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if len(x.strip()) > 18] or [text.strip() or "Video đã được tải lên; không nhận được transcript."]
    count = min(max(wanted, 1), len(sentences))
    spacing = max((total or clip_length * count) / count, clip_length)
    result = []
    for index, sentence in enumerate(sentences[:count]):
        start = round(index * spacing, 2); end = round(min(start + clip_length, total or start + clip_length), 2)
        title = " ".join(sentence.split()[:8]).rstrip(".,:;!? ")
        result.append({"id": index, "start": start, "end": end, "content": sentence, "score": max(72, 94 - index * 5), "title": title or f"Highlight {index + 1}"})
    return result

def ass_subtitles(text: str, output: Path):
    safe = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")
    output.write_text("[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Arial,20,&H00FFFFFF,&H00101010,&H80000000,1,0,2,36,36,90,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\nDialogue: 0,0:00:00.00,9:59:59.00,Default,,0,0,0,," + safe, encoding="utf-8")

def process(job: dict):
    try:
        video = Path(job["video_path"]); config = job["config"]
        update(job, "transcribing", 18)
        if config["provider"] == "openai": transcript = transcribe_openai(video, config["language"], config["model"])
        else: raise RuntimeError(f"Provider '{config['provider']}' chưa được cấu hình. Chọn OpenAI hoặc thêm adapter provider ở server.py.")
        update(job, "analysing", 58, transcript=transcript)
        highlights = suggestions(transcript, job.get("duration") or 0, config["count"], config["length"])
        update(job, "ready", 100, highlights=highlights)
    except Exception as error:
        update(job, "error", 100, error=str(error))

def render(job: dict, highlight_id: int):
    try:
        if not command_available("ffmpeg"): raise RuntimeError("FFmpeg không được cài trên server. Cài ffmpeg và thử lại để xuất video 9:16.")
        highlight = next((item for item in job.get("highlights", []) if item["id"] == highlight_id), None)
        if not highlight: raise RuntimeError("Không tìm thấy đoạn highlight được chọn.")
        update(job, "rendering", 76)
        output = OUTPUTS / f"{job['id']}-{highlight_id}.mp4"; ass = OUTPUTS / f"{job['id']}-{highlight_id}.ass"; ass_subtitles(highlight["content"], ass)
        vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles={ass.as_posix()}"
        command = ["ffmpeg", "-y", "-ss", str(highlight["start"]), "-to", str(highlight["end"]), "-i", job["video_path"], "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode: raise RuntimeError(f"FFmpeg không thể xuất video: {result.stderr[-500:]}")
        update(job, "complete", 100, output=f"/api/outputs/{output.name}")
    except Exception as error: update(job, "error", 100, error=str(error))

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self): self.send_header("Cache-Control", "no-store"); super().end_headers()
    def respond(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/api/health": return self.respond({"ok": True, "ffmpeg": command_available("ffmpeg"), "ffprobe": command_available("ffprobe"), "providers": ["openai"]})
        if self.path == "/api/options": return self.respond({"languages": ["vi", "en", "ja", "ko"], "providers": [{"id": "openai", "models": ["gpt-4o-mini-transcribe", "whisper-1"]}], "aspect_ratios": ["9:16"]})
        if self.path.startswith("/api/jobs/"):
            job = JOBS.get(self.path.rsplit("/", 1)[-1]); return self.respond(job or {"error": "Không tìm thấy job"}, 200 if job else 404)
        if self.path.startswith("/api/outputs/"):
            file = OUTPUTS / Path(self.path).name
            if file.is_file(): self.path = str(file.relative_to(ROOT)); return super().do_GET()
            return self.respond({"error": "Không tìm thấy file xuất"}, 404)
        return super().do_GET()
    def do_POST(self):
        if self.path == "/api/uploads":
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type: return self.respond({"error": "Cần gửi multipart/form-data."}, 400)
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            message = BytesParser(policy=default).parsebytes(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw)
            part = next((item for item in message.iter_attachments() if item.get_param("name", header="content-disposition") == "video"), None)
            if not part or not part.get_filename(): return self.respond({"error": "Không có trường video trong yêu cầu upload."}, 400)
            name = Path(part.get_filename()).name; ext = Path(name).suffix.lower()
            if ext not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}: return self.respond({"error": "Định dạng video không được hỗ trợ. Dùng MP4, MOV, MKV hoặc WebM."}, 400)
            ident = uuid.uuid4().hex; target = UPLOADS / f"{ident}{ext}"; target.write_bytes(part.get_payload(decode=True)); meta = {"id": ident, "name": name, "path": str(target), "size": target.stat().st_size, "duration": duration(target)}; UPLOADS_INDEX[ident] = meta; return self.respond(meta, 201)
        if self.path == "/api/jobs":
            try: payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except json.JSONDecodeError: return self.respond({"error": "JSON cấu hình không hợp lệ."}, 400)
            upload = UPLOADS_INDEX.get(payload.get("video_id"));
            if not upload: return self.respond({"error": "Video upload không tồn tại hoặc phiên làm việc đã hết."}, 404)
            config = payload.get("config", {}); required = ["language", "provider", "model", "length", "count", "aspect_ratio"]
            if any(not config.get(key) for key in required) or config["aspect_ratio"] != "9:16": return self.respond({"error": "Cấu hình tạo Short chưa đầy đủ hoặc tỷ lệ không phải 9:16."}, 400)
            job = {"id": uuid.uuid4().hex, "status": "queued", "progress": 4, "video_path": upload["path"], "duration": upload["duration"], "config": config, "created_at": time.time()}; JOBS[job["id"]] = job; save_state(); threading.Thread(target=process, args=(job,), daemon=True).start(); return self.respond(job, 202)
        match = re.fullmatch(r"/api/jobs/([a-f0-9]+)/export", self.path)
        if match:
            job = JOBS.get(match.group(1));
            if not job: return self.respond({"error": "Không tìm thấy job."}, 404)
            try: payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except json.JSONDecodeError: return self.respond({"error": "JSON không hợp lệ."}, 400)
            threading.Thread(target=render, args=(job, payload.get("highlight_id")), daemon=True).start(); return self.respond(job, 202)
        return self.respond({"error": "API endpoint không tồn tại."}, 404)

if __name__ == "__main__":
    print("AutoClip API running at http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()

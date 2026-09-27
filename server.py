#!/usr/bin/env python3
"""Local-first AutoClip API: Faster-Whisper + Ollama + FFmpeg, no cloud keys."""
from __future__ import annotations

import json
import mimetypes
import re
import shutil
import subprocess
import threading
import time
import uuid
from email.parser import BytesParser
from email.policy import default
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent.resolve()
DATA, UPLOADS, OUTPUTS = ROOT / "data", ROOT / "data" / "uploads", ROOT / "data" / "outputs"
for directory in (DATA, UPLOADS, OUTPUTS): directory.mkdir(parents=True, exist_ok=True)
JOBS: dict[str, dict] = {}
UPLOADS_INDEX: dict[str, dict] = {}
LOCK = threading.Lock()
SUPPORTED_EXTENSIONS = {".mp4"}
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def ollama_available() -> bool:
    try:
        request = Request("http://127.0.0.1:11434/api/tags")
        with urlopen(request, timeout=2) as response:
            return response.status == 200
    except (URLError, TimeoutError):
        return False


def save_state() -> None:
    (DATA / "jobs.json").write_text(json.dumps(JOBS, ensure_ascii=False, indent=2), encoding="utf-8")


def update(job: dict, status: str, progress: int, **extra) -> None:
    with LOCK:
        job.update(status=status, progress=progress, updated_at=time.time(), **extra)
        save_state()


def video_duration(path: Path) -> float:
    if not command_available("ffprobe"):
        raise RuntimeError("Không tìm thấy FFprobe. Cài FFmpeg đầy đủ và thêm thư mục bin vào PATH.")
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"FFprobe không đọc được video: {result.stderr[-300:]}")
    return float(result.stdout.strip())


def transcribe_local(video: Path, language: str, model_name: str) -> tuple[str, list[dict]]:
    """Transcribe locally; import lazily so health and API errors work before setup."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError("Chưa cài Faster-Whisper. Chạy: py -m pip install -r requirements.txt") from error
    try:
        model = WhisperModel(model_name, device="auto", compute_type="int8")
        segments, _info = model.transcribe(str(video), language=language, vad_filter=True, word_timestamps=True)
        items = [{"start": round(segment.start, 2), "end": round(segment.end, 2), "text": segment.text.strip()} for segment in segments if segment.text.strip()]
    except Exception as error:
        raise RuntimeError(f"Faster-Whisper không thể tạo transcript: {error}") from error
    if not items:
        raise RuntimeError("Faster-Whisper không nhận được lời nói trong video.")
    return " ".join(item["text"] for item in items), items


def ollama_highlights(transcript: str, segments: list[dict], duration: float, count: int, length: int, model: str) -> list[dict]:
    prompt = f'''Bạn là biên tập viên video Shorts. Chỉ trả về JSON hợp lệ, không markdown.
Chọn tối đa {count} đoạn hấp dẫn từ transcript sau để tạo Shorts dài tối đa {length} giây.
Video dài {duration:.2f} giây. Mỗi phần tử có start, end, title, score (0-100), content.
start/end phải nằm trong 0..{duration:.2f}; end > start; không tự bịa nội dung.
Transcript có mốc: {json.dumps(segments, ensure_ascii=False)}
Đáp án là mảng JSON.'''
    request = Request(OLLAMA_URL, data=json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0.2}}).encode(), headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=180) as response:
            raw = json.loads(response.read().decode())["response"]
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Không kết nối được Ollama. Mở Ollama và chạy `ollama serve`.") from error
    except (KeyError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Ollama trả về phản hồi không hợp lệ: {error}") from error
    try:
        payload = json.loads(raw)
        candidates = payload["highlights"] if isinstance(payload, dict) else payload
    except (TypeError, json.JSONDecodeError, KeyError) as error:
        raise RuntimeError(f"Ollama không trả về danh sách highlight JSON hợp lệ: {raw[:200]}") from error
    highlights = []
    for candidate in candidates[:count]:
        try:
            start, end = float(candidate["start"]), float(candidate["end"])
            if not (0 <= start < end <= duration and end - start <= length + 2):
                continue
            highlights.append({"id": len(highlights), "start": round(start, 2), "end": round(end, 2), "title": str(candidate["title"])[:120], "content": str(candidate["content"])[:700], "score": min(100, max(0, int(candidate["score"])))})
        except (KeyError, TypeError, ValueError):
            continue
    if not highlights:
        raise RuntimeError("Ollama không đề xuất được đoạn hợp lệ. Thử model khác hoặc tăng thời lượng Short.")
    return highlights


def ass_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def write_ass(segments: list[dict], highlight: dict, destination: Path) -> None:
    header = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Caption,Arial,64,&H00FFFFFF,&H00111111,&H80000000,1,0,2,64,64,150,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"""
    lines = []
    for segment in segments:
        start, end = max(segment["start"], highlight["start"]), min(segment["end"], highlight["end"])
        if end <= start: continue
        relative_start, relative_end = start - highlight["start"], end - highlight["start"]
        to_ass_time = lambda value: f"{int(value // 3600)}:{int(value % 3600 // 60):02d}:{value % 60:05.2f}"
        lines.append(f"Dialogue: 0,{to_ass_time(relative_start)},{to_ass_time(relative_end)},Caption,,0,0,0,,{ass_escape(segment['text'])}")
    destination.write_text(header + "\n".join(lines), encoding="utf-8-sig")


def subtitle_filter(path: Path) -> str:
    # FFmpeg filters use ':' as a separator, including Windows drive letters.
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def process(job: dict) -> None:
    try:
        config = job["config"]
        update(job, "transcribing", 15)
        transcript, segments = transcribe_local(Path(job["video_path"]), config["language"], config["whisper_model"])
        update(job, "analysing", 55, transcript=transcript, transcript_segments=segments)
        highlights = ollama_highlights(transcript, segments, job["duration"], config["count"], config["length"], config["ollama_model"])
        update(job, "ready", 100, highlights=highlights)
    except Exception as error:
        update(job, "error", 100, error=str(error))


def render(job: dict, highlight_id: int) -> None:
    try:
        if not command_available("ffmpeg"):
            raise RuntimeError("Không tìm thấy FFmpeg. Cài FFmpeg đầy đủ và thêm thư mục bin vào PATH.")
        highlight = next((item for item in job.get("highlights", []) if item["id"] == highlight_id), None)
        if not highlight: raise RuntimeError("Không tìm thấy highlight đã chọn.")
        update(job, "rendering", 72)
        output = OUTPUTS / f"{job['id']}-{highlight_id}.mp4"; subtitles = OUTPUTS / f"{job['id']}-{highlight_id}.ass"
        write_ass(job["transcript_segments"], highlight, subtitles)
        filters = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles='{subtitle_filter(subtitles)}'"
        command = ["ffmpeg", "-y", "-ss", str(highlight["start"]), "-t", str(highlight["end"] - highlight["start"]), "-i", job["video_path"], "-vf", filters, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode: raise RuntimeError(f"FFmpeg không thể xuất video: {result.stderr[-500:]}")
        update(job, "complete", 100, output=f"/api/outputs/{output.name}")
    except Exception as error:
        update(job, "error", 100, error=str(error))


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self): self.send_header("Cache-Control", "no-store"); super().end_headers()
    def respond(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/api/health": return self.respond({"ok": True, "local_only": True, "ffmpeg": command_available("ffmpeg"), "ffprobe": command_available("ffprobe"), "faster_whisper": faster_whisper_available(), "ollama": ollama_available()})
        if self.path == "/api/options": return self.respond({"languages": ["vi", "en", "ja", "ko"], "whisper_models": ["base", "small", "medium"], "ollama_models": ["llama3.2", "qwen2.5"], "aspect_ratios": ["9:16"]})
        if self.path.startswith("/api/jobs/"):
            job = JOBS.get(self.path.rsplit("/", 1)[-1]); return self.respond(job or {"error": "Không tìm thấy job."}, 200 if job else 404)
        if self.path.startswith("/api/outputs/"):
            file = OUTPUTS / Path(self.path).name
            if file.is_file(): self.path = str(file.relative_to(ROOT)); return super().do_GET()
            return self.respond({"error": "Không tìm thấy file xuất."}, 404)
        return super().do_GET()
    def do_POST(self):
        if self.path == "/api/uploads": return self.upload()
        if self.path == "/api/jobs": return self.create_job()
        match = re.fullmatch(r"/api/jobs/([a-f0-9]+)/export", self.path)
        if match: return self.create_export(match.group(1))
        return self.respond({"error": "API endpoint không tồn tại."}, 404)
    def upload(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type: return self.respond({"error": "Cần gửi multipart/form-data."}, 400)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))); message = BytesParser(policy=default).parsebytes(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw)
        part = next((item for item in message.iter_attachments() if item.get_param("name", header="content-disposition") == "video"), None)
        if not part or not part.get_filename(): return self.respond({"error": "Không có video trong yêu cầu upload."}, 400)
        name = Path(part.get_filename()).name
        if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS: return self.respond({"error": "Chỉ hỗ trợ video MP4."}, 400)
        ident = uuid.uuid4().hex; target = UPLOADS / f"{ident}.mp4"; target.write_bytes(part.get_payload(decode=True))
        try: length = video_duration(target)
        except RuntimeError as error: target.unlink(missing_ok=True); return self.respond({"error": str(error)}, 422)
        meta = {"id": ident, "name": name, "path": str(target), "size": target.stat().st_size, "duration": length}; UPLOADS_INDEX[ident] = meta; return self.respond(meta, 201)
    def create_job(self):
        try: payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except json.JSONDecodeError: return self.respond({"error": "JSON cấu hình không hợp lệ."}, 400)
        upload = UPLOADS_INDEX.get(payload.get("video_id")); config = payload.get("config", {})
        required = ["language", "whisper_model", "ollama_model", "length", "count", "aspect_ratio"]
        if not upload: return self.respond({"error": "Video upload không tồn tại."}, 404)
        if any(not config.get(key) for key in required) or config["aspect_ratio"] != "9:16": return self.respond({"error": "Cấu hình local pipeline chưa đầy đủ hoặc tỷ lệ không phải 9:16."}, 400)
        job = {"id": uuid.uuid4().hex, "status": "queued", "progress": 4, "video_path": upload["path"], "duration": upload["duration"], "config": config, "created_at": time.time()}; JOBS[job["id"]] = job; save_state(); threading.Thread(target=process, args=(job,), daemon=True).start(); return self.respond(job, 202)
    def create_export(self, job_id: str):
        job = JOBS.get(job_id)
        if not job: return self.respond({"error": "Không tìm thấy job."}, 404)
        try: highlight_id = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))["highlight_id"]
        except (json.JSONDecodeError, KeyError): return self.respond({"error": "highlight_id không hợp lệ."}, 400)
        threading.Thread(target=render, args=(job, highlight_id), daemon=True).start(); return self.respond(job, 202)


if __name__ == "__main__":
    print("AutoClip local API running at http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()

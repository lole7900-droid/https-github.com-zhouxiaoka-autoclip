import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class LocalPipelineTests(unittest.TestCase):
    def test_process_moves_local_transcript_to_ready_highlights(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "source.mp4"; video.write_bytes(b"video")
            job = {"id": "test-job", "video_path": str(video), "duration": 90.0, "config": {"language": "vi", "whisper_model": "small", "ollama_model": "llama3.2", "count": 1, "length": 45}}
            highlights = [{"id": 0, "start": 2.0, "end": 30.0, "title": "Điểm chính", "content": "Nội dung", "score": 91}]
            with patch("server.transcribe_local", return_value=("Nội dung", [{"start": 2.0, "end": 30.0, "text": "Nội dung"}])) as whisper, patch("server.ollama_highlights", return_value=highlights) as ollama:
                server.process(job)
            self.assertEqual(job["status"], "ready")
            self.assertEqual(job["highlights"], highlights)
            whisper.assert_called_once(); ollama.assert_called_once()

    def test_ass_subtitles_are_relative_to_selected_highlight(self):
        with tempfile.TemporaryDirectory() as folder:
            subtitle = Path(folder) / "caption.ass"
            server.write_ass([{"start": 8.0, "end": 13.0, "text": "Chào {AutoClip}"}], {"start": 10.0, "end": 20.0}, subtitle)
            content = subtitle.read_text(encoding="utf-8-sig")
            self.assertIn("0:00:00.00,0:00:03.00", content)
            self.assertIn("Chào \\{AutoClip\\}", content)

    def test_highlight_validation_discards_out_of_range_response(self):
        class Response:
            status = 200
            def read(self): return b'{"response":"[{\\\"start\\\": 1, \\\"end\\\": 12, \\\"title\\\": \\\"Hop le\\\", \\\"content\\\": \\\"Noi dung\\\", \\\"score\\\": 90}, {\\\"start\\\": -1, \\\"end\\\": 2, \\\"title\\\": \\\"Sai\\\", \\\"content\\\": \\\"Sai\\\", \\\"score\\\": 1}]"}'
            def __enter__(self): return self
            def __exit__(self, *args): return False
        with patch("server.urlopen", return_value=Response()):
            output = server.ollama_highlights("text", [{"start": 0, "end": 15, "text": "text"}], 20, 3, 15, "llama3.2")
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["title"], "Hop le")

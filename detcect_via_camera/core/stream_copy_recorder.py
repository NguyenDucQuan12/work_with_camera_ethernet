# -*- coding: utf-8 -*-
# core/stream_copy_recorder.py – Ghi nguyên bản RTSP (stream copy) bằng FFmpeg

import os, time, subprocess, sys, platform

class StreamCopyRecorder:
    """
    Ghi trực tiếp stream RTSP → file video bằng FFmpeg, không decode/encode:
      ffmpeg -rtsp_transport tcp -i "<url>" -c copy -an -movflags +faststart <file.mp4>

    - Ưu điểm: CPU gần như 0, không drop chất lượng, mượt.
    - Nhược: file chỉ phát được sau khi stop (moov viết lúc kết thúc). Nếu cần xem “đang ghi”,
             chuyển sang MKV hoặc segment HLS/DASH.

    Yêu cầu: hệ thống có `ffmpeg` trong PATH.
    """
    def __init__(self, out_dir="recordings"):
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)
        self.proc: subprocess.Popen|None = None
        self.path: str|None = None

    def is_recording(self) -> bool:
        return self.proc is not None and (self.proc.poll() is None)

    def start(self, url: str, basename: str = "capture_copy"):
        """Bắt đầu ghi stream copy vào MP4."""
        if self.is_recording():
            return self.path
        ts = time.strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(self.out_dir, f"{basename}-{ts}.mp4")
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",   # TCP ổn định
            "-i", url,                  # nguồn RTSP
            "-c", "copy",               # không encode lại
            "-an",                      # bỏ audio (nếu có)
            "-movflags", "+faststart",  # di chuyển 'moov' để mở nhanh sau khi dừng
            "-y",                       # ghi đè nếu trùng
            self.path
        ]
        # Ẩn console trên Windows
        creationflags = 0
        if platform.system().lower().startswith("win"):
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
        except FileNotFoundError:
            raise RuntimeError("Không tìm thấy 'ffmpeg'. Hãy cài FFmpeg và thêm vào PATH.")
        return self.path

    def stop(self):
        """Dừng ghi."""
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        self.path = None

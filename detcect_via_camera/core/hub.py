# -*- coding: utf-8 -*-
# core/hub.py – Đệm khung mới nhất, không gây backlog

import threading

class LatestFrameHub:
    """
    Lưu đúng 1 khung mới nhất (và metadata), thread-safe.
    Dữ liệu: tuple (av_frame, clock_offset, transport, fps_in)
    - av_frame: av.VideoFrame (giữ timecode)
    - clock_offset: (mono_now - wall_now) để nội suy latency
    - transport: "tcp"
    - fps_in: float (FPS camera đo ở reader)
    """
    def __init__(self):
        self._lock = threading.Lock()          # Khóa bảo vệ đọc/ghi
        self._item = None                      # Item hiện tại (hoặc None)

    def set(self, item):
        """Ghi đè khung mới nhất."""
        with self._lock:
            self._item = item

    def get(self):
        """Đọc khung mới nhất (có thể trả None)."""
        with self._lock:
            return self._item

    def clear(self):
        """Xoá khung (khi disconnect)."""
        with self._lock:
            self._item = None

# -*- coding: utf-8 -*-
# core/reader.py – RTSP Reader (TCP-only) + auto-reconnect

import time, threading
import av                                             # PyAV (ffmpeg binding) – giải mã RTSP
from core.logutil import jlog

STALL_TIMEOUT_S = 1.5                                 # Nếu không có frame > 1.5s → coi là stall
RECONNECT_BACKOFF = (0.5, 5.0)                        # Backoff lần đầu 0.5s, tối đa 5s

class RtspReader:
    """
    Mở RTSP qua TCP, đọc frame liên tục và bơm vào hub.
    Tự reconnect nếu lỗi/STALL.
    """
    def __init__(self, url: str, hub, stall_timeout=STALL_TIMEOUT_S, reconnect_backoff=RECONNECT_BACKOFF):
        self.url = url
        self.hub = hub
        self.stall_timeout = float(stall_timeout)
        self.reconnect_backoff = reconnect_backoff
        self._thr = None
        self._stop = threading.Event()

    def start(self):
        """Khởi động thread đọc."""
        if self._thr and self._thr.is_alive():
            return self
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()
        return self

    def stop(self):
        """Dừng thread; đóng kết nối."""
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=1.0)

    def _loop(self):
        """Vòng đọc + reconnect nếu cần."""
        backoff = self.reconnect_backoff[0]
        while not self._stop.is_set():
            try:
                # Mở stream RTSP qua TCP với options low-latency
                opts = {
                    "rtsp_transport": "tcp",
                    "fflags": "discardcorrupt",
                    "flags": "low_delay",
                    "reorder_queue_size": "0",
                    "max_delay": "30000",
                    "probesize": "500000",
                    "analyzeduration": "1000000",
                }
                jlog(event="rtsp_open", transport="tcp", opts=opts)
                ic = av.open(self.url, options=opts)              # Mở input container
                jlog(event="rtsp_open_ok", transport="tcp")

                # Lấy video stream đầu tiên
                vstream = next(s for s in ic.streams if s.type == "video")
                last_frame_ts = time.time()
                last_fps_calc = time.time()
                frame_cnt = 0
                fps_in = 0.0

                # clock_offset = mono_now - wall_now (dùng để ước tính latency khi render)
                clock_offset = time.perf_counter() - time.time()

                for packet in ic.demux(vstream):
                    if self._stop.is_set():
                        break
                    for frame in packet.decode():
                        # Cập nhật đếm để ước lượng FPS input
                        frame_cnt += 1
                        now = time.time()
                        if (now - last_fps_calc) >= 1.0:
                            fps_in = frame_cnt / (now - last_fps_calc)
                            frame_cnt = 0
                            last_fps_calc = now
                            jlog(event="stats_in", fps_in=round(fps_in, 2), transport="tcp", need_idr=False, corrupt=0)

                        # Ghi khung mới nhất vào Hub
                        self.hub.set((frame, clock_offset, "tcp", fps_in))
                        last_frame_ts = now

                    # Phát hiện STALL (quá 1.5s không có frame mới)
                    if (time.time() - last_frame_ts) > self.stall_timeout:
                        jlog(level="error", event="rtsp_loop_error", err=f"stall > {self.stall_timeout}s", transport="tcp")
                        raise RuntimeError("stall")

                try:
                    ic.close()
                except Exception:
                    pass

                backoff = self.reconnect_backoff[0]  # nếu rơi khỏi vòng for do stop → reset backoff
            except Exception as e:
                # Mỗi lần lỗi → backoff tăng dần đến max
                jlog(event="reconnecting_in", seconds=round(backoff, 2))
                time.sleep(backoff)
                backoff = min(self.reconnect_backoff[1], backoff * 1.5)
                continue

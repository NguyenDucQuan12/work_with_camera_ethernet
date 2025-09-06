# -*- coding: utf-8 -*-
# core/render_worker.py – Biến khung AV thành ảnh PIL đã resize (thread riêng)

import threading, time
import numpy as np
import cv2
from PIL import Image

class RenderWorker:
    """
    Lấy khung mới nhất từ hub và chuẩn bị sẵn PIL.Image đã resize:
      - Chuyển BGR (từ AV frame) → RGB
      - Resize khớp vùng hiển thị (fit hoặc giữ nguyên theo kích thước mục tiêu)
    UI chỉ việc bọc CTkImage → gắn vào Label (nhẹ).
    """
    def __init__(self, hub, get_target_size, proc_fps: int = 24):
        self.hub = hub                                     # LatestFrameHub
        self.get_target_size = get_target_size             # Hàm trả (w,h) mục tiêu
        self._thr = None
        self._stop = threading.Event()
        self._proc_fps = int(proc_fps)                     # Tốc độ xử lý tối đa
        self.latest_pil: Image.Image|None = None           # Ảnh PIL đã chuẩn bị sẵn

    def start(self):
        if self._thr and self._thr.is_alive():
            return self
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=1.0)

    def set_proc_fps(self, fps: int):
        """Đổi tốc độ xử lý ảnh (giảm tải CPU)."""
        self._proc_fps = max(1, int(fps))

    def _loop(self):
        """Đọc Hub → chuyển thành PIL.Image → lưu vào self.latest_pil."""
        interval = 1.0 / float(self._proc_fps)
        while not self._stop.is_set():
            t0 = time.time()
            item = self.hub.get()
            if item:
                av_frame, _clk, _transport, _fps_in = item
                # Lấy ndarray BGR từ AV frame
                bgr = av_frame.to_ndarray(format="bgr24")
                # Resize theo kích thước mục tiêu
                tw, th = self.get_target_size()
                if bgr.shape[1] != tw or bgr.shape[0] != th:
                    # Fit giữ tỉ lệ, thêm padding đen nhẹ để không méo
                    h, w = bgr.shape[:2]
                    scale = min(tw / w, th / h)
                    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
                    resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
                    canvas = np.zeros((th, tw, 3), dtype=np.uint8)
                    y0 = (th - nh) // 2
                    x0 = (tw - nw) // 2
                    canvas[y0:y0+nh, x0:x0+nw] = resized
                    bgr = canvas
                # BGR → RGB → PIL
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                self.latest_pil = Image.fromarray(rgb)

            # Nhịp xử lý cố định để không ăn hết CPU
            dt = time.time() - t0
            if dt < interval:
                time.sleep(interval - dt)

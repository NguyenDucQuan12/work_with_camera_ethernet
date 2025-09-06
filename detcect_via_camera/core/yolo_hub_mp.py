# -*- coding: utf-8 -*-
# core/yolo_hub_mp.py – Hub YOLO 1 process (dùng chung cho tối đa 6 tile)
# Mục tiêu:
#  - Chọn model động (set_model) → ví dụ yolo11n.pt cho CPU.
#  - "Adaptive throttle" khi device=cpu: nếu infer quá chậm → tự hạ proc_fps / imgsz.
#  - Chống nghẽn hàng đợi: result_q lớn hơn + parent xả nhanh + child put_nowait() có try/except.
#  - Shutdown an toàn: gửi "stop", join, kill nếu cần, đóng queues.

from __future__ import annotations
import multiprocessing as mp
import threading, time, traceback
from typing import Optional, Dict, Any, List
import numpy as np
import queue as pyqueue
from core.logutil import jlog

def _child_main(in_qs, result_q, ctrl_r):
    """Process con: nhận frame mới nhất từng tile, suy luận YOLO và bắn kết quả về parent."""
    import torch
    from ultralytics import YOLO

    # ----- Trạng thái cấu hình (nhận từ parent) -----
    enabled = False                 # YOLO bật/tắt toàn cục
    device  = "cpu"                 # "cpu" hoặc "cuda"
    conf    = 0.25                  # ngưỡng confidence
    imgsz   = 640                   # độ phân giải suy luận (sẽ làm tròn bội 32)
    proc_fps= 10                    # tốc độ suy luận mục tiêu (tile/giây)
    tracker = "none"                # none / bytetrack / ocsort
    classes = None                  # None = tất cả; hoặc danh sách class id
    model_name = "yolo11n.pt"       # tên/đường dẫn model
    max_tiles = len(in_qs)

    # ----- Biến runtime -----
    last_infer: List[float] = [0.0]*max_tiles  # thời điểm infer lần cuối mỗi tile
    tile_enabled: List[bool] = [True]*max_tiles
    model = None                   # đối tượng YOLO
    cur_dev = None                 # "cpu"/"cuda"
    ewma_dt = 0.0                  # EWMA thời gian infer (để throttle CPU)

    def _round32(v: int) -> int:
        """Làm tròn lên bội số 32 như cảnh báo của YOLO gợi ý."""
        s = 32
        return int(max(s, (int(v + s - 1) // s) * s))

    def _tracker_yaml(name: str) -> str|None:
        """Chọn file tracker theo tên ngắn; dùng YAML mặc định của Ultralytics."""
        if name == "bytetrack":
            return "bytetrack.yaml"
        if name == "ocsort":
            return "botsort.yaml"
        return None

    def _ensure_model_loaded():
        """Load/reload model khi enable và khi đổi thiết bị/model."""
        nonlocal model, cur_dev
        want_cuda = (device == "cuda" and torch.cuda.is_available())
        want_dev = "cuda" if want_cuda else "cpu"
        if (model is None) or (cur_dev != want_dev):
            # Giải phóng model cũ (nếu có)
            model = YOLO(model_name)     # Cho phép thay model từ parent
            model.to(want_dev)
            cur_dev = want_dev
            jlog(event="yolo_loaded", model=model_name, device=cur_dev)

    while True:
        try:
            # 1) Đọc lệnh điều khiển (không block) từ parent
            while ctrl_r.poll(0):
                cmd, val = ctrl_r.recv()
                if cmd == "stop":
                    return
                elif cmd == "enable":
                    enabled = bool(val)
                elif cmd == "device":
                    device = str(val); model = None   # buộc reload
                elif cmd == "conf":
                    conf = float(val)
                elif cmd == "proc_fps":
                    proc_fps = max(1, int(val))
                elif cmd == "imgsz":
                    imgsz = _round32(int(val))
                elif cmd == "enable_tile":
                    tid, on = val
                    if 0 <= tid < max_tiles: tile_enabled[tid] = bool(on)
                elif cmd == "tracker":
                    tracker = str(val or "none").lower()
                    if tracker not in ("none", "bytetrack", "ocsort"): tracker = "none"
                    jlog(event="yolo_tracker", tracker=tracker)
                elif cmd == "classes":
                    classes = None if (val is None) else list(map(int, val))
                    jlog(event="yolo_classes_child", classes=classes)
                elif cmd == "model":
                    model_name = str(val or "yolo11n.pt")
                    model = None  # buộc reload

            # 2) Nếu chưa bật, ngủ nhẹ để nhường CPU
            if not enabled:
                time.sleep(0.01)
                continue

            # 3) Đảm bảo model sẵn sàng
            _ensure_model_loaded()

            # 4) Suy luận theo nhịp proc_fps
            #    period = 1 / proc_fps (mỗi tile), nhưng ta quay vòng qua các tile
            base_period = 1.0 / float(proc_fps)
            now = time.time()

            # --- Adaptive throttle cho CPU ---
            # Nếu chạy CPU và infer trung bình > 1.25 * base_period thì:
            #   - giảm imgsz (tối thiểu 320) hoặc
            #   - giảm proc_fps (tối thiểu 2)
            # Giúp CPU không 100% kéo dài.
            if cur_dev == "cpu" and ewma_dt > 0:
                if ewma_dt > 1.25 * base_period:
                    if imgsz > 320:
                        imgsz = _round32(max(320, imgsz - 64))
                        jlog(event="yolo_adapt_imgsz", value=imgsz)
                    elif proc_fps > 2:
                        proc_fps = max(2, proc_fps - 1)
                        jlog(event="yolo_adapt_proc_fps", value=proc_fps)
                    # cập nhật base_period sau khi điều chỉnh
                    base_period = 1.0 / float(proc_fps)

            for tid, q in enumerate(in_qs):
                if not tile_enabled[tid]:
                    # Xả queue nếu tile tắt detect để tránh dồn RAM
                    try:
                        while True: q.get_nowait()
                    except Exception:
                        pass
                    continue

                # Lấy khung mới nhất (drop backlog)
                arr = None
                try:
                    while True:
                        arr = q.get_nowait()
                except Exception:
                    pass
                if arr is None:
                    continue

                # Giới hạn nhịp mỗi tile
                if (now - last_infer[tid]) < base_period:
                    continue

                # BGR → RGB (YOLO dùng RGB)
                bgr = arr
                rgb = bgr[..., ::-1]

                # Suy luận/tracking
                t0 = time.time()
                try:
                    if tracker == "none":
                        results = model.predict(rgb, imgsz=imgsz, conf=conf,
                                                classes=classes, verbose=False, device=cur_dev)
                    else:
                        yaml = _tracker_yaml(tracker)
                        if yaml is None:
                            results = model.predict(rgb, imgsz=imgsz, conf=conf,
                                                    classes=classes, verbose=False, device=cur_dev)
                        else:
                            results = model.track(rgb, imgsz=imgsz, conf=conf, classes=classes,
                                                  verbose=False, device=cur_dev, tracker=yaml, persist=True)

                    r = results[0]
                    boxes_xyxy = r.boxes.xyxy.detach().cpu().numpy().astype(int)
                    confs = r.boxes.conf.detach().cpu().numpy().tolist()
                    clss  = r.boxes.cls.detach().cpu().numpy().astype(int).tolist()

                    ids = None
                    try:
                        ids_t = r.boxes.id
                        if ids_t is not None:
                            ids = ids_t.detach().cpu().numpy().astype(int).tolist()
                    except Exception:
                        ids = None

                    # Bắn kết quả về parent (không để crash khi full)
                    try:
                        result_q.put_nowait({
                            "tile_id": tid,
                            "boxes": boxes_xyxy.tolist(),
                            "confs": confs,
                            "clss":  clss,
                            "ids":   ids,
                            "t": time.time()
                        })
                    except Exception:
                        pass

                    last_infer[tid] = now

                except Exception as e:
                    try:
                        result_q.put_nowait({
                            "event": "yolo_child_exception",
                            "err": str(e),
                            "trace": traceback.format_exc()
                        })
                    except Exception:
                        pass
                finally:
                    # Cập nhật EWMA thời gian infer để throttle CPU
                    dt = time.time() - t0
                    if ewma_dt == 0.0:
                        ewma_dt = dt
                    else:
                        ewma_dt = 0.9 * ewma_dt + 0.1 * dt

            # Nhường CPU nhẹ ở cuối vòng
            time.sleep(0.002)

        except KeyboardInterrupt:
            return
        except Exception as e:
            try:
                result_q.put_nowait({
                    "event": "yolo_child_exception",
                    "err": str(e),
                    "trace": traceback.format_exc()
                })
            except Exception:
                pass
            time.sleep(0.01)

class YoloMPHub:
    """Parent-side API: gửi cấu hình/frames, đọc kết quả và vẽ."""
    def __init__(self, max_tiles: int = 6, imgsz: int = 640):
        self.max_tiles = max_tiles
        self.imgsz = int(imgsz)
        self.enabled = False

        ctx = mp.get_context("spawn")
        # Mỗi tile 1 input queue (max=1) → luôn giữ frame mới nhất
        self._in_qs = [ctx.Queue(maxsize=1) for _ in range(max_tiles)]
        # Kết quả từ child: tăng lên 512 để khó đầy
        self._result_q = ctx.Queue(maxsize=512)
        # Pipe điều khiển: parent WRITE → child READ
        self._ctrl_r, self._ctrl_w = ctx.Pipe(duplex=False)
        self._proc: Optional[mp.Process] = None

        # Bộ đệm kết quả theo tile
        self._latest: Dict[int, Dict[str, Any]] = {}
        self._res_thr: Optional[threading.Thread] = None
        self._alive = False

    def start(self) -> "YoloMPHub":
        if self._proc is not None:
            return self
        ctx = mp.get_context("spawn")
        self._proc = ctx.Process(target=_child_main,
                                 args=(self._in_qs, self._result_q, self._ctrl_r),
                                 daemon=True)
        self._proc.start()
        self._alive = True

        # Thread hứng kết quả → xả nhanh để không đầy result_q
        def _reader():
            while self._alive:
                try:
                    msg = self._result_q.get(timeout=0.2)  # chờ có dữ liệu
                    self._handle_msg(msg)
                    # Sau khi lấy 1 bản ghi, xả thêm tất cả cái đang có
                    while True:
                        msg2 = self._result_q.get_nowait()
                        self._handle_msg(msg2)
                except pyqueue.Empty:
                    continue
                except Exception as e:
                    jlog(event="yolo_reader_exception", err=str(e))
        self._res_thr = threading.Thread(target=_reader, daemon=True)
        self._res_thr.start()

        # Thiết lập mặc định (enable False → chưa load model)
        self.set_imgsz(self.imgsz)
        self.set_conf(0.25)
        self.set_proc_fps(10)
        self.set_device("cpu")
        self.set_tracker("none")
        self.set_classes([0])
        self.set_model("yolo11n.pt")  # CPU-friendly mặc định
        self.set_enabled(False)
        return self

    def _handle_msg(self, msg: Dict[str, Any]):
        if isinstance(msg, dict) and msg.get("event") == "yolo_child_exception":
            jlog(event="yolo_child_exception", err=msg.get("err"), trace=msg.get("trace"))
            return
        tid = msg.get("tile_id")
        if tid is not None:
            self._latest[tid] = msg

    def stop(self):
        if not self._proc:
            return
        try:
            self._alive = False
            try:
                self._ctrl_w.send(("stop", None))
            except Exception:
                pass
            self._proc.join(timeout=1.0)
        except Exception:
            pass
        if self._proc.is_alive():
            self._proc.kill()
        self._proc = None

        try: self._result_q.close()
        except Exception: pass
        for q in self._in_qs:
            try: q.close()
            except Exception: pass
        time.sleep(0.05)

    # ===== Cấu hình toàn cục =====
    def set_enabled(self, v: bool):
        self.enabled = bool(v)
        try: self._ctrl_w.send(("enable", bool(v)))
        except Exception: pass
        jlog(event="yolo_enabled", value=self.enabled)

    def set_device(self, dev: str):
        try: self._ctrl_w.send(("device", str(dev)))
        except Exception: pass
        jlog(event="yolo_device", device=dev)

    def set_conf(self, conf: float):
        try: self._ctrl_w.send(("conf", float(conf)))
        except Exception: pass
        jlog(event="yolo_conf", conf=conf)

    def set_proc_fps(self, fps: int):
        try: self._ctrl_w.send(("proc_fps", int(fps)))
        except Exception: pass
        jlog(event="yolo_fps", fps=fps)

    def set_imgsz(self, imgsz: int):
        try: self._ctrl_w.send(("imgsz", int(imgsz)))
        except Exception: pass

    def set_tracker(self, tracker: str):
        t = (tracker or "none").lower()
        if t not in ("none", "bytetrack", "ocsort"):
            t = "none"
        try: self._ctrl_w.send(("tracker", t))
        except Exception: pass
        jlog(event="yolo_tracker_parent", tracker=t)

    def set_classes(self, classes: Optional[List[int]]):
        payload = None if classes is None else list(map(int, classes))
        try: self._ctrl_w.send(("classes", payload))
        except Exception: pass
        jlog(event="yolo_classes_parent", classes=payload)

    def set_model(self, model_name: str):
        """Chọn model YOLO (vd: yolo11n.pt/yolov8n.pt/đường dẫn custom)."""
        try: self._ctrl_w.send(("model", str(model_name)))
        except Exception: pass
        jlog(event="yolo_model_parent", model=model_name)

    # ===== Theo tile =====
    def enable_tile(self, tile_id: int, enabled: bool):
        if 0 <= tile_id < self.max_tiles:
            try: self._ctrl_w.send(("enable_tile", (int(tile_id), bool(enabled))))
            except Exception: pass

    def submit_bgr(self, tile_id: int, bgr: np.ndarray):
        """Đưa frame BGR mới nhất cho YOLO (drop backlog để không dồn RAM/CPU)."""
        if not (0 <= tile_id < self.max_tiles): return
        if not self.enabled: return
        q = self._in_qs[tile_id]
        try:
            # Xóa bản cũ nếu hàng đợi đã đủ 1 phần tử (giữ duy nhất frame mới nhất)
            while q.qsize() >= 1:
                q.get_nowait()
        except Exception:
            pass
        try:
            q.put_nowait(bgr)
        except Exception:
            pass

    def get_latest(self, tile_id: int) -> Optional[Dict[str, Any]]:
        return self._latest.get(tile_id)

    def draw_on(self, tile_id: int, bgr: np.ndarray):
        """Vẽ bbox/ID lên BGR theo kết quả gần nhất (nếu có)."""
        data = self.get_latest(tile_id)
        if not data:
            return bgr
        import cv2
        boxes = data.get("boxes", [])
        confs = data.get("confs", [])
        clss  = data.get("clss", [])
        ids   = data.get("ids", None)
        for i, ((x1, y1, x2, y2), cf, cl) in enumerate(zip(boxes, confs, clss)):
            color = (0, 255, 0) if cl == 0 else (0, 180, 255)  # person xanh, khác → cam
            cv2.rectangle(bgr, (x1, y1), (x2, y2), color, 2)
            tid = None if ids is None or i >= len(ids) else ids[i]
            label = f"{'ID:'+str(tid)+' ' if tid is not None else ''}{cl}:{cf:.2f}"
            cv2.putText(bgr, label, (x1, max(12, y1-6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        return bgr

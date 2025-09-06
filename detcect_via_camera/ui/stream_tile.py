# -*- coding: utf-8 -*-
# ui/stream_tile.py – 1 tile camera đầy đủ:
#  - Toolbar 2 hàng để không bị ẩn nút khi tile hẹp
#  - Overlay hiển thị giờ hiện tại (HH:MM:SS) + FPS camera
#  - Detect theo tile (checkbox), gửi frame cho YOLO Hub dùng chung
#  - Snapshot/Record thủ công + Auto snapshot/record theo phát hiện người
#  - Record nguyên bản (FFmpeg MKV) hoặc re-encode (PyAV/OpenCV MP4)
#  - Đóng tile dọn sạch tài nguyên

import os, time
import customtkinter as ctk
from tkinter import messagebox, filedialog
import cv2, numpy as np
from PIL import Image

from core.hub import LatestFrameHub
from core.reader import RtspReader, STALL_TIMEOUT_S, RECONNECT_BACKOFF
from core.video_recorder import VideoRecorder
from core.render_worker import RenderWorker
from core.logutil import jlog

SNAPSHOT_DIR = "snapshots"

class StreamTile(ctk.CTkFrame):
    def __init__(self, master, tile_id: int, yolo_hub, on_remove, **kwargs):
        super().__init__(master, **kwargs)
        self.tile_id = tile_id                # ID duy nhất trong 0..MAX_TILES-1
        self.yolo_hub = yolo_hub             # Hub YOLO dùng chung
        self.on_remove_cb = on_remove        # callback xóa tile

        # Lõi stream
        self.hub = LatestFrameHub()          # nhận khung mới nhất
        self.reader: RtspReader|None = None  # đọc RTSP
        self.render: RenderWorker|None = None# xử lý BGR->RGB + resize ở thread riêng
        self.connected = False               # trạng thái kết nối

        # Recorder
        self.recorder = VideoRecorder(out_dir="recordings", prefer_av=True)
        self.record_original = False         # true → copy-stream (FFmpeg MKV)

        # Lưu URL hiện tại để copy-stream
        self.current_url: str|None = None

        # Chính sách: được App áp từ Settings
        self.policy_auto_snapshot = False
        self.policy_auto_record   = False

        # Ngưỡng & hysteresis auto record
        self.det_conf_th = 0.40
        self.det_no_person_grace = 3.0
        self._last_person_ts = 0.0

        # Tốc độ render UI
        self.display_fps = ctk.IntVar(value=24)
        self._ctk_img = None
        self._render_busy = False

        # ====== Toolbar 2 hàng để không bị ẩn nút ======
        bar = ctk.CTkFrame(self); bar.pack(side="top", fill="x", padx=6, pady=(6,2))
        bar.grid_columnconfigure(1, weight=1)  # cột URL giãn

        # Hàng 0: Title + Detect + Remove
        self.lbl_title = ctk.CTkLabel(bar, text=f"Camera {self.tile_id+1}", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_title.grid(row=0, column=0, sticky="w", padx=4, pady=(4,2))
        self.detect_enable = ctk.BooleanVar(value=False)
        self.chk_detect = ctk.CTkCheckBox(bar, text="Detect (YOLO)", variable=self.detect_enable,
                                          command=self.on_toggle_detect)
        self.chk_detect.grid(row=0, column=1, sticky="e", padx=4, pady=(4,2))
        self.btn_remove = ctk.CTkButton(bar, text="🗑 Remove", width=80, fg_color="#883333",
                                        command=lambda: self.on_remove_cb(self.tile_id))
        self.btn_remove.grid(row=0, column=2, sticky="e", padx=4, pady=(4,2))

        # Hàng 1: URL + Connect/Disconnect + Snapshot + Record
        self.url_entry = ctk.CTkEntry(bar, width=10, placeholder_text="rtsp://user:pass@ip:port/...")  # width sẽ giãn theo grid
        self.url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(4,6), pady=(2,4))

        self.btn_connect = ctk.CTkButton(bar, text="Connect", width=88, command=self.on_connect)
        self.btn_connect.grid(row=1, column=2, sticky="e", padx=2, pady=(2,4))

        self.btn_disconnect = ctk.CTkButton(bar, text="Disconnect", width=88,
                                            command=self.on_disconnect, state="disabled")
        self.btn_disconnect.grid(row=1, column=3, sticky="e", padx=2, pady=(2,4))

        self.btn_snapshot = ctk.CTkButton(bar, text="Snapshot", width=88, command=self.on_snapshot)
        self.btn_snapshot.grid(row=1, column=4, sticky="e", padx=2, pady=(2,4))

        self.btn_record = ctk.CTkButton(bar, text="Record", width=88, command=self.on_toggle_record)
        self.btn_record.grid(row=1, column=5, sticky="e", padx=2, pady=(2,4))

        # Bật giãn cột URL
        bar.grid_columnconfigure(0, weight=0)
        bar.grid_columnconfigure(1, weight=1)  # cột của URL entry
        for col in (2,3,4,5):
            bar.grid_columnconfigure(col, weight=0)

        # ====== Vùng hiển thị video ======
        self.video_frame = ctk.CTkFrame(self, corner_radius=8)
        self.video_frame.pack(side="top", expand=True, fill="both", padx=6, pady=(2,6))
        self.canvas = ctk.CTkLabel(self.video_frame, text="")   # nơi hiển thị ảnh
        self.canvas.pack(expand=True, fill="both")
        self.video_frame.bind("<Configure>", lambda e: self._ensure_render_worker())

        # Thông tin nhỏ phía dưới
        self.lbl_stats = ctk.CTkLabel(self, text="—", justify="left")
        self.lbl_stats.pack(side="bottom", fill="x", padx=6, pady=(0,6))

        # Lên lịch render
        self._schedule_render()

    # ---------- Helpers ----------
    def _target_size(self):
        """Kích thước mục tiêu để RenderWorker resize cho khớp khung, auto-fit."""
        w = max(1, self.video_frame.winfo_width() - 12)
        h = max(1, self.video_frame.winfo_height() - 12)
        return (w, h)

    def _ensure_render_worker(self):
        """Khởi tạo/cập nhật RenderWorker cho tile."""
        if self.render is None:
            self.render = RenderWorker(self.hub, self._target_size, proc_fps=int(self.display_fps.get()))
            self.render.start()
        else:
            self.render.set_proc_fps(int(self.display_fps.get()))

    def _handle_detection_policies(self, bgr: np.ndarray):
        """Auto snapshot/record theo kết quả YOLO (person=0)."""
        res = self.yolo_hub.get_latest(self.tile_id)
        now = time.time()
        has_person = False
        try:
            if res:
                for (x1, y1, x2, y2), cf, cl in zip(res["boxes"], res["confs"], res["clss"]):
                    if cl == 0 and cf >= self.det_conf_th:
                        has_person = True
                        break
        except Exception:
            pass

        if has_person:
            self._last_person_ts = now
            # Auto snapshot (mỗi ≥2s)
            if self.policy_auto_snapshot:
                if not hasattr(self, "_last_snapshot_ts"): self._last_snapshot_ts = 0.0
                if (now - self._last_snapshot_ts) >= 2.0:
                    self._last_snapshot_ts = now
                    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
                    path = os.path.join(SNAPSHOT_DIR, f"tile{self.tile_id+1}_{time.strftime('%Y%m%d_%H%M%S')}.jpg")
                    cv2.imwrite(path, bgr)

            # Auto record
            if self.policy_auto_record and not self.recorder.is_recording():
                h, w = bgr.shape[:2]
                if self.record_original and self.current_url:
                    # copy-stream nguyên bản (FFmpeg MKV)
                    self.recorder.start(copy_stream=True, url=self.current_url)
                else:
                    # re-encode từ khung UI (MP4)
                    self.recorder.start(fps=25, size=(w, h))
        else:
            # Nếu vắng người liên tục > grace → dừng
            if self.policy_auto_record and self.recorder.is_recording():
                if (now - self._last_person_ts) > self.det_no_person_grace:
                    self.recorder.stop()

    # ---------- Actions ----------
    def on_connect(self):
        """Kết nối RTSP, auto-reconnect, bắt đầu render."""
        if self.connected: return
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Nhập RTSP URL trước.")
            return

        self._ensure_render_worker()
        self.reader = RtspReader(url, hub=self.hub,
                                 stall_timeout=STALL_TIMEOUT_S,
                                 reconnect_backoff=RECONNECT_BACKOFF).start()
        self.connected = True
        self.current_url = url
        self.btn_connect.configure(state="disabled")
        self.btn_disconnect.configure(state="normal")
        jlog(event="tile_connect", tile=self.tile_id, url=url)

    def on_disconnect(self):
        """Ngắt kết nối, dừng recorder & render worker, dọn UI."""
        # Tắt detect cho tile
        self.yolo_hub.enable_tile(self.tile_id, False)
        # Dừng reader
        if self.reader:
            self.reader.stop(); self.reader = None
        # Dừng ghi
        self.recorder.stop()
        # Dừng render
        if self.render:
            self.render.stop(); self.render = None
        # Trạng thái/UI
        self.connected = False
        self.current_url = None
        self.btn_connect.configure(state="normal")
        self.btn_disconnect.configure(state="disabled")
        self.hub.clear()
        self.canvas.configure(image=None, text="")
        jlog(event="tile_disconnect", tile=self.tile_id)

    def on_snapshot(self):
        """Chụp ảnh PNG từ khung mới nhất trong hub."""
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        item = self.hub.get()
        if not item:
            messagebox.showwarning("Snapshot", "Chưa có khung hình.")
            return
        frame, _, _, _ = item
        bgr = frame.to_ndarray(format="bgr24")
        path = os.path.join(SNAPSHOT_DIR, f"tile{self.tile_id+1}-{time.strftime('%Y%m%d-%H%M%S')}.png")
        cv2.imwrite(path, bgr)
        jlog(event="snapshot_saved", tile=self.tile_id, path=path)
        messagebox.showinfo("Snapshot", f"Lưu: {path}")

    def on_toggle_record(self):
        """Bật/tắt ghi video (copy-stream MKV hoặc re-encode MP4)."""
        if not self.recorder.is_recording():
            # Bắt đầu ghi
            if self.record_original:
                # Copy-stream: cần URL RTSP
                if not self.current_url:
                    messagebox.showerror("Record error", "Chưa có URL để copy-stream.")
                    return
                path = filedialog.asksaveasfilename(
                    defaultextension=".mkv",
                    filetypes=[("MKV (copy stream)", "*.mkv"), ("All files", "*.*")],
                    initialfile=time.strftime(f"tile{self.tile_id+1}-%Y%m%d-%H%M%S.mkv"),
                )
                if not path: return
                try:
                    self.recorder.start(path_or_basename=path, copy_stream=True, url=self.current_url)
                    self.btn_record.configure(text="Stop")
                except Exception as e:
                    messagebox.showerror("Record error", str(e))
            else:
                # Re-encode từ khung UI
                path = filedialog.asksaveasfilename(
                    defaultextension=".mp4",
                    filetypes=[("MP4 (H.264/mp4v)", "*.mp4"), ("All files", "*.*")],
                    initialfile=time.strftime(f"tile{self.tile_id+1}-%Y%m%d-%H%M%S.mp4"),
                )
                if not path: return
                size = (1280, 720)
                item = self.hub.get()
                if item:
                    frame, _, _, _ = item
                    bgr = frame.to_ndarray(format="bgr24")
                    size = (bgr.shape[1], bgr.shape[0])
                try:
                    self.recorder.start(path_or_basename=path, fps=25, size=size, copy_stream=False)
                    self.btn_record.configure(text="Stop")
                except Exception as e:
                    messagebox.showerror("Record error", str(e))
        else:
            # Dừng ghi
            self.recorder.stop()
            self.btn_record.configure(text="Record")

    def on_toggle_detect(self):
        """Bật/tắt detect cho tile này (YOLO Hub sẽ nhận frame)."""
        self.yolo_hub.enable_tile(self.tile_id, self.detect_enable.get())

    # ---------- Render loop ----------
    def _schedule_render(self):
        interval = max(1, int(1000 / max(1, int(self.display_fps.get()))))
        self.after(interval, self._render_once)

    def _render_once(self):
        try:
            if not self.render:
                self._ensure_render_worker()

            item = self.hub.get()
            fps_in = 0.0
            if item:
                frame, clock_offset, transport, fps_in = item

            pil_img = self.render.latest_pil if self.render else None
            if pil_img and not self._render_busy:
                self._render_busy = True

                # PIL → BGR để vẽ overlay/YOLO
                rgb = np.array(pil_img)
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

                # Gửi frame cho YOLO (nếu detect on)
                if self.detect_enable.get():
                    self.yolo_hub.submit_bgr(self.tile_id, bgr)

                # Vẽ bbox từ YOLO (nếu có)
                bgr = self.yolo_hub.draw_on(self.tile_id, bgr)

                # HUD: thời gian hiện tại + FPS camera
                now_txt = time.strftime("%H:%M:%S")  # yêu cầu đổi ms -> giờ hiện tại
                cv2.rectangle(bgr, (6, 6), (280, 32), (0, 0, 0), -1)
                cv2.putText(bgr, f"{now_txt} | {fps_in:.1f} fps",
                            (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80,255,80), 2, cv2.LINE_AA)

                # Ghi video khung UI nếu đang re-encode
                if self.recorder.vw is not None or self.recorder.av_container is not None:
                    try:
                        self.recorder.write(bgr)
                    except Exception:
                        pass

                # Auto policies (chỉ khi detect bật, vì dựa vào kết quả YOLO)
                if self.detect_enable.get():
                    self._handle_detection_policies(bgr)

                # Hiển thị lên UI
                rgb2 = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                pil_img2 = Image.fromarray(rgb2)
                self._ctk_img = ctk.CTkImage(light_image=pil_img2, dark_image=pil_img2,
                                             size=(pil_img2.width, pil_img2.height))
                self.canvas.configure(image=self._ctk_img)
                self.lbl_stats.configure(text=f"Tile {self.tile_id+1} | Connected: {self.connected} | FPS in: {fps_in:.1f}")

                self._render_busy = False

        except Exception as e:
            jlog(level="error", event="tile_render_error", tile=self.tile_id, err=str(e))
            self._render_busy = False
        finally:
            self._schedule_render()

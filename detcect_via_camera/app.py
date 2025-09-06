# -*- coding: utf-8 -*-
# app.py – Cập nhật: truyền device_items (label,value) cho SettingsPanel
# để OptionMenu hiển thị tên GPU đẹp và trả về value nội bộ (cpu/cuda:idx).

import os, time
import customtkinter as ctk
from tkinter import messagebox

from ui.stream_tile import StreamTile
from ui.settings_panel import SettingsPanel
from core.logutil import jlog
from core.yolo_hub_mp import YoloMPHub
from core.devutil import detect_devices   # <— mới

MAX_TILES = 6

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("RTSP Viewer – Multi (x6) + Snapshot/Record + YOLO Shared Hub")
        self.geometry("1600x900"); self.minsize(1400, 850)

        # YOLO Hub (dùng chung)
        self.yolo = YoloMPHub(max_tiles=MAX_TILES, imgsz=640).start()

        # Bố cục trái/phải
        self.grid_columnconfigure(0, weight=0, minsize=360)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.left = ctk.CTkFrame(self);  self.left.grid(row=0, column=0, sticky="nsew", padx=(8,4), pady=8)
        self.right = ctk.CTkFrame(self); self.right.grid(row=0, column=1, sticky="nsew", padx=(4,8), pady=8)
        self.right.grid_rowconfigure(1, weight=1); self.right.grid_columnconfigure(0, weight=1)

        # Topbar phải
        topbar = ctk.CTkFrame(self.right); topbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))
        topbar.grid_columnconfigure(0, weight=1)
        self.btn_add = ctk.CTkButton(topbar, text="➕ Add Camera", command=self.on_add)
        self.btn_add.grid(row=0, column=0, sticky="w", padx=(0,8))
        self.btn_close_all = ctk.CTkButton(topbar, text="✖ Close All", fg_color="#7a2b2b", command=self.on_close_all)
        self.btn_close_all.grid(row=0, column=1, sticky="e")

        # Khu grid tile
        self.grid_frame = ctk.CTkFrame(self.right); self.grid_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4,8))
        for r in range(2): self.grid_frame.grid_rowconfigure(r, weight=1, minsize=300)
        for c in range(3): self.grid_frame.grid_columnconfigure(c, weight=1, minsize=320)

        self.tiles = {}
        self.free_ids = list(range(MAX_TILES))

        # Dò thiết bị để hiển thị
        device_items = detect_devices()  # [(label,value), ...]
        # Giá trị mặc định cho state ban đầu: lấy value của phần tử đầu (CPU hoặc CUDA:0)
        default_device_value = device_items[0][1] if device_items else "cpu"

        # State ban đầu
        initial = {
            "yolo_enabled": False,
            "yolo_device": default_device_value,  # value (cpu/cuda:idx)
            "yolo_model": "yolo11n.pt",
            "yolo_conf": 0.25,
            "yolo_fps": 10,
            "yolo_tracker": "none",
            "yolo_imgsz": 640,
            "yolo_classes": [0],
            "auto_snapshot_on_person": False,
            "auto_record_on_person": False,
            "record_backend_prefer_av": True,
            "record_original_stream": False,
        }

        # Settings panel (truyền device_items để hiển thị)
        self.settings = SettingsPanel(self.left, initial, on_change=self.on_settings_change, device_items=device_items)
        self.settings.pack(fill="both", expand=True, padx=8, pady=8)

        # Ít nhất 1 tile
        self.on_add()
        # Áp settings lần đầu
        self.apply_settings(self.settings.get_state())

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---- quản lý tile ----
    def _next_free_id(self):
        if not self.free_ids: return None
        self.free_ids.sort(); return self.free_ids.pop(0)

    def on_add(self):
        tid = self._next_free_id()
        if tid is None:
            messagebox.showinfo("Limit", f"Tối đa {MAX_TILES} luồng.")
            return
        r, c = divmod(tid, 3)
        tile = StreamTile(self.grid_frame, tile_id=tid, yolo_hub=self.yolo, on_remove=self.on_remove)
        tile.grid(row=r, column=c, sticky="nsew", padx=8, pady=8)
        self.tiles[tid] = tile
        jlog(event="add_tile", count=len(self.tiles))
        # Áp lại cài đặt cho tile mới
        self.apply_settings(self.settings.get_state())

    def on_remove(self, tile_id: int):
        t = self.tiles.get(tile_id)
        if not t: return
        t.on_disconnect()
        t.destroy()
        del self.tiles[tile_id]
        self.free_ids.append(tile_id)
        jlog(event="remove_tile", tile=tile_id)

    def on_close_all(self):
        for tid in list(self.tiles.keys()):
            self.on_remove(tid)
        jlog(event="close_all")

    # ---- settings ----
    def on_settings_change(self, st: dict):
        self.apply_settings(st)

    def apply_settings(self, st: dict):
        # YOLO Hub (toàn cục)
        self.yolo.set_enabled(st["yolo_enabled"])
        self.yolo.set_device(st["yolo_device"])   # value: "cpu"/"cuda:idx"
        self.yolo.set_model(st["yolo_model"])
        self.yolo.set_conf(st["yolo_conf"])
        self.yolo.set_proc_fps(st["yolo_fps"])
        self.yolo.set_tracker(st["yolo_tracker"])
        self.yolo.set_imgsz(st["yolo_imgsz"])
        self.yolo.set_classes(st["yolo_classes"])
        # Chính sách/ghi hình ở mọi tile
        for tile in self.tiles.values():
            tile.policy_auto_snapshot = st["auto_snapshot_on_person"]
            tile.policy_auto_record   = st["auto_record_on_person"]
            tile.record_original      = st["record_original_stream"]
            tile.recorder.prefer_av   = st["record_backend_prefer_av"]

    # ---- đóng app ----
    def on_close(self):
        try:
            self.on_close_all()
            try: self.yolo.stop()
            except Exception: pass
        finally:
            try: self.destroy()
            except Exception: pass
            os._exit(0)

if __name__ == "__main__":
    try:
        import cv2
        cv2.setNumThreads(1)
    except Exception:
        pass
    app = App()
    app.mainloop()

# -*- coding: utf-8 -*-
# ui/settings_panel.py
# Thay đổi chính:
#  - Nhận danh sách thiết bị (label,value) từ App (đã dò GPU).
#  - Hiển thị đầy đủ 80 lớp COCO để chọn nhận diện.
#  - Giữ nguyên các option khác (conf, fps, imgsz, tracker, record policies).

import customtkinter as ctk
from typing import Callable, List, Tuple

# Đầy đủ COCO80 (Ultralytics): (id, name)
COCO_80 = [
    (0, "person"), (1, "bicycle"), (2, "car"), (3, "motorcycle"), (4, "airplane"),
    (5, "bus"), (6, "train"), (7, "truck"), (8, "boat"), (9, "traffic light"),
    (10, "fire hydrant"), (11, "stop sign"), (12, "parking meter"), (13, "bench"),
    (14, "bird"), (15, "cat"), (16, "dog"), (17, "horse"), (18, "sheep"),
    (19, "cow"), (20, "elephant"), (21, "bear"), (22, "zebra"), (23, "giraffe"),
    (24, "backpack"), (25, "umbrella"), (26, "handbag"), (27, "tie"), (28, "suitcase"),
    (29, "frisbee"), (30, "skis"), (31, "snowboard"), (32, "sports ball"), (33, "kite"),
    (34, "baseball bat"), (35, "baseball glove"), (36, "skateboard"), (37, "surfboard"), (38, "tennis racket"),
    (39, "bottle"), (40, "wine glass"), (41, "cup"), (42, "fork"), (43, "knife"),
    (44, "spoon"), (45, "bowl"), (46, "banana"), (47, "apple"), (48, "sandwich"),
    (49, "orange"), (50, "broccoli"), (51, "carrot"), (52, "hot dog"), (53, "pizza"),
    (54, "donut"), (55, "cake"), (56, "chair"), (57, "couch"), (58, "potted plant"),
    (59, "bed"), (60, "dining table"), (61, "toilet"), (62, "tv"), (63, "laptop"),
    (64, "mouse"), (65, "remote"), (66, "keyboard"), (67, "cell phone"), (68, "microwave"),
    (69, "oven"), (70, "toaster"), (71, "sink"), (72, "refrigerator"), (73, "book"),
    (74, "clock"), (75, "vase"), (76, "scissors"), (77, "teddy bear"), (78, "hair drier"),
    (79, "toothbrush")
]

class SettingsPanel(ctk.CTkScrollableFrame):
    def __init__(self,
                 master,
                 initial: dict,
                 on_change: Callable[[dict], None],
                 device_items: List[Tuple[str, str]]):
        """
        device_items: list (label,value) từ core.devutil.detect_devices()
                      ví dụ: [("CPU","cpu"), ("CUDA:0 — NVIDIA RTX 3060","cuda:0")]
        """
        super().__init__(master, label_text="Settings")
        self.on_change = on_change

        # ====== Map thiết bị cho OptionMenu ======
        self._dev_label_to_value = {lbl: val for (lbl, val) in device_items}
        device_labels = [lbl for (lbl, _val) in device_items]

        # Xác định label mặc định dựa trên initial["yolo_device"]
        init_device_val = initial.get("yolo_device", "cpu")
        init_device_label = device_labels[0]
        for lbl, val in device_items:
            if val == init_device_val:
                init_device_label = lbl
                break

        # ====== Biến trạng thái ======
        self.v_yolo_enabled = ctk.BooleanVar(value=initial.get("yolo_enabled", False))
        self.v_device_label = ctk.StringVar(value=init_device_label)  # lưu label, khi emit sẽ map → value
        self.v_model        = ctk.StringVar(value=initial.get("yolo_model", "yolo11n.pt"))
        self.v_conf         = ctk.DoubleVar(value=initial.get("yolo_conf", 0.25))
        self.v_fps          = ctk.IntVar(value=initial.get("yolo_fps", 10))
        self.v_tracker      = ctk.StringVar(value=initial.get("yolo_tracker", "none"))
        self.v_imgsz        = ctk.IntVar(value=initial.get("yolo_imgsz", 640))

        # classes: 80 ô checkbox
        self.class_vars = {}
        init_classes = set(initial.get("yolo_classes", [0]))
        for cid, _ in COCO_80:
            self.class_vars[cid] = ctk.BooleanVar(value=(cid in init_classes))

        self.v_auto_snap  = ctk.BooleanVar(value=initial.get("auto_snapshot_on_person", False))
        self.v_auto_rec   = ctk.BooleanVar(value=initial.get("auto_record_on_person", False))
        self.v_pref_av    = ctk.BooleanVar(value=initial.get("record_backend_prefer_av", True))
        self.v_rec_orig   = ctk.BooleanVar(value=initial.get("record_original_stream", False))

        # ====== UI ======
        sec1 = ctk.CTkFrame(self); sec1.pack(fill="x", padx=6, pady=(8,6))
        ctk.CTkLabel(sec1, text="YOLO").grid(row=0, column=0, sticky="w", padx=6, pady=(8,4))

        ctk.CTkCheckBox(sec1, text="Enable YOLO (load model)",
                        variable=self.v_yolo_enabled, command=self._emit)\
            .grid(row=1, column=0, columnspan=3, sticky="w", padx=12, pady=2)

        # Device (hiển thị label GPU)
        ctk.CTkLabel(sec1, text="Device").grid(row=2, column=0, sticky="w", padx=12, pady=2)
        ctk.CTkOptionMenu(sec1, values=device_labels, variable=self.v_device_label,
                          command=lambda _v: self._emit())\
            .grid(row=2, column=1, sticky="ew", padx=6, pady=2)

        # Model
        ctk.CTkLabel(sec1, text="Model").grid(row=3, column=0, sticky="w", padx=12, pady=2)
        ctk.CTkOptionMenu(sec1,
                          values=["yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolov8n.pt"],
                          variable=self.v_model,
                          command=lambda _v: self._emit())\
            .grid(row=3, column=1, sticky="ew", padx=6, pady=2)

        # Conf
        ctk.CTkLabel(sec1, text="Confidence").grid(row=4, column=0, sticky="w", padx=12, pady=(6,2))
        s_conf = ctk.CTkSlider(sec1, from_=0.05, to=0.9, number_of_steps=85,
                               variable=self.v_conf, command=lambda _v: self._emit())
        s_conf.grid(row=4, column=1, sticky="ew", padx=6, pady=(6,2))

        # Proc FPS
        ctk.CTkLabel(sec1, text="Proc FPS").grid(row=5, column=0, sticky="w", padx=12, pady=2)
        ctk.CTkSlider(sec1, from_=2, to=30, number_of_steps=28,
                      variable=self.v_fps, command=lambda _v: self._emit())\
            .grid(row=5, column=1, sticky="ew", padx=6, pady=2)

        # imgsz
        ctk.CTkLabel(sec1, text="imgsz").grid(row=6, column=0, sticky="w", padx=12, pady=2)
        ctk.CTkOptionMenu(sec1, values=["320","384","448","512","576","640"],
                          variable=self.v_imgsz, command=lambda _v: self._emit())\
            .grid(row=6, column=1, sticky="ew", padx=6, pady=2)

        # Tracker
        ctk.CTkLabel(sec1, text="Tracker").grid(row=7, column=0, sticky="w", padx=12, pady=(6,2))
        ctk.CTkOptionMenu(sec1, values=["none","bytetrack","ocsort"],
                          variable=self.v_tracker, command=lambda _v: self._emit())\
            .grid(row=7, column=1, sticky="ew", padx=6, pady=(6,2))

        # Classes (80 ô, chia 4 cột)
        sec2 = ctk.CTkFrame(self); sec2.pack(fill="x", padx=6, pady=(6,6))
        ctk.CTkLabel(sec2, text="Classes (COCO 80)").grid(row=0, column=0, columnspan=4, sticky="w", padx=6, pady=(8,4))
        # Nút nhanh: All / None / People-only
        btns = ctk.CTkFrame(sec2); btns.grid(row=1, column=0, columnspan=4, sticky="w", padx=6, pady=(0,6))
        ctk.CTkButton(btns, text="All", width=60, command=self._check_all).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="None", width=60, command=self._uncheck_all).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="People only", width=100, command=self._people_only).pack(side="left", padx=2)

        # 80 checkbox, 4 cột x 20 dòng
        cols = 4
        for idx, (cid, cname) in enumerate(COCO_80):
            r = 2 + (idx % 20)
            c = (idx // 20)
            ctk.CTkCheckBox(sec2, text=f"{cname} ({cid})",
                            variable=self.class_vars[cid],
                            command=self._emit).grid(row=r, column=c, sticky="w", padx=8, pady=1)

        # Policies & Record
        sec3 = ctk.CTkFrame(self); sec3.pack(fill="x", padx=6, pady=(6,8))
        ctk.CTkLabel(sec3, text="Policies / Record").grid(row=0, column=0, sticky="w", padx=6, pady=(8,4))

        ctk.CTkCheckBox(sec3, text="Auto snapshot on person",
                        variable=self.v_auto_snap, command=self._emit)\
            .grid(row=1, column=0, sticky="w", padx=12, pady=2)

        ctk.CTkCheckBox(sec3, text="Auto record on person",
                        variable=self.v_auto_rec, command=self._emit)\
            .grid(row=2, column=0, sticky="w", padx=12, pady=2)

        ctk.CTkCheckBox(sec3, text="Record original stream (FFmpeg MKV)",
                        variable=self.v_rec_orig, command=self._emit)\
            .grid(row=3, column=0, sticky="w", padx=12, pady=2)

        ctk.CTkCheckBox(sec3, text="Prefer PyAV for re-encode (MP4)",
                        variable=self.v_pref_av, command=self._emit)\
            .grid(row=4, column=0, sticky="w", padx=12, pady=(2,8))

        # Giãn cột
        for c in range(3):
            sec1.grid_columnconfigure(c, weight=1)
        for c in range(4):
            sec2.grid_columnconfigure(c, weight=1)
        for c in range(2):
            sec3.grid_columnconfigure(c, weight=1)

    # --- utils cho classes ---
    def _check_all(self):
        for v in self.class_vars.values():
            v.set(True)
        self._emit()

    def _uncheck_all(self):
        for v in self.class_vars.values():
            v.set(False)
        self._emit()

    def _people_only(self):
        for cid, v in self.class_vars.items():
            v.set(cid == 0)
        self._emit()

    # ---- state ----
    def get_state(self) -> dict:
        classes: List[int] = [cid for cid, var in self.class_vars.items() if var.get()]
        if not classes:
            classes = [0]
        return {
            "yolo_enabled": self.v_yolo_enabled.get(),
            # Map label -> value nội bộ (cpu/cuda:idx)
            "yolo_device": self._dev_label_to_value.get(self.v_device_label.get(), "cpu"),
            "yolo_model": self.v_model.get(),
            "yolo_conf": float(self.v_conf.get()),
            "yolo_fps": int(self.v_fps.get()),
            "yolo_tracker": self.v_tracker.get(),
            "yolo_imgsz": int(self.v_imgsz.get()),
            "yolo_classes": classes,
            "auto_snapshot_on_person": self.v_auto_snap.get(),
            "auto_record_on_person": self.v_auto_rec.get(),
            "record_backend_prefer_av": self.v_pref_av.get(),
            "record_original_stream": self.v_rec_orig.get(),
        }

    def _emit(self, *_):
        self.on_change(self.get_state())

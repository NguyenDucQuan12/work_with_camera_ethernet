# -*- coding: utf-8 -*-
# core/devutil.py
# Mục đích: dò các thiết bị tính toán sẵn có (CPU, CUDA GPUs) để
# hiển thị lên UI với tên "thân thiện", nhưng vẫn trả về "value" dùng nội bộ.
# - labels:  hiển thị trên UI, ví dụ "CUDA:0 — NVIDIA GeForce RTX 3060"
# - values:  đưa xuống YOLO Hub, ví dụ "cuda:0" hoặc "cpu"

from typing import List, Tuple

def detect_devices() -> List[Tuple[str, str]]:
    """
    Trả về list (label, value).
    Luôn có CPU, nếu có CUDA thì thêm từng GPU với tên.
    """
    devices: List[Tuple[str, str]] = [("CPU", "cpu")]  # CPU luôn sẵn
    try:
        import torch  # PyTorch dùng để dò CUDA và tên GPU
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                try:
                    name = torch.cuda.get_device_name(i)
                except Exception:
                    name = "CUDA Device"
                # label đẹp cho UI, value là chuỗi device hợp lệ cho YOLO
                devices.append((f"CUDA:{i} — {name}", f"cuda:{i}"))
    except Exception:
        # Không có torch hoặc CUDA → chỉ có CPU
        pass
    return devices

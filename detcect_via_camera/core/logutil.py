# -*- coding: utf-8 -*-
# core/logutil.py – Logger xuất JSON (dễ đọc/parse)

import json, time, sys

def jlog(level="info", **data):
    """
    In log dạng JSON 1 dòng:
      - Có field 'level' (info/error/warn)
      - Có timestamp ISO
    """
    data = dict(data)                          # Sao chép để không chỉnh object gốc
    data["level"] = level
    data["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        print(json.dumps(data, ensure_ascii=False), flush=True)
    except Exception:
        # Fallback nếu có object không serialize được
        print(str(data), flush=True, file=sys.stderr)

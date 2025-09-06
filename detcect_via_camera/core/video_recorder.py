# -*- coding: utf-8 -*-
# core/video_recorder.py
# Ghi video ở 2 chế độ:
# 1) copy-stream (bản gốc): dùng FFmpeg, container MKV, không tái mã hóa -> tương thích tốt
# 2) re-encode từ khung UI: ưu tiên PyAV (H.264, yuv420p), fallback OpenCV (mp4v)
#
# Mọi thao tác đều "best-effort" và có kiểm tra lỗi rõ ràng.

import os, time, shutil, subprocess, sys
from typing import Tuple, Optional

import numpy as np

class VideoRecorder:
    def __init__(self, out_dir: str = "recordings", prefer_av: bool = True):
        # Thư mục mặc định để lưu nếu người dùng không chọn đường dẫn
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)

        # Ghi re-encode (PyAV/OpenCV)
        self.prefer_av = prefer_av
        self.av_container = None         # av.container.OutputContainer
        self.av_stream = None            # av.video.stream.VideoStream
        self.vw = None                   # cv2.VideoWriter fallback

        # Ghi copy-stream (FFmpeg)
        self.ffmpeg_proc: Optional[subprocess.Popen] = None

        # Thông số re-encode (để write())
        self._reencode_size: Optional[Tuple[int, int]] = None
        self._reencode_fps: Optional[int] = None

    # ---------- Helpers ----------
    def _auto_path(self, ext: str) -> str:
        """Sinh đường dẫn mặc định theo thời gian."""
        ts = time.strftime("%Y%m%d-%H%M%S")
        return os.path.join(self.out_dir, f"rec-{ts}{ext}")

    def is_recording(self) -> bool:
        """Đang ghi ở bất kỳ chế độ nào?"""
        return (self.ffmpeg_proc is not None) or (self.av_container is not None) or (self.vw is not None)

    # ---------- START ----------
    def start(self,
              path_or_basename: Optional[str] = None,
              fps: int = 25,
              size: Optional[Tuple[int, int]] = None,
              copy_stream: bool = False,
              url: Optional[str] = None):
        """
        Bắt đầu ghi:
        - copy_stream=True  -> ghi bản gốc bằng FFmpeg (mkv).
                              yêu cầu url=rtsp...; path đuôi .mkv; nếu None sẽ tự tạo.
        - copy_stream=False -> re-encode từ khung UI:
                              path đuôi .mp4; nếu None sẽ tự tạo; cần fps & size.
        """
        # Nếu đang ghi thì dừng trước để tránh rối tài nguyên
        if self.is_recording():
            self.stop()

        if copy_stream:
            # ---- COPY-STREAM (FFmpeg) ----
            if not url:
                raise ValueError("copy-stream cần 'url' RTSP.")
            # Đường dẫn mặc định .mkv
            path = path_or_basename or self._auto_path(".mkv")
            if not path.lower().endswith(".mkv"):
                path += ".mkv"

            # Kiểm tra ffmpeg trong PATH
            exe = shutil.which("ffmpeg")
            if not exe:
                raise RuntimeError("Không tìm thấy FFmpeg trong PATH. Cài FFmpeg hoặc thêm vào PATH.")

            # Lệnh FFmpeg:
            # -rtsp_transport tcp : ép TCP cho ổn định
            # -i <url>            : nguồn RTSP
            # -c copy -map 0      : copy-stream tất cả track (video/audio) nếu có
            # -f matroska         : ghi container MKV
            # -y                  : ghi đè file cũ (nếu có)
            cmd = [
                exe, "-hide_banner", "-loglevel", "warning", "-y",
                "-rtsp_transport", "tcp",
                "-i", url,
                "-c", "copy", "-map", "0",
                "-f", "matroska",
                path
            ]
            # Tạo process FFmpeg
            creationflags = 0
            if os.name == "nt":
                # 0x08000000 = CREATE_NO_WINDOW để tránh mở console trên Windows
                creationflags = 0x08000000
            self.ffmpeg_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags
            )
            # Lưu để App có thể biết file đang ghi
            self._reencode_size = None
            self._reencode_fps = None
            return

        # ---- RE-ENCODE (PyAV/OpenCV) ----
        if size is None or fps is None:
            raise ValueError("Re-encode cần 'size' và 'fps'.")

        path = path_or_basename or self._auto_path(".mp4")
        if not (path.lower().endswith(".mp4") or path.lower().endswith(".m4v")):
            path += ".mp4"

        # Thử PyAV trước (chất lượng & tương thích tốt)
        self._reencode_size = (int(size[0]), int(size[1]))
        self._reencode_fps = int(fps)

        if self.prefer_av:
            try:
                import av
                # Tạo container MP4
                self.av_container = av.open(path, mode="w")
                # Tạo video stream H.264, yuv420p để tương thích player
                self.av_stream = self.av_container.add_stream("h264", rate=self._reencode_fps)
                self.av_stream.pix_fmt = "yuv420p"
                self.av_stream.width = self._reencode_size[0]
                self.av_stream.height = self._reencode_size[1]
                # Bitrate vừa phải (tùy biến)
                self.av_stream.bit_rate = 3_000_000
                return
            except Exception as e:
                # Fallback OpenCV nếu PyAV lỗi (không có libx264…)
                self.av_container = None
                self.av_stream = None

        # OpenCV fallback (codec mp4v – dễ phát, tuy hơi nặng)
        import cv2
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.vw = cv2.VideoWriter(path, fourcc, self._reencode_fps, self._reencode_size)
        if not self.vw.isOpened():
            self.vw = None
            raise RuntimeError("OpenCV VideoWriter không mở được file MP4. Hãy bật prefer_av hoặc kiểm tra codec.")

    # ---------- WRITE ----------
    def write(self, bgr: np.ndarray):
        """
        Ghi 1 khung BGR (chỉ dùng cho re-encode).
        copy-stream không cần write() vì FFmpeg tự hút từ RTSP.
        """
        if self.ffmpeg_proc is not None:
            return  # copy-stream → không cần ghi thủ công

        if self.av_container is not None:
            import av
            # Đảm bảo kích thước đúng (resize nếu cần)
            h, w = bgr.shape[:2]
            tw, th = self._reencode_size
            if (w, h) != (tw, th):
                import cv2
                bgr = cv2.resize(bgr, (tw, th), interpolation=cv2.INTER_AREA)
            # BGR -> RGB -> Frame -> encode
            rgb = bgr[:, :, ::-1].copy()
            frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            for packet in self.av_stream.encode(frame):
                self.av_container.mux(packet)
            return

        if self.vw is not None:
            # OpenCV nhận BGR đúng kích thước
            self.vw.write(bgr)

    # ---------- STOP ----------
    def stop(self):
        """Dừng ghi & giải phóng tài nguyên an toàn cho cả 2 chế độ."""
        # Dừng FFmpeg copy-stream
        if self.ffmpeg_proc is not None:
            proc = self.ffmpeg_proc
            self.ffmpeg_proc = None
            try:
                # Gửi tín hiệu kết thúc (đóng stdin là đủ cho ffmpeg thoát)
                if proc.stdin:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
                # Chờ một chút cho ffmpeg thoát êm
                for _ in range(20):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                # Nếu vẫn chưa thoát thì terminate/kill
                if proc.poll() is None:
                    proc.terminate()
                for _ in range(20):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        # Đóng PyAV
        if self.av_container is not None:
            try:
                # flush dữ liệu còn lại
                if self.av_stream is not None:
                    for packet in self.av_stream.encode(None):
                        self.av_container.mux(packet)
                self.av_container.close()
            except Exception:
                pass
            finally:
                self.av_container = None
                self.av_stream = None

        # Đóng OpenCV
        if self.vw is not None:
            try:
                self.vw.release()
            except Exception:
                pass
            finally:
                self.vw = None

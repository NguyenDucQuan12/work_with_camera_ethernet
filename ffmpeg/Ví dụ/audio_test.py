import cv2
import numpy as np
import subprocess
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import pyaudio
import threading
import signal
import os

class RTSPStreamer:
    def __init__(self, root):
        self.root = root
        self.ffmpeg_process = None
        self.ffmpeg_audio_process = None
        self.target_width = 640
        self.target_height = 360
        self.audio_thread = None

        # Giao diện Tkinter
        self.root.title("RTSP Video Streamer with Audio")
        self.root.geometry("800x600")

        # Label và entry cho URL RTSP
        url_label = tk.Label(self.root, text="RTSP URL:")
        url_label.pack(pady=5)
        self.url_entry = tk.Entry(self.root, width=50)
        self.url_entry.pack(pady=5)

        # Label và entry cho kích thước video
        width_label = tk.Label(self.root, text="Width:")
        width_label.pack(pady=5)
        self.width_entry = tk.Entry(self.root, width=10)
        self.width_entry.insert(0, "640")
        self.width_entry.pack(pady=5)

        height_label = tk.Label(self.root, text="Height:")
        height_label.pack(pady=5)
        self.height_entry = tk.Entry(self.root, width=10)
        self.height_entry.insert(0, "360")
        self.height_entry.pack(pady=5)

        # Nút để bắt đầu và dừng stream video và âm thanh
        start_button = ttk.Button(self.root, text="Start Stream", command=self.start_stream)
        start_button.pack(pady=10)

        stop_button = ttk.Button(self.root, text="Stop Stream", command=self.stop_stream)
        stop_button.pack(pady=10)

        # Label để hiển thị video
        self.video_label = tk.Label(self.root)
        self.video_label.pack()

        # Đảm bảo đóng FFmpeg process khi kết thúc
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def update_frame(self):
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:  # Kiểm tra xem FFmpeg process còn chạy không
            raw_frame = self.ffmpeg_process.stdout.read(self.target_width * self.target_height * 3)

            if len(raw_frame) == (self.target_width * self.target_height * 3):
                # Chuyển đổi dữ liệu thô từ OpenCV sang dạng hình ảnh mà Tkinter có thể hiển thị
                frame = np.frombuffer(raw_frame, np.uint8).reshape((self.target_height, self.target_width, 3))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Chuyển từ BGR sang RGB (Tkinter dùng RGB)

                # Chuyển đổi frame sang định dạng Image để dùng với Tkinter
                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(image=img)

                # Cập nhật hình ảnh trong giao diện Tkinter
                self.video_label.imgtk = imgtk  # Giữ một tham chiếu để tránh bị garbage collected
                self.video_label.configure(image=imgtk)

        # Gọi lại hàm update_frame sau một khoảng thời gian
        self.video_label.after(10, self.update_frame)

    def play_audio(self):
        # Cấu hình cho PyAudio
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16,  # Định dạng âm thanh (16-bit PCM)
                        channels=1,              # Số kênh âm thanh (mono)
                        rate=8000,               # Tần số mẫu (8000 Hz cho G711)
                        output=True)             # Chế độ phát âm thanh

        try:
            while self.ffmpeg_audio_process and self.ffmpeg_audio_process.poll() is None:  # Kiểm tra xem FFmpeg audio process còn chạy không
                audio_frame = self.ffmpeg_audio_process.stdout.read(1024)
                if len(audio_frame) == 0:
                    break
                stream.write(audio_frame)
        except Exception as e:
            print(f"Audio error: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    def start_stream(self):
        self.target_width = int(self.width_entry.get())
        self.target_height = int(self.height_entry.get())
        in_stream = self.url_entry.get()

        if not in_stream:
            tk.messagebox.showerror("Error", "Please enter a valid RTSP URL")
            return

        try:
            # Lệnh FFmpeg để xử lý video
            # lệnh để không hiển thị log: `quiet`: ko thông báo, `panic`: hiển thị thông báo nghêm trọng nhất, `fatal`: hiển thị thông báo nghiêm trọng,
            # `error`: thông báo lỗi, `warning`, `infor`, `verbose`: hiển thị nhiều thông tin chi tiết hơn, `debug`
            command_video = [
                'C:/ffmpeg/bin/ffmpeg.exe',  # Đường dẫn đến FFmpeg trên máy của bạn
                '-loglevel', 'quiet',    # Tắt log, nếu cần thông tin từ log thì bỏ dòng này
                '-use_wallclock_as_timestamps', '1',  # Sử dụng thời gian thực cho dấu thời gian
                '-err_detect', 'ignore_err',  # Bỏ qua các lỗi dấu thời gian không hợp lệ
                '-rtsp_transport', 'tcp',
                '-i', in_stream,
                '-vf', f'scale={self.target_width}:{self.target_height}',  # Thay đổi kích thước video
                '-f', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-an', 'pipe:'
            ]

            # Lệnh FFmpeg để xử lý âm thanh (G711 mu-law)
            command_audio = [
                'C:/ffmpeg/bin/ffmpeg.exe',  # Đường dẫn đến FFmpeg trên máy của bạn
                '-loglevel', 'quiet', 
                '-use_wallclock_as_timestamps', '1',  # Sử dụng thời gian thực cho dấu thời gian
                '-rtsp_transport', 'tcp',
                '-i', in_stream,
                '-vn',  # Bỏ video, chỉ lấy âm thanh
                '-acodec', 'pcm_s16le',  # Âm thanh G711 mu-law
                '-ar', '8000',           # Tần số mẫu (8000 Hz)
                '-ac', '1',              # 1 kênh âm thanh (mono)
                '-f', 's16le',           # Định dạng raw
                '-'
            ]

            # Khởi chạy FFmpeg để xử lý video
            self.ffmpeg_process = subprocess.Popen(command_video, stdout=subprocess.PIPE)

            # Khởi chạy FFmpeg để xử lý âm thanh
            self.ffmpeg_audio_process = subprocess.Popen(command_audio, stdout=subprocess.PIPE)

            # Bắt đầu luồng phát âm thanh
            # self.audio_thread = threading.Thread(target=self.play_audio, daemon=True)
            # self.audio_thread.start()

            # Bắt đầu cập nhật khung hình lên giao diện Tkinter
            self.update_frame()

        except Exception as e:
            tk.messagebox.showerror("Error", str(e))

    def stop_stream(self):
        self.stop_ffmpeg_process()

    def stop_ffmpeg_process(self):
        try:
            if self.ffmpeg_process:
                self.ffmpeg_process.stdout.close()
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait()
                self.ffmpeg_process = None
            if self.ffmpeg_audio_process:
                self.ffmpeg_audio_process.stdout.close()
                self.ffmpeg_audio_process.terminate()
                self.ffmpeg_audio_process.wait()
                self.ffmpeg_audio_process = None
        except Exception as e:
            print(f"Error stopping FFmpeg process: {e}")

    def on_closing(self):
        # Đảm bảo rằng tất cả các tiến trình FFmpeg được dừng trước khi đóng chương trình
        self.stop_ffmpeg_process()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = RTSPStreamer(root)
    root.mainloop()

import cv2
import numpy as np
import subprocess
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import pyaudio
import threading

class RTSPStreamer:
    def __init__(self, root, camera_id, rtsp_url):
        self.root = root
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.ffmpeg_process = None
        self.ffmpeg_audio_process = None
        self.target_width = 640
        self.target_height = 360
        self.audio_thread = None

        # Frame cho mỗi camera
        self.frame = tk.Frame(self.root)
        self.frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Tạo giao diện cho mỗi camera
        camera_label = tk.Label(self.frame, text=f"Camera {self.camera_id} - RTSP: {self.rtsp_url}")
        camera_label.pack(pady=5)

        # Label để hiển thị video của camera này
        self.video_label = tk.Label(self.frame)
        self.video_label.pack()

        # Nút để bắt đầu và dừng stream video và âm thanh
        start_button = ttk.Button(self.frame, text=f"Start Camera {self.camera_id}", command=self.start_stream)
        start_button.pack(pady=5)

        stop_button = ttk.Button(self.frame, text=f"Stop Camera {self.camera_id}", command=self.stop_stream)
        stop_button.pack(pady=5)

    def update_frame(self):
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            raw_frame = self.ffmpeg_process.stdout.read(self.target_width * self.target_height * 3)
            if len(raw_frame) == (self.target_width * self.target_height * 3):
                frame = np.frombuffer(raw_frame, np.uint8).reshape((self.target_height, self.target_width, 3))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(image=img)
                self.video_label.imgtk = imgtk
                self.video_label.configure(image=imgtk)

        self.video_label.after(10, self.update_frame)

    def play_audio(self):
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=8000, output=True)
        try:
            while self.ffmpeg_audio_process and self.ffmpeg_audio_process.poll() is None:
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
        try:
            command_video = [
                'ffmpeg', # Sử dụng nếu đã thêm FFmpeg vào biến môi trường Path, còn không thì sử dụng đường dẫn cụ thể 'C:/ffmpeg/bin/ffmpeg.exe'
                '-loglevel', 'quiet',
                '-use_wallclock_as_timestamps', '1',
                '-err_detect', 'ignore_err',
                '-rtsp_transport', 'tcp',
                '-i', self.rtsp_url,
                '-vf', f'scale={self.target_width}:{self.target_height}',
                '-f', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-an', 'pipe:'
            ]

            command_audio = [
                'C:/ffmpeg/bin/ffmpeg.exe',
                '-loglevel', 'quiet',
                '-use_wallclock_as_timestamps', '1',
                '-rtsp_transport', 'tcp',
                '-i', self.rtsp_url,
                '-vn',
                '-acodec', 'pcm_s16le',
                '-ar', '8000',
                '-ac', '1',
                '-f', 's16le',
                '-'
            ]

            self.ffmpeg_process = subprocess.Popen(command_video, stdout=subprocess.PIPE)
            self.ffmpeg_audio_process = subprocess.Popen(command_audio, stdout=subprocess.PIPE)

            self.audio_thread = threading.Thread(target=self.play_audio, daemon=True)
            self.audio_thread.start()

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
        self.stop_ffmpeg_process()

class MultiCameraApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Camera RTSP Streamer")
        self.root.geometry("1200x800")

        self.cameras = []
        self.camera_urls = [
            "rtsp://192.168.0.122:554/1/stream1/Profile1",  # Camera 1
            "rtsp://192.168.0.21:554/1/stream1/Profile1",  # Camera 2
            "rtsp://192.168.0.42:554/1/stream1/Profile1",  # Camera 3
            "rtsp://192.168.0.92:554/1/stream1/Profile1"   # Camera 4
        ]

        for i, url in enumerate(self.camera_urls, start=1):
            camera_streamer = RTSPStreamer(root, i, url)
            self.cameras.append(camera_streamer)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        for camera in self.cameras:
            camera.on_closing()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = MultiCameraApp(root)
    root.mainloop()

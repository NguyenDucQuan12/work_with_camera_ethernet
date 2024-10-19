import cv2
import numpy as np
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import threading
import queue

class RTSPStreamer:
    def __init__(self, root):
        self.root = root
        self.ffmpeg_process = None
        self.frame_queue = queue.Queue(maxsize=10)  # Giới hạn kích thước hàng đợi
        self.frame_thread = None
        self.error_thread = None
        self.running = False  # Cờ để kiểm soát việc chạy/dừng
        self.buffer_size = 0  # Không sử dụng bộ đệm cho pipe

        # Giao diện Tkinter
        self.root.title("RTSP Video Streamer with Audio")
        self.root.geometry("800x800")

        # Label và entry cho URL RTSP
        url_label = tk.Label(self.root, text="RTSP URL:")
        url_label.pack(pady=5)
        self.url_entry = tk.Entry(self.root, width=50)
        self.url_entry.insert(0, "rtsp://192.168.0.122:554/1/stream1/Profile1")
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

        # Nút để chuyển camera
        switch_button = ttk.Button(self.root, text="Switch Camera", command=self.switch_camera)
        switch_button.pack(pady=10)

        # Label để hiển thị video
        self.video_label = tk.Label(self.root)
        self.video_label.pack()

        # Đảm bảo đóng FFmpeg process khi kết thúc
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def read_frames(self):
        frame_size = self.target_width * self.target_height * 3
        buffer = b''
        while self.running and self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            try:
                # Đọc dữ liệu cho đến khi đủ một khung hình
                while len(buffer) < frame_size:
                    chunk = self.ffmpeg_process.stdout.read(frame_size - len(buffer))
                    if not chunk:
                        # EOF hoặc lỗi
                        print("Không nhận được khung hình nào từ FFmpeg.")
                        # self.running = False
                        break
                    buffer += chunk

                if not self.running:
                    break

                raw_frame = buffer[:frame_size]
                buffer = buffer[frame_size:]  # Xóa dữ liệu đã xử lý khỏi bộ đệm

                frame = np.frombuffer(raw_frame, np.uint8).reshape((self.target_height, self.target_width, 3))
                try:
                    self.frame_queue.put(frame, timeout=0.1)
                except queue.Full:
                    print("hàng đợi đầy")
                    # pass  # Hàng đợi đầy, bỏ qua khung hình
            except Exception as e:
                if not self.running:
                    # Có thể do tiến trình đã dừng, bỏ qua lỗi
                    break
                print(f"Lỗi đọc khung hình: {e}")
                break

    def update_frame(self):
        try:
            frame = self.frame_queue.get_nowait()
            # Chuyển đổi dữ liệu thô từ OpenCV sang dạng hình ảnh mà Tkinter có thể hiển thị
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Chuyển từ BGR sang RGB (Tkinter dùng RGB)

            # Chuyển đổi frame sang định dạng Image để dùng với Tkinter
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)

            # Cập nhật hình ảnh trong giao diện Tkinter
            self.video_label.imgtk = imgtk  # Giữ một tham chiếu để tránh bị garbage collected
            self.video_label.configure(image=imgtk)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Lỗi cập nhật khung hình: {e}")
        finally:
            # Gọi lại hàm update_frame sau một khoảng thời gian
            if self.running:
                self.video_label.after(10, self.update_frame)

    def start_stream(self):
        self.target_width = int(self.width_entry.get())
        self.target_height = int(self.height_entry.get())
        in_stream = self.url_entry.get()

        if not in_stream:
            messagebox.showerror("Error", "Please enter a valid RTSP URL")
            return

        # Dừng stream hiện tại nếu đang chạy
        if self.running:
            self.stop_ffmpeg_process()

        try:
            # Lệnh FFmpeg để xử lý video
            command_video = [
                'ffmpeg',  # Đường dẫn đến FFmpeg trên máy của bạn
                '-nostdin',  # Không chờ đầu vào từ người dùng
                # '-loglevel', 'error',  # Chỉ hiển thị lỗi
                '-rtsp_transport', 'tcp',
                '-i', in_stream,
                '-vf', f'scale={self.target_width}:{self.target_height}',  # Thay đổi kích thước video
                '-f', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-an', 'pipe:1'
            ]

            # Khởi chạy FFmpeg để xử lý video
            self.ffmpeg_process = subprocess.Popen(
                command_video, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=self.buffer_size
            )

            self.running = True

            # Bắt đầu luồng đọc lỗi từ FFmpeg
            self.error_thread = threading.Thread(target=self.read_ffmpeg_errors, daemon=True)
            self.error_thread.start()

            # Bắt đầu luồng đọc khung hình từ FFmpeg
            self.frame_thread = threading.Thread(target=self.read_frames, daemon=True)
            self.frame_thread.start()

            # Bắt đầu cập nhật khung hình lên giao diện Tkinter
            self.update_frame()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def read_ffmpeg_errors(self):
        try:
            while self.running and self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                error_line = self.ffmpeg_process.stderr.readline()
                if error_line:
                    print(f"FFmpeg error: {error_line.decode().strip()}")
                else:
                    print("không có error line")
                    break
        except Exception as e:
            if not self.running:
                # Có thể do tiến trình đã dừng, bỏ qua lỗi
                print(f"sell.running trong luồng đọc lỗi: {self.running}")
            else:
                print(f"Lỗi đọc lỗi từ FFmpeg: {e}")

    def stop_stream(self):
        self.stop_ffmpeg_process()

    def stop_ffmpeg_process(self):
        try:
            self.running = False
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=5)
                self.ffmpeg_process = None

            if self.frame_thread:
                self.frame_thread.join(timeout=1)
                self.frame_thread = None

            if self.error_thread:
                self.error_thread.join(timeout=1)
                self.error_thread = None

            # Xóa hàng đợi khung hình
            with self.frame_queue.mutex:
                self.frame_queue.queue.clear()

            # Xóa hình ảnh khỏi giao diện
            self.video_label.config(image='')

        except Exception as e:
            print(f"Lỗi dừng tiến trình FFmpeg: {e}")

    def switch_camera(self):
        # Dừng stream hiện tại
        self.stop_ffmpeg_process()

        in_stream = self.url_entry.get()
        if in_stream == "rtsp://192.168.0.122:554/1/stream1/Profile1":
            # Thiết lập URL mới 
            new_url = "rtsp://192.168.0.21:554/1/stream1/Profile1"
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, new_url)
        else:
            # Thiết lập URL mới 
            new_url = "rtsp://192.168.0.122:554/1/stream1/Profile1"
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, new_url)

        # Bắt đầu stream mới
        self.start_stream()

    def on_closing(self):
        # Đảm bảo rằng tất cả các tiến trình FFmpeg được dừng trước khi đóng chương trình
        self.stop_ffmpeg_process()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = RTSPStreamer(root)
    root.mainloop()

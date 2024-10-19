import cv2
import numpy as np
import subprocess
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

# Hàm để cập nhật khung hình từ luồng video
def update_frame():
    raw_frame = ffmpeg_process.stdout.read(target_width * target_height * 3)

    if len(raw_frame) == (target_width * target_height * 3):
        # Chuyển đổi dữ liệu thô từ OpenCV sang dạng hình ảnh mà Tkinter có thể hiển thị
        frame = np.frombuffer(raw_frame, np.uint8).reshape((target_height, target_width, 3))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Chuyển từ BGR sang RGB (Tkinter dùng RGB)

        # Chuyển đổi frame sang định dạng Image để dùng với Tkinter
        img = Image.fromarray(frame)
        imgtk = ImageTk.PhotoImage(image=img)

        # Cập nhật hình ảnh trong giao diện Tkinter
        video_label.imgtk = imgtk  # Giữ một tham chiếu để tránh bị garbage collected
        video_label.configure(image=imgtk)

    # Gọi lại hàm update_frame sau một khoảng thời gian
    video_label.after(10, update_frame)

# Hàm để bắt đầu quá trình stream video
def start_stream():
    global ffmpeg_process, target_width, target_height

    # Lấy URL RTSP và kích thước từ giao diện người dùng
    in_stream = url_entry.get()
    target_width = int(width_entry.get())
    target_height = int(height_entry.get())

    if not in_stream:
        tk.messagebox.showerror("Error", "Please enter a valid RTSP URL")
        return

    try:
        # Lệnh FFmpeg để xử lý video
        command = [
            'C:/ffmpeg/bin/ffmpeg.exe',  # Đường dẫn đến FFmpeg trên máy của bạn
            '-rtsp_transport', 'tcp',    # Phương thức kết nối là TCP
            '-i', in_stream,
            '-vf', f'scale={target_width}:{target_height}',  # Thay đổi kích thước video
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-an', 'pipe:'
        ]

        # Khởi chạy FFmpeg và đọc từ stdout
        ffmpeg_process = subprocess.Popen(command, stdout=subprocess.PIPE)

        # Bắt đầu cập nhật khung hình lên giao diện Tkinter
        update_frame()

    except Exception as e:
        tk.messagebox.showerror("Error", str(e))

# Giao diện Tkinter
root = tk.Tk()
root.title("RTSP Video Streamer")
root.geometry("800x600")

# Label và entry cho URL RTSP
url_label = tk.Label(root, text="RTSP URL:")
url_label.pack(pady=5)
url_entry = tk.Entry(root, width=50)
url_entry.pack(pady=5)

# Label và entry cho kích thước video
width_label = tk.Label(root, text="Width:")
width_label.pack(pady=5)
width_entry = tk.Entry(root, width=10)
width_entry.insert(0, "640")  # Đặt giá trị mặc định
width_entry.pack(pady=5)

height_label = tk.Label(root, text="Height:")
height_label.pack(pady=5)
height_entry = tk.Entry(root, width=10)
height_entry.insert(0, "360")  # Đặt giá trị mặc định
height_entry.pack(pady=5)

# Nút để bắt đầu stream video
start_button = ttk.Button(root, text="Start Stream", command=start_stream)
start_button.pack(pady=10)

# Label để hiển thị video
video_label = tk.Label(root)
video_label.pack()

# Chạy giao diện Tkinter
root.mainloop()

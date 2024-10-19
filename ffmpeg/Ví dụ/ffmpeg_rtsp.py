import cv2
import numpy as np
import subprocess

# URL RTSP từ camera
in_stream = 'rtsp://192.168.0.122:554/1/stream1/Profile1'

# Kiểm tra kích thước gốc của video bằng OpenCV
cap = cv2.VideoCapture(in_stream)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap.release()

print(f"Original Width: {width}, Height: {height}")

# Thay đổi kích thước mục tiêu
target_width = 640  # Kích thước mới (ví dụ 640x360)
target_height = 360

# Lệnh FFmpeg để thay đổi kích thước video
command = [
    'ffmpeg',
    '-rtsp_transport', 'tcp',
    '-i', in_stream,
    '-vf', f'scale={target_width}:{target_height}',  # Thay đổi kích thước video
    '-f', 'rawvideo',
    '-pix_fmt', 'bgr24',
    '-an', 'pipe:'
]

# Khởi chạy FFmpeg và đọc từ stdout
ffmpeg_process = subprocess.Popen(command, stdout=subprocess.PIPE)

while True:
    # Đọc số byte tương ứng với kích thước mới của video
    raw_frame = ffmpeg_process.stdout.read(target_width * target_height * 3)

    if len(raw_frame) != (target_width * target_height * 3):
        print('Error reading frame!!!')
        break

    # Chuyển đổi dữ liệu thô thành numpy array và reshape về kích thước mới
    frame = np.frombuffer(raw_frame, np.uint8).reshape((target_height, target_width, 3))

    # Hiển thị khung hình
    cv2.imshow('image', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Đóng stdout và chờ FFmpeg kết thúc
ffmpeg_process.stdout.close()
ffmpeg_process.wait()
cv2.destroyAllWindows()

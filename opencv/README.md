# Sử dụng phần mềm opencv để kết nối và xem camera thông qua đường link rtsp  

# Mục lục

[I. Opencv](#i-Opencv)
- [1. Cài đặt opencv bằng pip](#1-cài-đặt-opencv-bằng-pip)
- [2. Giải nén và đổi tên](#2-giải-nén-và-đổi-tên)
- [3. Di chuyển thư mục vào ổ C](#3-Di-chuyển-thư-mục-vào-ổ-C)
- [4. Đặt PATH cho FFMPEG](#4-Đặt-PATH-cho-FFMPEG)

[II. Cách sử dụng](#ii-cách-sử-dụng)
- [1. Sử dụng bằng cách gọi trực tiếp ffmpeg](#1-Sử-dụng-bằng-cách-gọi-trực-tiếp-ffmpeg)
    - [1. Lệnh chỉ sử dụng hình ảnh](#1-Lệnh-chỉ-sử-dụng-hình-ảnh)
    - [2. Lệnh lấy cả âm thanh từ camera](#2-Lệnh-lấy-cả-âm-thanh-từ-camrra)

- [2. Sử dụng bằng cách gọi thư viện ffmpeg-python](#2-Sử-dụng-bằng-cách-gọi-thư-viện-ffmpeg---python)

[III. Ví dụ](#iii-Ví-dụ)

# Opencv

## I. Cài đặt opencv bằng pip  
Truy cập trang chủ `opencv` trên [Pypi](https://pypi.org/project/opencv-python/) hoặc [Github](https://github.com/opencv/opencv-python)  
Cài đặt đơn giản `opencv` nhất là sử dụng `pip`. Mở dự án, kích hoạt môi trường ảo và chạy câu lệnh sau bằng terminal: 

```python
pip install opencv-python
```
![cài đặt opencv thông qua pip](image\install_opencv_pip.png)


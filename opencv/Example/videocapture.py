import threading
import cv2
import time
import PIL.ImageTk, PIL.Image
import time
from language.language_manager import language_system
import logging

# Lấy tên file của nơi gọi hàm logger
logger = logging.getLogger(__name__)

class VideoCapture:
    """
    Class chịu trách nhiệm đọc các khung hình từ camera và gửi các khung hình đến các class khác để xử lý
    
    Tham số:
    video_source: là đường dẫn rtsp đối với camera ip
    
    Hàm:
    open_camera: Mở kết nối đến với camera, và ghi lại log cùng với địa chỉ kết nối
    
    process: Hàm này được chạy trong 1 thread riêng, luôn luôn lấy các khung hình từ camera và không gây ảnh hưởng đến các thread khác
            việc chạy trong thread khác giúp cho việc phát các khung hình mượt mà hơn
            
    get_frame: Chịu trách nhiệm lấy frame hiện tại, phục vụ cho các class khác khi gọi hàm này
        
    release_function: Giải phóng tài nguyên khi kết thúc chương trình hoặc mất kết nối đến camera
    """
    def __init__(self, video_source):

        # Khởi tạo các giá trị mặc định
        self.video_source = video_source
        self.vid = None
        
        self.ret = False
        self.frame = None

        self.width = 500
        self.height = 400

        # số lần thử kết nối lại
        self.count = 0
        # Hình ảnh mặc định khi mất kết nối tới camera
        self.disconnected_camera= cv2.imread("opencv/image/disconnected.png")
        
        # Cố gắng kết nối với camera trong luồng khác với luồng chính của giao diện tkinter
        self.thread_open_camera = threading.Thread(target=self.open_camera)
        self.thread_open_camera.daemon = True
        self.thread_open_camera.start()

    def open_camera(self):
        self.vid = cv2.VideoCapture(self.video_source)
        self.vid.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        # self.vid.set(cv2.CAP_PROP_FPS, 15)
        
        if not self.vid.isOpened():
            logger.error('%s %s', language_system.get_text("camera.language_system"), self.video_source)
            self.camera_connected = False
        else:
            logger.info('%s %s', language_system.get_text("camera.connected_camera"), self.video_source)
            self.camera_connected = True

            self.process()
        
    # Thực hiện luồng stream
    def process(self):        
        while self.camera_connected:
            try:
                self.ret, frame = self.vid.read()

                if self.ret:
                    self.frame = cv2.resize(frame, (self.width, self.height))
                else:
                    logger.error('%s %s', language_system.get_text("camera.error_read_frame"), self.video_source)
                    self.frame = None
                    self.ret = False
                    self.count += 1

                    # Sau 4 lần thử lại mà vẫn không được thì ngắt kết nối tới camera
                    if self.count == 3 :
                        self.camera_connected = False
                        self.frame = self.disconnected_camera
                        self.ret = True
                    time.sleep(5)  # Thử lại sau 5s

            except cv2.error as e:
                logger.exception('OpenCV ERROR: %s', str(e))
                break  # Thoát vòng lặp nếu gặp ngoại lệ

            except Exception as e:
                logger.exception('Lỗi không xác định: %s', str(e))
                
                
    # Trả về frame hiện tại
    def get_frame(self):
        return self.ret, self.frame
    
    def snapshot(self):
        if not self.ret:
            print('[MyVideoCapture] no frame for snapshot')
        else:
            if not filename:
                filename = time.strftime("frame-%d-%m-%Y-%H-%M-%S.jpg")

            if not self.convert_pillow:
                cv2.imwrite(filename, self.frame)
                print('[MyVideoCapture] snapshot (using cv2):', filename)
            else:
                self.frame.save(filename)
                print('[MyVideoCapture] snapshot (using pillow):', filename)


    # Giải phóng tài nguyên khi kết thúc ghi hình, gọi hàm này để kết thúc đúng cách
    def release_camera(self):
        # Hàm này được gọi để ngăn chặn thread lấy khung hình từ camera đang chạy liên tục
        if self.camera_connected:
            self.camera_connected = False
            
        if self.vid.isOpened():
            self.vid.release()
            
        logger.info('%s %s', language_system.get_text("camera.release_camera"), self.video_source)    
            
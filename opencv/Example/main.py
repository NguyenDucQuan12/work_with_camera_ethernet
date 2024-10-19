import logging
import tkinter
import json
from language.language_manager import language_system
from log import console
from gui_camera import tkCamera

# Tạo logging 
"""
Tạo logging để lưu lại những thông tin ra với các tham số cụ thể như: thời gian, mức độ, tên file, hàm gọi, dòng code, và tin nhắn
Lưu ý có thêm tham số: force = True bởi vì xung đột giữa các trình ghi nhật ký của các thư viện hoặc file
Nếu đối số từ khóa này được chỉ định là True, mọi trình xử lý hiện có được gắn vào bộ ghi nhật ký gốc sẽ bị 
xóa và đóng trước khi thực hiện cấu hình như được chỉ định bởi các đối số khác

Đối với file main sẽ dùng: logger = logging.getLogger()
Còn các file khác sẽ dùng: logger = logging.getLogger(__name__) thì sẽ tự động cùng lưu vào 1 file, cùng 1 định dạng
"""

logger = logging.getLogger()
# Dòng dưới sẽ ngăn chặn việc có những log không mong muốn từ thư viện PILLOW
# ví dụ: 2020-12-16 15:21:30,829 - DEBUG - PngImagePlugin - STREAM b'PLTE' 41 768
logging.getLogger("PIL.PngImagePlugin").propagate = False


logging.basicConfig(filename=console.log_file_path, filemode= 'a',
                    format='%(asctime)s %(levelname)s:\t %(filename)s: %(funcName)s()-Line: %(lineno)d\t message: %(message)s',
                    datefmt='%d/%m/%Y %I:%M:%S %p', encoding = 'utf-8', force=True)

# Mức độ lưu nhật ký, DEBUG chỉ dành cho trong quá trình DEBUG, nếu không sẽ có nhiều log thừa thãi, khi chạy thật thì chỉ nên để INFO hoặc WARNING
logger.setLevel(logging.INFO)
logger.info(language_system.get_text("app.start_app"))


json_filename = "opencv/Example/config.json"

# Lấy các thông tin ban đầu để khởi tạo cho phần mềm
with open(json_filename, 'r') as inside:
    data = json.load(inside)

    cam1 = data['Camera_IP']["rtsp_cam_1"]
    cam2 = data['Camera_IP']["rtsp_cam_2"]
    cam3 = data['Camera_IP']["rtsp_cam_3"]
    cam4 = data['Camera_IP']["rtsp_cam_4"]

class App:
    def __init__(self, parent, title, sources):
        """TODO: add docstring"""

        self.parent = parent

        self.parent.title(title)

        self.stream_widgets = []

        width = 400
        height = 300

        columns = 2
        for number, (text, source) in enumerate(sources):
            widget = tkCamera(self.parent, text, source, width, height, sources)
            row = number // columns
            col = number % columns
            widget.grid(row=row, column=col)
            self.stream_widgets.append(widget)

        self.parent.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self, event=None):
        """TODO: add docstring"""

        print("[App] stoping threads")
        for widget in self.stream_widgets:
            widget.vid.running = False

        print("[App] exit")
        self.parent.destroy()

if __name__ == "__main__":

    """
    Để sử dụng ví dụ thì chỉ cần chạy file main này là được
    python path/to/main.py
    """

    sources =[  # (text, source)
        # local webcams
        ("cam1", cam1),
        # remote videos (or streams)
        (
            "cam2",cam2
        ),
        (
            "cam3", cam3
        ),
        (
            "cam4",cam4
        )
    ]

    root = tkinter.Tk()
    App(root, "Tkinter and OpenCV", sources)
    root.mainloop()

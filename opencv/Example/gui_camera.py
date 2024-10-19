import logging
import PIL.ImageTk, PIL.Image
import tkinter as tk
from language.language_manager import language_system
import cv2
from videocapture import VideoCapture
# from memory_profiler import profile

# Lấy tên file của nơi gọi hàm logger
logger = logging.getLogger(__name__)


class tkCamera(tk.Frame):

    def __init__(self, parent, text="", source=0, width=None, height=None, sources=None):
        """TODO: add docstring"""

        super().__init__(parent)

        self.source = source
        self.width  = width
        self.height = height
        self.other_sources = sources

        #self.window.title(window_title)
        self.vid = VideoCapture(self.source)

        self.label = tk.Label(self, text=text)
        self.label.pack()

        self.canvas = tk.Canvas(self, width=self.vid.width, height=self.vid.height)
        self.canvas.pack()

        # Hình ảnh mặc định cho các khung hình camera
        default_image_ = PIL.Image.open("opencv/image/disconnected.png")
        self.default_image= PIL.ImageTk.PhotoImage(default_image_)

        self.id_image = self.canvas.create_image(0, 0, image=self.default_image, anchor='nw')

        # Button that lets the user take a snapshot
        self.btn_snapshot = tk.Button(self, text="Start", command=self.start)
        self.btn_snapshot.pack(anchor='center', side='left')

        self.btn_snapshot = tk.Button(self, text="Stop", command=self.stop)
        self.btn_snapshot.pack(anchor='center', side='left')

        # Button that lets the user take a snapshot
        self.btn_snapshot = tk.Button(self, text="Snapshot", command=self.snapshot)
        self.btn_snapshot.pack(anchor='center', side='left')

        # Button that lets the user take a snapshot
        self.btn_snapshot = tk.Button(self, text="Source", command=self.select_source)
        self.btn_snapshot.pack(anchor='center', side='left')

        # After it is called once, the update method will be automatically called every delay milliseconds
        # calculate delay using `FPS`
        # self.delay = int(1000/self.vid.fps)
        self.delay = 10

        self.image = None

        self.dialog = None

        self.running = True
        self.update_frame()

    def start(self):
        """TODO: add docstring"""

        #if not self.running:
        #    self.running = True
        #    self.update_frame()
        self.vid.start_recording()

    def stop(self):
        """TODO: add docstring"""

        #if self.running:
        #   self.running = False
        self.vid.stop_recording()

    def snapshot(self):
        """TODO: add docstring"""

        # Get a frame from the video source
        #ret, frame = self.vid.get_frame()
        #if ret:
        #    cv2.imwrite(time.strftime("frame-%d-%m-%Y-%H-%M-%S.jpg"), cv2.cvtColor(self.frame, cv2.COLOR_RGB2BGR))

        # Save current frame in widget - not get new one from camera - so it can save correct image when it stoped
        #if self.image:
        #    self.image.save(time.strftime("frame-%d-%m-%Y-%H-%M-%S.jpg"))

        self.vid.snapshot()

    def update_frame(self):
        """TODO: add docstring"""

        ret, frame = self.vid.get_frame()

        if ret and frame is not None:
            self.canvas.delete(self.id_image)

            color_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            tkinter_frame = PIL.Image.fromarray(color_frame)
            self.photo = PIL.ImageTk.PhotoImage(image=tkinter_frame)
            self.id_image = self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        else:
            self.canvas.delete(self.id_image)
            self.id_image = self.canvas.create_image(0, 0, image=self.default_image, anchor='nw')
        if self.running:
            self.after(self.delay, self.update_frame)

    def select_source(self):
        """TODO: add docstring"""

        # open only one dialog
        if self.dialog:
            print('[tkCamera] dialog already open')
        else:
            print("Nothinh")


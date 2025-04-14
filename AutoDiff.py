import os
import time
import json
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from pystray import Icon, MenuItem as Item, Menu
from PIL import Image, ImageDraw
from plyer import notification

# 全局变量
observer = None
icon = None
config = {}
tray_status = "初始化中..."

CONFIG_FILE = "config.json"
COMPARE_ARGS = ["-nobdpos", "-nobdcosm", "-nofppos"]
TEMP_DIR = tempfile.gettempdir()


# ========== 配置处理 ==========
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)

def choose_lvcompare_path():
    print("请选择 LVCompare.exe 的位置")
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="选择 LabVIEW Compare 工具 (LVCompare.exe)",
        filetypes=[("LVCompare", "LVCompare.exe")]
    )
    return path

def auto_detect_lvcompare():
    possible_paths = [
        r"C:\Program Files\National Instruments\Shared\LabVIEW Compare\LVCompare.exe",
        r"C:\Program Files (x86)\National Instruments\Shared\LabVIEW Compare\LVCompare.exe"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            print(f"[自动检测] 找到 LVCompare.exe: {path}")
            return path
    return ""


# ========== 托盘功能 ==========
def create_image():
    image = Image.new('RGB', (64, 64), color='white')
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill='blue')
    return image

def show_notification():
    notification.notify(
        title='LVCompare 自动监听器已启动',
        message='正在监控临时 .vi 文件（右键托盘图标退出或更改设置）',
        app_name='AutoDiff',
        timeout=5
    )

def update_tray_title(status):
    global icon, tray_status
    tray_status = status
    if icon:
        icon.title = f"AutoDiff - {tray_status}"

def on_exit_clicked(_icon, _item):
    global icon, observer
    print("[退出] 正在关闭监听器...")
    update_tray_title("正在退出...")
    if observer:
        observer.stop()
        observer.join()
    if icon:
        icon.stop()
    os._exit(0)

def on_reselect_lvcompare(_icon, _item):
    global config
    path = choose_lvcompare_path()
    if path and os.path.exists(path):
        config["lvcompare_path"] = path
        save_config(config)
        update_tray_title("路径已更新")
        print(f"[设置更新] 已更改 LVCompare 路径为: {path}")
        notification.notify(
            title='LVCompare 路径已更新',
            message='新路径已保存并将用于后续比较',
            app_name='AutoDiff',
            timeout=3
        )
    else:
        print("[取消] 未选择任何路径")


# ========== 文件监听器 ==========
class VIFileHandler(FileSystemEventHandler):
    def __init__(self, lvcompare_path):
        self.vi_files = []
        self.last_processed = 0
        self.lvcompare_path = lvcompare_path

    def on_any_event(self, event):
        if event.is_directory or not event.src_path.endswith(".vi"):
            return
        print(f"[事件] {event.event_type} - {event.src_path}")
        if event.src_path not in self.vi_files:
            self.vi_files.append(event.src_path)
        self.check_and_compare()

    def check_and_compare(self):
        current_time = time.time()
        if current_time - self.last_processed < 3 or len(self.vi_files) < 2:
            return
        vi_file1, vi_file2 = self.vi_files[-2:]
        if vi_file1 == vi_file2:
            return
        print(f"[比较] {vi_file1} vs {vi_file2}")
        update_tray_title("比较中...")
        try:
            subprocess.run(
                [self.lvcompare_path, vi_file1, vi_file2] + COMPARE_ARGS,
                check=True)
            print("[完成] LVCompare 比较完成")
            update_tray_title("比较完成")
            self.last_processed = current_time
            self.vi_files = []
        except subprocess.CalledProcessError as e:
            print(f"[错误] 比较失败: {e}")
            update_tray_title("比较失败")


# ========== 启动监听线程 ==========
def start_monitoring(lvcompare_path):
    global observer
    handler = VIFileHandler(lvcompare_path)
    observer = Observer()
    observer.schedule(handler, TEMP_DIR, recursive=False)
    observer.start()
    show_notification()
    update_tray_title("监听中...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


# ========== 程序入口 ==========
def main():
    global icon, config
    config = load_config()
    LVCOMPARE_PATH = config.get("lvcompare_path", "")

    if not os.path.exists(LVCOMPARE_PATH):
        LVCOMPARE_PATH = auto_detect_lvcompare()

    if not os.path.exists(LVCOMPARE_PATH):
        LVCOMPARE_PATH = choose_lvcompare_path()
        if not LVCOMPARE_PATH:
            print("未选择 LVCompare.exe，程序退出")
            return
        config["lvcompare_path"] = LVCOMPARE_PATH
        save_config(config)

    # 启动监听线程
    t = threading.Thread(target=start_monitoring, args=(LVCOMPARE_PATH,), daemon=True)
    t.start()

    # 托盘菜单
    icon = Icon("AutoDiff")
    icon.icon = create_image()
    icon.title = f"AutoDiff - {tray_status}"  # 初始托盘提示
    icon.menu = Menu(
        Item('重新选择 LVCompare.exe', on_reselect_lvcompare),
        Item('退出', on_exit_clicked)
    )
    icon.run()


if __name__ == "__main__":
    main()

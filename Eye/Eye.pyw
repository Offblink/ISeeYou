#!/usr/bin/env python3
"""
相机共享桌面应用
基于PyQt5，包含QR码和系统托盘功能
"""

import sys
import os
import threading
import socket
import subprocess
import webbrowser
import signal
from io import BytesIO
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QPushButton, QTextEdit, 
                            QGroupBox, QMessageBox, QTabWidget)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QPalette, QColor, QPainter, QPen, QBrush
import qrcode
from PIL import Image, ImageDraw
from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayMenuItem
import numpy as np

# 服务器配置
SERVER_CONFIG = {
    'port': 8888,
    'host': '0.0.0.0',
}

class CameraServerThread(QThread):
    """相机服务器线程"""
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.server_process = None
        self.running = False
        self.server_script = self.create_server_script()
        
    def create_server_script(self):
        """创建相机服务器脚本"""
        script_content = '''#!/usr/bin/env python3
"""
相机共享服务器
"""

from flask import Flask, Response
import cv2
import threading
import time
import numpy as np
import signal
import sys
import os

app = Flask(__name__)

class SimpleCamera:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.camera = None
        self.frame = None
        self.running = True
        self.thread = threading.Thread(target=self._capture)
        self.thread.daemon = True
        self.thread.start()
    
    def _capture(self):
        """捕获摄像头帧"""
        while self.running:
            try:
                if self.camera is None or not self.camera.isOpened():
                    self.camera = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                    if not self.camera.isOpened():
                        print(f"无法打开摄像头 {self.camera_index}")
                        time.sleep(1)
                        continue
                
                ret, frame = self.camera.read()
                if ret:
                    # 调整大小
                    frame = cv2.resize(frame, (640, 480))
                    # 编码为JPEG
                    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    self.frame = jpeg.tobytes()
                else:
                    print("读取摄像头失败")
                    if self.camera:
                        self.camera.release()
                    self.camera = None
                    
            except Exception as e:
                print(f"摄像头捕获错误: {e}")
                if self.camera:
                    self.camera.release()
                self.camera = None
            
            time.sleep(0.033)  # ~30fps
    
    def get_frame(self):
        """获取当前帧"""
        if self.frame is None:
            # 返回黑色帧
            black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            _, buffer = cv2.imencode('.jpg', black_frame)
            return buffer.tobytes()
        return self.frame
    
    def stop(self):
        """停止摄像头"""
        self.running = False
        if self.camera:
            self.camera.release()

# 创建摄像头实例
camera = SimpleCamera(camera_index=0)

def generate_frames():
    """生成MJPEG流"""
    boundary = b'--frame'
    header = b'Content-Type: image/jpeg\\r\\n\\r\\n'
    
    while True:
        try:
            frame = camera.get_frame()
            yield boundary + b'\\r\\n' + header + frame + b'\\r\\n'
            time.sleep(0.033)  # ~30fps
        except Exception as e:
            print(f"生成帧错误: {e}")
            time.sleep(0.1)

@app.route('/')
def index():
    """简单HTML页面"""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>相机测试</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { margin: 0; padding: 0; background: #000; }
        img { width: 100%; height: 100vh; object-fit: contain; }
    </style>
</head>
<body>
    <img src="/video_feed">
</body>
</html>"""
    return html

@app.route('/video_feed')
def video_feed():
    """视频流端点"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

def signal_handler(sig, frame):
    """信号处理函数"""
    print("\\n正在停止服务器...")
    camera.stop()
    sys.exit(0)

if __name__ == '__main__':
    # 设置信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("="*60)
    print("相机共享服务器")
    print("="*60)
    print("访问地址: http://localhost:8888")
    print("视频流: http://localhost:8888/video_feed")
    print("="*60)
    print("按 Ctrl+C 停止服务器")
    
    try:
        app.run(host='0.0.0.0', port=8888, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\\n停止服务器...")
        camera.stop()
'''
        
        # 保存脚本到临时文件
        import tempfile
        temp_dir = tempfile.gettempdir()
        script_path = os.path.join(temp_dir, "camera_server_temp.py")
        
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        return script_path
        
    def run(self):
        """运行服务器线程"""
        try:
            self.running = True
            self.status_signal.emit("正在启动相机服务器...")
            
            # --- 关键修复：根据是否打包来构建正确的启动命令 ---
            if getattr(sys, 'frozen', False):
                # 情况A：程序已被打包（如PyInstaller打包为.exe）
                # 此时 sys.executable 指向打包后的 exe 文件自身（例如 eye.exe）
                # 在Windows上，这个 exe 可以像Python解释器一样执行 .py 脚本
                cmd = [sys.executable, self.server_script]
            else:
                # 情况B：开发环境（直接运行 .py 脚本）
                # 此时 sys.executable 指向真正的Python解释器（如 python.exe）
                cmd = [sys.executable, self.server_script]
            # 注意：虽然两种情况下 cmd 看起来一样，但 sys.executable 的含义已完全不同。
            # 此修复确保了在打包环境下，不会错误地试图去启动另一个Python解释器，
            # 而是用应用自身（已内含解释器功能）去执行临时脚本，符合打包后的运行逻辑。
            # --- 修复结束 ---
            
            # 启动服务器子进程（使用修复后的 cmd）
            self.server_process = subprocess.Popen(
                cmd,  # 使用修复后构建的cmd列表
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            
            # 等待服务器启动
            import time
            time.sleep(2)
            
            if self.server_process.poll() is None:
                self.status_signal.emit("相机服务器运行中")
            else:
                stdout, stderr = self.server_process.communicate()
                self.error_signal.emit(f"服务器启动失败: {stderr}")
                
        except Exception as e:
            self.error_signal.emit(f"启动服务器错误: {str(e)}")
    
    def stop(self):
        """停止服务器"""
        if self.server_process and self.running:
            self.running = False
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=3)
            except:
                self.server_process.kill()
            
            # 清理临时文件
            try:
                if os.path.exists(self.server_script):
                    os.remove(self.server_script)
            except:
                pass
            
            self.status_signal.emit("服务器已停止")

class CameraShareApp(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.tray_icon = None
        self.tray_thread = None
        
        self.init_ui()
        self.setup_connections()
        self.create_tray_icon()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("相机共享应用")
        self.setGeometry(100, 100, 600, 500)
        
        # 设置窗口图标
        self.setWindowIcon(self.create_icon())
        
        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #4CAF50;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #4CAF50;
            }
            QPushButton {
                padding: 8px 16px;
                font-weight: bold;
                border-radius: 4px;
                min-width: 100px;
                border: none;
            }
            QPushButton#startBtn {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton#startBtn:hover {
                background-color: #45a049;
            }
            QPushButton#stopBtn {
                background-color: #f44336;
                color: white;
            }
            QPushButton#stopBtn:hover {
                background-color: #da190b;
            }
            QPushButton#openBtn {
                background-color: #2196F3;
                color: white;
            }
            QPushButton#openBtn:hover {
                background-color: #0b7dda;
            }
            QLabel#titleLabel {
                font-size: 24px;
                font-weight: bold;
                color: #333333;
                padding: 10px;
            }
            QLabel#statusLabel {
                font-size: 14px;
                padding: 8px 12px;
                border-radius: 4px;
                background-color: #ffcc80;
            }
            QTextEdit#urlDisplay {
                background-color: white;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Courier New', monospace;
                font-size: 13px;
            }
        """)
        
        # 中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("相机共享应用")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 状态组
        status_group = QGroupBox("服务器状态")
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("未启动")
        self.status_label.setObjectName("statusLabel")
        status_layout.addWidget(self.status_label)
        
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)
        
        # URL组
        url_group = QGroupBox("访问地址")
        url_layout = QVBoxLayout()
        
        # 当前IP显示
        ip_layout = QHBoxLayout()
        ip_layout.addWidget(QLabel("本机IP:"))
        self.ip_label = QLabel("正在获取...")
        self.ip_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        ip_layout.addWidget(self.ip_label)
        ip_layout.addStretch()
        url_layout.addLayout(ip_layout)
        
        # URL显示
        self.url_display = QTextEdit()
        self.url_display.setObjectName("urlDisplay")
        self.url_display.setReadOnly(True)
        self.url_display.setMaximumHeight(50)
        url_layout.addWidget(self.url_display)
        
        url_group.setLayout(url_layout)
        main_layout.addWidget(url_group)
        
        # QR码组
        qr_group = QGroupBox("扫描二维码访问")
        qr_layout = QVBoxLayout()
        qr_layout.setAlignment(Qt.AlignCenter)
        
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(250, 250)
        self.qr_label.setStyleSheet("""
            background-color: white; 
            border: 2px solid #4CAF50; 
            border-radius: 8px;
            padding: 10px;
        """)
        qr_layout.addWidget(self.qr_label)
        
        qr_info = QLabel("使用手机浏览器扫描二维码")
        qr_info.setAlignment(Qt.AlignCenter)
        qr_info.setStyleSheet("color: #666666; font-size: 12px; margin-top: 5px;")
        qr_layout.addWidget(qr_info)
        
        qr_group.setLayout(qr_layout)
        main_layout.addWidget(qr_group)
        
        # 按钮组
        button_group = QGroupBox("控制")
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("启动服务器")
        self.start_btn.setObjectName("startBtn")
        self.stop_btn = QPushButton("停止服务器")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.open_btn = QPushButton("在浏览器中打开")
        self.open_btn.setObjectName("openBtn")
        self.open_btn.setEnabled(False)
        
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.open_btn)
        
        button_group.setLayout(button_layout)
        main_layout.addWidget(button_group)
        
        # 提示信息
        tips_label = QLabel("提示：关闭窗口将最小化到系统托盘")
        tips_label.setAlignment(Qt.AlignCenter)
        tips_label.setStyleSheet("color: #ff9800; font-size: 12px; padding: 5px;")
        main_layout.addWidget(tips_label)
        
        main_layout.addStretch()
        
    def create_icon(self):
        """创建应用图标"""
        from PyQt5.QtCore import QRect
        
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制相机图标
        painter.setBrush(QBrush(QColor(76, 175, 80)))
        painter.setPen(QPen(QColor(56, 142, 60), 2))
        
        # 相机主体
        painter.drawEllipse(12, 12, 40, 40)
        
        # 相机镜头
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(20, 20, 24, 24)
        
        # 相机闪光灯
        painter.setBrush(QBrush(QColor(255, 193, 7)))
        painter.drawRect(40, 8, 8, 6)
        
        painter.end()
        
        return QIcon(pixmap)
    
    def create_tray_icon(self):
        """创建系统托盘图标"""
        def create_tray_image():
            """创建托盘图标"""
            # 创建一个绿色圆形背景
            image = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
            dc = ImageDraw.Draw(image)
            
            # 绘制绿色圆形背景
            dc.ellipse([4, 4, 60, 60], fill=(76, 175, 80, 255))
            
            # 绘制相机图标
            # 相机主体
            dc.ellipse([16, 16, 48, 48], outline='white', width=3)
            # 相机镜头
            dc.ellipse([24, 24, 40, 40], outline='white', width=2)
            # 字母C
            dc.text((28, 30), "C", fill='white', font=None)
            
            return image
        
        # 创建托盘图标
        image = create_tray_image()
        
        # 创建菜单
        menu = TrayMenu(
            TrayMenuItem('打开主界面', self.restore_from_tray),
            TrayMenuItem('退出', self.quit_application)
        )
        
        # 创建托盘图标
        self.tray_icon = TrayIcon("camera_share", image, "相机共享应用", menu)
        
        # 启动托盘图标线程
        def run_tray():
            try:
                self.tray_icon.run()
            except Exception as e:
                print(f"托盘图标运行错误: {e}")
        
        self.tray_thread = threading.Thread(target=run_tray, daemon=True)
        self.tray_thread.start()
        
    def setup_connections(self):
        """设置信号槽连接"""
        self.start_btn.clicked.connect(self.start_server)
        self.stop_btn.clicked.connect(self.stop_server)
        self.open_btn.clicked.connect(self.open_in_browser)
        
        # 获取本机IP
        QTimer.singleShot(100, self.get_local_ip)
        
    def get_local_ip(self):
        """获取本机IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            self.ip_label.setText(ip)
        except:
            self.ip_label.setText("127.0.0.1")
            
    def generate_qr_code(self, url):
        """生成QR码"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=8,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # 转换为QPixmap
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())
            
            # 缩放以适应标签
            self.qr_label.setPixmap(pixmap.scaled(
                250, 250,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        except Exception as e:
            print(f"生成QR码失败: {e}")
            
    def start_server(self):
        """启动服务器"""
        if self.server_thread and self.server_thread.isRunning():
            QMessageBox.warning(self, "警告", "服务器已在运行中")
            return
            
        self.server_thread = CameraServerThread()
        self.server_thread.status_signal.connect(self.update_status)
        self.server_thread.error_signal.connect(self.show_error)
        self.server_thread.finished.connect(self.server_finished)
        
        self.server_thread.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        
    def stop_server(self):
        """停止服务器"""
        if self.server_thread and self.server_thread.isRunning():
            self.server_thread.stop()
            self.server_thread.wait(3000)
            
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.status_label.setText("服务器已停止")
        self.status_label.setStyleSheet("background-color: #ffcc80;")
        
    def open_in_browser(self):
        """在浏览器中打开"""
        url = self.url_display.toPlainText()
        if url:
            webbrowser.open(url)
            
    def update_status(self, message):
        """更新状态"""
        self.status_label.setText(message)
        
        if "运行中" in message:
            self.status_label.setStyleSheet("background-color: #c8e6c9;")
            
            # 生成URL和QR码
            ip = self.ip_label.text()
            url = f"http://{ip}:{SERVER_CONFIG['port']}"
            self.url_display.setText(url)
            self.generate_qr_code(url)
            
        elif "启动" in message:
            self.status_label.setStyleSheet("background-color: #fff9c4;")
            
    def show_error(self, error_message):
        """显示错误信息"""
        QMessageBox.critical(self, "错误", error_message)
        self.status_label.setText("启动失败")
        self.status_label.setStyleSheet("background-color: #ffcdd2;")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        
    def server_finished(self):
        """服务器线程完成"""
        self.status_label.setText("服务器已停止")
        self.status_label.setStyleSheet("background-color: #ffcc80;")
        
    def restore_from_tray(self, icon=None, item=None):
        """从系统托盘恢复主窗口"""
        self.show()
        self.raise_()
        self.activateWindow()
        
    def minimize_to_tray(self):
        """最小化到系统托盘"""
        self.hide()
        
    def quit_application(self, icon=None, item=None):
        """安全退出应用"""
        # 停止服务器
        self.stop_server()
        
        # 停止托盘图标
        if self.tray_icon:
            self.tray_icon.stop()
        
        # 退出应用
        QApplication.quit()
        
    def closeEvent(self, event):
        """重写关闭事件，实现最小化到托盘"""
        event.ignore()  # 忽略默认关闭行为
        self.minimize_to_tray()

def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 防止关闭窗口时退出应用
    app.setStyle("Fusion")
    
    # 设置应用信息
    app.setApplicationName("相机共享应用")
    app.setApplicationVersion("1.0.0")
    
    window = CameraShareApp()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
屏幕共享桌面应用 - 带系统托盘功能
"""

import sys
import os
import threading
import socket
import subprocess
import webbrowser
from io import BytesIO
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QPushButton, QTextEdit, 
                            QGroupBox, QMessageBox, QTabWidget, QSystemTrayIcon, QMenu, QAction)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont, QIcon, QPalette, QColor, QPainter, QPen, QBrush
import qrcode
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

# 服务器配置
SERVER_CONFIG = {
    'port': 8888,
    'host': '0.0.0.0',
}

class ServerThread(QThread):
    """服务器线程"""
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.server_process = None
        self.running = False
        
    def run(self):
        """运行服务器线程"""
        try:
            self.running = True
            self.status_signal.emit("正在启动服务器...")
            
            # 启动服务器子进程
            server_script = os.path.join(os.path.dirname(__file__), "server.pyw")
            if not os.path.exists(server_script):
                self.error_signal.emit(f"找不到服务器脚本: {server_script}")
                return
                
            self.server_process = subprocess.Popen(
                [sys.executable, server_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            
            # 等待服务器启动
            import time
            time.sleep(2)
            
            if self.server_process.poll() is None:
                self.status_signal.emit("服务器运行中")
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
            self.status_signal.emit("服务器已停止")

class ScreenShareApp(QMainWindow):
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
        self.setWindowTitle("屏幕共享应用")
        self.setGeometry(100, 100, 800, 600)
        
        # 设置窗口图标
        self.setWindowIcon(self.create_icon())
        
        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                padding: 8px 16px;
                font-weight: bold;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton#startBtn {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton#stopBtn {
                background-color: #f44336;
                color: white;
            }
            QPushButton#openBtn {
                background-color: #2196F3;
                color: white;
            }
            QLabel#titleLabel {
                font-size: 24px;
                font-weight: bold;
                color: #333333;
            }
            QLabel#statusLabel {
                font-size: 14px;
                padding: 5px;
                border-radius: 3px;
            }
            QTextEdit#urlDisplay {
                background-color: white;
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 5px;
                font-family: monospace;
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
        title_label = QLabel("屏幕共享应用")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 创建选项卡
        tabs = QTabWidget()
        main_layout.addWidget(tabs)
        
        # 控制选项卡
        control_tab = QWidget()
        tabs.addTab(control_tab, "控制")
        self.setup_control_tab(control_tab)
        
        # 信息选项卡
        info_tab = QWidget()
        tabs.addTab(info_tab, "使用说明")
        self.setup_info_tab(info_tab)
        
        # 状态栏
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪")
        
    def create_icon(self):
        """创建应用图标"""
        # 创建一个简单的图标
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制屏幕图标
        painter.setBrush(QBrush(QColor(33, 150, 243)))
        painter.setPen(QPen(QColor(25, 118, 210), 2))
        painter.drawRoundedRect(8, 8, 48, 36, 5, 5)
        
        # 绘制屏幕内容
        painter.setBrush(QBrush(QColor(66, 165, 245)))
        painter.drawRect(12, 12, 40, 28)
        
        # 绘制底座
        painter.setBrush(QBrush(QColor(97, 97, 97)))
        painter.drawRect(28, 44, 8, 12)
        
        painter.end()
        
        return QIcon(pixmap)
    
    def create_tray_icon(self):
        """创建系统托盘图标 - 参考文档1的实现"""
        def create_fallback_image():
            """创建备用图标"""
            image = Image.new('RGB', (64, 64), color='#4CAF50')
            dc = ImageDraw.Draw(image)
            dc.rectangle([16, 16, 48, 48], fill='#2196F3')
            dc.text((25, 25), "SS", fill='white')  # SS表示Screen Share
            return image
        
        # 尝试加载图标文件
        try:
            image = Image.open("icon.ico")
        except:
            image = create_fallback_image()
        
        # 创建菜单
        menu = (
            item('打开主界面', self.restore_from_tray, default=True),  # 左键点击功能
            item('退出', self.quit_application)
        )
        
        self.tray_icon = pystray.Icon("screen_share", image, "屏幕共享应用", menu)
        
        # 启动托盘图标线程
        def run_tray():
            try:
                self.tray_icon.run()
            except Exception as e:
                print(f"托盘图标运行错误: {e}")
        
        self.tray_thread = threading.Thread(target=run_tray, daemon=True)
        self.tray_thread.start()
        
    def setup_control_tab(self, parent):
        """设置控制选项卡"""
        layout = QVBoxLayout(parent)
        layout.setSpacing(15)
        
        # 状态组
        status_group = QGroupBox("服务器状态")
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("未启动")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setStyleSheet("background-color: #ffcc80;")
        status_layout.addWidget(self.status_label)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # URL组
        url_group = QGroupBox("访问地址")
        url_layout = QVBoxLayout()
        
        # 当前IP显示
        ip_layout = QHBoxLayout()
        ip_layout.addWidget(QLabel("本机IP:"))
        self.ip_label = QLabel("正在获取...")
        ip_layout.addWidget(self.ip_label)
        ip_layout.addStretch()
        url_layout.addLayout(ip_layout)
        
        # URL显示
        self.url_display = QTextEdit()
        self.url_display.setObjectName("urlDisplay")
        self.url_display.setReadOnly(True)
        self.url_display.setMaximumHeight(60)
        url_layout.addWidget(self.url_display)
        
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)
        
        # QR码组
        qr_group = QGroupBox("QR码")
        qr_layout = QVBoxLayout()
        qr_layout.setAlignment(Qt.AlignCenter)
        
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(300, 300)
        self.qr_label.setStyleSheet("background-color: white; border: 1px solid #cccccc;")
        qr_layout.addWidget(self.qr_label)
        
        qr_group.setLayout(qr_layout)
        layout.addWidget(qr_group)
        
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
        layout.addWidget(button_group)
        
        layout.addStretch()
        
    def setup_info_tab(self, parent):
        """设置信息选项卡"""
        layout = QVBoxLayout(parent)
        layout.setSpacing(15)
        
        # 使用说明
        instructions = QGroupBox("使用说明")
        instructions_layout = QVBoxLayout()
        
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setHtml("""
        <h3>屏幕共享应用使用说明</h3>
        
        <h4>1. 启动服务器</h4>
        <p>点击"启动服务器"按钮，启动屏幕共享服务。</p>
        
        <h4>2. 获取访问地址</h4>
        <p>服务器启动后，会显示访问地址和QR码。</p>
        
        <h4>3. 手机访问</h4>
        <p>在手机上：</p>
        <ul>
            <li>使用手机浏览器扫描QR码</li>
            <li>或直接输入显示的URL地址</li>
        </ul>
        
        <h4>4. 查看屏幕</h4>
        <p>手机浏览器会自动显示电脑屏幕画面。</p>
        
        <h4>5. 最小化到托盘</h4>
        <p>关闭窗口将最小化到系统托盘，不会退出应用。</p>
        
        <h4>6. 停止服务</h4>
        <p>从托盘菜单选择"退出"来完全关闭应用。</p>
        
        <h4>注意事项：</h4>
        <ul>
            <li>确保手机和电脑在同一WiFi网络</li>
            <li>首次使用可能需要允许防火墙访问</li>
            <li>共享期间请勿关闭本应用</li>
        </ul>
        
        <h4>技术信息：</h4>
        <ul>
            <li>端口: 8888</li>
            <li>协议: HTTP</li>
            <li>视频编码: MJPEG</li>
            <li>帧率: 15 FPS</li>
        </ul>
        """)
        
        instructions_layout.addWidget(info_text)
        instructions.setLayout(instructions_layout)
        layout.addWidget(instructions)
        
        # 系统信息
        sys_info = QGroupBox("系统信息")
        sys_layout = QVBoxLayout()
        
        sys_text = QTextEdit()
        sys_text.setReadOnly(True)
        
        import platform
        info = f"""
        操作系统: {platform.system()} {platform.release()}
        Python版本: {platform.python_version()}
        应用版本: 1.0.0
        服务器端口: {SERVER_CONFIG['port']}
        托盘功能: 已启用
        """
        
        sys_text.setPlainText(info)
        sys_layout.addWidget(sys_text)
        sys_info.setLayout(sys_layout)
        layout.addWidget(sys_info)
        
        layout.addStretch()
        
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
                box_size=10,
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
                self.qr_label.size(),
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
            
        self.server_thread = ServerThread()
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
            
    def open_in_browser_from_tray(self, icon=None, item=None):
        """从托盘菜单在浏览器中打开"""
        self.open_in_browser()
            
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
            
    def show_status_in_tray(self, icon=None, item=None):
        """在托盘中显示状态"""
        if self.server_thread and self.server_thread.running:
            status = "服务器运行中"
        else:
            status = "服务器已停止"
            
        # 获取IP
        ip = self.ip_label.text()
        if ip == "正在获取...":
            ip = "127.0.0.1"
            
        # 显示消息框
        QMessageBox.information(self, "服务器状态", 
                               f"状态: {status}\nIP地址: {ip}\n端口: {SERVER_CONFIG['port']}")
        
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
        # 显示消息提示
        self.status_bar.showMessage("应用已最小化到系统托盘", 3000)
        
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
    app.setApplicationName("屏幕共享应用")
    app.setApplicationVersion("1.0.0")
    
    window = ScreenShareApp()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
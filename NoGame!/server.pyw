#!/usr/bin/env python3
"""
屏幕共享服务器
只提供屏幕共享功能
"""

import os
import time
import json
import queue
import threading
import logging
from io import BytesIO
from flask import Flask, Response, render_template_string, jsonify
from gevent import pywsgi
from PIL import ImageGrab, Image
import socket
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__)

# 配置
CONFIG = {
    'port': 8888,
    'host': '0.0.0.0',
    'fps': 60,
    'quality': 60,
    'frame_scale': 0.5,
    'frame_queue_size': 2,
}

# 全局状态
frame_queue = queue.Queue(maxsize=CONFIG['frame_queue_size'])
is_capturing = True
screen_width, screen_height = 1920, 1080

# HTML界面
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>屏幕共享</title>
    <style>
        * { 
            margin: 0; 
            padding: 0; 
            -webkit-tap-highlight-color: transparent; 
            -webkit-touch-callout: none; 
            -webkit-user-select: none; 
            user-select: none; 
            box-sizing: border-box;
        }
        
        body, html { 
            width: 100%; 
            height: 100%; 
            overflow: hidden; 
            background: #000; 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        
        .container { 
            position: relative;
            width: 100%;
            height: 100%;
        }
        
        .video { 
            width: 100%; 
            height: 100%; 
            object-fit: contain; 
            background: #000;
        }
        
        .status { 
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 8px 12px;
            border-radius: 5px;
            font-size: 12px;
            z-index: 100;
        }
        
        .fps-counter { 
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0, 0, 0, 0.7);
            color: #4CAF50;
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 12px;
            z-index: 100;
        }
        
        .info { 
            position: absolute;
            bottom: 20px;
            left: 0;
            right: 0;
            text-align: center;
            color: rgba(255, 255, 255, 0.7);
            font-size: 12px;
            background: rgba(0, 0, 0, 0.5);
            padding: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <img class="video" src="/video" alt="屏幕共享">
        <div class="status" id="status">正在连接...</div>
        <div class="fps-counter" id="fps">FPS: 0</div>
        <div class="info">屏幕共享 - 手机浏览器查看</div>
    </div>
    
    <script>
        let fps = 0;
        let fpsCounter = 0;
        let lastFpsTime = Date.now();
        const video = document.querySelector('.video');
        const status = document.getElementById('status');
        const fpsElement = document.getElementById('fps');
        
        // 更新FPS显示
        function updateFPS() {
            const now = Date.now();
            fpsCounter++;
            
            if (now - lastFpsTime >= 1000) {
                fps = fpsCounter;
                fpsCounter = 0;
                lastFpsTime = now;
                fpsElement.textContent = `FPS: ${fps}`;
            }
        }
        
        // 视频加载成功
        video.onload = function() {
            status.textContent = '已连接';
            updateFPS();
        };
        
        // 视频加载失败
        video.onerror = function() {
            status.textContent = '连接失败，重试中...';
            // 3秒后重试
            setTimeout(() => {
                video.src = video.src.split('?')[0] + '?t=' + Date.now();
            }, 3000);
        };
        
        // 视频加载时更新FPS
        video.onload = updateFPS;
        
        // 页面加载完成
        window.addEventListener('load', function() {
            status.textContent = '正在连接...';
        });
    </script>
</body>
</html>
'''

# 屏幕捕获线程
def screen_capture_worker():
    """屏幕捕获工作线程"""
    global screen_width, screen_height
    
    while is_capturing:
        try:
            # 捕获屏幕
            screenshot = ImageGrab.grab()
            screen_width, screen_height = screenshot.size
            
            # 调整大小
            if CONFIG['frame_scale'] != 1.0:
                new_size = (int(screen_width * CONFIG['frame_scale']), 
                          int(screen_height * CONFIG['frame_scale']))
                try:
                    screenshot = screenshot.resize(new_size, Image.Resampling.LANCZOS)
                except AttributeError:
                    screenshot = screenshot.resize(new_size, Image.LANCZOS)
            
            # 转换为JPEG
            buffer = BytesIO()
            screenshot.save(buffer, format='JPEG', quality=CONFIG['quality'])
            jpeg_data = buffer.getvalue()
            
            # 放入队列
            if frame_queue.full():
                try:
                    frame_queue.get_nowait()
                except:
                    pass
            
            frame_queue.put(jpeg_data)
            
            # 控制帧率
            time.sleep(1.0 / CONFIG['fps'])
            
        except Exception as e:
            logger.error(f"屏幕捕获错误: {e}")
            time.sleep(0.1)

# 生成视频流
def generate_video_frames():
    """生成MJPEG视频流"""
    while True:
        try:
            if frame_queue.empty():
                time.sleep(0.01)
                continue
                
            frame = frame_queue.get()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + 
                   frame + b'\r\n')
        except Exception as e:
            logger.error(f"生成视频流错误: {e}")
            time.sleep(0.1)

# Flask路由
@app.route('/')
def index():
    """主页面"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/video')
def video_feed():
    """视频流端点"""
    return Response(generate_video_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/health')
def health_check():
    """健康检查端点"""
    return jsonify({'status': 'ok'})

@app.route('/screen_info')
def get_screen_info():
    """获取屏幕信息"""
    return jsonify({
        'width': screen_width,
        'height': screen_height,
        'fps': CONFIG['fps']
    })

def get_local_ip():
    """获取本机IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def start_server():
    """启动服务器"""
    global is_capturing
    
    # 获取屏幕大小
    try:
        screenshot = ImageGrab.grab()
        screen_width, screen_height = screenshot.size
    except Exception as e:
        print(f"获取屏幕大小失败: {e}")
        screen_width, screen_height = 1920, 1080
    
    # 启动屏幕捕获线程
    capture_thread = threading.Thread(target=screen_capture_worker, daemon=True)
    capture_thread.start()
    
    # 启动服务器
    try:
        server = pywsgi.WSGIServer(
            (CONFIG['host'], CONFIG['port']),
            app
        )
        
        local_ip = get_local_ip()
        
        print(f"服务器启动在: http://{local_ip}:{CONFIG['port']}")
        print(f"屏幕分辨率: {screen_width}x{screen_height}")
        print(f"帧率: {CONFIG['fps']} FPS")
        print("按 Ctrl+C 停止服务器")
        
        server.serve_forever()
        
    except KeyboardInterrupt:
        print("\n正在停止服务器...")
        is_capturing = False
        print("服务器已停止")
    except Exception as e:
        logger.error(f"服务器启动错误: {e}")
        print(f"错误: {e}")

if __name__ == '__main__':
    start_server()
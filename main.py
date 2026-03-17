import os
import sys
import requests
import yt_dlp
import imageio_ffmpeg  # 引入自带 FFmpeg 的神器库
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QGridLayout, QLabel, QLineEdit, 
                               QPushButton, QProgressBar, QTextEdit, QComboBox, QFileDialog, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage

class AnalyzeThread(QThread):
    """用于解析视频信息和获取封面的后台线程"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        ydl_opts = {
            'quiet': True,
            'no_playlist': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                
                # 获取封面图片数据
                thumbnail_data = None
                if info.get('thumbnail'):
                    try:
                        response = requests.get(info['thumbnail'], timeout=10)
                        thumbnail_data = response.content
                    except Exception:
                        pass
                
                result = {
                    'title': info.get('title', '未知标题'),
                    'uploader': info.get('uploader', '未知UP主'),
                    'duration': info.get('duration_string', '未知时长'),
                    'thumbnail_data': thumbnail_data,
                    'webpage_url': info.get('webpage_url', self.url)
                }
                self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class DownloadThread(QThread):
    """用于下载视频的后台线程"""
    progress_update = Signal(int, str)  # 进度百分比, 速度文本
    log_update = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, url, save_path, resolution_height):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.resolution_height = resolution_height

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int(downloaded / total * 100)
            else:
                percent = 0
            
            speed = d.get('_speed_str', 'N/A')
            self.progress_update.emit(percent, speed)
            
        elif d['status'] == 'finished':
            self.log_update.emit("下载完成，正在合并音视频（请耐心等待）...")

    def run(self):
        # 自动获取 imageio_ffmpeg 自带的 ffmpeg.exe 路径，免除用户配置！
        ffmpeg_exe_path = imageio_ffmpeg.get_ffmpeg_exe()

        # 根据选择的分辨率构建 format 字符串
        if self.resolution_height == 'best':
            format_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        else:
            format_str = f'bestvideo[height<={self.resolution_height}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

        ydl_opts = {
            'format': format_str,
            'outtmpl': os.path.join(self.save_path, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'quiet': True,
            'progress_hooks': [self.progress_hook],
            # 将内置的 FFmpeg 路径直接交给 yt-dlp
            'ffmpeg_location': ffmpeg_exe_path,
            'ignore_no_formats_error': True,
            'no_playlist': True,
        }

        try:
            self.log_update.emit(f"开始下载: {self.url}\n请求画质: <= {self.resolution_height}p")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            self.finished.emit("视频下载并处理成功！")
        except Exception as e:
            self.error.emit(str(e))

class BilibiliDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pybi_Dow")
        self.resize(700, 500)
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ================= 1. 链接与解析区 =================
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入B站视频链接 或 BV号 或 av号...")
        self.analyze_btn = QPushButton("解析视频")
        self.analyze_btn.clicked.connect(self.start_analyze)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.analyze_btn)
        main_layout.addLayout(url_layout)

        # ================= 2. 预览区 =================
        preview_layout = QHBoxLayout()
        
        # 封面图
        self.thumbnail_label = QLabel("封面预览区")
        self.thumbnail_label.setFixedSize(320, 180)
        self.thumbnail_label.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setScaledContents(True)
        preview_layout.addWidget(self.thumbnail_label)

        # 视频信息
        info_layout = QVBoxLayout()
        self.title_label = QLabel("标题: 等待解析...")
        self.title_label.setWordWrap(True)
        self.up_label = QLabel("UP主: -")
        self.duration_label = QLabel("时长: -")
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.up_label)
        info_layout.addWidget(self.duration_label)
        info_layout.addStretch()
        preview_layout.addLayout(info_layout)
        
        main_layout.addLayout(preview_layout)

        # ================= 3. 下载设置区 =================
        settings_layout = QGridLayout()
        
        # 分辨率
        settings_layout.addWidget(QLabel("下载画质:"), 0, 0)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1080", "720", "480", "360", "best"])
        self.resolution_combo.setItemText(0, "1080p (高清)")
        self.resolution_combo.setItemText(1, "720p")
        self.resolution_combo.setItemText(2, "480p")
        self.resolution_combo.setItemText(3, "360p")
        self.resolution_combo.setItemText(4, "最高可用画质 (Best)")
        settings_layout.addWidget(self.resolution_combo, 0, 1)

        # 保存目录
        settings_layout.addWidget(QLabel("保存目录:"), 1, 0)
        save_layout = QHBoxLayout()
        self.save_input = QLineEdit()
        self.save_input.setText(os.path.expanduser("~/Downloads"))
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self.browse_folder)
        save_layout.addWidget(self.save_input)
        save_layout.addWidget(self.browse_btn)
        settings_layout.addLayout(save_layout, 1, 1)

        main_layout.addLayout(settings_layout)

        # ================= 4. 进度与控制区 =================
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        main_layout.addWidget(self.log_output)

        self.download_btn = QPushButton("开始下载")
        self.download_btn.setFixedHeight(40)
        self.download_btn.setStyleSheet("background-color: #fb7299; color: white; font-weight: bold; font-size: 14px; border-radius: 5px;")
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setEnabled(False) # 解析完成后才允许下载
        main_layout.addWidget(self.download_btn)

        self.current_video_url = ""

    def log(self, text):
        self.log_output.append(text)
        self.log_output.ensureCursorVisible()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if folder:
            self.save_input.setText(folder)

    def format_url(self, raw_url):
        url = raw_url.strip()
        if not url.startswith('http'):
            if url.startswith('BV') or url.startswith('av'):
                url = f'https://www.bilibili.com/video/{url}'
        return url

    # --- 解析部分 ---
    def start_analyze(self):
        raw_url = self.url_input.text()
        if not raw_url:
            QMessageBox.warning(self, "错误", "请输入视频链接！")
            return

        self.current_video_url = self.format_url(raw_url)
        self.analyze_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.log("正在解析视频信息，请稍候...")

        self.analyze_thread = AnalyzeThread(self.current_video_url)
        self.analyze_thread.finished.connect(self.on_analyze_finished)
        self.analyze_thread.error.connect(self.on_analyze_error)
        self.analyze_thread.start()

    def on_analyze_finished(self, info):
        self.title_label.setText(f"标题: {info['title']}")
        self.up_label.setText(f"UP主: {info['uploader']}")
        self.duration_label.setText(f"时长: {info['duration']}")
        
        # 加载封面图
        if info['thumbnail_data']:
            image = QImage.fromData(info['thumbnail_data'])
            pixmap = QPixmap.fromImage(image)
            self.thumbnail_label.setPixmap(pixmap)
        else:
            self.thumbnail_label.setText("无法获取封面")

        self.log(f"解析成功！已准备好下载: {info['title']}")
        self.analyze_btn.setEnabled(True)
        self.download_btn.setEnabled(True)

    def on_analyze_error(self, err):
        self.log(f"解析失败: {err}")
        QMessageBox.critical(self, "解析失败", f"无法解析该链接:\n{err}")
        self.analyze_btn.setEnabled(True)

    # --- 下载部分 ---
    def start_download(self):
        save_path = self.save_input.text().strip()
        if not os.path.exists(save_path):
            QMessageBox.warning(self, "错误", "保存目录不存在，请重新选择！")
            return

        # 获取选择的分辨率实际值
        res_data =["1080", "720", "480", "360", "best"]
        selected_res = res_data[self.resolution_combo.currentIndex()]

        self.analyze_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        
        # 不再传递 ffmpeg_path，线程内部自动解决
        self.download_thread = DownloadThread(self.current_video_url, save_path, selected_res)
        self.download_thread.progress_update.connect(self.on_download_progress)
        self.download_thread.log_update.connect(self.log)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.error.connect(self.on_download_error)
        self.download_thread.start()

    def on_download_progress(self, percent, speed):
        self.progress_bar.setValue(percent)
        self.setWindowTitle(f"B站视频下载器 - 下载中... {percent}% (速度: {speed})")

    def on_download_finished(self, msg):
        self.log(msg)
        self.progress_bar.setValue(100)
        self.setWindowTitle("B站视频下载器 (免配置增强版)")
        QMessageBox.information(self, "下载完成", "视频下载并合并成功！")
        self.analyze_btn.setEnabled(True)
        self.download_btn.setEnabled(True)

    def on_download_error(self, err):
        self.log(f"下载失败: {err}")
        self.setWindowTitle("B站视频下载器 (免配置增强版)")
        QMessageBox.critical(self, "下载失败", f"下载过程中出错:\n{err}")
        self.analyze_btn.setEnabled(True)
        self.download_btn.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置应用全局字体（可选）
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    window = BilibiliDownloaderGUI()
    window.show()
    sys.exit(app.exec())
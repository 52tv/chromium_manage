#!/usr/bin/env python3
"""
Chromium 多实例管理器
优化版本，包含更好的错误处理、类型提示、性能优化等
"""

import sys
import os
import yaml
import psutil
import subprocess
import shutil
import webbrowser
import requests
import platform
import zipfile
import tarfile
import threading
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                            QLabel, QLineEdit, QMessageBox, QDialog, QFormLayout,
                            QComboBox, QCheckBox, QHeaderView, QStyle, QStyleOptionButton,
                            QGroupBox, QProgressBar, QTextEdit, QGridLayout, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal

# 常量定义
class Constants:
    # 网络超时设置
    IP_INFO_TIMEOUT = 5
    VERSION_FETCH_TIMEOUT = 10
    
    # 更新间隔
    PROCESS_STATUS_UPDATE_INTERVAL = 3000  # 3秒，降低频率
    
    # 下载设置
    DOWNLOAD_CHUNK_SIZE = 8192
    
    # 默认路径
    DEFAULT_WINDOWS_DATA_DIR = os.path.join("C:", "temp", "chromium")
    DEFAULT_MACOS_DATA_DIR = "/tmp/chromium"
    
    # GitHub API
    GITHUB_RELEASES_URL = "https://api.github.com/repos/adryfish/fingerprint-chromium/releases"
    
    # IP信息API
    IP_INFO_URL = "http://iprust.io/ip.json"
    
    # 指纹验证网站
    FINGERPRINT_SITES = [
        ("Bot Sannysoft", "https://bot.sannysoft.com/"),
        ("Browser Leaks", "https://browserleaks.com/"),
        ("AmIUnique", "https://amiunique.org/"),
        ("CreepJS", "https://abrahamjuliot.github.io/creepjs/")
    ]

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DownloadThread(QThread):
    """下载线程，支持进度报告"""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, url: str, filepath: str):
        super().__init__()
        self.url = url
        self.filepath = filepath
        self._is_cancelled = False
        
    def cancel(self):
        """取消下载"""
        self._is_cancelled = True
        
    def run(self):
        """执行下载"""
        try:
            self.status.emit("开始下载...")
            logger.info(f"开始下载: {self.url}")
            
            response = requests.get(self.url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(self.filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=Constants.DOWNLOAD_CHUNK_SIZE):
                    if self._is_cancelled:
                        f.close()
                        if os.path.exists(self.filepath):
                            os.remove(self.filepath)
                        self.finished.emit(False, "下载已取消")
                        return
                        
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress.emit(progress)
                            self.status.emit(f"下载中... {progress}%")
            
            self.status.emit("下载完成")
            logger.info(f"下载完成: {self.filepath}")
            self.finished.emit(True, "")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"网络错误: {e}")
            self.finished.emit(False, f"网络错误: {str(e)}")
        except IOError as e:
            logger.error(f"文件写入错误: {e}")
            self.finished.emit(False, f"文件写入错误: {str(e)}")
        except Exception as e:
            logger.error(f"下载失败: {e}")
            self.finished.emit(False, f"未知错误: {str(e)}")

class FileExtractor:
    """文件解压器"""
    
    @staticmethod
    def extract_zip(filepath: str, extract_dir: str, version_tag: str, platform_dir: str, parent) -> bool:
        """解压ZIP文件"""
        try:
            tmp_extract_dir = os.path.join(extract_dir, f"tmp_extract_{version_tag}")
            
            # 清理并创建临时目录
            if os.path.exists(tmp_extract_dir):
                shutil.rmtree(tmp_extract_dir)
            os.makedirs(tmp_extract_dir, exist_ok=True)
            
            # 解压文件
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(tmp_extract_dir)
            
            # 移动到目标版本目录
            version_dir = os.path.join(platform_dir, version_tag)
            if os.path.exists(version_dir):
                shutil.rmtree(version_dir)
            os.makedirs(version_dir, exist_ok=True)
            
            # 复制文件
            for item in os.listdir(tmp_extract_dir):
                s = os.path.join(tmp_extract_dir, item)
                d = os.path.join(version_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
            
            # 清理临时目录
            shutil.rmtree(tmp_extract_dir)
            
            # 查找chrome.exe
            chrome_paths = [
                os.path.join(version_dir, 'chrome.exe'),
                os.path.join(version_dir, 'Chromium', 'chrome.exe'),
                os.path.join(version_dir, 'chrome-win', 'chrome.exe')
            ]
            
            for path in chrome_paths:
                if os.path.exists(path):
                    parent.update_version_config(version_tag, path)
                    logger.info(f"Chrome可执行文件找到: {path}")
                    return True
                    
            logger.error("未找到chrome.exe")
            return False
            
        except Exception as e:
            logger.error(f"ZIP解压失败: {e}")
            return False
    
    @staticmethod
    def extract_dmg(filepath: str, version_tag: str, platform_dir: str, parent) -> bool:
        """解压DMG文件"""
        try:
            version_dir = os.path.join(platform_dir, version_tag)
            os.makedirs(version_dir, exist_ok=True)
            
            mount_point = f"/tmp/chromium_dmg_{version_tag.replace('.', '_')}"
            os.makedirs(mount_point, exist_ok=True)
            
            try:
                # 挂载DMG文件
                mount_cmd = ['hdiutil', 'attach', filepath, '-mountpoint', mount_point, '-readonly']
                result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode != 0:
                    logger.error(f"DMG挂载失败: {result.stderr}")
                    return False
                
                # 查找Chromium.app
                chromium_app_path = None
                for root, dirs, files in os.walk(mount_point):
                    if 'Chromium.app' in dirs:
                        chromium_app_path = os.path.join(root, 'Chromium.app')
                        break
                
                if not chromium_app_path:
                    logger.error("在DMG中未找到Chromium.app")
                    return False
                
                # 复制Chromium.app
                target_path = os.path.join(version_dir, 'Chromium.app')
                if os.path.exists(target_path):
                    shutil.rmtree(target_path)
                
                shutil.copytree(chromium_app_path, target_path)
                
                # 更新版本配置
                chromium_exe_path = os.path.join(target_path, 'Contents', 'MacOS', 'Chromium')
                if os.path.exists(chromium_exe_path):
                    parent.update_version_config(version_tag, chromium_exe_path)
                    logger.info(f"Chromium可执行文件找到: {chromium_exe_path}")
                    return True
                
                return False
                
            finally:
                # 卸载DMG文件
                try:
                    subprocess.run(['hdiutil', 'detach', mount_point], 
                                 capture_output=True, timeout=30)
                except subprocess.TimeoutExpired:
                    logger.warning("DMG卸载超时")
                
        except Exception as e:
            logger.error(f"DMG解压失败: {e}")
            return False

class DownloadDialog(QDialog):
    """下载对话框"""
    
    def __init__(self, parent=None, version_info: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("下载 Chromium")
        self.version_info = version_info
        self.download_thread: Optional[DownloadThread] = None
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        
        # 版本信息
        if self.version_info:
            info_text = (
                f"版本: {self.version_info['tag_name']}\n"
                f"发布日期: {self.version_info['published_at']}\n"
                f"文件大小: {self.version_info['size']} MB"
            )
            info_label = QLabel(info_text)
            layout.addWidget(info_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # 状态文本
        self.status_label = QLabel("准备下载...")
        layout.addWidget(self.status_label)
        
        # 日志输出
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(100)
        layout.addWidget(self.log_text)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.download_btn = QPushButton("开始下载")
        self.cancel_btn = QPushButton("取消")
        
        self.download_btn.clicked.connect(self.start_download)
        self.cancel_btn.clicked.connect(self.cancel_download)
        
        button_layout.addWidget(self.download_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def start_download(self):
        """开始下载"""
        if not self.version_info:
            return
            
        self.download_btn.setEnabled(False)
        self.download_thread = DownloadThread(
            self.version_info['download_url'], 
            self.version_info['filepath']
        )
        self.download_thread.progress.connect(self.progress_bar.setValue)
        self.download_thread.status.connect(self.status_label.setText)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.start()
    
    def cancel_download(self):
        """取消下载"""
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.download_thread.wait()
        self.reject()
        
    def download_finished(self, success: bool, error_msg: str):
        """下载完成处理"""
        if success:
            self.log_text.append("下载完成，正在解压...")
            self.extract_file()
        else:
            self.log_text.append(f"下载失败: {error_msg}")
            self.download_btn.setEnabled(True)
            
    def extract_file(self):
        """解压文件"""
        if not self.version_info:
            return
            
        try:
            filepath = self.version_info['filepath']
            download_dir = os.path.dirname(filepath)
            version_tag = self.version_info['tag_name']
            
            success = False
            if filepath.endswith('.zip'):
                success = FileExtractor.extract_zip(
                    filepath, download_dir, version_tag, 
                    self.parent().platform_dir, self.parent()
                )
                if success:
                    self.log_text.append("✅ ZIP文件处理完成！")
            elif filepath.endswith('.dmg'):
                success = FileExtractor.extract_dmg(
                    filepath, version_tag, 
                    self.parent().platform_dir, self.parent()
                )
                if success:
                    self.log_text.append("✅ DMG文件处理完成！")
            else:
                self.log_text.append(f"❌ 不支持的文件格式: {filepath}")
                return
            
            if success:
                # 删除下载的压缩文件
                try:
                    os.remove(filepath)
                    self.log_text.append("临时文件已清理")
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {e}")
                
                self.accept()
            else:
                self.log_text.append("❌ 文件处理失败")
                self.download_btn.setEnabled(True)
                
        except Exception as e:
            logger.error(f"解压文件失败: {e}")
            self.log_text.append(f"❌ 处理文件失败: {str(e)}")
            self.download_btn.setEnabled(True)

class CheckBoxHeader(QHeaderView):
    """支持全选的表头"""
    
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.isChecked = False
        self.setSectionsClickable(True)
        self.sectionClicked.connect(self.on_section_clicked)

    def on_section_clicked(self, logical_index: int):
        """处理表头点击"""
        if logical_index == 0:  # 只处理第一列（复选框列）
            self.isChecked = not self.isChecked
            # 通知表格更新所有复选框状态
            if self.parent():
                self.parent().update_all_checkboxes(self.isChecked)
            self.viewport().update()

    def paintSection(self, painter, rect, logical_index: int):
        """绘制表头"""
        super().paintSection(painter, rect, logical_index)
        if logical_index == 0:  # 只在第一列绘制复选框
            option = QStyleOptionButton()
            option.rect = rect
            option.state = QStyle.StateFlag.State_Enabled
            if self.isChecked:
                option.state |= QStyle.StateFlag.State_On
            else:
                option.state |= QStyle.StateFlag.State_Off
            QApplication.style().drawControl(QStyle.ControlElement.CE_CheckBox, option, painter)

class InstanceUtils:
    """实例工具类，减少重复代码"""
    
    @staticmethod
    def get_next_number(instances: List[Dict], field: str, prefix: str = "", start: int = 1) -> int:
        """获取下一个可用的数字"""
        existing_numbers = []
        for inst in instances:
            value = inst.get(field, "")
            if isinstance(value, str) and value.startswith(prefix):
                try:
                    num = int(value[len(prefix):])
                    existing_numbers.append(num)
                except ValueError:
                    continue
            elif isinstance(value, int):
                existing_numbers.append(value)
        return max(existing_numbers, default=start - 1) + 1
    
    @staticmethod
    def get_next_data_dir_number(instances: List[Dict], is_windows: bool) -> int:
        """获取下一个数据目录编号"""
        existing_dirs = []
        base_path = Constants.DEFAULT_WINDOWS_DATA_DIR if is_windows else Constants.DEFAULT_MACOS_DATA_DIR
        
        for inst in instances:
            dir_path = inst.get('user_data_dir', '')
            if f"{base_path}/default" in dir_path:
                try:
                    num = int(dir_path.split('default')[-1])
                    existing_dirs.append(num)
                except ValueError:
                    continue
        return max(existing_dirs, default=0) + 1
    
    @staticmethod
    def get_default_instance_values(instances: List[Dict], ip_info: Dict, is_windows: bool) -> Dict:
        """获取默认实例配置"""
        instance_num = InstanceUtils.get_next_number(instances, 'name', 'Instance ')
        data_dir_num = InstanceUtils.get_next_data_dir_number(instances, is_windows)
        fingerprint_num = InstanceUtils.get_next_number(instances, 'fingerprint', '', 1000)
        
        timezone = ip_info.get('timezone', 'Asia/Shanghai')
        
        # 根据系统设置默认用户数据目录
        if is_windows:
            user_data_dir = os.path.join(Constants.DEFAULT_WINDOWS_DATA_DIR, f"default{data_dir_num:03d}")
        else:
            user_data_dir = f"{Constants.DEFAULT_MACOS_DATA_DIR}/default{data_dir_num:03d}"
        
        return {
            "name": f"Instance {instance_num}",
            "fingerprint": str(fingerprint_num),
            "user_data_dir": user_data_dir,
            "timezone": timezone,
            "proxy_server": "",
            "chromium_version": "default",
            "resolution": "跟随系统",
            "font_fingerprint": "跟随系统",
            "webrtc": "禁止",
            "webgl_image": "随机",
            "webgl_info": "自定义",
            "canvas": "随机",
            "audiocontext": "随机",
            "speech_voices": "随机",
            "do_not_track": "开启",
            "client_rects": "随机",
            "media_devices": "随机",
            "device_name": "随机",
            "mac_address": "自定义",
            "hardware_concurrency": 12,
            "device_memory": 8,
            "ssl_fingerprint": "关闭",
            "speaker_protection": "开启"
        }

class AddInstanceDialog(QDialog):
    """添加/编辑实例对话框"""
    
    def __init__(self, parent, default_values: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("添加新实例")
        self.setModal(True)
        self.parent = parent
        self.default_values = default_values or self._get_default_values()
        self.setup_ui()

    def _get_default_values(self) -> Dict:
        """获取默认配置值"""
        if not self.parent or not hasattr(self.parent, 'config'):
            return InstanceUtils.get_default_instance_values([], {}, False)
        
        return InstanceUtils.get_default_instance_values(
            self.parent.config.get('instances', []),
            getattr(self.parent, 'ip_info', {}),
            getattr(self.parent, 'is_windows', False)
        )

    def setup_ui(self):
        layout = QVBoxLayout()
        # 基础参数分组
        base_group = QGroupBox("基础参数")
        base_form = QFormLayout()
        self.name_edit = QLineEdit(self.default_values["name"])
        self.fingerprint_edit = QLineEdit(self.default_values["fingerprint"])
        self.user_data_dir_edit = QLineEdit(self.default_values["user_data_dir"])
        self.timezone_edit = QLineEdit(self.default_values["timezone"])
        self.proxy_server_edit = QLineEdit(self.default_values["proxy_server"])
        
        # 版本选择
        self.version_combo = QComboBox()
        # self.version_combo.addItem("默认版本")
        if self.parent and hasattr(self.parent, 'available_versions'):
            for version in self.parent.available_versions:
                self.version_combo.addItem(version['tag_name'])
        
        base_form.addRow("名称:", self.name_edit)
        base_form.addRow("Fingerprint:", self.fingerprint_edit)
        base_form.addRow("用户数据目录:", self.user_data_dir_edit)
        base_form.addRow("时区:", self.timezone_edit)
        base_form.addRow("代理服务器:", self.proxy_server_edit)
        base_form.addRow("Chromium版本:", self.version_combo)
        base_group.setLayout(base_form)
        layout.addWidget(base_group)
        
        # 环境参数分组
        env_group = QGroupBox("环境参数")
        env_group.setCheckable(True)
        env_group.setChecked(False)  # 默认折叠
        env_grid = QGridLayout()
        # 左列参数
        env_grid.addWidget(QLabel("分辨率:"), 0, 0)
        self.resolution_edit = QLineEdit(self.default_values["resolution"])
        env_grid.addWidget(self.resolution_edit, 0, 1)
        env_grid.addWidget(QLabel("WebRTC:"), 1, 0)
        self.webrtc_combo = QComboBox(); self.webrtc_combo.addItems(["禁止", "允许"]); self.webrtc_combo.setCurrentText(self.default_values["webrtc"])
        env_grid.addWidget(self.webrtc_combo, 1, 1)
        env_grid.addWidget(QLabel("WebGL Info:"), 2, 0)
        self.webgl_info_combo = QComboBox(); self.webgl_info_combo.addItems(["自定义", "随机"]); self.webgl_info_combo.setCurrentText(self.default_values["webgl_info"])
        env_grid.addWidget(self.webgl_info_combo, 2, 1)
        env_grid.addWidget(QLabel("AudioContext:"), 3, 0)
        self.audiocontext_combo = QComboBox(); self.audiocontext_combo.addItems(["随机", "自定义"]); self.audiocontext_combo.setCurrentText(self.default_values["audiocontext"])
        env_grid.addWidget(self.audiocontext_combo, 3, 1)
        env_grid.addWidget(QLabel("Do Not Track:"), 4, 0)
        self.do_not_track_combo = QComboBox(); self.do_not_track_combo.addItems(["开启", "关闭"]); self.do_not_track_combo.setCurrentText(self.default_values["do_not_track"])
        env_grid.addWidget(self.do_not_track_combo, 4, 1)
        env_grid.addWidget(QLabel("媒体设备:"), 5, 0)
        self.media_devices_combo = QComboBox(); self.media_devices_combo.addItems(["随机", "自定义"]); self.media_devices_combo.setCurrentText(self.default_values["media_devices"])
        env_grid.addWidget(self.media_devices_combo, 5, 1)
        env_grid.addWidget(QLabel("MAC地址:"), 6, 0)
        self.mac_address_edit = QLineEdit(self.default_values["mac_address"])
        env_grid.addWidget(self.mac_address_edit, 6, 1)
        env_grid.addWidget(QLabel("设备内存(G):"), 7, 0)
        self.device_memory_edit = QLineEdit(str(self.default_values["device_memory"]))
        env_grid.addWidget(self.device_memory_edit, 7, 1)
        env_grid.addWidget(QLabel("喇叭扫描保护:"), 8, 0)
        self.speaker_protection_combo = QComboBox(); self.speaker_protection_combo.addItems(["开启", "关闭"]); self.speaker_protection_combo.setCurrentText(self.default_values["speaker_protection"])
        env_grid.addWidget(self.speaker_protection_combo, 8, 1)
        # 右列参数
        env_grid.addWidget(QLabel("字体指纹:"), 0, 2)
        self.font_fingerprint_edit = QLineEdit(self.default_values["font_fingerprint"])
        env_grid.addWidget(self.font_fingerprint_edit, 0, 3)
        env_grid.addWidget(QLabel("WebGL 图像:"), 1, 2)
        self.webgl_image_combo = QComboBox(); self.webgl_image_combo.addItems(["随机", "自定义"]); self.webgl_image_combo.setCurrentText(self.default_values["webgl_image"])
        env_grid.addWidget(self.webgl_image_combo, 1, 3)
        env_grid.addWidget(QLabel("Canvas:"), 2, 2)
        self.canvas_combo = QComboBox(); self.canvas_combo.addItems(["随机", "自定义"]); self.canvas_combo.setCurrentText(self.default_values["canvas"])
        env_grid.addWidget(self.canvas_combo, 2, 3)
        env_grid.addWidget(QLabel("Speech Voices:"), 3, 2)
        self.speech_voices_combo = QComboBox(); self.speech_voices_combo.addItems(["随机", "自定义"]); self.speech_voices_combo.setCurrentText(self.default_values["speech_voices"])
        env_grid.addWidget(self.speech_voices_combo, 3, 3)
        env_grid.addWidget(QLabel("Client Rects:"), 4, 2)
        self.client_rects_combo = QComboBox(); self.client_rects_combo.addItems(["随机", "自定义"]); self.client_rects_combo.setCurrentText(self.default_values["client_rects"])
        env_grid.addWidget(self.client_rects_combo, 4, 3)
        env_grid.addWidget(QLabel("设备名称:"), 5, 2)
        self.device_name_edit = QLineEdit(self.default_values["device_name"])
        env_grid.addWidget(self.device_name_edit, 5, 3)
        env_grid.addWidget(QLabel("硬件并发数:"), 6, 2)
        self.hardware_concurrency_edit = QLineEdit(str(self.default_values["hardware_concurrency"]))
        env_grid.addWidget(self.hardware_concurrency_edit, 6, 3)
        env_grid.addWidget(QLabel("SSL指纹设置:"), 7, 2)
        self.ssl_fingerprint_combo = QComboBox(); self.ssl_fingerprint_combo.addItems(["关闭", "开启"]); self.ssl_fingerprint_combo.setCurrentText(self.default_values["ssl_fingerprint"])
        env_grid.addWidget(self.ssl_fingerprint_combo, 7, 3)
        # 设置layout
        env_group.setLayout(env_grid)
        layout.addWidget(env_group)
        
        # 按钮
        buttons = QHBoxLayout()
        save_btn = QPushButton("保存")
        cancel_btn = QPushButton("取消")
        save_btn.clicked.connect(self.validate_and_accept)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def validate_and_accept(self):
        # 必填项校验
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "名称不能为空！")
            return
        if not self.fingerprint_edit.text().strip():
            QMessageBox.warning(self, "提示", "Fingerprint 不能为空！")
            return
        if not self.user_data_dir_edit.text().strip():
            QMessageBox.warning(self, "提示", "用户数据目录不能为空！")
            return
        # 数字校验
        try:
            int(self.hardware_concurrency_edit.text())
            int(self.device_memory_edit.text())
        except ValueError:
            QMessageBox.warning(self, "提示", "硬件并发数和设备内存必须为数字！")
            return
        # 新增：判断所选版本是否已下载
        version = self.version_combo.currentText()
        if not self.parent.has_version(version):
            reply = QMessageBox.question(self, "版本未下载", f"所选版本 {version} 尚未下载，是否立即下载？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                # 查找版本信息
                version_info = None
                for v in self.parent.available_versions:
                    if v['tag_name'] == version:
                        version_info = v
                        break
                if version_info:
                    ok = self.parent.download_version(version_info)
                    if not ok:
                        QMessageBox.warning(self, "提示", "下载失败，无法添加实例！")
                        return
                else:
                    QMessageBox.warning(self, "提示", "未找到该版本的下载信息！")
                    return
            else:
                return  # 用户取消
        self.accept()

    def get_instance_data(self):
        return {
            "name": self.name_edit.text(),
            "fingerprint": self.fingerprint_edit.text(),
            "user_data_dir": self.user_data_dir_edit.text(),
            "timezone": self.timezone_edit.text(),
            "proxy_server": self.proxy_server_edit.text(),
            "chromium_version": self.version_combo.currentText(),
            "resolution": self.resolution_edit.text(),
            "font_fingerprint": self.font_fingerprint_edit.text(),
            "webrtc": self.webrtc_combo.currentText(),
            "webgl_image": self.webgl_image_combo.currentText(),
            "webgl_info": self.webgl_info_combo.currentText(),
            "canvas": self.canvas_combo.currentText(),
            "audiocontext": self.audiocontext_combo.currentText(),
            "speech_voices": self.speech_voices_combo.currentText(),
            "do_not_track": self.do_not_track_combo.currentText(),
            "client_rects": self.client_rects_combo.currentText(),
            "media_devices": self.media_devices_combo.currentText(),
            "device_name": self.device_name_edit.text(),
            "mac_address": self.mac_address_edit.text(),
            "hardware_concurrency": int(self.hardware_concurrency_edit.text()),
            "device_memory": int(self.device_memory_edit.text()),
            "ssl_fingerprint": self.ssl_fingerprint_combo.currentText(),
            "speaker_protection": self.speaker_protection_combo.currentText()
        }

class VerifyFingerprintDialog(QDialog):
    """指纹验证对话框"""
    
    def __init__(self, parent=None, instance: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("验证指纹")
        self.instance = instance
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        
        # 添加说明文本
        info_label = QLabel(
            "请选择要访问的指纹检测网站，点击后将在选中的实例中打开。\n"
            "建议同时打开多个网站进行对比验证。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 添加网站选择下拉框
        self.site_combo = QComboBox()
        for name, url in Constants.FINGERPRINT_SITES:
            self.site_combo.addItem(f"{name} ({url})")
        layout.addWidget(self.site_combo)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        open_btn = QPushButton("打开网站")
        cancel_btn = QPushButton("关闭")
        
        open_btn.clicked.connect(self.open_website)
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(open_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)

    def open_website(self):
        """打开验证网站"""
        if not self.instance:
            QMessageBox.warning(self, "警告", "未选择实例")
            return
            
        if self.instance['name'] not in self.parent().running_instances:
            QMessageBox.warning(self, "警告", "请先启动该实例")
            return
            
        try:
            # 获取选中的网站URL
            site_text = self.site_combo.currentText()
            site_url = site_text.split("(")[1].rstrip(")")
            
            # 根据版本获取 Chromium 路径
            chromium_path = self.parent().get_chromium_path(
                self.instance.get('chromium_version', 'default')
            )
            
            if not chromium_path:
                QMessageBox.critical(self, "错误", "未找到Chromium可执行文件")
                return
            
            # 构建启动命令
            cmd = [chromium_path]
            cmd.extend([f"--fingerprint={self.instance['fingerprint']}"])
            cmd.extend([f"--user-data-dir={self.instance['user_data_dir']}"])
            cmd.extend([f"--timezone={self.instance['timezone']}"])
            if self.instance.get('proxy_server'):
                cmd.extend([f"--proxy-server={self.instance['proxy_server']}"])
            cmd.append(site_url)
            
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"打开验证网站: {site_url}")
            
        except Exception as e:
            logger.error(f"打开网站失败: {e}")
            QMessageBox.critical(self, "错误", f"打开网站失败: {str(e)}")

class ChromiumManager(QMainWindow):
    """Chromium多实例管理器主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chromium 多实例管理器 v2.0")
        self.setMinimumSize(1000, 700)
        
        # 初始化路径
        self._init_paths()
        
        # 初始化数据
        self.running_instances: Dict[str, int] = {}
        self.checkbox_states: Dict[str, bool] = {}
        self.config: Dict = {'instances': []}
        self.available_versions: List[Dict] = []
        
        # 检测操作系统
        self.system = platform.system().lower()
        self.is_windows = self.system == 'windows'
        self.is_macos = self.system == 'darwin'
        
        # 异步初始化
        self._init_async_data()
        
        # 加载配置和设置UI
        self.load_config()
        self.fetch_available_versions()
        self.setup_ui()
        
        # 设置定时器更新进程状态
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_process_status)
        self.timer.start(Constants.PROCESS_STATUS_UPDATE_INTERVAL)
        
        logger.info("ChromiumManager 初始化完成")
    
    def _init_paths(self):
        """初始化路径"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(script_dir, "config.yaml")
        self.app_dir = os.path.join(script_dir, "App")
        self.download_dir = os.path.join(script_dir, "DownLoad")
        self.platform_dir = os.path.join(
            self.app_dir, 
            "win_x64" if platform.system().lower() == 'windows' else "macos"
        )
        
        # 确保目录存在
        for directory in [self.app_dir, self.download_dir, self.platform_dir]:
            os.makedirs(directory, exist_ok=True)
    
    def _init_async_data(self):
        """异步初始化数据"""
        self.ip_info = self.fetch_ip_info()

    def fetch_ip_info(self) -> Dict:
        """获取IP信息"""
        try:
            logger.info("正在获取IP信息...")
            resp = requests.get(Constants.IP_INFO_URL, timeout=Constants.IP_INFO_TIMEOUT)
            if resp.status_code == 200:
                ip_info = resp.json()
                logger.info(f"IP信息获取成功: {ip_info.get('ip', 'Unknown')}")
                return ip_info
        except requests.exceptions.RequestException as e:
            logger.warning(f"网络错误，无法获取IP信息: {e}")
        except Exception as e:
            logger.error(f"获取IP信息失败: {e}")
        return {}

    def fetch_available_versions(self):
        """从 GitHub 获取可用的 Chromium 版本"""
        try:
            logger.info("正在获取可用版本...")
            response = requests.get(Constants.GITHUB_RELEASES_URL, timeout=Constants.VERSION_FETCH_TIMEOUT)
            response.raise_for_status()
            
            releases = response.json()
            self.available_versions = []
            
            for release in releases:
                for asset in release['assets']:
                    asset_name = asset['name'].lower()
                    # 根据系统筛选合适的文件
                    if ((self.is_windows and 'windows' in asset_name and asset_name.endswith('.zip')) or
                        (self.is_macos and 'macos' in asset_name and asset_name.endswith('.dmg'))):
                        
                        self.available_versions.append({
                            'tag_name': release['tag_name'],
                            'name': asset['name'],
                            'download_url': asset['browser_download_url'],
                            'size': round(asset['size'] / (1024 * 1024), 1),  # MB
                            'published_at': release['published_at'][:10],
                            'filepath': os.path.join(self.download_dir, asset['name'])
                        })
            
            # 按发布日期排序，最新的在前面
            self.available_versions.sort(key=lambda x: x['published_at'], reverse=True)
            
            logger.info(f"找到 {len(self.available_versions)} 个可用版本")
            for version in self.available_versions:
                logger.debug(f"- {version['tag_name']}: {version['name']}")
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"网络错误，无法获取版本信息: {e}")
        except Exception as e:
            logger.error(f"获取版本信息失败: {e}")
            import traceback
            traceback.print_exc()

    def get_chromium_path(self, version: str = "default") -> Optional[str]:
        """根据版本获取 Chromium 可执行文件路径"""
        # 首先从配置文件中查找
        if (self.config.get('versions', {}).get(version, {}).get('path')):
            config_path = self.config['versions'][version]['path']
            if os.path.exists(config_path):
                return config_path
        
        # 如果配置文件中没有或路径不存在，则动态查找
        version_dir = os.path.join(self.platform_dir, version)
        if not os.path.exists(version_dir):
            return None
            
        # 根据平台查找可执行文件
        if self.is_windows:
            possible_paths = [
                os.path.join(version_dir, 'chrome.exe'),
                os.path.join(version_dir, 'Chromium', 'chrome.exe'),
                os.path.join(version_dir, 'chrome-win', 'chrome.exe')
            ]
        else:  # macOS
            possible_paths = [
                os.path.join(version_dir, 'Chromium.app', 'Contents', 'MacOS', 'Chromium'),
                os.path.join(version_dir, 'Chromium', 'Contents', 'MacOS', 'Chromium')
            ]
            
        for path in possible_paths:
            if os.path.exists(path):
                # 更新配置文件
                self.update_version_config(version, path)
                return path
                
        logger.warning(f"未找到版本 {version} 的可执行文件")
        return None

    def download_version(self, version_info: Dict) -> bool:
        """下载指定版本的 Chromium"""
        dialog = DownloadDialog(self, version_info)
        if dialog.exec():
            # 下载完成后刷新版本列表
            self.fetch_available_versions()
            return True
        return False

    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = yaml.safe_load(f)
                    if loaded_config:
                        self.config = loaded_config
            
            # 确保配置结构完整
            if 'instances' not in self.config:
                self.config['instances'] = []
            if 'versions' not in self.config:
                self.config['versions'] = {}
                
            # 配置兼容性：补全每个实例缺失字段
            if self.config['instances']:
                default_fields = InstanceUtils.get_default_instance_values([], {}, self.is_windows)
                for inst in self.config['instances']:
                    for k, v in default_fields.items():
                        if k not in inst:
                            inst[k] = v
            
            logger.info(f"配置加载成功，共有 {len(self.config['instances'])} 个实例")
            
        except yaml.YAMLError as e:
            logger.error(f"配置文件格式错误: {e}")
            self._create_default_config()
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            self._create_default_config()

    def _create_default_config(self):
        """创建默认配置"""
        self.config = {
            "versions": {},
            "instances": []
        }
        self.save_config()

    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            logger.debug("配置文件保存成功")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            QMessageBox.critical(self, "错误", f"保存配置失败: {str(e)}")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()
        # 顶部 IP 信息
        ip_label = QLabel(self.format_ip_info())
        ip_label.setWordWrap(True)
        left_layout.addWidget(ip_label)
        # 按钮区域
        button_layout = QHBoxLayout()
        add_btn = QPushButton("添加实例")
        edit_btn = QPushButton("编辑实例")
        delete_btn = QPushButton("删除实例")
        verify_btn = QPushButton("验证指纹")
        batch_start_btn = QPushButton("批量启动")
        batch_stop_btn = QPushButton("批量停止")
        download_btn = QPushButton("下载版本")
        
        add_btn.clicked.connect(self.add_instance)
        edit_btn.clicked.connect(self.edit_instance)
        delete_btn.clicked.connect(self.delete_instance)
        verify_btn.clicked.connect(self.verify_fingerprint)
        batch_start_btn.clicked.connect(self.batch_start_instances)
        batch_stop_btn.clicked.connect(self.batch_stop_instances)
        download_btn.clicked.connect(self.show_download_dialog)
        
        button_layout.addWidget(add_btn)
        button_layout.addWidget(edit_btn)
        button_layout.addWidget(delete_btn)
        button_layout.addWidget(verify_btn)
        button_layout.addWidget(batch_start_btn)
        button_layout.addWidget(batch_stop_btn)
        button_layout.addWidget(download_btn)
        left_layout.addLayout(button_layout)

        # 实例列表
        self.table = QTableWidget()
        self.table.setColumnCount(8)  # 增加一列显示版本
        self.table.setHorizontalHeaderLabels(["选择", "名称", "Fingerprint", "用户数据目录", "时区", "代理服务器", "版本", "状态"])
        
        # 设置表头
        header = CheckBoxHeader(Qt.Orientation.Horizontal, self.table)
        self.table.setHorizontalHeader(header)
        self.table.update_all_checkboxes = self.update_all_checkboxes  # 修正
        
        # 设置列宽
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        for i in range(1, self.table.columnCount()):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        
        left_layout.addWidget(self.table)

        # 启动/停止按钮
        control_layout = QHBoxLayout()
        start_btn = QPushButton("启动选中实例")
        stop_btn = QPushButton("停止选中实例")
        
        start_btn.clicked.connect(self.start_selected_instance)
        stop_btn.clicked.connect(self.stop_selected_instance)
        
        control_layout.addWidget(start_btn)
        control_layout.addWidget(stop_btn)
        left_layout.addLayout(control_layout)

        # 环境参数区
        self.env_label = QLabel()
        self.env_label.setWordWrap(True)
        right_layout.addWidget(QLabel("环境参数（当前选中实例）"))
        right_layout.addWidget(self.env_label)
        right_layout.addStretch()
        main_layout.addLayout(left_layout, 4)
        main_layout.addLayout(right_layout, 2)
        self.update_table()

    def show_download_dialog(self):
        """显示版本下载对话框"""
        if not self.available_versions:
            QMessageBox.warning(self, "警告", "无法获取版本信息，请检查网络连接")
            return
        
        # 创建版本选择对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("选择要下载的版本")
        dialog.setModal(True)
        
        layout = QVBoxLayout()
        
        # 版本列表
        version_list = QListWidget()
        
        for version in self.available_versions:
            item_text = f"{version['tag_name']} - {version['published_at']} ({version['size']}MB)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, version)
            version_list.addItem(item)
        
        layout.addWidget(QLabel("可用的 Chromium 版本:"))
        layout.addWidget(version_list)
        
        # 按钮
        button_layout = QHBoxLayout()
        download_btn = QPushButton("下载选中版本")
        cancel_btn = QPushButton("取消")
        
        download_btn.clicked.connect(lambda: self.download_selected_version(version_list, dialog))
        cancel_btn.clicked.connect(dialog.reject)
        
        button_layout.addWidget(download_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec()

    def download_selected_version(self, version_list, dialog):
        """下载选中的版本"""
        current_item = version_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "警告", "请先选择一个版本")
            return
        
        version_info = current_item.data(Qt.ItemDataRole.UserRole)
        
        # 检查是否已经下载
        if os.path.exists(version_info['filepath']):
            reply = QMessageBox.question(
                self, "确认", 
                f"版本 {version_info['tag_name']} 已存在，是否重新下载？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        dialog.accept()
        self.download_version(version_info)

    def format_ip_info(self):
        info = self.ip_info
        if not info:
            return "IP/地理信息获取失败"
        return f"IP: {info.get('ip', '')}\n国家: {info.get('country_long', '')}\n城市: {info.get('city', '')}\n时区: {info.get('timezone', '')}"

    def update_table(self):
        # 保存当前复选框状态
        self.save_checkbox_states()
        self.table.setRowCount(len(self.config['instances']))
        for i, instance in enumerate(self.config['instances']):
            # 添加复选框
            checkbox = QCheckBox()
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            
            # 恢复复选框状态
            if instance['name'] in self.checkbox_states:
                checkbox.setChecked(self.checkbox_states[instance['name']])
            
            self.table.setCellWidget(i, 0, checkbox_widget)
            
            # 添加其他列
            self.table.setItem(i, 1, QTableWidgetItem(instance['name']))
            self.table.setItem(i, 2, QTableWidgetItem(instance['fingerprint']))
            self.table.setItem(i, 3, QTableWidgetItem(instance['user_data_dir']))
            self.table.setItem(i, 4, QTableWidgetItem(instance['timezone']))
            self.table.setItem(i, 5, QTableWidgetItem(instance['proxy_server']))
            self.table.setItem(i, 6, QTableWidgetItem(instance.get('chromium_version', '默认版本')))
            status = "运行中" if instance['name'] in self.running_instances else "已停止"
            self.table.setItem(i, 7, QTableWidgetItem(status))

        # 更新环境参数区
        self.update_env_info()
        # 强制保存配置，确保界面和文件同步
        self.save_config()

    def save_checkbox_states(self):
        # 保存所有复选框的当前状态
        for i in range(self.table.rowCount()):
            checkbox_widget = self.table.cellWidget(i, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox:
                    instance_name = self.table.item(i, 1).text()
                    self.checkbox_states[instance_name] = checkbox.isChecked()

    def update_all_checkboxes(self, checked):
        # 更新所有复选框状态并保存
        for i in range(self.table.rowCount()):
            checkbox_widget = self.table.cellWidget(i, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox:
                    checkbox.setChecked(checked)
                    instance_name = self.table.item(i, 1).text()
                    self.checkbox_states[instance_name] = checked

    def get_selected_instances(self):
        selected = []
        for i in range(self.table.rowCount()):
            checkbox_widget = self.table.cellWidget(i, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    selected.append(self.config['instances'][i])
        return selected

    def add_instance(self):
        """添加新实例"""
        # 获取最后一个实例的配置作为默认值
        default_values = None
        if self.config['instances']:
            last_instance = self.config['instances'][-1].copy()
            # 使用工具类生成新的默认值
            default_values = InstanceUtils.get_default_instance_values(
                self.config['instances'], self.ip_info, self.is_windows
            )
            # 保留上一个实例的一些设置
            for key in ['timezone', 'proxy_server', 'chromium_version', 'resolution', 
                       'font_fingerprint', 'webrtc', 'webgl_image', 'webgl_info', 
                       'canvas', 'audiocontext', 'speech_voices', 'do_not_track', 
                       'client_rects', 'media_devices', 'device_name', 'mac_address',
                       'hardware_concurrency', 'device_memory', 'ssl_fingerprint',
                       'speaker_protection']:
                if key in last_instance:
                    default_values[key] = last_instance[key]
        
        dialog = AddInstanceDialog(self, default_values)
        if dialog.exec():
            instance_data = dialog.get_instance_data()
            self.config['instances'].append(instance_data)
            self.save_config()
            self.update_table()
            logger.info(f"添加新实例: {instance_data['name']}")

    def edit_instance(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "警告", "请先选择一个实例")
            return

        instance = self.config['instances'][current_row]
        dialog = AddInstanceDialog(self, instance)  # 使用当前实例的配置作为默认值

        if dialog.exec():
            instance_data = dialog.get_instance_data()
            self.config['instances'][current_row] = instance_data
            self.save_config()
            self.update_table()

    def delete_instance(self):
        selected = self.get_selected_instances()
        if not selected:
            QMessageBox.warning(self, "警告", "请先选择要删除的实例")
            return
        # 检查是否有选中的实例正在运行
        running_selected = [inst for inst in selected if inst['name'] in self.running_instances]
        if running_selected:
            QMessageBox.warning(self, "警告", "请先停止以下实例：\n" + "\n".join(inst['name'] for inst in running_selected))
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected)} 个实例吗？\n这将同时删除它们的用户数据目录。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # 从后往前删除，避免索引变化
            for instance in sorted(selected, key=lambda x: self.config['instances'].index(x), reverse=True):
                # 删除用户数据目录
                user_data_dir = instance['user_data_dir']
                if os.path.exists(user_data_dir):
                    try:
                        shutil.rmtree(user_data_dir)
                    except Exception as e:
                        QMessageBox.warning(self, "警告", f"删除用户数据目录失败：{str(e)}")
                        continue
                # 从配置中删除实例
                self.config['instances'].remove(instance)
            self.update_table()
            QMessageBox.information(self, "成功", f"已成功删除 {len(selected)} 个实例")

    def start_selected_instance(self):
        selected = self.get_selected_instances()
        if not selected:
            QMessageBox.warning(self, "警告", "请先选择要启动的实例")
            return

        if len(selected) > 1:
            self.batch_start_instances()
        else:
            instance = selected[0]
            if instance['name'] in self.running_instances:
                QMessageBox.warning(self, "警告", "该实例已经在运行中")
                return
            self.start_instance(instance)

    def stop_selected_instance(self):
        selected = self.get_selected_instances()
        if not selected:
            QMessageBox.warning(self, "警告", "请先选择要停止的实例")
            return

        if len(selected) > 1:
            self.batch_stop_instances()
        else:
            instance = selected[0]
            if instance['name'] not in self.running_instances:
                QMessageBox.warning(self, "警告", "该实例未在运行")
                return
            self.stop_instance(instance)

    def start_instance(self, instance: Dict):
        """启动单个实例"""
        instance_name = instance['name']
        
        # 检查是否已经在运行
        if instance_name in self.running_instances:
            QMessageBox.warning(self, "警告", f"实例 {instance_name} 已经在运行中")
            return
        
        # 获取Chromium路径
        chromium_path = self.get_chromium_path(instance.get('chromium_version', 'default'))
        if not chromium_path:
            QMessageBox.critical(self, "错误", f"找不到 Chromium 可执行文件")
            return

        # 构建启动命令
        cmd = self._build_chromium_command(chromium_path, instance)
        
        try:
            logger.info(f"启动实例: {instance_name}")
            logger.debug(f"启动命令: {' '.join(cmd)}")
            
            # 启动进程
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.running_instances[instance_name] = process.pid
            self.update_table()
            
            # 异步检查启动错误
            self._check_process_errors(process, instance_name)
            
            logger.info(f"实例 {instance_name} 启动成功，PID: {process.pid}")

        except FileNotFoundError:
            QMessageBox.critical(self, "错误", f"Chromium 可执行文件不存在: {chromium_path}")
        except PermissionError:
            QMessageBox.critical(self, "错误", f"没有执行权限: {chromium_path}")
        except Exception as e:
            logger.error(f"启动实例失败: {e}")
            QMessageBox.critical(self, "错误", f"启动失败: {str(e)}")
    
    def _build_chromium_command(self, chromium_path: str, instance: Dict) -> List[str]:
        """构建Chromium启动命令"""
        cmd = [chromium_path]
        cmd.extend([f"--fingerprint={instance['fingerprint']}"])
        cmd.extend([f"--user-data-dir={instance['user_data_dir']}"])
        cmd.extend([f"--timezone={instance['timezone']}"])
        
        if instance.get('proxy_server'):
            cmd.extend([f"--proxy-server={instance['proxy_server']}"])
        
        # 添加其他启动参数
        cmd.extend([
            "--no-first-run",
            "--disable-default-apps",
            "--disable-background-mode"
        ])
        
        return cmd
    
    def _check_process_errors(self, process: subprocess.Popen, instance_name: str):
        """异步检查进程错误"""
        def read_errors():
            try:
                errors = process.stderr.read()
                if errors and errors.strip():
                    logger.warning(f"实例 {instance_name} 启动警告: {errors}")
                    # 只在有严重错误时才弹窗
                    if "FATAL" in errors or "ERROR" in errors:
                        QTimer.singleShot(0, lambda: QMessageBox.warning(
                            self, "启动警告", f"实例 {instance_name} 启动时出现错误:\n{errors[:500]}..."
                        ))
            except Exception as e:
                logger.error(f"读取进程错误信息失败: {e}")
        
        threading.Thread(target=read_errors, daemon=True).start()

    def stop_instance(self, instance: Dict):
        """停止单个实例"""
        instance_name = instance['name']
        
        if instance_name not in self.running_instances:
            QMessageBox.warning(self, "警告", f"实例 {instance_name} 未在运行")
            return
        
        try:
            pid = self.running_instances[instance_name]
            process = psutil.Process(pid)
            
            logger.info(f"正在停止实例: {instance_name} (PID: {pid})")
            
            # 优雅关闭
            process.terminate()
            
            # 等待进程结束
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                logger.warning(f"实例 {instance_name} 未能优雅关闭，强制终止")
                process.kill()
                process.wait(timeout=2)
            
            del self.running_instances[instance_name]
            self.update_table()
            logger.info(f"实例 {instance_name} 已停止")
            
        except psutil.NoSuchProcess:
            logger.warning(f"进程不存在，清理实例状态: {instance_name}")
            del self.running_instances[instance_name]
            self.update_table()
        except psutil.AccessDenied:
            QMessageBox.critical(self, "错误", f"没有权限停止实例 {instance_name}")
        except Exception as e:
            logger.error(f"停止实例失败: {e}")
            QMessageBox.critical(self, "错误", f"停止失败: {str(e)}")

    def batch_start_instances(self):
        """批量启动实例"""
        selected = self.get_selected_instances()
        if not selected:
            QMessageBox.warning(self, "警告", "请先选择要启动的实例")
            return

        success_count = 0
        failed_instances = []
        
        for instance in selected:
            if instance['name'] not in self.running_instances:
                try:
                    self.start_instance(instance)
                    success_count += 1
                except Exception as e:
                    failed_instances.append(f"{instance['name']}: {str(e)}")
                    logger.error(f"批量启动失败 {instance['name']}: {e}")
        
        # 显示结果
        if failed_instances:
            QMessageBox.warning(
                self, "批量启动结果", 
                f"成功启动 {success_count} 个实例\n失败的实例:\n" + "\n".join(failed_instances)
            )
        else:
            QMessageBox.information(self, "成功", f"成功启动 {success_count} 个实例")

    def batch_stop_instances(self):
        """批量停止实例"""
        selected = self.get_selected_instances()
        if not selected:
            QMessageBox.warning(self, "警告", "请先选择要停止的实例")
            return

        success_count = 0
        failed_instances = []
        
        for instance in selected:
            if instance['name'] in self.running_instances:
                try:
                    self.stop_instance(instance)
                    success_count += 1
                except Exception as e:
                    failed_instances.append(f"{instance['name']}: {str(e)}")
                    logger.error(f"批量停止失败 {instance['name']}: {e}")
        
        # 显示结果
        if failed_instances:
            QMessageBox.warning(
                self, "批量停止结果", 
                f"成功停止 {success_count} 个实例\n失败的实例:\n" + "\n".join(failed_instances)
            )
        else:
            QMessageBox.information(self, "成功", f"成功停止 {success_count} 个实例")

    def update_process_status(self):
        """更新进程状态"""
        try:
            # 检查所有运行中的进程是否还存在
            dead_instances = []
            for name, pid in list(self.running_instances.items()):
                try:
                    process = psutil.Process(pid)
                    if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                        dead_instances.append(name)
                except psutil.NoSuchProcess:
                    dead_instances.append(name)
                except psutil.AccessDenied:
                    # 进程存在但无法访问，保持状态
                    continue
                except Exception as e:
                    logger.warning(f"检查进程状态失败 {name}: {e}")
                    continue
            
            # 清理已死亡的进程
            for name in dead_instances:
                del self.running_instances[name]
                logger.debug(f"清理已停止的实例: {name}")
            
            # 只有在有变化时才更新表格
            if dead_instances:
                self.update_table()
                
        except Exception as e:
            logger.error(f"更新进程状态失败: {e}")

    def verify_fingerprint(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "警告", "请先选择一个实例")
            return

        instance = self.config['instances'][current_row]
        if instance['name'] not in self.running_instances:
            QMessageBox.warning(self, "警告", "请先启动该实例")
            return

        dialog = VerifyFingerprintDialog(self, instance)
        dialog.exec()

    def update_env_info(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.config['instances']):
            self.env_label.setText("未选中实例")
            return
        inst = self.config['instances'][row]
        # 这里可根据你的需求扩展更多参数
        env_text = (
            f"语言: 基于 IP 匹配\n"
            f"时区: {inst.get('timezone', '')}\n"
            f"分辨率: {inst.get('resolution', '')}\n"
            f"字体指纹: {inst.get('font_fingerprint', '')}\n"
            f"WebRTC: {inst.get('webrtc', '')}\n"
            f"WebGL 图像: {inst.get('webgl_image', '')}\n"
            f"WebGL Info: {inst.get('webgl_info', '')}\n"
            f"Canvas: {inst.get('canvas', '')}\n"
            f"AudioContext: {inst.get('audiocontext', '')}\n"
            f"Speech Voices: {inst.get('speech_voices', '')}\n"
            f"Do Not Track: {inst.get('do_not_track', '')}\n"
            f"Client Rects: {inst.get('client_rects', '')}\n"
            f"媒体设备: {inst.get('media_devices', '')}\n"
            f"设备名称: {inst.get('device_name', '')}\n"
            f"MAC地址: {inst.get('mac_address', '')}\n"
            f"硬件并发数: {inst.get('hardware_concurrency', '')}核\n"
            f"设备内存: {inst.get('device_memory', '')}G\n"
            f"SSL指纹设置: {inst.get('ssl_fingerprint', '')}\n"
            f"喇叭扫描保护: {inst.get('speaker_protection', '')}\n"
        )
        self.env_label.setText(env_text)
        # ... existing code ...
        # 记得在表格选中行变化时调用 self.update_env_info()
        self.table.currentCellChanged.connect(lambda *_: self.update_env_info())

    def closeEvent(self, event):
        """关闭应用时的清理工作"""
        logger.info("正在关闭应用...")
        
        # 停止定时器
        if hasattr(self, 'timer'):
            self.timer.stop()
        
        # 停止所有运行的实例
        if self.running_instances:
            logger.info(f"正在停止 {len(self.running_instances)} 个运行中的实例...")
            for name, pid in list(self.running_instances.items()):
                try:
                    process = psutil.Process(pid)
                    process.terminate()
                    # 给进程一些时间优雅关闭
                    try:
                        process.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        process.kill()
                    logger.debug(f"实例 {name} 已停止")
                except psutil.NoSuchProcess:
                    pass
                except Exception as e:
                    logger.warning(f"停止实例 {name} 时出错: {e}")
        
        # 保存配置
        self.save_config()
        
        logger.info("应用已关闭")
        event.accept()

    def update_version_config(self, version: str, path: str):
        """更新版本配置"""
        if 'versions' not in self.config:
            self.config['versions'] = {}
        
        self.config['versions'][version] = {
            'path': path,
            'type': 'downloaded',
            'description': f'下载版本 {version}',
            'last_updated': os.path.getmtime(path) if os.path.exists(path) else 0
        }
        self.save_config()
        logger.info(f"版本配置已更新: {version} -> {path}")

    def has_version(self, version: str) -> bool:
        """判断某个版本是否已下载（可用）"""
        # 首先检查配置中的路径
        version_config = self.config.get('versions', {}).get(version, {})
        if version_config.get('path') and os.path.exists(version_config['path']):
            return True
        
        # 动态查找版本目录
        version_dir = os.path.join(self.platform_dir, version)
        if not os.path.exists(version_dir):
            return False
        
        # 根据平台查找可执行文件
        if self.is_windows:
            possible_paths = [
                os.path.join(version_dir, 'chrome.exe'),
                os.path.join(version_dir, 'Chromium', 'chrome.exe'),
                os.path.join(version_dir, 'chrome-win', 'chrome.exe')
            ]
        else:
            possible_paths = [
                os.path.join(version_dir, 'Chromium.app', 'Contents', 'MacOS', 'Chromium'),
                os.path.join(version_dir, 'Chromium', 'Contents', 'MacOS', 'Chromium')
            ]
        
        for path in possible_paths:
            if os.path.exists(path):
                # 更新配置
                self.update_version_config(version, path)
                return True
        
        return False

def main():
    app = QApplication(sys.argv)
    window = ChromiumManager()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 
#!/usr/bin/env python3
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
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                            QLabel, QLineEdit, QMessageBox, QDialog, QFormLayout,
                            QComboBox, QCheckBox, QHeaderView, QStyle, QStyleOptionButton,
                            QGroupBox, QProgressBar, QTextEdit, QGridLayout)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal

class DownloadThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, url, filepath):
        super().__init__()
        self.url = url
        self.filepath = filepath
        
    def run(self):
        try:
            self.status.emit("开始下载...")
            response = requests.get(self.url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(self.filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress.emit(progress)
                            self.status.emit(f"下载中... {progress}%")
            
            self.status.emit("下载完成")
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))

class DownloadDialog(QDialog):
    def __init__(self, parent=None, version_info=None):
        super().__init__(parent)
        self.setWindowTitle("下载 Chromium")
        self.version_info = version_info
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # 版本信息
        if self.version_info:
            info_text = f"版本: {self.version_info['tag_name']}\n"
            info_text += f"发布日期: {self.version_info['published_at']}\n"
            info_text += f"文件大小: {self.version_info['size']} MB"
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
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.download_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def start_download(self):
        self.download_btn.setEnabled(False)
        self.download_thread = DownloadThread(self.version_info['download_url'], self.version_info['filepath'])
        self.download_thread.progress.connect(self.progress_bar.setValue)
        self.download_thread.status.connect(self.status_label.setText)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.start()
        
    def download_finished(self, success, error_msg):
        if success:
            self.log_text.append("下载完成，正在解压...")
            self.extract_file()
        else:
            self.log_text.append(f"下载失败: {error_msg}")
            self.download_btn.setEnabled(True)
            
    def extract_file(self):
        try:
            filepath = self.version_info['filepath']
            download_dir = os.path.dirname(filepath)
            
            if filepath.endswith('.zip'):
                # Windows ZIP 文件处理
                version_tag = self.version_info['tag_name']
                version_dir = os.path.join(self.parent().platform_dir, version_tag)
                tmp_extract_dir = os.path.join(download_dir, f"tmp_extract_{version_tag}")

                # 解压到临时目录
                if os.path.exists(tmp_extract_dir):
                    shutil.rmtree(tmp_extract_dir)
                os.makedirs(tmp_extract_dir, exist_ok=True)
                with zipfile.ZipFile(filepath, 'r') as zip_ref:
                    zip_ref.extractall(tmp_extract_dir)
                os.remove(filepath)
                self.log_text.append("解压完成！")

                # 移动到目标版本目录
                if os.path.exists(version_dir):
                    shutil.rmtree(version_dir)
                os.makedirs(version_dir, exist_ok=True)

                # 修正：拷贝整个临时解压目录下的所有内容到目标版本目录
                for item in os.listdir(tmp_extract_dir):
                    s = os.path.join(tmp_extract_dir, item)
                    d = os.path.join(version_dir, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)

                shutil.rmtree(tmp_extract_dir)

                # 检查 chrome.exe 是否存在
                possible_paths = [
                    os.path.join(version_dir, 'chrome.exe'),
                    os.path.join(version_dir, 'Chromium', 'chrome.exe'),
                    os.path.join(version_dir, 'chrome-win', 'chrome.exe')
                ]
                found = False
                for path in possible_paths:
                    if os.path.exists(path):
                        self.parent().update_version_config(version_tag, path)
                        self.log_text.append(f"版本配置已更新: {version_tag}")
                        found = True
                        break
                if not found:
                    self.log_text.append("❌ 未找到 chrome.exe")
                    return
                
            elif filepath.endswith('.dmg'):
                # macOS DMG 文件处理
                self.log_text.append("检测到 DMG 文件，正在处理...")
                
                # 获取版本信息
                version_tag = self.version_info['tag_name']
                version_dir = os.path.join(self.parent().platform_dir, version_tag)
                
                # 创建版本目录
                os.makedirs(version_dir, exist_ok=True)
                
                # 挂载 DMG 文件
                mount_point = f"/tmp/chromium_dmg_{version_tag.replace('.', '_')}"
                os.makedirs(mount_point, exist_ok=True)
                
                try:
                    # 挂载 DMG 文件
                    self.log_text.append("正在挂载 DMG 文件...")
                    mount_cmd = ['hdiutil', 'attach', filepath, '-mountpoint', mount_point, '-readonly']
                    result = subprocess.run(mount_cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        self.log_text.append("DMG 文件挂载成功")
                        
                        # 查找 Chromium.app
                        chromium_app_path = None
                        for root, dirs, files in os.walk(mount_point):
                            if 'Chromium.app' in dirs:
                                chromium_app_path = os.path.join(root, 'Chromium.app')
                                break
                        
                        if chromium_app_path:
                            # 复制 Chromium.app 到版本目录
                            target_path = os.path.join(version_dir, 'Chromium.app')
                            self.log_text.append(f"正在复制 Chromium.app 到 {target_path}...")
                            
                            if os.path.exists(target_path):
                                shutil.rmtree(target_path)
                            
                            shutil.copytree(chromium_app_path, target_path)
                            self.log_text.append("复制完成！")
                            
                            # 更新版本配置
                            chromium_exe_path = os.path.join(target_path, 'Contents', 'MacOS', 'Chromium')
                            if os.path.exists(chromium_exe_path):
                                self.parent().update_version_config(version_tag, chromium_exe_path)
                                self.log_text.append(f"版本配置已更新: {version_tag}")
                            
                            # 卸载 DMG 文件
                            self.log_text.append("正在卸载 DMG 文件...")
                            unmount_cmd = ['hdiutil', 'detach', mount_point]
                            subprocess.run(unmount_cmd, capture_output=True)
                            
                            # 删除 DMG 文件
                            os.remove(filepath)
                            self.log_text.append("DMG 文件已删除")
                            
                        else:
                            self.log_text.append("❌ 在 DMG 文件中未找到 Chromium.app")
                            # 卸载 DMG 文件
                            subprocess.run(['hdiutil', 'detach', mount_point], capture_output=True)
                            return
                            
                    else:
                        self.log_text.append(f"❌ DMG 文件挂载失败: {result.stderr}")
                        return
                        
                except Exception as e:
                    self.log_text.append(f"❌ 处理 DMG 文件时出错: {str(e)}")
                    # 尝试卸载
                    try:
                        subprocess.run(['hdiutil', 'detach', mount_point], capture_output=True)
                    except:
                        pass
                    return
                    
            else:
                self.log_text.append(f"不支持的文件格式: {filepath}")
                return
            
            self.log_text.append("✅ 处理完成！")
            self.accept()
            
        except Exception as e:
            self.log_text.append(f"处理文件失败: {str(e)}")
            self.download_btn.setEnabled(True)

class CheckBoxHeader(QHeaderView):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.isChecked = False
        self.setSectionsClickable(True)
        self.sectionClicked.connect(self.on_section_clicked)

    def on_section_clicked(self, logical_index):
        if logical_index == 0:  # 只处理第一列（复选框列）
            self.isChecked = not self.isChecked
            # 通知表格更新所有复选框状态
            if self.parent():
                self.parent().update_all_checkboxes(self.isChecked)
            self.viewport().update()

    def paintSection(self, painter, rect, logical_index):
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

class AddInstanceDialog(QDialog):
    def __init__(self, parent, default_values=None):
        super().__init__(parent)
        self.setWindowTitle("添加新实例")
        self.setModal(True)
        self.parent = parent
        self.default_values = default_values or self._get_default_values()
        self.setup_ui()

    def _get_default_values(self):
        instance_num = self._get_next_instance_number(self.parent)
        data_dir_num = self._get_next_data_dir_number(self.parent)
        fingerprint_num = self._get_next_fingerprint_number(self.parent)
        timezone = "Asia/Shanghai"
        if self.parent and hasattr(self.parent, 'ip_info') and self.parent.ip_info:
            timezone = self.parent.ip_info.get('timezone', timezone)
        
        # 根据系统设置默认用户数据目录
        if self.parent and hasattr(self.parent, 'is_windows') and self.parent.is_windows:
            user_data_dir = os.path.join("C:", "temp", "chromium", f"default{data_dir_num:03d}")
        else:
            user_data_dir = f"/tmp/chromium/default{data_dir_num:03d}"
        
        return {
            "name": f"Instance {instance_num}",
            "fingerprint": str(fingerprint_num),
            "user_data_dir": user_data_dir,
            "timezone": timezone,
            "proxy_server": "",
            "chromium_version": "default",  # 新增版本字段
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

    def _get_next_fingerprint_number(self, parent):
        if parent and hasattr(parent, 'config'):
            existing_fingerprints = []
            for inst in parent.config['instances']:
                try:
                    num = int(inst['fingerprint'])
                    existing_fingerprints.append(num)
                except ValueError:
                    continue
            return max(existing_fingerprints, default=999) + 1
        return 1000

    def _get_next_data_dir_number(self, parent):
        if parent and hasattr(parent, 'config'):
            existing_dirs = []
            for inst in parent.config['instances']:
                dir_path = inst['user_data_dir']
                # 支持 Windows 和 macOS 路径
                if parent and hasattr(parent, 'is_windows') and parent.is_windows:
                    if dir_path.startswith(os.path.join("C:", "temp", "chromium", "default")):
                        try:
                            num = int(dir_path.split('default')[-1])
                            existing_dirs.append(num)
                        except ValueError:
                            continue
                else:
                    if dir_path.startswith('/tmp/chromium/default'):
                        try:
                            num = int(dir_path.split('default')[-1])
                            existing_dirs.append(num)
                        except ValueError:
                            continue
            return max(existing_dirs, default=0) + 1
        return 1

    def _get_next_instance_number(self, parent):
        if parent and hasattr(parent, 'config'):
            existing_instances = [inst['name'] for inst in parent.config['instances']]
            base_name = "Instance "
            numbers = []
            for name in existing_instances:
                if name.startswith(base_name):
                    try:
                        num = int(name[len(base_name):])
                        numbers.append(num)
                    except ValueError:
                        continue
            return max(numbers, default=0) + 1
        return 1

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
    def __init__(self, parent=None, instance=None):
        super().__init__(parent)
        self.setWindowTitle("验证指纹")
        self.instance = instance
        self.setup_ui()

    def setup_ui(self):
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
        self.site_combo.addItems([
            "Bot Sannysoft (https://bot.sannysoft.com/)",
            "Browser Leaks (https://browserleaks.com/)",
            "AmIUnique (https://amiunique.org/)",
            "CreepJS (https://abrahamjuliot.github.io/creepjs/)"
        ])
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
        if not self.instance or self.instance['name'] not in self.parent().running_instances:
            QMessageBox.warning(self, "警告", "请先启动该实例")
            return
            
        # 获取选中的网站URL
        site_url = self.site_combo.currentText().split("(")[1].rstrip(")")
        
        # 根据版本获取 Chromium 路径
        chromium_path = self.parent().get_chromium_path(self.instance.get('chromium_version', 'default'))
        
        # 构建启动命令
        cmd = [chromium_path]
        cmd.extend([f"--fingerprint={self.instance['fingerprint']}"])
        cmd.extend([f"--user-data-dir={self.instance['user_data_dir']}"])
        cmd.extend([f"--timezone={self.instance['timezone']}"])
        if self.instance['proxy_server']:
            cmd.extend([f"--proxy-server={self.instance['proxy_server']}"])
        cmd.append(site_url)
        
        try:
            subprocess.Popen(cmd)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开网站失败: {str(e)}")

class ChromiumManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chromium 多实例管理器")
        self.setMinimumSize(900, 600)
        # 获取脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(script_dir, "config.yaml")
        self.running_instances = {}
        self.checkbox_states = {}
        self.ip_info = self.fetch_ip_info()
        self.config = {'instances': []}
        self.available_versions = []
        
        # 检测操作系统
        self.system = platform.system().lower()
        self.is_windows = self.system == 'windows'
        self.is_macos = self.system == 'darwin'
        
        # 设置应用目录
        self.app_dir = os.path.join(script_dir, "App")
        self.download_dir = os.path.join(script_dir, "DownLoad")
        self.platform_dir = os.path.join(self.app_dir, "win_x64" if self.is_windows else "macos")
        
        # 确保目录存在
        os.makedirs(self.app_dir, exist_ok=True)
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.platform_dir, exist_ok=True)
        
        self.load_config()
        self.fetch_available_versions()
        self.setup_ui()
        
        # 设置定时器更新进程状态
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_process_status)
        self.timer.start(2000)  # 每2秒更新一次

    def fetch_ip_info(self):
        try:
            resp = requests.get("http://iprust.io/ip.json", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}

    def fetch_available_versions(self):
        """从 GitHub 获取可用的 Chromium 版本"""
        try:
            url = "https://api.github.com/repos/adryfish/fingerprint-chromium/releases"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                releases = response.json()
                self.available_versions = []
                
                for release in releases:
                    for asset in release['assets']:
                        asset_name = asset['name'].lower()
                        # 根据系统筛选合适的文件
                        if self.is_windows and 'windows' in asset_name and asset_name.endswith('.zip'):
                            self.available_versions.append({
                                'tag_name': release['tag_name'],
                                'name': asset['name'],
                                'download_url': asset['browser_download_url'],
                                'size': round(asset['size'] / (1024 * 1024), 1),  # MB
                                'published_at': release['published_at'][:10],
                                'filepath': os.path.join(self.download_dir, asset['name'])
                            })
                        elif self.is_macos and 'macos' in asset_name and asset_name.endswith('.dmg'):
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
                
                print(f"找到 {len(self.available_versions)} 个可用版本")
                for version in self.available_versions:
                    print(f"- {version['tag_name']}: {version['name']}")
                    
        except Exception as e:
            print(f"获取版本信息失败: {e}")
            import traceback
            traceback.print_exc()

    def get_chromium_path(self, version="default"):
        """根据版本获取 Chromium 可执行文件路径"""
        # 首先从配置文件中查找
        if 'versions' in self.config and isinstance(self.config['versions'], dict) and version in self.config['versions']:
            config_path = self.config['versions'][version]['path']
            if os.path.exists(config_path):
                return config_path
        
        # 如果配置文件中没有或路径不存在，则动态查找
        for v in self.available_versions:
            if v['tag_name'] == version:
                # 查找版本目录中的可执行文件
                version_dir = os.path.join(self.platform_dir, version)
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
        # 没有找到则返回 None
        return None

    def download_version(self, version_info):
        """下载指定版本的 Chromium"""
        dialog = DownloadDialog(self, version_info)
        if dialog.exec():
            # 下载完成后刷新版本列表
            self.fetch_available_versions()
            return True
        return False

    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f)
                if not self.config:
                    self.config = {}
                if 'instances' not in self.config or self.config['instances'] is None:
                    self.config['instances'] = []
                # 初始化版本配置
                if 'versions' not in self.config:
                    self.config['versions'] = {}
                # 配置兼容性：补全每个实例缺失字段
                default_fields = AddInstanceDialog(self)._get_default_values()
                for inst in self.config['instances']:
                    for k, v in default_fields.items():
                        if k not in inst:
                            inst[k] = v
        except FileNotFoundError:
            self.config = {
                "versions": {},
                "instances": []
            }
            self.save_config()

    def save_config(self):
        with open(self.config_file, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False)

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
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
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
        # 获取最后一个实例的配置作为默认值
        default_values = None
        if self.config['instances']:
            last_instance = self.config['instances'][-1]
            # 复制最后一个实例的配置，但修改名称、fingerprint 和用户数据目录
            default_values = last_instance.copy()
            # 获取下一个可用的实例编号
            instance_num = len(self.config['instances']) + 1
            # 获取下一个可用的用户数据目录编号
            data_dir_num = self._get_next_data_dir_number()
            # 获取下一个可用的 fingerprint 编号
            fingerprint_num = self._get_next_fingerprint_number()
            
            default_values['name'] = f"Instance {instance_num}"
            # 根据系统设置正确的用户数据目录路径
            if self.is_windows:
                default_values['user_data_dir'] = os.path.join("C:", "temp", "chromium", f"default{data_dir_num:03d}")
            else:
                default_values['user_data_dir'] = f"/tmp/chromium/default{data_dir_num:03d}"
            default_values['fingerprint'] = str(fingerprint_num)
        
        dialog = AddInstanceDialog(self, default_values)
        if dialog.exec():
            instance_data = dialog.get_instance_data()
            self.config['instances'].append(instance_data)
            self.save_config()
            self.update_table()

    def _get_next_fingerprint_number(self):
        existing_fingerprints = []
        for inst in self.config['instances']:
            try:
                num = int(inst['fingerprint'])
                existing_fingerprints.append(num)
            except ValueError:
                continue
        return max(existing_fingerprints, default=999) + 1

    def _get_next_data_dir_number(self):
        existing_dirs = []
        for inst in self.config['instances']:
            dir_path = inst['user_data_dir']
            # 支持 Windows 和 macOS 路径
            if self.is_windows and dir_path.startswith(os.path.join("C:", "temp", "chromium", "default")):
                try:
                    num = int(dir_path.split('default')[-1])
                    existing_dirs.append(num)
                except ValueError:
                    continue
            else:
                if dir_path.startswith('/tmp/chromium/default'):
                    try:
                        num = int(dir_path.split('default')[-1])
                        existing_dirs.append(num)
                    except ValueError:
                        continue
        return max(existing_dirs, default=0) + 1

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

    def start_instance(self, instance):
        chromium_path = self.get_chromium_path(instance.get('chromium_version', 'default'))
        if not chromium_path or not os.path.exists(chromium_path):
            QMessageBox.critical(self, "错误", f"找不到 Chromium 可执行文件: {chromium_path}")
            return

        cmd = [chromium_path]
        cmd.extend([f"--fingerprint={instance['fingerprint']}"])
        cmd.extend([f"--user-data-dir={instance['user_data_dir']}"])
        cmd.extend([f"--timezone={instance['timezone']}"])
        if instance['proxy_server']:
            cmd.extend([f"--proxy-server={instance['proxy_server']}"])

        print("启动命令：", cmd)  # 打印命令，方便你手动测试

        try:
            # 捕获标准输出和错误输出
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.running_instances[instance['name']] = process.pid
            self.update_table()

            # 新增：读取并弹窗显示错误输出
            import threading
            def read_err():
                err = process.stderr.read()
                if err:
                    err_msg = err.decode(errors='ignore')
                    print("Chromium 错误输出：", err_msg)
                    QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Chromium 启动报错", err_msg))
            threading.Thread(target=read_err, daemon=True).start()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动失败: {str(e)}")

    def stop_instance(self, instance):
        try:
            pid = self.running_instances[instance['name']]
            process = psutil.Process(pid)
            process.terminate()
            process.wait(timeout=5)
            del self.running_instances[instance['name']]
            self.update_table()
        except psutil.NoSuchProcess:
            del self.running_instances[instance['name']]
            self.update_table()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"停止失败: {str(e)}")

    def batch_start_instances(self):
        selected = self.get_selected_instances()
        if not selected:
            QMessageBox.warning(self, "警告", "请先选择要启动的实例")
            return

        for instance in selected:
            if instance['name'] not in self.running_instances:
                self.start_instance(instance)

    def batch_stop_instances(self):
        selected = self.get_selected_instances()
        if not selected:
            QMessageBox.warning(self, "警告", "请先选择要停止的实例")
            return

        for instance in selected:
            if instance['name'] in self.running_instances:
                self.stop_instance(instance)

    def update_process_status(self):
        # 检查所有运行中的进程是否还存在
        for name, pid in list(self.running_instances.items()):
            try:
                process = psutil.Process(pid)
                if process.status() == psutil.STATUS_ZOMBIE:
                    del self.running_instances[name]
            except psutil.NoSuchProcess:
                del self.running_instances[name]
        # 保存复选框状态后再更新表格
        self.update_table()

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
        # 关闭窗口时停止所有运行的实例
        for name, pid in list(self.running_instances.items()):
            try:
                process = psutil.Process(pid)
                process.terminate()
            except:
                pass
        event.accept()

    def update_version_config(self, version, path):
        """更新版本配置"""
        if 'versions' not in self.config or not isinstance(self.config['versions'], dict):
            self.config['versions'] = {}
        self.config['versions'][version] = {
            'path': path,
            'type': 'downloaded',
            'description': f'下载版本 {version}'
        }
        self.save_config()

    def has_version(self, version):
        """判断某个版本是否已下载（可用）"""
        # 检查 config['versions'] 里有无该版本且路径存在
        if 'versions' in self.config and isinstance(self.config['versions'], dict) and version in self.config['versions']:
            config_path = self.config['versions'][version]['path']
            if os.path.exists(config_path):
                return True
        # 动态查找
        for v in self.available_versions:
            if v['tag_name'] == version:
                version_dir = os.path.join(self.platform_dir, version)
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
                        return True
        return False

def main():
    app = QApplication(sys.argv)
    window = ChromiumManager()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 
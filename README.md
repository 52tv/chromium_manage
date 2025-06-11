# Chromium 多实例管理器

这是一个用于管理多个 Chromium 浏览器实例的图形界面工具。它允许你创建、编辑和管理多个具有不同配置的 Chromium 实例，并支持丰富的环境参数自定义与批量操作。

## 功能特点

- 创建和管理多个 Chromium 实例
- 支持批量选择、批量删除、批量启动/停止实例
- 为每个实例配置不同的参数（均可自定义）：
  - Fingerprint
  - 用户数据目录
  - 时区（自动获取本地IP地理信息）
  - 代理服务器
  - 分辨率、字体指纹、WebRTC、WebGL、Canvas、MAC地址、硬件并发数、设备内存等十余项环境参数
- 环境参数分组可折叠，界面简洁
- 图形界面操作，支持参数编辑、实例验证、实时监控运行状态
- 配置文件自动同步，删除实例后配置立即更新
- 自动获取并展示本机公网IP及地理信息
- 配置文件持久化，兼容老版本自动补全新参数

## 安装要求

- Python 3.8 或更高版本
- macOS 操作系统
- Chromium 浏览器已安装（默认路径：/Applications/Chromium.app）

## 安装步骤

1. 克隆或下载此仓库
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

1. 运行程序：
   ```bash
   python chromium_manager.py
   ```

2. 在图形界面中：
   - 点击"添加实例"，可自定义所有参数（环境参数分组可折叠）
   - 勾选多个实例后点击"删除实例"，支持批量删除
   - 支持批量启动/停止实例
   - 选中实例后可编辑、验证指纹、查看环境参数
   - 所有操作自动同步到 config.yaml

## 配置说明

配置文件 `config.yaml` 包含以下设置：

- `chromium_path`: Chromium 可执行文件的路径
- `instances`: 实例列表，每个实例包含（部分字段）：
  - `name`: 实例名称
  - `fingerprint`: 指纹标识
  - `user_data_dir`: 用户数据目录
  - `timezone`: 时区设置
  - `proxy_server`: 代理服务器地址（可选）
  - `resolution`、`font_fingerprint`、`webrtc`、`webgl_image`、`canvas`、`mac_address`、`hardware_concurrency`、`device_memory` 等环境参数

## 注意事项

- 确保 Chromium 浏览器已正确安装
- 用户数据目录需要有适当的读写权限
- 关闭程序时会自动停止所有运行的实例
- 删除实例后配置文件自动同步，无需手动编辑
- 建议定期备份配置文件 
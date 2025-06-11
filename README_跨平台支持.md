# Chromium 多实例管理器 - 跨平台支持

## 新增功能

### 1. 跨平台支持
- **macOS**: 支持 macOS 系统，自动检测系统类型
- **Windows**: 支持 Windows 系统，自动检测系统类型
- **自动路径适配**: 根据操作系统自动设置正确的文件路径

### 2. 版本管理功能
- **在线版本获取**: 从 GitHub 自动获取可用的 Chromium 版本
- **版本下载**: 支持下载指定版本的 Chromium
- **版本选择**: 在创建实例时可以选择使用特定版本
- **自动 DMG 处理**: macOS 系统自动处理 DMG 文件并提取 Chromium.app

## 系统要求

### macOS
- Python 3.7+
- PyQt6
- 其他依赖见 requirements.txt

### Windows
- Python 3.7+
- PyQt6
- 其他依赖见 requirements.txt

## 安装说明

1. 克隆或下载项目
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 运行程序：
   ```bash
   python start.py
   ```

## 使用说明

### 下载 Chromium 版本

1. 点击界面上的"下载版本"按钮
2. 在弹出的对话框中选择要下载的版本
3. 点击"下载选中版本"
4. 等待下载和处理完成

#### macOS 用户
- 下载的文件是 `.dmg` 格式
- **自动处理**: 程序会自动挂载 DMG 文件，提取 Chromium.app 并复制到版本目录
- 无需手动安装，程序会自动完成所有操作

#### Windows 用户
- 下载的文件是 `.zip` 格式
- 程序会自动解压到版本目录

### 创建实例

1. 点击"添加实例"按钮
2. 在基础参数中选择 Chromium 版本
3. 配置其他参数
4. 点击"保存"

### 文件结构

```
chromium_manage/
├── App/                    # 应用程序目录
│   ├── macos/             # macOS 版本文件
│   │   ├── 136.0.7103.113/  # 版本目录
│   │   │   └── Chromium.app/ # Chromium 应用程序
│   │   └── 135.0.7049.95/    # 其他版本
│   └── win_x64/           # Windows 版本文件
│       ├── 136.0.7103.113/  # 版本目录
│       │   └── chrome.exe    # Chrome 可执行文件
│       └── 135.0.7049.95/    # 其他版本
├── DownLoad/              # 下载目录
│   ├── ungoogled-chromium_136.0.7103.113-1.1_macos.dmg
│   └── ungoogled-chromium_136.0.7103.113-1.1_windows_x64.zip
├── chromium_manager.py    # 主程序
├── start.py              # 启动脚本
├── config.yaml           # 配置文件
└── requirements.txt      # 依赖列表
```

## 配置说明

### 用户数据目录
- **macOS**: `/tmp/chromium/defaultXXX`
- **Windows**: `C:\temp\chromium\defaultXXX`

### 默认 Chromium 路径
- **macOS**: `/Applications/Chromium.app/Contents/MacOS/Chromium`
- **Windows**: `C:\Program Files\Chromium\Application\chrome.exe`

### 版本目录结构
- **macOS**: `App/macos/{version}/Chromium.app/Contents/MacOS/Chromium`
- **Windows**: `App/win_x64/{version}/chrome.exe`

## 故障排除

### 无法获取版本信息
1. 检查网络连接
2. 确认可以访问 GitHub API
3. 查看控制台输出的错误信息

### 下载失败
1. 检查磁盘空间
2. 确认网络连接稳定
3. 尝试重新下载

### DMG 文件处理失败
1. 确认有足够的磁盘空间
2. 检查 `/tmp` 目录权限
3. 确认 `hdiutil` 命令可用
4. 查看日志输出获取详细错误信息

### 版本不匹配
1. 确认选择了正确的操作系统版本
2. 检查文件是否完整下载
3. 重新下载版本

## 更新日志

### v2.1.0
- 新增自动 DMG 文件处理功能
- 优化目录结构，分离下载和应用目录
- 改进版本管理，按版本号组织文件
- 增强错误处理和日志输出

### v2.0.0
- 新增跨平台支持（macOS + Windows）
- 新增版本管理功能
- 新增在线版本下载
- 优化用户界面
- 修复路径兼容性问题

## 技术支持

如果遇到问题，请：
1. 查看控制台输出的错误信息
2. 检查网络连接
3. 确认系统兼容性
4. 运行测试脚本验证环境
5. 提交 Issue 或联系开发者 
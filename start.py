#!/usr/bin/env python3
"""
Chromium 多实例管理器启动脚本
"""
import sys
import os
import platform

def check_environment():
    """检查运行环境"""
    print("=== 环境检查 ===")
    
    # 检查 Python 版本
    python_version = sys.version_info
    print(f"Python 版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 7):
        print("❌ Python 版本过低，需要 Python 3.7 或更高版本")
        return False
    else:
        print("✅ Python 版本符合要求")
    
    # 检查操作系统
    system = platform.system()
    print(f"操作系统: {system}")
    
    if system in ['Darwin', 'Windows']:
        print("✅ 操作系统支持")
    else:
        print("⚠️  操作系统可能不完全支持")
    
    # 检查必要模块
    required_modules = ['PyQt6', 'psutil', 'yaml', 'requests']
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module} 已安装")
        except ImportError:
            print(f"❌ {module} 未安装")
            missing_modules.append(module)
    
    if missing_modules:
        print(f"\n缺少以下模块: {', '.join(missing_modules)}")
        print("请运行: pip install -r requirements.txt")
        return False
    
    return True

def main():
    """主函数"""
    print("Chromium 多实例管理器启动中...")
    print("=" * 50)
    
    # 检查环境
    if not check_environment():
        print("\n❌ 环境检查失败，请解决上述问题后重试")
        input("按回车键退出...")
        sys.exit(1)
    
    print("\n✅ 环境检查通过")
    print("=" * 50)
    
    # 导入并启动主程序
    try:
        from chromium_manager import main as start_app
        print("启动主程序...")
        start_app()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")
        sys.exit(1)

if __name__ == "__main__":
    main() 
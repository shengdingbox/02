"""Antigravity Tools - PyInstaller 入口文件

此文件是打包的入口点，将 src 包路径添加到 sys.path 后启动应用。
直接运行此文件等同于 python -m src.main
"""

import sys
import os

# 将项目根目录加入 sys.path，使 `from src.xxx` 正常工作
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# PyInstaller 打包后，_MEIPASS 指向临时解压目录
# 但我们的 src/ 是 --add-data 打包进去的，需要把解压根目录也加入
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
    if base_path not in sys.path:
        sys.path.insert(0, base_path)

from src.main import main

if __name__ == "__main__":
    main()

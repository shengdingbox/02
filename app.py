"""Buddy Tool - 打包入口文件

此文件是打包的入口点，将 src 包路径添加到 sys.path 后启动应用。
直接运行此文件等同于 python -m src.main
"""

import sys
import os

# Linux 无 X11 环境（如服务器）下设置 offscreen，避免 Qt xcb 插件加载失败
# 必须在 PySide6 被导入之前设置
if sys.platform.startswith('linux'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# 将项目根目录加入 sys.path，使 `from src.xxx` 正常工作
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 动态加载 src.main 模块并执行 main()
import importlib
_mod = importlib.import_module('src.main')
_mod.main()

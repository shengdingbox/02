"""Buddy Tool CLI - 命令行模式入口文件

直接运行此文件进入无窗口命令行模式：
    python cli_app.py                 # 交互模式
    python cli_app.py --redeem BC_xx  # 直接兑换
    python cli_app.py --start         # 直接启动服务
    python cli_app.py --credits       # 查询积分
"""

import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import importlib
_mod = importlib.import_module('src.cli')
_mod.main()

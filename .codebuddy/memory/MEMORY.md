# Antigravity Tools - 项目记忆

## 项目概述
- **名称**: Antigravity Tools（⚡ Antigravity Tools）
- **定位**: 多平台 IDE 工具管理器 — WorkBuddy / CodeBuddy 批量签到、API Key 代理、积分管理
- **技术栈**: Python 3.13+ / PySide6 (Qt6) / SQLite / PyInstaller 打包 / GitHub Actions CI/CD
- **仓库**: https://github.com/qinchangxv/antigravity-tools
- **当前版本**: v1.6.3（version.json），pyproject.toml 中为 0.1.0
- **许可**: MIT

## 项目结构
```
antigravity-tools/
├── app.py                 # PyInstaller 打包入口，importlib 动态加载 src.main
├── src/                   # 核心源码包
│   ├── main.py            # 应用入口（日志配置、单实例、信号处理、QApplication 启动）
│   ├── main_window.py     # 主窗口（侧边栏 + QStackedWidget 页面切换、托盘、自动更新）
│   ├── i18n/              # 国际化（zh-CN/en-US 翻译字典）
│   ├── models/__init__.py # 数据模型（Account, Platform, QuotaInfo, ResourcePackage, CheckinStatus 等）
│   ├── modules/           # 核心业务模块
│   │   ├── api_client.py    # CodeBuddy/WorkBuddy API 客户端（积分查询、签到）
│   │   ├── oauth.py         # WorkBuddy OAuth 登录流程
│   │   ├── checkin.py       # 签到管理器
│   │   ├── proxy_server.py  # 本地 API 中转代理服务（最大文件，~176KB）
│   │   └── updater.py       # 自动更新检查器
│   ├── ui/
│   │   ├── components/sidebar.py  # 侧边栏导航
│   │   ├── pages/                # 5 个页面
│   │   │   ├── dashboard.py   # 仪表盘
│   │   │   ├── accounts.py    # 账号管理（~104KB，最大页面）
│   │   │   ├── checkin.py     # 每日签到
│   │   │   ├── api_proxy.py   # API 代理配置（~120KB）
│   │   │   ├── settings.py    # 设置
│   │   │   └── quota.py       # 配额监控
│   │   └── styles/theme.py    # 主题样式
│   └── utils/store.py     # SQLite 持久化存储（账号、设置）
├── tests/                # 测试（test_model_config.py）
├── assets/icons/         # 应用图标
├── antigravity.spec      # Windows PyInstaller 打包配置
├── antigravity-mac.spec  # macOS PyInstaller 打包配置
├── pyproject.toml        # uv 项目配置
├── requirements.txt      # pip 依赖
├── version.json          # 版本信息（用于自动更新）
└── dist_final/           # 打包输出目录
```

## 核心功能模块
1. **账号管理**: 多平台账号统一管理，支持 API Key (ck_xxx) 导入、JSON/文本批量导入、卡密导入
2. **批量签到**: 每日自动签到 + 连续签到追踪
3. **积分监控**: 实时查询积分/配额，多资源包展示
4. **API 代理服务**: 本地 HTTP 代理，转发请求到上游 copilot.tencent.com，支持多 Key 轮询/粘性会话/负载感知/故障转移
5. **自动更新**: 定期检查 GitHub Releases，支持增量更新（src/ 目录替换）
6. **一键配置**: 一键配置 WorkBuddy/CodeBuddy 客户端走本地代理

## 关键技术细节
- **数据存储**: SQLite (`~/.antigravity-tools/antigravity.db`)，WAL 模式
- **API 认证**: 两种模式 — JWT (Keycloak) 和 API Key (ck_xxx)，推荐 API Key 模式
- **API 基址**: 积分/签到 API 在 `https://copilot.tencent.com`，公开 API 在 `https://codebuddy.cn`
- **代理上游**: `https://copilot.tencent.com/v2`（base64 双重编码隐藏）
- **单实例**: QLocalSocket/QLocalServer 实现，支持唤醒已运行窗口
- **打包**: PyInstaller 目录模式，app.py 用 importlib 动态加载 src.main 避免 src/ 编译进 PYZ
- **日志**: GUI 模式写文件 (`~/.antigravity-tools/logs/app.log`)，RotatingFileHandler 2MB×3

## 依赖
- PySide6==6.11.1 (Qt6 GUI 框架)
- requests==2.34.2 (HTTP 客户端)
- cryptography==48.0.0
- pyinstaller==6.20.0

## 运行方式
- 开发: `python src/main.py` 或 `python -m src.main`
- 打包: `pyinstaller antigravity.spec` (Windows) / `pyinstaller antigravity-mac.spec` (macOS)

## Git 状态备注
- `dist_final/` 是打包输出目录，内含 234 文件（.qm 翻译、.dll、.py 等）
- `src/` 下有 .pyc 缓存文件
- Git 仓库: github.com/qinchangxv/antigravity-tools，分支 main

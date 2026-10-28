@echo off
REM Qoder 重置工具 Windows 启动脚本

REM 设置控制台编码为 UTF-8
chcp 65001 >nul

REM 检测 Python 环境
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误：未找到 Python 环境
    echo 请先安装 Python 3.7 或更高版本：
    echo 1. 官网下载：https://www.python.org/downloads/windows/
    echo 2. 微软商店（Microsoft Store）安装
    echo 3. Anaconda 环境
    pause
    exit /b 1
)

REM 检查 Python 版本（要求 Python 3.7+）
for /f "delims=" %%a in ('python -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"') do set "PYVER=%%a"
set "PYVER=%PYVER:.=%"
if %PYVER% lss 37 (
    echo ❌ 错误：需要 Python 3.7 或更高版本
    echo 当前检测到的版本：%PYVER%
    pause
    exit /b 1
)

REM 检查并安装必要依赖库
echo ⚙️ 正在检查运行依赖...
python -c "import PyQt5; import requests" 2>nul
if %errorlevel% neq 0 (
    python -m pip install PyQt5 requests 2>nul
    if %errorlevel% neq 0 (
        echo ⚙️ 当前 Python 未能安装 PyQt5，正在尝试安装 PyQt6...
        python -m pip install PyQt6 requests 2>nul
    )
)

REM 检查图形界面（GUI）库可用性
python -c "import PyQt5" 2>nul
if %errorlevel% neq 0 (
    python -c "import PyQt6" 2>nul
    if %errorlevel% neq 0 (
        python -c "import PySide6" 2>nul
        if %errorlevel% neq 0 (
            echo ⚠️ 未安装 Qt 图形组件，程序将以命令行控制台（CLI）模式运行。
            set "QODER_CONSOLE=1"
        )
    )
)

REM 检查主程序脚本是否存在
if not exist "qoder_reset_gui.py" (
    echo ❌ 错误：未找到 qoder_reset_gui.py 文件
    echo 请确认您在正确的项目目录下运行此脚本。
    pause
    exit /b 1
)

REM 清屏并显示启动提示
cls
echo ==================================================
echo 🚀 Qoder 重置工具启动器
echo ==================================================
echo ✅ 环境检查通过
echo ✅ 正在启动应用程序...
echo ==================================================

REM 启动应用程序
if "%QODER_DEBUG%"=="1" (
    set "QODER_CONSOLE=1"
    set "QT_DEBUG_PLUGINS=1"
)

if "%QODER_CONSOLE%"=="1" (
    echo [*] 正在以控制台模式启动 Qoder 重置工具...
    python qoder_reset_gui.py
    echo.
    echo ==================================================
    echo 🏁 执行结束，按任意键退出...
    echo ==================================================
    pause >nul
    exit /b 0
) else (
    start "" pythonw qoder_reset_gui.py
)

REM 启动完毕
echo ==================================================
echo 🏁 Qoder 重置工具已成功启动
echo ==================================================
timeout /t 2 >nul

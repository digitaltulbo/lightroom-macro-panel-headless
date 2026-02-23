@echo off
cd /d "%~dp0"
echo [TEST] Dashboard.py를 실행합니다...
pythonw Dashboard.py
if %errorlevel% neq 0 (
    echo [ERROR] 실행에 실패했습니다. (파이썬이 꺼져있거나 라이브러리 문제)
    pause
)

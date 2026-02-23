@echo off
setlocal
cd /d "%~dp0"
title Studio Birthday - EXE Builder

echo ===================================================
echo    Studio Birthday - Dashboard EXE Builder
echo ===================================================
echo.

:: 1. 필수 라이브러리 확인
echo [1/3] 빌드 도구 확인 중...
python -m pip install --upgrade pip
pip install pyinstaller pywebview keyboard psutil pygame flask watchdog
echo.

:: 2. 빌드 실행
echo [2/3] EXE 빌드를 시작합니다...
:: --noconsole: 콘솔 창 없이 실행
:: --onefile: 단일 실행 파일로 생성
:: --name Dashboard: 실행 파일 이름 설정
:: --clean: 이전 빌드 캐시 삭제
pyinstaller --noconsole --onefile --name Dashboard Dashboard.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] 빌드에 실패했습니다. 코드를 확인해주세요.
    pause
    exit /b
)

:: 3. 후처리
echo.
echo [3/3] 빌드 완료! 결과물을 정리합니다...

:: dist 폴더의 EXE를 현재 폴더로 이동
if exist "dist\Dashboard.exe" (
    move /y "dist\Dashboard.exe" "Dashboard.exe"
)

:: 임시 폴더 삭제
rmdir /s /q build
rmdir /s /q dist
del /f /q Dashboard.spec

echo.
echo ===================================================
echo    성공! 이제 [Dashboard.exe]를 실행할 수 있습니다.
echo    주의: ui, Sounds 폴더와 config.json이 같은 곳에 있어야 합니다.
echo ===================================================
pause

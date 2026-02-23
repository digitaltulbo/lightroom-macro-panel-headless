@echo off
chcp 65001 >nul
title 스튜디오 대시보드 - 최신 업데이트 도우미

echo ===================================================
echo    스튜디오 대시보드 - 업데이트를 시작합니다
echo ===================================================
echo.
echo [안내] 이 작업은 자동으로 최신 기능을 설치합니다.
echo        잠시만 기다려주세요...
echo.

:: 1. 구글 드라이브 경로 자동 탐색 (H드라이브 또는 G드라이브)
set "SOURCE="
if exist "H:\내 드라이브\01.Studio-Improvement\lightroom_macro_panel-v3_portable" (
    set "SOURCE=H:\내 드라이브\01.Studio-Improvement\lightroom_macro_panel-v3_portable"
) else if exist "G:\내 드라이브\01.Studio-Improvement\lightroom_macro_panel-v3_portable" (
    set "SOURCE=G:\내 드라이브\01.Studio-Improvement\lightroom_macro_panel-v3_portable"
)

:: 드라이브를 못 찾을 경우 에러 메시지
if "%SOURCE%"=="" (
    echo [실패] 구글 드라이브를 찾을 수 없습니다.
    echo        1. 구글 드라이브 프로그램이 켜져 있는지 확인해주세요.
    echo        2. 인터넷 연결을 확인해주세요.
    echo.
    pause
    exit /b
)

:: 2. 파일 복사 시작
echo [진행] 최신 파일을 가져오고 있습니다...
:: /MIR: 폴더 동기화 | /XF: 각 컴별 개별 설정(config.json)은 보존
robocopy "%SOURCE%" "." /MIR /XF config.json 업데이트.bat /R:3 /W:5 /NDL /NFL /NJH /NJS

echo.
echo ===================================================
echo    ✅ 업데이트가 모두 완료되었습니다!
echo ===================================================
echo.
echo [Dashboard.exe]를 실행하여 촬영을 시작하세요.
echo.
pause

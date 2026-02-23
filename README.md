# Lightroom Macro Panel

**Studio Birthday** - Lightroom 자동화 매크로 패널 (Portable Edition)

셀프 사진 스튜디오에서 Adobe Lightroom Classic을 자동 제어하기 위한 데스크톱 앱입니다.

## 주요 기능

- **테더링 촬영 시작**: Lightroom Classic 테더링 캡처를 자동으로 시작
- **세션 타이머**: 베이직(30분) / 프리미엄(55분) 패키지별 타이머 + 소리 알림
- **사진 내보내기**: 전체 사진 일괄 내보내기 (Ctrl+Alt+Shift+E)
- **ZIP 압축**: 내보낸 사진을 자동 압축
- **세션 종료**: 임시 파일 정리 및 Lightroom 종료

## 기술 스택

- **Python** + [pywebview](https://pywebview.flowrl.com/) (웹뷰 기반 UI)
- **keyboard** / **win32gui** (Windows 키보드·윈도우 제어)
- **pygame** (사운드 재생)
- **psutil** (프로세스 관리)
- **PyInstaller** (EXE 빌드)

## 설치 및 실행

### 요구사항
- Windows 10/11
- Python 3.9+
- Adobe Lightroom Classic

### 설치
```bash
pip install -r requirements.txt
```

### 실행
```bash
python Dashboard.py
```

### EXE 빌드
```bash
build_exe.bat
```

## 프로젝트 구조

```
├── Dashboard.py        # 메인 앱 (매크로 로직 + API)
├── config.json         # 설정 파일
├── version.json        # 버전 정보
├── requirements.txt    # Python 패키지 목록
├── build_exe.bat       # PyInstaller 빌드 스크립트
├── run_test.bat        # 테스트 실행 스크립트
├── 업데이트.bat         # 자동 업데이트 스크립트
├── ui/
│   └── index.html      # 웹뷰 UI
└── Sounds/
    ├── Start_shoot.mp3
    ├── end_15min.mp3
    ├── end_5min.mp3
    └── The_end.mp3
```

## 라이선스

MIT License

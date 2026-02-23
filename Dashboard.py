#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
Studio Birthday - Lightroom Macro Panel (Headless Edition)
=============================================================================
Flask HTTP 서버로 Home Assistant에서 워크플로우를 제어합니다.
pywebview UI 없이 백그라운드 서비스로 동작합니다.
"""

import os
import sys
import json
import time
import ctypes
import threading
import subprocess
import shutil
import zipfile
import logging
from pathlib import Path
from datetime import datetime

import psutil
from flask import Flask, jsonify, request, make_response
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 실행 경로 설정 (EXE 실행 시와 스크립트 실행 시 대응)
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

# Windows 전용 모듈
try:
    import win32gui
    import win32con
    import win32api
    import keyboard
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


# =============================================================================
# 설정
# =============================================================================

# version.json에서 버전 읽어오기
APP_VERSION = "0.1 (Headless)"
try:
    with open(BASE_DIR / "version.json", "r", encoding="utf-8") as f:
        v_data = json.load(f)
        if "version" in v_data:
            APP_VERSION = f"{v_data['version']} (Headless)"
except Exception:
    pass
CONFIG_FILE = BASE_DIR / "config.json"
FLASK_PORT = 8765
EXPORT_PATH = Path.home() / "Desktop" / "내보내기"

DEFAULT_CONFIG = {
    "export_target_folder": "Desktop\\내보내기",
    "session_duration_basic": 35,
    "session_duration_premium": 50,
    "lightroom_process_name": "Lightroom.exe",
    "lightroom_window_title_contains": "Lightroom",
    "lightroom_path": "",
    "base_catalog_path": "",
    "work_catalog_path": "",
    "delays": {
        "window_activation_wait_ms": 500,
    },
}


def _block_input(enable: bool):
    """입력 잠금/해제. 관리자 권한 없으면 경고만 출력하고 계속 진행."""
    if not WINDOWS_AVAILABLE:
        log.warning('BlockInput: Windows 전용 기능 (건너뜀)')
        return
    try:
        ctypes.windll.user32.BlockInput(enable)
        log.info('입력 %s', '잠금' if enable else '해제')
    except Exception as e:
        log.warning('BlockInput 실패 (관리자 권한 필요): %s', e)


# =============================================================================
# Sound Player (pygame)
# =============================================================================

class SoundPlayer:
    """MP3 사운드 파일 재생 (pygame 사용)"""

    SOUND_FILES = {
        'start':    'Start_shoot.mp3',
        'end_15min': 'end_15min.mp3',
        'end_5min':  'end_5min.mp3',
        'end':      'The_end.mp3',
    }

    @classmethod
    def get_sounds_dir(cls):
        return BASE_DIR / "Sounds"

    @classmethod
    def play(cls, sound_type: str):
        """사운드 재생 (비동기)"""
        sound_file = cls.SOUND_FILES.get(sound_type)
        if not sound_file:
            return
        sound_path = cls.get_sounds_dir() / sound_file
        if not sound_path.exists():
            log.warning('사운드 파일 없음: %s', sound_path)
            return

        def _play_thread():
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(str(sound_path))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
            except Exception as e:
                log.error('사운드 재생 오류: %s', e)

        threading.Thread(target=_play_thread, daemon=True).start()


# =============================================================================
# Session Timer
# =============================================================================

class SessionTimer:
    """촬영 세션 타이머 + 사운드 알림"""

    def __init__(self, duration_minutes: int, on_tick=None, on_remind=None, on_end=None):
        self.duration_minutes = duration_minutes
        self.total_seconds = duration_minutes * 60
        self.remaining_seconds = self.total_seconds
        self.is_running = False
        self._thread = None
        self.on_tick = on_tick
        self.on_remind = on_remind
        self.on_end = on_end
        self.reminder_points = {15: 'end_15min', 5: 'end_5min'}
        self.reminded = set()

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.reminded.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        SoundPlayer.play('start')

    def stop(self):
        self.is_running = False

    def _run(self):
        while self.remaining_seconds > 0 and self.is_running:
            time.sleep(1)
            self.remaining_seconds -= 1
            if self.on_tick:
                self.on_tick(self.remaining_seconds)
            remaining_min = self.remaining_seconds // 60
            if remaining_min in self.reminder_points and remaining_min not in self.reminded:
                self.reminded.add(remaining_min)
                SoundPlayer.play(self.reminder_points[remaining_min])
                if self.on_remind:
                    self.on_remind(f'{remaining_min}분 남았습니다!')
        if self.is_running:
            SoundPlayer.play('end')
            if self.on_end:
                self.on_end()
        self.is_running = False


# =============================================================================
# Config Manager
# =============================================================================

class ConfigManager:
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.config = self._load()

    def _load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_CONFIG.copy()

    def get(self, key, default=None):
        keys = key.split('.')
        val = self.config
        try:
            for k in keys:
                val = val[k]
            return val
        except Exception:
            return default


# =============================================================================
# Windows Controller
# =============================================================================

class WindowsController:
    def __init__(self, config: ConfigManager):
        self.config = config

    def is_process_running(self, process_name: str) -> bool:
        if not WINDOWS_AVAILABLE:
            return False
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                    return True
            except Exception:
                pass
        return False

    def find_window_by_title(self, title_contains: str):
        if not WINDOWS_AVAILABLE:
            return None
        result = []
        def enum_callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title_contains.lower() in title.lower():
                    result.append(hwnd)
            return True
        win32gui.EnumWindows(enum_callback, None)
        return result[0] if result else None

    def activate_window(self, hwnd: int) -> bool:
        if not WINDOWS_AVAILABLE or not hwnd:
            return False
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(self.config.get('delays.window_activation_wait_ms', 500) / 1000.0)
            return True
        except Exception:
            return False

    def ensure_lightroom_running(self) -> bool:
        process_name = self.config.get('lightroom_process_name', 'Lightroom.exe')
        if self.is_process_running(process_name):
            return True
        lr_path = self.config.get('lightroom_path')
        if not lr_path or not os.path.exists(lr_path):
            log.warning('라이트룸 실행 경로를 찾을 수 없음: %s', lr_path)
            return False

        try:
            cmd = [lr_path]
            subprocess.Popen(cmd)
            
            title_contains = self.config.get('lightroom_window_title_contains', 'Lightroom')
            for _ in range(20):
                time.sleep(1.5)
                if self.find_window_by_title(title_contains):
                    launch_delay = self.config.get('delays.app_launch_wait_ms', 15000) / 1000.0
                    log.info('라이트룸 창 감지됨. 안정화를 위해 %.1f초 대기...', launch_delay)
                    time.sleep(launch_delay)
                    return True
        except Exception as e:
            log.error('라이트룸 실행 중 오류: %s', e)
            return False
        return False

    def activate_lightroom(self) -> bool:
        title_contains = self.config.get('lightroom_window_title_contains', 'Lightroom')
        hwnd = self.find_window_by_title(title_contains)
        if hwnd:
            return self.activate_window(hwnd)
        return False

    def wait_for_lightroom_focus(self, max_retries: int = 10) -> bool:
        if not WINDOWS_AVAILABLE:
            return True
        title_contains = self.config.get('lightroom_window_title_contains', 'Lightroom')
        for attempt in range(max_retries):
            hwnd = self.find_window_by_title(title_contains)
            if not hwnd:
                time.sleep(1.5)
                continue
            if win32gui.GetForegroundWindow() == hwnd:
                return True
            self.activate_lightroom()
            time.sleep(0.8)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
        return False


# =============================================================================
# Macro Actions
# =============================================================================

class MacroActions:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.win = WindowsController(config)

    def start_tether(self):
        log.info('테더링: 라이트룸 실행 확인 중...')
        if not self.win.ensure_lightroom_running():
            return '라이트룸 실행 실패'
            
        log.info('테더링: 최초 포커스 확인 중...')
        if not self.win.wait_for_lightroom_focus():
            return '라이트룸 포커스 실패'
            
        # [중요] 라이트룸이 완전히 로드될 때까지 추가 대기 (오리지널 코드)
        log.info('테더링: 로드 대기 3초...')
        time.sleep(3.0)
        
        # 다시 한번 포커스 확인 (오리지널 코드)
        log.info('테더링: 2차 포커스 활성화 중...')
        self.win.activate_lightroom()
        time.sleep(1.0)
        
        log.info('테더링: 매크로 단축키 입력 시작...')
        keyboard.send('alt+f')
        time.sleep(0.5)
        for _ in range(8):
            keyboard.send('down')
            time.sleep(0.1)
        keyboard.send('right')
        time.sleep(0.3)
        keyboard.send('enter')
        time.sleep(0.5) # 오리지널 값
        
        session_name = datetime.now().strftime('%Y-%m-%d_%H-%M')
        keyboard.write(session_name)
        
        # Tab 4번 후 시퀀스 번호 1로 초기화 (오리지널 코드)
        time.sleep(0.3)
        keyboard.send('tab')
        time.sleep(0.2)
        keyboard.send('tab')
        time.sleep(0.2)
        keyboard.send('tab')
        time.sleep(0.2)
        keyboard.send('tab')
        time.sleep(0.2)
        keyboard.write('1')
        
        time.sleep(0.3)
        keyboard.send('enter')
        
        # 테더링 세션 초기화 대기 (오리지널 코드)
        time.sleep(2.0)
        
        keyboard.send('ctrl+alt+1')
        time.sleep(0.5)
        keyboard.send('e')
        time.sleep(0.5)
        
        log.info('테더링 완료: %s', session_name)
        return f'테더링 시작: {session_name}'

    def terminate_lightroom(self):
        process_name = self.config.get('lightroom_process_name', 'Lightroom.exe')
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                    proc.terminate()
            except Exception:
                pass
        return '라이트룸 종료 완료'


# =============================================================================
# Export Watchdog
# =============================================================================

class ExportWatchdog(FileSystemEventHandler):
    """내보내기 폴더 감시 — 마지막 파일 이후 idle_seconds간 변화 없으면 완료 판단."""

    def __init__(self, on_complete, idle_seconds: int = 45):
        super().__init__()
        self.on_complete = on_complete
        self.idle_seconds = idle_seconds
        self._last_event_time = time.time()
        self._active = False
        self._observer = None

    def on_created(self, event):
        if not event.is_directory:
            self._last_event_time = time.time()
            log.info('파일 감지: %s', event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._last_event_time = time.time()

    def start_monitoring(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self._active = True
        self._last_event_time = time.time()
        self._observer = Observer()
        self._observer.schedule(self, str(path), recursive=False)
        self._observer.start()
        threading.Thread(target=self._idle_check, daemon=True).start()
        log.info('내보내기 폴더 감시 시작: %s', path)

    def _idle_check(self):
        while self._active:
            time.sleep(1)
            if time.time() - self._last_event_time >= self.idle_seconds:
                self._active = False
                log.info('%d초간 변화 없음 → 내보내기 완료 판단', self.idle_seconds)
                self._observer.stop()
                self.on_complete()
                break

    def stop(self):
        self._active = False
        if self._observer:
            self._observer.stop()


# =============================================================================
# Workflow Engine
# =============================================================================

class WorkflowEngine:
    """촬영 세션 전체 워크플로우 관리"""

    DURATIONS = {'basic': 35, 'premium': 50}

    def __init__(self, config: ConfigManager):
        self.config = config
        self.actions = MacroActions(config)
        self.timer = None
        self._running = False
        self._package = None
        self._lock = threading.Lock()

    @property
    def status(self) -> dict:
        with self._lock:
            if self.timer and self.timer.is_running:
                rem = self.timer.remaining_seconds
                m, s = divmod(rem, 60)
                return {
                    'running': True,
                    'remaining': rem,
                    'display': f'{m:02d}:{s:02d}',
                    'total': self.timer.total_seconds,
                    'package': self._package,
                    'version': APP_VERSION.split(' ')[0]
                }
            return {'running': self._running, 'version': APP_VERSION.split(' ')[0]}

    def start(self, package: str) -> str:
        with self._lock:
            if self._running:
                return 'already_running'
            self._running = True
            self._package = package
        minutes = self.DURATIONS.get(package, 35)
        threading.Thread(target=self._run_workflow, args=(minutes,), daemon=True).start()
        log.info('세션 시작: %s (%d분)', package, minutes)
        return 'started'

    def stop(self) -> str:
        with self._lock:
            self._running = False
        if self.timer:
            self.timer.stop()
        _block_input(False)
        self.actions.terminate_lightroom()
        log.info('세션 강제 종료')
        return 'stopped'

    # ── 내부 워크플로우 ──

    def _run_workflow(self, minutes: int):
        try:
            result = self.actions.start_tether()
            log.info('테더링: %s', result)
        except Exception as e:
            log.error('start_tether 오류: %s', e)

        self.timer = SessionTimer(
            minutes,
            on_remind=lambda msg: log.info('알림: %s', msg),
            on_end=self._on_timer_end,
        )
        self.timer.start()

    def _on_timer_end(self):
        if not self._running:
            return
        log.info('타이머 종료 → 자동 내보내기 시작')

        # 라이트룸 포커스 확보
        self.actions.win.wait_for_lightroom_focus()
        time.sleep(0.5)

        # 라이브러리 그리드 뷰 강제 전환
        # (현상 모듈이나 팝업 상태에서는 Ctrl+A/내보내기가 씹히므로 반드시 선행)
        if WINDOWS_AVAILABLE:
            for _ in range(3):          # 팝업/모달 닫기
                keyboard.send('esc')
                time.sleep(0.2)
            keyboard.send('g')          # Library 그리드 뷰 강제 전환
            time.sleep(0.8)             # 모듈 전환 애니메이션 대기

        # 전체선택 + 내보내기 단축키
        if WINDOWS_AVAILABLE:
            keyboard.send('ctrl+a')
            time.sleep(0.5)
            keyboard.send('ctrl+alt+shift+e')
            time.sleep(0.3)

        # 라이트룸 최소화
        if WINDOWS_AVAILABLE:
            title = self.config.get('lightroom_window_title_contains', 'Lightroom')
            hwnd = self.actions.win.find_window_by_title(title)
            if hwnd:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

        # 내보내기 폴더 미리 열기 (실시간 감상용)
        if WINDOWS_AVAILABLE:
            subprocess.Popen(['explorer', str(EXPORT_PATH)])

        # 입력 잠금
        _block_input(True)

        # watchdog으로 내보내기 완료 감시
        watchdog = ExportWatchdog(on_complete=self._on_export_complete)
        watchdog.start_monitoring(EXPORT_PATH)

    def _on_export_complete(self):
        log.info('내보내기 완료 → 정리 시작')
        _block_input(False)
        self.actions.terminate_lightroom()
        with self._lock:
            self._running = False
        log.info('워크플로우 완료')


# =============================================================================
# Flask HTTP Server (port 8765)
# =============================================================================

def create_flask_app(engine: WorkflowEngine) -> Flask:
    app = Flask(__name__)
    tablet_path = BASE_DIR / "ui" / "tablet.html"

    def _cors(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    @app.after_request
    def add_cors(response):
        return _cors(response)

    @app.route('/tablet')
    def tablet():
        return tablet_path.read_text(encoding='utf-8'), 200, {'Content-Type': 'text/html; charset=utf-8'}

    @app.route('/status', methods=['GET', 'OPTIONS'])
    def status():
        if request.method == 'OPTIONS':
            return _cors(make_response('', 204))
        return jsonify(engine.status)

    @app.route('/webhook/start', methods=['POST', 'OPTIONS'])
    def webhook_start():
        if request.method == 'OPTIONS':
            return _cors(make_response('', 204))
        data = request.get_json(silent=True) or {}
        pkg = data.get('package', 'basic')
        result = engine.start(pkg)
        return jsonify({'ok': True, 'result': result, 'package': pkg})

    @app.route('/webhook/end', methods=['POST', 'OPTIONS'])
    def webhook_end():
        if request.method == 'OPTIONS':
            return _cors(make_response('', 204))
        # 최우선으로 BlockInput 해제 — Flask 스레드는 네트워크 I/O 전용이므로
        # BlockInput(True) 상태에서도 이 핸들러는 항상 도달할 수 있음
        _block_input(False)
        result = engine.stop()
        return jsonify({'ok': True, 'result': result})

    return app


# =============================================================================
# Main
# =============================================================================

def main():
    log.info('Lightroom Macro Panel %s 시작', APP_VERSION)
    config = ConfigManager()
    engine = WorkflowEngine(config)
    app = create_flask_app(engine)

    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    def _run_flask():
        app.run(host='0.0.0.0', port=FLASK_PORT, debug=False, use_reloader=False)

    threading.Thread(target=_run_flask, daemon=True).start()
    log.info('Flask 서버 시작: http://0.0.0.0:%d', FLASK_PORT)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info('종료')


if __name__ == '__main__':
    main()

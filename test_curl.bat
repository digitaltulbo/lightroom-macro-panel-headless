@echo off
curl -X POST http://127.0.0.1:8765/webhook/start -H "Content-Type: application/json" -d "{\"package\":\"basic\"}"
pause

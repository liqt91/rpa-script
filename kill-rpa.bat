@echo off
chcp 65001 > nul
echo === RPA Process Killer ===

:: 结束 Python FastAPI 进程
echo [1/3] Killing Python processes...
taskkill /F /FI "WINDOWTITLE eq rpa*" /T 2> nul
taskkill /F /IM python.exe /FI "STATUS eq RUNNING" 2> nul
taskkill /F /IM pythonw.exe /FI "STATUS eq RUNNING" 2> nul

:: 结束占用 8000 端口的进程
netstat -ano | findstr :8000 > nul
if %errorlevel% equ 0 (
    echo [2/3] Killing process on port 8000...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
        taskkill /F /PID %%a 2> nul
    )
)

:: 可选参数 /chrome 结束 Chrome 扩展进程
if "%1"=="/chrome" (
    echo [3/3] Killing Chrome extension processes...
    taskkill /F /IM chrome.exe /FI "WINDOWTITLE eq *扩展*" 2> nul
)

echo Done.
pause

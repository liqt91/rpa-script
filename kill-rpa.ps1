# 强制结束 RPA 相关进程（解决 Uvicorn ctrl+c 无法退出的问题）
param(
    [switch]$Chrome,
    [switch]$All
)

Write-Host "=== RPA Process Killer ===" -ForegroundColor Cyan

# 1. 结束 Python FastAPI 进程（按标题或端口匹配）
$pythonProcs = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -like "*rpa*" -or
    $_.CommandLine -like "*main.py*" -or
    $_.CommandLine -like "*fastapi*" -or
    $_.CommandLine -like "*uvicorn*"
}
if ($pythonProcs) {
    Write-Host "Found Python processes:" -ForegroundColor Yellow
    $pythonProcs | ForEach-Object {
        Write-Host "  PID $($_.Id) - $($_.CommandLine.Substring(0, [Math]::Min(80, $_.CommandLine.Length)))..."
        Stop-Process -Id $_.Id -Force
    }
    Write-Host "Python processes killed." -ForegroundColor Green
} else {
    Write-Host "No Python processes found." -ForegroundColor Gray
}

# 2. 结束占用 8000 端口的进程（FastAPI 默认端口）
$portProcs = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -Property OwningProcess -Unique
if ($portProcs) {
    Write-Host "Found process(es) on port 8000:" -ForegroundColor Yellow
    $portProcs | ForEach-Object {
        try {
            $proc = Get-Process -Id $_.OwningProcess -ErrorAction Stop
            Write-Host "  PID $($proc.Id) - $($proc.ProcessName)"
            Stop-Process -Id $proc.Id -Force
        } catch {}
    }
    Write-Host "Port 8000 freed." -ForegroundColor Green
}

# 3. 可选：结束 Chrome 扩展相关进程
if ($Chrome -or $All) {
    $chromeProcs = Get-Process -Name chrome -ErrorAction SilentlyContinue | Where-Object {
        $_.MainWindowTitle -like "*扩展*" -or
        $_.MainWindowTitle -like "*Extension*" -or
        $_.CommandLine -like "*--load-extension*"
    }
    if ($chromeProcs) {
        Write-Host "Found Chrome extension processes:" -ForegroundColor Yellow
        $chromeProcs | ForEach-Object {
            Write-Host "  PID $($_.Id) - $($_.MainWindowTitle)"
            Stop-Process -Id $_.Id -Force
        }
        Write-Host "Chrome extension processes killed." -ForegroundColor Green
    }
}

# 4. 可选：结束所有 chromedriver / msedgedriver
if ($All) {
    @('chromedriver', 'msedgedriver', 'geckodriver') | ForEach-Object {
        $drivers = Get-Process -Name $_ -ErrorAction SilentlyContinue
        if ($drivers) {
            Write-Host "Killing $_ processes..." -ForegroundColor Yellow
            $drivers | Stop-Process -Force
        }
    }
}

Write-Host "Done." -ForegroundColor Green

# install-dsh-plugin.ps1 — 一键安装 rpa-dsh-plugin 到 dsh web profile（本地形态）
#
# 用户在仓库根执行：
#   powershell -ExecutionPolicy Bypass -File scripts/install-dsh-plugin.ps1
#
# 脚本自动完成：
#   1. 检查 pnpm（缺失则 npm i -g pnpm）
#   2. dsh plugin --profile web add file:./rpa-dsh-plugin   ← dsh 官方安装方式（bundle 自动协调）
#   3. 清理旧的手动安装遗留（profile 层重复 insert）
#   4. 写 profile 层覆盖：backendCommand/backendCwd 指向本仓库 venv（机器相关路径）
#   5. dsh --dump-config 验证 rpa 实例
#   6. 提示重启 dsh web
#
# npm 形态安装（无需本脚本）：
#   dsh plugin --profile web add rpa-dsh-plugin
#   # 插件激活时自动在包内 python/ 自举 venv（uv 优先）

$ErrorActionPreference = "Stop"

# PowerShell 5.1 下 native 命令 stderr + ErrorActionPreference=Stop 会抛
# NativeCommandError 中断脚本；捕获外部命令输出前临时降级。
function Invoke-NativeCapture {
  param([scriptblock]$Block, [string[]]$ArgsList)
  $prevEA = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    return & $Block @ArgsList 2>&1 | Out-String
  } finally {
    $ErrorActionPreference = $prevEA
  }
}

$root = Split-Path -Parent $PSScriptRoot
$profileDir = Join-Path $env:USERPROFILE ".dsh\profiles\web"
$pluginName = "rpa-dsh-plugin"

Write-Host "== rpa-dsh-plugin 一键安装（dsh web profile）=="

# ---------- 0) 检查 dsh ----------
if (-not (Get-Command dsh -ErrorAction SilentlyContinue)) {
  throw "未找到 dsh 命令。请先安装 DeepSeek Harness (dsh) 并加入 PATH。"
}
Write-Host "dsh: $((Invoke-NativeCapture { dsh } -ArgsList @('--version')).Trim())"

# ---------- 1) 检查 pnpm ----------
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
  Write-Host "未检测到 pnpm，正在全局安装（npm i -g pnpm）…"
  npm install -g pnpm
  if ($LASTEXITCODE -ne 0) { throw "pnpm 安装失败" }
}
Write-Host "pnpm: $((Invoke-NativeCapture { pnpm } -ArgsList @('--version')).Trim())"

# ---------- 2) dsh plugin add（官方方式，自动协调 bundles + 应用 bundle patch）----------
Write-Host "`n== dsh plugin --profile web add file:./$pluginName =="
Push-Location $root
try {
  dsh plugin --profile web add "file:./$pluginName"
  if ($LASTEXITCODE -ne 0) { throw "dsh plugin add 失败" }
} finally {
  Pop-Location
}

# ---------- 3) 清理旧手动安装遗留（profile 层重复 insert）----------
$patchFile = Join-Path $profileDir "cordis.patch.yml"
if (Test-Path $patchFile) {
  $content = Get-Content $patchFile -Raw -ErrorAction SilentlyContinue
  # 检测旧式手动 insert（README v0.1 写法：顶层 - insert: 含 id: rpa）
  if ($content -match "(?ms)^\s*-\s*insert:\s*$" -and $content -match "id:\s*rpa\b") {
    Write-Host "`n检测到旧版手动安装遗留（profile 层 insert rpa），已由 bundle patch 取代，正在清理…"
    $newContent = @"
# Your patch layer for this dsh profile, applied after every bundle layer:
# a top-level YAML array of loader patch entries (id-targeted config
# overrides, disables, and insert lists; ``!!js`` expressions allowed).
[]
"@
    [System.IO.File]::WriteAllText($patchFile, $newContent, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  cordis.patch.yml 已还原为空（rpa 实例由插件 bundle patch 提供）"
  }
}

# ---------- 4) 写 profile 层覆盖（机器相关路径：仓库 venv）----------
# bundle patch 提供通用默认（环境变量驱动）；这里写入本机实际路径。
# 注意：profile 层对同 id 是整体替换 config（dsh-app-boot 源码语义），必须写全字段。
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$backendCommand = ('"' + $venvPy + '" -m src.runtime.main')
$overrides = @(
  "# rpa-dsh-plugin 机器相关覆盖（由 install-dsh-plugin.ps1 写入）",
  "# 通用默认见插件自带 cordis.patch.yml；此处仅覆盖本机路径。",
  "- id: rpa",
  "  name: $pluginName",
  "  config:",
  "    backendUrl: !!js process.env.RPA_BACKEND_URL || ''",
  "    token: !!js process.env.RPA_API_TOKEN || ''",
  "    username: !!js process.env.RPA_USERNAME || 'admin'",
  "    password: !!js process.env.RPA_PASSWORD || 'admin123'",
  "    autoStartBackend: true",
  "    backendCommand: '$backendCommand'",
  "    backendCwd: '$root'",
  "    browserExecTimeoutMs: !!js Number(process.env.RPA_BROWSER_EXEC_TIMEOUT_MS || 30000)",
  "    waitPollMs: !!js Number(process.env.RPA_WAIT_POLL_MS || 1500)"
)
[System.IO.File]::WriteAllText($patchFile, ($overrides -join "`n") + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Host "`n已写入 profile 覆盖: backendCommand -> $venvPy"

# ---------- 5) 验证 ----------
Write-Host "`n== 验证（dsh --dump-config）=="
$dump = Invoke-NativeCapture { dsh } -ArgsList @('--profile', 'web', '--dump-config')
$match = $dump | Select-String -Pattern "id: rpa" 
if ($match) {
  Write-Host "✅ rpa 实例已加载"
  $dump | Select-String -Pattern "backendCommand|backendCwd" | Select-Object -First 4 | ForEach-Object { Write-Host "   $($_.Line.Trim())" }
} else {
  Write-Host "⚠ 未在配置树中找到 rpa 实例，请检查上方输出"
}

# ---------- 6) 提示 ----------
Write-Host "`n======================================================"
Write-Host " 安装完成。重启 dsh web 激活插件："
Write-Host "   1. 关闭当前 dsh web 窗口"
Write-Host "   2. 重新运行: dsh web"
Write-Host " 重启后：侧边栏出现「RPA 控制台」、13 个 rpa_* 工具、"
Write-Host "          /rpa 斜杠命令、后端自动拉起、编辑器可用。"
Write-Host "======================================================"

# build-plugin-package.ps1 — 构建 rpa-dsh-plugin 的 npm 发布包
#
# 职责：
#   1. 把后端最小运行集（src 7 个包 + commands/ 指令 JSON + requirements.txt）
#      同步到 rpa-dsh-plugin/python/（npm 形态插件自举用）
#   2. 可选：构建前端产物并放入 python/static/workflow-editor（编辑器开箱即用）
#   3. （由 npm pack 自动触发时）打 tarball
#
# 用法：
#   powershell -File scripts/build-plugin-package.ps1            # 全量（后端 + 前端 + 仅同步）
#   powershell -File scripts/build-plugin-package.ps1 -BackendOnly  # 只同步后端源码
#   （npm pack / npm publish 会自动通过 package.json 的 prepack 钩子调用全量）
#
# 注意：本脚本在仓库根执行；--BackendOnly 供开发期快速同步。

param(
  [switch]$BackendOnly,
  [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot          # 仓库根
$pkg  = Join-Path $root "rpa-dsh-plugin"
$py   = Join-Path $pkg "python"

Write-Host "== 构建 rpa-dsh-plugin npm 包 =="
Write-Host "  仓库根: $root"

# ---------- 1) 同步后端源码最小集 ----------
$srcPkgs = @("config", "dtypes", "providers", "repo", "runtime", "service", "shared")
foreach ($p in $srcPkgs) {
  $from = Join-Path $root "src\$p"
  $to   = Join-Path $py "src\$p"
  if (-not (Test-Path $from)) { throw "缺少 src/$p" }
  Write-Host "  sync src/$p -> python/src/$p"
  # 排除测试/缓存
  robocopy $from $to /E /XD __pycache__ tests /XF "*.pyc" /NFL /NDL /NJH /NJS /NP | Out-Null
}
# commands/ 指令 JSON（后端 _ROOT/commands 读取）
robocopy (Join-Path $root "commands") (Join-Path $py "commands") /E /NFL /NDL /NJH /NJS /NP | Out-Null
Write-Host "  sync commands/ -> python/commands/"

# requirements.txt（pip/uv 自举用）
Copy-Item (Join-Path $root "requirements.txt") (Join-Path $py "requirements.txt") -Force
Write-Host "  sync requirements.txt"

# 运行时数据目录骨架（data/ 由 RPA_DATA_DIR 重定向，不打包；但建目录避免首启告警）
New-Item -ItemType Directory -Path (Join-Path $py "data") -Force | Out-Null

if ($BackendOnly) {
  Write-Host "`n✅ 后端同步完成（python/ 就绪）。"
  exit 0
}

# ---------- 2) 前端产物（可选） ----------
if (-not $SkipFrontend) {
  $feDir = Join-Path $root "src\ui\workflow-editor"
  if (Test-Path (Join-Path $feDir "node_modules\.bin\vite.cmd")) {
    Write-Host "`n== 构建前端产物 =="
    Push-Location $feDir
    try {
      # PowerShell 5.1 下 ErrorActionPreference=Stop 时，native 命令的 stderr
      # （npm banner/警告）会抛 NativeCommandError 中断脚本；临时降级再取真实退出码。
      $prevEA = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      try {
        $buildOut = npm run build 2>&1 | Out-String
        $buildExit = $LASTEXITCODE
      } finally {
        $ErrorActionPreference = $prevEA
      }
      if ($buildExit -ne 0) {
        Write-Host "  ⚠ vite build 失败（$($buildOut.Split("`n") | Select-Object -Last 2)）"
        Write-Host "  将回退使用已有产物（若 src/runtime/static/workflow-editor/ 存在）"
      }
    } finally { Pop-Location }
    # 产物在 src/runtime/static/workflow-editor/，拷入 python/static/
    $staticFrom = Join-Path $root "src\runtime\static\workflow-editor"
    $staticTo   = Join-Path $py "static\workflow-editor"
    if (Test-Path $staticFrom) {
      robocopy $staticFrom $staticTo /E /NFL /NDL /NJH /NJS /NP | Out-Null
      Write-Host "  sync 前端产物 -> python/static/workflow-editor/"
    } else {
      Write-Host "  ⚠ 未找到前端产物目录，跳过"
    }
  } else {
    Write-Host "`n⚠ 前端依赖未安装（node_modules 缺失），跳过前端构建——npm 包内编辑器将不可用。"
    Write-Host "  先执行: cd src/ui/workflow-editor && npm install"
  }
} else {
  Write-Host "`n（跳过前端构建）"
}

# ---------- 3) venv 预置（懒启动零等待：npm 包内自带可用 venv）----------
# 首次构建时创建（1-3 分钟，uv 优先）；已存在则复用（幂等）。
# 发布后插件在任意机器启动后端无需再装依赖。
$venvPy = Join-Path $py "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  Write-Host "`n== 预置 venv（首次构建，1-3 分钟）=="
  Push-Location $py
  # PowerShell 5.1 下 native stderr（uv 进度/警告）会抛 NativeCommandError → 临时降级
  $prevEA = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $c1 = -1; $c2 = -1
    if (Get-Command uv -ErrorAction SilentlyContinue) {
      uv venv venv --python 3.12; $c1 = $LASTEXITCODE
      if ($c1 -eq 0) { uv pip install -p venv -r requirements.txt; $c2 = $LASTEXITCODE }
    } else {
      python -m venv venv; $c1 = $LASTEXITCODE
      if ($c1 -eq 0) { .\venv\Scripts\pip install -r requirements.txt; $c2 = $LASTEXITCODE }
    }
    if ($c1 -ne 0 -or $c2 -ne 0) {
      Write-Host "  ⚠ venv 预置失败（uv/pip 退出码 $c1/$c2），npm 包将不含 venv（首次启动仍需在线安装）"
    } else {
      Write-Host "  ✅ venv 预置完成"
    }
  } finally {
    Pop-Location
    $ErrorActionPreference = $prevEA
  }
} else {
  Write-Host "`n== venv 已存在，复用（$(Join-Path $py 'venv')）=="
}

# 关键：删除 uv 自动生成的 venv/.gitignore（内容为 `*`）。
# 否则 npm 打包时 ignore-walk 会逐目录应用该 .gitignore，整个 venv 被排除出 tarball。
$venvGi = Join-Path $py "venv\.gitignore"
if (Test-Path $venvGi) {
  Remove-Item $venvGi -Force
  Write-Host "  已删除 venv/.gitignore（防止 npm 打包排除 venv）"
}

# 瘦身：删除测试目录 / 帮助文档 / pythonwin IDE 组件（运行不需要，约省 15MB）
$venvRoot = Join-Path $py "venv"
$removed = 0
Get-ChildItem $venvRoot -Recurse -Directory -Filter "__pycache__" -Force -ErrorAction SilentlyContinue | ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue; $removed++ }
Get-ChildItem $venvRoot -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -in @("tests", "test") } | ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue; $removed++ }
foreach ($f in @("Lib\site-packages\PyWin32.chm", "Lib\site-packages\pythonwin")) {
  $p = Join-Path $venvRoot $f
  if (Test-Path $p) { Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue; $removed++ }
}
if ($removed -gt 0) { Write-Host "  venv 瘦身完成（清理 $removed 项缓存/测试/文档）" }

# ---------- 4) 清理 + 汇总 ----------
# 删除 __pycache__ 残留（robocopy 排除不彻底时）
Get-ChildItem $py -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$sizeMB = [math]::Round(((Get-ChildItem $py -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 2)
$fileCount = (Get-ChildItem $py -Recurse -File).Count
Write-Host "`n✅ python/ 就绪: $fileCount 文件, $sizeMB MB"
Write-Host "   npm pack / npm publish 将自动包含 python/（package.json files 白名单）"

# rollback-rpa.ps1 — 一键回滚 rpa-dsh-plugin，恢复 dsh web 可启动状态
# 用法: powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\profiles\web\rollback-rpa.ps1"
$ErrorActionPreference = "Stop"
$web = Join-Path $env:USERPROFILE ".dsh\profiles\web"
if (-not (Test-Path $web)) { Write-Host "未找到 profile: $web"; exit 1 }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

# 1) 备份配置 + 插件实体（node_modules 可再生，不备份）
$backup = Join-Path $env:USERPROFILE ".dsh\profiles\web-backup-$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
foreach ($f in @("package.json", "cordis.yml", "cordis.patch.yml", "pnpm-workspace.yaml")) {
  if (Test-Path "$web\$f") { Copy-Item "$web\$f" "$backup\$f" }
}
if (Test-Path "$web\rpa-dsh-plugin") { Copy-Item "$web\rpa-dsh-plugin" "$backup\rpa-dsh-plugin" -Recurse -Force }
Write-Host "[1/4] 已备份 -> $backup"

# 2) package.json 还原为 bundles-only
$pkg = @'
{
  "name": "dsh-profile-web",
  "private": true,
  "dependencies": {},
  "dsh": {
    "profile": {
      "bundles": [
        "@deepseek-ai/dsh-base",
        "@deepseek-ai/dsh-web-app"
      ]
    }
  }
}
'@
[System.IO.File]::WriteAllText("$web\package.json", $pkg, [System.Text.UTF8Encoding]::new($false))
Write-Host "[2/4] package.json 已还原"

# 3) cordis.patch.yml 清空
$patch = @'
# Your patch layer for this dsh profile, applied after every bundle layer:
# a top-level YAML array of loader patch entries (id-targeted config
# overrides, disables, and insert lists; `!!js` expressions allowed).
[]
'@
[System.IO.File]::WriteAllText("$web\cordis.patch.yml", $patch, [System.Text.UTF8Encoding]::new($false))
Write-Host "[3/4] cordis.patch.yml 已清空"

# 4) 移除插件实体 + 剪除依赖
Remove-Item "$web\rpa-dsh-plugin" -Recurse -Force -ErrorAction SilentlyContinue
Push-Location $web
pnpm install 2>&1 | Select-Object -Last 3
Pop-Location
Write-Host "[4/4] 回滚完成。重启 dsh web 即为无插件状态。备份在: $backup"

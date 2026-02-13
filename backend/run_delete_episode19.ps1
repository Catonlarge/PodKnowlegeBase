# 删除 Episode 19 脚本 - 在 backend 目录下执行
# 用法: 右键 -> 使用 PowerShell 运行，或在 backend 目录下执行 .\run_delete_episode19.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# 激活虚拟环境（如存在）
$venvPath = Join-Path $ScriptDir "venv-kb\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    & $venvPath
}

Write-Host "当前目录: $(Get-Location)"
Write-Host "执行: python scripts/delete_episode.py 19"
Write-Host ""

python scripts/delete_episode.py 19

Write-Host ""
Write-Host "完成。若成功会显示 '已删除 Episode 19 及所有关联数据'"

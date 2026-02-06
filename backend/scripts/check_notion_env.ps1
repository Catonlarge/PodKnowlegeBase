# Notion 环境变量诊断脚本
# 使用方法：在 PowerShell 中运行 .\check_notion_env.ps1

Write-Host "`n=== Notion 环境变量诊断 ===" -ForegroundColor Cyan

# 检查环境变量
Write-Host "`n1. 检查当前会话环境变量:" -ForegroundColor Yellow
$key = $env:NOTION_API_KEY
if ($key) {
    $masked = $key.Substring(0, [Math]::Min(8, $key.Length)) + "..." + $key.Substring([Math]::Max(0, $key.Length - 4))
    Write-Host "   NOTION_API_KEY: $masked" -ForegroundColor Green
} else {
    Write-Host "   NOTION_API_KEY: (未设置)" -ForegroundColor Red
}

# 检查用户级环境变量
Write-Host "`n2. 检查用户级环境变量（持久化）:" -ForegroundColor Yellow
$userKey = [System.Environment]::GetEnvironmentVariable("NOTION_API_KEY", "User")
if ($userKey) {
    $masked = $userKey.Substring(0, [Math]::Min(8, $userKey.Length)) + "..." + $userKey.Substring([Math]::Max(0, $userKey.Length - 4))
    Write-Host "   NOTION_API_KEY: $masked" -ForegroundColor Green
} else {
    Write-Host "   NOTION_API_KEY: (未设置)" -ForegroundColor Red
}

# 检查系统级环境变量
Write-Host "`n3. 检查系统级环境变量:" -ForegroundColor Yellow
$systemKey = [System.Environment]::GetEnvironmentVariable("NOTION_API_KEY", "Machine")
if ($systemKey) {
    $masked = $systemKey.Substring(0, [Math]::Min(8, $systemKey.Length)) + "..." + $systemKey.Substring([Math]::Max(0, $systemKey.Length - 4))
    Write-Host "   NOTION_API_KEY: $masked" -ForegroundColor Green
} else {
    Write-Host "   NOTION_API_KEY: (未设置)" -ForegroundColor Gray
}

# 测试 Python 脚本中的环境变量
Write-Host "`n4. 测试 Python 脚本能否读取环境变量:" -ForegroundColor Yellow
$testCode = @'
import os
key = os.environ.get("NOTION_API_KEY")
if key:
    print(f"Python 可以读取: {key[:8]}...{key[-4:]}")
else:
    print("Python 无法读取环境变量")
'@
$pythonPath = ".\venv-kb\Scripts\python.exe"
if (Test-Path $pythonPath) {
    $result = & $pythonPath -c $testCode 2>&1
    Write-Host "   $result"
} else {
    Write-Host "   Python 虚拟环境未找到" -ForegroundColor Red
}

# 提供设置建议
Write-Host "`n=== 设置建议 ===" -ForegroundColor Cyan
if (-not $userKey -and -not $systemKey) {
    Write-Host "`n环境变量未设置，请使用以下命令设置：`n" -ForegroundColor Yellow
    Write-Host "方法 1 - 临时设置（仅当前会话）:" -ForegroundColor White
    Write-Host '  $env:NOTION_API_KEY = "your_notion_api_token_here"' -ForegroundColor Gray
    Write-Host "`n方法 2 - 永久设置（需要重启终端）:" -ForegroundColor White
    Write-Host '  setx NOTION_API_KEY "your_notion_api_token_here"' -ForegroundColor Gray
} elseif (-not $key) {
    Write-Host "`n环境变量已设置，但当前会话未加载。请运行：`n" -ForegroundColor Yellow
    Write-Host '  $env:NOTION_API_KEY = [System.Environment]::GetEnvironmentVariable("NOTION_API_KEY", "User")' -ForegroundColor Gray
    Write-Host "`n或者关闭并重新打开终端窗口。" -ForegroundColor Gray
} else {
    Write-Host "`n环境变量配置正确！" -ForegroundColor Green
    Write-Host "可以运行测试脚本: `n  .\venv-kb\Scripts\python.exe scripts\test_notion_connection.py" -ForegroundColor Gray
}

Write-Host "`n"

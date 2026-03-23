# 激活项目根目录下的 .venv（解决默认 ExecutionPolicy 禁止运行 Activate.ps1 的问题）
# 用法：在项目根目录执行 .\scripts\ActivateVenv.ps1
# 说明：仅对「当前 PowerShell 进程」临时设为 Bypass，关闭窗口后不影响系统策略

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ActivatePs1 = Join-Path $Root ".venv\Scripts\Activate.ps1"

if (-not (Test-Path $ActivatePs1)) {
    Write-Host "未找到 $ActivatePs1 ，请先执行: python -m venv .venv" -ForegroundColor Red
    exit 1
}

# 仅当前进程允许运行脚本，从而可执行 Activate.ps1
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& $ActivatePs1

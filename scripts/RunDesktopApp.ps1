# 官方桌面客户端启动（Windows）
# 若存在 .venv 则优先使用其中的 Python，无需先手动 Activate.ps1
# 桌面默认连本机 8765 房间服务；未启动时会报 WinError 10061，故在端口空闲时自动另开窗口启服。
# 某些 PowerShell 场景里 PSScriptRoot 可能为空，这里做多重兜底，避免项目根目录解析失败。
$ScriptDir = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ScriptDir) -and $PSCommandPath) {
    $ScriptDir = Split-Path -Parent $PSCommandPath
}
if ([string]::IsNullOrWhiteSpace($ScriptDir) -and $MyInvocation.MyCommand.Path) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($ScriptDir)) {
    throw "无法解析脚本所在目录，请确认当前脚本是从文件执行，而不是粘贴到控制台里运行。"
}
$Root = Split-Path -Parent $ScriptDir
$env:PYTHONPATH = Join-Path $Root "src"
# 内嵌网页需解析 templates / static；打包或从其他目录启动时也依赖此路径
$env:MF_PROJECT_ROOT = $Root
Set-Location $Root
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$PythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

function Test-MfRoomPortOpen {
    param([int]$Port = 8765, [int]$TimeoutMs = 600)
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $c.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs)) {
            return $false
        }
        return $c.Connected
    }
    catch {
        return $false
    }
    finally {
        try {
            if ($c.Connected) { $c.Close() }
        }
        catch { }
        $c.Dispose()
    }
}

# 设为 0 可跳过自动启服（例如你只连远程房间服务时）：$env:MF_AUTO_START_ROOM_SERVER = "0"
if ($env:MF_AUTO_START_ROOM_SERVER -ne "0") {
    $portOk = Test-MfRoomPortOpen
    if (-not $portOk) {
        $roomScript = Join-Path $Root "scripts\RunRoomServer.ps1"
        Write-Host "未检测到本机 8765 房间服务，正在新窗口启动 RunRoomServer ..." -ForegroundColor Yellow
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoExit",
            "-ExecutionPolicy", "Bypass",
            "-File", $roomScript
        ) | Out-Null
        Start-Sleep -Seconds 2
    }
}

$DesktopMain = Join-Path $Root "apps\DesktopApp\Main.py"
& $PythonExe $DesktopMain

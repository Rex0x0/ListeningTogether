# 官方房间服务启动（Windows）
# 若存在 .venv 则优先使用其中的 Python，无需先手动 Activate.ps1
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $Root "src"
Set-Location $Root
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$PythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
& $PythonExe (Join-Path $Root "apps\RoomServer\Main.py")

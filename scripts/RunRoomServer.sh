#!/usr/bin/env bash
# 官方房间服务启动（Unix）
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src"
cd "$ROOT" || exit 1
exec python "$ROOT/apps/RoomServer/Main.py"

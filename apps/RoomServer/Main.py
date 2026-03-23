"""
房间服务端唯一正式发布入口：uvicorn 加载 FastAPI 应用。
"""

import sys
from pathlib import Path

# 仓库根目录加入路径，保证可导入 src/MusicFriend
_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import uvicorn  # noqa: E402

from MusicFriend.Server.App import createApp  # noqa: E402


def main() -> None:
    host = "0.0.0.0"
    port = int(__import__("os").environ.get("MF_PORT", "8765"))
    uvicorn.run(createApp, host=host, port=port, factory=True)


if __name__ == "__main__":
    main()

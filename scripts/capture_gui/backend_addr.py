"""capture_gui 共享：解析后端地址（随机端口自适应）。

优先级：RPA_BACKEND_URL 环境变量 > 端口文件（RPA_DATA_DIR/backend.port、
仓库 data/backend.port）> 兜底 8000（旧版）。
"""

import os


def backend_base() -> str:
    env_url = os.environ.get("RPA_BACKEND_URL", "").strip().rstrip("/")
    if env_url:
        return env_url
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = []
    if os.environ.get("RPA_DATA_DIR"):
        candidates.append(os.path.join(os.environ["RPA_DATA_DIR"], "backend.port"))
    candidates.append(os.path.join(root, "data", "backend.port"))
    for cand in candidates:
        if not os.path.isfile(cand):
            continue
        try:
            with open(cand, "r", encoding="utf-8") as f:
                port = f.read().strip()
            if port.isdigit():
                return f"http://127.0.0.1:{port}"
        except OSError:
            pass
    return "http://127.0.0.1:8000"

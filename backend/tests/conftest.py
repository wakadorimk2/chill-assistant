"""
pytest 共通設定

backend ディレクトリを sys.path に通し、`from app...` 形式の import を可能にする。
"""

import sys
from pathlib import Path

# backend/ を sys.path に追加 (backend/app/... を import 可能にする)
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

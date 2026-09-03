import os
import tempfile
from pathlib import Path

# Configure the app for an isolated throwaway environment *before* dc_api is
# imported anywhere (settings are read at import time).
_tmp = Path(tempfile.mkdtemp(prefix="foreman_test_"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(_tmp / 'test.db').as_posix()}")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("STORAGE_DIR", str(_tmp / "files"))
os.environ.setdefault("JOB_BACKEND", "inline")
os.environ.setdefault("VLM_BASE_URL", "")
os.environ.setdefault("OCR_PROVIDER", "none")

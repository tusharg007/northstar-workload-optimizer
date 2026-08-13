"""Download and verify the exact Metabase OSS JAR used by Gate 6."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import tempfile
from urllib.request import urlopen

URL = "https://downloads.metabase.com/v0.63.2.x/metabase.jar"
SHA256 = "dc719b2dce60e0fae8d351dc0d44a59f0da696245f10bfb2882aa20c0506c858"
TARGET = Path(__file__).resolve().parent / ".runtime" / "metabase.jar"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main() -> int:
    if TARGET.is_file() and digest(TARGET) == SHA256:
        print(f"PASS: Metabase artifact already verified at {TARGET}")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=TARGET.parent, delete=False) as temporary:
        temp_path = Path(temporary.name)
        with urlopen(URL, timeout=60) as response:
            shutil.copyfileobj(response, temporary, length=1024 * 1024)
    actual = digest(temp_path)
    if actual != SHA256:
        temp_path.unlink(missing_ok=True)
        print(f"FAIL: Metabase artifact SHA-256 mismatch: expected {SHA256}, got {actual}")
        return 1
    temp_path.replace(TARGET)
    print(f"PASS: downloaded Metabase 0.63.2.7 ({SHA256}) to {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

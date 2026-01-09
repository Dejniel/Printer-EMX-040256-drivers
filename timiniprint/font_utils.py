import os
import subprocess
from typing import Optional

from PIL import ImageFont


def find_monospace_bold_font() -> Optional[str]:
    fc_match = _find_fc_match()
    if fc_match:
        return fc_match
    return _find_common_monospace()


def _find_fc_match() -> Optional[str]:
    if not _has_executable("fc-match"):
        return None
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}\n", "monospace:style=Bold"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return None
    path = (result.stdout or "").strip()
    if path and os.path.isfile(path):
        return path
    return None


def _has_executable(name: str) -> bool:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(path, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return True
    return False


def _find_common_monospace() -> Optional[str]:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-B.ttf",
        "/Library/Fonts/Andale Mono.ttf",
        "/Library/Fonts/Menlo.ttc",
        "C:\\Windows\\Fonts\\consolab.ttf",
        "C:\\Windows\\Fonts\\courbd.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def load_font(path: Optional[str], size: int) -> ImageFont.FreeTypeFont:
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()

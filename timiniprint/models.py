from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, List

DATA_PATH = Path(__file__).resolve().parent / "data" / "printer_models.json"


@dataclass(frozen=True)
class PrinterModel:
    model_no: str
    model: int
    size: int
    paper_size: int
    print_size: int
    one_length: int
    head_name: str
    can_change_mtu: bool
    dev_dpi: int
    img_print_speed: int
    text_print_speed: int
    img_mtu: int
    new_compress: bool
    paper_num: int
    interval_ms: int
    thin_energy: int
    moderation_energy: int
    deepen_energy: int
    text_energy: int
    has_id: bool
    use_spp: bool
    new_format: bool
    can_print_label: bool
    label_value: str
    back_paper_num: int
    a4xii: bool = False
    add_mor_pix: Optional[bool] = None

    @property
    def width(self) -> int:
        return self.paper_size


class PrinterModelRegistry:
    _cache: Dict[Path, "PrinterModelRegistry"] = {}

    def __init__(self, models: Iterable[PrinterModel]) -> None:
        self._models = list(models)

    @classmethod
    def load(cls, path: Path = DATA_PATH) -> "PrinterModelRegistry":
        key = path.resolve()
        cached = cls._cache.get(key)
        if cached:
            return cached
        raw = json.loads(path.read_text(encoding="utf-8"))
        models = [PrinterModel(**item) for item in raw]
        registry = cls(models)
        cls._cache[key] = registry
        return registry

    @property
    def models(self) -> List[PrinterModel]:
        return list(self._models)

    def get(self, model_no: str) -> Optional[PrinterModel]:
        for model in self._models:
            if model.model_no == model_no:
                return model
        return None

    def detect_from_device_name(self, name: str) -> Optional[PrinterModel]:
        if not name:
            return None
        name_lower = name.lower()
        match = None
        for model in self._models:
            if model.head_name and name_lower.startswith(model.head_name.lower()):
                if match is None or len(model.head_name) > len(match.head_name):
                    match = model
        if match:
            return match
        for model in self._models:
            if name_lower.startswith(model.model_no.lower()):
                if match is None or len(model.model_no) > len(match.model_no):
                    match = model
        return match

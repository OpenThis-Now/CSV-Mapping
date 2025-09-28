from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Thresholds:
    vendor_min: int = 80
    product_min: int = 75
    overall_accept: int = 85
    weight_vendor: float = 0.6
    weight_product: float = 0.4
    sku_exact_boost: int = 10
    numeric_mismatch_penalty: int = 8

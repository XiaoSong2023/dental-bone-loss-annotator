"""骨吸收比例的区间归属（2018 EFP/AAP 影像学骨吸收范围）。

⚠️ **本软件不下分期分级结论。**
   2018 新分类的 Stage 需要结合缺牙数、探诊深度、根分叉病变、咬合创伤、
   咀嚼功能等临床资料；Grade 还需要病史与危险因素（吸烟、糖尿病）。
   仅凭一张全景片给出 I/II/III/IV 或 A/B/C 是不严谨的。

   所以软件只输出两件事实：
     · 骨吸收比例（最重位点）
     · 骨吸收年龄比 = 骨吸收比例 ÷ 年龄
   外加骨吸收比例落在 2018 分类的哪个**影像学区间**（<15% / 15%–33% / >33%）。
   最终分期分级由医生结合临床判断。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .formula import FormulaConfig


@dataclass
class GradingConfig:
    # 2018 分类的影像学骨吸收范围分界
    interval_i_max: float = 0.15        # < 15%      冠 1/3
    interval_ii_max: float = 0.33       # 15% – 33%  冠 1/3
    # 校验
    min_root_px: float = 20.0
    ratio_warn_above: float = 1.0

    # ── 序列化 ──────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "interval": {"I_max": self.interval_i_max, "II_max": self.interval_ii_max},
            "validation": {
                "min_root_px": self.min_root_px,
                "ratio_warn_above": self.ratio_warn_above,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GradingConfig":
        base = cls()
        # 兼容旧版把阈值写在 "stage" 段的配置文件
        seg = d.get("interval") or d.get("stage") or {}
        v = d.get("validation", {})
        return cls(
            interval_i_max=float(seg.get("I_max", base.interval_i_max)),
            interval_ii_max=float(seg.get("II_max", base.interval_ii_max)),
            min_root_px=float(v.get("min_root_px", base.min_root_px)),
            ratio_warn_above=float(v.get("ratio_warn_above", base.ratio_warn_above)),
        )

    @classmethod
    def load(cls, path: Path) -> "GradingConfig":
        if path.exists():
            try:
                return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass        # 配置损坏时静默回退到默认值，不阻断使用
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def formula_config(self) -> FormulaConfig:
        return FormulaConfig(
            min_root_px=self.min_root_px, ratio_warn_above=self.ratio_warn_above
        )

    # ── 区间 ────────────────────────────────────────────────────────
    def intervals(self) -> list[tuple[str, str, str]]:
        """(key, 区间文字, 部位描述)，供界面画区间尺。"""
        a = self.interval_i_max * 100
        b = self.interval_ii_max * 100
        return [
            ("I", f"< {a:g}%", "冠 1/3"),
            ("II", f"{a:g}% – {b:g}%", "冠 1/3"),
            ("III", f"> {b:g}%", "根中 1/3 及以上"),
        ]


INTERVAL_LABEL = {
    "I": "< 15%（冠 1/3）",
    "II": "15% – 33%（冠 1/3）",
    "III": "> 33%（根中 1/3 及以上）",
}


def interval_of(ratio: float | None, cfg: GradingConfig) -> str | None:
    """骨吸收比例落在 2018 分类的哪个影像学区间。**不是分期结论。**"""
    if ratio is None:
        return None
    if ratio < cfg.interval_i_max:
        return "I"
    if ratio <= cfg.interval_ii_max:
        return "II"
    return "III"


def interval_text(key: str | None, cfg: GradingConfig) -> str:
    """把区间 key 渲染成带实际阈值的文字（阈值可能被用户改过）。"""
    if key is None:
        return ""
    for k, rng, site in cfg.intervals():
        if k == key:
            return f"{rng}（{site}）"
    return INTERVAL_LABEL.get(key, key)

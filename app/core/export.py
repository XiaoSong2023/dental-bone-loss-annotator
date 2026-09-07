"""导出 —— 患者级汇总表 + 位点级明细表。

每条记录都带 formula_id 与 schema_version，保证「这批数据是用哪个公式算的」可追溯。
换公式后重新导出即可，原始坐标不受影响。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .formula import FORMULAS
from .grading import GradingConfig, interval_of, interval_text
from .models import SCHEMA_VERSION, SURFACE_LABEL, CaseAnnotation
from .project import CaseEntry, Project

# 四个公式全都算一遍导出 —— 反正存的是坐标，多算几遍几乎不要钱，
# 而各组之差正好量化了两种修正各自的影响，做研究时很有用：
#   ① − ②：牙齿倾斜带来的高估
#   ① − ③：把起点从 CEJ 移到 CEJ 下 2mm 带来的差异
COMPARE_IDS = ("direct_v1", "projection_v1", "direct_cej2_v1", "projection_cej2_v1")
COMPARE_NAMES = {
    "direct_v1": "①直线法",
    "projection_v1": "②投影法",
    "direct_cej2_v1": "③直线法2mm",
    "projection_cej2_v1": "④投影法2mm",
}

SUMMARY_HEADER = [
    "病例号", "片数", "最重所在片", "年龄", "性别",
    "最重牙位", "最重邻面", "最重骨吸收比例", "最重骨吸收比例%",
    "骨吸收年龄比", "骨吸收区间(2018影像学)",
    "已标牙数", "根长px", "骨吸收px",
    "该位点_①直线法", "该位点_②投影法", "该位点_③直线法2mm", "该位点_④投影法2mm",
    "倾斜高估(①−②)", "起点差异(①−③)",
    "公式", "状态", "标注时间", "耗时秒", "备注",
]

SITES_HEADER = [
    "病例号", "片名", "牙序", "牙位FDI", "邻面",
    "CEJ_x", "CEJ_y", "CEJ2mm_x", "CEJ2mm_y", "AC_x", "AC_y", "APEX_x", "APEX_y",
    "根长px", "骨吸收px", "骨吸收比例", "骨吸收比例%", "骨吸收区间",
    "比例_①直线法", "比例_②投影法", "比例_③直线法2mm", "比例_④投影法2mm",
    "倾斜高估(①−②)", "起点差异(①−③)",
    "是否最重", "跳过", "警告",
]


def _fmt(v, nd: int = 4):
    if v is None:
        return ""
    if isinstance(v, float):
        return round(v, nd)
    return v


def both_ratios(site, cfg: GradingConfig) -> dict[str, float | None]:
    """同一位点用**四个公式**各算一遍，返回 {公式id: 比例}。

    某公式所需的点没标齐时该项为 None —— 只标了 3 点的旧数据，
    ①② 照样有值，③④ 为空。
    """
    out: dict[str, float | None] = {fid: None for fid in COMPARE_IDS}
    if site is None or site.skipped:
        return out
    fcfg = cfg.formula_config()
    for fid in COMPARE_IDS:
        f = FORMULAS.get(fid)
        m = site.metrics(f, fcfg) if f else None
        out[fid] = m.ratio if m else None
    return out


def _diff(a: float | None, b: float | None) -> float | None:
    return (a - b) if (a is not None and b is not None) else None


def _both_cols(site, cfg: GradingConfig) -> tuple:
    """四个公式的比例 + 两个差值列。"""
    v = both_ratios(site, cfg)
    return (
        *(_fmt(v[fid]) for fid in COMPARE_IDS),
        _fmt(_diff(v["direct_v1"], v["projection_v1"])),      # 倾斜高估
        _fmt(_diff(v["direct_v1"], v["direct_cej2_v1"])),     # 起点差异
    )


def _warn_text(m) -> str:
    if m is None:
        return ""
    names = {
        "too_short": "根长过短",
        "ratio_gt_1": "比值>1需复核",
        "no_loss": "未见吸收",
    }
    return " / ".join(names.get(w, w) for w in m.warnings)


def _patient_meta(anns: list[CaseAnnotation]) -> tuple[str, float | None, str, str]:
    """一个病人的多张片子里，取第一个填了的病例号 / 年龄 / 性别 / 备注。"""
    pid = next((a.patient.id for a in anns if a.patient.id), "")
    age = next((a.patient.age for a in anns if a.patient.age), None)
    sex = next((a.patient.sex for a in anns if a.patient.sex), "")
    note = next((a.patient.note for a in anns if a.patient.note), "")
    return pid, age, sex, note


def summary_rows(project: Project, cfg: GradingConfig,
                 entries: Iterable[CaseEntry] | None = None) -> list[list]:
    """患者级汇总。

    全景片模式：一张片 = 一个病人，一行一张片。
    根尖片模式：一个病人多张片，**跨全部片子取最重位点**再出一行 ——
                「全口最重」本来就该跨全口所有片子取，不是每张片各算各的。
    """
    pool = list(entries) if entries is not None else project.sorted_cases()
    groups: dict[str, list[CaseEntry]] = {}
    for c in pool:
        groups.setdefault(c.patient_key or c.case_id, []).append(c)

    rows: list[list] = []
    for key, films in groups.items():
        anns = [project.load_annotation(f) for f in films]
        pid, age, sex, note = _patient_meta(anns)
        for a in anns:                       # 年龄统一，保证年龄比一致
            a.patient.age = age

        best_res = best_ann = best_film = None
        teeth_n = duration = 0.0
        for film, a in zip(films, anns):
            r = a.compute(cfg)
            teeth_n += a.annotated_tooth_count
            duration += a.duration_s
            if r.worst_ratio is not None and (
                best_res is None or best_res.worst_ratio is None
                or r.worst_ratio > best_res.worst_ratio
            ):
                best_res, best_ann, best_film = r, a, film

        res = best_res if best_res is not None else anns[0].compute(cfg)
        ann = best_ann if best_ann is not None else anns[0]
        wm = res.worst_metrics
        rows.append([
            pid or key,
            len(films),
            best_film.display if best_film else "",
            _fmt(age, 1),
            sex,
            res.worst_tooth.name if res.worst_tooth else "",
            SURFACE_LABEL.get(res.worst_site.surface, "") if res.worst_site else "",
            _fmt(res.worst_ratio),
            "" if res.worst_ratio is None else f"{res.worst_ratio * 100:.1f}%",
            _fmt(res.bone_loss_age_ratio, 6),
            interval_text(res.interval, cfg),
            int(teeth_n),
            _fmt(wm.root_length, 2) if wm else "",
            _fmt(wm.bone_loss, 2) if wm else "",
            *_both_cols(res.worst_site, cfg),
            f"{ann.formula_id}（{COMPARE_NAMES.get(ann.formula_id, '')}）",
            "、".join(sorted({f.status for f in films})),
            max((a.updated for a in anns), default=""),
            _fmt(duration, 1),
            note,
        ])
    return rows


def site_rows(project: Project, cfg: GradingConfig,
              entries: Iterable[CaseEntry] | None = None) -> list[list]:
    """位点级明细：每个测量位点一行，带所属片名。"""
    rows: list[list] = []
    for entry in (entries if entries is not None else project.sorted_cases()):
        ann = project.load_annotation(entry)
        res = ann.compute(cfg)
        pid = ann.patient.id or entry.patient_key or entry.case_id
        for tooth, site, m in ann.all_metrics(cfg):
            if site.filled_count == 0 and not site.skipped:
                continue                      # 完全没标的一侧不占行
            rows.append([
                pid,
                entry.display,
                tooth.index + 1,
                tooth.fdi or "",
                SURFACE_LABEL.get(site.surface, site.surface),
                *[_fmt(getattr(site.get(r), a, None), 2)
                  for r in ("cej", "cej2", "ac", "apex") for a in ("x", "y")],
                _fmt(m.root_length, 2) if m else "",
                _fmt(m.bone_loss, 2) if m else "",
                _fmt(m.ratio) if m else "",
                "" if m is None else f"{m.ratio * 100:.1f}%",
                "" if m is None else interval_text(interval_of(m.ratio, cfg), cfg),
                *_both_cols(site, cfg),
                "★" if site is res.worst_site else "",
                "是" if site.skipped else "",
                _warn_text(m),
            ])
    return rows


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig：中文 Excel 双击打开不乱码
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def export_csv(project: Project, cfg: GradingConfig, out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or project.exports_dir
    p1 = out_dir / "summary.csv"
    p2 = out_dir / "sites.csv"
    write_csv(p1, SUMMARY_HEADER, summary_rows(project, cfg))
    write_csv(p2, SITES_HEADER, site_rows(project, cfg))
    return [p1, p2]


def export_excel(project: Project, cfg: GradingConfig, out_path: Path | None = None) -> Path:
    """两个 sheet：患者级汇总 + 位点级明细。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    out_path = out_path or (project.exports_dir / "汇总.xlsx")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="2F5597")

    for title, header, rows in (
        ("患者级汇总", SUMMARY_HEADER, summary_rows(project, cfg)),
        ("位点级明细", SITES_HEADER, site_rows(project, cfg)),
    ):
        ws = wb.create_sheet(title)
        ws.append(header)
        for c in ws[1]:
            c.font = head_font
            c.fill = head_fill
            c.alignment = Alignment(horizontal="center", vertical="center")
        for r in rows:
            ws.append(r)
        ws.freeze_panes = "A2"
        for i, name in enumerate(header, start=1):
            width = max(len(str(name)) * 2 + 2,
                        *(len(str(r[i - 1])) + 2 for r in rows[:200]), 10) if rows else 14
            ws.column_dimensions[get_column_letter(i)].width = min(width, 32)

    wb.remove(wb["Sheet"])
    wb.save(out_path)
    return out_path


def export_single_json(project: Project, entry: CaseEntry, out_path: Path) -> Path:
    """单例 JSON —— 你最初需求里的「带坐标的 JSON」。

    额外附上一份 _derived 计算结果做参考，但注明它是派生的、以坐标为准。
    """
    import json

    ann: CaseAnnotation = project.load_annotation(entry)
    res = ann.compute(project.grading)
    d = ann.to_dict()
    d["_derived"] = {
        "_note": "派生量，仅供参考。真值以 teeth 里的坐标 + formula.id 重算为准。",
        "schema_version": SCHEMA_VERSION,
        "worst_ratio": _fmt(res.worst_ratio),
        "worst_tooth": res.worst_tooth.name if res.worst_tooth else None,
        "worst_surface": res.worst_site.surface if res.worst_site else None,
        "bone_loss_age_ratio": _fmt(res.bone_loss_age_ratio, 6),
        "interval_2018": interval_text(res.interval, project.grading),
        "_interval_note": "仅为影像学骨吸收范围区间，非 Stage 分期结论。"
                          "分期分级需结合临床资料由医生判断。",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path

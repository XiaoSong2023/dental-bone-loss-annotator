"""核心计算的单元测试 —— 不需要 Qt，可以直接 `python tests/test_core.py` 跑。

重点验证投影法的几何正确性，尤其是「牙齿倾斜时投影法优于直线法」这个卖点。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认 GBK，中文测试名和 ✓/✗ 会炸
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from app.core import formula as F           # noqa: E402
from app.core import geometry as g          # noqa: E402
from app.core.grading import (               # noqa: E402
    GradingConfig,
    interval_of,
    interval_text,
)
from app.core.models import (                # noqa: E402
    CaseAnnotation,
    Pt,
    point_label,
)
from app.core.project import natural_key     # noqa: E402

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        FAILED.append(name)


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) < tol


# ── 几何 ────────────────────────────────────────────────────────────────


def test_geometry() -> None:
    print("\n[geometry]")
    check("投影：同向", close(g.projection_length((0, 10), (0, 100)), 10.0))
    check("投影：反向为负", close(g.projection_length((0, -10), (0, 100)), -10.0))
    check("投影：正交为零", close(g.projection_length((10, 0), (0, 100)), 0.0))
    # 45° 轴上，向量 (10,0) 的投影是 10·cos45
    check("投影：45°", close(g.projection_length((10, 0), (10, 10)), 10 / math.sqrt(2)))
    check("垂足", g.foot_of_perpendicular((5, 5), (0, 0), (0, 10)) == (0.0, 5.0))
    check("退化轴不炸", close(g.projection_length((1, 1), (0, 0)), 0.0))


# ── 公式 ────────────────────────────────────────────────────────────────


def m(points: dict, fid: str = "projection_v1", cfg: F.FormulaConfig | None = None):
    return F.get(fid)(points, cfg or F.FormulaConfig())


def test_formula() -> None:
    print("\n[formula]")
    cfg = F.FormulaConfig()

    # 竖直牙：CEJ(100,100) 根尖(100,300) 根长 200；AC(100,150) 吸收 50 → 0.25
    p = {"cej": (100, 100), "ac": (100, 150), "apex": (100, 300)}
    r = m(p)
    check("竖直牙 根长", close(r.root_length, 200.0))
    check("竖直牙 吸收", close(r.bone_loss, 50.0))
    check("竖直牙 比值 0.25", close(r.ratio, 0.25))

    # AC 在 CEJ 冠方 → 负值，如实保留不截断
    p2 = {"cej": (100, 100), "ac": (100, 80), "apex": (100, 300)}
    r2 = m(p2)
    check("未见吸收为负值", r2.ratio < 0 and close(r2.ratio, -0.1))
    check("未见吸收打标记", "no_loss" in r2.warnings and r2.no_loss)

    # ★ 倾斜牙：AC 偏在牙侧方。投影法应剔除侧向分量，直线法会高估
    #   长轴 (0,200)；AC 相对 CEJ 是 (60, 50)
    p3 = {"cej": (100, 100), "ac": (160, 150), "apex": (100, 300)}
    proj = m(p3, "projection_v1")
    direct = m(p3, "direct_v1")
    check("投影法剔除侧向分量", close(proj.bone_loss, 50.0))
    check("直线法含侧向分量", close(direct.bone_loss, math.hypot(60, 50)))
    check("直线法高估", direct.ratio > proj.ratio,
          f"direct={direct.ratio:.4f} proj={proj.ratio:.4f}")

    # 四个公式：①②从 CEJ 起，③④从 CEJ 下 2mm 起
    check("注册了四个公式", len(F.FORMULAS) == 4, f"got {sorted(F.FORMULAS)}")
    check("①②只需 3 点",
          F.FORMULAS["direct_v1"].needs == F.FORMULAS["projection_v1"].needs
          == ("cej", "ac", "apex"))
    check("③④需要 cej2",
          "cej2" in F.FORMULAS["direct_cej2_v1"].needs
          and "cej2" in F.FORMULAS["projection_cej2_v1"].needs)
    check("默认是投影法", F.DEFAULT_FORMULA_ID == "projection_v1")

    # ★ ③④ = ①② 把起点从 CEJ 换成 CEJ-2mm，终点不变
    #   竖直牙：CEJ(100,100) CEJ2(100,120) AC(100,180) 根尖(100,300)
    p4 = {"cej": (100, 100), "cej2": (100, 120),
          "ac": (100, 180), "apex": (100, 300)}
    check("① CEJ 起点：80/200 = 0.40", close(m(p4, "direct_v1").ratio, 0.40))
    check("③ 2mm 起点：60/180 ≈ 0.3333",
          close(m(p4, "direct_cej2_v1").ratio, 60 / 180))
    check("竖直牙时 ①=② 、③=④",
          close(m(p4, "direct_v1").ratio, m(p4, "projection_v1").ratio)
          and close(m(p4, "direct_cej2_v1").ratio, m(p4, "projection_cej2_v1").ratio))
    check("起点后移 ⇒ 根长变短",
          close(m(p4, "direct_cej2_v1").root_length, 180.0)
          and close(m(p4, "direct_v1").root_length, 200.0))

    # 倾斜牙：③④ 之间同样是「投影剔除侧向分量」
    p5 = {"cej": (100, 100), "cej2": (100, 120),
          "ac": (160, 180), "apex": (100, 300)}
    check("④ 投影剔除侧向分量", close(m(p5, "projection_cej2_v1").bone_loss, 60.0))
    check("③ 含侧向分量", close(m(p5, "direct_cej2_v1").bone_loss, math.hypot(60, 60)))
    check("③ ≥ ④", m(p5, "direct_cej2_v1").ratio > m(p5, "projection_cej2_v1").ratio)

    # 缺 P2 时 ③④ 算不出，①② 照常 —— 旧数据仍然可用
    p3only = {"cej": (100, 100), "cej2": None, "ac": (100, 180), "apex": (100, 300)}
    check("缺 cej2 时 ①仍可算", m(p3only, "direct_v1").ratio > 0)
    for fid in ("direct_cej2_v1", "projection_cej2_v1"):
        try:
            F.get(fid)(p3only, cfg)
            check(f"缺 cej2 时 {fid} 应抛错", False)
        except F.FormulaError:
            check(f"缺 cej2 时 {fid} 应抛错", True)

    # 投影只会缩短分子不会拉长 ⇒ 直线法恒 ≥ 投影法，差值即倾斜带来的高估
    import random
    rnd = random.Random(11)
    worst = 0.0
    for _ in range(300):
        pts = {
            "cej": (rnd.uniform(0, 500), rnd.uniform(0, 500)),
            "ac": (rnd.uniform(0, 500), rnd.uniform(0, 500)),
            "apex": (rnd.uniform(0, 500), rnd.uniform(0, 500)),
        }
        try:
            d_ = m(pts, "direct_v1").ratio
            p_ = m(pts, "projection_v1").ratio
        except F.FormulaError:
            continue
        worst = min(worst, d_ - p_)
    check("直线法恒 ≥ 投影法（300 组随机点）", worst >= -1e-9, f"最小差值 {worst}")

    # 45° 倾斜的牙，AC 严格沿轴 → 比值应等于沿轴距离之比
    L = 200.0
    ux, uy = 1 / math.sqrt(2), 1 / math.sqrt(2)
    cej = (100.0, 100.0)
    apex = (cej[0] + ux * L, cej[1] + uy * L)
    ac = (cej[0] + ux * 60, cej[1] + uy * 60)
    r4 = m({"cej": cej, "ac": ac, "apex": apex})
    check("45° 倾斜牙 比值 0.3", close(r4.ratio, 0.3, 1e-9))

    # 根长过短 → 告警
    r5 = m({"cej": (0, 0), "ac": (0, 2), "apex": (0, 10)}, cfg=F.FormulaConfig(min_root_px=20))
    check("根长过短告警", "too_short" in r5.warnings and not r5.valid)

    # 缺点 → 抛错而不是算出垃圾
    try:
        F.get("projection_v1")({"cej": (0, 0), "ac": None, "apex": (0, 10)}, cfg)
        check("缺点应抛错", False)
    except F.FormulaError:
        check("缺点应抛错", True)

    # 未知公式 id 回退到默认（保证旧数据能打开）
    check("未知公式回退", F.get("nonexistent_v9").id == F.DEFAULT_FORMULA_ID)


# ── 点编号 ──────────────────────────────────────────────────────────────


def test_labels() -> None:
    print("\n[point labels]")
    # 每侧 4 个点（CEJ → CEJ-2mm → AC → 根尖），每颗牙 8 个
    expect = [
        (0, "mesial", "cej", "P1"), (0, "mesial", "cej2", "P2"),
        (0, "mesial", "ac", "P3"), (0, "mesial", "apex", "P4"),
        (0, "distal", "cej", "P5"), (0, "distal", "cej2", "P6"),
        (0, "distal", "ac", "P7"), (0, "distal", "apex", "P8"),
        (1, "mesial", "cej", "P9"), (1, "distal", "apex", "P16"),
        (2, "mesial", "cej", "P17"), (2, "distal", "apex", "P24"),
    ]
    for idx, sf, role, want in expect:
        got = point_label(idx, sf, role)
        check(f"第{idx + 1}颗 {sf} {role} = {want}", got == want, f"got {got}")


# ── 取大 / 分级 ─────────────────────────────────────────────────────────


def test_case() -> None:
    print("\n[case]")
    cfg = GradingConfig()
    ann = CaseAnnotation()
    ann.patient.age = 40

    t1 = ann.add_tooth(fdi=16)
    t1.site("mesial").cej = Pt(100, 100)
    t1.site("mesial").ac = Pt(100, 140)      # 0.20
    t1.site("mesial").apex = Pt(100, 300)
    t1.site("distal").cej = Pt(150, 100)
    t1.site("distal").ac = Pt(150, 190)      # 0.45  ← 本牙取大
    t1.site("distal").apex = Pt(150, 300)

    t2 = ann.add_tooth(fdi=36)
    t2.site("mesial").cej = Pt(300, 400)
    t2.site("mesial").ac = Pt(300, 460)      # 0.30
    t2.site("mesial").apex = Pt(300, 600)
    t2.site("distal").skipped = True         # 跳过的一侧不参与取大

    res = ann.compute(cfg)
    check("全口取最大值", close(res.worst_ratio, 0.45), f"got {res.worst_ratio}")
    check("最重牙位是 16", res.worst_tooth.fdi == 16)
    check("最重邻面是远中", res.worst_site.surface == "distal")
    check("年龄比 = 0.45/40", close(res.bone_loss_age_ratio, 0.01125))
    check("区间 III (0.45>0.33)", res.interval == "III")
    check("已标牙数 2", ann.annotated_tooth_count == 2,
          f"got {ann.annotated_tooth_count}")

    # 跳过一侧不该让这颗牙算「未完成」（按当前公式判定）
    proj = F.get("projection_v1")
    check("跳过一侧仍算完成", t2.complete_for(proj))
    check("只标 3 点时 ③④ 判为未完成",
          not t2.complete_for(F.get("direct_cej2_v1")))

    # 软件不下分期分级结论 —— CaseResult 里不该有 grade / stage 字段
    check("结果里没有 Grade/Stage 结论",
          not hasattr(res, "grade") and not hasattr(res, "stage"))

    # 换公式后重算生效，且**不需要重标**：点一个没动
    before_points = [(s_.cej.as_tuple(), s_.ac.as_tuple(), s_.apex.as_tuple())
                     for t_ in ann.teeth for s_ in t_.sites if s_.complete]
    ann.formula_id = "direct_v1"
    res2 = ann.compute(cfg)
    after_points = [(s_.cej.as_tuple(), s_.ac.as_tuple(), s_.apex.as_tuple())
                    for t_ in ann.teeth for s_ in t_.sites if s_.complete]
    check("换公式后标定点一个没动", before_points == after_points)
    check("换公式后直线法 ≥ 投影法",
          res2.worst_ratio is not None and res2.worst_ratio >= res.worst_ratio - 1e-9,
          f"direct={res2.worst_ratio} proj={res.worst_ratio}")
    ann.formula_id = "projection_v1"
    check("切回来结果复原", close(ann.compute(cfg).worst_ratio, res.worst_ratio))


def test_grading() -> None:
    """只判影像学骨吸收区间，不判 Stage / Grade。"""
    print("\n[interval]")
    cfg = GradingConfig()
    check("< 15% → I", interval_of(0.10, cfg) == "I")
    check("恰好 15% → II（下边界含）", interval_of(0.15, cfg) == "II")
    check("30% → II", interval_of(0.30, cfg) == "II")
    check("恰好 33% → II（上边界含）", interval_of(0.33, cfg) == "II")
    check("> 33% → III", interval_of(0.34, cfg) == "III")
    check("无值 → 无区间", interval_of(None, cfg) is None)
    check("区间文字带百分数", "15%" in interval_text("II", cfg), interval_text("II", cfg))

    # 阈值可改，区间文字跟着变
    cfg2 = GradingConfig(interval_i_max=0.20, interval_ii_max=0.40)
    check("改阈值后 18% 落回 I", interval_of(0.18, cfg2) == "I")
    check("改阈值后文字同步", "20%" in interval_text("I", cfg2), interval_text("I", cfg2))

    # 不再对外提供分期分级判定
    import app.core.grading as G
    check("不再导出 grade_of / stage_of",
          not hasattr(G, "grade_of") and not hasattr(G, "stage_of"))


# ── 序列化往返 ──────────────────────────────────────────────────────────


def test_roundtrip() -> None:
    print("\n[serialization]")
    ann = CaseAnnotation(image_file="001.jpg", image_width=2943, image_height=1435)
    ann.patient.age = 42
    t = ann.add_tooth(fdi=26)
    t.site("mesial").cej = Pt(1.5, 2.5)
    t.site("mesial").ac = Pt(3.5, 4.5)
    t.site("mesial").apex = Pt(5.5, 6.5)
    t.site("distal").skipped = True

    d = ann.to_dict()
    back = CaseAnnotation.from_dict(d)
    check("往返：年龄", back.patient.age == 42)
    check("往返：牙位", back.teeth[0].fdi == 26)
    check("往返：坐标", back.teeth[0].site("mesial").cej.as_tuple() == (1.5, 2.5))
    check("往返：跳过标记", back.teeth[0].site("distal").skipped)
    # 派生量绝不能落盘 —— 换公式后必须靠重算，而不是读旧结果
    derived_keys = {"ratio", "metrics", "bone_loss", "root_length",
                    "grade", "stage", "worst", "result"}
    site_d = d["teeth"][0]["sites"][0]
    check("site 里无派生量", not (derived_keys & set(site_d)))
    check("tooth 里无派生量", not (derived_keys & set(d["teeth"][0])))
    check("顶层无派生量", not (derived_keys & set(d)))
    check("点标签写进了 JSON",
          d["teeth"][0]["sites"][0]["cej"]["label"] == "P1")

    # v1 → v2 迁移：共享根尖复制到两侧，丢弃 cej2
    from app.core.storage import migrate
    old = {
        "schema_version": 1,
        "teeth": [{
            "fdi": 16,
            "apex": {"x": 10, "y": 20},
            "sites": [
                {"surface": "mesial", "cej": {"x": 1, "y": 2},
                 "cej2": {"x": 1, "y": 4}, "ac": {"x": 1, "y": 6}},
                {"surface": "distal", "cej": {"x": 5, "y": 2}, "ac": {"x": 5, "y": 6}},
            ],
        }],
    }
    new = migrate(old)
    check("迁移：版本升到 3", new["schema_version"] == 3)
    check("迁移：根尖复制到近中", new["teeth"][0]["sites"][0]["apex"] == {"x": 10, "y": 20})
    check("迁移：根尖复制到远中", new["teeth"][0]["sites"][1]["apex"] == {"x": 10, "y": 20})
    # v1 里的 cej2 就是 CEJ 下 2mm，与 v3 含义一致 —— 必须原样保留
    check("迁移：保留 v1 的 cej2",
          new["teeth"][0]["sites"][0]["cej2"] == {"x": 1, "y": 4})

    # v2（3 点）数据直接读，①②可用、③④缺 P2
    from app.core.models import CaseAnnotation as _CA
    v2 = {"schema_version": 2, "teeth": [{"fdi": 16, "sites": [
        {"surface": "mesial", "cej": {"x": 0, "y": 0},
         "ac": {"x": 0, "y": 40}, "apex": {"x": 0, "y": 200}}]}]}
    a2 = _CA.from_dict(migrate(v2))
    site2 = a2.teeth[0].site("mesial")
    check("v2 旧数据：①仍可算",
          site2.metrics(F.get("direct_v1"), F.FormulaConfig()) is not None)
    check("v2 旧数据：③算不出（缺 P2）",
          site2.metrics(F.get("direct_cej2_v1"), F.FormulaConfig()) is None)


def test_sorting() -> None:
    print("\n[natural sort]")
    names = ["10.jpg", "2.jpg", "1.jpg", "20.jpg", "3.jpg"]
    got = sorted(names, key=natural_key)
    want = ["1.jpg", "2.jpg", "3.jpg", "10.jpg", "20.jpg"]
    check("1,2,3,10,20 而不是字典序", got == want, f"got {got}")


def test_project_formula() -> None:
    """公式是**项目级**的 —— 一批研究数据必须口径一致。"""
    print("\n[project formula]")
    import tempfile, shutil
    from app.core.project import Project

    tmp = Path(tempfile.mkdtemp(prefix="perio_f_"))
    try:
        proj = Project.create(tmp / "p")
        check("默认公式是投影法", proj.settings.formula_id == "projection_v1")

        proj.settings.formula_id = "direct_v1"
        proj.save()
        again = Project.open(tmp / "p")
        check("公式设置能持久化", again.settings.formula_id == "direct_v1")

        # 载入任何标注都强制用项目公式，防止一批数据里口径混杂
        entry = type("E", (), {"case_id": "x", "image": "x.png", "sha1": "",
                               "status": "pending"})()
        ann = again.load_annotation(entry)
        check("载入标注强制用项目公式", ann.formula_id == "direct_v1")

        again.settings.formula_id = "不存在的公式"
        again.save()
        check("非法公式 id 回落到默认",
              Project.open(tmp / "p").settings.formula_id == "projection_v1")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    test_geometry()
    test_formula()
    test_labels()
    test_case()
    test_grading()
    test_project_formula()
    test_roundtrip()
    test_sorting()
    print()
    if FAILED:
        print(f"✗ {len(FAILED)} 项失败：" + ", ".join(FAILED))
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

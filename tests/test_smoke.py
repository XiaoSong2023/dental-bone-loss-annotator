"""端到端冒烟测试：合成片子，跑通导入 → 标点 → 导出 → 界面。

Qt 部分在 offscreen 平台下运行，不需要真实显示器。
    python tests/test_smoke.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import numpy as np  # noqa: E402

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  {detail}" if not cond and detail else ""))
    if not cond:
        FAILED.append(name)


# 合成片的解剖比例照真实全景片来（咬合平面 ≈ 纵向 55%），
# 否则测的就不是算法在真实几何下的行为。
UPPER_CREST, LOWER_CREST = 315, 435      # h=700 时的上下颌牙槽嵴基线
OCCLUSAL = 382
ARC = 25                                  # 牙弓弧度


def synth_panoramic(w: int = 1400, h: int = 700) -> np.ndarray:
    """合成一张结构接近真实全景片的灰度图。

    结构照真实全景片来：上下颌骨 + 牙冠 + 上颌窦 + 眶缘 + 下颌下缘，
    用来验证读图、缩放、打点、导出这条链路在真实几何下能跑通。
    """
    img = np.full((h, w), 22, dtype=np.uint8)
    rng = np.random.default_rng(7)
    arc = (np.sin(np.arange(w) / w * np.pi) * ARC).astype(int)

    for x in range(w):
        uc, lc = UPPER_CREST - arc[x], LOWER_CREST + arc[x]
        img[max(0, uc - 165):uc, x] = 150              # 上颌骨
        img[lc:min(h, lc + 155), x] = 148              # 下颌骨
        img[uc:uc + 55, x] = 225                       # 上颌牙冠（最亮）
        img[max(0, lc - 40):lc, x] = 222               # 下颌牙冠

    # 诱饵 1：上颌窦（骨内大片暗区）
    img[175:290, int(w * 0.20):int(w * 0.80)] = 40
    # 诱饵 2：眶下缘 / 颧弓亮带
    img[60:95, int(w * 0.12):int(w * 0.88)] = 205
    # 诱饵 3：下颌下缘
    img[int(h * 0.85):, :] = 30

    for x in range(60, w - 60, 52):                    # 牙间暗缝
        img[:, x:x + 3] = np.clip(img[:, x:x + 3].astype(int) - 75, 0, 255).astype(np.uint8)

    return np.clip(img.astype(int) + rng.normal(0, 6, img.shape), 0, 255).astype(np.uint8)


def main() -> int:
    from app.core import export as exporter
    from app.core.models import Pt
    from app.core.formula import get as get_formula
    from app.core.project import STATUS_DONE, Project
    from app.imaging.loader import ImageAdjust, apply_adjust, imwrite_unicode, load_gray

    tmp = Path(tempfile.mkdtemp(prefix="perio_smoke_"))
    try:
        # ── 1. 造数据（路径故意带中文，验证 imread 的 Unicode 处理） ──
        print("\n[图像读写]")
        src = tmp / "原始片子"
        src.mkdir()
        img = synth_panoramic()
        for i in (1, 2, 10):
            # 每张加一点不同的噪声，否则会被 sha1 去重正确地拦掉
            variant = np.clip(img.astype(int) + i, 0, 255).astype(np.uint8)
            check(f"写出 {i}.png", imwrite_unicode(src / f"{i}.png", variant))
        back = load_gray(src / "1.png")
        check("中文路径读回", back is not None and back.shape == img.shape)

        # ── 2. 项目 ──
        print("\n[项目]")
        proj_dir = tmp / "研究项目"
        proj = Project.create(proj_dir)
        added, skipped = proj.import_paths([src])
        check("导入 3 张", len(added) == 3, f"got {len(added)}")
        check("自然排序 1,2,10",
              [c.case_id for c in proj.sorted_cases()] == ["1", "2", "10"],
              f"got {[c.case_id for c in proj.sorted_cases()]}")

        added2, skipped2 = proj.import_paths([src])       # 重复导入
        check("sha1 去重", len(added2) == 0 and len(skipped2) == 3)

        # ── 4. 标注 ──
        print("\n[标注与计算]")
        entry = proj.find("1")
        ann = proj.load_annotation(entry)
        ann.patient.age = 45

        t = ann.add_tooth(fdi=16, roi=(300, 150, 120, 420))
        t.site("mesial").cej = Pt(330, 260)
        t.site("mesial").ac = Pt(336, 320)
        t.site("mesial").apex = Pt(342, 500)
        t.site("distal").cej = Pt(400, 258)
        t.site("distal").ac = Pt(398, 300)
        t.site("distal").apex = Pt(396, 498)

        t2 = ann.add_tooth(fdi=36, roi=(700, 400, 120, 300))
        t2.site("mesial").cej = Pt(730, 470)
        t2.site("mesial").ac = Pt(733, 560)
        t2.site("mesial").apex = Pt(736, 690)
        t2.site("distal").skipped = True

        result = ann.compute(proj.grading)
        check("算出最重位点", result.worst_ratio is not None)
        check("算出所属区间", result.interval in ("I", "II", "III"))
        check("已标 2 颗牙", ann.annotated_tooth_count == 2)

        proj.save_annotation(entry, ann)
        reloaded = proj.load_annotation(entry)
        check("存盘往返一致",
              abs(reloaded.compute(proj.grading).worst_ratio - result.worst_ratio) < 1e-9)

        proj.set_status(entry, STATUS_DONE)
        cnt = proj.counts()
        check("进度统计", cnt[STATUS_DONE] == 1 and cnt["remaining"] == 2,
              f"got {cnt}")

        # ── 根尖片模式：一个文件夹 = 一个病人 ──
        print(chr(10) + "[根尖片模式]")
        from app.core.project import MODE_PERIAPICAL

        pa_root = tmp / "根尖片原始"
        base_pa = synth_panoramic(600, 800)
        for pi, (patient, n) in enumerate((("张三", 4), ("李四", 3))):
            d = pa_root / patient
            d.mkdir(parents=True)
            for k in range(1, n + 1):
                # 每张必须内容不同，否则会被 sha1 去重正确地拦掉
                imwrite_unicode(
                    d / f"{k}.png",
                    np.clip(base_pa.astype(int) + k + pi * 11, 0, 255).astype(np.uint8),
                )

        pa = Project.create(tmp / "根尖片项目")
        pa.settings.mode = MODE_PERIAPICAL
        pa.save()
        added_pa, _ = pa.import_paths([pa_root])
        check("批量导入两个文件夹共 7 张", len(added_pa) == 7, f"got {len(added_pa)}")
        pats = pa.patients()
        check("按文件夹分成 2 个病人", set(pats) == {"张三", "李四"}, f"got {sorted(pats)}")
        check("张三 4 张 / 李四 3 张",
              len(pats["张三"]) == 4 and len(pats["李四"]) == 3)
        check("同名文件不冲突",
              len({c.case_id for c in pa.cases}) == 7,
              f"ids={sorted(c.case_id for c in pa.cases)}")
        check("片名保留原始文件名",
              sorted(c.title for c in pats["李四"]) == ["1", "2", "3"])

        zs = pats["张三"]
        check("siblings 找到同病人全部片子", len(pa.siblings(zs[0])) == 4)

        # 在张三的第 2、3 张上各标一颗牙，最重的那颗在第 3 张
        for film, ratio_y in ((zs[1], 340), (zs[2], 420)):
            a = pa.load_annotation(film)
            a.patient.age = 50
            t = a.add_tooth(fdi=16)
            t.site("mesial").cej = Pt(200, 300)
            t.site("mesial").ac = Pt(200, ratio_y)
            t.site("mesial").apex = Pt(200, 600)
            t.site("distal").skipped = True
            pa.save_annotation(film, a)

        rows = exporter.summary_rows(pa, pa.grading)
        check("按病人汇总成 2 行", len(rows) == 2, f"got {len(rows)}")
        zs_row = next(r for r in rows if r[0] in ("张三", pats["张三"][0].case_id))
        check("片数列 = 4", zs_row[1] == 4, f"got {zs_row[1]}")
        check("最重跨片取到第 3 张", zs_row[2] == zs[2].title, f"got {zs_row[2]}")
        check("最重比例 = 0.40（第3张的 120/300）",
              abs(float(zs_row[7]) - 0.4) < 1e-6, f"got {zs_row[7]}")
        check("位点明细带片名",
              any(r[1] == zs[2].title for r in exporter.site_rows(pa, pa.grading)))

        # ── 重命名 / 移除 ──
        print(chr(10) + "[列表右键操作]")
        pa.rename(zs[0], "右上后牙区")
        check("重命名生效", pa.find(zs[0].case_id).display == "右上后牙区")

        keep_img = pa.image_path(zs[3])
        pa.remove_case(zs[3], delete_files=False)
        check("仅移出列表：条目没了", pa.find(zs[3].case_id) is None)
        check("仅移出列表：图片还在", keep_img.exists())

        gone = pats["李四"][0]
        gone_img = pa.image_path(gone)
        pa.save_annotation(gone, pa.load_annotation(gone))
        gone_ann = pa.annotation_path(gone)
        pa.remove_case(gone, delete_files=True)
        check("连同文件删除：图片已删", not gone_img.exists())
        check("连同文件删除：标注已删", not gone_ann.exists())
        check("删除后计数正确", len(pa.cases) == 5, f"got {len(pa.cases)}")

        # 手工并组
        li = pa.patients()["李四"]
        pa.set_patient_key(li[0], "张三")
        check("手工并组生效",
              len(pa.patients()["张三"]) == 4, f"got {len(pa.patients().get('张三', []))}")

        # ── 5. 名册 ──
        print("\n[名册导入]")
        from app.core import roster as roster_mod
        rpath = tmp / "名册.csv"
        rpath.write_text("文件名,年龄,性别,备注\n1.png,45,女,基线\n2,52,男,\n10.png,38,女,\n",
                         encoding="utf-8-sig")
        rows = roster_mod.read_roster(rpath)
        check("读到 3 行", len(rows) == 3, f"got {len(rows)}")
        rep = roster_mod.match([c.case_id for c in proj.cases], rows)
        check("全部匹配上", len(rep.matched) == 3 and not rep.unmatched_cases,
              rep.summary())
        check("年龄解析", {r.age for _, r in rep.matched} == {45.0, 52.0, 38.0})

        # 带「岁」字和 GBK 编码也要能读
        rpath2 = tmp / "名册gbk.csv"
        rpath2.write_bytes("病例号,年龄\n1,45岁\n".encode("gbk"))
        check("GBK + 「45岁」", roster_mod.read_roster(rpath2)[0].age == 45.0)

        # ── 6. 导出 ──
        print("\n[导出]")
        paths = exporter.export_csv(proj, proj.grading)
        check("CSV 生成", all(p.exists() and p.stat().st_size > 0 for p in paths))
        head = paths[0].read_text(encoding="utf-8-sig").splitlines()
        check("汇总表有表头+3行", len(head) == 4, f"got {len(head)}")
        check("汇总表带四公式对照列",
              all(k in head[0] for k in ("该位点_①直线法", "该位点_②投影法",
                                         "该位点_③直线法2mm", "该位点_④投影法2mm",
                                         "倾斜高估(①−②)", "起点差异(①−③)")),
              head[0])
        check("汇总表带骨吸收区间列且无 Grade/Stage",
              "骨吸收区间(2018影像学)" in head[0] and "Grade" not in head[0]
              and "Stage" not in head[0], head[0])
        check("汇总表带百分数列", "最重骨吸收比例%" in head[0], head[0])
        # 区间结论确实写进了数据行
        check("数据行里有区间文字",
              any("%" in cell for cell in head[1].split(",")), head[1])
        sites = paths[1].read_text(encoding="utf-8-sig").splitlines()
        # t1 近中+远中（2）＋ t2 近中完整 + 远中跳过（2）= 4 行数据 + 表头
        check("位点表 4 行数据", len(sites) == 5, f"got {len(sites)}")
        check("位点表带四公式对照列",
              all(k in sites[0] for k in ("比例_①直线法", "比例_②投影法",
                                          "比例_③直线法2mm", "比例_④投影法2mm")),
              sites[0])
        check("位点表带 CEJ-2mm 坐标列",
              "CEJ2mm_x" in sites[0] and "CEJ2mm_y" in sites[0], sites[0])
        check("位点表也带区间列", "骨吸收区间" in sites[0], sites[0])

        # 同一位点四法对照
        from app.core.export import both_ratios
        site0 = next(s_ for t_ in ann.teeth for s_ in t_.sites if s_.filled_count >= 3)
        v = both_ratios(site0, proj.grading)
        check("①② 可算（只标了 3 点）",
              v["direct_v1"] is not None and v["projection_v1"] is not None)
        check("① ≥ ②（倾斜高估）",
              v["direct_v1"] - v["projection_v1"] >= -1e-9)
        check("③④ 因缺 P2 为空",
              v["direct_cej2_v1"] is None and v["projection_cej2_v1"] is None)

        # 补上 CEJ-2mm 后四个公式都出结果
        from app.core.models import Pt as _Pt
        site0.cej2 = _Pt(site0.cej.x, site0.cej.y + 12)
        v2 = both_ratios(site0, proj.grading)
        check("补 P2 后四个公式全部出值",
              all(v2[k] is not None for k in v2), v2)
        check("③ 起点后移 ⇒ 比①的根长短",
              site0.metrics(get_formula("direct_cej2_v1"), proj.grading.formula_config()).root_length
              < site0.metrics(get_formula("direct_v1"), proj.grading.formula_config()).root_length)
        site0.cej2 = None       # 还原，后面的断言按 3 点算

        xlsx = exporter.export_excel(proj, proj.grading)
        check("Excel 生成", xlsx.exists() and xlsx.stat().st_size > 0)

        jpath = exporter.export_single_json(proj, entry, tmp / "one.json")
        import json
        jd = json.loads(jpath.read_text(encoding="utf-8"))
        check("单例 JSON 含坐标", jd["teeth"][0]["sites"][0]["cej"]["label"] == "P1")
        check("单例 JSON 派生量单独放", "_derived" in jd)

        # ── 7. 看片增强 ──
        print("\n[看片调节]")
        adj = ImageAdjust(brightness=20, contrast=30, clahe=True, invert=True)
        out = apply_adjust(img, adj)
        check("增强后形状不变", out.shape == img.shape and out.dtype == np.uint8)
        check("恒等时零拷贝", apply_adjust(img, ImageAdjust()) is img)

        # ── 8. Qt 界面 ──
        print("\n[Qt 界面 offscreen]")
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtWidgets import QApplication
        from app.ui.main_window import MainWindow
        from app.ui.tooth_dialog import STEPS, ToothDialog
        from app.core.formula import FormulaConfig, get as get_formula

        appq = QApplication.instance() or QApplication([])
        # 用独立的组织名隔离 QSettings，避免读到上次真实运行留下的「上次项目」
        import app.ui.main_window as MW
        MW.ORG = "PerioToolsTest"
        appq.setOrganizationName(MW.ORG)

        win = MainWindow()
        check("主窗口构建", win is not None)
        win._load_project(proj)
        check("加载项目后有列表", win.cases.lists[0].count() + win.cases.lists[1].count() == 3)

        win.open_case(proj.find("1"), force=True)
        check("打开病例", win.ann is not None and win._gray is not None)
        check("打开即进入画框模式", win.btn_pick.isChecked())

        # 延迟恢复「上次项目」不能顶掉调用方已经打开的项目
        win._restore_last_project()
        for _ in range(3): appq.processEvents()
        check("延迟恢复不覆盖已打开项目",
              win.project is proj and win.ann is not None)

        # ── 画框选牙的真实鼠标交互 ──
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest
        from app.ui.panorama_view import MODE_PICK

        win.view.box_drawn.disconnect()          # 绕开会弹窗的 QInputDialog
        boxes = []
        win.view.box_drawn.connect(boxes.append)
        win.view.set_mode(MODE_PICK)
        for _ in range(4): appq.processEvents()

        def drag(x0, y0, x1, y1):
            vp = win.view.viewport()
            QTest.mousePress(vp, Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier, QPoint(x0, y0))
            QTest.mouseMove(vp, QPoint((x0 + x1) // 2, (y0 + y1) // 2))
            appq.processEvents()
            QTest.mouseMove(vp, QPoint(x1, y1))
            appq.processEvents()
            QTest.mouseRelease(vp, Qt.MouseButton.LeftButton,
                               Qt.KeyboardModifier.NoModifier, QPoint(x1, y1))
            appq.processEvents()

        drag(150, 80, 260, 300)
        check("拖框产生选框", len(boxes) == 1, f"got {len(boxes)}")

        boxes.clear(); drag(400, 200, 404, 203)
        check("微小拖拽判为误触不成框", len(boxes) == 0, f"got {len(boxes)}")

        boxes.clear(); drag(500, 250, 400, 120)      # 从右下往左上拖
        check("反向拖框归一化为正尺寸",
              len(boxes) == 1 and boxes[0].width() > 0 and boxes[0].height() > 0)

        # 从图内某点拖到视口外 —— 终点应被钳制回图像边界，仍产出合法框
        boxes.clear()
        iw, ih = win.ann.image_width, win.ann.image_height
        start = win.view.mapFromScene(QPointF(iw - 260, ih - 200))
        vw, vh = win.view.viewport().width(), win.view.viewport().height()
        drag(start.x(), start.y(), vw + 60, vh + 60)
        check("越界拖框钳制在图内",
              len(boxes) == 1 and boxes[0].x() >= 0 and boxes[0].y() >= 0
              and boxes[0].right() <= iw and boxes[0].bottom() <= ih,
              str(boxes[0]) if boxes else "no box")

        win.view.set_mode("view")
        boxes.clear(); drag(150, 80, 260, 300)
        check("浏览模式下不出框", len(boxes) == 0, f"got {len(boxes)}")

        n_before = len(win.ann.teeth)
        win.ann.add_tooth(fdi=26, roi=(500, 150, 120, 420))
        win._refresh_all()
        check("加框后回显刷新", len(win.ann.teeth) == n_before + 1)

        # ── 公式切换（项目级） ──
        from app.core.formula import FORMULAS
        from app.core.project import MODE_PERIAPICAL as _MP
        check("工具栏有四个公式", win.formula_combo.count() == 4,
              f"got {win.formula_combo.count()}")
        check("初始选中投影法", win.formula_combo.currentData() == "projection_v1")

        before = win.ann.compute(proj.grading).worst_ratio
        win.set_formula("direct_v1")
        after = win.ann.compute(proj.grading).worst_ratio
        check("切换后项目设置已更新", proj.settings.formula_id == "direct_v1")
        check("两个下拉框同步",
              win.formula_combo.currentData() == "direct_v1"
              and win.inspector.formula_box.currentData() == "direct_v1")
        check("切换后比值按新公式变化", after >= before - 1e-9 and after != before,
              f"proj={before} direct={after}")

        reopened = Project.open(proj.root)
        check("公式选择写盘持久化", reopened.settings.formula_id == "direct_v1")
        win.set_formula("projection_v1")
        check("切回投影法结果复原",
              abs(win.ann.compute(proj.grading).worst_ratio - before) < 1e-9)

        # ── 片型切换 ──
        check("工具栏有片型选择器", win.mode_combo.count() == 2)
        check("默认全景片", win.mode_combo.currentData() == "panoramic")
        win.set_mode(_MP)
        check("切换后写盘", Project.open(proj.root).settings.mode == _MP)
        check("左右栏都收到片型",
              win.cases._periapical and win.inspector._periapical)
        win.set_mode("panoramic")
        check("切回全景片", win.project.settings.mode == "panoramic")

        # ── 一键清空所有标记 ──
        win._mark_dirty()
        win.save_current(silent=True)          # 先落盘，备份比对才有意义
        n_before = len(win.ann.teeth)
        check("清空前有牙位", n_before > 0)
        win.ann.teeth.clear()          # 走 clear_all_marks 会弹确认框，这里直接验后半段
        win._mark_dirty()
        win.save_current(silent=True)
        win._refresh_all()
        check("清空后牙位为 0", len(win.project.load_annotation(win.entry).teeth) == 0)
        import json as _json
        bks = list((win.project.annotations_dir / "_backup").glob("*.json"))
        check("清空前自动留了备份", len(bks) >= 1, f"got {len(bks)}")
        saved = max((len(_json.loads(b.read_text(encoding="utf-8")).get("teeth", []))
                     for b in bks), default=0)
        check("备份里完整保住了被清掉的牙位", saved == n_before,
              f"backup={saved} cleared={n_before}")
        # 还原 3 颗牙，后面的分步标定对话框测试还要用
        win.ann = win.project.load_annotation(win.entry)
        for fdi, x in ((16, 300), (26, 500), (36, 700)):
            win.ann.add_tooth(fdi=fdi, roi=(x, 150, 120, 420))
        win._mark_dirty()
        win.save_current(silent=True)
        win._refresh_all()
        check("还原后 3 颗牙", len(win.ann.teeth) == 3)

        # ── 右键菜单信号 ──
        # 先摘掉主窗口的真实处理器，否则 emit 会弹出模态对话框把测试挂死
        win.cases.delete_requested.disconnect()
        win.cases.rename_requested.disconnect()
        win.cases.regroup_requested.disconnect()
        got_del, got_ren, got_grp = [], [], []
        win.cases.delete_requested.connect(got_del.append)
        win.cases.rename_requested.connect(got_ren.append)
        win.cases.regroup_requested.connect(got_grp.append)
        win.cases.delete_requested.emit([win.entry])
        win.cases.rename_requested.emit(win.entry)
        win.cases.regroup_requested.emit([win.entry])
        check("右键三个信号都可达",
              len(got_del) == 1 and len(got_ren) == 1 and len(got_grp) == 1)

        # 右键菜单本身能建出来（不弹出）
        from PySide6.QtCore import QPoint as _QP
        lw = win.cases.lists[0]
        if lw.count():
            lw.setCurrentRow(0)
            check("右键菜单可构建", win.cases._selected_entries(lw) != [])

        check("8 个标定步骤", len(STEPS) == 8, f"got {len(STEPS)}")
        check("步骤顺序：一侧走完 CEJ→2mm→AC→根尖 再换另一侧",
              STEPS == [("mesial", "cej"), ("mesial", "cej2"),
                        ("mesial", "ac"), ("mesial", "apex"),
                        ("distal", "cej"), ("distal", "cej2"),
                        ("distal", "ac"), ("distal", "apex")], f"got {STEPS}")

        dlg = ToothDialog(img, win.ann, list(win.ann.teeth),
                          get_formula(win.ann.formula_id), FormulaConfig(), win)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        dlg.show()
        for _ in range(6): appq.processEvents()
        check("标定对话框构建", dlg is not None)
        # 布局完成后必须真的缩放到牙框上，不能停在「整幅图缩成一小团」的状态
        check("放大到牙框（延迟 fit 生效）", dlg.canvas.current_scale() > 1.0,
              f"scale={dlg.canvas.current_scale():.3f}")
        tooth3 = win.ann.teeth[2]
        dlg._goto_tooth(2)
        for pt in ((540, 260), (543, 285), (545, 330), (550, 520)):
            dlg._on_click(QPointF(*pt))
        s = tooth3.site("mesial")
        check("四次点击落成近中 4 个点", s.filled_count == 4, f"got {s.filled_count}")
        check("点位对应正确（CEJ→2mm→AC→根尖 由冠向根）",
              s.cej.y < s.cej2.y < s.ac.y < s.apex.y)
        check("自动跳到远中", dlg.step == ("distal", "cej"), f"got {dlg.step}")
        check("四个公式此时都能算",
              all(s.metrics(get_formula(f), FormulaConfig()) is not None
                  for f in ("direct_v1", "projection_v1",
                            "direct_cej2_v1", "projection_cej2_v1")))
        dlg.undo()
        check("撤销退回根尖", tooth3.site("mesial").apex is None
              and dlg.step == ("mesial", "apex"))
        dlg.close()

        win.recalculate_all_silent = None
        win.close()
        check("导出菜单可用", win.act_csv.isEnabled())

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print(f"✗ {len(FAILED)} 项失败：" + ", ".join(FAILED))
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

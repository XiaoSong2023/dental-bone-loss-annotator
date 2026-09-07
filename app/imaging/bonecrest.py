"""牙槽嵴顶曲线自动提取 —— ⛔ **当前已从界面停用，本模块不被调用**。

停用原因：在真实全景片上的准确度达不到临床可用的程度。虽然第二版已经把线
拉回了牙槽区（区域限制 + 骨/空气剖面判据），但个别片子仍会贴着牙冠走，
作为"帮医生定位可疑牙位"的辅助反而可能误导。医生的判断更可靠。

代码予以保留：思路和踩过的坑都记在下面，将来若要用带 FDI 的分割权重把牙
逐颗抠出来、再在每颗牙的邻面局部找骨缘，这些结论仍然适用。要重新启用，
把 main_window 里的生成入口和 panorama_view 的绘制图层接回来即可。

── 以下是停用前的设计说明 ────────────────────────────────────────

定位：**纯可视化辅助**。绿色曲线只帮你肉眼快速定位「曲线掉得最低」的区域，
   从而挑出可疑牙位；它**不参与任何计算**，提取失败也不影响任何数据可靠性。

── 为什么不能只看梯度 ────────────────────────────────────────────────
第一版直接找"垂直方向最强的边缘"，在真实全景片上会跑偏，因为片子里比牙槽嵴
更强的水平边缘到处都是：上颌窦底、眶下缘、下颌管、下颌下缘，以及**牙齿与空气
的交界**（牙冠比骨亮得多，边缘也更锐）。结果就是线画到了离谱的高度。

这一版换成两条约束：

1. **区域限制**：只在牙槽嵴所在的中央条带里找。条带可由用户框定并保存，
   没框时按牙列的亮结构自动估一个。
2. **骨/空气剖面判据**：不看梯度绝对值，而是检查候选点两侧的实际灰度构成 ——
   根方一侧要像**牙槽骨**（中灰），冠方一侧要像**空气**（暗）。
   根方一侧若亮到牙齿的量级，判为"牙-空气"交界并大幅降权。
   这正是把"牙槽骨与空气的界限"和"牙齿与空气的界限"区分开的地方。

牙齿遮挡的列没有可靠的骨缘信息，代价置平，由动态规划从两侧邻牙间隙平滑插值 ——
临床上牙槽嵴顶本来就是在邻面判读的，这与你的测量口径一致。

只用 numpy + cv2，打包体积增量为 0。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

WORK_WIDTH = 900          # 处理分辨率：降采样后更快、噪声更少

# 自动条带：相对图像高度，以咬合线为原点向上/向下
BAND_NEAR = 0.03          # 离咬合线太近的是牙冠，排除
BAND_FAR = 0.14           # 离咬合线太远的是上颌窦 / 下颌下缘，排除

# 咬合暗带的纵向搜索范围（相对图像高度）。全景片的咬合平面几乎恒在这个区间
OCCLUSAL_LO, OCCLUSAL_HI = 0.45, 0.72
# 牙弓的横向范围（相对图像宽度）。两侧是升支、髁突、颈椎，不含牙槽嵴
ARCH_X0, ARCH_X1 = 0.18, 0.82

PROFILE_WIN = 9           # 骨/空气剖面的采样窗（工作分辨率下的像素）
SLOPE_PENALTY = 0.30      # 每列上下移动 1 像素的代价，越大曲线越平滑
TOOTH_DEMOTE = 0.12       # 判为"牙-空气"交界时的降权系数
UNRELIABLE_COST = 1.0     # 牙齿遮挡列的平代价（让 DP 靠平滑项插值）


@dataclass
class CrestResult:
    upper: list[tuple[int, int]]
    lower: list[tuple[int, int]]
    ok: bool
    message: str = ""
    band: tuple[int, int, int, int] | None = None    # 实际使用的搜索区(x0,y0,x1,y1)


def extract(gray: np.ndarray,
            band: tuple[float, float, float, float] | None = None) -> CrestResult:
    """提取上下颌牙槽嵴顶曲线，返回**原图坐标**。

    band: 搜索区 (x0, y0, x1, y1)，原图像素坐标。None 表示自动估计。
    """
    if gray is None or gray.size == 0 or gray.ndim != 2:
        return CrestResult([], [], False, "图像无效")

    H0, W0 = gray.shape
    scale = min(1.0, WORK_WIDTH / W0)
    work = (cv2.resize(gray, (int(W0 * scale), int(H0 * scale)), interpolation=cv2.INTER_AREA)
            if scale < 1.0 else gray.copy())
    H, W = work.shape

    # 两张工作图，各司其职：
    #   raw  —— 保留真实灰度关系，用来定位牙列（牙釉质是全片最致密的组织）
    #   blur —— CLAHE 增强后，用来找骨/空气边缘
    # 千万别用 CLAHE 图定位牙列：它会把上颌窦下缘的骨提亮到超过牙釉质，
    # 「牙齿最亮」的前提就不成立了，条带会整个偏掉。
    raw = cv2.GaussianBlur(work, (0, 0), sigmaX=1.6).astype(np.float32)
    blur = cv2.GaussianBlur(
        cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(work),
        (0, 0), sigmaX=1.6,
    ).astype(np.float32)

    # ── 搜索区 ───────────────────────────────────────────────────
    if band is not None:
        x0, y0, x1, y1 = (int(round(v * scale)) for v in band)
        x0, x1 = max(0, min(x0, W - 2)), min(W, max(x0 + 2, x1))
        y0, y1 = max(0, min(y0, H - 2)), min(H, max(y0 + 2, y1))
    else:
        x0, y0, x1, y1 = _auto_band(raw)
    if x1 - x0 < 40 or y1 - y0 < 20:
        return CrestResult([], [], False, "搜索区过小")

    y_occ = _occlusal_line(raw, x0, x1, y0, y1)

    # 牙齿 / 骨 / 空气三档阈值，全部在搜索区内统计，不受片子整体明暗影响
    roi = blur[y0:y1, x0:x1]
    tooth_thr = float(np.percentile(roi, 88))     # 比这更亮的基本是牙或致密骨皮质
    air_thr = float(np.percentile(roi, 35))       # 比这更暗的基本是空气 / 软组织

    near = max(2, int(H * BAND_NEAR))
    upper = _trace(blur, y_occ, x0, x1,
                   top=y0, bottom=max(y0 + 4, y_occ - near),
                   bone_above=True, tooth_thr=tooth_thr, air_thr=air_thr)
    lower = _trace(blur, y_occ, x0, x1,
                   top=min(y1 - 4, y_occ + near), bottom=y1,
                   bone_above=False, tooth_thr=tooth_thr, air_thr=air_thr)

    if upper is None and lower is None:
        return CrestResult([], [], False, "搜索区内对比度不足，未能提取曲线")

    inv = 1.0 / scale
    to_full = lambda pts: [(int(round(x * inv)), int(round(y * inv))) for x, y in pts]
    return CrestResult(
        upper=to_full(upper) if upper else [],
        lower=to_full(lower) if lower else [],
        ok=True,
        band=(int(x0 * inv), int(y0 * inv), int(x1 * inv), int(y1 * inv)),
    )


def auto_band(gray: np.ndarray) -> tuple[int, int, int, int]:
    """对外暴露的自动搜索区估计，返回**原图坐标** (x0, y0, x1, y1)。"""
    H0, W0 = gray.shape
    scale = min(1.0, WORK_WIDTH / W0)
    work = (cv2.resize(gray, (int(W0 * scale), int(H0 * scale)), interpolation=cv2.INTER_AREA)
            if scale < 1.0 else gray)
    x0, y0, x1, y1 = _auto_band(cv2.GaussianBlur(work, (0, 0), 1.6).astype(np.float32))
    inv = 1.0 / scale
    return (int(x0 * inv), int(y0 * inv), int(x1 * inv), int(y1 * inv))


# ── 内部 ────────────────────────────────────────────────────────────────


def _auto_band(raw: np.ndarray) -> tuple[int, int, int, int]:
    """自动估计牙槽嵴所在的中央条带。

    锚点是**咬合暗带**（上下牙列之间的口腔空隙）——
    它在全景片里几乎恒定落在纵向 45%~72% 之间，是最稳的解剖参照。
    牙槽嵴就贴在它上下 BAND_FAR 的范围内。

    为什么不用「找最亮的牙齿」来定位牙列（前两版都试过，都不行）：
      · 在 CLAHE 增强图上，上颌窦下缘的骨会被提亮到超过牙釉质；
      · 在原始灰度图上，下颌骨皮质、颧弓、颈椎又和牙釉质一样亮。
    「牙齿最亮」这个前提在真实机器输出上并不成立，所以放弃。

    横向用固定的保守范围：牙弓在全景片里总是占据中央，两侧是升支和颈椎。
    这个默认值可以被用户框定的搜索区覆盖（工具 → 框定曲线搜索区）。
    """
    H, W = raw.shape
    prof = raw[:, int(W * 0.25):int(W * 0.75)].mean(axis=1)
    sm = _smooth_profile(prof, H // 18)
    lo, hi = int(H * OCCLUSAL_LO), int(H * OCCLUSAL_HI)
    y_occ = (lo + int(np.argmin(sm[lo:hi]))) if hi - lo >= 3 else H // 2

    far = int(H * BAND_FAR)
    return (int(W * ARCH_X0), max(0, y_occ - far),
            int(W * ARCH_X1), min(H, y_occ + far))


def _smooth_profile(prof: np.ndarray, win: int) -> np.ndarray:
    k = max(5, win | 1)
    return cv2.GaussianBlur(prof.reshape(-1, 1).astype(np.float32), (1, k), 0).ravel()


def _occlusal_line(raw: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> int:
    """咬合平面：牙列中部行均值最暗的一行（上下牙列之间的暗带）。

    用**原始灰度**而非 CLAHE 图 —— CLAHE 会把局部暗区拉亮，暗带就不再是最暗。
    """
    prof = raw[y0:y1, x0:x1].mean(axis=1)
    k = max(5, (prof.size // 20) | 1)
    prof = cv2.GaussianBlur(prof.reshape(-1, 1).astype(np.float32), (1, k), 0).ravel()
    lo, hi = int(prof.size * 0.30), int(prof.size * 0.70)
    if hi - lo < 3:
        return (y0 + y1) // 2
    return y0 + lo + int(np.argmin(prof[lo:hi]))


def _one_sided_means(blur: np.ndarray, win: int) -> tuple[np.ndarray, np.ndarray]:
    """每个像素「上方 win 行」与「下方 win 行」的均值。"""
    k = win | 1
    centered = cv2.blur(blur, (1, k))
    off = k // 2 + 1
    up = np.roll(centered, off, axis=0)      # up[y] = 以 y-off 为中心的均值
    dn = np.roll(centered, -off, axis=0)
    up[:off] = centered[:off]
    dn[-off:] = centered[-off:]
    return up, dn


def _trace(blur: np.ndarray, y_occ: int, x0: int, x1: int,
           top: int, bottom: int, bone_above: bool,
           tooth_thr: float, air_thr: float) -> list[tuple[int, int]] | None:
    """在咬合线的一侧求最优骨嵴路径。

    bone_above=True 用于上颌（骨在上、空气在下），False 用于下颌。
    """
    H = blur.shape[0]
    top = max(0, min(top, H - 2))
    bottom = max(top + 6, min(bottom, H))
    if bottom - top < 8:
        return None

    up, dn = _one_sided_means(blur, PROFILE_WIN)
    bone_side, air_side = (up, dn) if bone_above else (dn, up)

    b = bone_side[top:bottom, x0:x1]
    a = air_side[top:bottom, x0:x1]

    # ① 骨侧要比空气侧亮 —— 这是「牙槽骨 / 空气」界限的本质特征
    contrast = np.clip(b - a, 0.0, None)
    # ② 空气侧必须真的暗；越接近空气阈值以下，权重越高
    air_ok = np.clip((air_thr - a) / max(air_thr, 1.0) + 0.35, 0.0, 1.0)
    # ③ 骨侧若亮到牙齿量级，判为「牙 / 空气」交界，大幅降权
    not_tooth = np.where(b > tooth_thr, TOOTH_DEMOTE, 1.0)

    score = contrast * air_ok * not_tooth
    peak = float(score.max())
    if peak < 1e-3:
        return None
    score /= peak

    cost = 1.0 / (score + 0.06)

    # 牙齿遮挡的列没有可靠骨缘信息 → 代价置平，交给平滑项从邻面插值
    band = blur[top:bottom, x0:x1]
    tooth_frac = (band > tooth_thr).mean(axis=0)
    unreliable = tooth_frac > 0.55
    if unreliable.any():
        cost[:, unreliable] = UNRELIABLE_COST * cost.mean()

    ys = _dp_min_path(cost.astype(np.float32), SLOPE_PENALTY)
    ys = _smooth(ys, window=max(11, (cost.shape[1] // 14) | 1))
    return [(x0 + i, top + int(round(v))) for i, v in enumerate(ys)]


def _dp_min_path(cost: np.ndarray, slope_penalty: float) -> np.ndarray:
    """逐列动态规划求「每列恰好一个像素、纵向每步最多移动 1 像素」的最小代价路径。

    seam carving 的经典解法，O(H·W)，全向量化。
    """
    H, W = cost.shape
    dp = np.empty((H, W), dtype=np.float32)
    back = np.zeros((H, W), dtype=np.int8)
    dp[:, 0] = cost[:, 0]

    big = np.float32(np.inf)
    for x in range(1, W):
        prev = dp[:, x - 1]
        up = np.empty_like(prev)
        up[0] = big
        up[1:] = prev[:-1] + slope_penalty
        down = np.empty_like(prev)
        down[-1] = big
        down[:-1] = prev[1:] + slope_penalty
        stack = np.stack((up, prev, down))            # 0:y−1  1:y  2:y+1
        choice = np.argmin(stack, axis=0)
        dp[:, x] = cost[:, x] + stack[choice, np.arange(H)]
        back[:, x] = choice.astype(np.int8) - 1

    ys = np.empty(W, dtype=np.int32)
    y = int(np.argmin(dp[:, -1]))
    ys[-1] = y
    for x in range(W - 1, 0, -1):
        y = max(0, min(H - 1, y + int(back[y, x])))
        ys[x - 1] = y
    return ys.astype(np.float32)


def _smooth(ys: np.ndarray, window: int) -> np.ndarray:
    """中值滤波去毛刺 + 滑动平均。替代 scipy.savgol_filter，避免引入 scipy。"""
    if ys.size < 5:
        return ys
    w = min(window if window % 2 else window + 1, (ys.size // 2) * 2 - 1)
    if w < 3:
        return ys
    pad = w // 2
    view = np.lib.stride_tricks.sliding_window_view(np.pad(ys, pad, mode="edge"), w)
    med = np.median(view, axis=1)
    view2 = np.lib.stride_tricks.sliding_window_view(np.pad(med, pad, mode="edge"), w)
    return view2.mean(axis=1).astype(np.float32)

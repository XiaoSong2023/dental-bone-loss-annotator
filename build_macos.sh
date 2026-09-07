#!/usr/bin/env bash
# macOS 打包 —— 产出 .app 与 .dmg
#
#   bash build_macos.sh
#
# ⚠️ **必须在 macOS 上运行**。PyInstaller 不支持交叉编译：它要把目标平台的
#    Python 解释器和 Qt 框架原样打进产物，这些 .dylib / .framework 在
#    Windows 上根本不存在。DMG 也依赖 macOS 自带的 hdiutil。
#    没有 Mac 的话，用 .github/workflows/build.yml 让 GitHub 的 macOS
#    机器免费替你构建（见 README「跨平台打包」）。

set -euo pipefail
cd "$(dirname "$0")"

APP_VERSION="${APP_VERSION:-1.0.0}"
APP_NAME="牙槽骨吸收测量"
VOL_NAME="${APP_NAME} ${APP_VERSION}"
DMG_PATH="dist/${APP_NAME}_v${APP_VERSION}.dmg"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "错误：这个脚本只能在 macOS 上运行（当前是 $(uname)）。" >&2
  echo "      没有 Mac 请用 GitHub Actions —— 见 README「跨平台打包」。" >&2
  exit 1
fi

# ── 1. 环境 ────────────────────────────────────────────────────────────
if [[ ! -x .venv/bin/python ]]; then
  echo "[1/5] 创建 venv…"
  python3 -m venv .venv
fi
PY=.venv/bin/python
echo "[1/5] 安装依赖…"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt pyinstaller

# ── 2. 测试 ────────────────────────────────────────────────────────────
echo "[2/5] 跑测试…"
"$PY" tests/test_core.py
"$PY" tests/test_smoke.py

# ── 3. 打包 .app ───────────────────────────────────────────────────────
echo "[3/5] 打包 .app…"
rm -rf build dist
APP_VERSION="$APP_VERSION" "$PY" -m PyInstaller build.spec --noconfirm --clean

APP_BUNDLE="dist/${APP_NAME}.app"
[[ -d "$APP_BUNDLE" ]] || { echo "错误：没生成 $APP_BUNDLE" >&2; exit 1; }

# ── 4. 自检 ────────────────────────────────────────────────────────────
echo "[4/5] 自检（确认打出来的包真能跑）…"
SELFTEST_QUIET=1 "$APP_BUNDLE/Contents/MacOS/${APP_NAME}" --selftest || true
LOG="$APP_BUNDLE/Contents/MacOS/selftest.log"
if [[ -f "$LOG" ]]; then cat "$LOG"; else
  echo "警告：自检没写出日志，请手动双击 .app 确认。" >&2
fi

# ── 5. 打 DMG ──────────────────────────────────────────────────────────
# 做一个带「拖到 Applications」快捷方式的标准安装盘，用户拖一下就装好。
echo "[5/5] 生成 DMG…"
STAGE="$(mktemp -d)"
cp -R "$APP_BUNDLE" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

rm -f "$DMG_PATH"
hdiutil create \
  -volname "$VOL_NAME" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "$DMG_PATH"
rm -rf "$STAGE"

echo
echo "============================================================"
echo "  完成"
echo "    .app : $APP_BUNDLE"
echo "    .dmg : $DMG_PATH  ($(du -h "$DMG_PATH" | cut -f1))"
echo "============================================================"
echo
echo "  发给别人：直接发这个 .dmg。对方双击打开，把图标拖到"
echo "  Applications 就装好了，不用装 Python 或任何东西。"
echo
echo "  ⚠️ 没有苹果开发者签名的话，对方首次打开会被 Gatekeeper 拦下，"
echo "     提示「无法打开，因为无法验证开发者」。让对方："
echo "       在「访达」里右键点图标 → 打开 → 再点「打开」"
echo "     只需这一次，之后正常双击即可。"

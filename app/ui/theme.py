"""配色与样式 —— 淡雅日式（和風 / Japandi）。

两条设计原则：

1. **界面用暖白纸感底色**（生成り #F7F4EE 一系）。长时间读片时，冷白和纯黑
   都会加重视觉疲劳；暖中性色是 Notion 一类"久看不累"产品的通行做法。
2. **画布保持深色**。这不是审美选择 —— 看 X 光片时周边越暗，人眼对灰阶的
   分辨力越高，这是放射科阅片室的常规。所以是"浅色外壳 + 深色片盒"。

强调色只用两支：藍鼠（主操作）与 朱（最重位点）。多了就花。
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# ── 基础色 ──────────────────────────────────────────────────────────────
KINARI      = "#F7F4EE"   # 生成り  窗口底色
SHIRONERI   = "#FFFDF9"   # 白練    卡片 / 输入框面
GOFUN       = "#FFFFFF"   # 胡粉    最亮面
BORDER      = "#E3DCCF"   # 边框
BORDER_SOFT = "#EDE7DC"   # 弱边框 / 分隔线
HOVER       = "#EFEAE0"   # 悬停底

SUMI        = "#33302B"   # 墨      主文字
NIBI        = "#7B756A"   # 鈍色    次要文字
USUZUMI     = "#A8A196"   # 薄墨    占位符 / 禁用

AI          = "#3E5C76"   # 藍鼠    主强调（选中、主按钮）
AI_HOVER    = "#4C6E8C"
AI_WASH     = "#E7EDF2"   # 藍鼠的极淡底

SHU         = "#B5533F"   # 朱      最重位点 / 错误
SHU_WASH    = "#F7EAE6"
YAMABUKI    = "#A8791F"   # 山吹    告警
MATSUBA     = "#5B7355"   # 松葉    正常 / 完成
MATSUBA_WASH = "#EAEFE8"

# ── 画布（深色片盒） ─────────────────────────────────────────────────────
CANVAS_BG   = "#1B1B1D"

# 叠加在 X 光片上的图元 —— 必须在深色灰阶背景上高可辨
CREST_CURVE = "#3DDC84"   # 牙槽嵴顶曲线
BAND_EDGE   = "#7DA9C7"   # 曲线搜索区边框
BOX_DRAW    = "#7DD3FC"   # 正在拖拽的选框

# 每颗牙一色。在灰阶片上取高辨识度，同时避开曲线的绿
TOOTH_COLORS = [
    "#22D3EE",  # 青
    "#FBBF24",  # 琥珀
    "#F87171",  # 珊瑚
    "#A78BFA",  # 藤
    "#FB923C",  # 橙
    "#F472B6",  # 桃
    "#38BDF8",  # 空
    "#FDE047",  # 黄
]


def palette() -> QPalette:
    p = QPalette()
    c = QColor
    p.setColor(QPalette.ColorRole.Window, c(KINARI))
    p.setColor(QPalette.ColorRole.WindowText, c(SUMI))
    p.setColor(QPalette.ColorRole.Base, c(SHIRONERI))
    p.setColor(QPalette.ColorRole.AlternateBase, c(KINARI))
    p.setColor(QPalette.ColorRole.Text, c(SUMI))
    p.setColor(QPalette.ColorRole.Button, c(KINARI))
    p.setColor(QPalette.ColorRole.ButtonText, c(SUMI))
    p.setColor(QPalette.ColorRole.Highlight, c(AI))
    p.setColor(QPalette.ColorRole.HighlightedText, c(GOFUN))
    p.setColor(QPalette.ColorRole.ToolTipBase, c(SUMI))
    p.setColor(QPalette.ColorRole.ToolTipText, c(SHIRONERI))
    p.setColor(QPalette.ColorRole.PlaceholderText, c(USUZUMI))
    for grp in (QPalette.ColorGroup.Disabled,):
        p.setColor(grp, QPalette.ColorRole.Text, c(USUZUMI))
        p.setColor(grp, QPalette.ColorRole.ButtonText, c(USUZUMI))
        p.setColor(grp, QPalette.ColorRole.WindowText, c(USUZUMI))
    return p


STYLESHEET = f"""
* {{ outline: none; }}

QWidget {{
    font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 10pt;
    color: {SUMI};
}}

QMainWindow, QDialog {{ background: {KINARI}; }}

/* ── 菜单栏 ───────────────────────────────────────────── */
QMenuBar {{
    background: {KINARI};
    border-bottom: 1px solid {BORDER_SOFT};
    padding: 2px 4px;
}}
QMenuBar::item {{ padding: 5px 11px; border-radius: 5px; background: transparent; }}
QMenuBar::item:selected {{ background: {HOVER}; }}
QMenu {{
    background: {SHIRONERI};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 5px;
}}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {AI_WASH}; color: {AI}; }}
QMenu::separator {{ height: 1px; background: {BORDER_SOFT}; margin: 4px 8px; }}

/* ── 工具栏 ───────────────────────────────────────────── */
QToolBar {{
    background: {SHIRONERI};
    border: 0;
    border-bottom: 1px solid {BORDER_SOFT};
    padding: 5px 8px;
    spacing: 3px;
}}
QToolBar#bottomBar {{
    border-bottom: 0;
    border-top: 1px solid {BORDER_SOFT};
}}
QToolBar::separator {{
    width: 1px; background: {BORDER_SOFT}; margin: 5px 7px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 10px;
}}
QToolButton:hover {{ background: {HOVER}; border-color: {BORDER}; }}
QToolButton:pressed, QToolButton:checked {{
    background: {AI_WASH}; border-color: {AI}; color: {AI};
}}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* ── 按钮 ─────────────────────────────────────────────── */
QPushButton {{
    background: {SHIRONERI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {BORDER_SOFT}; }}
QPushButton:disabled {{ color: {USUZUMI}; background: {KINARI}; border-color: {BORDER_SOFT}; }}
QPushButton:checked {{ background: {AI_WASH}; border-color: {AI}; color: {AI}; font-weight: 600; }}
QPushButton#primary {{
    background: {AI}; color: {GOFUN}; border-color: {AI}; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {AI_HOVER}; border-color: {AI_HOVER}; }}
QPushButton#primary:disabled {{ background: {BORDER_SOFT}; color: {USUZUMI}; border-color: {BORDER_SOFT}; }}

/* ── 输入 ─────────────────────────────────────────────── */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {SHIRONERI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {AI};
    selection-color: {GOFUN};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{ border-color: {AI}; }}
QLineEdit:read-only {{ background: {KINARI}; color: {NIBI}; }}
QComboBox::drop-down {{ border: 0; width: 20px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {NIBI};
    margin-right: 7px;
}}
QComboBox QAbstractItemView {{
    background: {SHIRONERI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 3px;
    selection-background-color: {AI_WASH};
    selection-color: {AI};
}}

/* ── 列表 / 表格 ───────────────────────────────────────── */
QListWidget, QTableWidget, QTreeWidget {{
    background: {SHIRONERI};
    border: 1px solid {BORDER_SOFT};
    border-radius: 8px;
    alternate-background-color: {KINARI};
}}
QListWidget::item {{ padding: 6px 4px; border-radius: 6px; margin: 1px 3px; }}
QListWidget::item:hover {{ background: {HOVER}; }}
QListWidget::item:selected {{ background: {AI_WASH}; color: {SUMI}; }}
QHeaderView::section {{
    background: {KINARI};
    color: {NIBI};
    border: 0;
    border-bottom: 1px solid {BORDER};
    padding: 6px 5px;
    font-weight: 600;
}}
QTableWidget {{ gridline-color: {BORDER_SOFT}; }}
QTableWidget::item {{ padding: 3px 5px; }}
QTableWidget::item:selected {{ background: {AI_WASH}; color: {SUMI}; }}

/* ── Tab ──────────────────────────────────────────────── */
QTabWidget::pane {{ border: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {NIBI};
    border: 0;
    border-bottom: 2px solid transparent;
    padding: 7px 12px;
    margin-right: 2px;
}}
QTabBar::tab:hover {{ color: {SUMI}; }}
QTabBar::tab:selected {{ color: {AI}; border-bottom-color: {AI}; font-weight: 600; }}

/* ── 进度条 ───────────────────────────────────────────── */
QProgressBar {{
    background: {BORDER_SOFT};
    border: 0;
    border-radius: 5px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {MATSUBA}; border-radius: 5px; }}

/* ── 分组框 ───────────────────────────────────────────── */
QGroupBox {{
    background: {SHIRONERI};
    border: 1px solid {BORDER_SOFT};
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px 10px 8px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 11px;
    padding: 0 5px;
    color: {AI};
}}

/* ── 勾选框 ───────────────────────────────────────────── */
QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {SHIRONERI};
}}
QCheckBox::indicator:hover {{ border-color: {AI}; }}
QCheckBox::indicator:checked {{ background: {AI}; border-color: {AI}; }}

/* ── 滑块 ─────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER_SOFT}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {AI}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -6px 0;
    background: {SHIRONERI};
    border: 2px solid {AI};
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ background: {AI_WASH}; }}

/* ── 分割条 ───────────────────────────────────────────── */
QSplitter::handle {{ background: {BORDER_SOFT}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:hover {{ background: {AI}; }}

/* ── 滚动条 ───────────────────────────────────────────── */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 4px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {USUZUMI}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {BORDER}; border-radius: 4px; min-width: 28px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ── 状态栏 ───────────────────────────────────────────── */
QStatusBar {{
    background: {SHIRONERI};
    border-top: 1px solid {BORDER_SOFT};
    color: {NIBI};
}}
QStatusBar::item {{ border: 0; }}

/* ── 提示 ─────────────────────────────────────────────── */
QToolTip {{
    background: {SUMI};
    color: {SHIRONERI};
    border: 0;
    border-radius: 6px;
    padding: 6px 9px;
}}

/* ── 画布：深色片盒 ─────────────────────────────────────── */
QGraphicsView {{ background: {CANVAS_BG}; border: 0; }}
"""


def apply(app) -> None:
    app.setStyle("Fusion")
    app.setPalette(palette())
    app.setStyleSheet(STYLESHEET)

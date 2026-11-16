"""Colours, fonts and the single application stylesheet."""
from __future__ import annotations

C = dict(
    bg="#0D0F14", surface="#12151B", card="#171B23", card2="#1D222C", border="#262C38", border_hi="#38405A",
    text="#EEF0F6", muted="#97A0B2", faint="#5F687B",
    accent="#8B7CFF", accent2="#4FC3F7", accent_dim="#262350", accent_soft="#2F2B63",
    ok="#4ADE80", warn="#F5B94A", bad="#F87171",
)
FONT = '"Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial, sans-serif'


def qss() -> str:
    c = C
    return f"""
* {{ font-family: {FONT}; font-size: 13px; color: {c['text']}; outline: none; }}
QMainWindow, QDialog, QWidget#Root {{ background: {c['bg']}; }}
QWidget#Page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QToolTip {{ background: {c['card2']}; color: {c['text']}; border: 1px solid {c['border_hi']}; padding: 6px 8px;
           border-radius: 6px; }}

QFrame#Card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 16px; }}
QFrame#CardFlat {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QFrame#Rail {{ background: {c['surface']}; border-right: 1px solid {c['border']}; }}
QFrame#Footer {{ background: {c['surface']}; border-top: 1px solid {c['border']}; }}
QFrame#Divider {{ background: {c['border']}; max-height: 1px; min-height: 1px; border: none; }}

QLabel[role="display"] {{ font-size: 30px; font-weight: 700; letter-spacing: 0.2px; }}
QLabel[role="title"] {{ font-size: 22px; font-weight: 650; }}
QLabel[role="h2"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="sub"] {{ font-size: 14px; color: {c['muted']}; }}
QLabel[role="muted"] {{ color: {c['muted']}; font-size: 12px; }}
QLabel[role="faint"] {{ color: {c['faint']}; font-size: 11px; }}
QLabel[role="chip"] {{ background: {c['accent_soft']}; color: #CFC9FF; border-radius: 9px; padding: 2px 9px;
                       font-size: 11px; font-weight: 600; }}
QLabel[role="chipwarn"] {{ background: #3A2F17; color: {c['warn']}; border-radius: 9px; padding: 2px 9px;
                           font-size: 11px; font-weight: 600; }}
QLabel[role="value"] {{ color: {c['text']}; font-weight: 600; min-width: 70px; }}

QPushButton {{ background: {c['card2']}; border: 1px solid {c['border_hi']}; border-radius: 10px;
               padding: 9px 18px; font-weight: 600; }}
QPushButton:hover {{ background: #262C3A; border-color: #4A5370; }}
QPushButton:pressed {{ background: #1A1F29; }}
QPushButton:disabled {{ color: {c['faint']}; background: {c['surface']}; border-color: {c['border']}; }}
QPushButton#Primary {{ border: none; color: white; padding: 11px 26px; border-radius: 11px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7A6BFF, stop:1 #5B8CFF); }}
QPushButton#Primary:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8A7CFF, stop:1 #6B9AFF); }}
QPushButton#Primary:disabled {{ background: {c['card2']}; color: {c['faint']}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {c['muted']}; }}
QPushButton#Ghost:hover {{ background: {c['card2']}; color: {c['text']}; }}
QPushButton#Danger {{ background: transparent; border: 1px solid #5A2F36; color: {c['bad']}; }}
QPushButton#Danger:hover {{ background: #2B171B; }}
QPushButton#Seg {{ background: transparent; border: none; border-radius: 8px; padding: 7px 16px; color: {c['muted']};
                   font-weight: 600; }}
QPushButton#Seg:hover {{ color: {c['text']}; }}
QPushButton#Seg:checked {{ background: {c['accent_soft']}; color: white; }}
QFrame#SegBar {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 11px; }}
QToolButton#Help {{ background: {c['card2']}; border: 1px solid {c['border_hi']}; border-radius: 9px; color: {c['muted']};
                    font-weight: 700; font-size: 11px; min-width: 18px; max-width: 18px; min-height: 18px;
                    max-height: 18px; }}
QToolButton#Help:hover {{ background: {c['accent_soft']}; color: white; border-color: {c['accent']}; }}
QToolButton#Link {{ background: transparent; border: none; color: {c['accent2']}; font-weight: 600; }}
QToolButton#Link:hover {{ color: white; }}

QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {c['surface']}; border: 1px solid {c['border_hi']};
    border-radius: 9px; padding: 8px 10px; selection-background-color: {c['accent']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {c['card2']}; border: 1px solid {c['border_hi']}; selection-background-color:
    {c['accent_soft']}; padding: 4px; }}

QSlider::groove:horizontal {{ height: 6px; background: {c['border']}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7A6BFF, stop:1 #5B8CFF);
                                border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; width: 18px; height: 18px; margin: -6px 0; border-radius: 9px;
                              border: 3px solid {c['accent']}; }}
QSlider::handle:horizontal:hover {{ border-color: #B3A9FF; }}

QProgressBar {{ background: {c['border']}; border: none; border-radius: 5px; height: 10px; text-align: center;
                color: transparent; }}
QProgressBar::chunk {{ border-radius: 5px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7A6BFF,
                       stop:1 #4FC3F7); }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border_hi']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {c['muted']}; padding: 8px 16px; border-radius: 8px; margin-right: 4px;
                font-weight: 600; }}
QTabBar::tab:selected {{ background: {c['accent_soft']}; color: white; }}
"""

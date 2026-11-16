"""'Developed by …' signature and the 'Buy me a coffee' UPI dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import branding
from .theme import C
from .widgets import label


def qr_pixmap(data: str, size: int = 260) -> QPixmap:
    """A crisp black-on-white QR code for `data`."""
    import qrcode
    border = 4                                    # the standard quiet zone: scanners need it to find the code
    probe = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=border)
    probe.add_data(data)
    probe.make(fit=True)
    modules = probe.modules_count + 2 * border
    # a WHOLE number of pixels per square: resizing to an arbitrary size blurs the edges and breaks scanning
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=max(3, size // modules),
                       border=border)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    w, h = img.size
    return QPixmap.fromImage(QImage(img.tobytes(), w, h, 3 * w, QImage.Format_RGB888).copy())


class CoffeeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buy me a coffee")
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 28, 30, 26)
        lay.setSpacing(12)
        lay.setAlignment(Qt.AlignHCenter)
        lay.setSizeConstraint(QVBoxLayout.SetFixedSize)      # the dialog is exactly as tall as its content
        title = label("Buy me a coffee  ☕", "title")
        title.setAlignment(Qt.AlignHCenter)
        lay.addWidget(title)
        text = label("If Mosaic Studio helped you make something you love, you can support its development. "
                     "Scan with any UPI app (GPay, PhonePe, Paytm, BHIM…). You choose the amount.", "sub", wrap=True)
        text.setAlignment(Qt.AlignHCenter)
        lay.addWidget(text)
        lay.addSpacing(4)

        frame = QFrame()
        frame.setStyleSheet("QFrame { background: white; border-radius: 18px; }")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(14, 14, 14, 14)
        qr = QLabel()
        pm = qr_pixmap(branding.upi_uri(), 250)
        qr.setPixmap(pm)
        qr.setFixedSize(pm.size())                  # never squeezed or cropped: a cut-off QR cannot be scanned
        qr.setStyleSheet("background: white;")
        fl.addWidget(qr)
        lay.addWidget(frame, 0, Qt.AlignHCenter)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        self.upi_lb = QLabel(branding.UPI_ID)
        self.upi_lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.upi_lb.setStyleSheet(f"color: {C['text']}; font-weight: 600; font-size: 14px;")
        self.copy_btn = QPushButton("Copy UPI ID")
        self.copy_btn.clicked.connect(self._copy)
        row.addWidget(self.upi_lb)
        row.addWidget(self.copy_btn)
        row.addStretch(1)
        lay.addLayout(row)
        who = label(f"{branding.UPI_NAME}", "muted")
        who.setAlignment(Qt.AlignHCenter)
        lay.addWidget(who)
        thanks = label("Thank you! It means a lot.", "muted")
        thanks.setAlignment(Qt.AlignHCenter)
        lay.addWidget(thanks)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignHCenter)

    def _copy(self):
        QGuiApplication.clipboard().setText(branding.UPI_ID)
        self.copy_btn.setText("Copied ✓")
        QTimer.singleShot(1600, lambda: self.copy_btn.setText("Copy UPI ID"))


class Signature(QWidget):
    """'Developed by Sourav' plus (when a UPI ID is set) a 'Buy me a coffee' button."""

    def __init__(self, compact: bool = False, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self) if compact else QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6 if compact else 14)
        self.credit = QLabel(f"<span style='color:{C['accent']}'>◆</span>&nbsp;&nbsp;{branding.CREDIT}")
        self.credit.setTextFormat(Qt.RichText)
        self.credit.setStyleSheet(f"color: {C['muted']}; font-size: 12px; font-weight: 600;")
        lay.addWidget(self.credit)
        self.button = QPushButton("☕  Buy me a coffee")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setObjectName("Ghost")
        self.button.setStyleSheet(f"QPushButton {{ color: {C['accent2']}; text-align: left; padding: 6px 8px;"
                                  f" font-size: 12px; }} QPushButton:hover {{ color: white; }}")
        self.button.clicked.connect(lambda: CoffeeDialog(self.window()).exec())
        self.button.setVisible(branding.has_upi())
        lay.addWidget(self.button, 0, Qt.AlignLeft)

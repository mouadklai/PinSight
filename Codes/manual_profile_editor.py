import copy
import numpy as np
from enum import Enum
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QMessageBox
)
from PySide6.QtGui import (
    QPixmap, QPainter, QImage,
    QPen, QColor, QFont, QKeySequence, QShortcut
)
from PySide6.QtCore import Qt, QPointF


MAX_UNDO = 60
# =====================================================
# WORKFLOW STEPS
# =====================================================
class Step(Enum):
    ROI = 0
    X_CALIB = 1   
    Z_CALIB = 2     
    PINS = 3


# =====================================================
# IMAGE CANVAS WITH STATE + UNDO SUPPORT
# =====================================================
class ImageCanvas(QLabel):
    def __init__(self, pixmap):
        super().__init__()
        self.pixmap_orig = pixmap
        self.setAlignment(Qt.AlignCenter)

        self.reset()

        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

    def reset(self):
        self.points = []
        self.pins = []
        self.x_calib = None   # [(x1,y1), (x2,y2)]
        self.z_calib = None   # [(x3,y3), (x4,y4)]
        self.x_len_cm = None
        self.z_len_cm = None
        self.mode = "points"
        self.selected = None
        self.roi_rect = None      # (x0, y0, x1, y1) in image coords
        self.roi_points = []     # temporary clicks

    # -----------------------------
    def resizeEvent(self, event):
        scaled = self.pixmap_orig.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.setPixmap(scaled)
        self.scale = scaled.width() / self.pixmap_orig.width()
        self.offset_x = (self.width() - scaled.width()) / 2
        self.offset_y = (self.height() - scaled.height()) / 2

    def widget_to_image(self, pos):
        x = (pos.x() - self.offset_x) / self.scale
        y = (pos.y() - self.offset_y) / self.scale
        return int(x), int(y)

    # -----------------------------
    def mousePressEvent(self, event):
        ix, iy = self.widget_to_image(event.position().toPoint())
        if self.mode == "roi":
            self.roi_points.append((ix, iy))
            if len(self.roi_points) == 2:
                x0, y0 = self.roi_points[0]
                x1, y1 = self.roi_points[1]
                self.roi_rect = (
                    min(x0, x1),
                    min(y0, y1),
                    max(x0, x1),
                    max(y0, y1)
                )
                self.parent().push_state()
            self.update()
            return
        

        if self.mode == "points":
            self.points.append((ix, iy))
            self.parent().push_state()
            self.update()
            return

        if self.mode == "pins":
            if event.button() == Qt.LeftButton:
                for i, p in enumerate(self.pins):
                    if np.hypot(p[0] - ix, p[1] - iy) < 18:
                        self.selected = i
                        return
                self.pins.append([ix, iy])
                self.parent().push_state()

            elif event.button() == Qt.RightButton:
                self.pins = [
                    p for p in self.pins
                    if np.hypot(p[0] - ix, p[1] - iy) > 18
                ]
                self.parent().push_state()

            self.update()

    def mouseMoveEvent(self, event):
        if self.selected is not None:
            ix, iy = self.widget_to_image(event.position().toPoint())
            self.pins[self.selected] = [ix, iy]
            self.update()

    def mouseReleaseEvent(self, event):
        if self.selected is not None:
            self.parent().push_state()
        self.selected = None

    # -----------------------------
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.translate(self.offset_x, self.offset_y)
        painter.scale(self.scale, self.scale)

        # ===== ROI =====
        if self.roi_rect:
            painter.setPen(QPen(QColor(255, 0, 0), 3, Qt.DashLine))
            x0, y0, x1, y1 = self.roi_rect
            painter.drawRect(x0, y0, x1 - x0, y1 - y0)

                
        # ===== AXIS GRADUATIONS =====
        if self.x_calib and self.x_len_cm:
            self.draw_axis(painter,
                        self.x_calib[0],
                        self.x_calib[1],
                        self.x_len_cm,
                        horizontal=True)

        if self.z_calib and self.z_len_cm:
            self.draw_axis(painter,
                        self.z_calib[0],
                        self.z_calib[1],
                        self.z_len_cm,
                        horizontal=False)




        # ===== POINTS =====
        painter.setPen(QPen(QColor(255, 255, 0), 4))
        for p in self.points:
            painter.drawEllipse(QPointF(*p), 16, 16)

        # ===== PINS =====
        painter.setPen(QPen(QColor(255, 140, 0), 4))
        for i, p in enumerate(self.pins):
            painter.drawEllipse(QPointF(*p), 12, 12)
            if i > 0:
                painter.drawLine(QPointF(*self.pins[i - 1]),
                                 QPointF(*self.pins[i]))
                    
    def draw_axis(self, painter, p1, p2, length_cm, horizontal=True):
        x1, y1 = p1
        x2, y2 = p2

        painter.setPen(QPen(QColor(0, 255, 255), 3))
        painter.drawLine(x1, y1, x2, y2)

        # direction vector
        dx = x2 - x1
        dy = y2 - y1
        L = np.hypot(dx, dy)
        if L == 0:
            return

        ux = dx / L
        uy = dy / L

        # perpendicular direction (for tick marks)
        px = -uy
        py = ux

        tick_spacing = 1.0  # 1 cm graduations
        n_ticks = int(length_cm // tick_spacing)

        painter.setFont(QFont("Arial", 10))
        painter.setPen(QPen(QColor(0, 255, 255), 2))

        for i in range(n_ticks + 1):
            t = (i * tick_spacing) / length_cm
            xt = x1 + dx * t
            yt = y1 + dy * t

            # tick length (in pixels)
            tick_len = 15

            painter.drawLine(
                xt - px * tick_len / 2,
                yt - py * tick_len / 2,
                xt + px * tick_len / 2,
                yt + py * tick_len / 2
            )

            painter.drawText(
                xt + px * 20,
                yt + py * 20,
                f"{i}"
            )

def intersect_lines(p1, p2, p3, p4):
    p1, p2, p3, p4 = map(np.array, (p1, p2, p3, p4))
    d1 = p2 - p1
    d2 = p4 - p3
    A = np.vstack([d1, -d2]).T
    b = p3 - p1
    t, _ = np.linalg.lstsq(A, b, rcond=None)[0]
    return p1 + t * d1

# =====================================================
# MANUAL PROFILE EDITOR (USED BY PINSIGHT)
# =====================================================
class ManualProfileEditor(QDialog):
    def __init__(self, image_rgb, initial_state=None, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Manual Profile Editor")
        self.resize(1200, 750)

        self.image_rgb = image_rgb

        self.step = Step.ROI
        self.undo_stack = []
        self.redo_stack = []

        h, w, _ = image_rgb.shape
        qimg = QImage(image_rgb.data, w, h, w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg)

        self.canvas = ImageCanvas(pix)

        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.input = QLineEdit()
        self.input.setFixedWidth(160)

        self.btn_next = QPushButton("Next ▶")
        self.btn_crop = QPushButton("Crop ROI")
        self.btn_undo = QPushButton("↶ Undo")
        self.btn_redo = QPushButton("↷ Redo")
        self.btn_finish = QPushButton("Finish")

        self.btn_crop.clicked.connect(self.crop_roi_and_continue)
        self.btn_next.clicked.connect(self.next_step)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo.clicked.connect(self.redo)
        self.btn_finish.clicked.connect(self.accept)

        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.redo)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addWidget(self.canvas, 1)

        self.length_label = QLabel("Length (cm):")

        row = QHBoxLayout()
        
        row.addWidget(self.length_label)
        row.addWidget(self.input)
        row.addWidget(self.btn_next)
        row.addWidget(self.btn_crop)   # 👈 add this
        row.addStretch()
        row.addWidget(self.btn_undo)
        row.addWidget(self.btn_redo)
        row.addWidget(self.btn_finish)
        layout.addLayout(row)

        if initial_state:
            snapshot = initial_state.get("snapshot")
            undo_history = initial_state.get("undo_history", [])
            redo_history = initial_state.get("redo_history", [])

            if snapshot:
                self.restore_state(snapshot)
                if undo_history:
                    self.undo_stack = undo_history
                else:
                    self.undo_stack = [snapshot]
                self.redo_stack = redo_history
        else:
            self.push_state()

        self.update_ui()

    # -----------------------------
    def current_state(self):
        return {
            "image_rgb": self.image_rgb.copy(),
            "pins": [p.copy() for p in self.canvas.pins],
            "x_calib": self.canvas.x_calib,
            "z_calib": self.canvas.z_calib,
            "x_len_cm": self.canvas.x_len_cm,
            "z_len_cm": self.canvas.z_len_cm,
            "step": self.step,
            "roi_rect": self.canvas.roi_rect,
        }
    
    def accept(self):
        """
        Intercept Finish / OK to ensure the manual workflow is complete.
        """
        if not self.is_profile_complete():
            reply = QMessageBox.question(
                self,
                "Manual profile not finished",
                "The manual profile is not fully completed yet.\n\n"
                "Do you want to continue editing or cancel and discard this profile?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            # Yes → continue editing
            if reply == QMessageBox.Yes:
                return

            # No → discard and close
            super().reject()
            return

        # Profile complete → normal close
        super().accept()
    def closeEvent(self, event):
        if not self.is_profile_complete():
            reply = QMessageBox.question(
                self,
                "Manual profile not finished",
                "The manual profile is not fully completed yet.\n\n"
                "Do you want to continue editing or cancel and discard this profile?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                event.ignore()
                return

            event.accept()
            return

        event.accept()
    def push_state(self):
        self.undo_stack.append(copy.deepcopy(self.current_state()))
        self.redo_stack.clear()
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)

    def restore_state(self, state):
        # --- restore image data ---
        self.image_rgb = state["image_rgb"].copy()

        h, w, _ = self.image_rgb.shape
        qimg = QImage(
            self.image_rgb.data,
            w,
            h,
            w * 3,
            QImage.Format_RGB888
        )
        pix = QPixmap.fromImage(qimg)

        self.canvas.pixmap_orig = pix

        # --- restore annotations ---
        self.canvas.pins = copy.deepcopy(state.get("pins", []))
        self.canvas.x_calib = state.get("x_calib")
        self.canvas.z_calib = state.get("z_calib")
        self.canvas.x_len_cm = state.get("x_len_cm")
        self.canvas.z_len_cm = state.get("z_len_cm")
        self.canvas.roi_rect = state.get("roi_rect", None)
        self.step = state.get("step", Step.ROI)

        # --- force redraw ---
        scaled = pix.scaled(
            self.canvas.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.canvas.setPixmap(scaled)
        self.canvas.scale = scaled.width() / pix.width()
        self.canvas.offset_x = (self.canvas.width() - scaled.width()) / 2
        self.canvas.offset_y = (self.canvas.height() - scaled.height()) / 2

        self.canvas.update()
        self.update_ui()

    def is_profile_complete(self):
        """
        Returns True if the manual profile is fully defined.
        """
        return (
            self.step == Step.PINS and
            self.canvas.x_calib is not None and
            self.canvas.z_calib is not None and
            self.canvas.x_len_cm is not None and
            self.canvas.z_len_cm is not None and
            len(self.canvas.pins) > 0
        )
    
    def undo(self):
        # 🔁 SPECIAL CASE: Step 0 (ROI)
        if self.step == Step.ROI:
            # Restart Step 0 completely
            self.canvas.roi_points.clear()
            self.canvas.roi_rect = None
            self.canvas.update()
            return
        if len(self.undo_stack) <= 1:
            return
        self.redo_stack.append(self.undo_stack.pop())
        self.restore_state(self.undo_stack[-1])

    def redo(self):
        if not self.redo_stack:
            return
        state = self.redo_stack.pop()
        self.undo_stack.append(state)
        self.restore_state(state)

    # -----------------------------
    def update_ui(self):
        self.input.setVisible(False)
        self.length_label.setVisible(False)
        self.canvas.points.clear()
        self.input.clear()

        # Default visibility
        self.input.setVisible(False)
        self.btn_next.setVisible(True)
        self.btn_crop.setVisible(False)

        if self.step == Step.X_CALIB:
            if not self.canvas.x_len_cm:
                self.input.setText("113")
            self.input.setVisible(True)
            self.length_label.setText("Horizontal length (cm):")
            self.length_label.setVisible(True)

        elif self.step == Step.Z_CALIB:
            if not self.canvas.z_len_cm:
                self.input.setText("53")
            self.input.setVisible(True)
            self.length_label.setText("Vertical length (cm):")
            self.length_label.setVisible(True)

        if self.step == Step.ROI:
            self.info.setText(
                "STEP 0 – SELECT REGION OF INTEREST (ROI)\n"
                "Click TWO opposite corners of the profile area,\n"
                "then click CROP to continue."
            )
            self.canvas.mode = "roi"
            self.btn_next.setVisible(False)
            self.btn_crop.setVisible(True)

        elif self.step == Step.X_CALIB:
            self.info.setText(
                "STEP 1 – DEFINE X AXIS (points 1–2)"
            )
            self.canvas.mode = "points"
            self.input.setVisible(True)
            self.length_label.setVisible(True)

        elif self.step == Step.Z_CALIB:
            self.info.setText(
                "STEP 2 – DEFINE Z AXIS (points 3–4)"
            )
            self.canvas.mode = "points"
            self.input.setVisible(True)
            self.length_label.setVisible(True)
            


        elif self.step == Step.PINS:
            self.btn_next.setVisible(False)
            self.info.setText(
                "STEP 3 – DIGITIZE SURFACE\n"
                "Left-click: add pin\n"
                "Drag: move pin\n"
                "Right-click: delete pin\n"
                "Undo/Redo supported"
            )
            self.canvas.mode = "pins"

    def crop_roi_and_continue(self):
        if self.canvas.roi_rect is None:
            QMessageBox.warning(self, "Error", "Please select a region of interest.")
            return

        # ✅ SAVE PRE-CROP STATE (this is the important one)
        self.push_state()

        x0, y0, x1, y1 = self.canvas.roi_rect

        # --- Crop image data ---
        self.image_rgb = self.image_rgb[y0:y1, x0:x1].copy()
        self.info.setText("ROI cropped. Define horizontal scale.")

        # --- Build new pixmap ---
        h, w, _ = self.image_rgb.shape
        qimg = QImage(
            self.image_rgb.data,
            w,
            h,
            w * 3,
            QImage.Format_RGB888
        )
        pix = QPixmap.fromImage(qimg)

        # --- Reset canvas state completely ---
        self.canvas.reset()
        self.canvas.pixmap_orig = pix

        # --- Clear ROI visuals ---
        self.canvas.roi_rect = None
        self.canvas.roi_points.clear()

        # --- FORCE QLabel to display new pixmap ---
        scaled = pix.scaled(
            self.canvas.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.canvas.setPixmap(scaled)

        self.canvas.scale = scaled.width() / pix.width()
        self.canvas.offset_x = (self.canvas.width() - scaled.width()) / 2
        self.canvas.offset_y = (self.canvas.height() - scaled.height()) / 2

        # --- Advance workflow ---
        self.step = Step.X_CALIB

        # ❌ REMOVE THIS:
        # self.push_state()

        self.update_ui()


    def next_step(self):
        # -----------------------------
        if self.step == Step.ROI:
            if self.canvas.roi_rect is None:
                QMessageBox.warning(self, "Error", "Please select a region of interest.")
                return

            self.step = Step.X_CALIB
            self.push_state()
            self.update_ui()
            return

        # -----------------------------
        try:
            if self.step == Step.X_CALIB:
                if len(self.canvas.points) != 2:
                    QMessageBox.warning(self, "Error", "Select exactly 2 points.")
                    return

                self.canvas.x_calib = self.canvas.points.copy()

                length = float(self.input.text())
                if length <= 0:
                    raise ValueError("Length must be positive.")
                self.canvas.x_len_cm = length

                self.canvas.points.clear()
                self.step = Step.Z_CALIB

            elif self.step == Step.Z_CALIB:
                if len(self.canvas.points) != 2:
                    QMessageBox.warning(self, "Error", "Select exactly 2 points.")
                    return

                self.canvas.z_calib = self.canvas.points.copy()

                length = float(self.input.text())
                if length <= 0:
                    raise ValueError("Length must be positive.")
                self.canvas.z_len_cm = length

                self.canvas.points.clear()
                self.step = Step.PINS


            else:
                return

            # ✅ THESE TWO LINES WERE MISSING
            self.push_state()
            self.update_ui()

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
                

    def get_result(self):
        """
        Returns the manually digitized surface profile.

         -faithful implementation.
        All coordinates are expressed in physical units (cm).
        """

        # --------------------------------------------------
        # 1. Raw calibration points (image coordinates)
        # --------------------------------------------------
        (x1, y1), (x2, y2) = self.canvas.x_calib   # X axis
        (x3, y3), (x4, y4) = self.canvas.z_calib   # Z axis

        # --------------------------------------------------
        # 2.   scaling of ALL clicked points
        # --------------------------------------------------
        # Compute norms exactly like  
        normeu = np.hypot(x2 - x1, y2 - y1)
        normev = np.hypot(x4 - x3, y4 - y3)

        # Scale all clicked points (calibration + pins)
        all_points = (
            [self.canvas.x_calib[0], self.canvas.x_calib[1],
            self.canvas.z_calib[0], self.canvas.z_calib[1]]
            + self.canvas.pins
        )

        xf = np.array([p[0] * self.canvas.x_len_cm / normeu for p in all_points])
        yf = np.array([p[1] * self.canvas.z_len_cm / normev for p in all_points])

        # --------------------------------------------------
        # 3.   basis vectors (NOT orthonormal)
        # --------------------------------------------------
        xu1 = (xf[1] - xf[0]) / self.canvas.x_len_cm
        yu1 = (yf[1] - yf[0]) / self.canvas.x_len_cm

        xv1 = (xf[3] - xf[2]) / self.canvas.z_len_cm
        yv1 = (yf[3] - yf[2]) / self.canvas.z_len_cm


        # --------------------------------------------------
        # 4. Intersection of axes (origin O)
        # --------------------------------------------------
        x0, y0 = intersect_lines(
            self.canvas.x_calib[0], self.canvas.x_calib[1],
            self.canvas.z_calib[0], self.canvas.z_calib[1]
        )

        # Convert origin to scaled space
        x0 = x0 * self.canvas.x_len_cm / normeu
        y0 = y0 * self.canvas.z_len_cm / normev

        # --------------------------------------------------
        # 5. Project points → (xn, yn) (  equations)
        # --------------------------------------------------
        xn = []
        yn = []

        for i in range(len(all_points)):
            xOM = xf[i] - x0
            yOM = yf[i] - y0

            xn.append(xOM * xu1 + yOM * yu1)
            yn.append(xOM * xv1 + yOM * yv1)

        xn = np.array(xn)
        yn = np.array(yn)

        # --------------------------------------------------
        # 6. Remove calibration points (first 4)
        # --------------------------------------------------
        xm = xn[4:]
        ym = yn[4:]

        # --------------------------------------------------
        # 7.   leveling (REMOVE SLOPE FIRST)
        # --------------------------------------------------
        #pente, origine = np.polyfit(xm, ym, 1)
        #ym = ym - (pente * xm + origine)

        # --------------------------------------------------
        # 8.   Δx filtering
        # --------------------------------------------------
        #filtered = []
        #filtered.append((xm[0], ym[0]))

        #for k in range(1, len(xm)):
            #dx = abs(xm[k] - xm[k - 1])
            #filtered.append((xm[k], (ym[k] + ym[k - 1]) / 2))
        #    filtered.append((xm[k], ym[k]))
            #if dx >  _MAX_DX:
            #    filtered.append((xm[k], (ym[k] + ym[k - 1]) / 2))
            #elif dx >  _MIN_DX:
            #    filtered.append((xm[k], ym[k]))
            # else: discard (exact   behavior)

        # --------------------------------------------------
        # 9. Output pins (cm)
        # --------------------------------------------------
        pins_manual = [{
                'x': float(xm[k]),   # cm
                'y': 0.0,
                'h': float( ym[k] )    # cm
            } for k in range(xm.shape[0])]

        # --------------------------------------------------
        # 10. Return result
        # --------------------------------------------------
        return {
            "warped_image": self.image_rgb,
            "pins": pins_manual,
            "units": "cm",
            "calibration": {
                "x": {
                    "points": self.canvas.x_calib,
                    "length_cm": self.canvas.x_len_cm 
                },
                "z": {
                    "points": self.canvas.z_calib,
                    "length_cm": self.canvas.z_len_cm
                }
            },
            "editor_state": {
                "snapshot": self.current_state(),
                "undo_history": copy.deepcopy(self.undo_stack),
                "redo_history": copy.deepcopy(self.redo_stack),
            }
        }

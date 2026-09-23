# ==============================
# PinSight v0.1
# Author: Dr. Mouad Klai
# ==============================

import sys
import cv2
import numpy as np
import os
import ctypes
import csv
from scipy.stats import linregress
import requests
# --- MATPLOTLIB SETUP ---
import matplotlib
matplotlib.use('qtagg')  # backend_qtagg is best for PySide6
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QSplashScreen, QVBoxLayout, 
                             QHBoxLayout, QWidget, QLabel, QFileDialog, QFrame, 
                             QLineEdit, QProgressBar, QStackedWidget, QTableWidget, 
                             QTableWidgetItem, QSizePolicy, QHeaderView, QDialog, 
                             QTextEdit, QGroupBox, QSplitter, QMessageBox, QAbstractItemView)
from PySide6.QtGui import QDesktopServices, QImage, QPainter, QPen, QPixmap, QIcon, QColor
from PySide6.QtCore import QPointF, QUrl, Qt, QThread, Signal, QTimer

APP_VERSION = "0.1"
# --- WINDOWS TASKBAR LOGO FIX ---
try:
    myappid = 'klai.pinsight.v0.1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ============================================================
# === SHARED KERNELS (CREATED ONCE)
# ============================================================
KERNEL_RECT_7 = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
KERNEL_RECT_1x7 = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 7))
KERNEL_ELLIPSE_3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
KERNEL_HORZ_15 = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))


# ============================================================
# === OPTIMIZED PIN TEXTURE SCORE
# ============================================================
def pin_texture_score(img_gray, mask):
    """
    Higher score = more likely this region contains pins
    Optimized:
    - ROI crop
    - No contours
    - Scharr gradients
    """
    x, y, w, h = cv2.boundingRect(mask)
    if w == 0 or h == 0:
        return 0.0

    roi = img_gray[y:y+h, x:x+w]
    mask_roi = mask[y:y+h, x:x+w]

    roi = cv2.bitwise_and(roi, roi, mask=mask_roi)

    # --- Edge density ---
    edges = cv2.Canny(roi, 60, 180)
    edge_density = cv2.countNonZero(edges) / (cv2.countNonZero(mask_roi) + 1e-6)

    # --- Vertical texture dominance ---
    gx = cv2.Scharr(roi, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(roi, cv2.CV_32F, 0, 1)
    vertical_ratio = np.mean(np.abs(gy)) / (np.mean(np.abs(gx)) + 1e-6)

    # --- Thin vertical activity (no contours) ---
    _, bw = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, KERNEL_RECT_1x7)

    thin_activity = cv2.countNonZero(bw) / (h + 1e-6)

    return (
        2.0 * edge_density +
        1.5 * vertical_ratio +
        0.05 * thin_activity
    )


# ============================================================
# === FALLBACK BOARD + PIN EXTRACTION
# ============================================================
def extract_board_Semantic(
    img,
    img_rgb,
    gray,
    left_expand_px=80,
    right_expand_px=80
):
    #Semantic Texture-Based Board Detector (STBD)


    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # --- Board segmentation ---
    board_mask = cv2.inRange(
        img_hsv,
        np.array([0, 0, 130]),
        np.array([180, 60, 255])
    )
    board_mask = cv2.morphologyEx(board_mask, cv2.MORPH_OPEN, KERNEL_RECT_7, 2)
    board_mask = cv2.morphologyEx(board_mask, cv2.MORPH_CLOSE, KERNEL_RECT_7, 2)
    board_mask = cv2.dilate(board_mask, KERNEL_RECT_7, 1)

    cnts, _ = cv2.findContours(board_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]

    best_score = -1
    board_cnt = None

    for c in cnts:
        if cv2.contourArea(c) < 2000:
            continue
        mask = np.zeros_like(gray)
        cv2.drawContours(mask, [c], -1, 255, -1)
        score = pin_texture_score(gray, mask)
        if score > best_score:
            best_score = score
            board_cnt = c

    # --- Geometry ---
    eps = 0.02 * cv2.arcLength(board_cnt, True)
    approx = cv2.approxPolyDP(board_cnt, eps, True)
    pts = approx.reshape(4, 2) if len(approx) == 4 else cv2.boxPoints(cv2.minAreaRect(board_cnt))

    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]

    rect[0][0] -= left_expand_px
    rect[3][0] -= left_expand_px
    rect[1][0] += right_expand_px
    rect[2][0] += right_expand_px

    # --- Warp ---
    dst_w, dst_h = 1200, 400
    dst = np.array([[0,0],[dst_w,0],[dst_w,dst_h],[0,dst_h]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(img_rgb, M, (dst_w, dst_h)) #Semantic Texture-Based Board Detector (STBD)

    return warped


def is_valid_pin_profiler_roi(warped_img, debug=False):
    """
    Determines if the warped image corresponds to a valid Pin Profiler board.
    
    This function analyzes the global characteristics of the image (texture, 
    brightness, and frequency) rather than relying on individual pin detection.
    
    Args:
        warped_img (np.array): The 1200x400 warped image from the extraction functions.
        debug (bool): If True, prints internal metric values for tuning.
        
    Returns:
        bool: True if the image is likely the pin profiler, False otherwise.
    """
    if warped_img is None or warped_img.size == 0:
        return False

    # 1. Convert to Grayscale
    if len(warped_img.shape) == 3:
        gray = cv2.cvtColor(warped_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = warped_img

    h, w = gray.shape

    # --- CHECK 1: GLOBAL BRIGHTNESS ---
    # The board is white. If the warped region is dark (e.g., clothing, soil), fail.
    # We ignore the black frame edges, so we look at the center.
    center_roi = gray[int(h*0.2):int(h*0.8), int(w*0.1):int(w*0.9)]
    avg_brightness = np.mean(center_roi)
    
    # Threshold: Board is usually > 100 in 0-255 scale outdoors. 
    # Dark clothing/soil usually < 80.
    if avg_brightness < 90:
        if debug: print(f"REJECT: Image too dark (Avg: {avg_brightness:.1f})")
        return False

    # --- CHECK 2: VERTICAL VS HORIZONTAL TEXTURE ---
    # The board is defined by vertical pins. Vertical edges should dominate horizontal ones.
    # We crop top/bottom text/rails to focus on the pins.
    pin_band = gray[int(h*0.3):int(h*0.8), :] 
    
    sx = cv2.Sobel(pin_band, cv2.CV_64F, 1, 0, ksize=3) # Vertical edges
    sy = cv2.Sobel(pin_band, cv2.CV_64F, 0, 1, ksize=3) # Horizontal edges
    
    mag_x = np.sum(np.abs(sx))
    mag_y = np.sum(np.abs(sy)) + 1e-6 # Avoid div/0
    
    ratio = mag_x / mag_y
    
    # Threshold: A pin board usually has a ratio > 1.5 or 2.0. 
    # General scenery is usually ~1.0.
    if ratio < 1.2:
        if debug: print(f"REJECT: Weak vertical texture (Ratio: {ratio:.2f})")
        return False

    # --- CHECK 3: PIN COUNT ESTIMATION (PROJECTION) ---
    # We project the image vertically to count "dark vs light" transitions.
    # This checks if there is a repeating pattern roughly matching 50-60 pins.
    
    # Inverse threshold to make pins white, board black (for counting)
    _, bin_band = cv2.threshold(pin_band, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Sum columns to create a 1D signal
    col_sum = np.sum(bin_band, axis=0)
    
    # A column is considered "part of a pin" if it has enough dark pixels 
    # (e.g., > 30% of the band height)
    pin_signal = (col_sum > (pin_band.shape[0] * 0.3)).astype(np.uint8)
    
    # Count transitions from 0 to 1 (start of a pin)
    transitions = np.abs(np.diff(pin_signal))
    approx_pin_count = np.count_nonzero(transitions) // 2
    
    # The board has ~53-60 pins. 
    # We allow a range to account for noise or slight mis-crops.
    MIN_PINS = 15
    MAX_PINS = 85
    
    if not (MIN_PINS <= approx_pin_count <= MAX_PINS):
        if debug: print(f"REJECT: Invalid pin count signature (Count: {approx_pin_count})")
        return False

    if debug: print(f"ACCEPT: Br:{avg_brightness:.0f}, Ratio:{ratio:.2f}, Pins:{approx_pin_count}")
    return True

def detect_blobs(warped,dst_h):
    gray_w = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)

    thresh = cv2.adaptiveThreshold(
        gray_w, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 51, 12
    )
    morph = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, KERNEL_ELLIPSE_3)

    cut = int(0.15 * dst_h)
    
    #morph[:cut] = cv2.erode(morph[:cut], KERNEL_HORZ_15)

    #morph[-cut:] = cv2.erode(morph[-cut:], KERNEL_HORZ_15)
    # HARD SILENCE: remove top and bottom completely
    morph[:cut, :] = 0
    morph[-cut:, :] = 0
    cnts, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = []
    for c in cnts:
        area = cv2.contourArea(c)
        if 50 < area < 25000:
            m = cv2.moments(c)
            if m["m00"]:
                cx = int(m["m10"] / m["m00"])
                x, y, w, h = cv2.boundingRect(c)
                blobs.append({'x': cx, 'y': y, 'w': w, 'h': h})
    return blobs
# ============================================================
# === MAIN ROBUST PIPELINE
# ============================================================
def extract_pins(
    image_path,
    threshold_px=15,
    left_expand_px=60,
    right_expand_px=40,
    min_edge_density=0.005
):
    
    #Geometric Edge-Based Board Detector (GEBD)
    img = cv2.imread(image_path)
    if img is None:
        return None, [], "Image could not be loaded"

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    blurred = cv2.medianBlur(gray, 9)
    edges = cv2.Canny(blurred, 50, 150)

    _, board_mask = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    board_mask = cv2.dilate(board_mask, KERNEL_RECT_7, 1)

    cnts, _ = cv2.findContours(board_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]
    best = cnts[0]

    for c in cnts:
        area = cv2.contourArea(c)
        if area < 1000:
            continue
        mask = np.zeros_like(gray)
        cv2.drawContours(mask, [c], -1, 255, -1)
        density = cv2.countNonZero(cv2.bitwise_and(edges, edges, mask=mask)) / area
        if density > min_edge_density:
            best = c
            break

    rect = cv2.minAreaRect(best)
    pts = cv2.boxPoints(rect)

    ordered = np.zeros((4,2), np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1)
    ordered[0] = pts[np.argmin(s)]
    ordered[2] = pts[np.argmax(s)]
    ordered[1] = pts[np.argmin(d)]
    ordered[3] = pts[np.argmax(d)]

    ordered[0][0] -= left_expand_px
    ordered[3][0] -= left_expand_px
    ordered[1][0] += right_expand_px
    ordered[2][0] += right_expand_px

    dst_w, dst_h = 1200, 400
    M = cv2.getPerspectiveTransform(
        ordered,
        np.array([[0,0],[dst_w,0],[dst_w,dst_h],[0,dst_h]], np.float32)
    )

    warped = cv2.warpPerspective(img_rgb, M, (dst_w, dst_h)) #Geometric Edge-Based Board Detector (GEBD)

    if not is_valid_pin_profiler_roi(warped):
        #Semantic Texture-Based Board Detector (STBD)
        warped = extract_board_Semantic(img,img_rgb,gray)
        if not is_valid_pin_profiler_roi(warped):
            return warped, [], "Invalid pin profiler ROI"
    
    blobs = detect_blobs(warped,dst_h)

    blobs.sort(key=lambda b: b['h'], reverse=True)
    bars = sorted(blobs[:2], key=lambda b: b['x'])

    left = bars[0]['x'] + threshold_px
    right = bars[1]['x'] - threshold_px
    pins = [b for b in blobs[2:] if left < b['x'] < right]

    pins = sorted(pins, key=lambda p: p['x'])

    return warped, pins, None

# --- MATH LOGIC ---
def calculate_all_metrics(pins, pitch_cm, do_leveling=True):

    # 1. Prepare Data (Logic from Function 1)
    pins_sorted = sorted(pins, key=lambda p: p['x'])
    # Calculate mean pixel distance to find the scale factor
    mean_px_dist = np.mean([pins_sorted[i+1]['x'] - pins_sorted[i]['x'] for i in range(len(pins_sorted)-1)])
    scale_factor = pitch_cm / mean_px_dist
    
    # Apply scaling to heights and x-coordinates
    x_raw = np.array([p['x'] * scale_factor for p in pins_sorted])
    x = x_raw - x_raw[0]
    z_raw = np.array([p['h'] * scale_factor for p in pins_sorted])
    n = len(z_raw)

    # 2. Leveling / Detrending (Crucial Step from Doc)
    # This removes the overall slope of the profile to isolate roughness

    if do_leveling:
        coeffs = np.polyfit(x, z_raw, 1)
        z_trend = np.polyval(coeffs, x)
        z_used = z_raw - z_trend      # leveled profile
    else:
        z_used = z_raw.copy()         # raw profile (no detrending)

    # "Zero-Minimum" adjustment for visualization
    z_plot = z_used - np.min(z_used)

    # Metric 1: RMS Height (Logic from Function 1)
    # Using z centered around the mean
    z_centered = z_used - np.mean(z_used)  #put z_leveled instead of z_raw to exclude leveling effects
    h_rms = np.sqrt(np.sum(z_centered**2) / n)

    # Metric 2: Correlation Length (Logic from Function 1)
    rho = []
    denominator = np.sum(z_centered**2)
    if denominator == 0: denominator = 1e-9 # Safety for flat lines
    
    for h_lag in range(n // 2):
        numerator = np.sum(z_centered[:n-h_lag] * z_centered[h_lag:])
        rho.append(numerator / denominator)
    
    rho = np.array(rho)
    l_cm = 0.0
    target = 1.0 / np.e
    for i in range(1, len(rho)):
        if rho[i] < target:
            y1, y2 = rho[i-1], rho[i]
            # Linear interpolation for fractional lag
            fractional_lag = (i - 1) + (target - y1) / (y2 - y1)
            l_cm = fractional_lag * pitch_cm
            break

    # --- Rest of the metrics remain as they were in Function 2 ---

    # Metric 3: Maximum Height
    h_max = np.max(z_used) - np.min(z_used)

    # Metric 4: Chain Index (IC)
    L1 = x[-1] - x[0]
    dx = np.diff(x)
    dz = np.diff(z_used)
    L2 = np.sum(np.sqrt(dx**2 + dz**2))
    ic_val = (1 - (L1 / L2)) * 100

    # Metric 5: Fractal Dimension (DF)
    lags, semivariances = [], []
    max_lag_idx = max(3, n // 3)
    for k in range(1, max_lag_idx):
        h = k * pitch_cm 
        gamma = 0.5 * np.mean((z_used[k:] - z_used[:-k]) ** 2)
        if gamma > 0:
            lags.append(h); semivariances.append(gamma)
            
    df_val, slope, intercept = 0.0, 0.0, 0.0
    if len(lags) > 2:
        try:
            log_h, log_gamma = np.log(lags), np.log(semivariances)
            from scipy.stats import linregress
            slope, intercept, _, _, _ = linregress(log_h, log_gamma)
            df_val = 2 - (slope / 2.0)
        except: pass

    return {
        'rms': float(h_rms), 'cl': float(l_cm), 'h_max': float(h_max),
        'ic': float(ic_val), 'df': float(df_val),
        'plot_data': {
            'x': x, 'z_plot': z_plot, 'z_orig': z_raw,
            'lags': np.array(range(len(rho))) * pitch_cm, 'rho': rho,
            'sv_h': lags, 'sv_g': semivariances,
            'slope': slope, 'intercept': intercept
        }
    }


# =========================================================
# ================== VISUALIZATION ========================
# =========================================================

class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=12, height=6, dpi=110):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.fig.patch.set_facecolor('#fafafa')
        super().__init__(self.fig)


class VisualizationWidget(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.canvas = MplCanvas(self)
        layout.addWidget(self.canvas)

        # ---- SAVE BUTTON (NEW) ----
        self.btn_save = QPushButton("💾 Save Plot")
        self.btn_save.setFixedWidth(150)
        self.btn_save.clicked.connect(self.save_plot)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.btn_save)
        layout.addLayout(btn_row)

        # Edit mode toggle
        self.edit_mode = False

    def set_edit_mode(self, enabled):
        self.edit_mode = enabled
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
    def save_plot(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Plot",
            "pinsight_plot.png",
            "PNG (*.png);;JPEG (*.jpg);;PDF (*.pdf)"
        )
        if path:
            self.canvas.fig.savefig(path, dpi=300, bbox_inches="tight")

    def plot_metrics(self, data):
        if not data:
            self.canvas.fig.clear(); self.canvas.draw(); return

        self.canvas.fig.clear()
        self.canvas.fig.set_constrained_layout(True)
        
        # 1. Surface Profile (Matches Fig 2)
        ax1 = self.canvas.fig.add_subplot(131)
        ax1.plot(data['x'], data['z_plot'], 'k-', linewidth=1.2) # Solid black line
        ax1.set_title("Microtopography Profile", fontsize=11, fontweight='bold')
        ax1.set_xlabel("Distance (cm)", fontsize=10)
        ax1.set_ylabel("Height (cm)", fontsize=10)
        ax1.grid(True, linestyle='--', alpha=0.5)
        ax1.set_ylim(0, max(data['z_plot']) * 1.2) # Minimum brought to 0

        # 2. Autocorrelogram (Matches Fig 3)
        ax2 = self.canvas.fig.add_subplot(132)
        rho = np.array(data['rho'])
        lags = np.array(data['lags'])
        
        ax2.plot(lags, rho, 'b-o', markersize=3, linewidth=1, label='Autocorrelation')
        ax2.axhline(1/np.e, color='r', linestyle='--', label='1/e threshold')
        ax2.axhline(0, color='k', linewidth=0.8, alpha=0.3) # Zero line for reference
        
        ax2.set_title("Autocorrelogram", fontsize=11, fontweight='bold')
        ax2.set_xlabel("Lag (cm)", fontsize=10)
        ax2.set_ylabel("Correlation (ρ)", fontsize=10)
        
        # --- DYNAMIC Y-LIMIT ADJUSTMENT ---
        # We ensure the 1/e line (0.367) and all rho values are visible
        y_min = min(np.min(rho), -0.2) # Show at least down to -0.2
        y_max = 1.1 # Always show the peak at 1.0
        ax2.set_ylim(y_min - 0.1, y_max) 
        
        ax2.legend(fontsize=8, loc='upper right')
        ax2.grid(True, linestyle='--', alpha=0.5)

        # 3. Fractal Semivariogram (Matches Fig 5)
        ax3 = self.canvas.fig.add_subplot(133)
        if data['sv_h']:
            ax3.loglog(data['sv_h'], data['sv_g'], 'ks', markersize=4, label='Data')
            x_fit = np.array(data['sv_h'])
            y_fit = np.exp(data['intercept'] + data['slope'] * np.log(x_fit))
            ax3.loglog(x_fit, y_fit, 'r-', label=f'DF = {2 - data["slope"]/2:.2f}')
        ax3.set_title("Semivariogram (Log-Log)", fontsize=11, fontweight='bold')
        ax3.set_xlabel("log Lag (cm)", fontsize=10)
        ax3.set_ylabel("log Semivariance", fontsize=10)
        ax3.legend(fontsize=8)
        ax3.grid(True, which="both", linestyle='--', alpha=0.5)

        self.canvas.draw()


# --- NEW DOCUMENTATION DIALOG ---
class DocumentationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Methodology & Documentation")
        self.setFixedSize(800, 700) 
        layout = QVBoxLayout(self)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("padding: 15px; font-size: 13px; line-height: 1.4;")
        
        # HTML Content based on Nolin et al. (2005)
        html_content = """
        <h2 style="color:#00796b;">Soil Surface Roughness — Methodology</h2>

        <p>
        This application computes quantitative soil surface roughness indicators following the
        methodology described in:
        <i>“Rugosité de la surface du sol – description et interprétation”</i>
        (Nolin et al., 2005).
        </p>

        <p>
        These indicators characterize soil surface geometry at multiple spatial scales, ranging
        from micro-structural irregularities to meso-scale spatial organization.
        </p>

        <hr>

        <h3 style="color:#263238;">1. RMS Height (Root Mean Square Height)</h3>

        <p>
        <b>Purpose:</b> Vertical roughness descriptor representing the amplitude of height variations
        around the mean surface level.
        </p>

        <p><b>Reference:</b> Nolin et al. (2005), Eq. (1), p. 8.</p>

        <p><b>Equation:</b></p>

        <p style="margin-left:20px;">
        RMS =
        <span style="font-size:16px;">&#8730;</span>
        <span style="border-top:1px solid black; padding-top:3px;">
        &nbsp;
        &#931;<sub>i=1</sub><sup>n</sup>
        (z<sub>i</sub> − z̄)<sup>2</sup>
        &nbsp; / &nbsp; n
        </span>
        </p>

        <p><b>Where:</b></p>
        <ul>
        <li><i>z<sub>i</sub></i> = height at point <i>i</i></li>
        <li><i>z̄</i> = mean surface height</li>
        <li><i>n</i> = number of sampled points</li>
        </ul>

        <hr>

        <h3 style="color:#263238;">2. Correlation Length (λ)</h3>

        <p>
        <b>Purpose:</b> Horizontal roughness descriptor reflecting the spatial continuity
        and dominant structure size of the surface.
        </p>

        <p>
        A larger correlation length indicates a smoother surface with larger-scale features.
        </p>

        <p><b>Reference:</b> Nolin et al. (2005), Eq. (2–3), p. 9.</p>

        <p><b>Definition:</b></p>

        <p style="margin-left:20px;">
        The correlation length <i>λ</i> is defined as the distance <i>h</i> for which the
        autocorrelation function <i>ρ(h)</i> satisfies:
        </p>

        <p style="margin-left:40px;">
        ρ(h) = 1 / e ≈ 0.368
        </p>

        <hr>

        <h3 style="color:#263238;">3. Chain Index (IC)</h3>

        <p>
        <b>Purpose:</b> Describes surface <b>tortuosity</b>, quantifying the deviation of the
        surface profile from a perfectly flat line.
        </p>

        <p><b>Reference:</b> Nolin et al. (2005), Eq. (4), p. 10; Saleh (1993).</p>

        <p><b>Equation:</b></p>

        <p style="margin-left:20px;">
        IC (%) = (1 − L<sub>1</sub> / L<sub>2</sub>) × 100
        </p>

        <p><b>Where:</b></p>
        <ul>
        <li><i>L<sub>1</sub></i> = projected (horizontal) length</li>
        <li><i>L<sub>2</sub></i> = true surface (chain) length</li>
        </ul>

        <hr>

        <h3 style="color:#263238;">4. Fractal Dimension (D<sub>F</sub>)</h3>

        <p>
        <b>Purpose:</b> Characterizes micro-scale roughness and surface irregularity associated
        with soil aggregation.
        </p>

        <p><b>Reference:</b> Nolin et al. (2005), Eq. (5), p. 10.</p>

        <p><b>Method:</b></p>

        <p style="margin-left:20px;">
        The fractal dimension is derived from the slope <i>m</i> of the log–log semivariogram:
        </p>

        <p style="margin-left:40px;">
        D<sub>F</sub> = 2 − m / 2
        </p>

        <p>
        Higher values of <i>D<sub>F</sub></i> indicate greater surface complexity at fine spatial scales.
        </p>

        <hr>

        <p style="color:#666; font-size:12px;">
        <i>
        Reference:<br>
        Nolin, M. C., Quenum, M., Cambouris, A. N., Martin, A., & Cluis, D. (2005).
        Rugosité de la surface du sol – description et interprétation.
        Agrosol, 16(1), 5–22.
        </i>
        </p>
        """
        
        text_edit.setHtml(html_content)
        layout.addWidget(text_edit)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

class CitationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cite this Work")
        self.setFixedWidth(550)
        layout = QVBoxLayout(self)
        citations = {
            "APA Style": "Klai, M. (2026). PinSight: A computer vision-based software for the efficient and automated processing of pin profiler photographs for soil roughness analysis.",
            "BibTeX": "@software{klai2026pinprofiler,\n  author = {Klai, Mouad},\n  title = {PinSight: A computer vision-based software for the efficient and automated processing of pin profiler photographs for soil roughness analysis},\n  year = {2026}\n}"
        }
        for style, text in citations.items():
            box = QGroupBox(style)
            blay = QVBoxLayout(box)
            edit = QTextEdit(); edit.setPlainText(text); edit.setReadOnly(True); edit.setFixedHeight(70 if "Bib" not in style else 100)
            btn = QPushButton("Copy " + style.split()[0])
            btn.clicked.connect(lambda ch, t=text, b=btn: self.copy(t, b))
            blay.addWidget(edit); blay.addWidget(btn)
            layout.addWidget(box)

    def copy(self, text, btn):
        QApplication.clipboard().setText(text)
        old = btn.text(); btn.setText("Copied!"); btn.setStyleSheet("background: #28a745; color: white;")
        QTimer.singleShot(1000, lambda: (btn.setText(old), btn.setStyleSheet("")))

class InteractivePinEditor(QWidget):
    pins_changed = Signal(list)   # emits updated pin list

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)


        self.image = None
        self.pins = []
        self.selected_idx = None
        self.dragging = False
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
        self.edit_mode = False
        self.hy_a = None
        self.hy_b = None

    
    def set_edit_mode(self, enabled: bool):
        """Enable or disable pin editing."""
        self.edit_mode = enabled
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        self.selected_idx = None
        self.update()

    def resizeEvent(self, event):
            super().resizeEvent(event)

            parent = self.parent()
            if parent and hasattr(parent, "position_delete_button"):
                parent.position_delete_button()
        
    def set_data(self, image, pins, hy_calib=None):
        if image is None:
            self.image = None
            self.pins = []
            self.hy_a = None
            self.hy_b = None
            self.update()
            return

        self.image = image.copy()
        self.pins = pins

        if hy_calib is not None:
            self.hy_a, self.hy_b = hy_calib

        self.update()
    
    def h_from_y(self, y):
        if self.hy_a is None or self.hy_b is None:
            return 0.0
        return self.hy_a * y + self.hy_b

    def paintEvent(self, event):
        if self.image is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        h, w, _ = self.image.shape
        qimg = QImage(self.image.data, w, h, w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg)

        pix = pix.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # Compute scale & offsets
        self.scale = pix.width() / w
        self.offset_x = (self.width() - pix.width()) / 2
        self.offset_y = (self.height() - pix.height()) / 2

        # Draw image
        painter.drawPixmap(self.offset_x, self.offset_y, pix)

        # --- EDIT MODE BORDER (SAFE NOW) ---
        if self.edit_mode:
            painter.setPen(QPen(QColor(255, 140, 0), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(
                self.offset_x,
                self.offset_y,
                pix.width(),
                pix.height()
            )

        # Draw pins
        for i, p in enumerate(self.pins):
            x = self.offset_x + p['x'] * self.scale
            y = self.offset_y + p['y'] * self.scale

            if i == self.selected_idx:
                painter.setBrush(QColor(255, 0, 0))
            else:
                painter.setBrush(QColor(0, 200, 0))

            painter.setPen(Qt.black)
            painter.drawEllipse(QPointF(x, y), 6, 6)


    def widget_to_image(self, x, y):
        ix = int((x - self.offset_x) / self.scale)
        iy = int((y - self.offset_y) / self.scale)
        return ix, iy
    
    def find_pin(self, x, y, tol=8):
        for i, p in enumerate(self.pins):
            px = self.offset_x + p['x'] * self.scale
            py = self.offset_y + p['y'] * self.scale
            if np.hypot(px - x, py - y) < tol:
                return i
        return None


    def mousePressEvent(self, event):
        if not self.edit_mode:
            return

        x = event.position().x()
        y = event.position().y()

        # LEFT CLICK → select & start drag
        if event.button() == Qt.LeftButton:
            idx = self.find_pin(x, y)
            if idx is not None:
                self.selected_idx = idx
                self.dragging = True

        # RIGHT CLICK → delete pin
        elif event.button() == Qt.RightButton:
            idx = self.find_pin(x, y)
            if idx is not None:
                del self.pins[idx]
                self.selected_idx = None
                self.update()
                self.pins_changed.emit(self.pins)

    def mouseMoveEvent(self, event):
        if not self.edit_mode:
            return
        if self.dragging and self.selected_idx is not None:
            ix, iy = self.widget_to_image(event.position().x(), event.position().y())
            self.pins[self.selected_idx]['x'] = ix
            self.pins[self.selected_idx]['y'] = iy
            self.pins[self.selected_idx]['h'] = self.h_from_y(iy)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.dragging = False
            self.pins_changed.emit(self.pins)


    def mouseDoubleClickEvent(self, event):
        if not self.edit_mode:
            return

        ix, iy = self.widget_to_image(
            event.position().x(),
            event.position().y()
        )
        h_est = self.h_from_y(iy)

        new_pin = {'x': ix, 'y': iy, 'h': h_est}

        # --- Find insertion index based on x ---
        insert_idx = 0
        for i, p in enumerate(self.pins):
            if ix < p['x']:
                insert_idx = i
                break
        else:
            insert_idx = len(self.pins)

        # Insert pin at correct position
        self.pins.insert(insert_idx, new_pin)

        self.selected_idx = insert_idx
        self.update()
        self.pins_changed.emit(self.pins)

class ToggleSwitch(QPushButton):
    def __init__(self, text_on="ON", text_off="OFF", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(120, 34)
        self.text_on = text_on
        self.text_off = text_off
        self.update_style(False)
        self.toggled.connect(self.update_style)

    def update_style(self, checked):
        if checked:
            self.setText(self.text_on)
            self.setStyleSheet("""
                QPushButton {
                    background-color: #00796b;
                    color: white;
                    border-radius: 17px;
                    font-weight: bold;
                }
            """)
        else:
            self.setText(self.text_off)
            self.setStyleSheet("""
                QPushButton {
                    background-color: #b0bec5;
                    color: #263238;
                    border-radius: 17px;
                    font-weight: bold;
                }
            """)

class BatchWorker(QThread):
    finished = Signal(list); progress = Signal(int)
    invalid_image = Signal(str, str, str)  # (filename, reason)
    def __init__(self, paths, pitch, do_leveling): super().__init__(); self.paths = paths; self.pitch = pitch; self.do_leveling = do_leveling
    def run(self):
        results = []
        for i, p in enumerate(self.paths):
            data = extract_pins(p)
            if data is None:
                self.invalid_image.emit(
                    os.path.basename(p),
                    p,
                    "Image could not be loaded or is corrupted."
                )
                self.progress.emit(i + 1)
                continue
            if data[-1]:
                self.invalid_image.emit(
                    os.path.basename(p),
                    p,
                    data[-1]
                )
                self.progress.emit(i + 1)
                continue
            if len(data[1])>1:
                metrics = calculate_all_metrics(data[1], self.pitch,self.do_leveling)
                metrics['viz'] = data[:-1]
                metrics['path'] = p
                metrics['pins'] = data[1]
                metrics['pitch'] = self.pitch
                results.append(metrics)
            self.progress.emit(i + 1)
        self.finished.emit(results)

class PinApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PinSight v0.1 - Pin Profiler Photographs Digital Analysis")
        self.resize(1000, 600) # Slightly taller initial window
        
        icon_path = resource_path("PinSight.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.results = []; self.current_idx = 0
        self._setup_stylesheet()
        self._init_ui()
        self.check_for_updates()

    def _setup_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow { background: #f0f2f5; }
            #Sidebar { background-color: #ffffff; border-right: 1px solid #dfe1e5; }
            QLabel#ToolTitle { font-weight: bold; font-size: 18px; color: #004d40; margin-top: 14px; }
            QLabel#PitchLabel { font-weight: 700; color: #546e7a; font-size: 11px; letter-spacing: 0.5px; margin-top: 30px;}
            QLabel#SectionHeader { font-weight: bold; color: #263238; font-size: 13px; text-transform: uppercase; margin-top: 20px; border-bottom: 1px solid #eee; padding-bottom: 5px;}
            QLineEdit { padding: 8px; border: 1px solid #cfd8dc; border-radius: 4px; background: #fafafa; font-size: 14px; color: #37474f; }
            QLineEdit:focus { border: 1px solid #009688; background: #fff; }
            
            /* Standard Buttons */
            QPushButton { padding: 10px; border-radius: 5px; font-weight: 600; font-size: 13px; background-color: #eceff1; border: 1px solid #cfd8dc; color: #455a64; }
            QPushButton:hover { background-color: #cfd8dc; }
            QPushButton#PrimaryAction { background-color: #00796b; color: white; border: none; }
            QPushButton#PrimaryAction:hover { background-color: #004d40; }
            QPushButton#ExportAction { background-color: #2e7d32; color: white; border: none; }
            QPushButton#ExportAction:hover { background-color: #1b5e20; }
            QPushButton#DocAction { background-color: #0277bd; color: white; border: none; }
            QPushButton#DocAction:hover { background-color: #01579b; }
            
            /* Tab Buttons for View Switcher */
            QPushButton#TabBtn { 
                background-color: #ffffff; 
                border: 1px solid #cfd8dc; 
                color: #546e7a; 
                border-radius: 15px;
                padding: 6px 20px;
                margin-left: 5px;
            }
            QPushButton#TabBtn[active="true"] { 
                background-color: #00796b; 
                color: white; 
                border: 1px solid #00796b; 
            }
            QPushButton#TabBtn:hover { background-color: #e0f2f1; color: #00796b; }
            QPushButton#TabBtn[active="true"]:hover { background-color: #00695c; color: white; }
            
            /* Table */
            QTableWidget { border: 1px solid #cfd8dc; border-radius: 4px; background-color: white; color: #37474f; font-size: 12px; selection-background-color: #e0f2f1; selection-color: #004d40; alternate-background-color: #fafafa; gridline-color: #f0f0f0; }
            QHeaderView::section { background-color: #eceff1; color: #455a64; padding: 6px; border: none; border-bottom: 1px solid #cfd8dc; font-weight: bold; }
            
            /* Metrics Box */
            #CurrentMetricBox { background: #ffffff; border: 1px solid #cfd8dc; border-radius: 8px; padding: 15px; }
            QLabel.MetricValue { font-size: 18px; font-weight: bold; color: #00695c; }
            QLabel.MetricLabel { font-size: 11px; color: #78909c; text-transform: uppercase; font-weight: bold;}
            
            /* Navigation */
            QPushButton#Nav { font-size: 24px; color: #90a4ae; border: 1px solid #cfd8dc; border-radius: 25px; background: white; }
            QPushButton#Nav:hover { color: #00796b; border-color: #00796b; background: #e0f2f1; }
            
            QPushButton#EditPinsBtn {
                background-color: #eceff1;
                border: 1px solid #cfd8dc;
                color: #37474f;
            }

            QPushButton#EditPinsBtn:checked {
                background-color: #c62828;   /* red */
                color: white;
                border: 1px solid #b71c1c;
            }

            QPushButton#EditPinsBtn:checked:hover {
                background-color: #b71c1c;
            }
        """)

    def _init_ui(self):
        main = QWidget(); self.setCentralWidget(main); layout = QHBoxLayout(main); layout.setSpacing(0); layout.setContentsMargins(0,0,0,0)
        
        # --- SIDEBAR ---
        side = QFrame(); side.setObjectName("Sidebar"); side.setFixedWidth(380); s_lay = QVBoxLayout(side); s_lay.setContentsMargins(25,30,25,30); s_lay.setSpacing(15)
        pix = QPixmap(resource_path("CRSA_UM6P.png"))
        if not pix.isNull():
            l_lbl = QLabel(); l_lbl.setPixmap(pix.scaled(378, 378, Qt.KeepAspectRatio, Qt.SmoothTransformation)); l_lbl.setAlignment(Qt.AlignCenter); s_lay.addWidget(l_lbl)

        title_lbl = QLabel("<b>PinSight</b><br><span style='font-size: 10pt;'>Pin Profiler Photographs Digital Analysis</span><br><span style='font-size: 10pt;'>General Roughness Analysis Tool</span>"); title_lbl.setObjectName("ToolTitle"); title_lbl.setAlignment(Qt.AlignCenter)
        s_lay.addWidget(title_lbl); s_lay.addSpacing(10)
        
        # Pitch
        pitch_box = QVBoxLayout(); pitch_box.setSpacing(5)
        pitch_lbl = QLabel("PIN PITCH (CM)"); pitch_lbl.setObjectName("PitchLabel"); pitch_box.addWidget(pitch_lbl)
        self.pitch_in = QLineEdit("2.0"); pitch_box.addWidget(self.pitch_in)
        self.pitch_in.editingFinished.connect(self.recompute_all_metrics)
        s_lay.addLayout(pitch_box)

        lvl_label = QLabel("LEVELING / DETRENDING")
        lvl_label.setObjectName("PitchLabel")
        s_lay.addWidget(lvl_label)

        self.level_switch = ToggleSwitch("ON", "OFF")
        self.level_switch.setChecked(True)  # default ON
        self.level_switch.toggled.connect(self.recompute_all_metrics)
        s_lay.addWidget(self.level_switch)

        # Actions
        btn_f = QPushButton("Add Images"); btn_f.setObjectName("PrimaryAction")
        btn_d = QPushButton("Add Folder")
        btn_f.clicked.connect(self.load_files); btn_d.clicked.connect(self.load_folder)
        btn_lay = QHBoxLayout(); btn_lay.addWidget(btn_f); btn_lay.addWidget(btn_d)
        s_lay.addLayout(btn_lay)
        
        self.btn_export = QPushButton("Export Report + Stats"); self.btn_export.setObjectName("ExportAction"); self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_data)
        s_lay.addWidget(self.btn_export)

        # Batch Stats
        s_lay.addSpacing(10)
        summary_lbl = QLabel("Batch Statistics"); summary_lbl.setObjectName("SectionHeader"); s_lay.addWidget(summary_lbl)
        self.stats_table = QTableWidget(4, 5)
        self.stats_table.setHorizontalHeaderLabels(["RMS", "L", "H_max", "IC", "DF"])
        self.stats_table.setVerticalHeaderLabels(["Mean", "Std", "Min", "Max"])
        self.stats_table.setFixedHeight(145)
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        s_lay.addWidget(self.stats_table)
        
        s_lay.addStretch()
        s_lay.addWidget(QFrame(frameShape=QFrame.HLine, styleSheet="color: #eee"))

        d_lbl = QLabel("Dr. Mouad KLAI"); d_lbl.setStyleSheet("font-weight: bold; color: #333;"); d_lbl.setAlignment(Qt.AlignCenter); s_lay.addWidget(d_lbl)
        c_btn = QPushButton("Cite Software"); c_btn.clicked.connect(lambda: CitationDialog(self).exec()); s_lay.addWidget(c_btn)
        doc_btn = QPushButton("Documentation"); doc_btn.setObjectName("DocAction"); doc_btn.clicked.connect(lambda: DocumentationDialog(self).exec())
        s_lay.addWidget(doc_btn)
        about_btn = QPushButton("About PinSight")
        about_btn.clicked.connect(self.show_about)
        s_lay.addWidget(about_btn)

        
        layout.addWidget(side)
        
        # --- MAIN SPLIT VIEW ---
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
                
        # 1. Top View (Image + Metrics)
        top_widget = QWidget()
        v_top = QVBoxLayout(top_widget)
        v_top.setContentsMargins(30, 30, 30, 10)

        # --- Image row ---
        img_row = QHBoxLayout()

        # Navigation buttons
        self.b_prev = QPushButton("❮")
        self.b_next = QPushButton("❯")
        for b in (self.b_prev, self.b_next):
            b.setObjectName("Nav")
            b.setFixedSize(50, 50)

        self.b_prev.clicked.connect(self.prev)
        self.b_next.clicked.connect(self.next)

        # --- Interactive image canvas (CREATE FIRST) ---
        self.img_view = InteractivePinEditor()
        self.img_view.setMinimumHeight(200)
        self.img_view.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
        # --- Overlay delete button (top-right of image) ---
        self.btn_delete_img = QPushButton("✕", self.img_view)
        self.btn_delete_img.setFixedSize(28, 28)
        self.btn_delete_img.setToolTip("Remove this image")
        self.btn_delete_img.setCursor(Qt.PointingHandCursor)
        self.btn_delete_img.setFocusPolicy(Qt.NoFocus)
        self.btn_delete_img.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.btn_delete_img.setVisible(False)

        self.btn_delete_img.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 140);
                color: white;
                border: none;
                border-radius: 14px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(200, 0, 0, 180);
            }
        """)

        # --- Edit pins toggle ---
        self.btn_edit_pins = QPushButton("✏ Edit pins")
        self.btn_edit_pins.setObjectName("EditPinsBtn")
        self.btn_edit_pins.setCheckable(True)
        self.btn_edit_pins.setFixedHeight(40)
        self.btn_edit_pins.setToolTip("Enable manual pin editing")
        self.btn_edit_pins.setEnabled(False)  # enabled only when image is loaded

        # --- Layout order matters ---
        img_row.addWidget(self.b_prev)
        img_row.addWidget(self.btn_edit_pins)
        img_row.addWidget(self.img_view, 1)
        img_row.addWidget(self.b_next)

        # --- Now connect signals (SAFE) ---
        self.btn_edit_pins.toggled.connect(self.img_view.set_edit_mode)
        self.img_view.pins_changed.connect(self.on_pins_modified)
        self.btn_delete_img.clicked.connect(self.confirm_delete_current)


        # Add row to top layout
        v_top.addLayout(img_row, 1)


        
        info_box = QFrame(); info_box.setObjectName("CurrentMetricBox"); info_lay = QHBoxLayout(info_box)
        self.lbl_vals = {}
        metrics_def = [("h_rms", "RMS Height"), ("cl", "Corr. Len"), ("h_max", "Max Height"), ("ic", "Tortuosity"), ("df", "Fractal Dim")]
        for key, name in metrics_def:
            v_m = QVBoxLayout()
            l_name = QLabel(name); l_name.setAlignment(Qt.AlignCenter); l_name.setProperty("class", "MetricLabel")
            l_val = QLabel("--"); l_val.setAlignment(Qt.AlignCenter); l_val.setProperty("class", "MetricValue")
            v_m.addWidget(l_val); v_m.addWidget(l_name)
            info_lay.addLayout(v_m)
            self.lbl_vals[key] = l_val
            if key != "df": 
                sep = QFrame(); sep.setFrameShape(QFrame.VLine); sep.setStyleSheet("color: #eee;"); info_lay.addWidget(sep)

        v_top.addWidget(info_box)
        self.l_file = QLabel("Ready"); self.l_file.setAlignment(Qt.AlignCenter); self.l_file.setStyleSheet("color: #78909c; margin-top: 10px; font-weight: 500;")
        v_top.addWidget(self.l_file)
        self.splitter.addWidget(top_widget)
        
        # 2. Bottom View (Tabs + Content)
        bottom_widget = QWidget()
        v_bot = QVBoxLayout(bottom_widget); v_bot.setContentsMargins(30, 0, 30, 30)
        
        h_row = QHBoxLayout()
        lbl_det = QLabel("Results Analysis"); lbl_det.setObjectName("SectionHeader"); 
        
        # TAB BUTTONS
        tabs_box = QWidget(); tabs_lay = QHBoxLayout(tabs_box); tabs_lay.setContentsMargins(0,0,0,0)
        self.btn_tab_table = QPushButton("DATA TABLE"); self.btn_tab_table.setObjectName("TabBtn")
        self.btn_tab_viz = QPushButton("VISUALIZATIONS"); self.btn_tab_viz.setObjectName("TabBtn")
        
        self.btn_tab_table.clicked.connect(lambda: self.switch_view(0))
        self.btn_tab_viz.clicked.connect(lambda: self.switch_view(1))
        
        tabs_lay.addWidget(self.btn_tab_table); tabs_lay.addWidget(self.btn_tab_viz)
        
        h_row.addWidget(lbl_det); h_row.addStretch(); h_row.addWidget(tabs_box)
        v_bot.addLayout(h_row)
        
        # Stacked Content
        self.bottom_stack = QStackedWidget()
        
        # Page 0: Table
        self.details_table = QTableWidget(0, 6)
        self.details_table.setHorizontalHeaderLabels(["Image", "RMS (cm)", "L (cm)", "H_max (cm)", "IC (%)", "DF"])
        self.details_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6): self.details_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.details_table.setAlternatingRowColors(True)
        self.details_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.details_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.details_table.cellClicked.connect(self.table_row_clicked)
        self.bottom_stack.addWidget(self.details_table)
        
        # Page 1: Viz
        self.viz_widget = VisualizationWidget()
        self.bottom_stack.addWidget(self.viz_widget)
        
        v_bot.addWidget(self.bottom_stack)
        
        self.splitter.addWidget(bottom_widget)
        # CHANGED: Adjusted sizes to give bottom part more height by default (Top: 550, Bottom: 400)
        self.splitter.setSizes([550, 400]) 
        
        # Loading Stack
        self.stack = QStackedWidget()
        self.stack.addWidget(self.splitter)
        
        # Loading Page Styling (Black Text)
        self.prog = QProgressBar(); 
        self.prog.setAlignment(Qt.AlignCenter); 
        self.prog.setStyleSheet("""
            QProgressBar {
                height: 30px; 
                text-align: center; 
                color: black; 
                border: 1px solid #bbb;
                background-color: #eee;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #00796b;
            }
        """)
        
        loading_page = QWidget(); l_lay = QVBoxLayout(loading_page); l_lay.setAlignment(Qt.AlignCenter)
        l_text = QLabel("Processing Images... Please Wait")
        l_text.setStyleSheet("font-size: 18px; font-weight: bold; color: black; margin-bottom: 10px;")
        
        l_lay.addWidget(l_text); l_lay.addWidget(self.prog)
        self.stack.addWidget(loading_page)
        
        layout.addWidget(self.stack, 1)
        
        # Set default tab
        self.switch_view(0)
        def reposition_delete_button():
            margin = 8
            self.btn_delete_img.move(
                self.img_view.width() - self.btn_delete_img.width() - margin,
                margin
            )

        self.img_view.resizeEvent = lambda e: (
            QWidget.resizeEvent(self.img_view, e),
            reposition_delete_button()
        )

    # --- LOGIC ---
    def load_files(self):
        f, _ = QFileDialog.getOpenFileNames(self, "Images", "", "Images (*.png *.jpg *.jpeg)")
        if f: self.run_batch(f,append=True)

    def load_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Folder")
        if d: self.run_batch([os.path.join(d, x) for x in os.listdir(d) if x.lower().endswith(('.png','.jpg','.jpeg'))], append=True)
    
    def position_delete_button(self):
        if not hasattr(self, "btn_delete_img"):
            return

        margin = 8
        self.btn_delete_img.move(
            self.img_view.width() - self.btn_delete_img.width() - margin,
            margin
        )

    def update_delete_button_visibility(self):
        if not hasattr(self, "btn_delete_img"):
            return

        has_images = bool(self.results)

        self.btn_delete_img.setVisible(has_images)
        self.btn_delete_img.setEnabled(has_images)   # 🔴 THIS LINE FIXES IT

        if has_images:
            self.position_delete_button()
            self.btn_delete_img.raise_()

    def check_for_updates(self):
        try:
            url = "https://mouadklai.github.io/PinSight/version.json"
            r = requests.get(url, timeout=3)
            info = r.json()

            latest = info["latest_version"]
            minimum = info["minimum_version"]
            download_url = info["download_url"]

            if APP_VERSION < minimum:
                # 🔴 FORCE UPDATE
                QMessageBox.critical(
                    self,
                    "Update required",
                    f"You are using PinSight v{APP_VERSION}.\n\n"
                    f"Minimum required version is v{minimum}.\n\n"
                    "The application will now close."
                )
                QDesktopServices.openUrl(QUrl(download_url))
                sys.exit(0)

            elif APP_VERSION < latest:
                # 🟡 OPTIONAL UPDATE
                reply = QMessageBox.information(
                    self,
                    "Update available",
                    f"A new version of PinSight (v{latest}) is available.\n\n"
                    "Would you like to download it now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    QDesktopServices.openUrl(QUrl(download_url))

        except Exception:
            # Silent fail → app still opens
            pass

    def show_about(self):
        QMessageBox.information(
            self,
            "About PinSight",
            f"PinSight\n"
            f"Version {APP_VERSION}\n\n"
            "A computer vision–based software for automated processing\n"
            "of pin profiler photographs for soil surface roughness analysis.\n\n"
            "© 2026 Dr. Mouad Klai"
        )

    def show_invalid_image_popup(self, filename,image_path, reason):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Invalid Pin Profiler Image")

        msg.setText(
            f"<b>File:</b> {filename}<br><br>"
            f"<b>Reason:</b> {reason}<br><br>"
            "Please provide a <b>high-quality photograph</b> corresponding to a "
            "<b>pin profiler measurement</b> with:<ul>"
            "<li>Clearly visible board</li>"
            "<li>Good lighting and contrast</li>"
            "<li>At least <b>45 detectable pins</b></li>"
            "</ul>"
            "<b>What is a pin profiler?</b><br>"
            "A pin profiler is a mechanical device composed of vertically sliding pins "
            "used to capture soil surface microtopography.<br><br>"
            "<b>Reference:</b><br>"
            "Klai, M. (2026). <i>PinSight: A computer vision-based software for the efficient "
            "and automated processing of pin profiler photographs for soil roughness analysis.</i>"
        )

        # ---------- IMAGE PREVIEW ----------
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            img_label = QLabel()
            img_label.setAlignment(Qt.AlignCenter)
            img_label.setPixmap(
                pixmap.scaled(
                    500, 350,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )

            # Insert image under the text
            msg.layout().addWidget(
                img_label,
                msg.layout().rowCount(),
                0,
                1,
                msg.layout().columnCount()
            )
        # -----------------------------------

        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def run_batch(self, files, append=True):
        try:
            self.append_mode = append
            pitch_val = float(self.pitch_in.text())
            self.prog.setRange(0, len(files)); self.stack.setCurrentIndex(1)
            self.worker = BatchWorker(
                            files,
                            pitch_val,
                            self.level_switch.isChecked()
                        )
            self.worker.progress.connect(self.prog.setValue)
            self.worker.invalid_image.connect(self.show_invalid_image_popup)
            self.worker.finished.connect(self.on_done); self.worker.start()
        except ValueError: pass
    
    def compute_h_y_calibration(self, pins):
        """
        Compute h = a*y + b using the 4 middle pins.
        """
        if len(pins) < 4:
            return None, None

        # Sort by x
        pins_sorted = sorted(pins, key=lambda p: p['x'])
        n = len(pins_sorted)

        # Take 4 middle pins
        mid = n // 2
        mid_pins = pins_sorted[mid-2:mid+2]

        ys = np.array([p['y'] for p in mid_pins])
        hs = np.array([p['h'] for p in mid_pins])

        slope, intercept, _, _, _ = linregress(ys, hs)
        return float(slope), float(intercept)

    def on_done(self, res):
        if not res:
            self.stack.setCurrentIndex(0)
            return

        # ---------- 🔐 DUPLICATE PROTECTION (ADD HERE) ----------
        if self.results:
            existing_paths = {r['path'] for r in self.results}
            res = [r for r in res if r['path'] not in existing_paths]

            if not res:
                QMessageBox.information(
                    self,
                    "No new images",
                    "All selected images were already loaded."
                )
                self.stack.setCurrentIndex(0)
                return
        # --------------------------------------------------------

        # ---------- APPEND vs REPLACE ----------
        if getattr(self, "append_mode", False) and self.results:
            start_idx = len(self.results)
            self.results.extend(res)
            self.current_idx = start_idx
        else:
            self.results = res
            self.current_idx = 0
        # --------------------------------------

        # Compute h–y calibration
        for r in res:
            r['hy_calib'] = self.compute_h_y_calibration(r['pins'])

        self.stack.setCurrentIndex(0)
        self.populate_details_table()
        self.update_ui()
        self.update_delete_button_visibility()

    def populate_details_table(self):
        self.details_table.setRowCount(len(self.results))
        for i, res in enumerate(self.results):
            self.details_table.setItem(i, 0, QTableWidgetItem(os.path.basename(res['path'])))
            self.details_table.setItem(i, 1, QTableWidgetItem(f"{res['rms']:.4f}"))
            self.details_table.setItem(i, 2, QTableWidgetItem(f"{res['cl']:.4f}"))
            self.details_table.setItem(i, 3, QTableWidgetItem(f"{res['h_max']:.4f}"))
            self.details_table.setItem(i, 4, QTableWidgetItem(f"{res['ic']:.2f}"))
            self.details_table.setItem(i, 5, QTableWidgetItem(f"{res['df']:.4f}"))

    def switch_view(self, index):
        self.bottom_stack.setCurrentIndex(index)
        # Update styling properties to highlight active button
        self.btn_tab_table.setProperty("active", str(index == 0).lower())
        self.btn_tab_viz.setProperty("active", str(index == 1).lower())
        
        # Force style refresh
        self.btn_tab_table.style().unpolish(self.btn_tab_table)
        self.btn_tab_table.style().polish(self.btn_tab_table)
        self.btn_tab_viz.style().unpolish(self.btn_tab_viz)
        self.btn_tab_viz.style().polish(self.btn_tab_viz)

    def table_row_clicked(self, row, col):
        self.current_idx = row
        self.update_ui(update_table_selection=False)

    def delete_current(self):
        if self.results:
            self.results.pop(self.current_idx)
            self.details_table.removeRow(self.current_idx)
            self.current_idx = max(0, min(self.current_idx, len(self.results)-1)) if self.results else 0
            self.update_ui()
            self.update_delete_button_visibility()
    

    def confirm_delete_current(self):
        if not self.results:
            return

        fname = os.path.basename(self.results[self.current_idx]['path'])

        reply = QMessageBox.question(
            self,
            "Delete image",
            f"Are you sure you want to remove:\n\n{fname}\n\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.delete_current()


    def on_pins_modified(self, pins):
        r = self.results[self.current_idx]
        r['pins'] = pins
        r['manually_corrected'] = True

        metrics = calculate_all_metrics(
            pins,
            r['pitch'],
            self.level_switch.isChecked()
        )
        r.update(metrics)
        self.update_ui(update_table_selection=False)


    def recompute_all_metrics(self):
        if not self.results:
            return
        
        try:
            pitch = float(self.pitch_in.text())
        except ValueError:
            return

        do_leveling = self.level_switch.isChecked()

        for i, r in enumerate(self.results):
            r['pitch'] = pitch   
            new_metrics = calculate_all_metrics(
                r['pins'],
                pitch,
                do_leveling
            )

            # Preserve non-metric data
            r.update(new_metrics)

        self.populate_details_table()
        self.update_ui(update_table_selection=False)

    def update_ui(self, update_table_selection=True):
        self.update_delete_button_visibility()

        self.btn_export.setEnabled(len(self.results) > 0)
        #self.btn_delete_img.setVisible(True)

        
        if not self.results:
            self.btn_delete_img.hide()
            self.btn_edit_pins.setChecked(False)
            self.img_view.setCursor(Qt.ArrowCursor)
            # Disable pin editing safely
            self.btn_edit_pins.setEnabled(False)
            self.btn_edit_pins.setChecked(False)
            self.img_view.set_edit_mode(False)

            # Clear interactive canvas
            self.img_view.set_data(None, [])

            # Reset metric labels
            for k in self.lbl_vals:
                self.lbl_vals[k].setText("--")

            self.l_file.setText("Ready")
            self.stats_table.clearContents()
            self.details_table.setRowCount(0)
            self.viz_widget.plot_metrics(None)
            return
        
        
        self.btn_edit_pins.setEnabled(True)

        res = self.results[self.current_idx]
        img, pins = res['viz']; viz = img.copy()
        #for p in pins: cv2.circle(viz, (p['x'], p['y']), 7, (255, 0, 0), -1)
        for i in range(len(pins) - 1):
            p1 = pins[i]
            p2 = pins[i + 1]

            cv2.line(
                viz,
                (p1['x'], p1['y']),
                (p2['x'], p2['y']),
                (30, 255, 0),   # slightly softened red
                thickness=1,
                lineType=cv2.LINE_AA
            )
        for p in pins:
            c = (p['x'], p['y'])

            # Outer outline (dark blue)
            cv2.circle(
                viz,
                c,
                radius=5,
                color=(255, 70, 30),
                thickness=1,
                lineType=cv2.LINE_AA
            )

            # Inner fill (light blue)
            cv2.circle(
                viz,
                c,
                radius=4,
                color=(220, 210, 190),
                thickness=-1,
                lineType=cv2.LINE_AA
            )

            # Center dot
            cv2.circle(
                viz,
                c,
                radius=1,
                color=(120, 70, 30),
                thickness=-1,
                lineType=cv2.LINE_AA
            )


        self.img_view.set_data(viz, pins,res.get('hy_calib'))

        
        self.lbl_vals['h_rms'].setText(f"{res['rms']:.3f} cm")
        self.lbl_vals['cl'].setText(f"{res['cl']:.3f} cm")
        self.lbl_vals['h_max'].setText(f"{res['h_max']:.3f} cm")
        self.lbl_vals['ic'].setText(f"{res['ic']:.2f} %")
        self.lbl_vals['df'].setText(f"{res['df']:.3f}")
        
        self.l_file.setText(f"{os.path.basename(res['path'])} ({self.current_idx+1}/{len(self.results)})")
        
        keys = ['rms', 'cl', 'h_max', 'ic', 'df']
        for col, key in enumerate(keys):
            vals = [r[key] for r in self.results]
            if vals:
                self.stats_table.setItem(0, col, QTableWidgetItem(f"{np.mean(vals):.4f}"))
                self.stats_table.setItem(1, col, QTableWidgetItem(f"{np.std(vals):.4f}"))
                self.stats_table.setItem(2, col, QTableWidgetItem(f"{np.min(vals):.4f}"))
                self.stats_table.setItem(3, col, QTableWidgetItem(f"{np.max(vals):.4f}"))
        
        self.viz_widget.plot_metrics(res['plot_data'])

        if update_table_selection:
            self.details_table.selectRow(self.current_idx)
        
        self.b_prev.setEnabled(self.current_idx > 0)
        self.b_next.setEnabled(self.current_idx < len(self.results)-1)
        

    def next(self): 
        self.current_idx += 1; self.update_ui()
        
    def prev(self): 
        self.current_idx -= 1; self.update_ui()

    def export_data(self):
        if not self.results: return
        path, _ = QFileDialog.getSaveFileName(self, "Export Data", "results_full.csv", "CSV Files (*.csv)")
        if path:
            try:
                keys = ['rms', 'cl', 'h_max', 'ic', 'df']
                key_headers = ['RMS_cm', 'L_cm', 'H_max_cm', 'Tortuosity_%', 'Fractal_Dim']
                
                with open(path, 'w', newline='') as csvfile:
                    csvfile.write("--- BATCH STATISTICS ---\n")
                    csvfile.write("Metric,Mean,Std_Dev,Min,Max\n")
                    for key, header in zip(keys, key_headers):
                        vals = [r[key] for r in self.results]
                        line = f"{header},{np.mean(vals):.4f},{np.std(vals):.4f},{np.min(vals):.4f},{np.max(vals):.4f}\n"
                        csvfile.write(line)
                    
                    csvfile.write("\n")
                    csvfile.write("--- DETAILED RESULTS ---\n")
                    fieldnames = ['Filename'] + key_headers + ['Full_Path']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for r in self.results:
                        row = {
                            'Filename': os.path.basename(r['path']),
                            'RMS_cm': r['rms'],
                            'L_cm': r['cl'],
                            'H_max_cm': r['h_max'],
                            'Tortuosity_%': r['ic'],
                            'Fractal_Dim': r['df'],
                            'Full_Path': r['path']
                        }
                        writer.writerow(row)
                        
                QMessageBox.information(self, "Success", "Data and statistics exported successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # --- SPLASH SCREEN ---
    splash_pix = QPixmap(resource_path("splash.png"))
    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()

    # Optional message
    splash.showMessage(
        "Loading PinSight...",
        Qt.AlignBottom | Qt.AlignCenter,
        Qt.white
    )

    # --- LOAD MAIN WINDOW ---
    window = PinApp()

    splash.showMessage(
        "Initializing interface...",
        Qt.AlignBottom | Qt.AlignCenter,
        Qt.white
    )
    app.processEvents()

    window.show()

    splash.finish(window)
    sys.exit(app.exec())

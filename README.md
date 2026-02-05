# PinSight  
**Digital Analysis of Pin Profiler Photographs for Soil Surface Roughness**

PinSight is a **computer vision–based desktop application** for the automated and reproducible processing of **pin profiler photographs**, enabling quantitative analysis of **soil surface roughness**.

The software is designed for researchers and practitioners in **soil physics, hydrology, erosion studies, and agricultural engineering**, providing an end-to-end workflow from image acquisition to numerical indicators and scientific visualization.

---

## 📸 Application Screenshots

### Full Application Interface
The complete PinSight workspace showing image processing, detected pins, roughness metrics, batch statistics, and scientific visualizations.

![PinSight Full Interface](./pinsight_full.png)

---

### Interactive Pin Editing Mode
Manual editing mode allows users to **add, delete, or reposition pins** when automatic detection requires refinement.  
All roughness metrics are **updated instantly** after any modification.

![PinSight Pin Editing Mode](./pinsight_edit_mode.png)

---

## 🚀 Key Features

### 🔍 Automated Image Processing
- Automatic detection of pin profiler boards
- Perspective correction and image warping
- Robust extraction of pin positions from photographs
- Image quality validation and error handling

### ✏️ Interactive Pin Editing
- Enable or disable manual pin editing
- Drag pins to refine their positions
- Add pins (double-click)
- Remove pins (right-click)
- Real-time update of all computed metrics

### 📐 Soil Surface Roughness Metrics
- Multiple roughness indicators are computed automatically
- Metrics describe both vertical variability and spatial structure
- Optional **leveling and detrending** can be applied
- All approaches follow methods commonly adopted in the scientific literature

### 📊 Scientific Visualizations
- Surface microtopography profile
- Autocorrelation analysis
- Log–log semivariogram representation
- High-quality plot export (PNG, JPG, PDF)

### 📁 Batch Processing
- Process multiple images or entire folders
- Automatic computation of batch statistics
- Efficient navigation between samples

### 📤 Data Export
- Export results and statistics to CSV format
- Outputs ready for modeling, reporting, and publication

---

## 💻 Installation

### Windows
Download the latest installer from the **Releases** page:

👉 https://github.com/mouadklai/PinSight/releases

Run:
PinSight_v0.1_Setup.exe

No Python installation is required.

---

## 🖥️ System Requirements

- **Operating System:** Windows 10 / 11 (64-bit)
- **RAM:** ≥ 8 GB recommended
- **Display:** Full HD or higher recommended
- **Input:** High-quality pin profiler photographs

---

## 📷 Image Acquisition Guidelines

For optimal performance:
- Ensure uniform and sufficient lighting
- Capture the full pin profiler board
- Pins should be clearly visible and distinguishable
- Avoid shadows, blur, and extreme perspective distortion
- Recommended minimum: **~45 detectable pins**

The application automatically identifies and reports unsuitable images.

---

## 📚 Citation

If you use PinSight in academic or technical work, please cite:

**APA**
Klai, M. et al. (2026). PinSight: A computer vision-based software for automated processing of pin profiler photographs for soil surface roughness analysis.

**BibTeX**
```bibtex
@software{klai2026pinsight,
  author = {Klai, Mouad et al.},
  title  = {PinSight: A computer vision-based software for automated processing of pin profiler photographs for soil surface roughness analysis},
  year   = {2026}
}

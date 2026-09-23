# PinSight User Guide

PinSight is a desktop application for extracting and analyzing soil-surface profiles from photographs of pin profilers. It supports automated computer-vision processing, interactive correction of detected pins, and fully manual profile digitization.

## Main features

- Automatic detection and perspective correction of the profiler board
- Automatic pin detection and one-dimensional profile reconstruction
- Interactive addition, movement, and removal of detected pins
- Manual digitization with region-of-interest and axis calibration
- Optional linear detrending of reconstructed profiles
- Calculation of root-mean-square height, correlation length, maximum height, chain index, and fractal dimension
- Surface-profile, autocorrelation, and semivariogram plots
- Batch processing with validation messages and summary statistics
- CSV and image export

## System requirements

- Windows 10 or Windows 11, 64-bit
- At least 8 GB of RAM recommended
- No separate Python installation is required for the packaged Windows release
- Current release: PinSight v0.1
- Approximate distribution size: 414 MB

## Download and installation

1. Open the [PinSight project page](https://mouadklai.github.io/PinSight/) or the [GitHub repository](https://github.com/mouadklai/PinSight).
2. Download the current Windows distribution from the repository's **Releases** section.
3. Install or extract the distribution as indicated by the release package.
4. Launch PinSight.

## Recommended image acquisition

Good photographs reduce detection errors and manual correction.

1. Place the pin profiler on the soil and lower it gently until all pins contact the surface.
2. Wait until the pins are stable.
3. Include the complete profiler frame in the photograph.
4. Keep the camera approximately perpendicular to the profiler board.
5. Avoid motion blur, strong shadows, glare, and severe oblique viewing angles.
6. When possible, orient the profiler toward the sun to reduce shadows on the backing board.
7. Check that the pin tips and the high-contrast backing board are clearly visible.

PinSight can correct moderate perspective and illumination differences, but heavily blurred, shadowed, tilted, or obstructed images may require manual processing.

## Automatic processing

1. Enter the physical horizontal and vertical dimensions of the profiler board.
2. Import one photograph, or select a folder for batch processing.
3. Start automatic processing.
4. Inspect the rectified board image and the detected pin overlay.
5. If necessary, use the interactive editor to add, move, or delete pin detections.
6. Enable detrending when the objective is to remove large-scale slope from the profile.
7. Review the calculated metrics and plots.
8. Export the results.

The automated workflow detects the profiler region, rectifies its perspective, segments the pins, converts pixel positions to physical coordinates, and constructs the surface profile.

## Manual profile acquisition

Use manual acquisition when the profiler board or pins cannot be detected reliably.

1. Open the manual profiling tool and load the photograph.
2. Draw a rectangular region of interest around the profiler board.
3. Define the horizontal axis by selecting two points on a segment of known length.
4. Define the vertical axis in the same way.
5. Select the visible pin tips.
6. Add, move, or remove points as needed. Undo and redo are available.
7. Finish the digitization to convert the selected points to physical coordinates.
8. Review and export the resulting profile and roughness metrics.

Saved manual profiles retain their calibration and editing state so that work can be resumed later. Automated and manual profiles use the same metric-computation module.

## Calculated roughness metrics

### Root-mean-square height

The root-mean-square height, $H_{\mathrm{RMS}}$, describes the vertical variability of the profile around its mean elevation.

### Correlation length

The correlation length, $L$, is the physical lag at which the normalized autocorrelation decreases to $1/e$. It describes the horizontal scale over which surface elevations remain correlated.

### Maximum height

The maximum height, $H_{\max}$, is the difference between the highest and lowest profile elevations.

### Chain index

The chain index expresses the difference between the projected horizontal length and the cumulative length of the measured profile. It provides a measure of profile tortuosity.

### Fractal dimension

The fractal dimension, $F_D$, is estimated from the slope of the log-log semivariogram and describes surface complexity across the analyzed lag range. Its value depends on pin spacing and sampling scale.

## Detrending

PinSight can fit and remove a first-order elevation trend before calculating the roughness metrics.

- Disable detrending to retain total relief, including large-scale slope.
- Enable detrending to focus the analysis on microtopographic variation.

Use the same setting when comparing profiles.

## Batch processing and exports

In batch mode, each photograph is processed through the same detection, validation, and metric-computation workflow. Images that fail board, texture, contrast, geometry, or pin-count checks are flagged and excluded with an explanatory message.

PinSight reports the mean, standard deviation, minimum, and maximum of each metric across successfully processed images. CSV exports contain batch summaries, per-image metrics, and references to the original image files. Plots can be exported in PNG, JPEG, or PDF format.

## Troubleshooting

### The board is not detected

- Confirm that the complete board is visible.
- Crop distracting background objects when possible.
- Use a less oblique photograph.
- Check that the board contrasts with the surrounding scene.
- Use manual acquisition if automatic detection still fails.

### Pins are missing or merged

- Check for motion blur, shadows, adhered soil, or partial occlusion.
- Correct individual detections with the interactive editor.
- Use manual acquisition when many pins are affected.

### The physical scale is incorrect

- Verify the entered board dimensions.
- In manual mode, confirm the reference lengths and selected axis endpoints.
- Ensure that the full profiler board is contained within the selected region.

### Results are not comparable across images

- Use the same physical dimensions and detrending setting.
- Apply the same acquisition orientation and image-quality criteria.
- Check that each reconstructed profile contains the expected pins.

## Known limitations

Automatic detection can be affected by severe motion blur, large oblique viewing angles, strong or uneven shadows, partial pin occlusion, and soil or debris attached to the pins. All automatically reconstructed profiles should be visually inspected before analysis.

## Project links and contact

- Project page: https://mouadklai.github.io/PinSight/
- Source code and releases: https://github.com/mouadklai/PinSight
- Developer: Mouad Klai
- Contact: klaimouadklai@gmail.com


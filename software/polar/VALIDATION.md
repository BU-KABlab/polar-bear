# Validation of POLAR 0.6.0

Build checked on macOS with Python 3.10, NumPy/SciPy/OpenCV and Flask. These checks establish software behavior, not experimental measurement accuracy.

Current calibration defaults (updated October 7, 2026): Reference Z = 123.5 mm, Reference LED height = 111.7 mm, consistently in the website, API, Python functions and command-line entry points. Historical regression values below use their original supplied calibration; saved runs retain their own settings.

- **93 automated tests passed**: original MATLAB-equivalent known-volume solver, 24-spot detection and missing/ambiguous-ring rejection; focus response to blur/exposure and broad lobes; height propagation; synthetic below/above-90° outline inversions; rejection of two-root ambiguity; circle fitting; unavailable error when a height interval crosses a branch; synthetic OWRK recovery and negative-coefficient handling; mixed-substrate/convention/degenerate-polarity rejection; ZIP traversal/large multipart upload; outline confirmation and clipping; token/host checks; three-column Excel export. This includes elongated-spot detection, missing-spot rejection on an elliptical ring, and provisional-result/audit/export checks in both focus-stack and individual-frame modes.
- **Actual browser upload:** an 80-image, 438 MB ZIP assembled from `formal-4-PAMA-C1-C4-10ul-2/images`, using original unmodified TIFFs. All 80 were scanned, 36 yielded valid complete rings, and one image was selected for each of C1–C4. Selection and numerical output match the existing batch result to 1e-9 degrees.
- **Clean Excel:** the actual web endpoint produced one `Results` sheet, three columns, four wells. Missing results remain blank. Filenames are treated as strings, not Excel formulas.
- **Browser UI:** ZIP upload, progress, result table, image/LED overlay, saved-run listing, OWRK input, fit chart and exact synthetic energy recovery were checked. The outline browser workflow proposed and confirmed the synthetic droplet boundary, recovering 60.019° and 17.663 µL against a constructed 60° / 17.671 µL cap. The synthetic case recovered dispersive 22, polar 7, total 29 mJ/m²; it is not a measurement of the user's substrate.
- **CubOS:** file-export naming inspected in the cloned repository; no hardware was touched and no CubOS runtime was changed.

Real-image regression, at supplied volume 10 µL and height step 0.2 mm:

| Well | Selected image ID | Z (mm) | Angle (°) | Error (°) |
|---|---:|---:|---:|---:|
| C1 | 242 | 59.9 | 55.075808 | 2.442452 |
| C2 | 262 | 59.9 | 55.317149 | 0.354606 |
| C3 | 283 | 59.7 | 55.667605 | 4.396856 |
| C4 | 305 | 59.3 | 44.465668 | 1.570886 |

C1, C3 and C4 have review flags. C3 has a nearby focus competitor; C4 is at a scan boundary. The existing directional-spread and alignment flags are retained. Error is the requested two-source combination, not total measurement uncertainty.

## Not yet established

- Independent ground-truth accuracy of the new outline/unknown-volume method on real droplets.
- Performance across arbitrary illumination, magnification, droplet shapes and severe saturation. The detector retains calibrated pixel-area and ring-geometry limits; this is not universal detection.
- Physical Raspberry Pi performance or Docker-image execution on the target architecture.
- Dynamic advancing/receding protocol validation, evaporation tracking accuracy, temperature compensation, or a complete metrological uncertainty budget.
- Surface energy of the user's substrate: three identified probe-liquid datasets are still needed.

## Version 0.2: configurable names and time-series focus stacks

Added filename templates editable in the website, previewed well/Z/time extraction, remembered browser conventions, explicit elapsed-time units or scan-number conversion, and independent focus selection for each well/time point. The new tests cover decimal-hyphen heights, field order, unit conversion and mismatch rejection, invalid templates, unmatched names, failed time points, protection against collapsing different times into a single well result, and four-column time-series Excel exports. The default CubOS workflow remains covered by the original tests.

Browser verification used synthetic images labeled as tests: two wells × two time points × three focus heights. This checks grouping and interaction behavior; it is not an evaporation experiment or a validation of experimental angle accuracy.

## Version 0.3: conditional OWRK error propagation

Added optional angle-error inputs, imported measurement errors, repeat fits with bounded angular distributions, energy-component SDs and a labeled plot with transformed error bars and a propagated fit band. The three-column energy workbook preserves missing errors as blank and documents the scope in a header comment.

New tests compare batched nonnegative fits with SciPy NNLS, compare small-error Monte Carlo propagation against finite-difference linear propagation, verify total-energy covariance, reproducibility, zero versus missing errors, partial-input rejection, invalid and near-boundary spreads, replicate handling, and API/workbook agreement. Browser verification recovered the synthetic 29/22/7 mJ/m² energies with propagated errors 0.84/1.11/1.01 mJ/m² from 2° input spreads and displayed the annotated plot. Saved-result import was verified both into an empty preset row and into a new replicate row, retaining the angle/error and provenance warning. Partial error input was rejected in the browser; the workbook export endpoint completed successfully. These are software-validation inputs, not substrate measurements.

This is conditional propagation under the documented angular-distribution and independence assumptions. It does not establish full experimental uncertainty, uncertainty in a replicate mean, liquid-property uncertainty, or OWRK model accuracy.

## Version 0.3.1: explicit temperature labeling

The temperature field, help text, result notes, API method description and Excel document metadata now explicitly state that temperature is recorded only. Users must enter liquid properties appropriate to the measurement temperature. This is a presentation/metadata correction; no temperature compensation model was introduced.

Verification: all 67 tests passed; changing only recorded temperature from 20 to 30 °C left every numerical result and propagated error identical. The browser label/help layout and the exported workbook temperature metadata were checked.

## Version 0.4.1: reference-Z calibration

Removed the separate filename offset setting. Filename heights are read directly; coordinate differences are handled by Reference Z. A regression check verifies the B1 wellplate filename gives Zg=124.800 mm and that increasing Reference Z by 12 mm reproduces the same LED-to-substrate height as subtracting 12 mm from the filename value. Legacy offset inputs are ignored in new runs, while historical stored results are not modified.

## Version 0.4.2: calculate complete elliptical rings with review warnings

Removed the ellipse-axis-ratio rejection and individual spot aspect-ratio restriction. Wider spot neighborhoods connect elongated rings. Full-ring spacing, opposite-pair symmetry, ambiguity and physical-solver checks remain. Ratios above 1.5 are reported as provisional results, with an explicit warning that geometry/model bias is not included in the error. Measured pixel distances are never circularized.

Reprocessed all 20 original campaign 22 images through the application pipeline, with no manual ROI: B2 selects camera 111 at Z=123.2 mm and returns 23.871829° with combined error 4.433112°, axis ratio 1.865540. It retains the scan-boundary warning. Campaign 19 still selects camera 49 at Z=123.6 mm, returning the unchanged 50.557848° and error 1.767783°.

The axis ratio is included in image review and the JSON audit. The known-volume run workbook remains one Results sheet with only well/frame, angle and error. These are software and real-image regression checks; they do not establish physical accuracy for distorted droplets.


## Version 0.5.0: independent focus stacks by position

Added the {position} filename field and Position scan grouping. The three supplied left_4mm, left_1mm and center_0mm filenames parse into separate A1 groups. A synthetic ZIP of nine offsets with ten heights each produces nine rows, picks the sharpest height independently, and retains a failed offset as a blank result. Additional checks prevent position labels being silently merged by well-only grouping and keep identical offset labels in different wells separate. The run Excel remains one Results sheet with three columns; labels include both well and position. Existing calibration defaults remain 123.5 / 111.7 mm.


## Version 0.6.0: manual LED pairs and decimal-p filenames

Manual endpoints are checked for finite coordinates, image bounds, distinct reflections and 1–12 pairs. The known-volume path uses the existing physical solver and height propagation, with unavailable directional SD/combined error for a single pair. Tests cover original pixel distances, partial sets, outline preparation, recovery of failed results, group-restricted source access, audit history and clean Excel export. Custom height tokens now accept p/P decimal notation, including negative heights, with tests against silent truncation of malformed tokens.

Browser verification used a separate, clearly labeled synthetic run with a missing LED: opened its failed result, loaded the original-resolution image, clicked two opposite-pair lines, changed zoom without changing pixel distances, and saved a finite angle/error with manual provenance. No user measurement was overwritten during this UI test.

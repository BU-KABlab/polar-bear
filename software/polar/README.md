# POLAR

**Precise Optical Liquid Angle Resolver** — a standalone, local web application for top-down telecentric droplet analysis. No cloud account, frontend build, or CubOS installation is needed.

## Start on a Mac or Linux computer

Requires Python 3.10–3.13. Open a terminal inside the extracted POLAR folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:8765**. Stop with Ctrl+C. Later starts only need activation and `python app.py`. Alternatively, `./run.sh` creates the environment on first use and starts POLAR. On Windows activate with `.venv\Scripts\activate` instead.

## Analyze images

1. Upload one CubOS ZIP, or multiple original TIFF/PNG/JPEG images. ZIPs may contain nested image directories and manifests; unrelated files are ignored. Keep one experiment per run so repeated well names are not mixed. Limit: 512 MB upload, 1,000 images, 128 MB/image, 4 GB extracted images.
2. Enter the run name, substrate/preparation and probe liquid. These identities allow reusing results for OWRK.
3. Choose **Known volume**, enter µL, and use **Focus stack** to select the sharpest usable image per well. **Time series · focus stack per time point** chooses one image per well and elapsed time. **Individual frames** keeps every image without focus selection (ordered by CubOS capture timestamp when all filenames contain one, otherwise upload order).
4. Check calibration. The defaults use your current calibration: 59.5 mm opposite LED spacing, 6.35/909.85 mm/pixel, LED-to-substrate height 111.7 mm at gantry Z=123.5 mm. `plate.C4_z=59-300mm` gives well C4 and Z=59.300 mm. Supply fallback Z for images without compatible metadata.
5. Analyze. The result table and Excel contain only **Well/frame, Contact angle, Error**. Time-series stacks add **Time (s)** and keep one row per well and time point. Review flags, rejected images, pair measurements and source previews remain in the app. A blank angle/error is unavailable, never zero.

Height calibration assumes the gantry motion changes LED-to-substrate height by the same signed amount. If only the camera moves and the LEDs remain fixed, this calibration model must be changed before use. Preserve the original pixel scale; resized images invalidate the default calibration.

Ellipticity alone does not reject a measurement. POLAR measures all 12 actual opposite-pair distances when it identifies a complete ring, including elongated reflections. A long/short ellipse axis ratio above 1.5 produces a provisional result with a review warning; its geometry/model bias is not included in the reported error. The ratio remains in image review and the JSON audit, while the Excel run export stays simple. Missing spots, ambiguous rings, inconsistent spacing/pair symmetry and nonphysical solver results still produce no angle.

### Configure the filename convention on the website

For offset experiments, choose **Position scan · focus stack per offset** and use a custom pattern such as:

```text
camera_*_{position}_ursa_wellplate.{well}_after_dispense_white_height*{z}mm*
```

This reads `left_4mm`, `left_1mm` or `center_0mm` as the position, `A1` as the well, and `124-200` as Z=124.200 mm. The wildcard after height accepts either = or _, and 122p8 is read as 122.8 mm. Upload all nine positions × ten heights in one ZIP (90 images), or select the images together. Focus is selected independently for each well and position, giving nine results for one well. Preview filenames to confirm the group count before analyzing. The simple Excel export labels rows `A1 · left_4mm` and keeps just label, contact angle and error. Original image files must retain a supported extension such as `.tiff`. Position scans do not treat capture timestamps as time-series labels; use separate runs for repeated experiments at the same offsets.

Open **Filename convention** in the image-import card. Keep the CubOS default for the original `plate.C4_z=59-300mm` names, or choose **Custom pattern**. No Python edits are needed.

For example, the filename:

```text
camera_123_plate.C4_t=120s_z=59-300mm_b25.tiff
```

can use this pattern:

```text
*plate.{well}_t={time}s_z={z}mm*
```

`{well}` captures a well such as C4 or A12. `{z}` captures gantry Z in millimetres; both 59.300 and 59-300 mean 59.300 mm. `{time}` captures a numeric elapsed time or scan number. Fixed text must follow each captured field, or the field must end the filename; `*` ignores other text. Templates are case-insensitive. Up to four wildcards are supported; unknown or duplicate fields are rejected. `{z}` may be omitted only if a fallback Z is supplied in Calibration. This changes how POLAR reads names; it does not rename images or configure CubOS acquisition.

For filenames such as `camera_43_ursa_wellplate.B1_PAMA_water_after_dispense_white_height=124-800mm_b25_20261006-205557.tiff`, use `*wellplate.{well}_*height={z}mm*`. POLAR reads **124.800 mm directly**. Handle the coordinate difference using **Reference Z** under Calibration: to reproduce subtracting 12 mm from each filename height, increase the original reference Z by 12 mm while retaining the same reference LED height. For example, 59.7 becomes 71.7 mm, with H_ref still 110.2 mm for that same physical calibration anchor. This follows `H_sub = H_ref + (Zg − Z_ref)`. There is no separate filename offset setting. Existing saved results remain unchanged; legacy remembered offset fields are ignored for new runs.

Select seconds, minutes or hours for elapsed-time labels. If labels are scan numbers, choose **Scan number**, enter the scan interval in the selected time unit, and specify whether the first scan is 0 or 1. POLAR computes elapsed time as `(scan − first scan) × interval` and stores/exports seconds. This conversion assumes equally spaced scans; use explicit elapsed-time labels when the schedule is irregular.

Use **Preview grouping** to inspect the extracted well, Z and elapsed time. Selecting individual images fills the preview filenames automatically; for a ZIP, paste sample filenames from the archive. All uploaded custom filenames are checked again before image analysis. A mismatch blocks that run with an example filename and reason. **Remember convention** stores the rule and collection mode in this browser; each saved run also retains its own rule, so later changes do not rewrite previous results. Calibration values are not saved by this button.

For time-series focus stacks, every image within one well/time point must share the same time label even though Z and capture timestamp change. POLAR selects focus independently for each `(well, elapsed time)` group, retains failed groups with blank angles, and plots each well against elapsed time. Capture timestamps are not automatically treated as scan labels. Attempting to combine multiple labeled times in ordinary one-result-per-well mode is blocked. For evaporation, use the experimental unknown-volume geometry or an independently established volume for every time point: known-volume mode applies one supplied volume to the whole run.

### What is the error?

Directional sample SD across the 12 opposite pairs is combined in quadrature with a shared geometric height contribution. A step ΔZ gives u(Z)=ΔZ/√12, assuming the unresolved best-focus position is uniform over ±ΔZ/2. All pairs are recalculated at the two height endpoints, keeping measured separations fixed; the change in mean angle divided by √12 estimates its standard contribution.

This is a **two-source descriptive error**, k=1, under an uncorrelated-contributions assumption. It is not the standard error of the mean, a 95% interval, or a complete uncertainty budget. It excludes volume, pixel-scale calibration, LED placement, focus-induced centroid displacement, outline localization and model bias. Focus-selection errors larger than half a step are not covered. Directional variation can also reflect actual shape asymmetry rather than independent measurement noise.

### Unknown volume: Outline + LEDs (experimental)

Choose below/above 90° and the boundary interpretation. POLAR proposes circles from image contours, but you must review the complete physical boundary. Select a proposal or mark at least three widely spaced boundary points. Reject images whose physical boundary cannot be established. The app rejects clipped, poorly circular or severely misaligned fits, impossible solutions and ambiguous multiple roots. It cannot reliably distinguish every reflection from a physical boundary automatically.

A footprint alone cannot determine both contact angle and volume. This mode combines your LED reflection equation with a spherical-cap boundary constraint:

- LED radius r = R sin α.
- H = R(cos α − cos θ) + (L − r) cot(2α).
- Below 90°, the contact radius b = R sin θ.
- Above 90°, an outer silhouette gives R=b; a separately identified contact line instead gives b=R sin θ.
- h = R(1−cos θ), V = πh²(3R−h)/3.

Mean angle, directional SD, height contribution and estimated volume are available in measurement review. If height perturbation crosses a valid branch, a symmetric error is not reported. This extension is a mathematical inversion of the supplied model, tested against synthetic geometry; it still needs validation against independent measurements. Spherical-cap assumptions can fail for distorted, large, gravitationally flattened or pinned/noncircular drops. Do not interpret a fitted circle as proof of a spherical cap.

Evaporation is not automatically a receding-angle measurement: the contact line may remain pinned. Advancing/receding labels require an appropriate protocol and established contact-line motion. Above 90°, silhouette motion alone is not contact-line motion.

### Surface energy

Use at least three **distinct liquids** on the same substrate preparation and with one angle convention. Enter angles directly, or add saved image measurements. Edit and verify liquid polar/dispersive tensions at your actual temperature; the **Measurement temperature (°C) — recorded only** field does not automatically correct contact angles, liquid tensions or surface energy. Changing this field alone leaves the numerical fit and propagated errors unchanged. Temperature remains in the API result and exported workbook metadata. The initial values are literature starting points, not certified constants. Empty initial angle fields are intentional.

POLAR fits the OWRK linearization:

```text
x = sqrt(γL_p / γL_d)
y = γL (1 + cos θ) / (2 sqrt(γL_d))
y = b + m x
γS_d = b², γS_p = m², γS_total = b² + m²
```

Replicate angles are averaged within each liquid, then liquids receive equal weight. At least two different liquid polarities are mathematically necessary; POLAR enforces your three-liquid requirement and rejects inadequate contrast. Nonnegative coefficients are imposed, with a warning if the unconstrained fit is negative. R² and residuals describe fit agreement, not total uncertainty. Angle errors can be propagated as described below; this does not make directional SD an uncertainty in the mean. Using advancing/receding/apparent angles gives a convention-specific apparent energy. OWRK is a model for dispersive/polar interactions; it does not identify separate acid/base components or validate surface homogeneity.

### Surface-energy error and plot

Enter **Angle error (°)** as a one-standard-deviation input spread, or import a saved measurement to carry over its existing directional + height error. Supply an error for every included measurement, or leave all error fields blank for point estimates only. An explicitly entered zero means no angular spread is assumed; a blank is unknown. Do not enter a 95% confidence interval as though it were one SD.

POLAR runs 20,000 nonnegative OWRK fits using independent bounded beta distributions on 0–180°, matched to each liquid's entered mean angle and spread. This distribution is a modeling choice, not an experimentally established error distribution. Repeated calculations use a fixed seed for reproducibility. The primary energies come from the nominal input angles; each reported error is the sample SD of the propagated energy draws. Total energy is calculated within each draw, preserving covariance between the fitted polar and dispersive components. It is not calculated by combining their errors as independent quantities.

For repeated rows of the same liquid, the fit uses the arithmetic mean angle and the RMS entered error. **This describes propagation of a representative angular spread, not statistical uncertainty in the replicate mean.** No automatic sqrt(n) reduction is applied, and between-drop scatter is not added (it could overlap the entered errors). If you have independently evaluated an uncertainty in a mean angle, enter that mean and its standard uncertainty as one row for the liquid. Shared calibration errors across different liquids are not modeled; the independent-liquid assumption must be appropriate for your interpretation.

The plot shows numbered liquid labels, ±1 SD vertical bars after the nonlinear angle transformation, the nominal fit and a pointwise 16th–84th percentile band of propagated fits. That band is neither a prediction interval for a new liquid nor a simultaneous confidence band. Near a zero component the distribution can be asymmetric; the app flags boundary fits and the reported ±SD should not be interpreted as symmetric physical bounds. Liquid tensions are treated as fixed, so no horizontal error bars are inferred.

The clean Excel sheet contains only **Component, Surface energy, Propagated error (1 SD)**. Its error-header comment records the assumptions. Values without supplied angle errors have blank error cells. These are **conditional propagated angle-error estimates**, not a complete uncertainty budget: uncertainties in liquid properties, omitted calibration terms, and OWRK/model bias are excluded. In particular, propagating an imported directional spread does not convert it into a standard uncertainty of the mean.

## Storage and integration

Original uploads, previews, settings and computed JSON are saved under `data/` beside the application. Set `POLAR_DATA_DIR` to change this. Jobs survive restarts; interrupted analyses must be re-uploaded. There is no automatic deletion; archive or remove a run's directory while the server is stopped. Back up this directory if the measurements matter.

CubOS compatibility is file-based and was checked against its ZIP export naming. POLAR does not operate hardware or change CubOS. A small same-origin JSON API supports future integration:

- `POST /api/naming/preview`: JSON `filenames` and `settings`; returns extracted fields and grouping counts.
- `POST /api/jobs`: multipart `files`, JSON string `settings`, optional `name`.
- `GET /api/jobs/<id>`: poll state/progress/results.
- `GET /api/jobs/<id>/results.xlsx` and `/audit.json`.
- `POST /api/owrk`: `rows`, `substrate`, `convention`, `temperature`, `confirmed:true`. Each row may include `angle_error` in degrees and `error_kind` (`polar_spread` for imported measurement errors). The response includes `uncertainty` or null when no errors were supplied.

Local requests need `X-POLAR-Request: 1`. If a token is configured, use `Authorization: Bearer TOKEN` on API calls. Cross-origin browser requests are rejected. Without a token, only localhost/loopback Host headers are accepted. Use a trusted network or HTTPS; a token alone does not encrypt traffic. The health endpoint and static interface are public; uploaded data require the configured token.

## Raspberry Pi deployment

Designed for **64-bit Raspberry Pi OS** with a 64-bit Python 3.11 runtime. This release has not been tested on physical Pi hardware. Start with the same virtual-environment steps above. Image processing uses one worker to bound CPU/memory demand; large TIFF scans may take longer on a Pi. Python wheels are easiest on a current 64-bit OS.

For a persistent server:

```bash
source .venv/bin/activate
POLAR_DATA_DIR="$PWD/data" gunicorn --workers 1 --threads 4 --bind 127.0.0.1:8765 --timeout 180 'app:create_app()'
```

Keep **one process worker**: the local queue and write lock are per process. For a trusted LAN, set a long random `POLAR_API_TOKEN` and change the bind address to `0.0.0.0:8765`. Enter the token in the web app's Connection dialog. The built-in `python app.py` launcher refuses non-loopback binding without a token. Gunicorn/Docker bind settings are operator-controlled; do not expose them without a token and appropriate network protection.

`deploy/polar.service.example` is a template, not an installed service. Adjust paths/user, create a writable data directory, and put configuration in `/etc/polar.env`. Docker is optional: `docker compose up --build -d` binds localhost by default and persists data in a named volume. The Docker build and physical Pi deployment still require verification on the target device.

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

Tests cover the original solver, focus metrics/height propagation, synthetic outline inversion including multiple roots, circle fitting, OWRK recovery, invalid input, archive traversal and clean exports. See `VALIDATION.md` for measured checks for this build.

References: [Owens & Wendt (1969)](https://onlinelibrary.wiley.com/doi/10.1002/app.1969.070130815), [liquid-property source, Table 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC6105199/), [top-view spherical-cap geometry](https://pubs.acs.org/doi/10.1021/acs.langmuir.5c04532), [NIST uncertainty propagation](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-law-propagation-uncertainty), [JCGM 101 Monte Carlo propagation](https://www.bipm.org/documents/20126/2071204/JCGM_101_2008_E.pdf/325dcaad-c15a-407c-1105-8b7f322d651c).


### Mark LED pairs manually

Open a result (including a failed measurement), then choose **Mark LED pairs manually**. Select the best-focused source image from that same well/position/time point. Click the center of one LED reflection and then its opposite to draw each pair. Zoom up to 8×, drag endpoints to refine them, and use Undo endpoint or Clear lines as needed. Save the manual measurement to calculate with the saved run calibration and volume. For Outline + LEDs, saving the pairs returns to boundary fitting; at least two pairs are required.

The editor accepts 1–12 distinct pairs, measured in original image pixels regardless of zoom. With only one pair, the angle and height contribution are available but directional SD and combined error remain blank. Partial sets are flagged for incomplete directional coverage. Manual results retain a review warning; the reported error excludes manual placement and model uncertainty. The JSON audit stores the endpoints, selected image, save time, and previous result history. The Excel export stays simple.

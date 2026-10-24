#!/usr/bin/env python3
"""Top-down telecentric contact angle from 24 white LED reflections.

All coordinates and distances refer to the original, unresized image.
Requires Python >=3.10, numpy, scipy, opencv-python.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import brentq
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


def gantry_from_filename(path: str | Path) -> float:
    """z=59-300mm or z=59.300mm -> 59.300, NOT 59 or 59.333."""
    matches = re.findall(r"(?:^|_)z=([+-]?\d+(?:[.-]\d+)?)mm(?=_|\.|$)",
                         Path(path).name, flags=re.I)
    if len(matches) != 1:
        raise ValueError("Expected exactly one z=59-300mm or z=59.300mm field; use --zg to override.")
    token = matches[0]
    sign = -1 if token.startswith('-') else 1
    return sign * float(token.lstrip('+-').replace('-', '.'))


def positive(value: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("Must be finite and greater than zero.")
    return result


def read_image(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read a single image; preserve integer bit depth before normalization."""
    if not path.is_file():
        raise ValueError(f"Image does not exist: {path}")
    if path.suffix.lower() in {'.tif', '.tiff'} and cv2.imcount(str(path)) != 1:
        raise ValueError("Expected a single-frame TIFF; export the desired frame first.")
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        raise ValueError(f"Cannot decode image: {path}")
    if im.ndim == 3:
        if im.shape[2] == 4:
            im = cv2.cvtColor(im, cv2.COLOR_BGRA2BGR)
        if im.shape[2] != 3:
            raise ValueError("Expected grayscale, RGB, or RGBA image.")
    elif im.ndim != 2:
        raise ValueError("Expected a 2D grayscale or RGB image.")
    im = im.astype(np.float32)
    if not np.isfinite(im).all():
        raise ValueError("Image contains nonfinite pixels.")
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im
    lo, hi = np.percentile(gray, [1, 99.9])
    if hi <= lo:
        raise ValueError("Image has insufficient intensity contrast.")
    gray = np.clip((gray - lo) / (hi - lo), 0, 1)
    display = (np.clip((im - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
    if display.ndim == 2:
        display = cv2.cvtColor(display, cv2.COLOR_GRAY2BGR)
    return gray, display


def ring_geometry(points: np.ndarray) -> tuple[np.ndarray, dict]:
    """Validate a complete near-elliptical ring, then order spots clockwise."""
    (cx, cy), (d1, d2), angle = cv2.fitEllipse(points.astype(np.float32))
    if not np.isfinite([cx, cy, d1, d2, angle]).all() or min(d1, d2) <= 0:
        raise ValueError("Cannot fit a nondegenerate LED ellipse.")
    phi = math.radians(angle)
    rotation = np.array([[math.cos(phi), -math.sin(phi)],
                         [math.sin(phi), math.cos(phi)]])
    center = np.array([cx, cy])
    uv = ((points - center) @ rotation) / np.array([d1 / 2, d2 / 2])
    radial = np.abs(np.linalg.norm(uv, axis=1) - 1)
    phase = np.sort(np.mod(np.arctan2(uv[:, 1], uv[:, 0]), 2 * np.pi))
    gaps = np.diff(np.r_[phase, phase[0] + 2 * np.pi])
    expected = 2 * np.pi / len(points)
    gap_error = np.max(np.abs(gaps / expected - 1))
    if np.max(radial) > .08 or gap_error > .35:
        raise ValueError("Spots do not form a complete, evenly spaced LED ring.")
    order = np.argsort(np.mod(np.arctan2(points[:, 1] - cy, points[:, 0] - cx), 2 * np.pi))
    points = points[order]
    half = len(points) // 2
    midpoints = (points[:half] + points[half:]) / 2
    midpoint_error = np.linalg.norm(midpoints - center, axis=1)
    radius = (d1 + d2) / 4
    if np.max(midpoint_error) > .06 * radius:
        raise ValueError("Opposite spot pairs are not symmetric about the fitted center.")
    return points, {
        'center_x_px': float(cx), 'center_y_px': float(cy),
        'ellipse_diameters_px': [float(d1), float(d2)],
        'ellipse_rotation_deg': float(angle),
        'ellipse_axis_ratio': float(max(d1, d2) / min(d1, d2)),
        'provisional': bool(max(d1, d2) / min(d1, d2) > 1.5),
        'max_relative_ellipse_residual': float(np.max(radial)),
        'max_relative_angular_gap_error': float(gap_error),
        'max_pair_midpoint_error_px': float(np.max(midpoint_error)),
        'score': float(np.mean(radial) + .1 * gap_error),
    }


def ring_warnings(axis_ratio: float) -> list[str]:
    """Ellipticity requests review, rather than suppressing a measured angle."""
    if axis_ratio > 1.5:
        return ['Provisional result: strongly elliptical LED ring (long/short axis ratio '
                f'{axis_ratio:.3f}). Actual opposite-pair distances were used. '
                'Geometry or droplet-shape bias is not included in the reported error.']
    if axis_ratio > 1.05:
        return ['Elliptical LED ring; directional spread may reflect geometry or droplet asymmetry.']
    return []


def detect_leds(gray: np.ndarray, pairs: int = 12,
                roi: tuple[int, int, int, int] | None = None,
                min_area: float = 12, max_area: float = 600) -> tuple[np.ndarray, dict]:
    """Segment distinct highlights at multiple thresholds and find a full ring.

    No missing spot is synthesized. Multiple distinct valid rings are rejected.
    The ellipse locates/validates spots only; it never replaces measured distances.
    """
    offset = np.zeros(2)
    if roi is not None:
        x, y, w, h = roi
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > gray.shape[1] or y+h > gray.shape[0]:
            raise ValueError("ROI must lie inside the original image: x y width height.")
        gray = gray[y:y+h, x:x+w]
        offset = np.array([x, y])
    candidates = []
    target = pairs * 2
    for threshold in [.65, .72, .80, .86, .91, .95]:
        _, _, stats, centroids = cv2.connectedComponentsWithStats((gray > threshold).astype(np.uint8))
        width, height, area = stats[:, 2], stats[:, 3], stats[:, 4]
        fill = area / np.maximum(width * height, 1)
        # Elongated reflections are expected for elliptical rings. Identify the
        # ring by its complete, evenly spaced, symmetric centroids, rather than
        # rejecting individual spots solely for their aspect ratio.
        keep = (area >= min_area) & (area <= max_area) & (fill > .35)
        keep[0] = False
        xy, area = centroids[keep], area[keep]
        if len(xy) < target:
            continue
        diam = 2 * np.sqrt(area / np.pi)
        # Sparse neighborhood graph avoids a quadratic matrix on textured images.
        tree = cKDTree(xy)
        # Wider neighborhoods also connect spots along an ellipse's long axis.
        edges = tree.query_pairs(4 * float(np.max(diam)), output_type='ndarray')
        if len(edges) == 0:
            continue
        distance = np.linalg.norm(xy[edges[:, 0]] - xy[edges[:, 1]], axis=1)
        scale = np.sqrt(diam[edges[:, 0]] * diam[edges[:, 1]])
        seen = set()
        for factor in [2, 2.5, 3, 3.5, 4]:
            e = edges[distance < factor * scale]
            graph = csr_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(xy), len(xy)))
            n, labels = connected_components(graph, directed=False)
            counts = np.bincount(labels)
            for label in np.flatnonzero(counts == target):
                idx = tuple(np.flatnonzero(labels == label))
                if idx in seen:
                    continue
                seen.add(idx)
                if np.max(area[list(idx)]) / np.min(area[list(idx)]) > 3:
                    continue
                try:
                    spots, quality = ring_geometry(xy[list(idx)] + offset)
                except ValueError:
                    continue
                quality['segmentation_threshold'] = threshold
                candidates.append((spots, quality))
    if not candidates:
        raise ValueError(f"Could not confidently detect all {target} LED spots. Check focus/exposure, "
                         "or specify --roi / --min-spot-area / --max-spot-area. No angle was estimated.")
    candidates.sort(key=lambda c: c[1]['score'])
    spots, quality = candidates[0]
    center = np.array([quality['center_x_px'], quality['center_y_px']])
    radius = min(quality['ellipse_diameters_px']) / 2
    for other, q in candidates[1:]:
        other_center = np.array([q['center_x_px'], q['center_y_px']])
        if np.linalg.norm(center - other_center) > .2 * radius or abs(
                np.mean(q['ellipse_diameters_px']) / np.mean(quality['ellipse_diameters_px']) - 1) > .2:
            raise ValueError("Multiple LED rings detected; select one using --roi x y width height.")
    quality['valid_threshold_detections'] = len(candidates)
    return spots, quality


def solve_pair(r: float, L: float, H_sub: float, volume: float) -> dict:
    """Solve the supplied MATLAB equations on the physical optical branch.

    Eliminating theta via the volume constraint lets us bracket alpha instead of
    accepting an unconstrained fsolve root. 0<alpha<45 degrees, 0<theta<180 degrees,
    alpha<=theta, and the apex must be below the LEDs.
    """
    if not all(math.isfinite(v) and v > 0 for v in [r, L, H_sub, volume]) or r >= L:
        raise ValueError("Solver requires positive finite inputs and r < L.")
    minimum_R = (3 * volume / (4 * math.pi)) ** (1 / 3)
    upper = min(math.pi / 4 - 1e-8, math.asin(min(1., r / minimum_R)) * (1 - 1e-10))

    def state(alpha):
        R = r / math.sin(alpha)
        target = 3 * volume / (math.pi * R**3)
        theta = brentq(lambda t: 4 * math.sin(t / 2)**4 * (2 + math.cos(t)) - target,
                       0, math.pi, xtol=1e-13)
        h = 2 * R * math.sin(theta / 2)**2
        return R, theta, h

    def residual(alpha):
        R, theta, h = state(alpha)
        return math.tan(2 * alpha) * (H_sub - h + r * math.tan(alpha / 2)) - (L - r)

    grid = np.linspace(1e-7, upper, 300)
    values = [residual(a) for a in grid]
    roots = []
    for a, b, fa, fb in zip(grid[:-1], grid[1:], values[:-1], values[1:]):
        if fa * fb <= 0:
            alpha = brentq(residual, a, b, xtol=1e-13)
            R, theta, h = state(alpha)
            if theta >= alpha and h < H_sub and all(abs(alpha - old[0]) > 1e-8 for old in roots):
                roots.append((alpha, R, theta, h))
    if len(roots) != 1:
        raise ValueError(f"Found {len(roots)} physical solutions; check volume, calibration, and geometry.")
    alpha, R, theta, h = roots[0]
    f1 = math.tan(2 * alpha) - (r - L) / (r * (math.cos(alpha)-1) / math.sin(alpha) - (H_sub-h))
    f2 = (1-math.cos(theta))**2 * (2+math.cos(theta)) - 3*volume/(math.pi*R**3)
    if max(abs(f1), abs(f2)) > 1e-8:
        raise ValueError("Solution failed the original MATLAB equation residual check.")
    return {'alpha_deg': math.degrees(alpha), 'R_mm': R,
            'theta_deg': math.degrees(theta), 'droplet_height_mm': h,
            'reflection_residual': f1, 'volume_residual': f2}


def analyze(path: Path, *, volume: float, zg: float | None = None,
            z_ref: float = 123.5, h_ref: float = 111.7, spacing: float = 59.5,
            mm_per_pixel: float = 6.35 / 909.85, pairs: int = 12,
            roi=None, min_area: float = 12, max_area: float = 600) -> tuple[dict, np.ndarray]:
    if pairs < 3:
        raise ValueError("At least three opposite pairs are required for ring detection.")
    if not all(math.isfinite(x) for x in [z_ref, h_ref]):
        raise ValueError("Calibration anchors must be finite.")
    if not all(math.isfinite(x) and x > 0 for x in [volume, spacing, mm_per_pixel, min_area, max_area]):
        raise ValueError("Volume, spacing, scale and spot areas must be positive and finite.")
    if max_area < min_area:
        raise ValueError("Maximum spot area must be >= minimum spot area.")
    zg = gantry_from_filename(path) if zg is None else zg
    H_sub = h_ref + (zg - z_ref)
    gray, display = read_image(path)
    spots, quality = detect_leds(gray, pairs, roi, min_area, max_area)
    rows = []
    for i in range(pairs):
        a, b = spots[i], spots[i+pairs]
        distance = float(np.linalg.norm(a-b))
        s = distance * mm_per_pixel
        row = {'pair': i+1, 'spot_a': i+1, 'spot_b': i+pairs+1,
               'x_a_px': float(a[0]), 'y_a_px': float(a[1]),
               'x_b_px': float(b[0]), 'y_b_px': float(b[1]),
               'separation_px': distance, 'separation_mm': s, 'r_mm': s/2}
        row.update(solve_pair(s/2, spacing/2, H_sub, volume))
        rows.append(row)
    angles = np.array([row['theta_deg'] for row in rows])
    warnings = ring_warnings(quality['ellipse_axis_ratio'])
    result = {'image': str(path.resolve()), 'image_width_px': gray.shape[1], 'image_height_px': gray.shape[0],
              'volume_ul': volume, 'volume_mm3': volume, 'Zg_mm': zg,
              'Z_ref_mm': z_ref, 'H_ref_mm': h_ref, 'H_sub_mm': H_sub,
              'led_opposite_spacing_mm': spacing, 'mm_per_pixel': mm_per_pixel,
              'detected_spots': len(spots), 'pair_count': pairs, 'quality': quality,
              'contact_angle_mean_deg': float(np.mean(angles)),
              'contact_angle_sample_std_deg': float(np.std(angles, ddof=1)),
              'contact_angle_min_deg': float(np.min(angles)),
              'contact_angle_max_deg': float(np.max(angles)), 'warnings': warnings, 'pairs': rows}
    return result, display


def save_result(result: dict, display: np.ndarray, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(result['image']).stem
    (out / f'{stem}_results.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    with (out / f'{stem}_pairs.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(result['pairs'][0]))
        writer.writeheader()
        writer.writerows(result['pairs'])
    # Enlarge a crop only for annotation. All measurements use original pixels.
    rows = result['pairs']
    points = np.array([[r[f'x_{end}_px'], r[f'y_{end}_px']] for r in rows for end in ['a', 'b']])
    x0, y0 = np.maximum(0, np.floor(points.min(0)-35)).astype(int)
    x1, y1 = np.minimum([display.shape[1], display.shape[0]], np.ceil(points.max(0)+35)).astype(int)
    scale = min(5., 1000 / max(x1-x0, y1-y0))
    crop = cv2.resize(display[y0:y1, x0:x1], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    for row in rows:
        hsv = np.uint8([[[int((row['pair']-1)*179/len(rows)), 240, 220]]])
        color = tuple(int(x) for x in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0])
        a, b = [tuple(np.rint((np.array([row[f'x_{e}_px'], row[f'y_{e}_px']])-[x0, y0])*scale).astype(int)) for e in ['a', 'b']]
        cv2.line(crop, a, b, color, 1, cv2.LINE_AA)
        for point in [a, b]:
            cv2.circle(crop, point, max(5, round(6*scale)), color, 2, cv2.LINE_AA)
            text_at = (point[0]+12, point[1]-12)
            cv2.putText(crop, str(row['pair']), text_at, cv2.FONT_HERSHEY_SIMPLEX, .6, (0,0,0), 4, cv2.LINE_AA)
            cv2.putText(crop, str(row['pair']), text_at, cv2.FONT_HERSHEY_SIMPLEX, .6, (255,255,255), 1, cv2.LINE_AA)
    crop = cv2.copyMakeBorder(crop, 65, 0, 0, 0, cv2.BORDER_CONSTANT, value=(25,25,25))
    caption = f"{result['contact_angle_mean_deg']:.3f} deg | SD {result['contact_angle_sample_std_deg']:.3f} deg | {len(rows)} pairs"
    cv2.putText(crop, caption, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, .65, (255,255,255), 1, cv2.LINE_AA)
    cv2.putText(crop, 'Matching numbers mark opposite LEDs. Crop enlarged for viewing.', (15, 51), cv2.FONT_HERSHEY_SIMPLEX, .45, (220,220,220), 1, cv2.LINE_AA)
    if not cv2.imwrite(str(out / f'{stem}_annotated.png'), crop):
        raise ValueError("Could not save annotated image.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('image', type=Path, help='Original single-frame TIFF, PNG, etc.')
    parser.add_argument('--volume', type=positive, help='User-supplied microliters (= mm^3); prompts if omitted.')
    parser.add_argument('--zg', type=float, help='Override gantry height; default: parse filename.')
    parser.add_argument('--z-ref', type=float, default=123.5)
    parser.add_argument('--h-ref', type=positive, default=111.7)
    parser.add_argument('--led-spacing', type=positive, default=59.5)
    parser.add_argument('--mm-per-pixel', type=positive, default=6.35/909.85)
    parser.add_argument('--pairs', type=int, default=12)
    parser.add_argument('--roi', type=int, nargs=4, metavar=('X','Y','WIDTH','HEIGHT'))
    parser.add_argument('--min-spot-area', type=positive, default=12, help='Original-image pixels; default 12.')
    parser.add_argument('--max-spot-area', type=positive, default=600, help='Original-image pixels; default 600.')
    parser.add_argument('--out', type=Path, default=Path('contact_angle_results'))
    args = parser.parse_args()
    try:
        volume = args.volume if args.volume is not None else positive(input('Droplet volume (uL = mm^3): '))
        result, display = analyze(args.image, volume=volume, zg=args.zg, z_ref=args.z_ref,
                                  h_ref=args.h_ref, spacing=args.led_spacing, mm_per_pixel=args.mm_per_pixel,
                                  pairs=args.pairs, roi=args.roi, min_area=args.min_spot_area, max_area=args.max_spot_area)
        save_result(result, display, args.out)
    except (ValueError, OSError, EOFError, argparse.ArgumentTypeError, cv2.error) as error:
        parser.exit(2, f'Error: {error}\n')
    print(f"Zg = {result['Zg_mm']:.3f} mm; LED-to-substrate height = {result['H_sub_mm']:.4f} mm")
    print(f"Volume = {volume:g} uL; {result['detected_spots']} spots / {result['pair_count']} opposite pairs")
    print('Pair    Separation (px)    Separation (mm)    Contact angle (deg)')
    for r in result['pairs']:
        print(f"{r['pair']:4d}    {r['separation_px']:15.4f}    {r['separation_mm']:15.6f}    {r['theta_deg']:19.4f}")
    print(f"Average contact angle = {result['contact_angle_mean_deg']:.3f} deg")
    print(f"Sample SD across pairs = {result['contact_angle_sample_std_deg']:.3f} deg")
    for warning in result['warnings']:
        print(f'Note: {warning}')
    print(f'Results saved in {args.out.resolve()}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Select the sharpest complete LED ring per well and export an Excel report.

Example: python3 batch_contact_angle.py /path/to/images --volume 10
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

import cv2
import numpy as np
from scipy.spatial import cKDTree

from .contact_angle import (analyze, detect_leds, gantry_from_filename, positive,
                           read_image, save_result, solve_pair, ring_warnings)


def image_metadata(path: Path) -> dict:
    match = re.search(r'(?:^|_)plate\.([A-Za-z]+\d+)(?=_)', path.name)
    if not match:
        raise ValueError('Missing plate.WELL field, for example plate.C4')
    brightness = re.search(r'_b(\d+(?:[.-]\d+)?)(?=_|\.)', path.name)
    return {'well': match[1].upper(), 'zg_mm': gantry_from_filename(path),
            'brightness_group': 'b'+brightness[1] if brightness else 'unspecified'}


def well_key(well: str):
    match = re.fullmatch(r'([A-Z]+)(\d+)', well)
    return (match[1], int(match[2])) if match else (well, 0)


def focus_metrics(gray: np.ndarray, spots: np.ndarray) -> dict:
    """Measure light spread around each LED; smaller spread means better focus.

    Each patch extends one neighboring-LED spacing. A Voronoi mask excludes
    pixels closer to another LED. Local background and two robust noise sigmas
    are subtracted before calculating the intensity-weighted second moment.
    The reciprocal median moment is the focus score (higher is sharper).
    Extended blur lobes are included, unlike a score of only the bright core.
    """
    tree = cKDTree(spots)
    separation = tree.query(spots, k=2)[0][:, 1]
    radius = max(5, int(np.floor(np.median(separation))))
    size = 2*radius+1
    yy, xx = np.mgrid[-radius:radius+1, -radius:radius+1]
    rr = np.hypot(xx, yy)
    gray = gray.astype(np.float32)
    moments, widths = [], []
    for index, (x, y) in enumerate(spots):
        if x-radius < 0 or y-radius < 0 or x+radius >= gray.shape[1] or y+radius >= gray.shape[0]:
            raise ValueError('LED focus patch touches the image boundary.')
        patch = cv2.getRectSubPix(gray, (size,size), (float(x),float(y)))
        nearest = tree.query(np.c_[xx.ravel()+x, yy.ravel()+y])[1].reshape(xx.shape)
        mask = (nearest==index) & (rr<radius)
        annulus = mask & (rr>.75*radius)
        background_pixels = patch[annulus]
        if len(background_pixels)<8:
            raise ValueError('Insufficient LED background pixels for focus comparison.')
        background = float(np.median(background_pixels))
        noise = 1.4826*float(np.median(np.abs(background_pixels-background)))
        weights = np.maximum(patch-background-2*noise,0)*mask
        contrast = float(np.max(weights))
        total = float(np.sum(weights))
        if contrast<=.03 or total<=0:
            raise ValueError('Insufficient local LED contrast for focus comparison.')
        cx, cy = float(np.sum(xx*weights)/total), float(np.sum(yy*weights)/total)
        moment = float(np.sum(((xx-cx)**2+(yy-cy)**2)*weights)/total)
        if moment<=0:
            raise ValueError('Degenerate LED profile for focus comparison.')
        moments.append(moment)
        widths.append(2*math.sqrt(float(np.count_nonzero((weights>=.5*contrast)&mask))/math.pi))
    score_values = 1/np.array(moments)
    return {'focus_score': 1/float(np.median(moments)),
            'focus_score_spot_iqr': float(np.percentile(score_values,75)-np.percentile(score_values,25)),
            'median_spot_spread_px': math.sqrt(float(np.median(moments))),
            'median_spot_halfmax_diameter_px': float(np.median(widths)),
            'focus_patch_radius_px': radius}


def height_error(result: dict, step_mm: float) -> dict:
    """Uniform +/-step/2 height error, shared across all 12 pairs.

    The selected image's pixel separations are held fixed. Thus this covers the
    geometric height contribution, not changes in centroid detection with defocus.
    Directional sample SD is retained as requested, without dividing by sqrt(12).
    """
    if not math.isfinite(step_mm) or step_mm <= 0:
        raise ValueError('Height step must be positive and finite.')
    half = step_mm/2
    means = []
    for delta in [-half, half]:
        angles = [solve_pair(p['r_mm'], result['led_opposite_spacing_mm']/2,
                             result['H_sub_mm']+delta, result['volume_mm3'])['theta_deg']
                  for p in result['pairs']]
        means.append(float(np.mean(angles)))
    sensitivity = (means[1]-means[0])/step_mm
    uz = step_mm/math.sqrt(12)
    height_u = abs(sensitivity)*uz
    directional = result['contact_angle_sample_std_deg']
    return {'height_step_mm': step_mm, 'height_half_interval_mm': half,
            'height_standard_uncertainty_mm': uz,
            'mean_angle_z_minus_halfstep_deg': means[0],
            'mean_angle_z_plus_halfstep_deg': means[1],
            'height_sensitivity_deg_per_mm': sensitivity,
            'height_angle_standard_uncertainty_deg': height_u,
            'combined_direction_height_deg': math.hypot(directional,height_u)}


def choose_images(candidates: list[dict], step_mm: float) -> list[dict]:
    """One selection per well. Retain failed wells and flag unbracketed focus."""
    groups = defaultdict(list)
    for row in candidates:
        if row.get('well'):
            groups[row['well']].append(row)
    selected = []
    for well, rows in sorted(groups.items(), key=lambda item:well_key(item[0])):
        valid = [r for r in rows if r['status']=='valid']
        if not valid:
            selected.append({'well':well,'status':'failed','warnings':['No image has a valid complete LED ring.'],
                             'candidate_count':len(rows),'valid_count':0})
            continue
        # Filename tie-break makes repeat runs deterministic.
        valid.sort(key=lambda r:(-r['focus_score'],r['filename']))
        best = dict(valid[0])
        best['candidate_count'],best['valid_count'] = len(rows),len(valid)
        flags = []
        zs = sorted(set(r['zg_mm'] for r in rows if r['brightness_group']==best['brightness_group']))
        pos = zs.index(best['zg_mm'])
        bracketed = 0 < pos < len(zs)-1
        best['focus_bracketed'] = bracketed
        if not bracketed:
            flags.append('Best available focus lies at scan boundary; extend the height scan. Half-step error is provisional.')
        else:
            neighbors = [zs[pos-1],zs[pos+1]]
            if any(not any(r['status']=='valid' and r['zg_mm']==z and
                           r['brightness_group']==best['brightness_group'] for r in rows) for z in neighbors):
                flags.append('An adjacent height failed detection; focus maximum needs review.')
            gaps = np.diff(zs)
            if not np.allclose(gaps,step_mm,atol=1e-5,rtol=0):
                flags.append('Observed height grid differs from requested step; half-step error is provisional.')
        distinct = [r for r in valid[1:] if r['zg_mm']!=best['zg_mm']]
        margin = (best['focus_score']-distinct[0]['focus_score'])/best['focus_score'] if distinct else None
        best['focus_margin_fraction'] = margin
        if margin is not None and margin < .03:
            flags.append('Another height has a focus score within 3%; selection is weakly separated.')
        flags.extend(ring_warnings(best['ellipse_axis_ratio']))
        best['warnings'] = flags
        best['status'] = 'review' if flags else 'selected'
        selected.append(best)
    return selected


def run_batch(folder: Path, output: Path, volume: float, step_mm: float=.2,
              *, spacing=59.5, mm_per_pixel=6.35/909.85, z_ref=123.5, h_ref=111.7,
              roi=None, min_area=12, max_area=600) -> dict:
    if not folder.is_dir():
        raise ValueError(f'Not an image folder: {folder}')
    if not math.isfinite(volume) or volume<=0 or not math.isfinite(step_mm) or step_mm<=0:
        raise ValueError('Volume and height step must be positive and finite.')
    paths = sorted(p for p in folder.iterdir() if p.is_file() and
                   p.suffix.lower() in {'.tif','.tiff','.png','.jpg','.jpeg','.bmp'})
    if not paths:
        raise ValueError('No supported image files found in the folder.')
    output.mkdir(parents=True,exist_ok=True)
    candidates = []
    for index,path in enumerate(paths,1):
        row = {'filename':path.name,'path':str(path.resolve()),'status':'rejected','reason':''}
        try:
            row.update(image_metadata(path))
            gray,_ = read_image(path)
            points,quality = detect_leds(gray,roi=roi,min_area=min_area,max_area=max_area)
            row.update(focus_metrics(gray,points))
            row.update({'ellipse_axis_ratio':quality['ellipse_axis_ratio'],
                        'detection_score':quality['score'],'status':'valid'})
        except (ValueError,OSError,cv2.error) as error:
            row['reason'] = str(error)
        candidates.append(row)
        if index%10==0 or index==len(paths):
            print(f'Focus scan: {index}/{len(paths)} images',flush=True)
    selections = choose_images(candidates,step_mm)
    if not selections:
        raise ValueError('No filenames contained a valid plate.WELL and gantry-height field.')
    for selected in selections:
        if selected['status']=='failed':
            continue
        try:
            result,display = analyze(Path(selected['path']),volume=volume,spacing=spacing,
                                     mm_per_pixel=mm_per_pixel,z_ref=z_ref,h_ref=h_ref,
                                     roi=roi,min_area=min_area,max_area=max_area)
            result['uncertainty'] = height_error(result,step_mm)
            selected['result'] = result
            selected['uncertainty'] = result['uncertainty']
            save_result(result,display,output/'selected_images')
            print(f"{selected['well']}: {Path(selected['path']).name} -> "
                  f"{result['contact_angle_mean_deg']:.3f} deg; combined "
                  f"{result['uncertainty']['combined_direction_height_deg']:.3f} deg",flush=True)
        except (ValueError,OSError,cv2.error) as error:
            selected['status']='failed'
            selected['warnings'].append(str(error))
    report = {'folder':str(folder.resolve()),'created_utc':datetime.now(timezone.utc).isoformat(),
              'volume_ul':volume,'height_step_mm':step_mm,'mm_per_pixel':mm_per_pixel,
              'led_spacing_mm':spacing,'z_ref_mm':z_ref,'h_ref_mm':h_ref,
              'image_count':len(paths),'selections':selections,'candidates':candidates,
              'uncertainty_model':'sqrt(directional_sample_sd^2 + (abs(dmean_angle/dZ)*step/sqrt(12))^2)',
              'uncertainty_scope':'Two-component dispersion/error estimate, k=1; not a confidence interval for the mean or full measurement uncertainty. '
              'Uniform unresolved focus height +/-half step, independent of directional variation. '
              'Distances fixed during height propagation. Excludes focus-induced centroid shifts, volume/calibration errors and model bias.'}
    (output/'batch_report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--volume',type=positive,help='Same user-supplied volume (uL) for all wells; prompts if omitted.')
    parser.add_argument('--height-step',type=positive,default=.2,help='Full height increment in mm; default 0.2.')
    parser.add_argument('--out',type=Path,help='Default: contact_angle_batch inside the image folder.')
    parser.add_argument('--led-spacing',type=positive,default=59.5)
    parser.add_argument('--mm-per-pixel',type=positive,default=6.35/909.85)
    parser.add_argument('--z-ref',type=float,default=123.5)
    parser.add_argument('--h-ref',type=positive,default=111.7)
    parser.add_argument('--roi',type=int,nargs=4)
    parser.add_argument('--min-spot-area',type=positive,default=12)
    parser.add_argument('--max-spot-area',type=positive,default=600)
    parser.add_argument('--json-only',action='store_true',help='Skip Excel export; useful for external report builders.')
    args=parser.parse_args()
    try:
        if not args.json_only:
            from .batch_excel import export_excel
        volume=args.volume if args.volume is not None else positive(input('Droplet volume for all wells (uL): '))
        output=args.out or args.folder/'contact_angle_batch'
        report=run_batch(args.folder,output,volume,args.height_step,spacing=args.led_spacing,
                         mm_per_pixel=args.mm_per_pixel,z_ref=args.z_ref,h_ref=args.h_ref,
                         roi=args.roi,min_area=args.min_spot_area,max_area=args.max_spot_area)
        if not args.json_only:
            export_excel(report,output/'contact_angles.xlsx')
        print(f'Saved results: {output.resolve()}')
    except (ValueError,OSError,EOFError,ImportError,argparse.ArgumentTypeError) as error:
        parser.exit(2,f'Error: {error}\n')


if __name__=='__main__':
    main()

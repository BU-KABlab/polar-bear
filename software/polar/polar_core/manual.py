"""Contact angles from user-marked opposite LED endpoints in original pixels."""
import math
import cv2
import numpy as np
from .contact_angle import solve_pair,ring_warnings
from .batch_contact_angle import height_error


def measure_manual(raw,width,height,settings,zg):
    try:segments=np.asarray(raw,dtype=float)
    except (ValueError,TypeError):raise ValueError('Provide endpoint coordinates for each LED pair.')
    if segments.ndim!=3 or segments.shape[1:]!=(2,2) or not 1<=len(segments)<=12:
        raise ValueError('Draw between 1 and 12 opposite LED pairs.')
    if not np.isfinite(segments).all():raise ValueError('Endpoints must be finite pixel coordinates.')
    if (segments<0).any() or (segments[:,:,0]>width-1).any() or (segments[:,:,1]>height-1).any():
        raise ValueError('All endpoints must lie inside the original image.')
    flat=segments.reshape(-1,2)
    distance=np.linalg.norm(flat[:,None]-flat[None,:],axis=2)
    np.fill_diagonal(distance,np.inf)
    if distance.min()<1:raise ValueError('Use distinct LED endpoints at least one pixel apart.')
    if settings['mode']=='outline' and len(segments)<2:
        raise ValueError('Draw at least two opposite pairs for outline analysis.')
    points=np.concatenate([segments[:,0],segments[:,1]])
    center=segments.mean(axis=(0,1))
    quality=dict(center_x_px=float(center[0]),center_y_px=float(center[1]),provisional=True,
                 detection_method='manual',ellipse_axis_ratio=None)
    if len(flat)>=6 and np.linalg.matrix_rank(flat-center)==2:
        try:
            (cx,cy),(d1,d2),angle=cv2.fitEllipse(flat.astype(np.float32))
            if np.isfinite([cx,cy,d1,d2,angle]).all() and min(d1,d2)>0:
                quality.update(ellipse_axis_ratio=float(max(d1,d2)/min(d1,d2)),
                               ellipse_diameters_px=[float(d1),float(d2)],ellipse_rotation_deg=float(angle))
        except cv2.error:pass
    warnings=['Manual LED endpoints; automatic ring validation was bypassed. Inspect the selected opposite pairs.',
              'Image/focus selected manually. Height-step contribution is provisional; endpoint-placement error is not included.']
    if len(segments)<12:warnings.append(f'Only {len(segments)} of 12 directions measured; directional coverage is incomplete.')
    if quality['ellipse_axis_ratio'] is not None:warnings+=ring_warnings(quality['ellipse_axis_ratio'])
    answer=dict(points=points.tolist(),manual_pairs=segments.tolist(),quality=quality,provisional=True,
                analysis_method='manual',manual_focus_selection=True,warnings=warnings,pairs=[],
                angle=None,error=None,directional_sd=None,height_error=None,focus_score=None,
                image_width=width,image_height=height,zg=zg)
    if settings['mode']=='outline':
        answer.update(status='outline_review',circles=[])
        return answer
    H=settings['h_ref']+(zg-settings['z_ref']);rows=[]
    for i,(a,b) in enumerate(segments):
        sep=float(np.linalg.norm(a-b));r=sep*settings['mm_per_pixel']/2
        rows.append(dict(pair=i+1,spot_a=i+1,spot_b=i+1+len(segments),x_a_px=float(a[0]),y_a_px=float(a[1]),
                         x_b_px=float(b[0]),y_b_px=float(b[1]),separation_px=sep,separation_mm=2*r,r_mm=r,
                         **solve_pair(r,settings['led_spacing']/2,H,settings['volume'])))
    angles=[p['theta_deg'] for p in rows]
    sd=float(np.std(angles,ddof=1)) if len(rows)>1 else None
    # Propagate height even for a single pair, but never present missing SD as zero.
    u=height_error(dict(pairs=rows,led_opposite_spacing_mm=settings['led_spacing'],H_sub_mm=H,
                        volume_mm3=settings['volume'],contact_angle_sample_std_deg=sd or 0.),settings['height_step'])
    if sd is None:
        u['combined_direction_height_deg']=None
        warnings.append('One pair: directional SD and combined error are unavailable.')
    answer.update(angle=float(np.mean(angles)),error=u['combined_direction_height_deg'],directional_sd=sd,
                  height_error=u['height_angle_standard_uncertainty_deg'],uncertainty=u,pairs=rows,status='review',
                  supplied_volume=settings['volume'],H_sub_mm=H)
    return answer

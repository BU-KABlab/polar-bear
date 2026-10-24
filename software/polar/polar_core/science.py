"""POLAR spherical-cap geometry and OWRK calculations, all lengths in mm."""
import math
from collections import defaultdict

import cv2
import numpy as np
from scipy.optimize import brentq, least_squares, minimize_scalar, nnls

from .contact_angle import read_image

LIQUID_SOURCE = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC6105199/'
LIQUIDS = [dict(name=n,dispersive=d,polar=p,total=d+p,source=LIQUID_SOURCE,
                temperature_note='Literature starting values; verify at your measurement temperature.')
           for n,d,p in [('Water',21.8,51.),('Diiodomethane',50.8,0.),
                         ('Ethylene glycol',29.,19.),('Formamide',39.,19.),('Glycerol',34.,30.)]]


def finite(value,name,minimum=None,maximum=None):
    try: x=float(value)
    except (ValueError,TypeError): raise ValueError(f'{name} must be a number.')
    if not math.isfinite(x) or (minimum is not None and x<minimum) or (maximum is not None and x>maximum):
        raise ValueError(f'{name} is outside the supported range.')
    return x


def cap(R,theta,alpha):
    h=R*(1-math.cos(theta))
    return {'theta_deg':math.degrees(theta),'R_mm':R,'alpha_deg':math.degrees(alpha),
            'height_mm':h,'contact_radius_mm':R*math.sin(theta),
            'volume_ul':math.pi*h*h*(3*R-h)/3}


def solve_outline(r,b,L,H,branch='below',boundary='silhouette'):
    """Our inversion of the user's reflection model; not an independently validated method."""
    for value in (r,b,L,H): finite(value,'Geometry',1e-9)
    if r>=L or b<=r: raise ValueError('The outline must enclose the LED reflections, and r must be smaller than L.')
    if branch not in ('below','above') or boundary not in ('silhouette','contact'):
        raise ValueError('Choose a valid angle branch and boundary type.')
    if branch=='above' and boundary=='silhouette':
        R=b
        if R<=math.sqrt(2)*r: raise ValueError('Outline is incompatible with the reflection geometry.')
        alpha=math.asin(r/R)
        cosine=math.cos(alpha)-(H-(L-r)/math.tan(2*alpha))/R
        if not -1<cosine<0:
            raise ValueError('Outline and LEDs do not give an above-90-degree spherical cap. Check boundary and calibration.')
        return cap(R,math.acos(cosine),alpha)
    limit=math.asin(min(1.,b/(math.sqrt(2)*r)))-1e-8
    lo,hi=(1e-5,limit) if branch=='below' else (math.pi-limit,math.pi-1e-5)
    def f(theta):
        R=b/math.sin(theta)
        alpha=math.asin(r/R)
        return R*(math.cos(alpha)-math.cos(theta))+(L-r)/math.tan(2*alpha)-H
    # Below 90 the height function has an interior minimum and can have two roots.
    # Split at that minimum so near-tangent roots are not lost on a coarse grid.
    bounds=[lo,hi]
    if branch=='below':
        minimum=minimize_scalar(f,bounds=(lo,hi),method='bounded',options={'xatol':1e-13})
        bounds=[lo,float(minimum.x),hi]
    roots=[]
    for a,z in zip(bounds[:-1],bounds[1:]):
        if f(a)*f(z)<0:
            root=brentq(f,a,z,xtol=1e-12)
            if all(abs(root-v)>1e-7 for v in roots): roots.append(root)
    if len(roots)!=1:
        raise ValueError('Ambiguous outline: multiple physical angles are possible. Supply an independent volume.' if roots else
                         'No physical solution for this outline and angle branch. Check the selected boundary.')
    theta=roots[0];R=b/math.sin(theta);alpha=math.asin(r/R)
    if alpha>theta or alpha>=math.pi/4: raise ValueError('Reflections lie outside the modeled cap.')
    return cap(R,theta,alpha)


def fit_circle(points):
    pts=np.array(points,dtype=float)
    if pts.ndim!=2 or pts.shape[1]!=2 or not 3<=len(pts)<=10000 or not np.isfinite(pts).all():
        raise ValueError('Select at least three finite boundary points.')
    center=pts.mean(axis=0)
    if np.linalg.matrix_rank(pts-center)<2: raise ValueError('Boundary points are collinear.')
    fit=least_squares(lambda x:np.linalg.norm(pts-x[:2],axis=1)-x[2],
                      [*center,np.linalg.norm(pts-center,axis=1).mean()],loss='soft_l1')
    x,y,r=fit.x
    if r<=0: raise ValueError('Invalid circle radius.')
    residual=np.linalg.norm(pts-[x,y],axis=1)-r
    angles=np.sort(np.mod(np.arctan2(pts[:,1]-y,pts[:,0]-x),2*np.pi))
    gap=np.diff(np.r_[angles,angles[0]+2*np.pi]).max()
    return {'cx':float(x),'cy':float(y),'radius_px':float(r),
            'relative_rms':float(np.sqrt(np.mean(residual**2))/r),
            'angular_coverage_deg':float(360-math.degrees(gap)),'points':len(pts)}


def propose_circles(path,center,led_radius):
    """Contour proposals only. Every outline must be reviewed and confirmed."""
    gray,_=read_image(path)
    scale=min(1.,900/max(gray.shape))
    a=cv2.resize((gray*255).astype(np.uint8),None,fx=scale,fy=scale)
    blurred=cv2.GaussianBlur(a,(5,5),1.2)
    candidates=[]
    for low,high in [(15,40),(30,80),(50,120)]:
        edges=cv2.Canny(blurred,low,high)
        contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            if len(contour)<80: continue
            pts=contour[:,0,:].astype(float)/scale
            try: circle=fit_circle(pts[::max(1,len(pts)//500)])
            except ValueError: continue
            r=circle['radius_px'];x=circle['cx'];y=circle['cy']
            if not led_radius*1.8<r<min(gray.shape)*.6: continue
            if np.linalg.norm(np.array([x,y])-center)>.35*r: continue
            if circle['relative_rms']>.06 or circle['angular_coverage_deg']<230: continue
            if x-r<0 or y-r<0 or x+r>=gray.shape[1] or y+r>=gray.shape[0]: continue
            if any(abs(c['radius_px']-r)<.08*r and np.hypot(c['cx']-x,c['cy']-y)<.08*r for c in candidates): continue
            candidates.append(circle)
    return sorted(candidates,key=lambda c:c['relative_rms'])[:5]


def outline_result(points,circle,settings,step):
    radius=circle['radius_px']*settings['mm_per_pixel']
    rows=[];half=len(points)//2
    for i in range(half):
        r=float(np.linalg.norm(points[i]-points[i+half]))*settings['mm_per_pixel']/2
        p=solve_outline(r,radius,settings['led_spacing']/2,settings['height'],settings['branch'],settings['boundary'])
        p.update(pair=i+1,r_mm=r,separation_px=2*r/settings['mm_per_pixel'])
        rows.append(p)
    angles=[p['theta_deg'] for p in rows]
    sd=float(np.std(angles,ddof=1))
    warnings=['Experimental spherical-cap estimate. Outline localization and model errors are not included.']
    try:
        endpoints=[]
        for offset in [-step/2,step/2]:
            endpoints.append(float(np.mean([solve_outline(p['r_mm'],radius,settings['led_spacing']/2,
                settings['height']+offset,settings['branch'],settings['boundary'])['theta_deg'] for p in rows])))
        hu=abs(endpoints[1]-endpoints[0])/math.sqrt(12)
        error=math.hypot(sd,hu)
    except ValueError:
        hu=None;error=None
        warnings.append('A height perturbation changes the valid branch. Symmetric error is unavailable.')
    return {'angle':float(np.mean(angles)),'directional_sd':sd,'height_error':hu,'error':error,
            'estimated_volume':float(np.mean([p['volume_ul'] for p in rows])),
            'volume_directional_sd':float(np.std([p['volume_ul'] for p in rows],ddof=1)),
            'contact_radius_mm':float(np.mean([p['contact_radius_mm'] for p in rows])),
            'pairs':rows,'warnings':warnings,'circle':circle}


def _owrk_draw_fits(X, ys):
    """Exact two-variable NNLS for a batch of nonnegative response vectors."""
    coefficients=ys@np.linalg.pinv(X).T
    invalid=np.any(coefficients<0,axis=1)
    if np.any(invalid):
        y=ys[invalid];x=X[:,1]
        b=np.maximum(y.mean(axis=1),0)
        m=np.maximum(y@x/(x@x),0)
        use_b=np.sum((y-b[:,None])**2,axis=1)<=np.sum((y-m[:,None]*x)**2,axis=1)
        coefficients[invalid]=np.c_[np.where(use_b,b,0),np.where(use_b,0,m)]
    return coefficients


def _owrk_uncertainty(data,X):
    """Conditional propagation of angular spreads, not a complete uncertainty budget."""
    count=20000;rng=np.random.default_rng(20260929)
    ys=[]
    for point in data:
        angle=point['angle'];error=point['angle_error']
        if error==0:
            angles=np.full(count,angle)
        else:
            mean=angle/180;variance=(error/180)**2
            concentration=mean*(1-mean)/variance-1
            angles=180*rng.beta(mean*concentration,(1-mean)*concentration,count)
        values=(point['dispersive']+point['polar'])*(1+np.cos(np.deg2rad(angles)))/(2*np.sqrt(point['dispersive']))
        point['y_error']=float(np.std(values,ddof=1)) if error else 0.
        ys.append(values)
    coefs=_owrk_draw_fits(X,np.array(ys).T)
    energies=coefs**2
    totals=energies.sum(axis=1)
    exact=all(p['angle_error']==0 for p in data)
    errors={key:0. if exact else float(np.std(values,ddof=1)) for key,values in
            [('dispersive',energies[:,0]),('polar',energies[:,1]),('total',totals)]}
    grid=np.linspace(0,float(max(p['x'] for p in data))*1.1,61)
    fitted=coefs[:,0,None]+coefs[:,1,None]*grid
    low,high=np.quantile(fitted,[.16,.84],axis=0)
    return dict(errors=errors,samples=count,seed=20260929,
                component_covariance=0. if exact else float(np.cov(energies.T,ddof=1)[0,1]),
                boundary_fraction=float(np.mean(np.any(coefs<=1e-12,axis=1))),
                band=[dict(x=float(x),low=float(a),high=float(b)) for x,a,b in zip(grid,low,high)],
                band_description='Pointwise 16th–84th percentiles of propagated fits; not a prediction interval.',
                distribution='Independent bounded beta distributions per liquid, matching angle mean and input spread on 0–180 degrees.',
                replicate_policy='Mean angle and RMS input error per liquid; errors are not divided by sqrt(n). Replicate scatter is not added.',
                scope='Propagated angle-error estimate (one SD). Liquid-property, omitted calibration and model uncertainties are excluded; cross-liquid errors are assumed independent.')


def owrk(rows,substrate,convention,temperature):
    if not str(substrate).strip(): raise ValueError('Name the substrate/preparation being analyzed.')
    if convention not in ('static','advancing','receding','apparent'): raise ValueError('Choose an angle convention.')
    temperature=finite(temperature,'Measurement temperature',-20,150)
    if not isinstance(rows,list) or not 3<=len(rows)<=200: raise ValueError('Enter measurements from at least three distinct liquids.')
    groups=defaultdict(list)
    for row in rows:
        name=str(row.get('liquid','')).strip()
        if not name: raise ValueError('Every measurement needs a liquid name.')
        if row.get('substrate',substrate).strip().casefold()!=substrate.strip().casefold():
            raise ValueError('All liquids must be measured on the same substrate preparation.')
        if row.get('convention',convention)!=convention: raise ValueError('Do not mix static, advancing and receding measurements.')
        theta=finite(row.get('angle'),'Contact angle',.001,179.999)
        gd=finite(row.get('dispersive'),'Dispersive liquid tension',.001,1000)
        gp=finite(row.get('polar'),'Polar liquid tension',0,1000)
        if row.get('total') is not None and abs(finite(row['total'],'Total tension')-gd-gp)>.05:
            raise ValueError('Liquid total surface tension must equal its polar plus dispersive components.')
        raw_error=row.get('angle_error')
        error=None if raw_error is None or raw_error=='' else finite(raw_error,'Angle error',0)
        if error is not None and error*error>=theta*(180-theta):
            raise ValueError('Angle error is too large for a distribution bounded by 0 and 180 degrees.')
        groups[name.casefold()].append(dict(liquid=name,angle=theta,angle_error=error,
            error_kind=str(row.get('error_kind','user_supplied')),dispersive=gd,polar=gp,source=str(row.get('source','User supplied'))))
    if len(groups)<3: raise ValueError('Three different liquids are required; replicate drops do not count as different liquids.')
    errors=[p['angle_error'] for group in groups.values() for p in group]
    supplied=any(e is not None for e in errors)
    if supplied and any(e is None for e in errors):
        raise ValueError('Enter an angle error for every included measurement, or leave all errors blank for a fit without propagated errors. Blank is not zero.')
    data=[]
    for group in groups.values():
        gd=group[0]['dispersive'];gp=group[0]['polar']
        if any(abs(p['dispersive']-gd)>1e-6 or abs(p['polar']-gp)>1e-6 for p in group):
            raise ValueError('Replicates of the same liquid have inconsistent surface-tension values.')
        angle=float(np.mean([p['angle'] for p in group]));x=math.sqrt(gp/gd)
        y=(gd+gp)*(1+math.cos(math.radians(angle)))/(2*math.sqrt(gd))
        error=math.sqrt(np.mean([p['angle_error']**2 for p in group])) if supplied else None
        data.append(dict(group[0],angle=angle,angle_error=error,n=len(group),x=x,y=y,
                         error_kinds=sorted({p['error_kind'] for p in group})))
    X=np.c_[np.ones(len(data)),[p['x'] for p in data]];y=np.array([p['y'] for p in data])
    condition=float(np.linalg.cond(X))
    if np.ptp(X[:,1])<.05 or condition>1000: raise ValueError('The liquids have insufficient polar/dispersive contrast for a stable OWRK fit.')
    unconstrained=np.linalg.lstsq(X,y,rcond=None)[0]
    coef,_=nnls(X,y);b,m=coef
    prediction=X@coef;residual=y-prediction
    sst=float(np.sum((y-y.mean())**2));sse=float(np.sum(residual**2))
    warnings=[]
    if np.min(unconstrained)<-1e-8: warnings.append('Unconstrained fit had a negative component. Nonnegative boundary fit shown; review model compatibility.')
    if convention!='static': warnings.append('This is a convention-specific apparent surface-energy estimate, not an equilibrium determination.')
    for i,p in enumerate(data): p.update(predicted=float(prediction[i]),residual=float(residual[i]))
    uncertainty=_owrk_uncertainty(data,X) if supplied else None
    if uncertainty:
        if uncertainty['boundary_fraction']>.01:
            warnings.append('Some propagated fits reach a zero component. The distribution is asymmetric; ± error is an SD, not a symmetric confidence interval.')
        if any('polar_spread' in p['error_kinds'] for p in data):
            warnings.append('Imported POLAR errors combine directional spread and height error. Propagation does not turn them into uncertainties in mean contact angles.')
        if any(p['n']>1 for p in data):
            warnings.append('Replicates use the mean angle and RMS entered error without a sqrt(n) reduction. Between-drop scatter is not added; supply an independently justified mean-angle error if needed.')
    return {'substrate':substrate,'convention':convention,'temperature_c':temperature,
            'total':float(b*b+m*m),'dispersive':float(b*b),'polar':float(m*m),
            'intercept':float(b),'slope':float(m),'r_squared':1-sse/sst if sst>1e-12 else None,
            'rmse':math.sqrt(sse/len(data)),'condition_number':condition,'liquid_count':len(data),
            'data':data,'warnings':warnings,'units':'mJ/m²','uncertainty':uncertainty,
            'method':'Equal weight per liquid, replicate angles averaged; nonnegative OWRK fit. Temperature is recorded only; no automatic temperature correction is applied. '+
                ('20,000 repeated fits propagate entered angle spreads; reported errors are one SD, not 95% intervals.' if supplied else
                 'No angle errors supplied; propagated errors are unavailable.')}

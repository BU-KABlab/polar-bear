import math
import numpy as np
import pytest
from polar_core.science import solve_outline,fit_circle,owrk,LIQUIDS,outline_result

def geometry(theta):
    R=3.;alpha=math.radians(7);t=math.radians(theta);r=R*math.sin(alpha)
    H=R*(math.cos(alpha)-math.cos(t))+(29.75-r)/math.tan(2*alpha)
    return r,R*math.sin(t),H,R

@pytest.mark.parametrize('theta,branch,boundary',[(40,'below','silhouette'),(60,'below','contact'),(120,'above','silhouette'),(140,'above','contact')])
def test_outline_forward_inverse(theta,branch,boundary):
    r,b,H,R=geometry(theta)
    out=solve_outline(r,R if branch=='above' and boundary=='silhouette' else b,29.75,H,branch,boundary)
    assert out['theta_deg']==pytest.approx(theta,abs=1e-7)
    assert out['R_mm']==pytest.approx(R)
    h=R*(1-math.cos(math.radians(theta)))
    assert out['volume_ul']==pytest.approx(math.pi*h*h*(3*R-h)/3)

def test_ambiguous_two_roots_rejected():
    with pytest.raises(ValueError,match='multiple physical'):
        solve_outline(.4,3,29.75,110.05931382141456,'below','contact')

def test_impossible_above_branch():
    r,b,H,R=geometry(40)
    with pytest.raises(ValueError):solve_outline(r,R,29.75,H,'above','silhouette')

def test_circle_with_noise():
    a=np.linspace(0,2*np.pi,100,endpoint=False);rng=np.random.default_rng(12)
    pts=np.c_[100+50*np.cos(a),120+50*np.sin(a)]+rng.normal(0,.1,(100,2))
    c=fit_circle(pts)
    assert c['radius_px']==pytest.approx(50,abs=.1)
    assert c['relative_rms']<.005 and c['angular_coverage_deg']>350
    with pytest.raises(ValueError):fit_circle([[0,0],[1,1],[2,2]])

def rows_for_energy(d=22,p=7):
    rows=[]
    for liquid in LIQUIDS[:3]:
        gd,gp=liquid['dispersive'],liquid['polar']
        cost=2*(math.sqrt(d*gd)+math.sqrt(p*gp))/(gd+gp)-1
        rows.append(dict(liquid=liquid['name'],dispersive=gd,polar=gp,angle=math.degrees(math.acos(cost))))
    return rows

def test_owrk_recovers_known_surface():
    out=owrk(rows_for_energy(),'PAMA','static',20)
    assert out['dispersive']==pytest.approx(22)
    assert out['polar']==pytest.approx(7)
    assert out['total']==pytest.approx(29)
    assert out['r_squared']==pytest.approx(1)

@pytest.mark.parametrize('case',['same_liquids','same_polarity','mixed_substrate','mixed_convention','nan'])
def test_owrk_rejects_invalid(case):
    rows=rows_for_energy()
    if case=='same_liquids': rows=rows[:1]*3
    if case=='same_polarity':
        for row in rows:row.update(dispersive=30,polar=0)
    if case=='mixed_substrate':rows[0]['substrate']='Another material'
    if case=='mixed_convention':rows[0]['convention']='advancing'
    if case=='nan':rows[0]['angle']=float('nan')
    with pytest.raises(ValueError):owrk(rows,'PAMA','static',20)

def test_height_propagated_for_unknown_volume():
    r,b,H,R=geometry(120);a=np.arange(24)*2*np.pi/24;scale=.01
    points=np.c_[r*np.cos(a)/scale,r*np.sin(a)/scale]
    out=outline_result(points,dict(radius_px=R/scale),dict(mm_per_pixel=scale,led_spacing=59.5,height=H,branch='above',boundary='silhouette'),.2)
    expected=math.degrees(1/(R*math.sin(math.radians(120))))*.2/math.sqrt(12)
    assert out['height_error']==pytest.approx(expected,rel=.002)
    assert out['directional_sd']<1e-10

def test_height_interval_crossing_branch_does_not_report_false_error():
    r,b,H,R=geometry(90.01);a=np.arange(24)*2*np.pi/24;scale=.01
    points=np.c_[r*np.cos(a)/scale,r*np.sin(a)/scale]
    out=outline_result(points,dict(radius_px=R/scale),dict(mm_per_pixel=scale,led_spacing=59.5,height=H,branch='above',boundary='silhouette'),.2)
    assert out['angle']==pytest.approx(90.01)
    assert out['error'] is None and out['height_error'] is None

def test_owrk_negative_fit_flagged_not_squared():
    rows=rows_for_energy()
    for row,angle in zip(rows,[150,30,120]):row['angle']=angle
    out=owrk(rows,'Sample','static',20)
    assert out['polar']==0
    assert any('negative' in w for w in out['warnings'])

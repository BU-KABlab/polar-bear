import math
from pathlib import Path
import unittest

import cv2
import numpy as np

from polar_core.batch_contact_angle import choose_images, focus_metrics, height_error, image_metadata
from polar_core.contact_angle import solve_pair


class BatchTests(unittest.TestCase):
    def test_metadata(self):
        m=image_metadata(Path('camera_305_ursa_plate.C12_z=59-300mm_b25_test.tiff'))
        self.assertEqual(m,{'well':'C12','zg_mm':59.3,'brightness_group':'b25'})
        with self.assertRaises(ValueError):
            image_metadata(Path('no_well_z=59-300mm.tiff'))

    def test_focus_blur_and_exposure(self):
        yy,xx=np.mgrid[:360,:360]
        angles=np.arange(24)*math.pi/12
        spots=np.c_[180+90*np.cos(angles),180+90*np.sin(angles)]
        image=np.full(xx.shape,.15,dtype=np.float32)
        for x,y in spots:
            image+=.7*np.exp(-((xx-x)**2+(yy-y)**2)/(2*2.3**2))
        scores=[focus_metrics(cv2.GaussianBlur(image,(0,0),sigma),spots)['focus_score'] for sigma in [.1,1,2,3]]
        self.assertTrue(all(a>b for a,b in zip(scores,scores[1:])))
        score=focus_metrics(image,spots)['focus_score']
        rescaled=focus_metrics(image*.6+.1,spots)['focus_score']
        self.assertAlmostEqual(score,rescaled,places=5)

    def test_broad_lobes_reduce_focus(self):
        yy,xx=np.mgrid[:360,:360]
        angles=np.arange(24)*math.pi/12
        spots=np.c_[180+90*np.cos(angles),180+90*np.sin(angles)]
        clean=np.full(xx.shape,.15,dtype=np.float32)
        blurred=clean.copy()
        for x,y in spots:
            clean+=.7*np.exp(-((xx-x)**2+(yy-y)**2)/(2*2.3**2))
            blurred+=.35*np.exp(-((xx-x)**2+(yy-y)**2)/(2*2.3**2))
            blurred+=.2*np.exp(-((xx-x-3)**2+(yy-y-3)**2)/(2*4**2))
        self.assertGreater(focus_metrics(clean,spots)['focus_score'],focus_metrics(blurred,spots)['focus_score'])

    def test_height_uncertainty(self):
        rows=[{'r_mm':r,'theta_deg':solve_pair(r,29.75,110.2,10)['theta_deg']} for r in [.4,.42,.44,.46]]
        result={'pairs':rows,'led_opposite_spacing_mm':59.5,'H_sub_mm':110.2,'volume_mm3':10,
                'contact_angle_sample_std_deg':float(np.std([r['theta_deg'] for r in rows],ddof=1))}
        u=height_error(result,.2)
        self.assertAlmostEqual(u['height_standard_uncertainty_mm'],.1/math.sqrt(3))
        self.assertAlmostEqual(u['combined_direction_height_deg']**2,
                               result['contact_angle_sample_std_deg']**2+u['height_angle_standard_uncertainty_deg']**2)
        fine=height_error(result,.02)
        self.assertAlmostEqual(u['height_angle_standard_uncertainty_deg']/fine['height_angle_standard_uncertainty_deg'],10,places=3)
        with self.assertRaises(ValueError): height_error(result,-1)

    def test_selection_boundary_missing_and_tie(self):
        def row(well,z,score,status='valid'):
            return {'well':well,'zg_mm':z,'focus_score':score,'filename':f'{well}_{z}',
                    'status':status,'brightness_group':'b25','ellipse_axis_ratio':1.}
        rows=[row('C1',59.3,1),row('C1',59.5,2),row('C1',59.7,1),
              row('C2',59.3,3),row('C2',59.5,2),row('C3',59.3,0,'rejected')]
        a,b,c=choose_images(rows,.2)
        self.assertEqual(a['zg_mm'],59.5); self.assertEqual(a['status'],'selected')
        self.assertTrue(any('boundary' in s for s in b['warnings']))
        self.assertEqual(c['status'],'failed')
        rows[0]['focus_score']=1.99
        a=choose_images(rows,.2)[0]
        self.assertTrue(any('within 3%' in s for s in a['warnings']))

    def test_nonuniform_grid_flag(self):
        rows=[{'well':'C1','zg_mm':z,'focus_score':score,'filename':str(z),'status':'valid',
               'brightness_group':'b25','ellipse_axis_ratio':1.} for z,score in [(59.,1),(59.4,2),(59.8,1)]]
        s=choose_images(rows,.2)[0]
        self.assertTrue(any('differs' in v for v in s['warnings']))


if __name__=='__main__':
    unittest.main()

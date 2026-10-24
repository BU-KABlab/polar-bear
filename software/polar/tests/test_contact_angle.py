"""Run with: python3 -m unittest discover -s outputs -p 'test_*.py' -v"""
import math
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import brentq, root

from polar_core.contact_angle import analyze, detect_leds, gantry_from_filename, read_image, solve_pair


def synthetic(centers=((170, 175),), missing=None, noise=0.):
    yy, xx = np.mgrid[:360, :700]
    image = np.full(xx.shape, .18)
    expected = []
    for cx, cy in centers:
        for i in range(24):
            if i == missing:
                continue
            t = i*math.pi/12 + .13
            x, y = cx+64*math.cos(t), cy+70*math.sin(t)
            expected.append((x, y))
            image += .8*np.exp(-((xx-x)**2+(yy-y)**2)/(2*3.2**2))
    image += np.random.default_rng(2026).normal(0, noise, image.shape)
    return np.clip(image, 0, 1).astype(np.float32), np.array(expected)


class SolverTests(unittest.TestCase):
    def test_filename(self):
        for token in ['59-300', '59.300', '+59-300']:
            self.assertEqual(gantry_from_filename(f'camera_z={token}mm_b25.tiff'), 59.3)
        self.assertEqual(gantry_from_filename('camera_z=-1-250mm.tiff'), -1.25)
        with self.assertRaises(ValueError):
            gantry_from_filename('camera_20260903.tiff')

    def test_original_equations(self):
        for px in [106.001, 111.011, 125.2041, 139.2378]:
            r = px*6.35/909.85/2
            def original(x):
                a, t = x
                R = r / np.sin(a)
                h = R*(1-np.cos(t))
                return [np.tan(2*a)-(r-29.75)/(r*(np.cos(a)-1)/np.sin(a)-(109.8-h)),
                        (1-np.cos(t))**2*(2+np.cos(t))-30/(np.pi*R**3)]
            old = root(original, np.deg2rad([5,60]))
            new = solve_pair(r, 29.75, 109.8, 10)
            self.assertTrue(old.success)
            self.assertAlmostEqual(new['theta_deg'], np.rad2deg(old.x[1]), places=6)

    def test_known_forward_geometries(self):
        for volume in [2., 10., 25.]:
            for degrees in [25., 60., 100., 145.]:
                theta = math.radians(degrees)
                R = (3*volume/(math.pi*(1-math.cos(theta))**2*(2+math.cos(theta))))**(1/3)
                h = R*(1-math.cos(theta))
                alpha = brentq(lambda a: math.tan(2*a)*(109.8-h+R*(1-math.cos(a)))
                               -(29.75-R*math.sin(a)), 1e-7, math.pi/4-1e-7)
                result = solve_pair(R*math.sin(alpha), 29.75, 109.8, volume)
                self.assertAlmostEqual(result['theta_deg'], degrees, places=6)

    def test_bad_physical_inputs(self):
        for inputs in [(0,29.75,109.8,10),(.5,29.75,109.8,-10),(30,29.75,109.8,10),
                       (.5,29.75,float('nan'),10)]:
            with self.assertRaises(ValueError):
                solve_pair(*inputs)


class ImageTests(unittest.TestCase):
    def test_elongated_spots_and_elliptical_ring_are_measured(self):
        image, truth = synthetic(noise=.002)
        # Stretch both the ring and each reflection, as in campaign 22.
        image = cv2.resize(image, None, fx=2., fy=1., interpolation=cv2.INTER_LINEAR)
        truth[:, 0] = 2*truth[:, 0]+.5
        points, quality = detect_leds(image)
        self.assertGreater(quality['ellipse_axis_ratio'], 1.5)
        self.assertTrue(quality['provisional'])
        self.assertEqual(len(points), 24)
        errors = np.linalg.norm(points[:,None]-truth[None,:],axis=2).min(axis=1)
        self.assertLess(float(errors.max()),1.)
        # The long direction remains long; no ellipse circularization.
        measured = np.linalg.norm(points[:12]-points[12:],axis=1)
        self.assertGreater(float(measured.max()/measured.min()),1.7)

    def test_elongated_missing_spot_still_rejected(self):
        image,_ = synthetic(missing=7)
        image=cv2.resize(image,None,fx=2.,fy=1.)
        with self.assertRaisesRegex(ValueError,'all 24'):
            detect_leds(image)

    def test_detection_and_original_coordinate_roi(self):
        image, truth = synthetic(noise=.01)
        points, _ = detect_leds(image, roi=(70,65,210,220))
        self.assertEqual(len(points), 24)
        errors = np.linalg.norm(points[:,None]-truth[None,:], axis=2).min(axis=1)
        self.assertLess(float(errors.max()), .5)
        distances = np.linalg.norm(points[:12]-points[12:], axis=1)
        self.assertGreater(float(distances.min()), 127)
        self.assertLess(float(distances.max()), 141)

    def test_missing_spot_rejected(self):
        image, _ = synthetic(missing=7)
        with self.assertRaisesRegex(ValueError, 'all 24'):
            detect_leds(image)

    def test_multiple_rings_rejected(self):
        image, _ = synthetic(centers=((170,175),(500,175)))
        with self.assertRaisesRegex(ValueError, 'Multiple LED rings'):
            detect_leds(image)

    def test_blank_rejected(self):
        with self.assertRaises(ValueError):
            detect_leds(np.zeros((300,300),np.float32))

    def test_16bit_tiff_end_to_end(self):
        image, _ = synthetic(noise=.002)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'synthetic_z=59-300mm_test.tiff'
            cv2.imwrite(str(path), (image*65535).astype(np.uint16))
            gray, display = read_image(path)
            self.assertEqual(gray.shape, image.shape)
            result, _ = analyze(path, volume=10, z_ref=59.7, h_ref=110.2)
            self.assertEqual(result['pair_count'],12)
            self.assertEqual(result['Zg_mm'],59.3)
            self.assertAlmostEqual(result['H_sub_mm'],109.8)
            self.assertTrue(40 < result['contact_angle_mean_deg'] < 50)
            with self.assertRaises(ValueError):
                analyze(path, volume=0)


if __name__ == '__main__':
    unittest.main()

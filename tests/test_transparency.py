import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6 import QtWidgets

from colors import rgb
from demo import demo_project
from main import MainWindow
from model import Project, Store
import rendering


class TransparencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.color = (65, 105, 165)
        self.path = self.folder / 'background.png'
        Image.new('RGB', (100, 100), self.color).save(self.path)

    def test_background_transparency_endpoints_and_middle(self):
        project = Project()
        project.style['bg_common'] = str(self.path)
        palette_color = rgb(rendering.PALETTES['Светлый']['bg'])
        for percent in (0, 50, 100):
            with self.subTest(percent=percent):
                project.style['bg_transparency'] = percent
                image, _ = rendering.canvas(project, 'post', (100, 100))
                expected = Image.blend(Image.new('RGB', (1, 1), self.color),
                                       Image.new('RGB', (1, 1), palette_color), 1 - percent / 100)
                self.assertEqual(image.getpixel((50, 50)), expected.getpixel((0, 0)))

    def test_transparent_source_keeps_theme_color_under_transparent_pixels(self):
        project = Project()
        source = self.folder / 'transparent.png'
        Image.new('RGBA', (100, 100)).save(source)
        project.style.update(bg_common=str(source), bg_transparency=100)
        image, _ = rendering.canvas(project, 'post', (100, 100))
        self.assertEqual(image.getpixel((50, 50)), rgb(rendering.PALETTES['Светлый']['bg']))

    def test_day_panels_can_be_opaque_partial_or_completely_transparent(self):
        project = Project(days=['Понедельник'], times=['09:00'])
        project.style.update(bg_common=str(self.path), bg_transparency=100)
        original = rendering.cell_blocks
        samples = []
        for percent in (0, 50, 100):
            sample = []
            def capture(values, x, y, width, height, gap):
                sample.append((round(x + 15), round(y + height / 2)))
                return original(values, x, y, width, height, gap)
            project.style['panel_transparency'] = percent
            with patch.object(rendering, 'cell_blocks', side_effect=capture):
                image = rendering.render(project, 'post')[0]
            samples.append(image.getpixel(sample[0]))
        self.assertEqual(samples[0], rgb(rendering.PALETTES['Светлый']['card']))
        self.assertEqual(samples[2], self.color)
        for full, middle, clear in zip(*samples):
            self.assertGreaterEqual(middle, min(full, clear))
            self.assertLessEqual(middle, max(full, clear))
        self.assertNotEqual(samples[1], samples[0])
        self.assertNotEqual(samples[1], samples[2])

    def test_training_cards_stay_opaque_with_transparent_background_panels(self):
        project = demo_project()
        project.style.update(bg_common=str(self.path), bg_transparency=100, panel_transparency=100)
        original = rendering.cell_blocks
        for variant in rendering.FORMATS:
            samples = []
            def capture(*args):
                blocks = original(*args)
                samples.extend(blocks)
                return blocks
            with self.subTest(variant=variant), patch.object(rendering, 'cell_blocks', side_effect=capture):
                image = rendering.render(project, variant)[0]
                self.assertTrue(samples)
                for block in samples:
                    x0, y0, x1, y1 = block['box']
                    point = (round((x0 + x1) / 2), round(y0 + 4))
                    self.assertEqual(image.getpixel(point), rgb(project.halls[block['hall']]['color']))

    def test_old_or_invalid_percentages_fall_back_and_new_values_roundtrip(self):
        data = Project().to_dict()
        del data['style']['bg_transparency']
        del data['style']['panel_transparency']
        restored = Project.from_dict(data)
        self.assertEqual(restored.style['bg_transparency'], 8)
        self.assertEqual(restored.style['panel_transparency'], 0)
        for invalid in (None, True, -1, 101, '70', 50.5):
            data['style'].update(bg_transparency=invalid, panel_transparency=invalid)
            restored = Project.from_dict(data)
            self.assertEqual(restored.style['bg_transparency'], 8)
            self.assertEqual(restored.style['panel_transparency'], 0)
        restored.style.update(bg_transparency=85, panel_transparency=55)
        store = Store(self.folder)
        store.save(restored)
        saved, _ = store.load()
        self.assertEqual(saved.style['bg_transparency'], 85)
        self.assertEqual(saved.style['panel_transparency'], 55)

    def test_ui_slider_spin_undo_redo_and_save(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        store = Store(self.folder)
        window = MainWindow(store, start_preview=False)
        try:
            window.transparency_sliders['bg_transparency'].setValue(85)
            window.transparency_spins['panel_transparency'].setValue(55)
            self.assertEqual(window.project.style['bg_transparency'], 85)
            self.assertEqual(window.project.style['panel_transparency'], 55)
            self.assertEqual(window.transparency_spins['bg_transparency'].value(), 85)
            self.assertEqual(window.transparency_sliders['panel_transparency'].value(), 55)
            window.undo()
            self.assertEqual(window.transparency_sliders['panel_transparency'].value(), 0)
            window.redo()
            self.assertEqual(window.transparency_spins['panel_transparency'].value(), 55)
            self.assertTrue(window.save(quiet=True))
            saved, _ = store.load()
            self.assertEqual(saved.style['bg_transparency'], 85)
            self.assertEqual(saved.style['panel_transparency'], 55)
        finally:
            window.autosave.stop()
            window.preview_timer.stop()
            window.deleteLater()


if __name__ == '__main__':
    unittest.main()

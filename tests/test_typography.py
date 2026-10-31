import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageChops

from demo import demo_project
import rendering


class TypographyTests(unittest.TestCase):
    def test_visible_text_is_centered_for_single_and_multiple_lines(self):
        for size in (14, 32, 64):
            for lines in (['Круговая'], ['Гибкость и', 'сила'], ['Йога', 'растяжка'], ['gyp', 'Body sculpt']):
                with self.subTest(size=size, lines=lines):
                    image = Image.new('L', (820, 300), 255)
                    box = (10, 10, 810, 290)
                    rendering.centered_text(ImageDraw.Draw(image), lines, box,
                                            rendering.font(size), 0, round(size * 1.24))
                    ink = ImageChops.invert(image).getbbox()
                    self.assertIsNotNone(ink)
                    self.assertAlmostEqual((ink[0] + ink[2]) / 2, 410, delta=1.5)
                    self.assertAlmostEqual((ink[1] + ink[3]) / 2, 150, delta=1.5)
                    self.assertGreaterEqual(ink[1], box[1])
                    self.assertLessEqual(ink[3], box[3])

    def test_logo_is_large_on_left_and_does_not_overlap_header_text(self):
        with tempfile.TemporaryDirectory() as directory:
            # A deliberately small mark inside a much larger transparent canvas.
            path = Path(directory) / 'padded.png'
            logo = Image.new('RGBA', (800, 600))
            ImageDraw.Draw(logo).rectangle((375, 275, 425, 325), fill=(250, 0, 85, 255))
            logo.save(path)
            project = demo_project()
            project.style['logo_path'] = str(path)
            for width, scale in ((1080, .86), (3508, 3508 / 1080 * .52)):
                with self.subTest(width=width):
                    image = Image.new('RGB', (width, 1200), '#F4F2F8')
                    drawn = []
                    original = rendering.text_lines
                    def capture(draw, lines, x, y, face, fill, line_height, anchor='lt'):
                        drawn.extend(draw.textbbox((x, y + index * line_height), text,
                                                   font=face, anchor=anchor) for index, text in enumerate(lines))
                        return original(draw, lines, x, y, face, fill, line_height, anchor)
                    with patch.object(rendering, 'text_lines', side_effect=capture):
                        bottom = rendering.header(image, project, rendering.PALETTES['Светлый'], scale)
                    channels = image.split()
                    mask = channels[0].point(lambda value: 255 if value == 250 else 0)
                    mask = ImageChops.multiply(mask, channels[1].point(lambda value: 255 if value == 0 else 0))
                    mask = ImageChops.multiply(mask, channels[2].point(lambda value: 255 if value == 85 else 0))
                    bounds = mask.getbbox()
                    self.assertIsNotNone(bounds)
                    self.assertGreaterEqual(bounds[2] - bounds[0], round(155 * scale))
                    self.assertLess(bounds[0], width * .1)
                    self.assertLess(bounds[3], bottom)
                    self.assertTrue(all(box[0] > bounds[2] + 10 * scale for box in drawn))

    def test_transparent_logo_reports_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'transparent.png'
            Image.new('RGBA', (100, 100)).save(path)
            project = demo_project()
            project.style['logo_path'] = str(path)
            with self.assertRaisesRegex(ValueError, 'полностью прозрачный'):
                rendering.render(project, 'post')

    def test_training_font_has_cyrillic_and_medium_weight(self):
        face = rendering.font(32)
        self.assertIn('Manrope', face.getname()[0])
        for name in ('Здоровая спина', 'Ягодицы и пресс', 'Флекс растяжка'):
            self.assertIsNotNone(face.getmask(name).getbbox())


if __name__ == '__main__':
    unittest.main()

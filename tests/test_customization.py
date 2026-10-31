import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6 import QtCore, QtGui, QtWidgets

from colors import text_color, rgb
from demo import demo_project
from main import MainWindow, RenderJob
from model import Project, Store, HALLS, atomic_json, read_json
import rendering


class CustomizationModelTests(unittest.TestCase):
    def test_old_v2_project_is_migrated_without_changing_assignments(self):
        project = demo_project()
        old = project.to_dict()
        old['version'] = 2
        for key in ('halls', 'formats', 'enabled_formats'):
            del old[key]
        del old['style']['studio_name']
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            atomic_json(store.path, old)
            restored, _ = store.load()
            self.assertEqual(restored.schedule, Project.from_dict(project.to_dict()).schedule)
            self.assertEqual(restored.hall_ids, HALLS)
            self.assertEqual(restored.style['studio_name'], 'Богини')
            store.save(restored)
            self.assertEqual(read_json(store.backup), old)
            self.assertEqual(store.load()[0].to_dict(), restored.to_dict())

    def test_renaming_recoloring_and_deleting_hall_keeps_other_halls(self):
        project = demo_project()
        third = project.add_hall('Йога', '#122449')
        project.set('Воскресенье', '18:30', third, 'Степ')
        project.update_hall(third, 'Студия йоги', '#000000')
        project.rename('Степ', 'Новый степ')
        self.assertEqual(project.get('Воскресенье', '18:30', third), 'Новый степ')
        self.assertEqual(project.hall(third)['color'], '#000000')
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.to_dict(), project.to_dict())
        expected = restored.get('Понедельник', '18:30', HALLS[1])
        restored.remove_hall(third)
        self.assertEqual(restored.get('Понедельник', '18:30', HALLS[1]), expected)
        self.assertEqual(restored.get('Воскресенье', '18:30', third), '')
        restored.remove_hall(HALLS[1])
        with self.assertRaises(ValueError):
            restored.remove_hall(HALLS[0])

    def test_invalid_halls_and_formats_are_rejected(self):
        project = Project()
        for name, color in [('', '#123456'), ('Другой', 'red'), ('Зелёный зал', '#123456')]:
            with self.subTest(name=name, color=color), self.assertRaises(ValueError):
                project.add_hall(name, color)
        for dimensions in [(0, 1200, 96), (8000, 8000, 300), (1080, 1080, 0), (True, 1080, 96)]:
            with self.subTest(dimensions=dimensions), self.assertRaises(ValueError):
                project.add_format('Некорректный', *dimensions)
        data = project.to_dict()
        data['formats'][0]['id'] = '../../escape'
        with self.assertRaises(ValueError):
            Project.from_dict(data)

    def test_custom_format_and_export_selection_roundtrip(self):
        project = demo_project()
        key = project.add_format('Квадрат', 1400, 1400, 180)
        project.enabled_formats = ['post', key]
        project.style['studio_name'] = 'Новая студия'
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.enabled_formats, ['post', key])
        self.assertEqual(restored.format(key)['dpi'], 180)
        self.assertEqual(restored.style['studio_name'], 'Новая студия')

    def test_text_contrast_for_extreme_and_saturated_colors(self):
        self.assertEqual(text_color('#000000'), '#FFFFFF')
        self.assertEqual(text_color('#FFFFFF'), '#000000')
        for value in ('#FF0000', '#0000FF', '#00FF00', '#765191', '#777777'):
            def luminance(color):
                values = [c / 255 for c in rgb(color)]
                values = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in values]
                return sum(a * b for a, b in zip(values, (.2126, .7152, .0722)))
            levels = sorted((luminance(value), luminance(text_color(value))))
            self.assertGreaterEqual((levels[1] + .05) / (levels[0] + .05), 4.5)


class CustomRenderingTests(unittest.TestCase):
    def test_three_halls_use_equal_blocks_and_custom_colors(self):
        project = Project(days=['Понедельник'], times=['09:00'], trainings=['А', 'Б', 'В'])
        third = project.add_hall('Третий зал', '#0011AA')
        project.update_hall(HALLS[0], 'Первый', '#000000')
        project.update_hall(HALLS[1], 'Второй', '#FFFFFF')
        for hall, name in zip(project.hall_ids, project.trainings):
            project.set('Понедельник', '09:00', hall, name)
        original = rendering.cell_blocks
        for variant in rendering.FORMATS:
            boxes = []
            def capture(*args):
                result = original(*args)
                boxes.extend(result)
                return result
            with self.subTest(variant=variant), patch.object(rendering, 'cell_blocks', side_effect=capture):
                image = rendering.render(project, variant)[0]
                self.assertEqual(len(boxes), 3)
                heights = [b['box'][3] - b['box'][1] for b in boxes]
                for height in heights:
                    self.assertAlmostEqual(height, heights[0])
                for block, hall in zip(boxes, project.halls):
                    x0, y0, x1, y1 = block['box']
                    pixel = image.getpixel((round((x0 + x1) / 2), round(y0 + 4)))
                    self.assertEqual(pixel, rgb(hall['color']))

    def test_square_and_landscape_custom_sizes_and_dpi(self):
        project = demo_project()
        with tempfile.TemporaryDirectory() as directory:
            for name, width, height in [('Квадрат', 1200, 1200), ('Экран', 1920, 1080)]:
                key = project.add_format(name, width, height, 180)
                images = rendering.render(project, key)
                self.assertEqual(len(images), 1)
                paths = rendering.save_images(images, directory, key, 'PNG', project.format(key)['dpi'])
                with Image.open(paths[0]) as image:
                    self.assertEqual(image.size, (width, height))
                    self.assertAlmostEqual(image.info['dpi'][0], 180, delta=1)

    def test_brand_uses_studio_name_in_export(self):
        project = demo_project()
        project.style['studio_name'] = 'Моя студия'
        drawn = []
        original = rendering.text_lines
        def capture(draw, lines, *args):
            drawn.extend(lines)
            return original(draw, lines, *args)
        with patch.object(rendering, 'text_lines', side_effect=capture):
            rendering.render(project, 'post')
        self.assertTrue(any('МОЯ СТУДИЯ' in text for text in drawn))
        self.assertFalse(any('БОГИНИ /' in text for text in drawn))


class CustomWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.store.save(demo_project())
        self.window = MainWindow(self.store, start_preview=False)
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        self.window.autosave.stop()
        self.window.preview_timer.stop()
        self.window.deleteLater()

    def test_studio_name_updates_title_and_persists(self):
        self.window.change_style('studio_name', 'Студия «Луна»')
        self.assertIn('Студия «Луна»', self.window.windowTitle())
        self.assertIn('ЛУНА', self.window.brand_label.text())
        self.assertTrue(self.window.save(quiet=True))
        self.assertEqual(self.store.load()[0].style['studio_name'], 'Студия «Луна»')

    def test_add_hall_dialog_editor_assignment_undo_and_save(self):
        def fill():
            dialog = self.app.activeModalWidget()
            dialog.findChild(QtWidgets.QLineEdit).setText('Третий зал')
            dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok).click()
        QtCore.QTimer.singleShot(0, fill)
        self.window.edit_hall(new=True)
        third = self.window.project.hall_ids[-1]
        combo = self.window.cell_combos[('Понедельник', '09:00', third)]
        combo.setCurrentIndex(combo.findData('Степ'))
        self.assertEqual(self.window.project.get('Понедельник', '09:00', third), 'Степ')
        self.window.undo()
        self.assertEqual(self.window.project.get('Понедельник', '09:00', third), '')
        self.window.redo()
        self.assertTrue(self.window.save(quiet=True))
        self.assertEqual(self.store.load()[0].get('Понедельник', '09:00', third), 'Степ')

    def test_custom_format_dialog_and_selective_export(self):
        def fill():
            dialog = self.app.activeModalWidget()
            dialog.findChild(QtWidgets.QLineEdit).setText('Мой квадрат')
            for spin, value in zip(dialog.findChildren(QtWidgets.QSpinBox), (1200, 1200, 180)):
                spin.setValue(value)
            dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok).click()
        QtCore.QTimer.singleShot(0, fill)
        self.window.edit_format(new=True)
        key = self.window.project.formats[-1]['id']
        self.assertGreaterEqual(self.window.format_combo.findData(key), 0)
        def choose():
            dialog = self.app.activeModalWidget()
            for checkbox in dialog.findChildren(QtWidgets.QCheckBox):
                checkbox.setChecked('Мой квадрат' in checkbox.text())
            dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok).click()
        QtCore.QTimer.singleShot(0, choose)
        with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=self.temp.name), \
             patch.object(self.window, 'start_render') as export:
            self.window.export_dialog()
        export.assert_called_once_with([key], self.temp.name, 'PNG')
        self.assertEqual(self.window.project.enabled_formats, [key])

    def test_export_worker_writes_only_selected_formats(self):
        project = demo_project()
        key = project.add_format('Квадрат', 1200, 1200, 180)
        results, errors = [], []
        job = RenderJob(project, ['post', key], self.temp.name)
        job.succeeded.connect(results.append)
        job.failed.connect(errors.append)
        job.run()
        self.assertEqual(errors, [])
        self.assertEqual(set(results[0][0]), {'post', key})
        self.assertEqual(len(results[0][1]), 2)
        self.assertFalse((Path(self.temp.name) / 'bogini_story.png').exists())
        self.assertFalse((Path(self.temp.name) / 'bogini_a4.png').exists())

    def test_dark_system_palette_does_not_make_ui_unreadable(self):
        previous = QtGui.QPalette(self.app.palette())
        dark = QtGui.QPalette()
        for role in (QtGui.QPalette.Window, QtGui.QPalette.Base, QtGui.QPalette.Button):
            dark.setColor(role, QtGui.QColor('#101010'))
        for role in (QtGui.QPalette.WindowText, QtGui.QPalette.Text, QtGui.QPalette.ButtonText):
            dark.setColor(role, QtGui.QColor('#EEEEEE'))
        self.app.setPalette(dark)
        extra = MainWindow(self.store, start_preview=False)
        try:
            extra.show()
            self.app.processEvents()
            self.assertGreater(extra.tabs.widget(2).widget().palette().color(QtGui.QPalette.Window).lightness(), 200)
            combo = next(iter(extra.cell_combos.values()))
            combo.showPopup()
            self.app.processEvents()
            self.assertGreater(combo.view().palette().color(QtGui.QPalette.Base).lightness(), 200)
            self.assertLess(combo.view().palette().color(QtGui.QPalette.Text).lightness(), 100)
            combo.hidePopup()
            menu = extra.menuBar().actions()[0].menu()
            menu.ensurePolished()
            self.assertLess(menu.palette().color(QtGui.QPalette.Text).lightness(), 100)
        finally:
            extra.autosave.stop()
            extra.preview_timer.stop()
            extra.hide()
            extra.deleteLater()
            self.app.setPalette(previous)


if __name__ == '__main__':
    unittest.main()

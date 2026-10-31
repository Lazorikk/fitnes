import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from PySide6 import QtCore, QtGui, QtWidgets

import model
import rendering
from model import Project, Store, HALLS, ALL_DAYS, atomic_json
from demo import demo_project
from main import MainWindow, RenderJob


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_both_halls_roundtrip_and_rename(self):
        project = demo_project()
        day, time = 'Понедельник', '18:30'
        self.assertEqual(project.get(day, time, HALLS[0]), 'Степ')
        self.assertEqual(project.get(day, time, HALLS[1]), 'Ягодицы и пресс')
        project.rename('Степ', 'Степ + кардио')
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.get(day, time, HALLS[0]), 'Степ + кардио')
        self.assertEqual(restored.get(day, time, HALLS[1]), 'Ягодицы и пресс')
        restored.remove_training('Ягодицы и пресс')
        self.assertEqual(restored.get(day, time, HALLS[1]), '')
        self.assertEqual(restored.get(day, time, HALLS[0]), 'Степ + кардио')

    def test_atomic_failure_preserves_previous_file(self):
        path = self.root / 'project.json'
        atomic_json(path, {'old': 'Занятия'})
        with patch.object(model.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                atomic_json(path, {'new': True})
        self.assertEqual(model.read_json(path), {'old': 'Занятия'})
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_backup_recovery_does_not_replace_good_backup_with_corruption(self):
        store = Store(self.root)
        first = demo_project()
        store.save(first)
        second = copy.deepcopy(first)
        second.style['title'] = 'Новая неделя'
        store.save(second)
        store.path.write_text('{bad json', encoding='utf-8')
        restored, notice = store.load()
        self.assertTrue(notice)
        self.assertEqual(restored.to_dict(), first.to_dict())
        store.save(restored)
        self.assertEqual(model.read_json(store.backup), first.to_dict())
        self.assertEqual(store.load()[0].to_dict(), first.to_dict())

    def test_invalid_project_is_rejected(self):
        for value in ([], {}, {**Project().to_dict(), 'days': []},
                      {**Project().to_dict(), 'times': ['24:00']},
                      {**Project().to_dict(), 'schedule': {'Понедельник': {'09:00': {'Другой зал': 'Йога'}}}}):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Project.from_dict(value)

    def test_legacy_migration_keeps_halls_hidden_days_and_original_files(self):
        settings = {'days': ['Понедельник'], 'times': ['18:30'], 'title': 'Старое расписание'}
        schedule = {'Понедельник': {'18:30': {HALLS[0]: 'Степ', HALLS[1]: 'Растяжка'}},
                    'Воскресенье': {'19:30': {HALLS[1]: 'Йога'}}}
        atomic_json(self.root / 'settings.json', settings)
        atomic_json(self.root / 'trainings.json', [{'name': 'Степ'}, {'name': 'Растяжка'}])
        atomic_json(self.root / 'schedule.json', schedule)
        project, message = Store(self.root).load()
        self.assertTrue(message)
        self.assertEqual(project.get('Понедельник', '18:30', HALLS[1]), 'Растяжка')
        self.assertEqual(project.get('Воскресенье', '19:30', HALLS[1]), 'Йога')
        self.assertIn('Йога', project.trainings)
        Store(self.root).save(project)
        self.assertEqual(model.read_json(self.root / 'schedule.json'), schedule)


class RenderingTests(unittest.TestCase):
    def test_single_hall_fills_entire_row_and_two_halls_split_it(self):
        project = demo_project()
        original = rendering.cell_blocks
        for variant in rendering.FORMATS:
            counts = [0, 0]
            def capture(values, x, y, width, height, gap):
                blocks = original(values, x, y, width, height, gap)
                if len(blocks) == 1:
                    counts[0] += 1
                    self.assertAlmostEqual(blocks[0]['box'][1], y + gap / 2)
                    self.assertAlmostEqual(blocks[0]['box'][3], y + height - gap / 2)
                    self.assertAlmostEqual(blocks[0]['box'][3] - blocks[0]['box'][1], height - gap)
                    self.assertEqual(blocks[0]['hall'], 0 if values[0] else 1)
                elif len(blocks) == 2:
                    counts[1] += 1
                    first, second = [block['box'] for block in blocks]
                    self.assertAlmostEqual(first[3] - first[1], second[3] - second[1])
                    self.assertAlmostEqual(second[1] - first[3], gap)
                    self.assertEqual([block['hall'] for block in blocks], [0, 1])
                return blocks
            with self.subTest(variant=variant), patch.object(rendering, 'cell_blocks', side_effect=capture):
                self.assertEqual(len(rendering.render(project, variant)), 1)
                self.assertGreater(counts[0], 0)
                self.assertGreater(counts[1], 0)

    def test_export_dimensions_and_a4_dpi(self):
        with tempfile.TemporaryDirectory() as directory:
            for variant in rendering.FORMATS:
                images = rendering.render(demo_project(), variant)
                self.assertTrue(images)
                for kind in ('PNG', 'JPEG'):
                    paths = rendering.save_images(images, directory, variant, kind)
                    self.assertEqual(len(paths), len(images))
                    for path in paths:
                        with Image.open(path) as image:
                            self.assertEqual(image.size, rendering.FORMATS[variant][1])
                            self.assertEqual(image.format, kind)
                            if variant == 'a4':
                                self.assertAlmostEqual(image.info['dpi'][0], 300, delta=1)

    def test_all_formats_have_one_shared_time_row_and_two_aligned_halls(self):
        project = demo_project()
        names = []
        for day_index, day in enumerate(project.days):
            for time_index, time in enumerate(project.times):
                for hall_index, hall in enumerate(HALLS):
                    name = f'К{day_index}{time_index}{hall_index}'
                    names.append(name)
                    project.set(day, time, hall, name)
        original = rendering.text_lines
        for variant in rendering.FORMATS:
            seen, positions = [], {}
            def capture(draw, lines, x, y, *args, **kwargs):
                for line in lines:
                    if line in names:
                        seen.append(line)
                        # Baselines vary with glyph ascenders/descenders; compare ink centers.
                        face = args[0]
                        anchor = args[3] if len(args) > 3 else 'lt'
                        ink = draw.textbbox((x, y), line, font=face, anchor=anchor)
                        positions[line] = ((ink[0] + ink[2]) / 2, (ink[1] + ink[3]) / 2)
                return original(draw, lines, x, y, *args, **kwargs)
            with self.subTest(variant=variant), patch.object(rendering, 'text_lines', side_effect=capture):
                images = rendering.render(project, variant)
                self.assertEqual(len(images), 1)
                self.assertCountEqual(seen, names)
                for time_index in range(len(project.times)):
                    # All days share two hall baselines inside a single time row.
                    upper = positions[f'К0{time_index}0'][1]
                    lower = positions[f'К0{time_index}1'][1]
                    self.assertLess(upper, lower)
                    for day_index in range(len(project.days)):
                        self.assertAlmostEqual(positions[f'К{day_index}{time_index}0'][1], upper, delta=1)
                        self.assertAlmostEqual(positions[f'К{day_index}{time_index}1'][1], lower, delta=1)

    def test_export_all_is_exactly_three_files(self):
        with tempfile.TemporaryDirectory() as directory:
            for variant in rendering.FORMATS:
                rendering.save_images(rendering.render(demo_project(), variant), directory, variant)
            self.assertEqual({path.name for path in Path(directory).iterdir()},
                             {'bogini_story.png', 'bogini_vk_post.png', 'bogini_a4.png'})

    def test_impossible_density_reports_error_instead_of_extra_pages(self):
        project = Project(times=[f'{hour:02}:{minute:02}' for hour in range(24) for minute in (0, 30)])
        for variant in rendering.FORMATS:
            with self.subTest(variant=variant), self.assertRaisesRegex(ValueError, 'Дополнительные страницы не создаются'):
                rendering.render(project, variant)

    def test_wrap_preserves_long_names_without_overflow(self):
        draw = ImageDraw.Draw(Image.new('RGB', (10, 10)))
        face = rendering.font(24, bold=True)
        for text in ('Очень длинное название тренировки для двух разных залов', 'Сверхдлинноесловобезпробелов' * 4):
            lines = rendering.wrap(draw, text, face, 180)
            self.assertEqual(''.join(''.join(lines).split()), ''.join(text.split()))
            self.assertTrue(all(draw.textlength(line, font=face) <= 180 for line in lines))

    def test_dark_palette_logo_and_background(self):
        with tempfile.TemporaryDirectory() as folder:
            asset = Path(folder) / 'logo.png'
            Image.new('RGBA', (100, 80), '#AF88DD').save(asset)
            project = demo_project()
            project.style.update(palette='Тёмный', logo_path=str(asset), bg_common=str(asset))
            images = rendering.render(project, 'story')
            self.assertEqual(images[0].mode, 'RGB')
            self.assertLess(images[0].getpixel((0, 0))[0], 80)

    def test_missing_asset_reports_filename(self):
        project = demo_project()
        project.style['logo_path'] = '/missing/logo.png'
        with self.assertRaisesRegex(ValueError, 'logo.png'):
            rendering.render(project, 'story')


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setOrganizationName(model.APP_ORG)
        cls.app.setApplicationName(model.APP_ID)

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

    def test_assign_both_halls_undo_redo_and_reload(self):
        day, time = 'Вторник', '09:00'
        self.window.cell_combos[(day, time, HALLS[0])].setCurrentIndex(
            self.window.cell_combos[(day, time, HALLS[0])].findData('Степ'))
        self.window.cell_combos[(day, time, HALLS[1])].setCurrentIndex(
            self.window.cell_combos[(day, time, HALLS[1])].findData('Флекс растяжка'))
        self.window.undo()
        self.assertEqual(self.window.project.get(day, time, HALLS[1]), '')
        self.assertEqual(self.window.project.get(day, time, HALLS[0]), 'Степ')
        self.window.redo()
        self.assertTrue(self.window.save(quiet=True))
        restored, _ = self.store.load()
        self.assertEqual(restored.get(day, time, HALLS[0]), 'Степ')
        self.assertEqual(restored.get(day, time, HALLS[1]), 'Флекс растяжка')

    def test_hide_day_keeps_assignments(self):
        expected = copy.deepcopy(self.window.project.schedule['Понедельник'])
        self.window.day_checks['Понедельник'].setChecked(False)
        self.assertNotIn('Понедельник', self.window.project.days)
        self.window.day_checks['Понедельник'].setChecked(True)
        self.assertEqual(self.window.project.schedule['Понедельник'], expected)

    def test_add_delete_time_and_undo(self):
        self.window.time_input.setTime(QtCore.QTime(21, 15))
        self.window.add_time()
        self.assertIn('21:15', self.window.project.times)
        self.window.table.selectRow(self.window.project.times.index('21:15'))
        with patch.object(self.window, 'confirm', return_value=True):
            self.window.delete_time()
        self.assertNotIn('21:15', self.window.project.times)
        self.window.undo()
        self.assertIn('21:15', self.window.project.times)

    def test_failed_save_does_not_close_without_permission(self):
        self.window.change_style('title', 'Изменено')
        event = QtGui.QCloseEvent()
        with patch.object(self.store, 'save', side_effect=OSError('disk full')), \
             patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Cancel):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertEqual(self.window.state_label.text(), 'Не удалось сохранить')

    def test_autosave_runs_after_edit(self):
        self.window.change_style('title', 'Новая неделя')
        from PySide6.QtTest import QTest
        QTest.qWait(1050)
        self.window.preview_timer.stop()
        self.assertEqual(self.store.load()[0].style['title'], 'Новая неделя')

    def test_background_preview_worker_completes(self):
        from PySide6.QtTest import QTest
        self.window.refresh_preview()
        for _ in range(200):
            if self.window.job is None:
                break
            QTest.qWait(20)
        self.assertIsNone(self.window.job)
        self.assertTrue(self.window.images)
        self.assertEqual(self.window.page_label.text(), 'Вся неделя · одна картинка')
        self.assertTrue(self.window.export_btn.isEnabled())


if __name__ == '__main__':
    unittest.main()

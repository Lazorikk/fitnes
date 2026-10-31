"""Month repetition, direct editing and photo-background contrast regressions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6 import QtCore, QtWidgets as Q
from colors import rgb
from model import ALL_DAYS, Project, Store
from main import MainWindow
import rendering

DAY = ALL_DAYS[0]


def simple_project():
    p = Project(trainings=['Йога', 'Растяжка'], times=['18:00', '19:00'])
    p.halls = p.halls[:1]
    p.set(DAY, '18:00', p.hall_ids[0], 'Йога')
    p.set_detail(DAY, '18:00', p.hall_ids[0], 'Анна', 60)
    return p


class MonthTests(unittest.TestCase):
    def test_month_repeats_without_week_dates_and_restores_independently(self):
        p = simple_project()
        h = p.hall_ids[0]
        p.switch_month('2026-11-18')
        self.assertEqual(p.active_month, '2026-11-01')
        self.assertEqual(p.day_title(DAY), DAY)
        self.assertIn('01.11.2026 — 30.11.2026', p.period_text())
        self.assertIn('каждую неделю', p.publication_text())
        p.set(DAY, '18:00', h, 'Растяжка')
        p.switch_month('2026-12-01')
        self.assertEqual(p.get(DAY, '18:00', h), 'Йога')
        p.switch_month('2026-11-01')
        self.assertEqual(p.get(DAY, '18:00', h), 'Растяжка')
        p.switch_week('')
        self.assertEqual(p.get(DAY, '18:00', h), 'Йога')

    def test_month_boundary_exception_uses_requested_month_and_keeps_month_unchanged(self):
        p = simple_project()
        h = p.hall_ids[0]
        p.switch_month('2026-11-01')
        p.set(DAY, '18:00', h, 'Растяжка')
        p.switch_week('2026-11-01')  # Sunday in a week beginning in October.
        self.assertEqual(p.active_week, '2026-10-26')
        self.assertEqual(p.get(DAY, '18:00', h), 'Растяжка')
        p.set(DAY, '18:00', h, '')
        p.switch_month('2026-11-01')
        self.assertEqual(p.get(DAY, '18:00', h), 'Растяжка')
        p.switch_week('2026-11-01')
        self.assertFalse(p.get(DAY, '18:00', h))

    def test_exception_reset_restores_its_month_even_at_month_boundary(self):
        p = simple_project()
        h = p.hall_ids[0]
        p.switch_month('2026-11-01')
        p.set(DAY, '18:00', h, 'Растяжка')
        p.switch_week('2026-11-01')
        p.set(DAY, '18:00', h, '')
        restored = Project.from_dict(p.to_dict())
        restored.replace_week()
        self.assertEqual(restored.get(DAY, '18:00', h), 'Растяжка')

    def test_copy_across_year_and_leap_month(self):
        p = simple_project()
        p.switch_month('2027-12-01')
        p.switch_month('2028-01-01', copy_current=True)
        p.switch_month('2028-02-01', copy_current=True)
        self.assertIn('29.02.2028', p.period_text())
        self.assertEqual(p.detail(DAY, '18:00', p.hall_ids[0])['trainer'], 'Анна')
        p.set(DAY, '18:00', p.hall_ids[0], '')
        p.switch_month('2028-01-01')
        self.assertEqual(p.get(DAY, '18:00', p.hall_ids[0]), 'Йога')

    def test_month_archive_roundtrip_and_global_catalog_operations(self):
        p = simple_project()
        p.switch_month('2026-11-01')
        p.switch_month('2026-12-01', copy_current=True)
        p.rename('Йога', 'Йога мягкая')
        restored = Project.from_dict(p.to_dict())
        self.assertEqual(restored.to_dict(), p.to_dict())
        restored.switch_month('2026-11-01')
        self.assertEqual(restored.get(DAY, '18:00', restored.hall_ids[0]), 'Йога мягкая')
        restored.remove_training('Йога мягкая')
        restored.switch_month('2026-12-01')
        self.assertFalse(restored.get(DAY, '18:00', restored.hall_ids[0]))

    def test_v4_and_v3_migrate_without_reinterpreting_the_current_week(self):
        for version in (3, 4):
            p = simple_project()
            if version == 4:
                p.switch_week('2026-11-02')
            data = p.to_dict()
            data['version'] = version
            data.pop('active_month')
            data.pop('months')
            restored = Project.from_dict(data)
            self.assertEqual(restored.active_week, p.active_week)
            self.assertEqual(restored.schedule, p.schedule)
            self.assertEqual(restored.active_month, '')

    def test_invalid_month_data_is_rejected(self):
        p = simple_project()
        p.switch_month('2026-11-01')
        for field, value in [('active_month', '2026-11-02'), ('months', []),
                             ('months', {'2026-11-02': p.week_state()}),
                             ('months', {'2026-11-01': {'schedule': []}}),
                             ('active_week', '2026-11-02')]:
            data = p.to_dict()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                Project.from_dict(data)


class InlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Q.QApplication.instance() or Q.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        p = simple_project()
        p.options.update(trainer=1, duration=1)
        self.h = p.hall_ids[0]
        self.store = Store(self.temp.name)
        self.store.save(p)
        self.w = MainWindow(self.store, False)
        self.w.show()
        self.app.processEvents()

    def tearDown(self):
        self.w.autosave.stop()
        self.w.preview_timer.stop()
        self.w.deleteLater()
        self.temp.cleanup()

    def test_private_fields_are_visible_and_editable_in_grid_but_absent_from_publication(self):
        trainer, duration, start = self.w.cell_details[(DAY, '18:00', self.h)]
        self.assertTrue(trainer.isVisible())
        self.assertTrue(duration.isVisible())
        self.assertEqual(trainer.text(), 'Анна')
        self.assertEqual(duration.value(), 60)
        trainer.setText('Ульяна')
        trainer.editingFinished.emit()
        duration.setValue(45)
        duration.editingFinished.emit()
        self.assertEqual(self.w.project.detail(DAY, '18:00', self.h), {'trainer': 'Ульяна', 'duration': 45})
        self.assertNotIn('Ульяна', self.w.project.publication_text())
        self.assertNotIn('45 мин', self.w.project.publication_text())
        self.w.undo()
        self.assertEqual(self.w.project.detail(DAY, '18:00', self.h)['duration'], 60)
        self.w.redo()
        self.w.save(quiet=True)
        self.assertEqual(self.store.load()[0].detail(DAY, '18:00', self.h)['duration'], 45)

    def test_time_moves_inline_without_losing_details(self):
        start = self.w.cell_details[(DAY, '18:00', self.h)][2]
        start.setTime(QtCore.QTime(18, 30))
        start.editingFinished.emit()
        self.assertFalse(self.w.project.get(DAY, '18:00', self.h))
        self.assertEqual(self.w.project.get(DAY, '18:30', self.h), 'Йога')
        self.assertEqual(self.w.project.detail(DAY, '18:30', self.h)['trainer'], 'Анна')
        self.w.undo()
        self.assertEqual(self.w.project.get(DAY, '18:00', self.h), 'Йога')

    def test_editor_visibility_controls_sync_and_public_fields_use_new_lines(self):
        self.w.editor_option_fields['trainer'].setCurrentIndex(2)
        self.w.editor_option_fields['duration'].setCurrentIndex(2)
        self.assertEqual(self.w.option_fields['trainer'].currentIndex(), 2)
        self.assertEqual(self.w.project.session_text(DAY, '18:00', self.h), 'Йога\nАнна\n60 мин')
        self.w.option_fields['trainer'].setCurrentIndex(0)
        trainer = self.w.cell_details[(DAY, '18:00', self.h)][0]
        self.assertFalse(trainer.isVisible())
        self.assertEqual(self.w.editor_option_fields['trainer'].currentIndex(), 0)

    def test_first_month_adopts_visible_schedule_then_copy_next_month_supports_undo(self):
        self.w.open_week('2026-11-02')
        self.w.project.set(DAY, '18:00', self.h, 'Растяжка')
        self.w.open_month('2026-11-01')
        self.assertEqual(self.w.project.get(DAY, '18:00', self.h), 'Растяжка')
        self.assertEqual(self.w.week_mode.currentIndex(), 2)
        self.assertEqual(self.w.schedule_heading.text(), 'Расписание на месяц')
        self.w.copy_next_month()
        self.assertEqual(self.w.project.active_month, '2026-12-01')
        self.assertEqual(self.w.project.get(DAY, '18:00', self.h), 'Растяжка')
        self.w.undo()
        self.assertEqual(self.w.project.active_month, '2026-11-01')

    def test_copy_month_requires_confirmation_before_replacing_existing(self):
        self.w.open_month('2026-11-01')
        self.w.copy_next_month()
        self.w.open_month('2026-11-01')
        before = self.w.project.to_dict()
        with patch.object(self.w, 'confirm', return_value=False) as confirm:
            self.w.copy_next_month()
        self.assertTrue(confirm.called)
        self.assertEqual(self.w.project.to_dict(), before)


class BackgroundContrastTests(unittest.TestCase):
    def test_header_and_footer_have_contrast_surfaces_over_any_photo(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'background.png'
            for background in ('#FFFFFF', '#000000'):
                Image.new('RGB', (40, 40), background).save(path)
                for theme in ('Светлый', 'Тёмный'):
                    p = simple_project()
                    p.style.update(palette=theme, bg_common=str(path), bg_transparency=100,
                                   panel_transparency=100, subtitle='Адрес студии', contact='Запись на занятия')
                    image = rendering.render(p, 'post')[0]
                    palette = rendering.PALETTES[theme]
                    self.assertEqual(image.getpixel((100, 25)), rgb(palette['bg']))
                    self.assertEqual(image.getpixel((100, image.height - 20)), rgb(palette['bg']))
                    def luminance(color):
                        channels = [v / 255 for v in rgb(color)]
                        channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
                        return sum(v * weight for v, weight in zip(channels, (.2126, .7152, .0722)))
                    for key in ('text', 'muted', 'accent'):
                        light, dark = sorted((luminance(palette[key]), luminance(palette['bg'])), reverse=True)
                        self.assertGreaterEqual((light + .05) / (dark + .05), 4.5)

    def test_export_keeps_title_trainer_duration_on_separate_lines_with_smaller_details(self):
        p = simple_project()
        p.options.update(trainer=2, duration=2)
        original = rendering.text_lines
        for variant in rendering.FORMATS:
            seen = []
            def capture(draw, lines, x, y, face, *args, **kwargs):
                seen.extend((line, y, face.size) for line in lines)
                return original(draw, lines, x, y, face, *args, **kwargs)
            with patch.object(rendering, 'text_lines', side_effect=capture):
                rendering.render(p, variant)
            title = next(row for row in seen if row[0] == 'Йога')
            trainer = next(row for row in seen if row[0] == 'Анна')
            duration = next(row for row in seen if row[0] == '60 мин')
            self.assertLess(title[1], trainer[1])
            self.assertLess(trainer[1], duration[1])
            self.assertLess(trainer[2], title[2])
            self.assertEqual(trainer[2], duration[2])


if __name__ == '__main__':
    unittest.main()

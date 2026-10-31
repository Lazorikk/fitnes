"""Regression coverage for dated schedules and private optional fields."""
import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from unittest.mock import patch
from PySide6 import QtCore, QtWidgets as Q
from model import Project, Store, ALL_DAYS
from main import MainWindow
from rendering import render

DAY = ALL_DAYS[0]


class StudioModelTests(unittest.TestCase):
    def setUp(self):
        self.p = Project(trainings=['Йога', 'Пилатес'], times=['18:00', '18:30', '19:00'])
        self.hall = self.p.hall_ids[0]
        self.p.set(DAY, '18:00', self.hall, 'Йога')

    def test_dated_cancellation_does_not_touch_template_or_next_week(self):
        self.p.switch_week('2026-11-04')
        self.assertEqual(self.p.active_week, '2026-11-02')
        self.p.set(DAY, '18:00', self.hall, '')
        restored = Project.from_dict(self.p.to_dict())
        restored.switch_week('2026-11-09')
        self.assertEqual(restored.get(DAY, '18:00', self.hall), 'Йога')
        restored.switch_week('2026-11-02')
        self.assertEqual(restored.get(DAY, '18:00', self.hall), '')
        restored.switch_week('')
        self.assertEqual(restored.get(DAY, '18:00', self.hall), 'Йога')

    def test_week_days_and_times_are_isolated(self):
        self.p.switch_week('2026-11-02')
        self.p.times.append('20:15')
        self.p.days.append(ALL_DAYS[-1])
        self.p.switch_week('2026-11-09')
        self.assertNotIn('20:15', self.p.times)
        self.assertNotIn(ALL_DAYS[-1], self.p.days)
        self.p.switch_week('2026-11-02')
        self.assertIn('20:15', self.p.times)
        self.assertIn(ALL_DAYS[-1], self.p.days)

    def test_existing_week_is_not_replaced_by_template_edits(self):
        self.p.switch_week('2026-11-02')
        self.p.switch_week('')
        self.p.set(DAY, '18:00', self.hall, 'Пилатес')
        self.p.switch_week('2026-11-02')
        self.assertEqual(self.p.get(DAY, '18:00', self.hall), 'Йога')
        self.p.switch_week('2026-11-09')
        self.assertEqual(self.p.get(DAY, '18:00', self.hall), 'Пилатес')

    def test_copy_previous_and_restore_template_have_no_shared_references(self):
        self.p.switch_week('2026-11-02')
        self.p.set(DAY, '18:00', self.hall, 'Пилатес')
        self.p.set_detail(DAY, '18:00', self.hall, 'Анна', 60)
        self.p.switch_week('2026-11-09')
        self.p.replace_week(previous=True)
        self.assertEqual(self.p.detail(DAY, '18:00', self.hall)['duration'], 60)
        self.p.set(DAY, '18:00', self.hall, '')
        self.p.switch_week('2026-11-02')
        self.assertEqual(self.p.get(DAY, '18:00', self.hall), 'Пилатес')
        self.p.replace_week()
        self.assertEqual(self.p.get(DAY, '18:00', self.hall), 'Йога')

    def test_missing_previous_week_has_no_side_effects(self):
        self.p.switch_week('2026-11-02')
        before = self.p.to_dict()
        with self.assertRaises(ValueError):
            self.p.replace_week(previous=True)
        self.assertEqual(before, self.p.to_dict())

    def test_private_fields_never_appear_in_public_text(self):
        self.p.set_detail(DAY, '18:00', self.hall, 'Анна', 60)
        for value in (0, 1):
            self.p.options.update(trainer=value, duration=value)
            text = self.p.publication_text()
            self.assertNotIn('Анна', text)
            self.assertNotIn('60 мин', text)
            self.assertEqual(self.p.session_text(DAY, '18:00', self.hall), 'Йога')
        self.p.options.update(trainer=2, duration=2)
        self.assertIn('Анна · 60 мин', self.p.publication_text())

    def test_conflicts_known_duration_and_optional_trainer(self):
        self.p.options.update(trainer=1, duration=1)
        self.p.set_detail(DAY, '18:00', self.hall, 'Анна', 60)
        self.p.set(DAY, '18:30', self.hall, 'Пилатес')
        self.assertEqual(len(self.p.conflicts()), 1)
        self.p.set(DAY, '18:30', self.hall, '')
        other = self.p.hall_ids[1]
        self.p.set(DAY, '18:30', other, 'Пилатес')
        self.p.set_detail(DAY, '18:30', other, 'анна', 60)
        self.assertEqual(len(self.p.conflicts()), 1)
        self.p.options['trainer'] = 0
        self.assertEqual(self.p.conflicts(), [])
        self.p.set(DAY, '19:00', self.hall, 'Пилатес')
        self.assertEqual(self.p.conflicts(), [])

    def test_rename_and_hall_deletion_apply_to_archived_weeks(self):
        self.p.set_detail(DAY, '18:00', self.hall, 'Анна', 60)
        self.p.switch_week('2026-11-02')
        self.p.switch_week('2026-11-09')
        self.p.rename('Йога', 'Йога мягкая')
        self.p.switch_week('2026-11-02')
        self.assertEqual(self.p.get(DAY, '18:00', self.hall), 'Йога мягкая')
        self.p.remove_hall(self.hall)
        restored = Project.from_dict(self.p.to_dict())
        restored.switch_week('')
        self.assertNotIn(self.hall, restored.hall_ids)

    def test_malformed_archive_and_options_are_rejected(self):
        self.p.switch_week('2026-11-02')
        for field, value in [('active_week', '2026-11-03'), ('weeks', {'bad': {}}),
                             ('weeks', {'2026-11-09': {'schedule': []}}),
                             ('options', {'trainer': True, 'duration': 0}),
                             ('details', {DAY: {'18:00': {self.hall: {'duration': -1}}}})]:
            payload = self.p.to_dict()
            payload[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                Project.from_dict(payload)

    def test_store_roundtrip_preserves_archive_and_private_details(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            self.p.switch_week('2026-11-02')
            self.p.set_detail(DAY, '18:00', self.hall, 'Анна', 45)
            self.p.switch_week('2026-11-09')
            store.save(self.p)
            restored, _ = store.load()
            self.assertEqual(restored.to_dict(), self.p.to_dict())
            restored.switch_week('2026-11-02')
            self.assertEqual(restored.detail(DAY, '18:00', self.hall)['duration'], 45)

    def test_new_install_is_neutral_single_hall_and_optional_fields_off(self):
        with tempfile.TemporaryDirectory() as directory:
            project, _ = Store(directory).load()
            self.assertEqual(len(project.halls), 1)
            self.assertEqual(project.style['studio_name'], 'Моя студия')
            self.assertEqual(project.options, {'trainer': 0, 'duration': 0})

    def test_dated_export_contains_dates_and_respects_field_visibility(self):
        self.p.switch_week('2026-11-02')
        self.p.set_detail(DAY, '18:00', self.hall, 'Анна', 60)
        import rendering
        original = rendering.text_lines
        for public in (False, True):
            self.p.options.update(trainer=2 if public else 1, duration=2 if public else 1)
            seen = []
            def capture(draw, lines, *args, **kwargs):
                seen.extend(lines)
                return original(draw, lines, *args, **kwargs)
            with patch.object(rendering, 'text_lines', side_effect=capture):
                for variant in ('story', 'post', 'a4'):
                    self.assertEqual(len(render(self.p, variant)), 1)
            self.assertIn('Понедельник 02.11', seen)
            self.assertTrue(any('08.11.2026' in line for line in seen))
            self.assertEqual(any('Анна' in line for line in seen), public)


class StudioWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Q.QApplication.instance() or Q.QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(self.directory.name)
        self.project = Project(trainings=['Йога'], times=['18:00', '19:00'])
        self.hall = self.project.hall_ids[0]
        self.project.set(DAY, '18:00', self.hall, 'Йога')
        self.store.save(self.project)
        self.window = MainWindow(self.store, start_preview=False)

    def tearDown(self):
        self.window.autosave.stop()
        self.window.preview_timer.stop()
        self.window.deleteLater()
        self.directory.cleanup()

    def test_week_controls_and_undo_redo_survive_save(self):
        self.window.open_week('2026-11-02')
        self.assertIn('02.11', self.window.table.horizontalHeaderItem(0).text())
        self.window.assign(DAY, '18:00', self.hall, '')
        self.window.undo()
        self.assertEqual(self.window.project.get(DAY, '18:00', self.hall), 'Йога')
        self.window.redo()
        self.window.open_week('')
        self.assertEqual(self.window.project.get(DAY, '18:00', self.hall), 'Йога')
        self.window.save(quiet=True)
        restored, _ = self.store.load()
        restored.switch_week('2026-11-02')
        self.assertEqual(restored.get(DAY, '18:00', self.hall), '')

    def test_session_move_preserves_template_and_produces_message(self):
        self.window.open_week('2026-11-02')
        self.window.change_option('duration', 1)
        def edit(dialog):
            dialog.findChild(Q.QTimeEdit).setTime(QtCore.QTime(19, 30))
            dialog.findChild(Q.QSpinBox).setValue(60)
            return Q.QDialog.Accepted
        with patch.object(Q.QDialog, 'exec', edit), patch.object(self.window, 'show_publication') as message:
            self.window.edit_session(DAY, '18:00', self.hall)
        p = self.window.project
        self.assertFalse(p.get(DAY, '18:00', self.hall))
        self.assertEqual(p.get(DAY, '19:30', self.hall), 'Йога')
        self.assertEqual(p.detail(DAY, '19:30', self.hall)['duration'], 60)
        self.assertIn('Перенос с 18:00', message.call_args.args[0])
        p.switch_week('')
        self.assertEqual(p.get(DAY, '18:00', self.hall), 'Йога')

    def test_session_cancel_and_back(self):
        self.window.open_week('2026-11-02')
        before = self.window.project.to_dict()
        with patch.object(Q.QDialog, 'exec', return_value=Q.QDialog.Rejected):
            self.window.edit_session(DAY, '18:00', self.hall)
        self.assertEqual(self.window.project.to_dict(), before)
        with patch.object(Q.QDialog, 'exec', return_value=2), patch.object(self.window, 'show_publication'):
            self.window.edit_session(DAY, '18:00', self.hall)
        self.assertFalse(self.window.project.get(DAY, '18:00', self.hall))
        self.window.undo()
        self.assertEqual(self.window.project.get(DAY, '18:00', self.hall), 'Йога')

    def test_occupied_destination_is_rejected_without_overwriting(self):
        self.window.project.set(DAY, '19:00', self.hall, 'Йога')
        before = self.window.project.to_dict()
        def attempt(dialog):
            dialog.findChild(Q.QTimeEdit).setTime(QtCore.QTime(19, 0))
            buttons = dialog.findChild(Q.QDialogButtonBox)
            buttons.button(Q.QDialogButtonBox.Save).click()
            self.assertIn('уже занято', dialog.findChild(Q.QLabel, 'formError').text())
            buttons.button(Q.QDialogButtonBox.Cancel).click()
            return dialog.result()
        with patch.object(Q.QDialog, 'exec', attempt):
            self.window.edit_session(DAY, '18:00', self.hall)
        self.assertEqual(self.window.project.to_dict(), before)

    def test_new_training_choice_opens_editor_and_cancel_restores_selection(self):
        combo = self.window.cell_combos[(DAY, '18:00', self.hall)]
        before = self.window.project.to_dict()
        with patch.object(self.window, 'edit_session') as editor:
            combo.setCurrentIndex(combo.count() - 1)
        editor.assert_called_once_with(DAY, '18:00', self.hall)
        self.assertEqual(combo.currentData(), 'Йога')
        self.assertEqual(self.window.project.to_dict(), before)

    def test_publication_can_be_edited_and_copied(self):
        before = self.window.project.to_dict()
        def copy_text(dialog):
            editor = dialog.findChild(Q.QPlainTextEdit)
            self.assertIn('18:00 — Йога', editor.toPlainText())
            editor.setPlainText('Запись открыта!')
            next(b for b in dialog.findChildren(Q.QPushButton) if b.text() == 'Скопировать текст').click()
            self.assertEqual(self.app.clipboard().text(), 'Запись открыта!')
            return Q.QDialog.Accepted
        with patch.object(Q.QDialog, 'exec', copy_text):
            self.window.show_publication()
        self.assertEqual(self.window.project.to_dict(), before)

    def test_optional_field_switches_and_conflict_warning(self):
        self.window.option_fields['duration'].setCurrentIndex(1)
        self.window.project.set_detail(DAY, '18:00', self.hall, '', 90)
        self.window.assign(DAY, '19:00', self.hall, 'Йога')
        self.assertIn('Проверьте пересечения', self.window.conflict_label.text())
        self.assertNotIn('90 мин', self.window.project.publication_text())
        self.window.option_fields['duration'].setCurrentIndex(2)
        self.assertIn('90 мин', self.window.project.publication_text())

    def test_copy_week_and_archived_week_selector(self):
        self.window.open_week('2026-11-02')
        self.window.assign(DAY, '18:00', self.hall, '')
        self.window.open_week('2026-11-09')
        with patch.object(self.window, 'confirm', return_value=True):
            self.window.copy_week(True)
        self.assertFalse(self.window.project.get(DAY, '18:00', self.hall))
        self.window.week_archive.setCurrentIndex(self.window.week_archive.findData('2026-11-02'))
        self.assertEqual(self.window.project.active_week, '2026-11-02')


if __name__ == '__main__':
    unittest.main()

"""Small-studio workflows: dated weeks, quick edits and publication text."""
from __future__ import annotations

import copy

from PySide6 import QtCore, QtWidgets as Q


class StudioWorkflows:
    def week_controls(self):
        panel = Q.QFrame()
        panel.setObjectName('weekPanel')
        layout = Q.QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        row = Q.QHBoxLayout()
        self.week_mode = Q.QComboBox()
        self.week_mode.addItems(['Каждую неделю · без периода', 'Разовые изменения · неделя', 'Весь месяц · каждую неделю'])
        self.week_mode.setToolTip('На месяц: одна сетка повторяется весь месяц. Разовые изменения — исключения на выбранные даты.')
        self.week_mode.currentIndexChanged.connect(self.change_week_mode)
        row.addWidget(self.week_mode)
        self.week_previous = Q.QPushButton('‹')
        self.week_previous.setToolTip('Предыдущая неделя')
        self.week_previous.clicked.connect(lambda: self.navigate_week(-7))
        row.addWidget(self.week_previous)
        self.week_date = Q.QDateEdit()
        self.week_date.setCalendarPopup(True)
        self.week_date.setDisplayFormat('dd.MM.yyyy')
        self.week_date.setDate(QtCore.QDate.currentDate())
        self.week_date.dateChanged.connect(self.select_week)
        row.addWidget(self.week_date)
        self.week_next = Q.QPushButton('›')
        self.week_next.setToolTip('Следующая неделя')
        self.week_next.clicked.connect(lambda: self.navigate_week(7))
        row.addWidget(self.week_next)
        row.addStretch()
        self.month_date = Q.QDateEdit()
        self.month_date.setDisplayFormat('MMMM yyyy')
        self.month_date.setLocale(QtCore.QLocale('ru_RU'))
        self.month_date.setDate(QtCore.QDate.currentDate())
        self.month_date.dateChanged.connect(self.select_month)
        row.addWidget(self.month_date)
        self.next_month_btn = Q.QPushButton('Скопировать на следующий месяц')
        self.next_month_btn.clicked.connect(self.copy_next_month)
        row.addWidget(self.next_month_btn)
        self.exception_btn = Q.QPushButton('Разовое изменение…')
        self.exception_btn.clicked.connect(self.month_exception)
        row.addWidget(self.exception_btn)
        layout.addLayout(row)
        self.week_hint = Q.QLabel()
        self.week_hint.setObjectName('muted')
        self.week_hint.setWordWrap(True)
        layout.addWidget(self.week_hint)
        actions = Q.QHBoxLayout()
        self.copy_previous_btn = Q.QPushButton('Как на прошлой неделе')
        self.copy_previous_btn.clicked.connect(lambda: self.copy_week(True))
        actions.addWidget(self.copy_previous_btn)
        self.from_template_btn = Q.QPushButton('Взять обычное расписание')
        self.from_template_btn.clicked.connect(lambda: self.copy_week(False))
        actions.addWidget(self.from_template_btn)
        actions.addStretch()
        self.week_archive = Q.QComboBox()
        self.week_archive.setToolTip('Ранее открытые недели сохраняются автоматически')
        self.week_archive.currentIndexChanged.connect(self.select_archived_week)
        actions.addWidget(self.week_archive, 1)
        layout.addLayout(actions)
        return panel

    def refresh_week_controls(self):
        active = bool(self.project.active_week)
        month = bool(self.project.active_month)
        self.schedule_heading.setText('Расписание на месяц' if month else 'Разовые изменения' if active else 'Повторяющееся расписание')
        self.style_fields['period'].setEnabled(not (active or month))
        self.style_fields['period'].setText(self.project.period_text())
        self.style_fields['period'].setToolTip('Даты выбранной недели подставляются автоматически.' if active else '')
        self.from_template_btn.setText('Вернуть сетку месяца' if self.project.active_week in self.project.week_sources else 'Взять постоянный шаблон')
        self.week_mode.setCurrentIndex(2 if month else 1 if active else 0)
        if month:
            self.month_date.setDate(QtCore.QDate.fromString(self.project.active_month, 'yyyy-MM-dd'))
        for widget in (self.month_date, self.next_month_btn, self.exception_btn):
            widget.setVisible(month)
        if active:
            self.week_date.setDate(QtCore.QDate.fromString(self.project.active_week, 'yyyy-MM-dd'))
        for widget in (self.week_date, self.week_previous, self.week_next,
                       self.copy_previous_btn, self.from_template_btn):
            widget.setEnabled(active)
            widget.setVisible(active)
        self.week_hint.setText(
            self.project.period_text() + '. Одна сетка на весь месяц; для отмен и переносов нажмите «Разовое изменение».' if month else
            self.project.period_text() + ' · Изменения действуют только в этой неделе.' if active else
            'Повторяющаяся неделя. Новые недели создаются из этого шаблона; уже открытые недели сохраняются отдельно.')
        self.week_archive.clear()
        self.week_archive.addItem('Архив недель…', '')
        for key in sorted(set(self.project.weeks) | ({self.project.active_week} if active else set()), reverse=True):
            value = QtCore.QDate.fromString(key, 'yyyy-MM-dd')
            self.week_archive.addItem(value.toString('dd.MM.yyyy') + ' — ' + value.addDays(6).toString('dd.MM.yyyy'), key)
        self.week_archive.setEnabled(self.week_archive.count() > 1)
        self.week_archive.setVisible(self.week_archive.count() > 1)
        for fields in (self.option_fields, self.editor_option_fields):
            for key, combo in fields.items():
                combo.setCurrentIndex(self.project.options[key])

    def select_archived_week(self, index):
        if not self.loading and self.week_archive.itemData(index):
            self.open_week(self.week_archive.itemData(index))

    def change_week_mode(self, index):
        if self.loading:
            return
        if index == 2:
            self.open_month(self.month_date.date().toString('yyyy-MM-dd'))
        else:
            self.open_week((self.project.active_month or self.week_date.date().toString('yyyy-MM-dd')) if index else '')

    def select_month(self, value):
        if not self.loading and self.week_mode.currentIndex() == 2:
            self.open_month(value.toString('yyyy-MM-dd'))

    def open_month(self, key, copy_current=False):
        if self.project.active_month == self.project.month_key(key):
            return
        self.remember()
        # On first adopting a month, keep the schedule the user is looking at.
        # Existing months always restore their own saved state.
        use_current = copy_current or (not self.project.months and not self.project.active_month)
        self.project.switch_month(key, use_current)
        self.changed(refresh=True)

    def copy_next_month(self):
        if not self.project.active_month:
            return
        next_date = QtCore.QDate.fromString(self.project.active_month, 'yyyy-MM-dd').addMonths(1)
        key = next_date.toString('yyyy-MM-dd')
        if key in self.project.months and not self.confirm('Заменить следующий месяц?',
                'Там уже есть расписание. Заменить его текущим? Изменение можно отменить.'):
            return
        self.open_month(key, copy_current=True)

    def month_exception(self):
        first = QtCore.QDate.fromString(self.project.active_month, 'yyyy-MM-dd')
        dialog = Q.QDialog(self)
        dialog.setWindowTitle('Разовое изменение в месяце')
        form = Q.QFormLayout(dialog)
        hint = Q.QLabel('Выберите дату. Откроется её неделя для переноса или отмены. Основное расписание месяца останется прежним.')
        hint.setWordWrap(True)
        form.addRow(hint)
        value = Q.QDateEdit(first)
        value.setCalendarPopup(True)
        value.setDisplayFormat('dd.MM.yyyy')
        value.setDateRange(first, first.addMonths(1).addDays(-1))
        form.addRow('Дата', value)
        buttons = Q.QDialogButtonBox(Q.QDialogButtonBox.Ok | Q.QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == Q.QDialog.Accepted:
            self.open_week(value.date().toString('yyyy-MM-dd'))


    def select_week(self, value):
        if not self.loading and self.week_mode.currentIndex():
            self.open_week(value.toString('yyyy-MM-dd'))

    def navigate_week(self, days):
        self.week_date.setDate(self.week_date.date().addDays(days))

    def open_week(self, key):
        normalized = self.project.monday(key) if key else ''
        if self.project.active_week == normalized and not self.project.active_month:
            return
        self.remember()
        self.project.switch_week(key)
        self.changed(refresh=True)

    def copy_week(self, previous):
        if not self.project.active_week:
            return
        if not self.confirm('Заменить расписание недели?',
                            'Занятия выбранной недели будут заменены. Другие недели сохранятся. Действие можно отменить.'):
            return
        # Validate before adding an undo entry or touching the live state.
        candidate = copy.deepcopy(self.project)
        try:
            candidate.replace_week(previous)
        except ValueError as error:
            Q.QMessageBox.information(self, 'Копирование недели', str(error))
            return
        self.remember()
        self.project = candidate
        self.changed(refresh=True)

    def optional_fields_panel(self):
        panel = Q.QWidget()
        form = Q.QFormLayout(panel)
        form.setContentsMargins(0, 0, 0, 0)
        title = Q.QLabel('Только нужные вам поля')
        title.setObjectName('section')
        form.addRow(title)
        hint = Q.QLabel('Для расписания достаточно времени и названия. Дополнительные поля можно включить позже.')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        form.addRow(hint)
        self.option_fields = {}
        for key, name in [('trainer', 'Тренер'), ('duration', 'Длительность')]:
            combo = Q.QComboBox()
            combo.addItems(['Не использовать', 'Только для себя', 'Показывать клиентам'])
            combo.currentIndexChanged.connect(lambda value, k=key: self.change_option(k, value))
            self.option_fields[key] = combo
            form.addRow(name, combo)
        return panel

    def change_option(self, key, value):
        if self.loading or self.project.options[key] == value:
            return
        self.remember()
        self.project.options[key] = value
        self.changed(refresh=True)

    def editor_options(self):
        row = Q.QHBoxLayout()
        self.editor_option_fields = {}
        for key, title in [('trainer', 'Тренер'), ('duration', 'Длительность')]:
            row.addWidget(Q.QLabel(title))
            combo = Q.QComboBox()
            combo.addItems(['Не использовать', 'Вижу только я', 'Показывать клиентам'])
            combo.currentIndexChanged.connect(lambda value, k=key: self.change_option(k, value))
            self.editor_option_fields[key] = combo
            row.addWidget(combo)
        row.addStretch()
        return row

    def save_inline_detail(self, day, time, hall, trainer, duration):
        if self.loading or not self.project.get(day, time, hall):
            return
        if duration and int(time[:2]) * 60 + int(time[3:]) + duration > 1440:
            Q.QMessageBox.warning(self, 'Длительность', 'Занятие должно завершиться в пределах дня.')
            self.refresh_all()
            return
        detail = {'trainer': trainer.strip(), 'duration': duration}
        if detail == self.project.detail(day, time, hall):
            return
        self.remember()
        self.project.set_detail(day, time, hall, **detail)
        self.changed()

    def move_inline_session(self, day, old_time, hall, new_time):
        if self.loading or new_time == old_time or not self.project.get(day, old_time, hall):
            return
        if self.project.get(day, new_time, hall):
            Q.QMessageBox.warning(self, 'Время занято', 'В этом зале уже есть занятие в выбранное время.')
            self.refresh_all()
            return
        name = self.project.get(day, old_time, hall)
        detail = dict(self.project.detail(day, old_time, hall))
        if detail.get('duration', 0) and self.project.options['duration'] and int(new_time[:2]) * 60 + int(new_time[3:]) + detail['duration'] > 1440:
            Q.QMessageBox.warning(self, 'Начало занятия', 'Занятие должно завершиться в пределах дня.')
            self.refresh_all()
            return
        self.remember()
        self.project.set(day, old_time, hall, '')
        if new_time not in self.project.times:
            self.project.times = sorted([*self.project.times, new_time])
        self.project.set(day, new_time, hall, name)
        self.project.set_detail(day, new_time, hall, **detail)
        self.changed(refresh=True)

    def update_conflicts(self):
        warnings = self.project.conflicts()
        missing_duration = any(not self.project.detail(d, t, h).get('duration')
                               for d in self.project.days for t in self.project.times for h in self.project.hall_ids
                               if self.project.get(d, t, h))
        self.conflict_label.setText(
            '⚠ Проверьте пересечения: ' + ' '.join(warnings[:3]) if warnings else
            (('Пересечений не найдено. Для полной проверки укажите длительность всех занятий.' if missing_duration
              else 'Пересечений в расписании не найдено.')
             if self.project.options['duration'] else
             'Тренер и длительность необязательны. Включите нужные поля над таблицей.'))
        self.conflict_label.setProperty('warning', bool(warnings))
        self.conflict_label.style().unpolish(self.conflict_label)
        self.conflict_label.style().polish(self.conflict_label)
        self.conflict_label.setToolTip('\n'.join(warnings))

    def edit_session(self, day, time, hall):
        dialog = Q.QDialog(self)
        dialog.setWindowTitle('Занятие · ' + self.project.day_title(day))
        dialog.setMinimumWidth(440)
        form = Q.QFormLayout(dialog)
        form.setSpacing(14)
        info = Q.QLabel(('Только эта неделя: ' + self.project.period_text()) if self.project.active_week
                        else 'Обычное расписание · шаблон новых недель')
        info.setWordWrap(True)
        info.setObjectName('muted')
        form.addRow(info)
        form.addRow('Зал', Q.QLabel(self.project.hall(hall)['name']))
        name = Q.QComboBox()
        name.setEditable(True)
        name.addItems(sorted(self.project.trainings, key=str.casefold))
        name.setCurrentText(self.project.get(day, time, hall))
        name.lineEdit().setMaxLength(120)
        form.addRow('Занятие', name)
        start = Q.QTimeEdit(QtCore.QTime.fromString(time, 'HH:mm'))
        start.setDisplayFormat('HH:mm')
        form.addRow('Начало', start)
        detail = self.project.detail(day, time, hall)
        trainer = Q.QLineEdit(detail.get('trainer', ''))
        trainer.setMaxLength(80)
        trainer.setPlaceholderText('Можно оставить пустым')
        if self.project.options['trainer']:
            form.addRow('Тренер', trainer)
        else:
            trainer.hide()
        duration = Q.QSpinBox()
        duration.setRange(0, 720)
        duration.setSpecialValueText('Не указана')
        duration.setSuffix(' мин')
        duration.setValue(detail.get('duration', 0))
        if self.project.options['duration']:
            form.addRow('Длительность', duration)
        else:
            duration.hide()
        error_label = Q.QLabel()
        error_label.setWordWrap(True)
        error_label.setObjectName('formError')
        error_label.hide()
        form.addRow(error_label)
        controls = Q.QDialogButtonBox(Q.QDialogButtonBox.Save | Q.QDialogButtonBox.Cancel)
        controls.button(Q.QDialogButtonBox.Save).setText('Сохранить занятие')
        controls.button(Q.QDialogButtonBox.Cancel).setText('Назад')
        remove = controls.addButton('Отменить занятие', Q.QDialogButtonBox.DestructiveRole)
        remove.setEnabled(bool(self.project.get(day, time, hall)))
        remove.clicked.connect(lambda: dialog.done(2))
        controls.rejected.connect(dialog.reject)
        def fail(message):
            error_label.setText(message)
            error_label.show()

        def accept():
            title = ' '.join(name.currentText().split())
            target = start.time().toString('HH:mm')
            if not title:
                fail('Введите название занятия.')
                return
            if target != time and self.project.get(day, target, hall):
                fail('Это время в выбранном зале уже занято. Выберите другое время.')
                return
            if self.project.options['duration'] and duration.value() and start.time().hour() * 60 + start.time().minute() + duration.value() > 1440:
                fail('Занятие должно завершиться в пределах дня. Проверьте время и длительность.')
                return
            dialog.accept()
        controls.accepted.connect(accept)
        form.addRow(controls)
        outcome = dialog.exec()
        if outcome not in (Q.QDialog.Accepted, 2):
            return
        self.remember()
        old_name = self.project.get(day, time, hall)
        self.project.set(day, time, hall, '')
        if outcome == Q.QDialog.Accepted:
            title = ' '.join(name.currentText().split())
            target = start.time().toString('HH:mm')
            canonical = next((n for n in self.project.trainings if n.casefold() == title.casefold()), title)
            if canonical not in self.project.trainings:
                self.project.trainings.append(canonical)
            if target not in self.project.times:
                self.project.times = sorted([*self.project.times, target])
            self.project.set(day, target, hall, canonical)
            self.project.set_detail(day, target, hall, trainer.text(), duration.value())
            message = f'{self.project.day_title(day)}: {target} — {canonical}.'
            if old_name and target != time:
                message += f' Перенос с {time}.'
        else:
            message = f'{self.project.day_title(day)}: занятие «{old_name}» в {time} отменено.'
        self.changed(refresh=True)
        if self.project.active_week:
            self.show_publication(message, 'Сообщение об изменении')

    def show_publication(self, text=None, title='Текст для клиентов'):
        # clicked(bool) is not a text argument.
        if not isinstance(text, str):
            text = self.project.publication_text()
        dialog = Q.QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(550, 550)
        layout = Q.QVBoxLayout(dialog)
        hint = Q.QLabel('Скопируйте и отправьте в чат студии. Перед отправкой текст можно изменить.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        editor = Q.QPlainTextEdit(text)
        layout.addWidget(editor)
        row = Q.QHBoxLayout()
        status = Q.QLabel()
        row.addWidget(status, 1)
        copy_btn = Q.QPushButton('Скопировать текст')
        copy_btn.setObjectName('primary')
        def copy_text():
            Q.QApplication.clipboard().setText(editor.toPlainText())
            status.setText('Текст скопирован')
        copy_btn.clicked.connect(copy_text)
        row.addWidget(copy_btn)
        close = Q.QPushButton('Готово')
        close.clicked.connect(dialog.accept)
        row.addWidget(close)
        layout.addLayout(row)
        dialog.exec()

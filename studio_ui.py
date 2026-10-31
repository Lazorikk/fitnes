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
        self.week_mode.addItems(['Обычное расписание', 'Неделя по датам'])
        self.week_mode.setToolTip('Обычное расписание — шаблон для новых недель')
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
        self.style_fields['period'].setEnabled(not active)
        self.style_fields['period'].setText(self.project.period_text())
        self.style_fields['period'].setToolTip('Даты выбранной недели подставляются автоматически.' if active else '')
        self.week_mode.setCurrentIndex(1 if active else 0)
        if active:
            self.week_date.setDate(QtCore.QDate.fromString(self.project.active_week, 'yyyy-MM-dd'))
        for widget in (self.week_date, self.week_previous, self.week_next,
                       self.copy_previous_btn, self.from_template_btn):
            widget.setEnabled(active)
            widget.setVisible(active)
        self.week_hint.setText(
            self.project.period_text() + ' · Изменения действуют только в этой неделе.' if active else
            'Повторяющаяся неделя. Новые недели создаются из этого шаблона; уже открытые недели сохраняются отдельно.')
        self.week_archive.clear()
        self.week_archive.addItem('Архив недель…', '')
        for key in sorted(set(self.project.weeks) | ({self.project.active_week} if active else set()), reverse=True):
            value = QtCore.QDate.fromString(key, 'yyyy-MM-dd')
            self.week_archive.addItem(value.toString('dd.MM.yyyy') + ' — ' + value.addDays(6).toString('dd.MM.yyyy'), key)
        self.week_archive.setEnabled(self.week_archive.count() > 1)
        self.week_archive.setVisible(self.week_archive.count() > 1)
        for key, combo in self.option_fields.items():
            combo.setCurrentIndex(self.project.options[key])

    def select_archived_week(self, index):
        if not self.loading and self.week_archive.itemData(index):
            self.open_week(self.week_archive.itemData(index))

    def change_week_mode(self, index):
        if not self.loading:
            self.open_week(self.week_date.date().toString('yyyy-MM-dd') if index else '')

    def select_week(self, value):
        if not self.loading and self.week_mode.currentIndex():
            self.open_week(value.toString('yyyy-MM-dd'))

    def navigate_week(self, days):
        self.week_date.setDate(self.week_date.date().addDays(days))

    def open_week(self, key):
        normalized = self.project.monday(key) if key else ''
        if self.project.active_week == normalized:
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

    def update_conflicts(self):
        warnings = self.project.conflicts()
        self.conflict_label.setText(
            '⚠ Проверьте пересечения: ' + ' '.join(warnings[:3]) if warnings else
            ('Пересечений не найдено. Для проверки интервалов укажите длительность занятий.'
             if self.project.options['duration'] else
             'Тренер и длительность необязательны. Настроить их можно во вкладке «Студия и залы».'))
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

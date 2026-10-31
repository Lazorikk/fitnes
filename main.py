from __future__ import annotations

import copy
import argparse
import html
import re
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PIL.ImageQt import ImageQt

from model import (APP_ID, APP_ORG, ALL_DAYS, Project, Store,
                   atomic_json, read_json, migrate_legacy, valid_time, validate_format)
from rendering import FORMATS, render, save_images
from colors import text_color, tint
from studio_ui import StudioWorkflows

Q = QtWidgets

STYLE = '''
QMainWindow, QDialog { background: #F4F5F8; }
QWidget { background-color: #F4F5F8; color: #292C3E; font-family: "Segoe UI", "DejaVu Sans"; font-size: 13px; }
QFrame#header, QFrame#preview { background: #FFFFFF; border: 1px solid #E3E5ED; border-radius: 16px; }
QLabel { background: transparent; }
QLabel#brand { color: #74618F; font-size: 12px; font-weight: 700; }
QLabel#title { font-size: 27px; font-weight: 700; }
QLabel#section { font-size: 20px; font-weight: 700; }
QLabel#muted { color: #7C8194; }
QLabel#status { color: #59696A; }
QPushButton { background: #FFFFFF; border: 1px solid #DDE0E9; border-radius: 9px; padding: 9px 15px; font-weight: 600; }
QPushButton:hover { background: #EFEBF7; border-color: #BDB0D3; }
QPushButton:pressed { background: #E1D8EF; }
QPushButton:disabled { color: #A7ADBD; background: #F4F5F8; }
QPushButton#primary { background: #76618F; color: #FFFFFF; border: 1px solid #76618F; }
QPushButton#primary:hover { background: #65507E; }
QPushButton#danger { color: #AA4F5C; }
QLineEdit, QListWidget, QComboBox, QTimeEdit, QDateEdit, QPlainTextEdit { background: #FFFFFF; border: 1px solid #DDE0E9; border-radius: 8px; padding: 8px; selection-background-color: #E7DFF2; selection-color: #292C3E; }
QLineEdit:focus, QComboBox:focus, QTimeEdit:focus { border: 1px solid #9980B6; }
QListWidget::item { padding: 12px; border-radius: 6px; }
QListWidget::item:selected { background: #EDE6F5; color: #55416C; }
QTabWidget::pane { background: transparent; border: none; }
QTabBar::tab { padding: 12px 22px; color: #777C90; border-bottom: 3px solid transparent; font-weight: 600; }
QTabBar::tab:selected { color: #6E528B; border-bottom: 3px solid #9375AF; }
QTableWidget { background: #FFFFFF; border: 1px solid #E3E5ED; border-radius: 10px; gridline-color: #EDF0F5; }
QHeaderView::section { background: #F2F3F7; color: #697085; border: none; padding: 14px 7px; font-weight: 600; }
QCheckBox { spacing: 7px; padding: 5px; }
QStatusBar { background: #F4F5F8; color: #7C8194; }
QScrollArea { background: #F4F5F8; border: none; }
QAbstractItemView { background: #FFFFFF; color: #292C3E; selection-background-color: #E7DFF2; selection-color: #292C3E; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #292C3E; selection-background-color: #E7DFF2; selection-color: #292C3E; }
QMenuBar { background: #F4F5F8; color: #292C3E; }
QMenuBar::item:selected, QMenu::item:selected { background: #E7DFF2; color: #292C3E; }
QMenu { background: #FFFFFF; color: #292C3E; border: 1px solid #DDE0E9; }
QMenu::item { background: transparent; padding: 8px 22px; }
QMenu::separator { height: 1px; background: #E3E5ED; margin: 5px; }
QWidget#scheduleCell { background: #FFFFFF; }
QTableCornerButton::section { background: #F2F3F7; border: none; }
QSpinBox { background: #FFFFFF; color: #292C3E; border: 1px solid #DDE0E9; border-radius: 8px; padding: 8px; }
QScrollBar { background: #F2F3F7; }
QScrollBar::handle { background: #C7BCD5; border-radius: 4px; min-height: 20px; min-width: 20px; }
QSlider::groove:horizontal { height: 6px; background: #DDE0E9; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #9375AF; border-radius: 3px; }
QSlider::handle:horizontal { background: #FFFFFF; border: 2px solid #76618F; width: 16px; margin: -7px 0; border-radius: 9px; }
QFrame#weekPanel { background: #EDE8F5; border: 1px solid #DDD3EC; border-radius: 12px; }
QLabel#conflicts { color: #68717D; padding: 8px; background: #EBF2EF; border-radius: 8px; }
QLabel#conflicts[warning="true"], QLabel#formError { color: #9B5626; background: #FFF1DE; }
QToolButton { background: #FFFFFF; border: 1px solid #DDE0E9; border-radius: 6px; padding: 5px; }
QToolButton:hover { background: #EDE6F5; }
QToolTip { background: #292C3E; color: white; border: none; padding: 7px; }
'''


def light_palette():
    palette = QtGui.QPalette()
    roles = {
        'Window': '#F4F5F8', 'WindowText': '#292C3E', 'Base': '#FFFFFF',
        'AlternateBase': '#F2F3F7', 'Text': '#292C3E', 'Button': '#FFFFFF',
        'ButtonText': '#292C3E', 'Highlight': '#E7DFF2', 'HighlightedText': '#292C3E',
        'ToolTipBase': '#292C3E', 'ToolTipText': '#FFFFFF', 'PlaceholderText': '#7C8194',
        'Link': '#70538F', 'Light': '#FFFFFF', 'Midlight': '#F2F3F7',
        'Mid': '#C5C8D4', 'Dark': '#777C90', 'Shadow': '#777C90',
    }
    for group in (QtGui.QPalette.Active, QtGui.QPalette.Inactive, QtGui.QPalette.Disabled):
        for role, color in roles.items():
            palette.setColor(group, getattr(QtGui.QPalette, role), QtGui.QColor(color))
    return palette


def label(text, name=None):
    widget = Q.QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


def button(text, callback, primary=False):
    widget = Q.QPushButton(text)
    if primary:
        widget.setObjectName('primary')
    widget.clicked.connect(callback)
    return widget


class Preview(Q.QLabel):
    activated = QtCore.Signal()

    def __init__(self):
        super().__init__('Предпросмотр появится здесь')
        self.source = None
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setMinimumSize(200, 240)
        self.setSizePolicy(Q.QSizePolicy.Ignored, Q.QSizePolicy.Ignored)
        self.setStyleSheet('background: #E9EBF1; border-radius: 12px; color: #7C8194;')

    def set_image(self, image):
        self.source = QtGui.QPixmap.fromImage(ImageQt(image))
        self.rescale()

    def rescale(self):
        if self.source:
            self.setPixmap(self.source.scaled(self.size() - QtCore.QSize(20, 20),
                           QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.rescale()

    def mouseDoubleClickEvent(self, event):
        self.activated.emit()
        super().mouseDoubleClickEvent(event)


class SessionCombo(Q.QComboBox):
    """A multiline selector keeps training names readable in a compact week grid."""
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(40)

    def paintEvent(self, event):
        option = Q.QStyleOptionComboBox()
        self.initStyleOption(option)
        text = option.currentText
        option.currentText = ''
        painter = Q.QStylePainter(self)
        painter.drawComplexControl(Q.QStyle.CC_ComboBox, option)
        rect = self.style().subControlRect(Q.QStyle.CC_ComboBox, option, Q.QStyle.SC_ComboBoxEditField, self)
        painter.setPen(self.palette().color(QtGui.QPalette.Text))
        painter.drawText(rect.adjusted(3, 1, -2, -1), QtCore.Qt.AlignVCenter | QtCore.Qt.TextWordWrap, text)
        painter.setPen(QtGui.QColor('#A197AD'))
        painter.drawText(self.rect().adjusted(0, 0, -5, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight, '⌄')


class TimeHeader(Q.QHeaderView):
    """Anchor the time to the top of its band instead of centering between halls."""
    def __init__(self, parent):
        super().__init__(QtCore.Qt.Vertical, parent)
        self.setMinimumWidth(88)
        self.setSectionsClickable(True)

    def paintSection(self, painter, rect, index):
        if not rect.isValid():
            return
        painter.save()
        painter.fillRect(rect, QtGui.QColor('#ECE8F2'))
        painter.setPen(QtGui.QColor('#D2CBDD'))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.setClipRect(rect)
        text_rect = QtCore.QRect(rect)
        text_rect.moveTop(min(max(rect.top(), 0), rect.bottom() - 58))
        small = QtGui.QFont(self.font())
        small.setPixelSize(9)
        painter.setFont(small)
        painter.setPen(QtGui.QColor('#766D86'))
        painter.drawText(text_rect.adjusted(6, 12, -6, 0), QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter, 'НАЧАЛО')
        face = QtGui.QFont(self.font())
        face.setPixelSize(17)
        face.setBold(True)
        painter.setFont(face)
        painter.setPen(QtGui.QColor('#493D60'))
        value = str(self.model().headerData(index, QtCore.Qt.Vertical) or '')
        painter.drawText(text_rect.adjusted(6, 30, -6, 0), QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter, value)
        painter.restore()


class RenderJob(QtCore.QThread):
    succeeded = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, project, variants, directory=None, kind='PNG', parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)
        self.variants, self.directory, self.kind = variants, directory, kind

    def run(self):
        try:
            images, paths = {}, []
            # Validate every layout before writing: a failed format must not
            # leave an apparently complete export with only one or two pictures.
            for variant in self.variants:
                images[variant] = render(self.project, variant)
            if self.directory:
                for variant in self.variants:
                    paths.extend(save_images(images[variant], self.directory, variant, self.kind, self.project.format(variant)['dpi']))
            self.succeeded.emit((images, paths))
        except Exception as error:
            self.failed.emit(str(error))


class MainWindow(StudioWorkflows, Q.QMainWindow):
    def __init__(self, store=None, start_preview=True):
        super().__init__()
        self.store = store or Store()
        # On unreadable data, fail visibly instead of silently replacing it with an empty project.
        self.project, notice = self.store.load()
        self.saved = self.project.to_dict()
        self.undo_history, self.redo_history = [], []
        self.revision = 0
        self.job = None
        self.images, self.page = [], 0
        self.loading = False
        self.setWindowTitle('Богини — студия расписаний[*]')
        area = Q.QApplication.primaryScreen().availableGeometry()
        self.resize(min(1500, max(1060, area.width() - 60)), min(940, max(650, area.height() - 60)))
        self.setMinimumSize(1060, 650)
        self.setPalette(light_palette())
        self.setStyleSheet(STYLE)
        self.autosave = QtCore.QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(900)
        self.autosave.timeout.connect(lambda: self.save(quiet=True))
        self.preview_timer = QtCore.QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(1100)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.editor_refresh = QtCore.QTimer(self)
        self.editor_refresh.setSingleShot(True)
        self.editor_refresh.timeout.connect(self.finish_inline_move)
        self.move_target = None
        self.setup_ui()
        self.setup_menu()
        self.refresh_all()
        self.statusBar().showMessage(notice or 'Выберите занятие из списка. Кнопка ⋯ открывает время и сведения. Всё сохраняется автоматически.')
        if notice:
            QtCore.QTimer.singleShot(0, lambda: Q.QMessageBox.information(self, 'Открытие данных', notice))
        if start_preview:
            QtCore.QTimer.singleShot(100, self.refresh_preview)

    def setup_ui(self):
        container = Q.QWidget()
        self.setCentralWidget(container)
        root = Q.QVBoxLayout(container)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(18)
        header = Q.QFrame()
        header.setObjectName('header')
        head = Q.QHBoxLayout(header)
        head.setContentsMargins(22, 17, 22, 17)
        branding = Q.QVBoxLayout()
        self.brand_label = label('', 'brand')
        self.brand_label.setTextFormat(QtCore.Qt.PlainText)
        branding.addWidget(self.brand_label)
        heading = label('Расписание студии', 'title')
        heading.setWordWrap(False)
        branding.addWidget(heading)
        head.addLayout(branding, 1)
        self.state_label = label('Все изменения сохранены', 'status')
        self.state_label.setWordWrap(False)
        branding.addWidget(self.state_label)
        self.undo_btn = button('↶', self.undo)
        self.undo_btn.setToolTip('Отменить действие · Ctrl+Z')
        self.redo_btn = button('↷', self.redo)
        self.redo_btn.setToolTip('Повторить действие · Ctrl+Shift+Z')
        head.addWidget(self.undo_btn)
        head.addWidget(self.redo_btn)
        head.addWidget(button('Сохранить', self.save))
        head.addWidget(button('Текст для чата', self.show_publication))
        self.export_btn = button('Сохранить картинки', self.export_dialog, True)
        head.addWidget(self.export_btn)
        root.addWidget(header)
        body = Q.QSplitter(QtCore.Qt.Horizontal)
        body.setChildrenCollapsible(False)
        self.tabs = Q.QTabWidget()
        self.tabs.addTab(self.make_schedule_tab(), 'Расписание')
        self.tabs.addTab(self.make_trainings_tab(), 'Тренировки')
        self.tabs.addTab(self.make_style_tab(), 'Оформление')
        self.tabs.addTab(self.make_studio_tab(), 'Студия и залы')
        self.tabs.addTab(self.make_formats_tab(), 'Форматы')
        body.addWidget(self.tabs)
        self.preview_panel = self.make_preview_panel()
        body.addWidget(self.preview_panel)
        self.preview_panel.setVisible(self.width() >= 1440)
        body.setStretchFactor(0, 4)
        body.setStretchFactor(1, 2)
        body.setSizes([990, 410])
        root.addWidget(body, 1)

    def setup_menu(self):
        menu = self.menuBar().addMenu('Проект')
        actions = [('Сохранить', self.save, 'Ctrl+S'),
                   ('Сохранить копию проекта…', self.backup_project, 'Ctrl+Shift+S'),
                   ('Открыть проект…', self.open_project, 'Ctrl+O'),
                   ('Импорт из старой программы…', self.import_legacy, None),
                   ('Открыть папку данных', self.open_data_folder, None)]
        for text, callback, shortcut in actions:
            action = menu.addAction(text)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(shortcut)
        menu.addSeparator()
        menu.addAction('Загрузить пример расписания', self.load_demo)
        menu.addAction('Выход', self.close)
        edit = self.menuBar().addMenu('Правка')
        for text, callback, shortcut in [('Отменить', self.undo, 'Ctrl+Z'),
                                          ('Повторить', self.redo, 'Ctrl+Shift+Z')]:
            action = edit.addAction(text)
            action.triggered.connect(callback)
            action.setShortcut(shortcut)
        help_menu = self.menuBar().addMenu('Помощь')
        help_menu.addAction('Как пользоваться', lambda: Q.QMessageBox.information(self, 'Быстрый старт',
            '1. Добавьте названия во вкладке «Тренировки».\n'
            '2. Выберите дни и время во вкладке «Расписание».\n'
            '3. В каждой ячейке назначьте занятия нужным залам.\n'
            '4. Настройте заголовок и цвета во вкладке «Оформление».\n'
            '5. Проверьте нужные форматы в предпросмотре и нажмите «Экспорт картинок».\n\n'
            'Изменения сохраняются автоматически. Ctrl+Z отменяет действия.\n'
            'Скрытые дни сохраняют занятия. В меню «Проект» можно сохранить копию.'))

    def make_schedule_tab(self):
        page = Q.QWidget()
        layout = Q.QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 12, 0)
        row = Q.QHBoxLayout()
        self.schedule_heading = label('Расписание', 'section')
        self.schedule_heading.setWordWrap(False)
        row.addWidget(self.schedule_heading)
        row.addStretch()
        self.count_label = label('', 'muted')
        self.count_label.setWordWrap(False)
        row.addWidget(self.count_label)
        self.preview_toggle = button('Показать / скрыть макет', self.toggle_preview_panel)
        row.addWidget(self.preview_toggle)
        layout.addLayout(row)
        layout.addWidget(self.week_controls())
        days = Q.QHBoxLayout()
        self.day_checks = {}
        for day, short in zip(ALL_DAYS, ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']):
            check = Q.QCheckBox(short)
            check.setToolTip(day + ' · скрытие не удаляет занятия')
            check.toggled.connect(lambda checked, d=day: self.toggle_day(d, checked))
            self.day_checks[day] = check
            days.addWidget(check)
        days.addStretch()
        layout.addLayout(days)
        tools = Q.QHBoxLayout()
        self.time_input = Q.QTimeEdit(QtCore.QTime(18, 0))
        self.time_input.setDisplayFormat('HH:mm')
        tools.addWidget(self.time_input)
        tools.addWidget(button('+ Время', self.add_time))
        tools.addWidget(button('Удалить время', self.delete_time))
        self.hide_empty = Q.QCheckBox('Скрыть пустые')
        self.hide_empty.setToolTip('Скрывает только пустые строки редактора, не меняя данные')
        self.hide_empty.toggled.connect(self.filter_rows)
        tools.addWidget(self.hide_empty)
        tools.addStretch()
        tools.addWidget(button('Копировать день…', self.copy_day))
        layout.addLayout(tools)
        self.hall_legend = label('', 'muted')
        layout.addWidget(self.hall_legend)
        layout.addLayout(self.editor_options())
        self.table = Q.QTableWidget()
        self.table.setSelectionMode(Q.QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(Q.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        self.table.setVerticalHeader(TimeHeader(self.table))
        self.table.setShowGrid(False)
        layout.addWidget(self.table, 1)
        self.conflict_label = label('', 'conflicts')
        layout.addWidget(self.conflict_label)
        bottom = Q.QHBoxLayout()
        bottom.addWidget(label('Занятия и оформление сохраняются автоматически.', 'muted'))
        bottom.addStretch()
        clear = button('Очистить сетку…', self.clear_week)
        clear.setObjectName('danger')
        bottom.addWidget(clear)
        layout.addLayout(bottom)
        return page

    def make_trainings_tab(self):
        page = Q.QWidget()
        layout = Q.QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 18, 0)
        layout.addWidget(label('Библиотека тренировок', 'section'))
        layout.addWidget(label('Добавляйте названия один раз и выбирайте их в расписании для любого зала.', 'muted'))
        self.training_search = Q.QLineEdit()
        self.training_search.setPlaceholderText('Поиск тренировки…')
        self.training_search.textChanged.connect(self.filter_trainings)
        layout.addWidget(self.training_search)
        self.training_list = Q.QListWidget()
        self.training_list.itemDoubleClicked.connect(lambda _: self.edit_training())
        layout.addWidget(self.training_list, 1)
        row = Q.QHBoxLayout()
        row.addWidget(button('+ Добавить тренировку', self.add_training, True))
        row.addWidget(button('Переименовать', self.edit_training))
        row.addWidget(button('Удалить', self.delete_training))
        row.addStretch()
        layout.addLayout(row)
        return page

    def make_style_tab(self):
        scroll = Q.QScrollArea()
        scroll.setWidgetResizable(True)
        page = Q.QWidget()
        form = Q.QFormLayout(page)
        form.setContentsMargins(10, 22, 24, 20)
        form.setSpacing(18)
        form.addRow(label('Дизайн расписания', 'section'))
        form.addRow(label('Недельная сетка во всех форматах · одна строка времени, несколько залов', 'muted'))
        self.style_fields = {}
        for key, title, placeholder in [
            ('title', 'Заголовок', 'Расписание занятий'),
            ('subtitle', 'Подзаголовок', 'Например: движение в удовольствие'),
            ('period', 'Период', 'Например: 2–8 ноября'),
            ('contact', 'Подпись внизу', 'Телефон, адрес или запись на тренировку')]:
            field = Q.QLineEdit()
            field.setMaxLength(160)
            field.setPlaceholderText(placeholder)
            field.textEdited.connect(lambda text, k=key: self.change_style(k, text))
            self.style_fields[key] = field
            form.addRow(title, field)
        self.palette = Q.QComboBox()
        self.palette.addItems(['Светлый', 'Тёмный'])
        self.palette.currentTextChanged.connect(lambda value: self.change_style('palette', value))
        form.addRow('Стиль картинок', self.palette)
        for key, title in [('logo_path', 'Логотип'), ('bg_common', 'Фоновое изображение')]:
            field = Q.QLineEdit()
            field.setPlaceholderText('Не выбрано')
            field.setReadOnly(True)
            self.style_fields[key] = field
            row = Q.QHBoxLayout()
            row.addWidget(field, 1)
            row.addWidget(button('Выбрать…', lambda checked=False, k=key: self.pick_asset(k)))
            row.addWidget(button('×', lambda checked=False, k=key: self.change_style(k, '', refresh=True)))
            form.addRow(title, row)
        self.transparency_sliders = {}
        self.transparency_spins = {}
        for key, title, hint in (
            ('bg_transparency', 'Прозрачность заливки',
             '0% — картинку полностью закрывает заливка; 100% — картинка без приглушения.'),
            ('panel_transparency', 'Прозрачность подложек дней',
             '0% — плотные столбцы; 100% — подложки дней полностью прозрачные.')):
            slider = Q.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setToolTip(hint)
            spin = Q.QSpinBox()
            spin.setRange(0, 100)
            spin.setSuffix(' %')
            spin.setMinimumWidth(85)
            spin.setToolTip(hint)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            slider.valueChanged.connect(lambda value, k=key: self.change_style(k, value))
            self.transparency_sliders[key] = slider
            self.transparency_spins[key] = spin
            row = Q.QHBoxLayout()
            row.addWidget(slider, 1)
            row.addWidget(spin)
            form.addRow(title, row)
        form.addRow(label('Чем выше прозрачность, тем лучше видна фоновая картинка. Карточки занятий остаются непрозрачными. Для заметного фона попробуйте 70–90% для заливки и 40–60% для подложек дней.', 'muted'))
        form.addRow(button('Сбросить отдельные фоны старой программы', self.reset_old_backgrounds))
        form.addRow(label('Выбирайте нужные форматы при экспорте. Свои размеры можно добавить во вкладке «Форматы».', 'muted'))
        scroll.setWidget(page)
        return scroll

    def make_studio_tab(self):
        page = Q.QWidget()
        layout = Q.QVBoxLayout(page)
        layout.setContentsMargins(10, 20, 18, 0)
        layout.addWidget(label('Ваша студия', 'section'))
        layout.addWidget(label('Название отображается в заголовке окна и на экспортируемых картинках.', 'muted'))
        studio = Q.QLineEdit()
        studio.setMaxLength(60)
        studio.setPlaceholderText('Название студии')
        studio.textEdited.connect(lambda text: self.change_style('studio_name', text))
        self.style_fields['studio_name'] = studio
        layout.addWidget(studio)
        layout.addWidget(self.optional_fields_panel())
        layout.addSpacing(18)
        layout.addWidget(label('Залы и цвета', 'section'))
        layout.addWidget(label('Каждый зал получает свою строку в редакторе. Цвет текста на картинках подбирается автоматически.', 'muted'))
        self.hall_list = Q.QListWidget()
        self.hall_list.itemDoubleClicked.connect(lambda _: self.edit_hall())
        layout.addWidget(self.hall_list, 1)
        controls = Q.QHBoxLayout()
        controls.addWidget(button('+ Зал', lambda: self.edit_hall(new=True), True))
        controls.addWidget(button('Название и цвет…', self.edit_hall))
        controls.addWidget(button('Удалить зал…', self.delete_hall))
        controls.addStretch()
        layout.addLayout(controls)
        return page

    @staticmethod
    def format_title(item):
        return f'{item["name"]} · {item["width"]} × {item["height"]} · {item["dpi"]} DPI'

    def make_formats_tab(self):
        page = Q.QWidget()
        layout = Q.QVBoxLayout(page)
        layout.setContentsMargins(10, 20, 18, 0)
        layout.addWidget(label('Размеры экспорта', 'section'))
        layout.addWidget(label('Стандартные форматы остаются доступными. Добавьте свои размеры в пикселях и выберите нужные галочками при экспорте.', 'muted'))
        self.formats_list = Q.QListWidget()
        self.formats_list.itemDoubleClicked.connect(lambda _: self.edit_format())
        layout.addWidget(self.formats_list, 1)
        controls = Q.QHBoxLayout()
        controls.addWidget(button('+ Свой формат', lambda: self.edit_format(new=True), True))
        controls.addWidget(button('Изменить…', self.edit_format))
        controls.addWidget(button('Удалить…', self.delete_format))
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(label('320–8000 пикселей по стороне, до 40 мегапикселей. Вся неделя размещается на одной картинке; слишком плотный макет потребует больше места.', 'muted'))
        return page

    def refresh_settings_lists(self):
        selected_hall = self.hall_list.currentItem()
        selected_hall = selected_hall.data(QtCore.Qt.UserRole) if selected_hall else None
        self.hall_list.clear()
        legend = []
        for hall in self.project.halls:
            item = Q.QListWidgetItem(hall['name'] + '   ' + hall['color'])
            item.setData(QtCore.Qt.UserRole, hall['id'])
            pixmap = QtGui.QPixmap(20, 20)
            pixmap.fill(QtGui.QColor(hall['color']))
            item.setIcon(QtGui.QIcon(pixmap))
            self.hall_list.addItem(item)
            if hall['id'] == selected_hall:
                self.hall_list.setCurrentItem(item)
            legend.append(f'<span style="color:{hall["color"]}">●</span> {html.escape(hall["name"])}')
        self.hall_legend.setText(' &nbsp; '.join(legend))
        selected_format = self.formats_list.currentItem()
        selected_format = selected_format.data(QtCore.Qt.UserRole) if selected_format else None
        self.formats_list.clear()
        current = self.format_combo.currentData()
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        for item in self.project.formats:
            title = self.format_title(item)
            entry = Q.QListWidgetItem(title)
            entry.setData(QtCore.Qt.UserRole, item['id'])
            self.formats_list.addItem(entry)
            if item['id'] == selected_format:
                self.formats_list.setCurrentItem(entry)
            self.format_combo.addItem(title, item['id'])
        self.format_combo.setCurrentIndex(max(0, self.format_combo.findData(current)))
        self.format_combo.blockSignals(False)

    def edit_hall(self, checked=False, *, new=False):
        item = self.hall_list.currentItem()
        if not new and item is None:
            self.statusBar().showMessage('Выберите зал из списка.', 4000)
            return
        identity = None if new else item.data(QtCore.Qt.UserRole)
        hall = {'name': '', 'color': '#A9C9F0'} if new else self.project.hall(identity)
        dialog = Q.QDialog(self)
        dialog.setWindowTitle('Добавить зал' if new else 'Название и цвет зала')
        form = Q.QFormLayout(dialog)
        name = Q.QLineEdit(hall['name'])
        name.setMaxLength(40)
        color = [hall['color']]
        swatch = Q.QPushButton()
        def update_color():
            swatch.setText(color[0])
            swatch.setStyleSheet(f'background:{color[0]}; color:{text_color(color[0])}; padding:10px;')
        def pick_color():
            chosen = Q.QColorDialog.getColor(QtGui.QColor(color[0]), dialog, 'Цвет зала')
            if chosen.isValid():
                color[0] = chosen.name().upper()
                update_color()
        update_color()
        swatch.clicked.connect(pick_color)
        form.addRow('Название', name)
        form.addRow('Цвет', swatch)
        controls = Q.QDialogButtonBox(Q.QDialogButtonBox.Ok | Q.QDialogButtonBox.Cancel)
        def accept():
            try:
                self.project.validate_hall(name.text(), color[0], identity)
                if new and len(self.project.halls) >= 12:
                    raise ValueError('Можно добавить до 12 залов.')
            except ValueError as error:
                Q.QMessageBox.warning(dialog, 'Проверьте зал', str(error))
                return
            dialog.accept()
        controls.accepted.connect(accept)
        controls.rejected.connect(dialog.reject)
        form.addRow(controls)
        if dialog.exec() == Q.QDialog.Accepted:
            self.remember()
            if new:
                self.project.add_hall(name.text(), color[0])
            else:
                self.project.update_hall(identity, name.text(), color[0])
            self.changed(refresh=True)

    def delete_hall(self):
        item = self.hall_list.currentItem()
        if item is None:
            return
        if len(self.project.halls) == 1:
            Q.QMessageBox.information(self, 'Залы', 'Нужен хотя бы один зал.')
            return
        identity = item.data(QtCore.Qt.UserRole)
        if self.confirm('Удалить зал?', f'Удалить «{self.project.hall(identity)["name"]}» и его занятия во всех днях? Действие можно отменить.'):
            self.remember()
            self.project.remove_hall(identity)
            self.changed(refresh=True)

    def edit_format(self, checked=False, *, new=False):
        entry = self.formats_list.currentItem()
        if not new and entry is None:
            self.statusBar().showMessage('Выберите свой формат из списка.', 4000)
            return
        identity = None if new else entry.data(QtCore.Qt.UserRole)
        if not new and identity in FORMATS:
            Q.QMessageBox.information(self, 'Стандартный формат', 'Для другого размера добавьте свой формат. Стандартные размеры остаются неизменными.')
            return
        item = {'name': '', 'width': 1080, 'height': 1080, 'dpi': 96} if new else self.project.format(identity)
        dialog = Q.QDialog(self)
        dialog.setWindowTitle('Свой формат экспорта')
        form = Q.QFormLayout(dialog)
        name = Q.QLineEdit(item['name'])
        name.setMaxLength(60)
        form.addRow('Название', name)
        spins = {}
        for key, title, minimum, maximum in [('width', 'Ширина, пикс.', 320, 8000),
                                                ('height', 'Высота, пикс.', 320, 8000), ('dpi', 'DPI', 72, 600)]:
            spin = Q.QSpinBox()
            spin.setRange(minimum, maximum)
            spin.setValue(item[key])
            spins[key] = spin
            form.addRow(title, spin)
        controls = Q.QDialogButtonBox(Q.QDialogButtonBox.Ok | Q.QDialogButtonBox.Cancel)
        def accept():
            try:
                validate_format(name.text(), *(spins[key].value() for key in ('width', 'height', 'dpi')))
                if any(f['id'] != identity and f['name'].casefold() == name.text().strip().casefold() for f in self.project.formats):
                    raise ValueError('Формат с таким названием уже есть.')
                if new and len(self.project.formats) >= 20:
                    raise ValueError('Можно добавить до 20 форматов.')
            except ValueError as error:
                Q.QMessageBox.warning(dialog, 'Проверьте формат', str(error))
                return
            dialog.accept()
        controls.accepted.connect(accept)
        controls.rejected.connect(dialog.reject)
        form.addRow(controls)
        if dialog.exec() == Q.QDialog.Accepted:
            self.remember()
            values = [spins[key].value() for key in ('width', 'height', 'dpi')]
            if new:
                self.project.add_format(name.text(), *values)
            else:
                self.project.format(identity).update(name=name.text().strip(), width=values[0], height=values[1], dpi=values[2])
            self.changed(refresh=True)

    def delete_format(self):
        entry = self.formats_list.currentItem()
        if entry is None:
            return
        if len(self.project.formats) == 1:
            Q.QMessageBox.information(self, 'Форматы', 'Оставьте хотя бы один формат экспорта.')
            return
        identity = entry.data(QtCore.Qt.UserRole)
        if identity in FORMATS:
            Q.QMessageBox.information(self, 'Стандартный формат', 'Стандартные форматы можно снять галочкой при экспорте. Удалять их не нужно.')
            return
        if self.confirm('Удалить формат?', 'Удалить выбранный размер экспорта?'):
            self.remember()
            self.project.formats = [f for f in self.project.formats if f['id'] != identity]
            self.project.enabled_formats = [key for key in self.project.enabled_formats if key != identity]
            self.changed(refresh=True)

    def make_preview_panel(self):
        frame = Q.QFrame()
        frame.setObjectName('preview')
        frame.setMinimumWidth(315)
        layout = Q.QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(label('Предпросмотр', 'section'))
        self.format_combo = Q.QComboBox()
        for item in self.project.formats:
            self.format_combo.addItem(self.format_title(item), item['id'])
        self.format_combo.currentIndexChanged.connect(lambda _: self.refresh_preview())
        layout.addWidget(self.format_combo)
        self.preview = Preview()
        self.preview.setToolTip('Двойной щелчок — крупный просмотр')
        self.preview.activated.connect(self.large_preview)
        layout.addWidget(self.preview, 1)
        row = Q.QHBoxLayout()
        self.page_label = label('Вся неделя · одна картинка', 'muted')
        self.page_label.setAlignment(QtCore.Qt.AlignCenter)
        row.addWidget(self.page_label, 1)
        layout.addLayout(row)
        self.preview_status = label('Подготовка макета…', 'muted')
        layout.addWidget(self.preview_status)
        self.refresh_btn = button('Обновить предпросмотр', self.refresh_preview)
        layout.addWidget(self.refresh_btn)
        layout.addWidget(button('Крупный просмотр', self.large_preview))
        return frame

    def toggle_preview_panel(self):
        self.preview_panel.setVisible(not self.preview_panel.isVisible())

    def remember(self):
        self.undo_history.append(self.project.to_dict())
        self.undo_history = self.undo_history[-100:]
        self.redo_history.clear()

    def changed(self, refresh=False):
        self.revision += 1
        if refresh:
            self.refresh_all()
        self.update_status()
        self.autosave.start()
        self.preview_status.setText('Обновляем макет…')
        self.preview_timer.start()

    def update_status(self):
        studio = self.project.style.get('studio_name', 'Богини').strip() or 'Студия'
        self.setWindowTitle(studio + ' — Студия расписаний 3.2[*]')
        self.brand_label.setText(studio.upper())
        dirty = self.project.to_dict() != self.saved
        self.state_label.setText('Сохраняем…' if dirty else 'Все изменения сохранены')
        self.setWindowModified(dirty)
        self.count_label.setText(f'{self.project.count()} занятий')
        self.update_conflicts()
        self.undo_btn.setEnabled(bool(self.undo_history))
        self.redo_btn.setEnabled(bool(self.redo_history))

    def refresh_all(self):
        self.editor_refresh.stop()
        self.move_target = None
        self.loading = True
        try:
            for day, checkbox in self.day_checks.items():
                checkbox.setChecked(day in self.project.days)
            self.training_list.clear()
            for name in sorted(self.project.trainings, key=str.casefold):
                item = Q.QListWidgetItem(name)
                self.training_list.addItem(item)
            self.filter_trainings(self.training_search.text())
            for key, field in self.style_fields.items():
                field.setText(self.project.style.get(key, ''))
            self.palette.setCurrentText(self.project.style['palette'])
            for key, slider in self.transparency_sliders.items():
                slider.setValue(self.project.style[key])
            self.refresh_settings_lists()
            self.refresh_week_controls()
            self.build_table()
        finally:
            self.loading = False
        self.update_status()

    def build_table(self):
        self.table.clear()
        self.table.setRowCount(len(self.project.times))
        self.table.setColumnCount(len(self.project.days))
        self.table.setHorizontalHeaderLabels([self.project.day_title(d) for d in self.project.days])
        self.table.setVerticalHeaderLabels(self.project.times)
        self.table.horizontalHeader().setMinimumSectionSize(145)
        self.table.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(160)
        self.cell_combos = {}
        self.cell_details = {}
        self.cell_panels = {}
        for column, day in enumerate(self.project.days):
            self.table.setColumnWidth(column, 200)
            for row, time in enumerate(self.project.times):
                cell = Q.QWidget()
                cell.setObjectName('scheduleCell')
                background = '#F7F8FC' if row % 2 == 0 else '#EFF2F8'
                cell.setStyleSheet(f'QWidget#scheduleCell {{ background: {background}; border-bottom: 3px solid #D5D9E5; }}')
                layout = Q.QVBoxLayout(cell)
                layout.setContentsMargins(6, 9, 6, 12)
                layout.setSpacing(6)
                for hall_info in self.project.halls:
                    hall = hall_info['id']
                    card = Q.QFrame(cell)
                    card.setObjectName('sessionCard')
                    card.setStyleSheet(f'QFrame#sessionCard {{ background: #FFFFFF; border: 1px solid #E1E3EB; border-left: 3px solid {hall_info["color"]}; border-radius: 9px; }}')
                    card_layout = Q.QVBoxLayout(card)
                    card_layout.setContentsMargins(9, 7, 9, 8)
                    card_layout.setSpacing(4)
                    hall_label = label(hall_info['name'])
                    hall_label.setStyleSheet('color: #756B84; font-size: 10px; font-weight: 600; background: transparent;')
                    card_layout.addWidget(hall_label)
                    combo = SessionCombo()
                    combo.setParent(card)
                    combo.setSizePolicy(Q.QSizePolicy.Ignored, Q.QSizePolicy.Fixed)
                    combo.setMinimumContentsLength(8)
                    combo.addItem('＋ Занятие', '')
                    for name in sorted(self.project.trainings, key=str.casefold):
                        combo.addItem(name, name)
                    combo.addItem('＋ Новая тренировка…', None)
                    combo.setCurrentIndex(max(0, combo.findData(self.project.get(day, time, hall))))
                    combo.setToolTip(hall_info['name'] + ' · ' + day + ' · ' + time + '\n'
                                     + (self.project.session_text(day, time, hall) or 'Нет занятия'))
                    color, border = '#FFFFFF', '#FFFFFF'
                    combo.setStyleSheet(f'QComboBox {{ background: {color}; color: #292C3E; border: 1px solid {border}; padding: 3px; font-size: 12px; font-weight: 600; }} QComboBox QAbstractItemView {{ background: #FFFFFF; color: #292C3E; selection-background-color: #E7DFF2; selection-color: #292C3E; }} QComboBox::drop-down {{ border: none; width: 16px; }}')
                    combo.currentIndexChanged.connect(
                        lambda _, d=day, t=time, h=hall, w=combo: self.assign(d, t, h, w.currentData()))
                    line = Q.QHBoxLayout()
                    line.setSpacing(3)
                    line.addWidget(combo, 1)
                    edit = Q.QToolButton()
                    edit.setText('⋯')
                    edit.setAccessibleName(f'Изменить занятие: {day}, {time}, {hall_info["name"]}')
                    edit.setToolTip('Изменить время, сведения или отменить занятие')
                    edit.clicked.connect(lambda checked=False, d=day, t=time, h=hall: self.edit_session(d, t, h))
                    line.addWidget(edit)
                    card_layout.addLayout(line)
                    self.cell_combos[(day, time, hall)] = combo
                    self.add_inline_fields(card_layout, day, time, hall)
                    layout.addWidget(card)
                layout.addStretch()
                self.table.setCellWidget(row, column, cell)
        if not self.project.trainings:
            self.statusBar().showMessage('Начните с вкладки «Тренировки» или загрузите пример в меню «Проект».')
        self.resize_time_bands()
        self.filter_rows()

    def add_inline_fields(self, layout, day, time, hall):
        panel = Q.QWidget(layout.parentWidget())
        panel.setObjectName('sessionDetails')
        panel.setStyleSheet('QWidget#sessionDetails { background: transparent; } QLineEdit, QTimeEdit, QSpinBox { padding: 5px; border: 1px solid #E3E5ED; border-radius: 6px; font-size: 11px; background: #FAFAFD; } QLabel { color: #81778D; font-size: 9px; background: transparent; } QTimeEdit::up-button, QTimeEdit::down-button, QSpinBox::up-button, QSpinBox::down-button { width: 0px; height: 0px; border: none; }')
        fields = Q.QVBoxLayout(panel)
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(5)
        detail = self.project.detail(day, time, hall)
        trainer = Q.QLineEdit(detail.get('trainer', ''), panel)
        trainer.setMaxLength(80)
        trainer.setMinimumHeight(28)
        trainer.setPlaceholderText('Тренер · имя')
        trainer.setToolTip('Только для вас' if self.project.options['trainer'] == 1 else 'Тренер · отдельная строка на картинке')
        fields.addWidget(trainer)
        trainer.setVisible(bool(self.project.options['trainer']))
        row = Q.QHBoxLayout()
        row.setSpacing(5)
        start_column = Q.QVBoxLayout()
        start_column.setSpacing(2)
        start_column.addWidget(Q.QLabel('Начало', panel))
        start = Q.QTimeEdit(QtCore.QTime.fromString(time, 'HH:mm'), panel)
        start.setDisplayFormat('HH:mm')
        start.setKeyboardTracking(False)
        start.setMinimumWidth(48)
        start.setMinimumHeight(28)
        start.setToolTip('Время начала · Enter или выход из поля применяет перенос')
        start_column.addWidget(start)
        row.addLayout(start_column, 1)
        duration_column = Q.QVBoxLayout()
        duration_column.setSpacing(2)
        duration_label = Q.QLabel('Длительность', panel)
        duration = Q.QSpinBox(panel)
        duration.setRange(0, 720)
        duration.setKeyboardTracking(False)
        duration.setSpecialValueText('—')
        duration.setSuffix(' мин')
        duration.setValue(detail.get('duration', 0))
        duration.setMinimumWidth(48)
        duration.setMinimumHeight(28)
        for control in (start, duration):
            control.lineEdit().setStyleSheet('border: none; background: transparent; padding: 0px;')
            control.lineEdit().setTextMargins(5, 0, 2, 0)
        duration.setToolTip('Длительность · только для вас' if self.project.options['duration'] == 1 else 'Длительность · отдельная строка на картинке')
        duration_column.addWidget(duration_label)
        duration_column.addWidget(duration)
        row.addLayout(duration_column, 1)
        duration_label.setVisible(bool(self.project.options['duration']))
        duration.setVisible(bool(self.project.options['duration']))
        fields.addLayout(row)
        layout.addWidget(panel)
        enabled = bool(self.project.get(day, time, hall))
        panel.setVisible(enabled)
        for widget in (trainer, start, duration):
            widget.setEnabled(enabled)
        trainer.editingFinished.connect(lambda: self.save_inline_detail(day, time, hall, trainer.text(), duration.value()))
        duration.editingFinished.connect(lambda: self.save_inline_detail(day, time, hall, trainer.text(), duration.value()))
        start.editingFinished.connect(lambda: self.move_inline_session(day, time, hall, start.time().toString('HH:mm')))
        self.cell_details[(day, time, hall)] = (trainer, duration, start)
        self.cell_panels[(day, time, hall)] = panel

    def resize_time_bands(self):
        for row, time in enumerate(self.project.times):
            height = 20
            for hall in self.project.hall_ids:
                occupied = any(self.project.get(day, time, hall) for day in self.project.days)
                height += (164 if self.project.options['trainer'] else 132) if occupied else 76
            self.table.setRowHeight(row, height)

    def finish_inline_move(self):
        target = self.move_target
        self.move_target = None
        self.refresh_all()
        if target:
            day, time = target
            if day in self.project.days and time in self.project.times:
                index = self.table.model().index(self.project.times.index(time), self.project.days.index(day))
                self.table.setCurrentIndex(index)
                self.table.scrollTo(index, Q.QAbstractItemView.PositionAtCenter)

    def filter_rows(self):
        for row, time in enumerate(self.project.times):
            empty = not any(self.project.get(day, time, hall)
                            for day in self.project.days for hall in self.project.hall_ids)
            self.table.setRowHidden(row, self.hide_empty.isChecked() and empty)

    def assign(self, day, time, hall, name):
        if not self.loading and name is None:
            combo = self.cell_combos[(day, time, hall)]
            blocker = QtCore.QSignalBlocker(combo)
            combo.setCurrentIndex(max(0, combo.findData(self.project.get(day, time, hall))))
            del blocker
            self.edit_session(day, time, hall)
            return
        if self.loading or self.project.get(day, time, hall) == (name or ''):
            return
        self.remember()
        self.project.set(day, time, hall, name)
        combo = self.cell_combos[(day, time, hall)]
        combo.setToolTip(f'{self.project.hall(hall)["name"]} · {day} · {time}\n{name or "Нет занятия"}')
        for widget in self.cell_details[(day, time, hall)]:
            widget.setEnabled(bool(name))
        trainer, duration, start = self.cell_details[(day, time, hall)]
        trainer.setText('')
        duration.setValue(0)
        self.cell_panels[(day, time, hall)].setVisible(bool(name))
        self.resize_time_bands()
        self.changed()

    def change_style(self, key, value, refresh=False):
        if self.loading or self.project.style.get(key) == value:
            return
        self.remember()
        self.project.style[key] = value
        self.changed(refresh)

    def pick_asset(self, key):
        path, _ = Q.QFileDialog.getOpenFileName(self, 'Выберите изображение', '', 'Изображения (*.png *.jpg *.jpeg *.webp)')
        if path:
            self.change_style(key, path, refresh=True)

    def reset_old_backgrounds(self):
        self.remember()
        for key in ('bg_story', 'bg_post', 'bg_a4'):
            self.project.style[key] = ''
        self.changed()

    def toggle_day(self, day, checked):
        if self.loading:
            return
        if not checked and len(self.project.days) == 1:
            self.loading = True
            self.day_checks[day].setChecked(True)
            self.loading = False
            self.statusBar().showMessage('Нужен хотя бы один видимый день.', 4000)
            return
        self.remember()
        selected = set(self.project.days)
        selected.add(day) if checked else selected.discard(day)
        self.project.days = [d for d in ALL_DAYS if d in selected]
        self.changed(refresh=True)

    def add_time(self):
        time = self.time_input.time().toString('HH:mm')
        if time in self.project.times:
            self.table.selectRow(self.project.times.index(time))
            self.statusBar().showMessage('Это время уже есть в расписании.', 4000)
            return
        self.remember()
        self.project.times = sorted(self.project.times + [time])
        self.hide_empty.setChecked(False)
        self.changed(refresh=True)

    def delete_time(self):
        row = self.table.currentRow()
        if row < 0 and self.table.selectedRanges():
            row = self.table.selectedRanges()[0].topRow()
        if row < 0:
            self.statusBar().showMessage('Сначала выберите строку времени в таблице.', 4000)
            return
        if len(self.project.times) == 1:
            Q.QMessageBox.information(self, 'Время', 'Оставьте хотя бы один временной слот.')
            return
        time = self.project.times[row]
        if not self.confirm('Удалить время?', f'Удалить {time} и все занятия в этой строке, включая скрытые дни?'):
            return
        self.remember()
        self.project.times.remove(time)
        for collection in (self.project.schedule, self.project.details):
            for slots in collection.values():
                slots.pop(time, None)
        self.changed(refresh=True)

    def filter_trainings(self, text):
        for index in range(self.training_list.count()):
            item = self.training_list.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())

    def ask_name(self, initial=''):
        name, ok = Q.QInputDialog.getText(self, 'Тренировка', 'Название (до 120 символов):', text=initial)
        name = ' '.join(name.split())
        if not ok or not name:
            return None
        if len(name) > 120:
            Q.QMessageBox.warning(self, 'Слишком длинное название', 'Используйте до 120 символов.')
            return None
        if name != initial and any(n.casefold() == name.casefold() for n in self.project.trainings):
            Q.QMessageBox.warning(self, 'Тренировка', 'Такое название уже есть.')
            return None
        return name

    def add_training(self):
        name = self.ask_name()
        if name:
            self.remember()
            self.project.trainings.append(name)
            self.changed(refresh=True)

    def edit_training(self):
        item = self.training_list.currentItem()
        if item:
            name = self.ask_name(item.text())
            if name and name != item.text():
                self.remember()
                self.project.rename(item.text(), name)
                self.changed(refresh=True)

    def delete_training(self):
        item = self.training_list.currentItem()
        if item and self.confirm('Удалить тренировку?', f'«{item.text()}» будет удалена из библиотеки и всех дней расписания. Действие можно отменить.'):
            self.remember()
            self.project.remove_training(item.text())
            self.changed(refresh=True)

    def copy_day(self):
        dialog = Q.QDialog(self)
        dialog.setWindowTitle('Копировать день')
        form = Q.QFormLayout(dialog)
        source, target = Q.QComboBox(), Q.QComboBox()
        source.addItems(ALL_DAYS)
        target.addItems(ALL_DAYS)
        target.setCurrentIndex(1)
        form.addRow('Откуда', source)
        form.addRow('Куда', target)
        form.addRow(label('Все занятия выбранного дня назначения будут заменены.', 'muted'))
        buttons = Q.QDialogButtonBox(Q.QDialogButtonBox.Ok | Q.QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == Q.QDialog.Accepted and source.currentText() != target.currentText():
            self.remember()
            self.project.schedule[target.currentText()] = copy.deepcopy(self.project.schedule.get(source.currentText(), {}))
            self.project.details[target.currentText()] = copy.deepcopy(self.project.details.get(source.currentText(), {}))
            self.changed(refresh=True)

    def clear_week(self):
        if self.confirm('Очистить выбранное расписание?', 'Удалить занятия из текущей сетки? В режиме месяца это изменит повторяющееся расписание выбранного месяца. Другие месяцы, отдельные недели и библиотека тренировок останутся. Действие можно отменить.'):
            self.remember()
            self.project.schedule.clear()
            self.project.details.clear()
            self.changed(refresh=True)

    def undo(self):
        if self.undo_history:
            self.redo_history.append(self.project.to_dict())
            self.project = Project.from_dict(self.undo_history.pop())
            self.changed(refresh=True)

    def redo(self):
        if self.redo_history:
            self.undo_history.append(self.project.to_dict())
            self.project = Project.from_dict(self.redo_history.pop())
            self.changed(refresh=True)

    def save(self, checked=False, quiet=False):
        self.autosave.stop()
        if quiet and self.project.to_dict() == self.saved:
            return True
        try:
            self.store.save(self.project)
        except OSError as error:
            self.state_label.setText('Не удалось сохранить')
            self.statusBar().showMessage(str(error))
            if not quiet:
                Q.QMessageBox.critical(self, 'Ошибка сохранения', str(error))
            return False
        self.saved = self.project.to_dict()
        self.update_status()
        if not quiet:
            self.statusBar().showMessage('Проект сохранён.', 4000)
        return True

    def confirm(self, title, text):
        return Q.QMessageBox.question(self, title, text, Q.QMessageBox.Yes | Q.QMessageBox.No,
                                     Q.QMessageBox.No) == Q.QMessageBox.Yes

    def backup_project(self):
        path, _ = Q.QFileDialog.getSaveFileName(self, 'Сохранить копию проекта', re.sub(r'[\\/:*?"<>|]', '_', self.project.style.get('studio_name', 'Студия')) + '-расписание.json', 'Проект (*.json)')
        if path:
            try:
                atomic_json(Path(path), self.project.to_dict())
                self.statusBar().showMessage('Копия проекта сохранена.', 5000)
            except OSError as error:
                Q.QMessageBox.critical(self, 'Ошибка', str(error))

    def open_project(self):
        path, _ = Q.QFileDialog.getOpenFileName(self, 'Открыть проект', '', 'Проект (*.json)')
        if path:
            try:
                project = Project.from_dict(read_json(Path(path)))
                self.replace_project(project)
            except (OSError, ValueError) as error:
                Q.QMessageBox.critical(self, 'Ошибка открытия', str(error))

    def import_legacy(self):
        folder = Q.QFileDialog.getExistingDirectory(self, 'Папка с trainings.json, settings.json и schedule.json')
        if folder:
            try:
                if not any((Path(folder) / name).exists() for name in ('settings.json', 'schedule.json', 'trainings.json')):
                    raise ValueError('В выбранной папке нет файлов старого расписания.')
                self.replace_project(migrate_legacy(Path(folder)))
            except (OSError, ValueError) as error:
                Q.QMessageBox.critical(self, 'Ошибка импорта', str(error))

    def replace_project(self, project):
        if self.confirm('Заменить текущий проект?', 'Открываемый проект заменит текущее расписание. Можно отменить через Ctrl+Z. Для отдельной копии используйте меню «Проект».'):
            self.remember()
            self.project = project
            self.changed(refresh=True)

    def open_data_folder(self):
        self.store.directory.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.store.directory)))

    def load_demo(self):
        from demo import demo_project
        self.replace_project(demo_project())

    def refresh_preview(self):
        if self.job is not None:
            return
        self.preview_timer.stop()
        self.start_render([self.format_combo.currentData()])

    def start_render(self, variants, directory=None, kind='PNG'):
        if self.job is not None:
            return
        self.job_revision = self.revision
        self.job_format = self.format_combo.currentData()
        self.job = RenderJob(self.project, variants, directory, kind, self)
        self.refresh_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.preview_status.setText('Готовим картинки…' if directory else 'Обновляем макет…')
        self.job.succeeded.connect(self.render_ready)
        self.job.failed.connect(self.render_failed)
        self.job.finished.connect(self.render_finished)
        self.job.start()

    def render_ready(self, result):
        images, paths = result
        if self.job_revision == self.revision and self.job_format == self.format_combo.currentData():
            current = self.format_combo.currentData()
            if current in images:
                self.images, self.page = images[current], 0
                self.show_page()
                self.preview_status.setText('Макет актуален · вся неделя на одной картинке')
        if paths:
            Q.QMessageBox.information(self, 'Экспорт готов', f'Сохранено файлов: {len(paths)}\nПапка: {Path(paths[0]).parent}')

    def render_failed(self, error):
        self.preview_status.setText('Не удалось подготовить макет')
        Q.QMessageBox.warning(self, 'Ошибка макета', error)

    def render_finished(self):
        stale = self.job_revision != self.revision or self.job_format != self.format_combo.currentData()
        self.job.deleteLater()
        self.job = None
        self.refresh_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        if stale:
            self.preview_timer.start()

    def show_page(self):
        if self.images:
            self.preview.set_image(self.images[self.page])
            self.page_label.setText('Вся неделя · одна картинка')

    def turn_page(self, direction):
        if self.images:
            self.page = (self.page + direction) % len(self.images)
            self.show_page()

    def large_preview(self):
        if not self.images:
            return
        images = self.images[:]
        dialog = Q.QDialog(self)
        dialog.setWindowTitle('Расписание — крупный просмотр')
        dialog.resize(1040, 850)
        layout = Q.QVBoxLayout(dialog)
        scroll = Q.QScrollArea()
        scroll.setAlignment(QtCore.Qt.AlignCenter)
        image_label = Q.QLabel()
        scroll.setWidget(image_label)
        layout.addWidget(scroll, 1)
        tools = Q.QHBoxLayout()
        page = [self.page]
        count = label('', 'muted')
        zoom = Q.QSlider(QtCore.Qt.Horizontal)
        zoom.setRange(25, 100)
        zoom.setValue(75 if images[page[0]].width < 2000 else 25)
        def update():
            source = QtGui.QPixmap.fromImage(ImageQt(images[page[0]]))
            scaled = source.scaledToWidth(round(source.width() * zoom.value() / 100), QtCore.Qt.SmoothTransformation)
            image_label.setPixmap(scaled)
            image_label.resize(scaled.size())
            count.setText(f'{page[0] + 1} / {len(images)} · {zoom.value()}%')
        def turn(direction):
            page[0] = (page[0] + direction) % len(images)
            update()
        tools.addWidget(button('←', lambda: turn(-1)))
        tools.addWidget(count)
        tools.addWidget(button('→', lambda: turn(1)))
        tools.addWidget(zoom, 1)
        tools.addWidget(button('Закрыть', dialog.accept))
        zoom.valueChanged.connect(lambda _: update())
        layout.addLayout(tools)
        update()
        dialog.exec()

    def export_dialog(self):
        if self.job is not None:
            return
        dialog = Q.QDialog(self)
        dialog.setWindowTitle('Экспорт расписания')
        layout = Q.QFormLayout(dialog)
        layout.addRow(label('Отметьте нужные форматы', 'section'))
        checks = {}
        formats_area = Q.QScrollArea()
        formats_area.setWidgetResizable(True)
        formats_area.setMaximumHeight(320)
        formats_area.setMinimumHeight(110)
        choices = Q.QWidget()
        choices_layout = Q.QVBoxLayout(choices)
        for item in self.project.formats:
            checkbox = Q.QCheckBox(self.format_title(item))
            checkbox.setChecked(item['id'] in self.project.enabled_formats)
            checks[item['id']] = checkbox
            choices_layout.addWidget(checkbox)
        formats_area.setWidget(choices)
        layout.addRow(formats_area)
        kind = Q.QComboBox()
        kind.addItems(['PNG', 'JPEG'])
        layout.addRow('Тип файла', kind)
        layout.addRow(label('Каждый выбранный формат — одна картинка со всей неделей.\nНеотмеченные форматы не создаются.\nОдноимённые файлы будут заменены.', 'muted'))
        controls = Q.QDialogButtonBox(Q.QDialogButtonBox.Ok | Q.QDialogButtonBox.Cancel)
        def accept():
            if not any(checkbox.isChecked() for checkbox in checks.values()):
                Q.QMessageBox.warning(dialog, 'Выберите форматы', 'Отметьте хотя бы один формат.')
                return
            dialog.accept()
        controls.accepted.connect(accept)
        controls.rejected.connect(dialog.reject)
        layout.addRow(controls)
        if dialog.exec() == Q.QDialog.Accepted:
            variants = [key for key, checkbox in checks.items() if checkbox.isChecked()]
            directory = Q.QFileDialog.getExistingDirectory(self, 'Папка для картинок расписания')
            if directory:
                if variants != self.project.enabled_formats:
                    self.remember()
                    self.project.enabled_formats = variants
                    self.changed()
                self.start_render(variants, directory, kind.currentText())

    def closeEvent(self, event):
        if self.job is not None:
            self.statusBar().showMessage('Дождитесь завершения подготовки картинок перед выходом.', 5000)
            event.ignore()
            return
        if self.project.to_dict() != self.saved and not self.save(quiet=True):
            answer = Q.QMessageBox.question(self, 'Есть несохранённые изменения',
                'Сохранить проект не удалось. Всё равно выйти? Для сохранения копии отмените выход и откройте меню «Проект».',
                Q.QMessageBox.Discard | Q.QMessageBox.Cancel, Q.QMessageBox.Cancel)
            if answer != Q.QMessageBox.Discard:
                event.ignore()
                return
        self.autosave.stop()
        self.preview_timer.stop()
        self.editor_refresh.stop()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description='Студия расписаний — редактор для фитнес-студии')
    parser.add_argument('--export-demo', type=Path, metavar='ПАПКА', help='Сохранить примеры всех форматов без изменения вашего проекта')
    arguments = parser.parse_args()
    if arguments.export_demo:
        from demo import demo_project
        try:
            images = {variant: render(demo_project(), variant) for variant in FORMATS}
            for variant in FORMATS:
                save_images(images[variant], arguments.export_demo, variant)
        except (OSError, ValueError) as error:
            print(error, file=sys.stderr)
            return 1
        return 0
    app = Q.QApplication(sys.argv)
    app.setOrganizationName(APP_ORG)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName('Студия расписаний')
    app.setApplicationVersion('3.2.0')
    app.setStyle('Fusion')
    app.setPalette(light_palette())
    try:
        window = MainWindow()
    except (OSError, ValueError) as error:
        Q.QMessageBox.critical(None, 'Не удалось открыть расписание',
            f'{error}\n\nФайлы оставлены без изменений. Проверьте папку данных приложения.')
        return 1
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())

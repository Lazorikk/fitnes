"""Project format, legacy migration and safe local persistence."""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import tempfile
import uuid

from colors import valid_color
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QStandardPaths

APP_ORG = 'Bogini'
APP_ID = 'BoginiSchedule'
ALL_DAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
DEFAULT_TIMES = ['09:00', '10:00', '11:00', '12:00', '16:00', '17:00', '17:30', '18:30', '19:30']
# Legacy keys are kept so both halls migrate without swapping assignments.
HALLS = ['Большой зал', 'Малый зал']
HALL_LABELS = ['Зелёный зал', 'Фиолетовый зал']
HALL_COLORS = ['#B9ED83', '#C6B5F4']
DEFAULT_STYLE = {
    'title': 'Расписание занятий', 'subtitle': 'Женский фитнес-центр «Богини»',
    'studio_name': 'Богини',
    'period': '', 'contact': '', 'palette': 'Светлый', 'logo_path': '',
    'bg_common': '', 'bg_story': '', 'bg_post': '', 'bg_a4': '',
    'bg_transparency': 8, 'panel_transparency': 0,
}


DEFAULT_FORMATS = [
    {'id': 'story', 'name': 'Сторис', 'width': 1080, 'height': 1920, 'dpi': 96},
    {'id': 'post', 'name': 'Пост ВК', 'width': 1080, 'height': 1350, 'dpi': 96},
    {'id': 'a4', 'name': 'A4 для печати', 'width': 3508, 'height': 2480, 'dpi': 300},
]


def default_halls():
    return [{'id': key, 'name': name, 'color': color}
            for key, name, color in zip(HALLS, HALL_LABELS, HALL_COLORS)]


def validate_format(name, width, height, dpi):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
        raise ValueError('Название формата должно содержать от 1 до 60 символов.')
    if any(type(value) is not int for value in (width, height, dpi)):
        raise ValueError('Размеры и DPI должны быть целыми числами.')
    if not (320 <= width <= 8000 and 320 <= height <= 8000) or width * height > 40_000_000:
        raise ValueError('Размер: 320–8000 пикселей по стороне, не более 40 мегапикселей.')
    if not 72 <= dpi <= 600:
        raise ValueError('DPI: от 72 до 600.')


def valid_time(value):
    return isinstance(value, str) and re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', value) is not None


def atomic_json(path: Path, value):
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass
class Project:
    trainings: list[str] = field(default_factory=list)
    days: list[str] = field(default_factory=lambda: ALL_DAYS[:6])
    times: list[str] = field(default_factory=lambda: DEFAULT_TIMES[:])
    schedule: dict = field(default_factory=dict)
    style: dict = field(default_factory=lambda: dict(DEFAULT_STYLE))

    halls: list[dict] = field(default_factory=default_halls)
    formats: list[dict] = field(default_factory=lambda: copy.deepcopy(DEFAULT_FORMATS))
    enabled_formats: list[str] = field(default_factory=lambda: [f['id'] for f in DEFAULT_FORMATS])

    @property
    def hall_ids(self):
        return [hall['id'] for hall in self.halls]

    def hall(self, identity):
        return next(hall for hall in self.halls if hall['id'] == identity)

    def format(self, identity):
        return next(item for item in self.formats if item['id'] == identity)

    def add_hall(self, name, color):
        self.validate_hall(name, color)
        if len(self.halls) >= 12:
            raise ValueError('Можно добавить до 12 залов.')
        hall = {'id': 'hall_' + uuid.uuid4().hex, 'name': name.strip(), 'color': color.upper()}
        self.halls.append(hall)
        return hall['id']

    def validate_hall(self, name, color, identity=None):
        if not name.strip() or len(name.strip()) > 40:
            raise ValueError('Название зала: от 1 до 40 символов.')
        if not valid_color(color):
            raise ValueError('Цвет должен быть в формате #RRGGBB.')
        if any(h['id'] != identity and h['name'].casefold() == name.strip().casefold() for h in self.halls):
            raise ValueError('Зал с таким названием уже есть.')

    def update_hall(self, identity, name, color):
        self.validate_hall(name, color, identity)
        self.hall(identity).update(name=name.strip(), color=color.upper())

    def remove_hall(self, identity):
        if len(self.halls) == 1:
            raise ValueError('Нужен хотя бы один зал.')
        self.halls = [hall for hall in self.halls if hall['id'] != identity]
        for slots in self.schedule.values():
            for halls in slots.values():
                halls.pop(identity, None)

    def add_format(self, name, width, height, dpi=96):
        validate_format(name, width, height, dpi)
        if len(self.formats) >= 20:
            raise ValueError('Можно добавить до 20 форматов.')
        if any(item['name'].casefold() == name.strip().casefold() for item in self.formats):
            raise ValueError('Формат с таким названием уже есть.')
        identity = 'custom_' + uuid.uuid4().hex
        self.formats.append({'id': identity, 'name': name.strip(), 'width': width, 'height': height, 'dpi': dpi})
        self.enabled_formats.append(identity)
        return identity

    def to_dict(self):
        return copy.deepcopy({'version': 3, 'trainings': self.trainings, 'days': self.days,
                              'times': self.times, 'schedule': self.schedule, 'style': self.style,
                              'halls': self.halls, 'formats': self.formats, 'enabled_formats': self.enabled_formats})

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get('version') not in (2, 3):
            raise ValueError('Поддерживаются проекты студии расписаний версий 2 и 3.')
        for key in ('trainings', 'days', 'times'):
            if not isinstance(data.get(key), list) or not all(isinstance(x, str) for x in data[key]):
                raise ValueError(f'Некорректное поле проекта: {key}.')
        if not data['days'] or any(day not in ALL_DAYS for day in data['days']):
            raise ValueError('В проекте должны быть выбраны дни недели.')
        if not data['times'] or not all(valid_time(t) for t in data['times']):
            raise ValueError('Некорректное время. Используйте ЧЧ:ММ.')
        if not isinstance(data.get('schedule'), dict) or not isinstance(data.get('style'), dict):
            raise ValueError('Некорректное расписание или оформление.')
        project = cls(trainings=list(dict.fromkeys(t.strip() for t in data['trainings'] if t.strip())),
                      days=[d for d in ALL_DAYS if d in data['days']], times=sorted(set(data['times'])))
        halls = data.get('halls', default_halls())
        if not isinstance(halls, list) or not 1 <= len(halls) <= 12:
            raise ValueError('В проекте должно быть от 1 до 12 залов.')
        project.halls = []
        for hall in halls:
            if (not isinstance(hall, dict) or not isinstance(hall.get('id'), str)
                    or not hall['id'] or hall['id'] in project.hall_ids
                    or not isinstance(hall.get('name'), str)):
                raise ValueError('Некорректный зал или повторяющийся идентификатор.')
            project.validate_hall(hall['name'], hall.get('color'))
            project.halls.append({'id': hall['id'], 'name': hall['name'].strip(), 'color': hall['color'].upper()})
        formats = data.get('formats', copy.deepcopy(DEFAULT_FORMATS))
        if not isinstance(formats, list) or not 1 <= len(formats) <= 20:
            raise ValueError('В проекте должно быть от 1 до 20 форматов.')
        project.formats = []
        for item in formats:
            if (not isinstance(item, dict) or not isinstance(item.get('id'), str)
                    or re.fullmatch(r'[A-Za-z0-9_-]+', item['id']) is None
                    or item['id'] in [f['id'] for f in project.formats]):
                raise ValueError('Некорректный идентификатор формата.')
            validate_format(item.get('name'), item.get('width'), item.get('height'), item.get('dpi'))
            project.formats.append({key: item[key] for key in ('id', 'name', 'width', 'height', 'dpi')})
        enabled = data.get('enabled_formats', [f['id'] for f in project.formats])
        if (not isinstance(enabled, list) or not all(isinstance(key, str) for key in enabled)
                or any(key not in [f['id'] for f in project.formats] for key in enabled)):
            raise ValueError('Некорректный выбор форматов.')
        project.enabled_formats = list(dict.fromkeys(enabled))
        for day, slots in data['schedule'].items():
            if day not in ALL_DAYS or not isinstance(slots, dict):
                raise ValueError('Некорректный день в расписании.')
            for time, halls in slots.items():
                if not valid_time(time) or not isinstance(halls, dict):
                    raise ValueError('Некорректная ячейка расписания.')
                for hall, name in halls.items():
                    if hall not in project.hall_ids or (name is not None and not isinstance(name, str)):
                        raise ValueError('Некорректное назначение тренировки.')
                    if name and name.strip():
                        project.set(day, time, hall, name.strip())
                        if time not in project.times:
                            project.times.append(time)
                        if name.strip() not in project.trainings:
                            project.trainings.append(name.strip())
        project.times.sort()
        for key, default in DEFAULT_STYLE.items():
            value = data['style'].get(key, default)
            if type(default) is int:
                project.style[key] = value if type(value) is int and 0 <= value <= 100 else default
            else:
                project.style[key] = value if isinstance(value, str) else default
        if project.style['palette'] not in ('Светлый', 'Тёмный'):
            project.style['palette'] = 'Светлый'
        return project

    def get(self, day, time, hall):
        return self.schedule.get(day, {}).get(time, {}).get(hall) or ''

    def set(self, day, time, hall, name):
        self.schedule.setdefault(day, {}).setdefault(time, {})[hall] = name or None

    def count(self):
        return sum(bool(self.get(d, t, h)) for d in self.days for t in self.times for h in self.hall_ids)

    def rename(self, old, new):
        if new in self.trainings and old != new:
            raise ValueError('Такая тренировка уже есть.')
        self.trainings = [new if name == old else name for name in self.trainings]
        for slots in self.schedule.values():
            for halls in slots.values():
                for hall in self.hall_ids:
                    if halls.get(hall) == old:
                        halls[hall] = new

    def remove_training(self, name):
        self.trainings.remove(name)
        for slots in self.schedule.values():
            for halls in slots.values():
                for hall in self.hall_ids:
                    if halls.get(hall) == name:
                        halls[hall] = None


def data_dir():
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def migrate_legacy(folder):
    settings = read_json(folder / 'settings.json') if (folder / 'settings.json').exists() else {}
    raw_trainings = read_json(folder / 'trainings.json') if (folder / 'trainings.json').exists() else []
    raw_schedule = read_json(folder / 'schedule.json') if (folder / 'schedule.json').exists() else {}
    if not isinstance(settings, dict) or not isinstance(raw_trainings, list) or not isinstance(raw_schedule, dict):
        raise ValueError('Не удалось прочитать структуру данных старой программы.')
    names = [t.get('name') if isinstance(t, dict) else t for t in raw_trainings]
    days = settings.get('days', ALL_DAYS[:6])
    times = settings.get('times', DEFAULT_TIMES[:])
    normalized = {}
    for day, slots in raw_schedule.items():
        if isinstance(slots, dict):
            normalized[day] = {t: {HALLS[0]: cell} if isinstance(cell, str) else cell
                               for t, cell in slots.items() if cell is not None}
    return Project.from_dict({'version': 2, 'trainings': [n for n in names if isinstance(n, str)],
                              'days': days, 'times': times, 'schedule': normalized, 'style': settings})


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_dir()
        self.path = self.directory / 'project-v2.json'
        self.backup = self.directory / 'project-v2.backup.json'

    def load(self):
        if self.path.exists():
            try:
                return Project.from_dict(read_json(self.path)), ''
            except (OSError, ValueError) as error:
                if self.backup.exists():
                    project = Project.from_dict(read_json(self.backup))
                    return project, f'Основной файл не читается ({error}). Открыта резервная копия. Сохраните проект.'
                raise ValueError(f'Не удалось открыть {self.path}: {error}') from error
        app_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
        for folder in (self.directory, app_dir / 'data'):
            if any((folder / name).exists() for name in ('settings.json', 'schedule.json', 'trainings.json')):
                return migrate_legacy(folder), 'Данные прежней программы открыты. Сохраните проект в новом формате; старые файлы останутся на месте.'
        return Project(), ''

    def save(self, project):
        if self.path.exists():
            try:
                previous = read_json(self.path)
                Project.from_dict(previous)
            except (OSError, ValueError):
                pass  # A damaged main file must never replace a good backup.
            else:
                atomic_json(self.backup, previous)
        atomic_json(self.path, project.to_dict())

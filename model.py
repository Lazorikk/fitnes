"""Project format, legacy migration and safe local persistence."""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import tempfile
import uuid
import calendar
from datetime import date, timedelta

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

    # The active schedule remains compatible with the original editor and renderer.
    active_week: str = ''
    active_month: str = ''
    months: dict = field(default_factory=dict)
    week_sources: dict = field(default_factory=dict)
    template: dict = field(default_factory=dict)
    weeks: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)
    options: dict = field(default_factory=lambda: {'trainer': 0, 'duration': 0})

    def week_state(self):
        return copy.deepcopy({key: getattr(self, key) for key in ('schedule', 'details', 'times', 'days')})

    @staticmethod
    def monday(value):
        day = date.fromisoformat(value) if isinstance(value, str) else value
        return (day - timedelta(days=day.weekday())).isoformat()

    @staticmethod
    def month_key(value):
        day = date.fromisoformat(value) if isinstance(value, str) else value
        return day.replace(day=1).isoformat()

    def retain_active(self):
        if self.active_week:
            self.weeks[self.active_week] = self.week_state()
        elif self.active_month:
            self.months[self.active_month] = self.week_state()
        else:
            self.template = self.week_state()

    def load_state(self, state):
        for name, value in state.items():
            setattr(self, name, copy.deepcopy(value))

    def switch_week(self, key):
        requested_month = self.month_key(key) if key else ''
        key = self.monday(key) if key else ''
        if key == self.active_week and not self.active_month:
            return
        self.retain_active()
        source = self.months.get(requested_month, self.template)
        if key and key not in self.weeks and requested_month in self.months:
            self.week_sources[key] = requested_month
        self.load_state(self.weeks.get(key, source) if key else self.template)
        self.active_week, self.active_month = key, ''

    def switch_month(self, key, copy_current=False):
        key = self.month_key(key)
        if key == self.active_month:
            return
        current = self.week_state()
        self.retain_active()
        self.load_state(current if copy_current else self.months.get(key, self.template))
        self.active_month, self.active_week = key, ''

    def replace_week(self, previous=False):
        if not self.active_week:
            raise ValueError('Сначала выберите неделю по дате.')
        key = (date.fromisoformat(self.active_week) - timedelta(days=7)).isoformat()
        if previous and key not in self.weeks:
            raise ValueError('Предыдущая неделя ещё не сохранена. Откройте её или используйте шаблон.')
        baseline = self.months.get(self.week_sources.get(self.active_week), self.template)
        state = self.weeks[key] if previous else baseline
        for name, value in state.items():
            setattr(self, name, copy.deepcopy(value))

    def detail(self, day, time, hall):
        return self.details.get(day, {}).get(time, {}).get(hall, {})

    def set_detail(self, day, time, hall, trainer='', duration=0):
        if not isinstance(trainer, str) or len(trainer) > 80 or type(duration) is not int or not 0 <= duration <= 720:
            raise ValueError('Тренер: до 80 символов. Длительность: до 720 минут.')
        self.details.setdefault(day, {}).setdefault(time, {})[hall] = {'trainer': trainer.strip(), 'duration': duration}

    def session_text(self, day, time, hall):
        name = self.get(day, time, hall)
        if not name:
            return ''
        detail = self.detail(day, time, hall)
        extra = []
        if self.options['trainer'] == 2 and detail.get('trainer'):
            extra.append(detail['trainer'])
        if self.options['duration'] == 2 and detail.get('duration'):
            extra.append(str(detail['duration']) + ' мин')
        return '\n'.join([name, *extra])

    def period_text(self):
        if self.active_month:
            start = date.fromisoformat(self.active_month)
            end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
            return f'{start:%d.%m.%Y} — {end:%d.%m.%Y} · каждую неделю'
        if not self.active_week:
            return self.style.get('period', '')
        start = date.fromisoformat(self.active_week)
        return f'{start:%d.%m.%Y} — {start + timedelta(days=6):%d.%m.%Y}'

    def day_title(self, day):
        if not self.active_week:
            return day
        value = date.fromisoformat(self.active_week) + timedelta(days=ALL_DAYS.index(day))
        return f'{day} {value:%d.%m}'

    def publication_text(self):
        lines = [self.style.get('studio_name', '').strip() or 'Наша студия',
                 'Расписание занятий' + (' · ' + self.period_text() if self.period_text() else '')]
        for day in self.days:
            sessions = []
            for time in self.times:
                for hall in self.hall_ids:
                    text = self.session_text(day, time, hall)
                    if text:
                        suffix = ' · ' + self.hall(hall)['name'] if len(self.halls) > 1 else ''
                        title, *metadata = text.split('\n')
                        sessions.append(f'{time} — {title}{suffix}')
                        sessions.extend('    ' + line for line in metadata)
            if sessions:
                lines.extend(['', self.day_title(day), *sessions])
        if self.style.get('contact', '').strip():
            lines.extend(['', self.style['contact'].strip()])
        return '\n'.join(lines)

    def conflicts(self):
        warnings = []
        for day in self.days:
            sessions = [(t, h, self.get(day, t, h), self.detail(day, t, h))
                        for t in self.times for h in self.hall_ids if self.get(day, t, h)]
            for index, (time, hall, name, detail) in enumerate(sessions):
                start = int(time[:2]) * 60 + int(time[3:])
                for other_time, other_hall, other_name, other in sessions[index + 1:]:
                    other_start = int(other_time[:2]) * 60 + int(other_time[3:])
                    same_trainer = (self.options['trainer'] > 0 and detail.get('trainer', '').strip()
                                    and detail['trainer'].casefold() == other.get('trainer', '').casefold())
                    duration = detail.get('duration', 0) if self.options['duration'] else 0
                    other_duration = other.get('duration', 0) if self.options['duration'] else 0
                    overlap = (start == other_start or
                               (start < other_start + max(other_duration, 1)
                                and other_start < start + max(duration, 1)))
                    if overlap and (hall == other_hall or same_trainer):
                        reason = self.hall(hall)['name'] if hall == other_hall else 'тренер ' + detail['trainer']
                        warnings.append(f'{day}: {time} «{name}» и {other_time} «{other_name}» — {reason}.')
        return warnings

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
        for state in [self.week_state(), self.template, *self.weeks.values(), *self.months.values()]:
            for slots in state.get('schedule', {}).values():
                for halls in slots.values():
                    halls.pop(identity, None)
            for slots in state.get('details', {}).values():
                for halls in slots.values():
                    halls.pop(identity, None)
        for slots in self.schedule.values():
            for halls in slots.values():
                halls.pop(identity, None)
        for slots in self.details.values():
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
        return copy.deepcopy({'version': 5, 'trainings': self.trainings, 'days': self.days,
                              'times': self.times, 'schedule': self.schedule, 'style': self.style,
                              'halls': self.halls, 'formats': self.formats, 'enabled_formats': self.enabled_formats,
                              'active_week': self.active_week, 'active_month': self.active_month, 'months': self.months,
                              'week_sources': self.week_sources, 'template': self.template,
                              'weeks': self.weeks, 'details': self.details, 'options': self.options})

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get('version') not in (2, 3, 4, 5):
            raise ValueError('Поддерживаются проекты студии расписаний версий 2–5.')
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
        options = data.get('options', {'trainer': 0, 'duration': 0})
        if not isinstance(options, dict) or any(type(options.get(k)) is not int or options[k] not in (0, 1, 2) for k in ('trainer', 'duration')):
            raise ValueError('Некорректные настройки дополнительных полей.')
        project.options = dict(options)
        details = data.get('details', {})
        if not isinstance(details, dict):
            raise ValueError('Некорректные сведения о занятиях.')
        for day, slots in details.items():
            if day not in ALL_DAYS or not isinstance(slots, dict):
                raise ValueError('Некорректные сведения о дне.')
            for time, halls in slots.items():
                if not valid_time(time) or not isinstance(halls, dict):
                    raise ValueError('Некорректные сведения о времени.')
                for hall, detail in halls.items():
                    if hall not in project.hall_ids or not isinstance(detail, dict):
                        raise ValueError('Некорректные сведения о зале.')
                    project.set_detail(day, time, hall, detail.get('trainer', ''), detail.get('duration', 0))
        key = data.get('active_week', '')
        if not isinstance(key, str) or (key and cls.monday(key) != key):
            raise ValueError('Неделя должна начинаться с понедельника.')
        project.active_week = key
        month = data.get('active_month', '')
        if not isinstance(month, str) or (month and (cls.month_key(month) != month or key)):
            raise ValueError('Некорректный месяц расписания.')
        project.active_month = month
        weeks, template = data.get('weeks', {}), data.get('template', {})
        if not isinstance(weeks, dict) or not isinstance(template, dict) or ((key or month) and not template):
            raise ValueError('Некорректный архив недель.')
        def normalize(state):
            if not isinstance(state, dict) or any(k not in state for k in ('schedule', 'times', 'days', 'details')):
                raise ValueError('Некорректное расписание недели.')
            base = project.to_dict()
            for k in ('weeks', 'template', 'active_week', 'months', 'active_month', 'week_sources'):
                base.pop(k, None)
            base.update({k: state[k] for k in ('schedule', 'times', 'days', 'details')})
            restored = cls.from_dict(base)
            for name in restored.trainings:
                if name not in project.trainings:
                    project.trainings.append(name)
            return restored.week_state()
        project.template = normalize(template) if template else {}
        for week, state in weeks.items():
            if not isinstance(week, str) or cls.monday(week) != week:
                raise ValueError('Некорректная дата в архиве.')
            project.weeks[week] = normalize(state)
        months = data.get('months', {})
        if not isinstance(months, dict):
            raise ValueError('Некорректный архив месяцев.')
        for key, state in months.items():
            if not isinstance(key, str) or cls.month_key(key) != key:
                raise ValueError('Некорректная дата месяца.')
            project.months[key] = normalize(state)
        sources = data.get('week_sources', {})
        if not isinstance(sources, dict):
            raise ValueError('Некорректные связи недель с месяцами.')
        for week, source in sources.items():
            if (not isinstance(week, str) or cls.monday(week) != week
                    or week not in {*project.weeks, project.active_week}
                    or not isinstance(source, str) or source not in project.months):
                raise ValueError('Некорректная связь недели с месяцем.')
        project.week_sources = dict(sources)
        return project

    def get(self, day, time, hall):
        return self.schedule.get(day, {}).get(time, {}).get(hall) or ''

    def set(self, day, time, hall, name):
        if self.get(day, time, hall) != (name or ''):
            self.details.get(day, {}).get(time, {}).pop(hall, None)
        self.schedule.setdefault(day, {}).setdefault(time, {})[hall] = name or None

    def count(self):
        return sum(bool(self.get(d, t, h)) for d in self.days for t in self.times for h in self.hall_ids)

    def rename(self, old, new):
        if new in self.trainings and old != new:
            raise ValueError('Такая тренировка уже есть.')
        self.trainings = [new if name == old else name for name in self.trainings]
        for schedule in [self.schedule, self.template.get('schedule', {}), *[s['schedule'] for s in self.weeks.values()], *[s['schedule'] for s in self.months.values()]]:
            for slots in schedule.values():
                for halls in slots.values():
                    for hall in self.hall_ids:
                        if halls.get(hall) == old:
                            halls[hall] = new

    def remove_training(self, name):
        self.trainings.remove(name)
        for schedule in [self.schedule, self.template.get('schedule', {}), *[s['schedule'] for s in self.weeks.values()], *[s['schedule'] for s in self.months.values()]]:
            for slots in schedule.values():
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
        project = Project()
        project.style.update(studio_name='Моя студия', subtitle='')
        project.halls = [dict(default_halls()[0], name='Основной зал')]
        return project, ''

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

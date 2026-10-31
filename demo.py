"""Optional example; never loaded over a user's project without confirmation."""
from model import Project, ALL_DAYS, HALLS


def demo_project():
    project = Project()
    project.style.update(period='2 — 8 ноября', contact='Запись на занятия · ваш путь к себе', palette='Светлый')
    project.trainings = ['Здоровая спина', 'Стройное тело', 'Флекс растяжка', 'Гибкость и сила',
                         'Круговая', 'Степ', 'Ягодицы и пресс', 'Силовая тренировка', 'Боди Комбат', 'Body sculpt']
    for index in (0, 2, 4):
        day = ALL_DAYS[index]
        for time, hall, name in [('17:00', 1, 'Гибкость и сила'), ('17:30', 0, 'Здоровая спина'),
            ('18:30', 0, 'Боди Комбат' if index == 4 else 'Степ'), ('18:30', 1, 'Ягодицы и пресс'),
            ('19:30', 0, 'Body sculpt'), ('19:30', 1, 'Флекс растяжка')]:
            project.set(day, time, HALLS[hall], name)
    for index in (1, 3):
        for time, name in [('17:30', 'Круговая'), ('18:30', 'Силовая тренировка'), ('19:30', 'Стройное тело')]:
            project.set(ALL_DAYS[index], time, HALLS[0], name)
    for time, name in [('10:00', 'Здоровая спина'), ('11:00', 'Стройное тело'), ('12:00', 'Флекс растяжка')]:
        project.set(ALL_DAYS[5], time, HALLS[0], name)
    return project

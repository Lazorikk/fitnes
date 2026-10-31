"""One complete weekly grid for each of the three export formats."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from colors import text_color, rgb

FORMATS = {'story': ('Сторис · 1080 × 1920', (1080, 1920)),
           'post': ('Пост ВК · 1080 × 1350', (1080, 1350)),
           'a4': ('A4 · 3508 × 2480', (3508, 2480))}
PALETTES = {
    'Светлый': {'bg': '#F4F2F8', 'card': '#FFFFFF', 'text': '#262237', 'muted': '#59536A',
                'line': '#EAE5F0', 'accent': '#7955AA', 'green': '#D5F0B2', 'purple': '#DFD0F7',
                'day': '#E9E0F4', 'day_text': '#63507D', 'green_text': '#304526',
                'purple_text': '#493366', 'shadow': '#E8E2EF', 'time': '#EAE5F1'},
    'Тёмный': {'bg': '#161522', 'card': '#211F31', 'text': '#FAF8FF', 'muted': '#C7C1D4',
               'line': '#302B43', 'accent': '#C8ADF0', 'green': '#C2E99C', 'purple': '#CFB6F5',
               'day': '#342A48', 'day_text': '#E6D9FA', 'green_text': '#2D4226',
               'purple_text': '#3F2C5E', 'shadow': '#11101B', 'time': '#2C273D'},
}
FONT_DIR = Path(__file__).parent / 'assets' / 'fonts'


def format_spec(project, variant):
    try:
        return project.format(variant)
    except StopIteration:
        raise ValueError('Неизвестный формат экспорта.') from None


def format_size(project, variant):
    item = format_spec(project, variant)
    return item['width'], item['height']


def font(size, bold=False, serif=False):
    name = 'DejaVuSerif.ttf' if serif else 'Manrope-SemiBold.ttf' if bold else 'Manrope-Medium.ttf'
    return ImageFont.truetype(str(FONT_DIR / name), max(1, round(size)))


def wrap(draw, text, face, width):
    """Wrap even long unbroken names without ellipses or dropped characters."""
    lines = []
    for paragraph in str(text).split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = f'{line} {word}'.strip()
            if draw.textlength(candidate, font=face) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ''
            for char in word:
                if line and draw.textlength(line + char, font=face) > width:
                    lines.append(line)
                    line = ''
                line += char
        lines.append(line)
    return lines or ['']


def text_lines(draw, lines, x, y, face, fill, line_height, anchor='lt'):
    for line in lines:
        draw.text((x, y), line, font=face, fill=fill, anchor=anchor)
        y += line_height
    return y


def centered_text(draw, lines, box, face, fill, line_height):
    """Center the visible glyph bounds, including ascenders and descenders.

    A font's nominal line box is not its visible height. Use one shared baseline
    layout for all lines, then center its actual ink bounds inside the card.
    """
    bounds = [draw.textbbox((0, 0), line, font=face, anchor='ls') for line in lines]
    visible = [(index, bounds[index]) for index, line in enumerate(lines) if line.strip()]
    if not visible:
        return
    top = min(index * line_height + bbox[1] for index, bbox in visible)
    bottom = max(index * line_height + bbox[3] for index, bbox in visible)
    x0, y0, x1, y1 = box
    first_baseline = (y0 + y1 - top - bottom) / 2
    for index, line in enumerate(lines):
        bbox = bounds[index]
        x = (x0 + x1 - bbox[0] - bbox[2]) / 2
        text_lines(draw, [line], x, first_baseline + index * line_height,
                   face, fill, line_height, 'ls')


def centered_session(draw, title_lines, detail_lines, box, face, fill, line_height):
    if not detail_lines:
        centered_text(draw, title_lines, box, face, fill, line_height)
        return
    small = font(max(6, face.size * .82))
    small_height = round(small.size * 1.24)
    lines = [(line, face, line_height) for line in title_lines]
    lines += [(line, small, small_height) for line in detail_lines]
    positioned, baseline = [], 0
    for index, (line, current_face, height) in enumerate(lines):
        if index == len(title_lines):
            baseline += round(face.size * .22)
        bounds = draw.textbbox((0, 0), line, font=current_face, anchor='ls')
        positioned.append((line, current_face, height, baseline, bounds))
        baseline += height
    top = min(y + bounds[1] for _, _, _, y, bounds in positioned)
    bottom = max(y + bounds[3] for _, _, _, y, bounds in positioned)
    x0, y0, x1, y1 = box
    start = (y0 + y1 - top - bottom) / 2
    for line, current_face, height, y, bounds in positioned:
        x = (x0 + x1 - bounds[0] - bounds[2]) / 2
        text_lines(draw, [line], x, start + y, current_face, fill, height, 'ls')


def open_asset(path):
    try:
        with Image.open(path) as source:
            return ImageOps.exif_transpose(source).convert('RGBA')
    except (OSError, ValueError) as error:
        raise ValueError(f'Не удалось открыть изображение «{path}»: {error}') from error


def canvas(project, variant, size):
    palette = PALETTES[project.style.get('palette', 'Светлый')]
    image = Image.new('RGB', size, palette['bg'])
    path = project.style.get('bg_' + variant) or project.style.get('bg_common')
    if path:
        source = ImageOps.fit(open_asset(path), size)
        background = Image.alpha_composite(image.convert('RGBA'), source).convert('RGB')
        transparency = project.style.get('bg_transparency', 8) / 100
        image = Image.blend(background, image, 1 - transparency)
    return image, palette


def header(image, project, palette, scale):
    surface = Image.new('RGBA', image.size)
    draw = ImageDraw.Draw(surface)
    width, _ = image.size
    margin = round(42 * scale)
    start_y = round(40 * scale)
    text_x = margin
    logo = None
    logo_size = round(184 * scale)
    if project.style.get('logo_path'):
        logo = open_asset(project.style['logo_path'])
        visible = logo.getchannel('A').getbbox()
        if visible is None:
            raise ValueError('Логотип полностью прозрачный. Выберите изображение с видимым логотипом.')
        # Transparent padding in the original must not make the mark look tiny.
        logo = logo.crop(visible)
        text_x += logo_size + round(28 * scale)
    text_width = width - margin - text_x
    studio = project.style.get('studio_name', 'Богини').strip() or 'Студия'
    brand_face = font(16 * scale, bold=True)
    brand_lines = wrap(draw, studio.upper() + ' / STUDIO PLANNER', brand_face, text_width)
    y = text_lines(draw, brand_lines, text_x, start_y, brand_face,
                   palette['accent'], round(22 * scale))
    y += round(23 * scale)
    title = project.style.get('title') or 'Расписание занятий'
    face = font(62 * scale, bold=True)
    lines = wrap(draw, title, face, text_width)
    y = text_lines(draw, lines, text_x, y, face, palette['text'], round(73 * scale))
    if project.style.get('subtitle'):
        y += round(12 * scale)
        face = font(21 * scale)
        y = text_lines(draw, wrap(draw, project.style['subtitle'], face, text_width),
                       text_x, y, face, palette['muted'], round(29 * scale))
    if logo is not None:
        logo_y = round(max(start_y, (start_y + y - logo_size) / 2))
        tile = (margin, logo_y, margin + logo_size, logo_y + logo_size)
        draw.rounded_rectangle(tile, radius=round(22 * scale), fill=palette['card'])
        inset = round(12 * scale)
        logo = ImageOps.contain(logo, (logo_size - 2 * inset, logo_size - 2 * inset),
                                Image.Resampling.LANCZOS)
        surface.alpha_composite(logo, (round(margin + (logo_size - logo.width) / 2),
                                       round(logo_y + (logo_size - logo.height) / 2)))
        y = max(y, logo_y + logo_size)
    if project.period_text():
        y += round(20 * scale)
        face = font(19 * scale, bold=True)
        lines = wrap(draw, project.period_text(), face, text_width - 32 * scale)
        badge_width = max(draw.textlength(line, font=face) for line in lines) + 32 * scale
        badge_height = len(lines) * 26 * scale + 18 * scale
        draw.rounded_rectangle((text_x, y, text_x + badge_width, y + badge_height),
                               radius=12 * scale, fill=palette['day'])
        text_lines(draw, lines, text_x + 16 * scale, y + 10 * scale,
                   face, palette['day_text'], round(26 * scale))
        y += badge_height
    bottom = y + round(32 * scale)
    if has_background(project):
        # A solid local surface guarantees contrast, even over a bright photograph
        # with 100% background visibility. The rest of the background is untouched.
        ImageDraw.Draw(image).rounded_rectangle(
            (max(0, margin - 18 * scale), max(0, start_y - 18 * scale),
             width - max(0, margin - 18 * scale), bottom - 12 * scale),
            radius=18 * scale, fill=palette['bg'])
    image.paste(surface, (0, 0), surface)
    return bottom


def has_background(project):
    return any(project.style.get(key) for key in ('bg_common', 'bg_story', 'bg_post', 'bg_a4'))


def legend_layout(project, width, scale):
    draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    face = font(18 * scale)
    available = width - round(104 * scale)
    entries, x, y, row_height = [], 0, 0, 0
    for hall in project.halls:
        lines = wrap(draw, hall['name'], face, min(430 * scale, available - 28 * scale))
        entry_width = max(draw.textlength(line, font=face) for line in lines) + 46 * scale
        if x and x + entry_width > available:
            x, y, row_height = 0, y + row_height + 12 * scale, 0
        entries.append((x, y, hall, lines))
        row_height = max(row_height, len(lines) * 25 * scale)
        x += entry_width
    return entries, y + row_height


def footer_height(project, width, scale):
    draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    _, legend_height = legend_layout(project, width, scale)
    contact = project.style.get('contact', '')
    contact_height = 0
    if contact:
        contact_height = len(wrap(draw, contact, font(19 * scale), width - round(104 * scale))) * 27 * scale + 14 * scale
    return round(legend_height + contact_height + 58 * scale)


def footer(image, project, palette, page, total, scale):
    draw = ImageDraw.Draw(image)
    w, h = image.size
    margin = round(52 * scale)
    y = h - footer_height(project, w, scale) + round(12 * scale)
    if has_background(project):
        draw.rounded_rectangle((margin - 18 * scale, y - 12 * scale,
                                w - margin + 18 * scale, h - 8 * scale),
                               radius=18 * scale, fill=palette['bg'])
    draw.line((margin, y, w - margin, y), fill=palette['line'], width=max(1, round(scale)))
    y += round(20 * scale)
    entries, legend_height = legend_layout(project, w, scale)
    for x, dy, hall, lines in entries:
        draw.ellipse((margin + x, y + dy + scale, margin + x + 13 * scale, y + dy + 14 * scale), fill=hall['color'])
        text_lines(draw, lines, margin + x + 23 * scale, y + dy,
                   font(18 * scale), palette['muted'], round(25 * scale))
    if project.style.get('contact'):
        face = font(19 * scale)
        text_lines(draw, wrap(draw, project.style['contact'], face, w - 2 * margin),
                   margin, y + legend_height + 14 * scale, face, palette['muted'], round(27 * scale))


def cell_blocks(values, x, y, width, height, gap):
    """One occupied hall fills the row; two halls share it equally, in hall order."""
    occupied = [(hall, lines) for hall, lines in enumerate(values) if lines]
    if not occupied:
        return []
    inner_height = height - gap
    block_height = (inner_height - gap * (len(occupied) - 1)) / len(occupied)
    return [dict(hall=hall, lines=lines, box=(x, y + gap / 2 + index * (block_height + gap),
                x + width, y + gap / 2 + index * (block_height + gap) + block_height))
            for index, (hall, lines) in enumerate(occupied)]


def grid_layout(project, variant, draw, top, bottom):
    """Fit full-week columns with variable row heights and full-height single cards."""
    width, image_height = format_size(project, variant)
    landscape = width > image_height
    scale = width / 1080
    margin = round(42 * scale)
    time_width = round(78 * scale)
    column_width = (width - 2 * margin - time_width) / len(project.days)
    padding = max(2, round((3.7 if landscape else 8) * scale))
    gap = max(2, round((4.3 if landscape else 8) * scale))
    head_height = round((38 if landscape else 68) * scale)
    available = bottom - top - head_height
    max_font = round((15 if landscape else 20 if len(project.days) <= 6 else 18) * scale)
    minimum_font = max(6, round((8.6 if landscape else 11) * scale))
    for size in range(max_font, minimum_font - 1, -1):
        face = font(size)
        line_height = round(size * 1.24)
        rows = []
        words_fit = True
        for time in project.times:
            cells = []
            row_height = max(line_height + padding * 2 + gap, round((26 if landscape else 45) * scale))
            for day in project.days:
                values = []
                for hall in project.hall_ids:
                    name = project.session_text(day, time, hall)
                    if size > minimum_font and any(
                            draw.textlength(word, font=face) > column_width - padding * 4
                            for word in name.split() if len(word) <= 18):
                        words_fit = False
                    lines = wrap(draw, name, face, column_width - padding * 4) if name else []
                    values.append(lines)
                occupied = [lines for lines in values if lines]
                if occupied:
                    # Both cards have equal height; a single card never reserves another band.
                    text_height = max(len(lines) for lines in occupied) * line_height
                    required = len(occupied) * (text_height + padding * 2) + gap * len(occupied)
                    row_height = max(row_height, required)
                cells.append(values)
            rows.append({'time': time, 'cells': cells, 'height': row_height})
        required = sum(row['height'] for row in rows)
        if required <= available and words_fit:
            extra = (available - required) / max(1, len(rows))
            y = top + head_height
            for row in rows:
                row['y'] = y
                row['height'] += extra
                y += row['height']
            return {'rows': rows, 'font': face, 'line_height': line_height,
                    'margin': margin, 'time_width': time_width, 'column_width': column_width,
                    'padding': padding, 'gap': gap, 'head_height': head_height,
                    'top': top, 'bottom': bottom}
    raise ValueError(
        f"Расписание слишком плотное для формата «{format_spec(project, variant)['name']}». "
        'Чтобы сохранить всю неделю на одной картинке с читаемым текстом, '
        'сократите названия тренировок, заголовок или количество временных строк. '
        'Дополнительные страницы не создаются.')


def weekly_grid(project, variant):
    size = format_size(project, variant)
    landscape = size[0] > size[1]
    scale = size[0] / 1080
    image, palette = canvas(project, variant, size)
    draw = ImageDraw.Draw(image)
    top = header(image, project, palette, scale * (.52 if landscape else .86))
    footer_scale = scale * .55 if landscape else scale
    bottom = size[1] - footer_height(project, size[0], footer_scale) - round(20 * scale)
    layout = grid_layout(project, variant, draw, top, bottom)
    margin, time_width = layout['margin'], layout['time_width']
    column_width, padding = layout['column_width'], layout['padding']
    gap, head_height = layout['gap'], layout['head_height']
    table_top = top + head_height
    radius = round(14 * scale)
    # Independent day panels preserve the weekly grid without spreadsheet borders.
    day_face = font(round(14 * scale), bold=True)
    while any(draw.textlength(project.day_title(day), font=day_face) > column_width - padding * 2 for day in project.days):
        day_face = font(day_face.size - 1, bold=True)
    panel_layer = Image.new('RGBA', size, (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel_layer)
    panel_alpha = round(255 * (1 - project.style.get('panel_transparency', 0) / 100))
    for column in range(len(project.days)):
        x = margin + time_width + column * column_width
        panel_left, panel_right = x + gap / 2, x + column_width - gap / 2
        panel_draw.rounded_rectangle((panel_left, table_top + round(3 * scale), panel_right,
                                      bottom + round(3 * scale)), radius=radius,
                                     fill=(*rgb(palette['shadow']), panel_alpha))
        panel_draw.rounded_rectangle((panel_left, table_top, panel_right, bottom),
                                     radius=radius, fill=(*rgb(palette['card']), panel_alpha))
    image = Image.alpha_composite(image.convert('RGBA'), panel_layer).convert('RGB')
    draw = ImageDraw.Draw(image)
    for column, day in enumerate(project.days):
        x = margin + time_width + column * column_width
        panel_left, panel_right = x + gap / 2, x + column_width - gap / 2
        draw.rounded_rectangle((panel_left, top, panel_right, table_top - gap),
                               radius=radius, fill=palette['day'])
        centered_text(draw, [project.day_title(day)], (panel_left, top, panel_right, table_top - gap),
                      day_face, palette['day_text'], round(day_face.size * 1.24))
    face, line_height = layout['font'], layout['line_height']
    time_face = font(round(18 * scale), bold=True)
    for row in layout['rows']:
        y, height = row['y'], row['height']
        ty = y + (height - round(34 * scale)) / 2
        draw.rounded_rectangle((margin, ty, margin + time_width - gap, ty + 34 * scale),
                               radius=round(9 * scale), fill=palette['time'])
        centered_text(draw, [row['time']], (margin, ty, margin + time_width - gap, ty + 34 * scale),
                      time_face, palette['muted'], round(time_face.size * 1.24))
        for column, values in enumerate(row['cells']):
            x = margin + time_width + column * column_width
            blocks = cell_blocks(values, x + padding, y, column_width - padding * 2, height, gap)
            for block in blocks:
                hall, lines = block['hall'], block['lines']
                bx0, by0, bx1, by1 = block['box']
                color = project.halls[hall]['color']
                draw.rounded_rectangle(block['box'], radius=round(11 * scale), fill=color)
                day = project.days[column]
                title = project.get(day, row['time'], project.hall_ids[hall])
                title_lines = wrap(draw, title, face, column_width - padding * 4)
                centered_session(draw, title_lines, lines[len(title_lines):], block['box'],
                                 face, text_color(color), line_height)
            # Short, faint ticks retain the time rhythm in empty cells, without boxing them in.
            if not blocks:
                cy = y + height / 2
                cx = x + column_width / 2
                draw.rounded_rectangle((cx - 6 * scale, cy - scale, cx + 6 * scale, cy + scale),
                                       radius=scale, fill=palette['line'])
    footer(image, project, palette, 1, 1, footer_scale)
    return image


def render(project, variant):
    format_spec(project, variant)
    return [weekly_grid(project, variant)]


def save_images(images, directory, variant, kind='PNG', dpi=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    if len(images) != 1:
        raise ValueError('Для каждого формата требуется ровно одна картинка.')
    for image in images:
        filename = {'story': 'bogini_story', 'post': 'bogini_vk_post', 'a4': 'bogini_a4'}.get(variant, 'schedule_' + variant)
        extension = 'jpg' if kind == 'JPEG' else 'png'
        path = directory / f'{filename}.{extension}'
        resolution = dpi or (300 if variant == 'a4' else 96)
        options = {'dpi': (resolution, resolution)}
        if kind == 'JPEG':
            options.update(quality=96, subsampling=0)
        image.convert('RGB').save(path, format=kind, **options)
        paths.append(str(path))
    return paths

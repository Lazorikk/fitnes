"""Shared color validation and readable text on arbitrary hall colors."""
import re


def valid_color(value):
    return isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) is not None


def rgb(value):
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def text_color(background):
    channels = [component / 255 for component in rgb(background)]
    channels = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    luminance = sum(c * weight for c, weight in zip(channels, (.2126, .7152, .0722)))
    return '#000000' if (luminance + .05) / .05 >= 1.05 / (luminance + .05) else '#FFFFFF'


def tint(value, white=.78):
    return '#' + ''.join(f'{round(c + (255 - c) * white):02X}' for c in rgb(value))

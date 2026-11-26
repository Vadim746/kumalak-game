"""Оформление игры «Кумалак»: матовая палитра, шрифты и элементы интерфейса."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

Color = Tuple[int, int, int]

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"

SCREEN_W = 1100
SCREEN_H = 760
FPS = 60

EMERALD_DEEP: Color = (13, 39, 33)
EMERALD: Color = (20, 55, 46)
EMERALD_LIGHT: Color = (29, 72, 59)
FELT: Color = (27, 74, 58)
FELT_DARK: Color = (16, 51, 41)
TERRA: Color = (146, 78, 58)
TERRA_DARK: Color = (94, 50, 39)
TERRA_LIGHT: Color = (166, 95, 70)
COPPER: Color = (205, 150, 92)
COPPER_LIGHT: Color = (222, 172, 116)
COPPER_DARK: Color = (128, 89, 55)
CREAM: Color = (244, 236, 219)
CREAM_SHADE: Color = (214, 203, 181)
TEXT: Color = (238, 233, 220)
TEXT_DIM: Color = (158, 176, 163)
INK: Color = (30, 34, 29)
RED: Color = (193, 104, 82)

# Алиасы прежних имён.
BAIZE_DARK = EMERALD_DEEP
BAIZE = EMERALD
BAIZE_LIGHT = EMERALD_LIGHT
GOLD = COPPER
GOLD_DARK = COPPER_DARK
WOOD = TERRA
WOOD_DARK = TERRA_DARK
WOOD_LIGHT = TERRA_LIGHT
INK_SOFT: Color = (66, 78, 68)
BLUE: Color = (94, 133, 158)
BURGUNDY: Color = (124, 61, 51)

STONE_WHITE: Color = CREAM
STONE_WHITE_SHADE: Color = (205, 195, 174)
STONE_BLACK: Color = (40, 46, 41)
STONE_BLACK_SHADE: Color = (24, 29, 25)

BUTTON_TOP = BUTTON_BOTTOM = TERRA_DARK
BUTTON_ACCENT_TOP = BUTTON_ACCENT_BOTTOM = COPPER

RADIUS = 4

_font_cache: Dict[tuple, pygame.font.Font] = {}


def _font_path(name: str) -> Optional[str]:
    """Путь к вложенному шрифту или ``None``, если файла нет."""
    path = FONT_DIR / name
    return str(path) if path.exists() else None


def font(size: int, bold: bool = False, display: bool = False) -> pygame.font.Font:
    """Шрифт игры: Marck Script для заголовков, PT Sans для интерфейса."""
    key = (size, bold, display)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    if not pygame.font.get_init():
        pygame.font.init()
    if display:
        candidates = ["MarckScript-Regular.ttf"]
    elif bold:
        candidates = ["PT_Sans-Web-Bold.ttf", "NotoSans-Bold.ttf"]
    else:
        candidates = ["PT_Sans-Web-Regular.ttf", "NotoSans-Regular.ttf"]
    result = None
    for name in candidates:
        path = _font_path(name)
        if path:
            try:
                result = pygame.font.Font(path, size)
                break
            except Exception:
                continue
    if result is None:
        system = "dejavusans-bold" if bold else "dejavusans"
        if display:
            system = "georgia,dejavusans"
        try:
            result = pygame.font.SysFont(system, size, bold=bold)
        except Exception:
            result = pygame.font.Font(None, size)
    _font_cache[key] = result
    return result


_baize_cache: Dict[tuple, pygame.Surface] = {}


def baize_background(size: Tuple[int, int]) -> pygame.Surface:
    """Матовое войлоковое полотно заданного размера."""
    width, height = size
    surface = pygame.Surface(size)
    surface.fill(EMERALD_DEEP)
    for y in range(0, height, 6):
        pygame.draw.line(surface, (17, 46, 38), (0, y), (width, y))
    for x in range(0, width, 6):
        pygame.draw.line(surface, (15, 44, 36), (x, 0), (x, height))
    seed = 1100
    for _ in range(700):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = seed % width
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        y = seed % height
        pygame.draw.line(surface, (21, 53, 44), (x, y), (x + 1, y))
    return surface


def get_baize(size: Tuple[int, int]) -> pygame.Surface:
    """Войлочный фон заданного размера."""
    key = tuple(size)
    if key not in _baize_cache:
        _baize_cache[key] = baize_background(size)
    return _baize_cache[key]


_ornament_cache: Dict[tuple, pygame.Surface] = {}


def ornament(surface: pygame.Surface, color: Color = GOLD_DARK, alpha: int = 90) -> None:
    """Тонкая вышивка ромбами вдоль кромки экрана."""
    width, height = surface.get_size()
    key = (width, height, color, alpha)
    overlay = _ornament_cache.get(key)
    if overlay is None:
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        thread = (*color, max(8, alpha // 2))
        fine = (*color, max(6, alpha // 3))
        pygame.draw.rect(overlay, fine, pygame.Rect(20, 20, width - 40, height - 40), 1)
        for y in (20, height - 20):
            for x in range(38, width - 38, 28):
                pygame.draw.polygon(
                    overlay, thread,
                    [(x, y - 4), (x + 4, y), (x, y + 4), (x - 4, y)], 1,
                )
        for x in (20, width - 20):
            for y in range(38, height - 38, 28):
                pygame.draw.polygon(
                    overlay, thread,
                    [(x, y - 4), (x + 4, y), (x, y + 4), (x - 4, y)], 1,
                )
        for cx, cy in ((20, 20), (width - 20, 20),
                       (20, height - 20), (width - 20, height - 20)):
            pygame.draw.polygon(
                overlay, (*color, alpha),
                [(cx, cy - 8), (cx + 8, cy), (cx, cy + 8), (cx - 8, cy)], 1,
            )
            pygame.draw.polygon(
                overlay, fine,
                [(cx, cy - 3), (cx + 3, cy), (cx, cy + 3), (cx - 3, cy)], 1,
            )
        _ornament_cache[key] = overlay
    surface.blit(overlay, (0, 0))


def draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    radius: int = RADIUS,
    fill: Color = EMERALD,
    fill_alpha: int = 255,
    border: Optional[Color] = COPPER_DARK,
    border_alpha: int = 255,
    border_width: int = 1,
) -> None:
    """Плоская панель без тени и градиента, с тонкой медной окантовкой."""
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(
        panel, (*fill, fill_alpha), panel.get_rect(), border_radius=radius
    )
    if border:
        pygame.draw.rect(
            panel, (*border, border_alpha), panel.get_rect(),
            border_radius=radius, width=border_width,
        )
    surface.blit(panel, rect.topleft)


_text_cache: Dict[tuple, pygame.Surface] = {}


def draw_text(
    surface: pygame.Surface,
    text: str,
    font_obj: pygame.font.Font,
    color: Color,
    center: Optional[Tuple[int, int]] = None,
    topleft: Optional[Tuple[int, int]] = None,
    midleft: Optional[Tuple[int, int]] = None,
    midright: Optional[Tuple[int, int]] = None,
) -> pygame.Rect:
    """Текст с привязкой к одному из якорей."""
    key = (font_obj, text, color)
    image = _text_cache.get(key)
    if image is None:
        image = font_obj.render(text, True, color)
        if len(_text_cache) > 800:
            _text_cache.clear()
        _text_cache[key] = image
    rect = image.get_rect()
    if center:
        rect.center = center
    elif topleft:
        rect.topleft = topleft
    elif midleft:
        rect.midleft = midleft
    elif midright:
        rect.midright = midright
    surface.blit(image, rect)
    return rect


def wrap_text(text: str, font_obj: pygame.font.Font, width: int) -> List[str]:
    """Перенос текста по ширине (для экрана правил и журнала)."""
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font_obj.size(candidate)[0] <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fade(surface: pygame.Surface, alpha: int, color: Color = (0, 0, 0)) -> pygame.Surface:
    """Затемняющий слой для модальных диалогов."""
    layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    layer.fill((*color, max(0, min(255, alpha))))
    return layer

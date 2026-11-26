"""Отрисовка доски «Тогыз кумалак»."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

import pygame

from game.kumalak import BOT, HAND, PITS, Move, opponent, pit_index, pit_number, pit_owner
from . import theme

BOARD_X, BOARD_Y = 24, 94
# 772×548 — доска вписана в окно 1100×760, оставляя место под подписи.
BOARD_W, BOARD_H = 772, 548

PIT_R = 28
PIT_W, PIT_H = 2 * PIT_R, 2 * PIT_R
PIT_STEP = 66
PITS_X0 = 118
TOP_Y = 214
BOTTOM_Y = 466

KAZAN_R = 42
KAZAN_CY = BOARD_Y + BOARD_H // 2
KAZAN_CX = {BOT: 72, HAND: 748}
CENTER_Y = KAZAN_CY

BOARD_RECT = pygame.Rect(BOARD_X, BOARD_Y, BOARD_W, BOARD_H)
KAZAN_RECTS = {
    side: pygame.Rect(cx - KAZAN_R, KAZAN_CY - KAZAN_R, 2 * KAZAN_R, 2 * KAZAN_R)
    for side, cx in KAZAN_CX.items()
}

_board_cache: dict = {}
_pit_cache: dict = {}
_kazan_cache: dict = {}
_ring_cache: dict = {}
_stone_cache: dict = {}
_glow_cache: dict = {}
_text_cache: dict = {}


def clear_cache() -> None:
    """Очищает кэши поверхностей."""
    _board_cache.clear()
    _pit_cache.clear()
    _kazan_cache.clear()
    _ring_cache.clear()
    _stone_cache.clear()
    _glow_cache.clear()
    _text_cache.clear()


def _lerp(a: Tuple[int, int, int], b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _text(text: str, size: int, color: Tuple[int, int, int],
          bold: bool = False) -> pygame.Surface:
    key = (text, size, color, bold)
    image = _text_cache.get(key)
    if image is None:
        image = theme.font(size, bold=bold).render(text, True, color)
        _text_cache[key] = image
    return image


def _ring(size: Tuple[int, int], color: Tuple[int, int, int],
          alpha: int, width: int) -> pygame.Surface:
    key = (size, color, alpha, width)
    ring = _ring_cache.get(key)
    if ring is None:
        ring = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.ellipse(ring, (*color, alpha), ring.get_rect(), width)
        _ring_cache[key] = ring
    return ring


def _glow(radius: int) -> pygame.Surface:
    surface = _glow_cache.get(radius)
    if surface is None:
        surface = pygame.Surface((radius * 2 + 12, radius * 2 + 12), pygame.SRCALPHA)
        c = surface.get_width() // 2
        pygame.draw.circle(surface, (*theme.COPPER, 130), (c, c), radius + 4)
        _glow_cache[radius] = surface
    return surface


def _stone_surface(radius: int, side: int) -> pygame.Surface:
    key = (radius, side)
    stone = _stone_cache.get(key)
    if stone is not None:
        return stone
    diameter = 2 * max(2, radius) + 2
    stone = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    c = diameter // 2
    if side == HAND:
        base, shade = theme.STONE_WHITE, theme.STONE_WHITE_SHADE
    else:
        base, shade = theme.STONE_BLACK, theme.STONE_BLACK_SHADE
    pygame.draw.circle(stone, shade, (c, c), radius)
    pygame.draw.circle(stone, base, (c, c), max(1, radius - 1))
    pygame.draw.circle(stone, shade, (c, c), radius, 1)
    _stone_cache[key] = stone
    return stone


def pit_rect(index: int) -> pygame.Rect:
    """Прямоугольник круглой лунки ``index`` (0..17) в экранных координатах."""
    index = int(index) % (2 * PITS)
    if index < PITS:
        column, y = index, BOTTOM_Y
    else:
        column, y = 2 * PITS - 1 - index, TOP_Y
    return pygame.Rect(PITS_X0 + column * PIT_STEP, y, PIT_W, PIT_H)


def _local(rect: pygame.Rect) -> pygame.Rect:
    return rect.move(-BOARD_X, -BOARD_Y)


def kazan_rect(side: int) -> pygame.Rect:
    """Прямоугольник казана игрока ``side`` (``HAND`` или ``BOT``)."""
    return KAZAN_RECTS[int(side)]


def pit_at(pos: Tuple[int, int]) -> Optional[int]:
    """Возвращает индекс лунки под курсором ``pos`` или ``None``."""
    x, y = pos
    for index in range(2 * PITS):
        if pit_rect(index).collidepoint(x, y):
            return index
    return None


def kazan_at(pos: Tuple[int, int]) -> Optional[int]:
    """Возвращает сторону казана под курсором ``pos`` или ``None``."""
    x, y = pos
    for side, rect in KAZAN_RECTS.items():
        if rect.collidepoint(x, y):
            return side
    return None


def _board_surface() -> pygame.Surface:
    cached = _board_cache.get((BOARD_W, BOARD_H))
    if cached is not None:
        return cached

    surface = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
    rect = surface.get_rect()
    pygame.draw.rect(surface, theme.TERRA, rect, border_radius=6)
    pygame.draw.rect(surface, (*theme.COPPER_DARK, 170), rect, 1, border_radius=6)
    pygame.draw.rect(surface, (*theme.COPPER_DARK, 110),
                     rect.inflate(-16, -16), 1, border_radius=3)
    theme.ornament(surface, color=theme.COPPER_DARK, alpha=55)

    mid = CENTER_Y - BOARD_Y
    pygame.draw.rect(surface, theme.TERRA_DARK,
                     pygame.Rect(92, mid - 5, BOARD_W - 184, 10))
    pygame.draw.line(surface, (*theme.COPPER_DARK, 140), (100, mid), (BOARD_W - 100, mid))
    for x in range(112, BOARD_W - 108, 30):
        pygame.draw.polygon(
            surface, (*theme.COPPER, 80),
            [(x, mid - 3), (x + 4, mid), (x, mid + 3), (x - 4, mid)], 1,
        )

    # две полосы сукна: отау утоплены в войлок
    for cy in (TOP_Y - BOARD_Y + PIT_R, BOTTOM_Y - BOARD_Y + PIT_R):
        strip = pygame.Rect(84, cy - 44, BOARD_W - 168, 88)
        pygame.draw.rect(surface, theme.FELT_DARK, strip, border_radius=8)
        pygame.draw.rect(surface, (*theme.COPPER_DARK, 110), strip, 1, border_radius=8)

    for index in range(2 * PITS):
        center = _local(pit_rect(index)).center
        pygame.draw.circle(surface, theme.FELT, center, PIT_R + 2)
        pygame.draw.circle(surface, theme.FELT_DARK, center, PIT_R + 2, 1)

    for cx in (KAZAN_CX[BOT] - BOARD_X, KAZAN_CX[HAND] - BOARD_X):
        pygame.draw.circle(surface, theme.TERRA_DARK, (cx, mid), KAZAN_R + 6)

    _board_cache[(BOARD_W, BOARD_H)] = surface
    return surface


def _kazan_surface(radius: int) -> pygame.Surface:
    cached = _kazan_cache.get(radius)
    if cached is not None:
        return cached
    size = radius * 2
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    c = radius
    pygame.draw.circle(surface, theme.TERRA_LIGHT, (c, c), radius)
    pygame.draw.circle(surface, theme.TERRA, (c, c), radius - 3)
    pygame.draw.circle(surface, theme.FELT_DARK, (c, c), radius - 8)
    pygame.draw.circle(surface, theme.COPPER_DARK, (c, c), radius - 1, 1)
    for i in range(8):
        angle = i * math.tau / 8
        x = c + int((radius - 5) * math.cos(angle))
        y = c + int((radius - 5) * math.sin(angle))
        pygame.draw.polygon(
            surface, (*theme.COPPER, 110),
            [(x, y - 2), (x + 2, y), (x, y + 2), (x - 2, y)], 1,
        )
    _kazan_cache[radius] = surface
    return surface


def _stone_positions(count: int, area: pygame.Rect) -> Tuple[int, list]:
    if count <= 0 or area.width <= 0 or area.height <= 0:
        return 0, []
    aspect = area.width / max(1, area.height)
    cols = max(1, math.ceil(math.sqrt(count * aspect)))
    rows = max(1, math.ceil(count / cols))
    radius = 9
    while radius > 2:
        step = 2 * radius + 1
        if ((cols - 1) * step + 2 * radius <= area.width
                and (rows - 1) * step + 2 * radius <= area.height):
            break
        radius -= 1
    step = 2 * radius + 1
    left = area.centerx - (cols - 1) * step / 2
    top = area.centery - (rows - 1) * step / 2
    limit = min(area.width, area.height) / 2 - radius
    centers = []
    for i in range(count):
        cx = int(left + (i % cols) * step)
        cy = int(top + (i // cols) * step)
        if math.hypot(cx - area.centerx, cy - area.centery) <= limit:
            centers.append((cx, cy))
    return radius, centers


def draw_stones(surface: pygame.Surface, rect: pygame.Rect, count: int, side: int,
                extra: int = 0, glow_extra: bool = False) -> None:
    """Рисует кумалаки в лунке/казане; ``extra`` — камни анимации."""
    total = max(0, int(count)) + max(0, int(extra))
    if total <= 0:
        return
    area = rect.inflate(-6, -6)
    radius, centers = _stone_positions(total, area)
    if radius <= 0:
        return
    image = _stone_surface(radius, side)
    base = max(0, int(count))
    for i, center in enumerate(centers):
        if glow_extra and i >= base:
            glow = _glow(radius)
            surface.blit(glow, (center[0] - glow.get_width() // 2,
                                center[1] - glow.get_height() // 2))
        surface.blit(image, (center[0] - image.get_width() // 2,
                             center[1] - image.get_height() // 2))


@dataclass(frozen=True)
class AnimStone:
    """Кадр анимации кумалака: ``source``, ``target`` и прогресс ``t``."""
    source: int
    target: int
    t: float


class SowAnimation:
    """Пошаговая анимация посева по ``path``."""

    def __init__(self, path: Iterable[int], source: int, step_time: float = 0.09) -> None:
        self.path: list = [int(i) % (2 * PITS) for i in path]
        self.source: int = int(source) % (2 * PITS)
        self.step_time: float = max(0.01, float(step_time))
        self.elapsed: float = 0.0

    @property
    def filled(self) -> int:
        """Уже пройденные шаги посева."""
        return min(len(self.path), int(self.elapsed // self.step_time))

    @property
    def done(self) -> bool:
        """Вся анимация пройдена."""
        return self.elapsed >= len(self.path) * self.step_time

    def update(self, dt: float) -> bool:
        """Сдвинуть анимацию на ``dt``; вернуть True, если есть кадры вперёд."""
        self.elapsed += max(0.0, float(dt))
        return not self.done

    def finish(self) -> None:
        """Сразу перемотать анимацию до конца."""
        self.elapsed = len(self.path) * self.step_time

    def stones(self) -> Tuple[AnimStone, ...]:
        """Камни для текущего кадра: уложенные и летящий."""
        result = []
        filled = self.filled
        for index in self.path[:filled]:
            result.append(AnimStone(self.source, index, 1.0))
        if filled < len(self.path):
            t = (self.elapsed - filled * self.step_time) / self.step_time
            result.append(AnimStone(self.source, self.path[filled],
                                    max(0.0, min(1.0, t))))
        return tuple(result)


def _unpack_anim(item) -> AnimStone:
    if isinstance(item, AnimStone):
        return item
    try:
        source, target, t = item
        return AnimStone(int(source), int(target) % (2 * PITS), float(t))
    except (TypeError, ValueError):
        return AnimStone(-1, -1, 1.0)


def _selected_index(game, selected) -> Optional[int]:
    if selected is None:
        return None
    if isinstance(selected, Move):
        return pit_index(game.turn, selected.pit)
    if isinstance(selected, int):
        if 1 <= selected <= PITS:
            return pit_index(game.turn, selected)
        if 0 <= selected < 2 * PITS:
            return selected
    return None


def _draw_kazans(surface: pygame.Surface, game) -> None:
    bowl = _kazan_surface(KAZAN_R)
    turn = getattr(game, "turn", HAND)
    for side in (BOT, HAND):
        rect = KAZAN_RECTS[side]
        if side == turn and not getattr(game, "over", False):
            # медное кольцо отмечает активную сторону
            pygame.draw.circle(surface, (*theme.COPPER, 200),
                               rect.center, KAZAN_R + 5, 2)
        surface.blit(bowl, rect.topleft)
        count = int(game.kazans.get(side, 0))
        if count > 0:
            area = pygame.Rect(rect.centerx - 30, rect.centery + 14, 60, 26)
            draw_stones(surface, area, min(count, 11), side)
        number = _text(str(count), 46, theme.CREAM, bold=True)
        surface.blit(number, number.get_rect(center=(rect.centerx, rect.centery - 6)))
        label = "казан · вы" if side == HAND else "казан · бот"
        caption = _text(label, 14, theme.TEXT_DIM)
        surface.blit(caption, caption.get_rect(center=(rect.centerx, rect.bottom + 14)))


def _draw_tuzdyk(surface: pygame.Surface, game, now: int) -> None:
    for owner, number in game.tuzdyk.items():
        if number is None:
            continue
        index = pit_index(opponent(int(owner)), int(number))
        rect = pit_rect(index)
        pulse = 0.5 + 0.5 * math.sin(now / 320.0)
        alpha = int(120 + 90 * pulse)
        outer = rect.inflate(12, 12)
        surface.blit(_ring(outer.size, theme.COPPER, alpha, 3), outer)
        label = _text("туздык", 13, theme.COPPER, bold=True)
        y = rect.bottom + 12 if pit_owner(index) == BOT else rect.top - 14
        surface.blit(label, label.get_rect(center=(rect.centerx, y)))


def render(surface: pygame.Surface, game, *, selected=None, last_path=None,
           anim_stones: Iterable = (), hint: bool = False) -> pygame.Rect:
    """Рисует доску в состоянии ``game`` и возвращает её прямоугольник."""
    surface.blit(_board_surface(), (BOARD_X, BOARD_Y))

    legal: set = set()
    targets: dict = {}
    if not game.over:
        for move in game.legal_moves():
            index = pit_index(game.turn, move.pit)
            legal.add(index)
            if hint:
                targets[index] = game.last_landed_pit(move)

    _draw_kazans(surface, game)

    selected_index = _selected_index(game, selected)
    for index in legal:
        rect = pit_rect(index)
        strong = hint or index == selected_index
        surface.blit(_ring(rect.size, theme.COPPER, 210 if strong else 105,
                           3 if strong else 2), rect)

    path = [int(i) % (2 * PITS) for i in (last_path or ())]
    for index in path:
        rect = pit_rect(index)
        surface.blit(_ring(rect.size, theme.CREAM, 45, 2), rect)
    if path:
        last_rect = pit_rect(path[-1]).inflate(8, 8)
        surface.blit(_ring(last_rect.size, theme.COPPER, 160, 2), last_rect)
    elif game.last_move is not None:
        mover = opponent(game.turn)
        rect = pit_rect(pit_index(mover, game.last_move.pit))
        surface.blit(_ring(rect.size, theme.COPPER_DARK, 150, 2), rect)

    if selected_index is not None:
        rect = pit_rect(selected_index).inflate(10, 10)
        surface.blit(_ring(rect.size, theme.COPPER, 235, 3), rect)
        inner = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.circle(inner, (*theme.COPPER, 30),
                           (rect.width // 2, rect.height // 2), rect.width // 2)
        surface.blit(inner, rect)

    flying = [_unpack_anim(item) for item in anim_stones]
    airborne = [item for item in flying
                if item.t < 1.0 and 0 <= item.source < 2 * PITS]
    placed: dict = {}
    for item in flying:
        if item.t >= 1.0 and 0 <= item.target < 2 * PITS:
            placed[item.target] = placed.get(item.target, 0) + 1
    source_index = airborne[0].source if airborne else None
    taken = sum(1 for item in airborne if item.source == source_index)
    for index in range(2 * PITS):
        rect = pit_rect(index)
        count = int(game.pits[index])
        if index == source_index:
            count = max(0, count - taken)
        draw_stones(surface, rect, count,
                    HAND if index < PITS else BOT,
                    extra=placed.get(index, 0), glow_extra=bool(placed))

    for index in range(2 * PITS):
        rect = pit_rect(index)
        side = pit_owner(index)
        label_y = rect.top - 14 if side == BOT else rect.bottom + 8
        label = _text(str(pit_number(index)), 15,
                      theme.CREAM if side == HAND else theme.TEXT_DIM, bold=True)
        surface.blit(label, label.get_rect(center=(rect.centerx, label_y)))
        if index in targets and targets[index] > 0:
            badge_y = rect.bottom + 22 if side == BOT else rect.top - 20
            badge = _text(str(targets[index]), 16, theme.COPPER, bold=True)
            box = badge.get_rect(center=(rect.centerx, badge_y)).inflate(10, 4)
            plate = pygame.Surface(box.size, pygame.SRCALPHA)
            pygame.draw.rect(plate, (*theme.EMERALD_DEEP, 230), plate.get_rect(),
                             border_radius=theme.RADIUS)
            pygame.draw.rect(plate, (*theme.COPPER, 170), plate.get_rect(), 1,
                             border_radius=theme.RADIUS)
            surface.blit(plate, box)
            surface.blit(badge, badge.get_rect(center=box.center))

    _draw_tuzdyk(surface, game, pygame.time.get_ticks())

    for item in flying:
        if item.t >= 1.0 or not (0 <= item.target < 2 * PITS):
            continue
        source = pit_rect(item.source) if 0 <= item.source < 2 * PITS else pit_rect(0)
        target = pit_rect(item.target)
        x = source.centerx + (target.centerx - source.centerx) * item.t
        y = source.centery + (target.centery - source.centery) * item.t
        y -= math.sin(math.pi * item.t) * 24
        side = pit_owner(item.target)
        radius = 8
        glow = _glow(radius)
        surface.blit(glow, (int(x) - glow.get_width() // 2, int(y) - glow.get_height() // 2))
        image = _stone_surface(radius, side)
        surface.blit(image, (int(x) - image.get_width() // 2, int(y) - image.get_height() // 2))

    if hint:
        note = _text("Подсказка: медью — доступные отау, цифры — куда упадёт последний кумалак",
                     15, theme.TEXT_DIM)
        surface.blit(note, note.get_rect(center=(theme.SCREEN_W // 2, 734)))

    return BOARD_RECT

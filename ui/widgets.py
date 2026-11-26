"""Базовые элементы интерфейса игры «Кумалак».

Плоские кнопки, поле ввода имени, журнал с прокруткой и уведомления.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import pygame

from . import theme

_button_body_cache: dict = {}
_input_body_cache: dict = {}

# Заливка, обводка, цвет текста для каждого состояния кнопки.
_BUTTON_STATES = {
    "normal": (theme.TERRA_DARK, theme.COPPER_DARK, theme.CREAM),
    "hover": (theme.TERRA, theme.COPPER, theme.CREAM),
    "accent": (theme.COPPER, theme.COPPER, theme.INK),
    "accent_hover": (theme.COPPER_LIGHT, theme.COPPER, theme.INK),
    "pressed": (theme.COPPER_DARK, theme.COPPER, theme.CREAM),
}


def _button_body(size: Tuple[int, int], state: str) -> pygame.Surface:
    """Плоская подложка кнопки для заданного состояния."""
    key = (size, state)
    body = _button_body_cache.get(key)
    if body is None:
        fill, border, _ = _BUTTON_STATES[state]
        body = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.rect(body, fill, body.get_rect(), border_radius=theme.RADIUS)
        pygame.draw.rect(
            body, border, body.get_rect(), 1, border_radius=theme.RADIUS
        )
        _button_body_cache[key] = body
    return body


def _input_body(size: Tuple[int, int], focused: bool) -> pygame.Surface:
    """Подложка поля ввода; фокус отмечен медной обводкой."""
    key = (size, focused)
    body = _input_body_cache.get(key)
    if body is None:
        body = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.rect(body, theme.EMERALD, body.get_rect(), border_radius=theme.RADIUS)
        pygame.draw.rect(
            body, theme.COPPER if focused else theme.COPPER_DARK,
            body.get_rect(), 1, border_radius=theme.RADIUS,
        )
        _input_body_cache[key] = body
    return body


class Button:
    """Плоская кнопка с состояниями hover и active."""

    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        on_click: Callable[[], None],
        font_size: int = 26,
        accent: bool = False,
    ):
        self.rect = rect
        self.label = label
        self.on_click = on_click
        self.font = theme.font(font_size, bold=True)
        self.hover = False
        self.pressed = False
        self.accent = accent

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Возвращает True, если событие обработано кнопкой."""
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_pressed = self.pressed
            self.pressed = False
            if was_pressed and self.rect.collidepoint(event.pos):
                self.on_click()
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if self.pressed:
            state = "pressed"
        elif self.accent:
            state = "accent_hover" if self.hover else "accent"
        else:
            state = "hover" if self.hover else "normal"
        rect = self.rect.move(0, 1 if self.pressed else 0)
        surface.blit(_button_body(rect.size, state), rect.topleft)
        color = _BUTTON_STATES[state][2]
        theme.draw_text(surface, self.label, self.font, color, center=rect.center)


class TextInput:
    """Поле ввода имени игрока (кириллица, курсор, сообщение ошибки)."""

    def __init__(
        self,
        rect: pygame.Rect,
        text: str = "",
        placeholder: str = "",
        max_length: int = 24,
        font_size: int = 28,
    ):
        self.rect = rect
        self.text = text
        self.placeholder = placeholder
        self.max_length = max_length
        self.font = theme.font(font_size)
        self.focused = False
        self.error = ""
        self.caret_timer = 0.0

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Возвращает True, если событие обработано полем ввода."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focused = self.rect.collidepoint(event.pos)
            if self.focused:
                self.error = ""
            return self.focused
        if event.type == pygame.KEYDOWN and self.focused:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
                self.error = ""
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.focused = False
            elif event.key == pygame.K_ESCAPE:
                self.focused = False
            elif event.unicode and event.unicode.isprintable():
                if len(self.text) < self.max_length:
                    self.text += event.unicode
                    self.error = ""
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(_input_body(self.rect.size, self.focused), self.rect.topleft)
        text = self.text
        image = (
            self.font.render(self.placeholder, True, theme.TEXT_DIM)
            if not text else self.font.render(text, True, theme.TEXT)
        )
        surface.blit(image, (self.rect.x + 14, self.rect.centery - image.get_height() // 2))
        if self.focused and int(self.caret_timer * 2) % 2 == 0:
            caret_x = self.rect.x + 14 + self.font.size(text)[0] + 2
            pygame.draw.line(
                surface, theme.COPPER,
                (caret_x, self.rect.centery - 14),
                (caret_x, self.rect.centery + 14), 2,
            )
        if self.error:
            theme.draw_text(
                surface, self.error, theme.font(20, bold=True), theme.RED,
                topleft=(self.rect.x, self.rect.bottom + 8),
            )

    def update(self, dt: float) -> None:
        """Двигает мигание курсора, только когда поле в фокусе."""
        if self.focused:
            self.caret_timer += dt

    def value(self) -> str:
        """Имя без крайних пробелов."""
        return self.text.strip()

    def set_error(self, message: str) -> None:
        """Показать сообщение об ошибке ввода."""
        self.error = message


class ScrollBox:
    """Прокручиваемый текстовый блок (правила и журнал партии)."""

    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.offset = 0
        self.content_height = 0
        self.lines: List[Tuple[str, pygame.font.Font, tuple]] = []
        self._images: List[pygame.Surface] = []

    def set_lines(self, lines: List[Tuple[str, pygame.font.Font, tuple]]) -> None:
        """Задать строки для отображения."""
        self.lines = lines
        self._images = [font.render(text, True, color) for text, font, color in lines]
        self.content_height = sum(image.get_height() + 6 for image in self._images) + 16
        self.offset = 0

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Прокрутка колесом мыши внутри блока."""
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pygame.mouse.get_pos()):
            max_offset = max(0, self.content_height - self.rect.height)
            self.offset = max(0, min(max_offset, self.offset - event.y * 42))
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if len(self._images) != len(self.lines):
            self.set_lines(self.lines)
        clip = surface.get_clip()
        surface.set_clip(self.rect)
        y = self.rect.y - self.offset + 8
        for image in self._images:
            surface.blit(image, (self.rect.x + 6, y))
            y += image.get_height() + 6
        surface.set_clip(clip)
        if self.content_height > self.rect.height:
            bar_x = self.rect.right - 6
            pygame.draw.rect(
                surface, theme.EMERALD_LIGHT,
                pygame.Rect(bar_x, self.rect.y, 3, self.rect.height),
            )
            visible = self.rect.height / self.content_height
            bar_h = max(30, int(self.rect.height * visible))
            max_offset = max(1, self.content_height - self.rect.height)
            bar_y = self.rect.y + int((self.rect.height - bar_h) * (self.offset / max_offset))
            pygame.draw.rect(
                surface, theme.COPPER_DARK,
                pygame.Rect(bar_x, bar_y, 3, bar_h),
            )


class Message:
    """Всплывающее уведомление внизу экрана."""

    def __init__(self):
        self.text = ""
        self.timer = 0.0
        self.color = theme.TEXT

    def show(self, text: str, seconds: float = 3.0, color: tuple = theme.TEXT) -> None:
        """Показать уведомление на заданное число секунд."""
        self.text = text
        self.timer = seconds
        self.color = color

    def update(self, dt: float) -> None:
        if self.timer > 0:
            self.timer -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.timer <= 0 or not self.text:
            return
        alpha = int(min(255, self.timer * 255))
        image = theme.font(21).render(self.text, True, self.color)
        rect = image.get_rect(center=(surface.get_width() // 2, surface.get_height() - 64))
        panel = pygame.Surface((rect.width + 36, rect.height + 20), pygame.SRCALPHA)
        pygame.draw.rect(panel, (*theme.EMERALD_DEEP, 235), panel.get_rect(),
                         border_radius=theme.RADIUS)
        pygame.draw.rect(panel, (*theme.COPPER_DARK, 235), panel.get_rect(), 1,
                         border_radius=theme.RADIUS)
        surface.blit(panel, (rect.x - 18, rect.y - 10))
        image.set_alpha(alpha)
        surface.blit(image, rect)

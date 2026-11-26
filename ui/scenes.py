"""Экраны игры «Кумалак» (Тогыз кумалак): меню, правила, имя, партия, итог, рекорды.

ПУБЛИЧНЫЙ API ДЛЯ main.py

Все экраны — классы с единым интерфейсом::

    Scene(app)                       # app: объект приложения (нужен только app.store)
    scene.on_enter()                 # вызывается после push/replace
    scene.handle_event(event) -> Optional[Transition]
    scene.update(dt)          -> Optional[Transition]
    scene.draw(surface)      -> None

``Transition`` — простой dataclass с полями ``action`` и ``scene``.
Возможные значения ``action``:

* ``"push"``    — положить ``transition.scene`` на стек;
* ``"replace"`` — заменить верх стека на ``transition.scene``;
* ``"pop"``     — убрать верхний экран;
* ``"menu"``    — вернуться в меню ( ``scenes = scenes[:1]`` );
* ``"quit"``    — выйти из приложения.

Переход возвращают **оба** метода — ``handle_event`` и ``update`` (партия может закончиться
во время анимации хода бота). Главный цикл должен проверять оба результата::

    from ui.scenes import (SCREEN_H, SCREEN_W, MenuScene, ResultScene,
                           Scene, Transition, apply_transition)

    class App:
        def __init__(self):
            pygame.init()
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
            self.clock = pygame.time.Clock()
            self.running = True
            self.store = RecordStore()          # обязательно: нужен сценам
            self.scenes = [MenuScene(self)]     # первый экран — меню
            self.scenes[0].on_enter()

        @property
        def scene(self) -> Scene:
            return self.scenes[-1]

        def run(self):
            while self.running:
                dt = self.clock.tick(60) / 1000.0
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        break
                    trans = self.scene.handle_event(event)
                    if trans:
                        apply_transition(self, trans)
                if not self.running:
                    break
                trans = self.scene.update(dt)
                if trans:
                    apply_transition(self, trans)
                    continue
                self.scene.draw(self.screen)
                pygame.display.flip()
            pygame.quit()

``apply_transition(app, transition)`` сама обновляет ``app.scenes`` и
``app.running``; можно также обработать ``transition.action`` вручную.
Дополнительно ``scene.take_transition()`` возвращает и сбрасывает отложенный
переход (если main.py предпочитает опрашивать сцены). Для совместимости с
проектом-образцом, если у ``app`` есть методы ``push``/``pop``/``pop_to_menu``/
``start_game``, сцены выполняют навигацию через них и возвращают ``None`` —
двойного перехода не происходит.

Классы сцен и конструкторы:

* ``MenuScene(app)``                              — главное меню;
* ``RulesScene(app)``                             — правила с скроллом и источниками;
* ``NameScene(app)``                              — имя + сложность + формат матча;
* ``GameScene(app, name, difficulty=MEDIUM, limit=100)`` — партия;
* ``ResultScene(app, source)``                    — итог, автосохранение рекорда;
  ``source`` — ``GameScene``, либо словарь с ключами ``name``, ``difficulty``,
  ``score``, ``opponent_score``, ``winner``, ``reason``, ``rounds``, ``moves``,
  ``limit`` ( ``GameScene.match_result()`` возвращает такой словарь );
* ``RecordsScene(app)``                           — таблица рекордов.

Формат матча ``limit``: ``1`` — одна партия, ``100``/``150``/``200`` — матч до
соответствующего числа кумалаков в казане (суммируется по партиям).

Импорт ``ui.board_render`` и ``ui.sounds`` защищён: если модуль ещё недоступен
или изменил API, доска рисуется встроенным резервным рендером, а звук молчит.
Все тексты интерфейса — на русском; ошибки ввода и записи не роняют игру.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pygame

try:  # pragma: no cover
    from game.kumalak import (BOT, HAND, PITS, KumalakGame, Move, pit_index,
                              pit_number, pit_owner)
except Exception:  # pragma: no cover
    HAND, BOT, PITS = 0, 1, 9

    def pit_index(player: int, pit: int) -> int:  # type: ignore[misc]
        return int(player) * PITS + (int(pit) - 1)

    KumalakGame = None  # type: ignore[assignment]
    Move = None  # type: ignore[assignment]

    def pit_owner(index: int) -> int:  # type: ignore[misc]
        return HAND if index < PITS else BOT

    def pit_number(index: int) -> int:  # type: ignore[misc]
        return int(index) % PITS + 1


try:  # pragma: no cover
    from game.ai import EASY, HARD, LEVELS, LEVEL_LABELS, MEDIUM, Bot
except Exception:  # pragma: no cover
    EASY, MEDIUM, HARD = "easy", "medium", "hard"
    LEVELS = (EASY, MEDIUM, HARD)
    LEVEL_LABELS = {EASY: "Лёгкий", MEDIUM: "Средний", HARD: "Сложный"}
    Bot = None  # type: ignore[assignment]

try:  # pragma: no cover
    from storage import (RESULT_DRAW, RESULT_LOSS, RESULT_WIN, RecordStore)
except Exception:  # pragma: no cover
    RESULT_WIN, RESULT_LOSS, RESULT_DRAW = "победа", "поражение", "ничья"
    RecordStore = None  # type: ignore[assignment]

from . import theme
from .widgets import Button, Message, ScrollBox, TextInput

try:
    from .sounds import sound_manager as _sound
except Exception:  # pragma: no cover
    _sound = None

try:
    from . import board_render as _board_render
except Exception:  # pragma: no cover
    _board_render = None

SCREEN_W, SCREEN_H = theme.SCREEN_W, theme.SCREEN_H
LIMITS = (1, 100, 150, 200)


@dataclass(frozen=True)
class Transition:
    """Описание перехода: ``action`` и, для push/replace, новый ``scene``."""

    action: str
    scene: Optional["Scene"] = None
    data: Any = None


def apply_transition(app: Any, transition: Optional[Transition]) -> None:
    """Применяет переход к приложению со стеком ``app.scenes``.

    Ничего не делает для ``None``; несовместимые действия игнорируются,
    поэтому вызов безопасен и при частично настроенном ``app``.
    """
    if transition is None:
        return
    scenes = getattr(app, "scenes", None)
    action = str(transition.action).strip().lower()
    if action == "quit":
        try:
            app.running = False
        except Exception:
            pass
        return
    if scenes is None:
        return
    if action in ("push", "replace") and transition.scene is not None:
        if action == "replace" and scenes:
            scenes[-1] = transition.scene
        else:
            scenes.append(transition.scene)
        try:
            transition.scene.on_enter()
        except Exception:
            pass
    elif action == "pop":
        if len(scenes) > 1:
            scenes.pop()
    elif action == "menu":
        del scenes[1:]
        if scenes:
            try:
                scenes[0].on_enter()
            except Exception:
                pass


class _MemoryStore:
    """Заглушка хранилища для smoke-тестов без настоящего ``RecordStore``."""

    def __init__(self) -> None:
        self.records: List[Any] = []
        self.last_error: Optional[str] = None

    def filtered(self, query: str = "") -> List[Any]:
        needle = str(query).strip().lower()
        if not needle:
            return list(self.records)
        return [r for r in self.records if needle in r.name.lower()]

    def sorted_records(self, records=None, key: str = "score") -> List[Any]:  # noqa: A002
        items = list(self.records if records is None else records)
        if str(key).lower() in ("date", "дата"):
            items.sort(key=lambda r: r.date, reverse=True)
        else:
            items.sort(key=lambda r: r.score, reverse=True)
        return items

    def best_score(self, name: str) -> int:
        scores = [r.score for r in self.records if r.name.lower() == name.strip().lower()]
        return max(scores) if scores else 0

    def add(self, name: str, score: int, **kwargs: Any) -> Any:
        from storage import Record  # type: ignore[import-not-found]

        record = Record(name=name, score=score, **{
            k: v for k, v in kwargs.items()
            if k in ("opponent_score", "result", "difficulty", "date", "rounds", "moves")
        })
        self.records.append(record)
        return record

    def clear(self) -> None:
        self.records = []

    def __len__(self) -> int:
        return len(self.records)


_fade_cache: Dict[tuple, pygame.Surface] = {}


def _fade(surface: pygame.Surface, alpha: int) -> pygame.Surface:
    """Кэшированный затемняющий слой для модальных диалогов."""
    key = (surface.get_size(), int(alpha))
    image = _fade_cache.get(key)
    if image is None:
        image = theme.fade(surface, alpha)
        _fade_cache[key] = image
    return image


def _sound_effect(name: str) -> None:
    """Безопасный вызов звука: отсутствие mixer не должно ломать UI."""
    if _sound is None:
        return
    methods = {
        "sow": "play_sow",
        "capture": "play_capture",
        "tuzdyk": "play_tuzdyk",
        "win": "play_win",
        "click": "play_click",
    }
    method = getattr(_sound, methods.get(name, ""), None)
    if callable(method):
        try:
            method()
        except Exception:
            pass


class _FallbackGame:
    """Минимальная заглушка на случай, если game/kumalak.py недоступен."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self.pits = [9] * (2 * PITS)
        self.kazans = {HAND: 0, BOT: 0}
        self.turn = HAND
        self.tuzdyk: Dict[int, int] = {}
        self.move_number = 0
        self.history: List[Any] = []
        self.last_move: Any = None
        self.over = False
        self.result: Optional[dict] = None
        self.log = ["Игровая логика недоступна — запустите main.py из корня проекта."]

    def legal_moves(self, player: Optional[int] = None) -> list:
        return []

    def score(self, side: Optional[int] = None):
        return (0, 0) if side is None else 0

    def notation(self, move: Any) -> str:
        return ""

    def last_landed_pit(self, move: Any) -> int:
        return 0

    def sow_path(self, move: Any) -> list:
        return []

    def apply_move(self, move: Any, set_tuzdyk: bool = False) -> Any:
        raise RuntimeError("Игровая логика недоступна")


class _FallbackBot:
    """Заглушка бота, если game/ai.py недоступен."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.level = MEDIUM

    def choose_move(self, game: Any) -> Any:
        moves = game.legal_moves()
        return moves[0] if moves else None

    def choose_tuzdyk(self, game: Any, move: Any) -> bool:
        return False

    def describe(self) -> str:
        return "Средний"


def _difficulty_label(value: Any) -> str:
    """Русская подпись уровня сложности для интерфейса."""
    text = str(value)
    return LEVEL_LABELS.get(text.strip().lower(), text)


def _new_game(seed: Optional[int] = None) -> Any:
    if KumalakGame is not None:
        try:
            return KumalakGame(seed=seed)
        except Exception:
            pass
    return _FallbackGame(seed)


def _new_bot(level: str, seed: Optional[int] = None) -> Any:
    if Bot is not None:
        try:
            return Bot(level, seed=seed)
        except Exception:
            try:
                return Bot(level)
            except Exception:
                pass
    return _FallbackBot(level, seed)


BOARD_X, BOARD_Y, BOARD_W, BOARD_H = 40, 98, 720, 430
_PIT_W, _PIT_H, _PIT_GAP, _PIT_X0 = 54, 54, 10, 90
_TOP_Y, _BOTTOM_Y = 158, 360


def _canonical_pits() -> Dict[Tuple[int, int], pygame.Rect]:
    result: Dict[Tuple[int, int], pygame.Rect] = {}
    for i in range(PITS):
        x = _PIT_X0 + i * (_PIT_W + _PIT_GAP)
        result[(BOT, i + 1)] = pygame.Rect(x, _TOP_Y, _PIT_W, _PIT_H)
        result[(HAND, i + 1)] = pygame.Rect(x, _BOTTOM_Y, _PIT_W, _PIT_H)
    return result


def _canonical_kazans() -> Dict[int, pygame.Rect]:
    return {
        BOT: pygame.Rect(672, 148, 72, 74),
        HAND: pygame.Rect(672, 350, 72, 74),
    }


def _normalize_rects(value: Any) -> Dict[Tuple[int, int], pygame.Rect]:
    """Приводит разные форматы прямоугольников к ``{(player, pit): Rect}``."""
    result: Dict[Tuple[int, int], pygame.Rect] = {}

    def put(player: Any, number: Any, rect: Any) -> None:
        if not isinstance(rect, pygame.Rect):
            try:
                rect = pygame.Rect(rect)
            except Exception:
                return
        try:
            number = int(number)
        except (TypeError, ValueError):
            return
        if 1 <= number <= PITS:
            white_keys = (HAND, "hand", "white", "белые")
            result[(HAND if player in white_keys else BOT, number)] = rect

    if isinstance(value, dict):
        for key, rect in value.items():
            if isinstance(key, tuple) and len(key) >= 2:
                put(key[0], key[1], rect)
                continue
            text = str(key)
            digits = "".join(ch for ch in text if ch.isdigit())
            number = digits[-1] if digits else "0"
            low = text.lower()
            player = BOT if any(s in low for s in ("bot", "black", "чёр", "чер", "сопер")) else HAND
            put(player, number, rect)
    elif isinstance(value, (list, tuple)) and len(value) >= 2 * PITS:
        flat = list(value[: 2 * PITS])
        for idx, rect in enumerate(flat):
            put(HAND if idx < PITS else BOT, idx % PITS + 1, rect)
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        for player, row in enumerate(value):
            if isinstance(row, (list, tuple)) and len(row) >= PITS:
                for idx, rect in enumerate(row[:PITS]):
                    put(player, idx + 1, rect)
    return result


_board_base_cache: Dict[tuple, pygame.Surface] = {}


def _board_base() -> pygame.Surface:
    """Деревянное основание доски с 18 углублениями и 2 казанами (кэш)."""
    key = (BOARD_W, BOARD_H)
    base = _board_base_cache.get(key)
    if base is not None:
        return base
    base = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
    for y in range(BOARD_H):
        t = y / max(1, BOARD_H - 1)
        color = tuple(
            int(theme.WOOD[i] * (1 - t) + theme.WOOD_DARK[i] * t) for i in range(3)
        )
        pygame.draw.rect(base, color, pygame.Rect(0, y, BOARD_W, 1))
    pygame.draw.rect(base, (*theme.GOLD_DARK, 210), base.get_rect(), 4, border_radius=18)
    pygame.draw.rect(base, (*theme.CREAM, 35), base.get_rect().inflate(-14, -14), 2, border_radius=14)

    def local(rect: pygame.Rect) -> pygame.Rect:
        return rect.move(-BOARD_X, -BOARD_Y)

    for rect in list(_canonical_pits().values()) + list(_canonical_kazans().values()):
        r = local(rect)
        pygame.draw.ellipse(base, theme.WOOD_DARK, r.inflate(10, 8))
        pygame.draw.ellipse(base, theme.INK, r)
        pygame.draw.ellipse(base, (*theme.CREAM, 28), r.inflate(-10, -10), 2)
    _board_base_cache[key] = base
    return base


class _BoardView:
    """Пытается использовать ``ui.board_render``; при неудаче рисует доску сам."""

    def __init__(self) -> None:
        self.module = _board_render
        self.renderer: Any = None
        self._external_rects: Optional[Dict[Tuple[int, int], pygame.Rect]] = None
        self._external_kazans: Dict[int, pygame.Rect] = {}
        self.last_path: Tuple[int, ...] = ()
        self.anim_stones: Tuple[Any, ...] = ()
        self.using_external = callable(getattr(self.module, "render", None))
        if self.module is not None:
            for name in ("BoardRenderer", "BoardView", "Board"):
                cls = getattr(self.module, name, None)
                if cls is None:
                    continue
                for args in ((), (SCREEN_W, SCREEN_H)):
                    try:
                        self.renderer = cls(*args)
                        break
                    except Exception:
                        self.renderer = None
                if self.renderer is not None:
                    break

    def _from_external(self, obj: Any) -> Dict[Tuple[int, int], pygame.Rect]:
        if obj is None:
            return {}
        for attr in ("pit_rects", "rects", "pit_rect_map", "PIT_RECTS"):
            try:
                normalized = _normalize_rects(getattr(obj, attr))
            except Exception:
                normalized = {}
            if normalized:
                return normalized
        getter = getattr(obj, "get_pit_rects", None)
        if callable(getter):
            try:
                normalized = _normalize_rects(getter())
            except Exception:
                normalized = {}
            if normalized:
                return normalized
        return {}

    def _external_kazan_rects(self, obj: Any) -> Dict[int, pygame.Rect]:
        if obj is None:
            return {}
        for attr in ("kazan_rects", "kazans", "KAZAN_RECTS"):
            try:
                value = getattr(obj, attr)
            except Exception:
                continue
            parsed: Dict[int, pygame.Rect] = {}
            if isinstance(value, dict):
                for key, rect in value.items():
                    try:
                        parsed[int(key)] = pygame.Rect(rect)
                    except Exception:
                        continue
            elif isinstance(value, (list, tuple)) and len(value) >= 2:
                for player in (HAND, BOT):
                    try:
                        parsed[player] = pygame.Rect(value[player])
                    except Exception:
                        continue
            if parsed:
                return parsed
        getter = getattr(obj, "get_kazan_rects", None)
        if callable(getter):
            try:
                value = getter()
                if isinstance(value, dict):
                    return {int(k): pygame.Rect(r) for k, r in value.items()}
            except Exception:
                pass
        return {}

    def pit_rects(self) -> Dict[Tuple[int, int], pygame.Rect]:
        if self._external_rects is not None:
            return self._external_rects
        if self.module is not None:
            pit_rect = getattr(self.module, "pit_rect", None)
            if callable(pit_rect):
                rects: Dict[Tuple[int, int], pygame.Rect] = {}
                for index in range(2 * PITS):
                    try:
                        rect = pit_rect(index)
                        rects[(HAND if index < PITS else BOT, index % PITS + 1)] = rect
                    except Exception:
                        continue
                if rects:
                    self._external_rects = rects
                    return rects
        rects = self._from_external(self.renderer)
        if not rects:
            rects = self._from_external(self.module)
        self._external_rects = rects or _canonical_pits()
        return self._external_rects

    def kazan_rects(self) -> Dict[int, pygame.Rect]:
        if self._external_kazans:
            return self._external_kazans
        if self.module is not None:
            kazan_rect = getattr(self.module, "kazan_rect", None)
            if callable(kazan_rect):
                parsed: Dict[int, pygame.Rect] = {}
                for side in (HAND, BOT):
                    try:
                        parsed[side] = pygame.Rect(kazan_rect(side))
                    except Exception:
                        continue
                if parsed:
                    self._external_kazans = parsed
                    return parsed
        rects = self._external_kazan_rects(self.renderer) or self._external_kazan_rects(self.module)
        self._external_kazans = rects or _canonical_kazans()
        return self._external_kazans

    def center(self, player: int, pit: int) -> Tuple[int, int]:
        rect = self.pit_rects().get((player, pit))
        if rect is None:
            rect = _canonical_pits().get((player, pit), pygame.Rect(_PIT_X0, _TOP_Y, _PIT_W, _PIT_H))
        return rect.center

    def kazan_center(self, player: int) -> Tuple[int, int]:
        rect = self.kazan_rects().get(player, _canonical_kazans()[player])
        return rect.center

    def draw(self, surface: pygame.Surface, game: Any, pulse: float = 0.0,
             hint: Tuple[int, ...] = ()) -> None:
        """Рисует доску внешним рендером либо резервным вариантом."""
        if self.using_external:
            func = getattr(self.module, "render", None)
            try:
                func(surface, game, last_path=self.last_path,
                     anim_stones=self.anim_stones, hint=False)
                return
            except Exception:
                self.using_external = False
        drawn = False
        if self.renderer is not None:
            for call in (
                lambda: self.renderer.draw(surface, game),
                lambda: self.renderer.render(surface, game),
            ):
                try:
                    result = call()
                    drawn = True
                    if isinstance(result, dict):
                        normalized = _normalize_rects(result)
                        if normalized:
                            self._external_rects = normalized
                    break
                except Exception:
                    continue
        if not drawn and self.module is not None:
            for name in ("draw_board", "render_board", "draw", "render"):
                func = getattr(self.module, name, None)
                if not callable(func):
                    continue
                try:
                    result = func(surface, game)
                    drawn = True
                    if isinstance(result, pygame.Surface):
                        surface.blit(result, (BOARD_X, BOARD_Y))
                    elif isinstance(result, dict):
                        normalized = _normalize_rects(result)
                        if normalized:
                            self._external_rects = normalized
                    break
                except Exception:
                    continue
            if not drawn:
                func = getattr(self.module, "board_surface", None)
                if callable(func):
                    try:
                        image = func(game)
                        if isinstance(image, pygame.Surface):
                            surface.blit(image, (BOARD_X, BOARD_Y))
                            drawn = True
                    except Exception:
                        pass
        if not drawn:
            self._draw_fallback(surface, game, pulse)
        self._draw_marks(surface, game, pulse, hint)

    def _draw_fallback(self, surface: pygame.Surface, game: Any, pulse: float) -> None:
        surface.blit(_board_base(), (BOARD_X, BOARD_Y))
        pits = _canonical_pits()
        count_font = theme.font(20, bold=True)
        stone_color = {HAND: theme.STONE_WHITE, BOT: theme.STONE_BLACK}
        for (player, number), rect in pits.items():
            amount = 0
            try:
                amount = int(game.pits[player * PITS + number - 1])
            except Exception:
                pass
            positions = (
                (rect.x + 14, rect.y + 12), (rect.x + 27, rect.y + 12),
                (rect.x + 40, rect.y + 12), (rect.x + 14, rect.y + 24),
                (rect.x + 27, rect.y + 24), (rect.x + 40, rect.y + 24),
                (rect.x + 14, rect.y + 36), (rect.x + 27, rect.y + 36),
                (rect.x + 40, rect.y + 36),
            )
            for i in range(min(9, max(0, amount))):
                pygame.draw.circle(surface, stone_color[player], positions[i], 4)
                pygame.draw.circle(surface, (*theme.CREAM, 120),
                                   (positions[i][0] - 1, positions[i][1] - 1), 1)
            theme.draw_text(surface, str(amount), count_font,
                            theme.GOLD if amount else theme.TEXT_DIM,
                            center=(rect.centerx, rect.bottom - 9))
        for player, rect in _canonical_kazans().items():
            amount = 0
            try:
                amount = int(game.kazans[player])
            except Exception:
                pass
            theme.draw_text(surface, str(amount), theme.font(30, bold=True), theme.GOLD,
                            center=rect.center)
            theme.draw_text(surface, "казан", theme.font(15), theme.CREAM,
                            center=(rect.centerx, rect.bottom - 6))

    def _draw_marks(self, surface: pygame.Surface, game: Any, pulse: float,
                    hint: Tuple[int, ...]) -> None:
        rects = self.pit_rects()
        tuzdyk = getattr(game, "tuzdyk", None) or {}
        alpha = int(140 + 90 * (0.5 + 0.5 * math.sin(pulse * 4.0)))
        for player, number in tuzdyk.items():
            try:
                number = int(number)
            except (TypeError, ValueError):
                continue
            target = (BOT if player == HAND else HAND, number)
            rect = rects.get(target)
            if rect is None:
                continue
            ring = pygame.Surface((rect.width + 16, rect.height + 16), pygame.SRCALPHA)
            pygame.draw.ellipse(ring, (*theme.GOLD, alpha), ring.get_rect(), 3)
            surface.blit(ring, (rect.x - 8, rect.y - 8))
            theme.draw_text(surface, "туздык", theme.font(16, bold=True), theme.GOLD,
                            center=(rect.centerx, rect.y - 14))
        if hint:
            for number in hint:
                rect = rects.get((HAND, number))
                if rect is None:
                    continue
                pygame.draw.rect(surface, theme.GOLD, rect.inflate(6, 6), 3,
                                 border_radius=12)


class Scene:
    """Общий интерфейс экрана. Возвращает переходы из handle_event/update."""

    def __init__(self, app: Any = None):
        self.app = app
        self.store = self._resolve_store(app)
        self.message = Message()
        self._pending: Optional[Transition] = None
        self.pulse = 0.0

    @staticmethod
    def _resolve_store(app: Any) -> Any:
        store = getattr(app, "store", None)
        if store is not None:
            return store
        if RecordStore is not None:
            try:
                return _MemoryStore()
            except Exception:
                pass
        return _MemoryStore()

    def on_enter(self) -> None:
        """Вызывается при переходе на экран."""

    def handle_event(self, event: pygame.event.Event) -> Optional[Transition]:
        """Обрабатывает событие; возвращает переход или ``None``."""
        return self.take_transition()

    def update(self, dt: float) -> Optional[Transition]:
        """Обновляет состояние; может вернуть переход (конец партии)."""
        self.message.update(dt)
        self.pulse += dt
        return None

    def draw(self, surface: pygame.Surface) -> None:
        """Отрисовывает экран."""

    def take_transition(self) -> Optional[Transition]:
        """Возвращает и сбрасывает отложенный переход."""
        result, self._pending = self._pending, None
        return result

    def _emit(self, transition: Transition) -> Optional[Transition]:
        """Отложить переход; при классическом App вызвать его методы навигации.

        Если у приложения есть ``push``/``pop``/``pop_to_menu``/``start_game``
        (как в проекте-образце), переход выполняется через них и ``None``
        возвращается вызывающему — это исключает двойную навигацию в main.py.
        Иначе переход возвращается как результат ``handle_event``/``update``.
        """
        if transition is None:
            return None
        if self._apply_classic(transition):
            self._pending = None
            return None
        self._pending = transition
        return transition

    def _apply_classic(self, transition: Transition) -> bool:
        app = self.app
        if app is None:
            return False
        action = transition.action
        scene = transition.scene
        if action == "push" and scene is not None and callable(getattr(app, "push", None)):
            try:
                app.push(scene)
                return True
            except Exception:
                return False
        if action == "replace" and isinstance(scene, GameScene):
            starter = getattr(app, "start_game", None)
            if callable(starter):
                try:
                    starter(scene.player_name, scene.difficulty, scene.limit)
                    return True
                except Exception:
                    pass
        if action == "pop" and callable(getattr(app, "pop", None)):
            try:
                app.pop()
                return True
            except Exception:
                pass
        if action == "menu" and callable(getattr(app, "pop_to_menu", None)):
            try:
                app.pop_to_menu()
                return True
            except Exception:
                pass
        if action == "quit":
            try:
                app.running = False
                return True
            except Exception:
                pass
        return False

    def draw_background(self, surface: pygame.Surface) -> None:
        try:
            surface.blit(theme.get_baize((SCREEN_W, SCREEN_H)), (0, 0))
        except Exception:
            surface.fill(theme.BAIZE_DARK)
        try:
            theme.ornament(surface)
        except Exception:
            pass


class MenuScene(Scene):
    """Главное меню: игра, правила, рекорды, выход."""

    def __init__(self, app: Any = None):
        super().__init__(app)
        self.title_font = theme.font(106, display=True)
        self.subtitle_font = theme.font(22)
        self.buttons: List[Button] = []
        specs = (
            ("Играть", self._play),
            ("Правила игры", self._rules),
            ("Таблица рекордов", self._records),
            ("Выход", self._quit),
        )
        width, height = 470, 64
        x = 88
        for index, (label, action) in enumerate(specs):
            self.buttons.append(
                Button(pygame.Rect(x, 308 + index * 82, width, height),
                       label, action, 28, accent=index == 0)
            )
        self.plaque = pygame.Rect(700, 250, 312, 366)

    def _play(self) -> None:
        self._emit(Transition("push", NameScene(self.app)))

    def _rules(self) -> None:
        self._emit(Transition("push", RulesScene(self.app)))

    def _records(self) -> None:
        self._emit(Transition("push", RecordsScene(self.app)))

    def _quit(self) -> None:
        self._emit(Transition("quit"))

    def handle_event(self, event: pygame.event.Event) -> Optional[Transition]:
        for button in self.buttons:
            button.handle_event(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                self._play()
            elif event.key == pygame.K_ESCAPE:
                self._quit()
        return self.take_transition()

    def update(self, dt: float) -> Optional[Transition]:
        return super().update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        """Меню: крупное имя слева, плоские действия и табличка-экспонат."""
        self.draw_background(surface)
        theme.draw_text(surface, "Кумалак", self.title_font, theme.CREAM,
                        midleft=(84, 166))
        theme.draw_text(surface, "Тогыз кумалак • тюркская народная игра",
                        self.subtitle_font, theme.TEXT_DIM,
                        midleft=(94, 244))
        pygame.draw.line(surface, theme.COPPER_DARK, (88, 222), (352, 222))
        for button in self.buttons:
            button.draw(surface)

        theme.draw_panel(surface, self.plaque, fill=theme.EMERALD)
        theme.draw_text(surface, "ЭКСПОНАТ", theme.font(16, bold=True),
                        theme.TEXT_DIM, midleft=(724, 284))
        theme.draw_text(surface, "18", theme.font(90, bold=True), theme.CREAM,
                        center=(856, 352))
        theme.draw_text(surface, "отау на доске", theme.font(20), theme.TEXT_DIM,
                        center=(856, 410))
        pygame.draw.line(surface, theme.COPPER_DARK, (724, 444), (988, 444))
        theme.draw_text(surface, "162", theme.font(90, bold=True), theme.CREAM,
                        center=(856, 514))
        theme.draw_text(surface, "кумалака в начале партии", theme.font(19),
                        theme.TEXT_DIM, center=(856, 570))
        theme.draw_text(surface, "Победа — 82 в казане", theme.font(17),
                        theme.TEXT_DIM, center=(856, 604))

        theme.draw_text(surface, "Enter — играть   •   Esc — выход",
                        theme.font(18), theme.TEXT_DIM, midleft=(88, 706))
        self.message.draw(surface)


class RulesScene(Scene):
    """Правила игры с прокруткой и списком источников."""

    def __init__(self, app: Any = None):
        super().__init__(app)
        self.scroll = ScrollBox(pygame.Rect(80, 142, 940, 534))
        self.back_button = Button(pygame.Rect(80, 690, 180, 52),
                                  "Назад", self._back, 24)
        self._build_content()

    def _build_content(self) -> None:
        heading = theme.font(27, bold=True)
        body = theme.font(21)
        small = theme.font(18)
        accent = theme.font(22, bold=True)
        lines: List[Tuple[str, pygame.font.Font, tuple]] = []

        def h(text: str) -> None:
            lines.append((text, heading, theme.CREAM))

        def p(text: str, font: Any = body, color: tuple = theme.TEXT) -> None:
            for wrapped in theme.wrap_text(text, font, self.scroll.rect.width - 32):
                lines.append((wrapped, font, color))

        h("История и народность")
        p("Кумалак (тогыз кумалак) — народная настольная игра татар, башкиров, "
          "казахов и киргизов. В России особенно распространена в Татарстане и "
          "Башкортостане. Игра относится к семейству «манкала» — игр с лунками и "
          "камешками, известных в Азии и Африке.")
        p("Первое наиболее полное описание оставил этнограф Н. Н. Пантусов в 1906 "
          "году («Киргизская игра \"Тогуз-кумалак\"»). Реализованный здесь вариант "
          "— «Тогыз кумалак»: 9×9 отау и 162 кумалака — следует этому описанию.",
          accent, theme.CREAM)

        h("1. Доска и фигуры")
        p("Доска состоит из двух рядов по 9 маленьких лунок-«отау» и двух больших "
          "чаш-«казанов» по краям. Своя чаша ставится на стороне соперника. "
          "Всего 162 кумалака: в начале в каждой из 18 лунок лежит по 9, казаны пусты.")
        p("Вид сверху ( белые — внизу, чёрные — вверху ):")
        p("чёрные:  9  8  7  6  5  4  3  2  1      [ казан чёрных ]", small, theme.GOLD)
        p("белые:   1  2  3  4  5  6  7  8  9      [ казан белых ]", small, theme.GOLD)
        p("Нумерация лунок — слева направо для белых и справа налево для чёрных; "
          "в интерфейсе обе стороны нумеруются от 1 до 9 со своей точки зрения.")

        h("2. Посев (ход)")
        p("Ход делается из любой своей непустой лунки. Игрок берёт оттуда все "
          "кумалаки и раскладывает их по одному против часовой стрелки: сначала "
          "по своим лункам слева направо, затем по лункам соперника справа налево, "
          "и так по кругу. Казаны в круг посева не входят.")
        p("Если в исходной лунке было больше одного кумалака, первый остаётся в "
          "ней (лунка не опустошается); если был ровно один — он перекладывается "
          "в следующую лунку круга.")

        h("3. Захват (правило чётности)")
        p("Если последний разложенный кумалак попал в лунку соперника и число "
          "кумалаков в ней стало чётным (2, 4, 6, …), игрок забирает все кумалаки "
          "из этой лунки в свой казан. Захват происходит автоматически. Чётное "
          "число в своей лунке или не последним камнем захвата не даёт.")

        h("4. Туздык — «священное место в степи»")
        p("Если последний кумалак сделал число в лунке соперника ровно 3, игрок "
          "может поставить там туздык: лунка становится его «десятой» лункой. "
          "Из туздыка нельзя ходить самому, но все кумалаки, попавшие туда любой "
          "стороной, сразу уходят в казан владельца туздыка.")
        p("Ограничения: можно иметь только один туздык; нельзя ставить его в "
          "9-ю лунку; нельзя ставить в лунку с тем же номером, где уже стоит "
          "туздык соперника. В игре появление туздыка всегда требует явного "
          "выбора «Да/Нет»; бот решает самостоятельно (лёгкий уровень не ставит).")

        h("5. Конец партии и счёт")
        p("Вариант A: как только в казане игрока становится 82 или больше "
          "кумалаков (половина плюс один от 162), партия сразу заканчивается "
          "его победой.")
        p("Вариант B — «атсырау»: если у игрока, чей ход, все лунки пусты, "
          "соперник забирает в свой казан все оставшиеся на доске кумалаки, "
          "после чего сравниваются казаны. Больше кумалаков — победа, ровно "
          "81:81 — ничья. Счёт показывается как «X : Y».")
        p("Первый ход делает человек («белые»). Нотация хода — «откуда><куда», "
          "например 76; постановка туздыка помечается буквой x (36x). "
          "Все ходы выводятся в журнале партии.", accent, theme.CREAM)

        h("Словарь терминов")
        p("кумалак — камешек и название игры; отау — маленькая лунка; казан — "
          "большая чаша для выигранных кумалаков; туздык — священная лунка; "
          "атсырау — положение без хода, конец партии.", small, theme.CREAM)

        h("Источники правил")
        p("Н. Н. Пантусов, «Киргизская игра \"Тогуз-кумалак\"», 1906 (первое "
          "полное описание).", small, theme.CREAM)
        p("Хабр: https://habr.com/ru/articles/800993/", small, theme.GOLD)
        p("Дирекция развития спорта Астаны: https://olympic-astana.kz/ru/sports/togyzkumalak/",
          small, theme.GOLD)
        p("Справочник: https://www.pravilaigr.ru/togizkymalak.php", small, theme.GOLD)
        p("Toguz Arena: https://toguzkumalak.com/wiki/", small, theme.GOLD)

        self.scroll.set_lines(lines)

    def _back(self) -> None:
        self._emit(Transition("pop"))

    def handle_event(self, event: pygame.event.Event) -> Optional[Transition]:
        self.scroll.handle_event(event)
        self.back_button.handle_event(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()
        return self.take_transition()

    def update(self, dt: float) -> Optional[Transition]:
        return super().update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        self.draw_background(surface)
        theme.draw_text(surface, "Правила игры в кумалак",
                        theme.font(46, display=True), theme.CREAM,
                        midleft=(80, 78))
        pygame.draw.line(surface, theme.COPPER_DARK, (80, 118), (300, 118))
        theme.draw_panel(surface, self.scroll.rect.inflate(20, 20), fill=theme.EMERALD)
        self.scroll.draw(surface)
        self.back_button.draw(surface)
        self.message.draw(surface)


class NameScene(Scene):
    """Имя игрока, уровень соперника и формат матча с валидацией ввода."""

    def __init__(self, app: Any = None):
        super().__init__(app)
        self.name_input = TextInput(
            pygame.Rect(80, 202, 560, 58),
            placeholder="Введите имя игрока", max_length=24,
        )
        self.name_input.focused = True
        self.difficulty = MEDIUM
        self.limit = 100
        self.difficulty_buttons: List[Button] = []
        self.limit_buttons: List[Button] = []
        for index, level in enumerate(LEVELS):
            rect = pygame.Rect(80 + index * 222, 350, 210, 56)
            label = LEVEL_LABELS.get(level, level)
            self.difficulty_buttons.append(
                Button(rect, label, lambda lv=level: self._set_difficulty(lv), 24)
            )
        limit_labels = {1: "одна партия", 100: "до 100", 150: "до 150", 200: "до 200"}
        for index, value in enumerate(LIMITS):
            rect = pygame.Rect(80 + index * 222, 462, 210, 56)
            self.limit_buttons.append(
                Button(rect, limit_labels[value], lambda v=value: self._set_limit(v), 23)
            )
        self.start_button = Button(pygame.Rect(80, 568, 360, 64),
                                   "Начать игру", self._start, 28, accent=True)
        self.back_button = Button(pygame.Rect(80, 666, 180, 52),
                                  "Назад", self._back, 24)

    def _set_difficulty(self, level: str) -> None:
        self.difficulty = level

    def _set_limit(self, value: int) -> None:
        self.limit = int(value)

    def _back(self) -> None:
        self._emit(Transition("pop"))

    def _start(self) -> None:
        name = self.name_input.value()
        if not name:
            self.name_input.set_error("Введите имя — без него результат не сохранить")
            self.name_input.focused = True
            _sound_effect("click")
            return
        if len(name) < 2:
            self.name_input.set_error("Имя должно содержать хотя бы 2 символа")
            self.name_input.focused = True
            _sound_effect("click")
            return
        _sound_effect("click")
        self._emit(Transition("replace",
                              GameScene(self.app, name, self.difficulty, self.limit)))

    def handle_event(self, event: pygame.event.Event) -> Optional[Transition]:
        self.name_input.handle_event(event)
        for button in self.difficulty_buttons + self.limit_buttons:
            button.handle_event(event)
        self.start_button.handle_event(event)
        self.back_button.handle_event(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._start()
            elif event.key == pygame.K_ESCAPE:
                self._back()
        return self.take_transition()

    def update(self, dt: float) -> Optional[Transition]:
        super().update(dt)
        self.name_input.update(dt)
        return self.take_transition()

    def draw(self, surface: pygame.Surface) -> None:
        self.draw_background(surface)
        theme.draw_text(surface, "Кто сегодня играет?",
                        theme.font(56, display=True), theme.CREAM,
                        midleft=(80, 92))
        theme.draw_text(surface, "Имя попадёт в таблицу рекордов",
                        theme.font(21), theme.TEXT_DIM,
                        midleft=(88, 160))
        self.name_input.draw(surface)

        theme.draw_text(surface, "Сложность соперника", theme.font(22, bold=True),
                        theme.TEXT, midleft=(80, 318))
        for button in self.difficulty_buttons:
            button.draw(surface)
        theme.draw_text(surface, "Формат матча", theme.font(22, bold=True),
                        theme.TEXT, midleft=(80, 430))
        for button in self.limit_buttons:
            button.draw(surface)

        difficulty_index = LEVELS.index(self.difficulty) if self.difficulty in LEVELS else -1
        if 0 <= difficulty_index < len(self.difficulty_buttons):
            pygame.draw.rect(surface, theme.COPPER,
                             self.difficulty_buttons[difficulty_index].rect, 2,
                             border_radius=theme.RADIUS)
        limit_index = LIMITS.index(self.limit) if self.limit in LIMITS else -1
        if 0 <= limit_index < len(self.limit_buttons):
            pygame.draw.rect(surface, theme.COPPER,
                             self.limit_buttons[limit_index].rect, 2,
                             border_radius=theme.RADIUS)

        self.start_button.draw(surface)
        self.back_button.draw(surface)
        self.message.draw(surface)


class GameScene(Scene):
    """Игровой экран: доска, счёт, анимация посева, туздык, журнал, подсказка."""

    ANIM_STONE = 0.09

    def __init__(self, app: Any = None, name: str = "Игрок",
                 difficulty: str = MEDIUM, limit: int = 100):
        super().__init__(app)
        self.player_name = str(name).strip() or "Игрок"
        self.difficulty = str(difficulty)
        self.limit = int(limit) if int(limit) in LIMITS else 100
        self.game = _new_game(seed=random.randint(1, 10 ** 9))
        self.bot = _new_bot(self.difficulty, seed=random.randint(1, 10 ** 9))
        self.board_view = _BoardView()
        self.match_scores = {HAND: 0, BOT: 0}
        self.round = 1
        self.total_moves = 0
        self.finished = False
        self.surrendered = False

        self.animations: List[dict] = []
        self.pending_round_over = False
        self.bot_timer = 0.0
        self.hint_timer = 0.0
        self.hint_pits: Tuple[int, ...] = ()
        self.banner = ""
        self.banner_timer = 0.0
        self.round_panel = False
        self.tuzdyk_dialog: Optional[dict] = None
        self.surrender_dialog = False
        self.log_lines: List[Tuple[str, pygame.font.Font, tuple]] = []
        # журнал вынесен в правую боковую панель и не перекрывает доску
        self.scroll = ScrollBox(pygame.Rect(828, 152, 240, 476))
        self.log_font = theme.font(16)
        self.journal_rect = pygame.Rect(816, 94, 260, 548)

        self.hint_button = Button(pygame.Rect(916, 660, 160, 56),
                                  "Подсказка", self._hint, 22)
        self.surrender_button = Button(pygame.Rect(744, 660, 160, 56),
                                       "Сдаться", self._surrender, 22)
        self.menu_button = Button(pygame.Rect(24, 660, 160, 56),
                                  "В меню", self._menu, 22)
        self.next_round_button = Button(
            pygame.Rect(SCREEN_W // 2 - 150, 462, 300, 58),
            "Следующая партия", self._next_round, 25, accent=True)
        self.dialog_yes = Button(pygame.Rect(SCREEN_W // 2 - 190, 430, 170, 54),
                                 "Да", self._dialog_yes, 24, accent=True)
        self.dialog_no = Button(pygame.Rect(SCREEN_W // 2 + 20, 430, 170, 54),
                                "Нет", self._dialog_no, 24)
        self._refresh_log()
        self._banner(f"Партия {self.round} — первый ход за вами", 3.0)

    def on_enter(self) -> None:
        try:
            pygame.display.set_caption(f"Кумалак — {self.player_name}")
        except Exception:
            pass

    def _banner(self, text: str, seconds: float = 2.5) -> None:
        self.banner = text
        self.banner_timer = seconds

    def _refresh_log(self) -> None:
        font = self.log_font
        lines: List[Tuple[str, pygame.font.Font, tuple]] = []
        try:
            entries = list(self.game.log)
        except Exception:
            entries = []
        for entry in entries[-120:]:
            for wrapped in theme.wrap_text(entry, font, self.scroll.rect.width - 24):
                lines.append((wrapped, font, theme.TEXT))
        self.scroll.set_lines(lines)
        self.scroll.offset = max(0, self.scroll.content_height - self.scroll.rect.height)

    def _finish_match(self, winner: Optional[int]) -> Transition:
        if self.finished:
            return Transition("pop")
        self.finished = True
        data = self.match_result(winner)
        return self._emit(Transition("push", ResultScene(self.app, data)))

    def match_result(self, winner: Optional[int] = None) -> dict:
        """Данные результата матча для :class:`ResultScene`."""
        if winner is None and getattr(self.game, "result", None):
            try:
                winner = self.game.result.get("winner")
            except Exception:
                winner = None
        reason = ""
        try:
            reason = str((self.game.result or {}).get("reason_text", ""))
        except Exception:
            reason = ""
        return {
            "name": self.player_name,
            "difficulty": self.difficulty,
            "score": int(self.match_scores[HAND]),
            "opponent_score": int(self.match_scores[BOT]),
            "winner": winner,
            "reason": reason,
            "surrendered": self.surrendered,
            "rounds": self.round,
            "moves": self.total_moves,
            "limit": self.limit,
        }

    def _menu(self) -> None:
        self._emit(Transition("menu"))

    def _hint(self) -> None:
        if self.game.over or self.round_panel or self.tuzdyk_dialog:
            return
        moves = self.game.legal_moves(HAND)
        if not moves:
            self.message.show("Нет доступных ходов — партия почти окончена", 2.6, theme.RED)
            return
        best = moves[0]
        try:
            landing = self.game.last_landed_pit(best)
        except Exception:
            landing = 0
        self.hint_pits = tuple(m.pit for m in moves)
        self.hint_timer = 4.0
        self.message.show(
            f"Ход из лунки {best.pit}: последний кумалак упадёт в лунку {landing}. "
            f"Доступно ходов: {len(moves)}", 4.0, theme.GOLD)
        _sound_effect("click")

    def _surrender(self) -> None:
        if self.game.over or self.finished:
            return
        self.surrender_dialog = True

    def _dialog_yes(self) -> None:
        if self.surrender_dialog:
            self.surrender_dialog = False
            self.surrendered = True
            self._emit(self._finish_match(BOT))
            return
        if self.tuzdyk_dialog:
            move = self.tuzdyk_dialog["move"]
            pit = self.tuzdyk_dialog["pit"]
            self.tuzdyk_dialog = None
            self._commit(move, True)
            self.message.show(f"Туздык поставлен в лунку {pit}!", 3.0, theme.GOLD)

    def _dialog_no(self) -> None:
        if self.surrender_dialog:
            self.surrender_dialog = False
            return
        if self.tuzdyk_dialog:
            move = self.tuzdyk_dialog["move"]
            self.tuzdyk_dialog = None
            self._commit(move, False)

    def _pit_at(self, pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        for (player, number), rect in self.board_view.pit_rects().items():
            if rect.collidepoint(pos):
                return player, number
        return None

    def _choose_move(self, move: Any) -> None:
        if self.game.over or self.finished:
            return
        try:
            notation = self.game.notation(move)
        except Exception:
            notation = ""
        if notation.endswith("x") and self.game.turn == HAND:
            # туздык требует явного ответа: ход применяется только после выбора
            self.tuzdyk_dialog = {"move": move, "pit": notation[:-1][-1:]}
            self.message.show("У вас право поставить туздык", 3.0, theme.GOLD)
            _sound_effect("tuzdyk")
            return
        self._commit(move, False)

    def _commit(self, move: Any, set_tuzdyk: bool) -> None:
        try:
            result = self.game.apply_move(move, set_tuzdyk=set_tuzdyk)
        except Exception as exc:
            self.message.show(f"Ход невозможен: {exc}", 3.0, theme.RED)
            return
        self._refresh_log()
        self.hint_timer = 0.0
        self.hint_pits = ()
        self._animate(result, move)
        _sound_effect("sow")
        if getattr(result, "captured", 0):
            _sound_effect("capture")
        if getattr(result, "tuzdyk_set", False):
            _sound_effect("tuzdyk")
        if getattr(self.game, "over", False):
            self.pending_round_over = True
        elif self.game.turn == BOT:
            self.bot_timer = 0.55
        else:
            self.bot_timer = 0.0

    def _animate(self, result: Any, move: Any) -> None:
        path = [int(i) for i in (getattr(result, "path", ()) or ())]
        self.board_view.last_path = tuple(path)
        mover = getattr(result, "player", self.game.turn)
        color = theme.STONE_WHITE if mover == HAND else theme.STONE_BLACK
        try:
            source_pit = int(getattr(move, "pit", 1))
            source = self.board_view.center(mover, source_pit)
            source_idx = pit_index(mover, source_pit)
        except Exception:
            source = self.board_view.center(HAND, 1)
            source_idx = 0
        previous = source
        previous_idx = source_idx
        start = 0.0
        for index in path:
            try:
                idx = int(index)
                target_player = HAND if idx < PITS else BOT
                target_pit = idx % PITS + 1
                target = self.board_view.center(target_player, target_pit)
            except Exception:
                continue
            self.animations.append({
                "x0": previous[0], "y0": previous[1],
                "x1": target[0], "y1": target[1],
                "source_idx": previous_idx, "target_idx": idx,
                "t": -start, "dur": self.ANIM_STONE, "color": color,
            })
            previous = target
            previous_idx = idx
            start += 0.035
        captured = int(getattr(result, "captured", 0) or 0)
        if captured:
            try:
                target = self.board_view.kazan_center(mover)
                for i in range(min(6, captured)):
                    self.animations.append({
                        "x0": previous[0], "y0": previous[1],
                        "x1": target[0] + (i % 3 - 1) * 8,
                        "y1": target[1] + (i // 3 - 1) * 8,
                        "source_idx": previous_idx, "target_idx": -1,
                        "t": -(start + i * 0.04), "dur": 0.16,
                        "color": color,
                    })
            except Exception:
                pass
        self._sync_anim()

    def _sync_anim(self) -> None:
        """Передаёт летящие кумалаки в board_render в его формате."""
        if not self.board_view.using_external:
            return
        stones = []
        for item in self.animations:
            target = int(item.get("target_idx", -1))
            elapsed, duration = float(item["t"]), float(item["dur"])
            if target >= 0 and 0 <= elapsed < duration:
                stones.append((int(item["source_idx"]), target,
                               min(0.99, elapsed / duration)))
        self.board_view.anim_stones = tuple(stones)

    def _bot_step(self) -> None:
        try:
            moves = self.game.legal_moves()
        except Exception:
            moves = []
        if not moves:
            return
        try:
            move = self.bot.choose_move(self.game) or moves[0]
        except Exception:
            move = moves[0]
        use_tuzdyk = False
        try:
            if str(self.game.notation(move)).endswith("x"):
                use_tuzdyk = bool(self.bot.choose_tuzdyk(self.game, move))
        except Exception:
            use_tuzdyk = False
        self._commit(move, use_tuzdyk)

    def _round_over(self) -> Optional[Transition]:
        try:
            scores = self.game.score()
        except Exception:
            scores = (0, 0)
        self.match_scores[HAND] += int(scores[0])
        self.match_scores[BOT] += int(scores[1])
        self.total_moves += int(getattr(self.game, "move_number", 0))
        result = getattr(self.game, "result", None) or {}
        try:
            winner = result.get("winner")
            reason = str(result.get("reason_text", ""))
        except Exception:
            winner, reason = None, ""
        if winner == HAND:
            self._banner("Партия ваша! " + reason, 3.2)
            _sound_effect("win")
        elif winner == BOT:
            self._banner("Партия за соперником. " + reason, 3.2)
        else:
            self._banner("Ничья. " + reason, 3.2)

        if self.limit == 1 or max(self.match_scores.values()) >= self.limit:
            return self._finish_match(winner)
        self.round_panel = True
        return None

    def _next_round(self) -> None:
        self.round += 1
        self.game = _new_game(seed=random.randint(1, 10 ** 9))
        self.bot = _new_bot(self.difficulty, seed=random.randint(1, 10 ** 9))
        self.animations = []
        self.board_view.last_path = ()
        self.board_view.anim_stones = ()
        self.pending_round_over = False
        self.bot_timer = 0.0
        self.round_panel = False
        self._refresh_log()
        self._banner(f"Партия {self.round}. Счёт матча: "
                     f"{self.match_scores[HAND]} : {self.match_scores[BOT]}", 3.0)

    def handle_event(self, event: pygame.event.Event) -> Optional[Transition]:
        if self.finished:
            return None
        if self.tuzdyk_dialog or self.surrender_dialog:
            self.dialog_yes.handle_event(event)
            self.dialog_no.handle_event(event)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_n:
                    self._dialog_no()
                elif event.key == pygame.K_RETURN or event.key == pygame.K_y:
                    self._dialog_yes()
            return self.take_transition()

        if self.round_panel:
            self.next_round_button.handle_event(event)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._menu()
            return self.take_transition()

        self.hint_button.handle_event(event)
        self.surrender_button.handle_event(event)
        self.menu_button.handle_event(event)
        self.scroll.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.animations:
                for animation in self.animations:
                    animation["t"] = animation["dur"]
                self._sync_anim()
                return self.take_transition()
            hit = self._pit_at(event.pos)
            if hit is None:
                return self.take_transition()
            player, number = hit
            if self.game.over:
                return self.take_transition()
            if player != self.game.turn:
                self.message.show("Это лунка соперника — отсюда ходить нельзя", 2.6, theme.RED)
                _sound_effect("click")
                return self.take_transition()
            if number in (getattr(self.game, "tuzdyk", None) or {}).values():
                self.message.show("Из туздыка ходить нельзя", 2.6, theme.RED)
                return self.take_transition()
            moves = self.game.legal_moves(self.game.turn)
            if not any(m.pit == number for m in moves):
                self.message.show("В этой лунке нет кумалаков", 2.6, theme.RED)
                return self.take_transition()
            try:
                self._choose_move(Move(number) if Move is not None else number)
            except Exception as exc:
                self.message.show(f"Не удалось сделать ход: {exc}", 3.0, theme.RED)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._menu()
            elif event.key == pygame.K_h:
                self._hint()
        return self.take_transition()

    def update(self, dt: float) -> Optional[Transition]:
        super().update(dt)
        if self.finished:
            return None
        if self.hint_timer > 0:
            self.hint_timer -= dt
            if self.hint_timer <= 0:
                self.hint_pits = ()
        if self.banner_timer > 0:
            self.banner_timer -= dt

        if self.animations:
            remaining = []
            for animation in self.animations:
                animation["t"] += dt
                if animation["t"] < animation["dur"]:
                    remaining.append(animation)
            self.animations = remaining
            self._sync_anim()
            return None

        if self.pending_round_over:
            self.pending_round_over = False
            trans = self._round_over()
            if trans is not None:
                return trans

        if (not self.game.over and not self.round_panel and not self.tuzdyk_dialog
                and not self.surrender_dialog and self.game.turn == BOT):
            self.bot_timer -= dt
            if self.bot_timer <= 0:
                self.bot_timer = 1.0
                self._bot_step()
        return self.take_transition()

    def draw(self, surface: pygame.Surface) -> None:
        self.draw_background(surface)
        self._draw_topbar(surface)
        self.board_view.draw(surface, self.game, self.pulse, self.hint_pits)
        if not self.board_view.using_external:
            self._draw_animations(surface)
        self._draw_journal(surface)
        self._draw_controls(surface)
        if self.banner_timer > 0 and not self.tuzdyk_dialog and not self.surrender_dialog:
            self._draw_banner(surface)
        if self.round_panel:
            self._draw_round_panel(surface)
        if self.tuzdyk_dialog or self.surrender_dialog:
            self._draw_dialog(surface)
        self.message.draw(surface)

    def _draw_topbar(self, surface: pygame.Surface) -> None:
        theme.draw_panel(surface, pygame.Rect(24, 12, SCREEN_W - 48, 72),
                         fill=theme.EMERALD)
        theme.draw_text(surface, "СЧЁТ МАТЧА", theme.font(14, bold=True),
                        theme.TEXT_DIM, midleft=(48, 30))
        theme.draw_text(surface,
                        f"{self.match_scores[HAND]} : {self.match_scores[BOT]}",
                        theme.font(34, bold=True), theme.CREAM, midleft=(48, 52))
        turn_text = "ваш ход" if self.game.turn == HAND else "ход бота"
        info = f"Ход {getattr(self.game, 'move_number', 0)} • {turn_text}"
        info_font = theme.font(21)
        theme.draw_text(surface, info, info_font, theme.TEXT,
                        center=(SCREEN_W // 2, 46))
        pygame.draw.circle(surface, theme.COPPER,
                           (SCREEN_W // 2 - info_font.size(info)[0] // 2 - 14, 46), 4)
        fmt = "одна партия" if self.limit == 1 else f"до {self.limit}"
        theme.draw_text(surface, f"Партия {self.round} • {fmt}",
                        theme.font(19), theme.TEXT_DIM,
                        midright=(SCREEN_W - 48, 32))
        tuzdyk = getattr(self.game, "tuzdyk", None) or {}
        yours, foes = tuzdyk.get(HAND), tuzdyk.get(BOT)
        detail = []
        if yours:
            detail.append(f"ваш туздык: лунка {yours}")
        if foes:
            detail.append(f"туздык бота: лунка {foes}")
        theme.draw_text(surface, "; ".join(detail) or "туздыков нет",
                        theme.font(17), theme.COPPER if detail else theme.TEXT_DIM,
                        midright=(SCREEN_W - 48, 62))

    def _draw_animations(self, surface: pygame.Surface) -> None:
        for animation in self.animations:
            t = animation["t"]
            if t < 0 or t > animation["dur"]:
                continue
            k = t / animation["dur"]
            x = int(animation["x0"] + (animation["x1"] - animation["x0"]) * k)
            y = int(animation["y0"] + (animation["y1"] - animation["y0"]) * k
                    - math.sin(k * math.pi) * 22)
            pygame.draw.circle(surface, animation["color"], (x, y), 7)
            pygame.draw.circle(surface, theme.CREAM, (x - 2, y - 2), 2)

    def _draw_journal(self, surface: pygame.Surface) -> None:
        """Боковая панель журнала: доска остаётся полностью видимой."""
        theme.draw_panel(surface, self.journal_rect, fill=theme.EMERALD)
        theme.draw_text(surface, "Журнал ходов", theme.font(21, bold=True),
                        theme.CREAM, midleft=(832, 120))
        pygame.draw.line(surface, theme.COPPER_DARK, (832, 138), (1060, 138))
        self.scroll.draw(surface)

    def _draw_controls(self, surface: pygame.Surface) -> None:
        self.hint_button.draw(surface)
        self.surrender_button.draw(surface)
        self.menu_button.draw(surface)
        theme.draw_text(surface, "Клик по своей лунке — ход • H — подсказка • Esc — меню",
                        theme.font(16), theme.TEXT_DIM, midleft=(88, 740))

    def _draw_banner(self, surface: pygame.Surface) -> None:
        alpha = int(min(255, self.banner_timer * 110))
        image = theme.font(26, display=True).render(self.banner, True, theme.CREAM)
        image.set_alpha(alpha)
        surface.blit(image, image.get_rect(center=(400, 692)))

    def _draw_round_panel(self, surface: pygame.Surface) -> None:
        surface.blit(_fade(surface, 150), (0, 0))
        panel = pygame.Rect(SCREEN_W // 2 - 280, 300, 560, 240)
        theme.draw_panel(surface, panel, fill=theme.EMERALD)
        theme.draw_text(surface, "Партия окончена", theme.font(40, display=True),
                        theme.CREAM, center=(panel.centerx, panel.y + 54))
        theme.draw_text(surface,
                        f"Счёт матча: {self.match_scores[HAND]} : {self.match_scores[BOT]} "
                        f"• играем до {self.limit}",
                        theme.font(22), theme.TEXT,
                        center=(panel.centerx, panel.y + 122))
        self.next_round_button.draw(surface)

    def _draw_dialog(self, surface: pygame.Surface) -> None:
        surface.blit(_fade(surface, 170), (0, 0))
        panel = pygame.Rect(SCREEN_W // 2 - 250, 330, 500, 210)
        theme.draw_panel(surface, panel, fill=theme.EMERALD)
        if self.surrender_dialog:
            title = "Сдаться?"
            body = "Поражение будет сохранено в таблице рекордов."
        else:
            pit = (self.tuzdyk_dialog or {}).get("pit", "")
            title = f"Поставить туздык в лунку {pit}?"
            body = "Лунка станет вашей: все попавшие кумалаки пойдут в ваш казан."
        theme.draw_text(surface, title, theme.font(30, display=True), theme.CREAM,
                        center=(panel.centerx, panel.y + 52))
        theme.draw_text(surface, body, theme.font(19), theme.TEXT,
                        center=(panel.centerx, panel.y + 96))
        self.dialog_yes.draw(surface)
        self.dialog_no.draw(surface)


class ResultScene(Scene):
    """Итог матча с автосохранением результата в таблицу рекордов."""

    def __init__(self, app: Any = None, source: Any = None):
        super().__init__(app)
        data = self._extract(source)
        self.name = str(data.get("name") or "Игрок")
        self.difficulty = str(data.get("difficulty") or MEDIUM)
        self.score = int(data.get("score") or 0)
        self.opponent_score = int(data.get("opponent_score") or 0)
        self.winner = data.get("winner")
        self.reason = str(data.get("reason") or "")
        self.surrendered = bool(data.get("surrendered", False))
        self.rounds = int(data.get("rounds") or 1)
        self.moves = int(data.get("moves") or 0)
        self.limit = int(data.get("limit") or 100)

        self.saved = False
        self.best = self.score
        self.warning = ""
        # рекорд сохраняется сразу при входе: он не должен зависеть от кнопок
        try:
            result_text = (RESULT_WIN if self.winner == HAND
                           else RESULT_LOSS if self.winner == BOT
                           else RESULT_DRAW)
            self.store.add(self.name, self.score,
                           opponent_score=self.opponent_score,
                           result=result_text, difficulty=self.difficulty,
                           rounds=self.rounds, moves=self.moves)
            self.saved = True
            self.best = self.store.best_score(self.name)
        except Exception as exc:
            self.warning = f"Не удалось сохранить рекорд: {exc}"
        try:
            if getattr(self.store, "last_error", None):
                self.warning = str(self.store.last_error)
        except Exception:
            pass
        if self.saved:
            _sound_effect("win")

        self.again_button = Button(pygame.Rect(80, 590, 205, 62),
                                   "Играть снова", self._again, 24)
        self.records_button = Button(pygame.Rect(305, 590, 205, 62),
                                     "Рекорды", self._records, 24)
        self.menu_button = Button(pygame.Rect(530, 590, 205, 62),
                                  "В меню", self._menu, 24, accent=True)

    @staticmethod
    def _extract(source: Any) -> dict:
        if isinstance(source, dict):
            return dict(source)
        if source is None:
            return {}
        getter = getattr(source, "match_result", None)
        if callable(getter):
            try:
                value = getter()
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
        return {
            "name": getattr(source, "player_name", getattr(source, "name", "Игрок")),
            "difficulty": getattr(source, "difficulty", MEDIUM),
            "score": getattr(source, "score", 0),
            "opponent_score": getattr(source, "opponent_score", 0),
            "winner": getattr(source, "winner", None),
            "reason": getattr(source, "reason", ""),
            "surrendered": getattr(source, "surrendered", False),
            "rounds": getattr(source, "rounds", 1),
            "moves": getattr(source, "moves", 0),
            "limit": getattr(source, "limit", 100),
        }

    def _again(self) -> None:
        self._emit(Transition("replace", GameScene(
            self.app, self.name, self.difficulty, self.limit)))

    def _records(self) -> None:
        self._emit(Transition("push", RecordsScene(self.app)))

    def _menu(self) -> None:
        self._emit(Transition("menu"))

    def handle_event(self, event: pygame.event.Event) -> Optional[Transition]:
        for button in (self.again_button, self.records_button, self.menu_button):
            button.handle_event(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._menu()
            elif event.key == pygame.K_RETURN:
                self._again()
        return self.take_transition()

    def update(self, dt: float) -> Optional[Transition]:
        return super().update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        self.draw_background(surface)
        title = ("Победа!" if self.winner == HAND else
                 ("Вы сдались" if self.surrendered else "Поражение")
                 if self.winner == BOT else "Ничья")
        theme.draw_text(surface, title, theme.font(74, display=True), theme.CREAM,
                        midleft=(88, 96))
        subtitle = self.reason or ("Матч завершён" if not self.winner else "")
        theme.draw_text(surface, subtitle, theme.font(23), theme.TEXT_DIM,
                        midleft=(96, 182))

        board = pygame.Rect(80, 240, SCREEN_W - 160, 310)
        theme.draw_panel(surface, board, fill=theme.EMERALD)
        theme.draw_text(surface, "ИТОГОВЫЙ СЧЁТ", theme.font(15, bold=True),
                        theme.TEXT_DIM, midleft=(110, 274))
        theme.draw_text(surface, f"{self.score} : {self.opponent_score}",
                        theme.font(78, bold=True), theme.CREAM,
                        midleft=(104, 314))
        fmt = "одна партия" if self.limit == 1 else f"до {self.limit} кумалаков"
        theme.draw_text(surface,
                        f"Партий: {self.rounds} • Ходов: {self.moves} • "
                        f"Сложность: {_difficulty_label(self.difficulty)} • {fmt}",
                        theme.font(20), theme.TEXT_DIM,
                        midleft=(110, 428))
        pygame.draw.line(surface, theme.COPPER_DARK, (110, 468), (SCREEN_W - 110, 468))
        theme.draw_text(surface,
                        ("Рекорд сохранён. " if self.saved else "")
                        + f"Лучший результат: {self.best}",
                        theme.font(20), theme.TEXT, midleft=(110, 496))
        if self.warning:
            for i, line in enumerate(theme.wrap_text(self.warning, theme.font(18), 640)[:3]):
                theme.draw_text(surface, line, theme.font(18), theme.RED,
                                midleft=(110, 522 + i * 23))

        for button in (self.again_button, self.records_button, self.menu_button):
            button.draw(surface)
        self.message.draw(surface)


class RecordsScene(Scene):
    """Таблица рекордов: фильтр, сортировка, очистка с подтверждением."""

    COLUMNS = (
        ("Игрок", 0.20), ("Счёт", 0.10), ("Соперник", 0.13),
        ("Результат", 0.14), ("Сложность", 0.17), ("Дата", 0.26),
    )

    def __init__(self, app: Any = None):
        super().__init__(app)
        self.filter_input = TextInput(pygame.Rect(80, 158, 420, 56),
                                      placeholder="Фильтр по имени игрока",
                                      max_length=32, font_size=22)
        self.sort_by_score = True
        self.sort_button = Button(pygame.Rect(520, 158, 230, 56),
                                  "Сортировка: очки", self._toggle_sort, 21)
        self.clear_button = Button(pygame.Rect(80, 690, 220, 52),
                                   "Очистить всё", self._clear, 22)
        self.back_button = Button(pygame.Rect(900, 690, 180, 52),
                                  "Назад", self._back, 24)
        self.yes_button = Button(pygame.Rect(SCREEN_W // 2 - 190, 330, 170, 54),
                                 "Да, очистить", self._confirm_clear, 22, accent=True)
        self.no_button = Button(pygame.Rect(SCREEN_W // 2 + 20, 330, 170, 54),
                                "Отмена", self._cancel_clear, 22)
        self.table_rect = pygame.Rect(80, 240, 940, 420)
        self.row_height = 40
        self.scroll_offset = 0.0
        self.confirming = False

    def _toggle_sort(self) -> None:
        self.sort_by_score = not self.sort_by_score
        self.sort_button.label = ("Сортировка: очки" if self.sort_by_score
                                  else "Сортировка: дата")

    def _clear(self) -> None:
        self.confirming = True

    def _confirm_clear(self) -> None:
        try:
            self.store.clear()
        except Exception as exc:
            self.message.show(f"Не удалось очистить таблицу: {exc}", 3.0, theme.RED)
        else:
            self.message.show("Таблица рекордов очищена", 2.5, theme.GOLD)
        self.confirming = False
        self.scroll_offset = 0.0

    def _cancel_clear(self) -> None:
        self.confirming = False

    def _back(self) -> None:
        self._emit(Transition("pop"))

    def _rows(self) -> List[Any]:
        try:
            records = self.store.filtered(self.filter_input.value())
            return self.store.sorted_records(records,
                                             "score" if self.sort_by_score else "date")
        except Exception:
            return []

    def handle_event(self, event: pygame.event.Event) -> Optional[Transition]:
        if self.confirming:
            self.yes_button.handle_event(event)
            self.no_button.handle_event(event)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._cancel_clear()
                elif event.key == pygame.K_RETURN:
                    self._confirm_clear()
            return self.take_transition()

        self.filter_input.handle_event(event)
        self.sort_button.handle_event(event)
        self.clear_button.handle_event(event)
        self.back_button.handle_event(event)
        if event.type == pygame.MOUSEWHEEL and self.table_rect.collidepoint(pygame.mouse.get_pos()):
            self.scroll_offset = max(0.0, self.scroll_offset - event.y * self.row_height)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._back()
            elif event.key == pygame.K_RETURN and self.filter_input.focused:
                self.filter_input.focused = False
        return self.take_transition()

    def update(self, dt: float) -> Optional[Transition]:
        super().update(dt)
        self.filter_input.update(dt)
        return self.take_transition()

    def draw(self, surface: pygame.Surface) -> None:
        self.draw_background(surface)
        theme.draw_text(surface, "Таблица рекордов",
                        theme.font(48, display=True), theme.CREAM,
                        midleft=(80, 68))
        pygame.draw.line(surface, theme.COPPER_DARK, (80, 118), (300, 118))
        warning = ""
        try:
            warning = str(getattr(self.store, "last_error", "") or "")
        except Exception:
            pass
        if warning:
            line = theme.wrap_text("Внимание: " + warning, theme.font(17), SCREEN_W - 100)[0]
            theme.draw_text(surface, line, theme.font(17), theme.RED,
                            midleft=(80, 132))

        theme.draw_text(surface, "Фильтр:", theme.font(21, bold=True),
                        theme.TEXT, midleft=(80, 142))
        self.filter_input.draw(surface)
        self.sort_button.draw(surface)

        theme.draw_panel(surface, self.table_rect, fill=theme.EMERALD)
        font_header = theme.font(19, bold=True)
        font_cell = theme.font(18)
        header_y = self.table_rect.y
        pygame.draw.rect(surface, theme.EMERALD_LIGHT,
                         pygame.Rect(self.table_rect.x, header_y,
                                     self.table_rect.width, 34))
        x = self.table_rect.x + 10
        for title, share in self.COLUMNS:
            theme.draw_text(surface, title, font_header, theme.CREAM,
                            midleft=(x, header_y + 17))
            x += int(self.table_rect.width * share)

        rows = self._rows()
        visible = max(1, (self.table_rect.height - 42) // self.row_height)
        if not rows:
            query = self.filter_input.value()
            empty = (f"Ничего не найдено по фильтру «{query}»" if query
                     else "Записей пока нет — сыграйте первую партию!")
            theme.draw_text(surface, empty, theme.font(23), theme.TEXT_DIM,
                            center=self.table_rect.center)
        else:
            offset = min(int(self.scroll_offset), max(0, len(rows) - visible))
            y = header_y + 40
            for index, record in enumerate(rows[offset:offset + visible]):
                if index % 2 == 0:
                    pygame.draw.rect(surface, theme.EMERALD_LIGHT,
                                     pygame.Rect(self.table_rect.x + 4, y - 3,
                                                 self.table_rect.width - 8, self.row_height))
                cells = (
                    (str(getattr(record, "name", "")), theme.TEXT),
                    (str(getattr(record, "score", 0)), theme.CREAM),
                    (str(getattr(record, "opponent_score", 0)), theme.TEXT_DIM),
                    (str(getattr(record, "result", "")), theme.CREAM),
                    (_difficulty_label(getattr(record, "difficulty", "")), theme.TEXT_DIM),
                    (str(getattr(record, "date", "")), theme.TEXT_DIM),
                )
                x = self.table_rect.x + 10
                for (_title, share), (value, color) in zip(self.COLUMNS, cells):
                    theme.draw_text(surface, value, font_cell, color,
                                    midleft=(x, y + self.row_height // 2 - 2))
                    x += int(self.table_rect.width * share)
                y += self.row_height
            if len(rows) > visible:
                bar_x = self.table_rect.right - 8
                pygame.draw.rect(surface, theme.EMERALD,
                                 pygame.Rect(bar_x, header_y + 38, 3,
                                             self.table_rect.height - 44))
                bar_h = max(30, int((self.table_rect.height - 44) * visible / len(rows)))
                max_off = max(1, len(rows) - visible)
                bar_y = header_y + 38 + int(
                    (self.table_rect.height - 44 - bar_h) * (offset / max_off))
                pygame.draw.rect(surface, theme.COPPER_DARK,
                                 pygame.Rect(bar_x, bar_y, 3, bar_h))

        self.clear_button.draw(surface)
        self.back_button.draw(surface)
        if self.confirming:
            surface.blit(_fade(surface, 160), (0, 0))
            panel = pygame.Rect(SCREEN_W // 2 - 260, 270, 520, 180)
            theme.draw_panel(surface, panel, fill=theme.EMERALD)
            theme.draw_text(surface, "Точно очистить всё?", theme.font(32, display=True),
                            theme.CREAM, center=(panel.centerx, panel.y + 48))
            theme.draw_text(surface, "Все записи таблицы рекордов будут удалены.",
                            theme.font(19), theme.TEXT,
                            center=(panel.centerx, panel.y + 88))
            self.yes_button.draw(surface)
            self.no_button.draw(surface)
        self.message.draw(surface)


__all__ = [
    "SCREEN_W", "SCREEN_H", "Transition", "apply_transition", "Scene",
    "MenuScene", "RulesScene", "NameScene", "GameScene", "ResultScene", "RecordsScene",
]

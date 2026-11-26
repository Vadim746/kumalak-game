"""Headless-проверка всех модулей проекта без исключений.

Запуск: ``.venv/bin/python tests/smoke.py`` из корня проекта.
Окно не показывается: pygame работает через заглушку ``SDL_VIDEODRIVER=dummy``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# При прямом запуске из корня проекта ``sys.path`` указывает на tests/.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Заглушку необходимо выставить до импорта pygame.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from game.ai import Bot, EASY, HARD, MEDIUM  # noqa: E402
from game.kumalak import KumalakGame, Move  # noqa: E402
from storage import RecordStore  # noqa: E402
from ui import theme, widgets  # noqa: E402


def check_rules() -> None:
    """«Щелчок» по ядру: партия, нотация, туздык, копирование."""
    game = KumalakGame()
    assert game.total_stones() == 162
    assert game.notation(Move(7)) == "76"
    result = game.apply_move(Move(7))
    assert result.captured > 0
    assert game.total_stones() == 162
    clone = game.clone()
    clone.apply_move(clone.legal_moves()[0])
    assert game.move_number != clone.move_number


def check_ai() -> None:
    """«Щелчок» по боту: все уровни делают ход, не мутируя позицию."""
    for level in (EASY, MEDIUM, HARD):
        game = KumalakGame()
        bot = Bot(level, seed=1, time_limit=0.02)
        move = bot.choose_move(game)
        assert move in game.legal_moves()
        bot.choose_tuzdyk(game, move)
        assert bot.describe()
        assert game.total_stones() == 162


def check_storage() -> None:
    """«Щелчок» по таблице рекордов во временном каталоге."""
    with tempfile.TemporaryDirectory() as directory:
        store = RecordStore(Path(directory) / "records.json")
        store.add("Тест", 82, 79, "победа", "Средний", rounds=1, moves=42)
        assert len(store.filtered("тест")) == 1
        assert len(store.sorted_records(key="очки")) == 1
        store.clear()
        assert len(store) == 0


def check_ui() -> None:
    """Headless-отрисовка панели, текста, кнопки, поля ввода и скролла."""
    pygame.init()
    try:
        # ``Surface.convert()`` в theme требует инициализированный дисплей.
        pygame.display.set_mode((640, 420))
        surface = pygame.Surface((640, 420))
        theme.get_baize(surface.get_size())
        theme.draw_panel(surface, pygame.Rect(10, 10, 400, 300))
        theme.draw_text(surface, "Кумалак", theme.font(28, bold=True), theme.CREAM,
                        center=(200, 60))

        clicked = []

        def on_click():
            """Фиксирует нажатие кнопки для проверки обработчика."""
            clicked.append(True)

        button = widgets.Button(pygame.Rect(20, 100, 200, 50), "Играть", on_click)
        button.draw(surface)
        button.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(50, 120)))
        button.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                               pos=(50, 120)))
        button.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                                               pos=(50, 120)))
        assert clicked

        field = widgets.TextInput(pygame.Rect(20, 180, 200, 44), "Алиса")
        field.draw(surface)
        field.set_error("Введите имя")
        field.draw(surface)
        field.update(0.016)

        scroll = widgets.ScrollBox(pygame.Rect(260, 20, 340, 360))
        scroll.set_lines([("Ход 1", theme.font(20), theme.CREAM)])
        scroll.draw(surface)

        message = widgets.Message()
        message.show("Рекорд сохранён")
        message.update(0.016)
        message.draw(surface)
    finally:
        pygame.quit()


def main() -> None:
    """Последовательно проверяет все модули и печатает итог."""
    check_rules()
    check_ai()
    check_storage()
    check_ui()
    print("Smoke-проверка пройдена: game, ai, storage, ui — без исключений.")


if __name__ == "__main__":
    main()

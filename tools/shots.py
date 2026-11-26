"""Headless-скриншоты всех экранов игры «Кумалак».

Запуск из корня проекта::

    .venv/bin/python -m tools.shots [папка]

По умолчанию PNG-файлы пишутся в ``shots`` рядом с проектом. Скрипт не требует
монитора и эмулятора: SDL переводится в ``dummy``-режим до импорта pygame.
Импорт ``main``/``ui.scenes`` защищён — если сцены ещё не готовы, вместо них
сохраняются заглушки, и скрипт всё равно завершается успешно.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

# Dummy-драйверы обязательно выставляем ДО импорта pygame.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "shots"

try:
    import pygame
except Exception as exc:  # без графической библиотеки делать нечего
    print(f"Не удалось импортировать pygame: {exc}")
    raise SystemExit(1)


theme: Any = None
RecordStore: Any = None
GameApp: Any = None
scene_module: Any = None
IMPORT_NOTES: list[str] = []

for module_name, attr, holder in (
    ("ui.theme", None, "theme"),
    ("storage", "RecordStore", "RecordStore"),
    ("main", "App", "GameApp"),
    ("ui.scenes", None, "scene_module"),
):
    try:
        imported = __import__(module_name, fromlist=["*"])
        value = imported if attr is None else getattr(imported, attr)
    except Exception as exc:
        IMPORT_NOTES.append(f"{module_name}: {exc}")
        continue
    if holder == "theme":
        theme = value
    elif holder == "RecordStore":
        RecordStore = value
    elif holder == "GameApp":
        GameApp = value
    else:
        scene_module = value

for note in IMPORT_NOTES:
    print(f"Защищённый импорт: {note}")


def _size() -> tuple[int, int]:
    """Размер окна из темы либо значение по умолчанию."""
    if theme is not None:
        return (int(getattr(theme, "SCREEN_W", 1100)), int(getattr(theme, "SCREEN_H", 760)))
    return (1100, 760)


class HeadlessApp:
    """Минимальная замена ``App``, если ``main.py`` пока недоступен."""

    def __init__(self) -> None:
        width, height = _size()
        self.screen = pygame.display.set_mode((width, height))
        self.clock = pygame.time.Clock()
        self.running = True
        self.scenes: list[Any] = []
        self.store = (
            RecordStore(path=Path(OUT_DIR) / "records.json") if RecordStore else None
        )
        pygame.display.set_caption("Кумалак — скриншоты")

    @property
    def scene(self) -> Any:
        """Верхняя сцена стека."""
        return self.scenes[-1] if self.scenes else None

    def push(self, scene: Any) -> None:
        """Кладёт сцену в стек и вызывает ``on_enter``."""
        self.scenes.append(scene)
        if hasattr(scene, "on_enter"):
            scene.on_enter()

    def pop(self) -> None:
        """Снимает верхнюю сцену, если она не единственная."""
        if len(self.scenes) > 1:
            self.scenes.pop()

    def pop_to_menu(self) -> None:
        """Оставляет в стеке только первую (меню) сцену."""
        self.scenes = self.scenes[:1]

    def set_title(self, title: str) -> None:
        """Меняет заголовок окна."""
        pygame.display.set_caption(title)

    def start_game(self, *args: Any, **kwargs: Any) -> None:
        """Заглушка для сцен, которые вызывают запуск матча через App."""

    def finish_game(self, *args: Any, **kwargs: Any) -> None:
        """Заглушка для сцен, которые вызывают экран итогов через App."""


def create_app() -> Any:
    """Создаёт приложение: настоящее, либо запасное headless-приложение."""
    if GameApp is not None:
        try:
            app = GameApp()
        except Exception as exc:
            print(f"Не удалось создать App, используется запасной: {exc}")
            app = HeadlessApp()
    else:
        app = HeadlessApp()

    # Скриншоты не должны портить records.json рядом с программой.
    if RecordStore is not None:
        try:
            app.store = RecordStore(path=Path(OUT_DIR) / "records.json")
        except Exception as exc:
            print(f"Не удалось создать тестовое хранилище: {exc}")
    return app


def _construct(constructor: Any, signatures: list[tuple]) -> Any:
    """Пробует несколько сигнатур конструктора сцены (API мог измениться)."""
    if constructor is None:
        return None
    last_error: Optional[Exception] = None
    for args in signatures:
        try:
            return constructor(*args)
        except Exception as exc:
            last_error = exc
    print(f"Не удалось создать {getattr(constructor, '__name__', constructor)}: {last_error}")
    return None


def _set_input(scene: Any, names: tuple[str, ...], value: str) -> None:
    """Заполняет поле ввода сцены, если оно есть."""
    if scene is None:
        return
    for name in names:
        field = getattr(scene, name, None)
        if field is None:
            continue
        try:
            if hasattr(field, "text"):
                field.text = value
            else:
                setattr(scene, name, value)
        except Exception as exc:
            print(f"Не удалось заполнить поле {name}: {exc}")
        return


def _advance_match(game_scene: Any, steps: int = 6) -> None:
    """Делает несколько ходов, чтобы на скриншоте была не начальная позиция."""
    core = getattr(game_scene, "game", None)
    if core is None:
        return
    for _ in range(steps):
        try:
            if getattr(core, "over", False):
                break
            if getattr(core, "turn", 0) == 1:
                bot_step = getattr(game_scene, "_bot_step", None)
                if bot_step:
                    bot_step()
                    continue
            moves = list(core.legal_moves())
            if not moves:
                break
            move = moves[0]
            play: Callable[..., Any] = getattr(game_scene, "_play", None) or getattr(
                game_scene, "play", None
            )
            if play:
                try:
                    play(getattr(move, "pit", 1))
                    continue
                except Exception:
                    pass
            core.apply_move(move)
        except Exception as exc:
            print(f"Ход пропущен при подготовке скриншота: {exc}")
            break


def build_screens(app: Any) -> list[tuple[str, Any, str]]:
    """Возвращает список ``(имя PNG, сцена, заголовок)`` в порядке экранов."""
    placeholders = [
        ("1_menu.png", "Меню — «Кумалак»"),
        ("2_name.png", "Ввод имени"),
        ("3_rules.png", "Правила игры"),
        ("4_game.png", "Партия"),
        ("5_result.png", "Итог матча"),
        ("6_records.png", "Таблица рекордов"),
    ]
    if scene_module is None:
        return [(name, None, title) for name, title in placeholders]

    menu_cls = getattr(scene_module, "MenuScene", None)
    name_cls = getattr(scene_module, "NameScene", None)
    rules_cls = getattr(scene_module, "RulesScene", None)
    game_cls = getattr(scene_module, "GameScene", None)
    result_cls = getattr(scene_module, "ResultScene", None)
    records_cls = getattr(scene_module, "RecordsScene", None)

    menu = _construct(menu_cls, [(app,)])
    name = _construct(name_cls, [(app,)])
    _set_input(name, ("name_input", "input", "text_input", "name_field"), "Аня")
    rules = _construct(rules_cls, [(app,)])

    store = getattr(app, "store", None)
    if store is not None:
        try:
            store.add("Аня", 84, 71, "победа", "Средний", 1, 38)
            store.add("Борис", 78, 82, "поражение", "Сложный", 1, 52)
            store.add("Анна", 81, 81, "ничья", "Лёгкий", 1, 61)
        except Exception as exc:
            print(f"Не удалось заполнить таблицу рекордов: {exc}")

    records = _construct(records_cls, [(app,)])
    _set_input(records, ("filter_input", "filter", "name_filter", "input"), "ан")

    game = _construct(
        game_cls,
        [
            (app, "Аня", "Средний", 100),
            (app, "Аня", "Средний"),
            (app,),
        ],
    )
    if game is not None:
        _advance_match(game)
    result = _construct(result_cls, [(app, game), (app,)])

    return [
        ("1_menu.png", menu, "Меню — «Кумалак»"),
        ("2_name.png", name, "Ввод имени"),
        ("3_rules.png", rules, "Правила игры"),
        ("4_game.png", game, "Партия"),
        ("5_result.png", result, "Итог матча"),
        ("6_records.png", records, "Таблица рекордов"),
    ]


def draw_placeholder(screen: Any, title: str, detail: str = "") -> None:
    """Рисует заглушку, если соответствующая сцена недоступна.

    Не выбрасывает исключений даже без рабочего ``pygame.font``.
    """
    try:
        width, height = screen.get_size()
        if theme is not None:
            try:
                screen.blit(theme.baize_background((width, height)), (0, 0))
                theme.ornament(screen)
                panel = pygame.Rect(width // 2 - 330, height // 2 - 130, 660, 260)
                theme.draw_panel(screen, panel)
                theme.draw_text(
                    screen,
                    "Кумалак",
                    theme.font(46, display=True),
                    theme.GOLD,
                    center=(width // 2, height // 2 - 68),
                )
                theme.draw_text(
                    screen,
                    title,
                    theme.font(30),
                    theme.CREAM,
                    center=(width // 2, height // 2),
                )
                theme.draw_text(
                    screen,
                    detail or "Сцена ещё не подключена — показана заглушка",
                    theme.font(18),
                    theme.TEXT_DIM,
                    center=(width // 2, height // 2 + 62),
                )
                return
            except Exception as exc:
                print(f"Ошибка отрисовки заглушки через тему: {exc}")

        # Запасной путь — без шрифтов и без модуля theme.
        screen.fill((9, 40, 31))
        panel = pygame.Rect(width // 2 - 330, height // 2 - 130, 660, 260)
        pygame.draw.rect(screen, (17, 68, 50), panel, border_radius=10)
        pygame.draw.rect(screen, (222, 183, 94), panel, width=2, border_radius=10)
        try:
            font = pygame.font.SysFont("arial", 32)
            image = font.render(title or "Кумалак", True, (222, 183, 94))
            screen.blit(image, image.get_rect(center=(width // 2, height // 2)))
        except Exception as exc:
            print(f"Шрифт недоступен, заглушка без текста: {exc}")
    except Exception as exc:
        print(f"Не удалось нарисовать заглушку: {exc}")
        try:
            screen.fill((9, 40, 31))
        except Exception:
            pass


def save_screen(app: Any, scene: Any, filename: str, title: str) -> None:
    """Рисует сцену (или заглушку) и сохраняет её в PNG."""
    path = os.path.join(OUT_DIR, filename)
    if scene is not None and hasattr(scene, "draw"):
        scene.draw(app.screen)
    else:
        draw_placeholder(app.screen, title, filename)
    pygame.display.flip()
    pygame.image.save(app.screen, path)
    print("сохранено:", path)


def main() -> int:
    """Точка входа: создать приложение, отрисовать и сохранить все экраны."""
    os.makedirs(OUT_DIR, exist_ok=True)
    pygame.init()
    try:
        app = create_app()
        for filename, scene, title in build_screens(app):
            try:
                save_screen(app, scene, filename, title)
            except Exception as exc:
                print(f"Не удалось отрисовать {filename}: {exc}")
                draw_placeholder(app.screen, title, str(exc))
                path = os.path.join(OUT_DIR, filename)
                pygame.image.save(app.screen, path)
                print("сохранена заглушка:", path)
    finally:
        pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

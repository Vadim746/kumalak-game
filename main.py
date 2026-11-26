"""Точка входа игры «Кумалак»."""

from __future__ import annotations

import sys
from typing import Any, List, Optional

import pygame

from storage import RecordStore
from ui import theme
from ui.widgets import Message


def info_exit(message: str, code: int = 0) -> None:
    """Вывести сообщение и корректно выйти."""
    print("ИНФО: " + message)
    sys.exit(code)


class App:
    """Окно, стек сцен и общее состояние приложения."""

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Кумалак")
        self.screen = pygame.display.set_mode((theme.SCREEN_W, theme.SCREEN_H))
        self.background = theme.get_baize((theme.SCREEN_W, theme.SCREEN_H)).convert()
        self.clock = pygame.time.Clock()
        self.running = True
        self.store = RecordStore()
        self.message = Message()

        self.scenes: List[Any] = []
        self.scenes_module: Optional[Any] = self._load_scenes()
        self._init_sounds()

        menu = self.scene_class("MenuScene")
        if menu is None:
            info_exit("Экран меню ещё не готов (проверьте ui/scenes.py).")
        self.push(self.construct(menu))

    @staticmethod
    def _load_scenes() -> Any:
        """Загрузить модуль сцен."""
        try:
            from ui import scenes
        except Exception as exc:
            info_exit(
                "Модуль сцен ui.scenes ещё не готов, запуск отменён. "
                f"Причина: {exc}"
            )
        return scenes

    @staticmethod
    def _init_sounds() -> None:
        """Подключить звук, если он доступен."""
        try:
            from ui import sounds
        except Exception:
            return
        try:
            if hasattr(sounds, "init"):
                sounds.init()
        except Exception:
            pass

    def scene_class(self, name: str) -> Optional[Any]:
        """Класс сцены по имени или ``None``."""
        if self.scenes_module is None:
            return None
        return getattr(self.scenes_module, name, None)

    def construct(self, scene_class: Any, *args: Any) -> Any:
        """Создать сцену."""
        try:
            return scene_class(self, *args)
        except TypeError:
            try:
                return scene_class(self)
            except Exception as exc:
                self.report(exc)
                return None

    @property
    def scene(self) -> Optional[Any]:
        """Верхняя (активная) сцена."""
        return self.scenes[-1] if self.scenes else None

    def _enter(self, scene: Any) -> None:
        """Передать сцене управление."""
        if scene is None or not hasattr(scene, "on_enter"):
            return
        try:
            scene.on_enter()
        except Exception as exc:
            self.report(exc)

    def push(self, scene: Any) -> None:
        """Положить сцену на вершину стека."""
        if scene is None:
            return
        self.scenes.append(scene)
        self._enter(scene)

    def pop(self) -> None:
        """Снять верхнюю сцену, сохранив меню."""
        if len(self.scenes) > 1:
            self.scenes.pop()

    def switch(self, scene: Any) -> None:
        """Заменить текущую сцену новой."""
        if scene is None:
            return
        if self.scenes:
            self.scenes[-1] = scene
        else:
            self.scenes.append(scene)
        self._enter(scene)

    def pop_to_menu(self) -> None:
        """Вернуться в меню."""
        menu_class = self.scene_class("MenuScene")
        menu = None
        if isinstance(menu_class, type):
            for scene in self.scenes:
                if isinstance(scene, menu_class):
                    menu = scene
                    break
            if menu is None:
                menu = self.construct(menu_class)
        self.scenes = [menu] if menu is not None else self.scenes[:1]

    def start_game(self, name: str, difficulty: str, limit: int) -> None:
        """Начать матч."""
        game_class = self.scene_class("GameScene")
        if game_class is None:
            self.report_message("Экран партии ещё не готов.")
            return
        self.switch(self.construct(game_class, name, difficulty, limit))

    def finish_game(self, game_scene: Any) -> None:
        """Показать итоги матча."""
        result_class = self.scene_class("ResultScene")
        if result_class is None:
            self.report_message("Экран итогов ещё не готов.")
            return
        self.push(self.construct(result_class, game_scene))

    def set_title(self, title: str) -> None:
        """Изменить заголовок окна."""
        pygame.display.set_caption(title)

    def handle_event(self, event: pygame.event.Event) -> None:
        """Обработать событие."""
        if event.type == pygame.QUIT:
            self.running = False
            return
        scene = self.scene
        if scene is not None and hasattr(scene, "handle_event"):
            try:
                scene.handle_event(event)
                return
            except Exception as exc:
                self.report(exc)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.pop()

    def update(self, dt: float) -> None:
        """Обновить активную сцену и уведомления."""
        scene = self.scene
        if scene is not None and hasattr(scene, "update"):
            try:
                scene.update(dt)
            except Exception as exc:
                self.report(exc)
        self.message.update(dt)

    def draw(self) -> None:
        """Отрисовать фон, сцену и уведомления."""
        self.screen.blit(self.background, (0, 0))
        scene = self.scene
        if scene is not None and hasattr(scene, "draw"):
            try:
                scene.draw(self.screen)
            except Exception as exc:
                self.report(exc)
        self.message.draw(self.screen)
        pygame.display.flip()

    def run(self) -> None:
        """Запустить главный цикл."""
        try:
            while self.running:
                dt = self.clock.tick(theme.FPS) / 1000.0
                for event in pygame.event.get():
                    self.handle_event(event)
                    if not self.running:
                        break
                if not self.running:
                    break
                self.update(dt)
                self.draw()
        except Exception as exc:
            print(f"Ошибка во время игры: {exc}", file=sys.stderr)
            self.report_message("Игра завершилась из-за ошибки. Попробуйте ещё раз.")
        finally:
            pygame.quit()

    def report_message(self, text: str) -> None:
        """Показать русское уведомление в интерфейсе."""
        try:
            self.message.show(text, 3.5, (255, 140, 130))
        except Exception:
            pass

    def report(self, exc: BaseException) -> None:
        """Сообщить об ошибке пользователю."""
        print(f"Ошибка: {exc}", file=sys.stderr)
        self.report_message("Действие не выполнено — попробуйте ещё раз.")


def main() -> None:
    """Создать приложение и запустить игру."""
    try:
        app = App()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Не удалось запустить игру: {exc}", file=sys.stderr)
        print("Проверьте установку pygame-ce и файлы проекта.", file=sys.stderr)
        sys.exit(1)
    app.run()
    sys.exit(0)


if __name__ == "__main__":
    main()

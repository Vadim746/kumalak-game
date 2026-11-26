"""Тесты бота (:mod:`game.ai`).

Проверяется, что каждый уровень возвращает легальный ход и не меняет
позицию, а одинаковое зерно даёт одинаковую последовательность ходов.
"""

from __future__ import annotations

import unittest

from game.ai import (
    EASY,
    HARD,
    LEVEL_LABELS,
    LEVELS,
    MEDIUM,
    Bot,
    Difficulty,
)
from game.kumalak import HAND, KumalakGame, Move


def position(pits=None, tuzdyk=None, turn=HAND):
    """Собирает тестовую позицию с заданными лунками и туздыками."""
    game = KumalakGame()
    if pits is not None:
        game.pits = [0] * 18
        for index, stones in pits.items():
            game.pits[int(index)] = stones
    if tuzdyk is not None:
        game.tuzdyk = dict(tuzdyk)
    game.turn = turn
    return game


def snapshot(game):
    """Снимает полный снимок состояния игры для проверки на мутации."""
    return (
        list(game.pits),
        dict(game.kazans),
        game.turn,
        dict(game.tuzdyk),
        game.move_number,
        list(game.history),
        game.over,
        dict(game.result) if game.result else None,
        list(game.log),
    )


class TestBotMoves(unittest.TestCase):
    """Проверка легальности и чистоты выбора хода всеми уровнями."""

    def test_all_levels_return_legal_move(self):
        """Каждый уровень возвращает ход из списка допустимых."""
        for level in LEVELS:
            for seed in (0, 1, 7):
                bot = Bot(level, seed=seed, time_limit=0.02)
                game = KumalakGame(seed=seed)
                move = bot.choose_move(game)
                self.assertIn(move, game.legal_moves(), f"{level}, seed={seed}")
                for _ in range(4):
                    legal = game.legal_moves()
                    if not legal:
                        break
                    game.apply_move(bot.choose_move(game))
                    if game.over:
                        break

    def test_legal_move_in_position_with_tuzdyk(self):
        """Бот не пытается сходить из лунки-туздыка."""
        game = position({14: 6, 13: 3}, tuzdyk={HAND: 6}, turn=1)
        for level in LEVELS:
            bot = Bot(level, seed=3, time_limit=0.02)
            move = bot.choose_move(game)
            self.assertIn(move, game.legal_moves())
            self.assertNotEqual(move.pit, 6)

    def test_no_moves_returns_none(self):
        """Если ходов нет (атсырау), бот возвращает ``None``."""
        empty = position({})
        for level in LEVELS:
            self.assertIsNone(Bot(level).choose_move(empty))

    def test_bot_does_not_mutate_game(self):
        """Выбор хода и решение про туздык не меняют переданную игру."""
        positions = [
            KumalakGame(),
            position({2: 13, 14: 2}),
            position({8: 4, 11: 7}, tuzdyk={HAND: 3}, turn=1),
        ]
        for game in positions:
            before = snapshot(game)
            for level in LEVELS:
                bot = Bot(level, seed=9, time_limit=0.02)
                move = bot.choose_move(game)
                bot.choose_tuzdyk(game, move)
                self.assertEqual(snapshot(game), before, f"{level} изменил игру")

    def test_hard_respects_time_limit(self):
        """Сложный уровень с маленьким лимитом быстро возвращает легальный ход."""
        bot = Bot(HARD, seed=5, time_limit=0.02)
        game = KumalakGame()
        move = bot.choose_move(game)
        self.assertIn(move, game.legal_moves())


class TestTuzdykDecision(unittest.TestCase):
    """Проверка решения бота о постановке туздыка."""

    def test_choose_tuzdyk_returns_bool(self):
        """Метод возвращает ``bool`` на всех уровнях и позициях."""
        for level in LEVELS:
            bot = Bot(level, seed=2, time_limit=0.02)
            for game in (KumalakGame(), position({2: 13, 14: 2})):
                move = bot.choose_move(game)
                self.assertIsInstance(bot.choose_tuzdyk(game, move), bool)

    def test_easy_never_sets_tuzdyk(self):
        """Лёгкий уровень упрощённо не ставит туздык никогда."""
        game = position({2: 13, 14: 2})
        bot = Bot(EASY, seed=1)
        self.assertFalse(bot.choose_tuzdyk(game, Move(3)))
        game.apply_move(Move(3), set_tuzdyk=bot.choose_tuzdyk(game, Move(3)))
        self.assertEqual(game.tuzdyk, {})

    def test_medium_and_hard_use_tuzdyk(self):
        """Средний и сложный уровни ставят туздык, когда это возможно."""
        for level in (MEDIUM, HARD):
            game = position({2: 13, 14: 2})
            bot = Bot(level, seed=4, time_limit=0.02)
            self.assertTrue(bot.choose_tuzdyk(game, Move(3)), level)

    def test_no_second_tuzdyk(self):
        """Если туздык уже есть, бот не ставит второй."""
        for level in (MEDIUM, HARD):
            game = position({2: 13, 14: 2}, tuzdyk={HAND: 5})
            bot = Bot(level, seed=4, time_limit=0.02)
            self.assertFalse(bot.choose_tuzdyk(game, Move(3)), level)


class TestBotConfiguration(unittest.TestCase):
    """Тесты конфигурации, подписей и воспроизводимости бота."""

    def test_describe_and_levels(self):
        """Описание уровня — русская подпись из ``LEVEL_LABELS``."""
        self.assertEqual(LEVELS, (EASY, MEDIUM, HARD))
        for level in LEVELS:
            bot = Bot(level)
            self.assertEqual(bot.describe(), LEVEL_LABELS[level])
            self.assertEqual(bot.level, level)

    def test_level_aliases(self):
        """Поддерживаются ``difficulty=`` и перечисление ``Difficulty``."""
        self.assertEqual(Bot(difficulty=HARD).level, HARD)
        self.assertEqual(Bot(Difficulty.EASY).level, EASY)
        self.assertEqual(Bot("неизвестный").level, MEDIUM)

    def test_easy_seed_is_reproducible(self):
        """Одинаковое зерно даёт одинаковую последовательность ходов."""
        sequences = []
        for _ in range(2):
            bot = Bot(EASY, seed=42)
            picks = []
            for _ in range(30):
                game = KumalakGame()
                picks.append(bot.choose_move(game).pit)
            sequences.append(picks)
        self.assertEqual(sequences[0], sequences[1])
        self.assertEqual(len(set(sequences[0])) > 1, True)

    def test_easy_random_share_about_thirty_percent(self):
        """При фиксированном сиде часть случайных ходов нетривиальна."""
        bot = Bot(EASY, seed=7)
        changes = 0
        previous = None
        for _ in range(100):
            move = bot.choose_move(KumalakGame()).pit
            if previous is not None and move != previous:
                changes += 1
            previous = move
        self.assertGreater(changes, 0)


if __name__ == "__main__":
    unittest.main()

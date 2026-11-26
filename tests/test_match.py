"""Интеграционные тесты: полный матч бота против бота.

Проверяется, что партия доигрывается до результата без зацикливания,
инвариант кумалаков соблюдается на всём протяжении матча.
"""

from __future__ import annotations

import unittest

from game.ai import Bot, EASY, HARD, MEDIUM
from game.kumalak import TOTAL_STONES, KumalakGame


def play_match(left, right, max_moves=600, seed=3):
    """Проводит матч; ``left`` ходит за HAND, ``right`` — за BOT."""
    game = KumalakGame(seed=seed)
    moves = 0
    while not game.over and moves < max_moves:
        bot = left if game.turn == 0 else right
        move = bot.choose_move(game)
        if move is None:
            break
        game.apply_move(move, set_tuzdyk=bot.choose_tuzdyk(game, move))
        assert game.total_stones() == TOTAL_STONES, f"нарушен инвариант на ходу {moves}"
        moves += 1
    return game, moves


class TestFullMatch(unittest.TestCase):
    """Сквозные прогоны партий разными уровнями сложности."""

    def test_easy_vs_medium_finishes(self):
        """Матч «лёгкий — средний» завершается результатом."""
        game, moves = play_match(
            Bot(EASY, seed=3), Bot(MEDIUM, seed=4)
        )
        self.assertTrue(game.over, f"партия не закончилась за {moves} ходов")
        self.assertGreater(moves, 5)
        self.assertIsNotNone(game.result)
        self.assertIn(game.result["reason"], ("win", "atsyrau", "draw"))
        # При досрочной победе часть кумалаков остаётся на доске.
        self.assertEqual(game.total_stones(), TOTAL_STONES)
        self.assertEqual(game.result["scores"], game.score())

    def test_medium_vs_hard_finishes(self):
        """Матч «средний — сложный» с коротким лимитом тоже доигрывается."""
        game, moves = play_match(
            Bot(MEDIUM, seed=8), Bot(HARD, seed=9, time_limit=0.02)
        )
        self.assertTrue(game.over, f"партия не закончилась за {moves} ходов")
        self.assertIsNotNone(game.result)
        self.assertEqual(game.total_stones(), TOTAL_STONES)

    def test_match_new_game_is_clean(self):
        """Новая партия после Finished не наследует состояние старой."""
        game, moves = play_match(Bot(EASY, seed=1), Bot(EASY, seed=2))
        self.assertTrue(game.over)
        fresh = KumalakGame()
        self.assertFalse(fresh.over)
        self.assertEqual(fresh.total_stones(), TOTAL_STONES)
        self.assertEqual(fresh.move_number, 0)

    def test_history_matches_move_number(self):
        """Журнал ходов и счётчик согласованы после завершения партии."""
        game, moves = play_match(Bot(EASY, seed=11), Bot(MEDIUM, seed=12))
        self.assertTrue(game.over)
        self.assertEqual(len(game.history), moves)
        self.assertEqual(game.move_number, moves)
        self.assertEqual(game.last_move, game.history[-1])
        self.assertGreaterEqual(len(game.log), moves)


if __name__ == "__main__":
    unittest.main()

"""Тесты ядра правил «Тогыз кумалак» (:mod:`game.kumalak`).

Главный инвариант: 162 кумалака распределены между лунками и казанами
после любого хода — включая захват, туздык и атсырау.
"""

from __future__ import annotations

import random
import unittest

from game.kumalak import (
    BOT,
    BOARD_PITS,
    HAND,
    PITS,
    START_STONES,
    TOTAL_STONES,
    WIN_THRESHOLD,
    KumalakGame,
    Move,
)


def position(pits=None, kazans=None, tuzdyk=None, turn=HAND):
    """Собирает заданную позицию: ``pits`` — словарь ``индекс: кумалаки``."""
    game = KumalakGame()
    if pits is not None:
        game.pits = [0] * BOARD_PITS
        for index, stones in pits.items():
            game.pits[int(index)] = stones
    if kazans is not None:
        game.kazans = dict(kazans)
    if tuzdyk is not None:
        game.tuzdyk = dict(tuzdyk)
    game.turn = turn
    return game


class TestRulesConstants(unittest.TestCase):
    """Проверка констант правил и описания доски."""

    def test_constants(self):
        """Константы соответствуют условию: 9 лунок, 9 камней, порог 82."""
        self.assertEqual(PITS, 9)
        self.assertEqual(START_STONES, 9)
        self.assertEqual(TOTAL_STONES, 162)
        self.assertEqual(BOARD_PITS, 18)
        self.assertEqual(WIN_THRESHOLD, 82)
        self.assertEqual((HAND, BOT), (0, 1))

    def test_initial_position(self):
        """Старт: 18 лунок по 9 кумалаков, пустые казаны, ход HAND."""
        game = KumalakGame()
        self.assertIsInstance(game.pits, list)
        self.assertEqual(len(game.pits), 18)
        self.assertEqual(game.pits, [9] * 18)
        self.assertEqual(sum(game.pits), 162)
        self.assertEqual(game.kazans, {HAND: 0, BOT: 0})
        self.assertEqual(game.total_stones(), TOTAL_STONES)
        self.assertEqual(game.turn, HAND)
        self.assertEqual(game.move_number, 0)
        self.assertEqual(game.history, [])
        self.assertEqual(game.tuzdyk, {})
        self.assertFalse(game.over)
        self.assertIsNone(game.result)
        self.assertTrue(game.log)


class TestSowing(unittest.TestCase):
    """Тесты посева (п. 3.2) и подсказки последней лунки (п. 3.6)."""

    def test_sow_nine_stones_leaves_first_in_place(self):
        """Из лунки с 9 камнями первый остаётся, остальные идут по кругу."""
        game = KumalakGame()
        result = game.apply_move(Move(1))
        self.assertEqual(result.path, tuple(range(1, 9)))
        self.assertEqual(game.pits[0], 1)
        for index in range(1, 9):
            self.assertEqual(game.pits[index], 10)
        self.assertEqual(game.pits[9], 9)
        self.assertEqual(game.total_stones(), 162)

    def test_sow_single_stone_moves_to_next_pit(self):
        """Один кумалак переносится в следующую лунку, отау пустеет."""
        # Кумалак в лунке 1 BOT'а нужен, чтобы не наступил атсырау.
        game = position({0: 1, 9: 1})
        result = game.apply_move(Move(1))
        self.assertEqual(result.path, (1,))
        self.assertEqual(game.pits[0], 0)
        self.assertEqual(game.pits[1], 1)

    def test_sow_path_matches_distribution(self):
        """Маршрут из ``sow_path`` совпадает с реальной раскладкой."""
        game = position({0: 4, 9: 1})
        path = game.sow_path(Move(1))
        self.assertEqual(path, [1, 2, 3])
        game.apply_move(Move(1))
        self.assertEqual(game.pits[0], 1)
        for index in path:
            self.assertEqual(game.pits[index], 1)

    def test_last_landed_pit_formula(self):
        """Подсказка: 7 + 9 → 6, одиночный камень → следующая лунка."""
        game = KumalakGame()
        self.assertEqual(game.last_landed_pit(Move(7)), 6)
        self.assertEqual(game.notation(Move(7)), "76")
        single = position({0: 1})
        self.assertEqual(single.last_landed_pit(Move(1)), 2)
        self.assertEqual(single.last_landed_pit(Move(2)), 0)


class TestCapture(unittest.TestCase):
    """Тесты захвата по чётности (п. 3.3)."""

    def test_capture_even_last_stone(self):
        """Последний камень делает лунку соперника чётной — захват 10."""
        game = KumalakGame()
        result = game.apply_move(Move(7))
        self.assertEqual(result.captured, 10)
        self.assertEqual(game.kazans[HAND], 10)
        self.assertEqual(game.kazans[BOT], 0)
        self.assertEqual(game.pits[14], 0)
        self.assertEqual(game.total_stones(), 162)

    def test_no_capture_when_even_not_last(self):
        """Чётное число посередине посева захвата не даёт."""
        game = position({7: 4, 9: 9, 10: 8})
        result = game.apply_move(Move(8))
        self.assertEqual(result.path, (8, 9, 10))
        self.assertEqual(result.captured, 0)
        self.assertEqual(game.pits[9], 10)  # чётное, но камень был не последним
        self.assertEqual(game.pits[10], 9)  # последний оставил нечётное
        self.assertEqual(game.kazans[HAND], 0)

    def test_no_capture_in_own_pit(self):
        """Чётное число в своей лунке захвата не даёт."""
        game = position({0: 2, 1: 9, 9: 1})
        result = game.apply_move(Move(1))
        self.assertEqual(result.captured, 0)
        self.assertEqual(game.pits[1], 10)
        self.assertEqual(game.kazans[HAND], 0)


class TestTuzdyk(unittest.TestCase):
    """Тесты туздыка (п. 3.4): постановка, запреты и поглощение."""

    def setUp(self):
        """Позиция, где ход из лунки 3 даёт право поставить туздык в лунку 6."""
        self.pits = {2: 13, 14: 2}

    def test_tuzdyk_set_with_flag_sweeps_three(self):
        """При ``set_tuzdyk=True`` три камня уходят в казан, лунка — туздык."""
        game = position(self.pits)
        self.assertEqual(game.notation(Move(3)), "36x")
        result = game.apply_move(Move(3), set_tuzdyk=True)
        self.assertTrue(result.tuzdyk_set)
        self.assertEqual(result.tuzdyk_pit, 6)
        self.assertEqual(game.tuzdyk, {HAND: 6})
        self.assertEqual(game.pits[14], 0)
        self.assertEqual(game.kazans[HAND], 3)
        self.assertEqual(game.total_stones(), 15)

    def test_tuzdyk_not_set_without_flag(self):
        """Без флага лунка остаётся обычной с тремя кумалаками."""
        game = position(self.pits)
        result = game.apply_move(Move(3), set_tuzdyk=False)
        self.assertFalse(result.tuzdyk_set)
        self.assertEqual(game.tuzdyk, {})
        self.assertEqual(game.pits[14], 3)
        self.assertEqual(game.kazans[HAND], 0)

    def test_tuzdyk_forbidden_in_ninth_pit(self):
        """Туздык нельзя поставить в девятую лунку."""
        game = position({8: 10, 17: 2})
        self.assertEqual(game.notation(Move(9)), "99")
        result = game.apply_move(Move(9), set_tuzdyk=True)
        self.assertFalse(result.tuzdyk_set)
        self.assertEqual(game.tuzdyk, {})

    def test_tuzdyk_forbidden_when_owner_already_has_one(self):
        """У игрока не может быть двух туздыков."""
        game = position(self.pits, tuzdyk={HAND: 2})
        self.assertEqual(game.notation(Move(3)), "36")
        result = game.apply_move(Move(3), set_tuzdyk=True)
        self.assertFalse(result.tuzdyk_set)
        self.assertEqual(game.tuzdyk, {HAND: 2})

    def test_tuzdyk_forbidden_same_number_as_opponent(self):
        """Нельзя поставить туздык под номером туздыка соперника."""
        game = position(self.pits, tuzdyk={BOT: 6})
        self.assertEqual(game.notation(Move(3)), "36")
        result = game.apply_move(Move(3), set_tuzdyk=True)
        self.assertFalse(result.tuzdyk_set)
        self.assertEqual(game.tuzdyk, {BOT: 6})

    def test_stone_into_opponent_tuzdyk_is_absorbed(self):
        """Камень, попавший в туздык соперника, идёт в казан его владельца."""
        game = position({13: 1}, tuzdyk={HAND: 6}, turn=BOT)
        result = game.apply_move(Move(5))
        self.assertEqual(result.absorbed, {HAND: 1})
        self.assertEqual(game.kazans, {HAND: 1, BOT: 0})
        self.assertEqual(game.pits[13], 0)
        self.assertEqual(game.pits[14], 0)
        self.assertEqual(game.total_stones(), 1)

    def test_cannot_move_from_tuzdyk(self):
        """Лунка-туздык не входит в допустимые ходы и отвергается движком."""
        game = position({14: 5}, tuzdyk={HAND: 6}, turn=BOT)
        self.assertNotIn(Move(6), game.legal_moves(BOT))
        self.assertEqual(game.legal_moves(BOT), [])
        self.assertFalse(game.can_move(BOT))
        with self.assertRaises(ValueError):
            game.apply_move(Move(6))


class TestFinish(unittest.TestCase):
    """Тесты окончания партии: атсырау, победа, ничья, доступ к результату."""

    def test_atsyrau_finishes_game(self):
        """Нет хода у соперника — атсырау, остатки достаются ходившему."""
        game = position({1: 1, 11: 5}, tuzdyk={HAND: 3})
        self.assertFalse(game.can_move(BOT))
        self.assertEqual(game.legal_moves(HAND), [Move(2)])
        game.apply_move(Move(2))
        self.assertTrue(game.over)
        self.assertTrue(game.is_finished())
        self.assertEqual(game.result["winner"], HAND)
        self.assertEqual(game.result["reason"], "atsyrau")
        self.assertEqual(game.result["scores"], (6, 0))
        self.assertEqual(sum(game.pits), 0)
        self.assertEqual(game.kazans[HAND], 6)
        self.assertEqual(game.total_stones(), 6)

    def test_win_at_82_stones(self):
        """Захват, доводящий казан до 82 кумалаков, завершает партию победой."""
        game = position({8: 2, 9: 1}, kazans={HAND: 80, BOT: 0})
        result = game.apply_move(Move(9))
        self.assertEqual(result.captured, 2)
        self.assertEqual(game.kazans[HAND], 82)
        self.assertTrue(game.over)
        self.assertEqual(game.result["winner"], HAND)
        self.assertEqual(game.result["reason"], "win")
        self.assertEqual(game.result["scores"], (82, 0))

    def test_draw_81_81(self):
        """Пустая доска и равный счёт 81:81 дают ничью по атсырау."""
        game = position({8: 1}, kazans={HAND: 80, BOT: 81}, tuzdyk={HAND: 1})
        game.apply_move(Move(9))
        self.assertTrue(game.over)
        self.assertEqual(game.result["winner"], None)
        self.assertEqual(game.result["reason"], "draw")
        self.assertEqual(game.result["scores"], (81, 81))
        self.assertEqual(game.total_stones(), 162)

    def test_score_accessor(self):
        """``score()`` возвращает пару казанов, ``score(side)`` — одно число."""
        game = KumalakGame()
        self.assertEqual(game.score(), (0, 0))
        self.assertEqual(game.score(HAND), 0)
        self.assertEqual(game.score(BOT), 0)
        game.apply_move(Move(7))
        self.assertEqual(game.score(), (10, 0))
        self.assertEqual(game.score(HAND), 10)
        with self.assertRaises(ValueError):
            game.score(2)

    def test_illegal_moves_raise(self):
        """Пустая лунка, номер вне диапазона и ход после конца — ошибки."""
        game = position({0: 1})
        for number in (2, 0, 10):
            with self.assertRaises(ValueError):
                game.apply_move(Move(number))
        game.apply_move(Move(1))
        with self.assertRaises(ValueError):
            game.apply_move(Move(1))


class TestState(unittest.TestCase):
    """Тесты инварианта, журнала и глубокой копии состояния."""

    def test_total_stones_invariant_during_random_game(self):
        """Сумма «на доске + в казанах» равна 162 после каждого хода."""
        rng = random.Random(11)
        game = KumalakGame(seed=11)
        moves = 0
        while not game.over and moves < 500:
            legal = game.legal_moves()
            self.assertTrue(legal, "у игрока не осталось хода до атсырау")
            game.apply_move(rng.choice(legal), set_tuzdyk=(rng.random() < 0.1))
            self.assertEqual(game.total_stones(), 162, f"ход {moves + 1}")
            self.assertEqual(sum(game.pits) + sum(game.kazans.values()), 162)
            moves += 1
        self.assertTrue(game.over, "партия должна завершиться за 500 ходов")
        self.assertGreater(moves, 5)

    def test_bookkeeping_after_move(self):
        """Ход обновляет историю, счётчик, чей ход и текстовый журнал."""
        game = KumalakGame()
        game.apply_move(Move(7))
        self.assertEqual(game.last_move, Move(7))
        self.assertEqual(game.history, [Move(7)])
        self.assertEqual(game.move_number, 1)
        self.assertEqual(game.turn, BOT)
        self.assertIn("76", game.log[-1])
        self.assertIn("захват 10", game.log[-1])

    def test_clone_is_deep_and_independent(self):
        """Копия не делит списки и словари с оригиналом."""
        game = KumalakGame()
        game.apply_move(Move(7), set_tuzdyk=False)
        game.tuzdyk[HAND] = 6
        clone = game.clone()
        clone.pits[0] = 77
        clone.kazans[HAND] = 999
        clone.tuzdyk[HAND] = 3
        clone.history.append(Move(1))
        clone.log.append("чужой текст")
        clone.turn = HAND
        clone.move_number = 123
        self.assertEqual(game.pits[0], 9)
        self.assertEqual(game.kazans[HAND], 10)
        self.assertEqual(game.tuzdyk, {HAND: 6})
        self.assertEqual(game.history, [Move(7)])
        self.assertEqual(len(game.log), 2)
        self.assertEqual(game.turn, BOT)
        self.assertEqual(game.move_number, 1)
        clone.apply_move(Move(1))
        self.assertEqual(game.move_number, 1)
        self.assertEqual(game.history, [Move(7)])
        self.assertNotEqual(clone.pits, game.pits)


if __name__ == "__main__":
    unittest.main()

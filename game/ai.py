from __future__ import annotations

import random
import time
from enum import Enum
from typing import Any

__all__ = [
    "EASY",
    "MEDIUM",
    "HARD",
    "LEVELS",
    "LEVEL_LABELS",
    "HAND",
    "BOT",
    "Difficulty",
    "Bot",
]

EASY = "easy"
MEDIUM = "medium"
HARD = "hard"
LEVELS = (EASY, MEDIUM, HARD)
LEVEL_LABELS = {
    EASY: "Лёгкий",
    MEDIUM: "Средний",
    HARD: "Сложный",
}

try:  # pragma: no cover
    from .kumalak import HAND, BOT  # type: ignore
except Exception:
    HAND, BOT = 0, 1

WIN_SCORE = 1_000_000.0
TUZDYK_VALUE = 12.0  # туздык стоит намного больше обычных камней
CAPTURE_VALUE = 0.5
TUZDYK_RISK = 0.25
TEMPO_VALUE = 0.02


class Difficulty(Enum):
    """Уровни сложности — альтернатива строковым константам.

    Позволяет писать ``Bot(Difficulty.HARD)`` наряду с ``Bot(HARD)``.
    """

    EASY = EASY
    MEDIUM = MEDIUM
    HARD = HARD

    def __str__(self) -> str:
        return self.value


class Bot:
    """Игровой бот для Кумалака.

    Args:
        level: ``EASY``, ``MEDIUM``, ``HARD`` либо ``Difficulty``; по
            умолчанию ``MEDIUM``.
        seed: зерно ``random.Random`` для воспроизводимых партий.
        difficulty: псевдоним ``level`` (совместимость с ``Bot(difficulty=HARD)``).
        time_limit: лимит раздумья в секундах на уровне ``HARD``.

    Уровни:
        * лёгкий — около 30 % ходов случайные, туздык не ставит;
        * средний — жадная оценка и ответ соперника на 1 полуход;
        * сложный — итеративное углубление до 3 полуходов с отсечением
          по времени.
    """

    def __init__(
        self,
        level: str | Difficulty = MEDIUM,
        seed: int | None = None,
        *,
        difficulty: str | Difficulty | None = None,
        time_limit: float = 0.7,
    ) -> None:
        if difficulty is not None:
            level = difficulty
        if isinstance(level, Difficulty):
            level = level.value
        level = str(level).strip().lower()
        if level not in LEVELS:
            level = MEDIUM

        self.level = level
        self.difficulty = level
        self.seed = seed
        self.rng = random.Random(seed)
        self.time_limit = float(time_limit)
        self.max_depth = {
            EASY: 1,
            MEDIUM: 2,
            HARD: 3,
        }[level]

    def describe(self) -> str:
        """Возвращает русское название уровня сложности."""
        return LEVEL_LABELS[self.level]

    def choose_move(self, game: Any) -> Any:
        """Выбирает ход для текущего игрока ``game.turn``.

        Возвращает один из ``game.legal_moves()``; если ходов нет — ``None``.
        """
        moves = list(game.legal_moves())
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]

        if self.level == EASY and self.rng.random() < 0.30:
            return self.rng.choice(moves)

        root_player = game.turn
        deadline = (
            time.perf_counter() + self.time_limit
            if self.level == HARD
            else float("inf")
        )

        best: Any = None
        for depth in range(1, self.max_depth + 1):
            if time.perf_counter() > deadline:
                break
            found = self._root_search(game, depth, deadline, root_player)
            if found is not None:
                best = found[1]
            if time.perf_counter() > deadline:
                break
        return best if best is not None else moves[0]

    def choose_tuzdyk(self, game: Any, move: Any) -> bool:
        """Решает, ставить ли туздык после хода ``move``.

        Лёгкий уровень не ставит туздык. Остальные ставят его, если ход
        даёт такое право и у игрока ещё нет туздыка: туздык очень ценен.
        """
        if self.level == EASY:
            return False

        player = game.turn
        tuzdyk = getattr(game, "tuzdyk", None) or {}
        if tuzdyk.get(player):
            return False

        target = getattr(move, "tuzdyk_target", None)
        if target:
            return True

        probe = game.clone()
        try:
            probe.apply_move(move, set_tuzdyk=True)
        except Exception:
            return False
        return bool((getattr(probe, "tuzdyk", None) or {}).get(player))

    def _root_search(
        self, game: Any, depth: int, deadline: float, root_player: int
    ) -> tuple[float, Any] | None:
        moves = self._order_moves(game, list(game.legal_moves()))
        if not moves:
            return None

        best_move = moves[0]
        best_score = float("-inf")
        alpha = float("-inf")
        for move in moves:
            if time.perf_counter() > deadline:
                break
            child = self._apply(game, move, root_player)
            score = self._search(
                child, depth - 1, alpha, float("inf"), root_player, deadline
            )
            if score > best_score:
                best_score, best_move = score, move
            if score > alpha:
                alpha = score
        return best_score, best_move

    def _search(
        self,
        game: Any,
        depth: int,
        alpha: float,
        beta: float,
        root_player: int,
        deadline: float,
    ) -> float:
        if getattr(game, "over", False) or depth <= 0:
            return self._evaluate(game, root_player)

        moves = self._order_moves(game, list(game.legal_moves()))
        if not moves:
            return self._evaluate(game, root_player)

        if game.turn == root_player:
            best = float("-inf")
            for move in moves:
                if time.perf_counter() > deadline:
                    break
                child = self._apply(game, move, root_player)
                score = self._search(
                    child, depth - 1, alpha, beta, root_player, deadline
                )
                if score > best:
                    best = score
                if best > alpha:
                    alpha = best
                if alpha >= beta:
                    break
            if best == float("-inf"):
                return self._evaluate(game, root_player)
            return best

        best = float("inf")
        for move in moves:
            if time.perf_counter() > deadline:
                break
            child = self._apply(game, move, root_player)
            score = self._search(
                child, depth - 1, alpha, beta, root_player, deadline
            )
            if score < best:
                best = score
            if best < beta:
                beta = best
            if alpha >= beta:
                break
        if best == float("inf"):
            return self._evaluate(game, root_player)
        return best

    def _apply(self, game: Any, move: Any, player: int) -> Any:
        child = game.clone()
        set_tuzdyk = (
            self.level != EASY and bool(getattr(move, "tuzdyk_target", None))
        )
        child.apply_move(move, set_tuzdyk=set_tuzdyk)
        return child

    @staticmethod
    def _order_moves(game: Any, moves: list[Any]) -> list[Any]:
        def key(move: Any) -> tuple[int, int, int]:
            captured = getattr(move, "captured", 0) or 0
            tuzdyk = 1 if getattr(move, "tuzdyk_target", None) else 0
            return (tuzdyk, int(captured), -int(getattr(move, "pit", 0) or 0))

        return sorted(moves, key=key, reverse=True)

    def _evaluate(self, game: Any, player: int) -> float:
        opponent = 1 - player
        kazans = game.kazans

        if getattr(game, "over", False):
            result = getattr(game, "result", None)
            winner = result.get("winner") if isinstance(result, dict) else None
            if winner == player:
                return WIN_SCORE
            if winner == opponent:
                return -WIN_SCORE
            if winner is None and result is not None:
                return 0.0
            if kazans[player] > kazans[opponent]:
                return WIN_SCORE
            if kazans[player] < kazans[opponent]:
                return -WIN_SCORE
            return 0.0

        value = float(kazans[player] - kazans[opponent])

        tuzdyk = getattr(game, "tuzdyk", None) or {}
        own_tuz = tuzdyk.get(player)
        opponent_tuz = tuzdyk.get(opponent)
        if own_tuz:
            value += TUZDYK_VALUE
        if opponent_tuz:
            value -= TUZDYK_VALUE

        pits = game.pits

        for idx in range(9):
            count = pits[player * 9 + idx]
            if count <= 0:
                continue
            landing = (idx + count - 1) % 18 if count > 1 else (idx + 1) % 18
            if landing < 9:
                continue
            target = landing - 9
            if pits[opponent * 9 + target] % 2 == 1:
                if opponent_tuz == target + 1:
                    value -= CAPTURE_VALUE * 0.8
                else:
                    value += CAPTURE_VALUE

        # Три камня в лунке — соперник сможет поставить туздык.
        for idx in range(9):
            if pits[player * 9 + idx] == 3 and opponent_tuz != idx + 1:
                value -= TUZDYK_RISK

        mobility = sum(
            1
            for idx in range(9)
            if pits[player * 9 + idx] > 0 and own_tuz != idx + 1
        )
        value += TEMPO_VALUE * mobility
        return value

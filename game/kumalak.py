"""Ядро правил «Тогыз кумалак» (вариант Н. Н. Пантусова, 1906).

Доска — плоский список из 18 лунок: индексы 0..8 — лунки 1..9 игрока HAND,
9..17 — лунки 1..9 игрока BOT (нумерация слева направо от игрока). Круг
посева — единый цикл 0 → 1 → … → 17 → 0; для HAND он начинается с 0,
для BOT — с 9 (см. :func:`circle_index`).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

PITS = 9
START_STONES = 9
TOTAL_STONES = 162
WIN_THRESHOLD = 82
HAND = 0
BOT = 1
BOARD_PITS = 2 * PITS


def opponent(player: int) -> int:
    """Индекс соперника для игрока ``player``."""
    return BOT if player == HAND else HAND


def pit_index(player: int, pit: int) -> int:
    """Номер лунки 1..9 игрока ``player`` → индекс 0..17."""
    return int(player) * PITS + (int(pit) - 1)


def pit_owner(index: int) -> int:
    """Владелец лунки с индексом ``index`` (0..8 — HAND)."""
    return HAND if index < PITS else BOT


def pit_number(index: int) -> int:
    """Номер лунки 1..9 (в нумерации владельца) по индексу."""
    return int(index) % PITS + 1


def circle_index(index: int, shift: int = 1) -> int:
    """Следующая лунка в круге посева (против часовой стрелки)."""
    return (int(index) + shift) % BOARD_PITS


@dataclass(frozen=True)
class Move:
    """Ход: номер своей лунки 1..9, из которой берутся кумалаки."""

    pit: int

    def __str__(self) -> str:  # pragma: no cover
        return f"Move({self.pit})"


@dataclass(frozen=True)
class MoveResult:
    """Сводка применённого хода (результат :meth:`apply_move`).

    ``path`` — индексы лунок в порядке раскладки (по элементу на кумалак,
    включая сразу ушедшие в туздык); ``absorbed`` — ``{владелец: число}``
    кумалаков в туздыках; ``captured`` — захвачено по чётности;
    ``tuzdyk_set`` / ``tuzdyk_pit`` — поставлен ли туздык и в какой лунке.
    """

    move: Move
    player: int
    path: tuple[int, ...]
    last_index: int
    last_pit: int
    captured: int
    absorbed: dict[int, int]
    tuzdyk_set: bool
    tuzdyk_pit: int | None
    finished: bool


@dataclass
class _SimResult:
    """Внутренний результат «сухого» расчёта хода без изменения состояния."""

    path: list[int]
    final_pits: list[int]
    absorbed: dict[int, int]
    captured: int
    last_index: int | None
    last_pit: int | None
    tuzdyk_pit: int | None


class KumalakGame:
    """Состояние партии в «тогыз кумалак».

    Поля доступны напрямую (ИИ и UI читают их), но менять вручную не
    рекомендуется: используйте :meth:`apply_move`. ``tuzdyk`` —
    ``{владелец: номер лунки 1..9 на стороне соперника}``; пустой словарь
    означает «туздыков нет». ``result`` — ключи ``winner``, ``scores``,
    ``reason`` (``win`` / ``atsyrau`` / ``draw``) и ``reason_text``
    (русский текст для журнала/UI).
    """

    def __init__(self, seed: int | None = None) -> None:
        """Начальная позиция: по 9 кумалаков в лунке, ход HAND."""
        self._seed = seed
        self.pits: list[int] = [START_STONES] * BOARD_PITS
        self.kazans: dict[int, int] = {HAND: 0, BOT: 0}
        self.turn: int = HAND
        self.tuzdyk: dict[int, int] = {}
        self.move_number: int = 0
        self.last_move: Move | None = None
        self.history: list[Move] = []
        self.over: bool = False
        self.result: dict | None = None
        self.log: list[str] = [
            "Начало партии: по 9 кумалаков в каждой лунке, первый ход — белые."
        ]

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"KumalakGame(turn={self.turn}, kazans={self.kazans}, "
            f"move_number={self.move_number}, over={self.over})"
        )

    def _tuzdyk_index_map(self) -> dict[int, int]:
        """Возвращает ``{индекс лунки на доске: владелец туздыка}``."""
        mapping: dict[int, int] = {}
        for owner, number in self.tuzdyk.items():
            if number is None:
                continue
            mapping[pit_index(opponent(owner), number)] = int(owner)
        return mapping

    @staticmethod
    def _resolve(move, pit=None):
        """Приводит аргументы публичных методов к паре ``(player, pit)``.

        ``player=None`` — текущий игрок. Поддерживаются ``method(Move(3))``,
        ``method(player, 3)`` и ``method(3)`` (номер лунки текущего игрока);
        последняя форма — для совместимости с вызовами ИИ и тестов.
        """
        if isinstance(move, Move):
            return None, move.pit
        if pit is not None:
            return int(move), int(pit)
        if isinstance(move, int):
            return None, move
        raise TypeError("Ожидался ход Move или пара (player, pit)")

    def _player_of_args(self, move, pit=None) -> tuple[int, int]:
        player, number = self._resolve(move, pit)
        return (self.turn if player is None else player), number

    def stones_on_board(self) -> int:
        """Кумалаки в 18 лунках (без казанов)."""
        return sum(self.pits)

    def total_stones(self) -> int:
        """Инвариант: кумалаки на доске + в казанах (должно быть 162)."""
        return self.stones_on_board() + sum(self.kazans.values())

    def _simulate(self, player: int, number: int) -> _SimResult | None:
        """Раскладывает кумалаки «на бумаге», определяет захват/туздык.

        Возвращает ``None``, если лунка пуста. Не изменяет ``self``.
        """
        if not (1 <= number <= PITS):
            return None
        start = pit_index(player, number)
        stones = self.pits[start]
        if stones <= 0:
            return None

        # Если кумалаков больше одного, первый остаётся в лунке; ровно один
        # перекладывается в следующую лунку круга (п. 3.2).
        if stones == 1:
            path = [circle_index(start)]
        else:
            path = [circle_index(start, i) for i in range(1, stones)]

        pits = list(self.pits)
        pits[start] = 1 if stones > 1 else 0

        tuzdyk_map = self._tuzdyk_index_map()
        absorbed: dict[int, int] = {}
        for index in path:
            owner = tuzdyk_map.get(index)
            if owner is None:
                pits[index] += 1
            else:
                # Камень в туздыке в лунке не остаётся: сразу идёт в казан
                # владельца туздыка (п. 3.4).
                absorbed[owner] = absorbed.get(owner, 0) + 1

        captured = 0
        last_index = path[-1] if path else None
        last_pit = pit_number(last_index) if last_index is not None else None
        tuzdyk_pit: int | None = None

        if last_index is not None and last_index not in tuzdyk_map:
            # Захват (чётность) и туздык (ровно 3) — только по последнему
            # камню в обычной лунке соперника (пп. 3.3, 3.4).
            if pit_owner(last_index) != player:
                count = pits[last_index]
                if count > 0 and count % 2 == 0:
                    captured = count
                    pits[last_index] = 0
                elif count == 3:
                    other = opponent(player)
                    same_number = self.tuzdyk.get(other) == last_pit
                    nine = last_pit == PITS
                    if player not in self.tuzdyk and not nine and not same_number:
                        tuzdyk_pit = last_pit

        return _SimResult(
            path=path,
            final_pits=pits,
            absorbed=absorbed,
            captured=captured,
            last_index=last_index,
            last_pit=last_pit,
            tuzdyk_pit=tuzdyk_pit,
        )

    def legal_moves(self, player: int | None = None) -> list[Move]:
        """Допустимые ходы игрока ``player`` (по умолчанию — чей ход).

        Ход из любой непустой своей лунки. Лунка-туздык блокируется для
        игрока, на чьей стороне она расположена: из туздыка нельзя ходить
        самому (п. 3.4).
        """
        who = self.turn if player is None else int(player)
        blocked: set[int] = set()
        for owner, number in self.tuzdyk.items():
            if opponent(owner) == who and number is not None:
                blocked.add(int(number))
        moves: list[Move] = []
        for number in range(1, PITS + 1):
            if number in blocked:
                continue
            if self.pits[pit_index(who, number)] > 0:
                moves.append(Move(number))
        return moves

    def can_move(self, player: int | None = None) -> bool:
        """Есть ли у игрока хотя бы один допустимый ход (не атсырау)."""
        return bool(self.legal_moves(player))

    def sow_path(self, move, pit=None) -> list[int]:
        """Индексы 0..17 лунок, в которые упадут кумалаки по порядку.

        Принимает ``Move``, ``(player, pit)`` или номер лунки. Состояние не
        меняется; используется анимацией и тестами (п. 3.2).
        """
        player, number = self._player_of_args(move, pit)
        sim = self._simulate(player, number)
        return [] if sim is None else list(sim.path)

    def last_landed_pit(self, move, pit=None) -> int:
        """Номер лунки 1..9, куда упадёт последний кумалак (п. 3.6).

        Для ``n > 1`` — по таблице ТЗ (7 + 9 → 6), для одиночного кумалака —
        реальная следующая лунка. 0, если ход из пустой лунки невозможен.
        """
        player, number = self._player_of_args(move, pit)
        sim = self._simulate(player, number)
        return 0 if sim is None or sim.last_pit is None else sim.last_pit

    def notation(self, move, pit=None) -> str:
        """Шахматная нотация хода ``«откуда><куда>»``, например ``"76"``.

        ``x`` на конце — право поставить туздык (``"36x"``). Нотация
        рассчитывается по состоянию доски до хода.
        """
        player, number = self._player_of_args(move, pit)
        sim = self._simulate(player, number)
        if sim is None or sim.last_pit is None:
            return ""
        text = f"{number}{sim.last_pit}"
        if sim.tuzdyk_pit is not None:
            text += "x"
        return text

    def apply_move(self, move, set_tuzdyk: bool = False) -> MoveResult:
        """Применяет ход текущего игрока, возвращает :class:`MoveResult`.

        Порядок: посев → захват по чётности → туздык → проверка конца партии
        → передача хода. Нет хода у следующего игрока — атсырау (п. 3.5,
        вариант B).
        """
        if isinstance(move, int):
            move = Move(move)
        if not isinstance(move, Move):
            raise TypeError("Ожидался объект Move или номер лунки")
        if self.over:
            raise ValueError("Партия уже окончена")

        player = self.turn
        number = move.pit
        if not (1 <= number <= PITS):
            raise ValueError(f"Номер лунки должен быть от 1 до {PITS}")
        start = pit_index(player, number)
        if self.pits[start] <= 0:
            raise ValueError(f"Лунка {number} игрока {player} пуста — ход невозможен")
        if start in self._tuzdyk_index_map():
            raise ValueError("Из туздыка ходить нельзя")

        move_text = self.notation(move)
        sim = self._simulate(player, number)
        if sim is None:
            raise ValueError("Ход невозможен")

        self.pits[:] = sim.final_pits
        for owner, amount in sim.absorbed.items():
            self.kazans[owner] += amount
        if sim.captured:
            self.kazans[player] += sim.captured

        tuzdyk_set = False
        if set_tuzdyk and sim.tuzdyk_pit is not None:
            self.tuzdyk[player] = sim.tuzdyk_pit
            sacred_index = pit_index(opponent(player), sim.tuzdyk_pit)
            # Три кумалака, сделавших лунку «священным местом», идут владельцу
            # туздыка; дальше лунка пуста и лишь поглощает всё, что в неё
            # попадает (п. 3.4).
            swept = self.pits[sacred_index]
            self.pits[sacred_index] = 0
            self.kazans[player] += swept
            tuzdyk_set = True

        self.history.append(move)
        self.last_move = move
        self.move_number += 1

        side_name = "белые" if player == HAND else "чёрные"
        details = []
        if sim.captured:
            details.append(f"захват {sim.captured}")
        if sim.absorbed:
            absorbed_text = ", ".join(
                f"{'белые' if owner == HAND else 'чёрные'}: {amount}"
                for owner, amount in sorted(sim.absorbed.items())
            )
            details.append(f"в туздык → {absorbed_text}")
        if tuzdyk_set:
            details.append(f"туздык в лунке {sim.tuzdyk_pit}")
        tail = f" ({'; '.join(details)})" if details else ""
        self.log.append(f"{self.move_number}. {side_name}: {move_text}{tail}")

        self._finish_check(player)
        return MoveResult(
            move=move,
            player=player,
            path=tuple(sim.path),
            last_index=sim.last_index,
            last_pit=sim.last_pit,
            captured=sim.captured,
            absorbed=dict(sim.absorbed),
            tuzdyk_set=tuzdyk_set,
            tuzdyk_pit=sim.tuzdyk_pit if tuzdyk_set else None,
            finished=self.over,
        )

    def _finish_check(self, mover: int) -> None:
        """Проверяет победу по 82+ и атсырау после сделанного хода."""
        a, b = self.kazans[HAND], self.kazans[BOT]
        self.turn = opponent(mover)

        if a >= WIN_THRESHOLD or b >= WIN_THRESHOLD:
            winner = HAND if a >= WIN_THRESHOLD else BOT
            name = "белые" if winner == HAND else "чёрные"
            self.over = True
            self.result = {
                "winner": winner,
                "scores": (a, b),
                "reason": "win",
                "reason_text": f"Победа {name}: {max(a, b)} кумалаков в казане",
            }
            self.log.append(self.result["reason_text"])
            return

        if not self.can_move(self.turn):
            # Атсырау: соперник (сделавший последний ход) забирает всё,
            # что осталось на доске (п. 3.5, вариант B).
            remaining = sum(self.pits)
            self.kazans[mover] += remaining
            self.pits = [0] * BOARD_PITS
            a, b = self.kazans[HAND], self.kazans[BOT]
            if a == b:
                winner = None
                reason = "draw"
                text = f"Ничья {a}:{b} — атсырау"
            else:
                winner = HAND if a > b else BOT
                reason = "atsyrau"
                name = "белые" if winner == HAND else "чёрные"
                mover_name = "белые" if mover == HAND else "чёрные"
                text = f"Атсырау: {mover_name} забирают {remaining} "
                text += f"кумалаков. Победа {name} — {a}:{b}"
            self.over = True
            self.result = {
                "winner": winner,
                "scores": (a, b),
                "reason": reason,
                "reason_text": text,
            }
            self.log.append(text)

    def is_finished(self) -> bool:
        """True, если партия окончена (победа, атсырау или ничья)."""
        return self.over

    def score(self, side: int | None = None):
        """Кумалаки в казане игрока ``side``.

        При ``side=None`` — пара ``(казан HAND, казан BOT)``: форма, удобная
        для UI и совместимая с вариантом API из ТЗ.
        """
        if side is None:
            return (self.kazans[HAND], self.kazans[BOT])
        side = int(side)
        if side not in (HAND, BOT):
            raise ValueError("Сторона должна быть HAND (0) или BOT (1)")
        return self.kazans[side]

    def clone(self) -> "KumalakGame":
        """Глубокая независимая копия состояния (для перебора ИИ)."""
        other = KumalakGame.__new__(KumalakGame)
        other._seed = self._seed
        other.pits = list(self.pits)
        other.kazans = dict(self.kazans)
        other.turn = self.turn
        other.tuzdyk = dict(self.tuzdyk)
        other.move_number = self.move_number
        other.last_move = self.last_move
        other.history = list(self.history)
        other.over = self.over
        other.result = copy.deepcopy(self.result)
        other.log = list(self.log)
        return other

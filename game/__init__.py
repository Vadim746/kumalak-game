"""Игровая логика «Тогыз кумалак».

Публичный API ядра реэкспортируется из :mod:`game.kumalak`.
"""

from .kumalak import (
    BOT,
    BOARD_PITS,
    HAND,
    PITS,
    START_STONES,
    TOTAL_STONES,
    WIN_THRESHOLD,
    KumalakGame,
    Move,
    MoveResult,
    opponent,
    pit_index,
    pit_number,
    pit_owner,
)

__all__ = [
    "PITS",
    "START_STONES",
    "TOTAL_STONES",
    "WIN_THRESHOLD",
    "HAND",
    "BOT",
    "BOARD_PITS",
    "Move",
    "MoveResult",
    "KumalakGame",
    "opponent",
    "pit_index",
    "pit_number",
    "pit_owner",
]

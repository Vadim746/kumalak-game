"""Синтезированные звуковые эффекты «Кумалака»."""

from __future__ import annotations

import io
import math
import wave
from array import array
from typing import Callable, Dict, Optional

try:
    import pygame

    try:
        import pygame.mixer  # noqa: F401

        MIXER_AVAILABLE = True
    except Exception:
        MIXER_AVAILABLE = False
except Exception:
    pygame = None  # type: ignore[assignment]
    MIXER_AVAILABLE = False

_RATE = 22050
_VOICES = ("sow", "capture", "tuzdyk", "win", "click")


def _limit(value: float) -> int:
    """Ограничивает отсчёт диапазоном 16-битного звука."""
    return max(-32768, min(32767, int(value)))


def _frames(duration: float, shape: Callable[[float], float]) -> array:
    """Генерирует моно-отсчёты заданной длительности."""
    count = int(_RATE * duration)
    samples = array("h", [0]) * count
    for i in range(count):
        samples[i] = _limit(shape(i / _RATE))
    return samples


def _sow() -> array:
    """Короткий стук кумалака о дно казана при посеве."""

    def shape(t: float) -> float:
        envelope = math.exp(-t * 55)
        body = math.sin(2 * math.pi * 520 * t) * 0.6
        body += math.sin(2 * math.pi * 880 * t) * 0.25
        body += math.sin(2 * math.pi * 2100 * t) * 0.15
        return 11000 * envelope * body

    return _frames(0.12, shape)


def _capture() -> array:
    """Глухой удар со спадающим тоном — захват кумалаков."""

    def shape(t: float) -> float:
        envelope = min(1.0, t * 30) * math.exp(-t * 16)
        sweep = math.sin(2 * math.pi * (420 - 240 * t) * t)
        thud = math.sin(2 * math.pi * 120 * t)
        return 12000 * envelope * (0.7 * sweep + 0.5 * thud)

    return _frames(0.28, shape)


def _tuzdyk() -> array:
    """Звонкий колокольчик: объявление туздыка."""

    def shape(t: float) -> float:
        envelope = min(1.0, t * 40) * math.exp(-t * 6)
        bell = math.sin(2 * math.pi * 1180 * t)
        bell += 0.5 * math.sin(2 * math.pi * 1770 * t)
        bell += 0.25 * math.sin(2 * math.pi * 2360 * t)
        return 8000 * envelope * bell

    return _frames(0.45, shape)


def _win() -> array:
    """Мягкий мажорный аккорд в честь победы."""

    def shape(t: float) -> float:
        envelope = min(1.0, t * 10) * math.exp(-t * 3)
        chord = 0.0
        for freq in (523.25, 659.25, 783.99, 1046.50):
            chord += math.sin(2 * math.pi * freq * t) / 4
        return 13000 * envelope * chord

    return _frames(0.85, shape)


def _click() -> array:
    """Сухой короткий щелчок для элементов интерфейса."""

    def shape(t: float) -> float:
        envelope = math.exp(-t * 90)
        click = 0.7 * math.sin(2 * math.pi * 1200 * t)
        click += 0.3 * math.sin(2 * math.pi * 1800 * t)
        return 7000 * envelope * click

    return _frames(0.05, shape)


_GENERATORS: Dict[str, Callable[[], array]] = {
    "sow": _sow,
    "capture": _capture,
    "tuzdyk": _tuzdyk,
    "win": _win,
    "click": _click,
}


class SoundManager:
    """Управляет звуковыми эффектами.

    Без pygame и микшера методы ничего не делают.
    """

    def __init__(self) -> None:
        self._mixer_ok = False
        self._muted = False
        self._volume = 1.0
        self._cache: Dict[str, object] = {}
        self.init()

    def init(self) -> None:
        """Инициализирует микшер и готовит звуки."""
        self._mixer_ok = False
        self._cache.clear()
        if not MIXER_AVAILABLE or pygame is None:
            return
        try:
            pygame.mixer.init(frequency=_RATE, size=-16, channels=1, buffer=512)
        except Exception:
            return
        self._mixer_ok = True
        for name in _VOICES:
            self._prepare(name)

    def _prepare(self, name: str) -> None:
        """Готовит эффект для воспроизведения."""
        if not self._mixer_ok or name in self._cache:
            return
        generator = _GENERATORS.get(name)
        if generator is None:
            return
        try:
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(_RATE)
                wav.writeframes(generator().tobytes())
            buffer.seek(0)
            sound = pygame.mixer.Sound(file=buffer)
            sound.set_volume(0.0 if self._muted else self._volume)
            self._cache[name] = sound
        except Exception:
            return

    def _play(self, name: str) -> None:
        """Проигрывает эффект, если он готов."""
        if not self._mixer_ok or self._muted:
            return
        self._prepare(name)
        sound = self._cache.get(name)
        if sound is None:
            return
        try:
            sound.play()
        except Exception:
            pass

    def play_sow(self) -> None:
        """Звук посева кумалака по казанам доски."""
        self._play("sow")

    def play_capture(self) -> None:
        """Звук захвата кумалаков соперника."""
        self._play("capture")

    def play_tuzdyk(self) -> None:
        """Звук объявления туздыка."""
        self._play("tuzdyk")

    def play_win(self) -> None:
        """Победный аккорд."""
        self._play("win")

    def play_click(self) -> None:
        """Щелчок по кнопке интерфейса."""
        self._play("click")

    def mute(self, muted: bool) -> None:
        """Выключает или включает звук."""
        self._muted = bool(muted)
        if not self._mixer_ok:
            return
        volume = 0.0 if self._muted else self._volume
        for sound in self._cache.values():
            try:
                sound.set_volume(volume)
            except Exception:
                pass

    def set_volume(self, volume: float) -> None:
        """Задаёт громкость от 0.0 до 1.0."""
        self._volume = max(0.0, min(1.0, float(volume)))
        if not self._mixer_ok or self._muted:
            return
        for sound in self._cache.values():
            try:
                sound.set_volume(self._volume)
            except Exception:
                pass


sound_manager = SoundManager()

"""Хранилище таблицы рекордов игры «Кумалак».

Файл лежит рядом с программой, чтобы архив работал «из коробки»; если
каталог недоступен для записи, используется XDG_DATA_HOME/kumalak-game.

Битый JSON уезжает в ``.bak``, таблица открывается пустой, а причина —
в ``last_error``. Число записей ограничено ``MAX_RECORDS``.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_DIR = Path(__file__).resolve().parent
DEFAULT_FILENAME = "records.json"
FILE_VERSION = 1
FALLBACK_DIR_NAME = "kumalak-game"

# При превышении самые старые записи удаляются.
MAX_RECORDS = 100

# Возможные исходы матча.
RESULT_WIN = "победа"
RESULT_LOSS = "поражение"
RESULT_DRAW = "ничья"
RESULTS = (RESULT_WIN, RESULT_LOSS, RESULT_DRAW)

DATE_FORMAT = "%d.%m.%Y %H:%M"


@dataclass
class Record:
    """Одна запись таблицы рекордов."""

    name: str
    score: int
    opponent_score: int = 0
    result: str = RESULT_DRAW
    difficulty: str = "Средний"
    date: str = field(default_factory=lambda: datetime.now().strftime(DATE_FORMAT))
    rounds: int = 0
    moves: int = 0

    @property
    def timestamp(self) -> float:
        """Числовой ключ для сортировки по дате (0 при неразбираемой дате)."""
        try:
            return datetime.strptime(self.date, DATE_FORMAT).timestamp()
        except (ValueError, TypeError):
            return 0.0


def _to_int(value: Any, default: int = 0) -> int:
    """Безопасно приводит значение к ``int``, не выбрасывая исключений."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def fallback_path() -> Path:
    """Путь в каталоге данных пользователя (XDG_DATA_HOME)."""
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    directory = Path(base) / FALLBACK_DIR_NAME
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return directory / DEFAULT_FILENAME


def default_path() -> Path:
    """Путь к файлу рекордов с учётом прав на запись.

    Сначала пробуем каталог программы; если он недоступен — каталог
    пользователя. Сам файл при проверке создаётся пустым (режим «a»).
    """
    candidate = APP_DIR / DEFAULT_FILENAME
    try:
        with open(candidate, "a", encoding="utf-8"):
            pass
        return candidate
    except OSError:
        return fallback_path()


class RecordStore:
    """Таблица рекордов: загрузка, фильтр, сортировка, сохранение.

    Ошибки чтения/записи никогда не поднимаются наружу: диагностика пишется
    в ``last_error`` (строку с предупреждением для интерфейса).
    """

    def __init__(self, path: Optional[Path] = None, max_records: int = MAX_RECORDS):
        self.path = Path(path) if path else default_path()
        self.max_records = max(1, int(max_records))
        self.records: List[Record] = []
        self.last_error: Optional[str] = None
        self.load()

    def _backup_broken(self) -> str:
        """Переименовывает битый файл в ``.bak``, возвращает имя копии."""
        backup = Path(str(self.path) + ".bak")
        if backup.exists():
            number = 1
            while Path(f"{self.path}.bak.{number}").exists():
                number += 1
            backup = Path(f"{self.path}.bak.{number}")
        try:
            os.replace(self.path, backup)
        except OSError:
            try:
                import shutil

                shutil.copyfile(self.path, backup)
            except (OSError, ImportError):
                pass
        return backup.name

    def load(self) -> None:
        """Читает файл рекордов. Ошибки не поднимаются — см. ``last_error``."""
        self.last_error = None
        self.records = []
        if not self.path.exists():
            return
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return
            data = json.loads(raw)
            items = data.get("records", []) if isinstance(data, dict) else data
            if not isinstance(items, list):
                raise ValueError("Некорректная структура файла рекордов")
            loaded: List[Record] = []
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Некорректная запись в файле рекордов")
                result = str(item.get("result", RESULT_DRAW)).strip().lower()
                if result not in RESULTS:
                    result = RESULT_DRAW
                loaded.append(
                    Record(
                        name=str(item.get("name", "")).strip(),
                        score=_to_int(item.get("score", 0)),
                        opponent_score=_to_int(item.get("opponent_score", 0)),
                        result=result,
                        difficulty=str(item.get("difficulty", "Средний")),
                        date=str(item.get("date") or datetime.now().strftime(DATE_FORMAT)),
                        rounds=_to_int(item.get("rounds", 0)),
                        moves=_to_int(item.get("moves", 0)),
                    )
                )
            self.records = loaded
            self._trim()
        except (json.JSONDecodeError, OSError, ValueError, TypeError, AttributeError):
            backup = self._backup_broken()
            self.records = []
            self.last_error = (
                "Файл рекордов повреждён и не мог быть прочитан. "
                f"Он переименован в {backup}, таблица открыта пустой."
            )

    def _write(self, path: Path) -> None:
        """Пишет таблицу в ``path``."""
        payload: Dict[str, Any] = {
            "version": FILE_VERSION,
            "records": [asdict(record) for record in self.records],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".records-", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
            tmp_name = ""
        finally:
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

    def save(self) -> None:
        """Сохраняет таблицу; при неудаче пробует fallback-путь, не падая."""
        try:
            self._write(self.path)
            return
        except (OSError, TypeError, ValueError) as exc:
            primary_error = exc
        fallback = fallback_path()
        if fallback != self.path:
            try:
                self._write(fallback)
                self.path = fallback
                self.last_error = (
                    "Не удалось записать рекорды рядом с программой; "
                    f"данные сохранены в {fallback}. {primary_error}"
                )
                return
            except (OSError, TypeError, ValueError) as exc:
                self.last_error = f"Не удалось сохранить рекорды: {exc}"
        else:
            self.last_error = f"Не удалось сохранить рекорды: {primary_error}"

    def clear_warning(self) -> None:
        """Сбрасывает предупреждение (после того как его показали в UI)."""
        self.last_error = None

    def _trim(self) -> None:
        """Удерживает не более ``max_records`` записей (удаляет старые)."""
        if len(self.records) <= self.max_records:
            return
        ordered = sorted(self.records, key=lambda record: record.timestamp)
        drop = len(ordered) - self.max_records
        oldest = {id(record) for record in ordered[:drop]}
        self.records = [r for r in self.records if id(r) not in oldest]

    def add(
        self,
        name: str,
        score: int,
        opponent_score: int = 0,
        result: str = RESULT_DRAW,
        difficulty: str = "Средний",
        rounds: int = 0,
        moves: int = 0,
        date: Optional[str] = None,
        **_: Any,
    ) -> Record:
        """Добавляет результат матча в таблицу и сохраняет её.

        Неизвестные именованные аргументы (например, ``limit``/``wins``
        из старого формата) игнорируются для совместимости.
        """
        normalized = str(result).strip().lower()
        if normalized not in RESULTS:
            normalized = RESULT_DRAW
        record = Record(
            name=str(name).strip(),
            score=_to_int(score),
            opponent_score=_to_int(opponent_score),
            result=normalized,
            difficulty=str(difficulty),
            date=str(date) if date else datetime.now().strftime(DATE_FORMAT),
            rounds=_to_int(rounds),
            moves=_to_int(moves),
        )
        self.records.append(record)
        self._trim()
        self.save()
        return record

    def remove(self, index: int) -> None:
        """Удаляет запись по индексу в текущем (неотсортированном) списке."""
        if 0 <= index < len(self.records):
            del self.records[index]
            self.save()

    def clear(self) -> None:
        """Полностью очищает таблицу рекордов."""
        self.records = []
        self.save()

    def filtered(self, name_query: str = "") -> List[Record]:
        """Отбирает записи по подстроке имени (без учёта регистра).

        Пустой запрос (в том числе из одних пробелов) возвращает все записи.
        """
        query = str(name_query).strip().lower()
        if not query:
            return list(self.records)
        return [record for record in self.records if query in record.name.lower()]

    def sorted_records(
        self, records: Optional[List[Record]] = None, key: str = "score"
    ) -> List[Record]:
        """Сортирует записи: по очкам (убывание) или по дате (новые первыми).

        Допустимы как английские (``score``/``date``), так и русские
        (``очки``/``дата``) значения ``key``.
        """
        items = list(self.records if records is None else records)
        if str(key).strip().lower() in ("date", "дата"):
            items.sort(key=lambda record: (record.timestamp, record.date), reverse=True)
        else:
            items.sort(
                key=lambda record: (record.score, record.timestamp), reverse=True
            )
        return items

    def best_score(self, name: str) -> int:
        """Лучший результат игрока с таким именем (0, если записей нет)."""
        wanted = str(name).strip().lower()
        scores = [r.score for r in self.records if r.name.lower() == wanted]
        return max(scores) if scores else 0

    def __len__(self) -> int:
        return len(self.records)

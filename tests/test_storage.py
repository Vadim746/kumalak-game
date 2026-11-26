"""Тесты таблицы рекордов (:mod:`storage`).

Все проверки используют ``tempfile``: реальный ``records.json`` проекта
не затрагивается.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import storage
from storage import MAX_RECORDS, Record, RecordStore, fallback_path


class TestRecordStore(unittest.TestCase):
    """Базовые сценарии: добавление, фильтр, сортировка, очистка."""

    def setUp(self):
        """Создаёт временный каталог и пустой файл рекордов."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "records.json"
        self.store = RecordStore(self.path)

    def test_add_and_reload(self):
        """Добавленная запись сохраняется в JSON и читается заново."""
        record = self.store.add(
            "Алиса", 82, 79, "победа", "Сложный", rounds=2, moves=54,
            date="01.03.2026 12:30",
        )
        self.assertIsInstance(record, Record)
        self.assertEqual(record.name, "Алиса")
        self.assertEqual(record.score, 82)
        self.assertEqual(record.opponent_score, 79)
        self.assertEqual(record.result, "победа")
        self.assertEqual(record.difficulty, "Сложный")
        self.assertEqual(record.rounds, 2)
        self.assertEqual(record.moves, 54)
        self.assertEqual(len(self.store), 1)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["records"][0]["name"], "Алиса")
        reloaded = RecordStore(self.path)
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded.records[0].name, "Алиса")

    def test_filtered_case_insensitive_substring(self):
        """Фильтр ищет подстроку без учёта регистра."""
        self.store.add("Алиса", 80, date="01.01.2026 10:00")
        self.store.add("боб", 70, date="02.01.2026 10:00")
        self.store.add("АЛИСА-2", 60, date="03.01.2026 10:00")
        self.assertEqual([r.name for r in self.store.filtered("алис")],
                         ["Алиса", "АЛИСА-2"])
        self.assertEqual([r.name for r in self.store.filtered("БОБ")], ["боб"])
        self.assertEqual(self.store.filtered("нет"), [])

    def test_filtered_empty_query(self):
        """Пустой запрос и одни пробелы показывают все записи."""
        self.store.add("Алиса", 80, date="01.01.2026 10:00")
        self.store.add("боб", 70, date="02.01.2026 10:00")
        self.assertEqual(len(self.store.filtered()), 2)
        self.assertEqual(len(self.store.filtered("   ")), 2)

    def test_sorted_by_score_russian_and_english_keys(self):
        """Сортировка по очкам: убывание, русский ключ ``очки`` тоже работает."""
        self.store.add("малый", 40, date="01.01.2026 10:00")
        self.store.add("большой", 90, date="02.01.2026 10:00")
        self.store.add("средний", 70, date="03.01.2026 10:00")
        for key in ("score", "очки", "ОЧКИ"):
            self.assertEqual(
                [r.name for r in self.store.sorted_records(key=key)],
                ["большой", "средний", "малый"],
            )

    def test_sorted_by_date_russian_and_english_keys(self):
        """Сортировка по дате: новые записи первыми, ключ ``дата`` работает."""
        self.store.add("старый", 99, date="01.01.2020 10:00")
        self.store.add("новый", 10, date="05.05.2025 10:00")
        self.store.add("средний", 50, date="06.06.2022 10:00")
        for key in ("date", "дата", "Дата"):
            self.assertEqual(
                [r.name for r in self.store.sorted_records(key=key)],
                ["новый", "средний", "старый"],
            )

    def test_sorted_records_accepts_explicit_list(self):
        """Метод сортирует переданный список, не меняя таблицу."""
        self.store.add("a", 1, date="01.01.2026 10:00")
        self.store.add("b", 2, date="02.01.2026 10:00")
        subset = [self.store.records[0]]
        self.assertEqual([r.name for r in self.store.sorted_records(subset)], ["a"])
        self.assertEqual(len(self.store.records), 2)

    def test_clear_and_remove(self):
        """Очистка и удаление по индексу сохраняют результат на диске."""
        self.store.add("a", 1, date="01.01.2026 10:00")
        self.store.add("b", 2, date="02.01.2026 10:00")
        self.store.remove(0)
        self.assertEqual([r.name for r in self.store.records], ["b"])
        self.assertEqual(len(RecordStore(self.path)), 1)
        self.store.clear()
        self.assertEqual(len(self.store), 0)
        self.assertEqual(len(RecordStore(self.path)), 0)

    def test_best_score(self):
        """Лучший результат ищется по имени без учёта регистра."""
        self.store.add("Алиса", 70, date="01.01.2026 10:00")
        self.store.add("алиса", 82, date="02.01.2026 10:00")
        self.store.add("боб", 90, date="03.01.2026 10:00")
        self.assertEqual(self.store.best_score(" АЛИСА "), 82)
        self.assertEqual(self.store.best_score("нет"), 0)

    def test_broken_json_creates_backup_and_warning(self):
        """Битый JSON откладывается в ``.bak``, таблица пуста, есть предупреждение."""
        self.path.write_text("{это не JSON", encoding="utf-8")
        store = RecordStore(self.path)
        self.assertEqual(len(store), 0)
        self.assertIsNotNone(store.last_error)
        self.assertIn("повреждён", store.last_error)
        self.assertTrue(Path(str(self.path) + ".bak").exists())
        self.assertEqual(Path(str(self.path) + ".bak").read_text(encoding="utf-8"),
                         "{это не JSON")

    def test_atomic_save_leaves_no_temp_files(self):
        """После сохранения не остаётся временных файлов, JSON валиден."""
        for i in range(5):
            self.store.add(f"игрок{i}", i, date=f"0{i + 1}.01.2026 10:00")
        leftovers = [p.name for p in Path(self.tmp.name).iterdir()
                     if ".tmp" in p.name]
        self.assertEqual(leftovers, [])
        self.assertEqual(len(json.loads(self.path.read_text(encoding="utf-8"))["records"]), 5)

    def test_max_records_trim(self):
        """При превышении лимита удаляются самые старые записи."""
        self.store.max_records = 3
        for i in range(6):
            self.store.add(f"n{i}", i, date=f"0{i + 1}.01.2020 10:00")
        self.assertEqual(len(self.store), 3)
        self.assertEqual([r.name for r in self.store.records], ["n3", "n4", "n5"])

    def test_record_defaults_and_timestamp(self):
        """Запись имеет разумные значения по умолчанию и числовой ключ даты."""
        record = Record("Гость", 5)
        self.assertEqual(record.opponent_score, 0)
        self.assertEqual(record.result, "ничья")
        self.assertEqual(record.rounds, 0)
        self.assertEqual(record.moves, 0)
        self.assertGreater(record.timestamp, 0)
        broken = Record("Гость", 5, date="не дата")
        self.assertEqual(broken.timestamp, 0.0)

    def test_invalid_result_and_bad_values_are_normalized(self):
        """Некорректные результат и числа при загрузке не роняют таблицу."""
        self.path.write_text(json.dumps({"records": [{
            "name": "  Алиса  ", "score": "82", "opponent_score": "x",
            "result": "победа!", "rounds": None, "moves": "3",
            "date": "10.10.2025 10:00",
        }]}), encoding="utf-8")
        store = RecordStore(self.path)
        record = store.records[0]
        self.assertEqual(record.name, "Алиса")
        self.assertEqual(record.score, 82)
        self.assertEqual(record.opponent_score, 0)
        self.assertEqual(record.result, "ничья")
        self.assertEqual(record.moves, 3)


class TestStorageFallback(unittest.TestCase):
    """Тесты работы с недоступными путями и XDG."""

    def setUp(self):
        """Временный каталог служит и домом пользователя, и папкой данных."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_xdg_fallback(self):
        """Недоступная папка программы → путь в ``XDG_DATA_HOME``."""
        with patch.object(storage, "APP_DIR", Path(self.tmp.name) / "нет-такого"), \
             patch.dict(os.environ, {"XDG_DATA_HOME": self.tmp.name}):
            path = storage.default_path()
            expected = Path(self.tmp.name) / "kumalak-game" / "records.json"
            self.assertEqual(path, expected)
            store = RecordStore()
            store.add("Тест", 42, date="01.01.2026 10:00")
            self.assertTrue(expected.exists())
            self.assertEqual(len(RecordStore(expected)), 1)

    def test_fallback_path_uses_default_xdg_location(self):
        """Без ``XDG_DATA_HOME`` используется ``~/.local/share``."""
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(storage.Path, "home", return_value=Path(self.tmp.name)):
            self.assertEqual(
                fallback_path(),
                Path(self.tmp.name) / ".local" / "share" / "kumalak-game" / "records.json",
            )

    def test_save_failure_does_not_raise(self):
        """Ошибка записи не поднимает исключение, а пишется в ``last_error``."""
        store = RecordStore(Path(self.tmp.name) / "records.json", max_records=MAX_RECORDS)
        store.add("Тест", 10, date="01.01.2026 10:00")
        fake = Path(self.tmp.name) / "fallback" / "records.json"
        with patch.object(store, "_write", side_effect=OSError("нет прав")), \
             patch.object(storage, "fallback_path", return_value=fake):
            store.save()
        self.assertIsNotNone(store.last_error)
        self.assertIn("Не удалось сохранить", store.last_error)

    def test_store_never_touches_project_file(self):
        """Тестовый ``RecordStore`` не создаёт файл рядом с исходниками."""
        project_file = Path(storage.__file__).resolve().parent / "records.json"
        existed = project_file.exists()
        store = RecordStore(Path(self.tmp.name) / "own.json")
        store.add("Тест", 1)
        self.assertEqual(project_file.exists(), existed)


if __name__ == "__main__":
    unittest.main()

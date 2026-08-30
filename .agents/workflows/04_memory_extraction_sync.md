# Сценарий 4: Извлечение фактов и синхронизация памяти (Memory Extraction & Sync)

Данный workflow предназначен для актуализации базы знаний проекта (`memory/<project>/`) на основе текста новой переведённой главы или пакета глав.

---

## 1. Параметры запуска

- **`<project>`**: Идентификатор проекта (например, `tenbin`).
- **`<volume>`**: Идентификатор тома (например, `volume01`).
- **`<chapter>`**: Идентификатор главы (например, `chapter04`).
- **Исходный текст:** `source/<project>/<volume>/<chapter>.txt`.
- **Готовый перевод:** `output/<project>/<volume>/<chapter>/chapter.md`.
- **База знаний:** `memory/<project>/`.

---

## 2. Пошаговый процесс

### Шаг 1. Анализ текста субагентом `memory-extractor`
Запусти субагента `memory-extractor`:

- **Входные данные:**
  - Оригинал главы (JP/EN) и готовый перевод `chapter.md`;
  - Мастер-память: `characters.json`, `glossary.json`, `locations.json`, `relationships.json`;
  - Буфер кандидатов: `candidates.json`;
  - Шаблон предложения: `.agents/skills/memory-extractor/resources/proposal_template.json`.
- **Что делает агент:**
  1. Выявляет новые имена, термины, ранги, топонимы и изменения в отношениях персонажей («ты» / «вы»).
  2. Определяет статус надёжности сущностей:
     - `provisional` — 1 упоминание, второстепенная роль $\rightarrow$ добавление в `candidates.json`.
     - `confirmed` — 2+ упоминаний либо центральная сюжетная роль $\rightarrow$ добавление в мастер-память.
     - `PROMOTE` — сущность уже была в `candidates.json` и встретилась повторно $\rightarrow$ повышение до `confirmed` и перенос в мастер-память.
  3. Сохраняет отчёт предложений в `qa/<project>/<volume>/<chapter>/MEMORY_PROPOSAL.json`.

---

### Шаг 2. Безопасная симуляция (Dry-Run)
Перед внесением изменений в базу знаний выполни симуляцию через `extract_memory.py`:

```bash
python3 .agents/skills/memory-extractor/scripts/extract_memory.py \
  --proposal qa/<project>/<volume>/<chapter>/MEMORY_PROPOSAL.json \
  --memory-dir memory/<project>/
```

- Скрипт не изменяет файлов на диске.
- Проверь лог операций: количество добавлений в кандидаты (`added_candidates`), добавления в мастер (`added_confirmed`), продвижения (`promoted_to_master`) и обновления (`updated_entries`).

---

### Шаг 3. Атомарное применение изменений (`--apply`)
Если в логе симуляции нет ошибок схемы и нежелательных слияний, примени изменения:

```bash
python3 .agents/skills/memory-extractor/scripts/extract_memory.py \
  --proposal qa/<project>/<volume>/<chapter>/MEMORY_PROPOSAL.json \
  --memory-dir memory/<project>/ \
  --apply
```

**Гарантии безопасности скрипта:**
- Блокировка файла через `fcntl.flock` (защита от гонок параллельных процессов).
- Атомарная замена файла через `os.replace` с автоматическим созданием резервной копии `.bak`.
- Накопительное суммирование счётчика упоминаний `occurrences_count`.

---

## 3. Критерии готовности

- [x] Отчёт `qa/<project>/<volume>/<chapter>/MEMORY_PROPOSAL.json` валиден по структуре.
- [x] Все мастер-файлы (`characters.json`, `glossary.json`...) и буфер `candidates.json` успешно обновлены и сохранены на диске.
- [x] Однократные второстепенные сущности изолированы в `candidates.json` и не перегружают контекст переводчика на следующие главы.

# Сценарий 3: Сборка главы, контроль швов и линтинг (Assembly & Publication)

Данный workflow предназначен для оркестратора, когда все сегменты главы (`SEG_01` ... `SEG_XX`) переведены, отредактированы и имеют статус `APPROVED_FOR_STITCHING`.

---

## 1. Параметры запуска

- **`<project>`**: Идентификатор проекта (например, `tenbin`).
- **`<volume>`**: Идентификатор тома (например, `volume01`).
- **`<chapter>`**: Идентификатор главы (например, `chapter04`).
- **Сегменты:** `output/<project>/<volume>/<chapter>/SEG_*.md`.
- **Манифест:** `source/<project>/<volume>/<chapter>/segments/manifest.json`.

---

## 2. Пошаговый процесс

### Шаг 1. Проверка готовности сегментов
1. Проверь наличие всех сегментов согласно `manifest.json`.
2. Убедись, что для всех сегментов в `qa/<project>/<volume>/<chapter>/` присутствуют финальные арбитражные отчёты со статусом `APPROVED_FOR_STITCHING`.

---

### Шаг 2. Автоматическая сборка и аудит стыков (Stitcher)
Запусти скрипт сборщика через `run_command`:

```bash
python3 .agents/skills/stitcher/scripts/stitch_segments.py \
  --segments-dir output/<project>/<volume>/<chapter> \
  --manifest source/<project>/<volume>/<chapter>/segments/manifest.json \
  --output-file output/<project>/<volume>/<chapter>/chapter.md \
  --report-file qa/<project>/<volume>/<chapter>/STITCH_REPORT.md \
  --project <project> \
  --chapter <chapter>
```

**Что делает скрипт:**
1. Склеивает сегменты в строгом порядке `manifest.json`.
2. Анализирует границы стыков (`SEG_N` $\rightarrow$ `SEG_{N+1}`):
   - Устраняет дублирование разделителей сцен (`***`, `◇◇◇`).
   - Проверяет однозначность местоимений («Он», «Она») в начале следующего сегмента.
   - Проверяет незакрытые кавычки на стыках.
3. Формирует отчёт `qa/<project>/<volume>/<chapter>/STITCH_REPORT.md`.

---

### Шаг 3. Анализ отчёта `STITCH_REPORT.md`
- Прочитай отчёт `STITCH_REPORT.md`.
- Если зафиксированы предупреждения по местоимениям (`Pronoun Notice`) — открой соответствующий стык в `output/<project>/<volume>/<chapter>/chapter.md` и при необходимости уточни имя персонажа.

---

### Шаг 4. Типографический линтинг и форматирование (Linter)
Запусти скрипт линтера в режиме форматирования:

```bash
python3 .agents/skills/linter/scripts/lint_chapter.py \
  --input-file output/<project>/<volume>/<chapter>/chapter.md \
  --report-file qa/<project>/<volume>/<chapter>/LINT_REPORT.md \
  --project <project> \
  --chapter <chapter>
```

**Что делает скрипт:**
1. Защищает все блоки кода, ссылки, списки и заголовки Markdown.
2. Приводит диалоговые тире к стандарту `AGENTS.md` (**em dash `—\u00A0`** с неразрывным пробелом).
3. Преобразует прямые кавычки в русские «ёлочки» и „лапки“.
4. Форматирует многоточия `…`, тире в середине предложений `\u00A0— ` и числовые диапазоны `10–15`.
5. Расставляет неразрывные пробелы после предлогов/союзов и перед частицами.
6. Генерирует отчёт `qa/<project>/<volume>/<chapter>/LINT_REPORT.md`.

---

### Шаг 5. Верификация качества типографики (`--check`)
Запусти проверочный режим:

```bash
python3 .agents/skills/linter/scripts/lint_chapter.py \
  --input-file output/<project>/<volume>/<chapter>/chapter.md \
  --check
```

**Критерий успеха:**
- Код возврата `0`.
- В выводе: `PASSED: No typography defects found in ...`.
- В отчёте `LINT_REPORT.md`: `Critical Errors: 0`, `Integrity Status: 100% VERIFIED AND CLEAN`.

---

## 3. Результат этапа

- Готовый к публикации файл главы: `output/<project>/<volume>/<chapter>/chapter.md`.
- Отчёт о сборке: `qa/<project>/<volume>/<chapter>/STITCH_REPORT.md`.
- Отчёт о линтинге: `qa/<project>/<volume>/<chapter>/LINT_REPORT.md`.

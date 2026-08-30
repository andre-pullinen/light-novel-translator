# Сценарий 1: Сквозной пайплайн перевода главы (Full Chapter Pipeline)

Данный workflow предназначен для агента-оркестратора при выполнении полного цикла обработки новой главы произведения.

---

## 1. Параметры запуска

- **`<project>`**: Идентификатор проекта (например, `tenbin`).
- **`<volume>`**: Идентификатор тома (например, `volume01`).
- **`<chapter>`**: Идентификатор главы (например, `chapter08`).
- **`source/<project>/<volume>/<chapter>.txt`**: Неизменяемый исходный файл главы.

---

## 2. Пошаговый регламент оркестратора

### Шаг 0. Инициализация таск-листа или возобновление (State & Resumption)
1. **Проверка состояния:** Проверь наличие файла `qa/<project>/<volume>/<chapter>/TASK_LIST.md`.
   - **Если файл существует:** Считай его, проверь физическое наличие готовых артефактов на диске и **возобнови работу с первой незавершённой задачи** (`PENDING`/`IN_PROGRESS`), не повторяя завершённые этапы.
   - **Если файл отсутствует:** Создай каталог `qa/<project>/<volume>/<chapter>/` и инициализируй `TASK_LIST.md` из шаблона `.agents/skills/pipeline-orchestrator/resources/task_list_template.md`.
2. Обновляй статус и чекбоксы `TASK_LIST.md` в реальном времени после каждого шага конвейера.

---

### Шаг 1. Препроцессинг и интеллектуальная сегментация
1. Запусти субагента `segmenter`:
   - **Задача:** Разбить `source/<project>/<volume>/<chapter>.txt` на семантически неделимые сегменты (`SEG_01.md`, `SEG_02.md`...) по 400–750 слов с формированием `manifest.json`.
   - **Целевые файлы:** `source/<project>/<volume>/<chapter>/segments/`.
2. После завершения субагента верифицируй отсутствие потерь текста:
   ```bash
   python3 .agents/skills/segmenter/scripts/validate_segments.py \
     --source source/<project>/<volume>/<chapter>.txt \
     --segments-dir source/<project>/<volume>/<chapter>/segments
   ```
   *(Команда обязана вернуть код 0 и статус `SUCCESS: 100% Zero-Loss Text Integrity Verified`)*.
3. Обнови `TASK_LIST.md`: заполни таблицу сегментов `SEG_01`..`SEG_XX` и отметь Фазу 1 как `[x] COMPLETED`.

---

### Шаг 2. Межсегментный параллельный перевод (Round 1)
1. Прочитай `source/<project>/<volume>/<chapter>/segments/manifest.json` и получи список сегментов `SEG_01` ... `SEG_XX`.
2. Запусти субагентов `translator` **параллельно** для каждого сегмента:
   - **Вход:** `source/<project>/<volume>/<chapter>/segments/SEG_XX.md`, `manifest.json`, мастер-память `memory/<project>/`.
   - **Выход:** `output/<project>/<volume>/<chapter>/SEG_XX.md` (черновик Раунда 1).
3. Дождись завершения перевода всех сегментов.
4. Обнови `TASK_LIST.md`: отметь завершённые сегменты в Фазе 2.

---

### Шаг 3. Параллельный многораундовый микроцикл аудита и редактуры
Для каждого сегмента `SEG_XX` запусти рабочий процесс [`02_segment_qa_microcycle.md`](./02_segment_qa_microcycle.md):
1. **Параллельный запуск рецензентов:**
   - Субагент `accuracy-reviewer` $\rightarrow$ `qa/<project>/<volume>/<chapter>/ACCURACY_REPORT_SEG_XX_R{N}.md`.
   - Субагент `naturalness-reviewer` $\rightarrow$ `qa/<project>/<volume>/<chapter>/NATURALNESS_REPORT_SEG_XX_R{N}.md`.
2. **Шлюзы экономии токенов:**
   - **Zero Issues:** Если оба отчёта `NO_ISSUES` $\rightarrow$ `review-judge` и `editor` **НЕ запускаются**, сегмент сразу получает `APPROVED_FOR_STITCHING`.
   - **Селективная подача:** Если замечания нашёл только один рецензент, судье передаётся только проблемный отчёт.
3. **Арбитраж (при наличии замечаний):**
   - Субагент `review-judge` $\rightarrow$ `qa/<project>/<volume>/<chapter>/JUDGE_REPORT_SEG_XX_R{N}.md`.
   - Если все замечания отклонены (`REJECT`/`KEEP_AS_STYLE`) $\rightarrow$ `editor` **НЕ запускается**, статус `APPROVED_FOR_STITCHING`.
4. **Редактура и обязательный Re-Audit:**
   - Если есть директивы `ACCEPT`/`DOWNGRADE` $\rightarrow$ субагент `editor` вносит точечные правки в `output/<project>/<volume>/<chapter>/SEG_XX.md`.
   - **Повторный аудит обязателен:** ЛЛМ легко пропускает неточности, поэтому после правок сегмент обязательно отправляется на повторный аудит (Раунд N+1). Цикл повторяется (при необходимости 2, 3 и более раундов) до полного утверждения судьей `APPROVED_FOR_STITCHING`.
5. Обнови `TASK_LIST.md`: зафиксируй вердикты и отметь сегменты со статусом `APPROVED_FOR_STITCHING`.


---

### Шаг 4. Сборка главы и аудит стыков
1. Запусти субагента `stitcher` или выполни автоматическую сборку:
   ```bash
   python3 .agents/skills/stitcher/scripts/stitch_segments.py \
     --segments-dir output/<project>/<volume>/<chapter> \
     --manifest source/<project>/<volume>/<chapter>/segments/manifest.json \
     --output-file output/<project>/<volume>/<chapter>/chapter.md \
     --report-file qa/<project>/<volume>/<chapter>/STITCH_REPORT.md \
     --project <project> \
     --chapter <chapter>
   ```
2. Проверь отчёт `STITCH_REPORT.md` на отсутствие неразрешённых предупреждений по разделителям и местоимениям.
3. Обнови `TASK_LIST.md`: отметь Фазу 4 как `[x] COMPLETED`.

---

### Шаг 5. Техническая типографика и линтинг
1. Запусти скрипт линтинга и форматирования:
   ```bash
   python3 .agents/skills/linter/scripts/lint_chapter.py \
     --input-file output/<project>/<volume>/<chapter>/chapter.md \
     --report-file qa/<project>/<volume>/<chapter>/LINT_REPORT.md \
     --project <project> \
     --chapter <chapter>
   ```
2. Проведи финальную валидацию без изменений:
   ```bash
   python3 .agents/skills/linter/scripts/lint_chapter.py \
     --input-file output/<project>/<volume>/<chapter>/chapter.md \
     --check
   ```
   *(Команда должна завершиться с кодом 0 и статусом `PASSED`)*.
3. Обнови `TASK_LIST.md`: отметь Фазу 5 как `[x] COMPLETED`.

---

### Шаг 6. Извлечение фактов и актуализация памяти проекта
1. Запусти субагента `memory-extractor`:
   - Анализ текста оригинала и готового перевода `chapter.md`.
   - Формирование предложений в `qa/<project>/<volume>/<chapter>/MEMORY_PROPOSAL.json`.
2. Примени подтверждённые предложения к базе знаний:
   ```bash
   python3 .agents/skills/memory-extractor/scripts/extract_memory.py \
     --proposal qa/<project>/<volume>/<chapter>/MEMORY_PROPOSAL.json \
     --memory-dir memory/<project>/ \
     --apply
   ```
3. Обнови `TASK_LIST.md`: отметь Фазу 6 как `[x] COMPLETED` и переведи общий статус конвейера в `COMPLETED`.

---

## 3. Критерии успешного завершения главы

- [x] Все сегменты `SEG_01` ... `SEG_XX` имеют статус `APPROVED_FOR_STITCHING`.
- [x] Файл `chapter.md` собран и успешно прошёл проверку `lint_chapter.py --check` (`PASSED`, 0 ошибок).
- [x] База знаний `memory/<project>/` актуализирована новыми терминами и персонажами.
- [x] Все QA-артефакты сохранены в `qa/<project>/<volume>/<chapter>/`.
- [x] Файл `qa/<project>/<volume>/<chapter>/TASK_LIST.md` полностью закрыт (`COMPLETED`, все задачи отмечены `[x]`).

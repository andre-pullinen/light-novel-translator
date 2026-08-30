---
name: pipeline-orchestrator
description: Главный оркестратор и диспетчер мультиагентного конвейера перевода японских ранобэ на русский язык. Активируй при запросах на перевод главы целиком, запуск конвейера (пайплайна), обработку тома, координацию межсегментного перевода, многораундовый QA-аудит или сборку готовой главы.
---

# Навык оркестратора конвейера перевода (Pipeline Orchestrator)

Данный навык определяет протокол управления и координации мультиагентного конвейера для **Главного агента (Primary Agent)** в среде Antigravity.

---

## 1. Роль и архитектурная модель

Главный агент выступает в роли **Верховного Диспетчера и Оркестратора**:
- **Не выполняет рутинную работу сам:** не переводит текст вручную, не делает самоаудит и не заменяет специализированных субагентов.
- **Делегирует задачи субагентам (`invoke_subagent`):** запускает специализированные роли с изолированным контекстом и строгой ответственностью (1 субагент = 1 роль).
- **Управляет параллелизмом:** запускает перевод и аудит сегментов одновременно, сокращая время обработки главы в разы.
- **Контролирует шлюзы качества (Quality Gates):** проверяет коды возврата скриптов валидации, собирает арбитражные отчёты и принимает решение о переходе к следующему этапу.

---

## 2. Маршрутизация по операционным сценариям (`.agents/workflows/`)

В зависимости от задачи пользователя оркестратор выбирает соответствующий сценарий:

| Задача пользователя | Целевой рабочий процесс | Ключевые субагенты / инструменты |
| :--- | :--- | :--- |
| **Перевод новой главы с нуля** | [`.agents/workflows/01_full_chapter_pipeline.md`](../../workflows/01_full_chapter_pipeline.md) | `segmenter` $\rightarrow$ `translator` $\times N$ $\rightarrow$ `reviewers` $\rightarrow$ `judge` $\rightarrow$ `editor` $\rightarrow$ `stitcher` $\rightarrow$ `linter` $\rightarrow$ `memory-extractor` |
| **Аудит и доработка конкретного сегмента** | [`.agents/workflows/02_segment_qa_microcycle.md`](../../workflows/02_segment_qa_microcycle.md) | `accuracy-reviewer` + `naturalness-reviewer` (параллельно) $\rightarrow$ `review-judge` $\rightarrow$ `editor` |
| **Сборка переведённых сегментов и вёрстка** | [`.agents/workflows/03_assembly_and_publication.md`](../../workflows/03_assembly_and_publication.md) | `stitch_segments.py` $\rightarrow$ `lint_chapter.py` |
| **Анализ текста и пополнение базы знаний** | [`.agents/workflows/04_memory_extraction_sync.md`](../../workflows/04_memory_extraction_sync.md) | `memory-extractor` $\rightarrow$ `extract_memory.py --apply` |

---

## 3. Протокол параллельного вызова субагентов (`invoke_subagent`)

### А. Параллельный перевод всех сегментов главы
После выполнения нарезки (`segmenter`) оркестратор считывает `manifest.json` и запускает **все сегменты одновременно** в одном вызове `invoke_subagent`:

```json
{
  "Subagents": [
    {
      "TypeName": "translator",
      "Role": "Translator SEG_01",
      "Prompt": "Переведи сегмент source/tenbin/volume01/chapter08/segments/SEG_01.md на русский язык. Сохрани перевод в output/tenbin/volume01/chapter08/SEG_01.md. Используй мастер-память memory/tenbin/."
    },
    {
      "TypeName": "translator",
      "Role": "Translator SEG_02",
      "Prompt": "Переведи сегмент source/tenbin/volume01/chapter08/segments/SEG_02.md на русский язык. Сохрани перевод в output/tenbin/volume01/chapter08/SEG_02.md. Контекст предшествующих событий: см. preceding_context_summary в manifest.json. Используй мастер-память memory/tenbin/."
    }
  ]
}
```

---

### Б. Параллельный независимый аудит (Двухуровневый параллелизм)
Для каждого сегмента `SEG_XX` запускается пара рецензентов одновременно:

```json
{
  "Subagents": [
    {
      "TypeName": "accuracy-reviewer",
      "Role": "Accuracy Reviewer SEG_01 R1",
      "Prompt": "Проведи построчный аудит точности перевода output/tenbin/volume01/chapter08/SEG_01.md относительно оригинала source/tenbin/volume01/chapter08/segments/SEG_01.md. Сохрани отчёт в qa/tenbin/volume01/chapter08/ACCURACY_REPORT_SEG_01_R1.md."
    },
    {
      "TypeName": "naturalness-reviewer",
      "Role": "Naturalness Reviewer SEG_01 R1",
      "Prompt": "Проведи аудит естественности и литературности слога перевода output/tenbin/volume01/chapter08/SEG_01.md. Сохрани отчёт в qa/tenbin/volume01/chapter08/NATURALNESS_REPORT_SEG_01_R1.md."
    }
  ]
}
```

---

### В. Запуск Арбитража, Редактуры и Шлюзы экономии токенов (Short-Circuits)

После получения отчётов обоих рецензентов:

1. **Шлюз 1 (Чистый сегмент — Zero Issues):**
   - Если и `ACCURACY_REPORT`, и `NATURALNESS_REPORT` имеют статус `NO_ISSUES`:
     - **Субагент `review-judge` НЕ запускается.**
     - **Субагент `editor` НЕ запускается.**
     - Оркестратор фиксирует статус сегмента `STATUS: APPROVED_FOR_STITCHING` (экономия тысяч токенов).

2. **Шлюз 2 (Выборочная подача судье):**
   - Если замечания есть только у одного рецензента (например, у точности есть, а у естественности `NO_ISSUES`), в промпт `review-judge` передаётся только проблемный отчёт.

3. **Запуск `review-judge` (при наличии замечаний):**
   ```json
   {
     "Subagents": [
       {
         "TypeName": "review-judge",
         "Role": "Review Judge SEG_01 R1",
         "Prompt": "Проведи арбитраж замечаний из отчётов для SEG_01. Вынеси вердикты ACCEPT/DOWNGRADE/KEEP_AS_STYLE/REJECT и сформируй qa/tenbin/volume01/chapter08/JUDGE_REPORT_SEG_01_R1.md в компактном формате."
       }
     ]
   }
   ```

4. **Шлюз 3 (Все замечания отклонены судьёй):**
   - Если в `JUDGE_REPORT` нет директив `ACCEPT` или `DOWNGRADE` (все `REJECT` или `KEEP_AS_STYLE`):
     - **Субагент `editor` НЕ запускается.**
     - Сегмент получает статус `STATUS: APPROVED_FOR_STITCHING`.

5. **Запуск `editor` и обязательный Re-Audit:**
   - Если в `JUDGE_REPORT` есть `ACCEPT` или `DOWNGRADE`:
     ```json
     {
       "Subagents": [
         {
           "TypeName": "editor",
           "Role": "Editor SEG_01 R1",
           "Prompt": "Примени директивы ACCEPT и DOWNGRADE из qa/tenbin/volume01/chapter08/JUDGE_REPORT_SEG_01_R1.md к файлу output/tenbin/volume01/chapter08/SEG_01.md. Сохрани компактный журнал правок в qa/tenbin/volume01/chapter08/EDITOR_LOG_SEG_01_R1.md."
         }
       ]
     }
     ```
   - **Обязательный повторный аудит (Re-Audit):** После внесения правок Редактором сегмент **в обязательном порядке** отправляется на повторный аудит (Раунд N+1). Языковые модели склонны пропускать неточности, поэтому микроцикл продолжается (при необходимости 2, 3 и более раундов) до тех пор, пока судья не подтвердит статус `APPROVED_FOR_STITCHING`.


---

## 4. Контрольные шлюзы качества (Quality Gates)

Оркестратор обязан валидировать каждый этап через запуск детерминированных скриптов:

1. **После сегментации:**
   ```bash
   python3 .agents/skills/segmenter/scripts/validate_segments.py \
     --source source/<project>/<volume>/<chapter>.txt \
     --segments-dir source/<project>/<volume>/<chapter>/segments
   ```
   *(Код возврата 0)*.

2. **После сборки:**
   ```bash
   python3 .agents/skills/stitcher/scripts/stitch_segments.py \
     --segments-dir output/<project>/<volume>/<chapter> \
     --manifest source/<project>/<volume>/<chapter>/segments/manifest.json \
     --output-file output/<project>/<volume>/<chapter>/chapter.md \
     --report-file qa/<project>/<volume>/<chapter>/STITCH_REPORT.md \
     --project <project> \
     --chapter <chapter>
   ```

3. **Финальная типографическая проверка:**
   ```bash
   python3 .agents/skills/linter/scripts/lint_chapter.py \
     --input-file output/<project>/<volume>/<chapter>/chapter.md \
     --check
   ```
   *(Статус `PASSED`, Critical Errors: 0)*.

---

## 5. Протокол ведения Task List и возобновления работы (State & Resumption Protocol)

Для обеспечения 100% надёжности, прозрачности и возможности **мгновенно продолжить работу в любой момент** (после паузы, прерывания или сбоя) оркестратор обязан вести и непрерывно актуализировать файл задач:
`qa/<project>/<volume>/<chapter>/TASK_LIST.md`

### А. Принцип нулевой потери состояния (Zero State Loss & Resumption)
1. **Проверка при старте:** Перед выполнением любого действия по главе оркестратор **всегда** проверяет наличие `qa/<project>/<volume>/<chapter>/TASK_LIST.md`.
2. **Если `TASK_LIST.md` уже существует (Возобновление работы):**
   - Прочитай файл таск-листа и определи последнюю завершённую фазу и статус каждого сегмента.
   - Верифицируй физическое наличие файлов на диске (`source/.../segments/`, `output/.../SEG_XX.md`, `qa/.../JUDGE_REPORT_*.md`).
   - Выведи пользователю статус возобновления (например: *«Обнаружен незавершённый процесс для chapter08. Сегменты SEG_01..03 переведены, продолжаю с QA Раунда 1...»*).
   - **Немедленно возобнови работу с первой незавершённой задачи** (`PENDING` или `IN_PROGRESS`), не повторяя уже выполненные шаги.
3. **Если `TASK_LIST.md` отсутствует (Новый запуск):**
   - Создай каталог `qa/<project>/<volume>/<chapter>/`.
   - Инициализируй `TASK_LIST.md` на основе эталонного шаблона `resources/task_list_template.md` (пример заполнения: `examples/task_list_example.md`).

### Б. Принцип непрерывного чекпоинтинга (Immediate Real-Time Checkpointing)
Оркестратор обязан обновлять `TASK_LIST.md` **сразу после завершения каждой элементарной операции**:
- После генерации сегментов и `manifest.json` $\rightarrow$ обнови количество сегментов и фазу в `TASK_LIST.md`.
- После получения перевода `output/.../SEG_XX.md` $\rightarrow$ отметь сегмент как `[x] COMPLETED` в Фазе 2.
- После формирования `JUDGE_REPORT` $\rightarrow$ запиши вердикт (`APPROVED_FOR_STITCHING` или `ACCEPT`) в таблицу Фазы 3.
- После применения правок `editor` $\rightarrow$ отметь лог и обнови номер следующего раунда.
- После сборки `stitch_segments.py` $\rightarrow$ отметь Фазу 4.
- После прохождения `lint_chapter.py --check` (`PASSED`) $\rightarrow$ отметь Фазу 5.
- После синхронизации `memory-extractor` $\rightarrow$ отметь Фазу 6 и переведи общий статус главы в `COMPLETED`.

---

## 6. Информирование пользователя (Status Reporting)

Оркестратор держит пользователя в курсе прогресса лаконичными отчётами по ключевым вехам со ссылкой на `TASK_LIST.md`:

- **Старт/Возобновление:** «Запущен конвейер перевода `chapter08`. Инициализирован таск-лист `qa/tenbin/volume01/chapter08/TASK_LIST.md`.»
- **Веха 1:** «Сегментация завершена (сегментов: $N$, потерь: 0%). Запущен параллельный перевод сегментов SEG_01..SEG_XX.»
- **Веха 2:** «Перевод всех сегментов завершён. Запущен независимый аудит качества (Раунд 1).»
- **Веха 3:** «Арбитраж и редактура завершены. Все сегменты одобрены (APPROVED_FOR_STITCHING).»
- **Веха 4:** «Глава успешно собрана, отформатирована (PASSED), база знаний обновлена, таск-лист закрыт (COMPLETED).»

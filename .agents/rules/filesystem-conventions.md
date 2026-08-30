# Соглашения о файловой системе проекта

Все агенты конвейера обязаны строго соблюдать единую схему путей.

## Структура каталогов (4-уровневая модель)

В проекте строго принята 4-уровневая иерархия: `<project>/<volume>/<chapter>`.
Канонический формат именования томов: `volume01`, `volume02`, `volume03`...
Канонический формат именования глав: `chapter01`, `chapter02`...

```
source/<project>/<volume>/<chapter>.txt          # Исходный текст главы (неизменяемый)
source/<project>/<volume>/<chapter>/segments/    # Выход segmenter
  SEG_01.md, SEG_02.md, ...                      # Сегменты (чистый текст, без метаданных)
  manifest.json                                  # Реестр главы

output/<project>/<volume>/<chapter>/             # Выход translator / editor / stitcher / linter
  SEG_XX.md                                      # Перевод / отредактированный перевод сегмента
  chapter.md                                     # Собранная глава (выход stitcher → linter)

qa/<project>/<volume>/<chapter>/                 # Все QA-артефакты (стандартизированные имена)
  TASK_LIST.md                                   # Реестр задач и чекпоинтов конвейера главы
  ACCURACY_REPORT_SEG_XX_R1.md                   # Отчёт accuracy-reviewer (Раунд 1)
  ACCURACY_REPORT_SEG_XX_R{N}.md                 # Отчёт accuracy-reviewer (Раунд N)
  NATURALNESS_REPORT_SEG_XX_R1.md                # Отчёт naturalness-reviewer (Раунд 1)
  NATURALNESS_REPORT_SEG_XX_R{N}.md              # Отчёт naturalness-reviewer (Раунд N)
  JUDGE_REPORT_SEG_XX_R1.md                      # Отчёт review-judge (Раунд 1)
  JUDGE_REPORT_SEG_XX_R{N}.md                    # Отчёт review-judge (Раунд N)
  EDITOR_LOG_SEG_XX_R{N}.md                      # Журнал правок editor (Раунд N)
  STITCH_REPORT.md                               # Отчёт stitcher (сборка главы)
  LINT_REPORT.md                                 # Отчёт linter (типографика)
  MEMORY_PROPOSAL.json                           # Предложения memory-extractor

memory/<project>/                               # База знаний проекта (мастер-память)
  characters.json
  glossary.json
  locations.json
  relationships.json
  speech_patterns.json
  style.md
  translation_memory.json
  candidates.json                                # Буфер кандидатов (provisional)
```

## Обязательные правила

- **Всегда используй 4-уровневую структуру**: `<project>/<volume>/<chapter>`.
- **Не изменяй** файлы в `source/` — они неизменяемые исходники.
- **Не создавай** дублирующих файлов (например, `SEG_XX_edited.md`, `SEG_XX_v2.md`).
- **Перезаписывай** целевой файл на месте (in-place) без переименования.
- **Не добавляй** технические метаданные, служебные заголовки или примечания в файлы `SEG_XX.md` и `chapter.md`.
- QA-артефакты сохраняй **строго по схеме** выше с явными суффиксами раунда `_R{N}.md`.

# Таск-лист конвейера перевода главы: {chapter} (Проект: {project})

## Метаданные процесса

- **Проект:** `{project}`
- **Том:** `{volume}`
- **Глава:** `{chapter}`
- **Исходный файл:** `source/{project}/{volume}/{chapter}.txt`
- **Манифест сегментов:** `source/{project}/{volume}/{chapter}/segments/manifest.json`
- **Финальный файл главы:** `output/{project}/{volume}/{chapter}/chapter.md`
- **Текущая фаза:** `PHASE_1_SEGMENTATION`
- **Общий статус конвейера:** `IN_PROGRESS`
- **Лимит раундов QA:** `MAX_ROUNDS = 2`
- **Время запуска:** `{start_time}`
- **Последнее обновление:** `{last_updated_time}`

---

## Сводный прогресс

| Этап | Статус | Готовность | Ключевой артефакт |
| :--- | :--- | :--- | :--- |
| **1. Сегментация главы** | `[ ] PENDING` | 0 / 1 | `source/{project}/{volume}/{chapter}/segments/manifest.json` |
| **2. Первичный перевод сегментов** | `[ ] PENDING` | 0 / {total_segments} | `output/{project}/{volume}/{chapter}/SEG_*.md` (R1) |
| **3. Микроциклы QA и редактуры** | `[ ] PENDING` | 0 / {total_segments} | `qa/{project}/{volume}/{chapter}/JUDGE_REPORT_*.md` |
| **4. Сборка главы и швы** | `[ ] PENDING` | 0 / 1 | `qa/{project}/{volume}/{chapter}/STITCH_REPORT.md` |
| **5. Типографика и линтинг** | `[ ] PENDING` | 0 / 1 | `qa/{project}/{volume}/{chapter}/LINT_REPORT.md` |
| **6. Извлечение памяти** | `[ ] PENDING` | 0 / 1 | `qa/{project}/{volume}/{chapter}/MEMORY_PROPOSAL.json` |

---

## Детализированный реестр задач

### Фаза 1. Препроцессинг и интеллектуальная сегментация (`segmenter`)
- [ ] **1.1.** Запустить субагента `segmenter` для семантической нарезки текста главы на файлы `SEG_01.md`, `SEG_02.md`...
- [ ] **1.2.** Сгенерировать служебный реестр `source/{project}/{volume}/{chapter}/segments/manifest.json`.
- [ ] **1.3.** Запустить автоматическую верификацию целостности:
  ```bash
  python3 .agents/skills/segmenter/scripts/validate_segments.py \
    --source source/{project}/{volume}/{chapter}.txt \
    --segments-dir source/{project}/{volume}/{chapter}/segments
  ```
  *(Обязателен код возврата 0 и статус 100% Zero-Loss)*.

---

### Фаза 2. Межсегментный параллельный перевод (`translator`)

| Сегмент | Исходный файл | Выходной черновик (R1) | Субагент | Статус перевода |
| :--- | :--- | :--- | :--- | :--- |
| `SEG_01` | `source/.../SEG_01.md` | `output/.../SEG_01.md` | `Translator SEG_01` | `[ ] PENDING` |
| `SEG_02` | `source/.../SEG_02.md` | `output/.../SEG_02.md` | `Translator SEG_02` | `[ ] PENDING` |

---

### Фаза 3. Параллельный многораундовый QA-микроцикл (Reviewers $\rightarrow$ Judge $\rightarrow$ Editor)

| Сегмент | Раунд | Accuracy Report | Naturalness Report | Judge Report | Вердикт Judge | Editor Log | Итоговый статус сегмента |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `SEG_01` | R1 | `qa/.../ACCURACY_SEG_01_R1.md` | `qa/.../NATURALNESS_SEG_01_R1.md` | `qa/.../JUDGE_SEG_01_R1.md` | `PENDING` | — | `[ ] IN_QA` |
| `SEG_02` | R1 | `qa/.../ACCURACY_SEG_02_R1.md` | `qa/.../NATURALNESS_SEG_02_R1.md` | `qa/.../JUDGE_SEG_02_R1.md` | `PENDING` | — | `[ ] IN_QA` |

> **Критерий перехода:** Все сегменты обязаны получить статус `APPROVED_FOR_STITCHING`.

---

### Фаза 4. Сборка главы и аудит стыков (`stitcher`)
- [ ] **4.1.** Запустить автоматическую сборку сегментов:
  ```bash
  python3 .agents/skills/stitcher/scripts/stitch_segments.py \
    --segments-dir output/{project}/{volume}/{chapter} \
    --manifest source/{project}/{volume}/{chapter}/segments/manifest.json \
    --output-file output/{project}/{volume}/{chapter}/chapter.md \
    --report-file qa/{project}/{volume}/{chapter}/STITCH_REPORT.md \
    --project {project} \
    --chapter {chapter}
  ```
- [ ] **4.2.** Проверить `qa/{project}/{volume}/{chapter}/STITCH_REPORT.md` (статус `APPROVED_AND_STITCHED`, отсутствие неразрешённых предупреждений по разделителям и местоимениям).

---

### Фаза 5. Техническая типографика и линтинг (`linter`)
- [ ] **5.1.** Запустить форматирование текста:
  ```bash
  python3 .agents/skills/linter/scripts/lint_chapter.py \
    --input-file output/{project}/{volume}/{chapter}/chapter.md \
    --report-file qa/{project}/{volume}/{chapter}/LINT_REPORT.md \
    --project {project} \
    --chapter {chapter}
  ```
- [ ] **5.2.** Запустить строгую валидацию без модификаций:
  ```bash
  python3 .agents/skills/linter/scripts/lint_chapter.py \
    --input-file output/{project}/{volume}/{chapter}/chapter.md \
    --check
  ```
  *(Обязателен код возврата 0 и статус PASSED)*.

---

### Фаза 6. Извлечение фактов и синхронизация памяти (`memory-extractor`)
- [ ] **6.1.** Запустить субагента `memory-extractor` для анализа оригинального и готового текста главы.
- [ ] **6.2.** Сформировать предложения сущностей в `qa/{project}/{volume}/{chapter}/MEMORY_PROPOSAL.json`.
- [ ] **6.3.** Применить подтверждённые изменения к базе знаний:
  ```bash
  python3 .agents/skills/memory-extractor/scripts/extract_memory.py \
    --proposal qa/{project}/{volume}/{chapter}/MEMORY_PROPOSAL.json \
    --memory-dir memory/{project}/ \
    --apply
  ```

---

### Фаза 7. Завершение главы
- [ ] **7.1.** Все файлы проверены, артефакты синхронизированы, общий статус установлен в `COMPLETED`.

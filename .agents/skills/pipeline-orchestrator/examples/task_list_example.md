# Пример заполненного таск-листа конвейера перевода

```markdown
# Таск-лист конвейера перевода главы: chapter04 (Проект: tenbin)

## Метаданные процесса
- **Проект:** `tenbin`
- **Том:** `volume01`
- **Глава:** `chapter04`
- **Текущая фаза:** `PHASE_4_STITCHING`
- **Общий статус:** `IN_PROGRESS`

## Сводный прогресс
| Этап | Статус | Готовность |
| :--- | :--- | :--- |
| **1. Сегментация главы** | `[x] COMPLETED` | 1 / 1 |
| **2. Первичный перевод сегментов** | `[x] COMPLETED` | 3 / 3 |
| **3. Микроциклы QA и редактуры** | `[x] COMPLETED` | 3 / 3 |
| **4. Сборка главы и швы** | `[/] IN_PROGRESS` | 0 / 1 |
| **5. Типографика и линтинг** | `[ ] PENDING` | 0 / 1 |
| **6. Извлечение памяти** | `[ ] PENDING` | 0 / 1 |

## Детализация микроциклов QA
- `SEG_01`: R1 Accuracy (NO_ISSUES), Naturalness (NO_ISSUES) -> `APPROVED_FOR_STITCHING (auto: 0 issues)`
- `SEG_02`: R1 (2 issues) -> Judge (2 ACCEPT) -> Editor (2 edits) -> R2 (NO_ISSUES) -> `APPROVED_FOR_STITCHING`
- `SEG_03`: R1 (1 issue) -> Judge (1 REJECT) -> `APPROVED_FOR_STITCHING (auto: 0 actionable)`
```

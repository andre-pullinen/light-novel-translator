# Пример отчёта Linter (LINT_REPORT)

```markdown
# Lint & Typography Report — chapter04 (Project: tenbin)

## Metadata
- **Project:** `tenbin`
- **Volume:** `volume01`
- **Chapter:** `chapter04`
- **Target File:** `output/tenbin/volume01/chapter04/chapter.md`
- **Status:** **PASSED**

---

## Applied Transformations Breakdown

| Transformation | Applied Count | Standard / Description |
|---|---|---|
| **Dialogue Em-Dashes (`—\u00A0`)** | 42 | Standard em-dash with NBSP (`AGENTS.md`) |
| **Dialogue Paragraphs** | 42 | Separate <p> paragraphs for each dialogue replica |
| **Narrative-Dialogue Separators (`<br>`)** | 6 | Rendered break line between narrative and dialogue |

| **Russian Quotes (`«...»` / `„...“`)** | 8 | Converted straight quotes to Russian typography |
| **Scene Dividers (`<p align="center">◇◆◇</p>`)** | 2 | Standard centered diamond divider (`AGENTS.md`) |
| **Typographical Ellipsis (`…`)** | 15 | Replaced ASCII `...` with `…` |
| **Preposition Non-Breaking Spaces** | 120 | Bound short words (`в`, `на`, `с`, etc.) to next word |


---

## Post-Transformation Diagnostics

- **Critical Errors:** 0
- **Typography Warnings:** 0
- **Integrity Status:** **100% VERIFIED AND CLEAN**
```

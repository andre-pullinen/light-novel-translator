# Light Novel Translation Project

## Purpose

This project is an agentic workflow for translating Japanese light novels into Russian.

The system must prioritize:

1. Meaning accuracy.
2. Preservation of author intent.
3. Preservation of character voice.
4. Natural Russian.
5. Consistent terminology.
6. Avoidance of Japanese syntactic calques.

## Translation principles

- Do not add information absent from the source.
- Do not remove information present in the source.
- Do not invent explanations.
- Do not rewrite the author's style without a reason.
- Do not translate sentence-by-sentence without paragraph context.
- Always consider previous and following context.
- Preserve POV.
- Preserve character speech patterns.
- Preserve ambiguity when the Japanese is intentionally ambiguous.

## Editing principles

The editor must not rewrite text merely because another wording is stylistically preferable.

Every substantive correction must have a reason.

Preferred reasons:

- mistranslation
- omission
- addition
- incorrect subject
- incorrect implication
- terminology inconsistency
- unnatural Russian
- Japanese syntactic calque
- incorrect character voice
- POV inconsistency

## Output

Translations are written in Russian.

Formatting standards:

- Dialogue uses an em dash:
  —\u00A0Реплика.
  (Do not use en dash or hyphen for dialogue).
- **Dialogue paragraphs and reader compatibility:**
  Each dialogue replica and narrative block MUST render in its own separate paragraph (`<p>...<p>`). In readers with first-line paragraph indentation (`text-indent`), this ensures every dialogue replica receives proper indentation.
  Consecutive dialogue replicas go on separate lines with a blank line between them (`\n\n`), without trailing spaces (`  `) or `<br>` line breaks.
- **Line break separator between narrative and dialogue:**
  Between narrative text and dialogue blocks (both before the first replica and after the last replica before narrative resumes), an explicit `<br>` tag MUST be placed:
  <br>
  surrounded by blank lines (`\n\n<br>\n\n`). This renders an empty line between narrative and dialogue in all readers without breaking paragraph indentation.


- Direct internal thoughts: *курсив* (`*Мысль персонажа.*`).
- Chat / instant messages / SMS: **Имя:** текст (`**Харуки:** Привет!`).
- System notifications and UI interface: `[Системное сообщение]` или `*курсивом системное сообщение*` (`[Получен новый навык]` или `*[Получен новый навык]*`).
- Scene breaks must always use a centered divider:
  <p align="center">◇◆◇</p>
  (Do not use raw horizontal rules or uncentered markers).

Keep paragraph structure unless there is a strong reason to change it.
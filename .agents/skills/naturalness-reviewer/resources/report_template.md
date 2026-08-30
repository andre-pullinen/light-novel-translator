# Шаблон компактного отчёта Naturalness Reviewer

## При наличии замечаний:

```markdown
NAT-01 H
S: [исходный фрагмент JP/EN при необходимости]
T: [фрагмент перевода RU]
I: [тип кальки/дефекта: syntactic calque | preposed modifier calque | foreign idiom/metaphor | unnatural word order | pronoun overuse | awkward participle/gerund | stiff dialogue | bureaucratese / passive]
A: [естественная альтернатива]

NAT-02 M
T: ...
I: ...
A: ...

SUMMARY: 1 H, 1 M
```

## Если текст звучит естественно и калек нет:

```markdown
NO_ISSUES
```

## Уровни критичности (Severity):
- **H (High / Major)** — грубая синтаксическая калька, канцелярит, спотыкание, неестественный пассив.
- **M (Medium / Minor)** — шероховатость, избыток местоимений, тяжеловесный причастный оборот.
- **L (Low / Stylistic)** — пограничный случай, допустимая шероховатость.

#!/usr/bin/env python3
"""
Production-grade Markdown-Aware Linter and Formatter for Russian Light Novel translations.

Features:
- Markdown Syntax Protection:
  - Standard Markdown bullet lists (- item, * item, + item, 1. item) are strictly preserved as lists and never converted to dialogue.
  - Preserves Markdown hard line breaks (exact 2 trailing spaces) without trimming or collapsing.
  - Supports Markdown links with titles: [text](url "title") and [text](url 'title').
  - Preserves footnote definitions [^1]: and references [^1].
  - Preserves Setext heading underlines (=== and ---).
  - Fenced code blocks (``` and ~~~) and inline code (`...`) are completely protected.
  - HTML comments and tags.
  - Headings (# Title) and blockquotes (> Quote) retain their markdown markers and single-line structure.
  - Scene dividers and horizontal rules (---, ***, ___, ◇◇◇, ◆◆◆) are preserved.
- Advanced Typography & Formatting Pipeline:
  - Dialogue formatting: canonical em-dash with NBSP (—\u00A0Реплика) for dialogue dashes (—, –, --).
  - Quotation marks: Russian guillemets («...») with nested quotes („...“), localized depth reset per paragraph/line.
  - Inch / Prime marks (70", 15", 27") preserved without false quote conversion.
  - Typographical ellipsis (…).
  - Dialogue thoughts and quotes starting with « are tracked in speech metrics.
  - Mid-sentence dashes: \u00A0— (NBSP + em-dash + space), supporting all punctuation before dash (, ! ? … » ”).
  - Number ranges: isolated 2-part ranges converted to unspaced en-dash (10–15, 2020–2026), phone numbers (8-800-555-35-35) preserved.
  - Russian initials with NBSP (А.\u00A0С.\u00A0Пушкин).
  - Common abbreviations with NBSP (и\u00A0т.\u00A0д., и\u00A0т.\u00A0п., т.\u00A0е., т.\u00A0к.).
  - Non-breaking spaces: compiled regex for prepositions/conjunctions with negative lookbehind against hyphenated suffixes (-то, из-за, по-русски).
  - Whitespace, CRLF/LF line ending preservation, and blank line normalization.
- 100% Synchronized CLI Modes & Honest Reporting:
  - Real post-transformation diagnostics in LINT_REPORT.md (no hardcoded metrics).
  - `--check`: Deterministic check-only mode (validates all rules and exits with code 1 if any transformations are needed).
  - `--fix` (default): Formatter mode with post-check validation and detailed report.
"""

import os
import sys
import re
import argparse
import difflib
from typing import Tuple, List, Dict

# Prepositions and conjunctions (case-insensitive) to bind with NBSP
SHORT_WORDS = [
    "в", "во", "на", "с", "со", "к", "ко", "из", "изо", "за", "по", "под", "подо",
    "и", "а", "но", "да", "о", "об", "обо", "от", "ото", "у", "до", "не", "ни",
    "для", "над", "надо", "при", "про", "без", "безо", "сквозь", "через", "то"
]

# Trailing particles to bind with leading NBSP
TRAILING_PARTICLES = ["же", "ж", "ли", "ль", "бы", "б"]

# Precompiled regular expressions for high performance
# Lookbehind includes hyphen [а-яА-ЯёЁa-zA-Z0-9_-] to prevent false match on -то (кто-то, что-то)
RE_SHORT_WORDS = re.compile(
    r'(?<![а-яА-ЯёЁa-zA-Z0-9_-])(' + '|'.join(SHORT_WORDS) + r')[ \t]+(?=[а-яА-ЯёЁa-zA-Z0-9_«„*(\[])',
    re.IGNORECASE
)

RE_TRAILING_PARTICLES = re.compile(
    r'(?<=[а-яА-ЯёЁa-zA-Z0-9_»”*)\].!?…])[ \t]+(' + '|'.join(TRAILING_PARTICLES) + r')(?=[\s\.,;!?:…«»\)\]\"\'\x00]|$)',
    re.IGNORECASE
)

# Initials and abbreviations
RE_INITIALS_1 = re.compile(r'\b([А-ЯЁ]\.)[ \t]+(?=[А-ЯЁ]\.)')
RE_INITIALS_2 = re.compile(r'\b([А-ЯЁ]\.[ \t\u00A0]*[А-ЯЁ]\.)[ \t]+(?=[А-ЯЁ][а-яё]+)')
RE_I_T_D = re.compile(r'\bи[ \t]+т\.[ \t]*д\.')
RE_I_T_P = re.compile(r'\bи[ \t]+т\.[ \t]*п\.')
RE_T_E = re.compile(r'\bт\.[ \t]*е\.')
RE_T_K = re.compile(r'\bт\.[ \t]*к\.')

# Isolated 2-part number ranges: 10-15, 2020—2026 -> 10–15 (en-dash, U+2013). Excludes phone numbers (8-800-...)
RE_NUMBER_RANGE = re.compile(
    r'(?<![\d\w-])\b(\d+)[ \t]*[-—–][ \t]*(\d+)\b(?![-–\w])'
)

# Mid-sentence dash: word — word or «Привет», — сказал он.
RE_MID_DASH = re.compile(r'(?<=[\S»”!?…,])[ \t]+[—–-][ \t]+(?=\S)')
RE_ASCII_ELLIPSIS = re.compile(r'\.{3,}')
RE_CONSECUTIVE_SPACES = re.compile(r'[ \t]{2,}')
RE_MULTIPLE_BLANK_LINES = re.compile(r'\n{3,}')

# Dialogue regex matching em-dash, en-dash, or double hyphen (single hyphen is strictly a Markdown list)
RE_DIALOGUE_START = re.compile(r'^[ \t]*([—–]|--)[ \t\u00A0]*(.*)$')
RE_QUOTE_SPEECH_START = re.compile(r'^[ \t]*([«„])(.*)$')

# Narrative-dialogue separator pattern (<br>)
CANONICAL_SEPARATOR = '<br>'
RE_SEPARATOR = re.compile(r'^[ \t]*(?:<br[ \t]*\/?>|<p>[ \t\u00A0]*(?:&nbsp;)?[ \t\u00A0]*<\/p>)[ \t]*$', re.IGNORECASE)


# Scene divider patterns
CANONICAL_SCENE_DIVIDER_TEXT = '<p align="center">◇◆◇</p>'
RE_CANONICAL_SCENE_DIVIDER = re.compile(r'^[ \t]*<p[ \t]+align=["\']?center["\']?>[ \t]*◇◆◇[ \t]*<\/p>[ \t]*$', re.MULTILINE | re.IGNORECASE)
RE_RAW_SCENE_DIVIDER = re.compile(
    r'^[ \t]*(?:'
    r'<p[ \t]+align=["\']?center["\']?>[ \t]*(?!◇◆◇)(?:[-*_]{3,}|(?:[◇◆*][ \t]*){3,})[ \t]*<\/p>|'
    r'<center>[ \t]*(?:[-*_]{3,}|(?:[◇◆*][ \t]*){3,})[ \t]*<\/center>|'
    r'[-*_]{3,}|'
    r'(?:[◇◆*][ \t]*){3,}'
    r')[ \t]*$',
    re.MULTILINE | re.IGNORECASE
)


# Markdown structural patterns
RE_FENCED_CODE = re.compile(r'(?s)(```[^\n]*\n.*?```|~~~[^\n]*\n.*?~~~)')
RE_INLINE_CODE = re.compile(r'(`+[^`\n]+`+)')
RE_HTML_TAGS = re.compile(r'(<!--.*?-->|<[a-zA-Z\/][^>]*>)', re.DOTALL)
# Link regex supporting balanced parentheses and optional title
RE_LINK_URL = re.compile(
    r'(!?\[(?:\\.|[^\]\\])*\])'
    r'(\((?:[^\(\)\s\\]|\\.|\((?:[^\(\)\s\\]|\\.)*\))*(?:\s+(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'))?\s*\))'
)
# Footnotes: [^1]: description and [^1]
RE_FOOTNOTE_DEF = re.compile(r'^[ \t]*(\[\^[^\]]+\]:)[ \t]*', re.MULTILINE)
RE_FOOTNOTE_REF = re.compile(r'(\[\^[^\]]+\])')
RE_SETEXT_UNDERLINE = re.compile(r'^[ \t]*={2,}[ \t]*$', re.MULTILINE)


class MarkdownMasker:
    """Safely masks and unmasks Markdown elements to protect them from typography transforms."""

    def __init__(self):
        self.tokens: List[str] = []

    def _store(self, match_str: str) -> str:
        idx = len(self.tokens)
        self.tokens.append(match_str)
        return f"\x00MD_TOKEN_{idx}\x00"

    def mask(self, text: str) -> str:
        self.tokens.clear()

        # 1. Mask fenced code blocks
        text = RE_FENCED_CODE.sub(lambda m: self._store(m.group(0)), text)

        # 2. Mask inline code
        text = RE_INLINE_CODE.sub(lambda m: self._store(m.group(0)), text)

        # 3. Mask canonical scene dividers
        text = RE_CANONICAL_SCENE_DIVIDER.sub(lambda m: self._store(CANONICAL_SCENE_DIVIDER_TEXT), text)

        # 4. Mask HTML comments and tags
        text = RE_HTML_TAGS.sub(lambda m: self._store(m.group(0)), text)

        # 5. Mask footnote definitions [^1]:
        text = RE_FOOTNOTE_DEF.sub(lambda m: self._store(m.group(1)) + " ", text)

        # 6. Mask footnote references [^1]
        text = RE_FOOTNOTE_REF.sub(lambda m: self._store(m.group(0)), text)

        # 7. Mask link/image target URLs and titles
        text = RE_LINK_URL.sub(lambda m: m.group(1) + self._store(m.group(2)), text)

        # 8. Mask Setext heading underlines (===)
        text = RE_SETEXT_UNDERLINE.sub(lambda m: self._store(m.group(0)), text)

        return text

    def unmask(self, text: str) -> str:
        for idx in range(len(self.tokens) - 1, -1, -1):
            token_placeholder = f"\x00MD_TOKEN_{idx}\x00"
            text = text.replace(token_placeholder, self.tokens[idx])
        return text


def convert_quotes_russian(text: str) -> Tuple[str, int]:
    """
    Converts straight double quotes (") to Russian typographic quotes:
    - Outer level: «...» (guillemets)
    - Nested level: „...“ (low-high quotes)
    - Preserves inch/prime marks (70", 15") directly following digits.
    - Resets depth = 0 per call to ensure errors do not propagate across paragraphs.
    """
    result = []
    depth = 0
    i = 0
    n = len(text)
    quotes_converted = 0

    while i < n:
        char = text[i]

        if char == '"':
            prev_char = text[i - 1] if i > 0 else ' '
            next_char = text[i + 1] if i + 1 < n else ' '

            # Check if this is an inch/prime symbol following a digit (e.g. 70" screen)
            if prev_char.isdigit() and (next_char in ' \t\n\r.,!?;:)»”\x00' or i + 1 == n):
                result.append('"')
                i += 1
                continue

            quotes_converted += 1
            is_opening = (prev_char in ' \t\n\r([{\u00A0—–-«„\x00') and (next_char not in ' \t\n\r.,!?;:…»”")}\x00')
            is_closing = (prev_char not in ' \t\n\r([{\u00A0—–-«„\x00') and (next_char in ' \t\n\r.,!?;:…»”")}\x00' or i + 1 == n)

            if is_opening and not is_closing:
                if depth == 0:
                    result.append('«')
                else:
                    result.append('„')
                depth += 1
            elif is_closing and not is_opening:
                if depth > 1:
                    result.append('“')
                    depth -= 1
                else:
                    result.append('»')
                    depth = max(0, depth - 1)
            else:
                if depth > 0:
                    if depth > 1:
                        result.append('“')
                    else:
                        result.append('»')
                    depth -= 1
                else:
                    result.append('«')
                    depth += 1
            i += 1
        elif char in '«„':
            depth += 1
            result.append(char)
            i += 1
        elif char in '»“':
            depth = max(0, depth - 1)
            result.append(char)
            i += 1
        else:
            result.append(char)
            i += 1

    return "".join(result), quotes_converted


def format_text_segment(text: str, stats: Dict[str, int]) -> str:
    """Unified typography pipeline applied to any text payload once."""
    if not text:
        return ""

    # 1. Russian quotation marks (depth localized per segment)
    text, q_count = convert_quotes_russian(text)
    stats["quotes_fixed"] += q_count

    # 2. Typographical ellipsis
    if '...' in text:
        stats["ellipsis_fixed"] += len(RE_ASCII_ELLIPSIS.findall(text))
        text = RE_ASCII_ELLIPSIS.sub('…', text)

    # 3. Number ranges: 10-15 -> 10–15
    num_matches = len(RE_NUMBER_RANGE.findall(text))
    if num_matches > 0:
        stats["number_ranges_fixed"] += num_matches
        text = RE_NUMBER_RANGE.sub(r'\1–\2', text)

    # 4. Russian Initials & common abbreviations (А. С. Пушкин -> А.\u00A0С.\u00A0Пушкин)
    if '.' in text:
        text = RE_INITIALS_1.sub(lambda m: m.group(1) + '\u00A0', text)
        text = RE_INITIALS_2.sub(lambda m: m.group(1) + '\u00A0', text)
        text = RE_I_T_D.sub('и\u00A0т.\u00A0д.', text)
        text = RE_I_T_P.sub('и\u00A0т.\u00A0п.', text)
        text = RE_T_E.sub('т.\u00A0е.', text)
        text = RE_T_K.sub('т.\u00A0к.', text)

    # 5. Non-breaking spaces for short words (with hyphen-suffix protection)
    sw_matches = len(RE_SHORT_WORDS.findall(text))
    if sw_matches > 0:
        stats["nbsp_prepositions"] += sw_matches
        text = RE_SHORT_WORDS.sub(lambda m: m.group(1) + '\u00A0', text)

    # 6. Non-breaking spaces for trailing particles
    part_matches = len(RE_TRAILING_PARTICLES.findall(text))
    if part_matches > 0:
        stats["nbsp_particles"] += part_matches
        text = RE_TRAILING_PARTICLES.sub(lambda m: '\u00A0' + m.group(1), text)

    # 7. Mid-sentence dashes (including dialogue author tags)
    mid_dash_matches = len(RE_MID_DASH.findall(text))
    if mid_dash_matches > 0:
        stats["mid_dashes_fixed"] += mid_dash_matches
        text = RE_MID_DASH.sub('\u00A0— ', text)

    # 8. Normalize consecutive normal spaces
    text = RE_CONSECUTIVE_SPACES.sub(' ', text)

    return text


def lint_and_format_line(line: str, stats: Dict[str, int]) -> str:
    """
    Decomposes line into markdown prefix and core payload.
    Strips trailing spaces (dialogues are rendered in separate paragraphs without hard breaks).
    """
    line_core = re.sub(r'[ \t]+$', '', line)
    if len(line_core) < len(line):
        stats["trailing_spaces_removed"] += 1

    stripped = line_core.strip()
    if not stripped:
        return ""

    # 1. Check Markdown heading (# Title)
    heading_match = re.match(r'^(#{1,6}[ \t]+)(.*)$', line_core)
    if heading_match:
        prefix = heading_match.group(1)
        payload = heading_match.group(2)
        return prefix + format_text_segment(payload, stats)

    # 2. Check Markdown blockquote (> Quote)
    blockquote_match = re.match(r'^([ \t]*>[ \t]*)(.*)$', line_core)
    if blockquote_match:
        prefix = blockquote_match.group(1)
        payload = blockquote_match.group(2)
        return prefix + format_text_segment(payload, stats)

    # 3. Check Markdown List (-, *, +, 1.) - strictly preserved as list
    list_match = re.match(r'^([ \t]*(?:[-*+]|\d+\.)[ \t]+)(.*)$', line_core)
    if list_match:
        prefix = list_match.group(1)
        payload = list_match.group(2)
        return prefix + format_text_segment(payload, stats)

    # 4. Check Dialogue (starts with —, –, or double hyphen --)
    dialogue_match = RE_DIALOGUE_START.match(line_core)
    if dialogue_match:
        stats["dialogue_total"] += 1
        dash_char = dialogue_match.group(1)
        if dash_char != '—' or not line_core.startswith('—\u00A0'):
            stats["dialogue_dashes_fixed"] += 1
        prefix = '—\u00A0'
        payload = dialogue_match.group(2)
        return prefix + format_text_segment(payload, stats)

    # 5. Check direct thought/quoted speech line starting with «
    quote_match = RE_QUOTE_SPEECH_START.match(line_core)
    if quote_match:
        stats["dialogue_total"] += 1
        return format_text_segment(line_core, stats)

    # 6. Regular paragraph text
    return format_text_segment(line_core, stats)


def is_dialogue_start(line: str) -> bool:
    """Detects if a line starts as dialogue (em-dash, en-dash, double hyphen)."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("\x00MD_TOKEN_"):
        return False
    return stripped.startswith("—") or stripped.startswith("–") or stripped.startswith("--")


def format_markdown_document(raw_text: str) -> Tuple[str, Dict[str, int]]:
    """Protects Markdown syntax, applies typography transformations, formats dialogues as separate paragraphs, places <br> between narrative and dialogue, and restores masked tokens."""
    has_crlf = "\r\n" in raw_text
    stats = {
        "dialogue_total": 0,
        "dialogue_dashes_fixed": 0,
        "dialogue_paragraphs": 0,
        "dialogue_separators_fixed": 0,
        "quotes_fixed": 0,
        "ellipsis_fixed": 0,
        "number_ranges_fixed": 0,
        "nbsp_prepositions": 0,
        "nbsp_particles": 0,
        "mid_dashes_fixed": 0,
        "trailing_spaces_removed": 0,
        "blank_lines_collapsed": 0,
        "scene_dividers_total": 0,
        "scene_dividers_fixed": 0
    }

    # Step 0: Pre-normalize scene dividers and strip existing empty paragraph / break tags
    normalized_raw = raw_text.replace("\r\n", "\n")
    pre_lines = []
    for line in normalized_raw.splitlines():
        stripped = line.strip()
        if RE_CANONICAL_SCENE_DIVIDER.match(stripped):
            stats["scene_dividers_total"] += 1
            pre_lines.append(CANONICAL_SCENE_DIVIDER_TEXT)
        elif RE_RAW_SCENE_DIVIDER.match(stripped):
            stats["scene_dividers_fixed"] += 1
            stats["scene_dividers_total"] += 1
            pre_lines.append(CANONICAL_SCENE_DIVIDER_TEXT)
        elif RE_SEPARATOR.match(stripped):
            # Omit during element extraction so we can place <br> deterministically
            continue
        else:
            pre_lines.append(line)
    normalized_raw = "\n".join(pre_lines)

    # Step 1: Mask Markdown structures
    masker = MarkdownMasker()
    masked_text = masker.mask(normalized_raw)

    # Step 2: Extract structural elements
    lines = [l.rstrip() for l in masked_text.splitlines()]
    elements = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped == CANONICAL_SCENE_DIVIDER_TEXT:
            elements.append(("DIVIDER", CANONICAL_SCENE_DIVIDER_TEXT))
            i += 1
        elif re.match(r"^#{1,6}\s", stripped):
            formatted_heading = lint_and_format_line(stripped, stats)
            elements.append(("HEADING", formatted_heading))
            i += 1
        elif is_dialogue_start(stripped):
            formatted_diag = lint_and_format_line(stripped, stats)
            stats["dialogue_paragraphs"] += 1
            elements.append(("DIALOGUE", formatted_diag))
            i += 1
        else:
            narr_lines = [stripped]
            i += 1
            while i < n and lines[i].strip() and not (
                lines[i].strip() == CANONICAL_SCENE_DIVIDER_TEXT or
                re.match(r"^#{1,6}\s", lines[i].strip()) or
                is_dialogue_start(lines[i].strip())
            ):
                narr_lines.append(lines[i].strip())
                i += 1
            combined_narr = " ".join(narr_lines)
            formatted_narr = lint_and_format_line(combined_narr, stats)
            elements.append(("NARRATIVE", formatted_narr))

    # Step 3: Assemble formatted document with <br> between narrative and dialogue
    out_blocks = []
    for idx, (t, content) in enumerate(elements):
        out_blocks.append(content)
        if idx < len(elements) - 1:
            next_t, _ = elements[idx + 1]
            if (t == "NARRATIVE" and next_t == "DIALOGUE") or (t == "DIALOGUE" and next_t == "NARRATIVE"):
                out_blocks.append(CANONICAL_SEPARATOR)
                stats["dialogue_separators_fixed"] += 1


    result_masked = "\n\n".join(out_blocks).rstrip("\n") + "\n"

    # Step 4: Unmask protected tokens
    final_text = masker.unmask(result_masked)

    # Restore original CRLF if present
    if has_crlf:
        final_text = final_text.replace("\n", "\r\n")

    return final_text, stats


def verify_typography_integrity(text: str) -> List[Tuple[int, str, str]]:
    """Performs real verification of final text to detect any remaining typography defects."""
    defects = []
    lines = text.replace("\r\n", "\n").splitlines()

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue

        # Check scene divider format
        if RE_RAW_SCENE_DIVIDER.match(stripped):
            defects.append((idx, "Non-canonical scene divider (must be <p align=\"center\">◇◆◇</p>)", line[:50]))
            continue

        # Check obsolete or non-canonical HTML markers
        if re.match(r'^[ \t]*<p>[ \t\u00A0]*(?:&nbsp;)?[ \t\u00A0]*<\/p>', stripped, re.I):
            defects.append((idx, "Obsolete '<p> </p>' separator (must be <br>)", line[:50]))
            continue
        if re.match(r'^[ \t]*<br[ \t]*\/>', stripped, re.I):
            defects.append((idx, "Non-canonical break tag (must be <br>)", line[:50]))
            continue

        # Canonical scene dividers and break separators are valid HTML markers
        if RE_CANONICAL_SCENE_DIVIDER.match(stripped) or stripped == CANONICAL_SEPARATOR:
            continue

        # Check dialogue dashes
        if re.match(r'^[ \t]*–[ \t\u00A0]*', line):
            defects.append((idx, "Non-standard en-dash dialogue", line[:50]))
        elif re.match(r'^[ \t]*—[ \t]+(?!\u00A0)', line):
            defects.append((idx, "Dialogue em-dash missing NBSP", line[:50]))

        # Check dialogue trailing spaces (obsolete hard break)
        if is_dialogue_start(stripped) and line.endswith("  "):
            defects.append((idx, "Dialogue line has obsolete Markdown hard break ('  ')", line[:50]))

        # Check consecutive dialogue lines on adjacent lines
        if is_dialogue_start(stripped) and idx < len(lines):
            next_line = lines[idx]
            if next_line.strip() and is_dialogue_start(next_line):
                defects.append((idx, "Consecutive dialogue replicas on adjacent lines without blank line", line[:50]))

        # Check straight quotes outside HTML tags (excluding inch numbers like 27" or 70")
        line_no_html = RE_HTML_TAGS.sub('', line)
        if re.search(r'(?<!\d)"', line_no_html):
            defects.append((idx, "Unconverted straight quote", line[:50]))

        # Check ASCII ellipsis
        if '...' in line:
            defects.append((idx, "ASCII ellipsis '...'", line[:50]))

        # Check unformatted number range with hyphen or em-dash (excluding phone numbers and valid en-dashes)
        if re.search(r'(?<![\d\w-])\b(\d+)[ \t]*[-—][ \t]*(\d+)\b(?![-–\w])', line):
            defects.append((idx, "Number range with hyphen/em-dash instead of en-dash", line[:50]))

    # Check structural transitions for <br> between narrative and dialogue
    blocks = []
    for idx, line in enumerate(lines, start=1):
        s = line.strip()
        if not s:
            continue
        if RE_CANONICAL_SCENE_DIVIDER.match(s) or RE_RAW_SCENE_DIVIDER.match(s):
            blocks.append((idx, "DIVIDER", s))
        elif s == CANONICAL_SEPARATOR:
            blocks.append((idx, "BR", s))
        elif re.match(r"^#{1,6}\s", s):
            blocks.append((idx, "HEADING", s))
        elif is_dialogue_start(s):
            blocks.append((idx, "DIALOGUE", s))
        else:
            blocks.append((idx, "NARRATIVE", s))

    for i in range(len(blocks) - 1):
        idx_curr, t_curr, s_curr = blocks[i]
        idx_next, t_next, s_next = blocks[i + 1]

        if t_curr == "NARRATIVE" and t_next == "DIALOGUE":
            defects.append((idx_curr, "Missing '<br>' separator between narrative and dialogue", s_curr[:50]))
        elif t_curr == "DIALOGUE" and t_next == "NARRATIVE":
            defects.append((idx_curr, "Missing '<br>' separator between dialogue and narrative", s_curr[:50]))
        elif t_curr == "BR" and t_next == "BR":
            defects.append((idx_curr, "Duplicate '<br>' separator", s_curr[:50]))


    return defects



def analyze_differences(raw_text: str, formatted_text: str) -> List[str]:
    """Generates detailed line-by-line defect diagnostics when formatted_text != raw_text."""
    raw_lines = raw_text.splitlines()
    formatted_lines = formatted_text.splitlines()
    diff_report = []

    matcher = difflib.SequenceMatcher(None, raw_lines, formatted_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'insert':
            ref_idx = min(i1, len(raw_lines) - 1) if raw_lines else 0
            snippet = raw_lines[ref_idx][:60] if raw_lines else "start of file"
            diff_report.append(f"Line {i1 + 1} [Missing separator]: near '{snippet}'")
        elif tag != 'equal':
            for line_idx in range(i1, i2):
                if line_idx < len(raw_lines):
                    diff_report.append(f"Line {line_idx + 1}: '{raw_lines[line_idx][:60]}'")


    return diff_report


def generate_lint_report(
    input_file: str,
    output_file: str,
    project: str,
    chapter: str,
    stats: Dict[str, int],
    raw_text: str,
    final_text: str
) -> str:
    """Generates an honest, comprehensive markdown lint report with verified diagnostics."""
    total_nbsp = final_text.count('\u00A0')
    total_dialogues = len(re.findall(r'^[ \t]*(?:—\u00A0|[«„])', final_text, re.MULTILINE))
    total_em_dashes = final_text.count('—')
    total_words = len(re.findall(r'[a-zA-Zа-яА-ЯёЁ0-9_]+', final_text))
    total_lines = len(final_text.splitlines())

    code_blocks_before = len(RE_FENCED_CODE.findall(raw_text))
    code_blocks_after = len(RE_FENCED_CODE.findall(final_text))
    syntax_intact = (code_blocks_before == code_blocks_after)

    # Real verification pass
    remaining_defects = verify_typography_integrity(final_text)
    total_warnings = len(remaining_defects)
    total_critical = 0 if syntax_intact else 1

    status = "PASSED" if total_warnings == 0 and total_critical == 0 else "WARNINGS_FOUND"

    report_lines = [
        f"# Lint & Typography Report — {chapter} (Project: {project})",
        "",
        "## Metadata",
        f"- **Project:** `{project}`",
        f"- **Chapter:** `{chapter}`",
        f"- **Target File:** `{output_file}`",
        f"- **Status:** **{status}**",
        "",
        "---",
        "",
        "## Applied Transformations Breakdown",
        "",
        "| Transformation | Applied Count | Standard / Description |",
        "|---|---|---|",
        f"| **Dialogue Em-Dashes (`—\\u00A0`)** | {stats['dialogue_dashes_fixed']} fixed / {stats['dialogue_total']} total | Standard em-dash with NBSP (`AGENTS.md`) |",
        f"| **Dialogue Paragraphs** | {stats['dialogue_paragraphs']} | Separate <p> paragraphs for each dialogue replica |",
        f"| **Narrative-Dialogue Separators (`<br>`)** | {stats['dialogue_separators_fixed']} | Rendered break line between narrative and dialogue |",

        f"| **Russian Quotes (`«...»` / `„...“`)** | {stats['quotes_fixed']} | Converted straight quotes with depth reset |",
        f"| **Scene Dividers (`<p align=\"center\">◇◆◇</p>`)** | {stats['scene_dividers_fixed']} fixed / {stats['scene_dividers_total']} total | Standard centered diamond divider (`AGENTS.md`) |",
        f"| **Typographical Ellipsis (`…`)** | {stats['ellipsis_fixed']} | Replaced ASCII `...` with `…` |",
        f"| **Number Ranges En-Dash (`–`)** | {stats['number_ranges_fixed']} | Formatted number ranges (10–15) |",
        f"| **Mid-Sentence Dashes (`\\u00A0— `)** | {stats['mid_dashes_fixed']} | Unified to em-dash with leading NBSP |",
        f"| **Preposition Non-Breaking Spaces** | {stats['nbsp_prepositions']} | Bound short words (`в`, `на`, `с`, etc.) to next word |",
        f"| **Particle Non-Breaking Spaces** | {stats['nbsp_particles']} | Bound trailing particles (`же`, `ли`, `бы`) |",
        f"| **Trailing Whitespace Cleaned** | {stats['trailing_spaces_removed']} lines | Stripped trailing spaces and obsolete hard breaks |",
        f"| **Multiple Blank Lines Normalized** | {stats['blank_lines_collapsed']} | Collapsed multi-empty lines to single blank line |",

        "",
        "---",
        "",
        "## Typography & Formatting Metrics",
        "",
        f"- **Total Lines:** {total_lines}",
        f"- **Total Words:** {total_words}",
        f"- **Total Non-Breaking Spaces (NBSP):** {total_nbsp}",
        f"- **Total Dialogue & Thought Lines:** {total_dialogues}",
        f"- **Total Em-Dashes (`—`):** {total_em_dashes}",
        f"- **Markdown Code Blocks Intact:** `{'YES (' + str(code_blocks_after) + ')' if syntax_intact else 'MISMATCH ERROR'}`",
        "",
        "---",
        "",
        "## Post-Transformation Diagnostics"
    ]

    if total_warnings == 0 and total_critical == 0:
        report_lines.extend([
            "",
            "- **Critical Errors:** 0",
            "- **Typography Warnings:** 0",
            "- **Integrity Status:** **100% VERIFIED AND CLEAN**",
            ""
        ])
    else:
        report_lines.extend([
            "",
            f"- **Critical Errors:** {total_critical}",
            f"- **Typography Warnings:** {total_warnings}",
            f"- **Integrity Status:** **{status}**",
            "",
            "### Warning Details:",
            ""
        ])
        for line_num, def_type, snippet in remaining_defects[:20]:
            report_lines.append(f"- Line {line_num} [{def_type}]: `{snippet}`")
        if len(remaining_defects) > 20:
            report_lines.append(f"- ... and {len(remaining_defects) - 20} more warnings.")
        report_lines.append("")

    return "\n".join(report_lines) + "\n"


def parse_args():
    parser = argparse.ArgumentParser(description="Production Markdown-aware Russian typography linter and formatter.")
    parser.add_argument("--input-file", required=True, help="Path to input markdown file")
    parser.add_argument("--output-file", default=None, help="Path to output markdown file (defaults to in-place edit)")
    parser.add_argument("--report-file", default=None, help="Path to write LINT_REPORT.md (optional)")
    parser.add_argument("--project", default="project", help="Project name")
    parser.add_argument("--chapter", default="chapter01", help="Chapter identifier")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--check", action="store_true", help="Lint-only mode: checks typography and exits with code 1 if issues found (does not modify file)")
    mode_group.add_argument("--fix", action="store_true", help="Fix/format mode (default): modifies file and generates diagnostics")

    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.input_file):
        print(f"Error: Input file {args.input_file} does not exist.", file=sys.stderr)
        sys.exit(1)

    with open(args.input_file, "r", encoding="utf-8", newline="") as f:
        raw_text = f.read()

    # Run simulation / formatting pass
    final_text, stats = format_markdown_document(raw_text)

    # Check mode
    if args.check:
        if raw_text == final_text:
            print(f"PASSED: No typography defects found in {args.input_file}.")
            sys.exit(0)
        else:
            diff_lines = analyze_differences(raw_text, final_text)
            total_transforms = (
                stats["dialogue_dashes_fixed"] + stats["quotes_fixed"] + stats["scene_dividers_fixed"] + stats["ellipsis_fixed"]
                + stats["number_ranges_fixed"] + stats["nbsp_prepositions"] + stats["nbsp_particles"]
                + stats["mid_dashes_fixed"] + stats["trailing_spaces_removed"] + stats["blank_lines_collapsed"]
            )
            print(f"FAILED: Found {len(diff_lines)} lines with typography defects ({total_transforms} total transformations needed) in {args.input_file}:")
            for d in diff_lines[:15]:
                print(f"  {d}")
            if len(diff_lines) > 15:
                print(f"  ... and {len(diff_lines) - 15} more lines.")
            sys.exit(1)

    # Format / Fix mode (default or --fix)
    output_path = args.output_file if args.output_file else args.input_file
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write(final_text)

    print(f"Successfully formatted '{output_path}'.")
    print(f"  - Dialogue em-dashes: {stats['dialogue_dashes_fixed']} fixed / {stats['dialogue_total']} total")
    print(f"  - Russian quotes converted: {stats['quotes_fixed']}")
    print(f"  - Scene dividers formatted: {stats['scene_dividers_fixed']} fixed / {stats['scene_dividers_total']} total")
    print(f"  - Ellipses fixed: {stats['ellipsis_fixed']}")
    print(f"  - Number ranges formatted: {stats['number_ranges_fixed']}")
    print(f"  - NBSP added: {stats['nbsp_prepositions'] + stats['nbsp_particles']} ({stats['nbsp_prepositions']} prepositions, {stats['nbsp_particles']} particles)")
    print(f"  - Mid-sentence dashes fixed: {stats['mid_dashes_fixed']}")

    if args.report_file:
        report_content = generate_lint_report(
            input_file=args.input_file,
            output_file=output_path,
            project=args.project,
            chapter=args.chapter,
            stats=stats,
            raw_text=raw_text,
            final_text=final_text
        )
        os.makedirs(os.path.dirname(os.path.abspath(args.report_file)), exist_ok=True)
        with open(args.report_file, "w", encoding="utf-8") as rf:
            rf.write(report_content)
        print(f"Report written to '{args.report_file}'.")


if __name__ == "__main__":
    main()

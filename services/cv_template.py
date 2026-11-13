"""Read the master CV as a template and rebuild it from a tailoring plan.

The LLM never writes LaTeX. It only says which entries/bullets to keep, in what order,
and how to reword them; this module puts those choices back into the master's own markup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re


SECTION = re.compile(r"\\section\*?\{([^}]*)\}")
ENTRY = re.compile(r"^\s*\\entry\{")
ITEM = re.compile(r"^(\s*)\\item\s+(.*\S)\s*$")
RIGHT_TO_WORK = re.compile(r"right to work|visa|sponsorship", re.IGNORECASE)
CVENTRY = re.compile(r"^\s*\\item\s*\{\s*\\cventry\b")  # moderncv: \item{\cventry{dates}{title}{org}{place}{}{...}}
SMALL_SUMMARY = re.compile(r"^(\s*\\small\{)(.*)(\}\s*)$")  # moderncv profile statement
HEADER_FIELD = re.compile(r"^\s*\\(name|address|phone|email)\b")
LABEL = re.compile(r"^\\textbf\{([^{}]*)\}")
# moderncv draws contact icons with a symbol font; in the PDF text they become stray letters
# ("I", "#", "MOBILE-ALT") in front of the phone number and e-mail address.
NO_CONTACT_ICONS = "".join(
    rf"\def\{name}symbol{{}}"
    for name in ("address", "mobilephone", "fixedphone", "faxphone", "email", "homepage")
)
LOCKED_SECTIONS = ("additional", "language", "reference")
COMMENT = re.compile(r"(?<!\\)%.*")
LATEX_UNESCAPES = {r"\i{}": "ı", r"\%": "%", r"\&": "&", r"\$": "$", r"\#": "#", r"\_": "_", "--": "-"}
LATEX_COMMAND_WITH_ARG = re.compile(r"\\[a-zA-Z]+\*?\{([^{}]*)\}")
LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+\*?|\\\\(\[[^\]]*\])?")


def latex_to_plain(text: str) -> str:
    for old, new in LATEX_UNESCAPES.items():
        text = text.replace(old, new)
    for _ in range(3):  # nested commands such as \textit{\textbf{x}}
        text = LATEX_COMMAND_WITH_ARG.sub(r"\1", text)
    text = LATEX_COMMAND.sub(" ", text).replace("{", " ").replace("}", " ")
    return " ".join(text.split())


def _brace_args(text: str, count: int) -> list[str]:
    """The first `count` top-level {...} groups of `text`; an unclosed last group is left out."""
    args: list[str] = []
    depth, start = 0, 0
    for index, char in enumerate(text):
        if char not in "{}" or (index and text[index - 1] == "\\"):
            continue
        if char == "{":
            if depth == 0:
                start = index + 1
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                args.append(text[start:index])
                if len(args) == count:
                    break
    return args


def _balanced_end(lines: list[str], start: int) -> int:
    """Index of the line on which the braces opened on line `start` are all closed."""
    depth = 0
    for index in range(start, len(lines)):
        text = COMMENT.sub("", lines[index])
        for position, char in enumerate(text):
            if char in "{}" and not (position and text[position - 1] == "\\"):
                depth += 1 if char == "{" else -1
        if depth <= 0:
            return index
    return len(lines) - 1


@dataclass
class Bullet:
    id: str
    text: str
    line: int


@dataclass
class Block:
    """One itemize list. Entry blocks (a job, a project) span from their \\entry to the next one."""

    id: str
    section: str
    heading: str
    droppable: bool
    editable: bool
    start: int
    end: int
    itemize: tuple[int, int] = (0, 0)
    bullets: list[Bullet] = field(default_factory=list)


@dataclass
class CvTemplate:
    lines: list[str]
    blocks: list[Block]
    summary_lines: list[int]
    header: tuple[int, int] | None
    # moderncv: the summary sits inside \small{...}; contact details are preamble commands.
    summary_wrap: tuple[str, str] | None = None
    header_fields: dict[str, int] = field(default_factory=dict)
    sections: list[tuple[str, int, int]] = field(default_factory=list)  # name, first line, last line

    @property
    def summary(self) -> str:
        if self.summary_wrap:
            return latex_to_plain(SMALL_SUMMARY.match(self.lines[self.summary_lines[0]]).group(2))
        return latex_to_plain(" ".join(self.lines[i] for i in self.summary_lines))

    @property
    def plain_text(self) -> str:
        """The CV's own words: no comments, and from the preamble only the contact lines."""
        begin = next((i for i, line in enumerate(self.lines) if r"\begin{document}" in line), -1)
        kept = [
            COMMENT.sub("", line)
            for index, line in enumerate(self.lines)
            if index > begin or index in self.header_fields.values()
        ]
        return latex_to_plain("\n".join(kept))

    def bullet(self, bullet_id: str) -> Bullet | None:
        return next((b for block in self.blocks for b in block.bullets if b.id == bullet_id), None)


def parse_cv(tex: str) -> CvTemplate:
    lines = tex.splitlines()
    blocks: list[Block] = []
    summary_lines: list[int] = []
    header_start = header = None
    section = ""
    entry_start: int | None = None
    entry_heading = ""
    entry_block: Block | None = None
    entry_end: int | None = None  # known up front for \cventry, found at the next entry for \entry
    current: Block | None = None
    bullet_count = 0
    summary_wrap: tuple[str, str] | None = None
    header_fields: dict[str, int] = {}
    section_starts: list[tuple[str, int]] = []
    in_document = False
    document_end = len(lines)

    def close_entry(end: int) -> None:
        nonlocal entry_start, entry_block, entry_end
        if entry_block is not None and entry_end is None:
            entry_block.end = end
        entry_start, entry_block, entry_end = None, None, None

    for index, line in enumerate(lines):
        stripped = line.strip()
        if header is None and stripped.startswith(r"\begin{center}"):
            header_start = index
        elif header is None and header_start is not None and stripped.startswith(r"\end{center}"):
            header = (header_start, index)

        if entry_end is not None and index > entry_end:
            close_entry(entry_end)
        if not in_document:
            field_match = HEADER_FIELD.match(line)
            if field_match:
                header_fields[field_match.group(1)] = index
            in_document = stripped.startswith(r"\begin{document}")
        small = SMALL_SUMMARY.match(line) if in_document and not section and not summary_lines else None
        if small:
            summary_lines.append(index)
            summary_wrap = (small.group(1), small.group(3))
            continue

        section_match = SECTION.search(line)
        if section_match:
            close_entry(index - 1)
            section = section_match.group(1).strip()
            section_starts.append((section, index))
            continue
        if stripped.startswith(r"\end{document}"):
            close_entry(index - 1)
            document_end = index
            continue
        if CVENTRY.match(line):
            close_entry(index - 1)
            entry_start = index
            dates, title, organisation, place = (_brace_args(line.split(r"\cventry", 1)[1], 4) + [""] * 4)[:4]
            entry_heading = " | ".join(part for part in (title, organisation, place, dates) if part.strip())
            entry_end = _balanced_end(lines, index)
            # The spacer between two entries goes with the entry above it.
            while entry_end + 1 < len(lines) and (
                not lines[entry_end + 1].strip() or lines[entry_end + 1].strip().startswith(r"\vspace")
            ):
                entry_end += 1
            continue
        if ENTRY.match(line):
            close_entry(index - 1)
            entry_start = index
            following = lines[index + 1] if index + 1 < len(lines) else ""
            entry_heading = " | ".join(
                part for part in re.findall(r"\{([^{}]*)\}", line + following) if part.strip()
            )
            continue

        if stripped.startswith(r"\begin{itemize}"):
            in_entry = entry_start is not None and entry_block is None
            current = Block(
                id=f"{'e' if in_entry else 's'}{len(blocks) + 1}",
                section=section,
                heading=latex_to_plain(entry_heading) if in_entry else section,
                droppable=in_entry and "education" not in section.casefold(),
                editable=not any(word in section.casefold() for word in LOCKED_SECTIONS),
                start=entry_start if in_entry else index,
                end=entry_end if in_entry and entry_end is not None else index,
                itemize=(index, index),
            )
            blocks.append(current)
            if in_entry:
                entry_block = current
            continue
        if stripped.startswith(r"\end{itemize}") and current is not None:
            current.itemize = (current.itemize[0], index)
            if entry_block is not current:
                current.end = index
            current = None
            continue

        item = ITEM.match(line) if current is not None else None
        if item:
            bullet_count += 1
            current.bullets.append(Bullet(f"b{bullet_count}", latex_to_plain(item.group(2)), index))
        elif "summary" in section.casefold() and stripped and not stripped.startswith("\\"):
            summary_lines.append(index)

    sections = [
        (name, start, (section_starts[i + 1][1] if i + 1 < len(section_starts) else document_end) - 1)
        for i, (name, start) in enumerate(section_starts)
    ]
    return CvTemplate(
        lines=lines,
        blocks=[block for block in blocks if block.bullets],  # moderncv wraps entries in a bullet-less itemize
        summary_lines=summary_lines,
        header=header,
        summary_wrap=summary_wrap,
        header_fields=header_fields,
        sections=sections,
    )


def _item_text(template: CvTemplate, original: Bullet | None, text: str, escape) -> str:
    """Escaped bullet text; a leading \\textbf{Label} of the original bullet stays bold."""
    if original is not None:
        label = LABEL.match(ITEM.match(template.lines[original.line]).group(2))
        plain = latex_to_plain(label.group(0)) if label else ""
        if plain and text.startswith(plain):
            return rf"\textbf{{{escape(plain)}}}{escape(text[len(plain):])}"
    return escape(text)


def render_header(contact: dict[str, str], escape) -> list[str]:
    parts = [contact.get(key, "") for key in ("address", "phone", "email", "linkedin")]
    details = r" \textbar \quad ".join(escape(part) for part in parts if part)
    return [
        r"\begin{center}",
        rf"    {{\Large \textbf{{{escape(contact.get('name', ''))}}}}} \\[0.2cm]",
        f"    {details}",
        r"\end{center}",
    ]


def render_cv(
    template: CvTemplate,
    *,
    summary: str | None,
    block_plans: dict[str, tuple[bool, list[tuple[str, str]]]],
    contact: dict[str, str],
    escape,
) -> str:
    """block_plans: block id -> (keep, [(bullet id, final plain text)]). Missing blocks stay as they are."""
    lines: list[str | None] = list(template.lines)

    if template.header and contact.get("name"):
        start, end = template.header
        lines[start] = "\n".join(render_header(contact, escape))
        for index in range(start + 1, end + 1):
            lines[index] = None

    for name, index in template.header_fields.items():
        value = contact.get(name, "")
        if not value:
            continue
        if name == "name":
            first_name, _, last_name = value.rpartition(" ")
            lines[index] = rf"\name{{{escape(first_name)}}}{{{escape(last_name)}}}"
        elif name == "address":
            lines[index] = rf"\address{{{escape(value)}}}{{}}{{}}"
        else:  # \phone[mobile]{...}, \email{...}: keep the command and its option
            command = template.lines[index][: template.lines[index].index("{")]
            lines[index] = f"{command}{{{escape(value)}}}"

    if template.header_fields:
        begin = next(i for i, line in enumerate(template.lines) if line.strip().startswith(r"\begin{document}"))
        lines[begin] = f"{NO_CONTACT_ICONS}\n{template.lines[begin]}"

    if summary and template.summary_lines:
        first, *rest = template.summary_lines
        prefix, suffix = template.summary_wrap or ("", "")
        lines[first] = f"{prefix}{escape(summary)}{suffix}"
        for index in rest:
            lines[index] = None

    dropped: set[str] = set()
    for block in template.blocks:
        keep, chosen = block_plans.get(block.id, (True, []))
        if not keep and block.droppable:
            dropped.add(block.id)
            for index in range(block.start, block.end + 1):
                lines[index] = None
            continue
        if not chosen:
            continue
        slots = [bullet.line for bullet in block.bullets]
        indent = ITEM.match(template.lines[slots[0]]).group(1)
        for slot, (bullet_id, text) in zip(slots, chosen):
            original = template.bullet(bullet_id)
            same = original is not None and original.text == text
            lines[slot] = template.lines[original.line] if same else f"{indent}\\item {_item_text(template, original, text, escape)}"
        for slot in slots[len(chosen):]:
            lines[slot] = None

    right_to_work = contact.get("right_to_work", "")
    for block in template.blocks:
        for bullet in block.bullets:
            if lines[bullet.line] is not None and RIGHT_TO_WORK.search(bullet.text):
                indent = ITEM.match(template.lines[bullet.line]).group(1)
                lines[bullet.line] = f"{indent}\\item {escape(right_to_work)}" if right_to_work else None

    for block in template.blocks:
        if block.bullets and all(lines[bullet.line] is None for bullet in block.bullets):
            begin, close = block.itemize
            lines[begin] = lines[close] = None  # an empty itemize does not compile

    # A section whose every entry was dropped or every bullet removed goes with its heading.
    for name, start, end in template.sections:
        members = [block for block in template.blocks if start <= block.start <= end]
        if members and all(
            block.id in dropped or all(lines[bullet.line] is None for bullet in block.bullets)
            for block in members
        ):
            for index in range(start, end + 1):
                lines[index] = None

    return "\n".join(line for line in lines if line is not None) + "\n"

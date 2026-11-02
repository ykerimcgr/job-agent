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
LATEX_UNESCAPES = {r"\%": "%", r"\&": "&", r"\$": "$", r"\#": "#", r"\_": "_", "--": "-"}
LATEX_COMMAND_WITH_ARG = re.compile(r"\\[a-zA-Z]+\*?\{([^{}]*)\}")
LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+\*?|\\\\(\[[^\]]*\])?")


def latex_to_plain(text: str) -> str:
    for old, new in LATEX_UNESCAPES.items():
        text = text.replace(old, new)
    for _ in range(3):  # nested commands such as \textit{\textbf{x}}
        text = LATEX_COMMAND_WITH_ARG.sub(r"\1", text)
    text = LATEX_COMMAND.sub(" ", text).replace("{", " ").replace("}", " ")
    return " ".join(text.split())


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

    @property
    def summary(self) -> str:
        return latex_to_plain(" ".join(self.lines[i] for i in self.summary_lines))

    @property
    def plain_text(self) -> str:
        return latex_to_plain("\n".join(self.lines))

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
    current: Block | None = None
    bullet_count = 0

    def close_entry(end: int) -> None:
        nonlocal entry_start, entry_block
        if entry_block is not None:
            entry_block.end = end
        entry_start, entry_block = None, None

    for index, line in enumerate(lines):
        stripped = line.strip()
        if header is None and stripped.startswith(r"\begin{center}"):
            header_start = index
        elif header is None and header_start is not None and stripped.startswith(r"\end{center}"):
            header = (header_start, index)

        section_match = SECTION.search(line)
        if section_match:
            close_entry(index - 1)
            section = section_match.group(1).strip()
            continue
        if stripped.startswith(r"\end{document}"):
            close_entry(index - 1)
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
                editable="additional" not in section.casefold(),
                start=entry_start if in_entry else index,
                end=index,
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

    return CvTemplate(lines=lines, blocks=blocks, summary_lines=summary_lines, header=header)


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

    if summary and template.summary_lines:
        first, *rest = template.summary_lines
        lines[first] = escape(summary)
        for index in rest:
            lines[index] = None

    for block in template.blocks:
        keep, chosen = block_plans.get(block.id, (True, []))
        if not keep and block.droppable:
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
            lines[slot] = template.lines[original.line] if same else f"{indent}\\item {escape(text)}"
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

    return "\n".join(line for line in lines if line is not None) + "\n"

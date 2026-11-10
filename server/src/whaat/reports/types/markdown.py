import re

from whaat.reports.schemas import ReportBody, ReportSection

HEADING = re.compile(r"^(#{2,6})\s+(.*)$")
PIN = re.compile(r"^-\s+(.*)$")


def parse_markdown(text: str) -> ReportBody:
    title = ""
    pins: list[str] = []
    sections: list[ReportSection] = []
    current: tuple[int, str] | None = None
    lines: list[str] = []
    in_fence = False

    def close_section() -> None:
        if current is not None:
            sections.append(ReportSection(level=current[0], heading=current[1], markdown="\n".join(lines).strip()))

    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        heading = None if in_fence else HEADING.match(line)
        if not in_fence and not title and line.startswith("# "):
            title = line[2:].strip()
        elif heading:
            close_section()
            current = (len(heading.group(1)), heading.group(2).strip())
            lines = []
        elif current is None:
            pin = PIN.match(line)
            if title and pin:
                pins.append(pin.group(1).strip())
        else:
            lines.append(line)
    close_section()
    return ReportBody(title=title, pins=pins, sections=sections)

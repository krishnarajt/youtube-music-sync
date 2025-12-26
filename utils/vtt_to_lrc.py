import re
from pathlib import Path

TIMESTAMP_RE = re.compile(r"(\d+):(\d+):(\d+\.\d+)")


def vtt_to_lrc(vtt_path: Path, lrc_path: Path):
    with vtt_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    lrc_lines = []

    for i, line in enumerate(lines):
        if "-->" in line:
            start = line.split("-->")[0].strip()
            h, m, s = start.replace(",", ".").split(":")
            timestamp = f"[{int(m):02d}:{float(s):05.2f}]"

            text = lines[i + 1].strip()
            if text:
                lrc_lines.append(f"{timestamp}{text}")

    lrc_path.write_text("\n".join(lrc_lines), encoding="utf-8")

"""Write every result we have as plain text, one file per search.

The searches leave their findings in JSON and in log files that are awkward to
read and easy to lose track of. This puts each in results/ as a ranked list,
so a run's output survives the run and can be compared with the next one.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "results")


def write(name, header, lines):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(header.rstrip() + "\n#\n")
        handle.write("\n".join(lines) + "\n")
    print(f"  {len(lines):>6,} rows -> results/{name}")


def main() -> int:
    for path in sorted(glob.glob(os.path.join(HERE, "out", "judged*.json"))):
        rows = json.load(open(path))
        if not rows or "text" not in rows[0]:
            continue
        name = os.path.basename(path).replace(".json", ".txt")
        lines = []
        for r in rows:
            score = r.get("score", r.get("probability", 0.0))
            lines.append(f"{score:>8.3f} {r.get('acceptability', 0):>6.3f} "
                         f"{r['text']:<46} "
                         f"{'/'.join(x.upper() for x in r['rows'])}")
        write(name,
              f"# {os.path.basename(path)}: {len(rows):,} candidates, ranked\n"
              f"# score  accept  text  rows\n"
              f"# The score ranks; it does not decide. The model returns 1.000\n"
              f"# for HALL A, HALL A, HALL AH.",
              lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())

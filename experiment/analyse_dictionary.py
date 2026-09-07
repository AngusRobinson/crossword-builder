"""Read experiment/dictionary.jsonl and report the dictionary comparison.

Completion is the headline, because completion is what was stuck. Coverage is
reported beside it and is comparable: the ceiling a run is measured against
comes from the pattern and the target list, never from the dictionary, so the
same pair scores against the same denominator under both. This is checked --
no pair in the results has a ceiling that moves.

Pairs are matched on (list, seed), so every comparison is like for like, and a
pair is dropped unless both dictionaries ran it.

    python3 experiment/analyse_dictionary.py
"""

import argparse
import collections
import json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="experiment/dictionary.jsonl")
    args = parser.parse_args()

    rows = [json.loads(line) for line in open(args.path)]
    by_key = {}
    unserved = collections.defaultdict(set)
    for row in rows:
        if row.get("ok") is None:
            unserved[row["dictionary"]].add(row["style"])
            continue
        by_key[(row["list"], row["seed"], row["dictionary"])] = row

    names = sorted({key[2] for key in by_key})
    pairs = collections.defaultdict(list)
    for (list_id, seed, dictionary), row in by_key.items():
        if all((list_id, seed, other) in by_key for other in names):
            pairs[row["style"]].append((list_id, seed))
    for style in pairs:
        pairs[style] = sorted(set(pairs[style]))

    print(f"{len(by_key)} runs, {sum(len(v) for v in pairs.values())} "
          f"complete pairs\n")

    header = f"{'style':<9} {'n':>3}"
    for name in names:
        header += f" {name + ' fills':>16} {name + ' cover':>15}"
    print(header)
    print("-" * len(header))

    totals = collections.defaultdict(lambda: [0, 0, 0.0, 0])
    for style in sorted(pairs):
        keys = pairs[style]
        line = f"{style:<9} {len(keys):>3}"
        for name in names:
            got = [by_key[(k[0], k[1], name)] for k in keys]
            filled = sum(1 for r in got if r["ok"])
            cover = [r["seated"] / r["ceiling"] for r in got if r["ceiling"]]
            mean = sum(cover) / len(cover) if cover else 0.0
            line += f" {filled:>7}/{len(got):<3} {filled/len(got):>4.0%}"
            line += f" {mean:>14.3f}"
            totals[name][0] += filled
            totals[name][1] += len(got)
            totals[name][2] += sum(cover)
            totals[name][3] += len(cover)
        print(line)

    line = f"{'all':<9} {sum(len(v) for v in pairs.values()):>3}"
    for name in names:
        filled, n, cover, m = totals[name]
        line += f" {filled:>7}/{n:<3} {filled/n:>4.0%}" if n else " " * 16
        line += f" {cover/m:>14.3f}" if m else " " * 15
    print("-" * len(header))
    print(line)

    for name in sorted(unserved):
        print(f"\n{name} cannot serve: {', '.join(sorted(unserved[name]))}")

    # Per-list detail for the style that motivated this, so a swing can be
    # traced to the grids it came from rather than taken on trust.
    for style in sorted(pairs):
        flips = []
        for key in pairs[style]:
            got = {n: by_key[(key[0], key[1], n)] for n in names}
            states = {n: got[n]["ok"] for n in names}
            if len(set(states.values())) > 1:
                flips.append((key[0], states))
        if flips:
            print(f"\n{style}: {len(flips)} lists where the dictionaries "
                  f"disagree")
            for list_id, states in flips:
                shown = "  ".join(
                    f"{n}={'fills' if states[n] else 'fails'}" for n in names)
                print(f"    {list_id:<14} {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

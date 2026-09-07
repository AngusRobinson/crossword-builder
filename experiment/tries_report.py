"""Read experiment/tries.jsonl: one budget, spent as N searches of T/N."""
import json, os, statistics as s, sys
if os.path.basename(os.getcwd()) == "experiment":
    os.chdir("..")

def reached(curve, seconds, ceiling):
    best = 0
    for moment, seated, ok, _q in curve:
        if moment <= seconds and ok:
            best = max(best, seated)
    return best / ceiling if ceiling else 0.0

rows = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1
                                    else "experiment/tries.jsonl")]
by = {}
for r in rows:
    by.setdefault((r["style"], r["list"]), []).append(r)
total = max(m for r in rows for m, *_ in (r["curve"] or [[0]]))
TOTAL = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
seeds = max(len(v) for v in by.values())

print(f"One budget of {TOTAL:.0f}s, split N ways. Best of N runs of {TOTAL:.0f}/N.\n")
print(f"{'style':10}" + "".join(f"{'x' + str(n):>10}" for n in (1, 2, 3, 5, 8)))
for style in ("british", "barred", "jumbo", "us"):
    line = ""
    for n in (1, 2, 3, 5, 8):
        if n > seeds:
            line += f"{'-':>10}"; continue
        got = []
        for (st, _lst), runs in by.items():
            if st != style:
                continue
            slice_ = TOTAL / n
            got.append(max(reached(r["curve"], slice_, r["ceiling"])
                           for r in runs[:n]))
        line += f"{s.mean(got):>10.3f}" if got else f"{'-':>10}"
    print(f"{style:10}" + line)
print("\n(x1 = one search of the whole budget; x8 = best of eight short ones)")

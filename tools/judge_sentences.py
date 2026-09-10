"""Rank candidate squares by whether a grammar model accepts them.

Every ranking before this one was a rule I wrote, and both rules failed the
same way: part-of-speech bigrams and language-model perplexity each reward a
predictable string of short words. BE WE RE HE RE WE RE WE RE HERE WEB
outscored real sentences under both, and perplexity ranked A MAN A PLAN A
CANAL PANAMA below gibberish, predictability being what perplexity measures.

This asks a model trained on the question instead. CoLA -- the Corpus of
Linguistic Acceptability -- is a set of sentences labelled by linguists as
acceptable or not, and a RoBERTa fine-tuned on it returns P(acceptable). On
the cases above it agrees with a reader: A MAN, A PLAN, A CANAL, PANAMA scores
0.999 and BE WE RE ... 0.001.

**Punctuation has to be searched, not assumed.** JAMES WATCH GREEN WATER SLYLY
scores 0.001 and JAMES, WATCH GREEN WATER SLYLY scores 1.000 -- the same words.
A square carries no punctuation, so every placement of a comma or two is tried
and the best kept, which is what a reader does anyway.

**It saturates on this distribution, and that is the thing to know.** On a
dozen hand-picked examples it looks decisive. Run over the 31,786 exhaustive
4x4 squares it returns 1.000 for HALL A, HALL A, HALL AH and for LAL A A LAL,
LAL A A LAL. CoLA marks *acceptability*, and a bare noun phrase is acceptable;
it was never asked whether a string is a sentence. XQZ VBN PLK MNB scores
0.998 for the same reason -- unfamiliar words read as nouns, and a run of
nouns is fine.

Nor does adding GPT-2 fix it by itself, though it was worth trying: it removes
what acceptability waves through in one direction and adds its own in the
other. Both models reward repetition, and a palindromic square repeats by
construction, so the score carries a variety term -- distinct words over total
-- that neither model supplies. Without it the best of nine hundred thousand
5x5 squares was I OH CHOI, OH CHOI OH CHOI OH CHOI.

So this ranks but does not decide, which is what every ranking here has come
to. Use it with --content to force real words in, take the shortlist, and read
it. A judge that separated a sentence from a noun phrase would want a model
asked that question rather than this one; the honest state is that we do not
have one.

Needs torch and transformers, which the runtime does not: this ranks results
that are already found.

    python3 tools/judge_sentences.py out/step2-4.json --top 20
"""

import argparse
import itertools
import json
import os
import sys


def load_model(name):
    for var in ("HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE"):
        os.environ.setdefault(var, os.path.join(
            os.environ.get("TMPDIR", "/tmp"), "hf"))
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tokeniser = AutoTokenizer.from_pretrained(name)
    model = AutoModelForSequenceClassification.from_pretrained(name)
    model.eval()
    return torch, tokeniser, model


def dress(words, commas=()):
    out = [w + ("," if i + 1 in commas else "") for i, w in enumerate(words)]
    text = " ".join(out)
    return text[0].upper() + text[1:] + "."


def placements(words, most=2):
    for count in range(most + 1):
        for where in itertools.combinations(range(1, len(words)), count):
            yield where


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("grids", help="JSON list of squares, as rows")
    parser.add_argument("--model", default="JeremiahZ/roberta-base-cola")
    parser.add_argument("--no-gpt2", action="store_true",
                        help="skip the second model. Its job is to catch what "
                             "CoLA waves through: a repetitive run of short "
                             "words scores 1.000 on acceptability and badly "
                             "on how much context helps predict it")
    parser.add_argument("--per-family", type=int, default=2,
                        help="squares sharing their outer rows differ only in "
                             "the middle and read alike; 98%% of them have a "
                             "twin, so a shortlist ranked purely by score is "
                             "one idea repeated. This caps each family")
    parser.add_argument("--floor", type=float, default=4.0)
    parser.add_argument("--dictionary", default="english-names.txt")
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--shortlist", type=int, default=400,
                        help="how many survive the unpunctuated pass and get "
                             "every comma placement tried")
    parser.add_argument("--content", type=int, default=0,
                        help="require this many words of four letters or "
                             "more. The model accepts a run of single letters "
                             "and unfamiliar short words as a noun phrase, so "
                             "without this it returns 1.000 for LAL A A LAL")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from crossword import frequency
    from crossword.words import load
    from squares.segmented import vocabulary, split

    scores = frequency.load_scores(
        os.path.splitext(args.dictionary)[0] + "-scores.txt")
    entries = load(args.dictionary, min_length=3, max_length=7,
                   allow_phrases=False, allow_proper=True, strict=False)
    by_length = vocabulary(entries, scores, floor=args.floor)
    by_length[1] = {"a", "i"}

    grids = json.load(open(args.grids))
    texts, keep = [], []
    for rows in grids:
        reading = split("".join(rows), by_length, 1)
        if not reading:
            continue
        if sum(1 for w in reading[0] if len(w) >= 4) < args.content:
            continue
        keep.append(rows)
        texts.append(reading[0])
    print(f"{len(keep):,} of {len(grids):,} squares split into words",
          file=sys.stderr, flush=True)

    # Squares sharing their first and last row are near-duplicates. Keeping a
    # couple of each stops one prolific family filling the shortlist.
    if args.per_family:
        import collections
        seen = collections.Counter()
        kept_rows, kept_texts = [], []
        for rows, text in zip(keep, texts):
            family = (rows[0], rows[-1])
            if seen[family] >= args.per_family:
                continue
            seen[family] += 1
            kept_rows.append(rows)
            kept_texts.append(text)
        print(f"{len(kept_rows):,} after keeping {args.per_family} per family "
              f"({len(seen):,} families)", file=sys.stderr, flush=True)
        keep, texts = kept_rows, kept_texts

    torch, tokeniser, model = load_model(args.model)
    gpt = None
    if not args.no_gpt2:
        from transformers import GPT2LMHeadModel, GPT2TokenizerFast
        gpt_tok = GPT2TokenizerFast.from_pretrained("gpt2")
        gpt_model = GPT2LMHeadModel.from_pretrained("gpt2")
        gpt_model.eval()

        def gpt(text):
            """How much the context helps over word frequency alone.

            Low for a repetitive run of short words, which is exactly what
            acceptability alone cannot see.
            """
            ids = gpt_tok(text, return_tensors="pt").input_ids
            if ids.shape[1] < 2:
                return 0.0
            with torch.no_grad():
                logits = gpt_model(ids).logits[0, :-1]
                target = ids[0, 1:]
                given = torch.log_softmax(logits, -1)[
                    torch.arange(len(target)), target]
                alone = torch.log_softmax(
                    gpt_model(ids[:, :1]).logits[0, -1], -1)[target]
            return (given - alone).mean().item()

    def judge(strings):
        out = []
        for start in range(0, len(strings), args.batch):
            chunk = strings[start:start + args.batch]
            ids = tokeniser(chunk, return_tensors="pt", padding=True,
                            truncation=True)
            with torch.no_grad():
                probs = torch.softmax(model(**ids).logits, -1)[:, 1]
            out += probs.tolist()
            if start % (args.batch * 40) == 0:
                print(f"   {start:,}/{len(strings):,}", file=sys.stderr,
                      flush=True)
        return out

    # One pass unpunctuated to shortlist, then every comma placement on those.
    first = judge([dress(w) for w in texts])
    order = sorted(range(len(texts)), key=lambda i: -first[i])
    short = order[:args.shortlist]
    print(f"shortlisted {len(short)}; trying comma placements",
          file=sys.stderr, flush=True)

    best = []
    for i in short:
        variants = [dress(texts[i], w) for w in placements(texts[i])]
        accept = judge(variants)
        pick = max(range(len(variants)), key=lambda k: accept[k])
        text, probability = variants[pick], accept[pick]
        lift = gpt(text) if gpt else 1.0
        # Both models reward repetition, and a palindromic square is
        # repetitive by construction. Acceptability sees a noun phrase and
        # says yes; the lift is *highest* for a repeated run, context being
        # most helpful exactly where the text repeats -- I OH CHOI OH CHOI OH
        # CHOI scored 5.61, the best in a field of nine hundred thousand.
        # Distinct words over total is the term neither model supplies.
        plain = [w.strip(",.?!").lower() for w in text.split()]
        variety = len(set(plain)) / len(plain)
        best.append((probability * variety * variety, probability, variety,
                     lift, text, keep[i]))
    best.sort(reverse=True)

    if args.out:
        json.dump([{"score": s, "acceptability": p, "variety": v, "lift": l,
                    "text": t, "rows": r} for s, p, v, l, t, r in best],
                  open(args.out, "w"), indent=1)
        print(f"wrote {args.out}", file=sys.stderr)
    print(f"{'score':>6} {'ok':>6} {'var':>5} {'lift':>6}  text")
    for score, probability, variety, lift, text, rows in best[:args.top]:
        print(f"{score:>6.2f} {probability:>6.3f} {variety:>5.2f} "
              f"{lift:>6.2f}  {text:<40} "
              f"[{'/'.join(x.upper() for x in rows)}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())

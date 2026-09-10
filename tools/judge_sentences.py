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


def dress(words, commas=(), stops=(), final="."):
    """The reading as a sentence, with breaks where asked for.

    Commas alone cannot express the best thing these searches have found --
    "Tide, I did. Did I edit?" needs a full stop and a question mark -- so a
    break may be either, and the closing mark varies too.
    """
    out = []
    for i, word in enumerate(words):
        if word == "i":
            word = "I"
        mark = ""
        if i + 1 in stops:
            mark = "."
        elif i + 1 in commas:
            mark = ","
        out.append(word + mark)
    text = " ".join(out)
    # capitalise the start, and whatever follows a full stop
    letters, upper = list(text), True
    for i, ch in enumerate(letters):
        if upper and ch.isalpha():
            letters[i] = ch.upper()
            upper = False
        elif ch == ".":
            upper = True
    return "".join(letters) + final


def punctuations(words, most=2, full=True):
    """Ways of pointing the reading: commas, one full stop, . or ?"""
    slots = range(1, len(words))
    seen = set()
    for count in range(most + 1):
        for commas in itertools.combinations(slots, count):
            for stop in ((None,) if not full else (None,) + tuple(slots)):
                if stop in commas:
                    continue
                stops = () if stop is None else (stop,)
                for final in (".", "?"):
                    text = dress(words, commas, stops, final)
                    if text not in seen:
                        seen.add(text)
                        yield text


def cheap(words, most=1):
    """A handful of pointings, for the pass that shortlists."""
    out = [dress(words), dress(words, final="?")]
    middle = len(words) // 2
    if len(words) > 2:
        out.append(dress(words, commas=(middle,)))
        out.append(dress(words, stops=(middle,), final="?"))
    return out


def readings(text, by_length, vocab, want, limit=40):
    """Every way the text splits, best first by how much substance it carries.

    Taking one reading was taking the shortest-first one: NOTABLE splits as
    NO TABLE and never as NOT ABLE, and 69% of candidates have more than one
    reading, so the square was being judged on an arbitrary choice among them.
    """
    found = []

    def walk(at, parts):
        if len(found) >= limit:
            return
        if at == len(text):
            found.append(list(parts))
            return
        for take in range(1, min(7, len(text) - at) + 1):
            piece = text[at:at + take]
            if piece in by_length.get(take, ()):
                parts.append(piece)
                walk(at + take, parts)
                parts.pop()

    walk(0, [])
    keep = [p for p in found if sum(1 for w in p if len(w) >= 4) >= want]
    keep.sort(key=lambda p: (-sum(1 for w in p if len(w) >= 4), len(p)))
    return keep


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
    parser.add_argument("--readings", type=int, default=4,
                        help="how many readings of each square to judge. One "
                             "was the shortest-first reading: NOTABLE splits "
                             "as NO TABLE and never NOT ABLE")
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
    vocab = {w for ws in by_length.values() for w in ws}
    kept = []
    for rows in grids:
        options = readings("".join(rows), by_length, vocab, args.content)
        if options:
            kept.append((rows, options[:args.readings]))
    print(f"{len(kept):,} of {len(grids):,} squares have a reading carrying "
          f"{args.content} real words", file=sys.stderr, flush=True)

    torch, tokeniser, model = load_model(args.model)
    gpt = None
    if not args.no_gpt2:
        from transformers import GPT2LMHeadModel, GPT2TokenizerFast
        gpt_tok = GPT2TokenizerFast.from_pretrained("gpt2")
        gpt_model = GPT2LMHeadModel.from_pretrained("gpt2")
        gpt_model.eval()

        def gpt(text):
            """How much context helps over word frequency alone.

            Highest where a text repeats, context being most helpful exactly
            there, which is why it cannot be the whole score.
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
            if start and start % (args.batch * 200) == 0:
                print(f"   {start:,}/{len(strings):,}", file=sys.stderr,
                      flush=True)
        return out

    def variety(text):
        plain = [w.strip(",.?!").lower() for w in text.split()]
        return len(set(plain)) / len(plain)

    # Shortlisting on unpunctuated text discarded whatever punctuation
    # rescues, and this project's own example moves 0.001 -> 1.000 on one
    # comma. So a few pointings are tried before the shortlist, not after.
    trial, owner = [], []
    for index, (rows, options) in enumerate(kept):
        for words in options:
            for text in cheap(words):
                trial.append(text)
                owner.append(index)
    print(f"scoring {len(trial):,} pointings to shortlist",
          file=sys.stderr, flush=True)
    first = judge(trial)
    rough = {}
    for score, index, text in zip(first, owner, trial):
        value = score * variety(text) ** 2
        if index not in rough or value > rough[index]:
            rough[index] = value
    short = sorted(rough, key=lambda i: -rough[i])[:args.shortlist]
    print(f"shortlisted {len(short)}; every pointing of every reading",
          file=sys.stderr, flush=True)

    best = []
    for index in short:
        rows, options = kept[index]
        pool = [t for words in options for t in punctuations(words)]
        got = judge(pool)
        top = max(range(len(pool)), key=lambda k: got[k] * variety(pool[k]) ** 2)
        text, probability = pool[top], got[top]
        lift = gpt(text) if gpt else 1.0
        v = variety(text)
        best.append((probability * v * v, probability, v, lift, text, rows))
    best.sort(reverse=True)

    # The family cap belongs here, not before scoring: applied first it kept
    # whichever members the search happened to reach, and a different middle
    # row is a different sentence.
    if args.per_family:
        import collections
        seen, trimmed = collections.Counter(), []
        for row in best:
            family = (row[5][0], row[5][-1])
            if seen[family] >= args.per_family:
                continue
            seen[family] += 1
            trimmed.append(row)
        print(f"{len(trimmed)} shown, {args.per_family} per family",
              file=sys.stderr)
        best = trimmed

    if args.out:
        json.dump([{"score": a, "acceptability": b, "variety": c, "lift": d,
                    "text": e, "rows": f} for a, b, c, d, e, f in best],
                  open(args.out, "w"), indent=1)
        print(f"wrote {args.out}", file=sys.stderr)
    print(f"{'score':>6} {'ok':>6} {'var':>5} {'lift':>6}  text")
    for score, probability, v, lift, text, rows in best[:args.top]:
        print(f"{score:>6.2f} {probability:>6.3f} {v:>5.2f} {lift:>6.2f}  "
              f"{text:<44} [{'/'.join(x.upper() for x in rows)}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build gpab_assessment/spell_freq_en.json — the word-frequency table
spellcheck.py ranks its suggestions with.

One-off, not a runtime dependency: wordfreq (~60 MB, all languages) is only
needed here, so run this from a throwaway venv rather than adding it to the
app's own:

    python3 -m venv --system-site-packages /tmp/wf && /tmp/wf/bin/pip install wordfreq
    /tmp/wf/bin/python scripts/build_spell_freq.py

Keeps the most common English words that the en_AU hunspell dictionary also
accepts (so US spellings like "behavior" never become suggestions), each
with its Zipf frequency (log10 of uses per billion words; ~7 for "the",
~3 for "sensation", 1 decimal place).
"""

import json
from pathlib import Path

import enchant
import wordfreq

TOP_N = 60000
OUT = Path(__file__).resolve().parent.parent / "gpab_assessment" / "spell_freq_en.json"


def main() -> None:
    d = enchant.Dict("en_AU")
    table = {}
    for w in wordfreq.top_n_list("en", TOP_N):
        if not all(c.isalpha() or c == "'" for c in w) or not d.check(w):
            continue
        table[w] = round(wordfreq.zipf_frequency(w, "en"), 1)
    OUT.write_text(json.dumps(table, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"{len(table)} words -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

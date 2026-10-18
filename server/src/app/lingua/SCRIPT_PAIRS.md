# Conservative character pairs

`script_pairs.json` is derived from OpenCC 1.4.2 STCharacters and TSCharacters dictionaries (https://github.com/BYVoid/OpenCC), licensed under Apache-2.0. OpenCC copyright © 2010–2026 BYVoid and contributors. This derived table excludes every multi-value conversion and any simplified character with multiple traditional predecessors. It intentionally rejects some linguistically valid alternatives rather than silently accepting meaning-changing conversions.

To regenerate, use OpenCC's `opencc_dict -f ocd2 -t text` on both dictionaries. Retain S→T only when S and T are single codepoints, S≠T, ST[S] is exactly T, TS[T] is exactly S, and T is the only predecessor of S in TS. Sort by S and serialize as UTF-8 JSON. No network or dictionary executable is needed at runtime.

A sentence supplies only its own permitted pairs to the browser. Feedback retains source spelling. This policy tests transcription, not semantic understanding or regional vocabulary equivalence.

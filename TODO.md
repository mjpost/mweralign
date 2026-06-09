- [X] Need to apply a segmenter so that it works seamlessly for any language, including CJK
 Maybe just do everything at the byte level? No that won't work
 Would also need then to make sure that you didn't split a token across lines

- [ ] Need to add special processing / weights to ensure that punctuation doesn't start a line.
This might fit with the above in some kind of general procedure where you accomplish this with weights.
Sounds hard.
  - Partially addressed: for SentencePiece input the aligner now forbids mid-word
    segment boundaries (no segment begins on a word-internal piece), which keeps
    word fragments from starting a line. Pure punctuation is still allowed to
    start a line (it is exempted from the constraint), so the punctuation case
    above is not yet handled.

- [X] Add docids
If docids are provided parallel to the reference, then, under the assumption that hypotheses are one doc
per line, you could limit search size by constraining search within documents.
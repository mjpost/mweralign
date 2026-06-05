- [X] Need to apply a segmenter so that it works seamlessly for any language, including CJK
 Maybe just do everything at the byte level? No that won't work
 Would also need then to make sure that you didn't split a token across lines

- [ ] Need to add special processing / weights to ensure that punctuation doesn't start a line.
This might fit with the above in some kind of general procedure where you accomplish this with weights.
Sounds hard.

- [X] Add docids
If docids are provided parallel to the reference, then, under the assumption that hypotheses are one doc
per line, you could limit search size by constraining search within documents.
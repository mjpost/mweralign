#!/usr/bin/env python3

"""
Take in a TSV stream on STDIN and report stats on the number of times the second column differs from the first.
"""

import difflib
import sys

def main(args):
    lines_correct, num_total = 0, 0
    chars_correct, chars_total = 0, 0
    for lineno, line in enumerate(sys.stdin, 1):
        fields = line.rstrip().split("\t")


        if len(fields) != 2:
            lines_correct += 1

        if len(fields) == 2:
            matcher = difflib.SequenceMatcher(None, fields[0], fields[1])
            match = matcher.find_longest_match(0, len(fields[0]), 0, len(fields[1]))
            num_matched_non_ws = sum(1 for c in fields[1][match.b:match.b + match.size] if not c.isspace())
            chars_correct += num_matched_non_ws
            num_non_ws = sum(1 for c in fields[1] if not c.isspace())
            chars_total += num_non_ws

        if len(fields) == 2 and fields[0] == fields[1]:
            lines_correct += 1
        else:
            if args.verbose:
                print(f"* {lineno} BAD LINE\n-> {fields[0]}\n-> {fields[1]}", file=sys.stderr)
        num_total += 1

    # print(f"{num_diff} / {num_total} = {100 * num_diff / num_total:.1f}%")
    # print(f"{chars_correct} / {chars_total} = {100 * chars_correct / chars_total:.1f}%")
    print(f"{100 * lines_correct / num_total:.1f} {100 * chars_correct / chars_total:.1f}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Take in a TSV stream on STDIN and report stats on the number of times the second column differs from the first.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print each line that differs")
    args = parser.parse_args()

    main(args)
# -*- coding: utf-8 -*-
"""Tell the player why Gallon's Photon service isn't showing.

The shop silently drops menu entries when the player hasn't unlocked them --
no explanation, just a shorter list -- so someone who has heard the shop sells
percentages concludes it is broken. This adds a line from Gallon pointing at
the Tower quests that set the flags.

Runs on the same --reassembly disassembly as patch_hit.py, and after it:

    newserv disassemble-quest-script --bb --reassembly --language=L IN.bin IN.txt
    python3 patch_hint.py IN.txt OUT.txt
    newserv assemble-quest-script OUT.txt OUT.bin

Nothing is unlocked and no flag is written -- this is dialogue only.
"""
import io
import re
import sys

FACE = "0x000000A5"  # Gallon's message-box portrait, as used elsewhere in the quest
COL = 32

# Gallon speaks plainly in English and in an archaic register in Japanese
# ("わし" / "そなた" / "〜なろう"), in both q204-bb-j and q219-bb-j. Each entry is
# a list of message pages; the first becomes `message`, the rest `add_msg`.
TEXT = {
    "E": {
        "none": [
            r'"I do run other services\nhere. Only for those\n<color 5>Paganini<color 0> vouches for."',
            r'"He\'s up at the Control\nTower. Help him out in\n<color 5>The East Tower<color 0> first."',
        ],
        "west": [
            r'"ES Weapons I can modify\nfor you now. Photon\nattributes? Not yet."',
            r'"<color 5>Paganini<color 0> owes me one\nmore word on you. Finish\n<color 5>The West Tower<color 0> for him."',
        ],
    },
    "J": {
        "none": [
            '"\u308f\u3057\u306b\u306f \u307b\u304b\u306b\u3082\\n'
            '\u5546\u3044\u304c \u3042\u308b\u306e\u3060\u304c\u306a\u2026"',
            '"<color 5>\u30d1\u30ac\u30cb\u30fc\u30cb<color 0>\u6bbf\u306e \u53e3\u5229\u304d\u304c\\n'
            '\u306a\u304f\u3066\u306f\u306a\u3002"',
            '"\u5fa1\u4ec1\u306f <color 5>\u5236\u5fa1\u5854<color 0>\u306b \u304a\u308b\u3002\\n'
            '\u307e\u305a\u306f <color 5>\u6771\u5929\u306e\u5854<color 0>\u3067\\n'
            '\u529b\u3092 \u8cb8\u3057\u3066\u3084\u308b\u304c\u3088\u3044\u3002"',
        ],
        "west": [
            '"<color 5>\uff25\uff33\u30a6\u30a7\u30dd\u30f3\u306e\u6539\u9020<color 0>\u306a\u3089\\n'
            '\u3044\u3064\u3067\u3082 \u5f15\u304d\u53d7\u3051\u3088\u3046\u3002"',
            '"\u3060\u304c <color 5>\u30d5\u30a9\u30c8\u30f3\u5c5e\u6027\u5f37\u5316<color 0>\u306f\\n'
            '\u307e\u3060 \u65e9\u3044\u3088\u3046\u3060\u306a\u3002"',
            '"<color 5>\u30d1\u30ac\u30cb\u30fc\u30cb<color 0>\u6bbf\u306e \u53e3\u5229\u304d\u304c\\n'
            '\u3044\u307e \u3072\u3068\u3064 \u305f\u308a\u306c\u3002\\n'
            '<color 5>\u897f\u5929\u306e\u5854<color 0>\u3078 \u5411\u304b\u3046\u304c\u3088\u3044\u3002"',
        ],
    },
}

# The two tests the shop menu runs before deciding which entries to show.
GATE_RE = (
    r"  va_start\n"
    r"  arg_pushl\s+0x00000002\n"
    r"  arg_pushl\s+0x00000020\n"
    r"  va_call\s+(label\w+)\n"
    r"  va_end\n"
    r"  jmpi_eq\s+r0, 0x00000000, (label\w+)\n"
    r"  va_start\n"
    r"  arg_pushl\s+0x00000002\n"
    r"  arg_pushl\s+0x00000040\n"
    r"  va_call\s+(label\w+)\n"
    r"  va_end\n"
    r"  jmpi_eq\s+r0, 0x00000000, (label\w+)\n"
)


def op(name, args=None):
    return "  " + name if not args else "  " + name.ljust(COL) + args


class PatchError(SystemExit):
    pass


def message_block(pages):
    """Render one multi-page NPC message."""
    lines = [op("arg_pushl", FACE),
             op("arg_pushs", pages[0]),
             op("message", "... 0xA5 /* 165 */, " + pages[0])]
    for page in pages[1:]:
        lines.append(op("arg_pushs", page))
        lines.append(op("add_msg", "... " + page))
    lines.append(op("message_end"))
    return lines


def main(inp, outp):
    t = io.open(inp, encoding="utf-8", newline="\n").read()

    lang_m = re.search(r"^\.language (\w)$", t, re.M)
    if not lang_m or lang_m.group(1) not in TEXT:
        raise PatchError("PATCH FAILED: no hint text for language %s"
                         % (lang_m.group(1) if lang_m else "?"))
    text = TEXT[lang_m.group(1)]

    gates = list(re.finditer(GATE_RE, t))
    if len(gates) != 1:
        raise PatchError("PATCH FAILED: expected 1 shop menu gate, found %d" % len(gates))
    gate = gates[0]
    if gate.group(1) != gate.group(3):
        raise PatchError("PATCH FAILED: the two gate tests call different helpers (%s, %s)"
                         % (gate.group(1), gate.group(3)))
    test_helper = gate.group(1)

    # The menu lives in the block the gate sits in; the greeting falls through
    # into that block's label, while the post-transaction loop jumps straight to
    # it. Hanging the hint off the fall-through shows it once per visit rather
    # than after every exchange.
    headers = list(re.finditer(r"^label\w+@0x\w+:\n", t[:gate.start()], re.M))
    if not headers:
        raise PatchError("PATCH FAILED: cannot find the menu block's label")
    header = headers[-1]
    preamble = t[:header.start()]
    if not preamble.endswith("  message_end\n\n"):
        raise PatchError("PATCH FAILED: expected the greeting to end with message_end, got:\n%r"
                         % preamble[-60:])

    base = ((max(int(x, 16) for x in re.findall(r"^label([0-9A-F]+)@", t, re.M)) + 0x100) & ~0xFF)
    L = {n: "%04X" % (base + i) for i, n in enumerate(["hint", "none", "west"])}

    t = (t[:header.start()]
         + op("call", "label" + L["hint"]) + "\n\n"
         + t[header.start():])

    new_code = "\n".join(
        [
            "",
            "// ---- unlock hint (added) --------------------------------------------",
            "// Say why the Photon service is missing instead of silently showing a",
            "// shorter menu. quest_counter[2] & 0x20 is set by The East Tower and",
            "// & 0x40 by The West Tower. Dialogue only -- nothing is unlocked here.",
            "label%s@0x%s:" % (L["hint"], L["hint"]),
            op("va_start"),
            op("arg_pushl", "0x00000002"),
            op("arg_pushl", "0x00000020"),
            op("va_call", test_helper),
            op("va_end"),
            op("jmpi_eq", "r0, 0x00000000, label" + L["none"]),
            op("va_start"),
            op("arg_pushl", "0x00000002"),
            op("arg_pushl", "0x00000040"),
            op("va_call", test_helper),
            op("va_end"),
            op("jmpi_eq", "r0, 0x00000000, label" + L["west"]),
            op("ret"),
            "",
            "// Neither Tower done: no ES Weapon service, no Photon service.",
            "label%s@0x%s:" % (L["none"], L["none"]),
        ]
        + message_block(text["none"])
        + [
            op("ret"),
            "",
            "// East Tower done, West Tower not: ES Weapons yes, Photon no.",
            "label%s@0x%s:" % (L["west"], L["west"]),
        ]
        + message_block(text["west"])
        + [
            op("ret"),
            "// ---- end unlock hint ------------------------------------------------",
            "",
        ])

    # Park the new blocks after the reduced-menu block the first test jumps to.
    anchor_name = gate.group(2)[5:]
    anchor_m = re.search(r"^label%s@0x%s:\n(?:  .*\n)+" % (anchor_name, anchor_name), t, re.M)
    if not anchor_m:
        raise PatchError("PATCH FAILED: cannot isolate block for %s" % gate.group(2))
    t = t[:anchor_m.end()] + new_code + t[anchor_m.end():]

    io.open(outp, "w", encoding="utf-8", newline="\n").write(t)
    print("hint added -> %s (language %s, new labels at 0x%04X)"
          % (outp, lang_m.group(1), base))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

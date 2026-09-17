# -*- coding: utf-8 -*-
"""Tell the player why Paganini's Photon service isn't showing.

Quest 204 is titled "Gallon's Shop", but the Photon Drop services -- item
exchange, ES weapon specials, Photon attribute upgrades -- belong to PAGANINI,
who introduces himself in the back room ("My name is Paganini.") with his son
Hopkins. Gallon is the other merchant in the quest (points, roulette, CDs).
Paganini is also the NPC whose errands in The East/West Tower set the unlock
flags, so the hint is spoken by him, in the first person, about his own
errands.

The shop silently drops menu entries when the player hasn't unlocked them --
no explanation, just a shorter list -- so someone who has heard the shop sells
percentages concludes it is broken. This adds a line pointing at the Tower
quests that set the flags.

Runs on the same --reassembly disassembly as patch_hit.py, and after it:

    newserv disassemble-quest-script --bb --reassembly --language=L IN.bin IN.txt
    python3 patch_hint.py IN.txt OUT.txt
    newserv assemble-quest-script OUT.txt OUT.bin

Nothing is unlocked and no flag is written -- this is dialogue only.
"""
import io
import re
import sys

FACE = "0x000000A5"  # Paganini's speaker id; Hopkins is 0xA1
COL = 32

# Paganini is theatrical in English ("This could be a very profitable opportunity
# for you too...") and archaic in Japanese ("わし" / "そなた" / "〜なろう"), in both
# q204-bb-j and q219-bb-j. Each entry is a list of message pages; the first becomes
# `message`, the rest `add_msg`. Keep lines to ~24 half-width / ~13 full-width
# characters so the bubble does not wrap them.
TEXT = {
    "E": {
        "none": [
            r'"I have other services,\ntoo... but only for\nhunters I can trust."',
            r'"Lend me a hand in\n<color 5>The East Tower<color 0>,\nand we\'ll talk again."',
        ],
        "west": [
            r'"You helped me in the\n<color 5>East Tower<color 0>. I haven\'t\nforgotten."',
            r'"Help me once more in\n<color 5>The West Tower<color 0>, and\nI\'ll show you the rest."',
        ],
    },
    "J": {
        "none": [
            '"わしには ほかにも\\n商いが あるのだがな…"',
            '"信用できる ハンターにしか\\n見せられんのだ。"',
            '"<color 5>東天の塔<color 0>で わしに\\n力を 貸してくれたら\\nまた 話そう。"',
        ],
        "west": [
            '"<color 5>東天の塔<color 0>での 恩は\\n忘れておらんぞ。"',
            '"<color 5>西天の塔<color 0>でも わしに\\n力を 貸してくれたら\\n残りを 見せてやろう。"',
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
    """Render one multi-page NPC message.

    Starts with a sync. The hint follows Paganini's greeting, so it is the same
    speaker opening a new message right after message_end -- and without a frame
    in between, the first page is silently lost (observed in game: the bubble shuts,
    nothing shows for ~2s, then page 2 appears). Every stock script does this the
    same way: across q204/q219/q223/q224 all 8 same-speaker message_end -> message
    transitions have a sync between them, and all 24 without one change speaker.
    """
    lines = [op("sync"),
             op("arg_pushl", FACE),
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

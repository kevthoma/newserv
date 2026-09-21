# -*- coding: utf-8 -*-
"""Pay the Control Tower quests in Photon Drops instead of meseta.

    newserv disassemble-quest-script --bb --reassembly --language=L IN.bin IN.txt
    python3 patch_tower_reward.py IN.txt OUT.txt
    newserv assemble-quest-script OUT.txt OUT.bin

Applies to quests 223 (The East Tower) and 224 (The West Tower).

Stock, both pay 5,000 / 10,000 / 20,000 / 40,000 meseta by difficulty, on *every*
clear and to *every* player in the party -- `set_qt_success` runs the difficulty
switch each time the quest is completed. Meseta is worthless against a 999,999
cap, but Photon Drops are the actual currency, so paying the headline amount on
every clear would make these the best PD faucet on the server.

So the headline amount is a FIRST-CLEAR bonus, once per difficulty per character,
and repeats pay a token amount. "Already claimed" is one bit per difficulty in
quest_counters[7] -- the same counter, and the same one-bit-per-difficulty
pattern, that Government 4-5 and 8-3 use for their "cleared on <difficulty>"
bits in its low byte. Its upper bits are unused by every stock quest (checked by
disassembling all 335 BB scripts; the only writers of counter 7, 4-5 and 8-3,
read-modify-write it one bit at a time).

Why a counter and not a quest flag: `gset` sends 6x75, which the server FORWARDS
to the whole party (quest flags keep everyone's quest state in sync). The reward
runs on every player's client at once, so one player's claim could arrive at
another before their own check and cost them their first-clear bonus. Counter
writes (6xD2) are applied to the sender's character only and never forwarded.

Why not the quest's own unlock bit (quest_counters[2] & 0x20/0x40, as an earlier
version did): that bit is only set by Paganini's errand, not by clearing the
quest, so a player who never did the errand read as "first clear" every time.
"""
import io
import re
import sys

FIRST_CLEAR = [10, 20, 40, 60]  # Normal, Hard, Very Hard, Ultimate
REPEAT = [2, 4, 6, 10]

PD_DATA1 = [0x03, 0x10, 0x00]  # Photon Drop; the stack count lives in data1[5]
COUNT_INDEX = 5

CLAIM_COUNTER = 7
# One "first clear claimed" bit per difficulty (Normal, Hard, Very Hard, Ultimate).
CLAIM_MASKS = {
    223: [0x0100, 0x0200, 0x0400, 0x0800],  # The East Tower
    224: [0x1000, 0x2000, 0x4000, 0x8000],  # The West Tower
}

# r140-r152 hold the item being created, r153 the amount, r154 the repeat amount,
# r155 this difficulty's claim mask. Verified unused in all four scripts.
R_ITEM_FIRST, R_ITEM_LAST, R_ITEM_ID = 140, 151, 152
R_AMOUNT, R_REPEAT, R_MASK = 153, 154, 155

# <rN> is substituted with the register's value, so one string covers both the
# first-clear and repeat amounts.
MESSAGE = {
    "E": '"You received <color 1><r%d><color 0>\\nPhoton Drops."' % R_AMOUNT,
    "J": '"<color 5>\u30d5\u30a9\u30c8\u30f3\u30c9\u30ed\u30c3\u30d7<color 0>\u3092\\n'
         '<color 1><r%d><color 0>\u500b \u53d7\u3051\u53d6\u3063\u305f\u3002"' % R_AMOUNT,
}
DESC_REWARD = {
    "E": ("Reward: ??? Meseta", "Reward: ??? Photon Drops"),
    "J": ("\u5831\u916c\uff1a  \uff1f\uff1f\uff1f\u30e1\u30bb\u30bf",
          "\u5831\u916c\uff1a  \uff1f\uff1f\uff1f\u30d5\u30a9\u30c8\u30f3\u30c9\u30ed\u30c3\u30d7"),
}

COL = 32


def op(name, args=None):
    return "  " + name if not args else "  " + name.ljust(COL) + args


class PatchError(SystemExit):
    pass


def find1(text, pattern, what):
    ms = list(re.finditer(pattern, text, re.M))
    if len(ms) != 1:
        raise PatchError("PATCH FAILED [%s]: expected 1 match, found %d" % (what, len(ms)))
    return ms[0]


def block_of(text, label, what):
    n = label[5:] if label.startswith("label") else label
    m = re.search(r"^label%s@0x%s:\n(?:  .*\n)+" % (n, n), text, re.M)
    if not m:
        raise PatchError("PATCH FAILED [%s]: cannot isolate block for label%s" % (what, n))
    return m


def main(inp, outp):
    t = io.open(inp, encoding="utf-8", newline="\n").read()

    quest_num = int(find1(t, r"^\.quest_num (\d+)$", "quest number").group(1))
    if quest_num not in CLAIM_MASKS:
        raise PatchError("PATCH FAILED: quest %d is not a Tower quest" % quest_num)
    masks = CLAIM_MASKS[quest_num]
    lang = find1(t, r"^\.language (\w)$", "language").group(1)
    if lang not in MESSAGE:
        raise PatchError("PATCH FAILED: no reward text for language %s" % lang)

    for r in range(R_ITEM_FIRST, R_MASK + 1):
        if re.search(r"\br%d\b" % r, t):
            raise PatchError("PATCH FAILED: r%d is already in use by this script" % r)

    base = ((max(int(x, 16) for x in re.findall(r"^label([0-9A-F]+)@", t, re.M)) + 0x100) & ~0xFF)
    L = {n: "%04X" % (base + i) for i, n in enumerate(["pd", "pick", "repeat"])}

    # No .allow_create_item mask is added. It is tempting -- neither quest
    # declares one, so newserv lets them create *any* item and only warns --
    # but both already create items for Paganini's rewards through a helper
    # whose registers the callers fill in. A Photon-Drop-only mask would reject
    # those and break the quest.
    if re.search(r"^\.allow_create_item ", t, re.M):
        raise PatchError("PATCH FAILED: quest unexpectedly declares item creation masks")

    old_reward, new_reward = DESC_REWARD[lang]
    if t.count(old_reward) != 1:
        raise PatchError("PATCH FAILED: reward line %r not found in the description" % old_reward)
    t = t.replace(old_reward, new_reward)

    # The quest's own counter helpers: test (r0 = counter[r1] & r2 != 0) and set (counter[r1] |= r2).
    test_helper = find1(
        t,
        r"^(label\w+)@0x\w+:\n"
        r"  clear\s+r0\n"
        r"  arg_pushr\s+r1\n"
        r"  arg_pushb\s+0x03\n"
        r"  read_counter\s+\.\.\. r1, r3\n"
        r"  and\s+r3, r2\n"
        r"  jmpi_eq\s+r3, 0x00000000, label\w+\n"
        r"  leti\s+r0, 0x00000001\n",
        "counter test helper").group(1)
    set_helper = find1(
        t,
        r"^(label\w+)@0x\w+:\n"
        r"  arg_pushr\s+r1\n"
        r"  arg_pushb\s+0x03\n"
        r"  read_counter\s+\.\.\. r1, r3\n"
        r"  or\s+r3, r2\n"
        r"  arg_pushr\s+r1\n"
        r"  arg_pushr\s+r3\n"
        r"  write_counter\s+\.\.\. r1, r3\n"
        r"  ret\n",
        "counter set helper").group(1)

    # -- the four reward blocks ----------------------------------------------
    diff_reg = find1(t, r"  get_difficulty_level_v2\s+(r\d+)\n", "difficulty register").group(1)
    sw = find1(t, r"  switch_jmp\s+%s, \[(label\w+), (label\w+), (label\w+), (label\w+)\]\n"
               % diff_reg, "difficulty reward switch")
    reward_labels = [sw.group(i) for i in (1, 2, 3, 4)]

    for i, reward_label in enumerate(reward_labels):
        blk = block_of(t, reward_label, "reward block")
        body = blk.group(0)
        if "pl_add_meseta2" not in body:
            raise PatchError("PATCH FAILED: %s does not pay meseta" % reward_label)
        msg_label = find1(body, r"  jmp\s+(label\w+)\n", "reward block tail").group(1)

        header = body.split("\n", 1)[0]
        new_body = "\n".join([
            header,
            op("leti", "r%d, 0x%08X" % (R_AMOUNT, FIRST_CLEAR[i])),
            op("leti", "r%d, 0x%08X" % (R_REPEAT, REPEAT[i])),
            op("leti", "r%d, 0x%08X" % (R_MASK, masks[i])),
            op("call", "label" + L["pick"]),
            op("call", "label" + L["pd"]),
            op("jmp", msg_label),
            "",
        ])
        t = t[:blk.start()] + new_body + t[blk.end():]

        # The message hardcoded the meseta amount; swap in the register so one
        # string serves both the first-clear and repeat payouts.
        mblk = block_of(t, msg_label, "reward message")
        mbody = mblk.group(0)
        old = find1(mbody, r"  arg_pushs\s+(\"(?:[^\"\\]|\\.)*\")\n", "reward message text").group(1)
        mbody = mbody.replace(old, MESSAGE[lang])
        t = t[:mblk.start()] + mbody + t[mblk.end():]

    # -- new code ------------------------------------------------------------
    item_regs = [op("leti", "r%d, 0x%08X" % (R_ITEM_FIRST + i, PD_DATA1[i] if i < len(PD_DATA1) else 0))
                 for i in range(R_ITEM_LAST - R_ITEM_FIRST + 1)]
    item_regs[COUNT_INDEX] = op("let", "r%d, r%d" % (R_ITEM_FIRST + COUNT_INDEX, R_AMOUNT))

    new_code = "\n".join([
        "",
        "// ---- Photon Drop reward (added) -------------------------------------",
        "// r%d = first-clear amount, r%d = repeat amount, r%d = this difficulty's"
        % (R_AMOUNT, R_REPEAT, R_MASK),
        "// \"first clear claimed\" bit in quest_counters[%d]. If the bit is already"
        % CLAIM_COUNTER,
        "// set, pay the repeat amount; otherwise claim it and pay the first-clear amount.",
        "label%s@0x%s:" % (L["pick"], L["pick"]),
        op("va_start"),
        op("arg_pushl", "0x%08X" % CLAIM_COUNTER),
        op("arg_pushr", "r%d" % R_MASK),
        op("va_call", test_helper),
        op("va_end"),
        op("jmpi_ne", "r0, 0x00000000, label%s" % L["repeat"]),
        op("va_start"),
        op("arg_pushl", "0x%08X" % CLAIM_COUNTER),
        op("arg_pushr", "r%d" % R_MASK),
        op("va_call", set_helper),
        op("va_end"),
        op("ret"),
        "",
        "label%s@0x%s:" % (L["repeat"], L["repeat"]),
        op("let", "r%d, r%d" % (R_AMOUNT, R_REPEAT)),
        op("ret"),
        "",
        "// Hand over r%d Photon Drops. If the inventory has no room the server" % R_AMOUNT,
        "// drops the item silently, same as any other quest reward.",
        "label%s@0x%s:" % (L["pd"], L["pd"]),
    ] + item_regs + [
        op("item_create2", "r%d-r%d, r%d" % (R_ITEM_FIRST, R_ITEM_LAST, R_ITEM_ID)),
        op("ret"),
        "// ---- end Photon Drop reward -----------------------------------------",
        "",
    ])

    anchor = block_of(t, reward_labels[-1], "new code insertion point")
    t = t[:anchor.end()] + new_code + t[anchor.end():]

    io.open(outp, "w", encoding="utf-8", newline="\n").write(t)
    print("quest %d (%s): first clear %s, repeats %s, claim bits %s in counter %d -> %s"
          % (quest_num, lang, FIRST_CLEAR, REPEAT, ["0x%04X" % m for m in masks], CLAIM_COUNTER, outp))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

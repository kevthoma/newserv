# -*- coding: utf-8 -*-
"""Government quest item rewards: every player, every clear, and no hand-in without it.

    newserv disassemble-quest-script --bb --reassembly --language=L IN.bin IN.txt
    python3 patch_gov_reward.py IN.txt OUT.txt
    newserv assemble-quest-script OUT.txt OUT.bin

Applies to the six government quests that hand out an item:
1-3 Subterranean Den (403), 2-4 Waterway Shadow (407), 3-3 Central Control (410),
5-5 Test/VR Temple 5 (455), 6-5 Test/Spaceship 5 (460), 7-5 Isle of Mutants (465).

Stock, each quest has a reward routine (class x difficulty -> item_create2) that
an NPC calls after you report in, guarded by a "reward claimed" quest flag
(0x023A-0x023F). Two things go wrong with that:

1. The flag is party-wide. `gset` sends 6x75, which the server forwards to the
   whole party, so the first player to collect sets the flag on every client in
   the game and everyone else is told they already have it. Seen on Coronet
   2026-10-02: three players cleared 5-5 on Hard, one got the Gladius +10, and the
   other two have 0x021B (cleared) set but 0x023D (reward) unset on disk.
2. The reward is a separate NPC visit. The counter accepts the quest as soon as
   r255 is 1, and r255 is set by the boss conversation, so a player can hand in
   without ever collecting.

The patch:

- Swaps the flag for a local register, r160, set by the reward routine and read
  wherever the flag was read. Registers are per client and never forwarded, so
  each player tracks their own claim. It resets when the quest loads, so the
  reward is paid on every clear rather than once per character per difficulty.
- Puts the reward in front of every `set r255`: a new guard routine calls the
  reward routine and sets r255 only if the item was created. If the inventory is
  full the stock "come back when you have room" line plays, r255 stays 0, the
  counter won't accept the quest, and talking to the NPC again retries.

Everything else the NPC does at that point (story flags, music, dialogue) still
runs; only r255 waits for the item.
"""
import io
import re
import sys

# Each quest's stock "reward claimed" flag.
REWARD_FLAGS = {
    403: 0x023A,
    407: 0x023B,
    410: 0x023C,
    455: 0x023D,
    460: 0x023E,
    465: 0x023F,
}

# 1 once this player has received the reward during this run. Verified unused in
# all six scripts (both languages); the patch also checks.
R_GOT = 160

# 5-5's chief now hands the item over himself, so stop sending the player to his
# assistant. In the other quests the existing lines still read correctly: the
# boss's "speak to Irene for your reward" speech is skipped once the reward has
# been paid, and 6-5 / 7-5 already give it from the NPC that sets r255.
TEXT_FIXES = {
    (455, "E"): [
        ('"Get it from my assistant.\\nI hope it helps you out\\non future tests."',
         '"Here it is. I hope it\\nhelps you out on\\nfuture tests."'),
    ],
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
    if quest_num not in REWARD_FLAGS:
        raise PatchError("PATCH FAILED: quest %d is not a government item-reward quest" % quest_num)
    lang = find1(t, r"^\.language (\w)$", "language").group(1)
    flag = "0x%04X" % REWARD_FLAGS[quest_num]
    got = "r%d" % R_GOT

    if re.search(r"\b%s\b" % got, t):
        raise PatchError("PATCH FAILED: %s is already in use by this script" % got)

    base = ((max(int(x, 16) for x in re.findall(r"^label([0-9A-F]+)@", t, re.M)) + 0x100) & ~0xFF)
    guard = "label%04X" % base

    # -- the reward flag becomes a local register --------------------------------
    n_create = len(re.findall(r"^  item_create2\s", t, re.M))
    gsets = re.findall(r"^  gset\s+%s\n" % flag, t, re.M)
    if not n_create or len(gsets) != n_create:
        raise PatchError("PATCH FAILED: expected one gset %s per item_create2, found %d for %d"
                         % (flag, len(gsets), n_create))
    t = re.sub(r"^  gset\s+%s\n" % flag, op("leti", "%s, 0x00000001" % got) + "\n", t, flags=re.M)

    t, n_gget = re.subn(r"^  gget\s+%s, (r\d+)\n" % flag,
                        lambda m: op("let", "%s, %s" % (m.group(1), got)) + "\n", t, flags=re.M)
    if not n_gget:
        raise PatchError("PATCH FAILED: no reads of %s" % flag)
    if flag in t:
        raise PatchError("PATCH FAILED: %s is still referenced after the rewrite" % flag)

    # -- the reward routine ------------------------------------------------------
    # label: let rA, r160 / jmpi_eq rA, 1, <ret> / get_difficulty... or get_chara_class
    rm = find1(
        t,
        r"^(label\w+)@0x\w+:\n"
        r"  let\s+(r\d+), %s\n"
        r"  jmpi_eq\s+\2, 0x00000001, (label\w+)\n"
        r"  get_chara_class\s+r\d+, r\d+-(r\d+)\n"
        r"  switch_jmp\s+\4, \[(label\w+), (label\w+), (label\w+), (label\w+)\]\n" % got,
        "reward routine")
    reward, ret_label = rm.group(1), rm.group(3)
    if block_of(t, ret_label, "return label").group(0).split("\n", 1)[1] != "  ret\n":
        raise PatchError("PATCH FAILED: %s is not a bare ret" % ret_label)

    # Every class x every difficulty must end in an item_create2, or the guard would
    # refuse completion forever for that combination. Class 3 means "no player
    # present or invalid class flags", which the routine's own client ID can't
    # return; some quests make it a bare ret, which is fine.
    diff_reg = find1(t, r"^  get_difficulty_level_v2\s+(r\d+)\n", "difficulty register").group(1)
    for i, class_label in enumerate(rm.group(5, 6, 7, 8)):
        body = block_of(t, class_label, "class branch").group(0)
        if i == 3 and body.split("\n", 1)[1] == "  ret\n":
            continue
        dm = re.match(r"label\w+@0x\w+:\n  switch_jmp\s+%s, \[(label\w+), (label\w+), (label\w+), (label\w+)\]\n"
                      % diff_reg, body)
        if not dm:
            raise PatchError("PATCH FAILED: %s is not a difficulty switch" % class_label)
        for leaf in dm.groups():
            if "  item_create2" not in block_of(t, leaf, "reward leaf").group(0):
                raise PatchError("PATCH FAILED: %s does not create an item" % leaf)

    # -- the guard ---------------------------------------------------------------
    t, n_r255 = re.subn(r"^  set\s+r255\n", op("call", guard) + "\n", t, flags=re.M)
    if not n_r255:
        raise PatchError("PATCH FAILED: nothing sets r255")

    new_code = "\n".join([
        "",
        "// ---- reward guard (added) ------------------------------------------",
        "// Replaces `set r255`. Pays the reward if this player hasn't had it this run,",
        "// and only then lets the counter accept the quest. Inventory full -> the",
        "// reward routine says so, r255 stays 0, and talking to the NPC again retries.",
        "// The sync keeps the reward's own message from opening in the same frame",
        "// as the caller's message_end (a same-speaker page is lost without one).",
        "%s@0x%s:" % (guard, guard[5:]),
        op("sync"),
        op("call", reward),
        op("jmpi_eq", "%s, 0x00000000, %s" % (got, ret_label)),
        op("set", "r255"),
        op("ret"),
        "// ---- end reward guard ----------------------------------------------",
        "",
    ])
    anchor = block_of(t, reward, "new code insertion point")
    t = t[:anchor.end()] + new_code + t[anchor.end():]

    # -- dialogue ----------------------------------------------------------------
    for old, new in TEXT_FIXES.get((quest_num, lang), []):
        if old not in t:
            raise PatchError("PATCH FAILED: line %s not found" % old)
        t = t.replace(old, new)

    io.open(outp, "w", encoding="utf-8", newline="\n").write(t)
    print("quest %d (%s): flag %s -> %s (%d reads, %d writes), %d r255 site(s) guarded by %s -> %s"
          % (quest_num, lang, flag, got, n_gget, len(gsets), n_r255, guard, outp))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

# -*- coding: utf-8 -*-
"""Add "Hit" as a fifth enhanceable attribute to Gallon's Shop.

Input/output is the --reassembly disassembly newserv produces:

    newserv disassemble-quest-script --bb --reassembly --language=L IN.bin IN.txt
    python3 patch_hit.py IN.txt OUT.txt
    newserv assemble-quest-script OUT.txt OUT.bin

Every label the patch touches is discovered from the script rather than
hardcoded, so this applies to both q204 (normal) and q219 (Valentine event),
which are the same program compiled with different label numbers.

Hit is attribute type 5 -- the same type the game already uses for hit that
drops naturally, so the slot-packing rules need no changes. What does change:
Hit costs 3x the element price and caps at 90 instead of 100.

This is only half the feature. newserv validates the payment amount and the
cap server-side in on_upgrade_weapon_attribute_bb (ReceiveSubcommands.cc);
without the matching change there, every Hit purchase fails.
"""
import io
import re
import sys

HIT_ATTR = 5         # item attribute type for Hit
HIT_MENU_INDEX = 4   # 0-based position of "Hit" in the attribute menu

HIT_COST_PD_1 = 0x0C    # 12 PD -> +1   (elements: 4)
HIT_COST_PD_5 = 0x3C    # 60 PD -> +5   (elements: 20)
HIT_COST_PS_30 = 0x03   # 3 PS  -> +30  (elements: 1)
HIT_CAP = 0x5A          # 90            (elements: 100)

ELEM_CAP = 0x64
COL = 32  # operands start here, matching newserv's disassembly


def op(name, args=None):
    return "  " + name if not args else "  " + name.ljust(COL) + args


def num(label):
    """"label04D0" -> "04D0" (the discovery regexes capture the full name)."""
    return label[5:] if label.startswith("label") else label


class PatchError(SystemExit):
    pass


class Script(object):
    def __init__(self, text):
        self.t = text

    # -- helpers ------------------------------------------------------------
    def find(self, pattern, what, count=1):
        ms = list(re.finditer(pattern, self.t))
        if len(ms) != count:
            raise PatchError("PATCH FAILED [%s]: expected %d match(es) for %s, found %d"
                             % (what, count, pattern, len(ms)))
        return ms[0] if count == 1 else ms

    def replace(self, old, new, what, count=1):
        n = self.t.count(old)
        if n != count:
            raise PatchError("PATCH FAILED [%s]: expected %d occurrence(s), found %d:\n%r"
                             % (what, count, n, old))
        self.t = self.t.replace(old, new)

    def block(self, label):
        """A label's block: its header plus every indented line under it.

        Blocks in newserv's output are separated by blank lines, and only
        instruction lines are indented, so that boundary is unambiguous.
        """
        n = num(label)
        m = re.search(r"^label%s@0x%s:\n(?:  .*\n)+" % (n, n), self.t, re.M)
        if not m:
            raise PatchError("PATCH FAILED: cannot isolate block for label%s" % n)
        return m.group(0)

    def max_label(self):
        return max(int(x, 16) for x in re.findall(r"^label([0-9A-F]+)@", self.t, re.M))


def discover(s):
    """Locate every label the patch depends on."""
    d = {}

    m = s.find(r"  switch_jmp\s+r130, \[(label\w+), (label\w+), (label\w+), (label\w+), "
               r"(label\w+)\]\n", "attribute menu switch")
    d["menu_switch"] = m.group(0)
    d["attr_labels"] = [m.group(i) for i in (1, 2, 3, 4)]
    d["goback"] = m.group(5)

    m = s.find(r"  jmpi_gt\s+r136, 0x%08X, (label\w+)\n" % ELEM_CAP, "slot cap check", 3)[0]
    d["cap_line"] = m.group(0)
    d["over_cap"] = m.group(1)

    m = s.find(r"  jmpi_eq\s+r135, 0x00000001, (label\w+)\n"
               r"  jmpi_eq\s+r135, 0x00000005, (label\w+)\n"
               r"  jmpi_eq\s+r135, 0x0000001E, (label\w+)\n", "payment dispatch")
    d["dispatch"] = m.group(0)
    d["pay_pd1"], d["pay_pd5"], d["pay_ps30"] = m.group(1), m.group(2), m.group(3)

    m = s.find(r"  switch_call\s+r1, \[(label\w+), (label\w+), (label\w+), (label\w+), "
               r"(label\w+)\]\n", "attribute value dispatch")
    d["value_switch"] = m.group(0)

    m = s.find(r"  switch_call\s+r130, \[(label\w+), (label\w+), (label\w+), (label\w+)\]\n",
               "confirmation line dispatch")
    d["line_switch"] = m.group(0)
    d["dark_line_label"] = m.group(4)

    m = s.find(r"  jmpi_gt\s+r1, 0x%08X, (label\w+)\n  let\s+r0, r1\n" % ELEM_CAP,
               "preview clamp")
    d["clamp_line"] = m.group(0)

    m = s.find(r"  jmpi_lt\s+r141, 0x00000004, (label\w+)\n", "PD shortage label")
    d["no_pd"] = m.group(1)
    m = s.find(r"  jmpi_eq\s+r142, 0x00000000, (label\w+)\n", "PS shortage label")
    d["no_ps"] = m.group(1)

    m = s.find(r"  jmpi_eq\s+r119, 0x00000005, (label\w+)\n", "slot-3 Hit detection")
    d["slot3_typo_line"] = m.group(0)

    return d


def main(inp, outp):
    s = Script(io.open(inp, encoding="utf-8", newline="\n").read())
    d = discover(s)

    # New labels start past the highest one the script already uses.
    base = (s.max_label() + 0x100) & ~0xFF
    L = {name: "%04X" % (base + i) for i, name in enumerate([
        "hit_select", "need_ps", "need_pd5", "hit_slots",
        "cap", "cap_hit", "cap_over",
        "pay", "pay_pd1", "pay_pd5", "pay_ps30",
        "stash", "line", "clamp_hit", "clamp_max"])}

    # -- menu: insert "Hit" before "Go back" ---------------------------------
    m = s.find(r'  arg_pushs\s+"((?:[^"\\]|\\.)*)"\n  list\s+\.\.\. r130, "(?:[^"\\]|\\.)*"\n',
               "attribute menu string")
    old_menu, menu_text = m.group(0), m.group(1)
    parts = menu_text.split(r"\n")
    if len(parts) != 5:
        raise PatchError("PATCH FAILED: attribute menu has %d entries, expected 5" % len(parts))
    new_text = r"\n".join(parts[:4] + ["Hit"] + parts[4:])
    s.replace(old_menu,
              op("arg_pushs", '"%s"' % new_text) + "\n"
              + op("list", '... r130, "%s"' % new_text) + "\n",
              "attribute menu string")
    s.replace(d["menu_switch"],
              d["menu_switch"].replace("%s]" % d["goback"],
                                       "label%s, %s]" % (L["hit_select"], d["goback"])),
              "attribute menu switch")

    # -- per-attribute cap ---------------------------------------------------
    # All three slot handlers shared one hardcoded 100. Route them through a
    # helper that knows Hit caps lower.
    s.replace(d["cap_line"],
              op("call", "label" + L["cap"]) + "\n"
              + op("jmpi_eq", "r0, 0x00000001, %s" % d["over_cap"]) + "\n",
              "slot cap checks", 3)

    # -- payment dispatch ----------------------------------------------------
    s.replace(d["dispatch"],
              op("jmpi_eq", "r130, 0x%08X, label%s" % (HIT_MENU_INDEX, L["pay"])) + "\n"
              + d["dispatch"],
              "payment dispatch")

    # -- display -------------------------------------------------------------
    s.replace(op("clear", "r134") + "\n",
              op("clear", "r134") + "\n" + op("clear", "r138") + "\n", "clear r138")
    s.replace(d["value_switch"],
              d["value_switch"].replace("]", ", label%s]" % L["stash"]),
              "attribute value dispatch")
    s.replace(d["line_switch"],
              d["line_switch"].replace("]", ", label%s]" % L["line"]),
              "confirmation line dispatch")
    s.replace(d["clamp_line"],
              op("jmpi_eq", "r130, 0x%08X, label%s" % (HIT_MENU_INDEX, L["clamp_hit"])) + "\n"
              + d["clamp_line"],
              "preview clamp")

    # -- pre-existing Sega typo ---------------------------------------------
    # The third "does this weapon already have Hit?" test read r119 (slot 2's
    # VALUE) where it meant r120 (slot 3's TYPE). Harmless while Hit could only
    # arrive from drops; wrong now that the shop can put Hit in slot 3.
    s.replace(d["slot3_typo_line"],
              d["slot3_typo_line"].replace("r119,", "r120,"),
              "slot-3 Hit detection typo")

    # -- shop intro ----------------------------------------------------------
    # The amount menu ("+5% - 20 PD's") can't show two prices, so state the Hit
    # price in Gallon's pitch instead. English text only; other languages keep
    # the original pitch and just gain the menu entry.
    INTRO_ANCHOR = r'"What would you like\nto do?"'
    INTRO_EXTRA = [
        r'"<color 5>Hit<color 0> costs triple:\n<color 1>12<color 0>/<color 1>60 '
        r'Photon Drops<color 0>\nor <color 1>3 Photon Spheres<color 0>."',
        r'"It will not go above\n<color 5>90<color 0>, though."',
    ]
    if re.search(r"^\.language E$", s.t, re.M) and s.t.count(INTRO_ANCHOR) == 2:
        old = op("arg_pushs", INTRO_ANCHOR) + "\n" + op("add_msg", "... " + INTRO_ANCHOR) + "\n"
        new = "".join(op("arg_pushs", x) + "\n" + op("add_msg", "... " + x) + "\n"
                      for x in INTRO_EXTRA) + old
        s.replace(old, new, "intro pricing text")
    else:
        print("note: intro pricing text not applied (non-English script)")

    # -- new code ------------------------------------------------------------
    # Clone the four element blocks rather than writing them from scratch, so
    # anything version-specific inside them is carried over verbatim.
    def clone(src_label, new_label, subs):
        text = s.block(src_label)
        text = text.replace("label%s@0x%s:" % (num(src_label), num(src_label)),
                            "label%s@0x%s:" % (new_label, new_label), 1)
        for old, new in subs:
            if old not in text:
                raise PatchError("PATCH FAILED: %r not found in label%s" % (old, src_label))
            text = text.replace(old, new)
        return text

    dark_select = d["attr_labels"][3]
    hit_slots = clone(dark_select, L["hit_slots"],
                      [("0x00000004", "0x%08X" % HIT_ATTR)])

    def pay_block(src, new, old_count, new_count):
        return clone(src, new, [
            ("arg_pushl                       0x%08X" % old_count,
             "arg_pushl                       0x%08X" % new_count),
            ("r139, 0x%X /* %d */" % (old_count, old_count),
             "r139, 0x%X /* %d */" % (new_count, new_count)),
        ])

    pay_pd1 = pay_block(d["pay_pd1"], L["pay_pd1"], 0x04, HIT_COST_PD_1)
    pay_pd5 = pay_block(d["pay_pd5"], L["pay_pd5"], 0x14, HIT_COST_PD_5)
    pay_ps30 = pay_block(d["pay_ps30"], L["pay_ps30"], 0x01, HIT_COST_PS_30)

    hit_line = clone(d["dark_line_label"], L["line"],
                     [("r134", "r138"), ("Dark    ", "Hit     ")])

    new_code = "\n".join([
        "",
        "// ---- Hit enhancement (added) ----------------------------------------",
        "// Hit is attribute type %d. It reuses the element slot search, but" % HIT_ATTR,
        "// costs 3x and caps at %d instead of %d." % (HIT_CAP, ELEM_CAP),
        "",
        "// Menu entry %d (Hit). The affordability checks on the amount menu ran" % HIT_MENU_INDEX,
        "// before the attribute was known, so re-check them at the 3x price.",
        "label%s@0x%s:" % (L["hit_select"], L["hit_select"]),
        op("jmpi_eq", "r135, 0x0000001E, label%s" % L["need_ps"]),
        op("jmpi_eq", "r135, 0x00000005, label%s" % L["need_pd5"]),
        op("jmpi_lt", "r141, 0x%08X, %s" % (HIT_COST_PD_1, d["no_pd"])),
        op("jmp", "label%s" % L["hit_slots"]),
        op("ret"),
        "",
        "label%s@0x%s:" % (L["need_ps"], L["need_ps"]),
        op("jmpi_lt", "r142, 0x%08X, %s" % (HIT_COST_PS_30, d["no_ps"])),
        op("jmp", "label%s" % L["hit_slots"]),
        op("ret"),
        "",
        "label%s@0x%s:" % (L["need_pd5"], L["need_pd5"]),
        op("jmpi_lt", "r141, 0x%08X, %s" % (HIT_COST_PD_5, d["no_pd"])),
        op("jmp", "label%s" % L["hit_slots"]),
        op("ret"),
        "",
        "// Same slot search as the elements, looking for attribute type %d." % HIT_ATTR,
        hit_slots,
        "// r0 = 1 when the new value (r136) exceeds the cap for the attribute",
        "// currently selected in r130.",
        "label%s@0x%s:" % (L["cap"], L["cap"]),
        op("jmpi_eq", "r130, 0x%08X, label%s" % (HIT_MENU_INDEX, L["cap_hit"])),
        op("jmpi_gt", "r136, 0x%08X, label%s" % (ELEM_CAP, L["cap_over"])),
        op("leti", "r0, 0x00000000"),
        op("ret"),
        "",
        "label%s@0x%s:" % (L["cap_hit"], L["cap_hit"]),
        op("jmpi_gt", "r136, 0x%08X, label%s" % (HIT_CAP, L["cap_over"])),
        op("leti", "r0, 0x00000000"),
        op("ret"),
        "",
        "label%s@0x%s:" % (L["cap_over"], L["cap_over"]),
        op("leti", "r0, 0x00000001"),
        op("ret"),
        "",
        "// Hit payment dispatch: same three increments, 3x the price.",
        "label%s@0x%s:" % (L["pay"], L["pay"]),
        op("jmpi_eq", "r135, 0x00000005, label%s" % L["pay_pd5"]),
        op("jmpi_eq", "r135, 0x0000001E, label%s" % L["pay_ps30"]),
        op("jmp", "label%s" % L["pay_pd1"]),
        op("ret"),
        "",
        pay_pd1,
        pay_pd5,
        pay_ps30,
        "// Stash the weapon's current Hit for the confirmation line.",
        "label%s@0x%s:" % (L["stash"], L["stash"]),
        op("let", "r138, r2"),
        op("ret"),
        "",
        hit_line,
        "// Preview clamp for Hit.",
        "label%s@0x%s:" % (L["clamp_hit"], L["clamp_hit"]),
        op("jmpi_gt", "r1, 0x%08X, label%s" % (HIT_CAP, L["clamp_max"])),
        op("let", "r0, r1"),
        op("ret"),
        "",
        "label%s@0x%s:" % (L["clamp_max"], L["clamp_max"]),
        op("leti", "r0, 0x%08X" % HIT_CAP),
        op("ret"),
        "// ---- end Hit enhancement --------------------------------------------",
        "",
    ])

    # Park the new blocks after the last element selector. Every one of them is
    # entered by an explicit jmp and left by ret/jmp, so placement is free.
    anchor = s.block(dark_select)
    s.replace(anchor, anchor + new_code, "new code insertion point")

    io.open(outp, "w", encoding="utf-8", newline="\n").write(s.t)
    print("patched OK -> %s (new labels at 0x%04X)" % (outp, base))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

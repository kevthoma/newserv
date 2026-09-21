# -*- coding: utf-8 -*-
"""Remove the Tower unlock gate from Paganini's shop (quests 204 / 219).

Stock, the shop menu only offers "Modify ES Weapon" once quest_counters[2] & 0x20
is set, and "Enhance weapon's Photon" once & 0x40 is set too. Those bits are set
by Paganini's errands in The East Tower and The West Tower -- an errand that has
to be started by talking to a specific NPC before the quest, and completed by
Ryukering back to town after the boss instead of taking the pipe. Nothing in the
game explains that sequence, and the Photon Drop price already meters the
service, so the gate is removed: every character sees the full menu.

Runs on the --reassembly disassembly, after patch_hit.py:

    newserv disassemble-quest-script --bb --reassembly --language=L IN.bin IN.txt
    python3 patch_hit.py IN.txt HIT.txt
    python3 patch_ungate.py HIT.txt OUT.txt
    newserv assemble-quest-script OUT.txt OUT.bin

The reduced-menu blocks the gate jumped to are left in place, unreachable.
"""
import io
import re
import sys

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
# What must follow the gate: the full menu, with all four entries.
FULL_MENU_RE = r'  arg_pushb\s+0x32\n  arg_pushs\s+"[^"\n]*\\n[^"\n]*\\n[^"\n]*\\n[^"\n]*"\n'


class PatchError(SystemExit):
    pass


def main(inp, outp):
    t = io.open(inp, encoding="utf-8", newline="\n").read()
    gates = list(re.finditer(GATE_RE, t))
    if len(gates) != 1:
        raise PatchError("PATCH FAILED: expected 1 shop menu gate, found %d" % len(gates))
    gate = gates[0]
    if not re.match(FULL_MENU_RE, t[gate.end():]):
        raise PatchError("PATCH FAILED: the gate is not followed by the four-entry menu:\n%r"
                         % t[gate.end():gate.end() + 200])
    if "call                            label2700" in t:
        raise PatchError("PATCH FAILED: this script carries the unlock hint; build from patch_hit.py "
                         "output, not from a hinted script")
    t = t[:gate.start()] + t[gate.end():]
    io.open(outp, "w", encoding="utf-8", newline="\n").write(t)
    print("gate removed -> %s (reduced menus %s / %s now unreachable)"
          % (outp, gate.group(2), gate.group(4)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

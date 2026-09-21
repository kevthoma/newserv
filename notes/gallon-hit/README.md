# Gallon's Shop: adding Hit

Gallon's Shop is the quest that sells Photon attribute upgrades — quest **204**
(`system/quests/shops/q204-bb-*.bin`) normally, and quest **219** during the
Valentine event (`V_Event == 3`). Stock, it offers Native / A.Beast / Machine /
Dark. This change adds **Hit** as a fifth choice, removes the Tower unlock gate,
and makes the Tower quests pay Photon Drops.

**Paganini runs this service, not Gallon.** The quest is titled "Gallon's Shop",
but its Photon Drop services belong to Paganini, who introduces himself in the
back room ("My name is Paganini.") with his son Hopkins (speaker ids `0xA5` and
`0xA1`); Gallon is the other merchant in the quest (points, roulette, CDs).

Hit is attribute type 5, which is what Hit already is when it drops naturally,
so nothing about how attributes pack into a weapon's three slots changes.

| | Elements | Hit |
|---|---|---|
| +1 | 4 Photon Drops | 12 Photon Drops |
| +5 | 20 Photon Drops | 60 Photon Drops |
| +30 | 1 Photon Sphere | 3 Photon Spheres |
| cap | 100 | 90 |

## It takes both halves

The quest does not apply the upgrade itself. It calls `bb_exchange_pd_percent`
(F957) / `bb_exchange_ps_percent` (F958), which send 6xDA, and the server does
the work in `on_upgrade_weapon_attribute_bb` (`src/ReceiveSubcommands.cc`).
That handler whitelists the three payment amounts and enforces the cap, so a
patched quest against a stock server fails every Hit purchase with
`unknown PD/PS expenditure` (safely — it refuses before taking any drops).
The server change must be deployed first, which needs a restart; the quest
files after it can be reloaded live.

The handler never validated the attribute id, so type 5 flows through its slot
search unchanged; the only server edits are the 3x payment amounts and the
90 cap.

## The unlock gate is removed

Stock, the menu only offers **Modify ES Weapon** once `quest_counters[2] & 0x20`
is set, and **Enhance weapon's Photon** once `& 0x40` is set too. Those bits are
set by Paganini's errands in The East Tower (223) and The West Tower (224) — an
errand that has to be started by talking to a specific NPC before the quest and
finished by Ryukering back to town after the boss instead of taking the pipe,
East before West, once per character. Nothing in the game explains that
sequence, and the Photon Drop price already meters the service, so
`patch_ungate.py` deletes the two tests: every character sees the full menu,
including ES Weapon modification. The reduced-menu blocks stay in the script,
unreachable.

An earlier version kept the gate and added a hint (`patch_hint.py`, removed; see
git history). One thing learned from it is worth keeping for any future dialogue
edit: **when the same speaker opens a new `message` straight after their own
`message_end`, put a `sync` between them, or the first page is silently lost.**
Recorded at 13.5 fps on the canary: the bubble closed, nothing was on screen for
2.2 s, then page 2 appeared. The stock scripts always do this — across
q204/q219/q223/q224 all 8 same-speaker transitions have a `sync`, and all 24
without one change speaker.

## Re-applying the quest patches

The scripts discover every label they touch by pattern, so they work on every
language variant despite different label numbering, and should survive a future
refresh of the stock files. They fail loudly rather than half-applying. Always
start from the stock `.orig` files kept next to the patched ones.

```bash
# shop: q204-bb-e (E), q204-bb-j (J), q219-bb-j (J)
newserv disassemble-quest-script --bb --reassembly --language=E q204-bb-e.bin.orig q204.txt
python3 patch_hit.py    q204.txt     q204-hit.txt
python3 patch_ungate.py q204-hit.txt q204-final.txt
newserv assemble-quest-script q204-final.txt q204-bb-e.bin

# towers: q223-bb-{e,j}, q224-bb-{e,j}
newserv disassemble-quest-script --bb --reassembly --language=E q223-bb-e.bin.orig q223.txt
python3 patch_tower_reward.py q223.txt q223-pd.txt
newserv assemble-quest-script q223-pd.txt q223-bb-e.bin
```

Those seven are every BB script of these quests. The gc/xb copies are untouched —
`bb_exchange_pd_percent` and `bb_exchange_ps_percent` are BB-only opcodes.

To review what changed, disassemble the patched file again and diff it against
the disassembly of the `.orig`. The loader ignores `.bin.orig` (it keys on the
last extension), so the stock files can sit in `system/quests/` safely.

## What the Hit patch does

- Adds `Hit` to the attribute menu, ahead of `Go back`, and routes it into the
  same slot search the elements use, looking for attribute type 5.
- Re-checks affordability at the 3x price. The Photon Drop / Photon Sphere
  checks on the amount menu run before the attribute is known, so choosing Hit
  with only enough for an element would otherwise fail server-side.
- Replaces the hardcoded 100 in all three slot handlers with a helper that
  returns the cap for the attribute being bought.
- Clones the three payment blocks with the 3x counts, and clamps the preview
  (`X% to Y%`) to 90 for Hit.
- Shows the weapon's current Hit on the confirmation line, in `r138`.
- Fixes a Sega typo while it's in there: the third "does this weapon already
  have Hit?" test read `r119` (slot 2's *value*) where it meant `r120` (slot 3's
  *type*). Harmless while Hit could only arrive from drops; wrong once the shop
  can put Hit in slot 3.

English text for the new menu entry and Paganini's price pitch is applied only to
the English script; other languages get the menu entry with the original pitch.

## Tower quest rewards

`patch_tower_reward.py` pays quests 223 and 224 in Photon Drops instead of
5,000–40,000 meseta (worthless against a 999,999 cap), so the Towers still have a
point now that they no longer unlock anything.

| Difficulty | First clear | Repeat clears |
|---|---|---|
| Normal | 10 PD | 2 PD |
| Hard | 20 PD | 4 PD |
| Very Hard | 40 PD | 6 PD |
| Ultimate | 60 PD | 10 PD |

The first-clear bonus is paid **once per difficulty per character**, so up to
130 PD per Tower per character. The split matters because `set_qt_success` runs
the reward on **every** clear and for **every player in the party** — a flat 60
PD would be 240 PD per Ultimate party-run with no cap.

**"Claimed" is one bit per difficulty in `quest_counters[7]`:**

| | Normal | Hard | Very Hard | Ultimate |
|---|---|---|---|---|
| The East Tower | `0x0100` | `0x0200` | `0x0400` | `0x0800` |
| The West Tower | `0x1000` | `0x2000` | `0x4000` | `0x8000` |

That is the counter, and the pattern, Government 4-5 and 8-3 already use for
their "cleared on \<difficulty\>" bits in its low byte. Its upper bits are unused
by every stock quest: all 335 BB scripts were disassembled, and the only writers
of counter 7 (4-5 and 8-3) read-modify-write it one bit at a time. The reward
uses the quest's own test/set counter helpers.

Two tempting alternatives, and why not:

- **A quest flag (`gset`/`gget`)** would be per-difficulty for free, but `gset`
  sends 6x75, which the server forwards to the whole party to keep quest state
  in sync. The reward runs on every player's client at once, so one player's
  claim could reach another before their own check and cost them their bonus.
  Counter writes (6xD2) apply to the sender's character only.
- **The quest's own unlock bit** (`counter 2 & 0x20/0x40`, used by an earlier
  version) is only set by Paganini's errand, not by clearing the quest — so a
  player who never did the errand read as "first clear" on every run.

`r153` carries the amount, which the reward message prints as `<r153>` so one
string serves both payouts.

**No `.allow_create_item` mask is added, deliberately.** Neither quest declares
one, which means newserv permits them to create *any* item and only logs a
warning — tempting to close while adding an item reward. But both already create
items for Paganini's rewards, through a helper whose registers its three callers
fill in, so a Photon-Drop-only mask would reject those and break the quest.

One cosmetic artifact: adding code shifts the code section's size, so the
assembler pads the final `.data` block (a `VectorXYZTF` list) with zero bytes.
Contents are unchanged and the trailing zeros are inert. Round-tripping the
unmodified file produces no differences at all.

## Deploying

The quest files live in the server's `system/` directory, which is a bind mount
on the host and is *not* refreshed by a new image — copy the three shop files to
`system/quests/shops/` and the four Tower files to `system/quests/tower/` on the
host, then run `reload quests` via `POST /y/shell-exec` (newserv's own README
says `reload quest-index`, which this build rejects). Quest reloads are safe with
players online: anyone already in a quest keeps its old script until it ends.

# Gallon's Shop: adding Hit

Gallon's Shop is the quest that sells Photon attribute upgrades — quest **204**
(`system/quests/shops/q204-bb-*.bin`) normally, and quest **219** during the
Valentine event (`V_Event == 3`). Stock, it offers Native / A.Beast / Machine /
Dark. This change adds **Hit** as a fifth choice.

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
`unknown PD/PS expenditure`. Both changes ship together.

The handler never validated the attribute id, so type 5 flows through its slot
search unchanged; the only server edits are the 3x payment amounts and the
90 cap.

## The unlock hint

The Photon service is gated behind two quest-counter bits, and stock the shop
just shows a shorter menu with no explanation — a player who has heard this
shop sells percentages concludes it is broken. `patch_hint.py` adds a line from
Gallon saying why, and pointing at the quest that opens it:

| State | Menu | Gallon says |
|---|---|---|
| neither Tower | Exchange for an item / Exit | do **The East Tower** for Paganini first |
| East Tower only | + Modify ES Weapon | finish **The West Tower** |
| both | + Enhance weapon's Photon | nothing |

It is dialogue only — nothing is unlocked and no flag is written. The hint hangs
off the greeting's fall-through into the menu block, not the menu block itself,
so it plays once per visit rather than after every exchange.

The flags themselves are `quest_counters[2] & 0x20` (The East Tower, quest 223)
and `& 0x40` (The West Tower, 224), both set at the end of Paganini's errand.
West Tower won't offer its errand until East Tower's bit is set, so they must be
done in that order. `quest_counters` is a flat array in `PSOBBCharacterFile` —
**not** per-difficulty, unlike `quest_flags` — so Normal clears are enough, but
it is per character, so every alt repeats both.

If you ever want the gate gone entirely rather than explained, delete the two
`va_call`/`jmpi_eq r0, 0x00000000` pairs at the top of the menu block; the
reduced-menu blocks then become unreachable, and no server change is needed.

## Re-applying the quest patch

`patch_hit.py` discovers every label it touches by pattern, so it works on both
quests despite their different label numbering, and it should survive a future
refresh of the stock quest files. It fails loudly rather than half-applying.

```bash
newserv disassemble-quest-script --bb --reassembly --language=E \
    q204-bb-e.bin.orig q204.txt
python3 patch_hit.py q204.txt q204-hit.txt
python3 patch_hint.py q204-hit.txt q204-final.txt
newserv assemble-quest-script q204-final.txt q204-bb-e.bin
```

The two patches are independent and compose in either order; the shipped files
have both. `patch_hint.py` carries English and Japanese text and picks by the
script's `.language`, matching Gallon's plain voice in English and his archaic
one (`わし` / `そなた`) in both Japanese scripts.

Same for `q204-bb-j.bin.orig` and `q219-bb-j.bin.orig` with `--language=J`.
The stock files are kept next to the patched ones as `.orig`.

Those three are every BB script of these two quests: 204 ships `-bb-e` and
`-bb-j`, 219 only `-bb-j`. The gc/xb copies are untouched — `bb_exchange_pd_percent`
and `bb_exchange_ps_percent` are BB-only opcodes, so those versions cannot
offer this at all.

To review what changed, disassemble the patched file again and diff it against
the disassembly of the `.orig`.

## What the quest patch does

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

English text for the new menu entry and Gallon's price pitch is applied only to
the English script; other languages get the menu entry with the original pitch.

## Tower quest rewards

`patch_tower_reward.py` pays quests 223 and 224 in Photon Drops instead of
meseta. They are the unlock path for the Photon service, so a mandatory pair of
quests paying a currency nobody needs (5,000–40,000 meseta against a 999,999
cap) was the other half of the same problem the hint addresses.

| Difficulty | First clear | Repeat clears |
|---|---|---|
| Normal | 10 PD | 2 PD |
| Hard | 20 PD | 4 PD |
| Very Hard | 40 PD | 6 PD |
| Ultimate | 60 PD | 10 PD |

The split matters because `set_qt_success` runs the reward on **every** clear
and for **every player in the party** — a flat 60 PD would be 240 PD per
Ultimate party-run with no cap, which is roughly a +5 Hit each per run and would
reprice everything else denominated in Photon Drops.

"First clear" reuses the quest's own unlock bit. The quest sets that bit partway
through, before the success handler runs, so it is sampled during init (right
after `get_difficulty_level_v2`) into `r155`. `r153` carries the amount, which
the reward message prints as `<r153>` so one string serves both payouts.

```bash
newserv disassemble-quest-script --bb --reassembly --language=E \
    q223-bb-e.bin.orig q223.txt
python3 patch_tower_reward.py q223.txt q223-pd.txt
newserv assemble-quest-script q223-pd.txt q223-bb-e.bin
```

All four BB scripts are patched: `q223-bb-{e,j}`, `q224-bb-{e,j}`.

**No `.allow_create_item` mask is added, deliberately.** Neither quest declares
one, which means newserv permits them to create *any* item and only logs a
warning — tempting to close while adding an item reward. But both already create
items for Paganini's rewards, through a helper whose registers its three callers
fill in, so a Photon-Drop-only mask would reject those and break the quest.
Closing the hole properly means enumerating what those call sites can produce
first.

One cosmetic artifact: adding code shifts the code section's size, so the
assembler pads the final `.data` block (a `VectorXYZTF` list) with two zero
bytes, `0x50` → `0x52`. Contents are unchanged and the trailing zeros are inert.
Round-tripping the unmodified file produces no differences at all.

## Deploying

The quest files live in the server's `system/` directory, which is a bind mount
on the host and is *not* refreshed by a new image — copy the three `.bin` files
to `system/quests/shops/` and the four Tower files to `system/quests/tower/` on
the host, then run `reload quests` (newserv's own README says `reload quest-index`, which this build rejects as an invalid data type). The server change needs a rebuilt
image; the quest changes alone do not.

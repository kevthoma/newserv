# Government quest item rewards

Six government quests give an item for clearing them:

| Quest | File | Stock "reward claimed" flag |
|---|---|---|
| 1-3 Subterranean Den | `government-ep1/q403` | `0x023A` |
| 2-4 Waterway Shadow | `government-ep1/q407` | `0x023B` |
| 3-3 Central Control | `government-ep1/q410` | `0x023C` |
| 5-5 Test/VR Temple 5 | `government-ep2/q455` | `0x023D` |
| 6-5 Test/Spaceship 5 | `government-ep2/q460` | `0x023E` |
| 7-5 Isle of Mutants | `government-ep2/q465` | `0x023F` |

The rest pay Meseta at the counter, or nothing. 9-2 (`q702`) also uses `item_create`,
but only for in-quest pickups.

## What was wrong

**Only the first player in a party got the item.** The reward routine marks the
claim with `gset`, which sends 6x75, which the server forwards to the whole party.
So the first player to collect sets the flag on every client in the game, and
everyone else is told they already have it. Seen on Coronet on 2026-10-02: three
players cleared 5-5 on Hard (`Setting quest flag Hard:021B` for all three within
21 s), one got the Gladius +10 (`Hard:023D`), and the other two have `021B` set
but `023D` unset in their `.psochar` files.

**You could hand the quest in without collecting.** The counter completes the
quest when `r255 == 1`, and `r255` is set by the boss conversation (the Principal,
the Chief, or the operator in 6-5). The item comes from a different NPC afterwards
(Irene, the assistant), so going straight to the counter skipped it.

## What the patch does

`patch_gov_reward.py`:

- Replaces every `gget`/`gset` of the reward flag with a read/write of local
  register `r160`. Registers belong to one client and are never forwarded, so
  each player tracks their own claim. They reset when the quest loads, so the
  item is paid **on every clear**, not once per character per difficulty.
- Replaces every `set r255` with a call to a new guard routine: call the reward
  routine, then set `r255` only if `r160` is now 1. Full inventory: the stock
  "you're already carrying too many items" line plays, `r255` stays 0, the
  counter won't accept the quest, and talking to the NPC again retries.
  Everything else the NPC does at that point (story flags, music, dialogue)
  still runs. Only `r255` waits.
- Changes the 5-5 Chief's "Get it from my assistant." to "Here it is." (English
  only), since he now hands it over himself. Nothing else needed rewording. The
  Principal's "speak to Irene for your reward" speech is already skipped once the
  claim register is set, and in 6-5 and 7-5 the item already comes from the NPC
  that sets `r255`.

The patch fails loudly if anything is off: the register is already in use, the
flag is still referenced afterwards, the counts don't match, or some
class × difficulty combination doesn't end in `item_create2`. That last check
matters because such a combination would block completion forever. Class 3
("no player / invalid class") is a bare `ret` in some quests, and that's allowed
because a player's own client ID can't return it.

The `.dat` files and the gating `.json` files are untouched.

## Re-applying

Start from the stock files: every `qNNN-bb-{e,j}.bin` of the six quests (12 scripts).

```bash
newserv disassemble-quest-script --bb --reassembly --language=E q455-bb-e.bin.orig q455-e.txt
python3 patch_gov_reward.py q455-e.txt q455-e-patched.txt
newserv assemble-quest-script q455-e-patched.txt q455-bb-e.bin
```

Then `reload quests` via `/y/shell-exec`. No restart and no image change: this is
quest data only.

## Residual risk

On BB, `item_create2` checks the inventory on the client, sends 6xCA, and returns
success right away. The server adds the item later and quietly drops it if
*its* copy of the inventory is full (`on_quest_create_item_bb`). If the client's
and server's inventories ever disagree, the player could be marked as paid
without getting the item. That isn't new, and it doesn't happen when they agree.

# Corellia: loads the current game's rare drop names into the table that EnemyHPBarsBB.s shows in enemy info windows.
# The server sends this on every game join and whenever the game's drop table changes (send_enemy_rare_table); the
# 0x1000-byte table is appended as suffix data. It does nothing (and returns 0) if EnemyHPBars isn't installed.

.meta name="Enemy rare table"
.meta description="Loads rare drop names for\nthe Enemy HP bars patch"

.versions 50YJ 59NJ 59NL

entry_ptr:
reloc0:
  .data     start

start:
  push      esi
  push      edi
  xor       eax, eax

  # Find EnemyHPBars' code by following its hook6 callsite; the table sits just before hook6, behind a magic word
  mov       edx, <VERS 0x0072B76C 0x00731FA8 0x00731F08>
  cmp       byte [edx], 0xE8
  jne       done
  mov       edi, [edx + 1]
  lea       edi, [edi + edx + 5]  # edi = hook6_update_window_text
  cmp       dword [edi - 4], 0x52524E43
  jne       done
  sub       edi, 0x1004  # edi = rare_table

  call      get_table_data_ret
get_table_data_ret:
  pop       esi
  lea       esi, [esi + (table_data - get_table_data_ret)]

  mov       ecx, 0x1000
copy_again:
  dec       ecx
  mov       al, [esi + ecx]
  mov       [edi + ecx], al
  test      ecx, ecx
  jnz       copy_again
  mov       eax, 1

done:
  pop       edi
  pop       esi
  ret

  # The server appends the table here (see the layout comment in EnemyHPBarsBB.s)
table_data:

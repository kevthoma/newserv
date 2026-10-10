.meta visibility="all"
.meta key="EnemyHPBars"
.meta name="Enemy HP bars"
.meta description="Shows HP bars and rare\ndrops in enemy info windows"

.versions 50YJ 59NJ 59NL

entry_ptr:
reloc0:
  .data   start

write_call_to_code_multi:
  .include  WriteCallToCodeMulti

start:
  push      edi
  push      0  # call count
  push      (hooks_end - hooks_start)  # code size
  call      hooks_end

hooks_start:
  .label    TBoss2DeRolLe_movement_data, <VERS 0x00A378C8 0x00A41848 0x00A43CC8>

get_enemy_hp_values:  # [/edi](TObjectV8047c128* enemy @ edi) -> current_hp @ eax, max_hp @ ecx, is_masked @ dl
  # Check if target is De Rol Le joint (segment)
  mov       eax, [edi + 4]  # eax = type name pointer

  xor       dl, dl

  cmp       eax, <VERS 0x00A379AC 0x00A4192C 0x00A43DAC>
  je        get_enemy_hp_values_target_is_de_rol_le_joint
  cmp       eax, <VERS 0x00A3B6EC 0x00A4568C 0x00A47B0C>
  je        get_enemy_hp_values_target_is_barba_ray_joint
  cmp       eax, <VERS 0x00A3792C 0x00A418AC 0x00A43D2C>
  je        get_enemy_hp_values_target_is_de_rol_le
  cmp       eax, <VERS 0x00A3B6D8 0x00A45678 0x00A47AF8>
  je        get_enemy_hp_values_target_is_barba_ray

  # If the target is not De Rol Le, Barba Ray, nor pieces thereof, then it uses the normal HP system; show those values
  movsx     ecx, word [edi + 0x02BC]  # max_hp
  movsx     eax, word [edi + 0x0334]  # current_hp
  jmp       get_enemy_hp_values_end

get_enemy_hp_values_target_is_de_rol_le_joint:
  # Check if shell (armor) is broken - if not, show the armor's remaining HP
  test      byte [edi + 0x0394], 0x01  # flags & 1 => shell is broken
  jnz       get_enemy_hp_values_de_rol_le_joint_shell_broken
  mov       eax, [edi + 0x039C]  # shell remaining HP
  mov       ecx, [TBoss2DeRolLe_movement_data]
  mov       ecx, [ecx + 0x1C]  # shell max HP (movement_data[0x0F]->iparam2)
  mov       dl, 1
  jmp       get_enemy_hp_values_end
get_enemy_hp_values_de_rol_le_joint_shell_broken:
  # If the shell is broken, show De Rol Le's HP instead, even if DRL's mask is intact (since the face isn't targeted)
  mov       edi, [edi + 0x14]  # enemy = enemy->parent
  jmp       get_enemy_hp_values_de_rol_le_mask_broken

get_enemy_hp_values_target_is_de_rol_le:
  # Check if mask (facial armor) is broken
  test      byte [edi + 0x03C8], 0x08  # flags & 8 => mask is broken
  jnz       get_enemy_hp_values_de_rol_le_mask_broken
  mov       eax, [edi + 0x06B8]  # mask remaining HP
  mov       ecx, [TBoss2DeRolLe_movement_data]
  mov       ecx, [ecx + 0x20]  # mask max HP (movement_data[0x0F]->iparam3)
  mov       dl, 1
  jmp       get_enemy_hp_values_end
get_enemy_hp_values_de_rol_le_mask_broken:
  # If the mask is broken, show De Rol Le's true HP
  mov       eax, [edi + 0x06B4]  # body_current_hp
  mov       ecx, [edi + 0x06B0]  # body_max_hp
  jmp       get_enemy_hp_values_end

get_enemy_hp_values_target_is_barba_ray_joint:
  # Check if shell (armor) is broken - if not, show the armor's remaining HP
  test      byte [edi + 0x03C4], 0x01  # flags & 1 => shell is broken
  jnz       get_enemy_hp_values_barba_ray_joint_shell_broken
  mov       eax, [edi + 0x03CC]  # shell remaining HP
  mov       ecx, [edi + 0x14]
  mov       ecx, [ecx + 0x0628]
  mov       ecx, [ecx + 0x1C]  # shell max HP (enemy->parent->movement_data->iparam2)
  mov       dl, 1
  jmp       get_enemy_hp_values_end
get_enemy_hp_values_barba_ray_joint_shell_broken:
  # If the shell is broken, show Barba Ray's HP instead, even if BR's mask is intact (since the face isn't targeted)
  mov       edi, [edi + 0x14]  # enemy = enemy->parent
  jmp       get_enemy_hp_values_barba_ray_mask_broken

get_enemy_hp_values_target_is_barba_ray:
  # Check if mask (facial armor) is broken
  test      byte [edi + 0x0630], 0x08  # flags & 8 => mask is broken
  jnz       get_enemy_hp_values_barba_ray_mask_broken
  mov       eax, [edi + 0x0708]  # mask remaining HP
  mov       ecx, [edi + 0x0628]
  mov       ecx, [ecx + 0x20]  # mask max HP (enemy->parent->movement_data->iparam3)
  mov       dl, 1
  jmp       get_enemy_hp_values_end
get_enemy_hp_values_barba_ray_mask_broken:
  # If the mask is broken, show Barba Ray's true HP
  mov       eax, [edi + 0x0704]  # body_current_hp
  mov       ecx, [edi + 0x0700]  # body_max_hp

get_enemy_hp_values_end:
  # When killed, De Rol Le's and Barba Ray's HP can go negative; this looks bad, so we max current_hp with 0 here
  xor       edi, edi
  cmp       eax, 0
  cmovl     eax, edi

  ret

get_rare_name:  # [/edi](TObjectV8047c128* enemy @ edi) -> const wchar_t* name @ eax (null if none)
  # Corellia: the server fills rare_table (below) with the current game's rare drop names; see EnemyRareTable.s
  call      get_rare_table_ret
get_rare_table_ret:
  pop       eax
  lea       eax, [eax + (rare_table - get_rare_table_ret)]
  mov       ecx, [edi + 0x0378]  # enemy->rt_index
  cmp       ecx, 0x70
  jae       get_rare_name_none
  movzx     ecx, word [eax + ecx * 2]  # offset of name from start of table; 0 = no rare
  test      ecx, ecx
  jz        get_rare_name_none
  add       eax, ecx
  ret
get_rare_name_none:
  xor       eax, eax
  ret

update_enemy_hp_text:  # [std](TObjectV8047c128* enemy @ eax, TWindowLockOn* window @ edx) -> char* text @ eax, int32_t max_hp @ ecx, int32_t current_hp @ edx
  push      edi
  push      esi
  push      ebx
  push      ebp
  mov       ebx, edx
  mov       edi, eax

  push      dword [edi + 0x0378]  # enemy->rt_index
  mov       esi, <VERS 0x0078CA14 0x00793E60 0x00793014>  # enemy_name_for_rt_index[std+0](uint32_t rt_index @ [esp + 4]) -> const char* name @ eax
  call      esi
  add       esp, 4
  mov       esi, eax

  # Corellia: look up the rare drop (ebp = name or null) and size the window for it; get_window_height reads this
  call      get_rare_name
  mov       ebp, eax
  mov       dword [ebx + 0x01B0], encode_float(125)
  test      ebp, ebp
  jz        update_enemy_hp_text_height_set
  mov       dword [ebx + 0x01B0], encode_float(165)
update_enemy_hp_text_height_set:

  call      get_enemy_hp_values
  push      ecx  # max hp
  push      eax  # current hp
  test      ebp, ebp
  jz        update_enemy_hp_text_no_rare_arg
  push      ebp  # rare item name (only consumed by rare_format_str)
update_enemy_hp_text_no_rare_arg:
  push      ecx  # max_hp
  push      eax  # current_hp
  call      get_shell_str_ret
shell_str:
  .binary   ' shell'0000
get_shell_str_ret:
  pop       eax
  lea       ecx, [eax + 0x0C]
  test      dl, dl
  cmovz     eax, ecx
  push      eax
  push      esi
  call      get_hp_format_str_ret
hp_format_str:
  .binary   '%s%s\n\nHP: %d / %d'0000
rare_format_str:
  # The Rare line is line 7: line 4 is the HP bar and line 5 is where the client draws status effect icons (Jellen,
  # Zalure, etc.; their positions are fixed when the window is created), which reach almost to line 6, so line 6 is
  # left blank as a gap. 0900 = tab, so `\tC6` is the client's color escape for yellow (the color it uses for rare item
  # names); it lasts to the end of the text, and this is the last line. hook9 relies on this line being the only one
  # that starts with a tab.
  .binary   '%s%s\n\nHP: %d / %d\n\n\n\n'0900'C6Rare Drop: %s'0000
get_hp_format_str_ret:
  pop       eax
  lea       ecx, [eax + (rare_format_str - hp_format_str)]
  test      ebp, ebp
  cmovnz    eax, ecx
  push      eax
  lea       esi, [ebx + 0x74]
  push      esi
  mov       eax, <VERS 0x0082C2F9 0x00835578 0x00857E29>  # swprintf[std+0](const wchar_t* fmt @ [esp+4], ... @ [esp+...]) -> uint32_t count @ eax
  call      eax
  add       esp, 0x18
  test      ebp, ebp
  jz        update_enemy_hp_text_no_rare_pop
  add       esp, 4
update_enemy_hp_text_no_rare_pop:

  mov       eax, esi  # text pointer
  pop       edx  # current hp
  pop       ecx  # max hp
  pop       ebp
  pop       ebx
  pop       esi
  pop       edi
  ret

get_window_height:  # [/ebp](TWindowLockOn* window @ ebp) -> float height @ eax
  # Only trust the two values update_enemy_hp_text writes; anything else means it hasn't run for this window yet
  mov       eax, [ebp + 0x01B0]
  cmp       eax, encode_float(165)
  je        get_window_height_done
  mov       eax, encode_float(125)
get_window_height_done:
  ret

hook7_init_window_height:  # 59NL:00731F2A; [ebp/](TWindowLockOn* window @ ebp); replaces `mov [ebp + 0x3C], 93.0`
  push      eax
  call      get_window_height
  mov       [ebp + 0x3C], eax
  pop       eax
  ret

hook8_update_window_height:  # 59NL:00731BA9; [ebp/](TWindowLockOn* window @ ebp) -> height @ st0
  # Replaces `fld [default_height]; mov [ebp + 0x3C], 93.0`; the caller positions the window from st0
  push      eax
  call      get_window_height
  mov       [ebp + 0x3C], eax
  pop       eax
  fld       st0, dword [ebp + 0x3C]
  ret

hook9_measure_window_text:  # 59NL:00731F20; [std](const wchar_t* text @ [esp + 4]) -> uint32_t width @ eax
  # The client sizes the window (and so the HP bar) by measuring the whole text as if it were one line. Keep that
  # measurement for everything above the Rare line, so windows look exactly as they do without it, and only widen the
  # window if the Rare line by itself is wider still.
  push      esi
  push      edi
  push      ebx
  mov       esi, [esp + 0x10]
  mov       edi, esi
hook9_find_rare_line:
  movzx     eax, word [edi]
  test      eax, eax
  jz        hook9_no_rare_line
  cmp       eax, 0x0A
  jne       hook9_next_char
  cmp       word [edi + 2], 0x09
  je        hook9_found_rare_line
hook9_next_char:
  add       edi, 2
  jmp       hook9_find_rare_line

hook9_found_rare_line:
  movzx     ebx, word [edi]
  mov       word [edi], 0  # Temporarily end the text before the Rare line
  push      esi
  call      hook9_call_measure_text
  add       esp, 4
  mov       [edi], bx
  mov       esi, eax  # esi = width of everything above the Rare line
  lea       eax, [edi + 2]
  push      eax
  call      hook9_call_measure_text
  add       esp, 4
  cmp       eax, esi
  cmovb     eax, esi
  jmp       hook9_done

hook9_no_rare_line:
  push      esi
  call      hook9_call_measure_text
  add       esp, 4
hook9_done:
  pop       ebx
  pop       edi
  pop       esi
  ret

hook9_call_measure_text:  # Jumps to the function hook9 replaced; its address is filled in when the patch is installed
  call      hook9_get_measure_text_ptr
hook9_get_measure_text_ptr:
  pop       eax
  jmp       [eax + (hook9_measure_text_fn - hook9_get_measure_text_ptr)]
hook9_measure_text_fn:
  .data     0

hook4_get_max_hp:  # 59NL:007318B7; [eax,ecx/](TWindowLockOn* window @ ebx, TObjectV8047c128* enemy @ eax) -> int32_t max_hp @ edx
  push      eax
  push      ecx
  mov       edx, ebx
  call      update_enemy_hp_text
  mov       edx, ecx
  pop       ecx
  pop       eax
  ret

hook5_get_current_hp:  # 59NL:007318C7; [eax,ecx/](TWindowLockOn* window @ ebx, TObjectV8047c128* enemy @ eax) -> int32_t current_hp @ edx
  push      eax
  push      ecx
  mov       edx, ebx
  call      update_enemy_hp_text
  pop       ecx
  pop       eax
  ret

  # Corellia: rare drop names for the current game, written by EnemyRareTable.s, which finds this table by following
  # hook6's callsite and checking rare_table_magic. Layout: uint16_t name_offset[0x70] (indexed by rt_index, 0 = no
  # rare), then the names themselves as null-terminated UTF-16. Must stay immediately before hook6.
rare_table:
  .zero     0x1000
rare_table_magic:
  .data     0x52524E43
hook6_update_window_text:  # 59NL:00731F08; [ecx/](TWindowLockOn* window @ ebp, TObjectV8047c128* enemy @ ecx) -> wchar_t* text @ eax
  push      ecx
  mov       eax, ecx
  mov       edx, ebp
  call      update_enemy_hp_text
  pop       ecx
  ret
hooks_end:

  call      write_call_to_code_multi
  mov       edi, eax

  mov       eax, <VERS 0x0072B11B 0x00731957 0x007318B7>  # hook4_get_max_hp_call
  mov       byte [eax], 0xE8
  lea       ecx, [edi + (hook4_get_max_hp - hooks_start + 5)]
  sub       ecx, eax
  mov       [eax + 1], ecx
  mov       word [eax + 5], 0x9090

  mov       eax, <VERS 0x0072B12B 0x00731967 0x007318C7>  # hook5_get_current_hp_call
  mov       byte [eax], 0xE8
  lea       ecx, [edi + (hook5_get_current_hp - hooks_start + 5)]
  sub       ecx, eax
  mov       [eax + 1], ecx
  mov       word [eax + 5], 0x9090

  mov       eax, <VERS 0x0072B76C 0x00731FA8 0x00731F08>  # hook6_update_window_text_call
  mov       byte [eax], 0xE8
  lea       ecx, [edi + (hook6_update_window_text - hooks_start + 5)]
  sub       ecx, eax
  mov       [eax + 1], ecx

  # Corellia: hook7/hook8 replace upstream's fixed 125.0 window height. Only the 59NL addresses have been checked
  # against a real binary; the other two are upstream's window_size_init/update addresses (and update - 6 for the
  # preceding fld), assuming the same instruction layout.
  mov       eax, <VERS 0x0072B78E 0x00731FCA 0x00731F2A>  # hook7: `mov [ebp + 0x3C], 93.0` (7 bytes)
  mov       byte [eax], 0xE8
  lea       ecx, [edi + (hook7_init_window_height - hooks_start + 5)]
  sub       ecx, eax
  mov       [eax + 1], ecx
  mov       word [eax + 5], 0x9090

  mov       eax, <VERS 0x0072B40D 0x00731C49 0x00731BA9>  # hook8: `fld [93.0]; mov [ebp + 0x3C], 93.0` (13 bytes)
  mov       byte [eax], 0xE8
  lea       ecx, [edi + (hook8_update_window_height - hooks_start + 5)]
  sub       ecx, eax
  mov       [eax + 1], ecx
  mov       dword [eax + 5], 0x90909090
  mov       dword [eax + 9], 0x90909090

  # hook9 replaces a call to the client's measure_text, so keep that call's target for hook9 to use. (The 59NJ and
  # 50YJ addresses are hook7's minus 0x0A, assuming the same layout; unverified.)
  mov       eax, <VERS 0x0072B784 0x00731FC0 0x00731F20>  # hook9: `call measure_text` (5 bytes)
  cmp       byte [eax], 0xE8
  jne       hook9_not_installed
  mov       ecx, [eax + 1]
  lea       ecx, [ecx + eax + 5]
  # (No +5 here: this assembler reads `a - b + 5` as `a - (b + 5)`, which is what the call targets above want since
  # they're relative to the end of the call opcode, but this is a plain data address)
  mov       [edi + (hook9_measure_text_fn - hooks_start)], ecx
  lea       ecx, [edi + (hook9_measure_window_text - hooks_start + 5)]
  sub       ecx, eax
  mov       [eax + 1], ecx
hook9_not_installed:

  pop       edi
  .include  WriteCodeBlocks

  # Clear window item flag that suppresses HP bar
  .label    flag_clear_patch, <VERS 0x0072B141 0x0073197D 0x007318DD>
  .data     flag_clear_patch
  .data     6
  .address  flag_clear_patch
  and       edx, 0xFFFFFFFD

  # Make TWindowLockOn 0x140 bytes bigger (Corellia; upstream adds 0x80): 0x74-0x1AF is the string buffer (158
  # wchar_ts, enough for the extra Rare line) and 0x1B0 is the window height chosen by update_enemy_hp_text
  .label    TWindowLockOn_size_load, <VERS 0x0072B4A8 0x00731CE4 0x00731C44>
  .data     TWindowLockOn_size_load
  .data     9
  .address  TWindowLockOn_size_load
  push      0x1B4  # Originally `push 0x74`; deleted a preceding opcode, which writes a value which seemingly isn't used
  nop
  nop
  nop
  nop

  # Update window size (Corellia: the per-window height itself is set by hook7 and hook8 above, so it can grow by a
  # line when there's a rare drop to show)
  .data     <VERS 0x009649F8 0x0096F098 0x009710B8>
  .data     4
  .data     encode_float(125)

  # Status effect icon row (4 slots). Upstream puts it at 75; Corellia uses 82 so that, with the Rare line two lines
  # below the HP bar, the icons sit centered between the bar and the Rare line (measured in game)
  .data     <VERS 0x009E6D84 0x009F0DA4 0x009F2DA4>
  .data     0x00000004
  .data     encode_float(82)

  .data     <VERS 0x009E6DB4 0x009F0DD4 0x009F2DD4>
  .data     0x00000004
  .data     encode_float(82)

  .data     <VERS 0x009E6DE4 0x009F0E04 0x009F2E04>
  .data     0x00000004
  .data     encode_float(82)

  .data     <VERS 0x009E6E14 0x009F0E34 0x009F2E34>
  .data     0x00000004
  .data     encode_float(82)

  .data     <VERS 0x009E6E44 0x009F0E64 0x009F2E64>
  .data     0x00000004
  .data     encode_float(62)

  .data     <VERS 0x009E6E60 0x009F0E80 0x009F2E80>
  .data     0x00000004
  .data     0xFF00FF15

  .data     0x00000000
  .data     0x00000000

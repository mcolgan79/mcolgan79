extends Node
class_name TurnManager

enum Phase { PLAYER, ENEMY }
enum State { PLAYER_SELECT, PLAYER_MOVE, PLAYER_ACT, ENEMY_TURN, BATTLE_END }

signal phase_changed(phase: int)
signal state_changed(state: int)
signal action_logged(msg: String)
signal battle_ended(winner: int)

var current_phase: Phase = Phase.PLAYER
var current_state: State = State.PLAYER_SELECT
var selected_char: Character = null
var turn_count: int = 1
var grid: BattleGrid = null

var _move_tiles: Array = []
var _attack_tiles: Array = []

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

func setup(battle_grid: BattleGrid) -> void:
	grid = battle_grid
	grid.tile_selected.connect(_on_tile_clicked)
	_set_state(State.PLAYER_SELECT)
	action_logged.emit("=== Battle Start!  Player Phase — Turn 1 ===")

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

func _set_state(new_state: State) -> void:
	current_state = new_state
	state_changed.emit(new_state)
	if new_state == State.PLAYER_SELECT:
		_deselect()
		grid.clear_highlights()

func _deselect() -> void:
	if selected_char:
		selected_char.is_selected = false
		selected_char.refresh_visuals()
		selected_char = null

func _on_tile_clicked(tile: GridTile) -> void:
	if current_state == State.ENEMY_TURN or current_state == State.BATTLE_END:
		return
	match current_state:
		State.PLAYER_SELECT: _handle_select(tile)
		State.PLAYER_MOVE:   _handle_move(tile)
		State.PLAYER_ACT:    _handle_act(tile)

# ---------------------------------------------------------------------------
# Player actions
# ---------------------------------------------------------------------------

func _handle_select(tile: GridTile) -> void:
	var occ := tile.occupant as Character
	if occ == null or occ.stats.team != 0 or not occ.is_alive():
		return
	if not occ.can_move() and not occ.can_act():
		action_logged.emit(occ.stats.character_name + " has already acted this turn.")
		return
	_select(occ)

func _select(char: Character) -> void:
	_deselect()
	selected_char      = char
	char.is_selected   = true
	char.refresh_visuals()
	grid.clear_highlights()
	grid.highlight_tiles([char.grid_pos], "selected")

	if char.can_move():
		_move_tiles = grid.get_movement_range(char)
		grid.highlight_tiles(_move_tiles, "move")
		_set_state(State.PLAYER_MOVE)
		action_logged.emit(char.stats.character_name + " selected — click blue tile to move, or own tile to stay.")
	else:
		_show_attack_tiles()
		_set_state(State.PLAYER_ACT)
		action_logged.emit(char.stats.character_name + " — choose action (red=attack, own tile=wait).")

func _show_attack_tiles() -> void:
	_attack_tiles = grid.get_attack_range(selected_char)
	grid.highlight_tiles(_attack_tiles, "attack")

func _handle_move(tile: GridTile) -> void:
	if selected_char == null:
		_set_state(State.PLAYER_SELECT)
		return

	# Clicked own tile → stay, skip to act
	if tile.grid_pos == selected_char.grid_pos:
		selected_char.has_moved = true
		selected_char.refresh_visuals()
		grid.clear_highlights()
		grid.highlight_tiles([selected_char.grid_pos], "selected")
		_show_attack_tiles()
		_set_state(State.PLAYER_ACT)
		action_logged.emit(selected_char.stats.character_name + " stayed — choose action.")
		return

	if tile.grid_pos in _move_tiles:
		var cname := selected_char.stats.character_name
		grid.move_character(selected_char, tile.grid_pos)
		grid.clear_highlights()
		grid.highlight_tiles([selected_char.grid_pos], "selected")
		_show_attack_tiles()
		_set_state(State.PLAYER_ACT)
		action_logged.emit(cname + " moved — choose action (red=attack, own tile=wait).")
	else:
		_set_state(State.PLAYER_SELECT)

func _handle_act(tile: GridTile) -> void:
	if selected_char == null:
		_set_state(State.PLAYER_SELECT)
		return

	# Clicked own tile → wait
	if tile.grid_pos == selected_char.grid_pos:
		selected_char.has_acted = true
		selected_char.refresh_visuals()
		action_logged.emit(selected_char.stats.character_name + " waited.")
		_after_action()
		return

	# Clicked an attack target
	if tile.grid_pos in _attack_tiles:
		var defender := tile.occupant as Character
		if defender and defender.stats.team != selected_char.stats.team:
			_do_attack(selected_char, defender)
			selected_char.has_acted = true
			selected_char.refresh_visuals()
			if not defender.is_alive():
				action_logged.emit(defender.stats.character_name + " was defeated!")
				grid.remove_character(defender)
				_check_end()
				if current_state == State.BATTLE_END:
					return
			_after_action()
			return

	# Clicked somewhere invalid → back to select
	_set_state(State.PLAYER_SELECT)

func _do_attack(attacker: Character, defender: Character) -> void:
	var dmg := defender.take_damage(attacker.stats.atk)
	action_logged.emit(
		attacker.stats.character_name + " → " + defender.stats.character_name +
		"  [" + str(dmg) + " dmg | " + str(defender.stats.current_hp) + " HP left]"
	)

func _after_action() -> void:
	var all_done := true
	for c in grid.get_team(0):
		var ch := c as Character
		if ch.can_move() or ch.can_act():
			all_done = false
			break
	if all_done:
		_start_enemy_phase()
	else:
		_set_state(State.PLAYER_SELECT)

# ---------------------------------------------------------------------------
# Enemy AI phase
# ---------------------------------------------------------------------------

func _start_enemy_phase() -> void:
	current_phase = Phase.ENEMY
	_set_state(State.ENEMY_TURN)
	phase_changed.emit(Phase.ENEMY)
	action_logged.emit("--- Enemy Phase ---")
	await get_tree().process_frame
	_run_enemy_ai()

func _run_enemy_ai() -> void:
	for c in grid.get_team(1).duplicate():
		var enemy := c as Character
		if not enemy.is_alive():
			continue

		var targets := grid.get_team(0)
		if targets.is_empty():
			break

		var nearest := _nearest(enemy, targets)
		var atk_range := grid.get_attack_range(enemy)

		if nearest.grid_pos in atk_range:
			_do_attack(enemy, nearest)
			if not nearest.is_alive():
				action_logged.emit(nearest.stats.character_name + " was defeated!")
				grid.remove_character(nearest)
				_check_end()
				if current_state == State.BATTLE_END:
					return
		else:
			# Move toward nearest player
			var move_range := grid.get_movement_range(enemy)
			if not move_range.is_empty():
				var best := _closest_to(move_range, nearest.grid_pos)
				grid.move_character(enemy, best)

			# Re-evaluate attack after moving
			targets = grid.get_team(0)
			if targets.is_empty():
				break
			nearest   = _nearest(enemy, targets)
			atk_range = grid.get_attack_range(enemy)
			if nearest.grid_pos in atk_range:
				_do_attack(enemy, nearest)
				if not nearest.is_alive():
					action_logged.emit(nearest.stats.character_name + " was defeated!")
					grid.remove_character(nearest)
					_check_end()
					if current_state == State.BATTLE_END:
						return

		action_logged.emit(enemy.stats.character_name + " finished turn.")

	_end_enemy_phase()

func _nearest(from: Character, targets: Array) -> Character:
	var best: Character = targets[0]
	var min_d: int = from.grid_pos.distance_squared_to(best.grid_pos)
	for t in targets:
		var ch := t as Character
		var d: int = from.grid_pos.distance_squared_to(ch.grid_pos)
		if d < min_d:
			min_d = d
			best  = ch
	return best

func _closest_to(tiles: Array, target: Vector2i) -> Vector2i:
	var best: Vector2i = tiles[0]
	var min_d: int = best.distance_squared_to(target)
	for t in tiles:
		var tp: Vector2i = t
		var d: int = tp.distance_squared_to(target)
		if d < min_d:
			min_d = d
			best  = tp
	return best

func _end_enemy_phase() -> void:
	turn_count += 1
	for c in grid.characters:
		(c as Character).reset_turn()
	current_phase = Phase.PLAYER
	phase_changed.emit(Phase.PLAYER)
	action_logged.emit("=== Player Phase — Turn " + str(turn_count) + " ===")
	_set_state(State.PLAYER_SELECT)

# ---------------------------------------------------------------------------
# Win / lose check
# ---------------------------------------------------------------------------

func _check_end() -> void:
	if grid.get_team(0).is_empty():
		_set_state(State.BATTLE_END)
		battle_ended.emit(1)
		action_logged.emit("GAME OVER — Enemies Win!")
	elif grid.get_team(1).is_empty():
		_set_state(State.BATTLE_END)
		battle_ended.emit(0)
		action_logged.emit("VICTORY — Players Win!")

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

func force_end_player_turn() -> void:
	if current_state == State.BATTLE_END:
		return
	for c in grid.get_team(0):
		var ch := c as Character
		ch.has_moved = true
		ch.has_acted = true
		ch.refresh_visuals()
	_start_enemy_phase()

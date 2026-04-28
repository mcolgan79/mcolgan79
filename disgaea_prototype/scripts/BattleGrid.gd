extends Node2D
class_name BattleGrid

signal tile_selected(tile: GridTile)

const TILE_SIZE   := 60
const GRID_OFFSET := Vector2(210, 120)

var grid_width: int = 10
var grid_height: int = 8
var tiles: Dictionary = {}
var characters: Array = []

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

func initialize(width: int, height: int) -> void:
	grid_width  = width
	grid_height = height
	for y in range(height):
		for x in range(width):
			var gpos := Vector2i(x, y)
			var tile := GridTile.new()
			tile.grid_pos = gpos
			tile.position = grid_to_world(gpos)
			tiles[gpos]   = tile
			add_child(tile)

# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

func grid_to_world(gpos: Vector2i) -> Vector2:
	return GRID_OFFSET + Vector2(gpos.x * TILE_SIZE, gpos.y * TILE_SIZE)

func world_to_grid(wpos: Vector2) -> Vector2i:
	var rel := wpos - GRID_OFFSET
	return Vector2i(
		floori((rel.x + TILE_SIZE * 0.5) / TILE_SIZE),
		floori((rel.y + TILE_SIZE * 0.5) / TILE_SIZE)
	)

func get_tile(gpos: Vector2i) -> GridTile:
	return tiles.get(gpos, null)

func is_valid_pos(gpos: Vector2i) -> bool:
	return gpos.x >= 0 and gpos.x < grid_width and gpos.y >= 0 and gpos.y < grid_height

# ---------------------------------------------------------------------------
# Character management
# ---------------------------------------------------------------------------

func add_character(character: Character, gpos: Vector2i) -> void:
	if not is_valid_pos(gpos):
		return
	var tile := get_tile(gpos)
	if tile == null or tile.occupant != null:
		return
	character.grid_pos  = gpos
	character.position  = grid_to_world(gpos)
	tile.occupant       = character
	characters.append(character)
	add_child(character)

func move_character(character: Character, target: Vector2i) -> void:
	var old_tile := get_tile(character.grid_pos)
	if old_tile:
		old_tile.occupant = null
	character.grid_pos = target
	character.position = grid_to_world(target)
	var new_tile := get_tile(target)
	if new_tile:
		new_tile.occupant = character
	character.has_moved = true
	character.refresh_visuals()

func remove_character(character: Character) -> void:
	var tile := get_tile(character.grid_pos)
	if tile:
		tile.occupant = null
	characters.erase(character)
	character.queue_free()

func get_team(team: int) -> Array:
	var out: Array = []
	for c in characters:
		if (c as Character).stats.team == team:
			out.append(c)
	return out

# ---------------------------------------------------------------------------
# Range calculations
# ---------------------------------------------------------------------------

func get_movement_range(character: Character) -> Array:
	var result: Array = []
	var mov    := character.stats.mov
	var visited: Dictionary = {}
	var queue: Array = [[character.grid_pos, 0]]
	visited[character.grid_pos] = true

	while not queue.is_empty():
		var entry: Array = queue.pop_front()
		var pos: Vector2i = entry[0]
		var dist: int     = entry[1]

		if dist > 0:
			result.append(pos)

		if dist < mov:
			for nb in _neighbors(pos):
				if not visited.has(nb):
					var t := get_tile(nb)
					if t and t.is_walkable():
						visited[nb] = true
						queue.append([nb, dist + 1])

	return result

func get_attack_range(character: Character) -> Array:
	var result: Array = []
	for nb in _neighbors(character.grid_pos):
		var t := get_tile(nb)
		if t and t.occupant is Character:
			var occ := t.occupant as Character
			if occ.stats.team != character.stats.team:
				result.append(nb)
	return result

func _neighbors(pos: Vector2i) -> Array:
	var out: Array = []
	for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
		var n := pos + d
		if is_valid_pos(n):
			out.append(n)
	return out

# ---------------------------------------------------------------------------
# Highlight helpers
# ---------------------------------------------------------------------------

func clear_highlights() -> void:
	for tile in tiles.values():
		tile.set_highlight("")

func highlight_tiles(positions: Array, state: String) -> void:
	for pos in positions:
		var t := get_tile(pos)
		if t:
			t.set_highlight(state)

# ---------------------------------------------------------------------------
# Input — handles mouse + touch for mobile/web portability
# ---------------------------------------------------------------------------

func _unhandled_input(event: InputEvent) -> void:
	var clicked := false
	if event is InputEventMouseButton:
		if event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
			clicked = true
	elif event is InputEventScreenTouch:
		if event.pressed:
			clicked = true

	if not clicked:
		return

	var gpos := world_to_grid(get_global_mouse_position())
	if is_valid_pos(gpos):
		var tile := get_tile(gpos)
		if tile:
			tile_selected.emit(tile)

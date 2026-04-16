extends Node2D

var grid: BattleGrid
var turns: TurnManager

var _phase_label: Label
var _state_label: Label
var _char_info: Label
var _log: RichTextLabel
var _end_btn: Button

func _ready() -> void:
	_build_battle()
	_build_ui()
	turns.setup(grid)

# ---------------------------------------------------------------------------
# Battle setup
# ---------------------------------------------------------------------------

func _build_battle() -> void:
	grid = BattleGrid.new()
	add_child(grid)
	grid.initialize(10, 8)

	# Scatter some wall tiles to create terrain variety
	for pos in [Vector2i(3,2), Vector2i(3,3), Vector2i(3,4), Vector2i(6,4), Vector2i(6,5), Vector2i(5,1)]:
		var t := grid.get_tile(pos)
		if t:
			t.tile_type = GridTile.TileType.WALL
			t.refresh_visuals()

	# Player team (blue)
	_add_char("Warrior", 0, Vector2i(1, 2), 120, 15, 8,  4)
	_add_char("Mage",    0, Vector2i(1, 4),  70, 18, 3,  4)
	_add_char("Cleric",  0, Vector2i(1, 6),  90, 10, 6,  4)

	# Enemy team (red)
	_add_char("Zombie",  1, Vector2i(8, 2),  80, 12, 6,  2)
	_add_char("Imp",     1, Vector2i(8, 4),  65, 14, 3,  5)
	_add_char("Ogre",    1, Vector2i(7, 6), 180, 20, 14, 2)

	turns = TurnManager.new()
	add_child(turns)

func _add_char(cname: String, team: int, pos: Vector2i,
               hp: int, atk: int, def_val: int, mov: int) -> void:
	var s := CharacterStats.new()
	s.character_name = cname
	s.max_hp         = hp
	s.current_hp     = hp
	s.atk            = atk
	s.def            = def_val
	s.mov            = mov
	s.team           = team
	var c := Character.new()
	c.stats = s
	grid.add_character(c, pos)

# ---------------------------------------------------------------------------
# UI construction
# ---------------------------------------------------------------------------

func _build_ui() -> void:
	var ui := CanvasLayer.new()
	add_child(ui)

	# Sidebar panel
	var bg := ColorRect.new()
	bg.color    = Color(0.08, 0.08, 0.12, 0.96)
	bg.size     = Vector2(250, 720)
	bg.position = Vector2(1030, 0)
	ui.add_child(bg)

	_phase_label = _label(ui, "PLAYER PHASE", Vector2(1035, 14), 20, 240)
	_phase_label.add_theme_color_override("font_color", Color(0.5, 0.7, 1.0))

	var div := ColorRect.new()
	div.color    = Color(0.35, 0.35, 0.50)
	div.size     = Vector2(240, 1)
	div.position = Vector2(1035, 52)
	ui.add_child(div)

	_state_label = _label(ui, "Click a unit to select", Vector2(1035, 60), 11, 240)
	_state_label.add_theme_color_override("font_color", Color(0.80, 0.80, 0.55))

	_char_info = _label(ui, "", Vector2(1035, 88), 11, 240)
	_char_info.autowrap_mode = TextServer.AUTOWRAP_WORD

	_label(ui, "Battle Log:", Vector2(1035, 190), 11, 240)

	_log = RichTextLabel.new()
	_log.position        = Vector2(1035, 210)
	_log.size            = Vector2(240, 390)
	_log.scroll_following = true
	_log.bbcode_enabled  = true
	_log.add_theme_font_size_override("normal_font_size", 10)
	ui.add_child(_log)

	_end_btn = Button.new()
	_end_btn.text     = "End Turn"
	_end_btn.position = Vector2(1035, 632)
	_end_btn.size     = Vector2(240, 40)
	_end_btn.pressed.connect(_on_end_turn)
	ui.add_child(_end_btn)

	# Bottom legend (main canvas, not sidebar)
	var leg := _label(ui,
		"[Blue]=Player  [Red]=Enemy  [Yellow]=Selected  [Blue tile]=Move range  [Red tile]=Attack range\n" +
		"Click unit → select | Click blue tile → move | Click red tile → attack | Click own tile → stay/wait",
		Vector2(8, 682), 9, 1020)
	leg.add_theme_color_override("font_color", Color(0.65, 0.65, 0.65))
	leg.autowrap_mode = TextServer.AUTOWRAP_WORD

	# Wire signals
	turns.phase_changed.connect(_on_phase)
	turns.state_changed.connect(_on_state)
	turns.action_logged.connect(_on_log)
	turns.battle_ended.connect(_on_end)

func _label(parent: Node, text: String, pos: Vector2, font_size: int, width: int = 0) -> Label:
	var lbl := Label.new()
	lbl.text     = text
	lbl.position = pos
	if width > 0:
		lbl.size = Vector2(width, 0)
	lbl.add_theme_font_size_override("font_size", font_size)
	parent.add_child(lbl)
	return lbl

# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------

func _on_phase(phase: int) -> void:
	if phase == TurnManager.Phase.PLAYER:
		_phase_label.text = "PLAYER PHASE"
		_phase_label.add_theme_color_override("font_color", Color(0.5, 0.7, 1.0))
		_end_btn.disabled = false
	else:
		_phase_label.text = "ENEMY PHASE"
		_phase_label.add_theme_color_override("font_color", Color(1.0, 0.5, 0.4))
		_end_btn.disabled = true

func _on_state(_state: int) -> void:
	match _state:
		TurnManager.State.PLAYER_SELECT: _state_label.text = "Select a unit"
		TurnManager.State.PLAYER_MOVE:   _state_label.text = "Choose where to move"
		TurnManager.State.PLAYER_ACT:    _state_label.text = "Choose action"
		TurnManager.State.ENEMY_TURN:    _state_label.text = "Enemy is acting…"
		TurnManager.State.BATTLE_END:    _state_label.text = "Battle over"

	if turns.selected_char:
		var c := turns.selected_char
		var s := c.stats
		_char_info.text = (
			"[" + s.character_name + "]\n" +
			"HP: %d / %d\n" % [s.current_hp, s.max_hp] +
			"ATK:%d  DEF:%d  MOV:%d\n" % [s.atk, s.def, s.mov] +
			("Moved" if c.has_moved else "Can move") + " · " +
			("Acted" if c.has_acted else "Can act")
		)
	else:
		_char_info.text = ""

func _on_log(msg: String) -> void:
	_log.append_text(msg + "\n")

func _on_end(winner: int) -> void:
	_end_btn.disabled = true
	if winner == 0:
		_phase_label.text = "VICTORY!"
		_phase_label.add_theme_color_override("font_color", Color(0.3, 1.0, 0.3))
	else:
		_phase_label.text = "DEFEAT!"
		_phase_label.add_theme_color_override("font_color", Color(1.0, 0.3, 0.3))

func _on_end_turn() -> void:
	turns.force_end_player_turn()

extends Node2D
class_name Character

signal stats_changed(character: Character)
signal died(character: Character)

const DRAW_SIZE := 44

var stats: CharacterStats = null
var grid_pos: Vector2i = Vector2i.ZERO
var has_moved: bool = false
var has_acted: bool = false
var is_selected: bool = false

var _body: ColorRect
var _hp_fill: ColorRect
var _name_label: Label

const TEAM_COLORS: Array = [Color(0.25, 0.45, 0.90), Color(0.90, 0.25, 0.25)]

func _ready() -> void:
	if not stats:
		stats = CharacterStats.new()
	z_index = 1
	_build_visuals()

func _build_visuals() -> void:
	var half: float = DRAW_SIZE * 0.5

	_body = ColorRect.new()
	_body.size = Vector2(DRAW_SIZE, DRAW_SIZE)
	_body.position = Vector2(-half, -half)
	add_child(_body)

	_name_label = Label.new()
	_name_label.text = stats.character_name
	_name_label.size = Vector2(64, 14)
	_name_label.position = Vector2(-32, -half - 16)
	_name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_name_label.add_theme_font_size_override("font_size", 9)
	add_child(_name_label)

	var hp_bg := ColorRect.new()
	hp_bg.size = Vector2(DRAW_SIZE, 5)
	hp_bg.position = Vector2(-half, half + 2)
	hp_bg.color = Color(0.15, 0.0, 0.0)
	add_child(hp_bg)

	_hp_fill = ColorRect.new()
	_hp_fill.size = Vector2(DRAW_SIZE, 5)
	_hp_fill.position = Vector2(-half, half + 2)
	_hp_fill.color = Color(0.1, 0.9, 0.1)
	add_child(_hp_fill)

	refresh_visuals()

func refresh_visuals() -> void:
	if not _body:
		return
	var base: Color = TEAM_COLORS[clamp(stats.team, 0, 1)]
	if has_moved and has_acted:
		base = base.darkened(0.55)
	elif has_moved or has_acted:
		base = base.darkened(0.28)
	if is_selected:
		base = base.lightened(0.3)
	_body.color = base

	var ratio := float(stats.current_hp) / float(stats.max_hp)
	_hp_fill.size.x = DRAW_SIZE * ratio
	if ratio > 0.5:
		_hp_fill.color = Color(0.1, 0.9, 0.1)
	elif ratio > 0.25:
		_hp_fill.color = Color(0.9, 0.9, 0.1)
	else:
		_hp_fill.color = Color(0.9, 0.1, 0.1)

func take_damage(amount: int) -> int:
	var dmg := max(1, amount - stats.def)
	stats.current_hp = max(0, stats.current_hp - dmg)
	refresh_visuals()
	stats_changed.emit(self)
	if stats.current_hp <= 0:
		died.emit(self)
	return dmg

func is_alive() -> bool:
	return stats.current_hp > 0

func can_move() -> bool:
	return not has_moved and is_alive()

func can_act() -> bool:
	return not has_acted and is_alive()

func reset_turn() -> void:
	has_moved = false
	has_acted = false
	refresh_visuals()

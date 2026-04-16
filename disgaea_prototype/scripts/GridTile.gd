extends Node2D
class_name GridTile

enum TileType { FLOOR, WALL, WATER }

const TILE_SIZE    := 60
const DRAW_SIZE    := 58

var tile_type: TileType = TileType.FLOOR
var elevation: int = 0
var grid_pos: Vector2i = Vector2i.ZERO
var occupant: Node = null
var highlight_state: String = ""

var _rect: ColorRect
var _label: Label

func _ready() -> void:
	_rect = ColorRect.new()
	_rect.size = Vector2(DRAW_SIZE, DRAW_SIZE)
	_rect.position = Vector2(-DRAW_SIZE * 0.5, -DRAW_SIZE * 0.5)
	add_child(_rect)

	_label = Label.new()
	_label.size = Vector2(DRAW_SIZE, DRAW_SIZE * 0.5)
	_label.position = Vector2(-DRAW_SIZE * 0.5, DRAW_SIZE * 0.25)
	_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_label.add_theme_font_size_override("font_size", 9)
	add_child(_label)

	refresh_visuals()

func set_highlight(state: String) -> void:
	highlight_state = state
	refresh_visuals()

func refresh_visuals() -> void:
	if not _rect:
		return
	match highlight_state:
		"move":     _rect.color = Color(0.20, 0.55, 1.00, 0.75)
		"attack":   _rect.color = Color(1.00, 0.25, 0.20, 0.75)
		"selected": _rect.color = Color(1.00, 0.85, 0.15, 0.85)
		_:          _rect.color = _base_color()
	if _label:
		_label.text = "^" + str(elevation) if elevation > 0 else ""

func _base_color() -> Color:
	match tile_type:
		TileType.WALL:  return Color(0.18, 0.10, 0.10)
		TileType.WATER: return Color(0.10, 0.25, 0.58)
		_:              return Color(0.25, 0.28, 0.45)

func is_walkable() -> bool:
	return tile_type == TileType.FLOOR and occupant == null

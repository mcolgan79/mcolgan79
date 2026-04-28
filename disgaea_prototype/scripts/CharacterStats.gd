extends Resource
class_name CharacterStats

@export var character_name: String = "Unknown"
@export var max_hp: int = 100
@export var current_hp: int = 100
@export var atk: int = 10
@export var def: int = 5
@export var spd: int = 10
@export var mov: int = 3
@export var jump: int = 3
@export var team: int = 0  # 0 = player, 1 = enemy

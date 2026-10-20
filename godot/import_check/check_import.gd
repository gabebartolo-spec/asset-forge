extends SceneTree
# Headless check of a .glb as a game project imports it (the editor import, which reads the
# <name>.glb.import sidecar). Run from a scratch project that already ran `--import`:
#   godot --headless --path <project> --script res://check_import.gd -- res://<name>.glb idle=1 ...
# Each name=mode pair is a clip and the loop mode it must have after import (0 none, 1 loop).
# Prints LOOP_CHECK_OK when every clip is there with its loop mode; IMPORT_CHECK_FAIL if not.


func _fail(msg: String) -> void:
	printerr("IMPORT_CHECK_FAIL: " + msg)
	quit(1)


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 1:
		_fail("expected a res:// path")
		return
	var ps := load(args[0]) as PackedScene
	if ps == null:
		_fail("the imported scene could not be loaded")
		return
	var root := ps.instantiate()
	var modes := {}
	for n in root.find_children("*", "AnimationPlayer", true, false):
		var ap := n as AnimationPlayer
		for a in ap.get_animation_list():
			modes[String(a)] = ap.get_animation(a).loop_mode
	root.free()
	var bad: Array[String] = []
	var looping: Array[String] = []
	for i in range(1, args.size()):
		var kv := args[i].split("=")
		var want := int(kv[1])
		if not modes.has(kv[0]):
			bad.append("%s is missing" % kv[0])
		elif modes[kv[0]] != want:
			bad.append("%s has loop mode %d, expected %d" % [kv[0], modes[kv[0]], want])
		elif want != 0:
			looping.append(kv[0])
	if not bad.is_empty():
		_fail(", ".join(bad))
		return
	print("LOOP_CHECK_OK clips=%d looping=%s" % [modes.size(), ",".join(looping)])
	quit(0)

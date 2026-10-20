extends SceneTree
# Headless rig check. Usage:
#   godot --headless --path godot/import_check --script check_skeleton.gd -- <rigged.glb> [humanoid]
# Prints RIG_CHECK_OK when the .glb imports with one skeleton, a skinned mesh using at most 4
# bone weights per vertex and at most 64 bones. With "humanoid" it also builds a BoneMap against
# SkeletonProfileHumanoid and prints which profile bones the skeleton fills. Engine ERROR or
# WARNING lines are failures too (the Python wrapper reads them).


func _fail(msg: String) -> void:
	printerr("RIG_CHECK_FAIL: " + msg)
	quit(1)


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 1:
		_fail("expected a .glb path")
		return
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if doc.append_from_file(args[0], state) != OK:
		_fail("could not read the file")
		return
	var root := doc.generate_scene(state)
	if root == null:
		_fail("no scene was built from the file")
		return
	var skels := root.find_children("*", "Skeleton3D", true, false)
	if skels.size() != 1:
		_fail("expected one skeleton, found %d" % skels.size())
		return
	var skel: Skeleton3D = skels[0]
	if skel.get_bone_count() > 64:
		_fail("%d bones is over the 64 limit" % skel.get_bone_count())
		return
	var skinned := 0
	var eight := 0
	for mi in root.find_children("*", "MeshInstance3D", true, false):
		var m: Mesh = (mi as MeshInstance3D).mesh
		if m == null:
			continue
		for s in m.get_surface_count():
			if m.surface_get_format(s) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS:
				eight += 1
			if m.surface_get_format(s) & Mesh.ARRAY_FORMAT_BONES:
				skinned += 1
	if skinned == 0:
		_fail("no skinned mesh surface")
		return
	if eight > 0:
		_fail("a surface uses more than 4 bone weights per vertex")
		return
	var anims := 0
	for n in root.find_children("*", "AnimationPlayer", true, false):
		anims += (n as AnimationPlayer).get_animation_list().size()
	var line := "RIG_CHECK_OK bones=%d skinned_surfaces=%d animations=%d" % [
		skel.get_bone_count(), skinned, anims]
	if args.size() > 1 and args[1] == "humanoid":
		var profile := SkeletonProfileHumanoid.new()
		var bmap := BoneMap.new()
		bmap.profile = profile
		var filled := 0
		var required_missing: Array[String] = []
		var optional_missing: Array[String] = []
		for i in profile.bone_size:
			var pname: String = profile.get_bone_name(i)
			if skel.find_bone(pname) >= 0:
				bmap.set_skeleton_bone_name(pname, pname)
				filled += 1
			elif profile.is_required(i):
				required_missing.append(pname)
			else:
				optional_missing.append(pname)
		line += " profile_bones=%d filled=%d required_missing=%s optional_missing=%d" % [
			profile.bone_size, filled, str(required_missing), optional_missing.size()]
		if not required_missing.is_empty():
			_fail("profile bones missing: " + str(required_missing))
			return
		print("OPTIONAL_UNMAPPED " + str(optional_missing))
	print(line)
	root.free()
	quit(0)

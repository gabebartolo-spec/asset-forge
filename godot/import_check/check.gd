extends SceneTree
# Headless import check. Usage:
#   godot --headless --path godot/import_check --script check.gd -- <file.glb>
# Exits 0 only when the .glb parses and builds a scene. Any engine ERROR or WARNING
# line in the output is also treated as a failure by the Python wrapper.


func _fail(msg: String) -> void:
	printerr("IMPORT_CHECK_FAIL: " + msg)
	quit(1)


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1:
		_fail("expected exactly one .glb path")
		return
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_file(args[0], state)
	if err != OK:
		_fail("could not read the file (error %d)" % err)
		return
	var root := doc.generate_scene(state)
	if root == null:
		_fail("no scene was built from the file")
		return
	var meshes := 0
	var skeletons := 0
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is MeshInstance3D:
			meshes += 1
		if n is Skeleton3D:
			skeletons += 1
		stack.append_array(n.get_children())
	if meshes == 0:
		_fail("the file has no mesh")
		return
	var anims := 0
	for n in root.find_children("*", "AnimationPlayer", true, false):
		anims += (n as AnimationPlayer).get_animation_list().size()
	print("IMPORT_CHECK_OK meshes=%d skeletons=%d animations=%d" % [meshes, skeletons, anims])
	root.free()
	quit(0)

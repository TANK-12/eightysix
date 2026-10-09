@tool
extends EditorPlugin
## Forge bridge: runs GDScript sent by Acchan's godot_editor tool inside this
## editor, on the main thread, while you watch.
##
## One JSON object per line on 127.0.0.1:FORGE_GODOT_PORT (default 9878):
## {"token": "...", "code": "..."} -> {"ok": bool, "result": ..., "error": "..."}.
## The code becomes the body of `func run(editor)`, where `editor` is
## EditorInterface; `return` a value to send it back. The token lives in
## ~/.local/share/forge/bridges/godot.token (mode 600).

var _server := TCPServer.new()
var _peers: Array = []
var _token := ""


func _enter_tree() -> void:
	_token = _load_token()
	var port := int(OS.get_environment("FORGE_GODOT_PORT")) if OS.has_environment("FORGE_GODOT_PORT") else 9878
	var err := _server.listen(port, "127.0.0.1")
	if err != OK:
		push_warning("Forge bridge: port %d is taken (error %d)" % [port, err])
	else:
		print("Forge bridge listening on 127.0.0.1:%d" % port)


func _exit_tree() -> void:
	for peer in _peers:
		peer["conn"].disconnect_from_host()
	_peers.clear()
	_server.stop()


func _token_path() -> String:
	if OS.has_environment("FORGE_GODOT_TOKEN"):
		return OS.get_environment("FORGE_GODOT_TOKEN")
	return OS.get_environment("HOME") + "/.local/share/forge/bridges/godot.token"


func _load_token() -> String:
	var path := _token_path()
	if FileAccess.file_exists(path):
		var existing := FileAccess.get_file_as_string(path).strip_edges()
		if existing != "":
			return existing
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var token := Crypto.new().generate_random_bytes(16).hex_encode()
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(token)
	f.close()
	OS.execute("chmod", ["600", path])
	return token


func _process(_delta: float) -> void:
	if not _server.is_listening():
		return
	while _server.is_connection_available():
		_peers.append({"conn": _server.take_connection(), "buf": ""})
	for peer in _peers.duplicate():
		var conn: StreamPeerTCP = peer["conn"]
		conn.poll()
		if conn.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			_peers.erase(peer)
			continue
		var n := conn.get_available_bytes()
		if n > 0:
			peer["buf"] += conn.get_utf8_string(n)
		while "\n" in peer["buf"]:
			var line: String = peer["buf"].get_slice("\n", 0)
			peer["buf"] = peer["buf"].substr(line.length() + 1)
			var reply := _handle(line)
			conn.put_data((JSON.stringify(reply) + "\n").to_utf8_buffer())


func _handle(line: String) -> Dictionary:
	var msg = JSON.parse_string(line)
	if typeof(msg) != TYPE_DICTIONARY:
		return {"ok": false, "error": "Send one JSON object per line"}
	if str(msg.get("token", "")) != _token:
		return {"ok": false, "error": "Wrong token"}
	var body := ""
	for code_line in str(msg.get("code", "")).split("\n"):
		body += "\t" + code_line + "\n"
	var script := GDScript.new()
	script.source_code = "@tool\nextends RefCounted\n\nfunc run(editor):\n" + body + "\tpass\n"
	var err := script.reload()
	if err != OK:
		return {"ok": false, "error": "The code does not compile (error %d); see the editor's Output panel" % err}
	var runner = script.new()
	var value = runner.run(EditorInterface)
	return {"ok": true, "result": _plain(value)}


func _plain(value):
	match typeof(value):
		TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING:
			return value
		TYPE_STRING_NAME, TYPE_NODE_PATH:
			return str(value)
		TYPE_ARRAY, TYPE_PACKED_STRING_ARRAY, TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_FLOAT32_ARRAY:
			return Array(value).map(func(v): return _plain(v))
		TYPE_DICTIONARY:
			var out := {}
			for k in value:
				out[str(k)] = _plain(value[k])
			return out
		_:
			return var_to_str(value)

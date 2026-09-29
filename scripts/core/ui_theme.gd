extends Node
## Menu themes: builds a Godot Theme from a data/themes.json entry and puts it on the root window,
## so every Control picks it up. Switching is live. Code-built UI asks for colours, fonts and sizes
## here (color("accent"), font("mono"), size("heading")) instead of hardcoding them.
##
## Type variations a scene can use (Control.theme_type_variation):
##   Labels: TitleLabel, HeadingLabel, GroupLabel, DimLabel, FaintLabel, MonoLabel, AccentLabel, HugeLabel
##   Buttons: MainMenuButton (big main-menu entries), TabButton, PageButton, SlotButton, SelectorButton
##   Panels: CardPanel, RowPanel, RowPanelFocus, HelpPanel

signal theme_changed

const BACKDROP_SHADER := "res://assets/shaders/menu_backdrop.gdshader"

var current_id := ""
var data: Dictionary = {}
const ADOPTED_GROUP := "ui_theme_roots"

var theme: Theme
var _fonts: Dictionary = {}


func _ready() -> void:
	apply(Settings.get_s("interface.theme"))
	Settings.changed.connect(_on_setting_changed)


func _on_setting_changed(key: String, _value: Variant) -> void:
	if key == "interface.theme" or key == "accessibility.high_contrast":
		apply(Settings.get_s("interface.theme"))


func apply(id: String) -> void:
	if not Registry.has_entry("themes", id):
		id = Registry.ids("themes")[0]
	current_id = id
	data = Registry.entry("themes", id)
	_fonts.clear()
	if Settings.get_b("accessibility.high_contrast"):
		data = _high_contrast(data)
	theme = _build()
	get_tree().root.theme = theme
	for node in get_tree().get_nodes_in_group(ADOPTED_GROUP):
		(node as Control).theme = theme
	theme_changed.emit()


## Controls under a CanvasLayer do not inherit the window's theme in Godot 4, so each layer's root
## control adopts it here and follows theme switches from then on.
func adopt(control: Control) -> void:
	control.theme = theme
	control.add_to_group(ADOPTED_GROUP)


func color(name: String) -> Color:
	return Color(str(data.get("colors", {}).get(name, "#ff00ff")))


func size(role: String) -> int:
	return int(data.get("sizes", {}).get(role, 22))


func shape(name: String) -> int:
	return int(data.get("shape", {}).get(name, 1))


func font(role: String) -> Font:
	if not _fonts.has(role):
		var path := str(data.get("fonts", {}).get(role, ""))
		var loaded: Font = load(path) if path != "" and ResourceLoader.exists(path) else null
		_fonts[role] = loaded if loaded != null else ThemeDB.fallback_font
	return _fonts[role]


## A font with extra space between letters, for titles.
func spaced_font(role: String, spacing: int) -> FontVariation:
	var v := FontVariation.new()
	v.base_font = font(role)
	v.spacing_glyph = spacing
	return v


## The animated menu backdrop (grid, contour lines, a slow sweep) coloured by the theme.
func make_backdrop() -> ColorRect:
	var rect := ColorRect.new()
	rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var mat := ShaderMaterial.new()
	mat.shader = load(BACKDROP_SHADER)
	rect.material = mat
	style_backdrop(rect)
	return rect


func style_backdrop(rect: ColorRect) -> void:
	var mat := rect.material as ShaderMaterial
	var bg: Dictionary = data.get("background", {})
	for key: String in ["top", "bottom", "grid", "sweep"]:
		mat.set_shader_parameter(key + "_color", Color(str(bg.get(key, "#000000"))))
	for key: String in ["grid_strength", "grid_size", "sweep_strength", "sweep_speed", "vignette", "grain"]:
		mat.set_shader_parameter(key, float(bg.get(key, 0.0)))


func _build() -> Theme:
	var t := Theme.new()
	var text := color("text")
	var dim := color("text_dim")
	var faint := color("text_faint")
	var accent := color("accent")
	var line := color("line")
	var bright := color("line_bright")
	var radius := shape("corner_radius")
	var border := shape("border")
	var bar := shape("focus_bar")
	var px := shape("padding_x")
	var py := shape("padding_y")

	t.default_font = font("body")
	t.default_font_size = size("body")

	# Labels
	t.set_color("font_color", "Label", text)
	_label_variant(t, "TitleLabel", "heading", size("title"), text)
	_label_variant(t, "HeadingLabel", "heading", size("heading"), text)
	_label_variant(t, "GroupLabel", "heading", size("button"), accent)
	_label_variant(t, "DimLabel", "body", size("small"), dim)
	_label_variant(t, "FaintLabel", "body", size("small"), faint)
	_label_variant(t, "MonoLabel", "mono", size("mono"), text)
	_label_variant(t, "AccentLabel", "body_strong", size("body"), accent)
	_label_variant(t, "HugeLabel", "heading_light", 220, accent)
	_label_variant(t, "WarnLabel", "body_strong", size("small"), color("warn"))

	# Buttons (general)
	var clear := Color(0, 0, 0, 0)
	t.set_font("font", "Button", font("button"))
	t.set_font_size("font_size", "Button", size("button"))
	t.set_stylebox("normal", "Button", _box(color("panel_alt"), line, border, radius, px, py))
	t.set_stylebox("hover", "Button", _box(color("accent_soft"), bright, border, radius, px, py))
	t.set_stylebox("pressed", "Button", _box(color("accent_soft"), accent, border, radius, px, py))
	t.set_stylebox("hover_pressed", "Button", _box(color("accent_soft"), accent, border, radius, px, py))
	t.set_stylebox("focus", "Button", _box(clear, bright, border + 1, radius, px, py))
	t.set_stylebox("disabled", "Button", _box(clear, faint, border, radius, px, py))
	t.set_color("font_color", "Button", text)
	t.set_color("font_hover_color", "Button", text)
	t.set_color("font_focus_color", "Button", text)
	t.set_color("font_pressed_color", "Button", accent)
	t.set_color("font_hover_pressed_color", "Button", accent)
	t.set_color("font_disabled_color", "Button", faint)

	# Main-menu entries: bare text, an accent bar and a soft wash on hover or focus.
	t.set_type_variation("MainMenuButton", "Button")
	t.set_font("font", "MainMenuButton", font("button"))
	t.set_font_size("font_size", "MainMenuButton", size("menu_button"))
	var wash := color("accent_soft")
	t.set_stylebox("normal", "MainMenuButton", _bar_box(clear, clear, 0, 26, 6))
	t.set_stylebox("hover", "MainMenuButton", _bar_box(wash, accent, bar, 26, 6))
	t.set_stylebox("focus", "MainMenuButton", _bar_box(wash, accent, bar, 26, 6))
	t.set_stylebox("pressed", "MainMenuButton", _bar_box(wash, color("warn"), bar, 26, 6))
	t.set_stylebox("hover_pressed", "MainMenuButton", _bar_box(wash, color("warn"), bar, 26, 6))
	t.set_stylebox("disabled", "MainMenuButton", _bar_box(clear, clear, 0, 26, 6))
	t.set_color("font_color", "MainMenuButton", dim)
	t.set_color("font_hover_color", "MainMenuButton", text)
	t.set_color("font_focus_color", "MainMenuButton", text)

	# Section tabs: underlined when chosen.
	t.set_type_variation("TabButton", "Button")
	t.set_font_size("font_size", "TabButton", size("button"))
	t.set_stylebox("normal", "TabButton", _under_box(clear, clear, 0, px))
	t.set_stylebox("hover", "TabButton", _under_box(clear, line, 2, px))
	t.set_stylebox("focus", "TabButton", _under_box(clear, bright, 2, px))
	t.set_stylebox("pressed", "TabButton", _under_box(clear, accent, 3, px))
	t.set_stylebox("hover_pressed", "TabButton", _under_box(clear, accent, 3, px))
	t.set_color("font_color", "TabButton", dim)
	t.set_color("font_pressed_color", "TabButton", text)
	t.set_color("font_hover_pressed_color", "TabButton", text)

	# Page list (sub-menus): left bar when chosen.
	t.set_type_variation("PageButton", "Button")
	t.set_font("font", "PageButton", font("body_strong"))
	t.set_font_size("font_size", "PageButton", size("body"))
	t.set_stylebox("normal", "PageButton", _bar_box(clear, clear, 0, 18, 8))
	t.set_stylebox("hover", "PageButton", _bar_box(color("panel_alt"), line, bar, 18, 8))
	t.set_stylebox("focus", "PageButton", _bar_box(color("panel_alt"), bright, bar, 18, 8))
	t.set_stylebox("pressed", "PageButton", _bar_box(wash, accent, bar, 18, 8))
	t.set_stylebox("hover_pressed", "PageButton", _bar_box(wash, accent, bar, 18, 8))
	t.set_color("font_color", "PageButton", dim)
	t.set_color("font_pressed_color", "PageButton", text)
	t.set_color("font_hover_pressed_color", "PageButton", text)

	# Binding slots and choice selectors: mono, boxed.
	for variant: String in ["SlotButton", "SelectorButton"]:
		t.set_type_variation(variant, "Button")
		t.set_font("font", variant, font("mono" if variant == "SlotButton" else "body_strong"))
		t.set_font_size("font_size", variant, size("mono") if variant == "SlotButton" else size("body"))
		t.set_stylebox("normal", variant, _box(color("panel"), line, border, radius, 12, 5))
		t.set_stylebox("hover", variant, _box(color("panel_alt"), bright, border, radius, 12, 5))
		t.set_stylebox("focus", variant, _box(wash, accent, border + 1, radius, 12, 5))
		t.set_stylebox("pressed", variant, _box(wash, accent, border, radius, 12, 5))

	# Panels
	var panel := _box(color("panel"), line, border, radius, 20, 16)
	t.set_stylebox("panel", "Panel", panel)
	t.set_stylebox("panel", "PanelContainer", panel)
	t.set_type_variation("CardPanel", "PanelContainer")
	t.set_stylebox("panel", "CardPanel", _box(color("panel"), line, border, radius, 28, 24))
	t.set_type_variation("HelpPanel", "PanelContainer")
	t.set_stylebox("panel", "HelpPanel", _box(color("panel_alt"), line, border, radius, 22, 18))
	t.set_type_variation("RowPanel", "PanelContainer")
	t.set_stylebox("panel", "RowPanel", _bar_box(clear, clear, 0, 14, 4))
	t.set_type_variation("RowPanelFocus", "PanelContainer")
	t.set_stylebox("panel", "RowPanelFocus", _bar_box(wash, accent, bar, 14, 4))

	# Toggles
	t.set_font("font", "CheckButton", font("body_strong"))
	t.set_icon("checked", "CheckButton", _toggle_icon(true, accent, line, color("bg")))
	t.set_icon("unchecked", "CheckButton", _toggle_icon(false, accent, line, dim))
	t.set_icon("checked_disabled", "CheckButton", _toggle_icon(true, faint, faint, color("bg")))
	t.set_icon("unchecked_disabled", "CheckButton", _toggle_icon(false, faint, faint, faint))
	for state: String in ["normal", "hover", "pressed", "hover_pressed", "disabled"]:
		t.set_stylebox(state, "CheckButton", _box(clear, clear, 0, 0, 4, 4))
	t.set_stylebox("focus", "CheckButton", _box(clear, bright, border + 1, radius, 4, 4))
	t.set_color("font_color", "CheckButton", text)
	t.set_color("font_pressed_color", "CheckButton", accent)
	t.set_color("font_hover_color", "CheckButton", text)
	t.set_color("font_hover_pressed_color", "CheckButton", accent)
	t.set_color("font_focus_color", "CheckButton", text)

	# Sliders
	var track := _box(line, clear, 0, 2, 0, 3)
	t.set_stylebox("slider", "HSlider", track)
	t.set_stylebox("grabber_area", "HSlider", _box(accent, clear, 0, 2, 0, 3))
	t.set_stylebox("grabber_area_highlight", "HSlider", _box(bright, clear, 0, 2, 0, 3))
	t.set_icon("grabber", "HSlider", _grabber_icon(text, 18))
	t.set_icon("grabber_highlight", "HSlider", _grabber_icon(accent, 20))
	t.set_icon("grabber_disabled", "HSlider", _grabber_icon(faint, 18))
	t.set_stylebox("focus", "HSlider", _box(clear, bright, border, radius, 6, 10))

	# Progress bars
	t.set_stylebox("background", "ProgressBar", _box(color("panel_alt"), line, border, radius, 0, 0))
	t.set_stylebox("fill", "ProgressBar", _box(accent, clear, 0, radius, 0, 0))
	t.set_font("font", "ProgressBar", font("mono"))
	t.set_color("font_color", "ProgressBar", text)

	# Scroll bars: thin.
	var grab := _box(line, clear, 0, 3, 3, 3)
	t.set_stylebox("scroll", "VScrollBar", _box(clear, clear, 0, 0, 3, 3))
	t.set_stylebox("grabber", "VScrollBar", grab)
	t.set_stylebox("grabber_highlight", "VScrollBar", _box(bright, clear, 0, 3, 3, 3))
	t.set_stylebox("grabber_pressed", "VScrollBar", _box(accent, clear, 0, 3, 3, 3))

	# Separators, tooltips, popups
	var sep := StyleBoxLine.new()
	sep.color = line
	sep.thickness = 1
	t.set_stylebox("separator", "HSeparator", sep)
	t.set_constant("separation", "HSeparator", 12)
	t.set_stylebox("panel", "TooltipPanel", _box(color("panel_alt"), bright, 1, radius, 10, 6))
	t.set_color("font_color", "TooltipLabel", text)
	t.set_stylebox("panel", "PopupMenu", _box(color("panel_alt"), line, border, radius, 8, 8))
	t.set_stylebox("hover", "PopupMenu", _box(wash, clear, 0, radius, 8, 4))
	t.set_color("font_color", "PopupMenu", text)
	t.set_color("font_hover_color", "PopupMenu", accent)
	return t


func _label_variant(t: Theme, name: String, role: String, font_size: int, col: Color) -> void:
	t.set_type_variation(name, "Label")
	t.set_font("font", name, font(role))
	t.set_font_size("font_size", name, font_size)
	t.set_color("font_color", name, col)


static func _box(bg: Color, border_col: Color, border_w: int, radius: int, px: int, py: int) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.border_color = border_col
	sb.set_border_width_all(border_w)
	sb.set_corner_radius_all(radius)
	sb.content_margin_left = px
	sb.content_margin_right = px
	sb.content_margin_top = py
	sb.content_margin_bottom = py
	sb.anti_aliasing = radius > 0
	return sb


static func _bar_box(bg: Color, bar_col: Color, bar_w: int, px: int, py: int) -> StyleBoxFlat:
	var sb := _box(bg, bar_col, 0, 0, px, py)
	sb.border_width_left = bar_w
	return sb


static func _under_box(bg: Color, line_col: Color, line_w: int, px: int) -> StyleBoxFlat:
	var sb := _box(bg, line_col, 0, 0, px, 10)
	sb.border_width_bottom = line_w
	return sb


static func _toggle_icon(on: bool, on_col: Color, off_col: Color, knob: Color) -> ImageTexture:
	var w := 52
	var h := 26
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	var track := on_col if on else Color(0, 0, 0, 0)
	var edge := on_col if on else off_col
	var r := h / 2.0
	for y in h:
		for x in w:
			var cx := clampf(x + 0.5, r, w - r)
			var d := Vector2(x + 0.5 - cx, y + 0.5 - r).length()
			if d <= r - 0.5:
				var inner := d <= r - 2.5
				img.set_pixel(x, y, track if inner else edge)
	var knob_x := w - r if on else r
	for y in h:
		for x in w:
			if Vector2(x + 0.5 - knob_x, y + 0.5 - r).length() <= r - 5.0:
				img.set_pixel(x, y, knob)
	return ImageTexture.create_from_image(img)


static func _grabber_icon(col: Color, side: int) -> ImageTexture:
	var img := Image.create(side, side, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	var c := side / 2.0
	for y in side:
		for x in side:
			if absf(x + 0.5 - c) + absf(y + 0.5 - c) <= c - 1.0:
				img.set_pixel(x, y, col)
	return ImageTexture.create_from_image(img)


static func _high_contrast(d: Dictionary) -> Dictionary:
	var out := d.duplicate(true)
	var c: Dictionary = out["colors"]
	c["text"] = "#ffffff"
	c["text_dim"] = "#d8e4ec"
	c["text_faint"] = "#9aa8b2"
	c["panel"] = "#000000"
	c["panel_alt"] = "#101418"
	c["line"] = "#9ab0c0"
	return out

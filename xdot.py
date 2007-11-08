#!/usr/bin/env python
'''Visualize dot graphs via the xdot format.'''


import sys
import subprocess
import math

import gtk
import gtk.gdk
import gtk.keysyms
import cairo
import pango
import pangocairo

import pydot


# See http://www.graphviz.org/pub/scm/graphviz-cairo/plugin/cairo/gvrender_cairo.c

# For pygtk inspiration and guidance see:
# - http://mirageiv.berlios.de/
# - http://comix.sourceforge.net/


class Pen:

	def __init__(self):
		self.color = (0.0, 0.0, 0.0, 1.0)
		self.fillcolor = (0.0, 0.0, 0.0, 1.0)
		self.linewidth = 1.0
		self.fontsize = 14.0
		self.fontname = "Times-Roman"

	def copy(self):
		pen = Pen()
		pen.__dict__ = self.__dict__.copy()
		return pen


class Shape:

	def __init__(self, pen):
		self.pen = pen.copy()

	def draw(self, cr):
		raise NotImplementedError


LEFT, CENTER, RIGHT = -1, 0, 1

class TextShape(Shape):
	
	#fontmap = pangocairo.CairoFontMap()
	#fontmap.set_resolution(72)
	#context = fontmap.create_context()

	def __init__(self, pen, x, y, j, w, t):
		Shape.__init__(self, pen)
		self.x = x
		self.y = y
		self.j = j
		self.w = w
		self.t = t

	def draw(self, cr):

		try:
			layout = self.layout
		except AttributeError:
			layout = cr.create_layout()
			
			# set font options
			# See http://lists.freedesktop.org/archives/cairo/2007-February/009688.html
			context = layout.get_context()
			fo = cairo.FontOptions()
			fo.set_antialias(cairo.ANTIALIAS_DEFAULT)
			fo.set_hint_style(cairo.HINT_STYLE_NONE)
			fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
			pangocairo.context_set_font_options(context, fo)
			
			# set font
			font = pango.FontDescription()
			font.set_family(self.pen.fontname)
			font.set_absolute_size(self.pen.fontsize*pango.SCALE)
			layout.set_font_description(font)
			
			# set text
			layout.set_text(self.t)
			
			# cache it
			self.layout = layout
		else:
			cr.update_layout(layout)

		width, height = layout.get_size()
		width = float(width)/pango.SCALE
		height = float(height)/pango.SCALE

		cr.move_to(self.x - self.w/2, self.y)

		if self.j == LEFT:
			x = self.x
		elif self.j == CENTER:
			x = self.x - 0.5*width
		elif self.j == RIGHT:
			x = self.x - width
		else:
			assert 0
		
		y = self.y - height
		
		cr.move_to(x, y)

		cr.set_source_rgba(*self.pen.color)
		cr.show_layout(layout)


class EllipseShape(Shape):

	def __init__(self, pen, x0, y0, w, h, filled=False):
		Shape.__init__(self, pen)
		self.x0 = x0
		self.y0 = y0
		self.w = w
		self.h = h
		self.filled = filled

	def draw(self, cr):
		cr.set_line_width(self.pen.linewidth)
		cr.save()
		cr.translate(self.x0, self.y0)
		cr.scale(self.w, self.h)
		cr.arc(0.0, 0.0, 1.0, 0, 2.0*math.pi)
		cr.restore()
		if self.filled:
			cr.set_source_rgba(*self.pen.fillcolor)
			cr.fill_preserve()
		cr.set_source_rgba(*self.pen.color)
		cr.stroke()


class PolygonShape(Shape):

	def __init__(self, pen, points, filled=False):
		Shape.__init__(self, pen)
		self.points = points
		self.filled = filled

	def draw(self, cr):
		x0, y0 = self.points[-1]
		cr.set_line_width(self.pen.linewidth)
		cr.move_to(x0, y0)
		for x, y in self.points:
			cr.line_to(x, y)
		cr.close_path()
		if self.filled:
			cr.set_source_rgba(*self.pen.fillcolor)
			cr.fill_preserve()
		cr.set_source_rgba(*self.pen.color)
		cr.stroke()


class BezierShape(Shape):

	def __init__(self, pen, points):
		Shape.__init__(self, pen)
		self.points = points

	def draw(self, cr):
		x0, y0 = self.points[0]
		cr.set_line_width(self.pen.linewidth)
		cr.move_to(x0, y0)
		for i in xrange(1, len(self.points), 3):
			x1, y1 = self.points[i]
			x2, y2 = self.points[i + 1]
			x3, y3 = self.points[i + 2]
			cr.curve_to(x1, y1, x2, y2, x3, y3)
		cr.set_source_rgba(*self.pen.color)
		cr.stroke()


class XDotAttrParser:
	# See http://www.graphviz.org/doc/info/output.html#d:xdot

	def __init__(self, parser, buf):
		self.parser = parser
		self.buf = self.unescape(buf)
		self.pos = 0

	def __nonzero__(self):
		return self.pos < len(self.buf)

	def unescape(self, buf):
		buf = buf.replace('\\"', '"')
		buf = buf.replace('\\n', '\n')
		return buf

	def read_code(self):
		pos = self.buf.find(" ", self.pos)
		res = self.buf[self.pos:pos]
		self.pos = pos + 1
		while self.pos < len(self.buf) and self.buf[self.pos].isspace():
			self.pos += 1
		return res

	def read_number(self):
		return int(self.read_code())

	def read_float(self):
		return float(self.read_code())

	def read_point(self):
		x = self.read_number()
		y = self.read_number()
		return self.transform(x, y)

	def read_text(self):
		num = self.read_number()
		pos = self.buf.find("-", self.pos) + 1
		self.pos = pos + num
		res = self.buf[pos:self.pos]
		while self.pos < len(self.buf) and self.buf[self.pos].isspace():
			self.pos += 1
		return res

	def read_polygon(self):
		n = self.read_number()
		p = []
		for i in range(n):
			x, y = self.read_point()
			p.append((x, y))
		return p

	def read_color(self):
		# See http://www.graphviz.org/doc/info/attrs.html#k:color
		c = self.read_text()
		c1 = c[:1]
		if c1 == '#':
			hex2float = lambda h: float(int(h, 16)/255.0)
			r = hex2float(c[1:3])
			g = hex2float(c[3:5])
			b = hex2float(c[5:7])
			try:
				a = hex2float(c[7:9])
			except (IndexError, ValueError):
				a = 1.0
			return r, g, b, a
		elif c1.isdigit():
			h, s, v = map(float, c[1:].split(","))
			raise NotImplementedError
		else:
			color = gtk.gdk.color_parse(c)
			s = 1.0/65535.0
			r = color.red*s
			g = color.green*s
			b = color.blue*s
			a = 1.0
			return r, g, b, a

	def parse(self):
		shapes = []
		pen = Pen()
		s = self

		while s:
			op = s.read_code()
			if op == "c":
				pen.color = s.read_color()
			elif op == "C":
				pen.fillcolor = s.read_color()
			elif op == "S":
				s.read_text()
			elif op == "F":
				pen.fontsize = s.read_float()
				pen.fontname = s.read_text()
			elif op == "T":
				x, y = s.read_point()
				j = s.read_number()
				w = s.read_number()
				t = s.read_text()
				shapes.append(TextShape(pen, x, y, j, w, t))
			elif op == "E":
				x0, y0 = s.read_point()
				w = s.read_number()
				h = s.read_number()
				shapes.append(EllipseShape(pen, x0, y0, w, h, filled=True))
			elif op == "e":
				x0, y0 = s.read_point()
				w = s.read_number()
				h = s.read_number()
				shapes.append(EllipseShape(pen, x0, y0, w, h))
			elif op == "B":
				p = self.read_polygon()
				shapes.append(BezierShape(pen, p))
			elif op == "P":
				p = self.read_polygon()
				shapes.append(PolygonShape(pen, p, filled=True))
			elif op == "p":
				p = self.read_polygon()
				shapes.append(PolygonShape(pen, p))
			else:
				sys.stderr.write("unknown xdot opcode '%s'\n" % op)
				break
		return shapes

	def transform(self, x, y):
		return self.parser.transform(x, y)


class Hyperlink:

	def __init__(self, url, x, y, w, h):
		self.url = url
		self.x1 = x - w/2
		self.y1 = y - h/2
		self.x2 = x + w/2
		self.y2 = y + h/2

	def hit(self, x, y):
		return self.x1 <= x and x <= self.x2 and self.y1 <= y and y <= self.y2


class DotWindow(gtk.Window):

	# TODO: Make a seperate, reusable widget

	ui = '''
	<ui>
		<toolbar name="ToolBar">
			<toolitem action="ZoomIn"/>
			<toolitem action="ZoomOut"/>
			<toolitem action="ZoomFit"/>
			<toolitem action="Zoom100"/>
		</toolbar>
	</ui>
	'''

	hand_cursor = gtk.gdk.Cursor(gtk.gdk.HAND2)
	regular_cursor = gtk.gdk.Cursor(gtk.gdk.XTERM)

	def __init__(self):
		gtk.Window.__init__(self)

		self.graph = None
		self.width = 1
		self.height = 1
		self.shapes = []
		self.hyperlinks = []

		window = self

		window.set_title('Dot')
		window.set_default_size(512, 512)
		vbox = gtk.VBox()
		window.add(vbox)

		# Create a UIManager instance
		uimanager = self.uimanager = gtk.UIManager()

		# Add the accelerator group to the toplevel window
		accelgroup = uimanager.get_accel_group()
		window.add_accel_group(accelgroup)

		# Create an ActionGroup
		actiongroup = gtk.ActionGroup('Actions')
		self.actiongroup = actiongroup

		# Create actions
		actiongroup.add_actions((
			('ZoomIn', gtk.STOCK_ZOOM_IN, None, None, None, self.on_zoom_in),
			('ZoomOut', gtk.STOCK_ZOOM_OUT, None, None, None, self.on_zoom_out),
			('ZoomFit', gtk.STOCK_ZOOM_FIT, None, None, None, self.on_zoom_fit),
			('Zoom100', gtk.STOCK_ZOOM_100, None, None, None, self.on_zoom_100),
		))

		# Add the actiongroup to the uimanager
		uimanager.insert_action_group(actiongroup, 0)

		# Add a UI description
		uimanager.add_ui_from_string(self.ui)

		# Create a Toolbar
		toolbar = uimanager.get_widget('/ToolBar')
		vbox.pack_start(toolbar, False)

		scrolled_window = self.scrolled_window = gtk.ScrolledWindow()
		scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		vbox.pack_start(scrolled_window)

		# TODO: Use a custom widget instead of Layout like in the scrollable.py example?
		self.area = gtk.Layout()
		self.area.connect("expose_event", self.on_expose)
		scrolled_window.add(self.area)

		self.area.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK)
		self.area.connect("button-press-event", self.on_area_button_press)
		self.area.add_events(gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.POINTER_MOTION_HINT_MASK | gtk.gdk.BUTTON_RELEASE_MASK)
		self.area.connect("motion-notify-event", self.on_area_motion_notify)
		self.area.connect("scroll-event", self.on_area_scroll_event)
		
		window.connect('key-press-event', self.on_key_press_event)

		self.zoom_ratio = 1.0
		self.pixbuf = None

		self.show_all()

	def set_dotcode(self, dotcode):
		p = subprocess.Popen(
			['dot', '-Txdot'],
			stdin=subprocess.PIPE,
			stdout=subprocess.PIPE,
			shell=False,
			universal_newlines=True
		)
		xdotcode = p.communicate(dotcode)[0]
		#if __name__ == '__main__':
		#	sys.stdout.write(xdotcode)
		self.parse(xdotcode)
		self.zoom_image()

	def parse(self, xdotcode):
		self.graph = pydot.graph_from_dot_data(xdotcode)

		bb = self.graph.get_bb()
		if bb is None:
			return

		xmin, ymin, xmax, ymax = map(int, bb.split(","))

		self.xoffset = -xmin
		self.yoffset = -ymax
		self.xscale = 1.0
		self.yscale = -1.0
		self.width = xmax - xmin
		self.height = ymax - ymin

		self.shapes = []
		self.hyperlinks = []

		for node in self.graph.get_node_list():
			for attr in ("_draw_", "_ldraw_"):
				if hasattr(node, attr):
					p = XDotAttrParser(self, getattr(node, attr))
					self.shapes.extend(p.parse())
			if node.URL is not None:
				x, y = map(float, node.pos.split(","))
				w = float(node.width)*72
				h = float(node.height)*72
				# TODO: use event boxes instead
				self.hyperlinks.append(Hyperlink(node.URL, x, y, w, h))
		for edge in self.graph.get_edge_list():
			for attr in ("_draw_", "_ldraw_", "_hdraw_", "_tdraw_", "_hldraw_", "_tldraw_"):
				if hasattr(edge, attr):
					p = XDotAttrParser(self, getattr(edge, attr))
					self.shapes.extend(p.parse())

	def transform(self, x, y):
		x = (x + self.xoffset)*self.xscale
		y = (y + self.yoffset)*self.yscale
		return x, y

	def on_expose(self, area, event):
		cr = area.bin_window.cairo_create()

		# set a clip region for the expose event
		cr.rectangle(
			event.area.x, event.area.y,
			event.area.width, event.area.height
		)
		cr.clip()

		cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
		cr.paint()

		#rect = area.get_allocation()
		#xscale = float(rect.width)/self.width
		#yscale = float(rect.height)/self.height
		#scale = min(xscale, yscale)*2

		cr.translate(0, 0)
		cr.scale(self.zoom_ratio, self.zoom_ratio)

		# FIXME: scale from points to pixels

		cr.set_source_rgba(0.0, 0.0, 0.0, 1.0)

		cr.set_line_cap(cairo.LINE_CAP_BUTT)
		cr.set_line_join(cairo.LINE_JOIN_MITER)
		cr.set_miter_limit(1.0)
		
		for shape in self.shapes:
			shape.draw(cr)

		return False

	def zoom_image(self):
		width = int(self.width*self.zoom_ratio)
		height = int(self.height*self.zoom_ratio)
		self.area.set_size(width, height)
		self.area.queue_draw()

	ZOOM_INCREMENT = 1.25

	def on_zoom_in(self, action):
		self.zoom_ratio *= self.ZOOM_INCREMENT
		self.zoom_image()

	def on_zoom_out(self, action):
		self.zoom_ratio /= self.ZOOM_INCREMENT
		self.zoom_image()

	def on_zoom_fit(self, action):
		rect = self.area.get_allocation()
		self.zoom_ratio = min(
			float(rect.width)/float(self.width),
			float(rect.height)/float(self.height)
		)
		self.zoom_image()

	def on_zoom_100(self, action):
		self.zoom_ratio = 1.0
		self.zoom_image()

	POS_INCREMENT = 100

	def on_key_press_event(self, widget, event):
		hadjust = self.scrolled_window.get_hadjustment()
		vadjust = self.scrolled_window.get_vadjustment()
		if event.keyval == gtk.keysyms.Left:
			hadjust.value = max(hadjust.value - self.POS_INCREMENT, hadjust.lower)
			return True
		if event.keyval == gtk.keysyms.Right:
			hadjust.value = min(hadjust.value + self.POS_INCREMENT, hadjust.upper - hadjust.page_size)
			return True
		if event.keyval == gtk.keysyms.Up:
			vadjust.value = max(vadjust.value - self.POS_INCREMENT, vadjust.lower)
			return True
		if event.keyval == gtk.keysyms.Down:
			vadjust.value = min(vadjust.value + self.POS_INCREMENT, vadjust.upper - vadjust.page_size)
			return True
		if event.keyval == gtk.keysyms.Page_Up:
			self.zoom_ratio *= self.ZOOM_INCREMENT
			self.zoom_image()
			return True
		if event.keyval == gtk.keysyms.Page_Down:
			self.zoom_ratio /= self.ZOOM_INCREMENT
			self.zoom_image()
			return True
		return False

	def on_area_button_press(self, area, event):
		if event.type not in (gtk.gdk.BUTTON_PRESS, gtk.gdk.BUTTON_RELEASE):
			return False
		x, y = int(event.x), int(event.y)
		url = self.get_url(x, y)
		if url is not None:
			return self.on_url_clicked(url, event)
		return False

	def on_area_scroll_event(self, area, event):
		if event.direction == gtk.gdk.SCROLL_UP:
			self.zoom_ratio *= self.ZOOM_INCREMENT
			self.zoom_image()
			return True
		if event.direction == gtk.gdk.SCROLL_DOWN:
			self.zoom_ratio /= self.ZOOM_INCREMENT
			self.zoom_image()
			return True
		return False

	def on_area_motion_notify(self, area, event):
		#print event.x, event.y
		x, y = int(event.x), int(event.y)
		if self.get_url(x, y) is not None:
			area.window.set_cursor(self.hand_cursor)
		else:
			area.window.set_cursor(self.regular_cursor)
		return True

	def get_url(self, x, y):
		x /= self.zoom_ratio
		y /= self.zoom_ratio
		y = self.height - y

		for hyperlink in self.hyperlinks:
			if hyperlink.hit(x, y):
				return hyperlink.url
		return None

	def on_url_clicked(self, url, event):
		return False


if __name__ == '__main__':
	win = DotWindow()
	try:
		fp = file(sys.argv[1], 'rt')
	except IndexError:
		fp = sys.stdin
	win.set_dotcode(fp.read())
	win.connect('destroy', gtk.main_quit)
	gtk.main()

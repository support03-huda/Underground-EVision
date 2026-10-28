# Copyright (c) 2026, huda and contributors
"""A small PDF table writer in plain Python (Helvetica, A4), so report PDFs work on a server
without wkhtmltopdf or system libraries: title, sub-title lines, a table whose header repeats on
every page, wrapped cells and "Page n of N" footers."""

import zlib

# Helvetica glyph widths (1/1000 em) for ASCII 32..126, from the standard AFM.
_WIDTHS = [
	278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
	556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
	1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
	667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
	333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
	556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
BOLD_FACTOR = 1.08
PAGE_SIZES = {"portrait": (595.28, 841.89), "landscape": (841.89, 595.28)}
MARGIN = 28
FONT_SIZE = 7.5
LEADING = 9.2
PAD = 3
MAX_CELL_LINES = 8
HEADER_FILL = (0.114, 0.306, 0.537)  # #1D4E89, the app colour
STRIPE_FILL = (0.95, 0.96, 0.98)
GRID = (0.78, 0.8, 0.84)


def text_width(text, size=FONT_SIZE, bold=False):
	width = sum(_WIDTHS[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in text)
	return width * size / 1000 * (BOLD_FACTOR if bold else 1)


def wrap(text, width, size=FONT_SIZE, bold=False):
	"""Lines of `text` no wider than `width`; words longer than a line are cut."""
	lines = []
	for paragraph in str(text).replace("\r", "").split("\n"):
		line = ""
		for word in paragraph.split(" "):
			candidate = f"{line} {word}" if line else word
			if text_width(candidate, size, bold) <= width:
				line = candidate
				continue
			if line:
				lines.append(line)
			while text_width(word, size, bold) > width and len(word) > 1:
				cut = len(word)
				while cut > 1 and text_width(word[:cut], size, bold) > width:
					cut -= 1
				lines.append(word[:cut])
				word = word[cut:]
			line = word
		lines.append(line)
	return lines or [""]


def _pdf_text(text):
	raw = str(text).encode("cp1252", "replace")
	return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class _Page:
	def __init__(self):
		self.ops = []

	def rect(self, x, y, w, h, fill=None, stroke=None):
		if fill:
			self.ops.append(b"%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (*fill, x, y, w, h))
		if stroke:
			self.ops.append(b"%.3f %.3f %.3f RG 0.4 w %.2f %.2f %.2f %.2f re S" % (*stroke, x, y, w, h))

	def text(self, x, y, text, size=FONT_SIZE, bold=False, color=(0, 0, 0)):
		font = b"F2" if bold else b"F1"
		self.ops.append(
			b"BT %.3f %.3f %.3f rg /%s %.2f Tf %.2f %.2f Td (%s) Tj ET" % (*color, font, size, x, y, _pdf_text(text))
		)


def _p90(values):
	values = sorted(values)
	return values[int(len(values) * 0.9)] if values else 0


def column_widths(headers, rows, available):
	"""Every column first gets room for its longest word (so IDs and amounts do not break), then
	the space left goes to the columns with longer text, in proportion to what they need."""
	minimum, desired = [], []
	for i, header in enumerate(headers):
		cells = [str(row[i]) for row in rows if row[i] not in (None, "")]
		words = [text_width(w, bold=True) for w in str(header).split()]
		words.append(_p90([max((text_width(w) for w in cell.split()), default=0) for cell in cells]))
		low = min(max(words + [20]), 140) + 2 * PAD
		minimum.append(low)
		desired.append(max(low, min(_p90([text_width(cell) for cell in cells]) + 2 * PAD, 260)))
	if sum(minimum) >= available:
		return [w * available / sum(minimum) for w in minimum]
	extra = available - sum(minimum)
	wants = [d - m for d, m in zip(desired, minimum)]
	if sum(wants) <= 0:
		return [m + extra / len(minimum) for m in minimum]
	if sum(wants) <= extra:
		spare = (extra - sum(wants)) / len(minimum)
		return [d + spare for d in desired]
	return [m + extra * w / sum(wants) for m, w in zip(minimum, wants)]


def make_pdf(title, subtitle_lines, headers, rows, align=None, orientation=None, footer=""):
	"""PDF bytes for a table. `rows` are lists of display strings; `align` has "right" for number columns."""
	orientation = orientation or ("landscape" if len(headers) > 6 else "portrait")
	page_w, page_h = PAGE_SIZES[orientation]
	align = align or ["left"] * len(headers)
	widths = column_widths(headers, rows, page_w - 2 * MARGIN)
	pages = []

	def header_cells(page, y):
		lines = [wrap(h, w - 2 * PAD, bold=True) for h, w in zip(headers, widths)]
		height = max(len(l) for l in lines) * LEADING + 2 * PAD
		x = MARGIN
		page.rect(MARGIN, y - height, sum(widths), height, fill=HEADER_FILL)
		for cell, w in zip(lines, widths):
			for n, line in enumerate(cell):
				page.text(x + PAD, y - PAD - (n + 1) * LEADING + 2, line, bold=True, color=(1, 1, 1))
			x += w
		return y - height

	def new_page(first=False):
		page = _Page()
		pages.append(page)
		y = page_h - MARGIN
		if first:
			page.text(MARGIN, y - 14, title, size=13, bold=True, color=HEADER_FILL)
			y -= 22
			for line in subtitle_lines:
				for part in wrap(line, page_w - 2 * MARGIN, size=8):
					page.text(MARGIN, y - 9, part, size=8, color=(0.33, 0.36, 0.4))
					y -= 11
			y -= 6
		return page, header_cells(page, y)

	page, y = new_page(first=True)
	if not rows:
		page.text(MARGIN, y - 16, "No rows match the filters.", size=9)
	for index, row in enumerate(rows):
		cells = []
		for value, w in zip(row, widths):
			lines = wrap("" if value is None else value, w - 2 * PAD)
			if len(lines) > MAX_CELL_LINES:
				lines = lines[:MAX_CELL_LINES - 1] + [lines[MAX_CELL_LINES - 1] + " ..."]
			cells.append(lines)
		height = max(len(c) for c in cells) * LEADING + 2 * PAD
		if y - height < MARGIN + 14:
			page, y = new_page()
		if index % 2:
			page.rect(MARGIN, y - height, sum(widths), height, fill=STRIPE_FILL)
		x = MARGIN
		for lines, w, side in zip(cells, widths, align):
			for n, line in enumerate(lines):
				tx = x + w - PAD - text_width(line) if side == "right" else x + PAD
				page.text(tx, y - PAD - (n + 1) * LEADING + 2, line)
			page.rect(x, y - height, w, height, stroke=GRID)
			x += w
		y -= height

	for number, page in enumerate(pages, 1):
		page.text(MARGIN, MARGIN - 12, footer, size=7, color=(0.45, 0.47, 0.5))
		label = f"Page {number} of {len(pages)}"
		page.text(page_w - MARGIN - text_width(label, 7), MARGIN - 12, label, size=7, color=(0.45, 0.47, 0.5))
	return _write(pages, page_w, page_h)


def _write(pages, page_w, page_h):
	objects = [
		b"<< /Type /Catalog /Pages 2 0 R >>",
		None,  # pages, filled below
		b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
		b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
	]
	kids = []
	for page in pages:
		stream = zlib.compress(b"\n".join(page.ops))
		objects.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream" % (len(stream), stream))
		content = len(objects)
		objects.append(
			b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
			b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>" % (page_w, page_h, content)
		)
		kids.append(b"%d 0 R" % len(objects))
	objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(kids))

	out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
	offsets = []
	for number, body in enumerate(objects, 1):
		offsets.append(len(out))
		out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
	xref = len(out)
	out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
	out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
	out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
	return bytes(out)

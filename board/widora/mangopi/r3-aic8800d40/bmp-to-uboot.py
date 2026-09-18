#!/usr/bin/env python3
"""Convert a BMP to the uncompressed 24-bit format understood by U-Boot 2020.07."""

import struct
import sys
from pathlib import Path


BI_RGB = 0
BI_BITFIELDS = 3
BI_ALPHABITFIELDS = 6


def component(pixel, mask):
	if not mask:
		return 0
	shift = (mask & -mask).bit_length() - 1
	maximum = mask >> shift
	value = (pixel & mask) >> shift
	return (value * 255 + maximum // 2) // maximum


def convert(source, destination):
	data = Path(source).read_bytes()
	if len(data) < 54 or data[:2] != b"BM":
		raise ValueError("input is not a valid BMP file")

	pixel_offset = struct.unpack_from("<I", data, 10)[0]
	dib_size = struct.unpack_from("<I", data, 14)[0]
	width, height = struct.unpack_from("<ii", data, 18)
	planes, bpp = struct.unpack_from("<HH", data, 26)
	compression = struct.unpack_from("<I", data, 30)[0]

	if dib_size < 40 or width <= 0 or height == 0 or planes != 1:
		raise ValueError("unsupported BMP header or dimensions")

	# U-Boot's legacy cfb_console accepts these formats without conversion.
	if bpp in (4, 8, 24) and compression == BI_RGB:
		Path(destination).write_bytes(data)
		print(f"U-Boot splash: keeping {width}x{abs(height)} {bpp}-bit BI_RGB BMP")
		return

	if bpp != 32 or compression not in (BI_RGB, BI_BITFIELDS,
						BI_ALPHABITFIELDS):
		raise ValueError(
			f"unsupported BMP format: {bpp} bpp, compression {compression}"
		)

	if compression == BI_RGB:
		red_mask = 0x00FF0000
		green_mask = 0x0000FF00
		blue_mask = 0x000000FF
	else:
		if len(data) < 66:
			raise ValueError("truncated BMP bitfield masks")
		red_mask, green_mask, blue_mask = struct.unpack_from("<III", data, 54)

	rows = abs(height)
	source_stride = ((width * bpp + 31) // 32) * 4
	destination_stride = ((width * 24 + 31) // 32) * 4
	needed = pixel_offset + source_stride * rows
	if pixel_offset < 14 + dib_size or needed > len(data):
		raise ValueError("truncated BMP pixel data")

	pixels = bytearray(destination_stride * rows)
	for row_index in range(rows):
		source_row = pixel_offset + row_index * source_stride
		destination_row = row_index * destination_stride
		for column in range(width):
			pixel = struct.unpack_from("<I", data, source_row + column * 4)[0]
			red = component(pixel, red_mask)
			green = component(pixel, green_mask)
			blue = component(pixel, blue_mask)
			position = destination_row + column * 3
			pixels[position:position + 3] = bytes((blue, green, red))

	x_ppm, y_ppm = struct.unpack_from("<ii", data, 38)
	image_size = len(pixels)
	file_size = 14 + 40 + image_size
	header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
	header += struct.pack(
		"<IiiHHIIiiII",
		40, width, height, 1, 24, BI_RGB, image_size,
		x_ppm, y_ppm, 0, 0,
	)
	Path(destination).write_bytes(header + pixels)
	print(f"U-Boot splash: converted {width}x{rows} 32-bit bitfields to 24-bit BI_RGB")


if __name__ == "__main__":
	if len(sys.argv) != 3:
		raise SystemExit(f"usage: {sys.argv[0]} INPUT.bmp OUTPUT.bmp")
	try:
		convert(sys.argv[1], sys.argv[2])
	except (OSError, ValueError, struct.error) as error:
		raise SystemExit(f"BMP conversion failed: {error}")

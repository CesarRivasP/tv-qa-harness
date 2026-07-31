"""Run once to (re)generate tests/fixtures/channel_unavailable.png.
Not part of the test suite itself — a fixture generator.
"""
from PIL import Image, ImageDraw

img = Image.new("RGB", (400, 120), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
draw.text((20, 40), "Channel unavailable", fill=(255, 255, 255))
img.save("tests/fixtures/channel_unavailable.png")

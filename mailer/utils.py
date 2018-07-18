from PIL import Image, ImageDraw


def generate_placeholder(width, height):
    image = Image.new('RGB', (int(width), int(height)), '#707070')
    draw = ImageDraw.Draw(image)

    x = 0
    y = 0
    line_size = 40
    while y < height:
        draw.polygon([(x, y), (x + line_size, y), (x + line_size * 2, y + line_size), (x + line_size * 2, y + line_size * 2)], fill='#808080')
        draw.polygon([(x, y + line_size), (x + line_size, y + line_size * 2), (x, y + line_size * 2)], fill='#808080')
        x = x + line_size * 2
        if (x > width):
            x = 0
            y = y + line_size * 2

    (textwidth, textheight) = draw.textsize(f"{width} x {height}")
    draw.text(((int(width)-textwidth)/2, (int(height)-textheight)/2), f"{width} x {height}", (255, 255, 255))

    return image

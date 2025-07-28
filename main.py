import argparse
import os
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont

# Font definitions based on the desired output sizes.
# render_font_size: The actual font size used for rendering.
# size: The dimensions (width and height) of the square of pixels to render and pack.
FONT_DEFINITIONS = [
    {"render_font_size": 12, "size": 12}, # Reverted render_font_size from 11 to 12
    {"render_font_size": 15, "size": 15}, # Reverted render_font_size from 14 to 15
    {"render_font_size": 20, "size": 20}, # Reverted render_font_size from 19 to 20
]

# Default font to use if "PingFang TC" is not found.
DEFAULT_FONT = "Arial Unicode MS"

def get_bit_code(pixel_value, bits_per_char):
    """
    Compresses a grayscale pixel value into 1, 2, or 4 bits.
    Pixel values are assumed to be 0-255 (0=black, 255=white).
    """
    if bits_per_char == 1:
        # 1-bit: 0 for white/light (>=128), 1 for black/dark (<128)
        return 1 if pixel_value <= 127 else 0
    elif bits_per_char == 2:
        # 2-bit: 0 (lightest) to 3 (darkest)
        if pixel_value < 0x44:  # 68
            return 3
        elif pixel_value < 0x66:  # 102
            return 2
        elif pixel_value < 0xaa:  # 170
            return 1
        else:
            return 0
    elif bits_per_char == 4:
        # 4-bit: 0 (lightest) to 15 (darkest)
        # Invert color (255-pixel_value) and scale to 0-15
        return (255 - pixel_value) // 16
    return 0

def render_character(char, font_path, font_def):
    """
    Renders a single character onto an image of 'size' x 'size' and returns its pixel data.
    The character is rendered in grayscale at (0,0) on the canvas.
    """
    render_font_size = font_def["render_font_size"]
    size = font_def["size"]

    # Create a new grayscale image (L mode for 8-bit pixels, 0=black, 255=white)
    image = Image.new("L", (size, size), color=255) # Start with white background
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype(font_path, render_font_size)
    except IOError:
        print(f"Warning: Font '{font_path}' not found. Falling back to '{DEFAULT_FONT}'.")
        try:
            font = ImageFont.truetype(DEFAULT_FONT, render_font_size)
        except IOError:
            print(f"Error: Default font '{DEFAULT_FONT}' also not found. Please ensure a valid font path is provided or a system font is available.")
            return None

    # Calculate text bounding box to adjust drawing position for middle alignment
    try:
        bbox = draw.textbbox((0, 0), char, font=font)
        text_height = bbox[3] - bbox[1]
        draw_y_offset = (size - text_height) / 2 - bbox[1]
    except AttributeError:
        # Fallback for older Pillow versions that might not have textbbox
        print("Warning: textbbox not available, using default (0,0) drawing offset. Character might appear 'sunk'.")
        draw_y_offset = 0

    # Draw the text at (0, draw_y_offset). Color 0 is black.
    draw.text((0, draw_y_offset), char, font=font, fill=0)

    # Get pixel data directly from the rendered image
    pixels = []
    for y in range(size):
        for x in range(size):
            pixels.append(image.getpixel((x, y)))

    return pixels

def pack_pixels_to_bytes(pixels, bits_per_char, size):
    """
    Packs pixel data into bytes based on bits_per_char, processing row by row.
    Ensures that any partially filled byte at the end of a row is written.
    """
    packed_bytes = bytearray()
    chars_per_byte = 8 // bits_per_char

    # Packing logic
    for y in range(size):
        current_byte = 0
        bits_in_current_byte = 0
        for x in range(size):
            # Calculate the index of the pixel in the flat list
            pixel_index = y * size + x
            pixel_value = pixels[pixel_index]

            code = get_bit_code(pixel_value, bits_per_char)

            # Shift the code into the current byte
            current_byte |= (code << bits_in_current_byte)
            bits_in_current_byte += bits_per_char

            # If the current byte is full, append it and reset
            if bits_in_current_byte >= 8:
                packed_bytes.append(current_byte)
                current_byte = 0
                bits_in_current_byte = 0

        # After processing all pixels in a row, if there are any remaining bits in current_byte,
        # append that byte
        if bits_in_current_byte > 0:
            packed_bytes.append(current_byte)

    return packed_bytes

def main():
    parser = argparse.ArgumentParser(description="Generate character map and rendered font data.")
    parser.add_argument("--text_file", required=True, help="Path to the input plain text file (UTF8).")
    parser.add_argument("--bits_per_char", type=int, choices=[1, 2, 4], required=True,
                        help="Number of bits per character pixel (1, 2, or 4).")
    parser.add_argument("--output_file", default="rome-v2.555",
                        help="Path to the output file for rendered character data.")
    parser.add_argument("--font_path", default="PingFang TC",
                        help="Path to the font file (e.g., 'PingFang.ttc' or 'NotoSansCJK-Regular.ttc').")

    args = parser.parse_args()

    text_file_path = args.text_file
    bits_per_char = args.bits_per_char
    output_file_path = args.output_file
    font_path = args.font_path

    # Step 1: Read the input text file
    try:
        with open(text_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: Input text file '{text_file_path}' not found.")
        return
    except Exception as e:
        print(f"Error reading input file: {e}")
        return

    # Step 2: Generate character list for processing and character map
    chars_to_process = [] # This list will contain characters to be rendered
    # unique_chars_seen will track characters already added to prevent duplicates,
    # except for Ideographic Space ('　').
    unique_chars_seen = set()
    
    # next_id will be assigned sequentially to each character added to chars_to_process
    # and will be used for the map file.
    next_id = 0x8080 # Starting ID

    char_map_data = [] # This list will hold the formatted map entries

    for char in content:
        # Ignore newlines and carriage returns
        if char == '\n' or char == '\r':
            continue

        # If it's Ideographic Space, add it to chars_to_process and the map.
        # Comment: Ideographic Space ('　') is allowed to appear multiple times in the list of characters to be processed and in the map.
        if char == '　':
            chars_to_process.append(char)
            # Add to map data with a new ID
            utf8_bytes = char.encode('utf-8')
            padded_bytes = list(utf8_bytes[:3]) + [0x00] * (3 - len(utf8_bytes))
            # Corrected format specifier from 0x2 to 02x
            char_map_data.append(f"{{0x{next_id:04x}, {{0x{padded_bytes[0]:02x}, 0x{padded_bytes[1]:02x}, 0x{padded_bytes[2]:02x}}}}}")
            
            # Increment next_id, skipping 0x00-0x7F in the last byte
            if (next_id & 0xFF) == 0xFF: # If the last byte is 0xFF
                next_id = (next_id & 0xFF00) + 0x100 + 0x80 # Increment the second to last byte, and set last byte to 0x80
            else:
                next_id += 1
                if (next_id & 0xFF) == 0x00: # If it just rolled over to 0x00, jump to 0x80
                     next_id += 0x80
        else:
            # For other characters, add to chars_to_process and map only if they haven't been seen before
            if char not in unique_chars_seen:
                chars_to_process.append(char)
                unique_chars_seen.add(char) # Mark as seen to prevent future duplicates

                # Add to map data with a new ID
                utf8_bytes = char.encode('utf-8')
                padded_bytes = list(utf8_bytes[:3]) + [0x00] * (3 - len(utf8_bytes))
                char_map_data.append(f"{{0x{next_id:04x}, {{0x{padded_bytes[0]:02x}, 0x{padded_bytes[1]:02x}, 0x{padded_bytes[2]:02x}}}}}")

                # Increment next_id, skipping 0x00-0x7F in the last byte
                if (next_id & 0xFF) == 0xFF: # If the last byte is 0xFF
                    next_id = (next_id & 0xFF00) + 0x100 + 0x80 # Increment the second to last byte, and set last byte to 0x80
                else:
                    next_id += 1
                    if (next_id & 0xFF) == 0x00: # If it just rolled over to 0x00, jump to 0x80
                         next_id += 0x80
            # If char is not '　' and already in unique_chars_seen, it's skipped for map/processing.


    # Output character map to a separate file for clarity
    map_output_file = output_file_path + ".map"
    with open(map_output_file, 'w', encoding='utf-8') as f:
        f.write("static const chinese_entry codepage_to_utf8[IMAGE_FONT_MULTIBYTE_SIMP_CHINESE_MAX_CHARS] = {\n")
        for entry in char_map_data:
            f.write(f"    {entry},\n") # Add four spaces for indentation
        f.write("};\n")

    print(f"Character map generated and saved to '{map_output_file}'.")

    # Step 3: Render characters, compress pixel data, and write to output file
    # total_characters_processed will now reflect the total count of entries in the map
    total_characters_processed = len(char_map_data) 
    try:
        with open(output_file_path, 'wb') as out_f:
            # Iterate through font sizes first
            for font_def in FONT_DEFINITIONS:
                # Then iterate through all characters to be processed
                for i, char in enumerate(chars_to_process):
                    pixels = render_character(char, font_path, font_def)
                    if pixels is None:
                        print(f"Skipping character '{char}' due to rendering error.")
                        continue

                    # Call pack_pixels_to_bytes
                    packed_data = pack_pixels_to_bytes(
                        pixels,
                        bits_per_char,
                        font_def["size"]
                    )
                    out_f.write(packed_data)
                
        print(f"Rendered character data saved to '{output_file_path}'.")

    except Exception as e:
        print(f"Error during character rendering or file writing: {e}")
        # Clean up partially written output file if an error occurs
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
        return

    # Step 4: Output total count of characters
    print(f"\nTotal characters processed (for map): {total_characters_processed}")
    print(f"Output file: {output_file_path}")
    print(f"Character map file: {map_output_file}")

if __name__ == "__main__":
    main()

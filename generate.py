#!/usr/bin/env python3
"""
Font rendering utility for generating Chinese character font data for the C3 project.
Handles both Simplified and Traditional Chinese characters with different bit depths.
"""

import argparse
import os
import re
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path


# Global configuration
ENCODING_MAP = {}
DEFAULT_FONT = "Arial Unicode MS"

# Language-specific configuration
LANGUAGES = {
    "sc": {
        "font": "fonts/sc.ttf",
        "extra_txt": "src/translation/simplified_chinese.c",
        "encoding_file": "src/core/encoding_simp_chinese.c",
        "output_name": "Simplified_Chinese.555",
        "output_path": "res/assets/i18n",
        "image_h": "src/core/image.h",
        "image_c": "src/core/image.c",
        "image_h_field": "IMAGE_FONT_MULTIBYTE_SIMP_CHINESE_MAX_CHARS",
        "image_c_field": "SIMP_CHINESE_FONTS_555_V2",
    },
    "tc": {
        "font": "fonts/tc.otf",
        "extra_txt": "src/translation/traditional_chinese.c",
        "encoding_file": "src/core/encoding_trad_chinese.c",
        "output_name": "Traditional_Chinese.555",
        "output_path": "res/assets/i18n",
        "image_h": "src/core/image.h",
        "image_c": "src/core/image.c",
        "image_h_field": "IMAGE_FONT_MULTIBYTE_TRAD_CHINESE_MAX_CHARS",
        "image_c_field": "TRAD_CHINESE_FONTS_555_V2",
    },
}

# Unicode range for Chinese characters
CHINESE_PATTERN = r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]'

# Font definitions for different sizes to render
FONT_DEFINITIONS = [
    {"render_font_size": 12, "size": 12},
    {"render_font_size": 15, "size": 15},
    {"render_font_size": 20, "size": 20},
]

class C3FontUtil:
    def __init__(self, font_path):
        self.font_path = font_path
        self.font_cache = {}
        
    def _get_font(self, render_font_size):
        cache_key = (self.font_path, render_font_size)
        if cache_key in self.font_cache:
            return self.font_cache[cache_key]

        try:
            font = ImageFont.truetype(self.font_path, render_font_size)
        except IOError:
            print(f"Warning: Font '{self.font_path}' not found. Falling back to '{DEFAULT_FONT}'.")
            try:
                font = ImageFont.truetype(DEFAULT_FONT, render_font_size)
            except IOError:
                print(f"Error: Default font '{DEFAULT_FONT}' also not found. Please ensure a valid font path is provided or a system font is available.")
                return None

        self.font_cache[cache_key] = font
        return font

    def render_character(self, char, font_def):
        render_font_size = font_def["render_font_size"]
        size = font_def["size"]

        # Create a new grayscale image (L mode for 8-bit pixels, 0=black, 255=white)
        image = Image.new("L", (size, size), color=255) # Start with white background
        draw = ImageDraw.Draw(image)

        font = self._get_font(render_font_size)
        if font is None:
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

        # Get pixel data more efficiently using getdata()
        pixels = list(image.getdata())
        return pixels

    def pack_pixels_to_bytes(self, pixels, bits_per_char, size):
        packed_bytes = bytearray()

        # Precompute bit masks and shifts for efficiency
        codes_per_byte = 8 // bits_per_char
        bit_mask = (1 << bits_per_char) - 1  # Create mask for bits_per_char bits

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

def get_bit_code(pixel_value, bits_per_char):
    """
    Compresses a grayscale pixel value into 1, 2, or 4 bits.
    Pixel values are assumed to be 0-255 (0=black, 255=white).
    """
    if bits_per_char == 1:
        # 1-bit: 0 for white/light (>=128), 1 for black/dark (<128)
        return 1 if pixel_value < 128 else 0
    elif bits_per_char == 2:
        # 2-bit: 0 (lightest) to 3 (darkest)
        # Using bit shifting for division
        return 3 - (pixel_value >> 6)
    elif bits_per_char == 4:
        # 4-bit: 0 (lightest) to 15 (darkest)
        # Invert color (255-pixel_value) and scale to 0-15
        return (255 - pixel_value) >> 4
    return 0

def read_extra_characters(translation_file_path):
    """
    Read extra characters from translation file and update encoding map.
    
    Returns:
        tuple: (id_to_char, char_to_id, new_chars)
    """
    id_to_char = ENCODING_MAP.copy()
    last_char_id = list(id_to_char.keys())[-1]
    char_to_id = {v: k for k, v in ENCODING_MAP.items()}
    
    with open(translation_file_path, 'r', encoding='utf-8') as f:
        translation_content = f.read()
        new_chars = []
        matches = re.findall(CHINESE_PATTERN, translation_content)
        for match in matches:
            if match not in char_to_id:
                new_chars.append(match)
                if (last_char_id & 0xFF) == 0xFF:  # If the last byte is 0xFF
                    last_char_id = (last_char_id & 0xFF00) + 0x100 + 0x80  # Increment the second to last byte, and set last byte to 0x80
                else:
                    last_char_id += 1
                    if (last_char_id & 0xFF) == 0x00:  # If it just rolled over to 0x00, jump to 0x80
                        last_char_id += 0x80

                char_to_id[match] = last_char_id
                id_to_char[last_char_id] = match

    print(f"[Step 1] New characters: {len(new_chars)}:")
    return id_to_char, char_to_id, new_chars

def generate_char_map_data(id_to_char):
    """
    Generate character map data for encoding file.
    
    Returns:
        tuple: (chars_to_process, char_map_data)
    """
    chars_to_process = []
    char_map_data = []
    
    for char_id, char in id_to_char.items():
        chars_to_process.append(char)
        utf8_bytes = char.encode('utf-8')
        padded_bytes = list(utf8_bytes[:3]) + [0x00] * (3 - len(utf8_bytes))
        char_map_data.append(f"{{0x{char_id:04x}, {{0x{padded_bytes[0]:02x}, 0x{padded_bytes[1]:02x}, 0x{padded_bytes[2]:02x}}}}}")
    
    return chars_to_process, char_map_data

def update_encoding_file(encoding_file_path, image_h_field, char_map_data):
    """
    Update encoding file with new character map data.
    """
    try:
        with open(encoding_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find the start and end positions of the codepage_to_utf8 array
        start_marker = f"static const chinese_entry codepage_to_utf8[{image_h_field}] = {{"
        end_marker = "};"

        start_idx = content.find(start_marker)
        if start_idx == -1:
            print(f"  - Error: Could not find codepage_to_utf8 array definition in {encoding_file_path}")
            return False

        # Find the end position of the array (first matching "};"）
        brace_count = 1
        search_idx = start_idx + len(start_marker)
        end_idx = -1

        while search_idx < len(content) and end_idx == -1:
            if content[search_idx] == '{':
                brace_count += 1
            elif content[search_idx] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = search_idx
                    break
            search_idx += 1

        if end_idx == -1:
            print(f"  - Error: Could not find the end position of the codepage_to_utf8 array in {encoding_file_path}")
            return False

        # 构建新的数组内容
        new_array_content = "\n"
        for entry in char_map_data:
            new_array_content += f"    {entry},\n"

        # 替换原数组内容
        new_content = content[:start_idx + len(start_marker)] + new_array_content + content[end_idx:]

        # Write back to file
        with open(encoding_file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print(f"  - Successfully updated character map in '{encoding_file_path}'")
        return True
    except Exception as e:
        print(f"  - Error updating {encoding_file_path} file: {e}")
        return False

def generate_font_data(font_util, chars_to_process, bits_per_char, output_file_path):
    """
    Generate font data by rendering characters and writing to output file.
    
    Returns:
        int: Total number of characters processed
    """
    total_characters_processed = len(chars_to_process)

    # Ensure output directory exists
    output_dir = os.path.dirname(output_file_path)
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"  - Created output directory: {output_dir}")
        except Exception as e:
            print(f"  - Error creating output directory '{output_dir}': {e}")
            return 0

    try:
        with open(output_file_path, 'wb') as out_f:
            # Iterate through font sizes first
            for font_def in FONT_DEFINITIONS:
                # Prepare a list to hold all packed data for this font size
                all_packed_data = bytearray()

                # Then iterate through all characters to be processed
                for char in chars_to_process:
                    pixels = font_util.render_character(char, font_def)
                    if pixels is None:
                        print(f"Skipping character '{char}' due to rendering error.")
                        continue

                    # Call pack_pixels_to_bytes
                    packed_data = font_util.pack_pixels_to_bytes(
                        pixels,
                        bits_per_char,
                        font_def["size"]
                    )
                    # Accumulate data instead of writing immediately
                    all_packed_data.extend(packed_data)

                # Write all data for this font size at once
                out_f.write(all_packed_data)

        print(f"  - Successfully saved rendered character data to '{output_file_path}'")
    except Exception as e:
        print(f"  - Error during character rendering or file writing: {e}")
        # Clean up partially written output file if an error occurs
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
        return 0

    return total_characters_processed

def update_image_h_file(image_h_path, image_h_field, total_characters_processed):
    """
    Update IMAGE_FONT_MULTIBYTE_*_MAX_CHARS in image.h file.
    """
    try:
        with open(image_h_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        print(f"  - Successfully read '{image_h_path}'")

        # Find the line with the #define for the specified field
        updated = False
        for i, line in enumerate(lines):
            # Look for #define with the specific field, allowing for various whitespace patterns
            if re.match(r'^\s*#\s*define\s+' + re.escape(image_h_field) + r'\s+\d+', line):
                # Extract the indentation and comments
                leading_whitespace = re.match(r'^(\s*)', line).group(1)
                # Find if there's a comment after the value
                comment_match = re.search(r'(\s*//.*)$', line)
                comment = comment_match.group(1) if comment_match else ''
                
                # Replace only the value while preserving formatting and comments
                lines[i] = f"{leading_whitespace}#define {image_h_field} {total_characters_processed}{comment}\n"
                updated = True
                print(f"  - Successfully updated {image_h_field} to {total_characters_processed} in {image_h_path}")
                break

        if not updated:
            print(f"  - Warning: No matches found for {image_h_field} in image.h. Value may already be correct.")
            return True

        # Write back to file preserving original line endings and formatting
        with open(image_h_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"  - Error updating {image_h_path} file: {e}")
        return False

def update_image_c_file(image_c_path, image_c_field, output_name):
    """
    Update CHINESE_FONTS_555_V2 in image.c file.
    """
    try:
        with open(image_c_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        print(f"  - Successfully read '{image_c_path}'")

        # Find the line with the static const char array for the specified field
        updated = False
        for i, line in enumerate(lines):
            # Look for static const char with the specific field, allowing for various whitespace patterns
            # Try multiple patterns to match different formatting styles
            patterns = [
                r'^\s*static\s+const\s+char\s+' + re.escape(image_c_field) + r'\s*\[.*?\]\s*=\s*"[^"]*";',
                r'^\s*static\s+const\s+char\s+' + re.escape(image_c_field) + r'\s*\[.*?\]\s*=\s*ASSETS_DIR\s*"[^"]*";',
                r'^\s*static\s+const\s+char\s+' + re.escape(image_c_field) + r'\s*\[.*?\]\s*=\s*ASSETS_DIRECTORY\s*"[^"]*";',
            ]
            
            for pattern in patterns:
                if re.match(pattern, line):
                    # Extract the indentation
                    leading_whitespace = re.match(r'^(\s*)', line).group(1)
                    
                    # Replace only the string value while preserving formatting
                    lines[i] = f"{leading_whitespace}static const char {image_c_field}[NAME_SIZE_LONG] = ASSETS_DIRECTORY \"/i18n/{output_name}\";\n"
                    updated = True
                    print(f"  - Updated {image_c_field} to 'ASSETS_DIRECTORY \"/i18n/{output_name}\"' in {image_c_path}")
                    break
            
            if updated:
                break

        if not updated:
            print(f"  - Warning: No matches found for {image_c_field} in image.c.")
            return True

        # Write back to file preserving original line endings and formatting
        with open(image_c_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"  - Error updating {image_c_path} file: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Generate character map and rendered font data.")
    parser.add_argument("--lang", "-l", choices=["sc", "tc"], required=True)
    parser.add_argument("--bits", "-b", type=int, choices=[1, 2, 4], default=4)
    parser.add_argument("--augustus-project-path", "-p", required=True)

    args = parser.parse_args()
    bits_per_char = args.bits
    
    target_language = LANGUAGES.get(args.lang)
    if not target_language:
        print(f"Error: language '{args.lang}' not found")
        return
    
    # Importing CODING_MAP by specified 'lang':
    global ENCODING_MAP
    if args.lang == "sc":
        from encoding_map import sc
        ENCODING_MAP.update(sc.SC_MAP)
    elif args.lang == "tc":
        from encoding_map import tc
        ENCODING_MAP.update(tc.TC_MAP)
    else:
        raise ValueError(f"No encoding_map for Language:{args.lang}")
    
    AUGUSTUS_PROJECT_PATH = os.path.abspath(args.augustus_project_path)
    if not os.path.exists(AUGUSTUS_PROJECT_PATH):
        print(f"Error: '{AUGUSTUS_PROJECT_PATH}' is invalid")
        return

    # Helper function to get file paths
    def get_language_file_path(key):
        return os.path.join(AUGUSTUS_PROJECT_PATH, os.path.normpath(target_language.get(key)))

    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(SCRIPT_DIR, target_language.get('font'))
    translation_file_path = get_language_file_path('extra_txt')
    encoding_file_path = get_language_file_path('encoding_file')
    image_h_path = get_language_file_path('image_h')
    image_h_field = target_language.get('image_h_field')
    image_c_path = get_language_file_path('image_c')
    image_c_field = target_language.get('image_c_field')
    output_name = target_language.get('output_name')
    output_file_path = os.path.join(AUGUSTUS_PROJECT_PATH, os.path.normpath(target_language.get('output_path')), output_name)

    print(f"[Step 1] Read extra characters from: '{translation_file_path}' and append to encoding_map...")
    id_to_char, char_to_id, new_chars = read_extra_characters(translation_file_path)

    print(f"[Step 2] Updating '{encoding_file_path}' ...")
    chars_to_process, char_map_data = generate_char_map_data(id_to_char)
    if not update_encoding_file(encoding_file_path, image_h_field, char_map_data):
        return

    print("[Step 3] Rendering characters and generating font data...")
    font_util = C3FontUtil(font_path)
    total_characters_processed = generate_font_data(font_util, chars_to_process, bits_per_char, output_file_path)
    if total_characters_processed == 0:
        return

    print(f"[Step 4] Summary:")
    print(f"  - Total characters processed (for map): {total_characters_processed}")
    print(f"  - Output file: {output_file_path}")
    print(f"  - Character map updated in: {encoding_file_path}")

    print(f"[Step 5] Updating '{image_h_path}' file...")
    if not update_image_h_file(image_h_path, image_h_field, total_characters_processed):
        return

    print(f"[Step 6] Updating '{image_c_path} file...")
    if not update_image_c_file(image_c_path, image_c_field, output_name):
        return

if __name__ == "__main__":
    main()
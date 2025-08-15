import argparse
import os
import re
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

LANGUAGES = {
    "sc": {
        "font": "fonts/AlibabaPuHuiTi-3-55-Regular.ttf",
        "base_txt": "raw_sc.txt",
        "extra_txt": "src/translation/simplified_chinese.c",
        "image_h": "src/core/image.h",
        "image_c": "src/core/image.c",
        "encoding_file": "src/core/encoding_simp_chinese.c",
        "output_name": "Simplified_Chinese.555",
        "output_path": "res/assets/i18n/",
        "image_h_field": "IMAGE_FONT_MULTIBYTE_SIMP_CHINESE_MAX_CHARS",
        "image_c_field": "SIMP_CHINESE_FONTS_555_V2",
    },
}

CHINESE_PATTERN = r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]'

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

# Cache for loaded fonts
font_cache = {}

def get_bit_code(pixel_value, bits_per_char):
    """
    Compresses a grayscale pixel value into 1, 2, or 4 bits.
    Pixel values are assumed to be 0-255 (0=black, 255=white).
    """
    # Using bit operations for better performance
    if bits_per_char == 1:
        # 1-bit: 0 for white/light (>=128), 1 for black/dark (<128)
        return 1 if pixel_value < 128 else 0
    elif bits_per_char == 2:
        # 2-bit: 0 (lightest) to 3 (darkest)
        # Using bit shifting for division by 85 (255/3)
        return 3 - (pixel_value >> 6)
    elif bits_per_char == 4:
        # 4-bit: 0 (lightest) to 15 (darkest)
        # Invert color (255-pixel_value) and scale to 0-15
        return (255 - pixel_value) >> 4
    return 0

def get_font(font_path, render_font_size):
    """
    Get font from cache or load it, with fallback to default font.
    """
    cache_key = (font_path, render_font_size)
    if cache_key in font_cache:
        return font_cache[cache_key]
    
    try:
        font = ImageFont.truetype(font_path, render_font_size)
    except IOError:
        print(f"Warning: Font '{font_path}' not found. Falling back to '{DEFAULT_FONT}'.")
        try:
            font = ImageFont.truetype(DEFAULT_FONT, render_font_size)
        except IOError:
            print(f"Error: Default font '{DEFAULT_FONT}' also not found. Please ensure a valid font path is provided or a system font is available.")
            return None
    
    font_cache[cache_key] = font
    return font


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

    font = get_font(font_path, render_font_size)
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

def pack_pixels_to_bytes(pixels, bits_per_char, size):
    """
    Packs pixel data into bytes based on bits_per_char, processing row by row.
    Ensures that any partially filled byte at the end of a row is written.
    """
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

def main():
    parser = argparse.ArgumentParser(description="Generate character map and rendered font data.")
    parser.add_argument("--lang", "-l", choices=["sc"], default="sc")
    parser.add_argument("--bits", "-b", type=int, choices=[1, 2, 4], default=4)
    parser.add_argument("--augustus-project-path", "-a", required=True)

    args = parser.parse_args()
    bits_per_char = args.bits
    lang = args.lang
    AUGUSTUS_PROJECT_PATH = os.path.abspath(args.augustus_project_path)
    if not os.path.exists(AUGUSTUS_PROJECT_PATH):
        print(f"Error: '{AUGUSTUS_PROJECT_PATH}' is invalid")
        return
    
    target_language = LANGUAGES.get(lang)
    if not target_language:
        print(f"Error: language '{lang}' not found")
        return
    
    # Helper function to get file paths
    def get_language_file_path(key):
        return os.path.join(AUGUSTUS_PROJECT_PATH, os.path.normpath(target_language.get(key)))
    
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    text_file_path = os.path.join(SCRIPT_DIR, target_language.get('base_txt'))
    font_path = os.path.join(SCRIPT_DIR, target_language.get('font'))
    translation_file_path = get_language_file_path('extra_txt')
    encoding_file_path = get_language_file_path('encoding_file')
    image_h_path = get_language_file_path('image_h')
    image_h_field = target_language.get('image_h_field')
    image_c_path = get_language_file_path('image_c')
    image_c_field = target_language.get('image_c_field')
    output_name = target_language.get('output_name')
    output_file_path = os.path.join(AUGUSTUS_PROJECT_PATH, os.path.normpath(target_language.get('output_path')), output_name)

        
    # Step 1: Read raw text
    print("[Step 1] Reading raw text file...")
    try:
        with open(text_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"  - Successfully read '{text_file_path}'")
    except FileNotFoundError:
        print(f"  - Error: Input text file '{text_file_path}' not found.")
        return
    except Exception as e:
        print(f"  - Error reading input file: {e}")
        return
    
    # Step 1.5: Read extra text from translation file
    print("[Step 1.5] Reading translation file...")
    try:
        with open(translation_file_path, 'r', encoding='utf-8') as f:
            translation_content = f.read()
        print(f"  - Successfully read '{translation_file_path}'")
        
        # Extract Chinese characters and punctuation
        chinese_chars = set()
        # Match Chinese characters and common Chinese punctuation
        matches = re.findall(CHINESE_PATTERN, translation_content)
        chinese_chars.update(matches)
        
        # Filter out characters that already exist in the main text
        existing_chars = set(content)
        new_chars = chinese_chars - existing_chars
        
        if new_chars:
            # Add new characters to the end of content
            new_content = content + ''.join(sorted(new_chars))
            content = new_content
            print(f"  - Added {len(new_chars)} new Chinese characters from translation file")
        else:
            print("  - No new Chinese characters found in translation file")     
    except FileNotFoundError:
        print(f"  - Warning: Translation file '{translation_file_path}' not found. Proceeding with original text only.")
    except Exception as e:
        print(f"  - Warning: Error reading translation file: {e}. Proceeding with original text only.")

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

    print("[Step 2] Updating character map in encoding file...")
    try:
        with open(encoding_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"  - Successfully read '{encoding_file_path}'")
        
        # Find the start and end positions of the codepage_to_utf8 array
        start_marker = f"static const chinese_entry codepage_to_utf8[{image_h_field}] = {{"
        end_marker = "};"
        
        start_idx = content.find(start_marker)
        if start_idx == -1:
            print(f"  - Error: Could not find codepage_to_utf8 array definition in {encoding_file_path}")
            return
            
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
            return
        
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
        
    except Exception as e:
        print(f"  - Error updating {encoding_file_path} file: {e}")
        return

    # Step 3: Render characters, compress pixel data, and write to output file
    print("[Step 3] Rendering characters and generating font data...")
    # total_characters_processed will now reflect the total count of entries in the map
    total_characters_processed = len(char_map_data) 
    
    # Prepare all font objects first to avoid repeated loading
    fonts = {}
    for font_def in FONT_DEFINITIONS:
        render_font_size = font_def["render_font_size"]
        fonts[render_font_size] = get_font(font_path, render_font_size)
    
    # Ensure output directory exists
    output_dir = os.path.dirname(output_file_path)
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"  - Created output directory: {output_dir}")
        except Exception as e:
            print(f"  - Error creating output directory '{output_dir}': {e}")
            return
    
    try:
        with open(output_file_path, 'wb') as out_f:
            # Iterate through font sizes first
            for font_def in FONT_DEFINITIONS:
                # Prepare a list to hold all packed data for this font size
                all_packed_data = bytearray()
                
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
        return

    # Step 4: Output total count of characters
    print(f"[Step 4] Summary:")
    print(f"  - Total characters processed (for map): {total_characters_processed}")
    print(f"  - Output file: {output_file_path}")
    print(f"  - Character map updated in: {encoding_file_path}")
    
    # Step 5: Update IMAGE_FONT_MULTIBYTE_SIMP_CHINESE_MAX_CHARS in image.h
    print("[Step 5] Updating image.h file...")
    try:
        with open(image_h_path, 'r', encoding='utf-8') as f:
            image_h_content = f.read()
        print(f"  - Successfully read '{image_h_path}'")
        
        # Find and replace the value of IMAGE_FONT_MULTIBYTE_SIMP_CHINESE_MAX_CHARS
        # Use raw strings to avoid escaping issues
        pattern = r'#define\s+' + image_h_field + r'\s+\d+'
        replacement = f'#define {image_h_field} {total_characters_processed}'
        
        # Use regex substitution
        new_content = re.sub(pattern, replacement, image_h_content)
        
        # If the first pattern didn't match, try a more flexible pattern
        if new_content == image_h_content:
            print(f"  - Trying more flexible pattern...")
            pattern2 = r'#define\s+' + image_h_field + r'\s*\d+'
            new_content = re.sub(pattern2, replacement, image_h_content)
            
            # If still no match, try an even more flexible pattern
            if new_content == image_h_content:
                print(f"  - Trying even more flexible pattern...")
                pattern3 = r'#define\s+' + image_h_field + r'(\s*\d*)'
                replacement3 = f'#define {image_h_field} {total_characters_processed}'
                new_content = re.sub(pattern3, replacement3, image_h_content, count=1)
        
        # Check if replacement was successful
        if new_content == image_h_content:
            print(f"  - Warning: No matches found for pattern in image.h. Value may already be correct.")
        else:
            print(f"  - Successfully updated {image_h_field} to {total_characters_processed} in {image_h_path}")
        
        # Write back to file
        with open(image_h_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
    except Exception as e:
        print(f"  - Error updating {image_h_path} file: {e}")
        return
    
    # Step 6: Update image.c
    print("[Step 6] Updating image.c file...")
    try:
        with open(image_c_path, 'r', encoding='utf-8') as f:
            image_c_content = f.read()
        print(f"  - Successfully read '{image_c_path}'")
        
        # Find and replace the value of CHINESE_FONTS_555_V2
        # Use a more flexible regular expression
        # pattern = r'static const char CHINESE_FONTS_555_V2\[.*?\] = (?:ASSETS_DIR )?"[^"]+";'
        # Use raw string to avoid escaping issues
        pattern = rf'static const char {image_c_field}\[.*?\] = (?:ASSETS_DIR )?"[^"]+";'
        # Fix path separators and escape characters, use the output filename for the corresponding language
        replacement = f'static const char {image_c_field}[NAME_SIZE_LONG] = ASSETS_DIRECTORY "/i18n/{output_name}";'
        
        # Use regex substitution
        new_content = re.sub(pattern, replacement, image_c_content)
        
        # Write back to file
        with open(image_c_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"  - Updated {image_c_field} to 'ASSETS_DIRECTORY \"/i18n/{output_name}\"' in {image_c_path}")
        
    except Exception as e:
        print(f"  - Error updating {image_c_path} file: {e}")
        return

if __name__ == "__main__":
    main()

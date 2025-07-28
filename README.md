# What is this

This tool helps expanding character set supported by [Augustus](https://github.com/Keriew/augustus), namely Chinese (Simplified and Traditional), Japanese, Korean.

**This tool is heavily vibe coded.**

Julius/Augusts uses 4-bit grayscale for character rendering, and each character comes in 3 sizes - 12x12, 15x15, 20x20. This means every rendered character takes 384.5 bytes storage.

# How to use
1. Prepare a raw text file in UTF8 encoding. The one present in this repository contains all the characters initially supported by the Chinese version of Caesar 3, do not remove any characters from it and only append new characters.
2. Prepare a font, be aware of legal requirements. I use [this one](https://github.com/paraself/PingFang-Fonts).
3. Run the python script.
4. A mapping file will be generated. Replace [codepage_to_utf8](https://github.com/bvschaik/julius/blob/17673a800bab934127c68b3c180d1a2ff20f48b9/src/core/encoding_simp_chinese.c#L15).
5. Update [IMAGE_FONT_MULTIBYTE_SIMP_CHINESE_MAX_CHARS ](https://github.com/bvschaik/julius/blob/17673a800bab934127c68b3c180d1a2ff20f48b9/src/core/image.h#L10)
6. Move the rome-v2.555 file generated to the language pack. A Chinese language pack consists of the following files
* c3.eng 
* C3_mm.eng
* rome.555
* rome-v2.555

# Known issue and TODOs
1. Font size == 12px does not guarantee a character to be completely contained within a 12x12 area. It depends on the font and rendering engine behavior. As a result, some character's edges are clipped.
2. Lift the exemption that Ideographic Space ('　') can appear multiple times in the mapping
3. Investigate why we need to skip the count between 0x00-0x80.
4. Adjust language pack support in Julius/Augustus, make file names more meaningful.

# Credits
[@bvschaik](https://github.com/bvschaik), the creator of [Julius](https://github.com/bvschaik/julius), shared a workflow with me and I developed this tool based on it.

The original workflow requires extensive human operation
1. Add characters to an HTML file, make sure styling is correct, then open it with some browser
2. Manually output page screenshots of 3 different font sizes
3. Compile a C program and feed it with the screenshots
4. Then same steps as this tool to apply to the game
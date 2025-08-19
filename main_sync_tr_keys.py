import re
import argparse

def parse_translation_strings(content):
    """Match translation kv lines"""
    pattern = r'\{\s*(TR_\w+)\s*,\s*([\s\S]*?)\s*\},?'
    order = []
    strings = {}
    
    for match in re.finditer(pattern, content):
        key = match.group(1)
        value = match.group(2).strip()
        if key not in strings:
            order.append(key)
            strings[key] = value
    
    return order, strings

def main():
    parser = argparse.ArgumentParser(description="Sync translation keys to other language")
    parser.add_argument("--source-file", default="english.c", help="Path to the source translation file (Default: english.c).")
    parser.add_argument("--target-file", help="Path to target translation file. (e.g., simplified_chinese.c)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write TARGET_FILE")
    
    args = parser.parse_args()
    
    with open(args.source_file, 'r', encoding='utf-8') as f:
        source_file_content = f.read()
    
    with open(args.target_file, 'r', encoding='utf-8') as f:
        target_file_content = f.read()

    source_file_order, source_file_strings = parse_translation_strings(source_file_content)
    target_file_order, target_file_strings = parse_translation_strings(target_file_content)

    new_strings = []
    for key in source_file_order:
        value = target_file_strings.get(key, source_file_strings[key])
        new_strings.append(f'    {{{key}, {value}}},')

    def replace_strings(match):
        return f'{match.group(1)}\n' + '\n'.join(new_strings) + '\n' + match.group(3)

    updated_content = re.sub(
        r'(static translation_string all_strings\[\] = \{)([\s\S]*?)(\};)',
        replace_strings,
        target_file_content,
        flags=re.DOTALL
    )

    print(updated_content)

    if not args.dry_run:
        with open(args.target_file, 'w', encoding='utf-8') as f:
            f.write(updated_content)

if __name__ == '__main__':
    main()
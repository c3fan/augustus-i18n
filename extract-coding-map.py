#!/usr/bin/env python

# 从C++代码中提取entries数组并转换为Python字典
def extract_cpp_entries_to_python_map(cpp_code):
    import re

    # 使用正则表达式匹配entries数组中的每一项
    pattern = r'\{0x([0-9A-Fa-f]+),\s*0x([0-9A-Fa-f]+)\}'
    matches = re.findall(pattern, cpp_code)

    # 转换为字典，key和value均为整数
    entries_map = {}
    for internal_hex, unicode_hex in matches:
        internal = int(internal_hex, 16)
        unicode_val = int(unicode_hex, 16)
        entries_map[internal] = unicode_val

    return entries_map

# 从traditionalchinesecodec.cpp文件读取内容
import os
import argparse

def read_cpp_file(file_path):
    """读取C++源文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        print(f"错误: 未找到文件 {file_path}")
        return None
    except Exception as e:
        print(f"读取文件时发生错误: {e}")
        return None

# 设置命令行参数解析
parser = argparse.ArgumentParser(description='从C++源文件提取编码映射并生成Python映射文件')
parser.add_argument('-i', '--input-file', 
                   help='输入的C++源文件路径',
                   required=True)
parser.add_argument('-o', '--output-file', 
                   help='输出的Python映射文件路径',
                   required=True)

args = parser.parse_args()

# 使用命令行参数作为文件路径
cpp_file_path = args.input_file
tc_map_path = args.output_file

# 读取C++文件内容
cpp_code = read_cpp_file(cpp_file_path)

if cpp_code is None:
    print("无法读取C++文件，程序退出。")
    exit(1)

# 转换并获取结果
entries_map = extract_cpp_entries_to_python_map(cpp_code)

filecontent = "coding_map = {\n"
for i, (key, value) in enumerate(entries_map.items()):
    # Convert Unicode code point to actual character
    char = chr(value)
    # Escape single quotes and backslashes in the character
    if char == '\\' or char == "'":
        char = f'\\{char}'
    filecontent += f"    0x{key:x}: '{char}'"
    if i < len(entries_map) - 1:
        filecontent += ","
    filecontent += "\n"
    # print(f"{i}: 0x{key:X}: 0x{value:X}")
    
filecontent += "}"

# 将内容写入tc_map.py文件
try:
    with open(tc_map_path, 'w', encoding='utf-8') as f:
        f.write(filecontent)
    print(f"成功将映射关系写入 {tc_map_path}")
except Exception as e:
    print(f"写入文件 {tc_map_path} 时发生错误: {e}")
    exit(1)
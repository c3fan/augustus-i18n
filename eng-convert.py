#!/usr/bin/env python

import argparse
import struct
import xml.etree.ElementTree as ET
from xml.dom import minidom
import codecs
from pathlib import Path

NAME_TEXT_FILE = "C3 textfile."
NAME_MSG_FILE = "C3 MMfile."
MAX_GROUP_INDEX_ENTRIES = 1000

INTERNAL_TO_UNICODE = {}
UNICODE_TO_INTERNAL = {}

def import_encoding_map(encoding):
    if encoding == "tc":
        from encoding_map import tc
        INTERNAL_TO_UNICODE.update(tc.TC_MAP)
        INTERNAL_TO_UNICODE.update(tc.BIG5_MAP)
        UNICODE_TO_INTERNAL.update({ v: k for k, v in tc.TC_MAP.ENCODING_MAP_ORIGIN.items() })
    elif encoding == "sc":
        from encoding_map import sc
        INTERNAL_TO_UNICODE.update(sc.SC_MAP)
        UNICODE_TO_INTERNAL.update({ v: k for k, v in INTERNAL_TO_UNICODE.items() })
    else:
        raise ValueError(f"Encoding err: {encoding}")
        
def _parse_int16(data, start, end):
    return struct.unpack('<h', data[start:end])[0]
    
def _parse_int32(data, start, end):
    return struct.unpack('<i', data[start:end])[0]

def _read_message_text(item, text_data):
    if 'offset' in item and item['offset'] > 0:
        i = item['offset']
        text_bytes = bytearray()
        while i < len(text_data):
            byte = text_data[i]
            i += 1
            if byte != 0:
                text_bytes.append(byte)
            else:
                item['text'] = _decode_str(text_bytes)
                break
            
def _encode_str(str_unicode):
    result = bytearray()
    for char in str_unicode:
        code = UNICODE_TO_INTERNAL.get(char)
        if code is not None:
            # little endian
            result.append(code & 0xFF)
            result.append((code >> 8) & 0xFF)
        else:
            # 不在映射中的字符，使用UTF-8编码
            result.extend(char.encode('utf-8'))
    return result
            
def _decode_str(str_bytes):
    result = ""
    i = 0
    str_len = len(str_bytes)
    while i < str_len:
        byte = str_bytes[i]
        if byte == 0x20:
            result += chr(byte)
            i += 1
            continue

        if (i+1 < len(str_bytes)):
            low = byte
            high = str_bytes[i+1]
            key = (high << 8) | low
            tmp = INTERNAL_TO_UNICODE.get(key)
            if tmp:
                result += tmp
                i += 2
            else:
                result += chr(byte)
                i += 1
        else:
            result += chr(byte)
            i += 1
    
    return result

def _gen_text_byte(item, index):
    if 'text' in item:    
        text = item['text']
        if len(text) > 0:
            text_bytes = _encode_str(text)
            text_bytes.append(0)
            item['text_bytes'] = text_bytes
            item['offset'] = index
            return len(text_bytes)
    item['offset'] = index
    return 0

def _extend_bytes(text_data, item):
    text_bytes = item['text_bytes']
    if len(text_bytes) > 0:
        text_data.extend(text_bytes)

class MessageEntry:
    def __init__(self, entry_id):
        self.id = entry_id
        self.type = 0
        self.subtype = 0
        self.urgent = False
        self.dialog = {'x': 0, 'y': 0, 'width': 0, 'height': 0}
        self.image = {'graphic': 0, 'x': 0, 'y': 0}
        self.image2 = {'graphic': 0, 'x': 0, 'y': 0}
        self.title = {'x': 0, 'y': 0, 'text': '', 'offset': 0, 'text_bytes': bytearray()}
        self.subtitle = {'x': 0, 'y': 0, 'text': '', 'offset': 0, 'text_bytes': bytearray()}
        self.video = {'x': 0, 'y': 0, 'text': '', 'offset': 0, 'text_bytes': bytearray()}
        self.content = {'text': '', 'offset': 0, 'text_bytes': bytearray()}
    
    def parse_eng_index(self, entry_data):
        self.type = _parse_int16(entry_data, 0, 2)
        self.subtype = _parse_int16(entry_data, 2, 4)
        self.dialog["x"] = _parse_int16(entry_data, 6, 8)
        self.dialog["y"] = _parse_int16(entry_data, 8, 10)
        self.dialog["width"] = _parse_int16(entry_data, 10, 12)
        self.dialog["height"] = _parse_int16(entry_data, 12, 14)
        self.image["graphic"] = _parse_int16(entry_data, 14, 16)
        self.image["x"] = _parse_int16(entry_data, 16, 18)
        self.image["y"] = _parse_int16(entry_data, 18, 20)
        self.image2["graphic"] = _parse_int16(entry_data, 20, 22)
        self.image2["x"] = _parse_int16(entry_data, 22, 24)
        self.image2["y"] = _parse_int16(entry_data, 24, 26)
        self.title['x'] = _parse_int16(entry_data, 26, 28)
        self.title['y'] = _parse_int16(entry_data, 28, 30)
        self.subtitle['x'] = _parse_int16(entry_data, 30, 32)
        self.subtitle['y'] = _parse_int16(entry_data, 32, 34)
        self.video['x'] = _parse_int16(entry_data, 38, 40)
        self.video['y'] = _parse_int16(entry_data, 40, 42)
        self.urgent = _parse_int32(entry_data, 56, 60) == 1
        self.video['offset'] = _parse_int32(entry_data, 60, 64)
        self.title['offset'] = _parse_int32(entry_data, 68, 72)
        self.subtitle['offset'] = _parse_int32(entry_data, 72, 76)
        self.content['offset'] = _parse_int32(entry_data, 76, 80)
        
    def read_eng_text(self, text_data):
        _read_message_text(self.video, text_data)
        _read_message_text(self.title, text_data)
        _read_message_text(self.subtitle, text_data)
        _read_message_text(self.content, text_data)
        
    def parse_xml_elem(self, xml_elem):
        self.type = int(xml_elem.get('type'))
        self.subtype = int(xml_elem.get('subtype'))
        self.urgent = bool(xml_elem.get('urgent'))
        for child in xml_elem:
            if child.tag == 'dialog':
                self.dialog = {
                    "x": int(child.get("x")),
                    "y": int(child.get("y")),
                    "width": int(child.get("width")),
                    "height": int(child.get("height"))
                }
            elif child.tag == "image":
                # image的属性（graphic, x, y）
                self.image = {
                    "graphic": int(child.get("graphic")),
                    "x": int(child.get("x")),
                    "y": int(child.get("y"))
                }
            elif child.tag == "image2":
                # image的属性（graphic, x, y）
                self.image2 = {
                    "graphic": int(child.get("graphic")),
                    "x": int(child.get("x")),
                    "y": int(child.get("y"))
                }
            elif child.tag == "title":
                # title的属性和文本内容
                self.title = {
                    "x": int(child.get("x")),
                    "y": int(child.get("y")),
                    "text": child.text.strip()
                }
            elif child.tag == "subtitle":
                # subtitle的属性和文本内容
                self.subtitle = {
                    "x": int(child.get("x")),
                    "y": int(child.get("y")),
                    "text": child.text.strip()
                }
            elif child.tag == "content":
                # content的文本内容
                self.content = {
                    'text': child.text.strip()
                }

class MessageFileConverter:
    def __init__(self, file_name):
        self.file_name = file_name
        self.entries = []
        self.total_entries = 0
        self.last_entry_index = 0
    
    def read_eng(self, eng_file_data):
        # 1. Header [0:24]
        #  - Name: [0:16]
        #  - Number of entries in the index, this is usually 1000: [16:20]
        #  - Last entry in use, plus 1: [20:24]
        self.total_entries = struct.unpack('<i', eng_file_data[16:20])[0]
        self.last_entry_index = struct.unpack('<i', eng_file_data[20:24])[0]
        
        print(f"[Read Msg ENG] Header.name: {self.file_name}")
        print(f"[Read Msg ENG] Header.total_entries: {self.total_entries}")
        print(f"[Read Msg ENG] Header.last_entry_index+1: {self.last_entry_index}")
        
        self.entries = []
        file_index = 24
        entry_size = 80
        text_index = file_index + entry_size * self.total_entries
        text_data = eng_file_data[text_index:]
        for i in range(self.total_entries):
            entry_data = eng_file_data[file_index:file_index+entry_size]
            file_index += entry_size
            entry = MessageEntry(i)
            if i < self.last_entry_index:
                entry.parse_eng_index(entry_data)
                entry.read_eng_text(text_data)
                self.entries.append(entry)
    
    def write_xml_file(self, xml_file):
        """写入MessageFile格式的XML文件"""
        root = ET.Element('messages')
        root.set('name', self.file_name)
        root.set('entries', str(self.total_entries))
        
        for entry in self.entries:
            msg_elem = ET.SubElement(root, 'message')
            msg_elem.set('id', str(entry.id))
            msg_elem.set('type', str(entry.type))
            msg_elem.set('subtype', str(entry.subtype))
            
            if entry.urgent:
                msg_elem.set('urgent', 'true')
            
            # 添加dialog信息
            dialog_elem = ET.SubElement(msg_elem, 'dialog')
            dialog_elem.set('x', str(entry.dialog['x']))
            dialog_elem.set('y', str(entry.dialog['y']))
            dialog_elem.set('width', str(entry.dialog['width']))
            dialog_elem.set('height', str(entry.dialog['height']))
            
            # 添加image信息
            if entry.image['graphic'] != 0:
                image_elem = ET.SubElement(msg_elem, 'image')
                image_elem.set('graphic', str(entry.image['graphic']))
                image_elem.set('x', str(entry.image['x']))
                image_elem.set('y', str(entry.image['y']))
            
            # 添加image2信息
            if entry.image2['graphic'] != 0:
                image_elem = ET.SubElement(msg_elem, 'image2')
                image_elem.set('graphic', str(entry.image2['graphic']))
                image_elem.set('x', str(entry.image2['x']))
                image_elem.set('y', str(entry.image2['y']))
            
            # 添加文本信息
            if entry.title['text']:
                title_elem = ET.SubElement(msg_elem, 'title')
                title_elem.set('x', str(entry.title['x']))
                title_elem.set('y', str(entry.title['y']))
                title_elem.text = entry.title['text']
            
            if entry.subtitle['text']:
                subtitle_elem = ET.SubElement(msg_elem, 'subtitle')
                subtitle_elem.set('x', str(entry.subtitle['x']))
                subtitle_elem.set('y', str(entry.subtitle['y']))
                subtitle_elem.text = entry.subtitle['text']
            
            if entry.video['text']:
                video_elem = ET.SubElement(msg_elem, 'video')
                video_elem.set('x', str(entry.video['x']))
                video_elem.set('y', str(entry.video['y']))
                video_elem.text = entry.video['text']
            
            if entry.content['text']:
                content_elem = ET.SubElement(msg_elem, 'content')
                content_elem.text = entry.content['text']
        
        # 美化XML并写入文件
        rough_string = ET.tostring(root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        
        with codecs.open(xml_file, 'w', encoding='utf-8') as f:
            f.write(reparsed.toprettyxml(indent='   ', encoding='utf-8').decode('UTF-8'))

    def resolve_xml(self, xml_root):
        self.total_entries = int(xml_root.get('entries'))
        self.entries = []
        for msg_elem in xml_root:
            if msg_elem.tag == 'message':
                msg_id = int(msg_elem.get('id'))
                entry = MessageEntry(msg_id)
                entry.parse_xml_elem(msg_elem)
                self.entries.append(entry)
        self.entries.sort(key=lambda x:x.id)
        self.last_entry_index = self.entries[len(self.entries)-1].id + 1
        print(f"[Resolve Msg XML] file name: {self.file_name}")
        print(f"[Resolve Msg XML] total entries: {self.total_entries}")
        print(f"[Resolve Msg XML] last entry + 1: {self.last_entry_index}")
        
    def write_eng(self, eng_file):
        index_data = bytearray()
        text_data = bytearray(16) # first 16-byte is 0.
        text_data_index = 16
        for i in range(self.total_entries):
            if i < self.last_entry_index:
                entry = self.entries[i]
                text_data_index += _gen_text_byte(entry.title, text_data_index)
                text_data_index += _gen_text_byte(entry.subtitle, text_data_index)
                text_data_index += _gen_text_byte(entry.video, text_data_index)
                text_data_index += _gen_text_byte(entry.content, text_data_index)
                _extend_bytes(text_data, entry.title)
                _extend_bytes(text_data, entry.subtitle)
                _extend_bytes(text_data, entry.video)
                _extend_bytes(text_data, entry.content)
                
                index_data.extend(struct.pack('<h', entry.type)) # 2
                index_data.extend(struct.pack('<h', entry.subtype)) # 4
                index_data.extend(bytearray(2)) # unused 6
                index_data.extend(struct.pack('<h', entry.dialog['x'])) # 8
                index_data.extend(struct.pack('<h', entry.dialog['y'])) # 10
                index_data.extend(struct.pack('<h', entry.dialog['width'])) # 12
                index_data.extend(struct.pack('<h', entry.dialog['height'])) # 14
                index_data.extend(struct.pack('<h', entry.image['graphic'])) # 16
                index_data.extend(struct.pack('<h', entry.image['x'])) # 18
                index_data.extend(struct.pack('<h', entry.image['y'])) # 20
                index_data.extend(struct.pack('<h', entry.image2['graphic'])) # 22
                index_data.extend(struct.pack('<h', entry.image2['x'])) # 24
                index_data.extend(struct.pack('<h', entry.image2['y'])) # 26
                index_data.extend(struct.pack('<h', entry.title['x'])) # 28
                index_data.extend(struct.pack('<h', entry.title['y'])) # 30
                index_data.extend(struct.pack('<h', entry.subtitle['x'])) # 32
                index_data.extend(struct.pack('<h', entry.subtitle['y'])) # 34
                index_data.extend(bytearray(2)) # unused x 36
                index_data.extend(bytearray(2)) # unused y 38
                index_data.extend(struct.pack('<h', entry.video['x'])) # 40
                index_data.extend(struct.pack('<h', entry.video['y'])) # 42
                index_data.extend(bytearray(14)) # unused 56
                index_data.extend(struct.pack('<i', 1 if entry.urgent else 0)) # 60
                index_data.extend(struct.pack('<i', entry.video['offset'])) # 64
                index_data.extend(bytearray(4)) # unused 68
                index_data.extend(struct.pack('<i', entry.title['offset'])) # 72
                index_data.extend(struct.pack('<i', entry.subtitle['offset'])) # 76
                index_data.extend(struct.pack('<i', entry.content['offset'])) # 80
            else:
                index_data.extend(bytearray(80))
        
        header = self.file_name.encode('ascii').ljust(16, b'\x00') + struct.pack('<i', self.total_entries) + struct.pack('<i', self.last_entry_index) 
        with open(eng_file, 'wb') as f:
            f.write(header)
            f.write(index_data)
            f.write(text_data)
            print(f"[Write Msg ENG] Success. '{eng_file}'")
        
class TextGroup:
    """文本组类（用于TextFile格式）"""
    def __init__(self, group_id, file_offset=0):
        self.id = group_id
        self.file_offset = file_offset
        self.strings = []
        self.used = 0
    
    def add(self, text):
        """添加字符串"""
        self.strings.append(text)
    
    def strings(self):
        return self.strings

# ENG file structure:
# 1. [0:28]: Header
#  - 0,16: name
#  - 16,4: Total number of groups in use, defined by maximum used group ID, plus 1
#  - 20,4: Total number of strings in the file
#  - 24,4: Total number of words in the file, may not be accurate
# 2. [28:8000]: Group indexes
#  - group size: 8
#  - offset: [0:4]
#  - used: [4:8]
#  - encoding: little endian
# 3. [8028:EOF]: text data
#  - Every group has multiple strings, seperated by '\x00'
class TextFileConverter: 
    def __init__(self, eng_name):
        self.file_name = eng_name
        self.index_with_counts = False
        self.groups = []
        
    def used_groups_num(self):
        num = 0
        for group in self.groups:
            if group.used:
                num += 1
        
        return num
    
    def resolve_eng(self, filecontent):
        # [0:16] -> name
        # [16:20] -> max group id + 1
        # [20:24] -> total strings
        # [24:28] -> total words
        max_group = struct.unpack('<i', filecontent[16:20])[0]
        total_strings = struct.unpack('<i', filecontent[20:24])[0]
        total_words = struct.unpack('<i', filecontent[24:28])[0]
        print(f"[RESOLVE ENG] Header.name: {self.file_name}")
        print(f"[RESOLVE ENG] Header.max_group: {max_group}")
        print(f"[RESOLVE ENG] Header.total_strings: {total_strings}")
        print(f"[RESOLVE ENG] Header.total_words: {total_words}")
        print("[RESOLVE ENG] Skip header section: 28 bytes")

        print("[RESOLVE ENG] Read group section: 8000 bytes (8-bytes/group, group num 1000)")
        for i in range(MAX_GROUP_INDEX_ENTRIES):
            group_data = filecontent[28+i*8:28+i*8+8]
            offset = struct.unpack('<i', group_data[:4])[0]
            used = struct.unpack('<i', group_data[4:])[0]
            # print(f"- {i}: offset:{offset}, used:{used}")
            if used:
                group = TextGroup(i, offset)
                self.groups.append(group)
        print(f"[RESOLVE ENG] Read group section done. {len(self.groups)} groups")
        
        # 3. text data: [8028:]
        text_data = filecontent[8028:]
        for i, group in enumerate(self.groups):
            # print(f"group: id={group.id} offset={group.file_offset}")
            start_offset = group.file_offset
            end_offset = (i + 1 == len(self.groups)) and len(text_data) or self.groups[i + 1].file_offset
            # print(f"=== group {group.id} start_offset:{start_offset} end_offset: {end_offset}")
            
            if start_offset >= end_offset:
                continue
            tdata = text_data[start_offset:end_offset]
            split_parts = tdata.split(b'\x00')
            for part in split_parts:
                text = _decode_str(part)
                if len(text) > 0:
                    group.add(text)
    
    def write_xml(self, xml_name):
        """写入TextFile格式的XML文件"""
        root = ET.Element('strings')
        root.set('name', self.file_name)
        root.set('indexWithCounts', 'true' if self.index_with_counts else 'false')
        
        for group in self.groups:
            group_elem = ET.SubElement(root, 'group')
            group_elem.set('id', str(group.id))
            
            for i, text in enumerate(group.strings):
                string_elem = ET.SubElement(group_elem, 'string')
                string_elem.set('id', str(i))
                string_elem.text = text
        
        # 美化XML并写入文件
        rough_string = ET.tostring(root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        
        with codecs.open(xml_name, 'w', encoding='utf-8') as f:
            f.write(reparsed.toprettyxml(indent='   ', encoding='utf-8').decode('UTF-8'))
            
    def resolve_xml(self, xml_root):
        self.index_with_counts = xml_root.get('indexWithCounts')
        self.groups = []
        for group_elem in xml_root:
            if group_elem.tag == 'group':
                group_id = int(group_elem.get('id'))
                strings = [s.text for s in group_elem.findall('string') if s.text is not None]
                group = TextGroup(group_id, 0)
                group.used = 1
                group.strings = strings
                self.groups.append(group)
        
    def write_eng(self, eng_file):
        header = self.file_name.encode('ascii').ljust(16, b'\x00')
        
        # 构建组索引（1000组，每组8字节：偏移4字节+已用数4字节）
        group_index = bytearray()
        text_data = bytearray()
        max_group = self.used_groups_num()
        total_strings = 0
        total_words = 0
        
        # 为每组计算偏移
        current_offset = 0
        for group in self.groups:  
            if group.strings:
                group.file_offset = current_offset
                total_strings += len(group.strings)
                for s in group.strings:
                    # 每个字符串以0结束
                    encoded = _encode_str(s)
                    text_data.extend(encoded)
                    text_data.append(0)
                    current_offset += len(encoded) + 1
                    total_words += len(s)
            else:
                group.file_offset = current_offset
        text_data += b'\x00'
        
        self.groups.insert(0, TextGroup(0, 0))
        for i in range(MAX_GROUP_INDEX_ENTRIES):
            if i < len(self.groups):
                group = self.groups[i]
                if group.id == i:
                    continue
            else:
                self.groups.append(TextGroup(i, 0)) # Fill in 1000 groups by 0 and 0
                
        for group in self.groups:
            # print(f"{group.id} offset:{group.file_offset} used: {group.used}")
            group_index.extend(struct.pack('<i', group.file_offset))
            group_index.extend(struct.pack('<i', group.used))
            
        full_header = header + struct.pack('<i', max_group) + struct.pack('<i', total_strings) + struct.pack('<i', total_words)
        with open(eng_file, 'wb') as f:
            f.write(full_header)
            f.write(group_index)
            f.write(text_data)
        
def eng_to_xml(eng_file, xml_file, dry_run):
    print(f"[ENG to XML] From: '{eng_file}'")
    print(f"[ENG to XML] To: '{xml_file}'")

    with open(eng_file, "rb") as f:
        eng_file_data = f.read()
        eng_name = eng_file_data[:16].decode('ascii').rstrip('\x00')
        print(f"[ENG to XML] Type: '{eng_name}'")

        if eng_name == NAME_MSG_FILE:
            converter = MessageFileConverter(eng_name)
            converter.read_eng(eng_file_data)
            if not dry_run:
                converter.write_xml_file(xml_file)
        elif eng_name == NAME_TEXT_FILE:
            converter = TextFileConverter(eng_name)
            converter.resolve_eng(eng_file_data)
            if not dry_run:
                converter.write_xml(xml_file)    
        else:
            print(f"Unknown ENG file: {eng_name}")
            return False
    
    return True

def xml_to_eng(xml_file, eng_file, dry_run):
    tree = ET.parse(xml_file)
    xml_root = tree.getroot()

    if xml_root.tag == 'messages':
        eng_name = xml_root.get('name', '')
        converter = MessageFileConverter(eng_name)
        converter.resolve_xml(xml_root)
        if not dry_run:
            converter.write_eng(eng_file)
    elif xml_root.tag == 'strings':
        eng_name = xml_root.get('name', '')
        converter = TextFileConverter(eng_name)
        converter.resolve_xml(xml_root)
        if not dry_run:
            converter.write_eng(eng_file)
    else:
        raise ValueError(f"Unsupprted XML element: {xml_root.tag}")

def main():
    parser = argparse.ArgumentParser(description="Convertor of ENG and XML files.")
    parser.add_argument("--input-file", "-i", required=True, help="Must be 'eng' or 'xml' file.")
    parser.add_argument("--output-file", "-o", required=False, help="Must be 'eng' or 'xml' file. If not assign, will use [--input-file] name.")
    parser.add_argument("--encoding", "-e", choices=["sc", "tc"], required=True, help="sc: Simplified Chinese, tc: Traditional Chinese")
    parser.add_argument("--dry-run", "-d", action="store_true")
    args = parser.parse_args()
    
    import_encoding_map(args.encoding)
    
    input_file = Path(args.input_file)
    if not input_file.exists():
        print(f"Input file: {args.input_file} not exists.")
        return 1

    input_file_suffix = input_file.suffix.lower()
    output_file_suffix = ".xml" if input_file_suffix == ".eng" else ".eng"
    output_file = Path(args.output_file) if args.output_file else (input_file.parent / input_file.stem).with_suffix(output_file_suffix)
    if input_file_suffix == ".eng":
        eng_to_xml(str(input_file.resolve()), str(output_file.resolve()), args.dry_run)
    elif input_file_suffix == ".xml":
        xml_to_eng(str(input_file.resolve()), str(output_file.resolve()), args.dry_run)
    else:
        print(f"invalid type: '{input_file_suffix}' of input file: `{args.input_file}`")
            
if __name__ == "__main__":
    main()
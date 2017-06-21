import sys
import collections
from opcode import opcode_map, has_arg
from struct import unpack
SOURCE_FILE = "t.py"
PYC_FILE = SOURCE_FILE + "c"

with open(SOURCE_FILE, "r") as source:
    source_code = source.read()
co = compile(source_code, SOURCE_FILE, "exec")
print ("consts", co.co_consts)
print ("names", co.co_names)
print ("var names", co.co_varnames)
print ("free vars", co.co_freevars)
print ("cell vars", co.co_cellvars)

SINGLE_BYTE = 1 
BYTES_OF_INT32 = 4 
BYTES_OF_INT64 = BYTES_OF_INT32 << 1  
BYTES_OF_LONG = BYTES_OF_INT32 << 2 
FLAG_REF = 0x80

def string2bytecode(string):
    index = 0
    opcodes = []
    while index < len(string):
        opcode = ord(string[index])
        opcode_name = opcode_map[opcode]
        index += 1
        if has_arg(opcode):
            opcode_arg = ord(string[index])
            opcode_name += " " + str(opcode_arg)
        index += 1
        opcodes.append(opcode_name)
    return opcodes

class pycLoader:
    def __init__(self, pyc_file):
        self.index = 0
        self.references = []
        self.code_attr_size_dict = collections.OrderedDict({
            'co_argcount': BYTES_OF_INT32,
            'co_kwonlyargcount': BYTES_OF_INT32,
            'co_nlocals': BYTES_OF_INT32,
            'co_stacksize': BYTES_OF_INT32,
            'co_flag': BYTES_OF_INT32,
            'co_code_tag': SINGLE_BYTE,
            'co_consts_tag': SINGLE_BYTE,
            'co_names_tag': SINGLE_BYTE,
            'co_varnames_tag': SINGLE_BYTE,
            'co_freevars_tag': SINGLE_BYTE,
            'co_cellvars_tag': SINGLE_BYTE,
            'co_filename_tag': SINGLE_BYTE,
            'co_name_tag': SINGLE_BYTE,
            'co_firstlineno': BYTES_OF_INT32,
            'co_lnotab_tag': SINGLE_BYTE,
        })
        self.type_method_dict = {
            'c' : self.parse_code,
            'i' : self.parse_int32,
            'l' : self.parse_long,
            'f' : self.parse_float,
            'g' : self.parse_binary_float,
            's' : self.parse_string,
            't' : self.parse_string,
            '(' : self.parse_tuple,
            ')' : self.parse_small_tuple,
            'N' : lambda: self.parse_single_byte('N'),
            'T' : lambda: self.parse_single_byte('T'),
            'F' : lambda: self.parse_single_byte('F'),
            'a' : self.parse_ascii,
            'A' : self.parse_ascii_interned,
            'z' : self.parse_short_ascii,
            'Z' : self.parse_short_ascii_interned,
            'r' : self.parse_interned,
        }
        self.single_byte_dict = {
            'T' : True,
            'F' : False,
            'N' : None,
        }
        with open(PYC_FILE, "rb") as pyc:
            self.content = bytearray(pyc.read())
    def parse_single_byte(self, b):
        return self.single_byte_dict[b]

    def parse_int32(self):
        n = unpack('i', self.content[self.index:self.index+BYTES_OF_INT32])[0]
        self.index += BYTES_OF_INT32
        return n

    def parse_long(self):
        n = unpack('q', self.content[self.index:self.index+BYTES_OF_LONG])[0]
        self.index += BYTES_OF_LONG

    def parse_float(self):
        n = unpack('f', self.content[self.index:self.index+BYTES_OF_INT32])[0]
        self.index += BYTES_OF_INT32

    def parse_binary_float(self):
        n = unpack('d', self.content[self.index:self.index+BYTES_OF_INT64])[0]
        self.index += BYTES_OF_INT64

    def parse_string(self):
        length = unpack('i', self.content[self.index:self.index+BYTES_OF_INT32])[0]
        self.index += BYTES_OF_INT32
        string = [chr(self.content[self.index+i]) for i in range(length)]
        self.index += length
        return string

    def parse_tuple(self):
        res = []
        length = unpack('i', self.content[self.index:self.index+BYTES_OF_INT32])[0]
        self.index += BYTES_OF_INT32 
        for i in range(length):
            res.append(self.parse_object())
        return tuple(res)

    def parse_small_tuple(self):
        res = []
        length = self.content[self.index]
        self.index += SINGLE_BYTE
        for i in range(length):
            res.append(self.parse_object())
        return res

    def parse_code(self):
        res = {}
        for attr, size in self.code_attr_size_dict.items():
            if attr.endswith('tag'):
                attr = attr.rstrip('_tag')
                res[attr] = self.parse_object()
                if attr == 'co_code':
                    res[attr] = string2bytecode(res[attr])
            else:
                flag = 'i' if size == 4 else 'q'
                result = unpack(flag, self.content[self.index:self.index+size])[0]
                self.index += size
                res[attr] = result
        return res

    def parse_ascii(self):
        length = unpack('i', self.content[self.index:self.index+BYTES_OF_INT32])[0]
        self.index += BYTES_OF_INT32
        string = self.content[self.index:self.index+length].decode('utf-8')
        self.index += length
        return string

    def parse_ascii_interned(self):
        return self.parse_ascii()

    def parse_short_ascii(self):
        length = self.content[self.index]
        self.index += SINGLE_BYTE
        string = self.content[self.index:self.index+length].decode('utf-8')
        self.index += length
        return string

    def parse_short_ascii_interned(self):
        return self.parse_short_ascii()

    def parse_interned(self):
        offset = unpack('i', self.content[self.index:self.index+BYTES_OF_INT32])[0]
        self.index += BYTES_OF_INT32
        return self.references[offset]

    def parse_object(self):
        code = self.content[self.index]
        object_type = code & ~FLAG_REF
        type_flag = code & FLAG_REF
        object_type = chr(object_type)
        self.index += SINGLE_BYTE
        if type_flag and object_type == 'c':
            self.references.append(None)
        result = self.type_method_dict[object_type]()
        if type_flag:
            if object_type == 'c':
                self.references[-1] = result
            else:
                self.references.append(result)
        return result

    def run(self):
        self.index = 0
        self.references = []
        magic = unpack('i', self.content[self.index:self.index+BYTES_OF_INT32])[0]
        self.index += BYTES_OF_INT32
        modify_time = unpack('i', self.content[self.index:self.index+BYTES_OF_INT32])[0]
        self.index += BYTES_OF_INT32
        unknown = unpack('i', self.content[self.index:self.index+BYTES_OF_INT32])[0]
        self.index += BYTES_OF_INT32
        return json.dumps(self.parse_object(), indent=4)

if __name__ == '__main__':
    import json
    loader = pycLoader(sys.argv[SINGLE_BYTE]) # pylint: disable=C0103
    json_str = loader.run() # pylint: disable=C0103
    print(json_str)

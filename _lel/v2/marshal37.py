# -*- coding: utf-8 -*-
"""最小 Python 3.7 marshal 解析器：只取 code object 的 co_consts[0]（PyInstaller AES 密钥）。"""
import struct
import sys


class R:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def byte(self):
        b = self.d[self.p]
        self.p += 1
        return b

    def i32(self):
        v = struct.unpack('<i', self.d[self.p:self.p + 4])[0]
        self.p += 4
        return v

    def raw(self, n):
        v = self.d[self.p:self.p + n]
        self.p += n
        return v

    def obj(self, has_posonly=False):
        tb = self.byte()
        flag = tb & 0x80
        t = tb & 0x7f
        if t == 0x4e:  # None
            return None
        if t == 0x4e:
            return None
        if t == 0x46:  # False
            return False
        if t == 0x54:  # True
            return True
        if t == 0x4e:
            return None
        if t == 0x53:  # StopIteration
            return '<stopiter>'
        if t == 0x2e:  # Ellipsis
            return '...'
        if t == 0x69:  # INT
            return self.i32()
        if t == 0x49:  # INT64
            v = struct.unpack('<q', self.raw(8))[0]
            return v
        if t == 0x66:  # FLOAT
            return struct.unpack('<d', self.raw(8))[0]
        if t == 0x67:  # BINARY_FLOAT
            return struct.unpack('<d', self.raw(8))[0]
        if t == 0x78:  # COMPLEX
            self.raw(16)
            return 'complex'
        if t == 0x6c:  # LONG
            n = self.i32()
            return 'long(%d)' % n
        if t == 0x73:  # STRING (bytes)
            n = self.i32()
            return self.raw(n)
        if t == 0x74:  # INTERNED
            n = self.i32()
            return self.raw(n)
        if t == 0x5a:  # SHORT ASCII
            n = self.byte()
            return self.raw(n)
        if t == 0x75:  # UNICODE
            n = self.i32()
            return self.raw(n).decode('utf-8', 'replace')
        if t == 0x5c:  # SHORT ASCII INTERNED
            n = self.byte()
            return self.raw(n)
        if t == 0x7c:  # SHORT ASCII INTERNED (3.4+)
            n = self.byte()
            return self.raw(n)
        if t == 0x5a + 0:  # unreachable
            pass
        if t == 0x72:  # REF
            return 'ref'
        if t == 0x28:  # TUPLE
            n = self.i32()
            return tuple(self.obj(has_posonly) for _ in range(n))
        if t == 0x29:  # SMALL TUPLE
            n = self.byte()
            return tuple(self.obj(has_posonly) for _ in range(n))
        if t == 0x5b:  # LIST
            n = self.i32()
            return [self.obj(has_posonly) for _ in range(n)]
        if t == 0x7b:  # DICT
            d = {}
            while True:
                k = self.obj(has_posonly)
                if k == '<stopiter>':
                    break
                v = self.obj(has_posonly)
                d[k] = v
            return d
        if t == 0x3c:  # SET
            n = self.i32()
            return set(self.obj(has_posonly) for _ in range(n))
        if t == 0x3e:  # FROZENSET
            n = self.i32()
            return frozenset(self.obj(has_posonly) for _ in range(n))
        if t == 0x63:  # CODE
            argcount = self.i32()
            if has_posonly:
                self.i32()
            self.i32()  # kwonlyargcount
            self.i32()  # nlocals
            self.i32()  # stacksize
            self.i32()  # flags
            code = self.obj(has_posonly)
            consts = self.obj(has_posonly)
            names = self.obj(has_posonly)
            varnames = self.obj(has_posonly)
            freevars = self.obj(has_posonly)
            cellvars = self.obj(has_posonly)
            filename = self.obj(has_posonly)
            name = self.obj(has_posonly)
            firstlineno = self.i32()
            lnotab = self.obj(has_posonly)
            return Code(consts, name, filename)
        raise ValueError('unknown marshal type 0x%02x at %d' % (t, self.p - 1))


class Code:
    def __init__(self, consts, name, filename):
        self.co_consts = consts
        self.co_name = name
        self.co_filename = filename


def load_code(pyc_path, header=16):
    d = open(pyc_path, 'rb').read()
    r = R(d[header:])
    return r.obj(has_posonly=False)


if __name__ == '__main__':
    path = sys.argv[1]
    hdr = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    c = load_code(path, hdr)
    print('name:', c.co_name, 'file:', c.co_filename)
    for i, k in enumerate(c.co_consts):
        print('  const[%d] = %r' % (i, k))

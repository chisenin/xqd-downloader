# -*- coding: utf-8 -*-
"""从运行中的学无止客户端进程内存中搜索明文字符串。

PyArmor 9 pro 的运行时会把解密后的 code object 放入解释器堆内存，
其常量区仍然保留原始字符串。直接从进程内存里 grep 即可拿到业务逻辑线索。
"""
import ctypes
import ctypes.wintypes as wt
import re
import sys

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, wt.LPCVOID, wt.LPVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.VirtualQueryEx.argtypes = [wt.HANDLE, wt.LPCVOID, ctypes.c_void_p, ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BaseAddress', wt.LPVOID),
        ('AllocationBase', wt.LPVOID),
        ('AllocationProtect', wt.DWORD),
        ('PartitionId', wt.WORD),
        ('RegionSize', ctypes.c_size_t),
        ('State', wt.DWORD),
        ('Protect', wt.DWORD),
        ('Type', wt.DWORD),
    ]


def regions(h):
    addr = 0
    while addr < 0x7FFFFFFF:
        mbi = MEMORY_BASIC_INFORMATION()
        n = kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if n == 0:
            break
        base = int(ctypes.cast(mbi.BaseAddress, ctypes.c_void_p).value or 0)
        size = int(mbi.RegionSize)
        if size <= 0:
            break
        if mbi.State == MEM_COMMIT and not (mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)):
            yield base, size
        addr = base + size


def read(h, base, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    if not kernel32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(got)):
        return b''
    return buf.raw[:got.value]


def main():
    pid = int(sys.argv[1])
    needles = [n.encode() for n in sys.argv[2:]]
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        print('OpenProcess failed', ctypes.get_last_error())
        return
    total = 0
    hits = {}
    for base, size in regions(h):
        if size > 64 * 1024 * 1024:
            continue
        data = read(h, base, size)
        total += len(data)
        for nd in needles:
            start = 0
            while True:
                i = data.find(nd, start)
                if i < 0:
                    break
                hits.setdefault(nd, []).append((base + i, data))
                start = i + 1
    print('scanned %.1f MB' % (total / 1048576.0))
    for nd, lst in hits.items():
        print('=== %s : %d hits' % (nd.decode(), len(lst)))
        for addr, data in lst[:6]:
            i = addr - 0  # locate again
            ctx = data[max(0, i - 0):]
            # find the needle inside data again
            j = ctx.find(nd)
            s = ctx[max(0, j - 300):j + 700]
            print('--- @0x%X' % addr)
            try:
                print(s.decode('utf-8', 'replace'))
            except Exception:
                print(repr(s))
            print()
    kernel32.CloseHandle(h)


if __name__ == '__main__':
    main()

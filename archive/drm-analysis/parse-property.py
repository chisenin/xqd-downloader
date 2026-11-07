import io, sys, collections

p = r'D:\.workbuddy\2026-11-06-20-15-25\cache-analysis\drm.property'
data = io.open(p, 'rb').read()
print("size:", len(data))

# 打印前 256 字节 hex+ascii
def dump(b, n=256):
    for off in range(0, min(n, len(b)), 16):
        chunk = b[off:off+16]
        hexs = ' '.join('%02x' % c for c in chunk)
        asc = ''.join(chr(c) if 32 <= c < 127 else '.' for c in chunk)
        print('%06x  %-47s  %s' % (off, hexs, asc))
dump(data, 320)
print()

# 找所有 .ts 名字出现位置
import re
names = [(m.start(), m.group().decode()) for m in re.finditer(rb'\d+\.ts', data)]
print("ts name occurrences:", len(names))
if names:
    print("first:", names[:5])
    print("last:", names[-3:])
    # 第一个名字前的头部
    h = data[:names[0][0]]
    print("header before first name:", h.hex())
    # 第一个名字之后到第二个名字之间的字节 = 该分片的记录体
    if len(names) > 1:
        rec = data[names[0][0]:names[1][0]]
        print("record[0] raw:", rec.hex())
        print("record[0] len:", len(rec))
print()

# 尝试：把整份文件里出现的所有 16 字节对齐块当作候选 IV/密钥，看有没有重复
blocks = collections.Counter()
for i in range(0, len(data)-16):
    pass

# 找 "Bj" 标记（前面观察到每个记录里都有）
idx = [m.start() for m in re.finditer(b'\x42\x6a', data)]
print("count of 0x42 0x6a:", len(idx))
if idx:
    print("first few offsets:", idx[:6])
    for o in idx[:4]:
        print("  @%d ->" % o, data[o:o+24].hex())

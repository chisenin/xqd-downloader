# -*- coding: utf-8 -*-
"""已下载检测（check_group / purge_broken）的单元测试。

覆盖需求 2、3：
  * 已存在且完整 → 跳过
  * 存在但残缺 → 判定 broken，清理后覆盖重下
  * ``-1`` 重名后缀 → 整组识别，不再产生新的重复名
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

import xqd_dedupe
import xqd_engine
import xqd_platform

PASS = []
FAIL = []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('[OK] ' if cond else '[FAIL]', name,
                       ('  ← ' + detail) if detail and not cond else ''))


def make_video(path, seconds=10):
    """造一个指定时长的真实 mp4（用 ffmpeg 生成测试片）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = [xqd_engine.ffmpeg_path(), '-y', '-loglevel', 'error',
           '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=10:duration=%s'
           % seconds,
           '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo:d=%s' % seconds,
           '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast',
           '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart',
           path]
    import subprocess
    p = subprocess.run(cmd, capture_output=True, timeout=300)
    return p.returncode == 0 and os.path.exists(path)


def main():
    root = tempfile.mkdtemp(prefix='xqd_dedupe_unit_')
    camp = os.path.join(root, '测试营')
    os.makedirs(camp, exist_ok=True)
    ck = xqd_dedupe.ExistingChecker(root)

    stem = '1.第一课.2026.01.01'

    # ── 1. 什么都没有 → missing ──
    st = ck.check_group(camp, stem, 10)
    check('空目录 → missing', st['status'] == 'missing', st['status'])

    # ── 2. 残缺文件（过小）→ broken ──
    tiny = os.path.join(camp, stem + '.mp4')
    with open(tiny, 'wb') as f:
        f.write(b'x' * 500)
    st = ck.check_group(camp, stem, 10)
    check('过小文件 → broken', st['status'] == 'broken', st['status'])

    # ── 3. purge_broken 删掉它 ──
    removed = ck.purge_broken(camp, stem, 10)
    check('purge_broken 删掉残缺文件',
          len(removed) == 1 and not os.path.exists(tiny),
          'removed=%s' % removed)
    st = ck.check_group(camp, stem, 10)
    check('清理后 → missing', st['status'] == 'missing', st['status'])

    # ── 4. 真实完整视频 → ok ──
    good = os.path.join(camp, stem + '.mp4')
    if not make_video(good, 10):
        print('[SKIP] ffmpeg 不可用，跳过真实视频用例')
        shutil.rmtree(root, ignore_errors=True)
        print('\n%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
        return 1 if FAIL else 0
    st = ck.check_group(camp, stem, 10)
    check('完整视频 → ok', st['status'] == 'ok', st['status'])
    check('ok 时给出路径', st['path'] == good, st['path'])

    # ── 5. 时长不符 → broken ──
    st = ck.check_group(camp, stem, 60)
    check('时长不符 → broken', st['status'] == 'broken', st['status'])

    # ── 6. 完整视频 + 一个 -1 残缺 → 仍算 ok（组内有完整的就行）──
    dup = os.path.join(camp, stem + '-1.mp4')
    with open(dup, 'wb') as f:
        f.write(b'y' * 300)
    st = ck.check_group(camp, stem, 10)
    check('组内有完整文件 → ok', st['status'] == 'ok', st['status'])
    check('组内识别出 2 个文件', len(st['files']) == 2,
          'files=%s' % len(st['files']))

    # ── 7. purge_broken 不动完整文件 ──
    removed = ck.purge_broken(camp, stem, 10)
    check('有完整文件时不删任何东西', removed == [], 'removed=%s' % removed)
    check('完整文件仍在', os.path.exists(good))

    # ── 8. 完整文件 + -1 完整文件 → 都是 ok ──
    dup2 = os.path.join(camp, stem + '-1.mp4')
    make_video(dup2, 10)
    st = ck.check_group(camp, stem, 10)
    check('两个完整文件 → ok', st['status'] == 'ok', st['status'])
    check('组内 2 个文件都 ok',
          all(f[2] for f in st['files']), st['files'])

    # ── 9. 全部残缺 → broken 且 purge 全部清掉 ──
    for p in (good, dup2):
        with open(p, 'wb') as f:
            f.write(b'z' * 400)
    st = ck.check_group(camp, stem, 10)
    check('全部残缺 → broken', st['status'] == 'broken', st['status'])
    removed = ck.purge_broken(camp, stem, 10)
    check('purge 清掉 2 个残缺文件', len(removed) == 2,
          'removed=%s' % removed)

    # ── 10. 音频扩展名不同也能匹配（.m4a vs .mp3）──
    astem = '2.音频课.2026.01.01'
    m4a = os.path.join(camp, astem + '.m4a')
    make_video(m4a, 8)
    st = ck.check_group(camp, astem, 8)
    check('.m4a 也能匹配主键', st['status'] == 'ok', st['status'])

    # ── 11. 规范命名不再产生 -1 ──
    class FakeLesson(object):
        index = 0
        title = '第一课'
        when_date = '2026.01.01'
        type = 'VIDEO'
    fn = xqd_platform.course_filename(FakeLesson())
    check('course_filename 无 -1 后缀', fn == '1.第一课.2026.01.01.mp4', fn)
    fn2 = xqd_platform.course_filename(FakeLesson(),
                                       used={'1.第一课.2026.01.01.mp4'})
    check('即使 used 冲突也不加后缀',
          fn2 == '1.第一课.2026.01.01.mp4', fn2)

    shutil.rmtree(root, ignore_errors=True)
    print('\n%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：%s' % FAIL)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())

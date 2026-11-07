# -*- coding: utf-8 -*-
"""修复：ScanWorker 在运行中被 GC 析构 → Qt abort。

现象：快速切换营（load_camps → setCurrentRow → load_lessons → _scan_existing）
第二次就崩溃，进程无任何 Python 异常信息直接消失。

根因：_scan_existing 里 `self.scan_worker = ScanWorker(...)` 直接覆盖引用，
上一个扫描线程还在跑（ffprobe 在 SMB 上很慢），引用一丢，Python GC 立刻
把它析构 → QThread 在运行中被销毁 → Qt 调用 qFatal abort。

修复：把所有 worker 存进列表保活，只在真正结束后才摘掉。
"""
import io
import sys

P = 'xqd_gui.py'
src = io.open(P, encoding='utf-8').read()
orig = src

# ── 1) __init__ 加保活列表 ──
old = """        self.scan_worker = None
        self._scan_counts = (0, 0)"""
new = """        self.scan_worker = None
        # ★ 保活列表：运行中的 ScanWorker 绝不能被 GC 析构。
        #   QThread 在运行中被销毁会让 Qt 直接 abort（进程无异常信息地消失）。
        #   见 _scan_existing 的注释。
        self._scan_workers = []
        self._scan_counts = (0, 0)"""
assert old in src, 'init 锚点未命中'
src = src.replace(old, new, 1)

# ── 2) _scan_existing 改为保活 ──
old = """        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.wait(2000)
        self.scan_worker = ScanWorker(self.checker, folder, lessons,
                                      alt_folders=alt)
        self.scan_worker.done.connect(self._on_scan_done)
        self.scan_worker.finished_all.connect(self._on_scan_finished)
        self.scan_worker.start()"""
new = """        # ★ 旧扫描线程可能还在跑（ffprobe 在 SMB 网络盘上很慢）。
        #   **不能**直接 `self.scan_worker = 新对象` —— 旧对象引用一丢，
        #   Python GC 就会把它析构，而它还在运行 → Qt 检测到
        #   「QThread 在运行中被销毁」→ qFatal abort，进程直接消失，
        #   连 Python traceback 都没有。
        #   办法：每个 worker 都存进 _scan_workers 保活，只摘掉已结束的。
        old_worker = self.scan_worker
        if old_worker is not None and old_worker.isRunning():
            old_worker.wait(5000)
        self._prune_scan_workers()

        worker = ScanWorker(self.checker, folder, lessons,
                            alt_folders=alt)
        worker.done.connect(self._on_scan_done)
        worker.finished_all.connect(self._on_scan_finished)
        self._scan_workers.append(worker)
        self.scan_worker = worker
        worker.start()

    def _prune_scan_workers(self):
        \"\"\"摘掉已结束的扫描线程（已结束的可以安全 GC）。\"\"\"
        self._scan_workers = [w for w in self._scan_workers
                              if w.isRunning()]"""
assert old in src, '_scan_existing 锚点未命中'
src = src.replace(old, new, 1)

# ── 3) closeEvent 等所有 worker ──
old = """        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.wait(3000)"""
new = """        for w in list(self._scan_workers):
            if w.isRunning():
                w.wait(3000)
        self._scan_workers = []"""
assert old in src, 'closeEvent 锚点未命中'
src = src.replace(old, new, 1)

io.open(P, 'w', encoding='utf-8').write(src)
print('补丁已应用，%d -> %d 字符' % (len(orig), len(src)))

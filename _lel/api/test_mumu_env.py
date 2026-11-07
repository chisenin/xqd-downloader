# -*- coding: utf-8 -*-
"""v1.5.2 离线回归：MuMu「no Qt platform plugin」弹窗的根因修复。

覆盖两层修复：
  A. xqd_proc —— 子进程 Qt 环境隔离（打包 exe 注入的 QT_PLUGIN_PATH 不再
     传给 MuMu 的 Qt5 程序），并对 MuMuManager 显式纠正插件目录。
  B. GUI —— 启动时优先用本机保存的授权，默认一个 MuMuManager 都不调；
     「重新授权」才强制刷新，拿到新 Cookie 后落盘复用。

★ 全程不启动 MuMu、不发网络请求、不写用户真实凭据文件
  （XQD_TEST_HOME 会让 xqd_creds.save_cookie 拒绝写真实文件）。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

TEST_HOME = os.path.join(tempfile.gettempdir(), 'xqd_v151_test')
os.makedirs(TEST_HOME, exist_ok=True)
os.environ['XQD_TEST_HOME'] = TEST_HOME
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication  # noqa: E402

import xqd_auth          # noqa: E402
import xqd_creds         # noqa: E402
import xqd_gui           # noqa: E402
import xqd_proc          # noqa: E402

PASS, FAIL = [], []


def ok(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('[OK]  ' if cond else '[FAIL]', name,
                       ('  <- ' + str(detail)) if detail and not cond else ''))


# ══════════════════════════════════════════════════════════════
#  A. 环境净化
# ══════════════════════════════════════════════════════════════
def test_clean_env():
    print('\n--- A. 子进程 Qt 环境净化 ---')
    base = {
        'QT_PLUGIN_PATH': r'C:\Temp\_MEI123456\PySide6\plugins',
        'QT_QPA_PLATFORM': 'offscreen',
        'QT_QPA_PLATFORM_PLUGIN_PATH': r'C:\Temp\_MEI123456\PySide6\plugins\platforms',
        'QT_DEBUG_PLUGINS': '1',
        'QML2_IMPORT_PATH': r'C:\Temp\_MEI123456\PySide6\qml',
        '_PYI_APPLICATION_HOME_DIR': r'C:\Temp\_MEI123456',
        '_PYI_PARENT_PROCESS_LEVEL': '1',
        '_MEIPASS2': r'C:\Temp\_MEI123456',
        'PATH': r'C:\Windows\System32',
        'TEMP': r'C:\Temp',
        'XQD_KEEP_ME': 'yes',
    }
    env = xqd_proc.clean_env(base)
    ok('清掉 QT_PLUGIN_PATH', 'QT_PLUGIN_PATH' not in env)
    ok('清掉 QT_QPA_PLATFORM', 'QT_QPA_PLATFORM' not in env)
    ok('清掉 QT_QPA_PLATFORM_PLUGIN_PATH',
       'QT_QPA_PLATFORM_PLUGIN_PATH' not in env)
    ok('清掉 QT_DEBUG_PLUGINS', 'QT_DEBUG_PLUGINS' not in env)
    ok('清掉 QML2_IMPORT_PATH', 'QML2_IMPORT_PATH' not in env)
    ok('清掉全部 _PYI_*', not any(k.startswith('_PYI_') for k in env))
    ok('清掉 _MEIPASS2', '_MEIPASS2' not in env)
    ok('普通变量 PATH 保留', env.get('PATH') == base['PATH'])
    ok('普通变量 TEMP 保留', env.get('TEMP') == base['TEMP'])
    ok('自定义变量保留', env.get('XQD_KEEP_ME') == 'yes')
    ok('不修改传入的 dict', 'QT_PLUGIN_PATH' in base)

    path = r'C:\Temp\_MEI123456;C:\Py\Lib\site-packages\PySide6;C:\Windows\System32'
    stripped = xqd_proc._strip_pyi_paths(path)
    ok('PATH 剔除 _MEI 临时目录', '_MEI123456' not in stripped, stripped)
    ok('PATH 剔除 PySide6 目录', 'PySide6' not in stripped, stripped)
    ok('PATH 保留 System32', 'System32' in stripped, stripped)


def test_mumu_kwargs():
    print('\n--- A2. MuMuManager 子进程的参数 ---')
    fake_root = os.path.join(tempfile.gettempdir(), 'xqd_v151_fake_mumu')
    mm_dir = os.path.join(fake_root, 'nx_main')
    os.makedirs(os.path.join(mm_dir, 'plugins', 'platforms'), exist_ok=True)
    mgr = os.path.join(mm_dir, 'MuMuManager.exe')
    with open(mgr, 'wb') as f:
        f.write(b'MZ')                 # 只要路径存在，不真的执行

    polluted = {
        'QT_PLUGIN_PATH': r'C:\Temp\_MEI987654\PySide6\plugins',
        'QML2_IMPORT_PATH': r'C:\Temp\_MEI987654\PySide6\qml',
        '_PYI_APPLICATION_HOME_DIR': r'C:\Temp\_MEI987654',
        'PATH': (r'C:\Temp\_MEI987654;C:\Py\Lib\site-packages\PySide6'
                 r';C:\Windows\System32'),
        'XQD_KEEP_ME': 'yes',
    }
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(polluted)

    captured = {}

    class FakeCompleted:
        stdout = b'{}'
        stderr = b''
        returncode = 0

    real_run = xqd_proc.subprocess.run

    def fake_run(*args, **kwargs):
        captured['cmd'] = args[0] if args else kwargs.get('args')
        captured['kw'] = kwargs
        return FakeCompleted()

    try:
        xqd_proc.subprocess.run = fake_run
        xqd_proc.run([mgr, 'info', '-v', '0'], capture_output=True, timeout=5)
        kw = captured['kw']
        env = kw.get('env', {})
        ok('识别 MuMuManager 命令',
           os.path.basename(captured['cmd'][0]).lower() == 'mumumanager.exe')
        ok('★ QT_PLUGIN_PATH 指向 MuMu 自带的 Qt5 插件目录',
           env.get('QT_PLUGIN_PATH') == os.path.join(mm_dir, 'plugins'),
           env.get('QT_PLUGIN_PATH'))
        ok('QT_QPA_PLATFORM_PLUGIN_PATH 指向自带 platforms',
           env.get('QT_QPA_PLATFORM_PLUGIN_PATH')
           == os.path.join(mm_dir, 'plugins', 'platforms'))
        ok('Qt6 的 QML2_IMPORT_PATH 已清除', 'QML2_IMPORT_PATH' not in env)
        ok('★ PATH 里没有 PyInstaller 临时目录',
           '_MEI987654' not in env.get('PATH', ''), env.get('PATH'))
        ok('★ PATH 里没有 PySide6 目录',
           'PySide6' not in env.get('PATH', ''), env.get('PATH'))
        ok('cwd 设为 MuMu 安装目录', kw.get('cwd') == mm_dir, kw.get('cwd'))
        ok('普通环境变量保留', env.get('XQD_KEEP_ME') == 'yes')
        ok('无窗参数仍在', 'creationflags' in kw)

        # 非 MuMu 命令：只净化，不动 PATH / cwd
        xqd_proc.run(['tasklist', '/FI', 'IMAGENAME eq x.exe'],
                     capture_output=True)
        kw2 = captured['kw']
        env2 = kw2.get('env', {})
        ok('非 MuMu 命令不注入 QT_PLUGIN_PATH',
           'QT_PLUGIN_PATH' not in env2, env2.get('QT_PLUGIN_PATH'))
        ok('非 MuMu 命令不改 cwd', kw2.get('cwd') is None)
        ok('非 MuMu 命令保留 PATH（ffmpeg 可能需要 _MEIPASS）',
           '_MEI987654' in env2.get('PATH', ''), env2.get('PATH'))

        # 调用方显式传 env → 完全尊重，不覆盖
        explicit = {'ONLY': 'mine'}
        xqd_proc.run([mgr, 'info', '-v', '0'], env=explicit,
                     capture_output=True)
        ok('显式 env 不被覆盖', captured['kw'].get('env') is explicit)
    finally:
        xqd_proc.subprocess.run = real_run
        os.environ.clear()
        os.environ.update(saved)


# ══════════════════════════════════════════════════════════════
#  B. 凭据落盘与隔离
# ══════════════════════════════════════════════════════════════
def test_save_cookie():
    print('\n--- B. 新授权落盘 + 测试隔离 ---')
    ok('save_cookie 存在', hasattr(xqd_creds, 'save_cookie'))
    ok('★ 设了 XQD_TEST_HOME 时拒绝写真实凭据',
       xqd_creds.save_cookie('userId=a; rsessionId=b') is False)
    ok('真实凭据文件未被改动（无 .tmp 残留）',
       not os.path.isfile(xqd_creds.CRED_FILE + '.tmp'))
    ok('空 Cookie 不写', xqd_creds.save_cookie('') is False)

    tmp_path = os.path.join(TEST_HOME, 'cookie_probe.txt')
    ok('显式 path 可写入',
       xqd_creds.save_cookie('userId=a; rsessionId=b', path=tmp_path))
    with open(tmp_path, encoding='utf-8') as f:
        content = f.read().strip()
    ok('写入内容正确', content == 'userId=a; rsessionId=b', content)
    ok('无临时文件残留', not os.path.isfile(tmp_path + '.tmp'))


# ══════════════════════════════════════════════════════════════
#  C. GUI 启动：缓存授权优先
# ══════════════════════════════════════════════════════════════
class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


class FakeWorker:
    """替身：不启动线程、不碰 MuMu，只记录被创建了几次。"""
    created = []

    def __init__(self, auto_launch=True, auto_close=True, parent=None):
        self.auto_launch = auto_launch
        self.auto_close = auto_close
        for name in ('status', 'ok', 'failed', 'closed', 'done'):
            setattr(self, name, FakeSignal())
        FakeWorker.created.append(self)

    def isRunning(self):
        return False

    def start(self):
        pass


def test_gui_auth():
    print('\n--- C. GUI 缓存授权优先 ---')
    app = QApplication.instance() or QApplication(sys.argv)

    # 构造期间不要真的排队授权检查（后面手动调）
    orig_auto = xqd_gui.MainWindow.auto_check_auth
    xqd_gui.MainWindow.auto_check_auth = lambda self, force_mumu=False: None
    try:
        win = xqd_gui.MainWindow()
    finally:
        xqd_gui.MainWindow.auto_check_auth = orig_auto

    calls = {'load_camps': 0, 'mumu': 0, 'saved': []}
    win.load_camps = lambda: calls.__setitem__('load_camps',
                                              calls['load_camps'] + 1)
    real_find = xqd_auth.find_mumu_manager

    def spy_find(*a, **kw):
        calls['mumu'] += 1
        raise AssertionError('缓存分支不应调用 MuMuManager')

    xqd_auth.find_mumu_manager = spy_find

    real_load = xqd_creds.load_cookie
    real_save = xqd_creds.save_cookie
    real_worker = xqd_gui.AuthWorker

    def spy_save(cookie, path=None):
        calls['saved'].append(cookie)
        return True

    try:
        xqd_creds.load_cookie = lambda required=False: 'userId=a; rsessionId=b'
        xqd_creds.save_cookie = spy_save
        xqd_gui.AuthWorker = FakeWorker

        # ① 自动检查（默认）→ 走缓存
        win.auto_check_auth()
        ok('★ 有缓存时直接用，未创建 AuthWorker', win.auth_worker is None)
        ok('★ 有缓存时完全不碰 MuMu', calls['mumu'] == 0, calls['mumu'])
        ok('cookie 已设置', win.cookie == 'userId=a; rsessionId=b')
        ok('platform.cookie 同步',
           win.platform is not None
           and win.platform.cookie == 'userId=a; rsessionId=b')
        ok('加载营列表被触发', calls['load_camps'] == 1,
           calls['load_camps'])
        ok('授权标签标明「本机保存」', '本机保存' in win.lbl_auth.text(),
           win.lbl_auth.text())
        ok('提示条说明未启动模拟器',
           '未启动 MuMu' in win.banner.text(), win.banner.text())
        ok('按钮文字为「重新授权」', win.btn_retry.text() == '重新授权',
           win.btn_retry.text())

        # ② 点「重新授权」→ 强制走 MuMu（FakeWorker，不真启动）
        FakeWorker.created = []
        win.auto_check_auth(force_mumu=True)
        ok('★ 强制刷新会创建授权线程', len(FakeWorker.created) == 1,
           len(FakeWorker.created))
        ok('强制刷新时按钮禁用', not win.btn_retry.isEnabled())
        ok('强制刷新时标签为检查中', '检查中' in win.lbl_auth.text(),
           win.lbl_auth.text())

        # ③ 无缓存 → 自动检查也要走 MuMu
        xqd_creds.load_cookie = lambda required=False: ''
        FakeWorker.created = []
        win.auth_worker = None
        win.btn_retry.setEnabled(True)
        win.auto_check_auth()
        ok('无缓存时自动检查会启动授权线程',
           len(FakeWorker.created) == 1, len(FakeWorker.created))

        # ④ 拿到新授权 → 落盘，下次复用
        calls['saved'] = []
        win._on_auth_ok('userId=new; rsessionId=new')
        ok('★ 新授权被保存', calls['saved'] == ['userId=new; rsessionId=new'],
           calls['saved'])
        ok('新授权已写入 self.cookie',
           win.cookie == 'userId=new; rsessionId=new')

        # ⑤ 营列表加载失败 → 引导重新授权
        class BadPlatform:
            camp_kinds = ['正式营']

            def list_camps(self, kind):
                raise RuntimeError('模拟：Cookie 已过期')

        win.platform = BadPlatform()
        win.cookie = 'expired'
        del win.load_camps          # 删掉实例属性 → 回退到真实的类方法
        win.load_camps()
        ok('加载失败时提示点「重新授权」',
           '重新授权' in win.banner.text(), win.banner.text())
    finally:
        xqd_auth.find_mumu_manager = real_find
        xqd_creds.load_cookie = real_load
        xqd_creds.save_cookie = real_save
        xqd_gui.AuthWorker = real_worker


def test_meta():
    print('\n--- D. 版本与帮助文案 ---')
    ok('版本号为 1.5.2', xqd_gui.APP_VERSION == '1.5.2',
       xqd_gui.APP_VERSION)
    ok('帮助说明「平时不用开模拟器」',
       '平时启动工具直接使用本机保存的授权' in xqd_gui.HELP_HTML)
    ok('帮助说明「重新授权」刷新', '重新授权' in xqd_gui.HELP_HTML)


def main():
    test_clean_env()
    test_mumu_kwargs()
    test_save_cookie()
    test_gui_auth()
    test_meta()
    print('\n%d 通过 / %d 失败' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项：%s' % FAIL)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())

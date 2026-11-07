# -*- coding: utf-8 -*-
"""兴趣岛授权获取（免 adbd 通道）。

核心思路
--------
兴趣岛 App 是个 WebView 壳，登录态存在 Android 侧 WebView 的 Cookie 库里：

    /data/data/com.qlchat.xingqudao/app_webview/Default/Cookies

这张表里 ``encrypted_value`` 是**空的**，``value`` 直接是明文，
所以只要能读到这张表就能拿到 ``userId`` / ``rsessionId``。

怎么免 adbd 读到它？
-------------------
网易 MuMu 自带 ``MuMuManager.exe``，其 ``sh`` 子命令走的是**模拟器内部 RPC**，
不是 adbd 协议（adb 是另一条独立通道）。而且它在 root 上下文执行：

    uid=0(root) gid=0(root) groups=0(root) context=u:r:nemuinit:s0

所以整条链路是：MuMuManager CLI → 内部 RPC → root shell → sqlite3 读表。
全程不启 adb、不用 adb 连接、不依赖 adb 端口。

实测（2026-11-07）
------------------
* 读到 ``.qianliao.net`` 域下的 userId + rsessionId
* 该授权直连 ``https://m.qianliao.net/financial/api/transfer/gate/...``
  返回 ``state.code=0``，正式营 9 个
"""

import os
import re
import shutil
import subprocess
import time

import xqd_proc

# ── 已知路径 ────────────────────────────────────────────────
MUMU_ROOT_CANDIDATES = [
    r'D:\Program Files\Netease\MuMu',
    r'C:\Program Files\Netease\MuMu',
    r'D:\Program Files\Netease\MuMu Player',
    r'C:\Program Files\Netease\MuMu Player',
]

# 兴趣岛 App 包名
QIANLIAO_PKG = 'com.qlchat.xingqudao'

# App 侧 WebView Cookie 库
COOKIE_DB = '/data/data/%s/app_webview/Default/Cookies' % QIANLIAO_PKG

# 需要的 Cookie（与官方登录器 login-mooc.exe 的契约一致：
# 源码里 qianliao 分支 include_names = ['userId', 'rsessionId']）
REQUIRED_COOKIES = ('userId', 'rsessionId')

# 业务网关里用到的补充字段（可选，缺失不影响鉴权）
OPTIONAL_COOKIES = ('caller', 'platform', 'ver', 'deviceType', 'os')

# 网关域名
API_HOST = 'm.qianliao.net'


class AuthError(Exception):
    """授权流程失败。"""


class MumuNotFound(AuthError):
    """找不到 MuMu 安装。"""


# ── 底层：定位 MuMuManager ───────────────────────────────────

def find_mumu_manager():
    """定位 MuMuManager.exe。

    先看环境变量覆盖，再扫常见安装目录，最后退到 PATH。
    """
    env = os.environ.get('XQD_MUMU_MANAGER')
    if env and os.path.isfile(env):
        return env

    for root in MUMU_ROOT_CANDIDATES:
        if not os.path.isdir(root):
            continue
        # nx_main / nx_device 布局
        for rel in (r'nx_main\MuMuManager.exe',
                    r'nx_main\MuMuManager.exe',
                    r'MuMuManager.exe',
                    r'nemu\MuMuManager.exe'):
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                return p
        # 递归兜底（限深）
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth > 2:
                dirnames[:] = []
                continue
            if 'MuMuManager.exe' in filenames:
                return os.path.join(dirpath, 'MuMuManager.exe')

    found = shutil.which('MuMuManager.exe') or shutil.which('MuMuManager')
    if found:
        return found
    raise MumuNotFound(
        '找不到 MuMuManager.exe。\n'
        '请确认已安装网易 MuMu 模拟器，或设置环境变量 XQD_MUMU_MANAGER 指向该文件。')


def _manager_cmd(manager, vm_index, sub):
    """组装命令行。

    注意 MuMuManager 的参数顺序是 **子命令在前、-v 在后**
    （``MuMuManager info -v 0``），写成 ``-v 0 info`` 会打印帮助并返回非 0。
    """
    return [manager, sub, '-v', str(vm_index)]


# ── 模拟器状态 ──────────────────────────────────────────────

def player_info(manager, vm_index=0):
    """取模拟器信息（JSON）。失败返回 {}。"""
    cmd = _manager_cmd(manager, vm_index, 'info')
    try:
        out = xqd_proc.run(cmd, capture_output=True, timeout=30).stdout
        import json
        return json.loads(out.decode('utf-8', 'replace'))
    except Exception:
        return {}


def is_running(manager, vm_index=0):
    """Android 是否已启动完毕。"""
    info = player_info(manager, vm_index)
    return bool(info.get('is_android_started'))


def launch_player(manager, vm_index=0):
    """启动模拟器。返回是否成功发起。"""
    cmd = _manager_cmd(manager, vm_index, 'control') + ['launch']
    try:
        xqd_proc.run(cmd, capture_output=True, timeout=60)
        return True
    except Exception:
        return False


def shutdown_player(manager, vm_index=0):
    """关闭模拟器。"""
    cmd = _manager_cmd(manager, vm_index, 'control') + ['shutdown']
    try:
        xqd_proc.run(cmd, capture_output=True, timeout=60)
        return True
    except Exception:
        return False


def wait_until_ready(manager, vm_index=0, timeout=180, poll=3, on_tick=None):
    """等待模拟器 Android 启动完成。

    on_tick(elapsed, ready) 每轮回调一次，用于给 GUI 报进度。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        ready = is_running(manager, vm_index)
        if on_tick:
            try:
                on_tick(time.time() - t0, ready)
            except Exception:
                pass
        if ready:
            return True
        time.sleep(poll)
    return False


def ensure_main(manager=None, on_status=None):
    """确保 MuMu 主程序（多开器）在跑。

    返回 True 表示**这次是本工具启动的**（调用方据此决定是否负责关闭）。
    """
    def say(msg):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    if main_running():
        return False
    say('正在启动 MuMu…')
    if not launch_main(manager):
        return False
    # 等主进程真正起来（最多 30 秒）
    t0 = time.time()
    while time.time() - t0 < 30:
        if main_running():
            say('MuMu 已启动')
            _SESSION['main'] = True
            return True
        time.sleep(1)
    say('MuMu 启动超时，继续尝试拉起安卓设备…')
    return False


def ensure_device(manager, vm_index=0, timeout=240, on_status=None):
    """确保安卓设备实例在跑。

    返回 (ok, launched_by_us) —— launched_by_us 表示**这次是本工具
    启动的**（调用方据此决定是否负责关闭）。

    ⚠️ 实测顺序很重要：**先 `control launch`，主程序会被连带带起来**
    （13 秒就绪）。反过来先 `main launch` 再 `control launch` 反而会卡住，
    因为多开器起来后设备启动请求被它接管了。
    """
    def say(msg):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    if is_running(manager, vm_index):
        return True, False

    say('安卓设备未启动，正在启动…')
    launch_player(manager, vm_index)

    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_running(manager, vm_index):
            say('安卓设备已就绪（%.0fs）' % (time.time() - t0))
            _SESSION['device'] = True
            _SESSION['main'] = _SESSION['main'] or main_running()
            return True, True
        say('等待安卓设备启动… %.0fs' % (time.time() - t0))
        time.sleep(3)
    return False, True


# ── 内部 RPC shell ───────────────────────────────────────────

def shell(manager, vm_index, command, timeout=60):
    """在模拟器里执行 shell 命令（内部 RPC，非 adbd）。

    返回 (stdout, ok)。注意 MuMuManager 的 sh 会把 stderr 也混进 stdout。
    """
    cmd = _manager_cmd(manager, vm_index, 'sh') + ['-c', command]
    try:
        p = xqd_proc.run(cmd, capture_output=True, timeout=timeout)
        return p.stdout.decode('utf-8', 'replace'), p.returncode == 0
    except subprocess.TimeoutExpired:
        return '', False
    except Exception:
        return '', False


def launch_app(manager, vm_index=0, package=QIANLIAO_PKG):
    """拉起 App。"""
    cmd = _manager_cmd(manager, vm_index, 'control') + ['app', 'launch',
                                                        '--package', package]
    try:
        xqd_proc.run(cmd, capture_output=True, timeout=60)
        return True
    except Exception:
        return False


def app_installed(manager, vm_index=0, package=QIANLIAO_PKG):
    """App 是否已安装。"""
    out, _ = shell(manager, vm_index,
                   'pm list packages %s' % package, timeout=30)
    return ('package:%s' % package) in out


def vm_not_running(out):
    """判断 shell 输出是不是「设备没运行」的错误。

    设备停了时 MuMuManager 的 sh 返回的是一段 JSON 错误，而不是空输出：
    ``{"errcode": -201, "errmsg": "vm not running, can not connect NemuShell !!"}``

    ⚠️ 不识别这个会踩坑：以为「App 还活着」（pidof 输出非空）
    或者以为「读到了 Cookie」（其实是一段错误 JSON）。
    """
    if not out:
        return False
    low = out.lower()
    return ('vm not running' in low or 'nemoshell' in low
            or '"errcode"' in low)


def stop_app(manager, vm_index=0, package=QIANLIAO_PKG):
    """关闭 App（相当于「从后台划掉」）。

    优先用 MuMuManager 的 ``control app close``（走官方通道，干净）；
    失败再退回 ``am force-stop``。
    """
    cmd = _manager_cmd(manager, vm_index, 'control') + [
        'app', 'close', '--package', package]
    try:
        xqd_proc.run(cmd, capture_output=True, timeout=60)
    except Exception:
        pass
    shell(manager, vm_index, 'am force-stop %s' % package, timeout=30)
    return True


def wait_app_stopped(manager, vm_index=0, package=QIANLIAO_PKG, timeout=20):
    """等 App 进程真的消失。

    设备已经停了也算「已停止」（不必空等）。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        out, _ = shell(manager, vm_index, 'pidof %s' % package, timeout=15)
        if vm_not_running(out):
            return True
        if not out.strip():
            return True
        time.sleep(1)
    return False


# ── 会话状态 ────────────────────────────────────────────────────
# 记录**本次工具运行期间**由工具启动的组件。
# 为什么需要它：用户没登录时，工具会拉起 MuMu + App 让用户去登录，
# 用户登录完点「重试」——第二次跑时 MuMu 已经在运行，
# 若只看「当前是否在运行」就分不清是谁启动的，工具启动的东西就关不掉了。
_SESSION = {'main': False, 'device': False}


def session_state():
    """返回本次会话中由工具启动的组件。"""
    return dict(_SESSION)


def reset_session():
    """清空会话状态（工具退出时调用）。"""
    _SESSION['main'] = False
    _SESSION['device'] = False


# ── 主程序（MuMu 多开器）────────────────────────────────────────

MAIN_PROCESS = 'MuMuNxMain.exe'


def main_running():
    """MuMu 主程序（多开器 UI）是否在跑。"""
    try:
        out = xqd_proc.run(['tasklist', '/FI', 'IMAGENAME eq %s' % MAIN_PROCESS],
                             capture_output=True, timeout=20)
        txt = out.stdout.decode('utf-8', 'replace')
        return MAIN_PROCESS.lower() in txt.lower()
    except Exception:
        return False


def launch_main(manager=None):
    """启动 MuMu 主程序（多开器）。

    只在需要拉起安卓设备时用得上：MuMu 的设备实例依附于主程序，
    主程序不在时 ``control launch`` 可能拉不起来。
    """
    if manager is None:
        try:
            manager = find_mumu_manager()
        except Exception:
            return False
    cmd = [manager, 'main', 'launch']
    try:
        xqd_proc.run(cmd, capture_output=True, timeout=90)
        return True
    except Exception:
        return False


def close_main(manager=None):
    """关闭 MuMu 主程序。"""
    if manager is None:
        try:
            manager = find_mumu_manager()
        except Exception:
            return False
    cmd = [manager, 'main', 'close']
    try:
        xqd_proc.run(cmd, capture_output=True, timeout=60)
        return True
    except Exception:
        return False


def close_player(manager, vm_index=0, timeout=90):
    """关闭模拟器实例并等待真正退出。

    MuMu 的 ``control shutdown`` 是异步的：命令返回后进程还在跑，
    资源也不立刻释放。所以这里轮询 ``info`` 直到 ``is_android_started``
    变 False，再多等一小会儿让磁盘落盘完成。
    """
    if not shutdown_player(manager, vm_index):
        return False
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if not is_running(manager, vm_index):
                break
        except Exception:
            break
        time.sleep(2)
    time.sleep(3)
    return True


def close_all(manager, vm_index=0, package=QIANLIAO_PKG, timeout=90,
              close_main_app=None, close_device=None):
    """一次性收尾：停 App + 关安卓设备（+ 可选关主程序）。

    授权拿到后调用 —— 工具后续完全靠 Cookie 直连网关，不再需要模拟器。

    close_main_app / close_device 为 None 时，按**会话状态**决定：
    只有本次工具运行期间启动过的组件才会被关掉（用户自己开的窗口不动）。
    """
    st = session_state()
    if close_main_app is None:
        close_main_app = st['main']
    if close_device is None:
        close_device = st['device']

    try:
        stop_app(manager, vm_index, package)
        wait_app_stopped(manager, vm_index, package, timeout=20)
    except Exception:
        pass

    ok = True
    if close_device:
        ok = close_player(manager, vm_index, timeout=timeout)
    if close_main_app:
        try:
            close_main(manager)
        except Exception:
            pass
    _SESSION['main'] = False
    _SESSION['device'] = False
    return ok


# ── 读 Cookie ────────────────────────────────────────────────

# sqlite3 输出用 | 分隔，避免值里的逗号/引号破坏解析
# 域过滤覆盖 App 用到的全部业务域：
#   .qianliao.net / .xqdaolove.cn  —— 主业务域
#   .nicegoods.cn                   —— 同集团业务域，App 也可能把
#                                    rsessionId 写在这里（实测出现过）
_COOKIE_QUERY = (
    "select host_key,name,value from cookies "
    "where host_key like '%qianliao%' "
    "   or host_key like '%xqdaolove%' "
    "   or host_key like '%nicegoods%';"
)


def read_app_cookies(manager, vm_index=0, timeout=60):
    """从 App 的 WebView Cookie 库里读兴趣岛相关 Cookie。

    返回 {name: value}（同名取顶层域优先）。
    """
    cmd = ("sqlite3 '%s' \"%s\"" % (COOKIE_DB, _COOKIE_QUERY))
    out, ok = shell(manager, vm_index, cmd, timeout=timeout)

    # 设备没运行 —— 明确报错，别把它当成「没读到 Cookie」
    if vm_not_running(out):
        raise AuthError('安卓设备未运行，无法读取 Cookie 库。')
    if not ok and not out.strip():
        raise AuthError('读取 Cookie 库失败（sqlite3 无输出）')

    cookies = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or '|' not in line:
            continue
        parts = line.split('|')
        if len(parts) < 3:
            continue
        host, name, value = parts[0], parts[1], parts[2]
        # 只取顶层域（.qianliao.net）优先，它对所有子域生效
        domain_pref = host.startswith('.')
        if name not in cookies or (domain_pref and not cookies[name][0]):
            cookies[name] = (value, domain_pref)
    return {k: v[0] for k, v in cookies.items()}


def get_cookie_header(manager, vm_index=0):
    """拼出可直接用的 Cookie 请求头值。

    必需 userId + rsessionId，缺失则抛 AuthError。
    """
    cookies = read_app_cookies(manager, vm_index)
    missing = [c for c in REQUIRED_COOKIES if not cookies.get(c)]
    if missing:
        raise AuthError(
            'App 未登录（缺少 %s）。请在模拟器里打开兴趣岛 App 完成登录，'
            '然后回到工具点「重试」。' % '、'.join(missing))

    parts = []
    for name in REQUIRED_COOKIES:
        parts.append('%s=%s' % (name, cookies[name]))
    for name in OPTIONAL_COOKIES:
        if cookies.get(name):
            parts.append('%s=%s' % (name, cookies[name]))
    return '; '.join(parts)


def check_auth(manager, vm_index=0):
    """只检查本地是否有可用授权（不联网）。

    返回 (True, cookie_header) 或 (False, 原因说明)。
    """
    try:
        header = get_cookie_header(manager, vm_index)
        return True, header
    except AuthError as e:
        return False, str(e)
    except Exception as e:
        return False, '检查授权时出错：%s' % e


# ── 一步到位：确保拿到授权 ───────────────────────────────────

def ensure_auth(manager=None, vm_index=0, auto_launch=True,
                wait_timeout=180, on_status=None):
    """完整授权流程。

    1. 定位 MuMuManager
    2. 模拟器未启动则启动并等待就绪
    3. 读 App Cookie 库拿授权

    on_status(text) 用于向 GUI 播报每一步。

    返回 Cookie header 字符串。拿不到则抛 AuthError。
    """
    def say(msg):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    if manager is None:
        manager = find_mumu_manager()
    say('MuMu 管理器：%s' % manager)

    if not is_running(manager, vm_index):
        if not auto_launch:
            raise AuthError('MuMu 模拟器未运行。请先启动模拟器并登录兴趣岛 App。')
        say('模拟器未启动，正在启动…')
        launch_player(manager, vm_index)
        say('等待 Android 启动…')

        def tick(elapsed, ready):
            if ready:
                say('模拟器已就绪（%.0fs）' % elapsed)
            else:
                say('等待模拟器启动… %.0fs' % elapsed)

        if not wait_until_ready(manager, vm_index, timeout=wait_timeout,
                                on_tick=tick):
            raise AuthError('模拟器启动超时（%ds）。' % wait_timeout)

    say('读取 App 授权…')
    try:
        header = get_cookie_header(manager, vm_index)
    except AuthError:
        # App 未登录：拉起 App 窗口，提示用户去登录
        say('未找到登录态，正在打开兴趣岛 App…')
        launch_app(manager, vm_index)
        raise AuthError(
            '兴趣岛 App 尚未登录。\n\n'
            '已在模拟器中打开兴趣岛 App，请完成登录后回到本工具点「重试」。')

    say('授权获取成功')
    return header


if __name__ == '__main__':
    import sys
    try:
        mgr = find_mumu_manager()
        print('MuMuManager:', mgr)
        print('运行状态:', '已启动' if is_running(mgr) else '未启动')
        print('App 已安装:', app_installed(mgr))
        ok, info = check_auth(mgr)
        print('授权可用:', ok)
        print('详情:', info[:120] + '...' if ok else info)
    except Exception as e:
        print('错误:', e)
        sys.exit(1)

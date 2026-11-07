# -*- coding: utf-8 -*-
"""凭据读取 —— **单一入口，代码里绝不硬编码 Cookie**。

为什么要有这个模块
------------------
兴趣岛的业务网关靠 App WebView 里的 Cookie 鉴权（``userId`` + ``rsessionId``）。
这套凭据**等价于账号密码**，因此：

* ❌ 不能写进源码 —— 会进 git 历史，删掉也留在历史里；
* ❌ 不能进仓库 —— 仓库可能被 clone / 打包 / 推送；
* ✅ 只应存在**运行时**：环境变量，或用户目录下的私有文件。

读取优先级（从高到低）
----------------------
1. 环境变量 ``XQD_COOKIE``（推荐，CI / 临时调试用）
2. 环境变量 ``QLD_COOKIE``（``_lel/api/qianliao.py`` 历史上用的名字，保留兼容）
3. ``%USERPROFILE%\\.xqd_tool\\cookie.txt`` —— 私有凭据文件，**在仓库之外**

★ 早期还有第 4 级「读 ``cache-analysis/_apitest.py`` 的 COOKIE 变量」。
  那份抓包原件现已改为**反向调用本模块**（``COOKIE = load_cookie()``），
  若这里再回去读它，一旦私有文件缺失就会**无限递归**。
  真实凭据已迁到第 3 级，故该级**已移除**。

三种来源都没有时返回空字符串，由调用方自行判断「未授权」。

★ 凭据文件**不受** ``XQD_TEST_HOME`` 影响：那是给配置/历史/分片缓存做
  隔离用的，把凭据也隔离掉会让真网络测试拿不到授权（见 docs/11 J 节）。
"""

import os

# 环境变量名（按优先级）
ENV_KEYS = ('XQD_COOKIE', 'QLD_COOKIE')

# 私有凭据文件（用户目录，仓库之外）
CRED_FILE = os.path.join(os.path.expanduser('~'), '.xqd_tool', 'cookie.txt')


def _from_env():
    for k in ENV_KEYS:
        v = (os.environ.get(k) or '').strip()
        if v:
            return v
    return ''


def _from_file():
    """读私有凭据文件（单行，或多行时用分号拼起来）。"""
    try:
        if not os.path.isfile(CRED_FILE):
            return ''
        with open(CRED_FILE, 'r', encoding='utf-8', errors='replace') as f:
            raw = f.read()
    except OSError:
        return ''
    raw = raw.strip()
    if not raw:
        return ''
    # 允许文件里写成多行 cookie（每行一个 name=value）
    parts = [p.strip() for p in raw.replace('\r', '\n').split('\n') if p.strip()]
    if len(parts) > 1 and all('=' in p for p in parts):
        return '; '.join(parts)
    return raw


def load_cookie(required=False):
    """取业务网关 Cookie。

    返回 Cookie header 字符串；三种来源都没有时返回 ``''``。
    required=True 时取不到就抛 RuntimeError。
    """
    cookie = _from_env() or _from_file()
    if required and not cookie:
        raise RuntimeError(
            '拿不到兴趣岛授权。请设置环境变量 XQD_COOKIE，'
            '或把 Cookie 写入 %s' % CRED_FILE)
    return cookie


if __name__ == '__main__':
    c = load_cookie()
    # 只打印是否可用 + 长度，绝不打印内容
    print('凭据来源优先级：env(%s) -> %s'
          % (' / '.join(ENV_KEYS), CRED_FILE))
    print('拿到凭据：%s（长度 %d）' % ('是' if c else '否', len(c)))

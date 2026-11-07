# 兴趣岛视频下载器

把「兴趣岛」App（`com.qlchat.xingqudao`）的课程视频批量导出为**通用 MP4**，
包括 DRM 课程（走同目录明文孪生，**无需解密**）。

> 用途：临时转移到教学大屏，用后删除。

---

## 快速开始

```bash
# 1. 确认模拟器在线
"D:/Program Files/Netease/MuMu/nx_main/adb.exe" devices

# 2. 启动服务（用后台任务方式，不要用 & 后台化）
python -u xqd_server.py --port 8765 --out "D:/user/chisenin/Videos"

# 3. 打开界面
#    http://127.0.0.1:8765/
```

界面：**筛选标签 → 营列表 → 点营进入课表 → 勾选/单点下载**。

---

## 文档

**先读这个，能省掉大量重复探测。**

| 文件 | 内容 |
|---|---|
| [`docs/01-已验证事实.md`](docs/01-已验证事实.md) | ⭐ **权威结论清单**。所有已实测确认的事实，探测前必查 |
| [`docs/02-架构与代码结构.md`](docs/02-架构与代码结构.md) | 分层架构、各模块函数清单、API 列表 |
| [`docs/03-踩坑与修复记录.md`](docs/03-踩坑与修复记录.md) | 实际浪费过时间的坑，别再犯 |
| [`docs/04-用户需求与UI规格.md`](docs/04-用户需求与UI规格.md) | 需求边界、UI 交互规格、保存结构 |
| [`docs/05-待办与下一步.md`](docs/05-待办与下一步.md) | 当前进度、待办、开工检查清单 |

---

## 目录结构

```
.
├── xqd.py              底层采集（ADB / 页面识别 / DOM 解析 / 清单读取）
├── xqd_app.py          业务动作（标签→营→课表→fileId→链接→下载）
├── xqd_server.py       本地 HTTP 服务（Python 标准库，无依赖）
├── ui.html             前端单页（原生 JS）
├── state/              持久化：names.json / links.json / catalog.json
├── docs/               文档（见上）
├── archive/probes/     一次性探测脚本（50 个，历史记录，非生产代码）
└── cache-analysis/     1.9G 原始分析材料（已 gitignore）
```

---

## 核心机制速览

1. **拿链接**：播放一节课 → App 刷新隐藏清单 `.<md5>.hls` → 清单 URL 里的业务
   fileId 就是该节课的 fileId。用**清单 mtime 差分**精确定位，约 0.7 秒/节。
2. **课名不靠反推**：进入课程列表页时，**整营全部课名已在 DOM 里**
   （屏幕外节点 bounds 为 0 但文本可读），按文档顺序配对课名/日期/按钮。
3. **DRM 绕过**：DRM 清单同目录存在明文孪生 `v.fXXXXXXX.m3u8`，
   **时长完全一致**（782.4s / 1214.0s 实测吻合），走孪生即得普通 MP4。
   时长校验是必需的 —— 同目录还有别的视频，不校验会下错内容。
4. **签名只绑目录**：URL 的 `sign` 只绑定目录和 `t`，不绑定文件名；
   `t` 偏移服务器时钟约 4.8 小时，有效性用 HTTP 200/403 实探判断。

---

## 输出

```
D:\user\chisenin\Videos\<营名>\<课名>.mp4
例：D:\user\chisenin\Videos\引气归源太极营\先导课：解谜自然之道.mp4
```

---

## 依赖

- Python 3.8+（**只用标准库**）
- ffmpeg（PATH 或 `C:\ffmpeg\bin\ffmpeg.exe`）
- MuMu 模拟器（桥接模式）

---

## 注意事项

- 改过 `xqd_app.py` **必须重启服务**才生效。
- 本机 curl 走系统代理，测接口要加 `--noproxy '*'`。
- 用户流量昂贵，下载前会先 `probe_alive`；签名过期会自动回模拟器重新绑定。

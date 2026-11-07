# 项目长期记忆 —— 兴趣岛视频下载器

项目目录：`D:\.workbuddy\2026-11-06-20-15-25`（**已 git 管理**）

## ★ 第一条规矩

**动手前先读 `docs/01-已验证事实.md`**（业务 API 契约、DOM 解析、签名、DRM 孪生、命名）。
文档里有的结论**不要重新探测** —— 用户已明确批评过反复探测。
实现细节 → `docs/11`；踩坑 → `docs/03`；现状/环境/合规 → `docs/12`；
改动过程 → `.workbuddy/memory/2026-11-0*.md`。

## 项目是什么 / 硬约束

把「兴趣岛」App（`com.qlchat.xingqudao`）课程视频批量导出为通用 MP4
（含 DRM 课，走明文孪生**无需解密**）。用户是教师，导到教学大屏用。

- 不用投屏 / HDMI / 录屏 / App 内手工下载（用户明确排除）。
- 网络极不稳定、流量昂贵 → 少请求、别重复下载。
- 教学大屏磁盘小 → 导出后及时删除。
- 只需「正式营」「体验营」（已付费）；「轻课」确认是空的，**别再探**。
- 成品结构见「命名规则」一节；全角冒号 `：` 保留。
## 代码结构（见 `docs/12`）

采集 `xqd.py` / `_lel/api/qianliao.py` → 业务 `xqd_app.py` / `xqd_api.py` →
`xqd_server.py` + `ui.html`（网页版）/ **`xqd_gui.py`（★ PySide6 桌面工具，用户现在用的
就是这个）**，配套 `xqd_platform.py`/`xqd_engine.py`/`xqd_auth.py`/`xqd_history.py`/
`xqd_dedupe.py`/`xqd_creds.py`；CLI 批处理 `xqd_pdl.py`/`xqd_batch.py`，打包 `build_exe.py`。
两套数据源靠 `--mode` 切换：`api`（默认，**不需要模拟器**）/ `adb`（旧路径）。
API 模式不需要 sweep，播放地址现场解析，`t` 每次都变 → 签名天然新鲜。
**课名不靠播放反推**（课表一次拿全）。## ★ 业务 API（已全链路打通，详见 `docs/09`）

`POST https://m.qianliao.net/financial/api/transfer/gate/<endpoint>`，Body `{"transferData":{...}}`
- **成功码在 `state.code`**（不是顶层 `code`）—— 读顶层永远 None，会误判打不通。
- **必须 `ProxyHandler({})` 禁用系统代理**，否则被代理吞掉返回 HTML。
- 端点（前缀 `/gate/course/`）：营列表 `myCourseListV2`（`skyType`：`FINANCIAL`→9 正式营、
  `INTENTION`→1 体验营、不传→26 含公开课）、课表 `playListOfCourse`、播放地址
  `getCoursePlayUrl`（`businessType`=`camp`/`OPEN_COURSE`）。

## 授权（免 adbd）与 MuMu 启停 → 全部细节见 `docs/11` A 节

- `MuMuManager sh -v 0 -c "sqlite3 '.../Cookies' \"select ...;\""` 走**模拟器内部 RPC
  （非 adb 协议）**，uid=0(root)，Cookie 明文存 rsessionId。
- ★ 参数顺序**子命令在前、`-v` 在后**；SQL `like '%%x%%'` 匹配不到行，**必须 `'%x%'`**；
  域名覆盖 `.qianliao.net` / `.xqdaolove.cn` / **`.nicegoods.cn`**。
- 直接 `control -v 0 launch` 会连带拉起主程序（13 秒就绪）；**先 `main launch` 反而卡住**。
  `control shutdown` 异步 → 轮询 `info` 等 `is_android_started` 变 False。

## 命名规则（见 `docs/01`）

`Z:\太极营\<营名>\<序号>.<课名>.<YYYY.MM.DD>.mp4`
- 序号 = 营内课表顺序（1 起）；`playListOfCourse` 顺序**与 App 列表一致**（实测吻合）。
- 日期 = 该节 `startTime`。单一事实来源：`xqd_api.course_filename(item, seq, used)`。

## 最易做错的六条（全部细节在 `docs/11`）

1. **两个独立速率计**：字节计→「速度」列，内容时长计→ETA；混用会让 248 倍速显示成 `248B/s`。
2. **总字节均匀抽样外推**（12 片等距）：取前 3 片外推偏高 37.3%。
3. **状态词表单一来源** + `_set_both_states()` 成对更新课名后状态词与下载管理状态；
   状态词存 `item.data(STATE_ROLE)`（`LessonTitleDelegate` 自绘，不占独立列）。
4. **续传**：引擎清理条件必须 `if own_dir or (ok_result and not keep_parts)`，写反会删本钱。
5. **Windows 下载目录读注册表 Known Folder GUID**
   `{374DE290-123F-4565-9164-39C4925E467B}` → `D:\user\chisenin\download`。
6. **测试必须设 `XQD_TEST_HOME`** 隔离配置/历史/分片缓存，否则会改用户下载目录。
   ⚠️ 凭据文件**不受**它影响（隔离了就拿不到授权）。

## 合规与进度（见 `docs/12`）

- 学无止：用了 `_lel/` 下部分材料（运行时主链路自建）；官方仓库
  `Xue-Wu-Zhi/xuewuzhi-downloader`（MIT、24★），NOTICE 明确**官方客户端不在 MIT 范围内**
  → 复现的 163 内核不能声称 MIT；旧址 `PyJun/Mooc_Downloader` 已 404。
- 进度：核心能力全就绪（API 全链路、端到端 6/6、GUI v1.4.0 含历史+续传、
  回归 284 项全绿 + 真网络 35 项）。待办：全量 266+6 节、163 适配器实战。
- 安全：凭据已脱敏。`xqd_creds.load_cookie()` 是唯一入口（env `XQD_COOKIE`
  → `~/.xqd_tool/cookie.txt`，仓库外）；**绝不硬编码 Cookie**。


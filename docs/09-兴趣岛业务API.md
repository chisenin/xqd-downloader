# 兴趣岛业务 API（**已实测打通，取代模拟器路径**）

> 最后更新：2026-11-07
> 状态：**全部端点 code=0 实测通过**；6/6 节课下载成功，ffprobe 时长误差 < 0.7s。
> 实现：`_lel/api/qianliao.py`（底层客户端）、`xqd_api.py`（数据源）、`xqd_server.py --mode api`。

---

## 一、结论先行：不需要 GUI 登录器，也不需要模拟器

上一轮的核心卡点是「实测 `login-mooc.exe` 拿 Cookie」。**这条路线已被绕过**：

- 手里有一份**从模拟器 App 抓包得到的真实 Cookie**
  （`rsessionId` + `userId` + `caller=app_edu` …），存在仓库外的
  `%USERPROFILE%\.xqd_tool\cookie.txt`（凭据等价账号密码，不入库）。
- 这份 Cookie 直接调业务网关即返回 `state.code = 0`。
- → 于是「官方登录器」这个支点变得**不必要**了。`login-mooc.exe` 保留作为
  Cookie 过期时的备用手段，但不再是阻塞项。

---

## 二、网关契约（权威，来自官方前端 bundle 明文）

前端 HTTP 封装（`webcache` 里的 bundle 原文）：

```js
r = location.origin + "/financial/api/transfer" + t.url
i = { transferData: t.body }
a = {method:"POST", body:i, headers:{"Content-Type":"application/json;charset=UTF-8"},
     credentials:"include"}
```

所以最终形态是：

```
POST https://m.qianliao.net/financial/api/transfer/gate/<endpoint>
Body: {"transferData": { ...业务参数... }}
Headers:
  Content-Type: application/json;charset=UTF-8
  Cookie: <rsessionId=...; userId=...; ...>
  Origin: https://m.qianliao.net
```

### ⚠️ 三个极易踩的坑

| 坑 | 现象 | 正解 |
|---|---|---|
| **成功码位置** | 读顶层 `code` 永远得到 `None`，误判为「打不通」 | 成功码在 **`state.code`**，结构是 `{state:{code,msg}, data:{...}}` |
| **代理** | 请求被系统代理吞掉，拿到 HTML 首页 | 必须 `ProxyHandler({})` **禁用系统代理** |
| **判响应类型** | 200 不代表是 JSON | `m.qianliao.net` 的 404/错误页会返回 **HTML**（title=`授权登录`），先判首字节是 `{` 还是 `<` |

> 附：`app.qianliao.net` 是 App 原生接口域名，返回 Spring 的 `{"status":404,...}`，
> **不承载 Web 业务端点**。业务端点只在 `m.qianliao.net`（及 `m1.xqdaolove.com/.cn` 镜像）上。

---

## 三、端点与参数（全部实测 code=0）

| 端点 | transferData | 返回 data | 备注 |
|---|---|---|---|
| `/gate/course/myCourseListV2` | `{skyType, page:{page,size}}` | `{courses:[...]}` | **营列表主入口** |
| `/gate/course/myCourseList` | `{page:{...}}` | `{courses:[...]}` | 老版，字段较少 |
| `/gate/course/playListOfCourse` | `{campId, onlyCourseCatalogue:true}` | `{courses:[...]}` | **整营课表** |
| `/gate/course/getSimpleCampDetail` | `{campId}` | 营详情 | |
| `/gate/course/getCoursePlayUrl` | `{videoHost, roomId, topicId, businessId, businessType}` | `{coursePlayUrl:{...}}` | **播放地址** |
| `/gate/course/getCampCourseDetail` | `{campId}` | 营详情（更全） | |
| `/gate/openCourse/playListOfCourse` | `{periodId}` | `{courses:[]}` | 公开课 |
| `/gate/smallCourse/smallCourseTopicList` | `{courseId}` | `{list:[]}` | |

### 营类型靠 `skyType` 区分（实测）

| skyType | 含义 | 实测数量 | 备注 |
|---|---|---|---|
| `FINANCIAL` | **正式营** | **9 个** | 与 App「正式营」标签实测的 9 个完全一致 |
| `INTENTION` | **体验营** | **1 个** | 道门-柔筋活络太极营-2营 |
| 不传 | 全部（含公开课） | 26 个 | 其中公开课 `campId=null`、`skuType=OPEN_COURSE` |
| `EXPERIENCE` | — | **0 个** | 服务端不认这个值 |

> **「轻课」在 App 内已确认是空的 → 不要探测。**
> 本表已覆盖 App「全部/正式营/体验营」三个标签的全部数据。

### 正式营清单（实测 9 个）

| 营名 | campId | 节数 |
|---|---|---|
| 道德经诵读 | 73040630406 | 27 |
| 太极功法巩固班 | 35650633025 | 4 |
| 静坐内观-身心共养计划 | 5721891467 | 61 |
| 太极中阶复训营 | 44504162806 | 3 |
| 五行养生音乐 | 67154432975 | 10 |
| 引气归源太极营 | 3485705003 | 70 |
| 先导课——以自然之道，养生命之源 | 45235137581 | 1 |
| 调和养正太极营 | 1491668059 | 52 |
| 【全面升级】养元活血太极营 | 1784767052 | 38 |

> 节数与既有 ADB 实测**完全吻合**（引气归源 70、静坐内观 61），
> 第一节课名也都是「先导课：解谜自然之道」—— 说明 API 与 App 数据同源。

---

## 四、播放地址返回结构

```json
{
  "type": "VIDEO",
  "playUrl": "https://video2.qianliao.net/43a5a542vodtranscq1500020547/c4e8eb573270835013331836280/v.f1440283.m3u8?t=6aee9e6a&us=25a4a5a1-...&sign=ef3d396c...",
  "fileId": "3270835013331836280",
  "keySign": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "totalSeconds": 535,
  "appId": "1500020547",
  "intelligentPlayUrl": null
}
```

- `playUrl` 的形态与 `docs/01-已验证事实.md` 第六节的 URL 结构**完全一致**，
  因此既有的清单分派（drm / master / media）、明文孪生、master 短边选清晰度
  等规则**可以原样复用**。
- `businessType`：`camp`（正课）| `OPEN_COURSE`（公开课，此时 `businessId` 传空串）。
- `totalSeconds` 可直接当作期望时长用于孪生校验。

### `t` 参数不再是问题

API 返回的 `t` 随请求变化（实测每次调用都不同），**签名天然新鲜**。
这意味着 API 模式下**不需要「链接过期 → 回模拟器重新绑定」**这套补偿逻辑。

---

## 五、端到端验证结果（6/6 通过）

| 课名 | 类型 | 期望时长 | 实测时长 | 分辨率 | 误差 |
|---|---|---|---|---|---|
| 清晰目标：开启性命双修之旅 | media | 535 | 535.4 | 1280×720 | 0.36s |
| 【静坐姿势】道家七支坐法 | media | 1164 | 1164.2 | 1280×720 | 0.25s |
| 【静坐法门】静坐准备、方法和注意事项 | media | 583 | 583.3 | 1280×720 | 0.31s |
| 聚气凝神巩固课——五行导引功串联+六字呼吸法 | master | 4251 | 4251.1 | 1080×1920 | 0.09s |
| 聚气凝神巩固课——十二段锦（9-12段）讲解带练 | master | 3842 | 3842.2 | 1080×1920 | 0.18s |
| 聚气凝神巩固课---太极拳详解 | master | 3773 | 3773.7 | 1080×1920 | 0.66s |

master 多码率实测：码率列表 `[(480,480x852), (720,720x1280), (1080,1080x1920)]`，
按**短边**选中 1080x1920（竖屏课，按高度选会误取最差一路）。

---

## 六、两种数据源对比

| | API 模式（`--mode api`，默认） | ADB 模式（`--mode adb`） |
|---|---|---|
| 需要模拟器 | **否** | 是 |
| 拿课表 | 一次请求拿全营 | 逐屏滚动 + uiautomator dump |
| 拿播放地址 | 现场调 `getCoursePlayUrl` | 逐节播放，用清单 mtime 差分反推 fileId |
| sweep 步骤 | **不需要** | 需要（约 0.7 秒/节） |
| 签名过期 | 不会（每次现场取新） | 需重新绑定 |
| 稳定性 | 高（纯 HTTP） | 受模拟器状态影响 |
| 速度 | 快 | 慢一个数量级 |

---

## 七、代码位置

| 文件 | 职责 |
|---|---|
| `_lel/api/qianliao.py` | API 客户端 + 清单解析工具（可独立 import） |
| `xqd_api.py` | 数据源适配层，语义与 `xqd_app.py`（ADB 版）一致 |
| `xqd_server.py` | `--mode api|adb` 切换；`/api/state` 暴露 `mode` |
| `ui.html` | 按 mode 隐藏「绑定链接」，状态列改显示类型+时长 |

---

## 八、遗留与后续

1. **Cookie 过期怎么办** —— `rsessionId` 有有效期。过期时 API 返回 `state.code=110`。
   备用方案（未验证）：
   - 从模拟器 App 重新抓包 Cookie，写入 `%USERPROFILE%\.xqd_tool\cookie.txt`；
   - 或走 `login-mooc.exe`（参数契约已确认：
     `login-mooc.exe <cookies_file> <login_name>`，见 `_lel/login/extracted/main.js` 第 19-27 行）。
2. **163 适配器** —— 解密内核已就绪（`_lel/core/netease_mooc.py`，官方样本 2/2 通过），
   只缺 `open163` Cookie 实战。
3. **全量下载** —— 9 个正式营共 266 节 + 1 个体验营 6 节。

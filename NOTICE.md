# NOTICE —— 第三方组件与开源项目声明

本仓库（兴趣岛课程导出工具）为本项目**独立编写**的代码，
不包含任何账号体系、加密服务或商业代码。

---

## 一、运行时依赖的第三方组件

| 组件 | 许可证 | 用途 |
|---|---|---|
| **FFmpeg** | LGPL-2.1+ / GPL（视构建而定） | HLS 分片拼接转封装为 MP4；ffprobe 校验成品时长 |
| **.NET 8 桌面运行时** | MIT（.NET Foundation / Microsoft） | WPF 界面与下载引擎的宿主；**不随本仓库分发** |

> **v1.6.1 起，Python 实现已从仓库删除** —— PySide6 / Qt、pycryptodome、
> Python 不再是运行时依赖。`_lel/` 下的分析原稿仍然保留（见第二节），
> 但**不在运行链路里**，其中的 `pycryptodome` 依赖仅供阅读参考。

---

## 二、参考的开源项目

### 学无止下载器（Xuewuzhi Downloader）

- 仓库：<https://github.com/Xue-Wu-Zhi/xuewuzhi-downloader>
- 许可：MIT License（**仅覆盖该仓库新编写的公开文档与 Python 离线骨架**）
- 官网：<https://www.xuewuzhi.cn/downloader>

**参考内容**：其公开的平台目录与图文教程，用于了解各教学平台
（兴趣岛、网易云课堂、中国大学 MOOC 等）的接口形态与常见加密方式。

### 特别声明（务必阅读）

在摸清兴趣岛与网易云课堂的接口细节时，曾分析学无止下载器**官方
Windows 客户端**（V1.5.0 / V2.19.70）的行为。本仓库中：

| 路径 | 性质 |
|---|---|
| `_lel/core/netease_mooc.py` | 依据其 V1.5.0 `Source/core` 的逻辑**独立复现**的 163 解密内核（非原文照抄） |
| `_lel/login/` | 从其 `Login-Mooc/resources/app.asar` 提取的登录层明文 JS（分析记录） |
| `_lel/v2/` | 对其 V2 PYZ 定制加密的分析/破解脚本（分析记录） |
| `_lel/api/qianliao.py` | 业务网关协议的对照原稿（分析记录；C# 实现在 `src/Xqd.Core/Api/`） |

上述部分**不属于** `Xue-Wu-Zhi/xuewuzhi-downloader` 仓库的 MIT 授权范围
（该仓库的 NOTICE 明确写明：GitHub Releases 中分发的官方桌面客户端
不属于 MIT 源码授权范围，其核心引擎与平台适配实现不在仓库内）。

本工具**不含**其客户端代码，仅用于个人学习与本地教学演示。

---

## 三、商标与平台名称

「学无止」名称及品牌标识用于说明本项目来源，版权归其权利人所有。
文中出现的各平台名称属于相应权利人；列入使用目录**不表示**与这些平台
存在合作或背书关系。

---

## 四、内容权利

课程内容的权利不因本软件或本仓库的许可而改变。
使用者请遵守课程提供方的授权要求，**只处理自己有权访问与保存的内容**。
本工具不提供、也不鼓励用于未购内容的批量获取。

---

## 五、C# / WPF 实现（`src/`）的额外声明

v1.5.3 起 C# 实现与 Python 实现同在 `master`；**v1.6.1 起 Python 实现已删除**，
仓库只剩 C# 一套运行时（`_lel/` 仅保留合规与分析材料）。上文第一至四节同样适用。
C# 实现的组件与授权：

| 组件 | 授权 | 说明 |
|---|---|---|
| .NET 8 SDK / Runtime、Windows Desktop Runtime（含 WPF） | MIT（.NET Foundation / Microsoft） | 使用系统自带运行时，**不随本仓库分发** |
| `System.Text.Json` / `HttpClient` / `Process` 等 BCL | MIT（.NET） | **零第三方 NuGet 依赖** |
| FFmpeg / ffprobe | LGPL-2.1+ / GPL | 外部可执行文件，不由本仓库分发 |

`Xqd.Core/Crypto/Netease163.cs` 是 `_lel/core/netease_mooc.py` 的等价移植，
**延续上文第二节的边界**：依据第三方客户端行为独立复现，
不属于 `Xue-Wu-Zhi/xuewuzhi-downloader` 仓库的 MIT 授权范围，不得声称 MIT。

C# 实现同样**不含任何账号凭据**，凭据只在运行时从环境变量或用户私有文件读取。

发行二进制由 `.github/workflows/release.yml` 在 GitHub Actions 的 Windows runner
上构建，仓库内不存放 exe / zip；发布包为 **C# 目录发布**，只含本项目编译产物，
运行时依赖（.NET 桌面运行时 / FFmpeg）由用户系统自行提供。

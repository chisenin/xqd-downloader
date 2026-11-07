using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Xqd.Core;

namespace Xqd.Core.Crypto;

/// <summary>
/// 网易课堂（163）视频加密地址解密内核 —— 对照 _lel/core/netease_mooc.py。
///
/// 原逻辑（见 netease_mooc.py 头注）：学无止下载器 v1.5.0 官方桌面客户端
/// Source/core.dec（明文 JS）里的 getToken()/formatM3u8EncryptUrl()/decryptAES()：
///   decryptAES(k, v):
///       key   = L(v)                  # 由 charListMap / charEnlist 派生的 16 字节
///       raw   = base64decode(k)
///       iv    = raw[:16] ; body = raw[16:]
///       plain = AES-CBC(key, iv, body)   # 不含自动去填充
///       手动 PKCS7 去填充 → JSON(plain 到首个 '}' 为止)
///   formatM3u8EncryptUrl(e) = e.videoUrl + "&amp;token=" + decryptAES(e.k, e.v).k
///
/// ★ 授权声明（docs/01「十四、学无止下载器的授权边界」，务必如实，不得含糊）：
///   · 本文件是依据上述 JS 逻辑「独立复现」的 163 解密内核，与 netease_mooc.py 等价。
///   · 学无止官方仓库（github.com/Xue-Wu-Zhi/xuewuzhi-downloader）为 MIT License，
///     但其 NOTICE.md 明确写明：GitHub Releases 中单独分发的「学无止官方桌面客户端」
///     **不属于**该 MIT 源码授权范围 —— 客户端核心引擎与平台适配实现并不在仓库内。
///   · 因此本复现内核 **不是 MIT 授权代码**，也**不在**学无止仓库的 MIT 授权范围内，
///     绝不能标注 / 声明为 MIT。此处仅作历史分析材料的等价实现保留。
///   · 本项目运行时主链路（兴趣岛 API 模式 / 自建下载内核）完全自建，不依赖本内核。
///   · 旧地址 github.com/PyJun/Mooc_Downloader（大量中文教程引用的那个）已 404，不要引用。
/// </summary>
public static class Netease163
{
    // ── 密钥派生表（来自 core.dec 的 charEnlist / charListMap） ─────────
    // charEnlist1 = 小写 a-z，charEnlist2 = 大写 A-Z，charEnlist3 = 数字 0-9
    private const string E1 = "abcdefghijklmnopqrstuvwxyz";
    private const string E2 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    private const string E3 = "0123456789";

    // v_<n> -> [(charEnlist 编号, 字符下标), ...]，每项 16 个 → 16 字节密钥
    private static readonly Dictionary<int, (int t, int i)[]> CharListMap = new()
    {
        [0] = new (int, int)[] {
            (3, 1), (1, 2), (1, 4), (2, 4), (2, 18), (2, 12), (2, 5), (2, 18),
            (2, 4), (1, 0), (2, 22), (1, 11), (2, 6), (2, 16), (1, 7), (2, 24),
        },
        [1] = new (int, int)[] {
            (3, 3), (1, 5), (1, 15), (3, 4), (1, 23), (1, 18), (3, 9), (3, 2),
            (3, 2), (1, 14), (1, 20), (1, 22), (3, 5), (1, 16), (3, 7), (3, 2),
        },
        [2] = new (int, int)[] {
            (2, 16), (2, 7), (1, 7), (2, 24), (1, 17), (2, 4), (1, 4), (2, 18),
            (2, 12), (2, 5), (2, 18), (2, 4), (1, 0), (2, 22), (1, 11), (2, 6),
        },
        [3] = new (int, int)[] {
            (2, 18), (1, 4), (1, 7), (2, 24), (1, 17), (2, 15), (1, 4), (2, 18),
            (2, 11), (2, 5), (2, 18), (1, 14), (1, 0), (2, 22), (1, 11), (3, 5),
        },
    };

    /// <summary>
    /// 按 version 号派生 16 字节 AES 密钥。对应 netease_mooc.derive_key。
    /// 未知版本抛 ArgumentException（与原 JS / Python 行为一致）。
    /// </summary>
    public static byte[] DeriveKey(int version)
    {
        if (!CharListMap.TryGetValue(version, out var pairs))
            throw new ArgumentException("unknown key version: " + version, nameof(version));

        var sb = new StringBuilder(16);
        foreach (var (t, i) in pairs)
        {
            string list = t switch
            {
                1 => E1,
                2 => E2,
                3 => E3,
                _ => throw new ArgumentException("unknown charEnlist: " + t),
            };
            sb.Append(list[i]);
        }
        return Encoding.ASCII.GetBytes(sb.ToString());
    }

    /// <summary>
    /// 解出明文 JSON。对应 netease_mooc.decrypt_aes。
    /// 失败返回 default(JsonElement)（ValueKind=Undefined），与原 JS「失败返回 None」一致。
    ///
    /// 填充语义：pycryptodome 的 AES-CBC decrypt 返回含填充的原始明文，
    /// 故这里用 PaddingMode.None + 手动 PKCS7 去填充，逐字节复现（不交给 BCL 自动校验）。
    /// IV=raw[:16]、body=raw[16:]；解码用 UTF-8 replacement（对应 decode('utf-8','replace')）；
    /// 只取到首个 '}' 为止的片段做 JSON 解析（其后是填充/其它数据）。
    /// </summary>
    public static JsonElement DecryptAes(string kB64, int version)
    {
        try
        {
            byte[] raw = Convert.FromBase64String(kB64 ?? "");
            if (raw.Length <= 16) return default;                 // body 为空 → None

            var iv = new byte[16];
            Buffer.BlockCopy(raw, 0, iv, 0, 16);
            var body = new byte[raw.Length - 16];
            Buffer.BlockCopy(raw, 16, body, 0, body.Length);

            byte[] key = DeriveKey(version);
            using var aes = Aes.Create();
            aes.Key = key;
            aes.IV = iv;
            aes.Mode = CipherMode.CBC;
            aes.Padding = PaddingMode.None;                       // 手动去填充
            using var dec = aes.CreateDecryptor();
            byte[] plain = dec.TransformFinalBlock(body, 0, body.Length);
            if (plain.Length == 0) return default;

            int pad = plain[plain.Length - 1];
            int len = plain.Length;
            if (pad >= 1 && pad <= 16) len -= pad;               // PKCS7：strip pad 字节

            string text = Encoding.UTF8.GetString(plain, 0, len);
            int end = text.IndexOf('}');
            if (end < 0) return default;
            return J.Parse(text.Substring(0, end + 1));          // JSON(plain 到首个 '}')
        }
        catch
        {
            return default;                                       // 与原 JS 行为一致
        }
    }

    /// <summary>
    /// 把带 k/v 的视频信息还原为可直连的 m3u8 URL。对应 netease_mooc.format_m3u8_encrypt_url。
    /// info 需含 videoUrl / k / v；无需解密时 Error=null，直接回传 videoUrl。
    /// </summary>
    public static (string Url, string Error) FormatM3u8EncryptUrl(JsonElement info)
    {
        string url = info.Str("videoUrl");
        string k = info.Str("k");
        string v = info.Str("v");
        if (string.IsNullOrEmpty(url)) return (null, "missing videoUrl");
        if (string.IsNullOrEmpty(k)) return (url, null);          // 无需解密

        // Python 里 v 会在 derive_key 里 int(version)；解析不了等价于解密失败
        if (!int.TryParse(v, NumberStyles.Any, CultureInfo.InvariantCulture, out int version))
            return (null, "decryptAES fail");

        var result = DecryptAes(k, version);
        if (result.ValueKind != JsonValueKind.Object) return (null, "decryptAES fail");

        string token = result.Str("k");
        if (string.IsNullOrEmpty(token)) token = result.Str("videoDecryptionKey");
        if (string.IsNullOrEmpty(token)) return (null, "no token in decrypted payload");

        string sep = url.IndexOf('?') >= 0 ? "&" : "?";
        return (url + sep + "token=" + token, null);
    }

    /// <summary>format_m3u8_encrypt_url 的字段直传重载（v 可为数字或数字字符串）。</summary>
    public static (string Url, string Error) FormatM3u8EncryptUrl(
        string videoUrl, string k, string v)
    {
        var json = JsonSerializer.Serialize(new Dictionary<string, string>
        {
            ["videoUrl"] = videoUrl ?? "",
            ["k"] = k ?? "",
            ["v"] = v ?? "",
        });
        return FormatM3u8EncryptUrl(J.Parse(json));
    }
}

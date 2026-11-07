import subprocess, sys
ADB = r'D:\Program Files\Netease\MuMu\nx_main\adb.exe'
DEV = '192.168.1.101:5555'

def sql(q):
    cmd = [ADB, '-s', DEV, 'shell', "sqlite3 -separator '|' /data/data/com.qlchat.xingqudao/databases/AndroidAria.db \"%s\"" % q]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return (r.stdout or '').strip()

print('--- DownloadEntity (fileName | url) ---')
print(sql("select fileName, substr(url,1,140) from DownloadEntity limit 15;"))
print('--- DownloadGroupEntity (alias | urls) ---')
print(sql("select alias, substr(urls,1,200) from DownloadGroupEntity limit 15;"))
print('--- counts ---')
for t in ('DownloadEntity', 'DownloadGroupEntity', 'TaskRecord', 'M3U8Entity'):
    print(t, sql("select count(*) from %s;" % t))

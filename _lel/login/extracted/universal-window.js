'use strict';
const path = require('path');
const fs = require('fs');
const net = require('net');
const {localFileURL} = require('./local-file-url');
const {openCaptureBrowser} = require('./universal-browser');
const {app, BrowserWindow, ipcMain, session, screen, dialog, clipboard, shell, powerMonitor} = require('electron');
app.commandLine.appendSwitch('no-proxy-server');
const DOTNET_DOWNLOAD_URL = 'https://dotnet.microsoft.com/zh-cn/download/dotnet-framework/net48';
const ACTIONS = new Set(['snapshot', 'select', 'select_batch', 'auto_select', 'directory', 'start_capture', 'stop_capture',
    'trust', 'trust_and_start', 'cancel_certificate', 'refresh', 'membership', 'download', 'cancel', 'clear', 'clear_records', 'open_directory',
    'open_resource_directory', 'domain_filter', 'network_settings', 'copy_title', 'copy_domain', 'copy_link',
    'parallelism', 'cancel_download', 'start_mobile', 'stop_mobile']);

function localPageURL(name) {
    return localFileURL(path.join(__dirname, name));
}

function startUniversalWindow() {
    const argument = process.argv.find(value => value.startsWith('--universal-pipe=')) || '';
    const pipeName = argument.slice('--universal-pipe='.length);
    if (!/^\\\\\.\\pipe\\xwz-universal-[a-f0-9]{32}$/.test(pipeName)) return app.exit(1);
    // This local controls-only window needs no GPU. Apply the same software
    // rendering path in packaged builds and on older/remote Windows displays.
    app.disableHardwareAcceleration();
    // A fixed per-user profile makes every downloader copy share this window's lock.
    const profile = path.join(app.getPath('appData'), 'LEL-Downloader', 'universal-window');
    fs.mkdirSync(profile, {recursive: true});
    app.setPath('userData', profile);
    if (!app.requestSingleInstanceLock()) {
        const duplicate = net.createConnection(pipeName);
        let exited = false;
        const finish = code => {
            if (exited) return;
            exited = true;
            clearTimeout(timer);
            duplicate.destroy();
            app.exit(code);
        };
        const timer = setTimeout(() => finish(1), 15000);
        duplicate.on('connect', () => duplicate.write(JSON.stringify({v: 1, event: 'already-open'}) + '\n'));
        duplicate.on('error', () => finish(1));
        duplicate.on('end', () => finish(0));
        duplicate.on('close', () => finish(0));
        return;
    }
    const channel = net.createConnection(pipeName);
    const page = localPageURL('universal.html');
    let win, input = '', initialized = false, closed = false, sequence = 0, initResolve;
    let pending, completed, closing = false, shutdownTimer, exitCode = 0, certificateHandoff = false;
    let mobileAvailable = false, latestCapture;
    const readFeatures = value => {
        if (value && Array.isArray(value.resources)) {
            mobileAvailable = !value.features || value.features.mobileAccess === undefined || value.features.mobileAccess === true;
            latestCapture = value.capture;
        }
    };
    const activate = () => {
        if (closed || !win || win.isDestroyed()) return;
        if (!win.isVisible()) win.show();
        if (win.isMinimized()) win.restore();
        if (!certificateHandoff) win.focus();
    };
    app.on('second-instance', activate);
    const emit = value => { if (!closed && !closing) channel.write(JSON.stringify(Object.assign({v: 1}, value)) + '\n'); };
    const finishExit = () => {
        if (closed) return;
        closed = true;
        clearTimeout(shutdownTimer);
        if (pending) clearTimeout(pending.timer);
        channel.destroy();
        app.exit(exitCode);
    };
    const shutdown = (code = 0) => {
        exitCode = Math.max(exitCode, code);
        if (closing || closed) return;
        closing = true;
        if (pending) clearTimeout(pending.timer);
        // The Python owner closes the pipe only after stopping capture.
        if (channel.writable) channel.write(JSON.stringify({v: 1, event: 'close'}) + '\n');
        else { finishExit(); return; }
        shutdownTimer = setTimeout(finishExit, 45000);
    };
    const fail = () => shutdown(1);
    const trusted = event => win && !win.isDestroyed() && event.sender === win.webContents
        && event.sender.getURL() === page && (!event.senderFrame || (!event.senderFrame.parent && event.senderFrame.url === page));
    channel.on('error', () => { exitCode = 1; finishExit(); });
    channel.on('end', finishExit);
    channel.on('close', finishExit);
    app.on('before-quit', event => { if (!closed) { event.preventDefault(); shutdown(); } });
    channel.setEncoding('utf8');
    channel.on('data', chunk => {
        if (closing) return;
        input += chunk;
        if (input.length > 4 * 1024 * 1024) return fail();
        let newline;
        while ((newline = input.indexOf('\n')) >= 0) {
            let message;
            try { message = JSON.parse(input.slice(0, newline)); } catch (_) { return fail(); }
            input = input.slice(newline + 1);
            if (!message || message.v !== 1) return fail();
            if (message.event === 'init' && initResolve && !initialized) {
                readFeatures(message.data);
                initialized = true; initResolve(message.data); initResolve = null;
            } else if (message.event === 'response' && pending && message.id === pending.id) {
                clearTimeout(pending.timer); const request = pending; pending = null;
                let result = message.data;
                readFeatures(result);
                if (['copy_title', 'copy_domain', 'copy_link'].includes(request.action)) {
                    if (result && result.error) result = {error: result.error};
                    else if (result && typeof result.clipboardText === 'string' && result.clipboardText.length <= 16384) {
                        try { clipboard.writeText(result.clipboardText); result = {copied: true}; }
                        catch (_) { result = {error: '复制失败，请重试。'}; }
                    } else result = {error: '复制内容不可用，请重新选择资源。'};
                }
                if (['open_directory', 'open_resource_directory'].includes(request.action)) {
                    if (result && result.error) result = {error: result.error};
                    else if (result && typeof result.shellPath === 'string' && path.isAbsolute(result.shellPath)
                        && !result.shellPath.includes('\0')) {
                        try {
                            // Electron owns the foreground permission from the user's click.
                            if (request.action === 'open_resource_directory') shell.showItemInFolder(result.shellPath);
                            else if (!shell.openItem(result.shellPath)) throw new Error('Folder unavailable');
                            result = {opened: true};
                        } catch (_) { result = {error: '打开文件夹失败，请确认文件夹仍然存在。'}; }
                    } else result = {error: '文件夹不可用，请重新选择。'};
                }
                if (certificateHandoff && result && (result.working === false
                    || (['trust', 'trust_and_start'].includes(request.action) && result.error))) {
                    certificateHandoff = false;
                    activate();
                }
                if (request.waiting) completed = {action: request.action, result};
                else request.resolve(result);
            } else return fail();
        }
    });
    ipcMain.handle('universal:init', event => {
        if (!trusted(event) || initialized || initResolve) return null;
        return new Promise(resolve => { initResolve = resolve; emit({event: 'ready'}); });
    });
    ipcMain.handle('universal:request', (event, action, data) => {
        if (closing || !trusted(event) || !initialized || !ACTIONS.has(action) || !data
            || typeof data !== 'object' || Array.isArray(data) || JSON.stringify(data).length > 100000
            || (['trust', 'trust_and_start'].includes(action) && (certificateHandoff || Object.keys(data).length !== 0)))
            return {error: '操作未提交，请稍后重试。'};
        if (['start_mobile', 'stop_mobile'].includes(action) && !mobileAvailable)
            return {error: '手机接入功能已在配置中关闭。'};
        if (pending) return {waiting: true};
        if (completed) {
            if (action !== 'snapshot') return {waiting: true};
            const response = {completed}; completed = null;
            return response;
        }
        return new Promise(resolve => {
            const request = {id: ++sequence, action, resolve};
            pending = request;
            // A slow authenticated request is still in flight. Retain its ID
            // until the late reply arrives, so downloads cannot be replayed.
            request.timer = setTimeout(() => {
                if (pending === request && !closing) {
                    request.waiting = true;
                    resolve({waiting: true});
                }
            }, 20000);
            if (['trust', 'trust_and_start'].includes(action)) {
                // Bind the background proxy's native confirmation to this window.
                certificateHandoff = true;
                data = {owner_window: win.getNativeWindowHandle().readUInt32LE(0)};
            }
            emit({event: 'request', id: sequence, action, data});
        });
    });
    ipcMain.handle('universal:directory', async event => {
        if (!trusted(event)) return '';
        const result = await dialog.showOpenDialog(win, {title: '选择保存位置', properties: ['openDirectory', 'createDirectory']});
        return result.canceled ? '' : (result.filePaths[0] || '');
    });
    ipcMain.handle('universal:runtime-download', async event => {
        if (closing || !trusted(event) || !initialized) return {error: '窗口未连接，请重新进入万能下载。'};
        try {
            await shell.openExternal(DOTNET_DOWNLOAD_URL);
            return {opened: true};
        } catch (_) {
            return {error: '无法打开浏览器，请复制安装指引中的微软下载链接到浏览器打开。'};
        }
    });
    ipcMain.handle('universal:browser', async event => {
        if (closing || !trusted(event) || !initialized) return {error: '窗口未连接，请重新进入万能下载。'};
        return openCaptureBrowser(latestCapture, app.getPath('appData'));
    });
    ipcMain.on('universal:alive', event => { if (trusted(event) && initialized) emit({event: 'heartbeat'}); });
    ipcMain.on('universal:close', event => { if (trusted(event)) win.close(); });
    app.allowRendererProcessReuse = true;
    app.whenReady().then(async () => {
        if (powerMonitor) powerMonitor.on('resume', () => {
            if (initialized) emit({event: 'network-resume'});
        });
        const isolated = session.fromPartition('universal-' + process.pid);
        isolated.setPermissionRequestHandler((contents, permission, callback) => callback(false));
        if (isolated.setPermissionCheckHandler) isolated.setPermissionCheckHandler(() => false);
        const allowed = new Set(['universal.html', 'universal.css', 'universal-renderer.js', 'universal-icons.js', 'duanshu_qr.js', 'xuewuzhi.png']
            .map(localPageURL));
        isolated.webRequest.onBeforeRequest((details, callback) => callback({cancel: !allowed.has(details.url)}));
        const area = screen.getPrimaryDisplay().workAreaSize;
        win = new BrowserWindow({title: '万能下载模式', icon: path.join(__dirname, 'xuewuzhi.png'),
            width: Math.min(area.width, 1140), height: Math.min(area.height, 780),
            minWidth: Math.min(area.width, 400), minHeight: Math.min(area.height, 520),
            center: true, show: false, autoHideMenuBar: true, backgroundColor: '#f6f7f9',
            webPreferences: {session: isolated, preload: path.join(__dirname, 'universal-preload.js'),
                sandbox: true, contextIsolation: true, nodeIntegration: false, nodeIntegrationInWorker: false,
                nodeIntegrationInSubFrames: false, enableRemoteModule: false, webviewTag: false,
                webSecurity: true, devTools: false, backgroundThrottling: false},
        });
        win.setMenu(null);
        for (const event of ['will-navigate', 'will-redirect', 'new-window', 'will-attach-webview'])
            win.webContents.on(event, e => e.preventDefault());
        if (win.webContents.setWindowOpenHandler) win.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
        win.webContents.on('crashed', fail);
        win.webContents.on('render-process-gone', fail);
        win.webContents.on('did-fail-load', (event, code, text, url, main) => { if (main !== false && code !== -3) fail(); });
        win.once('ready-to-show', activate);
        win.on('close', event => { if (!closed) { event.preventDefault(); shutdown(); } });
        await win.loadURL(page);
    }).catch(fail);
}
module.exports = {startUniversalWindow};

const {app, BrowserWindow, session, Menu, screen, ipcMain} = require("electron");
// Apply before Chromium creates any network context, including login partitions.
app.commandLine.appendSwitch('no-proxy-server');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const https = require('https');
const os = require('os');
const path = require('path');
const {localFileURL} = require('./local-file-url');
const childProcess = require('child_process');
const mddclassDevice = require('./mddclass_device_id');
const {createYuyouLoginProbe} = require('./yuyou_login');
const trySaveYuyouLogin = createYuyouLoginProbe({isWindowAlive, getSafeWindowUrl, saveLoginCookieValue});
const {createPukewxLoginProbe} = require('./pukewx_login');
const trySavePukewxLogin = createPukewxLoginProbe({isWindowAlive, getSafeWindowUrl, saveLoginCookieValue});
const {attachYikaobangLogin} = require('./yikaobang_login');
let yikaobang_login_success = false;
// 打包后 argv: [login-mooc.exe, cookies_file, login_name]
// 开发模式 argv: [electron.exe, '.', cookies_file, login_name]
const app_arg_anchor = process.argv.slice(1).findIndex((arg) => arg === '.');
const TESTING = app_arg_anchor !== -1;
const app_arg_base_index = TESTING ? (app_arg_anchor + 2) : 1;

function getAppArg(offset) {
    return process.argv[app_arg_base_index + offset];
}

function hasXuetianLoginCookie(cookies) {
    return (cookies || []).some(cookie => {
        const domain = String(cookie.domain || '').replace(/^\./, '').toLowerCase();
        if (cookie.name !== 'xtp_V2.1_userInfo' || !cookie.value ||
            !['xuetian.cn', 'www.xuetian.cn'].includes(domain) ||
            (cookie.expirationDate && cookie.expirationDate <= Date.now() / 1000)) {
            return false;
        }
        let value = cookie.value;
        for (let index = 0; index < 5; index++) {
            if (value && typeof value === 'object') {
                return typeof value.userToken === 'string' && !!value.userToken.trim();
            }
            try {
                value = JSON.parse(value);
            } catch (_) {
                try {
                    const decoded = decodeURIComponent(value);
                    if (decoded === value) return false;
                    value = decoded;
                } catch (_) {
                    return false;
                }
            }
        }
        return !!(value && typeof value.userToken === 'string' && value.userToken.trim());
    });
}

// console.log(process.argv);
var cookies_file = getAppArg(0);
var login_name = getAppArg(1);
var extra_arg = getAppArg(2);
const dingtalk_yunxuetang_login = login_name === 'dingtalk' && extra_arg === 'yunxuetang';
const dingtalk_yunketang_login = login_name === 'dingtalk' && extra_arg === 'yunketang';
var course_selector_window = null;
function configureDownloadDirectoryRuntime() {
    if (login_name !== 'course_selector') return;
    try {
        const job = JSON.parse(fs.readFileSync(String(extra_arg || ''), 'utf8'));
        if (job.schema_version !== 1 || job.stage !== 'download_directory') return;
        const workspace = path.dirname(path.resolve(extra_arg));
        const profile = path.join(workspace, 'browser');
        fs.mkdirSync(profile, {recursive: true});
        app.setPath('userData', profile);
        app.setPath('temp', workspace);
    } catch (error) {
        // The window reports invalid jobs; other login profiles remain untouched.
    }
}
configureDownloadDirectoryRuntime();
if (login_name == 'course_selector') {
    // The selector is a local form. Avoid GPU initialization/driver failures
    // in remote desktops and older Windows machines, as in our dev launcher.
    app.disableHardwareAcceleration();
    app.allowRendererProcessReuse = true;
}
var xiaoetech_login_mode = login_name == 'xiaoetech' && String(extra_arg || 'pc').trim().toLowerCase() == 'web' ? 'web' : 'pc';
var classin_login_success = false;
var classin_login_closing = false;
var classin_webcast_save_inflight = false;
var classin_webcast_uid = 'MBzHk5p7Z';
var xinghuo_login_success = false;
var xinghuo_save_inflight = false;
var huomiao_login_success = false;
var huomiao_save_inflight = false;
var lexuepeiyou_login_success = false;
var lexuepeiyou_save_inflight = false;
var cookie_poll_timer = null;
var duanshu_wechat_login_required = false;
var duanshu_qr_ticket = '';
var duanshu_qr_shop_id = '';
var duanshu_qr_origin = '';
var duanshu_qr_poll_timer = null;
var duanshu_qr_poll_inflight = false;
var duanshu_qr_refresh_inflight = false;
var duanshu_qr_expire_at = 0;
var duanshu_qr_finished = false;
var duanshu_qr_win = null;
var duanshu_qr_generation = 0;
var gaodoudou_edge_process = null;
var gaodoudou_edge_poll_timer = null;
var gaodoudou_edge_profile_dir = '';
var gaodoudou_edge_saved = false;
var gaodoudou_edge_host_window = null;
var aishangke_login_inflight = false;
var aishangke_last_submit_seq = 0;
var dongao_save_inflight = false;
var dongao_save_timer = null;
var dongao_save_delay_ms = 0;
var dongao_pending_cookie_entry = null;
var dongao_bootstrap_timer = null;
var dongao_bootstrap_inflight = false;
var dongao_bootstrap_last_at = 0;
var dongao_bootstrap_last_from_url = '';
var dongao_dynamic_user_agent = '';
const DEFAULT_BROWSER_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36';
const MISON_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';
const BENZHIXT_SCRIPT_URL_PATTERN = 'https://pc.benzhixt.com/pc/assets/*.js';
const BENZHIXT_COMPATIBILITY_MARKER = '/* xwz-benzhixt-compat */';
const BENZHIXT_COMPATIBILITY_PREFIX = `${BENZHIXT_COMPATIBILITY_MARKER}
(function () {
    if (typeof Object.hasOwn !== 'function') {
        Object.defineProperty(Object, 'hasOwn', {
            configurable: true,
            writable: true,
            value: function (object, property) {
                return Object.prototype.hasOwnProperty.call(Object(object), property);
            },
        });
    }
    if (typeof Array.prototype.at !== 'function') {
        Object.defineProperty(Array.prototype, 'at', {
            configurable: true,
            writable: true,
            value: function (index) {
                var length = this == null ? 0 : this.length >>> 0;
                var relative = Number(index) || 0;
                relative = relative < 0 ? Math.ceil(relative) : Math.floor(relative);
                if (relative < 0) {
                    relative += length;
                }
                return relative >= 0 && relative < length ? this[relative] : undefined;
            },
        });
    }
})();
`;
const MISON_LOGIN_STATE_URL = 'https://www.mison.cn/e/member/login/loginjs.php';
const MISON_LOGIN_REFERER = 'https://www.mison.cn/';
const XUEXI1998_COURSE_LIST_URL = 'https://www.service.1998xuexi.com/source-gateway/store-web-new/studyPage/getMyCourseV2.action';
const XUEXI1998_COOKIE_NAMES = ['userInfo', 'acw_tc', 'cdn_sec_tc', 'sl-session'];
const LOGIN_SESSION_RESET_TIMEOUT_MS = 1500;
var youzan_save_inflight = false;
var youzan_page_check_inflight = false;
var youzan_validate_inflight = false;
var duanshu_pc_detail_login = false;
var yunduan_save_inflight = false;
var ahu_save_inflight = false;
var speiyou_save_inflight = false;
var shikaobang_save_inflight = false;
var yiqikaojiaoshi_save_inflight = false;
var xiaoyuanyouke_save_inflight = false;
var yijiayk_save_inflight = false;
var todoen_save_inflight = false;
var dxy_save_inflight = false;
var mison_save_inflight = false;
var xuexi1998_save_inflight = false;
var sparke_login_success = false;
var sparke_save_inflight = false;
var sparke_rejected_token = '';
var sparke_rejected_token_at = 0;
var sparke_legacy_qr_inflight = false;
var sparke_legacy_exchange_inflight = false;
var sparke_legacy_state = '';
var sparke_legacy_terminal_id = '';
var sparke_legacy_sms_random_code = '';
var sparke_legacy_sms_phone = '';
var sparke_legacy_action_inflight = false;
var sparke_legacy_action_timer = null;
var unipus_save_inflight = false;
var sikiedu_save_inflight = false;
var zhi10_save_inflight = false;
var cnmooc_save_inflight = false;
var gradsmart_save_inflight = false;

function recordXuewuzhiLoginTiming(eventName, fields) {
    const timingPath = String(process.env.XUEWUZHI_LOGIN_TIMING_FILE || '').trim();
    if (!timingPath) {
        return;
    }
    const sample = Object.assign({
        event: String(eventName || '').slice(0, 64),
        ts_ms: Date.now(),
    }, fields || {});
    try {
        fs.appendFileSync(timingPath, JSON.stringify(sample) + '\n', {encoding: 'ascii'});
    } catch (error) {
        ;
    }
}
var benzhixt_save_inflight = false;
var smartedu_token_bootstrap_started = false;
var smartedu_login_ticket_seen = false;
var smartedu_last_bootstrap_ticket = '';
var smartedu_save_inflight = false;
var xiaoetech_pc_token_validation_inflight = false;
var xiaoetech_pc_rejected_tokens = new Map();
var speiyou_request_auth = {};
var mddclass_first_login_cookie_at = 0;
var mddclass_target_navigated = false;
var mddclass_request_context = {};
const SANJIEKE_COOKIE_NAMES = [
    'Hm_lpvt_85148c078fe4635816b80e5a36990313',
    'Hm_lvt_85148c078fe4635816b80e5a36990313',
    'HMACCOUNT',
    '__bid_n',
    '_c_WBKFRo',
    '_nb_ioWEgULi',
    '_sjk_jwt',
    'PHPSESSID',
    'sajssdk_2015_cross_new_user',
    'sensorsdata2015jssdkcross',
    'acw_tc'
];
const AISHANGKE_COOKIE_NAMES = [
    'HMACCOUNT',
    'HMACCOUNT_BFESS',
    'acw_tc',
    'PHPSESSID',
    'user_login_phone'
];
const AHU_COOKIE_NAMES = ['PHPSESSID', 'laravel_session'];
const MDDCLASS_COOKIE_NAMES = ['HJ_UID', 'HJ_SID', 'HJ_SSID_65', 'HJ_SSID_54', 'HJ_CST', 'HJ_CSST_65', 'HJ_CSST_54', 'TRACKSITEMAP', '_REF', '_SREF_65', '_SREF_54', '_REG', '_SREG_65', '_SREG_54', 'SESSION', 'ClubAuth', 'hj_token', 'access_token', 'refresh_token', 'HJUserAgent', 'acw_tc', 'cdn_sec_tc', 'hj_captcha'];
const MDDCLASS_AUTH_COOKIE_NAMES = ['ClubAuth', 'hj_token', 'access_token', 'SESSION'];
const MDDCLASS_ENV_PREFIX = login_name === 'sihaigongkao' ? 'SIHAIGONGKAO_' : 'MDDCLASS_';
const MDDCLASS_LOGIN_MODE = String(process.env[MDDCLASS_ENV_PREFIX + 'LOGIN_MODE'] || process.env[MDDCLASS_ENV_PREFIX + 'LOGIN_USE_WEB_PAGE'] || '').trim().toLowerCase();
const MDDCLASS_LOGIN_USE_WEB_PAGE = !['0', 'false', 'no', 'n', 'html', 'client', 'api', 'local'].includes(MDDCLASS_LOGIN_MODE);
const MDDCLASS_WEB_LOGIN_URL = login_name === 'sihaigongkao' ? 'https://sihaigongkao.mddclass.com/account-center/' : 'https://pass.mddclass.com/school/?business_domain=yyy_cctob&bireg=&url=https%3A%2F%2Fwww.mddclass.com%2F';
const MDDCLASS_DEFAULT_TARGET_URL = login_name === 'sihaigongkao' ? 'https://sihaigongkao.mddclass.com/account-center/' : 'https://www.mddclass.com/';
const MDDCLASS_RESTORE_STORED_COOKIES = String(process.env[MDDCLASS_ENV_PREFIX + 'RESTORE_STORED_COOKIES'] || '').trim().toLowerCase() === '1';
const HUATU_COOKIE_NAMES = [
    'ht_token_preview', 'ht_token', 'Newuc-Token', 'token', 'UserName', 'UserID', 'avatar', 'ht_id',
    'UserFace', 'UserReName', 'userCode', 'userMobile', 'ht_uname', 'ht_auth',
    'ht_qcount', 'ucId', 'htzxUps', 'accountStatus', 'synlogin', 'Operator'
];
const WANGXIAO_COOKIE_NAMES = [
    'NewPlatFormToken',
    'token',
    'userInfo',
    'UserCookieName',
    'UserCookieName_',
    'ASP.NET_SessionId',
    'uniqueVisitorId',
    'OldUsername',
    'OldUsername_',
    'OldUsername2',
    'OldUsername2_',
    'OldPassword',
    'OldPassword_',
];
const WANGXIAO233_COOKIE_NAMES = [
    '233ZhichiUUID',
    'ASP.NET_SessionId',
    'Auth',
    'AuthGuid',
    'clientauthentication',
    'clientauthenticationref',
    'fclasscname',
    'javadeviceid',
    'UserId',
    'wxuserinforset',
    'acw_tc',
    'SERVERID',
];

const CCTALK_COOKIE_NAMES = ['HJ_UID', 'HJ_SID', 'HJ_SSID_65', 'HJ_SSID_54', 'HJ_CST', 'HJ_CSST_65', 'HJ_CSST_54', 'TRACKSITEMAP', '_REF', '_SREF_65', '_SREF_54', '_REG', '_SREG_65', '_SREG_54', 'SESSION', 'ClubAuth', 'hj_token', 'access_token', 'HJUserAgent', 'acw_tc', 'cdn_sec_tc', 'hj_captcha'];
const CCTALK_AUTH_COOKIE_NAMES = ['ClubAuth', 'hj_token', 'access_token', 'SESSION'];
const CCTALK_LOGIN_USE_WEB_PAGE = true;
const TMOOC_COOKIE_DOMAIN_SUFFIX = '.tmooc.cn';
const HUATU_WINDOW_WIDTH = 800;
const HUATU_WINDOW_HEIGHT = 600;
const DONGAO_WINDOW_WIDTH = 800;
const DONGAO_WINDOW_HEIGHT = 600;
const LEDU_WINDOW_WIDTH = 390;
const LEDU_WINDOW_HEIGHT = 620;
const LEDU_WINDOW_ASPECT_RATIO = LEDU_WINDOW_WIDTH / LEDU_WINDOW_HEIGHT;
const MED66_VALIDATE_URL = 'https://member.med66.com/homes/mycourse';
const MED66_LOGIN_URL = 'https://www.med66.com/OtherItem/loginAgain/index.shtml';
const ZHENGBAO_VALIDATE_URL = 'https://member.chinaacc.com/home/';
const ZHENGBAO_LOGIN_URL = 'https://www.chinaacc.com/login/index.shtml';
const JIANSHE99_VALIDATE_URL = 'https://member.jianshe99.com/homes/mycourse';
const JIANSHE99_LOGIN_URL = 'https://www.jianshe99.com/login/index.shtml';
const DONGAO_COURSE_PROGRESS_URL = 'https://course.dongao.com/progress';
const DONGAO_LOGIN_URL = 'https://passport.dongao.com/login?redirectUrl=https%3A%2F%2Fcourse.dongao.com%2Fprogress';
const DONGAO_DEVICE_VERIFY_URL = 'https://my.dongao.com/qrcode/deviceVerify';
const DONGAO_MEMBER_EXAM_URL = 'https://serveapi.dongao.com/search/memberExamSubjectSeasonListV2';
const DONGAO_STAGE_LIST_URL = 'https://course.dongao.com/v4/liveAndCourseList';
const DONGAO_LOGIN_REDIRECT_GRACE_MS = 3500;
const DONGAO_BOOTSTRAP_REPEAT_GUARD_MS = 15000;
const CHAOGE_LOGIN_URL = 'https://chaogejiaoyu.com/user/login';
const CHAOGE_VALIDATE_URL = 'https://chaogejiaoyu.com/user/index/getLoginUserInfo';
const CHAOGE_COOKIE_NAMES = [
    'PHPSESSID',
    'user_exam_type',
    'user_login_phone',
    'Hm_lpvt_53a19e72d4c14094478abf3d7f96e512',
    'Hm_lvt_53a19e72d4c14094478abf3d7f96e512',
    'HMACCOUNT',
    '_csslcloud_fix',
];
const SHANXIANG_LOGIN_URL = 'https://www.sx1211.com/account/login.html';
const SHANXIANG_VALIDATE_URL = 'https://www.sx1211.com/user/course.html';
const SHIKAOBANG_LOGIN_URL = 'https://www.shikaobang.cn';
const SHIKAOBANG_VALIDATE_URL = 'https://www.shikaobang.cn/wp/course/detail?no=c6&brand=skb&province=zhejiang';
const YIJIAYK_LOGIN_URL = 'https://h.yijiayk.com/myCenter';
const YIJIAYK_VALIDATE_URL = 'https://m.yijiayk.com/user-api/app/user/getUserInfo';
const YIQIKAOJIAOSHI_LOGIN_URL = 'https://www.17kjs.com/';
const YIQIKAOJIAOSHI_VALIDATE_URL = 'https://www.17kjs.com/user/course.html';
const TODOEN_GT_SECRET_URL = 'https://www.todoen.com/ompScript/app/pc_api/get_gt_secret';
const FENBI_LOGIN_URL = 'https://www.fenbi.com/';
const FENBI_VALIDATE_URL = 'https://login.fenbi.com/api/users/current';
const HOUDA_LOGIN_URL = 'http://www.houdask.com';
const LEXUEYUN_LOGIN_URL = 'https://my.lexue-cloud.com/home';
const HOUDA_VALIDATE_URL = 'http://www.houdask.com/api/center/sysUserPower/anon/ifLogin';
const HOUDA_COOKIE_NAMES = [
    'houdatoken',
    'hd.token',
    'deviceId',
    'Hm_lpvt_025656ffc846b7a1beef6de5f4d07596',
    'Hm_lvt_025656ffc846b7a1beef6de5f4d07596',
    'HMACCOUNT',
    'looyu_id',
    'looyu_20000845',
];
const FENBI_COOKIE_NAMES = [
    'sess',
    'sid',
    'userid',
    'persistent',
    'device_id',
    'acw_tc',
];
const XIAOYUANYOUKE_COOKIE_NAMES = [
    'sid',
    'sess',
    'userid',
    'persistent',
    'device_id',
    'JSESSIONID',
    '__sub_user_infos__',
    'g_loc',
    'g_sess',
    'acw_tc',
];
const XIAOYUANYOUKE_LOGIN_VARIANT = String(extra_arg || '').trim().toLowerCase();
const XIAOYUANYOUKE_IS_COLLIE = XIAOYUANYOUKE_LOGIN_VARIANT === 'collie';
const XIAOYUANYOUKE_PRODUCT_ID = XIAOYUANYOUKE_IS_COLLIE ? '28000006' : '37000005';
const XIAOYUANYOUKE_VERSION = XIAOYUANYOUKE_IS_COLLIE ? '3.30.0' : '2.22.0';
const XIAOYUANYOUKE_CLIENT_NAME = XIAOYUANYOUKE_IS_COLLIE ? 'collie' : 'husky';
const XIAOYUANYOUKE_LOGIN_URL = localFileURL(path.join(app.getAppPath(), 'xiaoyuanyouke-login.html'))
    + (XIAOYUANYOUKE_IS_COLLIE ? '?variant=collie' : '');
const XIAOYUANYOUKE_HOME_URL = 'https://www.yuanfudao.com/';
const XIAOYUANYOUKE_PRODUCT_LIST_URL = 'https://www.yuanfudao.com/tutor-student-episode/win/v2/products';
const XIAOYUANYOUKE_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) tutor-electron-' + XIAOYUANYOUKE_CLIENT_NAME + '/' + XIAOYUANYOUKE_VERSION + ' Chrome/85.0.4183.121 Electron/10.1.5 Safari/537.36';
const XIAOYUANYOUKE_COMMON_PARAMS = {
    YFD_U: 'undefined',
    _productId: XIAOYUANYOUKE_PRODUCT_ID,
    _hostProductId: XIAOYUANYOUKE_PRODUCT_ID,
    version: XIAOYUANYOUKE_VERSION,
    hostVersion: XIAOYUANYOUKE_VERSION,
    platform: 'win_10.0.26200',
    userType: 'student',
    model: 'undefined',
};
const SHIKAOBANG_COOKIE_NAMES = [
    'user_infor',
    'web_user_token',
    'PHPSESSID',
    'brand',
    'skb_province',
    'skb_exam',
    'skb_tagtype',
    'skb_tagitemkey',
    'skb_tagrelationid',
    'Hm_lvt_9dd4fc5ab97a169d88a49dbf0c5e7d35',
    'Hm_lpvt_9dd4fc5ab97a169d88a49dbf0c5e7d35',
    'HMACCOUNT',
    'acw_tc',
];
const YIQIKAOJIAOSHI_COOKIE_NAMES = [
    'PHPSESSID',
    'YQ_CLIENT_UUID',
    'Hm_lvt_6d8609ec7d90e812cabfe095b34f9601',
    'Hm_lpvt_6d8609ec7d90e812cabfe095b34f9601',
    'HMACCOUNT',
    'acw_tc',
];
const UNIPUS_LOGIN_URL = 'https://sso.unipus.cn/sso/gl/login?service=https%3A%2F%2Fmoocs.unipus.cn%2Flogin%2Fcas%2Fcallback%3Fgoto%3D%252Fmy%252Fcourses%252Flearning';
const UNIPUS_VALIDATE_URL = 'https://moocs.unipus.cn/my/courses/learning';
const SIKIEDU_LOGIN_URL = 'https://www.sikiedu.com/login';
const SIKIEDU_VALIDATE_URL = 'https://www.sikiedu.com/my/courses/learning';
const ZHI10_LOGIN_URL = 'https://www.zhi10.com/login?goto=/my/courses/learning';
const ZHI10_VALIDATE_URL = 'https://www.zhi10.com/my/courses/learning';
const CNMOOC_VALIDATE_URL = 'https://cnmooc.sjtu.cn/portal/myCourseIndex/1.mooc';
const CHINESEMOOC_LOGIN_URL = 'https://www.chinesemooc.org/web/login.php';
const GRADSMART_ORIGIN = 'https://www.gradsmartedu.cn';
const GRADSMART_LOGIN_CHECK_URL = GRADSMART_ORIGIN + '/api/v1/u/login/check_is_l/';
const SMARTEDU_LOGIN_URL = 'https://auth.smartedu.cn/uias/login';
const SMARTEDU_BACK_URL = 'https://basic.smartedu.cn/';
const LIZHIWEIKE_WEB_LOGIN_URL = 'https://open.lizhiweike.com/oauth3/authorize?client_id=weike-html5-frontend&response_type=w_code&redirect_uri=https%3A%2F%2Fm1.lizhiweike.com%2Findexpage';
const LIZHIWEIKE_MINIPROGRAM_LOGIN_URL = 'https://web.lizhiweike.com/login';
const LIZHIWEIKE_MINIPROGRAM_COURSE_LIST_URL = 'https://web.lizhiweike.com/course/list';
const CAIXUETANG_AGENT_URL = 'https://service.agent.pro.caixuetang.cn';
const CAIXUETANG_APP_CODE = '5ecbbee7c8259jmj7etln6jf';
const CAIXUETANG_USER_INFO_URL = CAIXUETANG_AGENT_URL + '?c=user&a=memberinfo&v=user&site=user&serviceversion=v1';
const CAIXUETANG_MY_COURSE_URL = CAIXUETANG_AGENT_URL + '?c=Webmembercourse&a=mycourse&v=user&site=course&serviceversion=v3610';
const CAIXUETANG_MY_VIP_COURSE_URL = CAIXUETANG_AGENT_URL + '?c=Webmembercourse&a=myvipcourse&v=user&site=course&serviceversion=v3610';
const LUFFYCITY_API_BASE = 'https://api.luffycity.com/api/v1';
const MAGEDU_VALIDATE_URL = 'https://edu.magedu.com/v1/api/ke/user/simpleInfo';
const SPARKE_API_BASE = 'https://api2.sparke.cn';
const SPARKE_PROFILE_URL = SPARKE_API_BASE + '/user/profile';
const SPARKE_APP_ID = '210951669544977408';
const SPARKE_API_VERSION = '1.0.0';
const SPARKE_TERMINAL_TYPE = '3';
const SPARKE_WEB_GATEWAY = 'https://gateway.sparke.cn';
const SPARKE_WEB_APP_ID = '20016182957411972207';
const SPARKE_WEB_AUTHORIZATION = 'Basic MjAwMTYxODI5NTc0MTE5NzIyMDc6c3BhcmtwYw==';
var huatu_save_inflight = false;
var tmooc_save_inflight = false;
var ckjr_auth_records = [];
var ckjr_save_inflight = false;
var ledu_last_debug_snapshot = '';
var ledu_save_inflight = false;
var lexueyun_save_inflight = false;
var ledu_debug_file = login_name == 'ledu'
    ? path.join(path.dirname(cookies_file), 'ledu_login_debug.json')
    : '';
const LEDU_LOGIN_AES_KEY = '2hCTPP7do9o84yxx';
const LEDU_LOGIN_AES_IV = 'Omev83GjCjyrJWMJ';
const LEDU_PC_LOGIN_HOST = 'https://course-api-online.saasp.vdyoo.com';
const LEDU_PC_STU_TOKEN_LOGIN_URL = LEDU_PC_LOGIN_HOST + '/passport/v1/login/stu-token-login';
const LEDU_PC_COURSE_LIST_URL = LEDU_PC_LOGIN_HOST + '/course/v1/student/course/list';
const LEDU_PC_CLIENT_ID = '523601';
const LEDU_PC_TERMINAL = 'pc';
const LEDU_PC_PRODUCT = 'ss';
const LEDU_PC_VERSION = '3.56.0.1520';
const LEDU_PC_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36';
const SPEIYOU_PC_LOGIN_HOST = 'https://course-api-online.speiyou.com';
const SPEIYOU_PC_STUDENT_CODE_LOGIN_URL = SPEIYOU_PC_LOGIN_HOST + '/passport/v1/login/student/code';
const SPEIYOU_PC_SUBJECT_LIST_URL = SPEIYOU_PC_LOGIN_HOST + '/course/v1/student/course/subject-list';
const SPEIYOU_PC_VERSION = '3.60.0.2368';
const SPEIYOU_PC_RES_VERSION = '1.0.6';
const SPEIYOU_PC_USER_AGENT = DEFAULT_BROWSER_USER_AGENT;
const SPEIYOU_PC_CLIENT_ID = '123601';
const SPEIYOU_PC_TERMINAL = 'pc';
const SPEIYOU_PC_PRODUCT = 'ss';

function isObjectDestroyedError(error) {
    const message = String(
        (error && (error.message || error.stack))
        || error
        || ''
    ).toLowerCase();
    return message.includes('object has been destroyed');
}

function getSafeWebContents(win) {
    try {
        if (!win || win.isDestroyed() || !win.webContents || win.webContents.isDestroyed()) {
            return null;
        }
        return win.webContents;
    } catch (error) {
        return null;
    }
}

function isWindowAlive(win) {
    return !!getSafeWebContents(win);
}

function isBenzhixtScriptUrl(url) {
    return /^https:\/\/pc\.benzhixt\.com\/pc\/assets\/[^?#]+\.js(?:\?|#|$)/i.test(
        String(url || '')
    );
}

function transformBenzhixtScript(source) {
    source = String(source || '');
    if (source.indexOf(BENZHIXT_COMPATIBILITY_MARKER) !== -1) {
        return source;
    }
    const needs_compatibility = /\|\|=|&&=|\?\?=|Object\.hasOwn|\.at\(/.test(source);
    if (!needs_compatibility) {
        return source;
    }
    const transformed = source.replace(
        /([A-Za-z_$][\w$]*(?:(?:\.[A-Za-z_$][\w$]*)|(?:\[[^\]]+\]))*)\s*(\|\|=|&&=|\?\?=)/g,
        (match, left, operator) => left + ' = ' + left + ' ' + operator.slice(0, -1) + ' '
    );
    return BENZHIXT_COMPATIBILITY_PREFIX + transformed;
}

function installBenzhixtCompatibility(win, {
    scriptPattern = BENZHIXT_SCRIPT_URL_PATTERN,
    isScriptUrl = isBenzhixtScriptUrl,
    transformScript = transformBenzhixtScript,
} = {}) {
    const debugger_client = win && win.webContents && win.webContents.debugger;
    if (!debugger_client || typeof debugger_client.sendCommand !== 'function') {
        return Promise.resolve(false);
    }
    let attached_here = false;
    try {
        if (!debugger_client.isAttached()) {
            debugger_client.attach('1.3');
            attached_here = true;
        }
    } catch (error) {
        return Promise.resolve(false);
    }

    let fetch_enabled = false;
    let disposed = false;
    const continue_request = (request_id) => debugger_client.sendCommand(
        'Fetch.continueRequest',
        {requestId: request_id},
    ).catch(() => {});
    const on_message = (event, method, params) => {
        if (disposed || method !== 'Fetch.requestPaused' || !params || !params.requestId) {
            return;
        }
        const request_id = params.requestId;
        Promise.resolve().then(async () => {
            const request_url = String(params.request && params.request.url || '');
            const status_code = Number(params.responseStatusCode || 0);
            if (!isScriptUrl(request_url) || status_code < 200 || status_code >= 300) {
                await continue_request(request_id);
                return;
            }
            let response;
            try {
                response = await debugger_client.sendCommand('Fetch.getResponseBody', {requestId: request_id});
            } catch (error) {
                await continue_request(request_id);
                return;
            }
            const body = Buffer.from(
                String(response && response.body || ''),
                response && response.base64Encoded ? 'base64' : 'utf8',
            ).toString('utf8');
            const transformed = transformScript(body);
            if (transformed === body) {
                await continue_request(request_id);
                return;
            }
            const response_headers = (params.responseHeaders || []).filter((header) => {
                const name = String(header && header.name || '').toLowerCase();
                return name !== 'content-encoding' && name !== 'content-length';
            });
            await debugger_client.sendCommand('Fetch.fulfillRequest', {
                requestId: request_id,
                responseCode: status_code || 200,
                responseHeaders: response_headers,
                body: Buffer.from(transformed, 'utf8').toString('base64'),
            });
        }).catch(() => continue_request(request_id));
    };
    debugger_client.on('message', on_message);

    const cleanup = () => {
        if (disposed) {
            return;
        }
        disposed = true;
        debugger_client.removeListener('message', on_message);
        if (fetch_enabled) {
            debugger_client.sendCommand('Fetch.disable').catch(() => {});
        }
        if (attached_here) {
            try {
                if (debugger_client.isAttached()) {
                    debugger_client.detach();
                }
            } catch (error) {
                ;
            }
        }
    };
    if (win && typeof win.once === 'function') {
        win.once('closed', cleanup);
    }
    return debugger_client.sendCommand('Fetch.enable', {
        patterns: [{urlPattern: scriptPattern, requestStage: 'Response'}],
    }).then(() => {
        fetch_enabled = true;
        return true;
    }).catch(() => {
        cleanup();
        return false;
    });
}

function getSafeWindowUrl(win, fallback = '') {
    const contents = getSafeWebContents(win);
    if (!contents) {
        return String(fallback || '');
    }
    try {
        return String(contents.getURL() || '').trim() || String(fallback || '');
    } catch (error) {
        return String(fallback || '');
    }
}

process.on('uncaughtException', (error) => {
    if (isObjectDestroyedError(error)) {
        return;
    }
    process.stderr.write(String(error && error.stack || error) + '\n');
    app.exit(1);
});

process.on('unhandledRejection', (error) => {
    if (isObjectDestroyedError(error)) {
        return;
    }
    process.stderr.write(String(error && error.stack || error) + '\n');
    app.exit(1);
});

function buildCookieMap(cookies) {
    let cookie_map = {};
    (cookies || []).forEach((cookie) => {
        if (!cookie || !cookie.name) {
            return;
        }
        cookie_map[String(cookie.name)] = cookie.value === undefined || cookie.value === null
            ? ''
            : String(cookie.value);
    });
    return cookie_map;
}

function filterGaodoudouCookies(cookies) {
    const include_names = ['acw_tc', 'ptxkhzyapp', 'ptxkhzyappUserId'];
    return (cookies || []).filter((cookie) => (
        cookie
        && normalizeCookieDomain(cookie.domain) === 'gdd.aixuexi.com'
        && include_names.includes(String(cookie.name || '').trim())
        && cookie.value !== undefined
        && cookie.value !== null
        && String(cookie.value) !== ''
    ));
}

function hasGaodoudouLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterGaodoudouCookies(cookies));
    return !!(cookie_map.ptxkhzyapp && cookie_map.ptxkhzyappUserId);
}

function gaodoudouBrowserCandidates(env = process.env, platform = process.platform) {
    env = env || {};
    if (platform === 'win32') {
        const roots = [
            env['PROGRAMFILES(X86)'],
            env['ProgramFiles(x86)'],
            env.ProgramFiles,
            env.LOCALAPPDATA,
        ].filter(Boolean);
        const relative_paths = [
            ['Microsoft', 'Edge', 'Application', 'msedge.exe'],
            ['Google', 'Chrome', 'Application', 'chrome.exe'],
        ];
        const result = [];
        roots.forEach((root) => {
            relative_paths.forEach((parts) => {
                const candidate = path.join(root, ...parts);
                if (!result.includes(candidate)) {
                    result.push(candidate);
                }
            });
        });
        // Electron's packaged environment can omit one or more Windows
        // program-directory variables. Keep the standard install locations
        // as a final fallback so login does not fail before the popup opens.
        [
            'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
            'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
            'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        ].forEach((candidate) => {
            if (!result.includes(candidate)) {
                result.push(candidate);
            }
        });
        return result;
    }
    if (platform === 'darwin') {
        return [
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        ];
    }
    return [
        '/usr/bin/microsoft-edge',
        '/usr/bin/microsoft-edge-stable',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium',
    ];
}

function findGaodoudouBrowserExecutable(env = process.env, platform = process.platform) {
    return gaodoudouBrowserCandidates(env, platform).find((candidate) => {
        try {
            return fs.statSync(candidate).isFile();
        } catch (error) {
            return false;
        }
    }) || '';
}

function encodeGaodoudouWebSocketFrame(value, opcode = 1) {
    const body = Buffer.isBuffer(value) ? value : Buffer.from(String(value || ''), 'utf8');
    const mask = crypto.randomBytes(4);
    let header = null;
    if (body.length < 126) {
        header = Buffer.alloc(2);
        header[1] = 0x80 | body.length;
    } else if (body.length <= 0xffff) {
        header = Buffer.alloc(4);
        header[1] = 0x80 | 126;
        header.writeUInt16BE(body.length, 2);
    } else {
        header = Buffer.alloc(10);
        header[1] = 0x80 | 127;
        header.writeUInt32BE(0, 2);
        header.writeUInt32BE(body.length, 6);
    }
    header[0] = 0x80 | (opcode & 0x0f);
    const masked = Buffer.alloc(body.length);
    for (let index = 0; index < body.length; index += 1) {
        masked[index] = body[index] ^ mask[index % 4];
    }
    return Buffer.concat([header, mask, masked]);
}

function createGaodoudouCdpWebSocket(socket, initial_data = null) {
    let next_id = 0;
    let response_buffer = Buffer.alloc(0);
    let fragmented_opcode = 0;
    let fragmented_parts = [];
    let closed = false;
    const pending = new Map();
    const close_handlers = [];

    const close = (error) => {
        if (closed) {
            return;
        }
        closed = true;
        const reason = error instanceof Error
            ? error
            : new Error('browser debugging connection closed');
        pending.forEach((entry) => {
            clearTimeout(entry.timer);
            entry.reject(reason);
        });
        pending.clear();
        close_handlers.splice(0).forEach((handler) => {
            try {
                handler(reason);
            } catch (handler_error) {
                ;
            }
        });
    };

    const dispatch_message = (payload) => {
        let message = null;
        try {
            message = JSON.parse(payload.toString('utf8'));
        } catch (error) {
            return;
        }
        if (!message || !message.id || !pending.has(message.id)) {
            return;
        }
        const entry = pending.get(message.id);
        pending.delete(message.id);
        clearTimeout(entry.timer);
        if (message.error) {
            entry.reject(new Error(String(message.error.message || 'browser command failed')));
        } else {
            entry.resolve(message.result || {});
        }
    };

    const consume = (chunk) => {
        response_buffer = Buffer.concat([response_buffer, Buffer.from(chunk)]);
        while (true) {
            if (response_buffer.length < 2) {
                break;
            }
            const first = response_buffer[0];
            const second = response_buffer[1];
            const final_frame = !!(first & 0x80);
            const opcode = first & 0x0f;
            const masked = !!(second & 0x80);
            let payload_length = second & 0x7f;
            let offset = 2;
            if (payload_length === 126) {
                if (response_buffer.length < 4) {
                    break;
                }
                payload_length = response_buffer.readUInt16BE(2);
                offset = 4;
            } else if (payload_length === 127) {
                if (response_buffer.length < 10) {
                    break;
                }
                const high = response_buffer.readUInt32BE(2);
                if (high !== 0) {
                    close(new Error('browser response is too large'));
                    socket.destroy();
                    return;
                }
                payload_length = response_buffer.readUInt32BE(6);
                offset = 10;
            }
            const mask_length = masked ? 4 : 0;
            if (response_buffer.length < offset + mask_length + payload_length) {
                break;
            }
            let payload = response_buffer.slice(
                offset + mask_length,
                offset + mask_length + payload_length,
            );
            if (masked) {
                const mask = response_buffer.slice(offset, offset + 4);
                const unmasked = Buffer.alloc(payload.length);
                for (let index = 0; index < payload.length; index += 1) {
                    unmasked[index] = payload[index] ^ mask[index % 4];
                }
                payload = unmasked;
            }
            response_buffer = response_buffer.slice(offset + mask_length + payload_length);
            if (opcode === 8) {
                close(new Error('browser window closed'));
                socket.end();
                return;
            }
            if (opcode === 9) {
                socket.write(encodeGaodoudouWebSocketFrame(payload, 10));
                continue;
            }
            if (opcode === 10) {
                continue;
            }
            if (opcode === 1 || opcode === 2) {
                fragmented_opcode = opcode;
                fragmented_parts = [payload];
            } else if (opcode === 0 && fragmented_opcode) {
                fragmented_parts.push(payload);
            } else {
                continue;
            }
            if (final_frame) {
                const complete = Buffer.concat(fragmented_parts);
                const complete_opcode = fragmented_opcode;
                fragmented_opcode = 0;
                fragmented_parts = [];
                if (complete_opcode === 1) {
                    dispatch_message(complete);
                }
            }
        }
    };

    socket.on('data', consume);
    socket.on('error', close);
    socket.on('close', close);
    if (initial_data && initial_data.length) {
        consume(initial_data);
    }

    return {
        request(method, params = {}, timeout_ms = 5000) {
            if (closed || !socket.writable) {
                return Promise.reject(new Error('browser debugging connection is closed'));
            }
            const id = ++next_id;
            return new Promise((resolve, reject) => {
                const timer = setTimeout(() => {
                    pending.delete(id);
                    reject(new Error('browser command timed out'));
                }, Math.max(500, Number(timeout_ms) || 5000));
                pending.set(id, {resolve, reject, timer});
                const payload = encodeGaodoudouWebSocketFrame(
                    JSON.stringify({id, method, params}),
                );
                socket.write(payload, (error) => {
                    if (!error || !pending.has(id)) {
                        return;
                    }
                    const entry = pending.get(id);
                    pending.delete(id);
                    clearTimeout(entry.timer);
                    entry.reject(error);
                });
            });
        },
        onClose(handler) {
            if (typeof handler === 'function') {
                close_handlers.push(handler);
            }
        },
        close() {
            close();
            try {
                socket.end(encodeGaodoudouWebSocketFrame(Buffer.alloc(0), 8));
            } catch (error) {
                ;
            }
        },
    };
}

function connectGaodoudouCdpWebSocket(websocket_url, timeout_ms = 5000) {
    return new Promise((resolve, reject) => {
        let target = null;
        try {
            target = new URL(String(websocket_url || ''));
        } catch (error) {
            reject(new Error('invalid browser debugging address'));
            return;
        }
        if (
            target.protocol !== 'ws:'
            || !['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname)
        ) {
            reject(new Error('browser debugging address must be local'));
            return;
        }
        const websocket_key = crypto.randomBytes(16).toString('base64');
        const expected_accept = crypto.createHash('sha1').update(
            websocket_key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11',
        ).digest('base64');
        let settled = false;
        let timer = null;
        const finish = (error, value) => {
            if (settled) {
                return;
            }
            settled = true;
            clearTimeout(timer);
            if (error) {
                reject(error);
            } else {
                resolve(value);
            }
        };
        const request = http.request({
            hostname: target.hostname === '[::1]' ? '::1' : target.hostname,
            port: target.port,
            path: target.pathname + target.search,
            headers: {
                'Connection': 'Upgrade',
                'Upgrade': 'websocket',
                'Sec-WebSocket-Key': websocket_key,
                'Sec-WebSocket-Version': '13',
            },
        });
        timer = setTimeout(() => {
            request.destroy();
            finish(new Error('browser debugging connection timed out'));
        }, Math.max(1000, Number(timeout_ms) || 5000));
        request.once('upgrade', (response, socket, head) => {
            const accept = String(response.headers['sec-websocket-accept'] || '');
            if (response.statusCode !== 101 || accept !== expected_accept) {
                socket.destroy();
                finish(new Error('browser debugging handshake failed'));
                return;
            }
            finish(null, createGaodoudouCdpWebSocket(socket, head));
        });
        request.once('response', (response) => {
            response.resume();
            finish(new Error('browser debugging upgrade was rejected'));
        });
        request.once('error', (error) => finish(error));
        request.end();
    });
}

function readGaodoudouDevToolsEndpoint(profile_dir) {
    if (!isGaodoudouTempProfileDir(profile_dir)) {
        return '';
    }
    const endpoint_file = path.join(profile_dir, 'DevToolsActivePort');
    let lines = [];
    try {
        lines = String(fs.readFileSync(endpoint_file, 'utf8') || '').trim().split(/\r?\n/);
    } catch (error) {
        return '';
    }
    const port = Number(lines[0]);
    const websocket_path = String(lines[1] || '').trim();
    if (
        !Number.isInteger(port)
        || port < 1
        || port > 65535
        || !/^\/devtools\/browser\/[A-Za-z0-9_-]+$/.test(websocket_path)
    ) {
        return '';
    }
    return 'ws://127.0.0.1:' + port + websocket_path;
}

function isGaodoudouTempProfileDir(profile_dir) {
    const target = path.resolve(String(profile_dir || ''));
    const temp_root = path.resolve(os.tmpdir());
    return !!target
        && target !== temp_root
        && target.startsWith(temp_root + path.sep)
        && path.basename(target).startsWith('lel-gaodoudou-');
}

function removeGaodoudouTempProfile() {
    const profile_dir = gaodoudou_edge_profile_dir;
    if (!isGaodoudouTempProfileDir(profile_dir) || !fs.existsSync(profile_dir)) {
        gaodoudou_edge_profile_dir = '';
        return true;
    }
    try {
        if (typeof fs.rmSync === 'function') {
            fs.rmSync(profile_dir, {recursive: true, force: true});
        } else {
            fs.rmdirSync(profile_dir, {recursive: true});
        }
        gaodoudou_edge_profile_dir = '';
        return true;
    } catch (error) {
        return false;
    }
}

function createGaodoudouEdgeLogin() {
    // Keep one invisible Electron window alive while the actual login UI is
    // hosted by Edge/Chrome.  On some Electron builds, an app with no
    // BrowserWindow exits before the external browser and CDP poller finish
    // starting, even when window-all-closed is handled.
    try {
        gaodoudou_edge_host_window = new BrowserWindow({
            show: false,
            width: 1,
            height: 1,
            webPreferences: {
                nodeIntegration: false,
                contextIsolation: true,
            },
        });
    } catch (error) {
        gaodoudou_edge_host_window = null;
    }
    const browser_path = findGaodoudouBrowserExecutable();
    if (!browser_path) {
        const {dialog} = require('electron');
        dialog.showErrorBox(
            '高豆豆登录失败',
            '未找到可用的 Microsoft Edge 或 Google Chrome，请安装或更新浏览器后重试。',
        );
        app.exit(1);
        return;
    }

    try {
        gaodoudou_edge_profile_dir = fs.mkdtempSync(
            path.join(os.tmpdir(), 'lel-gaodoudou-'),
        );
    } catch (error) {
        app.exit(1);
        return;
    }

    const browser_args = [
        '--no-proxy-server',
        '--remote-debugging-port=0',
        '--remote-debugging-address=127.0.0.1',
        '--user-data-dir=' + gaodoudou_edge_profile_dir,
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-mode',
        '--disable-features=msEdgeFirstRunExperience',
            '--app=' + login_url,
    ];
    try {
        gaodoudou_edge_process = childProcess.spawn(browser_path, browser_args, {
            windowsHide: false,
            detached: true,
            stdio: 'ignore',
        });
        gaodoudou_edge_process.unref();
    } catch (error) {
        removeGaodoudouTempProfile();
        app.exit(1);
        return;
    }

    let cdp = null;
    let connect_inflight = false;
    let scan_inflight = false;
    let closing = false;
    let endpoint_poll_timer = null;
    const exit_after_cleanup = (exit_code, attempt = 0) => {
        if (removeGaodoudouTempProfile() || attempt >= 12) {
            app.exit(exit_code);
            return;
        }
        setTimeout(() => exit_after_cleanup(exit_code, attempt + 1), 250);
    };
    const close_browser = (exit_code) => {
        if (closing) {
            return;
        }
        closing = true;
        if (endpoint_poll_timer) {
            clearInterval(endpoint_poll_timer);
            endpoint_poll_timer = null;
        }
        if (gaodoudou_edge_poll_timer) {
            clearInterval(gaodoudou_edge_poll_timer);
            gaodoudou_edge_poll_timer = null;
        }
        if (cdp) {
            cdp.request('Browser.close', {}, 1500).catch(() => {});
        }
        if (gaodoudou_edge_host_window && !gaodoudou_edge_host_window.isDestroyed()) {
            try {
                gaodoudou_edge_host_window.close();
            } catch (error) {
                ;
            }
        }
        gaodoudou_edge_host_window = null;
        setTimeout(() => {
            if (gaodoudou_edge_process && !gaodoudou_edge_process.killed) {
                try {
                    gaodoudou_edge_process.kill();
                } catch (error) {
                    ;
                }
            }
            gaodoudou_edge_process = null;
            exit_after_cleanup(exit_code);
        }, 1500);
    };

    const start_time = Date.now();
    const connect_to_browser = () => {
        if (closing || cdp || connect_inflight) {
            return;
        }
        const endpoint = readGaodoudouDevToolsEndpoint(gaodoudou_edge_profile_dir);
        if (!endpoint) {
            if (Date.now() - start_time > 20000) {
                const {dialog} = require('electron');
                dialog.showErrorBox(
                    '高豆豆登录失败',
                    '浏览器未能启动高豆豆登录页，请更新 Microsoft Edge 或 Google Chrome 后重试。',
                );
                close_browser(1);
            }
            return;
        }
        connect_inflight = true;
        connectGaodoudouCdpWebSocket(endpoint, 5000).then((client) => {
            if (closing) {
                client.close();
                return;
            }
            cdp = client;
            if (endpoint_poll_timer) {
                clearInterval(endpoint_poll_timer);
                endpoint_poll_timer = null;
            }
            cdp.onClose(() => close_browser(gaodoudou_edge_saved ? 0 : 2));
            scan_cookies();
            gaodoudou_edge_poll_timer = setInterval(scan_cookies, 800);
        }).catch(() => {
            if (Date.now() - start_time > 20000) {
                close_browser(1);
            }
        }).finally(() => {
            connect_inflight = false;
        });
    };
    const scan_cookies = () => {
        if (!cdp || scan_inflight || closing) {
            return;
        }
        scan_inflight = true;
        cdp.request('Storage.getCookies', {}, 4000).then((result) => {
            const scoped_cookies = filterGaodoudouCookies(result.cookies || []);
            if (!hasGaodoudouLoginCookies(scoped_cookies)) {
                return;
            }
            const saved = saveGaodoudouCookieValue(
                buildCookieValue(scoped_cookies),
            );
            if (saved) {
                gaodoudou_edge_saved = true;
                close_browser(0);
            }
        }).catch(() => {}).finally(() => {
            scan_inflight = false;
        });
    };
    gaodoudou_edge_process.once('error', () => close_browser(1));
    endpoint_poll_timer = setInterval(connect_to_browser, 200);
    connect_to_browser();
}

function isCaixuetangCookie(cookie) {
    if (!cookie || !cookie.name || cookie.value === undefined || cookie.value === null || String(cookie.value) === '') {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    return domain === 'caixuetang.cn' || domain.endsWith('.caixuetang.cn');
}

function filterCaixuetangCookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isCaixuetangCookie(cookie)) {
            return;
        }
        const key = [
            String(cookie.name || ''),
            normalizeCookieDomain(cookie.domain || cookie.host_key || ''),
            String(cookie.path || '/')
        ].join('|');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function isJingtongxueCookie(cookie) {
    if (!cookie || !cookie.name || cookie.value === undefined || cookie.value === null || String(cookie.value) === '') {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    return domain === 'jingtongxue.com' || domain.endsWith('.jingtongxue.com');
}

function filterJingtongxueCookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isJingtongxueCookie(cookie)) {
            return;
        }
        const key = [
            String(cookie.name || ''),
            normalizeCookieDomain(cookie.domain || cookie.host_key || ''),
            String(cookie.path || '/')
        ].join('|');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function hasJingtongxueLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterJingtongxueCookies(cookies));
    return !!((cookie_map.token || cookie_map.up_token) && (cookie_map.userInfo || cookie_map.cookie_user_));
}

function isJingtongxueLoginPageUrl(url) {
    const text = String(url || '').toLowerCase();
    return text.includes('/join/login')
        || text.includes('popwin=login')
        || text.includes('/loginpage')
        || /[?#&]login(?:[=&]|$)/.test(text);
}

function decodeJingtongxueLoginCodeToken(url) {
    const raw_url = String(url || '');
    let code = '';
    try {
        const parsed = new URL(raw_url);
        code = parsed.searchParams.get('code') || '';
        if (!code && parsed.hash) {
            const hash_text = parsed.hash.charAt(0) === '#' ? parsed.hash.slice(1) : parsed.hash;
            const hash_query = hash_text.includes('?') ? hash_text.slice(hash_text.indexOf('?') + 1) : '';
            code = new URLSearchParams(hash_query).get('code') || '';
        }
    } catch (error) {
        ;
    }
    if (!code) {
        return '';
    }
    try {
        let encoded = String(code).trim().replace(/-/g, '+').replace(/_/g, '/');
        while (encoded.length % 4 !== 0) {
            encoded += '=';
        }
        const decoded = Buffer.from(encoded, 'base64').toString('utf8');
        const payload = JSON.parse(decoded);
        return String(payload && payload.token || '').trim();
    } catch (error) {
        return '';
    }
}

function readJingtongxueLoginState(win) {
    if (login_name !== 'jingtongxue' || !isWindowAlive(win)) {
        return Promise.resolve({});
    }
    return win.webContents.executeJavaScript(`
        (function () {
            function safeGet(storage, key) {
                try {
                    return storage && storage.getItem ? (storage.getItem(key) || '') : '';
                } catch (error) {
                    return '';
                }
            }
            function dumpStorage(storage) {
                var result = {};
                try {
                    if (!storage) {
                        return result;
                    }
                    for (var i = 0; i < storage.length; i++) {
                        var key = storage.key(i);
                        if (key) {
                            result[key] = storage.getItem(key);
                        }
                    }
                } catch (error) {
                    ;
                }
                return result;
            }
            var localData = dumpStorage(window.localStorage);
            var sessionData = dumpStorage(window.sessionStorage);
            var href = window.location.href || '';
            return {
                href: href,
                cookie: document.cookie || '',
                token: safeGet(window.localStorage, 'token') || safeGet(window.sessionStorage, 'token') || safeGet(window.localStorage, 'up_token') || safeGet(window.sessionStorage, 'up_token'),
                userInfo: safeGet(window.localStorage, 'userInfo') || safeGet(window.sessionStorage, 'userInfo'),
                companyId: safeGet(window.localStorage, 'companyId') || safeGet(window.sessionStorage, 'companyId'),
                userId: safeGet(window.localStorage, 'userId') || safeGet(window.sessionStorage, 'userId'),
                localStorage: localData,
                sessionStorage: sessionData,
            };
        })();
    `, true).catch(() => ({}));
}

function isMageduCookie(cookie) {
    if (!cookie || !cookie.name || cookie.value === undefined || cookie.value === null || String(cookie.value) === '') {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    return domain === 'edu.magedu.com' || domain.endsWith('.edu.magedu.com') || domain === 'magedu.com' || domain.endsWith('.magedu.com');
}

function filterMageduCookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isMageduCookie(cookie)) {
            return;
        }
        const key = [
            String(cookie.name || ''),
            normalizeCookieDomain(cookie.domain || cookie.host_key || ''),
            String(cookie.path || '/')
        ].join('|');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function hasMageduLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterMageduCookies(cookies));
    return !!(cookie_map.gupao_edu_college_token);
}

function fetchFormUrl(target_url, form_data = {}, extra_headers = null) {
    return new Promise((resolve) => {
        let settled = false;
        function finish(result) {
            if (!settled) {
                settled = true;
                resolve(result);
            }
        }
        try {
            const parsed = new URL(target_url);
            const body = new URLSearchParams();
            Object.keys(form_data || {}).forEach((key) => {
                const value = form_data[key];
                if (value !== undefined && value !== null) {
                    body.append(key, String(value));
                }
            });
            const body_text = body.toString();
            const request_headers = Object.assign({
                'User-Agent': DEFAULT_BROWSER_USER_AGENT,
                'Accept': 'application/json, text/plain, */*',
                'Accept-Encoding': 'identity',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Content-Length': Buffer.byteLength(body_text),
            }, extra_headers || {});
            const client = parsed.protocol === 'http:' ? http : https;
            const request = client.request({
                protocol: parsed.protocol,
                hostname: parsed.hostname,
                port: parsed.port || undefined,
                path: parsed.pathname + parsed.search,
                method: 'POST',
                headers: request_headers,
            }, (response) => {
                let response_body = '';
                response.setEncoding('utf8');
                response.on('data', (chunk) => {
                    if (response_body.length < 262144) {
                        response_body += chunk;
                    }
                });
                response.on('end', () => {
                    finish({
                        statusCode: Number(response.statusCode || 0),
                        url: target_url,
                        body: response_body,
                    });
                });
            });
            request.on('error', () => {
                finish(null);
            });
            request.setTimeout(8000, () => {
                request.destroy();
                finish(null);
            });
            request.write(body_text);
            request.end();
        } catch (error) {
            finish(null);
        }
    });
}

function readMageduLoginState(win) {
    if (login_name !== 'magedu' || !isWindowAlive(win)) {
        return Promise.resolve({});
    }
    return win.webContents.executeJavaScript(`
        (() => {
            function dumpStorage(storage) {
                const result = {};
                if (!storage) {
                    return result;
                }
                for (let i = 0; i < storage.length; i++) {
                    const key = storage.key(i);
                    if (key) {
                        result[key] = storage.getItem(key);
                    }
                }
                return result;
            }
            function readValue(storage, names) {
                if (!storage) {
                    return '';
                }
                for (const name of names) {
                    const value = storage.getItem(name);
                    if (value) {
                        return String(value);
                    }
                }
                for (let i = 0; i < storage.length; i++) {
                    const key = storage.key(i);
                    const lower = String(key || '').toLowerCase();
                    if (lower.includes('gupao') && lower.includes('token')) {
                        const value = storage.getItem(key);
                        if (value) {
                            return String(value);
                        }
                    }
                }
                return '';
            }
            const tokenNames = ['gupao_edu_college_token', 'token', 'accessToken'];
            return {
                href: window.location.href || '',
                cookie: document.cookie || '',
                token: readValue(localStorage, tokenNames) || readValue(sessionStorage, tokenNames),
                localStorage: dumpStorage(localStorage),
                sessionStorage: dumpStorage(sessionStorage),
            };
        })();
    `, true).catch(() => ({}));
}

function looksLikeMageduLoginInfo(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    try {
        const info = JSON.parse(String(result.body || '{}'));
        const data = info && info.data;
        return !!(
            data
            && typeof data === 'object'
            && (String(info.code) === '0' || String(info.code) === '200' || info.success === true)
        );
    } catch (error) {
        return false;
    }
}

function validateMageduCookieValue(cookie_value, token) {
    if (!cookie_value || !token) {
        return Promise.resolve(false);
    }
    return fetchUrlWithMergedCookieValue(MAGEDU_VALIDATE_URL, cookie_value, 0, {
        'Referer': 'https://edu.magedu.com/person/home/0/course',
        'Origin': 'https://edu.magedu.com',
        'Accept': 'application/json, text/plain, */*',
        'token': token,
    })
        .then((result) => looksLikeMageduLoginInfo(result))
        .catch(() => false);
}

function trySaveMageduLoginResult(win, fallback_cookies = null) {
    if (login_name !== 'magedu' || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    const finish = (cookies) => {
        const magedu_cookies = filterMageduCookies(cookies || []);
        const cookie_value = buildCookieValue(magedu_cookies);
        return readMageduLoginState(win).then((state) => {
            state = state && typeof state === 'object' ? state : {};
            const storage = Object.assign({}, state.localStorage || {}, state.sessionStorage || {});
            const cookie_map = Object.assign(
                {},
                parseCookieString(state.cookie || cookie_value),
                buildCookieMap(magedu_cookies)
            );
            const token = String(
                state.token
                || storage.gupao_edu_college_token
                || storage.token
                || cookie_map.gupao_edu_college_token
                || ''
            ).trim();
            if (!token) {
                return false;
            }
            cookie_map.gupao_edu_college_token = token;
            const payload_cookie = buildCookieValueFromMap(cookie_map);
            return validateMageduCookieValue(payload_cookie, token).then((valid) => {
                if (!valid) {
                    return false;
                }
                const payload = {
                    cookie: payload_cookie,
                    cookieValue: payload_cookie,
                    cookies: cookie_map,
                    cookieList: magedu_cookies,
                    gupao_edu_college_token: token,
                    token: token,
                    localStorage: state.localStorage || {},
                    sessionStorage: state.sessionStorage || {},
                };
                saveLoginCookieData(JSON.stringify(payload));
                return true;
            });
        });
    };
    if (fallback_cookies && fallback_cookies.length) {
        return finish(fallback_cookies);
    }
    return win.webContents.session.cookies.get({ domain: "edu.magedu.com" })
        .then(finish)
        .catch(() => false);
}

function trySaveJingtongxueLoginResult(win, fallback_cookies = null) {
    if (login_name !== 'jingtongxue' || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    const finish = (cookies) => {
        const jingtong_cookies = filterJingtongxueCookies(cookies || []);
        return readJingtongxueLoginState(win).then((state) => {
            state = state && typeof state === 'object' ? state : {};
            if (isJingtongxueLoginPageUrl(state.href || getSafeWindowUrl(win))) {
                return false;
            }
            const storage_cookies = parseCookieString(state.cookie || '');
            const cookie_map = Object.assign({}, storage_cookies, buildCookieMap(jingtong_cookies));
            const code_token = decodeJingtongxueLoginCodeToken(state.href || getSafeWindowUrl(win));
            const token = String(code_token || state.token || cookie_map.token || cookie_map.up_token || '').trim();
            const user_info = String(state.userInfo || cookie_map.userInfo || cookie_map.cookie_user_ || '').trim();
            if (!token || !user_info) {
                return false;
            }
            cookie_map.token = token;
            cookie_map.up_token = token;
            if (state.userInfo) {
                cookie_map.userInfo = String(state.userInfo);
            }
            if (state.companyId) {
                cookie_map.companyId = String(state.companyId);
            }
            if (state.userId) {
                cookie_map.userId = String(state.userId);
            }
            const cookie_value = buildCookieValueFromMap(cookie_map);
            const payload = Object.assign({}, state, {
                token: token,
                userInfo: user_info,
                up_token: cookie_map.up_token || '',
                cookie_user_: cookie_map.cookie_user_ || '',
                companyId: state.companyId || cookie_map.companyId || '',
                userId: state.userId || cookie_map.userId || '',
                cookie: cookie_value,
                cookieValue: cookie_value,
                cookies: cookie_map,
                cookieList: jingtong_cookies,
                savedAt: Date.now(),
            });
            saveLoginCookieData(JSON.stringify(payload));
            return true;
        });
    };
    if (fallback_cookies && fallback_cookies.length) {
        return finish(fallback_cookies);
    }
    return win.webContents.session.cookies.get({})
        .then(finish)
        .catch(() => false);
}

function parseCookieString(cookie_string) {
    let cookie_map = {};
    String(cookie_string || '').split(';').forEach((item) => {
        item = String(item || '').trim();
        if (!item) {
            return;
        }
        const equal_index = item.indexOf('=');
        if (equal_index <= 0) {
            return;
        }
        const name = item.slice(0, equal_index).trim();
        const value = item.slice(equal_index + 1).trim();
        if (name) {
            cookie_map[name] = value;
        }
    });
    return cookie_map;
}

function hasSanjiekeLoginCookies(cookies) {
    let cookie_map = buildCookieMap(cookies);
    return !!(cookie_map._sjk_jwt && cookie_map.PHPSESSID);
}

function hasAishangkeLoginCookies(cookies) {
    let cookie_map = buildCookieMap(cookies);
    return !!cookie_map.PHPSESSID;
}

function hasDingtalkLoginCookies(cookies) {
    let cookie_map = buildCookieMap(cookies);
    return !!(cookie_map.account && cookie_map.deviceid);
}

function isGradsmartCookie(cookie) {
    if (!cookie || !cookie.name || cookie.value === undefined || cookie.value === null || String(cookie.value) === '') {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    return !domain || domain === 'gradsmartedu.cn' || domain.endsWith('.gradsmartedu.cn');
}

function filterGradsmartCookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isGradsmartCookie(cookie)) {
            return;
        }
        const key = String(cookie.name || '');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function looksLikeGradsmartLoggedIn(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    try {
        const info = JSON.parse(String(result.body || '{}'));
        return !!(info && info.data && info.data.is_login === true);
    } catch (error) {
        return false;
    }
}

function validateGradsmartCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithMergedCookieValue(GRADSMART_LOGIN_CHECK_URL, cookie_value, 0, {
        'Referer': GRADSMART_ORIGIN + '/',
        'Origin': GRADSMART_ORIGIN,
        'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest',
    })
        .then((result) => ({
            valid: looksLikeGradsmartLoggedIn(result),
            cookieValue: result && result.cookieValue || cookie_value,
        }))
        .catch(() => ({ valid: false, cookieValue: cookie_value }));
}

function trySaveGradsmartCookies(cookies) {
    if (gradsmart_save_inflight) {
        return Promise.resolve(false);
    }
    const gradsmart_cookies = filterGradsmartCookies(cookies);
    const cookie_value = buildCookieValue(gradsmart_cookies);
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    gradsmart_save_inflight = true;
    return validateGradsmartCookieValue(cookie_value).then((result) => {
        if (!result || !result.valid) {
            gradsmart_save_inflight = false;
            return false;
        }
        saveLoginCookieValue(result.cookieValue || cookie_value);
        return true;
    }).catch(() => {
        gradsmart_save_inflight = false;
        return false;
    });
}

function isCctalkCookie(cookie) {
    if (!cookie || !cookie.name || cookie.value === undefined || cookie.value === null || String(cookie.value) === '') {
        return false;
    }
    const name = String(cookie.name);
    if (!CCTALK_COOKIE_NAMES.includes(name)) {
        return false;
    }
    const domain = String(cookie.domain || cookie.host_key || '').toLowerCase();
    if (!domain) {
        return true;
    }
    return domain.includes('cctalk.com') || domain.includes('cctalk.net') || domain.includes('hujiang.com');
}

function filterCctalkCookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isCctalkCookie(cookie)) {
            return;
        }
        const key = String(cookie.name || '');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function normalizeCctalkDeviceId(value) {
    const match = String(value || '').trim().match(/[\{(]?([0-9a-fA-F]{8})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{4})-?([0-9a-fA-F]{12})[\})]?/);
    if (!match) {
        return '';
    }
    return '{' + match.slice(1).join('-') + '}';
}

function extractCctalkDeviceIdFromText(text) {
    text = String(text || '');
    if (!text) {
        return '';
    }
    const guid_source = '[\\{(]?[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}[\\})]?';
    const patterns = [
        new RegExp('HJClient[^\\r\\n]{0,240}/qt/?(' + guid_source + ')', 'i'),
        new RegExp('HJUserAgent[^\\r\\n]{0,320}/qt/?(' + guid_source + ')', 'i'),
        new RegExp('(?:tracertNo|TracetNo|deviceId|clientDeviceId)[^\\r\\n]{0,200}(?:%7B|%7b)?(' + guid_source + ')', 'i'),
        new RegExp('(' + guid_source + ')[^\\r\\n]{0,200}(?:tracertNo|TracetNo|deviceId|clientDeviceId)', 'i'),
    ];
    for (const pattern of patterns) {
        const match = pattern.exec(text);
        if (match) {
            const device_id = normalizeCctalkDeviceId(match[1]);
            if (device_id) {
                return device_id;
            }
        }
    }
    return '';
}

function readCctalkClientDeviceId() {
    const local_appdata = process.env.LOCALAPPDATA || '';
    if (!local_appdata) {
        return '';
    }
    const cache_dir = path.join(local_appdata, 'CCtalk', 'WebEngine', 'Cache');
    let entries = [];
    try {
        entries = fs.readdirSync(cache_dir, { withFileTypes: true });
    } catch (error) {
        return '';
    }
    let total_bytes = 0;
    for (const entry of entries) {
        if (!entry || !entry.isFile || !entry.isFile()) {
            continue;
        }
        if (!/^data_\d+$/i.test(entry.name) && !/^f_\d+$/i.test(entry.name) && entry.name !== 'index') {
            continue;
        }
        const file_path = path.join(cache_dir, entry.name);
        let stat = null;
        try {
            stat = fs.statSync(file_path);
        } catch (error) {
            continue;
        }
        if (!stat || stat.size <= 0 || stat.size > 64 * 1024 * 1024 || total_bytes + stat.size > 128 * 1024 * 1024) {
            continue;
        }
        try {
            const text = fs.readFileSync(file_path).toString('latin1');
            total_bytes += stat.size;
            const device_id = extractCctalkDeviceIdFromText(text);
            if (device_id) {
                return device_id;
            }
        } catch (error) {
            ;
        }
    }
    return '';
}

function cctalkClientUserAgent(device_id, existing_user_agent = '') {
    const match = String(existing_user_agent || '').match(/HJClient\s+1\.0\/pc\/([^/]+)\//i);
    const os_version = match ? match[1] : '6.2.9200';
    return 'HJClient 1.0/pc/' + os_version + '/7.10.17.3/qt/' + device_id;
}

function sanitizeCctalkCookiesForSave(cookies) {
    const filtered = filterCctalkCookies(cookies);
    const device_id = readCctalkClientDeviceId();
    const result = [];
    let saw_hj_user_agent = false;
    filtered.forEach((cookie) => {
        if (!cookie || String(cookie.name || '') !== 'HJUserAgent') {
            result.push(cookie);
            return;
        }
        saw_hj_user_agent = true;
        if (device_id) {
            result.push(Object.assign({}, cookie, { value: cctalkClientUserAgent(device_id, cookie.value) }));
        }
    });
    if (device_id && !saw_hj_user_agent) {
        result.push({ name: 'HJUserAgent', value: cctalkClientUserAgent(device_id) });
    }
    return result;
}

function hasCctalkLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterCctalkCookies(cookies));
    if (CCTALK_LOGIN_USE_WEB_PAGE) {
        return !!(cookie_map.ClubAuth || cookie_map.hj_token || cookie_map.access_token);
    }
    return CCTALK_AUTH_COOKIE_NAMES.some((name) => !!cookie_map[name]);
}

function trySaveCctalkCookies(cookies) {
    const filtered_cookies = sanitizeCctalkCookiesForSave(cookies);
    if (!hasCctalkLoginCookies(filtered_cookies)) {
        return false;
    }
    const cookie_value = buildCookieValue(filtered_cookies);
    if (!cookie_value) {
        return false;
    }
    saveLoginCookieValue(cookie_value);
    return true;
}

function trySaveCctalkLoginResult(win, fallback_cookies = null, allow_cookie_fallback = false) {
    if (login_name !== 'cctalk' || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    if (CCTALK_LOGIN_USE_WEB_PAGE) {
        return Promise.resolve(!!(fallback_cookies && trySaveCctalkCookies(fallback_cookies)));
    }
    return win.webContents.executeJavaScript('window.__CCTALK_LOGIN_RESULT__', true)
    .then((result) => {
        if (result && result.success && result.cookieValue) {
            saveLoginCookieValue(result.cookieValue);
            return true;
        }
        if (allow_cookie_fallback && fallback_cookies && trySaveCctalkCookies(fallback_cookies)) {
            return true;
        }
        return false;
    }).catch(() => {
        if (allow_cookie_fallback && fallback_cookies && trySaveCctalkCookies(fallback_cookies)) {
            return true;
        }
        return false;
    });
}

function trySaveCctalkLoginResultFromUrl(target_url) {
    if (login_name !== 'cctalk' || CCTALK_LOGIN_USE_WEB_PAGE || !target_url) {
        return false;
    }
    const marker = 'cctalk_login_result=';
    const pos = String(target_url).indexOf(marker);
    if (pos < 0) {
        return false;
    }
    try {
        const encoded = String(target_url).slice(pos + marker.length).split('&')[0];
        const result = JSON.parse(decodeURIComponent(encoded));
        if (result && result.success && result.cookieValue) {
            saveLoginCookieValue(result.cookieValue);
            return true;
        }
    } catch (error) {
        ;
    }
    return false;
}

function trySaveCaixuetangLoginResult(win, fallback_cookies = null) {
    if (login_name !== 'caixuetang' || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return win.webContents.executeJavaScript(`
        (function () {
            function safeGet(storage, key) {
                try {
                    return storage && storage.getItem ? storage.getItem(key) : '';
                } catch (error) {
                    return '';
                }
            }
            function dumpStorage(storage) {
                var out = {};
                try {
                    if (!storage) {
                        return out;
                    }
                    for (var i = 0; i < storage.length; i++) {
                        var key = storage.key(i);
                        out[key] = storage.getItem(key);
                    }
                } catch (error) {
                    ;
                }
                return out;
            }
            return {
                token: safeGet(window.localStorage, 'TOKEN') || safeGet(window.sessionStorage, 'TOKEN'),
                member_id: safeGet(window.localStorage, 'MEMBER_ID') || safeGet(window.sessionStorage, 'MEMBER_ID'),
                localStorage: dumpStorage(window.localStorage),
                sessionStorage: dumpStorage(window.sessionStorage),
                href: location.href,
            };
        })();
    `, true).then((result) => {
        const token = String(result && result.token || '').trim();
        const member_id = String(result && result.member_id || '').trim();
        if (!token || !member_id) {
            return false;
        }
        const caixuetang_cookies = filterCaixuetangCookies(fallback_cookies || []);
        const cookie_value = buildCookieValue(caixuetang_cookies);
        const payload = Object.assign({}, result || {}, {
            token: token,
            member_id: member_id,
            cookie: cookie_value,
            cookieValue: cookie_value,
            cookies: buildCookieMap(caixuetang_cookies),
            cookieList: caixuetang_cookies,
            savedAt: Date.now(),
        });
        return validateCaixuetangLoginPayload(payload).then((valid) => {
            if (!valid) {
                return false;
            }
            saveLoginCookieData(JSON.stringify(payload));
            return true;
        });
    }).catch(() => false);
}

function looksLikeCaixuetangLoginInfo(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    try {
        const info = JSON.parse(String(result.body || '{}'));
        const code = String(info.code || info.errcode || '');
        return !!(
            (code === '1' || code === '0' || info.status === 1 || info.status === '1' || info.status === true)
            && info.data
        );
    } catch (error) {
        return false;
    }
}

function validateCaixuetangLoginPayload(payload) {
    const token = String(payload && payload.token || '').trim();
    const member_id = String(payload && payload.member_id || payload && payload.memberId || '').trim();
    if (!token || !member_id) {
        return Promise.resolve(false);
    }
    const cookie_value = String(payload.cookie || payload.cookieValue || '').trim();
    const headers = {
        'Cookie': cookie_value,
        'Referer': 'https://www.caixuetang.cn/',
        'Origin': 'https://www.caixuetang.cn',
        'Accept': 'application/json, text/plain, */*',
    };
    const base_form = {
        client_type: 'pc',
        member_id: member_id,
        key: token,
        appcode: CAIXUETANG_APP_CODE,
    };
    return fetchFormUrl(
        CAIXUETANG_USER_INFO_URL,
        Object.assign({}, base_form, { id: member_id }),
        headers
    ).then((result) => {
        if (looksLikeCaixuetangLoginInfo(result)) {
            return true;
        }
        return fetchFormUrl(CAIXUETANG_MY_COURSE_URL, base_form, headers)
            .then((course_result) => {
                if (looksLikeCaixuetangLoginInfo(course_result)) {
                    return true;
                }
                return fetchFormUrl(CAIXUETANG_MY_VIP_COURSE_URL, base_form, headers)
                    .then((vip_result) => looksLikeCaixuetangLoginInfo(vip_result));
            });
    }).catch(() => false);
}

function clickCaixuetangLoginButton(win, delay_ms = 0) {
    if (login_name !== 'caixuetang' || !isWindowAlive(win)) {
        return;
    }
    setTimeout(() => {
        if (!isWindowAlive(win)) {
            return;
        }
        win.webContents.executeJavaScript(`
            (function () {
                function textOf(el) {
                    try {
                        return String((el && (el.innerText || el.textContent)) || '').replace(/\\s+/g, '');
                    } catch (error) {
                        return '';
                    }
                }
                function markerOf(el) {
                    if (!el) {
                        return '';
                    }
                    var attrText = '';
                    try {
                        attrText = [
                            el.getAttribute && el.getAttribute('role'),
                            el.getAttribute && el.getAttribute('aria-label'),
                            el.getAttribute && el.getAttribute('title'),
                            el.getAttribute && el.getAttribute('placeholder')
                        ].join(' ');
                    } catch (error) {
                        ;
                    }
                    return String((el.id || '') + ' ' + (el.className || '') + ' ' + attrText).toLowerCase();
                }
                function isVisible(el) {
                    if (!el) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0) {
                        return false;
                    }
                    var rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }
                function hasLoginForm() {
                    return !!document.querySelector('input[type="password"], input[placeholder*="密码"], input[placeholder*="验证码"], input[placeholder*="手机号"], input[placeholder*="手机"], input[placeholder*="账号"]');
                }
                function hasLoginToken() {
                    try {
                        return !!(localStorage.getItem('TOKEN') || sessionStorage.getItem('TOKEN'));
                    } catch (error) {
                        return false;
                    }
                }
                function clickNode(el) {
                    if (!el || !isVisible(el)) {
                        return false;
                    }
                    try {
                        el.scrollIntoView({ block: 'center', inline: 'center' });
                    } catch (error) {
                        ;
                    }
                    try {
                        el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    } catch (error) {
                        ;
                    }
                    try {
                        el.click();
                    } catch (error) {
                        ;
                    }
                    return true;
                }
                function clickableOf(el) {
                    if (!el) {
                        return null;
                    }
                    var selectors = 'button,a,[role="button"],[onclick],[class*="login"],[class*="Login"],[class*="user"],[class*="User"],[class*="btn"],[class*="Btn"]';
                    var node = el;
                    for (var i = 0; node && i < 4; i++, node = node.parentElement) {
                        if (node.matches && node.matches(selectors) && isVisible(node)) {
                            return node;
                        }
                    }
                    return el;
                }
                function scoreCandidate(el) {
                    if (!isVisible(el)) {
                        return -1;
                    }
                    var text = textOf(el);
                    var marker = markerOf(el);
                    if (text.indexOf('退出登录') >= 0 || text.indexOf('已登录') >= 0) {
                        return -1;
                    }
                    var hasLoginText = text === '登录' || text === '立即登录' || text === '登录/注册' || text === '登录注册' || text.indexOf('登录') >= 0 || text.indexOf('登陆') >= 0;
                    var hasLoginMarker = /login|signin|user-login|loginbtn|login-btn/.test(marker);
                    if (!hasLoginText && !hasLoginMarker) {
                        return -1;
                    }
                    if (hasLoginText && text.length > 16 && text.indexOf('登录') > 8) {
                        return -1;
                    }
                    var rect = el.getBoundingClientRect();
                    var score = 0;
                    if (hasLoginText) {
                        score += 20;
                    }
                    if (hasLoginMarker) {
                        score += 8;
                    }
                    if (rect.top >= 0 && rect.top < Math.max(180, window.innerHeight * 0.25)) {
                        score += 12;
                    }
                    if (rect.left > window.innerWidth * 0.45) {
                        score += 10;
                    }
                    if (el.matches && el.matches('button,a,[role="button"]')) {
                        score += 6;
                    }
                    return score;
                }
                if (hasLoginToken() || hasLoginForm()) {
                    return false;
                }
                var roots = Array.prototype.slice.call(document.querySelectorAll('header,.header,.top,.nav,.navbar,.layout-header,.pc-header,#app,body'));
                if (!roots.length) {
                    roots = [document.body || document.documentElement];
                }
                var nodes = [];
                roots.forEach(function (root) {
                    if (!root || !root.querySelectorAll) {
                        return;
                    }
                    nodes = nodes.concat(Array.prototype.slice.call(root.querySelectorAll('button,a,div,span,li,p,[role="button"],[onclick]')));
                });
                var seen = [];
                var candidates = [];
                nodes.forEach(function (node) {
                    var target = clickableOf(node);
                    if (!target || seen.indexOf(target) >= 0) {
                        return;
                    }
                    seen.push(target);
                    var score = scoreCandidate(target);
                    if (score >= 0) {
                        candidates.push({ node: target, score: score });
                    }
                });
                candidates.sort(function (a, b) { return b.score - a.score; });
                if (!candidates.length) {
                    return false;
                }
                return clickNode(candidates[0].node);
            })();
        `, true).catch(() => {
            ;
        });
    }, delay_ms);
}

function isLuffycityCookie(cookie) {
    if (!cookie || !cookie.name || cookie.value === undefined || cookie.value === null || String(cookie.value) === '') {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    return domain === 'luffycity.com' || domain.endsWith('.luffycity.com');
}

function filterLuffycityCookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isLuffycityCookie(cookie)) {
            return;
        }
        const key = [
            String(cookie.name || ''),
            normalizeCookieDomain(cookie.domain || cookie.host_key || ''),
            String(cookie.path || '/')
        ].join('|');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function normalizeLuffycityWebUrl(url) {
    const text = String(url || '').trim();
    if (!text) {
        return '';
    }
    try {
        const parsed = new URL(text);
        if (parsed.hostname.toLowerCase() === 'm.luffycity.com') {
            parsed.hostname = 'www.luffycity.com';
            return parsed.toString();
        }
    } catch (error) {
        ;
    }
    return text;
}

function installLuffycityDesktopUrlGuard(login_session) {
    if (!login_session || !login_session.webRequest || login_session.__LEL_LUFFYCITY_DESKTOP_URL_GUARD__) {
        return;
    }
    login_session.__LEL_LUFFYCITY_DESKTOP_URL_GUARD__ = true;
    login_session.webRequest.onBeforeRequest(
        {urls: ['*://m.luffycity.com/*']},
        (details, callback) => {
            const redirect_url = normalizeLuffycityWebUrl(details.url);
            if (redirect_url && redirect_url !== details.url) {
                callback({redirectURL: redirect_url});
                return;
            }
            callback({});
        }
    );
}

function trySaveLuffycityLoginResult(win, fallback_cookies = null) {
    if (login_name !== 'luffycity' || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return win.webContents.executeJavaScript(`
        (function () {
            function safeGet(storage, key) {
                try {
                    return storage && storage.getItem ? storage.getItem(key) : '';
                } catch (error) {
                    return '';
                }
            }
            function dumpStorage(storage) {
                var out = {};
                try {
                    if (!storage) {
                        return out;
                    }
                    for (var i = 0; i < storage.length; i++) {
                        var key = storage.key(i);
                        out[key] = storage.getItem(key);
                    }
                } catch (error) {
                    ;
                }
                return out;
            }
            return {
                auth_type: safeGet(window.localStorage, 'luffy-client-auth-type') || safeGet(window.sessionStorage, 'luffy-client-auth-type') || 'Token',
                key: safeGet(window.localStorage, 'luffy-client-key') || safeGet(window.sessionStorage, 'luffy-client-key') || '',
                token: safeGet(window.localStorage, 'luffy-client-key') || safeGet(window.sessionStorage, 'luffy-client-key') || '',
                cookie: document.cookie || '',
                localStorage: dumpStorage(window.localStorage),
                sessionStorage: dumpStorage(window.sessionStorage),
                href: location.href,
            };
        })();
    `, true).then((result) => {
        const key = String(result && result.key || '').trim();
        if (!key) {
            return false;
        }
        const luffycity_cookies = filterLuffycityCookies(fallback_cookies || []);
        const cookie_value = buildCookieValue(luffycity_cookies) || String(result && result.cookie || '').trim();
        const payload = Object.assign({}, result || {}, {
            key: key,
            token: key,
            auth_type: String(result && result.auth_type || 'Token').trim() || 'Token',
            cookie: cookie_value,
            cookieValue: cookie_value,
            cookies: buildCookieMap(luffycity_cookies),
            cookieList: luffycity_cookies,
            savedAt: Date.now(),
        });
        return validateLuffycityLoginPayload(payload).then((valid) => {
            if (!valid) {
                return false;
            }
            saveLoginPayload(payload);
            return true;
        });
    }).catch(() => false);
}

function looksLikeLuffycityLoginInfo(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    try {
        const info = JSON.parse(String(result.body || '{}'));
        return !!(info && String(info.code) !== '401');
    } catch (error) {
        return false;
    }
}

function validateLuffycityLoginPayload(payload) {
    const key = String(payload && (payload.key || payload.token) || '').trim();
    if (!key) {
        return Promise.resolve(false);
    }
    const auth_type = String(payload.auth_type || payload.authType || 'Token').trim() || 'Token';
    const cookie_value = String(payload.cookie || payload.cookieValue || '').trim();
    const headers = {
        'Cookie': cookie_value,
        'Authorization': auth_type + ' ' + key,
        'Referer': 'https://www.luffycity.com/',
        'Origin': 'https://www.luffycity.com',
        'Accept': 'application/json, text/plain, */*',
    };
    return fetchUrlWithMergedCookieValue(LUFFYCITY_API_BASE + '/auth/token/', cookie_value, 0, headers)
        .then((result) => {
            if (looksLikeLuffycityLoginInfo(result)) {
                return true;
            }
            return fetchUrlWithMergedCookieValue(LUFFYCITY_API_BASE + '/study/courses/', cookie_value, 0, headers)
                .then((course_result) => looksLikeLuffycityLoginInfo(course_result));
        })
        .catch(() => false);
}

function clickLuffycityLoginButton(win, delay_ms = 0) {
    if (login_name !== 'luffycity' || !isWindowAlive(win)) {
        return;
    }
    setTimeout(() => {
        const contents = getSafeWebContents(win);
        if (!contents) {
            return;
        }
        contents.executeJavaScript(`
            (function () {
                function textOf(el) {
                    try {
                        return String((el && (el.innerText || el.textContent)) || '').replace(/\\s+/g, '');
                    } catch (error) {
                        return '';
                    }
                }
                function markerOf(el) {
                    if (!el) {
                        return '';
                    }
                    var attrText = '';
                    try {
                        attrText = [
                            el.getAttribute && el.getAttribute('role'),
                            el.getAttribute && el.getAttribute('aria-label'),
                            el.getAttribute && el.getAttribute('title')
                        ].join(' ');
                    } catch (error) {
                        ;
                    }
                    return String((el.id || '') + ' ' + (el.className || '') + ' ' + attrText).toLowerCase();
                }
                function isVisible(el) {
                    if (!el) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0) {
                        return false;
                    }
                    var rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }
                function hasLoginForm() {
                    return Array.prototype.slice.call(document.querySelectorAll(
                        'input[type="password"], input[placeholder*="密码"], input[placeholder*="验证码"], input[placeholder*="手机号"], input[placeholder*="手机"], input[placeholder*="账号"]'
                    )).some(isVisible);
                }
                function clickNode(el) {
                    if (!el || !isVisible(el)) {
                        return false;
                    }
                    try {
                        el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                    } catch (error) {
                        ;
                    }
                    try {
                        el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    } catch (error) {
                        ;
                    }
                    try {
                        el.click();
                    } catch (error) {
                        ;
                    }
                    return true;
                }
                function clickableOf(el) {
                    var node = el;
                    for (var i = 0; node && node !== document.body && i < 5; i++, node = node.parentElement) {
                        if (node.matches && node.matches('a,button,[role="button"],[onclick]')) {
                            return node;
                        }
                        if (/login|signin|user|avatar/.test(markerOf(node))) {
                            return node;
                        }
                    }
                    return el;
                }
                function scoreCandidate(el) {
                    if (!isVisible(el)) {
                        return -1;
                    }
                    var text = textOf(el);
                    var marker = markerOf(el);
                    if (text.indexOf('已登录') >= 0 || text.indexOf('退出登录') >= 0) {
                        return -1;
                    }
                    var hasLoginText = text === '登录' || text === '立即登录' || text === '登录注册' || text === '登录/注册';
                    var hasLoginMarker = /login|signin/.test(marker);
                    if (!hasLoginText && !hasLoginMarker) {
                        return -1;
                    }
                    if (hasLoginText && text.length > 8) {
                        return -1;
                    }
                    var rect = el.getBoundingClientRect();
                    var score = 0;
                    if (hasLoginText) {
                        score += 30;
                    }
                    if (hasLoginMarker) {
                        score += 8;
                    }
                    if (rect.top >= -10 && rect.top < Math.max(180, window.innerHeight * 0.35)) {
                        score += 10;
                    }
                    if (rect.left > window.innerWidth * 0.45) {
                        score += 12;
                    }
                    return score;
                }
                function centerOf(el) {
                    var rect = el.getBoundingClientRect();
                    return {
                        x: Math.max(1, Math.round(rect.left + rect.width / 2)),
                        y: Math.max(1, Math.round(rect.top + rect.height / 2))
                    };
                }
                if (hasLoginForm()) {
                    return {clicked: false, reason: 'has-form'};
                }
                var nodes = Array.prototype.slice.call(document.querySelectorAll('button,a,div,span,p,li,em,i,[role="button"],[onclick],[class*="login"],[class*="Login"],[id*="login"],[id*="Login"]'));
                var candidates = [];
                nodes.forEach(function (node) {
                    var target = clickableOf(node);
                    var score = scoreCandidate(target || node);
                    if (score > 0) {
                        candidates.push({node: target || node, score: score});
                    }
                });
                candidates.sort(function (a, b) {
                    return b.score - a.score;
                });
                if (!candidates.length) {
                    for (var y = 24; y <= 72 && !candidates.length; y += 16) {
                        for (var x = Math.floor(window.innerWidth * 0.5); x <= Math.floor(window.innerWidth * 0.9); x += 32) {
                            var hit = document.elementFromPoint(x, y);
                            var target = clickableOf(hit);
                            if (target && scoreCandidate(target) > 0) {
                                candidates.push({node: target, score: scoreCandidate(target)});
                                break;
                            }
                        }
                    }
                }
                if (!candidates.length) {
                    return {clicked: false, reason: 'no-candidate'};
                }
                var target = candidates[0].node;
                var point = centerOf(target);
                var clicked = clickNode(target);
                if (target.parentElement) {
                    clickNode(target.parentElement);
                }
                setTimeout(function () {
                    if (!hasLoginForm()) {
                        clickNode(target);
                    }
                }, 120);
                return {
                    clicked: clicked,
                    x: point.x,
                    y: point.y,
                    score: candidates[0].score,
                    text: textOf(target)
                };
            })();
        `, true).then((result) => {
            if (!result || !result.clicked || result.reason === 'has-form') {
                return;
            }
            const x = Number(result.x || 0);
            const y = Number(result.y || 0);
            if (x > 0 && y > 0) {
                try {
                    contents.sendInputEvent({type: 'mouseMove', x, y});
                    contents.sendInputEvent({type: 'mouseDown', x, y, button: 'left', clickCount: 1});
                    contents.sendInputEvent({type: 'mouseUp', x, y, button: 'left', clickCount: 1});
                } catch (error) {
                    ;
                }
            }
        }).catch(() => {
            ;
        });
    }, delay_ms);
}

function clickSiereduLoginButton(win, delay_ms = 0) {
    if (login_name !== 'sieredu' || !isWindowAlive(win)) {
        return;
    }
    setTimeout(() => {
        const contents = getSafeWebContents(win);
        if (!contents) {
            return;
        }
        contents.executeJavaScript(`
            (function () {
                function textOf(el) {
                    try {
                        return String((el && (el.innerText || el.textContent)) || '').replace(/\\s+/g, '');
                    } catch (error) {
                        return '';
                    }
                }
                function markerOf(el) {
                    if (!el) {
                        return '';
                    }
                    var attrText = '';
                    try {
                        attrText = [
                            el.getAttribute && el.getAttribute('role'),
                            el.getAttribute && el.getAttribute('aria-label'),
                            el.getAttribute && el.getAttribute('title')
                        ].join(' ');
                    } catch (error) {
                        ;
                    }
                    return String((el.id || '') + ' ' + (el.className || '') + ' ' + attrText).toLowerCase();
                }
                function isVisible(el) {
                    if (!el) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0) {
                        return false;
                    }
                    var rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }
                function hasLoginPanel() {
                    var bodyText = textOf(document.body);
                    if ((bodyText.indexOf('\\u626b\\u7801\\u767b\\u5f55') >= 0 && bodyText.indexOf('\\u5176\\u4ed6\\u767b\\u5f55') >= 0)
                        || (bodyText.indexOf('\\u6253\\u5f00\\u5fae\\u4fe1') >= 0 && bodyText.indexOf('\\u767b\\u5f55') >= 0)) {
                        return true;
                    }
                    return !!document.querySelector([
                        '.componentDialog input',
                        '.sierLogin input',
                        '[class*="login"] input',
                        '[class*="Login"] input',
                        'input[type="password"]',
                        'input[placeholder*="\\u624b\\u673a"]',
                        'input[placeholder*="\\u9a8c\\u8bc1\\u7801"]',
                        'input[placeholder*="\\u5bc6\\u7801"]'
                    ].join(','));
                }
                function clickNode(el) {
                    if (!el || !isVisible(el)) {
                        return false;
                    }
                    try {
                        el.scrollIntoView({ block: 'center', inline: 'center' });
                    } catch (error) {
                        ;
                    }
                    try {
                        el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    } catch (error) {
                        ;
                    }
                    try {
                        el.click();
                    } catch (error) {
                        ;
                    }
                    return true;
                }
                function clickableOf(el) {
                    if (!el) {
                        return null;
                    }
                    if (el.closest) {
                        var loginEntry = el.closest('.login_register');
                        if (loginEntry && isVisible(loginEntry)) {
                            return loginEntry;
                        }
                    }
                    var selectors = 'button,a,[role="button"],[onclick],.login_register,.login';
                    var node = el;
                    for (var i = 0; node && i < 5; i++, node = node.parentElement) {
                        if (node.matches && node.matches(selectors) && isVisible(node)) {
                            return node;
                        }
                    }
                    return el;
                }
                function scoreCandidate(el) {
                    if (!isVisible(el)) {
                        return -1;
                    }
                    var text = textOf(el);
                    var marker = markerOf(el);
                    if (!text || text.indexOf('\\u9000\\u51fa\\u767b\\u5f55') >= 0 || text.indexOf('\\u5df2\\u767b\\u5f55') >= 0) {
                        return -1;
                    }
                    var hasLoginText = text === '\\u767b\\u5f55' || text === '\\u7acb\\u5373\\u767b\\u5f55' || text === '\\u767b\\u5f55\\u6ce8\\u518c' || text === '\\u767b\\u5f55/\\u6ce8\\u518c';
                    var hasLoginMarker = /login|login_register|signin/.test(marker);
                    if (!hasLoginText && !hasLoginMarker) {
                        return -1;
                    }
                    if (hasLoginText && text.length > 8) {
                        return -1;
                    }
                    var rect = el.getBoundingClientRect();
                    var score = 0;
                    if (hasLoginText) {
                        score += 30;
                    }
                    if (hasLoginMarker) {
                        score += 12;
                    }
                    if (el.closest && el.closest('.user,.headR,.headFixd,.headBox,.headContent,header')) {
                        score += 25;
                    }
                    if (rect.top >= -10 && rect.top < Math.max(180, window.innerHeight * 0.3)) {
                        score += 10;
                    }
                    if (rect.left > window.innerWidth * 0.35) {
                        score += 8;
                    }
                    return score;
                }
                function findVueComponent(el) {
                    var node = el;
                    while (node) {
                        if (node.__vue__) {
                            return node.__vue__;
                        }
                        node = node.parentElement;
                    }
                    return null;
                }
                function openByVueComponent(el) {
                    var vm = findVueComponent(el);
                    var guard = 0;
                    while (vm && guard < 8) {
                        if (typeof vm.visibleLogin === 'function') {
                            try {
                                vm.visibleLogin(1);
                                return true;
                            } catch (error) {
                                return false;
                            }
                        }
                        vm = vm.$parent;
                        guard += 1;
                    }
                    return false;
                }
                if (!document || !document.documentElement) {
                    return {clicked: false, reason: 'no-document'};
                }
                if (hasLoginPanel()) {
                    return {clicked: false, panel: true};
                }
                var selectors = [
                    '.user .login_register',
                    '.user .login_register .login',
                    '.headR .login_register',
                    '.headR .login_register .login'
                ];
                for (var i = 0; i < selectors.length; i++) {
                    var node = document.querySelector(selectors[i]);
                    if (node && isVisible(node)) {
                        var target = clickableOf(node);
                        var clicked = clickNode(target);
                        if (!hasLoginPanel()) {
                            openByVueComponent(target);
                        }
                        return {clicked: clicked, selector: selectors[i]};
                    }
                }
                var nodes = Array.prototype.slice.call(document.querySelectorAll('button,a,div,span,li,[role="button"],[onclick]'));
                var candidates = [];
                nodes.forEach(function (node) {
                    var clickable = clickableOf(node);
                    var score = scoreCandidate(clickable || node);
                    if (score > 0) {
                        candidates.push({node: clickable || node, score: score});
                    }
                });
                candidates.sort(function (a, b) {
                    return b.score - a.score;
                });
                if (!candidates.length) {
                    return {clicked: false, reason: 'no-candidate', readyState: document.readyState};
                }
                var clicked = clickNode(candidates[0].node);
                if (!hasLoginPanel()) {
                    openByVueComponent(candidates[0].node);
                }
                return {clicked: clicked, score: candidates[0].score, text: textOf(candidates[0].node)};
            })();
        `, true).catch(() => {
            ;
        });
    }, Math.max(0, Number(delay_ms) || 0));
}

function clickZhidaoLoginButton(win, delay_ms = 0) {
    if (login_name !== 'zhidao' || !isWindowAlive(win)) {
        return;
    }
    setTimeout(() => {
        const contents = getSafeWebContents(win);
        if (!contents) {
            return;
        }
        contents.executeJavaScript(`
            (function () {
                function textOf(el) {
                    try {
                        return String((el && (el.innerText || el.textContent)) || '').replace(/\\s+/g, '');
                    } catch (error) {
                        return '';
                    }
                }
                function markerOf(el) {
                    if (!el) {
                        return '';
                    }
                    var attrText = '';
                    try {
                        attrText = [
                            el.getAttribute && el.getAttribute('role'),
                            el.getAttribute && el.getAttribute('aria-label'),
                            el.getAttribute && el.getAttribute('title'),
                            el.getAttribute && el.getAttribute('href')
                        ].join(' ');
                    } catch (error) {
                        ;
                    }
                    return String((el.id || '') + ' ' + (el.className || '') + ' ' + attrText).toLowerCase();
                }
                function isVisible(el) {
                    if (!el) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0) {
                        return false;
                    }
                    var rect = el.getBoundingClientRect();
                    return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
                }
                function hasLoginPanel() {
                    var frame = document.querySelector('#containFrame, iframe[name="containFrame"]');
                    if (frame && isVisible(frame)) {
                        return true;
                    }
                    var mask = document.querySelector('[class*="mask"]');
                    return !!(mask && isVisible(mask) && mask.querySelector('iframe'));
                }
                function clickNode(el) {
                    if (!el || !isVisible(el)) {
                        return false;
                    }
                    try {
                        el.scrollIntoView({ block: 'center', inline: 'center' });
                    } catch (error) {
                        ;
                    }
                    try {
                        el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    } catch (error) {
                        ;
                    }
                    try {
                        el.click();
                    } catch (error) {
                        ;
                    }
                    return true;
                }
                function exactLoginChild(el) {
                    if (!el || !el.querySelectorAll) {
                        return null;
                    }
                    var children = Array.prototype.slice.call(el.querySelectorAll('div,span,a,button,[role="button"],[role="none"]'));
                    for (var i = 0; i < children.length; i++) {
                        if (textOf(children[i]) === '\\u767b\\u5f55' && isVisible(children[i])) {
                            return children[i];
                        }
                    }
                    return null;
                }
                function clickableOf(el) {
                    if (!el) {
                        return null;
                    }
                    var exact = exactLoginChild(el);
                    if (exact) {
                        return exact;
                    }
                    if (textOf(el) === '\\u767b\\u5f55' && isVisible(el)) {
                        return el;
                    }
                    var node = el;
                    for (var i = 0; node && i < 4; i++, node = node.parentElement) {
                        if (node.matches && node.matches('button,a,[role="button"],[onclick]') && isVisible(node)) {
                            return exactLoginChild(node) || node;
                        }
                    }
                    return el;
                }
                function scoreCandidate(el) {
                    if (!isVisible(el)) {
                        return -1;
                    }
                    var text = textOf(el);
                    var marker = markerOf(el);
                    if (text.indexOf('\\u9000\\u51fa') >= 0 || text.indexOf('\\u5df2\\u767b\\u5f55') >= 0) {
                        return -1;
                    }
                    var hasLoginText = text === '\\u767b\\u5f55';
                    var hasLoginMarker = /login/.test(marker);
                    if (!hasLoginText && !hasLoginMarker) {
                        return -1;
                    }
                    if (hasLoginText && text.length > 4) {
                        return -1;
                    }
                    var rect = el.getBoundingClientRect();
                    var score = 0;
                    if (hasLoginText) {
                        score += 40;
                    }
                    if (hasLoginMarker) {
                        score += 12;
                    }
                    if (el.closest && el.closest('nav,header,[class*="topNav"],[class*="navList"]')) {
                        score += 25;
                    }
                    if (rect.top >= -10 && rect.top < Math.max(160, window.innerHeight * 0.25)) {
                        score += 15;
                    }
                    if (rect.left > window.innerWidth * 0.4) {
                        score += 10;
                    }
                    return score;
                }
                if (!document || !document.documentElement) {
                    return { clicked: false, reason: 'no-document' };
                }
                if (hasLoginPanel()) {
                    return { clicked: false, panel: true };
                }
                var directNodes = Array.prototype.slice.call(document.querySelectorAll('a[href*="/login"],a[href*="#/login"],[role="none"]'));
                var candidates = [];
                directNodes.concat(Array.prototype.slice.call(document.querySelectorAll('button,a,div,span,li,[role="button"],[onclick]'))).forEach(function (node) {
                    var target = clickableOf(node);
                    var score = scoreCandidate(target || node);
                    if (score > 0) {
                        candidates.push({ node: target || node, score: score });
                    }
                });
                candidates.sort(function (a, b) {
                    return b.score - a.score;
                });
                if (!candidates.length) {
                    return { clicked: false, reason: 'no-candidate', readyState: document.readyState };
                }
                var target = candidates[0].node;
                var rect = target.getBoundingClientRect();
                var clicked = clickNode(target);
                return {
                    clicked: clicked,
                    x: Math.round(rect.left + rect.width / 2),
                    y: Math.round(rect.top + rect.height / 2),
                    score: candidates[0].score,
                    text: textOf(target)
                };
            })();
        `, true).then((result) => {
            if (!result || !result.clicked || result.panel) {
                return;
            }
            const x = Number(result.x || 0);
            const y = Number(result.y || 0);
            if (x > 0 && y > 0) {
                try {
                    contents.sendInputEvent({type: 'mouseMove', x, y});
                    contents.sendInputEvent({type: 'mouseDown', x, y, button: 'left', clickCount: 1});
                    contents.sendInputEvent({type: 'mouseUp', x, y, button: 'left', clickCount: 1});
                } catch (error) {
                    ;
                }
            }
        }).catch(() => {
            ;
        });
    }, Math.max(0, Number(delay_ms) || 0));
}

function clickYiihuuLoginButton(win, delay_ms = 0) {
    if (login_name !== 'yiihuu' || !isWindowAlive(win)) {
        return;
    }
    setTimeout(() => {
        const contents = getSafeWebContents(win);
        if (!contents) {
            return;
        }
        const yiihuu_script = `
            (function () {
                function textOf(el) {
                    try {
                        return String((el && (el.innerText || el.textContent)) || '').replace(/\\s+/g, '');
                    } catch (error) {
                        return '';
                    }
                }
                function markerOf(el) {
                    if (!el) {
                        return '';
                    }
                    var attrText = '';
                    try {
                        attrText = [
                            el.getAttribute && el.getAttribute('role'),
                            el.getAttribute && el.getAttribute('aria-label'),
                            el.getAttribute && el.getAttribute('title'),
                            el.getAttribute && el.getAttribute('href')
                        ].join(' ');
                    } catch (error) {
                        ;
                    }
                    return String((el.id || '') + ' ' + (el.className || '') + ' ' + attrText).toLowerCase();
                }
                function isVisible(el) {
                    if (!el) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0) {
                        return false;
                    }
                    var rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }
                function hasLoginPanel() {
                    var href = String(window.location.href || '').toLowerCase();
                    if (href.indexOf('passport.yiihuu.com') >= 0) {
                        return true;
                    }
                    var panelNodes = Array.prototype.slice.call(document.querySelectorAll('#J_iframelogin,.login-dialog,.el-dialog,[class*="login-dialog"],[class*="loginDialog"],[class*="passport"]'));
                    for (var i = 0; i < panelNodes.length; i++) {
                        var panel = panelNodes[i];
                        if (!isVisible(panel)) {
                            continue;
                        }
                        var panelText = textOf(panel);
                        if ((panelText.indexOf('\\u624b\\u673a') >= 0 || panelText.indexOf('\\u5fae\\u4fe1') >= 0 || panelText.indexOf('\\u9a8c\\u8bc1\\u7801') >= 0)
                            && panelText.indexOf('\\u767b\\u5f55') >= 0) {
                            return true;
                        }
                    }
                    var loginNodes = Array.prototype.slice.call(document.querySelectorAll([
                        'iframe[src*="passport.yiihuu.com"]',
                        'form input[type="password"]',
                        'input[placeholder*="\\u624b\\u673a"]',
                        'input[placeholder*="\\u9a8c\\u8bc1\\u7801"]',
                        'input[placeholder*="\\u5bc6\\u7801"]',
                        '[class*="login"] input',
                        '[id*="login"] input'
                    ].join(',')));
                    for (var j = 0; j < loginNodes.length; j++) {
                        if (isVisible(loginNodes[j])) {
                            return true;
                        }
                    }
                    return false;
                }
                function clickNode(el) {
                    if (!el || !isVisible(el)) {
                        return false;
                    }
                    try {
                        el.scrollIntoView({ block: 'center', inline: 'center' });
                    } catch (error) {
                        ;
                    }
                    try {
                        el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                        el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    } catch (error) {
                        ;
                    }
                    try {
                        el.click();
                    } catch (error) {
                        ;
                    }
                    return true;
                }
                function hideNode(el) {
                    if (!el || !el.style) {
                        return;
                    }
                    if (el === document.body || el === document.documentElement || el.id === 'app') {
                        return;
                    }
                    try {
                        el.setAttribute('data-lel-yiihuu-hidden', '1');
                        el.style.setProperty('display', 'none', 'important');
                        el.style.setProperty('visibility', 'hidden', 'important');
                        el.style.setProperty('opacity', '0', 'important');
                        el.style.setProperty('pointer-events', 'none', 'important');
                    } catch (error) {
                        ;
                    }
                }
                function findPopupPanel(el) {
                    if (!el) {
                        return null;
                    }
                    if (el.closest) {
                        var panel = el.closest('[class*="popup"],[class*="Popup"],[class*="modal"],[class*="Modal"],[class*="dialog"],[class*="Dialog"],[class*="layer"],[class*="Layer"],[class*="mask"],[class*="Mask"],[class*="overlay"],[class*="Overlay"],[class*="lottery"],[class*="Lottery"],[class*="giftPack"],[class*="giftPacks"],[class*="prize"],[id*="popup"],[id*="modal"],[id*="dialog"],[id*="layer"],[id*="mask"],[id*="lottery"],[id*="Lottery"],[id*="giftPack"],[id*="giftPacks"],[id*="prize"]');
                        if (panel && isVisible(panel)) {
                            return panel;
                        }
                    }
                    var node = el;
                    for (var i = 0; node && node !== document.body && i < 5; i++, node = node.parentElement) {
                        if (!isVisible(node)) {
                            continue;
                        }
                        var marker = markerOf(node);
                        var style = window.getComputedStyle(node);
                        var zIndex = parseInt(style.zIndex || '0', 10) || 0;
                        if (/(popup|pop|modal|dialog|layer|mask|overlay|activity|gift|giftpack|coupon|packet|welfare|new|lottery|draw|prize)/i.test(marker)
                            || ((style.position === 'fixed' || style.position === 'absolute') && zIndex >= 100)) {
                            return node;
                        }
                    }
                    return null;
                }
                function isNewcomerGiftPopup(el) {
                    if (!el || !isVisible(el)) {
                        return false;
                    }
                    var text = textOf(el);
                    var marker = markerOf(el);
                    if (el === document.body || el === document.documentElement || el.id === 'app') {
                        return false;
                    }
                    if (/login|signin|passport|captcha|verify|password|phone|sms/.test(marker)) {
                        return false;
                    }
                    if (text.indexOf('\\u5bc6\\u7801') >= 0 || text.indexOf('\\u9a8c\\u8bc1\\u7801') >= 0 || text.indexOf('\\u624b\\u673a\\u53f7') >= 0) {
                        return false;
                    }
                    var hasGiftText = text.indexOf('\\u65b0\\u4eba') >= 0
                        || text.indexOf('\\u5927\\u793c\\u5305') >= 0
                        || text.indexOf('\\u793c\\u5305') >= 0
                        || text.indexOf('\\u56de\\u5f52\\u793c') >= 0
                        || text.indexOf('\\u4e13\\u5c5e') >= 0
                        || text.indexOf('\\u798f\\u5229') >= 0
                        || text.indexOf('\\u4f18\\u60e0\\u5238') >= 0
                        || text.indexOf('\\u5956\\u54c1') >= 0
                        || text.indexOf('\\u62bd\\u5956') >= 0
                        || text.indexOf('\\u9886\\u53d6') >= 0;
                    var hasGiftMarker = /(new|gift|giftpack|coupon|packet|welfare|activity|advert|adver|lottery|draw|prize)/i.test(marker);
                    if (!hasGiftText && !hasGiftMarker) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    var rect = el.getBoundingClientRect();
                    var zIndex = parseInt(style.zIndex || '0', 10) || 0;
                    if (!/(popup|pop|modal|dialog|layer|mask|overlay|activity|gift|giftpack|coupon|packet|welfare|new|lottery|draw|prize)/i.test(marker)
                        && !(style.position === 'fixed' || style.position === 'absolute')
                        && el !== document.body
                        && el !== document.documentElement) {
                        return false;
                    }
                    return (
                        hasGiftText
                        || ((style.position === 'fixed' || style.position === 'absolute') && zIndex >= 100 && rect.width >= 120 && rect.height >= 80)
                    );
                }
                function closeNewcomerGiftPopup() {
                    var closed = false;
                    Array.prototype.slice.call(document.querySelectorAll('#lotteryDraw-min,#lotteryDrawed-min,#lotteryDraw,.lotteryDraw,.lotteryDrawed,.lottery-shade,#giftPack_iframebox,#footerAdvert,.footer-advert,.giftBag_item,.activity_item,[class*="giftPack"],[class*="giftPacks"]')).forEach(function (panel) {
                        if (panel === document.body || panel === document.documentElement || panel.id === 'app') {
                            return;
                        }
                        hideNode(panel);
                        closed = true;
                    });
                    var closeSelectors = [
                        '#minLotteryDraw-closeBtn',
                        '#minLotteryDrawed-closeBtn',
                        '#lotteryDraw-closeBtn',
                        '.minLotteryDraw-closeBtn',
                        '.giftPacks-closeBtn',
                        '#gp-closeBtn',
                        '#advertCloseBtn',
                        '.closeAdvert-btn',
                        '.giftBag_close',
                        '.activity_close',
                        '.close',
                        '.close-btn',
                        '.closeButton',
                        '.popup-close',
                        '.pop-close',
                        '.modal-close',
                        '.dialog-close',
                        '.layui-layer-close',
                        '.ant-modal-close',
                        '.el-dialog__headerbtn',
                        '[aria-label="Close"]',
                        '[aria-label="close"]',
                        '[class*="close"]',
                        '[class*="Close"]'
                    ];
                    closeSelectors.forEach(function (selector) {
                        Array.prototype.slice.call(document.querySelectorAll(selector)).forEach(function (node) {
                            if (!isVisible(node)) {
                                return;
                            }
                            var panel = findPopupPanel(node);
                            if (!panel || !isNewcomerGiftPopup(panel)) {
                                return;
                            }
                            clickNode(node);
                            hideNode(panel);
                            closed = true;
                        });
                    });
                    Array.prototype.slice.call(document.querySelectorAll('[class*="popup"],[class*="Popup"],[class*="modal"],[class*="Modal"],[class*="dialog"],[class*="Dialog"],[class*="layer"],[class*="Layer"],[class*="mask"],[class*="Mask"],[class*="overlay"],[class*="Overlay"],[class*="lottery"],[class*="Lottery"],[class*="giftPack"],[class*="giftPacks"],[class*="prize"],[id*="popup"],[id*="modal"],[id*="dialog"],[id*="layer"],[id*="mask"],[id*="lottery"],[id*="Lottery"],[id*="giftPack"],[id*="giftPacks"],[id*="prize"]')).forEach(function (panel) {
                        if (!isNewcomerGiftPopup(panel)) {
                            return;
                        }
                        var nodes = Array.prototype.slice.call(panel.querySelectorAll('button,a,span,i,em,div'));
                        for (var i = 0; i < nodes.length; i++) {
                            var node = nodes[i];
                            if (!isVisible(node)) {
                                continue;
                            }
                            var text = textOf(node);
                            var marker = markerOf(node);
                            if (text === '\\u00d7' || text === 'x' || text === 'X' || text.indexOf('\\u5173\\u95ed') >= 0 || text.indexOf('\\u7a0d\\u540e') >= 0 || /close|guanbi/i.test(marker)) {
                                clickNode(node);
                                break;
                            }
                        }
                        hideNode(panel);
                        closed = true;
                    });
                    return closed;
                }
                function clickableOf(el) {
                    var selectors = 'button,a,[role="button"],[onclick],[class*="login"],[id*="login"]';
                    var node = el;
                    for (var i = 0; node && i < 5; i++, node = node.parentElement) {
                        if (node.matches && node.matches(selectors) && isVisible(node)) {
                            return node;
                        }
                    }
                    return el;
                }
                function scoreCandidate(el) {
                    if (!isVisible(el)) {
                        return -1;
                    }
                    var text = textOf(el);
                    var marker = markerOf(el);
                    if (text.indexOf('\\u9000\\u51fa') >= 0 || text.indexOf('\\u6ce8\\u9500') >= 0 || text.indexOf('\\u5df2\\u767b\\u5f55') >= 0) {
                        return -1;
                    }
                    var hasLoginText = text === '\\u767b\\u5f55'
                        || text === '\\u767b\\u5f55/\\u6ce8\\u518c'
                        || text === '\\u767b\\u5f55\\u6ce8\\u518c'
                        || text === '\\u7acb\\u5373\\u767b\\u5f55';
                    var hasLoginMarker = /login|signin|passport/.test(marker);
                    if (!hasLoginText && !hasLoginMarker) {
                        return -1;
                    }
                    if (hasLoginText && text.length > 8) {
                        return -1;
                    }
                    var rect = el.getBoundingClientRect();
                    var score = 0;
                    if (hasLoginText) {
                        score += 40;
                    }
                    if (hasLoginMarker) {
                        score += 10;
                    }
                    if (rect.top >= -20 && rect.top < Math.max(180, window.innerHeight * 0.3)) {
                        score += 15;
                    }
                    if (rect.left > window.innerWidth * 0.45) {
                        score += 15;
                    }
                    if (el.closest && el.closest('header,.header,.top,.nav,.head,.user,.login-register,.login_register')) {
                        score += 12;
                    }
                    return score;
                }
                if (!document || !document.documentElement) {
                    return { clicked: false, reason: 'no-document' };
                }
                closeNewcomerGiftPopup();
                if (hasLoginPanel()) {
                    return { clicked: false, panel: true };
                }
                var nodes = Array.prototype.slice.call(document.querySelectorAll('button,a,div,span,li,[role="button"],[onclick],[class*="login"],[id*="login"]'));
                var candidates = [];
                nodes.forEach(function (node) {
                    var clickable = clickableOf(node);
                    var score = scoreCandidate(clickable || node);
                    if (score > 0) {
                        candidates.push({ node: clickable || node, score: score });
                    }
                });
                candidates.sort(function (a, b) {
                    return b.score - a.score;
                });
                if (!candidates.length) {
                    return { clicked: false, reason: 'no-candidate', readyState: document.readyState };
                }
                var target = candidates[0].node;
                var rect = target.getBoundingClientRect();
                var clicked = clickNode(target);
                return {
                    clicked: clicked,
                    x: Math.round(rect.left + rect.width / 2),
                    y: Math.round(rect.top + rect.height / 2),
                    score: candidates[0].score,
                    text: textOf(target)
                };
            })();
        `;
        const runYiihuuScript = () => {
            const fallback = () => contents.executeJavaScript(yiihuu_script, true);
            try {
                if (!contents.debugger) {
                    return fallback();
                }
                let attached_here = false;
                if (!contents.debugger.isAttached()) {
                    contents.debugger.attach('1.3');
                    attached_here = true;
                }
                return contents.debugger.sendCommand('Runtime.evaluate', {
                    expression: yiihuu_script,
                    awaitPromise: true,
                    returnByValue: true
                }).then((response) => {
                    if (attached_here && contents.debugger.isAttached()) {
                        try {
                            contents.debugger.detach();
                        } catch (error) {
                            ;
                        }
                    }
                    if (response && response.exceptionDetails) {
                        return fallback();
                    }
                    return response && response.result ? response.result.value : null;
                }).catch(() => {
                    if (attached_here && contents.debugger && contents.debugger.isAttached()) {
                        try {
                            contents.debugger.detach();
                        } catch (error) {
                            ;
                        }
                    }
                    return fallback();
                });
            } catch (error) {
                return fallback();
            }
        };
        runYiihuuScript().then((result) => {
            if (!result || !result.clicked) {
                return;
            }
            const x = Number(result.x || 0);
            const y = Number(result.y || 0);
            if (x > 0 && y > 0) {
                try {
                    contents.sendInputEvent({type: 'mouseMove', x, y});
                    contents.sendInputEvent({type: 'mouseDown', x, y, button: 'left', clickCount: 1});
                    contents.sendInputEvent({type: 'mouseUp', x, y, button: 'left', clickCount: 1});
                } catch (error) {
                    ;
                }
            }
        }).catch(() => {
            ;
        });
    }, Math.max(0, Number(delay_ms) || 0));
}

function buildCaixuetangPopupSuppressScript() {
    return `
        (function () {
            if (window.__LEL_CAIXUETANG_POPUP_SUPPRESS_READY__) {
                try {
                    window.__LEL_CAIXUETANG_POPUP_SUPPRESS_READY__.run();
                } catch (error) {
                    ;
                }
                return true;
            }

            function textOf(node) {
                try {
                    return String((node && (node.innerText || node.textContent)) || '').replace(/\\s+/g, '');
                } catch (error) {
                    return '';
                }
            }

            function markerOf(node) {
                if (!node) {
                    return '';
                }
                var attrText = '';
                try {
                    attrText = [
                        node.getAttribute && node.getAttribute('role'),
                        node.getAttribute && node.getAttribute('aria-label'),
                        node.getAttribute && node.getAttribute('title')
                    ].join(' ');
                } catch (error) {
                    ;
                }
                return String((node.id || '') + ' ' + (node.className || '') + ' ' + attrText).toLowerCase();
            }

            function isVisible(node) {
                if (!node) {
                    return false;
                }
                var style = window.getComputedStyle(node);
                if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0) {
                    return false;
                }
                var rect = node.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            function hasLoginInputs(node) {
                if (!node || !node.querySelector) {
                    return false;
                }
                return !!node.querySelector([
                    'input[type="password"]',
                    'input[placeholder*="密码"]',
                    'input[placeholder*="验证码"]',
                    'input[placeholder*="手机"]',
                    'input[placeholder*="账号"]',
                    'input[placeholder*="账户"]',
                    '.aliyunCaptcha-window-popup',
                    '#aliyunCaptcha-window-popup',
                    '.nc-container',
                    '[class*="captcha"]',
                    '[class*="Captcha"]'
                ].join(','));
            }

            function isLoginNode(node) {
                if (!node) {
                    return false;
                }
                if (node.matches && node.matches('.login-dialog,.login-container,.login-dialog-content')) {
                    return true;
                }
                if (node.closest && node.closest('.login-dialog,.login-container,.login-dialog-content')) {
                    return true;
                }
                if (hasLoginInputs(node)) {
                    return true;
                }
                var marker = markerOf(node);
                var text = textOf(node);
                if (/login|signin|captcha|verify|password|phone|sms/.test(marker)) {
                    if (text.indexOf('登录') >= 0 || text.indexOf('验证码') >= 0 || text.indexOf('密码') >= 0 || text.indexOf('手机号') >= 0 || text.indexOf('微信') >= 0 || text.indexOf('二维码登录') >= 0) {
                        return true;
                    }
                }
                return false;
            }

            function hideNode(node) {
                if (!node || node === document.body || node === document.documentElement || isLoginNode(node)) {
                    return false;
                }
                node.setAttribute('data-lel-caixuetang-hidden', '1');
                node.style.setProperty('display', 'none', 'important');
                node.style.setProperty('visibility', 'hidden', 'important');
                node.style.setProperty('opacity', '0', 'important');
                node.style.setProperty('pointer-events', 'none', 'important');
                return true;
            }

            function findStore() {
                var roots = [
                    document.querySelector('#app'),
                    document.body,
                    document.documentElement
                ];
                for (var i = 0; i < roots.length; i++) {
                    var node = roots[i];
                    if (node && node.__vue__ && node.__vue__.$store) {
                        return node.__vue__.$store;
                    }
                }
                var nodes = Array.prototype.slice.call(document.querySelectorAll('*'));
                for (var j = 0; j < nodes.length; j++) {
                    if (nodes[j].__vue__ && nodes[j].__vue__.$store) {
                        return nodes[j].__vue__.$store;
                    }
                }
                return null;
            }

            function cleanupVuePopups() {
                var store = findStore();
                if (!store || typeof store.commit !== 'function') {
                    return;
                }
                try { store.commit('global/setAdvertVisible', false); } catch (error) { ; }
                try { store.commit('setPasStrengthDialogMark', false); } catch (error) { ; }
                try { store.commit('setServiceVisible', false); } catch (error) { ; }
            }

            function isKnownFloatingWidget(node) {
                var marker = markerOf(node);
                return /(meiqia|qimo|newbridge|nb-|kefu|customer|consult|service|code_popup|fixed_mod_user|fixed_vip_popup|app_down_code|customer-service|icon_vip|advert|adver|advertising|coupon|activity|download-app|app-download|qrcode|qr-code|wechat|wx)/i.test(marker);
            }

            function isKnownGlobalDialog(node) {
                var marker = markerOf(node);
                if (/login|signin|captcha|verify|password|phone|sms/.test(marker) || isLoginNode(node)) {
                    return false;
                }
                if (/(advertising-custom|advert-dialog|advert|adver|passtrength|pas-strength|strengthdialog|agreement-dialog|service-dialog|servicevisible|el-message-box__wrapper)/i.test(marker)) {
                    return true;
                }
                var text = textOf(node);
                if (!text) {
                    return false;
                }
                if (text.indexOf('尊敬的用户您好，您当前密码强度过低') >= 0 || text.indexOf('请尽快修改密码') >= 0) {
                    return true;
                }
                if (text.indexOf('协议更新通知') >= 0 || text.indexOf('隐私保护政策') >= 0 || text.indexOf('财学堂用户服务协议') >= 0) {
                    return true;
                }
                if (text.indexOf('开通VIP') >= 0 || text.indexOf('财学堂APP') >= 0 || text.indexOf('APP下载') >= 0 || text.indexOf('联系客服') >= 0 || text.indexOf('关注财学') >= 0 || text.indexOf('创作者中心') >= 0) {
                    return true;
                }
                return false;
            }

            function isLikelyNuisancePopup(node) {
                if (!node || !isVisible(node) || isLoginNode(node)) {
                    return false;
                }
                var marker = markerOf(node);
                if (/login|signin|captcha|verify|password|phone|sms/.test(marker)) {
                    return false;
                }
                if (isKnownFloatingWidget(node) || isKnownGlobalDialog(node)) {
                    return true;
                }
                if (/(popup|pop|modal|dialog|mask|overlay|layer|drawer)/i.test(marker)) {
                    var text = textOf(node);
                    if (text.indexOf('登录') >= 0 || text.indexOf('验证码') >= 0 || text.indexOf('密码') >= 0 || text.indexOf('手机号') >= 0 || text.indexOf('微信') >= 0) {
                        return false;
                    }
                    return isKnownGlobalDialog(node) || isKnownFloatingWidget(node);
                }
                var style = window.getComputedStyle(node);
                var zIndex = parseInt(style.zIndex || '0', 10) || 0;
                if ((style.position === 'fixed' || style.position === 'absolute') && zIndex >= 1000) {
                    if (isKnownGlobalDialog(node) || isKnownFloatingWidget(node)) {
                        return true;
                    }
                }
                return false;
            }

            function clickCloseButtons() {
                var closeSelectors = [
                    '.close',
                    '.close-btn',
                    '.closeButton',
                    '.popup-close',
                    '.modal-close',
                    '.dialog-close',
                    '.el-dialog__headerbtn',
                    '.ant-modal-close',
                    '.van-popup__close-icon',
                    '[class*="close"]',
                    '[class*="Close"]'
                ];
                closeSelectors.forEach(function (selector) {
                    Array.prototype.slice.call(document.querySelectorAll(selector)).forEach(function (node) {
                        if (!isVisible(node)) {
                            return;
                        }
                        var panel = node.closest && node.closest('[class*="popup"],[class*="Popup"],[class*="modal"],[class*="Modal"],[class*="dialog"],[class*="Dialog"],[class*="layer"],[class*="Layer"],[class*="mask"],[class*="Mask"]');
                        if (panel && isLoginNode(panel)) {
                            return;
                        }
                        if (panel && !isLikelyNuisancePopup(panel)) {
                            return;
                        }
                        try {
                            node.click();
                        } catch (error) {
                            ;
                        }
                    });
                });
            }

            function run() {
                try {
                    window.alert = function () {};
                    window.confirm = function () { return true; };
                    window.prompt = function () { return ''; };
                    if (!window.__LEL_CAIXUETANG_WINDOW_OPEN_WRAPPED__) {
                        window.__LEL_CAIXUETANG_WINDOW_OPEN_WRAPPED__ = true;
                        window.__LEL_CAIXUETANG_ORIGINAL_WINDOW_OPEN__ = window.open;
                        window.open = function (url, target, features) {
                            var rawUrl = String(url || '').trim();
                            if (!rawUrl) {
                                return null;
                            }
                            try {
                                var parsed = new URL(rawUrl, location.href);
                                if (parsed.hostname && parsed.hostname.endsWith('caixuetang.cn')) {
                                    return window.__LEL_CAIXUETANG_ORIGINAL_WINDOW_OPEN__.call(window, parsed.href, target, features);
                                }
                            } catch (error) {
                                ;
                            }
                            return null;
                        };
                    }
                } catch (error) {
                    ;
                }

                cleanupVuePopups();
                var style = document.getElementById('xuewuzhi-caixuetang-popup-suppress');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'xuewuzhi-caixuetang-popup-suppress';
                    (document.head || document.documentElement).appendChild(style);
                }
                style.textContent = [
                    '#MEIQIA-BTN-HOLDER,#qimoChat,#newBridge,.nb-icon-wrap,.nb-invite-wrap{display:none!important;visibility:hidden!important;pointer-events:none!important;}',
                    '.code_popup,.fixed_mod_user,.fixed_vip_popup,.app_down_code{display:none!important;visibility:hidden!important;pointer-events:none!important;}',
                    '[class*="kefu"],[id*="kefu"],[class*="customer"],[id*="customer"],[class*="consult"],[id*="consult"],[class*="service"][class*="float"],[class*="customer-service"]{display:none!important;visibility:hidden!important;pointer-events:none!important;}',
                    '.advertising-custom,[class*="advert"],[id*="advert"],[class*="adver"],[class*="coupon"],[class*="activity"],[class*="download-app"],[class*="app-download"]{display:none!important;visibility:hidden!important;pointer-events:none!important;}',
                    '[data-lel-caixuetang-hidden="1"]{display:none!important;visibility:hidden!important;opacity:0!important;pointer-events:none!important;}'
                ].join('\\n');

                clickCloseButtons();
                var selectors = [
                    '[role="dialog"]',
                    '.el-dialog__wrapper',
                    '.el-message-box__wrapper',
                    '.ant-modal-root',
                    '.van-overlay',
                    '.van-popup',
                    '.layui-layer',
                    '.advertising-custom',
                    '.code_popup',
                    '.fixed_mod_user',
                    '.fixed_vip_popup',
                    '.app_down_code',
                    '[class*="popup"]',
                    '[class*="Popup"]',
                    '[class*="modal"]',
                    '[class*="Modal"]',
                    '[class*="dialog"]',
                    '[class*="Dialog"]',
                    '[class*="overlay"]',
                    '[class*="Overlay"]',
                    '[class*="mask"]',
                    '[class*="Mask"]',
                    '[class*="layer"]',
                    '[class*="Layer"]',
                    '[class*="float"]',
                    '[class*="Float"]'
                ];
                selectors.forEach(function (selector) {
                    Array.prototype.slice.call(document.querySelectorAll(selector)).forEach(function (node) {
                        if (isLikelyNuisancePopup(node)) {
                            hideNode(node);
                        }
                    });
                });
            }

            var state = {
                run: run
            };
            window.__LEL_CAIXUETANG_POPUP_SUPPRESS_READY__ = state;
            run();
            if (typeof MutationObserver !== 'undefined' && !window.__LEL_CAIXUETANG_POPUP_SUPPRESS_OBSERVER__) {
                var observer = new MutationObserver(function () {
                    if (state.running) {
                        return;
                    }
                    state.running = true;
                    setTimeout(function () {
                        try {
                            run();
                        } finally {
                            state.running = false;
                        }
                    }, 80);
                });
                observer.observe(document.documentElement || document.body, {
                    childList: true,
                    subtree: true,
                    attributes: true,
                    attributeFilter: ['class', 'style']
                });
                window.__LEL_CAIXUETANG_POPUP_SUPPRESS_OBSERVER__ = observer;
            }
            return true;
        })();
    `;
}

function suppressCaixuetangPopups(win, delay_ms = 0) {
    if (login_name !== 'caixuetang') {
        return;
    }
    setTimeout(() => {
        if (!isWindowAlive(win)) {
            return;
        }
        win.webContents.executeJavaScript(buildCaixuetangPopupSuppressScript(), true).catch(() => {
            ;
        });
    }, Math.max(0, Number(delay_ms) || 0));
}

function installCaixuetangPopupBlockers(win) {
    if (!win || !win.webContents || win.__LEL_CAIXUETANG_POPUP_BLOCKER__) {
        return;
    }
    win.__LEL_CAIXUETANG_POPUP_BLOCKER__ = true;
    function isAllowedCaixuetangUrl(target_url) {
        try {
            const target = new URL(String(target_url || ''), getSafeWindowUrl(win) || 'https://www.caixuetang.cn/');
            return !!(target.hostname && target.hostname.endsWith('caixuetang.cn'));
        } catch (error) {
            return false;
        }
    }
    if (typeof win.webContents.setWindowOpenHandler === 'function') {
        win.webContents.setWindowOpenHandler((details) => {
            const target_url = details && details.url;
            if (isAllowedCaixuetangUrl(target_url)) {
                return { action: 'allow' };
            }
            return {action: 'deny'};
        });
    }
    win.webContents.on('new-window', (event, target_url) => {
        if (!isAllowedCaixuetangUrl(target_url)) {
            event.preventDefault();
        }
    });
    win.webContents.on('will-navigate', (event, target_url) => {
        const current_url = getSafeWindowUrl(win);
        const current_host = (() => {
            try { return new URL(current_url).hostname; } catch (error) { return ''; }
        })();
        const target_host = (() => {
            try { return new URL(target_url).hostname; } catch (error) { return ''; }
        })();
        if (current_host && target_host && current_host.endsWith('caixuetang.cn') && !target_host.endsWith('caixuetang.cn')) {
            event.preventDefault();
        }
    });
}


function isMddclassCookie(cookie) {
    if (!cookie || !cookie.name || cookie.value === undefined || cookie.value === null || String(cookie.value) === '') {
        return false;
    }
    const name = String(cookie.name);
    if (!MDDCLASS_COOKIE_NAMES.includes(name)) {
        return false;
    }
    const domain = String(cookie.domain || cookie.host_key || '').toLowerCase();
    if (!domain) {
        return true;
    }
    return domain.includes('mddclass.com') || domain.includes('sksight.com') || domain.includes('hujiang.com');
}

function withMddclassStableDeviceContext(payload) {
    if (login_name === 'sihaigongkao' && payload && typeof payload === 'object') {
        payload.auth_context = Object.assign({}, payload.auth_context || {}, {companyDomain: 'sihaigongkao', userDomain: 'hs'});
    }
    if (!mddclassDevice || typeof mddclassDevice.applyMddclassDeviceContext !== 'function') {
        return payload;
    }
    const cookies_obj = readCookiesObject();
    return mddclassDevice.applyMddclassDeviceContext(payload, {
        existingPayload: cookies_obj[login_name],
        loginName: login_name,
    });
}

function filterMddclassCookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isMddclassCookie(cookie)) {
            return;
        }
        const key = String(cookie.name || '');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function hasMddclassLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterMddclassCookies(cookies));
    if (MDDCLASS_LOGIN_USE_WEB_PAGE) {
        return !!cookie_map.ClubAuth;
    }
    return MDDCLASS_AUTH_COOKIE_NAMES.some((name) => !!cookie_map[name]);
}

function trySaveMddclassCookies(cookies) {
    const filtered_cookies = filterMddclassCookies(cookies);
    if (!hasMddclassLoginCookies(filtered_cookies)) {
        return false;
    }
    const cookie_value = buildCookieValue(filtered_cookies);
    if (!cookie_value) {
        return false;
    }
    const cookies_obj = readCookiesObject();
    const existing_value = cookies_obj[login_name];
    let payload = {};
    if (typeof existing_value === 'string') {
        try {
            const parsed = JSON.parse(existing_value);
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                payload = Object.assign({}, parsed);
            }
        } catch (error) {
            ;
        }
    } else if (existing_value && typeof existing_value === 'object' && !Array.isArray(existing_value)) {
        payload = Object.assign({}, existing_value);
    }
    const cookie_map = buildCookieMap(filtered_cookies);
    payload.cookie = cookie_value;
    payload.cookieValue = cookie_value;
    payload.cookies = cookie_map;
    if (!cookie_map.access_token && !cookie_map.hj_token) {
        const auth_context = Object.assign({}, payload.auth_context || payload.authContext || {});
        for (const key of ['access_token', 'accessToken', 'refresh_token', 'refreshToken']) {
            delete auth_context[key];
            delete payload[key];
        }
        payload.auth_context = auth_context;
    }
    payload = normalizeMddclassLoginPayload(payload, filtered_cookies);
    saveLoginCookieData(JSON.stringify(payload));
    return true;
}

function normalizeMddclassTargetUrl(target_url) {
    target_url = String(target_url || '').trim();
    if (!target_url || target_url === MDDCLASS_WEB_LOGIN_URL) {
        return MDDCLASS_DEFAULT_TARGET_URL;
    }
    try {
        const parsed = new URL(target_url);
        const host = String(parsed.hostname || '').toLowerCase();
        if (host.endsWith('mddclass.com') || host.endsWith('sksight.com')) {
            return parsed.toString();
        }
    } catch (error) {
        ;
    }
    return MDDCLASS_DEFAULT_TARGET_URL;
}

function buildMddclassWebLoginUrl(target_url) {
    const target = normalizeMddclassTargetUrl(target_url);
    return 'https://pass.mddclass.com/school/?business_domain=yyy_cctob&bireg=&url=' + encodeURIComponent(target);
}

function mddclassCookieUrls(target_url) {
    const urls = [
        'https://www.mddclass.com/',
        'https://pass.mddclass.com/',
        'https://access.mddclass.com/',
        'https://sksight.com/',
        'https://webapi.sksight.com/',
    ];
    try {
        const parsed = new URL(normalizeMddclassTargetUrl(target_url));
        if (parsed.hostname) {
            urls.unshift(parsed.origin + '/');
            if (parsed.hostname.endsWith('.mddclass.com')) {
                const prefix = parsed.hostname.split('.')[0].replace(/-m$/i, '');
                if (prefix && !['www', 'm', 'pass', 'access', 'service'].includes(prefix)) {
                    urls.unshift('https://' + prefix + '-m.mddclass.com/');
                }
            }
        }
    } catch (error) {
        ;
    }
    return urls.filter((url, index) => url && urls.indexOf(url) === index);
}

function mddclassStoredCookieValue() {
    const value = readStoredLoginPayload(login_name);
    if (typeof value === 'string') {
        try {
            const payload = JSON.parse(value);
            if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
                return String(payload.cookie || payload.cookieValue || '').trim();
            }
        } catch (error) {
            ;
        }
        return String(value || '').trim();
    }
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        return String(value.cookie || value.cookieValue || '').trim();
    }
    return '';
}

async function restoreMddclassStoredCookies(target_session, target_url) {
    if ((login_name !== 'mddclass' && login_name !== 'sihaigongkao') || !MDDCLASS_LOGIN_USE_WEB_PAGE || !target_session) {
        return;
    }
    const cookie_value = mddclassStoredCookieValue();
    if (!cookie_value) {
        return;
    }
    await setSessionCookieValue(target_session, cookie_value, mddclassCookieUrls(target_url));
}

function mddclassHeaderValue(headers, wanted_name) {
    wanted_name = String(wanted_name || '').toLowerCase();
    for (const key of Object.keys(headers || {})) {
        if (String(key).toLowerCase() === wanted_name) {
            return String(headers[key] || '').trim();
        }
    }
    return '';
}

function rememberMddclassRequestContext(details) {
    if ((login_name !== 'mddclass' && login_name !== 'sihaigongkao') || !MDDCLASS_LOGIN_USE_WEB_PAGE || !details) {
        return;
    }
    const url = String(details.url || '');
    const headers = details.requestHeaders || {};
    const context = {};
    const host = getHostnameFromUrl(url);
    let parsed = null;
    try {
        parsed = new URL(url);
    } catch (error) {
        parsed = null;
    }
    if (parsed) {
        for (const key of ['ocsAccessToken', 'ocs_access_token', 'ocsPlayerAccessToken', 'ocs_player_access_token', 'playerAccessToken', 'player_access_token']) {
            const value = parsed.searchParams.get(key);
            if (value) {
                context.playerAccessToken = value;
                context.ocsAccessToken = value;
                break;
            }
        }
    }
    const tenant_id = (
        mddclassHeaderValue(headers, 'X-Tenant-Id')
        || mddclassHeaderValue(headers, 'X-Tenant-ID')
        || mddclassHeaderValue(headers, 'tenantId')
    );
    if (tenant_id) {
        context.tenantId = tenant_id;
    }
    const fe_auth = mddclassHeaderValue(headers, 'X-FE-Auth');
    if (fe_auth) {
        context.feAuth = fe_auth;
    }
    const user_sign = mddclassHeaderValue(headers, 'X-User-Sign');
    if (user_sign) {
        context.userSign = user_sign;
    }
    const keys_encrypt = mddclassHeaderValue(headers, 'X-Keys-Encrypt');
    if (keys_encrypt) {
        context.keysEncrypt = keys_encrypt;
    }
    const hj_user_agent = mddclassHeaderValue(headers, 'HJUserAgent');
    if (hj_user_agent) {
        context.HJUserAgent = hj_user_agent;
    }
    const company = mddclassHeaderValue(headers, 'X-CC-COMPANY');
    if (company) {
        context.companyDomain = company;
    } else if (host.endsWith('.mddclass.com')) {
        const prefix = host.split('.')[0].replace(/-m$/i, '');
        if (prefix && !['www', 'm', 'pass', 'access', 'service'].includes(prefix)) {
            context.companyDomain = prefix;
        }
    }
    if (parsed && /\/v\/(\d+)/.test(parsed.pathname || '')) {
        const match = (parsed.pathname || '').match(/\/v\/(\d+)/);
        if (match) {
            context.lastVideoId = match[1];
        }
    }
    if (!Object.keys(context).length) {
        return;
    }
    mddclass_request_context = Object.assign({}, mddclass_request_context || {}, context);
}

function maybeNavigateMddclassTarget(win) {
    if (
        (login_name !== 'mddclass' && login_name !== 'sihaigongkao')
        || !MDDCLASS_LOGIN_USE_WEB_PAGE
        || mddclass_target_navigated
        || !isWindowAlive(win)
    ) {
        return;
    }
    const target = normalizeMddclassTargetUrl(typeof mddclass_target_url !== 'undefined' ? mddclass_target_url : '');
    if (!target || target === MDDCLASS_DEFAULT_TARGET_URL) {
        return;
    }
    const current_url = getSafeWindowUrl(win);
    if (!current_url || current_url.indexOf('pass.mddclass.com') !== -1 || current_url === target) {
        return;
    }
    mddclass_target_navigated = true;
    setTimeout(() => {
        if (isWindowAlive(win) && getSafeWindowUrl(win) !== target) {
            win.loadURL(target);
        }
    }, 800);
}

function extractMddclassTokenFromValue(value) {
    if (value === undefined || value === null) {
        return '';
    }
    if (typeof value === 'string') {
        const text = value.trim();
        if (!text) {
            return '';
        }
        try {
            return extractMddclassTokenFromValue(JSON.parse(text));
        } catch (error) {
            ;
        }
        if (/^[A-Za-z0-9._~+-]{16,220}$/.test(text)) {
            return text;
        }
        const match = text.match(/(?:ocsAccessToken|ocs_access_token|ocsPlayerAccessToken|playerAccessToken|accessToken|access_token|token)["'\s:=]+([A-Za-z0-9._~+-]{16,220})/i);
        return match ? match[1] : '';
    }
    if (Array.isArray(value)) {
        for (const item of value) {
            const token = extractMddclassTokenFromValue(item);
            if (token) {
                return token;
            }
        }
        return '';
    }
    if (typeof value !== 'object') {
        return '';
    }
    const direct_keys = [
        'ocsAccessToken', 'ocs_access_token', 'ocsPlayerAccessToken', 'ocs_player_access_token',
        'playerAccessToken', 'player_access_token',
    ];
    for (const key of direct_keys) {
        const token = extractMddclassTokenFromValue(value[key]);
        if (token) {
            return token;
        }
    }
    for (const key of Object.keys(value)) {
        if (String(key).toLowerCase().includes('token') || String(key).toLowerCase().includes('player')) {
            const token = extractMddclassTokenFromValue(value[key]);
            if (token) {
                return token;
            }
        }
    }
    return '';
}

function extractMddclassExplicitOcsToken(source) {
    if (!source || typeof source !== 'object' || Array.isArray(source)) {
        return '';
    }
    const direct_keys = [
        'ocsAccessToken', 'ocs_access_token', 'ocsPlayerAccessToken', 'ocs_player_access_token',
        'playerAccessToken', 'player_access_token', 'hrefToken',
    ];
    for (const key of direct_keys) {
        const token = extractMddclassTokenFromValue(source[key]);
        if (token) {
            return token;
        }
    }
    for (const key of Object.keys(source)) {
        const lower = String(key).toLowerCase();
        if (!(lower.includes('ocs') || lower.includes('player'))) {
            continue;
        }
        const token = extractMddclassTokenFromValue(source[key]);
        if (token) {
            return token;
        }
    }
    return '';
}

function normalizeMddclassLoginPayload(result, fallback_cookies = null) {
    if (!result || typeof result !== 'object' || Array.isArray(result)) {
        result = {};
    }
    let cookie_candidates = fallback_cookies || [];
    if (!Array.isArray(cookie_candidates) && result.cookies && typeof result.cookies === 'object' && !Array.isArray(result.cookies)) {
        cookie_candidates = Object.keys(result.cookies).map((name) => ({ name, value: result.cookies[name] }));
    }
    const filtered_cookies = filterMddclassCookies(Array.isArray(cookie_candidates) ? cookie_candidates : []);
    const cookie_map = Object.assign({}, result.cookies && !Array.isArray(result.cookies) ? result.cookies : {}, buildCookieMap(filtered_cookies));
    const cookie_value = String(
        result.cookieValue
        || result.cookie
        || result.cookie_string
        || result.cookie_value
        || buildCookieValue(filtered_cookies)
        || ''
    ).trim();
    const payload = Object.assign({}, result);
    if (cookie_value) {
        payload.cookie = cookie_value;
        payload.cookieValue = cookie_value;
    }
    if (Object.keys(cookie_map).length) {
        payload.cookies = cookie_map;
    }
    const auth_context = Object.assign({}, payload.auth_context || payload.authContext || {});
    for (const source of [payload, payload.login || {}, payload.user || {}, payload.windowGlobals || {}]) {
        if (!source || typeof source !== 'object' || Array.isArray(source)) {
            continue;
        }
        for (const [source_key, target_key] of [
            ['accessToken', 'accessToken'], ['access_token', 'accessToken'],
            ['refreshToken', 'refreshToken'], ['refresh_token', 'refreshToken'],
            ['uid', 'uid'], ['userId', 'uid'], ['user_id', 'uid'], ['UserId', 'uid'],
            ['companyDomain', 'companyDomain'], ['company_domain', 'companyDomain'],
            ['companyId', 'companyId'], ['company_id', 'companyId'],
            ['tenantId', 'tenantId'], ['tenant_id', 'tenantId'],
            ['HJUserAgent', 'HJUserAgent'],
        ]) {
            const value = source[source_key];
            if (value !== undefined && value !== null && String(value).trim() && !auth_context[target_key]) {
                auth_context[target_key] = String(value).trim();
            }
        }
    }
    const normal_access_token = cookie_map.access_token || cookie_map.hj_token || auth_context.accessToken || auth_context.access_token || '';
    if (normal_access_token) {
        auth_context.accessToken = normal_access_token;
        auth_context.access_token = normal_access_token;
    }
    const refresh_token = cookie_map.refresh_token || auth_context.refreshToken || auth_context.refresh_token || '';
    if (refresh_token) {
        auth_context.refreshToken = refresh_token;
        auth_context.refresh_token = refresh_token;
    }
    if (cookie_map.HJUserAgent && !auth_context.HJUserAgent) {
        auth_context.HJUserAgent = cookie_map.HJUserAgent;
    }
    if (payload.requestContext && typeof payload.requestContext === 'object' && !Array.isArray(payload.requestContext)) {
        for (const [source_key, target_key] of [
            ['tenantId', 'tenantId'], ['tenant_id', 'tenantId'],
            ['companyDomain', 'companyDomain'], ['company_domain', 'companyDomain'],
            ['companyId', 'companyId'], ['company_id', 'companyId'],
            ['userSign', 'userSign'], ['user_sign', 'userSign'],
            ['feAuth', 'feAuth'], ['fe_auth', 'feAuth'],
            ['keysEncrypt', 'keysEncrypt'], ['keys_encrypt', 'keysEncrypt'],
            ['HJUserAgent', 'HJUserAgent'],
        ]) {
            const value = payload.requestContext[source_key];
            if (value !== undefined && value !== null && String(value).trim() && !auth_context[target_key]) {
                auth_context[target_key] = String(value).trim();
            }
        }
    }
    const ocs_token = (
        extractMddclassExplicitOcsToken(auth_context)
        || extractMddclassExplicitOcsToken(payload.windowGlobals || {})
        || extractMddclassExplicitOcsToken(payload.localStorage || {})
        || extractMddclassExplicitOcsToken(payload.sessionStorage || {})
        || extractMddclassExplicitOcsToken(payload.requestContext || {})
        || extractMddclassExplicitOcsToken(payload)
    );
    if (ocs_token) {
        auth_context.ocsAccessToken = ocs_token;
        auth_context.ocs_access_token = ocs_token;
    }
    if (Object.keys(auth_context).length) {
        payload.auth_context = auth_context;
    }
    return withMddclassStableDeviceContext(payload);
}

function collectMddclassWebLoginResult(win, fallback_cookies = null) {
    if (!isWindowAlive(win)) {
        return Promise.resolve(null);
    }
    return win.webContents.executeJavaScript(`
        (() => {
            function safeGet(storage, key) {
                try {
                    return storage && storage.getItem(key) || '';
                } catch (error) {
                    return '';
                }
            }
            function dumpStorage(storage) {
                const result = {};
                try {
                    if (!storage) {
                        return result;
                    }
                    for (let i = 0; i < storage.length; i += 1) {
                        const key = storage.key(i);
                        if (!key) {
                            continue;
                        }
                        const lower = String(key).toLowerCase();
                        if (
                            lower.includes('token')
                            || lower.includes('user')
                            || lower.includes('uid')
                            || lower.includes('company')
                            || lower.includes('tenant')
                            || lower.includes('player')
                            || lower.includes('tracert')
                            || lower.includes('device')
                            || lower.includes('hj')
                        ) {
                            result[key] = storage.getItem(key);
                        }
                    }
                } catch (error) {
                    ;
                }
                return result;
            }
            const localStorageData = dumpStorage(window.localStorage);
            const sessionStorageData = dumpStorage(window.sessionStorage);
            const gdata = window.GDATA && typeof window.GDATA === 'object' ? window.GDATA : {};
            const playerSettings = window.PlayerSettings && typeof window.PlayerSettings === 'object' ? window.PlayerSettings : {};
            const ocsPlayerSettings = window.OCSPlayerSettings && typeof window.OCSPlayerSettings === 'object' ? window.OCSPlayerSettings : {};
            const requestContext = ${JSON.stringify(mddclass_request_context || {})};
            const href = window.location && window.location.href || '';
            const hrefTokenMatch = href.match(/[?#&](?:ocsAccessToken|ocs_access_token|ocsPlayerAccessToken|ocs_player_access_token|playerAccessToken|player_access_token)=([^&#]+)/i);
            return {
                success: true,
                href: href,
                title: document.title || '',
                cookies: (document.cookie || '').split(';').reduce((acc, item) => {
                    const pos = item.indexOf('=');
                    if (pos > 0) {
                        acc[item.slice(0, pos).trim()] = item.slice(pos + 1).trim();
                    }
                    return acc;
                }, {}),
                localStorage: localStorageData,
                sessionStorage: sessionStorageData,
                windowGlobals: {
                    uid: gdata.userId || gdata.uid || '',
                    userId: gdata.userId || gdata.uid || '',
                    companyDomain: gdata.companyDomain || '',
                    companyId: gdata.companyId || (gdata.companyInfo && gdata.companyInfo.companyId) || '',
                    tenantId: playerSettings.tenantId || ocsPlayerSettings.tenantId || '',
                    ocsAccessToken: playerSettings.accessToken || ocsPlayerSettings.accessToken || '',
                    playerAccessToken: playerSettings.accessToken || ocsPlayerSettings.accessToken || '',
                    hrefToken: hrefTokenMatch ? decodeURIComponent(hrefTokenMatch[1]) : '',
                    HJUserAgent: safeGet(window.localStorage, 'HJUserAgent') || safeGet(window.sessionStorage, 'HJUserAgent') || '',
                },
                requestContext: requestContext,
            };
        })();
    `, true).then((result) => {
        if (!result || typeof result !== 'object') {
            return null;
        }
        return normalizeMddclassLoginPayload(result, fallback_cookies);
    }).catch(() => null);
}

function hasMddclassUsefulWebContext(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        return false;
    }
    const auth_context = payload.auth_context || payload.authContext || {};
    const globals = payload.windowGlobals || {};
    const local_storage = payload.localStorage || {};
    const session_storage = payload.sessionStorage || {};
    return !!(
        extractMddclassExplicitOcsToken(auth_context)
        || extractMddclassExplicitOcsToken(globals)
        || extractMddclassExplicitOcsToken(local_storage)
        || extractMddclassExplicitOcsToken(session_storage)
        || extractMddclassExplicitOcsToken(payload.requestContext || {})
        || extractMddclassExplicitOcsToken(payload)
    );
}

function saveMddclassLoginPayload(payload, options = {}) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        return false;
    }
    payload = withMddclassStableDeviceContext(payload);
    const cookie_value = String(payload.cookie || payload.cookieValue || '').trim();
    const cookie_map = payload.cookies && typeof payload.cookies === 'object' && !Array.isArray(payload.cookies)
        ? payload.cookies
        : {};
    if (!cookie_value && !Object.keys(cookie_map).length) {
        return false;
    }
    if (!hasMddclassLoginCookies(Object.keys(cookie_map).map((name) => ({ name, value: cookie_map[name] })))) {
        return false;
    }
    if (options.requireUsefulContext && !hasMddclassUsefulWebContext(payload)) {
        return false;
    }
    saveLoginCookieData(JSON.stringify(payload));
    return true;
}

function trySaveMddclassLoginResult(win, fallback_cookies = null, allow_cookie_fallback = false) {
    if ((login_name !== 'mddclass' && login_name !== 'sihaigongkao') || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    const has_login_cookies = !!(fallback_cookies && hasMddclassLoginCookies(fallback_cookies));
    if (MDDCLASS_LOGIN_USE_WEB_PAGE && has_login_cookies && !mddclass_first_login_cookie_at) {
        mddclass_first_login_cookie_at = Date.now();
    }
    if (MDDCLASS_LOGIN_USE_WEB_PAGE) {
        return collectMddclassWebLoginResult(win, fallback_cookies).then((payload) => {
            if (saveMddclassLoginPayload(payload, { requireUsefulContext: !has_login_cookies })) {
                return true;
            }
            if (has_login_cookies && trySaveMddclassCookies(fallback_cookies)) {
                return true;
            }
            return false;
        }).catch(() => {
            if (has_login_cookies && trySaveMddclassCookies(fallback_cookies)) {
                return true;
            }
            return false;
        });
    }
    return win.webContents.executeJavaScript('window.__MDDCLASS_LOGIN_RESULT__', true)
    .then((result) => {
        if (result && result.success && result.cookieValue) {
            const payload = normalizeMddclassLoginPayload(
                typeof result.cookieValue === 'string' && result.cookieValue.trim().startsWith('{')
                    ? JSON.parse(result.cookieValue)
                    : result,
                fallback_cookies
            );
            return saveMddclassLoginPayload(payload);
        }
        if (allow_cookie_fallback && fallback_cookies && trySaveMddclassCookies(fallback_cookies)) {
            return true;
        }
        return false;
    }).catch(() => {
        if (allow_cookie_fallback && fallback_cookies && trySaveMddclassCookies(fallback_cookies)) {
            return true;
        }
        return false;
    });
}


function filterAhuCookies(cookies) {
    return (cookies || []).filter((cookie) => {
        if (!cookie || !cookie.name || !cookie.value) {
            return false;
        }
        return AHU_COOKIE_NAMES.includes(String(cookie.name));
    });
}

function hasAhuLoginCookies(cookies) {
    let cookie_map = buildCookieMap(filterAhuCookies(cookies));
    return !!(cookie_map.PHPSESSID || cookie_map.laravel_session);
}

function validateAhuCookieValue(cookie_value) {
    return new Promise((resolve) => {
        if (!cookie_value) {
            resolve(false);
            return;
        }
        const request = https.get('https://www.ahuyikao.com/center/mycourse.html?_=' + Date.now(), {
            headers: {
                'Cookie': cookie_value,
                'Referer': 'https://www.ahuyikao.com/',
                'User-Agent': DEFAULT_BROWSER_USER_AGENT,
            },
        }, (response) => {
            let body = '';
            response.setEncoding('utf8');
            response.on('data', (chunk) => {
                body += chunk;
            });
            response.on('end', () => {
                const status_code = Number(response.statusCode) || 0;
                const location = String((response.headers || {}).location || '').toLowerCase();
                resolve(
                    status_code >= 200
                    && status_code < 400
                    && !location.includes('/login/')
                    && (
                        body.includes('退出登录')
                        || body.includes('yxg-mc-student')
                        || body.includes('/login/loginout.html')
                    )
                );
            });
        });
        request.on('error', () => resolve(false));
        request.setTimeout(10000, () => {
            request.destroy();
            resolve(false);
        });
    });
}

function trySaveAhuCookies(cookies) {
    if (ahu_save_inflight) {
        return;
    }
    const filtered_cookies = filterAhuCookies(cookies);
    if (!hasAhuLoginCookies(filtered_cookies)) {
        return;
    }
    const cookie_value = buildCookieValue(filtered_cookies);
    if (!cookie_value) {
        return;
    }
    ahu_save_inflight = true;
    validateAhuCookieValue(cookie_value).then((valid) => {
        if (!valid) {
            ahu_save_inflight = false;
            return;
        }
        saveLoginCookieValue(cookie_value);
    }).catch(() => {
        ahu_save_inflight = false;
    });
}

function normalizeYunduanDomain(domain) {
    domain = String(domain || '').trim().replace(/^\./, '').toLowerCase();
    return /^[a-z0-9][a-z0-9-]*\.at\.baijiayun\.com$/.test(domain) ? domain : '';
}

function getYunduanDomainFromUrl(url) {
    try {
        return normalizeYunduanDomain(new URL(String(url || '')).hostname);
    } catch (error) {
        return '';
    }
}

function extractYunduanWebUrl(url) {
    url = String(url || '').trim();
    if (!url) {
        return '';
    }
    if (url.indexOf('baijiacloud://') === 0) {
        try {
            const match = url.match(/[?&]urlpath=([^&]+)/) || url.match(/urlpath=([^&]+)/);
            if (match) {
                url = decodeURIComponent(match[1]);
            }
        } catch (error) {
            return '';
        }
    }
    if (getYunduanDomainFromUrl(url)) {
        return url;
    }
    return '';
}

function isYunduanCookie(cookie) {
    if (!cookie || cookie.name !== 'ORGSUPERSESSID' || !cookie.value) {
        return false;
    }
    return !!normalizeYunduanDomain(cookie.domain);
}

function filterYunduanCookies(cookies) {
    return (cookies || []).filter((cookie) => isYunduanCookie(cookie));
}

function hasYunduanLoginCookies(cookies) {
    return filterYunduanCookies(cookies).length > 0;
}

function buildYunduanCookieEntry(cookies) {
    const cookie_list = extractStoredCookieList(filterYunduanCookies(cookies));
    const cookie_value = buildCookieValue(cookie_list);
    const org_cookie = cookie_list.find((cookie) => cookie && cookie.name === 'ORGSUPERSESSID') || {};
    const domain = String(org_cookie.domain || '').trim().replace(/^\./, '').toLowerCase();
    return {
        cookieValue: cookie_value,
        cookieList: cookie_list,
        domain: domain,
        baseUrl: domain ? ('https://' + domain + '/web/course/index') : '',
        savedAt: new Date().toISOString(),
    };
}

function forceYunduanLoginExit(win, delay_ms = 0) {
    setTimeout(() => {
        stopCookiePoll();
        const windows = BrowserWindow.getAllWindows();
        if (win && !win.isDestroyed() && !windows.includes(win)) {
            windows.push(win);
        }
        windows.forEach((browser_window) => {
            if (!browser_window || browser_window.isDestroyed()) {
                return;
            }
            try {
                browser_window.destroy();
            } catch (error) {
                try {
                    browser_window.close();
                } catch (ignored) {
                    ;
                }
            }
        });
        app.quit();
        setTimeout(() => {
            app.exit(0);
        }, 300);
    }, Math.max(0, Number(delay_ms) || 0));
}

function trySaveYunduanCookies(cookies, win = null) {
    if (yunduan_save_inflight) {
        return false;
    }
    if (!hasYunduanLoginCookies(cookies)) {
        return false;
    }
    const cookie_entry = buildYunduanCookieEntry(cookies);
    if (!cookie_entry.cookieValue || !cookie_entry.domain) {
        return false;
    }
    yunduan_save_inflight = true;
    saveLoginCookieData(cookie_entry);
    forceYunduanLoginExit(win, 120);
    return true;
}

function trySaveYunduanRequestCookies(details) {
    if (login_name !== 'yunduan' || yunduan_save_inflight || !details) {
        return;
    }
    const domain = getYunduanDomainFromUrl(details.url);
    if (!domain) {
        return;
    }
    const headers = details.requestHeaders || {};
    const cookie_header = headers.Cookie || headers.cookie || '';
    const cookie_map = parseCookieString(cookie_header);
    if (!cookie_map.ORGSUPERSESSID) {
        return;
    }
    trySaveYunduanCookies([{
        name: 'ORGSUPERSESSID',
        value: cookie_map.ORGSUPERSESSID,
        domain: domain,
        path: '/',
        secure: true,
        httpOnly: true,
    }]);
}

function checkYunduanLoginByCurrentUrl(win, url) {
    if (login_name !== 'yunduan' || yunduan_save_inflight || !win || win.isDestroyed()) {
        return;
    }
    const web_url = extractYunduanWebUrl(url);
    const domain = getYunduanDomainFromUrl(web_url);
    if (!domain) {
        return;
    }
    const queries = [
        {url: web_url},
        {domain: domain},
        {domain: '.' + domain},
        {name: 'ORGSUPERSESSID'},
        {},
    ];
    Promise.all(queries.map((query) => win.webContents.session.cookies.get(query).catch(() => [])))
        .then((cookie_groups) => {
            const cookies = [].concat.apply([], cookie_groups || []);
            if (trySaveYunduanCookies(cookies, win)) {
                return;
            }
            return win.webContents.executeJavaScript('document.cookie', true)
                .then((cookie_string) => {
                    const cookie_map = parseCookieString(cookie_string);
                    if (!cookie_map.ORGSUPERSESSID) {
                        return;
                    }
                    trySaveYunduanCookies([{
                        name: 'ORGSUPERSESSID',
                        value: cookie_map.ORGSUPERSESSID,
                        domain: domain,
                        path: '/',
                        secure: true,
                    }], win);
                });
        })
        .catch(() => {
            ;
        });
}


function getYunduanDeviceCheckSuppressSource() {
    return `
        (function () {
            var SUPPRESSOR_FLAG = '__LEL_YUNDUAN_DEVICE_CHECK_SUPPRESSOR__';
            var STORAGE_KEYS = ['bjy_detection_new_no_more_popup', 'bjy_detection_new_succeed'];
            var DEVICE_WORDS = [
                '\u8bbe\u5907\u68c0\u6d4b', '\u51c6\u5907\u68c0\u6d4b', '\u4e91\u7aef\u8bfe\u5802',
                '\u6444\u50cf\u5934', '\u9ea6\u514b\u98ce', '\u626c\u58f0\u5668', '\u7f51\u7edc\u68c0\u6d4b',
                '\u653e\u5f03\u68c0\u6d4b', '\u4e0d\u518d\u5f39\u51fa'
            ];
            var CLOSE_WORDS = [
                '\u5173\u95ed', '\u53d6\u6d88', '\u8df3\u8fc7', '\u7a0d\u540e', '\u653e\u5f03',
                '\u653e\u5f03\u68c0\u6d4b', '\u4e0d\u518d\u5f39\u51fa', '\u7ee7\u7eed\u8fdb\u5165',
                '\u786e\u8ba4', '\u786e\u5b9a'
            ];
            var EXACT_CONTAINER_SELECTOR = [
                '.bjy-device-detect-dialog', '.bjy-device-detect-dialog.show', '.bjy-detection-box',
                '.twice-confirm-dialog-container', '[data-lel-yunduan-device-hidden="1"]'
            ].join(',');
            var CANDIDATE_SELECTOR = [
                EXACT_CONTAINER_SELECTOR, '[role="dialog"]', '[class*="device"]', '[class*="Device"]',
                '[class*="detect"]', '[class*="Detect"]', '[class*="detection"]', '[class*="Detection"]',
                '[class*="modal"]', '[class*="Modal"]', '[class*="dialog"]', '[class*="Dialog"]',
                '[class*="popup"]', '[class*="Popup"]', '.ant-modal', '.el-dialog', '.ivu-modal',
                '.van-dialog', '.layui-layer'
            ].join(',');
            var CLOSE_SELECTOR = [
                '.bjy-detection-box .close-btn', '.bjy-device-detect-dialog .close-btn', '.close',
                '.close-btn', '.close-button', '.dialog-close', '.modal-close', '.popup-close',
                '.bjy-icon-close', '.icon-close', '.iconfont-close', '.ant-modal-close',
                '.el-dialog__headerbtn', '.ivu-modal-close', '.van-popup__close-icon',
                '.layui-layer-close', '[aria-label="Close"]', '[aria-label="close"]',
                '[title="\u5173\u95ed"]', '[title="Close"]'
            ].join(',');

            function getYunduanUrl(value) {
                value = String(value || '').trim();
                if (!value) {
                    return '';
                }
                if (value.indexOf('baijiacloud://') === 0) {
                    try {
                        var urlpathMatch = value.match(/[?&]urlpath=([^&]+)/) || value.match(/urlpath=([^&]+)/);
                        if (urlpathMatch) {
                            value = decodeURIComponent(urlpathMatch[1]);
                        }
                    } catch (error) {
                        ;
                    }
                }
                if (/^\/\//.test(value)) {
                    value = window.location.protocol + value;
                }
                if (/^\//.test(value)) {
                    value = window.location.origin + value;
                }
                if (/^https?:\/\/[a-z0-9][a-z0-9-]*\.at\.baijiayun\.com(?:[\/?#]|$)/i.test(value)) {
                    return value;
                }
                return '';
            }

            function rememberYunduanUrl(value) {
                var url = getYunduanUrl(value);
                if (!url) {
                    return '';
                }
                window.__LEL_YUNDUAN_LAST_ENTER_URL__ = url;
                try { window.localStorage && window.localStorage.setItem('__LEL_YUNDUAN_LAST_ENTER_URL__', url); } catch (error) { ; }
                return url;
            }

            function enterYunduanWeb(value) {
                var url = rememberYunduanUrl(value);
                if (!url) {
                    return false;
                }
                try {
                    window.location.href = url;
                    return true;
                } catch (error) {
                    return false;
                }
            }

            function hookWindowOpen() {
                if (window.__LEL_YUNDUAN_WINDOW_OPEN_HOOKED__) {
                    return;
                }
                window.__LEL_YUNDUAN_WINDOW_OPEN_HOOKED__ = true;
                var originalOpen = window.open;
                window.open = function (url) {
                    if (enterYunduanWeb(url)) {
                        return window;
                    }
                    return originalOpen.apply(window, arguments);
                };
                document.addEventListener('click', function (event) {
                    var target = event && event.target;
                    while (target && target !== document) {
                        var href = target.getAttribute && target.getAttribute('href');
                        if (href && enterYunduanWeb(href)) {
                            event.preventDefault();
                            event.stopPropagation();
                            return false;
                        }
                        target = target.parentNode;
                    }
                    return true;
                }, true);
            }

            function setPersistedFlags() {
                for (var i = 0; i < STORAGE_KEYS.length; i += 1) {
                    var key = STORAGE_KEYS[i];
                    try { window.localStorage && window.localStorage.setItem(key, 'true'); } catch (error) { ; }
                    try { window.sessionStorage && window.sessionStorage.setItem(key, 'true'); } catch (error) { ; }
                    try { document.cookie = key + '=true; path=/; max-age=31536000; SameSite=Lax'; } catch (error) { ; }
                }
            }

            function hasAnyWord(text, words) {
                text = String(text || '');
                for (var i = 0; i < words.length; i += 1) {
                    if (text.indexOf(words[i]) >= 0) {
                        return true;
                    }
                }
                return false;
            }

            function getText(el) {
                return String((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
            }

            function getClassName(el) {
                return String((el && el.className) || '');
            }

            function isVisible(el) {
                if (!el || !el.ownerDocument || !el.getClientRects || el.getClientRects().length === 0) {
                    return false;
                }
                var style = window.getComputedStyle(el);
                return !!style && style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) !== 0;
            }

            function containsLoginInput(el) {
                try {
                    return !!(el && el.querySelector && el.querySelector('input[type="password"],input[name*="password"],input[autocomplete*="password"]'));
                } catch (error) {
                    return false;
                }
            }

            function ensureStyle() {
                try {
                    var parent = document.head || document.documentElement;
                    if (!parent || document.getElementById('lel-yunduan-device-check-style')) {
                        return;
                    }
                    var style = document.createElement('style');
                    style.id = 'lel-yunduan-device-check-style';
                    style.textContent = [
                        '.bjy-device-detect-dialog,.bjy-device-detect-dialog.show,.bjy-detection-box{display:none!important;visibility:hidden!important;opacity:0!important;pointer-events:none!important;}',
                        '.bjy-device-detect-dialog *,.bjy-detection-box *{pointer-events:none!important;}',
                        '[data-lel-yunduan-device-hidden="1"]{display:none!important;visibility:hidden!important;opacity:0!important;pointer-events:none!important;}'
                    ].join('\n');
                    parent.appendChild(style);
                } catch (error) {
                    ;
                }
            }

            function clickElement(el, force) {
                if (!el || (!force && !isVisible(el))) {
                    return false;
                }
                try {
                    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                    el.click();
                    return true;
                } catch (error) {
                    try {
                        el.click();
                        return true;
                    } catch (ignored) {
                        return false;
                    }
                }
            }

            function hideElement(el) {
                if (!el || !el.style || containsLoginInput(el)) {
                    return false;
                }
                try { el.setAttribute('data-lel-yunduan-device-hidden', '1'); } catch (error) { ; }
                el.style.setProperty('display', 'none', 'important');
                el.style.setProperty('visibility', 'hidden', 'important');
                el.style.setProperty('opacity', '0', 'important');
                el.style.setProperty('pointer-events', 'none', 'important');
                return true;
            }

            function hideLikelyOverlay(el) {
                var changed = hideElement(el);
                var parent = el && el.parentElement;
                var depth = 0;
                while (parent && parent !== document.body && depth < 4) {
                    var style = window.getComputedStyle(parent);
                    var position = style && style.position;
                    var zIndex = Number((style && style.zIndex) || 0);
                    if ((position === 'fixed' || position === 'absolute') && zIndex >= 1 && !containsLoginInput(parent)) {
                        changed = hideElement(parent) || changed;
                    }
                    parent = parent.parentElement;
                    depth += 1;
                }
                return changed;
            }

            function closeInside(container) {
                var noMoreList = Array.prototype.slice.call(container.querySelectorAll('.prepare-checkbox-input,input[type="checkbox"]'));
                for (var i = 0; i < noMoreList.length; i += 1) {
                    if (!noMoreList[i].checked) {
                        clickElement(noMoreList[i], true);
                    }
                }
                var closeList = Array.prototype.slice.call(container.querySelectorAll(CLOSE_SELECTOR));
                for (var j = 0; j < closeList.length; j += 1) {
                    if (clickElement(closeList[j], true)) {
                        return true;
                    }
                }
                var clickableList = Array.prototype.slice.call(container.querySelectorAll('button,a,span,div'));
                for (var k = 0; k < clickableList.length; k += 1) {
                    var text = getText(clickableList[k]);
                    if (text.length <= 12 && hasAnyWord(text, CLOSE_WORDS) && clickElement(clickableList[k], true)) {
                        return true;
                    }
                }
                return false;
            }

            function looksLikeDeviceCheck(el) {
                if (!el) {
                    return false;
                }
                var className = getClassName(el);
                if (/bjy-device-detect-dialog|bjy-detection-box|twice-confirm-dialog-container/i.test(className)) {
                    return true;
                }
                var text = getText(el);
                if (!hasAnyWord(text, DEVICE_WORDS)) {
                    return false;
                }
                if (/device|detect|detection|modal|dialog|popup|layer/i.test(className)) {
                    return true;
                }
                var style = window.getComputedStyle(el);
                return !!style && (style.position === 'fixed' || style.position === 'absolute') && Number(style.zIndex || 0) >= 1;
            }

            function closeDeviceCheck() {
                setPersistedFlags();
                ensureStyle();
                var changed = false;
                var containers = Array.prototype.slice.call(document.querySelectorAll(CANDIDATE_SELECTOR));
                for (var i = 0; i < containers.length; i += 1) {
                    var container = containers[i];
                    if (!looksLikeDeviceCheck(container)) {
                        continue;
                    }
                    closeInside(container);
                    changed = hideLikelyOverlay(container) || changed;
                }
                return changed;
            }

            function patchDetectionNew(detection) {
                if (!detection || detection.__LEL_YUNDUAN_PATCHED__) {
                    return detection;
                }
                try { Object.defineProperty(detection, '__LEL_YUNDUAN_PATCHED__', { value: true }); } catch (error) { ; }
                detection.hasCheckedNoMorePopup = function () {
                    setPersistedFlags();
                    return true;
                };
                detection.hasDetectSucceeded = function () {
                    setPersistedFlags();
                    return true;
                };
                if (detection.methods) {
                    detection.methods.toggleNoMorePopup = function () {
                        setPersistedFlags();
                        this.hasCheckedNoMorePopup = true;
                    };
                    detection.methods.cancelDetect = function () {
                        setPersistedFlags();
                        if (this && typeof this.onDetectResult === 'function') {
                            this.onDetectResult(false);
                        }
                    };
                    detection.methods.exitDetect = function () {
                        setPersistedFlags();
                        if (this && typeof this.onDetectResult === 'function') {
                            this.onDetectResult(true, {});
                        }
                    };
                }
                detection.afterMount = function () {
                    setPersistedFlags();
                    setTimeout(closeDeviceCheck, 0);
                };
                if (typeof detection.create === 'function') {
                    var originalCreate = detection.create;
                    detection.create = function (options) {
                        setPersistedFlags();
                        if (options && options.props && typeof options.props.onDetectResult === 'function') {
                            setTimeout(function () { options.props.onDetectResult(true, {}); }, 0);
                        }
                        try {
                            return originalCreate.apply(this, arguments);
                        } finally {
                            setTimeout(closeDeviceCheck, 0);
                        }
                    };
                }
                return detection;
            }

            function patchBjyObject(bjy) {
                if (!bjy || bjy.__LEL_YUNDUAN_BJY_PATCHED__) {
                    return;
                }
                try { Object.defineProperty(bjy, '__LEL_YUNDUAN_BJY_PATCHED__', { value: true }); } catch (error) { ; }
                var currentDetection = bjy.DetectionNew;
                try {
                    Object.defineProperty(bjy, 'DetectionNew', {
                        configurable: true,
                        enumerable: true,
                        get: function () { return currentDetection; },
                        set: function (value) { currentDetection = patchDetectionNew(value); }
                    });
                    if (currentDetection) {
                        currentDetection = patchDetectionNew(currentDetection);
                    }
                } catch (error) {
                    if (bjy.DetectionNew) {
                        patchDetectionNew(bjy.DetectionNew);
                    }
                }
                var currentLogin = bjy.Login;
                function patchLogin(login) {
                    if (!login || login.__LEL_YUNDUAN_LOGIN_PATCHED__) {
                        return login;
                    }
                    try { Object.defineProperty(login, '__LEL_YUNDUAN_LOGIN_PATCHED__', { value: true }); } catch (error) { ; }
                    if (typeof login.create === 'function') {
                        var originalCreate = login.create;
                        login.create = function (options) {
                            options = options || {};
                            var originalWebHandler = options.webURLHandler;
                            options.webURLHandler = function (url) {
                                if (enterYunduanWeb(url)) {
                                    return;
                                }
                                if (typeof originalWebHandler === 'function') {
                                    return originalWebHandler.apply(this, arguments);
                                }
                                window.location.href = url;
                            };
                            var originalClientHandler = options.clientCodeinHandler;
                            options.clientCodeinHandler = function (url) {
                                if (enterYunduanWeb(url)) {
                                    return;
                                }
                                if (typeof originalClientHandler === 'function') {
                                    return originalClientHandler.apply(this, arguments);
                                }
                                window.location.href = url;
                            };
                            return originalCreate.apply(this, arguments);
                        };
                    }
                    return login;
                }
                try {
                    Object.defineProperty(bjy, 'Login', {
                        configurable: true,
                        enumerable: true,
                        get: function () { return currentLogin; },
                        set: function (value) { currentLogin = patchLogin(value); }
                    });
                    if (currentLogin) {
                        currentLogin = patchLogin(currentLogin);
                    }
                } catch (error) {
                    if (bjy.Login) {
                        patchLogin(bjy.Login);
                    }
                }
            }

            function hookBjyGlobal() {
                if (window.BJY) {
                    patchBjyObject(window.BJY);
                    return;
                }
                if (window.__LEL_YUNDUAN_BJY_GLOBAL_HOOK__) {
                    return;
                }
                window.__LEL_YUNDUAN_BJY_GLOBAL_HOOK__ = true;
                var currentBjy;
                try {
                    Object.defineProperty(window, 'BJY', {
                        configurable: true,
                        enumerable: true,
                        get: function () { return currentBjy; },
                        set: function (value) {
                            currentBjy = value;
                            patchBjyObject(value);
                        }
                    });
                } catch (error) {
                    ;
                }
            }

            setPersistedFlags();
            hookBjyGlobal();
            hookWindowOpen();
            ensureStyle();
            if (!window[SUPPRESSOR_FLAG]) {
                window[SUPPRESSOR_FLAG] = true;
                window.__LEL_YUNDUAN_CLOSE_DEVICE_CHECK__ = closeDeviceCheck;
                var runCount = 0;
                var timer = setInterval(function () {
                    runCount += 1;
                    hookBjyGlobal();
                    hookWindowOpen();
                    closeDeviceCheck();
                    if (runCount >= 180) {
                        clearInterval(timer);
                    }
                }, 300);
                try {
                    var observer = new MutationObserver(function () {
                        hookBjyGlobal();
                        closeDeviceCheck();
                    });
                    observer.observe(document.documentElement || document.body, { childList: true, subtree: true });
                    setTimeout(function () { observer.disconnect(); }, 60000);
                } catch (error) {
                    ;
                }
            }
            return closeDeviceCheck();
        })();
    `;
}

function buildYunduanDeviceCheckSuppressScript() {
    return getYunduanDeviceCheckSuppressSource();
}

function ensureYunduanDeviceCheckPreloadScript() {
    try {
        const preload_path = path.join(app.getPath('userData'), 'yunduan-device-check-preload.js');
        const preload_source = "'use strict';\n" + getYunduanDeviceCheckSuppressSource();
        fs.writeFileSync(preload_path, preload_source, 'utf8');
        return preload_path;
    } catch (error) {
        return null;
    }
}

function suppressYunduanDeviceCheckPopup(win, delay_ms = 0) {
    if (login_name !== 'yunduan') {
        return;
    }
    setTimeout(() => {
        if (!isWindowAlive(win)) {
            return;
        }
        win.webContents.executeJavaScript(buildYunduanDeviceCheckSuppressScript(), true).catch(() => {
            ;
        });
    }, Math.max(0, Number(delay_ms) || 0));
}

function isYunduanDeviceCheckUrl(url) {
    const lower_url = String(url || '').toLowerCase();
    return lower_url.includes('/page/detectionnew/')
        || lower_url.includes('detectionnew')
        || lower_url.includes('bjy-device-detect')
        || lower_url.includes('device-detect');
}

function installYunduanDeviceCheckRequestBlocker(login_session) {
    if (!login_session || !login_session.webRequest || login_session.__LEL_YUNDUAN_DEVICE_BLOCKER__) {
        return;
    }
    login_session.__LEL_YUNDUAN_DEVICE_BLOCKER__ = true;
    login_session.webRequest.onBeforeRequest(
        {urls: ['*://*/*detectionNew*', '*://*/*device-detect*', '*://*/*bjy-device-detect*']},
        (details, callback) => {
            if (isYunduanDeviceCheckUrl(details && details.url)) {
                callback({cancel: true});
                return;
            }
            callback({cancel: false});
        }
    );
}

function installYunduanDeviceCheckWindowBlocker(win) {
    if (!win || !win.webContents || win.__LEL_YUNDUAN_DEVICE_WINDOW_BLOCKER__) {
        return;
    }
    win.__LEL_YUNDUAN_DEVICE_WINDOW_BLOCKER__ = true;
    if (typeof win.webContents.setWindowOpenHandler === 'function') {
        win.webContents.setWindowOpenHandler(({url}) => {
            const yunduan_url = extractYunduanWebUrl(url);
            if (yunduan_url) {
                setTimeout(() => {
                    if (isWindowAlive(win)) {
                        win.loadURL(yunduan_url);
                    }
                }, 0);
                return {action: 'deny'};
            }
            if (isYunduanDeviceCheckUrl(url)) {
                return {action: 'deny'};
            }
            return {action: 'allow'};
        });
    }
    win.webContents.on('new-window', (event, url) => {
        const yunduan_url = extractYunduanWebUrl(url);
        if (yunduan_url) {
            event.preventDefault();
            if (isWindowAlive(win)) {
                win.loadURL(yunduan_url);
            }
            return;
        }
        if (isYunduanDeviceCheckUrl(url)) {
            event.preventDefault();
        }
    });
}

function filterWangxiaoCookies(cookies) {
    return (cookies || []).filter((cookie) => {
        if (!cookie || !cookie.name) {
            return false;
        }
        return WANGXIAO_COOKIE_NAMES.includes(String(cookie.name));
    });
}

function hasWangxiaoLoginCookies(cookies) {
    let cookie_map = buildCookieMap(filterWangxiaoCookies(cookies));
    return !!(
        cookie_map.NewPlatFormToken
        && cookie_map.token
        && (cookie_map.userInfo || cookie_map.UserCookieName || cookie_map.UserCookieName_)
    );
}

function trySaveWangxiaoCookies(cookies) {
    const filtered_cookies = filterWangxiaoCookies(cookies);
    if (!hasWangxiaoLoginCookies(filtered_cookies)) {
        return;
    }
    const cookie_value = buildCookieValue(filtered_cookies);
    if (!cookie_value) {
        return;
    }
    saveLoginCookieValue(cookie_value);
}

function filterWangxiao233Cookies(cookies) {
    return (cookies || []).filter((cookie) => {
        if (!cookie || !cookie.name) {
            return false;
        }
        return WANGXIAO233_COOKIE_NAMES.includes(String(cookie.name));
    });
}

function hasWangxiao233LoginCookies(cookies) {
    let cookie_map = buildCookieMap(filterWangxiao233Cookies(cookies));
    return !!cookie_map.clientauthentication;
}

function trySaveWangxiao233Cookies(cookies) {
    const filtered_cookies = filterWangxiao233Cookies(cookies);
    if (!hasWangxiao233LoginCookies(filtered_cookies)) {
        return;
    }
    const cookie_value = buildCookieValue(filtered_cookies);
    if (!cookie_value) {
        return;
    }
    saveLoginCookieValue(cookie_value);
}

function isAishangkeLoggedInUrl(url) {
    url = String(url || '').toLowerCase();
    if (!url) {
        return false;
    }
    return url.indexOf('/user/index') !== -1
        || url.indexOf('/course/index/viewmycourse') !== -1
        || url.indexOf('/course/index/entercourse') !== -1;
}

function isDongaoCookie(cookie) {
    if (!cookie || !cookie.name) {
        return false;
    }
    const domain = String(cookie.domain || '').toLowerCase();
    return domain === 'dongao.com'
        || domain.endsWith('.dongao.com');
}

function filterDongaoCookies(cookies) {
    return (cookies || []).filter((cookie) => isDongaoCookie(cookie));
}

function normalizeCookieExpirationDate(expiration_date) {
    const numeric = Number(expiration_date);
    return Number.isFinite(numeric) && numeric > 0
        ? numeric
        : undefined;
}

function normalizeCookieSameSite(same_site) {
    same_site = String(same_site || '').trim().toLowerCase();
    if (same_site === 'strict') {
        return 'strict';
    }
    if (same_site === 'lax') {
        return 'lax';
    }
    if (same_site === 'no_restriction' || same_site === 'none') {
        return 'no_restriction';
    }
    return undefined;
}

function normalizePersistedCookie(cookie) {
    if (!cookie || !cookie.name) {
        return null;
    }
    const name = String(cookie.name || '').trim();
    const value = cookie.value === undefined || cookie.value === null
        ? ''
        : String(cookie.value);
    if (!name || !value) {
        return null;
    }
    const domain = String(cookie.domain || '').trim();
    const path_value = String(cookie.path || '/').trim() || '/';
    return {
        name,
        value,
        domain,
        path: path_value.startsWith('/') ? path_value : '/' + path_value,
        secure: !!cookie.secure,
        httpOnly: !!cookie.httpOnly,
        hostOnly: !!cookie.hostOnly,
        sameSite: normalizeCookieSameSite(cookie.sameSite),
        expirationDate: normalizeCookieExpirationDate(cookie.expirationDate),
    };
}

function extractStoredCookieList(cookie_source) {
    let cookie_list = [];
    if (Array.isArray(cookie_source)) {
        cookie_list = cookie_source;
    } else if (cookie_source && typeof cookie_source === 'object') {
        if (Array.isArray(cookie_source.cookieList)) {
            cookie_list = cookie_source.cookieList;
        } else if (Array.isArray(cookie_source.cookies)) {
            cookie_list = cookie_source.cookies;
        }
    }
    const normalized = [];
    const seen = new Set();
    (cookie_list || []).forEach((cookie) => {
        const item = normalizePersistedCookie(cookie);
        if (!item) {
            return;
        }
        const unique_key = [
            item.name,
            item.domain,
            item.path,
        ].join('\t');
        if (seen.has(unique_key)) {
            return;
        }
        seen.add(unique_key);
        normalized.push(item);
    });
    return normalized;
}

function buildCookieHeaderValue(cookie_source) {
    if (typeof cookie_source === 'string') {
        return String(cookie_source || '').trim();
    }
    if (cookie_source && typeof cookie_source === 'object') {
        const cookie_value = String(cookie_source.cookieValue || '').trim();
        if (cookie_value) {
            return cookie_value;
        }
        const cookie_list = extractStoredCookieList(cookie_source);
        if (cookie_list.length) {
            return buildCookieValue(cookie_list);
        }
    }
    return '';
}

function buildCookieSetUrl(cookie, fallback_url = 'https://course.dongao.com/') {
    const domain = String((cookie && cookie.domain) || '').trim().replace(/^\./, '');
    const path_value = String((cookie && cookie.path) || '/').trim() || '/';
    if (!domain) {
        return fallback_url;
    }
    return (cookie && cookie.secure ? 'https://' : 'http://') + domain + (path_value.startsWith('/') ? path_value : '/' + path_value);
}

function buildDongaoCookieEntry(cookies) {
    const cookie_list = extractStoredCookieList(filterDongaoCookies(cookies));
    const cookie_value = cookie_list.length
        ? buildCookieValue(cookie_list)
        : '';
    const user_agent = decodeDongaoUserAgent(cookie_list.length ? { cookieList: cookie_list } : cookie_value);
    return {
        cookieValue: cookie_value,
        cookieList: cookie_list,
        userAgent: user_agent,
        savedAt: new Date().toISOString(),
    };
}

function hasDongaoLoginCookies(cookies) {
    let cookie_map = buildCookieMap(filterDongaoCookies(cookies));
    return !!(
        cookie_map.dongaoLogin
        || cookie_map.memberinfo
    );
}

function hasDongaoCourseCookies(cookies) {
    return (cookies || []).some((cookie) => {
        if (!cookie || !cookie.name) {
            return false;
        }
        const domain = String(cookie.domain || '').toLowerCase().replace(/^\./, '');
        const name = String(cookie.name || '').trim();
        if (name === 'JSESSIONID' && domain === 'course.dongao.com') {
            return true;
        }
        if (domain !== 'course.dongao.com') {
            return false;
        }
        if (!String(cookie.value || '').trim()) {
            return false;
        }
        return [
            'queryAssistant',
            'showLiveNotice',
        ].indexOf(name) === -1;
    });
}

function dongaoCookieDomainMatches(host, domain, host_only) {
    host = String(host || '').toLowerCase().trim();
    domain = String(domain || '').toLowerCase().trim().replace(/^\./, '');
    if (!host || !domain) {
        return false;
    }
    if (host_only) {
        return host === domain;
    }
    return host === domain || host.endsWith('.' + domain);
}

function dongaoCookiePathMatches(request_path, cookie_path) {
    request_path = String(request_path || '/') || '/';
    cookie_path = String(cookie_path || '/') || '/';
    if (!request_path.startsWith('/')) {
        request_path = '/' + request_path;
    }
    if (!cookie_path.startsWith('/')) {
        cookie_path = '/' + cookie_path;
    }
    return request_path === cookie_path || request_path.startsWith(cookie_path.replace(/\/$/, '') + '/') || cookie_path === '/';
}

function dongaoCookieDomainScore(host, cookie) {
    const domain = String((cookie && cookie.domain) || '').toLowerCase().trim().replace(/^\./, '');
    let score = domain.length;
    if ((cookie && cookie.hostOnly) || host === domain) {
        score += 10000;
    }
    return score;
}

function buildDongaoCookieValueForUrl(cookie_entry, target_url) {
    const cookie_list = extractStoredCookieList(cookie_entry);
    let url_info = null;
    try {
        url_info = new URL(target_url);
    } catch (error) {
        return buildCookieHeaderValue(cookie_entry);
    }
    const host = String(url_info.hostname || '').toLowerCase();
    const request_path = url_info.pathname || '/';
    const secure_request = String(url_info.protocol || '').toLowerCase() === 'https:';
    const emitted = new Set();
    return cookie_list.slice().sort((left, right) => {
        const left_path = String((left && left.path) || '/');
        const right_path = String((right && right.path) || '/');
        const path_score = right_path.length - left_path.length;
        if (path_score) {
            return path_score;
        }
        return dongaoCookieDomainScore(host, right) - dongaoCookieDomainScore(host, left);
    }).filter((cookie) => {
        if (!cookie || !cookie.name) {
            return false;
        }
        if (cookie.secure && !secure_request) {
            return false;
        }
        if (!dongaoCookieDomainMatches(host, cookie.domain, cookie.hostOnly)) {
            return false;
        }
        if (!dongaoCookiePathMatches(request_path, cookie.path)) {
            return false;
        }
        const name = String(cookie.name || '').trim();
        const dedupe_name = name.toUpperCase() === 'JSESSIONID' ? name.toUpperCase() : '';
        if (dedupe_name && emitted.has(dedupe_name)) {
            return false;
        }
        if (dedupe_name) {
            emitted.add(dedupe_name);
        }
        return true;
    }).map((cookie) => String(cookie.name || '').trim() + '=' + String(cookie.value || '')).join('; ');
}

function parseDongaoCookiePayload(cookies) {
    const cookie_map = buildCookieMap(filterDongaoCookies(cookies));
    const raw_value = String(cookie_map.dongaoLogin || '').trim();
    if (!raw_value) {
        return null;
    }
    try {
        const decoded_value = decodeURIComponent(raw_value);
        const padded_value = decoded_value + '='.repeat((4 - (decoded_value.length % 4)) % 4);
        return JSON.parse(Buffer.from(padded_value, 'base64').toString('utf8'));
    } catch (error) {
        return null;
    }
}

function getDongaoMemberId(cookies) {
    const payload = parseDongaoCookiePayload(cookies);
    return payload ? String(payload.memberId || '').trim() : '';
}

function buildDongaoStageProbePayload(exam_list) {
    for (const exam_info of (exam_list || [])) {
        if (!exam_info || typeof exam_info !== 'object') {
            continue;
        }
        for (const subject_info of (exam_info.slt || [])) {
            if (!subject_info || typeof subject_info !== 'object') {
                continue;
            }
            const sid = String(subject_info.sd || subject_info.subjectId || '').trim();
            if (!sid) {
                continue;
            }
            for (const season_info of (subject_info.sslt || [])) {
                if (!season_info || typeof season_info !== 'object') {
                    continue;
                }
                const ssid = String(season_info.ssd || season_info.sSubjectId || '').trim();
                if (ssid) {
                    return {sid, ssid, lecturerId: ''};
                }
            }
        }
    }
    return null;
}

function parseDongaoMemberExamList(text) {
    text = String(text || '').trim();
    if (!text) {
        return [];
    }
    const callback_match = text.match(/^[^(\s]+\(\s*'([\s\S]*)'\s*\)\s*$/);
    if (callback_match) {
        try {
            text = decodeURIComponent(callback_match[1]);
        } catch (error) {
            text = callback_match[1];
        }
    }
    try {
        const result = JSON.parse(text);
        return Array.isArray(result) ? result : [];
    } catch (error) {
        return [];
    }
}

function isDongaoLoginRedirectResponse(result) {
    if (!result) {
        return true;
    }
    const status_code = Number(result.statusCode || 0);
    const location = String(result.location || '').toLowerCase();
    const final_url = String(result.url || '').toLowerCase();
    return (status_code >= 300 && status_code < 400 && location.includes('passport.dongao.com/login'))
        || final_url.includes('passport.dongao.com/login');
}

function decodeDongaoUserAgent(cookieValue) {
    if (cookieValue && typeof cookieValue === 'object' && !Array.isArray(cookieValue)) {
        const direct_user_agent = String(
            cookieValue.userAgent
            || cookieValue.helperUserAgent
            || ''
        ).trim();
        if (direct_user_agent) {
            return direct_user_agent;
        }
    }
    const cookieMap = extractStoredCookieList(cookieValue).length
        ? buildCookieMap(extractStoredCookieList(cookieValue))
        : parseCookieString(cookieValue);
    const rawValue = String(cookieMap.dongaoLogin || '').trim();
    if (!rawValue) {
        return '';
    }
    try {
        const decodedValue = decodeURIComponent(rawValue);
        const paddedValue = decodedValue + '='.repeat((4 - (decodedValue.length % 4)) % 4);
        const payload = JSON.parse(Buffer.from(paddedValue, 'base64').toString('utf8'));
        return String(payload.browerMarker || payload.browserMarker || '').trim();
    } catch (error) {
        return '';
    }
}

function isDongaoPassportLoginUrl(url) {
    url = String(url || '').toLowerCase();
    return url.includes('passport.dongao.com/login');
}

function isDongaoDeviceVerifyUrl(url) {
    url = String(url || '').toLowerCase();
    return url.includes('my.dongao.com/qrcode/deviceverify');
}

function isDongaoLoginTransitionUrl(url) {
    return isDongaoPassportLoginUrl(url) || isDongaoDeviceVerifyUrl(url);
}

function isDongaoCoursePageUrl(url) {
    try {
        return String(new URL(String(url || '')).hostname || '').toLowerCase() === 'course.dongao.com';
    } catch (error) {
        url = String(url || '').toLowerCase();
        return url.includes('://course.dongao.com');
    }
}

function clearDongaoSaveTimer() {
    if (dongao_save_timer) {
        clearTimeout(dongao_save_timer);
        dongao_save_timer = null;
    }
    dongao_save_delay_ms = 0;
}

function clearDongaoBootstrapTimer() {
    if (dongao_bootstrap_timer) {
        clearTimeout(dongao_bootstrap_timer);
        dongao_bootstrap_timer = null;
    }
}

function bootstrapDongaoCourseSession(win, delay_ms = 0) {
    if (!win || win.isDestroyed()) {
        return;
    }
    delay_ms = Math.max(0, Number(delay_ms) || 0);
    if (delay_ms > 0) {
        if (dongao_bootstrap_timer) {
            return;
        }
        dongao_bootstrap_timer = setTimeout(() => {
            dongao_bootstrap_timer = null;
            bootstrapDongaoCourseSession(win, 0);
        }, delay_ms);
        return;
    }
    if (dongao_bootstrap_inflight) {
        return;
    }
    const current_url = getSafeWindowUrl(win);
    if (isDongaoDeviceVerifyUrl(current_url) || isDongaoCoursePageUrl(current_url)) {
        return;
    }
    const now = Date.now();
    if (dongao_bootstrap_last_from_url === current_url && now - dongao_bootstrap_last_at < DONGAO_BOOTSTRAP_REPEAT_GUARD_MS) {
        return;
    }
    dongao_bootstrap_last_from_url = current_url;
    dongao_bootstrap_last_at = now;
    dongao_bootstrap_inflight = true;
    win.loadURL(DONGAO_COURSE_PROGRESS_URL).catch(() => {
        dongao_bootstrap_inflight = false;
    });
    setTimeout(() => {
        dongao_bootstrap_inflight = false;
    }, 8000);
}

function validateDongaoCourseCookieEntry(cookie_entry) {
    const cookie_list = extractStoredCookieList(cookie_entry);
    if (!hasDongaoLoginCookies(cookie_list) || !hasDongaoCourseCookies(cookie_list)) {
        return Promise.resolve(false);
    }
    const member_id = getDongaoMemberId(cookie_list);
    if (!member_id) {
        return Promise.resolve(false);
    }
    const progress_cookie_value = buildDongaoCookieValueForUrl(cookie_entry, DONGAO_COURSE_PROGRESS_URL);
    const exam_cookie_value = buildDongaoCookieValueForUrl(cookie_entry, DONGAO_MEMBER_EXAM_URL);
    const stage_cookie_value = buildDongaoCookieValueForUrl(cookie_entry, DONGAO_STAGE_LIST_URL);
    if (!progress_cookie_value || !exam_cookie_value || !stage_cookie_value) {
        return Promise.resolve(false);
    }
    return requestUrlWithCookieValue(DONGAO_COURSE_PROGRESS_URL, {
        cookieValue: progress_cookie_value,
        method: 'GET',
        accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        headers: {'X-Requested-With': ''},
        referer: 'https://course.dongao.com/',
        origin: 'https://course.dongao.com',
    }).then((progress_result) => {
        if (isDongaoLoginRedirectResponse(progress_result)) {
            return false;
        }
        return requestUrlWithCookieValue(DONGAO_MEMBER_EXAM_URL, {
            cookieValue: exam_cookie_value,
            method: 'GET',
            referer: 'https://my.dongao.com/',
            origin: 'https://my.dongao.com',
        });
    }).then((exam_result) => {
        if (!exam_result || isDongaoLoginRedirectResponse(exam_result)) {
            return false;
        }
        const exam_list = parseDongaoMemberExamList(exam_result.body);
        const payload = buildDongaoStageProbePayload(exam_list);
        if (!payload) {
            return false;
        }
        const body = Object.keys(payload).map((name) => {
            return encodeURIComponent(name) + '=' + encodeURIComponent(payload[name]);
        }).join('&');
        return requestUrlWithCookieValue(DONGAO_STAGE_LIST_URL, {
            cookieValue: stage_cookie_value,
            method: 'POST',
            body: body,
            referer: DONGAO_COURSE_PROGRESS_URL,
            origin: 'https://course.dongao.com',
        });
    }).then((stage_result) => {
        if (!stage_result || isDongaoLoginRedirectResponse(stage_result)) {
            return false;
        }
        try {
            const payload = JSON.parse(String(stage_result.body || '{}'));
            return !!(payload && Object.prototype.hasOwnProperty.call(payload, 'obj'));
        } catch (error) {
            return false;
        }
    }).catch(() => false);
}

function finishDongaoSaveValidation(win, cookie_entry, current_url, has_course_cookies) {
    const cookie_value_text = buildCookieHeaderValue(cookie_entry);
    if (!cookie_value_text || !has_course_cookies) {
        dongao_save_inflight = false;
        return;
    }
    validateDongaoCourseCookieEntry(cookie_entry).then((valid) => {
        if (!valid) {
            dongao_save_inflight = false;
            bootstrapDongaoCourseSession(win);
            return;
        }
        saveLoginCookieData(cookie_entry);
    }).catch(() => {
        dongao_save_inflight = false;
    });
}

function handleDongaoPostLogin(win, cookies) {
    if (!win || win.isDestroyed()) {
        return;
    }
    const dongao_cookies = filterDongaoCookies(cookies);
    if (!hasDongaoLoginCookies(dongao_cookies)) {
        return;
    }
    const cookie_entry = buildDongaoCookieEntry(dongao_cookies);
    const cookie_value = buildCookieHeaderValue(cookie_entry);
    if (!cookie_value) {
        return;
    }
    const dynamic_user_agent = decodeDongaoUserAgent(cookie_value);
    if (dynamic_user_agent) {
        dongao_dynamic_user_agent = dynamic_user_agent;
        try {
            win.webContents.setUserAgent(dynamic_user_agent);
        } catch (error) {
            ;
        }
    }
    const current_url = getSafeWindowUrl(win);
    dongao_pending_cookie_entry = cookie_entry;
    const has_course_cookies = hasDongaoCourseCookies(dongao_cookies);
    const on_course_page = isDongaoCoursePageUrl(current_url);
    const on_login_transition = isDongaoLoginTransitionUrl(current_url);
    const ready_to_save = on_course_page && has_course_cookies;
    if (!ready_to_save) {
        clearDongaoSaveTimer();
        if (!on_course_page && !on_login_transition) {
            bootstrapDongaoCourseSession(win);
        } else if (isDongaoPassportLoginUrl(current_url)) {
            bootstrapDongaoCourseSession(win, DONGAO_LOGIN_REDIRECT_GRACE_MS);
        }
        return;
    }
    clearDongaoBootstrapTimer();
    if (dongao_save_inflight) {
        return;
    }
    const desired_delay_ms = 1200;
    if (dongao_save_timer && dongao_save_delay_ms <= desired_delay_ms) {
        return;
    }
    clearDongaoSaveTimer();
    dongao_save_delay_ms = desired_delay_ms;
    dongao_save_timer = setTimeout(() => {
        dongao_save_timer = null;
        dongao_save_delay_ms = 0;
        if (dongao_save_inflight || !dongao_pending_cookie_entry) {
            return;
        }
        dongao_save_inflight = true;
        finishDongaoSaveValidation(win, dongao_pending_cookie_entry, current_url, has_course_cookies);
    }, desired_delay_ms);
}


function scrollItbaizhanLoginViewportRight(win, center) {
    if (!win || win.isDestroyed()) {
        return;
    }
    win.webContents.executeJavaScript(`
        (() => {
            const center = ${center ? 'true' : 'false'};
            function pushRight(node) {
                if (!node || typeof node.scrollWidth !== 'number') {
                    return;
                }
                const target = center
                    ? Math.round(Math.max(0, (node.scrollWidth || 0) - (node.clientWidth || 0)) / 2)
                    : Math.max(node.scrollWidth || 0, 2147483647);
                try {
                    node.scrollLeft = target;
                } catch (error) {
                    ;
                }
                try {
                    if (typeof node.scrollTo === 'function') {
                        node.scrollTo({ left: target, top: node.scrollTop || 0, behavior: 'auto' });
                    }
                } catch (error) {
                    ;
                }
            }
            try {
                document.documentElement.style.overflowX = 'auto';
                if (document.body) {
                    document.body.style.overflowX = 'auto';
                }
                pushRight(document.documentElement);
                pushRight(document.body);
                Array.from(document.querySelectorAll('*')).forEach((node) => {
                    if (node && typeof node.scrollWidth === 'number' && typeof node.clientWidth === 'number' && node.scrollWidth > node.clientWidth + 8) {
                        pushRight(node);
                    }
                });
                const root = document.documentElement || document.body;
                const windowTarget = center ? Math.round(Math.max(0, ((root && root.scrollWidth) || 0) - (window.innerWidth || 0)) / 2) : 2147483647;
                window.scrollTo(windowTarget, window.scrollY || 0);
            } catch (error) {
                ;
            }
        })();
    `, true).catch(() => {
        ;
    });
}

function adjustDongaoLoginViewportLegacy(win) {
    if (!win || win.isDestroyed()) {
        return;
    }
    win.webContents.executeJavaScript(`
        (() => {
            function pushRight(node) {
                if (!node || typeof node.scrollWidth !== 'number') {
                    return;
                }
                const target = Math.max(node.scrollWidth || 0, 2147483647);
                try {
                    node.scrollLeft = target;
                } catch (error) {
                    ;
                }
                try {
                    if (typeof node.scrollTo === 'function') {
                        node.scrollTo({ left: target, top: node.scrollTop || 0, behavior: 'auto' });
                    }
                } catch (error) {
                    ;
                }
            }

            function normalizeText(text) {
                return String(text || '').replace(/\\s+/g, '').trim();
            }

            function hasQrText(text) {
                return text.includes('扫码登录')
                    || text.includes('微信扫码')
                    || text.includes('二维码登录');
            }

            function pushAncestorsRight(node) {
                let current = node;
                let depth = 0;
                while (current && depth < 12) {
                    pushRight(current);
                    current = current.parentElement || null;
                    depth += 1;
                }
            }

            try {
                document.documentElement.style.overflowX = 'auto';
                if (document.body) {
                    document.body.style.overflowX = 'auto';
                }
                const loginCont = document.querySelector('.login_cont');
                if (loginCont) {
                    loginCont.style.overflowX = 'auto';
                    pushRight(loginCont);
                }
                const loginCenter = document.querySelector('.login_center');
                if (loginCenter) {
                    pushRight(loginCenter);
                }
                const qrTriggers = Array.from(document.querySelectorAll(
                    '.change_way, .sm_title, .ewm_img, .change_icon, .login_bottom span'
                ));
                qrTriggers.forEach((node) => {
                    try {
                        if (typeof node.click === 'function') {
                            node.click();
                        }
                    } catch (error) {
                        ;
                    }
                });
                pushRight(document.documentElement);
                pushRight(document.body);
                try {
                    window.scrollTo(2147483647, 0);
                } catch (error) {
                    ;
                }
                const nodes = Array.from(document.querySelectorAll('*'));
                nodes.forEach((node) => {
                    if (!node || typeof node.scrollWidth !== 'number' || typeof node.clientWidth !== 'number') {
                        return;
                    }
                    if (node.scrollWidth > node.clientWidth + 24) {
                        pushRight(node);
                    }
                });
                const qrNode = nodes.find((node) => {
                    const text = normalizeText(node.innerText || node.textContent || '');
                    return text.includes('扫码登录') || text.includes('微信扫码') || text.includes('二维码登录');
                });
                if (qrNode) {
                    pushAncestorsRight(qrNode);
                    try {
                        if (typeof qrNode.click === 'function') {
                            qrNode.click();
                        }
                    } catch (error) {
                        ;
                    }
                    try {
                        qrNode.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'end' });
                    } catch (error) {
                        ;
                    }
                    pushAncestorsRight(qrNode);
                }
                const fallbackQrNode = nodes.find((node) => {
                    const text = normalizeText(node.innerText || node.textContent || '');
                    if (hasQrText(text)) {
                        return true;
                    }
                    const signature = (String(node.className || '') + ' ' + String(node.id || '')).toLowerCase();
                    return signature.includes('scan')
                        || signature.includes('qrcode')
                        || signature.includes('qr');
                });
                if (!qrNode && fallbackQrNode) {
                    pushAncestorsRight(fallbackQrNode);
                    try {
                        if (typeof fallbackQrNode.click === 'function') {
                            fallbackQrNode.click();
                        }
                    } catch (error) {
                        ;
                    }
                    try {
                        fallbackQrNode.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'end' });
                    } catch (error) {
                        ;
                    }
                    pushAncestorsRight(fallbackQrNode);
                }
                const widestNode = nodes
                    .filter((node) => node && typeof node.scrollWidth === 'number' && typeof node.clientWidth === 'number')
                    .sort((left, right) => (right.scrollWidth - right.clientWidth) - (left.scrollWidth - left.clientWidth))[0];
                if (widestNode) {
                    pushAncestorsRight(widestNode);
                }
                const qrBox = document.querySelector('#qrcode, .phoneLogin, .show_box, .two_code');
                if (qrBox) {
                    pushAncestorsRight(qrBox);
                    try {
                        qrBox.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'end' });
                    } catch (error) {
                        ;
                    }
                    pushAncestorsRight(qrBox);
                }
                return true;
            } catch (error) {
                return false;
            }
        })();
    `).catch(() => {
        ;
    });
}

function adjustDongaoLoginViewport(win) {
    if (!win || win.isDestroyed()) {
        return;
    }
    win.webContents.executeJavaScript(`
        (() => {
            const qrKeywords = [
                '\\u626b\\u7801\\u767b\\u5f55',
                '\\u5fae\\u4fe1\\u626b\\u7801',
                '\\u4e8c\\u7ef4\\u7801\\u767b\\u5f55',
                '\\u626b\\u7801',
                'qrcode',
                'qrlogin',
            ];

            function pushRight(node) {
                if (!node || typeof node.scrollWidth !== 'number') {
                    return;
                }
                const target = Math.max(node.scrollWidth || 0, 2147483647);
                try {
                    node.scrollLeft = target;
                } catch (error) {
                    ;
                }
                try {
                    if (typeof node.scrollTo === 'function') {
                        node.scrollTo({ left: target, top: node.scrollTop || 0, behavior: 'auto' });
                    }
                } catch (error) {
                    ;
                }
            }

            function normalizeText(text) {
                return String(text || '').replace(/\\s+/g, '').trim();
            }

            function hasQrText(text) {
                const lowered = normalizeText(text).toLowerCase();
                return qrKeywords.some((keyword) => lowered.includes(String(keyword || '').toLowerCase()));
            }

            function pushAncestorsRight(node) {
                let current = node;
                let depth = 0;
                while (current && depth < 12) {
                    pushRight(current);
                    current = current.parentElement || null;
                    depth += 1;
                }
            }

            try {
                document.documentElement.style.overflowX = 'auto';
                if (document.body) {
                    document.body.style.overflowX = 'auto';
                }
                const loginCont = document.querySelector('.login_cont');
                if (loginCont) {
                    loginCont.style.overflowX = 'auto';
                    pushRight(loginCont);
                }
                const loginCenter = document.querySelector('.login_center');
                if (loginCenter) {
                    pushRight(loginCenter);
                }
                pushRight(document.documentElement);
                pushRight(document.body);
                try {
                    window.scrollTo(2147483647, 0);
                } catch (error) {
                    ;
                }
                const nodes = Array.from(document.querySelectorAll('*'));
                nodes.forEach((node) => {
                    if (!node || typeof node.scrollWidth !== 'number' || typeof node.clientWidth !== 'number') {
                        return;
                    }
                    if (node.scrollWidth > node.clientWidth + 24) {
                        pushRight(node);
                    }
                });
                const qrNode = nodes.find((node) => hasQrText(node.innerText || node.textContent || ''));
                if (qrNode) {
                    pushAncestorsRight(qrNode);
                    try {
                        qrNode.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'end' });
                    } catch (error) {
                        ;
                    }
                    pushAncestorsRight(qrNode);
                }
                const fallbackQrNode = nodes.find((node) => {
                    if (hasQrText(node.innerText || node.textContent || '')) {
                        return true;
                    }
                    const signature = (String(node.className || '') + ' ' + String(node.id || '')).toLowerCase();
                    return signature.includes('scan')
                        || signature.includes('qrcode')
                        || signature.includes('qr');
                });
                if (!qrNode && fallbackQrNode) {
                    pushAncestorsRight(fallbackQrNode);
                    try {
                        fallbackQrNode.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'end' });
                    } catch (error) {
                        ;
                    }
                    pushAncestorsRight(fallbackQrNode);
                }
                const widestNode = nodes
                    .filter((node) => node && typeof node.scrollWidth === 'number' && typeof node.clientWidth === 'number')
                    .sort((left, right) => (right.scrollWidth - right.clientWidth) - (left.scrollWidth - left.clientWidth))[0];
                if (widestNode) {
                    pushAncestorsRight(widestNode);
                }
                const qrBox = document.querySelector('#qrcode, .phoneLogin, .show_box, .two_code');
                if (qrBox) {
                    pushAncestorsRight(qrBox);
                    try {
                        qrBox.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'end' });
                    } catch (error) {
                        ;
                    }
                    pushAncestorsRight(qrBox);
                }
                return true;
            } catch (error) {
                return false;
            }
        })();
    `).catch(() => {
        ;
    });
}

function adjustWangxiaoLoginViewport(win) {
    if (!win || win.isDestroyed()) {
        return;
    }
    win.webContents.executeJavaScript(`
        (() => {
            const HORIZONTAL_VIEW_RATIO = 3 / 4;

            function alignCenterPanel(doc) {
                if (!doc) {
                    return;
                }
                const box = doc.querySelector('.login-content .content-box');
                if (!box) {
                    return;
                }
                const viewportWidth = Math.max(
                    window.innerWidth || 0,
                    (doc.documentElement && doc.documentElement.clientWidth) || 0,
                    (doc.body && doc.body.clientWidth) || 0,
                );
                const boxWidth = Math.max(box.scrollWidth || 0, box.offsetWidth || 0, 1200);
                if (viewportWidth > 0 && boxWidth > viewportWidth) {
                    box.style.left = String(Math.round((viewportWidth - boxWidth) * HORIZONTAL_VIEW_RATIO)) + 'px';
                    box.style.right = 'auto';
                    box.style.marginLeft = '0';
                    box.style.marginRight = '0';
                }
            }

            function centerHorizontally(node) {
                if (!node || typeof node.scrollWidth !== 'number') {
                    return;
                }
                const overflowWidth = Math.max(0, (node.scrollWidth || 0) - (node.clientWidth || 0));
                const target = Math.round(overflowWidth * HORIZONTAL_VIEW_RATIO);
                try {
                    node.scrollLeft = target;
                } catch (error) {
                    ;
                }
                try {
                    if (typeof node.scrollTo === 'function') {
                        node.scrollTo({ left: target, top: node.scrollTop || 0, behavior: 'auto' });
                    }
                } catch (error) {
                    ;
                }
            }

            function adjustDocument(doc) {
                if (!doc) {
                    return;
                }
                try {
                    if (doc.documentElement) {
                        doc.documentElement.style.overflowX = 'auto';
                    }
                    if (doc.body) {
                        doc.body.style.overflowX = 'auto';
                    }
                    alignCenterPanel(doc);
                    centerHorizontally(doc.documentElement);
                    centerHorizontally(doc.body);
                    Array.from(doc.querySelectorAll('*')).forEach((node) => {
                        if (!node || typeof node.scrollWidth !== 'number' || typeof node.clientWidth !== 'number') {
                            return;
                        }
                        if (node.scrollWidth > node.clientWidth + 24) {
                            centerHorizontally(node);
                        }
                    });
                } catch (error) {
                    ;
                }
            }

            adjustDocument(document);
            try {
                const doc = document.documentElement || document.body;
                const overflowWidth = Math.max(0, ((doc && doc.scrollWidth) || 0) - (window.innerWidth || 0));
                window.scrollTo(Math.round(overflowWidth * HORIZONTAL_VIEW_RATIO), 0);
            } catch (error) {
                ;
            }
            Array.from(document.querySelectorAll('iframe')).forEach((frame) => {
                try {
                    adjustDocument(frame.contentDocument || (frame.contentWindow && frame.contentWindow.document));
                } catch (error) {
                    ;
                }
            });
            return true;
        })();
    `).catch(() => {
        ;
    });
}

function stopCookiePoll() {
    if (cookie_poll_timer) {
        clearInterval(cookie_poll_timer);
        cookie_poll_timer = null;
    }
    stopDuanshuQrPolling();
    duanshu_qr_ticket = '';
    duanshu_qr_expire_at = 0;
    duanshu_qr_poll_inflight = false;
    duanshu_qr_refresh_inflight = false;
    duanshu_qr_win = null;
    if (dongao_save_timer) {
        clearTimeout(dongao_save_timer);
        dongao_save_timer = null;
    }
    if (dongao_bootstrap_timer) {
        clearTimeout(dongao_bootstrap_timer);
        dongao_bootstrap_timer = null;
    }
    dongao_save_delay_ms = 0;
    dongao_bootstrap_inflight = false;
    dongao_bootstrap_last_at = 0;
    dongao_bootstrap_last_from_url = '';
    dongao_dynamic_user_agent = '';
    dongao_pending_cookie_entry = null;
    dongao_save_inflight = false;
    ckjr_save_inflight = false;
    ahu_save_inflight = false;
    huomiao_save_inflight = false;
    lexuepeiyou_save_inflight = false;
    speiyou_save_inflight = false;
    unipus_save_inflight = false;
    cnmooc_save_inflight = false;
    mison_save_inflight = false;
    xuexi1998_save_inflight = false;
    gradsmart_save_inflight = false;
    smartedu_token_bootstrap_started = false;
    smartedu_login_ticket_seen = false;
    smartedu_last_bootstrap_ticket = '';
    smartedu_save_inflight = false;
    shikaobang_save_inflight = false;
    sparke_save_inflight = false;
    sparke_rejected_token = '';
    sparke_rejected_token_at = 0;
    sparke_legacy_qr_inflight = false;
    sparke_legacy_exchange_inflight = false;
    sparke_legacy_state = '';
    sparke_legacy_terminal_id = '';
    sparke_legacy_sms_random_code = '';
    sparke_legacy_sms_phone = '';
    sparke_legacy_action_inflight = false;
    if (sparke_legacy_action_timer) {
        clearInterval(sparke_legacy_action_timer);
        sparke_legacy_action_timer = null;
    }
    speiyou_request_auth = {};
    sikiedu_save_inflight = false;
    zhi10_save_inflight = false;
}

function requestAppExit() {
    stopCookiePoll();
    BrowserWindow.getAllWindows().forEach((browser_window) => {
        if (!browser_window || browser_window.isDestroyed()) {
            return;
        }
        try {
            browser_window.close();
        } catch (error) {
            ;
        }
    });
    app.quit();
    setTimeout(() => {
        app.exit(0);
    }, 500);
}

function readCookiesObject() {
    if (!fs.existsSync(cookies_file)) {
        return {};
    }
    try {
        const text = String(fs.readFileSync(cookies_file, 'utf8') || '').replace(/^\uFEFF/, '').trim();
        if (!text) {
            return {};
        }
        const parsed = JSON.parse(text);
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
            ? parsed
            : {};
    } catch (error) {
        return {};
    }
}

function ensureCookiesFileParentDir() {
    const parent_dir = path.dirname(cookies_file);
    if (parent_dir && parent_dir !== '.' && !fs.existsSync(parent_dir)) {
        fs.mkdirSync(parent_dir, { recursive: true });
    }
}

function writeCookiesObject(cookies_obj) {
    ensureCookiesFileParentDir();
    const normalized = cookies_obj && typeof cookies_obj === 'object' && !Array.isArray(cookies_obj)
        ? cookies_obj
        : {};
    const serialized = JSON.stringify(normalized);
    const temp_path = cookies_file + '.' + process.pid + '.' + crypto.randomBytes(8).toString('hex') + '.tmp';
    let descriptor = null;
    try {
        descriptor = fs.openSync(temp_path, 'wx');
        fs.writeFileSync(descriptor, serialized, 'utf8');
        fs.fsyncSync(descriptor);
        fs.closeSync(descriptor);
        descriptor = null;
        fs.renameSync(temp_path, cookies_file);
        const persisted = String(fs.readFileSync(cookies_file, 'utf8') || '').replace(/^\uFEFF/, '');
        if (persisted !== serialized) {
            throw new Error('cookie store verification failed');
        }
    } finally {
        if (descriptor !== null) {
            try {
                fs.closeSync(descriptor);
            } catch (error) {
                ;
            }
        }
        if (fs.existsSync(temp_path)) {
            try {
                fs.unlinkSync(temp_path);
            } catch (error) {
                ;
            }
        }
    }
}

function hasCto51LoginCookies(cookies) {
    const names = new Set((Array.isArray(cookies) ? cookies : [])
        .filter(cookie => cookie && String(cookie.value || '').trim())
        .map(cookie => cookie.name));
    return ['BigUser', 'pub_sauth1', 'pub_sauth2', '_identity', 'www51cto']
        .every(name => names.has(name));
}

function buildCookieValue(cookies) {
    let cookie_value = '';
    (cookies || []).forEach((cookie) => {
        if (!cookie || !cookie.name) {
            return;
        }
        const value = cookie.value === undefined || cookie.value === null
            ? ''
            : String(cookie.value);
        if (!value) {
            return;
        }
        if (cookie_value.length !== 0) {
            cookie_value += ';';
        }
        cookie_value += cookie.name + '=' + value;
    });
    return cookie_value;
}

function trySaveDouyinCookies(cookies) {
    const scoped = (cookies || []).filter(cookie => {
        const domain = String(cookie && cookie.domain || '').toLowerCase().replace(/^\./, '');
        return cookie && cookie.name && cookie.value
            && (domain === 'douyin.com' || domain.endsWith('.douyin.com'));
    });
    if (!scoped.some(cookie => ['sessionid', 'sessionid_ss'].includes(cookie.name))) {
        return false;
    }
    // Save the whole web session, including CSRF and device cookies issued
    // during QR login, so the downloader can reuse the same browser context.
    saveLoginCookieValue(buildCookieValue(scoped));
    return true;
}

function hasYiihuuLoginCookies(cookies) {
    const names = new Set();
    (cookies || []).forEach((cookie) => {
        if (cookie && cookie.name && cookie.value) {
            names.add(String(cookie.name));
        }
    });
    return names.has('yiihuu_sso') && (
        names.has('PHPSESSID')
        || names.has('userinfo')
        || names.has('cookie_ssologin')
    );
}

function isSmarteduCookie(cookie) {
    if (!cookie || !cookie.name || !cookie.value) {
        return false;
    }
    const name = String(cookie.name || '').trim();
    const domain = normalizeCookieDomain(cookie.domain);
    if (/^UC_TOKEN(?:-|$)/i.test(name) || /^UC_SSO_TGC-/i.test(name)) {
        return true;
    }
    if (/^ND_UC_AUTH-/i.test(name)) {
        return !domain || domain.endsWith('smartedu.cn') || domain.endsWith('eduyun.cn') || domain.endsWith('101.com');
    }
    if (['X-EDU-WEB-ROLE', '_abfpc', 'cna'].includes(name)) {
        return !domain || domain.endsWith('smartedu.cn') || domain.endsWith('cbern.com.cn') || domain.endsWith('ykt.eduyun.cn');
    }
    return false;
}

function filterSmarteduCookies(cookies) {
    return (cookies || []).filter((cookie) => isSmarteduCookie(cookie));
}

function decodeSmarteduTokenValue(value) {
    let token_text = String(value || '').trim();
    if (!token_text) {
        return null;
    }
    token_text += '='.repeat((4 - token_text.length % 4) % 4);
    try {
        return JSON.parse(Buffer.from(token_text, 'base64').toString('utf8'));
    } catch (error) {
        return null;
    }
}

function hasSmarteduLoginCookies(cookies) {
    return (cookies || []).some((cookie) => {
        if (!cookie || !/^UC_TOKEN(?:-|$)/i.test(String(cookie.name || ''))) {
            return false;
        }
        const token = decodeSmarteduTokenValue(cookie.value);
        return !!(token && token.access_token && token.mac_key);
    });
}

function hasSmarteduSsoCookies(cookies) {
    return (cookies || []).some((cookie) => {
        const name = String(cookie && cookie.name || '');
        return cookie && cookie.value && (/^UC_SSO_TGC-/i.test(name) || /^ND_UC_AUTH-/i.test(name));
    });
}

function getSmarteduBootstrapTicket(cookies) {
    let parts = [];
    (cookies || []).forEach((cookie) => {
        if (!cookie || !cookie.value) {
            return;
        }
        const name = String(cookie.name || '');
        if (/^UC_SSO_TGC-/i.test(name) || /^ND_UC_AUTH-/i.test(name)) {
            parts.push(name + '=' + String(cookie.value));
        }
    });
    return parts.sort().join(';');
}

function isUnipusCookie(cookie) {
    if (!cookie || !cookie.name || !cookie.value) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain);
    return domain === 'unipus.cn' || domain.endsWith('.unipus.cn');
}

function filterUnipusCookies(cookies) {
    return (cookies || []).filter((cookie) => isUnipusCookie(cookie));
}

function hasUnipusLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterUnipusCookies(cookies));
    return !!cookie_map.PHPSESSID;
}

function isCnmoocCookie(cookie) {
    if (!cookie || !cookie.name || !cookie.value) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain);
    return domain === 'cnmooc.sjtu.cn' || domain.endsWith('.cnmooc.sjtu.cn');
}

function filterCnmoocCookies(cookies) {
    return (cookies || []).filter((cookie) => isCnmoocCookie(cookie));
}

function hasCnmoocLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterCnmoocCookies(cookies));
    return !!(cookie_map.JSESSIONID && (cookie_map.moocvk || cookie_map.MOOCVK || cookie_map.moocsk || cookie_map.keepalive));
}

function isChinesemoocCookie(cookie) {
    if (!cookie || !cookie.name || !cookie.value) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain);
    return domain === 'chinesemooc.org' || domain.endsWith('.chinesemooc.org');
}

function filterChinesemoocCookies(cookies) {
    return (cookies || []).filter((cookie) => isChinesemoocCookie(cookie));
}

function isChinesemoocPostLoginUrl(url) {
    return /^https?:\/\/(?:www\.)?chinesemooc\.org\/(?:index\.php(?:[?#]|$)|student\/)/i.test(String(url || ''));
}

function getCurrentCnmoocCookieValue(win) {
    const target_session = win && !win.isDestroyed() && win.webContents && win.webContents.session
        ? win.webContents.session
        : login_session;
    if (!target_session || !target_session.cookies) {
        return Promise.resolve('');
    }
    return target_session.cookies.get({}).then((cookies) => {
        const cnmooc_cookies = filterCnmoocCookies(cookies || []);
        if (!hasCnmoocLoginCookies(cnmooc_cookies)) {
            return '';
        }
        return buildCookieValue(cnmooc_cookies);
    }).catch(() => '');
}

function looksLikeUnipusLoggedInPage(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const final_url = String(result.url || '').toLowerCase();
    const body = String(result.body || '');
    const body_lower = body.toLowerCase();
    if (final_url.indexOf('/login') !== -1 || final_url.indexOf('sso.unipus.cn') !== -1) {
        return false;
    }
    if (body_lower.indexOf('/login?') !== -1 || body_lower.indexOf('sso.unipus.cn/sso/gl/login') !== -1) {
        return false;
    }
    return !!body;
}

function looksLikeCnmoocLoggedInPage(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const final_url = String(result.url || '').toLowerCase();
    const body = String(result.body || '');
    const body_lower = body.toLowerCase();
    if (final_url.indexOf('/home/login') !== -1) {
        return false;
    }
    if (
        body_lower.indexOf('id="userloginpage"') !== -1
        || body_lower.indexOf('id="isguest" value="true"') !== -1
        || body_lower.indexOf('$.g_login_coeus_user_id = "-1"') !== -1
    ) {
        return false;
    }
    return body_lower.indexOf('/home/logout.mooc') !== -1
        || body_lower.indexOf('/portal/mycourseindex/') !== -1
        || body_lower.indexOf('class="link-default mycourse"') !== -1
        || body_lower.indexOf('id="isguest" value="false"') !== -1
        || body.indexOf('我的课程') !== -1
        || body.indexOf('退出') !== -1;
}

const ZHIHUISHU_COOKIE_NAMES = ['CASTGC', 'CASLOGC', 'jt-cas', 'SESSION'];

function normalizeCookieDomain(domain) {
    return String(domain || '').trim().replace(/^\.+/, '').toLowerCase();
}

function getZhihuishuCookiePriority(cookie) {
    if (!cookie || !cookie.name) {
        return -1;
    }
    const name = String(cookie.name || '').trim();
    const domain = normalizeCookieDomain(cookie.domain);
    const path_value = String(cookie.path || '/').trim() || '/';
    let priority = 0;
    if (name === 'SESSION') {
        if (domain === 'studyservice-api.zhihuishu.com') {
            priority += 1000;
        } else if (domain === 'zhihuishu.com') {
            priority += 900;
        } else if (domain === 'onlineservice-api.zhihuishu.com') {
            priority += 800;
        } else if (domain === 'passport.zhihuishu.com') {
            priority += 700;
        }
    } else {
        if (domain === 'zhihuishu.com') {
            priority += 1000;
        } else if (domain === 'studyservice-api.zhihuishu.com') {
            priority += 900;
        } else if (domain === 'passport.zhihuishu.com') {
            priority += 800;
        } else if (domain === 'onlineservice-api.zhihuishu.com') {
            priority += 700;
        }
    }
    if (cookie.secure) {
        priority += 50;
    }
    if (path_value === '/') {
        priority += 10;
    } else if (path_value.startsWith('/')) {
        priority += 5;
    }
    return priority;
}

function normalizeZhihuishuCookies(cookies) {
    let cookie_map = {};
    (cookies || []).forEach((cookie) => {
        if (!cookie || !ZHIHUISHU_COOKIE_NAMES.includes(String(cookie.name || '').trim())) {
            return;
        }
        const value = cookie.value === undefined || cookie.value === null
            ? ''
            : String(cookie.value).trim();
        if (!value) {
            return;
        }
        const name = String(cookie.name || '').trim();
        const current_cookie = cookie_map[name];
        if (!current_cookie || getZhihuishuCookiePriority(cookie) > getZhihuishuCookiePriority(current_cookie)) {
            cookie_map[name] = cookie;
        }
    });
    return ZHIHUISHU_COOKIE_NAMES.map((name) => cookie_map[name]).filter((cookie) => !!cookie);
}

function buildCookieRemovalUrl(cookie) {
    if (!cookie) {
        return '';
    }
    let url = '';
    url += cookie.secure ? 'https://' : 'http://';
    url += cookie.domain && cookie.domain.charAt(0) === '.' ? 'www' : '';
    url += cookie.domain || '';
    url += cookie.path || '/';
    return url;
}

function clearSessionCookies(target_session) {
    target_session = target_session || session.defaultSession;
    return target_session.cookies.get({})
        .then((cookies) => Promise.all((cookies || []).map((cookie) => {
            const url = buildCookieRemovalUrl(cookie);
            if (!url || !cookie.name) {
                return Promise.resolve();
            }
            return target_session.cookies.remove(url, cookie.name).catch(() => {
                ;
            });
        })));
}

function settleLoginSessionReset(operation, timeout_ms) {
    timeout_ms = Math.max(0, Number(timeout_ms) || 0);
    return new Promise((resolve) => {
        let settled = false;
        let timer = null;
        const finish = (timed_out) => {
            if (settled) {
                return;
            }
            settled = true;
            if (timer) {
                clearTimeout(timer);
            }
            resolve({timed_out: !!timed_out});
        };
        Promise.resolve(operation).then(
            () => finish(false),
            () => finish(false),
        );
        timer = setTimeout(() => finish(true), timeout_ms);
    });
}

function resetLoginSession(
        target_session,
        target_url = '',
        timeout_ms = LOGIN_SESSION_RESET_TIMEOUT_MS) {
    target_session = target_session || session.defaultSession;
    const is_local_page = /^file:/i.test(String(target_url || '').trim());
    const storage_reset = is_local_page
        ? Promise.resolve()
        : target_session.clearStorageData();
    return Promise.all([
        settleLoginSessionReset(storage_reset, timeout_ms),
        settleLoginSessionReset(clearSessionCookies(target_session), timeout_ms),
    ]);
}

function isCkjrLoginName(name) {
    name = String(name || '');
    return name === 'ckjr' || name.startsWith('ckjr.');
}

function isDuanshuLoginName(name) {
    return String(name || '') === 'duanshu' || String(name || '').startsWith('duanshu.');
}

function isDuanshuWechatQrFlow() {
    return isDuanshuLoginName(login_name)
        && duanshu_wechat_login_required
        && !duanshu_pc_detail_login;
}

function getDuanshuH5Host(url) {
    let hostname = getHostnameFromUrl(url);
    if ((!hostname || !hostname.endsWith('.duanshu.com')) && isDuanshuLoginName(login_name)) {
        const parts = String(login_name || '').split('.');
        if (parts.length >= 2) {
            hostname = parts.slice(1).join('.').toLowerCase();
        }
    }
    hostname = String(hostname || '').toLowerCase().replace(/^www\./, '');
    if (hostname.endsWith('-pc.duanshu.com')) {
        hostname = hostname.slice(0, -'-pc.duanshu.com'.length) + '.duanshu.com';
    }
    return hostname.endsWith('.duanshu.com') ? hostname : '';
}

function duanshuOriginForHost(host) {
    return host ? 'https://' + host : '';
}

function duanshuConfigUrl(host) {
    const key = String(host || '').toLowerCase().replace(/\./g, '-');
    return key ? 'https://oss-web.duanshu.com/shop/' + key + '/config.json?timestamp=' + Date.now() : '';
}

function requestDuanshuJson(method, target_url, payload, origin, extra_headers) {
    const base_headers = Object.assign({
        'User-Agent': DEFAULT_BROWSER_USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'identity',
        'x-platform': 'h5',
    }, extra_headers || {});
    if (origin) {
        base_headers.Origin = origin;
        base_headers.Referer = origin + '/';
    }
    return requestJsonUrl(method, target_url, payload || null, base_headers).then((result) => {
        const body = parseJsonResponseBody(result);
        if (!result || result.statusCode !== 200 || !body || typeof body !== 'object' || Array.isArray(body)) {
            throw new Error('Duanshu service unavailable');
        }
        return {
            statusCode: Number(result.statusCode),
            body,
        };
    });
}

function duanshuExplicitError(body) {
    const scopes = [body];
    if (body && body.response && typeof body.response === 'object' && !Array.isArray(body.response)) {
        scopes.push(body.response);
    }
    for (const scope of scopes) {
        for (const key of ['errno', 'error', 'error_code', 'err_code', 'code']) {
            if (!Object.prototype.hasOwnProperty.call(scope || {}, key)) {
                continue;
            }
            const value = scope[key];
            const normalized = typeof value === 'string' ? value.trim().toLowerCase() : value;
            if (normalized !== undefined && normalized !== null && normalized !== ''
                    && normalized !== 0 && normalized !== '0' && normalized !== false
                    && normalized !== 'ok' && normalized !== 'success') {
                return key;
            }
        }
        if (scope && scope.success === false) {
            return 'success';
        }
    }
    return '';
}

async function detectDuanshuWechatOnly(login_url) {
    if (!isDuanshuLoginName(login_name) || duanshu_pc_detail_login) {
        return {required: false, host: '', shop_id: ''};
    }
    const host = getDuanshuH5Host(login_url || extra_arg);
    if (!host) {
        return {required: false, host: '', shop_id: ''};
    }
    try {
        const config_result = await requestDuanshuJson('GET', duanshuConfigUrl(host), null, duanshuOriginForHost(host));
        const config = config_result.body && typeof config_result.body === 'object'
            ? config_result.body : {};
        const shop_info = config.shop_info && typeof config.shop_info === 'object'
            ? config.shop_info : {};
        const only_wechat = [config.only_wechat_open_shop, shop_info.only_wechat_open_shop]
            .some(value => value === true || value === 1 || /^(true|1)$/i.test(String(value || '').trim()));
        if (duanshuExplicitError(config)) {
            return {required: false, host, shop_id: ''};
        }
        if (!only_wechat) {
            return {required: false, host, shop_id: ''};
        }
        let shop_id = String(config.shop_id || shop_info.shop_id || shop_info.shopId || '').trim();
        if (!shop_id) {
            const identifier = await requestDuanshuJson(
                'GET',
                'https://api.duanshu.com/fairy/api/v1/shop/identifier/',
                null,
                duanshuOriginForHost(host),
            );
            const identifier_body = identifier.body || {};
            if (duanshuExplicitError(identifier_body)) {
                return {required: false, host, shop_id: ''};
            }
            const identifier_response = identifier_body.response && typeof identifier_body.response === 'object'
                ? identifier_body.response : identifier_body;
            shop_id = String(
                identifier_response.shop_id || identifier_response.shopId
                || identifier_response.id || identifier_response.identifier || '',
            ).trim();
        }
        return shop_id ? {required: true, host, shop_id} : {required: false, host, shop_id: ''};
    } catch (error) {
        return {required: false, host, shop_id: ''};
    }
}

function duanshuQrLocalUrl(bridge_url, message, stage) {
    const page = localFileURL(path.join(app.getAppPath(), 'duanshu-login.html'));
    const params = [
        'qr=' + encodeURIComponent(String(bridge_url || '')),
        'message=' + encodeURIComponent(String(message || '')),
        'stage=' + encodeURIComponent(String(Number(stage || 0))),
    ];
    return page + '?' + params.join('&');
}

function isDuanshuQrPageUrl(target_url) {
    try {
        const target = new URL(target_url);
        const local = new URL(duanshuQrLocalUrl('', '', 0));
        if (target.protocol !== 'file:' || target.host !== local.host) {
            return false;
        }
        const fileURLToPath = require('url').fileURLToPath;
        const target_path = path.normalize(fileURLToPath(target));
        const local_path = path.normalize(fileURLToPath(local));
        return process.platform === 'win32'
            ? target_path.toLowerCase() === local_path.toLowerCase()
            : target_path === local_path;
    } catch (error) {
        return false;
    }
}

function isDuanshuQrRefreshUrl(target_url) {
    return isDuanshuQrPageUrl(target_url) && /^#refresh-\d+$/.test(new URL(target_url).hash);
}

async function pollDuanshuQrRefresh(target_window) {
    if (!target_window || target_window.isDestroyed() || target_window !== duanshu_qr_win
            || !isDuanshuWechatQrFlow() || duanshu_qr_finished || duanshu_qr_refresh_inflight
            || !isDuanshuQrPageUrl(target_window.webContents.getURL())) {
        return false;
    }
    duanshu_qr_refresh_inflight = true;
    const generation = duanshu_qr_generation;
    try {
        // Consume the page action once, including when Electron misses the hash navigation event.
        const request = await target_window.webContents.executeJavaScript(`
            (() => ({
                href: window.location.href,
                requested: !!(window.__duanshuTakeRefreshRequest && window.__duanshuTakeRefreshRequest()),
            }))();
        `, true);
        if (!request || !request.requested || !isDuanshuQrPageUrl(request.href)
                || !isDuanshuQrGenerationCurrent(generation)
                || !isDuanshuQrPageUrl(target_window.webContents.getURL())) {
            return false;
        }
        await startDuanshuQrLogin(target_window, true);
        return true;
    } catch (error) {
        return false;
    } finally {
        duanshu_qr_refresh_inflight = false;
    }
}

function duanshuQrSetStatus(message, color, stage, state = 'waiting') {
    const target = duanshu_qr_win;
    if (!target || target.isDestroyed()) {
        return;
    }
    try {
        target.webContents.executeJavaScript(
            'window.__duanshuSetStatus && window.__duanshuSetStatus('
            + JSON.stringify(String(message || '')) + ','
            + JSON.stringify(String(color || '')) + ','
            + JSON.stringify(Number(stage || 0)) + ','
            + JSON.stringify(state) + ');',
            true,
        ).catch(() => {});
    } catch (error) {
        ;
    }
}

function stopDuanshuQrPolling() {
    // Invalidate outstanding requests as well as scheduled polls.
    duanshu_qr_generation += 1;
    if (duanshu_qr_poll_timer) {
        clearTimeout(duanshu_qr_poll_timer);
        duanshu_qr_poll_timer = null;
    }
    duanshu_qr_poll_inflight = false;
}

function isDuanshuQrGenerationCurrent(generation) {
    return isDuanshuWechatQrFlow() && !duanshu_qr_finished
        && generation === duanshu_qr_generation
        && duanshu_qr_win && !duanshu_qr_win.isDestroyed();
}

async function verifyDuanshuMember(member_value, shop_id, host) {
    const parsed = parseDuanshuMemberValue(member_value);
    if (!parsed) {
        return false;
    }
    const origin = /^https?:\/\//i.test(String(host || ''))
        ? String(host || '').replace(/\/+$/, '')
        : duanshuOriginForHost(host);
    const result = await requestDuanshuJson(
        'GET',
        'https://api.duanshu.com/h5/user/detail?shop_id=' + encodeURIComponent(shop_id),
        null,
        origin,
        {
            'HTTP-X-H5-VERSION': '1',
            'X-CLIENT-VERSION': '1314',
            'x-shop': shop_id,
            'x-member': parsed.raw,
            'x-platform': 'h5',
        },
    );
    const body = result.body || {};
    const response = body.response;
    const user = response && typeof response === 'object' && !Array.isArray(response)
        ? (response.data || response) : null;
    const user_id = user && (user.uid || user.id || user.member_id || user.memberId);
    const member_id = parsed.member.id || parsed.member.member_id || parsed.member.memberId;
    return result.statusCode === 200 && !!user_id && String(user_id) === String(member_id)
        && (!user.shop_id || String(user.shop_id) === String(shop_id))
        && !duanshuExplicitError(body) && !duanshuExplicitError(user);
}

async function saveDuanshuQrMember(member_value, generation) {
    const parsed = parseDuanshuMemberValue(member_value);
    if (!parsed || !isDuanshuQrGenerationCurrent(generation)) {
        return false;
    }
    const shop_id = String(
        duanshu_qr_shop_id || parsed.member.shop_id || parsed.member.shopId || '',
    ).trim();
    if (!shop_id || !(await verifyDuanshuMember(parsed.raw, shop_id, duanshu_qr_origin))
            || !isDuanshuQrGenerationCurrent(generation)) {
        return false;
    }
    const cookie_value = buildDuanshuCookieValue(parsed.raw, shop_id);
    try {
        const cookies_obj = readCookiesObject();
        cookies_obj[login_name] = cookie_value;
        writeCookiesObject(cookies_obj);
    } catch (error) {
        duanshu_qr_ticket = '';
        duanshuQrSetStatus('登录信息保存失败，请检查文件权限后重试', '#b42318', 1, 'error');
        return false;
    }
    duanshu_qr_finished = true;
    duanshuQrSetStatus('登录成功', '#15803d', 2, 'success');
    stopDuanshuQrPolling();
    requestAppExit();
    return true;
}

async function pollDuanshuQrTicket(generation) {
    if (!isDuanshuQrGenerationCurrent(generation)
            || !duanshu_qr_ticket || duanshu_qr_poll_inflight) {
        return;
    }
    if (Date.now() > duanshu_qr_expire_at) {
        duanshu_qr_ticket = '';
        duanshuQrSetStatus('二维码已过期', '#b42318', 0, 'expired');
        return;
    }
    duanshu_qr_poll_inflight = true;
    const ticket = duanshu_qr_ticket;
    try {
        const status_result = await requestDuanshuJson(
            'GET',
            'https://api.duanshu.com/fairy/api/v2/member/auth/ticket_status/?ticket='
                + encodeURIComponent(ticket) + '&shop_id=' + encodeURIComponent(duanshu_qr_shop_id),
            null,
            duanshu_qr_origin,
        );
        if (!isDuanshuQrGenerationCurrent(generation)) {
            return;
        }
        const body = status_result.body || {};
        const status_body = body.response && typeof body.response === 'object' ? body.response : body;
        if (duanshuExplicitError(body) || status_body.status === undefined || status_body.status === null) {
            throw new Error('Duanshu ticket status unavailable');
        }
        const status = Number(status_body && status_body.status);
        if (status === 1) {
            duanshuQrSetStatus('已扫码，等待微信确认', '#1559ad', 1, 'scanned');
        } else if (status === 2) {
            duanshuQrSetStatus('正在验证登录状态...', '#1559ad', 1, 'verifying');
            const sign_result = await requestDuanshuJson(
                'GET',
                'https://api.duanshu.com/fairy/api/v2/member/auth/sign/?ticket='
                    + encodeURIComponent(ticket) + '&shop_id=' + encodeURIComponent(duanshu_qr_shop_id),
                null,
                duanshu_qr_origin,
            );
            if (!isDuanshuQrGenerationCurrent(generation)) {
                return;
            }
            const sign_body = sign_result.body || {};
            if (duanshuExplicitError(sign_body)) {
                throw new Error('Duanshu sign unavailable');
            }
            const sign_response = sign_body.response && typeof sign_body.response === 'object'
                ? sign_body.response : sign_body;
            const member_value = parseDuanshuMemberValue(sign_response) ? sign_response
                : sign_response.signature || sign_response.member || sign_response.userInfo
                || sign_response.user_info || sign_response;
            if (await saveDuanshuQrMember(member_value, generation)) {
                return;
            }
            if (!isDuanshuQrGenerationCurrent(generation) || !duanshu_qr_ticket) {
                return;
            }
            duanshuQrSetStatus('登录校验未通过，正在重试...', '#b42318', 1, 'error');
        } else if (status < 0) {
            duanshu_qr_ticket = '';
            duanshuQrSetStatus('二维码已过期', '#b42318', 0, 'expired');
            return;
        } else if (status === 0) {
            duanshuQrSetStatus('等待微信扫码', '#1559ad', 0);
        } else {
            throw new Error('Unknown Duanshu ticket status');
        }
    } catch (error) {
        if (isDuanshuQrGenerationCurrent(generation)) {
            duanshuQrSetStatus('连接暂时中断，正在重试...', '#9a6700', 0, 'error');
        }
    } finally {
        if (generation === duanshu_qr_generation) {
            duanshu_qr_poll_inflight = false;
        }
    }
    if (isDuanshuQrGenerationCurrent(generation) && duanshu_qr_ticket) {
        duanshu_qr_poll_timer = setTimeout(() => pollDuanshuQrTicket(generation), 1000);
    }
}

async function startDuanshuQrLogin(target_window, force_refresh) {
    if (!target_window || target_window.isDestroyed() || !isDuanshuWechatQrFlow()) {
        return;
    }
    if (duanshu_qr_poll_inflight && !force_refresh) {
        return;
    }
    duanshu_qr_win = target_window;
    stopDuanshuQrPolling();
    duanshu_qr_ticket = '';
    duanshu_qr_finished = false;
    const generation = duanshu_qr_generation;
    const loading_url = duanshuQrLocalUrl('', '正在生成二维码...', 0);
    try {
        await target_window.loadURL(loading_url);
        if (!isDuanshuQrGenerationCurrent(generation)) {
            return;
        }
        duanshuQrSetStatus('正在连接短书服务...', '#1559ad', 0, 'loading');
        const ticket_result = await requestDuanshuJson(
            'GET',
            'https://api.duanshu.com/fairy/api/v2/member/auth/ticket/?shop_id='
                + encodeURIComponent(duanshu_qr_shop_id),
            null,
            duanshu_qr_origin,
        );
        if (!isDuanshuQrGenerationCurrent(generation)) {
            return;
        }
        const ticket_body = ticket_result.body || {};
        const ticket_response = ticket_body.response && typeof ticket_body.response === 'object'
            ? ticket_body.response : ticket_body;
        const ticket = String(ticket_response.ticket || '').trim();
        if (!ticket || duanshuExplicitError(ticket_body)) {
            throw new Error('ticket unavailable');
        }
        duanshu_qr_ticket = ticket;
        duanshu_qr_expire_at = Date.now() + 180000;
        const bridge_url = duanshu_qr_origin + '/bridge/pc_login/m.html?shop_id='
            + encodeURIComponent(duanshu_qr_shop_id) + '&ticket=' + encodeURIComponent(ticket);
        await target_window.loadURL(duanshuQrLocalUrl(bridge_url, '等待微信扫码', 0));
        if (!isDuanshuQrGenerationCurrent(generation)) {
            return;
        }
        duanshuQrSetStatus('等待微信扫码', '#1559ad', 0);
        duanshu_qr_poll_timer = setTimeout(() => pollDuanshuQrTicket(generation), 700);
    } catch (error) {
        if (isDuanshuQrGenerationCurrent(generation)) {
            duanshuQrSetStatus('二维码获取失败', '#b42318', 0, 'error');
        }
    }
}

function getHostnameFromUrl(url) {
    try {
        return String(new URL(String(url || '')).hostname || '').toLowerCase();
    } catch (error) {
        return '';
    }
}

function getDuanshuCookieEnvFromUrl(url) {
    const hostname = getHostnameFromUrl(url);
    if (!hostname) {
        return 'release';
    }
    const parts = hostname.split('.');
    if (parts.some(part => /^test(?:-|$)/i.test(part))) {
        return 'test';
    }
    if (parts.some(part => /^pre(?:-|$)/i.test(part))) {
        return 'pre';
    }
    return 'release';
}

function decodeDuanshuCookieValue(value) {
    value = String(value || '').trim();
    for (let i = 0; i < 2; i++) {
        try {
            const decoded = decodeURIComponent(value);
            if (decoded === value) {
                break;
            }
            value = decoded;
        } catch (error) {
            break;
        }
    }
    return value;
}

function getDuanshuCookieValueCandidates(value) {
    value = String(value || '').trim();
    const candidates = [];
    function addCandidate(text) {
        text = String(text || '').trim();
        if (text && !candidates.includes(text)) {
            candidates.push(text);
        }
    }
    addCandidate(value);
    for (let i = 0; i < 2; i++) {
        try {
            const decoded = decodeURIComponent(value);
            if (decoded === value) {
                break;
            }
            value = decoded;
            addCandidate(value);
        } catch (error) {
            break;
        }
    }
    return candidates;
}

function parseDuanshuMemberValue(value, depth = 0) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        const object_member_id = value.id || value.member_id || value.memberId;
        if (object_member_id && value.signature) {
            return {
                raw: JSON.stringify(value),
                member: value,
            };
        }
        if (typeof value.value === 'string' && depth < 2) {
            const nested = parseDuanshuMemberValue(value.value, depth + 1);
            if (nested) {
                return nested;
            }
        }
        return null;
    }
    const raw_text = String(value || '').trim();
    if (!raw_text) {
        return null;
    }
    for (const candidate of getDuanshuCookieValueCandidates(raw_text)) {
        let member = null;
        try {
            member = JSON.parse(candidate);
        } catch (error) {
            continue;
        }
        if (member && typeof member.value === 'string' && depth < 2) {
            const inner = parseDuanshuMemberValue(member.value, depth + 1);
            if (inner) {
                return inner;
            }
            continue;
        }
        if (!member || typeof member !== 'object') {
            continue;
        }
        const member_id = member.id || member.member_id || member.memberId;
        if (!member_id || !member.signature) {
            continue;
        }
        return {
            raw: JSON.stringify(member),
            member,
        };
    }
    return null;
}

function buildDuanshuCookieValue(member_value, shop_id) {
    const parsed = parseDuanshuMemberValue(member_value);
    if (!parsed) {
        return '';
    }
    shop_id = shop_id || parsed.member.shop_id || parsed.member.shopId || '';
    return 'x-member=' + parsed.raw + (shop_id ? ';x-shop=' + shop_id : '');
}

function saveDuanshuCookieValue(member_value, shop_id) {
    const cookie_value = buildDuanshuCookieValue(member_value, shop_id);
    if (!cookie_value) {
        return false;
    }
    saveLoginCookieValue(cookie_value);
    return true;
}

function getLoginSessionPartition(name) {
    if (name == 'xiaoetech' && xiaoetech_login_mode == 'pc') {
        return 'xiaoetech-pc-login-' + Date.now();
    }
    if (name == 'shanxiang') {
        return 'persist:login-shanxiang';
    }
    if (name == 'luffycity') {
        return 'luffycity-login-' + Date.now();
    }
    const normalized = String(name || '')
        .toLowerCase()
        .replace(/[^a-z0-9._-]+/g, '_')
        .replace(/^_+|_+$/g, '');
    if (isCkjrLoginName(name)) {
        return 'persist:login-' + (normalized || 'ckjr');
    }
    return 'login-' + (normalized || 'generic') + '-' + Date.now();
}

function normalizeCkjrRoutePath(route_path) {
    route_path = String(route_path || '').trim();
    if (!route_path) {
        return '';
    }
    if (route_path.charAt(0) === '#') {
        route_path = route_path.slice(1);
    }
    if (!route_path) {
        return '';
    }
    if (route_path.charAt(0) !== '/') {
        route_path = '/' + route_path;
    }
    return route_path;
}

function decodeCkjrRouteParam(value) {
    value = String(value || '').trim();
    if (!value) {
        return '';
    }
    for (let i = 0; i < 3; i++) {
        try {
            const decoded = decodeURIComponent(value);
            if (decoded === value) {
                break;
            }
            value = decoded.trim();
        } catch (error) {
            break;
        }
    }
    return value;
}

function isCkjrLoginRoutePath(route_path) {
    route_path = normalizeCkjrRoutePath(route_path);
    return /^\/homePage\/login\/(?:qrLogin|wechatAuthPage|bindMobile)/i.test(route_path);
}

function normalizeCkjrBaseUrl(parsed) {
    if (!parsed) {
        return '';
    }
    let pathname = String(parsed.pathname || '/');
    const path_match = pathname.match(/^(.*?\/kpv2p\/[^\/?#]+)(?:\/)?(.*)$/i);
    if (path_match) {
        pathname = path_match[1] + '/';
        if (path_match[2]) {
            pathname += path_match[2].replace(/^\/+/, '');
        }
    }
    return parsed.origin + pathname + parsed.search;
}

function isCkjrContentRoutePath(route_path) {
    route_path = normalizeCkjrRoutePath(route_path);
    if (!route_path) {
        return false;
    }
    return /^\/homePage\/(?:course\/(?:video|voice|imgText)|column\/columnDetail|package\/packageDetail|live\/(?:liveDetail|livePersonalDetail|liveRoom)|datum\/datumDetail|testPaper\/testDetail)/i.test(route_path);
}

function isCkjrContentUrl(url) {
    url = String(url || '').trim();
    if (!url) {
        return false;
    }
    const hash_index = url.indexOf('#');
    if (hash_index !== -1) {
        return isCkjrContentRoutePath(url.slice(hash_index + 1));
    }
    return isCkjrContentRoutePath(url);
}

function mergeCkjrRouteParams(search_text, route_path) {
    const params = new URLSearchParams(String(search_text || '').replace(/^\?/, ''));
    const route_query = String(route_path || '').split('?')[1] || '';
    new URLSearchParams(route_query).forEach((value, key) => {
        params.set(key, value);
    });
    return params;
}

function buildCkjrContentRouteFromLoginParams(search_text, login_route_path) {
    const params = mergeCkjrRouteParams(search_text, login_route_path);
    const target_path = decodeCkjrRouteParam(
        params.get('targetPath')
        || params.get('beforeLoginUrl')
        || ''
    );
    if (target_path) {
        return normalizeCkjrRoutePath(target_path.replace(/^https?:\/\/[^#]+#/i, ''));
    }
    const resource_id = String(
        params.get('courseId')
        || params.get('prodId')
        || params.get('productId')
        || params.get('extId')
        || params.get('combosId')
        || params.get('comboId')
        || params.get('datumId')
        || params.get('liveId')
        || params.get('testId')
        || ''
    ).trim();
    if (!resource_id) {
        return '';
    }
    const prod_type = Number(params.get('prodType') || params.get('ckFrom') || params.get('courseType') || '0') || 0;
    const route_config = {
        110: ['course/video', 'courseId'],
        111: ['course/voice', 'courseId'],
        112: ['course/imgText', 'courseId'],
        5: ['course/video', 'courseId'],
        0: ['course/video', 'courseId'],
        1: ['course/voice', 'courseId'],
        2: ['course/imgText', 'courseId'],
        8: ['datum/datumDetail', 'datumId'],
        9: ['column/columnDetail', 'extId'],
        38: ['column/columnDetail', 'extId'],
        48: ['package/packageDetail', 'combosId'],
        61: ['package/packageDetail', 'combosId'],
        62: ['package/packageDetail', 'combosId'],
        70: ['package/packageDetail', 'combosId'],
        51: ['live/liveDetail', 'liveId'],
        72: ['live/liveDetail', 'liveId'],
        124: ['live/liveDetail', 'liveId'],
        125: ['testPaper/testDetail', 'testId'],
        173: ['live/liveDetail', 'liveId'],
        174: ['live/livePersonalDetail', 'liveId'],
        180: ['live/livePersonalDetail', 'liveId'],
    }[prod_type] || ['course/video', 'courseId'];
    const route_params = new URLSearchParams();
    route_params.set(route_config[1], resource_id);
    ['prodId', 'productId', 'prodType', 'ckFrom', 'courseType', 'extId', 'cId', 'refereeId', 'shareholderId', 'sourceForm', 'sourceFrom', 'merchantId'].forEach((key) => {
        const value = String(params.get(key) || '').trim();
        if (value && !route_params.has(key)) {
            route_params.set(key, value);
        }
    });
    if (!route_params.has('prodId')) {
        route_params.set('prodId', resource_id);
    }
    if (prod_type && !route_params.has('ckFrom')) {
        route_params.set('ckFrom', String(prod_type));
    }
    return '/homePage/' + route_config[0] + '?' + route_params.toString();
}

function parseCkjrStoreContext(target_url) {
    target_url = String(target_url || '').trim();
    if (!target_url) {
        return null;
    }
    let parsed = null;
    try {
        parsed = new URL(target_url);
    } catch (error) {
        return null;
    }
    const path_match = String(parsed.pathname || '').match(/\/kpv2p\/([^\/?#]+)\/?/i);
    const company_id = path_match ? decodeURIComponent(path_match[1] || '').trim() : '';
    let target_path = normalizeCkjrRoutePath(parsed.hash) || '/';
    if (isCkjrLoginRoutePath(target_path)) {
        const restored_target_path = buildCkjrContentRouteFromLoginParams(parsed.search, target_path);
        if (restored_target_path) {
            target_path = restored_target_path;
        }
    }
    if (!company_id || !target_path) {
        return null;
    }
    const route_query = new URLSearchParams(target_path.split('?')[1] || '');
    const referee_id = String(route_query.get('refereeId') || '').trim();
    const shareholder_id = String(route_query.get('shareholderId') || '').trim();
    const source_form = String(
        route_query.get('sourceForm')
        || route_query.get('sourceFrom')
        || route_query.get('ckFrom')
        || ''
    ).trim();
    const base_url = normalizeCkjrBaseUrl(parsed);
    let path_name = parsed.pathname;
    try {
        path_name = new URL(base_url).pathname;
    } catch (error) {
        ;
    }
    return {
        baseUrl: base_url,
        companyId: company_id,
        origin: parsed.origin,
        pathName: path_name,
        targetPath: target_path,
        targetUrl: base_url + '#' + target_path,
        loginUrl: base_url + '#/',
        refereeId: referee_id,
        shareholderId: shareholder_id,
        sourceForm: source_form,
    };
}

function buildCkjrInitScript(context) {
    if (!context) {
        return '';
    }
    return `
        (() => {
            const context = ${JSON.stringify(context)};
            try {
                if (!window || !window.location) {
                    return;
                }
                const href = String(window.location.href || '');
                if (context.origin && href.indexOf(context.origin) !== 0) {
                    return;
                }
                if (context.pathName && String(window.location.pathname || '') !== context.pathName) {
                    return;
                }
                function syncStorage(storage, key, value) {
                    if (!storage || !key || value === undefined || value === null || value === '') {
                        return;
                    }
                    const normalized = String(value);
                    try {
                        if (storage.getItem(key) !== normalized) {
                            storage.setItem(key, normalized);
                        }
                    } catch (error) {
                        ;
                    }
                }
                syncStorage(window.localStorage, '__xwz_ckjr_target_path__', context.targetPath);
                syncStorage(window.sessionStorage, '__xwz_ckjr_target_path__', context.targetPath);
                syncStorage(window.localStorage, '__xwz_ckjr_referee_id__', context.refereeId);
                syncStorage(window.sessionStorage, '__xwz_ckjr_referee_id__', context.refereeId);
                syncStorage(window.localStorage, '__xwz_ckjr_shareholder_id__', context.shareholderId);
                syncStorage(window.sessionStorage, '__xwz_ckjr_shareholder_id__', context.shareholderId);
                syncStorage(window.localStorage, '__xwz_ckjr_source_form__', context.sourceForm);
                syncStorage(window.sessionStorage, '__xwz_ckjr_source_form__', context.sourceForm);
                syncStorage(window.localStorage, 'companyId', context.companyId);
                syncStorage(window.sessionStorage, 'companyId', context.companyId);
            } catch (error) {
                ;
            }
        })();
    `;
}

function installCkjrInitScript(win, context) {
    if (!win || win.isDestroyed() || !context) {
        return Promise.resolve(false);
    }
    const debugger_client = win.webContents && win.webContents.debugger;
    if (!debugger_client) {
        return Promise.resolve(false);
    }
    try {
        if (!debugger_client.isAttached()) {
            debugger_client.attach('1.3');
        }
    } catch (error) {
        return Promise.resolve(false);
    }
    const source = buildCkjrInitScript(context);
    if (!source) {
        return Promise.resolve(false);
    }
    win.webContents.on('did-fail-load', (event, code, description, failed_url, is_main_frame) => {
        if (!is_main_frame || code !== -101 || win.__xwzCkjrStaticPage) return;
        try {
            const failed = new URL(failed_url);
            if (failed.origin !== context.origin || failed.pathname !== context.pathName) return;
        } catch (_) { return; }
        win.__xwzCkjrStaticPage = true;
        let static_request_handler = null;
        let interception_started = false;
        // The shop and this official CDN serve the same SPA entry document.
        // Keep the shop's HTTPS origin/cookies when its TLS connection is reset.
        const entry = new Promise((resolve, reject) => {
            const request = https.get('https://kpstaticbj.wx.ckjr001.com/index.html', response => {
                if (response.statusCode !== 200) {
                    response.resume();
                    reject(new Error('Login entry unavailable'));
                    return;
                }
                const chunks = [];
                let size = 0;
                response.on('data', chunk => {
                    size += chunk.length;
                    if (size > 2 * 1024 * 1024) request.destroy(new Error('Login entry too large'));
                    else chunks.push(chunk);
                });
                response.on('error', reject);
                // Electron 8 / Node 12 can emit `end` after an aborted response.
                response.on('aborted', () => reject(new Error('Login entry interrupted')));
                response.on('end', () => {
                    if (!response.complete) {
                        reject(new Error('Login entry incomplete'));
                        return;
                    }
                    resolve(Buffer.concat(chunks).toString('base64'));
                });
            });
            request.on('error', reject);
            request.setTimeout(10000, () => request.destroy(new Error('Login entry timed out')));
        });
        entry.then(async body => {
            if (win.isDestroyed()) return;
            static_request_handler = (event, method, params) => {
                if (method !== 'Fetch.requestPaused') return;
                debugger_client.sendCommand('Fetch.fulfillRequest', {
                    requestId: params.requestId, responseCode: 200,
                    responseHeaders: [{name: 'Content-Type', value: 'text/html; charset=utf-8'}], body,
                }).catch(() => {});
            };
            debugger_client.on('message', static_request_handler);
            interception_started = true;
            await debugger_client.sendCommand('Fetch.enable', {patterns: [{
                urlPattern: context.origin + context.pathName + '*',
                resourceType: 'Document', requestStage: 'Request',
            }]});
            if (!win.isDestroyed()) await win.loadURL(context.targetUrl).catch(error => {
                // The site redirects the course to its login route during load.
                if (error.code !== 'ERR_ABORTED' && error.errno !== -3) throw error;
            });
        }).catch(async () => {
            if (static_request_handler) {
                debugger_client.removeListener('message', static_request_handler);
            }
            if (interception_started && !win.isDestroyed()) {
                try {
                    await debugger_client.sendCommand('Fetch.disable');
                } catch (_) { ; }
            }
            // Allow a fresh attempt only after the previous interception is gone.
            win.__xwzCkjrStaticPage = false;
            if (!win.isDestroyed()) require('electron').dialog.showErrorBox('创客匠人登录', '登录页加载失败，请检查网络后重试。');
        });
    });
    return debugger_client.sendCommand('Page.addScriptToEvaluateOnNewDocument', {source: source})
        .then(() => true)
        .catch(() => false);
}

function syncCkjrStoreContext(win, context) {
    if (!win || win.isDestroyed() || win.__xwzCkjrLoginComplete || !context) {
        return;
    }
    win.webContents.executeJavaScript(`
        (() => {
            const context = ${JSON.stringify(context)};
            // Failed navigations have an opaque origin and no usable storage.
            if (window.location.origin !== context.origin || window.location.pathname !== context.pathName) return null;
            function readValue(storage, key) {
                try {
                    return storage ? String(storage.getItem(key) || '') : '';
                } catch (error) {
                    return '';
                }
            }
            function normalizeValue(value) {
                value = String(value || '').trim();
                if (!value) {
                    return '';
                }
                if (['null', 'undefined', 'none', 'nan'].includes(value.toLowerCase())) {
                    return '';
                }
                return value;
            }
            function writeValue(storage, key, value) {
                if (!storage || !key || value === undefined || value === null || value === '') {
                    return false;
                }
                const normalized = String(value);
                try {
                    if (storage.getItem(key) === normalized) {
                        return false;
                    }
                    storage.setItem(key, normalized);
                    return true;
                } catch (error) {
                    return false;
                }
            }
            const current_href = String(window.location.href || '');
            const current_hash = String(window.location.hash || '');
            const document_title = String(document.title || '');
            const body_text = String((document.body && (document.body.innerText || document.body.textContent)) || '')
                .replace(/\s+/g, ' ')
                .trim();
            const html_length = String((document.documentElement && document.documentElement.innerHTML) || '').length;
            const company_id = normalizeValue(readValue(window.localStorage, 'companyId') || readValue(window.sessionStorage, 'companyId'));
            const before_login_url = normalizeValue(readValue(window.localStorage, 'beforeLoginUrl') || readValue(window.sessionStorage, 'beforeLoginUrl'));
            const stored_target_path = normalizeValue(
                readValue(window.localStorage, '__xwz_ckjr_target_path__')
                || readValue(window.sessionStorage, '__xwz_ckjr_target_path__')
            );
            const user_id = normalizeValue(readValue(window.localStorage, 'userId') || readValue(window.sessionStorage, 'userId'));
            const aes_key = normalizeValue(readValue(window.localStorage, 'aesKey') || readValue(window.sessionStorage, 'aesKey'));
            const aes_vi = normalizeValue(readValue(window.localStorage, 'aesVi') || readValue(window.sessionStorage, 'aesVi'));
            const store_id = normalizeValue(readValue(window.localStorage, 'X-STORE-ID') || readValue(window.sessionStorage, 'X-STORE-ID'));
            const is_visitor = normalizeValue(readValue(window.localStorage, 'isVisitor') || readValue(window.sessionStorage, 'isVisitor'));
            const company_token = normalizeValue(
                readValue(window.localStorage, context.companyId + '|token')
                || readValue(window.sessionStorage, context.companyId + '|token')
            );
            const token = normalizeValue(
                readValue(window.localStorage, 'token')
                || readValue(window.sessionStorage, 'token')
                || company_token
            );
            let changed = false;
            changed = writeValue(window.localStorage, 'companyId', context.companyId) || changed;
            changed = writeValue(window.sessionStorage, 'companyId', context.companyId) || changed;
            changed = writeValue(window.localStorage, '__xwz_ckjr_target_path__', context.targetPath) || changed;
            changed = writeValue(window.sessionStorage, '__xwz_ckjr_target_path__', context.targetPath) || changed;
            changed = writeValue(window.localStorage, '__xwz_ckjr_referee_id__', context.refereeId) || changed;
            changed = writeValue(window.sessionStorage, '__xwz_ckjr_referee_id__', context.refereeId) || changed;
            changed = writeValue(window.localStorage, '__xwz_ckjr_shareholder_id__', context.shareholderId) || changed;
            changed = writeValue(window.sessionStorage, '__xwz_ckjr_shareholder_id__', context.shareholderId) || changed;
            changed = writeValue(window.localStorage, '__xwz_ckjr_source_form__', context.sourceForm) || changed;
            changed = writeValue(window.sessionStorage, '__xwz_ckjr_source_form__', context.sourceForm) || changed;
            const needs_login_fix = !token && /#\\/?homePage\\/login\\/(?:qrLogin|wechatAuthPage|bindMobile)/i.test(current_href);
            const current_target_match = current_hash.match(/[?&]targetPath=([^&]+)/i);
            const current_target = current_target_match ? decodeURIComponent(current_target_match[1] || '') : '';
            const bootstrap_key = '__xwz_ckjr_bootstrap__';
            const bootstrap_count = Number(readValue(window.sessionStorage, bootstrap_key) || '0') || 0;
            const effective_company_id = company_id || context.companyId;
            const effective_before_login_url = before_login_url || stored_target_path || context.targetPath;
            let redirect_url = '';
            if (token) {
                changed = writeValue(window.localStorage, 'beforeLoginUrl', effective_before_login_url) || changed;
                changed = writeValue(window.sessionStorage, 'beforeLoginUrl', effective_before_login_url) || changed;
                changed = writeValue(window.localStorage, 'refereeId', context.refereeId) || changed;
                changed = writeValue(window.localStorage, 'reservedRefereeId', context.refereeId) || changed;
                changed = writeValue(window.localStorage, 'shareholderId', context.shareholderId) || changed;
                changed = writeValue(window.localStorage, 'sourceForm', context.sourceForm) || changed;
            }
            if (needs_login_fix) {
                const context_missing = effective_company_id !== context.companyId;
                const target_missing = !current_target || current_target !== context.targetPath;
                if ((context_missing || target_missing) && bootstrap_count < 2) {
                    writeValue(window.sessionStorage, bootstrap_key, String(bootstrap_count + 1));
                    redirect_url = context.loginUrl;
                }
            } else if (token) {
                try {
                    window.sessionStorage.removeItem(bootstrap_key);
                } catch (error) {
                    ;
                }
            }
            const local_data = {};
            const session_data = {};
            function assignSnapshot(target, key, value) {
                if (!value) {
                    return;
                }
                target[key] = String(value);
            }
            assignSnapshot(local_data, 'companyId', effective_company_id);
            assignSnapshot(session_data, 'companyId', effective_company_id);
            assignSnapshot(local_data, 'beforeLoginUrl', effective_before_login_url);
            assignSnapshot(session_data, 'beforeLoginUrl', effective_before_login_url);
            assignSnapshot(local_data, 'userId', user_id);
            assignSnapshot(session_data, 'userId', user_id);
            assignSnapshot(local_data, 'token', token);
            assignSnapshot(session_data, 'token', token);
            assignSnapshot(local_data, 'aesKey', aes_key);
            assignSnapshot(session_data, 'aesKey', aes_key);
            assignSnapshot(local_data, 'aesVi', aes_vi);
            assignSnapshot(session_data, 'aesVi', aes_vi);
            assignSnapshot(local_data, 'X-STORE-ID', store_id);
            assignSnapshot(session_data, 'X-STORE-ID', store_id);
            assignSnapshot(local_data, 'isVisitor', is_visitor);
            assignSnapshot(session_data, 'isVisitor', is_visitor);
            if (effective_company_id && company_token) {
                assignSnapshot(local_data, effective_company_id + '|token', company_token);
                assignSnapshot(session_data, effective_company_id + '|token', company_token);
            }
            let final_href = current_href;
            if (effective_before_login_url && /#\\/?homePage\\/login\\/(?:qrLogin|wechatAuthPage|bindMobile)/i.test(current_href)) {
                let route_path = effective_before_login_url;
                if (route_path.charAt(0) !== '/') {
                    route_path = '/' + route_path;
                }
                final_href = (window.location.origin || '') + (window.location.pathname || '') + '#' + route_path;
            }
            return {
                changed: changed,
                currentHref: current_href,
                currentHash: current_hash,
                companyId: effective_company_id,
                beforeLoginUrl: effective_before_login_url,
                currentTargetPath: current_target,
                hasToken: !!token,
                token: token,
                userId: user_id,
                aesKey: aes_key,
                aesVi: aes_vi,
                storeId: store_id,
                isVisitor: is_visitor,
                origin: window.location.origin || '',
                href: final_href,
                localStorage: local_data,
                sessionStorage: session_data,
                documentTitle: document_title,
                bodyTextPreview: body_text.slice(0, 240),
                hasVisibleContent: !!body_text || html_length > 1024,
                htmlLength: html_length,
                redirectUrl: redirect_url,
            };
        })();
    `).then((state) => {
        if (!state || win.isDestroyed() || win.__xwzCkjrLoginComplete) {
            return;
        }
        const payload = buildCkjrPayloadFromState(state, context);
        if (payload && !ckjr_save_inflight) {
            ckjr_save_inflight = true;
            win.__xwzCkjrLoginComplete = saveLoginPayload(payload) === true;
            return;
        }
        if (state.redirectUrl && !win.isDestroyed()) {
            const current_url = getSafeWindowUrl(win);
            if (state.redirectUrl !== current_url) {
                win.loadURL(state.redirectUrl);
            }
        }
    }).catch(() => {
        ;
    });
}

function normalizeCkjrToken(token) {
    token = normalizeCkjrStateText(token);
    if (/^bearer\s+/i.test(token)) {
        return token.replace(/^bearer\s+/i, '').trim();
    }
    return token;
}

function normalizeCkjrStateText(value) {
    value = String(value || '').trim();
    if (!value) {
        return '';
    }
    if (['null', 'undefined', 'none', 'nan'].includes(value.toLowerCase())) {
        return '';
    }
    return value;
}

function isCkjrVisitorState(state, user_id) {
    const visitor_value = normalizeCkjrStateText((state && state.isVisitor) || '').toLowerCase();
    return user_id === '-100'
        || visitor_value === '1'
        || visitor_value === 'true';
}

function hasCkjrAuthenticatedRecord(auth_records, context, token, company_id, user_id) {
    const normalized_token = normalizeCkjrToken(token || '');
    const expected_company_id = normalizeCkjrStateText(
        (context && context.companyId)
        || company_id
        || ''
    ).toLowerCase();
    const actual_company_id = normalizeCkjrStateText(company_id || '').toLowerCase();
    if (expected_company_id && actual_company_id && actual_company_id !== expected_company_id) {
        return false;
    }
    const expected_user_id = normalizeCkjrStateText(user_id || '');
    const now = Date.now();
    const recent_records = (auth_records || []).slice(-20).reverse();
    return recent_records.some((record) => {
        if (!record || typeof record !== 'object') {
            return false;
        }
        const record_time = Number(record.timestamp || 0);
        if (record_time > 0 && now - record_time > 10 * 60 * 1000) {
            return false;
        }
        const headers = {};
        Object.keys(record.headers || {}).forEach((name) => {
            headers[String(name || '').toLowerCase()] = String((record.headers || {})[name] || '').trim();
        });
        const record_token = normalizeCkjrToken(headers.authorization || '');
        if (!record_token) {
            return false;
        }
        if (normalized_token && record_token !== normalized_token) {
            return false;
        }
        const x_dmp = normalizeCkjrStateText(headers['x-dmp'] || '');
        let record_company_id = '';
        let record_user_id = '';
        if (x_dmp) {
            const company_match = x_dmp.match(/(?:^|&)c=([^&]+)/i);
            const user_match = x_dmp.match(/(?:^|&)u=([^&]+)/i);
            try {
                if (company_match) {
                    record_company_id = normalizeCkjrStateText(decodeURIComponent(company_match[1] || '')).toLowerCase();
                }
                if (user_match) {
                    record_user_id = normalizeCkjrStateText(decodeURIComponent(user_match[1] || ''));
                }
            } catch (error) {
                return false;
            }
        }
        if (expected_company_id && record_company_id && record_company_id !== expected_company_id) {
            return false;
        }
        if (expected_user_id && record_user_id && record_user_id !== expected_user_id) {
            return false;
        }
        return true;
    });
}

function buildCkjrPayloadFromState(state, context) {
    if (!state || !context) {
        return null;
    }
    const auth_records = ckjr_auth_records.slice(-50);
    const record_auth = extractCkjrRecordAuthState(auth_records);
    const token = normalizeCkjrToken(state.token || record_auth.token || '');
    if (!token) {
        return null;
    }
    const jwt_payload = decodeCkjrJwtPayload(token);
    const company_id = normalizeCkjrStateText(
        state.companyId
        || record_auth.companyId
        || jwt_payload.c
        || context.companyId
        || ''
    );
    if (!company_id) {
        return null;
    }
    const user_id = normalizeCkjrStateText(
        state.userId
        || record_auth.userId
        || jwt_payload.u
        || ''
    );
    const route_path = normalizeCkjrRoutePath(
        state.beforeLoginUrl
        || context.targetPath
        || state.currentTargetPath
        || ''
    );
    const current_href = normalizeCkjrStateText(state.currentHref || '');
    let href = normalizeCkjrStateText(state.href || '');
    if ((!href || /#\/?homePage\/login\//i.test(href) || !isCkjrContentUrl(href)) && route_path && context.baseUrl) {
        href = context.baseUrl + '#' + route_path;
    }
    if (!href) {
        href = normalizeCkjrStateText(context.targetUrl || '');
    }
    const ckjr_is_visitor = isCkjrVisitorState(state, user_id);
    const has_authenticated_record = hasCkjrAuthenticatedRecord(auth_records, context, token, company_id, user_id);
    // Store homepages complete login too; the downloader selects a course after
    // receiving the authenticated store context.
    if (!(token && company_id && user_id && !ckjr_is_visitor && has_authenticated_record)) {
        return null;
    }

    const local_storage = Object.assign({}, state.localStorage || {});
    const session_storage = Object.assign({}, state.sessionStorage || {});
    const aes_key = normalizeCkjrStateText(state.aesKey || '');
    const aes_vi = normalizeCkjrStateText(state.aesVi || '');
    const store_id = normalizeCkjrStateText(state.storeId || record_auth.storeId || '');

    if (!local_storage.companyId && !session_storage.companyId) {
        local_storage.companyId = company_id;
    }
    if (!local_storage.beforeLoginUrl && !session_storage.beforeLoginUrl && route_path) {
        local_storage.beforeLoginUrl = route_path;
    }
    if (!local_storage.userId && !session_storage.userId && user_id) {
        local_storage.userId = user_id;
    }
    if (!local_storage.token && !session_storage.token) {
        local_storage.token = token;
    }
    if (!local_storage[company_id + '|token'] && !session_storage[company_id + '|token']) {
        local_storage[company_id + '|token'] = token;
    }
    if (!local_storage.aesKey && !session_storage.aesKey && aes_key) {
        local_storage.aesKey = aes_key;
    }
    if (!local_storage.aesVi && !session_storage.aesVi && aes_vi) {
        local_storage.aesVi = aes_vi;
    }
    if (!local_storage['X-STORE-ID'] && !session_storage['X-STORE-ID'] && store_id) {
        local_storage['X-STORE-ID'] = store_id;
    }

    return {
        href: href,
        loginHref: current_href,
        origin: normalizeCkjrStateText(state.origin || context.origin || record_auth.origin || ''),
        cookie: '',
        localStorage: local_storage,
        sessionStorage: session_storage,
        companyId: company_id,
        userId: user_id,
        token: token,
        aesKey: aes_key,
        aesVi: aes_vi,
        'X-STORE-ID': store_id,
        authRecords: auth_records,
        userAgent: user_agent,
    };
}

function isYouzanCourseDetailUrl(url) {
    url = String(url || '').toLowerCase();
    return url.indexOf('/wscvis/course/detail/') !== -1;
}

function isYouzanLoginName(name) {
    name = String(name || '');
    return name === 'youzan' || name.startsWith('youzan.');
}

function isYouzanCookie(cookie) {
    if (!cookie || !cookie.name || !cookie.value) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    return !domain || domain === 'youzan.com' || domain.endsWith('.youzan.com');
}

function filterYouzanCookies(cookies) {
    const include_names = ['KDTSESSIONID', 'nobody_sign', '_kdt_id_', 'open_token', 'dfp', 'yz_fp_hash', 'acw_tc'];
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isYouzanCookie(cookie) || !include_names.includes(String(cookie.name || ''))) {
            return;
        }
        const key = [
            String(cookie.name || ''),
            normalizeCookieDomain(cookie.domain || cookie.host_key || ''),
            String(cookie.path || '/')
        ].join('|');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function hasYouzanLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterYouzanCookies(cookies));
    return !!(cookie_map.KDTSESSIONID && cookie_map.nobody_sign);
}

function getYouzanKdtId(cookie_value, target_url = '') {
    const cookie_map = parseCookieString(cookie_value);
    const cookie_kdt_id = String(cookie_map._kdt_id_ || '').trim();
    if (cookie_kdt_id) {
        return cookie_kdt_id;
    }
    if (isYouzanLoginName(login_name)) {
        const login_parts = String(login_name || '').split('.');
        if (login_parts.length > 1 && login_parts[1]) {
            return login_parts.slice(1).join('.').trim();
        }
    }
    try {
        const parsed = new URL(String(target_url || ''));
        const query_kdt_id = parsed.searchParams.get('kdt_id') || parsed.searchParams.get('kdtId') || '';
        return String(query_kdt_id || '').trim();
    } catch (error) {
        return '';
    }
}

function buildYouzanCookieValue(cookies, target_url = '') {
    const cookie_map = buildCookieMap(filterYouzanCookies(cookies));
    const kdt_id = getYouzanKdtId(buildCookieValueFromMap(cookie_map), target_url);
    if (kdt_id && !cookie_map._kdt_id_) {
        cookie_map._kdt_id_ = kdt_id;
    }
    const ordered_names = ['KDTSESSIONID', 'nobody_sign', '_kdt_id_', 'open_token', 'dfp', 'yz_fp_hash', 'acw_tc'];
    const ordered_map = {};
    ordered_names.forEach((name) => {
        if (cookie_map[name]) {
            ordered_map[name] = cookie_map[name];
        }
    });
    Object.keys(cookie_map).forEach((name) => {
        if (!ordered_map[name]) {
            ordered_map[name] = cookie_map[name];
        }
    });
    return buildCookieValueFromMap(ordered_map);
}

function getYouzanShopBase(target_url = '') {
    try {
        const parsed = new URL(String(target_url || ''));
        const host = String(parsed.hostname || '').toLowerCase();
        if (host === 'youzan.com' || host.endsWith('.youzan.com')) {
            return parsed.origin;
        }
    } catch (error) {
        ;
    }
    return 'https://www.youzan.com';
}

function buildYouzanMemberCenterUrl(target_url, cookie_value) {
    const shop_base = getYouzanShopBase(target_url);
    const kdt_id = getYouzanKdtId(cookie_value, target_url);
    let url = shop_base.replace(/\/+$/, '') + '/wscuser/membercenter';
    if (kdt_id) {
        url += '?kdt_id=' + encodeURIComponent(kdt_id);
    }
    return url;
}

function looksLikeYouzanLoggedInPage(result, target_url) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const final_url = String(result.url || '').toLowerCase();
    const body = String(result.body || '');
    const body_lower = body.toLowerCase();
    if (final_url.indexOf('passport.youzan.com') !== -1 || final_url.indexOf('/login') !== -1) {
        return false;
    }
    if (body_lower.indexOf('scan-login') !== -1 || body.indexOf('\u626b\u7801\u767b\u5f55') !== -1) {
        return false;
    }
    return true;
}

function validateYouzanCookieValue(cookie_value, target_url = '') {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    const cookie_map = parseCookieString(cookie_value);
    if (!cookie_map.KDTSESSIONID || !cookie_map.nobody_sign) {
        return Promise.resolve(false);
    }
    const validate_url = buildYouzanMemberCenterUrl(target_url, cookie_value);
    const shop_base = getYouzanShopBase(validate_url);
    return fetchUrlWithCookieValue(validate_url, cookie_value, 0, {
        'Referer': target_url || validate_url,
        'Origin': shop_base,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
        .then((result) => looksLikeYouzanLoggedInPage(result, validate_url))
        .catch(() => false);
}

function saveValidatedYouzanCookie(cookie_value, target_url = '') {
    if (youzan_save_inflight || youzan_validate_inflight) {
        return;
    }
    youzan_validate_inflight = true;
    validateYouzanCookieValue(cookie_value, target_url)
        .then((valid) => {
            youzan_validate_inflight = false;
            if (!valid || youzan_save_inflight) {
                return;
            }
            youzan_save_inflight = true;
            saveLoginCookieValue(cookie_value);
        })
        .catch(() => {
            youzan_validate_inflight = false;
        });
}

function handleYouzanPostLogin(win, cookies) {
    if (youzan_save_inflight || !win || win.isDestroyed()) {
        return;
    }
    const target_url = isYouzanCourseDetailUrl(extra_arg) ? String(extra_arg || '') : '';
    const current_url = getSafeWindowUrl(win);
    const cookie_value = buildYouzanCookieValue(cookies, target_url || current_url);
    if (!cookie_value) {
        return;
    }
    if (hasYouzanLoginCookies(cookies)) {
        saveValidatedYouzanCookie(cookie_value, target_url || current_url);
        return;
    }
    if (target_url && current_url !== target_url && !isYouzanCourseDetailUrl(current_url)) {
        try {
            win.loadURL(target_url);
        } catch (error) {
            ;
        }
        return;
    }
    if (!target_url || !isYouzanCourseDetailUrl(current_url)) {
        youzan_save_inflight = true;
        saveLoginCookieValue(cookie_value);
        return;
    }
    if (youzan_page_check_inflight) {
        return;
    }
    youzan_page_check_inflight = true;
    win.webContents.executeJavaScript(`
        (() => {
            function cleanText(text) {
                return String(text || '').replace(/\\s+/g, '').trim();
            }
            function isClaimText(text) {
                return [
                    '立即领取',
                    '免费领取',
                    '领取专栏',
                    '确认领取',
                    '立即开通',
                ].includes(text);
            }
            const bodyText = cleanText(document.body && document.body.innerText);
            const clickable = Array.from(document.querySelectorAll('button, a, div, span'))
                .map((node) => ({
                    node,
                    text: cleanText(node.innerText || node.textContent || ''),
                }))
                .filter((item) => item.text);
            const claimItem = clickable.find((item) => isClaimText(item.text));
            if (claimItem && claimItem.node && typeof claimItem.node.click === 'function') {
                claimItem.node.click();
            }
            return {
                href: location.href || '',
                loginVisible: bodyText.includes('扫码登录'),
                claimVisible: clickable.some((item) => isClaimText(item.text)) || bodyText.includes('领取专栏后播放视频'),
                playReady: !bodyText.includes('领取专栏后播放视频')
                    && (bodyText.includes('播放视频') || bodyText.includes('继续学习') || bodyText.includes('试看')),
            };
        })();
    `).then((state) => {
        youzan_page_check_inflight = false;
        if (!state || state.loginVisible) {
            return;
        }
        if (state.claimVisible && !state.playReady) {
            return;
        }
        youzan_save_inflight = true;
        saveLoginCookieValue(cookie_value);
    }).catch((error) => {
        youzan_page_check_inflight = false;
    });
}

function isTmoocCookie(cookie) {
    if (!cookie || !cookie.name) {
        return false;
    }
    const domain = String(cookie.domain || '').toLowerCase();
    return domain === 'tmooc.cn'
        || domain.endsWith(TMOOC_COOKIE_DOMAIN_SUFFIX);
}

function buildTmoocCookieValue(cookies) {
    return buildCookieValue((cookies || []).filter((cookie) => isTmoocCookie(cookie)));
}

function parseGenericCookieString(cookie_string) {
    let cookie_map = {};
    String(cookie_string || '').split(';').forEach((item) => {
        item = String(item || '').trim();
        if (!item) {
            return;
        }
        const equal_index = item.indexOf('=');
        if (equal_index <= 0) {
            return;
        }
        const name = item.slice(0, equal_index).trim();
        let value = item.slice(equal_index + 1).trim();
        if (!name || !value) {
            return;
        }
        try {
            value = decodeURIComponent(value);
        } catch (error) {
            ;
        }
        cookie_map[name] = value;
    });
    return cookie_map;
}

function buildCookieValueFromMap(cookie_map) {
    let cookie_value = '';
    Object.keys(cookie_map || {}).forEach((name) => {
        const value = cookie_map[name];
        if (!name || value === undefined || value === null || value === '') {
            return;
        }
        if (cookie_value.length !== 0) {
            cookie_value += ';';
        }
        cookie_value += name + '=' + String(value);
    });
    return cookie_value;
}

function buildLeduCookieValue(payload) {
    const normalized = normalizeLeduPayload(payload);
    const cookie_map = {};
    [
        'tal_token',
        'tal_code',
        'token',
        'authorization',
        'user_id',
        'user_id_str',
        'user_uid',
        'user_name',
        'device_id',
        'puid',
        'open_id',
        'union_id',
        'client_type',
        'area_code',
        'category_types',
        'belong_citys',
        'home_select_city',
        'hb_token',
        'classroom_token',
        'version',
        'system_name',
        'guid',
        'device_cpu_type',
        'device_memory',
        'client_id',
    ].forEach((key) => {
        const value = normalized[key];
        if (value === undefined || value === null || value === '') {
            return;
        }
        cookie_map[key] = encodeURIComponent(String(value));
    });
    [
        'user_information',
        'system_info',
        'cpu_mem_info',
        'kebiao_user_info',
    ].forEach((key) => {
        const value = normalizeLeduObject(normalized[key]);
        if (!Object.keys(value).length) {
            return;
        }
        cookie_map[key] = encodeURIComponent(JSON.stringify(value));
    });
    return buildCookieValueFromMap(cookie_map);
}

function safeJsonParse(text, default_value = null) {
    try {
        return JSON.parse(text);
    } catch (error) {
        return default_value;
    }
}

function readStoredLoginPayload(target_login_name) {
    let cookies_obj = readCookiesObject();
    return cookies_obj[target_login_name];
}

function normalizeLeduString(value) {
    if (value === undefined || value === null) {
        return '';
    }
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        return String(value).trim();
    }
    return '';
}

function normalizeLeduObject(value) {
    if (!value) {
        return {};
    }
    if (typeof value === 'string') {
        const raw = String(value || '').trim();
        if (!raw) {
            return {};
        }
        const parsed = safeJsonParse(raw, null);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            return parsed;
        }
        return {};
    }
    if (typeof value === 'object' && !Array.isArray(value)) {
        return value;
    }
    return {};
}

function mergeLeduObjectFields() {
    let merged = {};
    Array.prototype.slice.call(arguments).forEach((value) => {
        const obj = normalizeLeduObject(value);
        Object.keys(obj).forEach((key) => {
            const item = obj[key];
            if (item !== undefined && item !== null && item !== '') {
                merged[key] = item;
            }
        });
    });
    return merged;
}

function pickLeduString() {
    for (let index = 0; index < arguments.length; index += 1) {
        const text = normalizeLeduString(arguments[index]);
        if (text) {
            return text;
        }
    }
    return '';
}

function normalizeLeduDeviceMemory(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        return pickLeduString(value.total, value.value, value.size);
    }
    const text = normalizeLeduString(value);
    if (!text) {
        return '';
    }
    if (text.startsWith('{') || text.startsWith('[')) {
        const parsed = safeJsonParse(text, null);
        if (parsed && typeof parsed === 'object') {
            return normalizeLeduDeviceMemory(parsed);
        }
    }
    return text;
}

function normalizeLeduPayload(payload) {
    if (!payload) {
        return {};
    }
    if (typeof payload === 'string') {
        const raw = String(payload || '').trim();
        if (!raw) {
            return {};
        }
        if (raw.startsWith('{') || raw.startsWith('[')) {
            payload = safeJsonParse(raw, {});
        } else {
            payload = parseGenericCookieString(raw);
        }
    }
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        return {};
    }
    const cookies = normalizeLeduObject(payload.cookies);
    const localStorage = normalizeLeduObject(payload.localStorage);
    const sessionStorage = normalizeLeduObject(payload.sessionStorage);
    const user = mergeLeduObjectFields(payload.user, payload.userInfo, payload.user_info);
    const user_information = mergeLeduObjectFields(
        payload.user_information,
        payload.userInformation,
        localStorage.userInformation,
        localStorage.LDYYT_UINFO_PROD,
        sessionStorage.userInformation,
        sessionStorage.LDYYT_UINFO_PROD
    );
    const system_info = mergeLeduObjectFields(
        payload.system_info,
        payload.systemInfo,
        localStorage.systemInfo,
        sessionStorage.systemInfo
    );
    const cpu_mem_info = mergeLeduObjectFields(
        payload.cpu_mem_info,
        payload.cpuMemInfo,
        localStorage.cpuMemInfo,
        sessionStorage.cpuMemInfo
    );
    const kebiao_user_info = mergeLeduObjectFields(
        payload.kebiao_user_info,
        payload.KEBIAO_USER_INFO,
        localStorage.KEBIAO_USER_INFO,
        sessionStorage.KEBIAO_USER_INFO
    );
    let result = {
        href: pickLeduString(payload.href, payload.url),
        tal_token: pickLeduString(payload.tal_token, payload.talToken, payload['tal-token']),
        tal_code: pickLeduString(payload.tal_code, payload.talCode, payload.code),
        token: pickLeduString(
            payload.token,
            payload.access_token,
            payload.accessToken,
            payload.authorization,
            payload.Authorization,
            user_information.token,
            user_information.authorization,
            cookies.LEDU_AUTHORIZATION_PROD
        ),
        authorization: pickLeduString(
            payload.authorization,
            payload.Authorization,
            user_information.authorization,
            user_information.token,
            cookies.LEDU_AUTHORIZATION_PROD
        ),
        user_id: pickLeduString(
            payload.user_id,
            payload.userId,
            payload.studentId,
            payload.stuId,
            payload.stu_id,
            payload.ui,
            payload.id,
            user.user_id,
            user.userId,
            user.studentId,
            user.id,
            user_information.userId,
            user_information.stuId,
            user_information.stuIdStr,
            user_information.studentId,
            user_information.ui,
            cookies.LEDU_STUID_PROD,
            sessionStorage.LEDU_STUID_PROD,
            kebiao_user_info.stuId,
            kebiao_user_info.stuIdStr
        ),
        user_id_str: pickLeduString(
            payload.user_id_str,
            payload.userIdStr,
            payload.studentId,
            payload.stuId,
            payload.stu_id,
            payload.ui,
            user.studentId,
            user_information.stuIdStr,
            user_information.studentId,
            user_information.stuId,
            user_information.userId,
            user_information.ui,
            cookies.LEDU_STUID_PROD,
            sessionStorage.LEDU_STUID_PROD,
            kebiao_user_info.stuId,
            kebiao_user_info.stuIdStr
        ),
        user_uid: pickLeduString(
            payload.user_uid,
            payload.userUid,
            payload.uid,
            user.uid,
            user_information.uid,
            user_information.puid,
            user_information.pu_uid,
            cookies.LEDU_PUID_PROD,
            kebiao_user_info.uid
        ),
        user_name: pickLeduString(
            payload.user_name,
            payload.userName,
            payload.name,
            payload.nickName,
            payload.nickname,
            payload.username,
            user.name,
            user.userName,
            user.username,
            user_information.username,
            user_information.name,
            user_information.userName,
            user_information.nickname
        ),
        device_id: pickLeduString(
            payload.device_id,
            payload.deviceId,
            payload.devid,
            payload['d-id'],
            payload.dv,
            user_information.deviceId,
            user_information.device_id,
            user_information.devid,
            user_information.dv,
            localStorage.deviceId,
            localStorage.device_id,
            localStorage.devid,
            localStorage['d-id'],
            localStorage.dv,
            sessionStorage.deviceId,
            sessionStorage.device_id,
            sessionStorage.devid,
            sessionStorage['d-id'],
            sessionStorage.dv
        ),
        puid: pickLeduString(
            payload.puid,
            payload.puId,
            user_information.puid,
            user_information.uid,
            user_information.pu_uid,
            cookies.LEDU_PUID_PROD,
            kebiao_user_info.uid
        ),
        open_id: pickLeduString(
            payload.open_id,
            payload.openId,
            payload.openid,
            cookies.LEDU_OPENID_PROD,
            localStorage.LDYYT_OPEN_ID_PROD,
            sessionStorage.LDYYT_OPEN_ID_PROD
        ),
        union_id: pickLeduString(
            payload.union_id,
            payload.unionId,
            payload.unionid,
            cookies.LEDU_UNIONID_PROD,
            localStorage.LDYYT_UNION_ID_PROD,
            sessionStorage.LDYYT_UNION_ID_PROD
        ),
        client_type: pickLeduString(payload.client_type, payload.clientType, user.clientType, user_information.clientType),
        area_code: pickLeduString(
            payload.area_code,
            payload.areaCode,
            payload.area,
            payload.local_city,
            payload.city_id,
            user.area_code,
            user.areaCode,
            user.local_city,
            user.city_id,
            user_information.area_code,
            user_information.areaCode,
            user_information.area,
            user_information.local_city,
            user_information.city_id
        ),
        category_types: pickLeduString(
            payload.category_types,
            payload.categoryTypes,
            user.categoryTypes,
            user_information.categoryTypes
        ),
        belong_citys: pickLeduString(
            payload.belong_citys,
            payload.belongCitys,
            user.belongCitys,
            user_information.belongCitys
        ),
        home_select_city: pickLeduString(
            payload.home_select_city,
            payload.homeSelectCity,
            user.homeSelectCity,
            user_information.homeSelectCity
        ),
        hb_token: pickLeduString(
            payload.hb_token,
            payload.hbToken,
            user_information.hb_token,
            user_information.hbToken,
            kebiao_user_info.token
        ),
        classroom_token: pickLeduString(
            payload.classroom_token,
            payload.classroomToken,
            localStorage.classroomToken,
            sessionStorage.classroomToken
        ),
        version: pickLeduString(payload.version, system_info.version, kebiao_user_info.clientVersion),
        system_name: pickLeduString(payload.system_name, payload.systemName, system_info.systemName),
        guid: pickLeduString(payload.guid, system_info.guid, kebiao_user_info.guid),
        device_cpu_type: pickLeduString(payload.device_cpu_type, payload.deviceCpuType, cpu_mem_info.deviceCpuType),
        device_memory: normalizeLeduDeviceMemory(
            payload.device_memory || payload.deviceMemory || cpu_mem_info.deviceMemory || cpu_mem_info.device_memory
        ),
        client_id: pickLeduString(payload.client_id, payload.clientId, localStorage.clientId, sessionStorage.clientId),
        user_information: user_information,
        system_info: system_info,
        cpu_mem_info: cpu_mem_info,
        kebiao_user_info: kebiao_user_info,
    };
    if (!result.token) {
        result.token = result.authorization;
    }
    if (!result.authorization) {
        result.authorization = result.token;
    }
    if (!result.user_id_str) {
        result.user_id_str = result.user_id;
    }
    if (!result.user_id) {
        result.user_id = result.user_id_str;
    }
    if (!result.user_uid && result.puid) {
        result.user_uid = result.puid;
    }
    if (!result.hb_token) {
        result.hb_token = result.classroom_token;
    }
    return result;
}

function mergeLeduPayload(base_payload, next_payload) {
    let merged = Object.assign({}, normalizeLeduPayload(base_payload));
    let next = normalizeLeduPayload(next_payload);
    [
        'href',
        'tal_token',
        'tal_code',
        'token',
        'authorization',
        'user_id',
        'user_id_str',
        'user_uid',
        'user_name',
        'device_id',
        'puid',
        'open_id',
        'union_id',
        'client_type',
        'area_code',
        'category_types',
        'belong_citys',
        'home_select_city',
        'hb_token',
        'classroom_token',
        'version',
        'system_name',
        'guid',
        'device_cpu_type',
        'device_memory',
        'client_id',
    ].forEach((key) => {
        if (next[key]) {
            merged[key] = next[key];
        }
    });
    [
        'user_information',
        'system_info',
        'cpu_mem_info',
        'kebiao_user_info',
    ].forEach((key) => {
        const value = normalizeLeduObject(next[key]);
        if (Object.keys(value).length) {
            merged[key] = Object.assign({}, normalizeLeduObject(merged[key]), value);
        }
    });
    if (!merged.token) {
        merged.token = merged.authorization || '';
    }
    if (!merged.authorization) {
        merged.authorization = merged.token || '';
    }
    if (!merged.user_id_str) {
        merged.user_id_str = merged.user_id || '';
    }
    if (!merged.user_id) {
        merged.user_id = merged.user_id_str || '';
    }
    if (!merged.user_uid) {
        merged.user_uid = merged.puid || '';
    }
    if (!merged.hb_token) {
        merged.hb_token = merged.classroom_token || '';
    }
    return merged;
}

function isLeduPayloadBetter(next_payload, current_payload) {
    let next = normalizeLeduPayload(next_payload);
    let current = normalizeLeduPayload(current_payload);
    return [
        'token',
        'authorization',
        'user_id',
        'user_id_str',
        'device_id',
        'tal_token',
        'tal_code',
        'puid',
        'open_id',
        'union_id',
        'user_uid',
        'user_name',
        'client_type',
        'area_code',
        'category_types',
        'belong_citys',
        'home_select_city',
        'hb_token',
        'classroom_token',
        'version',
        'system_name',
        'guid',
        'device_cpu_type',
        'device_memory',
        'client_id',
    ].some((key) => {
        const next_value = String(next[key] || '').trim();
        const current_value = String(current[key] || '').trim();
        return !!next_value && next_value !== current_value;
    }) || [
        'user_information',
        'system_info',
        'cpu_mem_info',
        'kebiao_user_info',
    ].some((key) => {
        const next_value = JSON.stringify(normalizeLeduObject(next[key]));
        const current_value = JSON.stringify(normalizeLeduObject(current[key]));
        return next_value !== '{}' && next_value !== current_value;
    });
}

function isLeduPayloadReady(payload) {
    let normalized = normalizeLeduPayload(payload);
    const pc_student_id = pickLeduString(
        normalized.user_uid,
        normalized.puid,
        /^\d+$/.test(String(normalized.user_id || '').trim()) ? normalized.user_id : '',
        /^\d+$/.test(String(normalized.user_id_str || '').trim()) ? normalized.user_id_str : ''
    );
    if (!(normalized.token && (normalized.user_id_str || normalized.user_id))) {
        return false;
    }
    return !!(pc_student_id || normalized.hb_token || normalized.classroom_token);
}

function looksLikeLeduPcStudentId(value) {
    return /^\d+$/.test(String(value || '').trim());
}

function buildLeduPcRequestHeaders(payload, extra_headers = null) {
    const normalized = normalizeLeduPayload(payload);
    const pc_student_id = pickLeduString(
        normalized.user_uid,
        normalized.puid,
        looksLikeLeduPcStudentId(normalized.user_id) ? normalized.user_id : '',
        looksLikeLeduPcStudentId(normalized.user_id_str) ? normalized.user_id_str : ''
    );
    const headers = Object.assign({
        'User-Agent': LEDU_PC_USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'identity',
        'Content-Type': 'application/json;charset=UTF-8',
        'terminal': LEDU_PC_TERMINAL,
        'product': LEDU_PC_PRODUCT,
        'clientId': pickLeduString(normalized.client_id, LEDU_PC_CLIENT_ID),
        'version': pickLeduString(normalized.version, LEDU_PC_VERSION),
        'token': pickLeduString(normalized.hb_token, normalized.classroom_token, normalized.token),
        'stuId': pc_student_id,
    }, extra_headers || {});
    Object.keys(headers).forEach((name) => {
        const value = headers[name];
        if (value === undefined || value === null || value === '') {
            delete headers[name];
        }
    });
    return headers;
}

function requestJsonUrl(method, target_url, payload = null, extra_headers = null) {
    return new Promise((resolve) => {
        let settled = false;
        function finish(result) {
            if (!settled) {
                settled = true;
                resolve(result);
            }
        }
        try {
            let final_url = String(target_url || '');
            const upper_method = String(method || 'GET').toUpperCase();
            if (upper_method === 'GET' && payload && typeof payload === 'object') {
                const url_obj = new URL(final_url);
                Object.keys(payload).forEach((name) => {
                    const value = payload[name];
                    if (value === undefined || value === null || value === '') {
                        return;
                    }
                    url_obj.searchParams.set(name, String(value));
                });
                final_url = url_obj.toString();
            }
            const parsed = new URL(final_url);
            const request_body = upper_method === 'GET' || payload === null || payload === undefined
                ? ''
                : JSON.stringify(payload);
            const request_headers = Object.assign({
                'User-Agent': LEDU_PC_USER_AGENT,
                'Accept': 'application/json, text/plain, */*',
                'Accept-Encoding': 'identity',
            }, extra_headers || {});
            if (upper_method !== 'GET') {
                if (!request_headers['Content-Type']) {
                    request_headers['Content-Type'] = 'application/json;charset=UTF-8';
                }
                request_headers['Content-Length'] = Buffer.byteLength(request_body);
            }
            const client = parsed.protocol === 'http:' ? http : https;
            const request = client.request({
                protocol: parsed.protocol,
                hostname: parsed.hostname,
                port: parsed.port || undefined,
                path: parsed.pathname + parsed.search,
                method: upper_method,
                headers: request_headers,
            }, (response) => {
                let body = '';
                response.setEncoding('utf8');
                response.on('data', (chunk) => {
                    if (body.length < 524288) {
                        body += chunk;
                    }
                });
                response.on('end', () => {
                    finish({
                        statusCode: Number(response.statusCode || 0),
                        url: final_url,
                        headers: response.headers || {},
                        body: body,
                    });
                });
            });
            request.on('error', () => {
                finish(null);
            });
            request.setTimeout(12000, () => {
                request.destroy();
                finish(null);
            });
            if (request_body) {
                request.write(request_body);
            }
            request.end();
        } catch (error) {
            finish(null);
        }
    });
}

function parseJsonResponseBody(result) {
    if (!result) {
        return null;
    }
    if (result.body && typeof result.body === 'object') {
        return result.body;
    }
    return safeJsonParse(String(result.body || '').trim(), null);
}

function buildLeduPcAuthPatch(payload, response_body = null) {
    const normalized = normalizeLeduPayload(payload);
    const response_data = response_body && typeof response_body === 'object'
        ? response_body
        : {};
    const pc_student_id = pickLeduString(
        response_data.pu_uid,
        normalized.user_uid,
        normalized.puid,
        looksLikeLeduPcStudentId(normalized.user_id) ? normalized.user_id : '',
        looksLikeLeduPcStudentId(normalized.user_id_str) ? normalized.user_id_str : ''
    );
    const h5_student_id = pickLeduString(
        normalized.user_id_str,
        !looksLikeLeduPcStudentId(normalized.user_id) ? normalized.user_id : '',
        normalized.user_information && normalized.user_information.stuId,
        normalized.user_information && normalized.user_information.studentId
    );
    const hb_token = pickLeduString(
        response_data.hb_token,
        normalized.hb_token,
        normalized.classroom_token,
        normalized.token
    );
    const user_name = pickLeduString(
        response_data.nickname,
        response_data.username,
        normalized.user_name
    );
    const area_code = pickLeduString(
        response_data.bindingCode,
        normalized.area_code
    );
    const user_information = Object.assign({}, normalizeLeduObject(normalized.user_information));
    if (pc_student_id) {
        user_information.user_id = pc_student_id;
        user_information.uid = pc_student_id;
        user_information.puid = pc_student_id;
        user_information.pu_uid = pc_student_id;
    }
    if (h5_student_id) {
        user_information.userId = h5_student_id;
        user_information.stuId = h5_student_id;
        user_information.stuIdStr = h5_student_id;
        user_information.studentId = h5_student_id;
        user_information.ui = h5_student_id;
    }
    if (hb_token) {
        user_information.hb_token = hb_token;
        user_information.hbToken = hb_token;
    }
    const auth_token = pickLeduString(normalized.authorization, normalized.token);
    if (auth_token) {
        user_information.authorization = auth_token;
        user_information.token = pickLeduString(normalized.token, auth_token);
    }
    if (user_name) {
        user_information.nickname = user_name;
        user_information.username = user_name;
        user_information.userName = user_name;
    }
    if (area_code) {
        user_information.bindingCode = area_code;
        user_information.areaCode = area_code;
    }
    if (normalized.device_id) {
        user_information.deviceId = normalized.device_id;
        user_information.dv = normalized.device_id;
    }
    return normalizeLeduPayload({
        user_id: pc_student_id,
        user_id_str: h5_student_id,
        user_uid: pc_student_id,
        puid: pc_student_id,
        user_name: user_name,
        area_code: area_code,
        hb_token: hb_token,
        classroom_token: hb_token,
        client_id: pickLeduString(normalized.client_id, LEDU_PC_CLIENT_ID),
        version: pickLeduString(normalized.version, LEDU_PC_VERSION),
        system_name: pickLeduString(normalized.system_name, 'Windows'),
        guid: pickLeduString(normalized.guid, normalized.device_id),
        user_information: user_information,
    });
}

async function refreshLeduPayloadPcToken(payload) {
    let normalized = normalizeLeduPayload(payload);
    const pc_student_id = pickLeduString(
        normalized.user_id,
        normalized.user_uid,
        normalized.puid
    );
    const auth_token = pickLeduString(
        normalized.hb_token,
        normalized.classroom_token,
        normalized.token
    );
    if (!pc_student_id || !auth_token) {
        return normalized;
    }
    const response = await requestJsonUrl('GET', LEDU_PC_COURSE_LIST_URL, {
        stuId: pc_student_id,
        courseStatus: 3,
        page: 1,
        perPage: 1,
        order: 'asc',
    }, buildLeduPcRequestHeaders(normalized));
    const header_token = pickLeduString(response && response.headers ? response.headers.token : '');
    if (!header_token) {
        return normalized;
    }
    return mergeLeduPayload(normalized, {
        hb_token: header_token,
        classroom_token: header_token,
    });
}

async function normalizeLeduPayloadForPc(payload) {
    let normalized = normalizeLeduPayload(payload);
    if (!normalized || !Object.keys(normalized).length) {
        return {};
    }
    normalized = mergeLeduPayload(normalized, buildLeduPcAuthPatch(normalized));
    const needs_exchange = !!pickLeduString(normalized.token) && (
        !looksLikeLeduPcStudentId(normalized.user_id)
        || !normalized.user_name
        || !normalized.area_code
        || !normalized.hb_token
    );
    if (needs_exchange) {
        const response = await requestJsonUrl(
            'POST',
            LEDU_PC_STU_TOKEN_LOGIN_URL,
            { token: normalized.token },
            buildLeduPcRequestHeaders(normalized)
        );
        const response_body = parseJsonResponseBody(response);
        if (
            response
            && response.statusCode >= 200
            && response.statusCode < 300
            && response_body
            && typeof response_body === 'object'
        ) {
            normalized = mergeLeduPayload(normalized, buildLeduPcAuthPatch(normalized, response_body));
        }
    }
    if (!normalized.hb_token && normalized.token) {
        normalized = mergeLeduPayload(normalized, {
            hb_token: normalized.token,
            classroom_token: normalized.token,
        });
    }
    normalized = await refreshLeduPayloadPcToken(normalized);
    return normalizeLeduPayload(normalized);
}

function writeLeduDebugSnapshot(snapshot) {
    if (!ledu_debug_file || !snapshot) {
        return;
    }
    try {
        const text = JSON.stringify(snapshot, null, 2);
        if (!text || text === ledu_last_debug_snapshot) {
            return;
        }
        ledu_last_debug_snapshot = text;
        fs.writeFile(ledu_debug_file, text, function () {
            ;
        });
    } catch (error) {
        ;
    }
}

function decryptLeduLoginAes(ciphertext) {
    const value = String(ciphertext || '').trim();
    if (!value) {
        return '';
    }
    try {
        const decipher = crypto.createDecipheriv(
            'aes-128-cbc',
            Buffer.from(LEDU_LOGIN_AES_KEY, 'utf8'),
            Buffer.from(LEDU_LOGIN_AES_IV, 'utf8')
        );
        decipher.setAutoPadding(true);
        let plaintext = decipher.update(value, 'base64', 'utf8');
        plaintext += decipher.final('utf8');
        return plaintext;
    } catch (error) {
        return '';
    }
}

function parseLeduDebugRequestBody(body) {
    if (!body) {
        return null;
    }
    if (typeof body === 'string') {
        return safeJsonParse(body, null);
    }
    if (typeof body === 'object') {
        return body;
    }
    return null;
}

function extractLeduXesloginPayload(debug) {
    const requests = debug && Array.isArray(debug.requests) ? debug.requests : [];
    for (let index = requests.length - 1; index >= 0; index -= 1) {
        const item = requests[index];
        if (!item || item.phase !== 'response' || String(item.url || '').indexOf('/multi-sceen-auth-2c/xeslogin') === -1) {
            continue;
        }
        const response = parseLeduDebugRequestBody(item.body);
        const encrypted = response && typeof response === 'object' ? String(response.data || '').trim() : '';
        if (!encrypted) {
            continue;
        }
        const decrypted = decryptLeduLoginAes(encrypted);
        const parsed = safeJsonParse(decrypted, null);
        const data = parsed && parsed.data && typeof parsed.data === 'object' ? parsed.data : {};
        if (!data || typeof data !== 'object') {
            continue;
        }
        const payload = normalizeLeduPayload({
            tal_code: data.code,
            token: data.token,
            user_id: data.stuId,
            user_id_str: data.stuId,
            user_uid: data.puid,
            puid: data.puid,
            open_id: data.openId,
            union_id: data.unionId,
        });
        if (Object.keys(payload).length) {
            return payload;
        }
    }
    return {};
}

function extractLeduUserInfoPayload(debug) {
    const requests = debug && Array.isArray(debug.requests) ? debug.requests : [];
    for (let index = requests.length - 1; index >= 0; index -= 1) {
        const item = requests[index];
        if (!item || item.phase !== 'response' || String(item.url || '').indexOf('/backend-service/m/cUser/v1/user/info') === -1) {
            continue;
        }
        const response = parseLeduDebugRequestBody(item.body);
        const data = response && response.data && typeof response.data === 'object' ? response.data : {};
        if (!data || typeof data !== 'object') {
            continue;
        }
        const payload = normalizeLeduPayload({
            user_name: data.username,
            user_id: data.stu_id,
            user_id_str: data.stu_id,
            user_uid: data.uid,
            puid: data.uid,
            area_code: data.local_city || data.city_id,
            area: data.local_city || data.city_id,
            client_type: '1',
        });
        if (Object.keys(payload).length) {
            return payload;
        }
    }
    return {};
}

function extractLeduStoragePayload(debug) {
    if (!debug || typeof debug !== 'object') {
        return {};
    }
    const localStorage = normalizeLeduObject(debug.localStorage);
    const sessionStorage = normalizeLeduObject(debug.sessionStorage);
    const cookies = normalizeLeduObject(debug.cookies);
    return normalizeLeduPayload({
        href: debug.href || debug.url || '',
        cookies: cookies,
        localStorage: localStorage,
        sessionStorage: sessionStorage,
        authorization: cookies.LEDU_AUTHORIZATION_PROD,
        token: cookies.LEDU_AUTHORIZATION_PROD,
        user_id: cookies.LEDU_STUID_PROD,
        user_id_str: cookies.LEDU_STUID_PROD,
        puid: cookies.LEDU_PUID_PROD,
        open_id: cookies.LEDU_OPENID_PROD,
        union_id: cookies.LEDU_UNIONID_PROD,
        device_id: pickLeduString(
            localStorage.deviceId,
            localStorage.device_id,
            localStorage.devid,
            localStorage['d-id'],
            localStorage.dv,
            sessionStorage.deviceId,
            sessionStorage.device_id,
            sessionStorage.devid,
            sessionStorage['d-id'],
            sessionStorage.dv
        ),
    });
}

function enrichLeduPayloadFromDebug(payload, debug) {
    let merged = mergeLeduPayload(payload, extractLeduXesloginPayload(debug));
    merged = mergeLeduPayload(merged, extractLeduUserInfoPayload(debug));
    merged = mergeLeduPayload(merged, extractLeduStoragePayload(debug));
    return merged;
}

function buildLeduLoginBootstrapPayload(payload) {
    const normalized = normalizeLeduPayload(payload);
    const device_id = pickLeduString(normalized.device_id);
    if (!device_id) {
        return {};
    }
    return { device_id: device_id };
}

function getLeduFreshLoginPayload(result) {
    const debug = result && result.debug ? result.debug : null;
    const xeslogin_payload = extractLeduXesloginPayload(debug);
    const userinfo_payload = extractLeduUserInfoPayload(debug);
    if (!Object.keys(xeslogin_payload).length && !Object.keys(userinfo_payload).length) {
        return {};
    }
    let payload = normalizeLeduPayload(result && result.payload ? result.payload : {});
    payload = enrichLeduPayloadFromDebug(payload, debug);
    return normalizeLeduPayload(payload);
}

function buildLeduLoginUrl() {
    const base_url = localFileURL(path.join(app.getAppPath(), 'ledu-login.html'));
    const bootstrap_payload = buildLeduLoginBootstrapPayload(readStoredLoginPayload('ledu'));
    if (!bootstrap_payload || !bootstrap_payload.device_id) {
        return base_url;
    }
    const query = new URLSearchParams();
    query.set('bootstrap', JSON.stringify(bootstrap_payload));
    return base_url + '?' + query.toString();
}

function writeJsonAndExit(file_path, payload, exit_code = 0) {
    try {
        if (file_path) {
            fs.writeFileSync(file_path, JSON.stringify(payload || {}, null, 2));
        } else {
            process.stdout.write(JSON.stringify(payload || {}, null, 2) + '\n');
        }
        app.exit(exit_code);
    } catch (error) {
        process.stdout.write(String(error && error.stack || error) + '\n');
        app.exit(1);
    }
}

async function setSessionCookieValue(target_session, cookie_value, urls) {
    const cookie_list = extractStoredCookieList(cookie_value);
    if (cookie_list.length) {
        const tasks = cookie_list.map((cookie) => {
            const cookie_details = {
                url: buildCookieSetUrl(cookie, (urls || [])[0] || 'https://course.dongao.com/'),
                name: cookie.name,
                value: cookie.value,
                path: cookie.path || '/',
                secure: !!cookie.secure,
                httpOnly: !!cookie.httpOnly,
            };
            if (!cookie.hostOnly && cookie.domain) {
                cookie_details.domain = cookie.domain;
            }
            if (cookie.expirationDate) {
                cookie_details.expirationDate = cookie.expirationDate;
            }
            if (cookie.sameSite) {
                cookie_details.sameSite = cookie.sameSite;
            }
            return target_session.cookies.set(cookie_details).catch(() => {});
        });
        await Promise.all(tasks);
        return;
    }
    const cookie_map = parseGenericCookieString(cookie_value);
    const tasks = [];
    Object.keys(cookie_map).forEach((name) => {
        const value = cookie_map[name];
        if (!name) {
            return;
        }
        (urls || []).forEach((target_url) => {
            if (!target_url) {
                return;
            }
            tasks.push(
                target_session.cookies.set({
                    url: target_url,
                    name: name,
                    value: value,
                    path: '/',
                    secure: String(target_url).startsWith('https://'),
                    httpOnly: false,
                }).catch(() => {})
            );
        });
    });
    await Promise.all(tasks);
}

async function runSanjiekeFetchHelper() {
    const helper_args_path = getAppArg(2);
    let helper_args = {};
    if (helper_args_path && fs.existsSync(helper_args_path)) {
        try {
            helper_args = JSON.parse(fs.readFileSync(helper_args_path).toString()) || {};
        } catch (error) {
            helper_args = {};
        }
    }
    const output_path = helper_args.outputPath || getAppArg(2);
    const page_url = helper_args.pageUrl || getAppArg(3);
    const media_url = helper_args.mediaUrl || getAppArg(4);
    const raw_cookie_value = helper_args.cookieValue || getAppArg(5);
    const helper_cookie_value = raw_cookie_value || getStoredCookieValue('sanjieke');
    if (!output_path || !page_url || !media_url || !helper_cookie_value) {
        writeJsonAndExit(output_path, { error: 'missing sanjieke helper args' }, 1);
        return;
    }
    const partition_name = 'persist:sanjieke-fetch-' + Date.now();
    const helper_session = session.fromPartition(partition_name);
    const helper_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36';
    try {
        await helper_session.clearStorageData();
        await setSessionCookieValue(helper_session, helper_cookie_value, [
            'https://study.sanjieke.cn/',
            'https://service.sanjieke.cn/',
            'https://classroom.sanjieke.cn/',
            'https://passport.sanjieke.cn/',
            'https://sanjieke.cn/',
        ]);
        helper_session.webRequest.onBeforeSendHeaders(
            { urls: ['*://*.sanjieke.cn/*'] },
            (details, callback) => {
                details.requestHeaders['User-Agent'] = helper_user_agent;
                callback({ requestHeaders: details.requestHeaders });
            }
        );
        Menu.setApplicationMenu(null);
        const win = new BrowserWindow({
            show: false,
            alwaysOnTop: false,
            width: 1280,
            height: 900,
            webPreferences: {
                partition: partition_name,
                webSecurity: false,
                backgroundThrottling: false,
                contextIsolation: true,
            },
        });
        win.webContents.setUserAgent(helper_user_agent);
        win.webContents.on('did-fail-load', (event, code, desc, validatedURL) => {
            writeJsonAndExit(output_path, {
                error: 'page load failed',
                code: code,
                desc: desc,
                validatedURL: validatedURL,
            }, 1);
        });
        win.webContents.on('did-finish-load', async () => {
            try {
                const payload = await win.webContents.executeJavaScript(`
                    (async () => {
                        const m3u8Response = await fetch(${JSON.stringify(media_url)}, {
                            credentials: 'include',
                            headers: {
                                'Accept': '*/*'
                            }
                        });
                        const m3u8Text = await m3u8Response.text();
                        const keyMatches = Array.from(new Set(
                            Array.from(m3u8Text.matchAll(/URI="(.*?)"/g)).map((item) => String(item[1] || '').trim()).filter(Boolean)
                        ));
                        const keyPairs = {};
                        for (const keyUrl of keyMatches) {
                            if (!/^https?:/i.test(keyUrl)) {
                                continue;
                            }
                            const keyResponse = await fetch(keyUrl, {
                                credentials: 'include',
                                headers: {
                                    'Accept': '*/*'
                                }
                            });
                            const buffer = new Uint8Array(await keyResponse.arrayBuffer());
                            keyPairs[keyUrl] = Array.from(buffer).map((item) => item.toString(16).padStart(2, '0')).join('');
                        }
                        return {
                            href: location.href,
                            mediaUrl: ${JSON.stringify(media_url)},
                            status: m3u8Response.status,
                            contentType: m3u8Response.headers.get('content-type') || '',
                            m3u8Text: m3u8Text,
                            keyPairs: keyPairs,
                        };
                    })();
                `, true);
                writeJsonAndExit(output_path, payload, 0);
            } catch (error) {
                writeJsonAndExit(output_path, {
                    error: String(error && error.stack || error),
                }, 1);
            }
        });
        await win.loadURL(page_url, { userAgent: helper_user_agent });
    } catch (error) {
        writeJsonAndExit(output_path, {
            error: String(error && error.stack || error),
        }, 1);
    }
}

function mergeCookieValueWithSetCookie(cookie_value, set_cookie_headers) {
    let cookie_map = parseGenericCookieString(cookie_value);
    (set_cookie_headers || []).forEach((item) => {
        const pair = String(item || '').split(';')[0].trim();
        if (!pair) {
            return;
        }
        const equal_index = pair.indexOf('=');
        if (equal_index <= 0) {
            return;
        }
        const name = pair.slice(0, equal_index).trim();
        const value = pair.slice(equal_index + 1).trim();
        if (!name || !value) {
            return;
        }
        cookie_map[name] = value;
    });
    return buildCookieValueFromMap(cookie_map);
}

function fetchUrlWithCookieValue(target_url, cookie_value, redirect_count = 0, extra_headers = null) {
    return new Promise((resolve) => {
        let settled = false;
        function finish(result) {
            if (!settled) {
                settled = true;
                resolve(result);
            }
        }
        try {
            const parsed = new URL(target_url);
            const request_headers = Object.assign({
                'Cookie': cookie_value,
                'Referer': ZHENGBAO_LOGIN_URL,
                'User-Agent': DEFAULT_BROWSER_USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Encoding': 'identity',
            }, extra_headers || {});
            const client = parsed.protocol === 'http:' ? http : https;
            const request = client.request({
                protocol: parsed.protocol,
                hostname: parsed.hostname,
                port: parsed.port || undefined,
                path: parsed.pathname + parsed.search,
                method: 'GET',
                headers: request_headers,
            }, (response) => {
                let body = '';
                response.setEncoding('utf8');
                response.on('data', (chunk) => {
                    if (body.length < 262144) {
                        body += chunk;
                    }
                });
                response.on('end', () => {
                    const location = String((response.headers || {}).location || '');
                    if (location && response.statusCode >= 300 && response.statusCode < 400 && redirect_count < 4) {
                        finish(fetchUrlWithCookieValue(new URL(location, target_url).toString(), cookie_value, redirect_count + 1, extra_headers));
                        return;
                    }
                    finish({
                        statusCode: Number(response.statusCode || 0),
                        url: target_url,
                        body: body,
                    });
                });
            });
            request.on('error', () => {
                finish(null);
            });
            request.setTimeout(8000, () => {
                request.destroy();
                finish(null);
            });
            request.end();
        } catch (error) {
            finish(null);
        }
    });
}

function fetchUrlWithMergedCookieValue(target_url, cookie_value, redirect_count = 0, extra_headers = null) {
    return new Promise((resolve) => {
        let settled = false;
        function finish(result) {
            if (!settled) {
                settled = true;
                resolve(result);
            }
        }
        try {
            const parsed = new URL(target_url);
            const request_headers = Object.assign({
                'Cookie': cookie_value,
                'User-Agent': DEFAULT_BROWSER_USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Encoding': 'identity',
            }, extra_headers || {});
            const client = parsed.protocol === 'http:' ? http : https;
            const request = client.request({
                protocol: parsed.protocol,
                hostname: parsed.hostname,
                port: parsed.port || undefined,
                path: parsed.pathname + parsed.search,
                method: 'GET',
                headers: request_headers,
            }, (response) => {
                let body = '';
                response.setEncoding('utf8');
                response.on('data', (chunk) => {
                    if (body.length < 262144) {
                        body += chunk;
                    }
                });
                response.on('end', () => {
                    const location = String((response.headers || {}).location || '');
                    const merged_cookie_value = mergeCookieValueWithSetCookie(cookie_value, (response.headers || {})['set-cookie'] || []);
                    if (location && response.statusCode >= 300 && response.statusCode < 400 && redirect_count < 4) {
                        finish(fetchUrlWithMergedCookieValue(new URL(location, target_url).toString(), merged_cookie_value, redirect_count + 1, extra_headers));
                        return;
                    }
                    finish({
                        statusCode: Number(response.statusCode || 0),
                        url: target_url,
                        cookieValue: merged_cookie_value,
                        body: body,
                    });
                });
            });
            request.on('error', () => {
                finish(null);
            });
            request.setTimeout(8000, () => {
                request.destroy();
                finish(null);
            });
            request.end();
        } catch (error) {
            finish(null);
        }
    });
}

function looksLikeZhengbaoMemberPage(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const final_url = String(result.url || '').toLowerCase();
    const body = String(result.body || '');
    if (final_url.indexOf('login/index.shtml') !== -1) {
        return false;
    }
    if (body.indexOf('login/index.shtml') !== -1) {
        return false;
    }
    if (body.indexOf('退出') !== -1 || body.indexOf('我的网校') !== -1 || body.indexOf('会员中心') !== -1) {
        return true;
    }
    if (body.indexOf('登录') !== -1 && body.indexOf('密码') !== -1) {
        return false;
    }
    return true;
}

function looksLikeMed66MemberPage(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const final_url = String(result.url || '').toLowerCase();
    const body = String(result.body || '');
    const body_lower = body.toLowerCase();
    if (final_url.indexOf('loginagain/index.shtml') !== -1) {
        return false;
    }
    if (body_lower.indexOf('loginagain/index.shtml') !== -1) {
        return false;
    }
    if (body_lower.indexOf('/homes/logout') !== -1) {
        return true;
    }
    if (body_lower.indexOf('id=\"table-mycourselist\"') !== -1) {
        return true;
    }
    if (body_lower.indexOf('/homes/mycourse') !== -1 && body_lower.indexOf('mycourselist.js') !== -1) {
        return true;
    }
    if (body_lower.indexOf('name=\"username\"') !== -1 && body_lower.indexOf('name=\"password\"') !== -1) {
        return false;
    }
    return false;
}

function looksLikeJianshe99MemberPage(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const final_url = String(result.url || '').toLowerCase();
    const body = String(result.body || '');
    const body_lower = body.toLowerCase();
    if (final_url.indexOf('login/index.shtml') !== -1) {
        return false;
    }
    if (body_lower.indexOf('login/index.shtml') !== -1) {
        return false;
    }
    if (body_lower.indexOf('/homes/mycourse') !== -1 || body_lower.indexOf('homes/static/js') !== -1 || body_lower.indexOf('/homes/logout') !== -1) {
        return true;
    }
    if (body_lower.indexOf('name=\"username\"') !== -1 && body_lower.indexOf('name=\"password\"') !== -1) {
        return false;
    }
    return false;
}

function validateZhengbaoCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(ZHENGBAO_VALIDATE_URL, cookie_value)
        .then((result) => looksLikeZhengbaoMemberPage(result))
        .catch(() => false);
}

function validateMed66CookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(MED66_VALIDATE_URL, cookie_value, 0, {
        'Referer': MED66_LOGIN_URL,
    })
        .then((result) => looksLikeMed66MemberPage(result))
        .catch(() => false);
}

function validateJianshe99CookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(JIANSHE99_VALIDATE_URL, cookie_value, 0, {
        'Referer': JIANSHE99_LOGIN_URL,
    })
        .then((result) => looksLikeJianshe99MemberPage(result))
        .catch(() => false);
}

function isChaogeCookie(cookie) {
    if (!cookie || !cookie.name) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || '');
    return domain === 'chaogejiaoyu.com' || domain.endsWith('.chaogejiaoyu.com');
}

function hasChaogeLoginCookies(cookies) {
    return (cookies || []).some((cookie) => isChaogeCookie(cookie) && cookie.name === 'PHPSESSID' && cookie.value);
}

function looksLikeChaogeLoginInfo(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    try {
        const info = JSON.parse(String(result.body || '{}'));
        return !!(info && Number(info.status) === 0 && info.data);
    } catch (error) {
        return false;
    }
}

function validateChaogeCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(CHAOGE_VALIDATE_URL, cookie_value, 0, {
        'Referer': CHAOGE_LOGIN_URL,
        'Origin': 'https://chaogejiaoyu.com',
        'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest',
    })
        .then((result) => looksLikeChaogeLoginInfo(result))
        .catch(() => false);
}

function isShanxiangCookie(cookie) {
    if (!cookie || !cookie.name) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || '');
    return domain === 'sx1211.com' || domain.endsWith('.sx1211.com');
}

function hasShanxiangLoginCookies(cookies) {
    const cookie_map = buildCookieMap((cookies || []).filter((cookie) => isShanxiangCookie(cookie)));
    return !!(cookie_map.PHPSESSID && cookie_map.sx_home_sx_wx_1211_sxenwebtoken);
}

function looksLikeShanxiangLoginInfo(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const body = String(result.body || '');
    return body.indexOf('js-user-name') !== -1
        || body.indexOf('/user/course.html') !== -1
        || body.indexOf('我的课程') !== -1;
}

function validateShanxiangCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(SHANXIANG_VALIDATE_URL, cookie_value, 0, {
        'Referer': SHANXIANG_LOGIN_URL,
        'Origin': 'https://www.sx1211.com',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
        .then((result) => looksLikeShanxiangLoginInfo(result))
        .catch(() => false);
}

function isShikaobangCookie(cookie) {
    if (!cookie || !cookie.name) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || '');
    return domain === 'shikaobang.cn' || domain.endsWith('.shikaobang.cn');
}

function hasShikaobangLoginCookies(cookies) {
    return (cookies || []).some((cookie) => isShikaobangCookie(cookie) && cookie.value);
}

function looksLikeShikaobangLoginInfo(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const body = String(result.body || '');
    if (body.indexOf('抱歉，你访问的内容不存在') !== -1) {
        return false;
    }
    if (/id=["']ucid["']\s+value=["']0["']/i.test(body)) {
        return false;
    }
    return /id=["']ucid["']\s+value=["'](?!0["'])[^"']+/i.test(body)
        || body.indexOf('退出登录') !== -1
        || body.indexOf('我的课程') !== -1;
}

function validateShikaobangCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(SHIKAOBANG_VALIDATE_URL, cookie_value, 0, {
        'Referer': SHIKAOBANG_LOGIN_URL,
        'Origin': 'https://www.shikaobang.cn',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
        .then((result) => looksLikeShikaobangLoginInfo(result))
        .catch(() => false);
}

function filterShikaobangCookies(cookies) {
    return (cookies || []).filter((cookie) => {
        return cookie
            && cookie.name
            && cookie.value
            && isShikaobangCookie(cookie);
    });
}

function normalizeShikaobangCookieValue(value) {
    return String(value || '').replace(/[^\x00-\xff]/g, (char) => encodeURIComponent(char));
}

function buildShikaobangCookieValue(cookies, page_cookie_value = '') {
    const cookie_map = {};
    filterShikaobangCookies(cookies || []).forEach((cookie) => {
        cookie_map[cookie.name] = normalizeShikaobangCookieValue(cookie.value);
    });
    const page_cookie_map = parseCookieString(page_cookie_value || '');
    Object.keys(page_cookie_map).forEach((name) => {
        cookie_map[name] = normalizeShikaobangCookieValue(page_cookie_map[name]);
    });
    return buildCookieValueFromMap(cookie_map);
}

function hasUsableShikaobangCookieValue(cookie_value) {
    const cookie_map = parseCookieString(cookie_value || '');
    if (cookie_map.PHPSESSID || cookie_map.web_user_token) {
        return true;
    }
    if (!cookie_map.user_infor) {
        return false;
    }
    return hasValidShikaobangUserInforCookie([{
        name: 'user_infor',
        value: cookie_map.user_infor,
    }]);
}

function hasValidShikaobangUserInforCookie(cookies) {
    const cookie = (cookies || []).find((item) => item && item.name === 'user_infor' && item.value);
    if (!cookie) {
        return false;
    }
    let value = String(cookie.value || '').trim();
    if (!value) {
        return false;
    }
    try {
        value = decodeURIComponent(value);
    } catch (error) {
        ;
    }
    try {
        const data = JSON.parse(value);
        if (!data || typeof data !== 'object' || Array.isArray(data)) {
            return false;
        }
        return ['id', 'uid', 'ucid', 'user_id', 'userId', 'phone', 'mobile', 'token']
            .some((key) => {
                const item = data[key];
                return item !== undefined
                    && item !== null
                    && !['', '0', 'null', 'undefined'].includes(String(item).trim());
            });
    } catch (error) {
        return /"(?:id|uid|ucid|user_id|userId|phone|mobile)"\s*:\s*"?[^",}\s][^",}]*"?/.test(value);
    }
}

function trySaveShikaobangLoginResult(win, cookies) {
    if (login_name !== 'shikaobang' || shikaobang_save_inflight) {
        return false;
    }
    if (win && !isWindowAlive(win)) {
        return false;
    }
    if (!hasShikaobangLoginCookies(cookies) && !isWindowAlive(win)) {
        return false;
    }
    shikaobang_save_inflight = true;
    const page_cookie_promise = isWindowAlive(win)
        ? win.webContents.executeJavaScript(`
            (() => {
                const ucid_input = document.querySelector('#ucid');
                return {
                    cookie: document.cookie || '',
                    ucid: ucid_input ? String(ucid_input.value || '') : '',
                };
            })();
        `, true).catch(() => ({}))
        : Promise.resolve({});
    page_cookie_promise.then((page_state) => {
        const cookie_value = buildShikaobangCookieValue(cookies, page_state && page_state.cookie);
        const page_ucid = String(page_state && page_state.ucid || '').trim();
        const page_logged_in = !!(page_ucid && page_ucid !== '0');
        if (!cookie_value || (!page_logged_in && !hasUsableShikaobangCookieValue(cookie_value))) {
            shikaobang_save_inflight = false;
            return;
        }
        return validateShikaobangCookieValue(cookie_value).then((valid) => {
            if (valid) {
                saveLoginCookieValue(cookie_value);
                return;
            }
            shikaobang_save_inflight = false;
        });
    }).catch(() => {
        shikaobang_save_inflight = false;
    });
    return true;
}

function isYiqikaojiaoshiCookie(cookie) {
    if (!cookie || !cookie.name) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || '');
    return domain === '17kjs.com' || domain.endsWith('.17kjs.com');
}

function hasYiqikaojiaoshiLoginCookies(cookies) {
    const cookie_map = buildCookieMap((cookies || []).filter((cookie) => isYiqikaojiaoshiCookie(cookie)));
    return !!(cookie_map.PHPSESSID || cookie_map.YQ_CLIENT_UUID);
}

function looksLikeYiqikaojiaoshiLoginInfo(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const final_url = String(result.url || '').toLowerCase();
    const body = String(result.body || '');
    const body_lower = body.toLowerCase();
    if (final_url.indexOf('/user/course') === -1) {
        return false;
    }
    return body_lower.indexOf('user-course') !== -1
        || body.indexOf('jumpToProfile(') !== -1
        || body.indexOf('/User/course') !== -1
        || body.indexOf('/User/order') !== -1
        || body.indexOf('\u6211\u7684\u8bfe\u7a0b') !== -1;
}

function validateYiqikaojiaoshiCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(YIQIKAOJIAOSHI_VALIDATE_URL, cookie_value, 0, {
        'Referer': YIQIKAOJIAOSHI_LOGIN_URL,
        'Origin': 'https://www.17kjs.com',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
        .then((result) => looksLikeYiqikaojiaoshiLoginInfo(result))
        .catch(() => false);
}

function trySaveYiqikaojiaoshiLoginResult(cookies) {
    if (login_name !== 'yiqikaojiaoshi' || yiqikaojiaoshi_save_inflight) {
        return false;
    }
    const yiqikaojiaoshi_cookies = (cookies || []).filter((cookie) => isYiqikaojiaoshiCookie(cookie));
    const cookie_value = buildCookieValue(yiqikaojiaoshi_cookies);
    if (!cookie_value) {
        return false;
    }
    yiqikaojiaoshi_save_inflight = true;
    validateYiqikaojiaoshiCookieValue(cookie_value).then((valid) => {
        if (valid) {
            saveLoginCookieValue(cookie_value);
            return;
        }
        yiqikaojiaoshi_save_inflight = false;
    }).catch(() => {
        yiqikaojiaoshi_save_inflight = false;
    });
    return true;
}

function validateYikaijiangCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue('https://jc.e-lesson.cn/spoc/auth/elective_course_list.action', cookie_value, 0, {
        'Referer': 'https://jc.e-lesson.cn/spoc/open/login.action',
        'Origin': 'https://jc.e-lesson.cn',
    }).then((result) => {
        if (!result || result.statusCode < 200 || result.statusCode >= 400) {
            return false;
        }
        const body = String(result.body || '');
        const final_url = String(result.url || '');
        if (final_url.indexOf('/spoc/open/login.action') !== -1) {
            return false;
        }
        return /\buserLoginId\b/.test(body)
            || /\btoStudy\s*\(/.test(body)
            || /class=["'][^"']*course_item/.test(body);
    }).catch(() => false);
}

function validateZhongxunwxCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue('https://www.zhongxunwx.com/home/learn/index', cookie_value, 0, {
        'Referer': 'https://www.zhongxunwx.com/home/regin/login',
        'Origin': 'https://www.zhongxunwx.com',
    }).then((result) => {
        if (!result || result.statusCode < 200 || result.statusCode >= 400) {
            return false;
        }
        const body = String(result.body || '');
        return body.indexOf('\u6211\u7684\u8bfe\u7a0b') !== -1
            && body.slice(0, 4000).indexOf('/home/regin/login') === -1;
    }).catch(() => false);
}

function buildDxyValidateUrl() {
    const params = {
        timestamp: String(Date.now()),
        noncestr: String(Math.floor(Math.random() * 100000000)).padStart(8, '0'),
    };
    const sign_key = '695e7084696bf4a6b4c73dc67da4f5df41405763ef4a2a854e3af96b141254b0050986ccf2b8cd9a6ab5cfabc6e4bb30';
    const keys = Object.keys(params).concat(['appSignKey']).sort();
    const sign_text = keys.map((key) => key + '=' + (key === 'appSignKey' ? sign_key : params[key])).join('&');
    params.sign = crypto.createHash('sha1').update(sign_text).digest('hex');
    return 'https://class.dxy.cn/pcweb/user/info?' + new URLSearchParams(params).toString();
}

function isDxyCookie(cookie) {
    if (!cookie || !cookie.name || cookie.value === undefined || cookie.value === null || String(cookie.value) === '') {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    return domain === 'dxy.cn' || domain.endsWith('.dxy.cn');
}

function getDxyCookiePriority(cookie) {
    if (!isDxyCookie(cookie)) {
        return -1;
    }
    const name = String(cookie.name || '');
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    const path_value = String(cookie.path || '/');
    let priority = 0;
    if (domain === 'class.dxy.cn') {
        priority += 1000;
    } else if (domain === 'dxy.cn') {
        priority += 900;
    } else if (domain === 'auth.dxy.cn') {
        priority += 700;
    } else if (domain.endsWith('.dxy.cn')) {
        priority += 500;
    }
    if (['JSESSIONID', 'route_php', 'route_dqapi'].includes(name)) {
        priority += 100;
    }
    if (/token|auth|sso|session|login|user|uid/i.test(name)) {
        priority += 50;
    }
    priority += Math.min(path_value.length, 50);
    return priority;
}

function filterDxyCookies(cookies) {
    const seen = new Set();
    return (cookies || [])
        .filter((cookie) => isDxyCookie(cookie))
        .sort((a, b) => getDxyCookiePriority(b) - getDxyCookiePriority(a))
        .filter((cookie) => {
            const name = String(cookie.name || '').trim();
            if (!name || seen.has(name)) {
                return false;
            }
            seen.add(name);
            return true;
        });
}

function validateDxyCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(buildDxyValidateUrl(), cookie_value, 0, {
        'Referer': 'https://class.dxy.cn/clazz/personal/study',
        'Origin': 'https://class.dxy.cn',
        'Accept': 'application/json, text/plain, */*',
    }).then((result) => {
        if (!result || result.statusCode < 200 || result.statusCode >= 400) {
            return false;
        }
        try {
            const data = JSON.parse(String(result.body || '{}'));
            const user = data && data.data && typeof data.data === 'object' ? data.data : {};
            return !!(
                data
                && (data.code === 'success' || data.success === true || String(data.message || '').toLowerCase() === 'success')
                && (user.userId || user.username || user.nickname)
            );
        } catch (error) {
            return false;
        }
    }).catch(() => false);
}

function trySaveDxyLoginResult(cookies) {
    if (login_name !== 'dxy' || dxy_save_inflight) {
        return false;
    }
    const dxy_cookies = filterDxyCookies(cookies);
    const cookie_value = buildCookieValue(dxy_cookies);
    if (!cookie_value) {
        return false;
    }
    dxy_save_inflight = true;
    validateDxyCookieValue(cookie_value).then((valid) => {
        if (valid) {
            saveLoginCookieValue(cookie_value);
            return;
        }
        dxy_save_inflight = false;
    }).catch(() => {
        dxy_save_inflight = false;
    });
    return true;
}

function validateEducityCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue('https://wangxiao.xisaiwang.com/ucenterapi/ucenter2/user/hasLogon.do', cookie_value, 0, {
        'Referer': 'https://wangxiao.xisaiwang.com/nstu/pages/course/index/index',
        'Origin': 'https://wangxiao.xisaiwang.com',
        'Accept': 'application/json, text/plain, */*',
    }).then((result) => {
        if (!result || result.statusCode < 200 || result.statusCode >= 400) {
            return false;
        }
        try {
            const data = JSON.parse(String(result.body || '{}'));
            return !!(
                data
                && data.resultCode === 'SUCCESS'
                && data.model
                && data.model.data === true
            );
        } catch (error) {
            return false;
        }
    }).catch(() => false);
}

function getShikaobangLoginPanelCheckScript() {
    return `
        (function () {
        function is_visible(el) {
            if (!el) {
                return false;
            }
            var style = window.getComputedStyle(el);
            if (!style || style.display == 'none' || style.visibility == 'hidden' || Number(style.opacity || 1) === 0) {
                return false;
            }
            var rect = el.getBoundingClientRect();
            return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
        }
        function text_of(el) {
            return String((el && (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title'))) || '').replace(/\\s+/g, '').trim();
        }
        var modal = document.querySelector('#loginModal,.layui-login,.layui-layer');
        if (modal && is_visible(modal)) {
            return true;
        }
        var panels = document.querySelectorAll('#loginModal,.login-modal,.layui-layer,[class*=login-modal],[class*=loginModal],[class*=login-box],form');
        for (var i = 0; i < panels.length; i++) {
            if (!is_visible(panels[i])) {
                continue;
            }
            var text = text_of(panels[i]);
            if (text.indexOf('\\u9a8c\\u8bc1\\u7801\\u767b\\u5f55') !== -1 || text.indexOf('\\u5bc6\\u7801\\u767b\\u5f55') !== -1 || text.indexOf('\\u624b\\u673a\\u53f7') !== -1) {
                return true;
            }
        }
        return false;
        })();
    `;
}

function getShikaobangLoginAutoOpenScript() {
    return `
        (function () {
        function is_visible(el) {
            if (!el) {
                return false;
            }
            var style = window.getComputedStyle(el);
            if (!style || style.display == 'none' || style.visibility == 'hidden' || Number(style.opacity || 1) === 0) {
                return false;
            }
            var rect = el.getBoundingClientRect();
            return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
        }
        function text_of(el) {
            return String((el && (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title'))) || '').replace(/\\s+/g, '').trim();
        }
        function has_login_panel() {
            var modal = document.querySelector('#loginModal,.layui-login,.layui-layer');
            if (modal && is_visible(modal)) {
                return true;
            }
            var panels = document.querySelectorAll('#loginModal,.login-modal,.layui-layer,[class*=login-modal],[class*=loginModal],[class*=login-box],form');
            for (var i = 0; i < panels.length; i++) {
                if (!is_visible(panels[i])) {
                    continue;
                }
                var text = text_of(panels[i]);
                if (text.indexOf('\\u9a8c\\u8bc1\\u7801\\u767b\\u5f55') !== -1 || text.indexOf('\\u5bc6\\u7801\\u767b\\u5f55') !== -1 || text.indexOf('\\u624b\\u673a\\u53f7') !== -1) {
                    return true;
                }
            }
            return false;
        }
        function clickable_target(node) {
            if (!node) {
                return null;
            }
            try {
                return node.closest('button,a,[role=button]') || node;
            } catch (error) {
                return node;
            }
        }
        function dispatch_click(node) {
            var el = clickable_target(node);
            if (!el) {
                return false;
            }
            try {
                el.scrollIntoView({ block: 'center', inline: 'center' });
            } catch (error) {
                ;
            }
            var rect = el.getBoundingClientRect();
            var event_options = { bubbles: true, cancelable: true, view: window, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
            var events = ['pointerover', 'mouseover', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
            for (var i = 0; i < events.length; i++) {
                try {
                    var event_name = events[i];
                    var event_obj = event_name.indexOf('pointer') === 0 && typeof PointerEvent !== 'undefined'
                        ? new PointerEvent(event_name, Object.assign({ pointerType: 'mouse', isPrimary: true }, event_options))
                        : new MouseEvent(event_name, event_options);
                    el.dispatchEvent(event_obj);
                } catch (error) {
                    ;
                }
            }
            try {
                el.click();
            } catch (error) {
                ;
            }
            return true;
        }
        function is_login_button(node) {
            if (!is_visible(node)) {
                return false;
            }
            var target = clickable_target(node);
            var text = (text_of(node) + text_of(target)).replace(/\\s+/g, '');
            if (!text || text.indexOf('\\u767b\\u5f55') === -1 || text.indexOf('\\u5df2\\u767b\\u5f55') !== -1 || text.indexOf('\\u9000\\u51fa') !== -1) {
                return false;
            }
            if (text.indexOf('\\u7acb\\u5373\\u8d2d\\u4e70') !== -1 || text.length > 10) {
                return false;
            }
            var rect = node.getBoundingClientRect();
            return rect.top <= Math.max(240, window.innerHeight * 0.32) && rect.left >= window.innerWidth * 0.35;
        }
        function find_login_button() {
            var direct_selectors = [
                '.login-text',
                '.header .login-text',
                '.nav .login-text',
                'header .login-text',
                '[class*=header] .login-text',
                '[class*=nav] .login-text',
                'button,a,[role=button],div,span'
            ];
            var candidates = [];
            for (var s = 0; s < direct_selectors.length; s++) {
                var list = document.querySelectorAll(direct_selectors[s]);
                for (var i = 0; i < list.length; i++) {
                    var node = list[i];
                    if (!is_login_button(node)) {
                        continue;
                    }
                    var rect = node.getBoundingClientRect();
                    candidates.push({ element: node, score: rect.top * 10000 + (window.innerWidth - rect.left) });
                }
            }
            candidates.sort(function (a, b) { return a.score - b.score; });
            return candidates.length ? candidates[0].element : null;
        }
        return new Promise(function (resolve) {
            if (has_login_panel()) {
                resolve({ opened: true, clicked: false });
                return;
            }
            if (typeof login_modal === 'function') {
                try {
                    login_modal();
                } catch (error) {
                    ;
                }
            }
            setTimeout(function () {
                if (has_login_panel()) {
                    resolve({ opened: true, clicked: false });
                    return;
                }
                var login_btn = find_login_button();
                if (!login_btn) {
                    resolve({ opened: false, clicked: false });
                    return;
                }
                dispatch_click(login_btn);
                setTimeout(function () {
                    resolve({ opened: has_login_panel(), clicked: true });
                }, 360);
            }, 120);
        });
        })();
    `;
}

function clickShikaobangLoginButton(win, delay_ms = 0) {
    if (login_name != 'shikaobang') {
        return;
    }
    setTimeout(() => {
        const contents = getSafeWebContents(win);
        if (!contents) {
            return;
        }
        contents.executeJavaScript(getShikaobangLoginAutoOpenScript(), true)
            .then((result) => {
                if (result && result.opened) {
                    return;
                }
                const latest_contents = getSafeWebContents(win);
                if (!latest_contents) {
                    return;
                }
                latest_contents.executeJavaScript(getShikaobangLoginPanelCheckScript(), true)
                    .catch(() => {});
            })
            .catch(() => {});
    }, delay_ms);
}

function getYiqikaojiaoshiLoginPanelCheckScript() {
    return `
        (function () {
        function is_visible(el) {
            if (!el) {
                return false;
            }
            var style = window.getComputedStyle(el);
            if (!style || style.display == 'none' || style.visibility == 'hidden' || Number(style.opacity || 1) === 0) {
                return false;
            }
            var rect = el.getBoundingClientRect();
            return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
        }
        function text_of(el) {
            return String((el && (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title'))) || '').replace(/\\s+/g, '').trim();
        }
        var panels = document.querySelectorAll('#login-box,#sms-check-box,#login-box-db,.login-box');
        for (var i = 0; i < panels.length; i++) {
            if (!is_visible(panels[i])) {
                continue;
            }
            var text = text_of(panels[i]);
            if (panels[i].id == 'login-box' || panels[i].id == 'sms-check-box' || panels[i].id == 'login-box-db') {
                return true;
            }
            if (text.indexOf('\\u77ed\\u4fe1\\u767b\\u5f55') !== -1 || text.indexOf('\\u5bc6\\u7801\\u767b\\u5f55') !== -1 || text.indexOf('\\u624b\\u673a\\u53f7') !== -1) {
                return true;
            }
        }
        return false;
        })();
    `;
}

function getYiqikaojiaoshiLoginAutoOpenScript() {
    return `
        (function () {
        function is_visible(el) {
            if (!el) {
                return false;
            }
            var style = window.getComputedStyle(el);
            if (!style || style.display == 'none' || style.visibility == 'hidden' || Number(style.opacity || 1) === 0) {
                return false;
            }
            var rect = el.getBoundingClientRect();
            return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
        }
        function text_of(el) {
            return String((el && (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title'))) || '').replace(/\\s+/g, '').trim();
        }
        function has_login_panel() {
            var panels = document.querySelectorAll('#login-box,#sms-check-box,#login-box-db,.login-box');
            for (var i = 0; i < panels.length; i++) {
                if (!is_visible(panels[i])) {
                    continue;
                }
                var text = text_of(panels[i]);
                if (panels[i].id == 'login-box' || panels[i].id == 'sms-check-box' || panels[i].id == 'login-box-db') {
                    return true;
                }
                if (text.indexOf('\\u77ed\\u4fe1\\u767b\\u5f55') !== -1 || text.indexOf('\\u5bc6\\u7801\\u767b\\u5f55') !== -1 || text.indexOf('\\u624b\\u673a\\u53f7') !== -1) {
                    return true;
                }
            }
            return false;
        }
        function clickable_target(node) {
            if (!node) {
                return null;
            }
            try {
                return node.closest('button,a,[role=button]') || node;
            } catch (error) {
                return node;
            }
        }
        function dispatch_click(node) {
            var el = clickable_target(node);
            if (!el) {
                return false;
            }
            try {
                el.scrollIntoView({ block: 'center', inline: 'center' });
            } catch (error) {
                ;
            }
            var rect = el.getBoundingClientRect();
            var event_options = { bubbles: true, cancelable: true, view: window, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
            var events = ['pointerover', 'mouseover', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
            for (var i = 0; i < events.length; i++) {
                try {
                    var event_name = events[i];
                    var event_obj = event_name.indexOf('pointer') === 0 && typeof PointerEvent !== 'undefined'
                        ? new PointerEvent(event_name, Object.assign({ pointerType: 'mouse', isPrimary: true }, event_options))
                        : new MouseEvent(event_name, event_options);
                    el.dispatchEvent(event_obj);
                } catch (error) {
                    ;
                }
            }
            try {
                el.click();
            } catch (error) {
                ;
            }
            return true;
        }
        function is_login_button(node) {
            if (!is_visible(node)) {
                return false;
            }
            var target = clickable_target(node);
            var text = (text_of(node) + text_of(target)).replace(/\\s+/g, '');
            var marker = String((node.className || '') + ' ' + (node.id || '') + ' ' + (node.getAttribute('onclick') || '') + ' ' + (target && target.getAttribute ? target.getAttribute('onclick') || '' : '')).toLowerCase();
            if (text.indexOf('\\u6ce8\\u518c') !== -1 || text.indexOf('\\u9000\\u51fa') !== -1 || text.indexOf('\\u5df2\\u767b\\u5f55') !== -1) {
                return false;
            }
            if (text === '\\u767b\\u5f55' || marker.indexOf('login_show') !== -1 || marker.indexOf('btn-login') !== -1) {
                var rect = node.getBoundingClientRect();
                return rect.top <= Math.max(260, window.innerHeight * 0.35) && rect.left >= window.innerWidth * 0.35;
            }
            return false;
        }
        function find_login_button() {
            var selectors = ['.btn-login', '.login-li .btn-login', '[onclick*=login_show]', 'button,a,[role=button],div,span'];
            var candidates = [];
            for (var s = 0; s < selectors.length; s++) {
                var list = document.querySelectorAll(selectors[s]);
                for (var i = 0; i < list.length; i++) {
                    var node = list[i];
                    if (!is_login_button(node)) {
                        continue;
                    }
                    var rect = node.getBoundingClientRect();
                    candidates.push({ element: node, score: rect.top * 10000 + (window.innerWidth - rect.left) });
                }
            }
            candidates.sort(function (a, b) { return a.score - b.score; });
            return candidates.length ? candidates[0].element : null;
        }
        return new Promise(function (resolve) {
            if (has_login_panel()) {
                resolve({ opened: true, clicked: false });
                return;
            }
            if (typeof login_show === 'function') {
                try {
                    login_show();
                } catch (error) {
                    ;
                }
            }
            setTimeout(function () {
                if (has_login_panel()) {
                    resolve({ opened: true, clicked: false });
                    return;
                }
                var login_btn = find_login_button();
                if (!login_btn) {
                    resolve({ opened: false, clicked: false });
                    return;
                }
                dispatch_click(login_btn);
                setTimeout(function () {
                    resolve({ opened: has_login_panel(), clicked: true });
                }, 360);
            }, 150);
        });
        })();
    `;
}

function clickYiqikaojiaoshiLoginButton(win, delay_ms = 0) {
    if (login_name != 'yiqikaojiaoshi') {
        return;
    }
    setTimeout(() => {
        const contents = getSafeWebContents(win);
        if (!contents) {
            return;
        }
        contents.executeJavaScript(getYiqikaojiaoshiLoginAutoOpenScript(), true)
            .then((result) => {
                if (result && result.opened) {
                    return;
                }
                const latest_contents = getSafeWebContents(win);
                if (!latest_contents) {
                    return;
                }
                latest_contents.executeJavaScript(getYiqikaojiaoshiLoginPanelCheckScript(), true)
                    .catch(() => {});
            })
            .catch(() => {});
    }, delay_ms);
}

function isFenbiCookie(cookie) {
    if (!cookie || !cookie.name) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || '');
    return domain === 'fenbi.com' || domain.endsWith('.fenbi.com');
}

function hasFenbiLoginCookies(cookies) {
    return (cookies || []).some((cookie) => isFenbiCookie(cookie) && (cookie.name === 'sess' || cookie.name === 'userid' || cookie.name === 'sid') && cookie.value);
}

function isHoudaCookie(cookie) {
    if (!cookie || !cookie.name) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || '');
    return domain === 'houdask.com' || domain.endsWith('.houdask.com');
}

function filterHoudaCookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isHoudaCookie(cookie) || !HOUDA_COOKIE_NAMES.includes(String(cookie.name || '')) || !cookie.value) {
            return;
        }
        const key = String(cookie.name || '');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function hasHoudaLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterHoudaCookies(cookies));
    return !!(cookie_map.houdatoken || cookie_map['hd.token']);
}

function looksLikeHoudaLoginInfo(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    try {
        const info = JSON.parse(String(result.body || '{}'));
        return !!(info && String(info.code) === '1' && info.data && typeof info.data === 'object');
    } catch (error) {
        return false;
    }
}

function validateHoudaCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(HOUDA_VALIDATE_URL, cookie_value, 0, {
        'Referer': HOUDA_LOGIN_URL + '/',
        'Origin': HOUDA_LOGIN_URL,
        'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest',
        'appType': 'WEB',
    })
        .then((result) => looksLikeHoudaLoginInfo(result))
        .catch(() => false);
}

function trySaveHoudaCookies(cookies) {
    const filtered_cookies = filterHoudaCookies(cookies);
    if (!hasHoudaLoginCookies(filtered_cookies)) {
        return false;
    }
    const cookie_value = buildCookieValue(filtered_cookies);
    if (!cookie_value) {
        return false;
    }
    validateHoudaCookieValue(cookie_value).then((valid) => {
        if (valid) {
            saveLoginCookieValue(cookie_value);
        }
    }).catch(() => {});
    return true;
}

function getHoudaLoginAutoOpenScript() {
    return `
        (function () {
            function isVisible(el) {
                if (!el) {
                    return false;
                }
                var style = window.getComputedStyle(el);
                if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0) {
                    return false;
                }
                var rect = el.getBoundingClientRect();
                return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
            }

            function fireClick(node) {
                if (!node) {
                    return false;
                }
                try {
                    node.dispatchEvent(new MouseEvent('mouseover', {bubbles: true, cancelable: true, view: window}));
                    node.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true, cancelable: true, view: window}));
                    node.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                    node.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                    node.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                } catch (error) {
                    ;
                }
                try {
                    node.click();
                } catch (error) {
                    ;
                }
                try {
                    if (window.jQuery) {
                        window.jQuery(node).trigger('click');
                    }
                } catch (error) {
                    ;
                }
                return true;
            }

            function showLoginWrap() {
                var wrap = document.querySelector('.loginWrap');
                if (!wrap) {
                    return false;
                }
                try {
                    wrap.style.display = 'block';
                    wrap.style.visibility = 'visible';
                    wrap.style.opacity = '1';
                    wrap.style.position = 'fixed';
                    wrap.style.left = '0';
                    wrap.style.top = '0';
                    wrap.style.right = '0';
                    wrap.style.bottom = '0';
                    wrap.style.width = '100%';
                    wrap.style.height = '100%';
                    wrap.style.zIndex = '2147483647';
                    if (!wrap.style.background) {
                        wrap.style.background = 'rgba(0,0,0,.5)';
                    }
                } catch (error) {
                    ;
                }
                var forgetWrap = document.querySelector('.forgetWrap');
                if (forgetWrap) {
                    try {
                        forgetWrap.style.display = 'none';
                    } catch (error) {
                        ;
                    }
                }
                var loginCont = document.querySelector('.loginWrap .loginCont');
                if (loginCont) {
                    try {
                        loginCont.style.position = 'absolute';
                        loginCont.style.left = '50%';
                        loginCont.style.top = '50%';
                        loginCont.style.transform = 'translate(-50%,-50%)';
                    } catch (error) {
                        ;
                    }
                }
                return isVisible(wrap) || isVisible(loginCont) || isVisible(document.querySelector('#btn_login'));
            }

            function clickTopLoginEntry() {
                var selectors = [
                    '#login > span',
                    '#login .LOGIN',
                    '.noLogin .LOGIN',
                    '.LOGIN',
                    '#login',
                    '.loginNav #login'
                ];
                for (var i = 0; i < selectors.length; i++) {
                    var node = document.querySelector(selectors[i]);
                    if (node && (isVisible(node) || selectors[i].indexOf('LOGIN') !== -1)) {
                        fireClick(node);
                    }
                    if (showLoginWrap()) {
                        return true;
                    }
                }
                return false;
            }

            if (!document || !document.documentElement) {
                return {opened: false, reason: 'no-document'};
            }
            if (showLoginWrap()) {
                return {opened: true, method: 'wrap'};
            }
            if (clickTopLoginEntry()) {
                return {opened: true, method: 'click'};
            }
            window.__xwzHoudaLoginOpenAttempts = (window.__xwzHoudaLoginOpenAttempts || 0) + 1;
            return {
                opened: false,
                attempts: window.__xwzHoudaLoginOpenAttempts,
                readyState: document.readyState,
                hasWrap: !!document.querySelector('.loginWrap'),
                hasLoginEntry: !!document.querySelector('#login > span')
            };
        })();
    `;
}

function openHoudaLoginDialog(win) {
    const contents = getSafeWebContents(win);
    if (!contents) {
        return Promise.resolve(false);
    }
    return contents.executeJavaScript(getHoudaLoginAutoOpenScript(), true)
        .then((result) => !!(result && result.opened))
        .catch(() => false);
}

function looksLikeFenbiLoginInfo(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    try {
        const info = JSON.parse(String(result.body || '{}'));
        const data = info && typeof info.data === 'object' ? info.data : info;
        return !!(data && (data.id || data.userId || data.userid || data.username));
    } catch (error) {
        return false;
    }
}

function isFenbiLoginName(value) {
    const name = String(value || '').trim();
    return name == 'fenbi' || name == '\u7c89\u7b14';
}

function validateFenbiCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithCookieValue(FENBI_VALIDATE_URL, cookie_value, 0, {
        'Referer': FENBI_LOGIN_URL,
        'Origin': 'https://www.fenbi.com',
        'Accept': 'application/json, text/plain, */*',
    })
        .then((result) => looksLikeFenbiLoginInfo(result))
        .catch(() => false);
}

function getFenbiLoginPanelCheckScript() {
    return `
        (function () {
        function is_visible(el) {
            if (!el) {
                return false;
            }
            var style = window.getComputedStyle(el);
            if (!style || style.display == 'none' || style.visibility == 'hidden' || Number(style.opacity || 1) === 0) {
                return false;
            }
            var rect = el.getBoundingClientRect();
            return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
        }
        function text_of(el) {
            return String((el && (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title'))) || '').replace(/\s+/g, '').trim();
        }
        var panel_nodes = document.querySelectorAll('[role=dialog],[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog],[class*=login-panel],[class*=LoginPanel],[class*=loginPanel],[class*=login-box],[class*=LoginBox],[class*=loginBox],form,iframe');
        for (var i = 0; i < panel_nodes.length; i++) {
            if (!is_visible(panel_nodes[i])) {
                continue;
            }
            if (panel_nodes[i].classList.contains('fenbi-login-modal-wrapper')) {
                return true;
            }
            var text = text_of(panel_nodes[i]);
            if (text.indexOf('\u624b\u673a\u53f7') !== -1 && (text.indexOf('\u9a8c\u8bc1\u7801') !== -1 || text.indexOf('\u5bc6\u7801') !== -1 || text.indexOf('\u5fae\u4fe1') !== -1)) {
                return true;
            }
        }
        var inputs = Array.prototype.slice.call(document.querySelectorAll('input')).filter(is_visible);
        if (inputs.length > 0) {
            var body_text = text_of(document.body);
            return body_text.indexOf('\u624b\u673a\u53f7') !== -1 || body_text.indexOf('\u9a8c\u8bc1\u7801') !== -1 || body_text.indexOf('\u5bc6\u7801') !== -1;
        }
        return false;
        })();
    `;
}

function getFenbiLoginAutoClickScript() {
    return `
        (function () {
        function is_visible(el) {
            if (!el) {
                return false;
            }
            var style = window.getComputedStyle(el);
            if (!style || style.display == 'none' || style.visibility == 'hidden' || Number(style.opacity || 1) === 0) {
                return false;
            }
            var rect = el.getBoundingClientRect();
            return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
        }
        function normalized_text(el) {
            return String((el && (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title'))) || '').replace(/\s+/g, '').trim();
        }
        function has_login_panel() {
            var panel_nodes = document.querySelectorAll('[role=dialog],[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog],[class*=login-panel],[class*=LoginPanel],[class*=loginPanel],[class*=login-box],[class*=LoginBox],[class*=loginBox],form,iframe');
            for (var i = 0; i < panel_nodes.length; i++) {
                if (!is_visible(panel_nodes[i])) {
                    continue;
                }
                if (panel_nodes[i].classList.contains('fenbi-login-modal-wrapper')) {
                    return true;
                }
                var text = normalized_text(panel_nodes[i]);
                if (text.indexOf('\u624b\u673a\u53f7') !== -1 && (text.indexOf('\u9a8c\u8bc1\u7801') !== -1 || text.indexOf('\u5bc6\u7801') !== -1 || text.indexOf('\u5fae\u4fe1') !== -1)) {
                    return true;
                }
            }
            var inputs = Array.prototype.slice.call(document.querySelectorAll('input')).filter(is_visible);
            if (inputs.length > 0) {
                var body_text = normalized_text(document.body);
                if (body_text.indexOf('\u624b\u673a\u53f7') !== -1 || body_text.indexOf('\u9a8c\u8bc1\u7801') !== -1 || body_text.indexOf('\u5bc6\u7801') !== -1) {
                    return true;
                }
            }
            return false;
        }
        function clickable_target(node) {
            if (!node) {
                return null;
            }
            try {
                return node.closest('button,a,[role=button]') || node;
            } catch (error) {
                return node;
            }
        }
        function dispatch_click(node) {
            var el = clickable_target(node);
            if (!el) {
                return false;
            }
            try {
                el.scrollIntoView({ block: 'center', inline: 'center' });
            } catch (error) {
                ;
            }
            var rect = el.getBoundingClientRect();
            var event_options = { bubbles: true, cancelable: true, view: window, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
            var events = ['pointerover', 'mouseover', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
            for (var i = 0; i < events.length; i++) {
                try {
                    var event_name = events[i];
                    var event_obj = event_name.indexOf('pointer') === 0 && typeof PointerEvent !== 'undefined'
                        ? new PointerEvent(event_name, Object.assign({ pointerType: 'mouse', isPrimary: true }, event_options))
                        : new MouseEvent(event_name, event_options);
                    el.dispatchEvent(event_obj);
                } catch (error) {
                    ;
                }
            }
            try {
                el.click();
            } catch (error) {
                ;
            }
            return true;
        }
        function rect_of(node) {
            var el = clickable_target(node);
            if (!el) {
                return null;
            }
            var rect = el.getBoundingClientRect();
            return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
        }
        function is_login_button(node) {
            if (!is_visible(node)) {
                return false;
            }
            var target = clickable_target(node);
            var text = (normalized_text(node) + normalized_text(target)).replace(/\s+/g, '');
            var class_name = String((node && node.className) || '') + ' ' + String((target && target.className) || '');
            if (class_name.indexOf('login-button') !== -1 || class_name.indexOf('loginButton') !== -1) {
                return true;
            }
            if (!text || text.indexOf('\u767b\u5f55') === -1 || text.indexOf('\u5df2\u767b\u5f55') !== -1 || text.indexOf('\u9000\u51fa\u767b\u5f55') !== -1) {
                return false;
            }
            if (text.length > 12) {
                return false;
            }
            var rect = node.getBoundingClientRect();
            return rect.top <= Math.max(220, window.innerHeight * 0.28) && rect.left >= window.innerWidth * 0.45;
        }
        function find_login_button() {
            var direct_selectors = [
                '.fb-header-wrapper .info-wrapper .login-button',
                '.info-wrapper .login-button',
                'button.login-button',
                '.login-button',
                'button[class*=\"login-button\"]',
                '[class*=\"login-button\"]',
                '[class*=\"loginButton\"]',
                'app-header .login-button',
                'fb-header .login-button'
            ];
            for (var d = 0; d < direct_selectors.length; d++) {
                var direct_list = document.querySelectorAll(direct_selectors[d]);
                for (var di = 0; di < direct_list.length; di++) {
                    if (is_visible(direct_list[di])) {
                        return direct_list[di];
                    }
                }
            }
            var selector_groups = [
                '.info-wrapper button,.info-wrapper a,.info-wrapper div,.info-wrapper span',
                '.fb-header-wrapper button,.fb-header-wrapper a,.fb-header-wrapper div,.fb-header-wrapper span',
                'header button,header a,header div,header span',
                '.header button,.header a,.header div,.header span',
                '[class*=header] button,[class*=header] a,[class*=header] div,[class*=header] span',
                '[class*=nav] button,[class*=nav] a,[class*=nav] div,[class*=nav] span',
                'button,a,[role=button],div,span'
            ];
            var candidates = [];
            for (var s = 0; s < selector_groups.length; s++) {
                var list = document.querySelectorAll(selector_groups[s]);
                for (var i = 0; i < list.length; i++) {
                    var node = list[i];
                    if (!is_login_button(node)) {
                        continue;
                    }
                    var rect = node.getBoundingClientRect();
                    candidates.push({ element: node, score: rect.top * 10000 + (window.innerWidth - rect.left) });
                }
            }
            candidates.sort(function (a, b) { return a.score - b.score; });
            return candidates.length ? candidates[0].element : null;
        }
        return new Promise(function (resolve) {
            if (has_login_panel()) {
                resolve({ clicked: false, hasPanel: true, rect: null });
                return;
            }
            var login_btn = find_login_button();
            if (!login_btn) {
                resolve({ clicked: false, hasPanel: false, rect: null });
                return;
            }
            var rect = rect_of(login_btn);
            dispatch_click(login_btn);
            setTimeout(function () {
                if (!has_login_panel()) {
                    dispatch_click(login_btn);
                    if (login_btn.parentElement) {
                        dispatch_click(login_btn.parentElement);
                    }
                }
            }, 120);
            setTimeout(function () {
                resolve({ clicked: true, hasPanel: has_login_panel(), rect: rect });
            }, 360);
        });
        })();
    `;
}

function sendFenbiLoginMouseClick(win, rect) {
    const contents = getSafeWebContents(win);
    if (!contents || !rect) {
        return;
    }
    const x = Math.max(1, Math.round(Number(rect.x || 0) + Number(rect.width || 0) / 2));
    const y = Math.max(1, Math.round(Number(rect.y || 0) + Number(rect.height || 0) / 2));
    try {
        contents.sendInputEvent({type: 'mouseMove', x, y});
        contents.sendInputEvent({type: 'mouseDown', x, y, button: 'left', clickCount: 1});
        contents.sendInputEvent({type: 'mouseUp', x, y, button: 'left', clickCount: 1});
    } catch (error) {
        ;
    }
}

function clickFenbiLoginButton(win, delay_ms = 0) {
    if (!isFenbiLoginName(login_name)) {
        return;
    }
    setTimeout(() => {
        const contents = getSafeWebContents(win);
        if (!contents) {
            return;
        }
        contents.executeJavaScript(getFenbiLoginAutoClickScript(), true)
            .then((result) => {
                if (!result || result.hasPanel || !result.rect) {
                    return;
                }
                const latest_contents = getSafeWebContents(win);
                if (!latest_contents) {
                    return;
                }
                latest_contents.executeJavaScript(getFenbiLoginPanelCheckScript(), true)
                    .then((has_panel) => {
                        if (!has_panel) {
                            sendFenbiLoginMouseClick(win, result.rect);
                        }
                    })
                    .catch(() => {
                        sendFenbiLoginMouseClick(win, result.rect);
                    });
            })
            .catch(() => {
                ;
            });
    }, Math.max(0, Number(delay_ms) || 0));
}

function submitAishangkePasswordLogin(phone, password, is_15, cookie_value) {
    if (!phone || !password) {
        return Promise.resolve('');
    }
    return new Promise((resolve) => {
        let settled = false;
        function finish(result) {
            if (!settled) {
                settled = true;
                resolve(result || '');
            }
        }
        try {
            const payload = 'phone=' + encodeURIComponent(phone)
                + '&password=' + encodeURIComponent(password)
                + '&is_15=' + (is_15 ? 'true' : 'false');
            const request = https.request({
                protocol: 'https:',
                hostname: 'loveshangke.com',
                path: '/user/login/loginAjax',
                method: 'POST',
                headers: {
                    'Cookie': cookie_value || '',
                    'Referer': 'https://loveshangke.com/user/login',
                    'Origin': 'https://loveshangke.com',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                    'Accept': '*/*',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Content-Length': Buffer.byteLength(payload),
                },
            }, (response) => {
                let body = '';
                response.setEncoding('utf8');
                response.on('data', (chunk) => {
                    if (body.length < 262144) {
                        body += chunk;
                    }
                });
                response.on('end', () => {
                    try {
                        const info = JSON.parse(body || '{}');
                        if (Number(info.status || -1) !== 0) {
                            finish('');
                            return;
                        }
                    } catch (error) {
                        finish('');
                        return;
                    }
                    finish(mergeCookieValueWithSetCookie(cookie_value, (response.headers || {})['set-cookie'] || []));
                });
            });
            request.on('error', () => {
                finish('');
            });
            request.setTimeout(12000, () => {
                request.destroy();
                finish('');
            });
            request.write(payload);
            request.end();
        } catch (error) {
            finish('');
        }
    });
}

function injectAishangkeLoginBridge(win) {
    if (!win || win.isDestroyed()) {
        return;
    }
    win.webContents.executeJavaScript(`
        (function () {
            function readForm() {
                var phone = document.getElementById('load_phone');
                var password = document.getElementById('load_password');
                var is15 = document.getElementById('is_15');
                return {
                    href: window.location.href || '',
                    phone: phone ? String(phone.value || '').trim() : '',
                    password: password ? String(password.value || '') : '',
                    is_15: !!(is15 && is15.checked),
                };
            }
            var bridge = window.__LEL_AISHANGKE_LOGIN__;
            if (!bridge) {
                bridge = {
                    submitSeq: 0,
                    form: null,
                    captureSubmit: function () {
                        bridge.submitSeq += 1;
                        bridge.form = readForm();
                    },
                    getState: function () {
                        return {
                            submitSeq: bridge.submitSeq,
                            form: bridge.form || readForm(),
                        };
                    },
                    bind: function () {
                        if (bridge.__bound) {
                            return;
                        }
                        bridge.__bound = true;
                        var handler = function () {
                            bridge.captureSubmit();
                        };
                        ['load_submit', 'load_sbm'].forEach(function (id) {
                            var button = document.getElementById(id);
                            if (button && !button.__lelBound) {
                                button.__lelBound = true;
                                button.addEventListener('click', handler, true);
                            }
                        });
                        if (!document.__lelAishangkeKeyBound) {
                            document.__lelAishangkeKeyBound = true;
                            document.addEventListener('keydown', function (event) {
                                if (event && (event.key === 'Enter' || event.keyCode === 13)) {
                                    handler();
                                }
                            }, true);
                        }
                    },
                };
                window.__LEL_AISHANGKE_LOGIN__ = bridge;
            }
            bridge.bind();
            return bridge.getState();
        })();
    `, true).catch(() => {
        ;
    });
}

function saveGaodoudouCookieValue(cookie_value) {
    if (!cookie_value) {
        return false;
    }
    const cookies_obj = readCookiesObject();
    cookies_obj.gaodoudou = String(cookie_value);
    try {
        writeCookiesObject(cookies_obj);
        return true;
    } catch (error) {
        console.error(
            '[login-mooc] write Gaodoudou cookie file failed:',
            cookies_file,
            error && error.stack || error,
        );
        return false;
    }
}

function saveLoginCookieData(cookie_data, cookie_key = login_name) {
    if (cookie_data === undefined || cookie_data === null || cookie_data === '') {
        return;
    }
    try {
        ensureCookiesFileParentDir();
    } catch (error) {
        console.error('[login-mooc] create cookie dir failed:', cookies_file, error && error.stack || error);
        if (login_name == 'dongao') {
            dongao_save_inflight = false;
        }
        if (login_name == 'huatu') {
            huatu_save_inflight = false;
        }
        if (login_name == 'tmooc') {
            tmooc_save_inflight = false;
        }
        if (login_name == 'youzan' || login_name.startsWith('youzan.')) {
            youzan_save_inflight = false;
        }
        if (login_name == 'ahuyikao') {
            ahu_save_inflight = false;
        }
        if (login_name == 'unipus') {
            unipus_save_inflight = false;
        }
        if (login_name == 'sikiedu') {
            sikiedu_save_inflight = false;
        }
        if (login_name == 'cnmooc') {
            cnmooc_save_inflight = false;
        }
        if (login_name == 'mison') {
            mison_save_inflight = false;
        }
        if (login_name == 'xuexi1998') {
            xuexi1998_save_inflight = false;
        }
        if (login_name == 'smartedu') {
            smartedu_save_inflight = false;
        }
        if (login_name == 'shikaobang') {
            shikaobang_save_inflight = false;
        }
        if (login_name == 'yiqikaojiaoshi') {
            yiqikaojiaoshi_save_inflight = false;
        }
        if (login_name == 'xiaoyuanyouke') {
            xiaoyuanyouke_save_inflight = false;
        }
        if (login_name == 'yijiayk') {
            yijiayk_save_inflight = false;
        }
        if (login_name == 'todoen') {
            todoen_save_inflight = false;
        }
        return;
    }
    let cookies_obj = readCookiesObject();
    cookies_obj[cookie_key] = cookie_data;
    try {
        writeCookiesObject(cookies_obj);
    } catch (error) {
        console.error('[login-mooc] write cookie file failed:', cookies_file, error && error.stack || error);
        if (login_name == 'dongao') {
            dongao_save_inflight = false;
        }
        if (login_name == 'huatu') {
            huatu_save_inflight = false;
        }
        if (login_name == 'tmooc') {
            tmooc_save_inflight = false;
        }
        if (login_name == 'youzan' || login_name.startsWith('youzan.')) {
            youzan_save_inflight = false;
        }
        if (login_name == 'ahuyikao') {
            ahu_save_inflight = false;
        }
        if (login_name == 'unipus') {
            unipus_save_inflight = false;
        }
        if (login_name == 'sikiedu') {
            sikiedu_save_inflight = false;
        }
        if (login_name == 'cnmooc') {
            cnmooc_save_inflight = false;
        }
        if (login_name == 'mison') {
            mison_save_inflight = false;
        }
        if (login_name == 'xuexi1998') {
            xuexi1998_save_inflight = false;
        }
        if (login_name == 'smartedu') {
            smartedu_save_inflight = false;
        }
        if (login_name == 'shikaobang') {
            shikaobang_save_inflight = false;
        }
        if (login_name == 'yiqikaojiaoshi') {
            yiqikaojiaoshi_save_inflight = false;
        }
        if (login_name == 'xiaoyuanyouke') {
            xiaoyuanyouke_save_inflight = false;
        }
        if (login_name == 'yijiayk') {
            yijiayk_save_inflight = false;
        }
        if (login_name == 'todoen') {
            todoen_save_inflight = false;
        }
        return;
    }
    if (login_name === 'yikaobang') yikaobang_login_success = true;
    requestAppExit();
    return true;
}

function saveLoginCookieValue(cookie_value, cookie_key = login_name) {
    if (!cookie_value) {
        return;
    }
    return saveLoginCookieData(String(cookie_value || ''), cookie_key);
}

let dingtalk_yunxuetang_login_pending = false;

async function trySaveDingtalkYunxuetangLoginResult(win) {
    if (!isWindowAlive(win) || dingtalk_yunxuetang_login_pending) {
        return;
    }
    dingtalk_yunxuetang_login_pending = true;
    let timeout = null;
    try {
        const probe = win.webContents.executeJavaScript(`
            (async () => {
                if (location.origin !== 'https://d.yunxuetang.cn') return null;
                const info = {};
                for (const key of ['token', 'orgId', 'orgCode', 'userId', 'domain', 'sourceCode']) {
                    info[key] = localStorage.getItem(key) || '';
                }
                if (!info.token || !info.orgId) return null;
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 10000);
                try {
                    const response = await fetch('https://api-phx-ali.yunxuetang.cn/core/token/check', {
                        headers: {Token: info.token, OrgId: info.orgId, Source: '501'},
                        signal: controller.signal,
                    });
                    if (!response.ok || !(await response.json()).isValid) return null;
                    if (localStorage.getItem('token') !== info.token
                            || localStorage.getItem('orgId') !== info.orgId) return null;
                    return info;
                } finally {
                    clearTimeout(timer);
                }
            })();
        `);
        const result = await Promise.race([
            probe,
            new Promise(resolve => { timeout = setTimeout(() => resolve(null), 12000); }),
        ]);
        if (isWindowAlive(win) && result && result.token && result.orgId) {
            saveLoginCookieValue(JSON.stringify(result), 'dingtalk.yunxuetang');
        }
    } catch (_) {
        // Navigation during the official login is retried by the shared poll.
    } finally {
        clearTimeout(timeout);
        dingtalk_yunxuetang_login_pending = false;
    }
}

let geekbang_login_probe_pending = false;
let geekbang_login_probe_last_at = 0;

function trySaveGeekbangLoginResult(win, cookies) {
    const scoped = (cookies || []).filter(cookie => {
        const domain = String(cookie.domain || '').replace(/^\./, '').toLowerCase();
        return domain === 'geekbang.org' || domain === 'time.geekbang.org';
    });
    if (!isWindowAlive(win) || geekbang_login_probe_pending
        || Date.now() - geekbang_login_probe_last_at < 3000
        || !scoped.some(cookie => cookie.name === 'GCESS' && cookie.value)) {
        return;
    }
    try {
        if (new URL(getSafeWindowUrl(win)).hostname !== 'time.geekbang.org') {
            return;
        }
    } catch (_) {
        return;
    }
    geekbang_login_probe_pending = true;
    geekbang_login_probe_last_at = Date.now();
    win.webContents.executeJavaScript(`(async () => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 8000);
        try {
            const response = await fetch('/serv/v3/learn/product', {
                method: 'POST', credentials: 'include', signal: controller.signal,
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({type: 'c3', size: 1, prev: 0})
            });
            const result = await response.json();
            return response.ok && result.code === 0;
        } catch (_) {
            return false;
        } finally {
            clearTimeout(timer);
        }
    })()`).then(valid => {
        if (valid && isWindowAlive(win)) {
            saveLoginCookieValue(buildCookieValue(scoped));
        }
    }).catch(() => {}).finally(() => {
        geekbang_login_probe_pending = false;
    });
}

function normalizeClassinWebcastContext(storage_result, cookies, fallback_uid) {
    storage_result = storage_result && typeof storage_result === 'object'
        ? storage_result
        : {};
    const live_chat_login = String(storage_result.liveChatLogin || '').trim();
    const live_chat_uid = String(
        storage_result.liveChatUid || fallback_uid || ''
    ).trim();
    const live_chat_account = String(
        storage_result.liveChatAccount || ''
    ).trim();
    const server_cookie = String(storage_result.serverCookie || '').trim();
    if (
        live_chat_login !== '1'
        || !live_chat_uid
        || !live_chat_account
        || !server_cookie
    ) {
        return null;
    }
    const login_cookie = (cookies || []).find((cookie) => (
        cookie
        && cookie.name === 'webcast_login_status'
        && cookie.value
    ));
    return {
        liveChatUid: live_chat_uid,
        liveChatAccount: live_chat_account,
        serverCookie: server_cookie,
        webcast_login_status: String(login_cookie && login_cookie.value || '').trim(),
    };
}

function trySaveClassinWebcastContext(win, cookies) {
    if (
        classin_webcast_save_inflight
        || !isWindowAlive(win)
    ) {
        return;
    }
    classin_webcast_save_inflight = true;
    win.webContents.executeJavaScript(`
        (() => ({
            liveChatUid: localStorage.getItem('liveChatUid') || '',
            liveChatAccount: localStorage.getItem('liveChatAccount') || '',
            liveChatLogin: localStorage.getItem('liveChatLogin') || '',
            serverCookie: localStorage.getItem('serverCookie') || '',
        }))();
    `).then((storage_result) => {
        const context = normalizeClassinWebcastContext(
            storage_result,
            cookies,
            classin_webcast_uid,
        );
        if (!context) {
            classin_webcast_save_inflight = false;
            return;
        }
        saveLoginCookieData(JSON.stringify(context));
    }).catch(() => {
        classin_webcast_save_inflight = false;
    });
}

function parseSparkeStoredValue(value) {
    if (value === undefined || value === null || value === '') {
        return null;
    }
    if (typeof value !== 'string') {
        return value;
    }
    try {
        return JSON.parse(value);
    } catch (error) {
        return value;
    }
}

function findSparkeLoginValue(value, keys, depth = 0, allow_string = false) {
    value = parseSparkeStoredValue(value);
    if (!value || depth > 4) {
        return '';
    }
    if (typeof value === 'string') {
        return allow_string ? value.trim() : '';
    }
    if (Array.isArray(value)) {
        for (const item of value) {
            const found = findSparkeLoginValue(item, keys, depth + 1, allow_string);
            if (found) {
                return found;
            }
        }
        return '';
    }
    if (typeof value !== 'object') {
        return '';
    }
    for (const key of keys) {
        const direct = value[key];
        if (direct !== undefined && direct !== null && String(direct).trim()) {
            return String(direct).trim();
        }
    }
    for (const key of ['data', 'body', 'results', 'result', 'payload', 'user', 'userinfo', 'userInfo']) {
        const nested = findSparkeLoginValue(value[key], keys, depth + 1, allow_string);
        if (nested) {
            return nested;
        }
    }
    return '';
}

function createSparkeTerminalId() {
    try {
        return crypto.randomBytes(16).toString('hex');
    } catch (error) {
        return String(Date.now()) + String(Math.random()).replace(/\D/g, '').padEnd(19, '0').slice(0, 19);
    }
}

function normalizeSparkeLoginPayload(state) {
    state = state && typeof state === 'object' ? state : {};
    const token_raw = state.tokenRaw !== undefined ? state.tokenRaw : (state.token_raw !== undefined ? state.token_raw : state);
    const parsed_token = parseSparkeStoredValue(token_raw);
    let token = findSparkeLoginValue(
        parsed_token,
        ['token', 'accessToken', 'access_token', 'sparkToken'],
        0,
        true,
    );
    if (/^bearer\s+/i.test(token)) {
        token = token.replace(/^bearer\s+/i, '').trim();
    }
    const terminalid = String(
        state.terminalid || state.terminalId
        || findSparkeLoginValue(parsed_token, ['terminalid', 'terminalId'], 0, false)
        || createSparkeTerminalId()
    ).trim();
    return {
        token,
        userId: findSparkeLoginValue(
            parsed_token,
            ['userId', 'userid', 'uid', 'user_id'],
            0,
            false,
        ) || String(state.userId || state.userid || state.uid || '').trim(),
        phone: findSparkeLoginValue(
            parsed_token,
            ['phone', 'mobile', 'username', 'account'],
            0,
            false,
        ) || String(state.phone || state.mobile || '').trim(),
        terminalid,
        browserId: String(state.browserId || state.browserid || '').trim(),
    };
}

function buildSparkePvalue(payload, timestamp = Date.now()) {
    payload = normalizeSparkeLoginPayload(payload);
    timestamp = Number(timestamp) || Date.now();
    const sign_text = 'sign'
        + SPARKE_APP_ID
        + SPARKE_API_VERSION
        + payload.terminalid
        + payload.token
        + timestamp
        + 'sign';
    return {
        appId: SPARKE_APP_ID,
        v: SPARKE_API_VERSION,
        os: 'web',
        terminalType: SPARKE_TERMINAL_TYPE,
        timestamp,
        terminalid: payload.terminalid,
        appSign: crypto.createHash('md5').update(sign_text, 'utf8').digest('hex'),
        token: payload.token,
        userId: payload.userId,
        browserId: payload.browserId,
    };
}

function parseSparkeApiResult(response_body) {
    if (!response_body || typeof response_body !== 'object') {
        return null;
    }
    const result = response_body.results && typeof response_body.results === 'object'
        ? response_body.results
        : response_body;
    const ret = String(result.ret !== undefined ? result.ret : (result.code !== undefined ? result.code : ''));
    if (!['100', '200', '0'].includes(ret)) {
        return null;
    }
    const body = result.body || result.data || result.result || result.payload;
    return body && typeof body === 'object' && !Array.isArray(body) ? body : null;
}

async function validateSparkeLoginPayload(payload) {
    const normalized = normalizeSparkeLoginPayload(payload);
    if (!normalized.token) {
        return null;
    }
    const result = await requestJsonUrl(
        'GET',
        SPARKE_PROFILE_URL,
        {pvalue: JSON.stringify(buildSparkePvalue(normalized))},
        {
            'User-Agent': DEFAULT_BROWSER_USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'text/plain;charset=utf-8',
            'Origin': 'https://course.sparke.cn',
            'Referer': 'https://course.sparke.cn/study/',
            'Authorization': 'Bearer ' + normalized.token,
        },
    );
    const profile = parseSparkeApiResult(parseJsonResponseBody(result));
    if (!profile) {
        return null;
    }
    const profile_user_id = String(profile.userId || profile.uid || '').trim();
    const profile_phone = String(profile.phone || profile.mobile || '').trim();
    const profile_token = String(profile.token || profile.accessToken || '').trim();
    if (!(profile_user_id || profile_phone || profile_token)) {
        return null;
    }
    normalized.token = profile_token || normalized.token;
    normalized.userId = profile_user_id || normalized.userId;
    normalized.phone = profile_phone || normalized.phone;
    return normalized;
}

async function exchangeSparkePcLoginPayload(payload) {
    const normalized = normalizeSparkeLoginPayload(payload);
    if (!normalized.token) {
        return null;
    }
    const pvalue = buildSparkePvalue(normalized);
    const result = await requestJsonUrl(
        'GET',
        SPARKE_API_BASE + '/user/exchangeToken',
        {
            accessToken: normalized.token,
            sparkPlatform: 'pc',
            pvalue: JSON.stringify(pvalue),
        },
        {
            'User-Agent': DEFAULT_BROWSER_USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'text/plain;charset=utf-8',
            'Origin': 'https://course.sparke.cn',
            'Referer': 'https://course.sparke.cn/',
            'Authorization': 'Bearer ' + normalized.token,
        },
    );
    const exchanged = parseSparkeApiResult(parseJsonResponseBody(result));
    if (!exchanged) {
        return null;
    }
    const pc_payload = normalizeSparkeLoginPayload({
        tokenRaw: exchanged,
        terminalid: normalized.terminalid,
        browserId: normalized.browserId,
    });
    return pc_payload.token ? pc_payload : null;
}

function isLegacySparkeRuntime() {
    const chrome_major = Number(String(process.versions.chrome || '').split('.')[0]);
    return chrome_major > 0 && chrome_major < 85;
}

function buildSparkeWebPvalue(terminal_id, token = '', timestamp = Date.now()) {
    terminal_id = String(terminal_id || '').trim() || createSparkeTerminalId();
    token = String(token || '').trim();
    timestamp = Number(timestamp) || Date.now();
    const sign_text = 'sign'
        + SPARKE_WEB_APP_ID
        + SPARKE_API_VERSION
        + terminal_id
        + token
        + timestamp
        + 'sign';
    return {
        appId: SPARKE_WEB_APP_ID,
        v: SPARKE_API_VERSION,
        os: 'web',
        terminalType: SPARKE_TERMINAL_TYPE,
        timestamp,
        terminalid: terminal_id,
        appSign: crypto.createHash('md5').update(sign_text, 'utf8').digest('hex'),
        token,
        userId: '',
        browserId: '',
    };
}

function buildSparkeWebHeaders(pvalue, token = '') {
    const authorization = JSON.stringify(pvalue);
    const headers = {
        'User-Agent': DEFAULT_BROWSER_USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://www.sparke.cn',
        'Referer': 'https://www.sparke.cn/',
        'authorization': authorization,
        'spark-authorization': SPARKE_WEB_AUTHORIZATION,
        'spark-platform': 'pc_new',
    };
    if (token) {
        headers['spark-auth'] = 'bearer ' + token;
    }
    return headers;
}

async function requestSparkeLegacyQrConfig() {
    sparke_legacy_terminal_id = sparke_legacy_terminal_id || createSparkeTerminalId();
    const pvalue = buildSparkeWebPvalue(sparke_legacy_terminal_id);
    const authorization = JSON.stringify(pvalue);
    const result = await requestJsonUrl(
        'GET',
        SPARKE_WEB_GATEWAY + '/spark-user/oauth/render/wechat_open/pc_new',
        {pvalue: authorization},
        buildSparkeWebHeaders(pvalue),
    );
    const response_body = parseJsonResponseBody(result);
    const data = response_body && response_body.data;
    if (Number(response_body && response_body.code) !== 200 || !data) {
        return null;
    }
    const authorize_url = String(data.authorizeUrl || '').trim();
    const state = String(data.state || '').trim();
    const app_id = String(data.appId || '').trim();
    try {
        const parsed = new URL(authorize_url);
        if (
            parsed.protocol !== 'https:'
            || parsed.hostname !== 'www.sparke.cn'
            || parsed.pathname !== '/loginSuccess'
        ) {
            return null;
        }
    } catch (error) {
        return null;
    }
    if (!state || !app_id) {
        return null;
    }
    sparke_legacy_state = state;
    return {authorizeUrl: authorize_url, state, appId: app_id};
}

function setSparkeLegacyStatus(win, message, is_error = false) {
    if (!isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return win.webContents.executeJavaScript(`
        (() => {
            const status = document.getElementById('sparkeLegacyStatus');
            const retry = document.getElementById('sparkeLegacyRetry');
            if (status) {
                status.textContent = ${JSON.stringify(String(message || ''))};
                status.classList.toggle('error', ${JSON.stringify(!!is_error)});
            }
            if (retry) {
                retry.hidden = ${JSON.stringify(!is_error)};
            }
            return Boolean(status);
        })();
    `, true).catch(() => false);
}

function renderSparkeLegacyLogin(win, config = null) {
    if (!isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    const html = [
        '<main class="sparke-legacy-bg">',
        '<section class="sparke-legacy-login loginBox" role="dialog" aria-label="\u661f\u706b\u82f1\u8bed\u767b\u5f55">',
        '<div class="sparke-legacy-top">',
        '<div id="sparkeLegacySwitchHint" class="sparke-legacy-switch-hint"><span class="ac">\u8d26\u53f7\u767b\u5f55</span></div>',
        '<span class="sparke-legacy-switch-arrow" aria-hidden="true">\u203a</span>',
        '<button id="sparkeLegacyModeSwitch" class="phone sparke-legacy-mode-switch" type="button" title="\u5207\u6362\u767b\u5f55\u65b9\u5f0f" aria-label="\u8d26\u53f7\u767b\u5f55"></button>',
        '</div>',
        '<div id="sparkeLegacyQrView" class="sparke-legacy-view sparke-legacy-qr-view">',
        '<h1>\u5fae\u4fe1\u626b\u7801\u767b\u5f55</h1>',
        '<div class="sparke-legacy-qr-wrap"><div id="login_container" class="sparke-legacy-qr">\u6b63\u5728\u83b7\u53d6\u4e8c\u7ef4\u7801...</div></div>',
        '</div>',
        '<div id="sparkeLegacyAccountView" class="sparke-legacy-view sparke-legacy-account-view" hidden>',
        '<div class="sparke-legacy-tabs" role="tablist">',
        '<button id="sparkeLegacySmsTab" class="codeTab sparke-legacy-tab active" type="button" role="tab" aria-selected="true">\u9a8c\u8bc1\u7801\u767b\u5f55<span></span></button>',
        '<button id="sparkeLegacyPasswordTab" class="passTab sparke-legacy-tab" type="button" role="tab" aria-selected="false">\u5bc6\u7801\u767b\u5f55<span></span></button>',
        '</div>',
        '<div id="sparkeLegacySmsForm" class="sparke-legacy-form">',
        '<label class="phonec sparke-legacy-field"><span class="sparke-legacy-field-icon">+86</span><input id="sparkeLegacySmsPhone" class="phoneNumber" type="tel" inputmode="numeric" maxlength="11" autocomplete="tel" placeholder="\u8bf7\u8f93\u5165\u624b\u673a\u53f7"></label>',
        '<label class="phonec sparke-legacy-field"><span class="sparke-legacy-field-icon">#</span><input id="sparkeLegacySmsCode" class="phoneNumber" type="text" inputmode="numeric" maxlength="12" autocomplete="one-time-code" placeholder="\u8bf7\u8f93\u5165\u9a8c\u8bc1\u7801"><button id="sparkeLegacySendSms" class="phoneTip0 sparke-legacy-send" type="button">\u83b7\u53d6\u9a8c\u8bc1\u7801</button></label>',
        '<button id="sparkeLegacySmsLogin" class="sparke-legacy-submit" type="button">\u767b\u5f55/\u6ce8\u518c</button>',
        '</div>',
        '<div id="sparkeLegacyPasswordForm" class="sparke-legacy-form" hidden>',
        '<label class="phonec sparke-legacy-field"><span class="sparke-legacy-field-icon">@</span><input id="sparkeLegacyAccount" class="phoneNumber" type="text" maxlength="100" autocomplete="username" placeholder="\u8bf7\u8f93\u5165\u8d26\u53f7"></label>',
        '<label class="phonec sparke-legacy-field"><span class="sparke-legacy-field-icon">*</span><input id="sparkeLegacyPassword" class="phoneNumber" type="password" maxlength="100" autocomplete="current-password" placeholder="\u8bf7\u8f93\u5165\u5bc6\u7801"><button id="sparkeLegacyPasswordVisible" class="sparke-legacy-password-visible" type="button" title="\u663e\u793a\u5bc6\u7801" aria-label="\u663e\u793a\u5bc6\u7801">\u25c9</button></label>',
        '<button id="sparkeLegacyPasswordLogin" class="sparke-legacy-submit" type="button">\u767b\u5f55</button>',
        '</div>',
        '</div>',
        '<p id="sparkeLegacyStatus" class="sparke-legacy-status" aria-live="polite"></p>',
        '<button id="sparkeLegacyRetry" class="sparke-legacy-retry" type="button" hidden>\u5237\u65b0\u4e8c\u7ef4\u7801</button>',
        '<footer class="sparke-legacy-footer">\u767b\u5f55\u6ce8\u518c\u5373\u4ee3\u8868\u540c\u610f<a href="https://course.sparke.cn/agreement/" target="_blank" rel="noopener">\u300a\u661f\u706b\u82f1\u8bed\u7528\u6237\u670d\u52a1\u534f\u8bae\u300b</a><a href="https://m.sparke.cn/login_hm/privacy/" target="_blank" rel="noopener">\u300a\u9690\u79c1\u653f\u7b56\u300b</a></footer>',
        '</section>',
        '</main>',
    ].join('');
    const css = [
        'html,body{height:100%!important;margin:0!important;min-width:100%!important;overflow-x:auto!important;overflow-y:auto!important;padding:0!important;width:100%!important}',
        '#__layout,#__nuxt{min-width:100%!important;overflow-x:visible!important;width:100%!important}',
        '.container-c{display:flex!important;flex-direction:row!important;height:auto!important;min-height:100vh!important;min-width:1440px!important;position:relative!important}',
        '.container-c .imagec{align-items:center!important;background:#3d7dcc url(https://www.sparke.cn/_nuxt/loginbg.itO_eZfS.png) center center/cover no-repeat!important;display:flex!important;flex-direction:column!important;height:auto!important;justify-content:space-between!important;min-height:800px!important;width:100%!important}',
        '.container-c .imagec .logo{display:block!important;height:89px!important;margin-top:92px!important;object-fit:contain!important;width:300px!important}',
        '.container-c .imagec .copyright{color:rgba(255,255,255,.6)!important;font-size:12px!important;font-style:normal!important;height:36px!important;line-height:18px!important;margin-bottom:40px!important;text-align:center!important}',
        '.container-c .loginc{flex:1!important;position:absolute!important;width:100%!important}',
        '.sparke-legacy-bg{align-items:center;display:flex;height:100vh;justify-content:center;min-height:800px;position:relative;width:100%;z-index:1}',
        '.sparke-legacy-login{background:#fff;border:1px solid rgba(0,0,0,.06);border-radius:8px;box-shadow:0 7px 14px rgba(0,0,0,.12);box-sizing:border-box;height:418px;margin-top:20px;overflow:hidden;position:relative;text-align:center;width:540px}',
        '.sparke-legacy-top{height:54px;position:relative}',
        '.sparke-legacy-switch-hint{align-items:center;background:#e8f1ff;border-radius:4px;display:flex;height:26px;padding:0 8px;position:absolute;right:58px;top:10px}',
        '.sparke-legacy-switch-hint .ac{color:#06f;font-size:12px;line-height:18px;white-space:nowrap}',
        '.sparke-legacy-switch-arrow{color:#06f;font-size:18px;line-height:18px;position:absolute;right:53px;top:14px}',
        '.sparke-legacy-mode-switch{background:#66a3ff;border:0;border-top-right-radius:8px;clip-path:polygon(0 0,100% 0,100% 100%);cursor:pointer;height:54px;margin:0;padding:0;position:absolute;right:0;top:0;width:54px}',
        '.sparke-legacy-mode-switch:before{border:2px solid #fff;border-radius:2px;box-sizing:border-box;content:"";height:20px;position:absolute;right:9px;top:7px;width:13px}',
        '.sparke-legacy-mode-switch.account:before{background:repeating-linear-gradient(0deg,#fff 0,#fff 2px,transparent 2px,transparent 4px),repeating-linear-gradient(90deg,#fff 0,#fff 2px,transparent 2px,transparent 4px);border:0;height:18px;width:18px}',
        '.sparke-legacy-view[hidden],.sparke-legacy-form[hidden]{display:none!important}',
        '.sparke-legacy-qr-view h1{color:#222;font-size:20px;font-weight:700;line-height:30px;margin:0;text-align:center}',
        '.sparke-legacy-qr-wrap{height:250px;margin:26px auto 0;overflow:hidden;width:300px}',
        '.sparke-legacy-qr{align-items:center;color:#818592;display:flex;font-size:14px;height:250px;justify-content:center;margin:0 auto;width:300px}',
        '.sparke-legacy-qr iframe{border:0!important;display:block!important;height:250px!important;margin:0 auto!important;width:300px!important}',
        '.sparke-legacy-account-view{align-items:center;display:flex;flex-direction:column}',
        '.sparke-legacy-tabs{box-sizing:border-box;display:flex;height:28px;justify-content:space-between;margin-top:12px;padding:0 53px;width:300px}',
        '.sparke-legacy-tab{background:transparent;border:0;color:#222;cursor:pointer;font-size:16px;line-height:24px;margin:0;padding:0;position:relative}',
        '.sparke-legacy-tab span{background:transparent;bottom:-4px;height:1px;left:0;position:absolute;width:100%}',
        '.sparke-legacy-tab.active{color:#06f;font-weight:700}',
        '.sparke-legacy-tab.active span{background:#06f}',
        '.sparke-legacy-form{display:flex;flex-direction:column;margin-top:30px;width:300px}',
        '.sparke-legacy-field{align-items:center;background:#fff;border:1px solid rgba(0,0,0,.15);border-radius:8px;box-sizing:border-box;display:flex;height:41px;margin:0;padding:0 10px 0 0;position:relative;width:300px}',
        '.sparke-legacy-field+.sparke-legacy-field{margin-top:16px}',
        '.sparke-legacy-field-icon{align-items:center;color:#818592;display:flex;flex:0 0 41px;font-size:12px;height:41px;justify-content:center}',
        '.sparke-legacy-field input{appearance:textfield;background:#fff;border:0;box-sizing:border-box;color:#222;flex:1;font-size:14px;height:39px;line-height:21px;min-width:0;outline:none;padding:0}',
        '.sparke-legacy-send{background:#fff;border:0;color:#06f;cursor:pointer;font-size:14px;line-height:21px;padding:0;white-space:nowrap}',
        '.sparke-legacy-send:disabled{color:#818592;cursor:default}',
        '.sparke-legacy-password-visible{background:#fff;border:0;color:#818592;cursor:pointer;font-size:18px;height:39px;padding:0;width:32px}',
        '.sparke-legacy-submit{background:linear-gradient(90deg,#00a1ff,#06f);border:0;border-radius:8px;color:#fff;cursor:pointer;font-size:14px;height:41px;line-height:21px;margin-top:30px;width:300px}',
        '.sparke-legacy-submit:disabled{cursor:default;opacity:.65}',
        '.sparke-legacy-status{bottom:45px;color:#818592;font-size:12px;left:20px;line-height:18px;margin:0;min-height:18px;overflow:hidden;position:absolute;right:20px;text-overflow:ellipsis;white-space:nowrap}',
        '.sparke-legacy-status.error{color:#ff2e00}',
        '.sparke-legacy-retry{background:transparent;border:0;bottom:45px;color:#06f;cursor:pointer;font-size:12px;line-height:18px;padding:0;position:absolute;right:44px}',
        '.sparke-legacy-footer{align-items:center;background:rgba(0,0,0,.03);bottom:0;color:#222;display:flex;font-size:12px;height:42px;justify-content:center;left:0;line-height:18px;position:absolute;right:0}',
        '.sparke-legacy-footer a{color:#06f;text-decoration:none}',
        '@media(max-height:700px){.container-c{min-height:600px!important}.container-c .imagec{min-height:600px!important}.container-c .imagec .logo{height:64px!important;margin-top:18px!important;width:216px!important}.container-c .imagec .copyright{margin-bottom:12px!important}.sparke-legacy-bg{min-height:600px}.sparke-legacy-login{margin-top:18px}}',
    ].join('');
    const safe_config = config ? {
        authorizeUrl: String(config.authorizeUrl || ''),
        state: String(config.state || ''),
        appId: String(config.appId || ''),
    } : null;
    return win.webContents.executeJavaScript(`
        (() => {
            let style = document.getElementById('sparkeLegacyStyle');
            if (!style) {
                style = document.createElement('style');
                style.id = 'sparkeLegacyStyle';
                document.head.appendChild(style);
            }
            style.textContent = ${JSON.stringify(css)};
            let shell = document.querySelector('.container-c');
            let loginRoot = document.querySelector('.loginc');
            if (!shell || !loginRoot) {
                document.body.innerHTML = '<div id="__nuxt"><div class="container-c">'
                    + '<div class="imagec"><img class="logo" alt="" src="https://www.sparke.cn/_nuxt/loginlogo.DZjBkc-K.png">'
                    + '<div class="copyright"><div>\u7248\u6743\u58f0\u660e Copyright\u00a92023. All Rights Reserved \u5317\u4eac\u76db\u4e16\u661f\u706b\u6559\u80b2\u79d1\u6280\u6709\u9650\u8d23\u4efb\u516c\u53f8</div><div>\u7248\u6743\u6240\u6709 \u4eacICP\u590708105196\u53f7-1</div></div></div>'
                    + '<div class="loginc"></div></div></div>';
                shell = document.querySelector('.container-c');
                loginRoot = document.querySelector('.loginc');
            }
            const image = shell && shell.querySelector('.imagec');
            let logo = image && image.querySelector('.logo');
            if (image && !logo) {
                logo = document.createElement('img');
                logo.className = 'logo';
                logo.alt = '';
                logo.src = 'https://www.sparke.cn/_nuxt/loginlogo.DZjBkc-K.png';
                image.insertBefore(logo, image.firstChild);
            }
            if (logo && !logo.getAttribute('src')) {
                logo.src = 'https://www.sparke.cn/_nuxt/loginlogo.DZjBkc-K.png';
            }
            if (image && !image.querySelector('.copyright')) {
                const copyright = document.createElement('div');
                copyright.className = 'copyright';
                copyright.innerHTML = '<div>\u7248\u6743\u58f0\u660e Copyright\u00a92023. All Rights Reserved \u5317\u4eac\u76db\u4e16\u661f\u706b\u6559\u80b2\u79d1\u6280\u6709\u9650\u8d23\u4efb\u516c\u53f8</div><div>\u7248\u6743\u6240\u6709 \u4eacICP\u590708105196\u53f7-1</div>';
                image.appendChild(copyright);
            }
            loginRoot.innerHTML = ${JSON.stringify(html)};
            document.body.dataset.sparkeLegacyLogin = '1';
            document.body.dataset.sparkeLegacyMode = 'qr';
            const retry = document.getElementById('sparkeLegacyRetry');
            retry.addEventListener('click', () => window.location.reload());
            const status = document.getElementById('sparkeLegacyStatus');
            const qrView = document.getElementById('sparkeLegacyQrView');
            const accountView = document.getElementById('sparkeLegacyAccountView');
            const switchHint = document.getElementById('sparkeLegacySwitchHint').querySelector('.ac');
            const modeSwitch = document.getElementById('sparkeLegacyModeSwitch');
            const smsTab = document.getElementById('sparkeLegacySmsTab');
            const passwordTab = document.getElementById('sparkeLegacyPasswordTab');
            const smsForm = document.getElementById('sparkeLegacySmsForm');
            const passwordForm = document.getElementById('sparkeLegacyPasswordForm');
            const sendSms = document.getElementById('sparkeLegacySendSms');
            const smsLogin = document.getElementById('sparkeLegacySmsLogin');
            const passwordLogin = document.getElementById('sparkeLegacyPasswordLogin');
            const passwordInput = document.getElementById('sparkeLegacyPassword');
            let mode = 'qr';
            let accountMode = 'sms';
            let pendingAction = '';
            let pendingActionId = '';
            let countdownTimer = null;

            function setStatus(message, isError) {
                status.textContent = String(message || '');
                status.classList.toggle('error', Boolean(isError));
            }
            function showMode(nextMode) {
                mode = nextMode === 'account' ? 'account' : 'qr';
                qrView.hidden = mode !== 'qr';
                accountView.hidden = mode !== 'account';
                switchHint.textContent = mode === 'qr' ? '\u8d26\u53f7\u767b\u5f55' : '\u5fae\u4fe1\u626b\u7801\u767b\u5f55';
                modeSwitch.setAttribute('aria-label', switchHint.textContent);
                modeSwitch.classList.toggle('account', mode === 'account');
                document.body.dataset.sparkeLegacyMode = mode;
                setStatus('', false);
            }
            function showAccountMode(nextMode) {
                accountMode = nextMode === 'password' ? 'password' : 'sms';
                smsForm.hidden = accountMode !== 'sms';
                passwordForm.hidden = accountMode !== 'password';
                smsTab.classList.toggle('active', accountMode === 'sms');
                passwordTab.classList.toggle('active', accountMode === 'password');
                smsTab.setAttribute('aria-selected', String(accountMode === 'sms'));
                passwordTab.setAttribute('aria-selected', String(accountMode === 'password'));
                document.body.dataset.sparkeLegacyAccountMode = accountMode;
                setStatus('', false);
            }
            function setBusy(type, busy) {
                if (type === 'send_sms') {
                    sendSms.disabled = busy;
                    if (busy) sendSms.textContent = '\u53d1\u9001\u4e2d...';
                } else if (type === 'login_sms') {
                    smsLogin.disabled = busy;
                    smsLogin.textContent = busy ? '\u767b\u5f55\u4e2d...' : '\u767b\u5f55/\u6ce8\u518c';
                } else if (type === 'login_password') {
                    passwordLogin.disabled = busy;
                    passwordLogin.textContent = busy ? '\u767b\u5f55\u4e2d...' : '\u767b\u5f55';
                }
            }
            function startCountdown(seconds) {
                let remaining = Number(seconds) || 60;
                if (countdownTimer) clearInterval(countdownTimer);
                sendSms.disabled = true;
                sendSms.textContent = remaining + '\u79d2\u540e\u83b7\u53d6';
                countdownTimer = setInterval(() => {
                    remaining -= 1;
                    if (remaining <= 0) {
                        clearInterval(countdownTimer);
                        countdownTimer = null;
                        sendSms.disabled = false;
                        sendSms.textContent = '\u83b7\u53d6\u9a8c\u8bc1\u7801';
                        return;
                    }
                    sendSms.textContent = remaining + '\u79d2\u540e\u83b7\u53d6';
                }, 1000);
            }
            function dispatchAction(type, values) {
                if (pendingAction) return;
                pendingAction = type;
                pendingActionId = String(Date.now()) + '-' + String(Math.random());
                setBusy(type, true);
                setStatus('', false);
                const action = {id: pendingActionId, type: type};
                Object.keys(values || {}).forEach((key) => { action[key] = values[key]; });
                window.__SPARKE_LEGACY_ACTION__ = action;
            }
            function validPhone(value) {
                return /^(13[0-9]|14[01456879]|15[0-35-9]|16[2567]|17[0-8]|18[0-9]|19[0-35-9])\\d{8}$/.test(value);
            }

            showAccountMode('sms');
            modeSwitch.addEventListener('click', () => showMode(mode === 'qr' ? 'account' : 'qr'));
            smsTab.addEventListener('click', () => showAccountMode('sms'));
            passwordTab.addEventListener('click', () => showAccountMode('password'));
            sendSms.addEventListener('click', () => {
                const phone = document.getElementById('sparkeLegacySmsPhone').value.trim();
                if (!validPhone(phone)) {
                    setStatus('\u8bf7\u8f93\u5165\u6b63\u786e\u7684\u624b\u673a\u53f7', true);
                    return;
                }
                dispatchAction('send_sms', {phone: phone});
            });
            smsLogin.addEventListener('click', () => {
                const phone = document.getElementById('sparkeLegacySmsPhone').value.trim();
                const code = document.getElementById('sparkeLegacySmsCode').value.trim();
                if (!validPhone(phone)) {
                    setStatus('\u8bf7\u8f93\u5165\u6b63\u786e\u7684\u624b\u673a\u53f7', true);
                    return;
                }
                if (!code) {
                    setStatus('\u8bf7\u8f93\u5165\u9a8c\u8bc1\u7801', true);
                    return;
                }
                dispatchAction('login_sms', {phone: phone, code: code});
            });
            passwordLogin.addEventListener('click', () => {
                const account = document.getElementById('sparkeLegacyAccount').value.trim();
                const password = passwordInput.value;
                if (!account) {
                    setStatus('\u8bf7\u8f93\u5165\u8d26\u53f7', true);
                    return;
                }
                if (!password) {
                    setStatus('\u8bf7\u8f93\u5165\u5bc6\u7801', true);
                    return;
                }
                dispatchAction('login_password', {account: account, password: password});
            });
            document.getElementById('sparkeLegacySmsCode').addEventListener('keydown', (event) => {
                if (event.key === 'Enter') smsLogin.click();
            });
            passwordInput.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') passwordLogin.click();
            });
            document.getElementById('sparkeLegacyPasswordVisible').addEventListener('click', (event) => {
                const visible = passwordInput.type === 'text';
                passwordInput.type = visible ? 'password' : 'text';
                event.currentTarget.textContent = visible ? '\u25c9' : '\u25ce';
                event.currentTarget.title = visible ? '\u663e\u793a\u5bc6\u7801' : '\u9690\u85cf\u5bc6\u7801';
                event.currentTarget.setAttribute('aria-label', event.currentTarget.title);
            });
            window.__SPARKE_LEGACY_HANDLE_RESULT__ = (result) => {
                if (!result || String(result.id || '') !== pendingActionId) return;
                const type = pendingAction;
                pendingAction = '';
                pendingActionId = '';
                setBusy(type, false);
                if (result.ok && type === 'send_sms') {
                    startCountdown(result.countdown || 60);
                }
                setStatus(result.message || '', !result.ok);
            };
            const config = ${JSON.stringify(safe_config)};
            if (!config) {
                setStatus('\u4e8c\u7ef4\u7801\u83b7\u53d6\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u540e\u91cd\u8bd5', true);
                retry.hidden = false;
                return false;
            }
            try {
                localStorage.setItem('STATE', config.state);
                localStorage.setItem('sparkpc-terminalid', ${JSON.stringify(sparke_legacy_terminal_id)});
            } catch (error) {
                ;
            }
            function showError() {
                setStatus('\u4e8c\u7ef4\u7801\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u540e\u91cd\u8bd5', true);
                retry.hidden = false;
            }
            function showQr() {
                try {
                    document.getElementById('login_container').textContent = '';
                    new window.WxLogin({
                        self_redirect: true,
                        id: 'login_container',
                        appid: config.appId,
                        response_type: 'code',
                        scope: 'snsapi_login',
                        fast_login: '1',
                        redirect_uri: encodeURIComponent(config.authorizeUrl),
                        state: config.state,
                        style: '',
                        href: 'https://img.sparke.cn/images/english/qrcode.css',
                        stylelite: 0,
                    });
                    setStatus('', false);
                } catch (error) {
                    showError();
                }
            }
            if (typeof window.WxLogin === 'function') {
                showQr();
            } else {
                const script = document.createElement('script');
                script.src = 'https://res.wx.qq.com/connect/zh_CN/htmledition/js/wxLogin.js';
                script.onload = showQr;
                script.onerror = showError;
                document.head.appendChild(script);
            }
            return true;
        })();
    `, true).catch(() => false);
}

async function prepareSparkeLegacyLogin(win) {
    if (!isLegacySparkeRuntime() || sparke_legacy_qr_inflight || !isWindowAlive(win)) {
        return false;
    }
    let current_url;
    try {
        current_url = new URL(getSafeWindowUrl(win));
    } catch (error) {
        return false;
    }
    if (
        current_url.hostname !== 'www.sparke.cn'
        || !/^\/login\/?$/.test(current_url.pathname)
    ) {
        return false;
    }
    sparke_legacy_qr_inflight = true;
    try {
        const config = await requestSparkeLegacyQrConfig();
        return await renderSparkeLegacyLogin(win, config);
    } catch (error) {
        return await renderSparkeLegacyLogin(win, null);
    } finally {
        sparke_legacy_qr_inflight = false;
    }
}

function getSparkeLegacyApiMessage(response_body, fallback_message) {
    const message = response_body && (
        response_body.msg || response_body.message || response_body.errorMessage
    );
    const normalized = String(message || '').replace(/[\r\n\t]+/g, ' ').trim().slice(0, 120);
    return normalized || String(fallback_message || '\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5');
}

async function completeSparkeLegacyLogin(win, response_body, fallback_message) {
    const response_code = Number(response_body && response_body.code);
    if (response_code !== 200) {
        return {
            ok: false,
            message: getSparkeLegacyApiMessage(response_body, fallback_message),
        };
    }
    const gateway_payload = normalizeSparkeLoginPayload({
        tokenRaw: response_body && (response_body.data || response_body),
        terminalid: sparke_legacy_terminal_id,
    });
    const payload = await exchangeSparkePcLoginPayload(gateway_payload) || gateway_payload;
    const validated = await validateSparkeLoginPayload(payload);
    if (!validated || !isWindowAlive(win)) {
        return {ok: false, message: String(fallback_message || '\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5')};
    }
    const saved = saveLoginPayload(validated, {exit: false});
    if (saved === false) {
        return {ok: false, message: '\u767b\u5f55\u4fe1\u606f\u4fdd\u5b58\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5'};
    }
    sparke_legacy_sms_random_code = '';
    sparke_legacy_sms_phone = '';
    sparke_login_success = true;
    requestAppExit();
    return {ok: true, message: '\u767b\u5f55\u6210\u529f'};
}

async function requestSparkeLegacySmsCode(phone) {
    phone = String(phone || '').trim();
    if (!/^(13[0-9]|14[01456879]|15[0-35-9]|16[2567]|17[0-8]|18[0-9]|19[0-35-9])\d{8}$/.test(phone)) {
        return {ok: false, message: '\u8bf7\u8f93\u5165\u6b63\u786e\u7684\u624b\u673a\u53f7'};
    }
    sparke_legacy_terminal_id = sparke_legacy_terminal_id || createSparkeTerminalId();
    const pvalue = buildSparkeWebPvalue(sparke_legacy_terminal_id);
    const result = await requestJsonUrl(
        'GET',
        SPARKE_WEB_GATEWAY + '/spark-user/auth/validateCode',
        {
            phone,
            type: '3',
            pvalue: JSON.stringify(pvalue),
        },
        buildSparkeWebHeaders(pvalue),
    );
    const response_body = parseJsonResponseBody(result);
    const random_code = String(
        response_body && response_body.data && response_body.data.randomCodeStr || ''
    ).trim();
    if (Number(response_body && response_body.code) !== 200 || !random_code) {
        return {
            ok: false,
            message: getSparkeLegacyApiMessage(
                response_body,
                '\u9a8c\u8bc1\u7801\u53d1\u9001\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5',
            ),
        };
    }
    sparke_legacy_sms_random_code = random_code;
    sparke_legacy_sms_phone = phone;
    return {
        ok: true,
        message: '\u9a8c\u8bc1\u7801\u53d1\u9001\u6210\u529f\uff0c\u8bf7\u6ce8\u610f\u67e5\u6536',
        countdown: 60,
    };
}

async function loginSparkeLegacyAccount(win, action) {
    const action_type = String(action && action.type || '');
    const request_payload = {};
    if (action_type === 'login_sms') {
        const phone = String(action.phone || '').trim();
        const code = String(action.code || '').trim().slice(0, 12);
        action.code = '';
        if (!phone || !code) {
            return {ok: false, message: '\u8bf7\u8f93\u5165\u624b\u673a\u53f7\u548c\u9a8c\u8bc1\u7801'};
        }
        if (!sparke_legacy_sms_random_code || sparke_legacy_sms_phone !== phone) {
            return {ok: false, message: '\u8bf7\u5148\u91cd\u65b0\u83b7\u53d6\u9a8c\u8bc1\u7801'};
        }
        request_payload.grantType = 'captcha';
        request_payload.account = phone;
        request_payload.code = code;
        request_payload.randomCodeStr = sparke_legacy_sms_random_code;
    } else if (action_type === 'login_password') {
        const account = String(action.account || '').trim().slice(0, 100);
        const password = String(action.password || '').slice(0, 100);
        action.password = '';
        if (!account || !password) {
            return {ok: false, message: '\u8bf7\u8f93\u5165\u8d26\u53f7\u548c\u5bc6\u7801'};
        }
        request_payload.grantType = 'password';
        request_payload.account = account;
        request_payload.password = crypto.createHash('md5')
            .update(password, 'utf8')
            .digest('hex')
            .toLowerCase();
    } else {
        return {ok: false, message: '\u4e0d\u652f\u6301\u7684\u767b\u5f55\u65b9\u5f0f'};
    }
    sparke_legacy_terminal_id = sparke_legacy_terminal_id || createSparkeTerminalId();
    const pvalue = buildSparkeWebPvalue(sparke_legacy_terminal_id);
    const result = await requestJsonUrl(
        'POST',
        SPARKE_WEB_GATEWAY + '/spark-user/auth/token?'
            + new URLSearchParams({pvalue: JSON.stringify(pvalue)}).toString(),
        request_payload,
        buildSparkeWebHeaders(pvalue),
    );
    return completeSparkeLegacyLogin(
        win,
        parseJsonResponseBody(result),
        '\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u8d26\u53f7\u4fe1\u606f',
    );
}

function sendSparkeLegacyActionResult(win, result) {
    if (!isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    const safe_result = {
        id: String(result && result.id || ''),
        type: String(result && result.type || ''),
        ok: Boolean(result && result.ok),
        message: String(result && result.message || '').slice(0, 160),
        countdown: Number(result && result.countdown || 0),
    };
    return win.webContents.executeJavaScript(`
        (() => {
            if (typeof window.__SPARKE_LEGACY_HANDLE_RESULT__ !== 'function') return false;
            window.__SPARKE_LEGACY_HANDLE_RESULT__(${JSON.stringify(safe_result)});
            return true;
        })();
    `, true).catch(() => false);
}

async function handleSparkeLegacyAction(win, action) {
    const id = String(action && action.id || '');
    const type = String(action && action.type || '');
    let result;
    try {
        if (type === 'send_sms') {
            result = await requestSparkeLegacySmsCode(action.phone);
        } else if (type === 'login_sms' || type === 'login_password') {
            result = await loginSparkeLegacyAccount(win, action);
        } else {
            result = {ok: false, message: '\u4e0d\u652f\u6301\u7684\u767b\u5f55\u64cd\u4f5c'};
        }
    } catch (error) {
        result = {ok: false, message: '\u8bf7\u6c42\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5'};
    }
    return Object.assign({id, type}, result || {});
}

function pollSparkeLegacyAction(win) {
    if (
        !isLegacySparkeRuntime()
        || sparke_legacy_action_inflight
        || !isWindowAlive(win)
    ) {
        return Promise.resolve(false);
    }
    sparke_legacy_action_inflight = true;
    return win.webContents.executeJavaScript(`
        (() => {
            const action = window.__SPARKE_LEGACY_ACTION__ || null;
            window.__SPARKE_LEGACY_ACTION__ = null;
            return action;
        })();
    `, true).then(async (action) => {
        if (!action || typeof action !== 'object') {
            return false;
        }
        const result = await handleSparkeLegacyAction(win, action);
        await sendSparkeLegacyActionResult(win, result);
        return true;
    }).catch(() => false).finally(() => {
        sparke_legacy_action_inflight = false;
    });
}

function startSparkeLegacyActionPoll(win) {
    if (!isLegacySparkeRuntime() || !isWindowAlive(win)) {
        return false;
    }
    if (sparke_legacy_action_timer) {
        clearInterval(sparke_legacy_action_timer);
    }
    sparke_legacy_action_timer = setInterval(() => {
        pollSparkeLegacyAction(win);
    }, 300);
    return true;
}

async function exchangeSparkeLegacyLogin(win, callback_url) {
    let parsed;
    try {
        parsed = new URL(String(callback_url || ''));
    } catch (error) {
        return false;
    }
    if (parsed.hostname !== 'www.sparke.cn' || parsed.pathname !== '/loginSuccess') {
        return false;
    }
    const code = String(parsed.searchParams.get('code') || '').trim();
    const state = String(parsed.searchParams.get('state') || '').trim();
    if (!code || !state || state !== sparke_legacy_state) {
        setSparkeLegacyStatus(win, '二维码登录校验失败，请刷新后重试', true);
        return true;
    }
    if (sparke_legacy_exchange_inflight) {
        return true;
    }
    sparke_legacy_exchange_inflight = true;
    setSparkeLegacyStatus(win, '正在验证登录...', false);
    try {
        const pvalue = buildSparkeWebPvalue(sparke_legacy_terminal_id);
        const result = await requestJsonUrl(
            'POST',
            SPARKE_WEB_GATEWAY + '/spark-user/auth/token?'
                + new URLSearchParams({pvalue: JSON.stringify(pvalue)}).toString(),
            {
                grantType: 'social',
                code,
                state,
                source: 'wechat_open',
                alias: 'pc_new',
            },
            buildSparkeWebHeaders(pvalue),
        );
        const response_body = parseJsonResponseBody(result);
        const response_code = Number(response_body && response_body.code);
        if (response_code === 102) {
            setSparkeLegacyStatus(win, '该微信需先在星火英语官网绑定手机号', true);
            return true;
        }
        const completed = await completeSparkeLegacyLogin(
            win,
            response_body,
            '\u4e8c\u7ef4\u7801\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u540e\u91cd\u8bd5',
        );
        if (!completed.ok) {
            setSparkeLegacyStatus(win, completed.message, true);
        }
        return true;
    } catch (error) {
        setSparkeLegacyStatus(win, '二维码登录失败，请刷新后重试', true);
        return true;
    } finally {
        sparke_legacy_exchange_inflight = false;
    }
}

function installSparkeLegacyCallbackHandler(win, login_session) {
    if (!isLegacySparkeRuntime() || !login_session || !login_session.webRequest) {
        return;
    }
    login_session.webRequest.onBeforeRequest(
        {urls: ['*://www.sparke.cn/loginSuccess*']},
        (details, callback) => {
            callback({cancel: true});
            exchangeSparkeLegacyLogin(win, details && details.url);
        },
    );
}

// 星火英语 PC 站把会话保存在 localStorage。页面进程只负责读取最小
// 状态，主进程验证受保护接口后再写入 AppData，避免保存过期令牌。
function trySaveSparkeLoginResult(win) {
    if (login_name !== 'sparke' || sparke_save_inflight || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    sparke_save_inflight = true;
    return win.webContents.executeJavaScript(`
        (() => {
            function read(key) {
                try {
                    return localStorage.getItem(key) || sessionStorage.getItem(key) || '';
                } catch (error) {
                    return '';
                }
            }
            return {
                tokenRaw: read('sparkpc-token'),
                terminalid: read('sparkpc-terminalid'),
                browserId: read('browserId'),
            };
        })();
    `, true).then((result) => {
        const payload = normalizeSparkeLoginPayload(result);
        if (!payload.token) {
            sparke_save_inflight = false;
            return false;
        }
        if (
            payload.token === sparke_rejected_token
            && Date.now() - sparke_rejected_token_at < 5000
        ) {
            sparke_save_inflight = false;
            return false;
        }
        return exchangeSparkePcLoginPayload(payload).then((pc_payload) => (
            validateSparkeLoginPayload(pc_payload || payload)
        )).then((validated) => {
            if (!validated) {
                sparke_rejected_token = payload.token;
                sparke_rejected_token_at = Date.now();
                sparke_save_inflight = false;
                return false;
            }
            sparke_rejected_token = '';
            sparke_rejected_token_at = 0;
            if (!isWindowAlive(win)) {
                sparke_save_inflight = false;
                return false;
            }
            const saved = saveLoginPayload(validated, {exit: false});
            if (saved === false) {
                sparke_save_inflight = false;
                return false;
            }
            sparke_login_success = true;
            requestAppExit();
            return true;
        });
    }).catch(() => {
        sparke_save_inflight = false;
        return false;
    });
}

function centerSparkeLoginViewport(win) {
    if (login_name !== 'sparke' || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return win.webContents.executeJavaScript(`
        (() => {
            const nodes = [];
            const seen = new Set();
            function addNode(node) {
                if (!node || seen.has(node)) {
                    return;
                }
                seen.add(node);
                nodes.push(node);
            }
            addNode(document.scrollingElement);
            addNode(document.documentElement);
            addNode(document.body);
            Array.from(document.querySelectorAll('*')).forEach((node) => {
                if (
                    node
                    && typeof node.scrollWidth === 'number'
                    && typeof node.clientWidth === 'number'
                    && node.scrollWidth > node.clientWidth + 8
                ) {
                    addNode(node);
                }
            });

            let primary = null;
            nodes.forEach((node) => {
                const maxScroll = Math.max(0, (node.scrollWidth || 0) - (node.clientWidth || 0));
                if (maxScroll <= 8) {
                    return;
                }
                const target = Math.round(maxScroll / 2);
                try {
                    node.scrollLeft = target;
                } catch (error) {
                    ;
                }
                try {
                    if (typeof node.scrollTo === 'function') {
                        node.scrollTo({left: target, top: node.scrollTop || 0, behavior: 'auto'});
                    }
                } catch (error) {
                    ;
                }
                if (!primary || maxScroll > primary.maxScroll) {
                    primary = {
                        maxScroll,
                        target,
                        scrollLeft: node.scrollLeft || 0,
                    };
                }
            });

            const root = document.scrollingElement || document.documentElement || document.body;
            const documentWidth = Math.max(
                (document.documentElement && document.documentElement.scrollWidth) || 0,
                (document.body && document.body.scrollWidth) || 0,
            );
            const windowMaxScroll = Math.max(0, documentWidth - (window.innerWidth || 0));
            if (windowMaxScroll > 8) {
                const target = Math.round(windowMaxScroll / 2);
                const top = window.scrollY || (root && root.scrollTop) || 0;
                try {
                    window.scrollTo({left: target, top, behavior: 'auto'});
                } catch (error) {
                    window.scrollTo(target, top);
                }
                if (!primary || windowMaxScroll > primary.maxScroll) {
                    primary = {
                        maxScroll: windowMaxScroll,
                        target,
                        scrollLeft: window.scrollX || (root && root.scrollLeft) || 0,
                    };
                }
            }
            return primary || {maxScroll: 0, target: 0, scrollLeft: 0};
        })();
    `, true).catch(() => false);
}

const XIAOETECH_PC_TOKEN_CHECK_URL = 'https://study.xiaoe-tech.com/xe.pc_client.course/platform.token.check/1.0.0';
const XIAOETECH_PC_APP_ID = 'apposolbh821040';
const XIAOETECH_PC_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) xiaoe-tong-client/1.2.11 Chrome/112.0.5615.204 Electron/24.8.8 Safari/537.36';

async function validateXiaoetechPcToken(token) {
    token = String(token || '').trim();
    if (!token) {
        return false;
    }
    const result = await requestJsonUrl(
        'POST',
        XIAOETECH_PC_TOKEN_CHECK_URL,
        {platform: 'pc_client'},
        {
            'User-Agent': XIAOETECH_PC_USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'xiaoetongclient://entrance',
            'App-Token': token,
            'Cookie': 'p_token=' + token,
            'login_app': 'eapppc',
            'login_client': 'pc',
            'app_id': XIAOETECH_PC_APP_ID,
        },
    );
    const response_body = parseJsonResponseBody(result);
    return !!(response_body && response_body.code === 0);
}

const XIAOETECH_STORE_COOKIE_NAMES = ['ko_token', 'pc_user_key'];

function isXiaoetechStoreLoginName(value = login_name) {
    return String(value || '').trim().toLowerCase().startsWith('xiaoetech.');
}

function filterXiaoetechStoreCookies(cookies) {
    return (cookies || []).filter((cookie) => (
        cookie
        && cookie.value
        && XIAOETECH_STORE_COOKIE_NAMES.includes(String(cookie.name || '').toLowerCase())
    ));
}

function saveXiaoetechStoreLoginResult(login_session, cookies) {
    if (!isXiaoetechStoreLoginName()) {
        return Promise.resolve(false);
    }
    const saveCookies = (cookie_list) => {
        const cookie_value = buildCookieValue(filterXiaoetechStoreCookies(cookie_list));
        if (!cookie_value) {
            return false;
        }
        saveLoginCookieValue(cookie_value);
        return true;
    };
    const fallback_cookies = cookies || [];
    if (!login_session || !login_session.cookies) {
        return Promise.resolve(saveCookies(fallback_cookies));
    }
    return login_session.cookies.get({}).then((session_cookies) => (
        saveCookies(session_cookies) || saveCookies(fallback_cookies)
    )).catch(() => saveCookies(fallback_cookies));
}

async function validateYijiaykToken(token) {
    token = String(token || '').trim();
    if (!token) {
        return false;
    }
    const response = await requestJsonUrl('GET', YIJIAYK_VALIDATE_URL, null, {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json;charset=utf-8',
        'Cache-Control': 'no-cache',
        'Referer': YIJIAYK_LOGIN_URL,
        'Origin': 'https://h.yijiayk.com',
        'from_source': 'yjyk',
        'client_model': 'pc',
        'client_type': 'pc',
    });
    if (!response || Number(response.statusCode || 0) !== 200) {
        return false;
    }
    try {
        const info = JSON.parse(response.body || '{}');
        return Number(info.code || 0) === 200 && !!(info.data && info.data.userId);
    } catch (error) {
        return false;
    }
}

async function trySaveYijiaykToken(win) {
    if (login_name !== 'yijiayk' || yijiayk_save_inflight || !isWindowAlive(win)) {
        return false;
    }
    let token = '';
    try {
        token = await win.webContents.executeJavaScript(`
            (() => {
                function readToken(storage) {
                    if (!storage) {
                        return '';
                    }
                    const direct = storage.getItem('token') || '';
                    if (direct) {
                        return String(direct).trim();
                    }
                    for (let index = 0; index < storage.length; index += 1) {
                        const key = storage.key(index);
                        if (key && String(key).toLowerCase() === 'token') {
                            const value = storage.getItem(key);
                            if (value) {
                                return String(value).trim();
                            }
                        }
                    }
                    return '';
                }
                try {
                    return readToken(localStorage) || readToken(sessionStorage);
                } catch (error) {
                    return '';
                }
            })();
        `, true);
    } catch (error) {
        return false;
    }
    token = String(token || '').trim();
    if (!token) {
        return false;
    }
    yijiayk_save_inflight = true;
    const valid = await validateYijiaykToken(token).catch(() => false);
    if (!valid) {
        yijiayk_save_inflight = false;
        return false;
    }
    saveLoginCookieValue('token=' + token);
    return true;
}

function getNestedValueByNames(value, names, depth = 0) {
    if (!value || typeof value !== 'object' || depth > 5) {
        return '';
    }
    const target_names = (names || []).map((name) => String(name || '').toLowerCase());
    for (const key of Object.keys(value)) {
        if (target_names.includes(String(key || '').toLowerCase())) {
            const found = value[key];
            if (found !== undefined && found !== null && String(found) !== '') {
                return String(found);
            }
        }
    }
    for (const key of Object.keys(value)) {
        const found = getNestedValueByNames(value[key], names, depth + 1);
        if (found) {
            return found;
        }
    }
    return '';
}

function collectTodoenLoginMap(win, fallback_cookies = null) {
    const fallback_map = buildCookieMap(fallback_cookies || []);
    if (login_name !== 'todoen' || !isWindowAlive(win)) {
        return Promise.resolve(fallback_map);
    }
    return win.webContents.executeJavaScript(`
        (() => {
            function parseCookie(text) {
                const map = {};
                String(text || '').split(';').forEach((item) => {
                    item = String(item || '').trim();
                    const index = item.indexOf('=');
                    if (index <= 0) {
                        return;
                    }
                    map[item.slice(0, index).trim()] = item.slice(index + 1).trim();
                });
                return map;
            }
            function readStorage(key) {
                try {
                    return localStorage.getItem(key) || sessionStorage.getItem(key) || '';
                } catch (error) {
                    return '';
                }
            }
            function safeJson(value) {
                try {
                    return JSON.parse(value || '{}') || {};
                } catch (error) {
                    return {};
                }
            }
            const cookieMap = parseCookie(document.cookie || '');
            const user = safeJson(readStorage('user'));
            return {
                cookieMap,
                userid: cookieMap.userid || cookieMap.userId || user.id || user.userId || '',
                token: cookieMap.token || readStorage('token') || user.token || user.userToken || '',
                sid: cookieMap.sid || readStorage('gaotuSid') || user.sid || user.gaotuSid || '',
                secret: cookieMap.secret || user.secret || '',
                mobile: cookieMap.mobile || user.phone || user.mobile || '',
                name: cookieMap.name || user.nickname || '',
                psd: cookieMap.psd || ''
            };
        })();
    `, true).then((state) => {
        const cookie_map = Object.assign({}, fallback_map);
        if (state && state.cookieMap && typeof state.cookieMap === 'object') {
            Object.assign(cookie_map, state.cookieMap);
        }
        ['userid', 'token', 'sid', 'secret', 'mobile', 'name', 'psd'].forEach((name) => {
            const value = state && state[name];
            if (value !== undefined && value !== null && String(value) !== '') {
                cookie_map[name] = String(value);
            }
        });
        return cookie_map;
    }).catch(() => fallback_map);
}

function fetchTodoenGtSecret(cookie_map) {
    const userid = String((cookie_map && (cookie_map.userid || cookie_map.userId)) || '').trim();
    const token = String((cookie_map && (cookie_map.token || cookie_map.userToken || cookie_map.usertoken)) || '').trim();
    if (!userid || !token || (cookie_map.sid && cookie_map.secret)) {
        return Promise.resolve(cookie_map || {});
    }
    const cookie_value = buildCookieValueFromMap(Object.assign({}, cookie_map, {
        userid: userid,
        token: token,
    }));
    return requestUrlWithCookieValue(TODOEN_GT_SECRET_URL, {
        method: 'POST',
        body: JSON.stringify({
            userid: userid,
            usertoken: token,
            appname: '',
        }),
        cookieValue: cookie_value,
        referer: 'https://www.todoen.com/v2/learning/courses',
        origin: 'https://www.todoen.com',
        contentType: 'application/json;charset=UTF-8',
        headers: {
            'Accept': 'application/json, text/plain, */*',
        },
    }).then((result) => {
        if (!result || result.statusCode < 200 || result.statusCode >= 400) {
            return cookie_map || {};
        }
        let data = {};
        try {
            data = JSON.parse(String(result.body || '{}')) || {};
        } catch (error) {
            data = {};
        }
        const sid = getNestedValueByNames(data, ['sid', 'gaotuSid', 'gaotu_session_id']);
        const secret = getNestedValueByNames(data, ['secret', 'gaotuSecret']);
        if (sid) {
            cookie_map.sid = sid;
        }
        if (secret) {
            cookie_map.secret = secret;
        }
        return cookie_map || {};
    }).catch(() => cookie_map || {});
}

function trySaveTodoenLoginResult(win, fallback_cookies = null) {
    if (login_name !== 'todoen' || todoen_save_inflight || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return collectTodoenLoginMap(win, fallback_cookies).then((cookie_map) => {
        const userid = String((cookie_map.userid || cookie_map.userId || '')).trim();
        const token = String((cookie_map.token || cookie_map.userToken || cookie_map.usertoken || '')).trim();
        if (!userid || !token) {
            return false;
        }
        todoen_save_inflight = true;
        cookie_map.userid = userid;
        cookie_map.token = token;
        cookie_map.psd = cookie_map.psd || '1';
        return fetchTodoenGtSecret(cookie_map).then((full_map) => {
            const cookie_value = buildCookieValueFromMap(full_map);
            if (!cookie_value || cookie_value.indexOf('userid=') === -1 || cookie_value.indexOf('token=') === -1) {
                todoen_save_inflight = false;
                return false;
            }
            saveLoginCookieValue(cookie_value);
            return true;
        });
    }).catch(() => {
        todoen_save_inflight = false;
        return false;
    });
}

function isXiaoyuanyoukeCookie(cookie) {
    if (!cookie || !cookie.name || cookie.value === undefined || cookie.value === null || String(cookie.value) === '') {
        return false;
    }
    const name = String(cookie.name || '').trim();
    if (!XIAOYUANYOUKE_COOKIE_NAMES.includes(name)) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    return !domain || domain === 'yuanfudao.com' || domain.endsWith('.yuanfudao.com') || domain === 'cookie.prod';
}

function filterXiaoyuanyoukeCookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isXiaoyuanyoukeCookie(cookie)) {
            return;
        }
        const key = [
            String(cookie.name || ''),
            normalizeCookieDomain(cookie.domain || cookie.host_key || ''),
            String(cookie.path || '/'),
        ].join('|');
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        filtered.push(cookie);
    });
    return filtered;
}

function hasXiaoyuanyoukeLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterXiaoyuanyoukeCookies(cookies));
    return !!(
        cookie_map.sid
        || cookie_map.sess
        || cookie_map.userid
        || cookie_map.persistent
        || cookie_map.JSESSIONID
    );
}

function buildXiaoyuanyoukeValidateParams() {
    return Object.assign({}, XIAOYUANYOUKE_COMMON_PARAMS, {
        startCursor: '0',
        limit: '1',
        time: String(Date.now()),
    });
}

async function validateXiaoyuanyoukeCookieValue(cookie_value) {
    cookie_value = String(cookie_value || '').trim();
    if (!cookie_value) {
        return false;
    }
    const response = await requestJsonUrl(
        'GET',
        XIAOYUANYOUKE_PRODUCT_LIST_URL,
        buildXiaoyuanyoukeValidateParams(),
        {
            'User-Agent': XIAOYUANYOUKE_USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'identity',
            'Referer': XIAOYUANYOUKE_HOME_URL,
            'Cookie': cookie_value,
        }
    );
    const response_body = parseJsonResponseBody(response);
    return !!(
        response
        && response.statusCode >= 200
        && response.statusCode < 300
        && response_body
        && typeof response_body === 'object'
        && Array.isArray(response_body.list)
    );
}

async function trySaveXiaoyuanyoukeCookies(cookies) {
    if (login_name !== 'xiaoyuanyouke' || xiaoyuanyouke_save_inflight) {
        return false;
    }
    const filtered_cookies = filterXiaoyuanyoukeCookies(cookies || []);
    if (!hasXiaoyuanyoukeLoginCookies(filtered_cookies)) {
        return false;
    }
    const cookie_value = buildCookieValue(filtered_cookies);
    if (!cookie_value) {
        return false;
    }
    xiaoyuanyouke_save_inflight = true;
    const valid = await validateXiaoyuanyoukeCookieValue(cookie_value).catch(() => false);
    if (!valid) {
        xiaoyuanyouke_save_inflight = false;
        return false;
    }
    saveLoginCookieValue(cookie_value);
    return true;
}

async function trySaveXiaoyuanyoukeLoginResult(win, fallback_cookies = null) {
    if (login_name !== 'xiaoyuanyouke' || xiaoyuanyouke_save_inflight || !isWindowAlive(win)) {
        return false;
    }
    let result = null;
    try {
        result = await win.webContents.executeJavaScript('window.__XIAOYUANYOUKE_LOGIN_RESULT__', true);
    } catch (error) {
        result = null;
    }
    if (result && result.success && result.cookieValue) {
        const cookie_value = String(result.cookieValue || '').trim();
        if (!cookie_value) {
            return false;
        }
        xiaoyuanyouke_save_inflight = true;
        const valid = await validateXiaoyuanyoukeCookieValue(cookie_value).catch(() => false);
        if (!valid) {
            xiaoyuanyouke_save_inflight = false;
            return false;
        }
        saveLoginCookieValue(cookie_value);
        return true;
    }
    if (fallback_cookies) {
        return trySaveXiaoyuanyoukeCookies(fallback_cookies);
    }
    return false;
}

function saveYukebangLoginResult(win) {
    if (login_name !== 'yukebang' || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return win.webContents.executeJavaScript(`
        (() => {
            if (location.origin !== 'https://study.yukebang.com') return '';
            function looksLikeToken(value) {
                value = String(value || '').trim().replace(/^['"]|['"]$/g, '');
                if (!value || value.length > 8192) return '';
                if (/^[A-Za-z0-9._~+/=-]+:[A-Za-z0-9._~+/=-]+$/.test(value)) return value;
                if (!/^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$/.test(value)) return '';
                try {
                    const parts = value.split('.');
                    const header = JSON.parse(atob(parts[0].replace(/-/g, '+').replace(/_/g, '/')));
                    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
                    if (!header || typeof header.alg !== 'string' || !header.alg || header.alg.toLowerCase() === 'none') return '';
                    const expires = payload && Number(payload.exp);
                    return Number.isFinite(expires) && expires > Date.now() / 1000 ? value : '';
                } catch (error) {
                    return '';
                }
            }
            function extract(value, depth = 0) {
                if (depth > 8) return '';
                const direct = looksLikeToken(value);
                if (direct) {
                    return direct;
                }
                if (!value) {
                    return '';
                }
                if (typeof value === 'string') {
                    try {
                        return extract(JSON.parse(value), depth + 1);
                    } catch (error) {
                        return '';
                    }
                }
                if (Array.isArray(value)) {
                    for (const item of value) {
                        const token = extract(item, depth + 1);
                        if (token) {
                            return token;
                        }
                    }
                    return '';
                }
                if (typeof value === 'object') {
                    if (value.expire !== undefined && value.expire !== null && Number(value.expire) <= Date.now()) return '';
                    for (const key of ['access_token', 'accessToken', 'YKB_WEB_ACCESS_TOKEN', 'ykb_web_access_token', 'value', 'token', 'TOKEN', 'Token', 'x-token', 'YUKEBANG-WEB-TOKEN', 'yukebang-web-Token']) {
                        const token = extract(value[key], depth + 1);
                        if (token) {
                            return token;
                        }
                    }
                    for (const key of ['localStorage', 'sessionStorage', 'storage', 'data', 'payload']) {
                        const token = extract(value[key], depth + 1);
                        if (token) {
                            return token;
                        }
                    }
                }
                return '';
            }
            function readStore(name) {
                try {
                    return readStorage(window[name]);
                } catch (error) {
                    return '';
                }
            }
            function readStorage(storage) {
                if (!storage) {
                    return '';
                }
                const keys = [
                    'YKB_WEB_ACCESS_TOKEN',
                    'ykb_web_access_token',
                    'YUKEBANG-WEB-TOKEN',
                    'yukebang-web-Token',
                    'yukebang-web-token',
                    'YKB-WEB-TOKEN',
                    'YKB_TOKEN',
                    'x-token',
                    'token',
                ];
                for (const key of keys) {
                    const token = extract(storage.getItem(key));
                    if (token) {
                        return token;
                    }
                }
                for (let i = 0; i < storage.length; i++) {
                    const key = storage.key(i);
                    const lower = String(key || '').toLowerCase();
                    if (lower.includes('refresh') || lower.includes('expires')) continue;
                    if (lower.includes('yukebang') || lower.includes('ykb') || lower === 'token') {
                        const token = extract(storage.getItem(key));
                        if (token) {
                            return token;
                        }
                    }
                }
                return '';
            }
            return readStore('localStorage') || readStore('sessionStorage') || '';
        })();
    `, true).then((token) => {
        token = String(token || '').trim();
        if (!token || !isWindowAlive(win)) {
            return false;
        }
        return saveLoginCookieValue('YUKEBANG-WEB-TOKEN=' + encodeURIComponent(token)) === true;
    }).catch(() => false);
}

function isShanganLoginName(value = login_name) {
    value = String(value || '').trim().toLowerCase();
    return value === 'shangan' || value.startsWith('shangan.');
}

function isShanganTenantHost(host) {
    host = String(host || '').toLowerCase().replace(/^\.+|\.+$/g, '');
    if (['7nstatic.91yoke.com', 'imgres.91yoke.com', 'static.91yoke.com', 'yapi.91yoke.com'].includes(host)) {
        return false;
    }
    return host === '91yoke.com' || host.endsWith('.91yoke.com');
}

function getShanganTargetHost() {
    const candidates = [String(extra_arg || '').trim()];
    if (String(login_name || '').startsWith('shangan.')) {
        candidates.push('https://' + String(login_name).slice('shangan.'.length));
    }
    for (const candidate of candidates) {
        if (!candidate) {
            continue;
        }
        try {
            const host = new URL(candidate).hostname.toLowerCase().replace(/^\.+|\.+$/g, '');
            if (isShanganTenantHost(host)) {
                return host;
            }
        } catch (error) {
            ;
        }
    }
    return 'shangan.91yoke.com';
}

function getShanganTargetOrigin() {
    return 'https://' + getShanganTargetHost();
}

function getShanganLoginUrl() {
    const candidate = String(extra_arg || '').trim();
    if (candidate) {
        try {
            const parsed = new URL(candidate);
            const host = parsed.hostname.toLowerCase().replace(/^\.+|\.+$/g, '');
            if (isShanganTenantHost(host)) {
                return parsed.href;
            }
        } catch (error) {
            ;
        }
    }
    return getShanganTargetOrigin() + '/user/login';
}

function isShanganCookie(cookie) {
    if (!cookie || !cookie.name || !cookie.value) {
        return false;
    }
    const name = String(cookie.name);
    if (!['token', 'ag', 'uniqueVisitorId'].includes(name)) {
        return false;
    }
    const domain = String(cookie.domain || '').toLowerCase().replace(/^\.+|\.+$/g, '');
    if (!domain) {
        return true;
    }
    const target_host = getShanganTargetHost();
    return target_host === domain || target_host.endsWith('.' + domain);
}

function buildShanganCookieValue(cookies) {
    return buildCookieValue((cookies || []).filter(isShanganCookie));
}

function extractShanganToken(value) {
    value = value === undefined || value === null ? '' : String(value).trim();
    value = value.replace(/^['"]|['"]$/g, '');
    return value || '';
}

function hasShanganLoginCookieValue(value) {
    value = String(value || '');
    return /(?:^|;\s*)token=/.test(value) && /(?:^|;\s*)ag=/.test(value);
}

function saveShanganLoginResult(win, cookies) {
    if (!isShanganLoginName()) {
        return Promise.resolve(false);
    }
    const cookie_value = buildShanganCookieValue(cookies);
    if (hasShanganLoginCookieValue(cookie_value)) {
        saveLoginCookieValue(cookie_value);
        return Promise.resolve(true);
    }
    if (!isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return win.webContents.session.cookies.get({url: getShanganTargetOrigin()}).then((session_cookies) => {
        const session_cookie_value = buildShanganCookieValue(session_cookies);
        if (hasShanganLoginCookieValue(session_cookie_value)) {
            saveLoginCookieValue(session_cookie_value);
            return true;
        }
        return win.webContents.executeJavaScript(`
            (() => {
                function pick(storage) {
                    if (!storage) {
                        return '';
                    }
                    for (const key of ['token', 'Authorization', 'authorization']) {
                        const value = storage.getItem(key);
                        if (value) {
                            return value;
                        }
                    }
                    for (let i = 0; i < storage.length; i++) {
                        const key = storage.key(i);
                        if (String(key || '').toLowerCase().indexOf('token') !== -1) {
                            const value = storage.getItem(key);
                            if (value) {
                                return value;
                            }
                        }
                    }
                    return '';
                }
                return pick(window.localStorage) || pick(window.sessionStorage) || '';
            })();
        `, true).then((token) => {
            token = extractShanganToken(token);
            if (!token) {
                return false;
            }
            const result = [session_cookie_value, 'token=' + token]
                .filter((item) => !!item)
                .join('; ');
            if (!hasShanganLoginCookieValue(result)) {
                return false;
            }
            saveLoginCookieValue(result);
            return true;
        });
    }).catch(() => false);
}

function saveLizhiweikeLoginResult(win) {
    if (login_name !== 'lizhiweike' || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return win.webContents.executeJavaScript(`
        (function () {
            function readStorage(storage) {
                if (!storage) {
                    return null;
                }
                var miniprogramInfo = storage.getItem('wk_miniprogram_pclogin_info');
                if (miniprogramInfo) {
                    try {
                        var parsed = JSON.parse(miniprogramInfo);
                        if (parsed && parsed.authorized && parsed.token) {
                            return {
                                type: 'miniprogram',
                                value: 'login_type=miniprogram;wk_miniprogram_pclogin_info=' + encodeURIComponent(JSON.stringify(parsed))
                            };
                        }
                    } catch (error) {
                        ;
                    }
                }
                var id = storage.getItem('Session/id');
                var idToken = storage.getItem('Session/id_token');
                var token = storage.getItem('Session/token');
                if (id && idToken && token) {
                    return {
                        type: 'web',
                        value: 'login_type=web;id=' + encodeURIComponent(id) + ';id_token=' + encodeURIComponent(idToken) + ';token=' + encodeURIComponent(token)
                    };
                }
                return null;
            }
            var result = readStorage(localStorage) || readStorage(sessionStorage);
            return result || {
                type: '',
                value: '',
                href: window.location.href
            };
        })();
    `).then((result) => {
        if (result && result.value) {
            saveLoginCookieValue(result.value);
            return true;
        }
        return false;
    }).catch(() => false);
}

function injectLizhiweikeLoginSwitcher(win) {
    if (login_name !== 'lizhiweike' || !isWindowAlive(win)) {
        return;
    }
    win.webContents.executeJavaScript(`
        (function () {
            if (window.__lel_lizhiweike_switcher_installed__) {
                return;
            }
            window.__lel_lizhiweike_switcher_installed__ = true;
            var webUrl = ${JSON.stringify(LIZHIWEIKE_WEB_LOGIN_URL)};
            var miniUrl = ${JSON.stringify(LIZHIWEIKE_MINIPROGRAM_LOGIN_URL)};
            var switcherHeight = 100;
            var switcherGap = 16;
            function activeMode() {
                var host = location.hostname || '';
                if (host.indexOf('web.lizhiweike.com') >= 0) {
                    return 'mini';
                }
                return 'web';
            }
            function setActive(container) {
                var mode = activeMode();
                Array.prototype.slice.call(container.querySelectorAll('button')).forEach(function (button) {
                    var active = button.getAttribute('data-mode') === mode;
                    var label = button.getAttribute('data-label') || button.textContent.replace('当前：', '');
                    button.textContent = label;
                    button.style.background = active ? '#ff7a1a' : '#ffffff';
                    button.style.color = active ? '#ffffff' : '#0f172a';
                    button.style.borderColor = active ? '#ff7a1a' : '#94a3b8';
                    button.style.boxShadow = active ? '0 8px 18px rgba(255,122,26,.32)' : 'none';
                    button.style.transform = active ? 'translateY(-1px)' : 'none';
                });
            }
            function makeButton(text, mode, url) {
                var button = document.createElement('button');
                button.type = 'button';
                button.setAttribute('data-mode', mode);
                button.setAttribute('data-label', text);
                button.textContent = text;
                button.style.cssText = 'height:42px;min-width:132px;padding:0 18px;border:2px solid #94a3b8;background:#fff;color:#0f172a;font-size:16px;font-weight:700;line-height:38px;cursor:pointer;transition:background .16s,color .16s,border-color .16s,box-shadow .16s,transform .16s;';
                button.onclick = function () {
                    if (location.href !== url) {
                        location.href = url;
                    }
                };
                return button;
            }
            function mount() {
                var old = document.getElementById('lel-lizhiweike-login-switcher');
                if (old) {
                    setActive(old);
                    return;
                }
                var container = document.createElement('div');
                container.id = 'lel-lizhiweike-login-switcher';
                container.style.cssText = 'position:fixed;left:0;right:0;top:0;height:' + switcherHeight + 'px;z-index:2147483647;background:linear-gradient(90deg,#0f172a,#263447);box-shadow:0 4px 18px rgba(15,23,42,.28);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:' + switcherGap + 'px;box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;';
                var tip = document.createElement('div');
                tip.textContent = '注意登录入口不要选错了！！！';
                tip.style.cssText = 'color:#ff2d2d;font-size:13px;font-weight:800;line-height:16px;text-align:center;width:100%;';
                var buttonRow = document.createElement('div');
                buttonRow.style.cssText = 'display:flex;align-items:center;justify-content:center;gap:12px;width:100%;';
                var webBtn = makeButton('网页端入口', 'web', webUrl);
                var miniBtn = makeButton('小程序入口', 'mini', miniUrl);
                webBtn.style.borderRadius = '8px';
                miniBtn.style.borderRadius = '8px';
                buttonRow.appendChild(webBtn);
                buttonRow.appendChild(miniBtn);
                container.appendChild(buttonRow);
                container.appendChild(tip);
                document.documentElement.appendChild(container);
                document.body.style.paddingTop = switcherHeight + 'px';
                setActive(container);
            }
            mount();
            setInterval(mount, 1000);
        })();
    `).catch(() => {});
}

function isSikieduCookie(cookie) {
    if (!cookie || !cookie.name || !cookie.value) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain);
    return domain === 'sikiedu.com' || domain.endsWith('.sikiedu.com');
}

function filterSikieduCookies(cookies) {
    return (cookies || []).filter((cookie) => isSikieduCookie(cookie));
}

function hasSikieduLoginCookies(cookies) {
    const cookie_map = buildCookieMap(filterSikieduCookies(cookies));
    return !!(cookie_map.PHPSESSID || cookie_map.REMEMBERME);
}

function looksLikeSikieduLoggedInPage(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const final_url = String(result.url || '').toLowerCase();
    const body = String(result.body || '');
    const body_lower = body.toLowerCase();
    if (/(?:^|\/)login(?:[/?#]|$)/i.test(final_url)) {
        return false;
    }
    if (/(?:<form[^>]+(?:login|signin)|name=["']password["'])/i.test(body)) {
        return false;
    }
    return !!(
        body_lower.indexOf('my-course-item') !== -1
        || body_lower.indexOf('/my/courses/learning') !== -1
        || body_lower.indexOf('/logout') !== -1
    );
}

function checkSikieduWindowLogin(win) {
    if (!isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return win.webContents.executeJavaScript(`
        (() => {
            if (!['sikiedu.com', 'www.sikiedu.com'].includes(String(location.hostname || '').toLowerCase())) {
                return false;
            }
            const href = String(location.href || '').toLowerCase();
            if (/(?:^|\\/)login(?:[/?#]|$)/i.test(href)) {
                return false;
            }
            const html = String((document.documentElement && document.documentElement.outerHTML) || '');
            const html_lower = html.toLowerCase();
            if (/<form[^>]+(?:login|signin)/i.test(html) || /name=["']password["']/i.test(html)) {
                return false;
            }
            return !!(
                document.querySelector('.my-course-item')
                || document.querySelector('a[href*="/logout"]')
                || html_lower.indexOf('/my/courses/learning') !== -1
                || html_lower.indexOf('my-course-item') !== -1
            );
        })();
    `, true).then((result) => !!result).catch(() => false);
}

function validateSikieduCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve({valid: false, cookieValue: cookie_value});
    }
    return fetchUrlWithMergedCookieValue(SIKIEDU_VALIDATE_URL, cookie_value, 0, {
        'Referer': 'https://www.sikiedu.com/',
        'Origin': 'https://www.sikiedu.com',
    })
        .then((result) => ({
            valid: looksLikeSikieduLoggedInPage(result),
            cookieValue: result && result.cookieValue || cookie_value,
        }))
        .catch(() => ({valid: false, cookieValue: cookie_value}));
}

function trySaveSikieduCookies(cookies, win = null) {
    if (login_name !== 'sikiedu' || sikiedu_save_inflight) {
        return;
    }
    const sikiedu_cookies = filterSikieduCookies(cookies);
    if (!hasSikieduLoginCookies(sikiedu_cookies)) {
        return;
    }
    const cookie_value = buildCookieValue(sikiedu_cookies);
    if (!cookie_value) {
        return;
    }
    sikiedu_save_inflight = true;
    checkSikieduWindowLogin(win).then((window_valid) => {
        if (window_valid) {
            saveLoginCookieValue(cookie_value);
            return;
        }
        return validateSikieduCookieValue(cookie_value).then((result) => {
            if (!result || !result.valid) {
                sikiedu_save_inflight = false;
                return;
            }
            saveLoginCookieValue(result.cookieValue || cookie_value);
        });
    }).catch(() => {
        sikiedu_save_inflight = false;
    });
}

function filterZhi10Cookies(cookies) {
    return (cookies || []).filter((cookie) => {
        const domain = normalizeCookieDomain(cookie.domain);
        return (domain === 'zhi10.com' || domain === 'www.zhi10.com')
            && ['PHPSESSID', 'REMEMBERME'].includes(cookie.name);
    });
}

function looksLikeZhi10LoggedInPage(result) {
    if (!result || result.statusCode !== 200) {
        return false;
    }
    try {
        const url = new URL(result.url);
        return url.protocol === 'https:' && url.hostname === 'www.zhi10.com'
            && url.pathname.startsWith('/my/')
            && /\bvar\s+loginUserId\s*=\s*["'][1-9]\d*["']/.test(String(result.body || ''));
    } catch (_) {
        return false;
    }
}

function trySaveZhi10Cookies(cookies) {
    if (login_name !== 'zhi10' || zhi10_save_inflight) {
        return Promise.resolve(false);
    }
    const scoped = filterZhi10Cookies(cookies);
    const cookie_value = buildCookieValue(scoped);
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    zhi10_save_inflight = true;
    return fetchUrlWithMergedCookieValue(ZHI10_VALIDATE_URL, cookie_value, 0, {
        Referer: 'https://www.zhi10.com/',
    }).then((result) => {
        if (!looksLikeZhi10LoggedInPage(result)) {
            zhi10_save_inflight = false;
            return false;
        }
        const saved = saveLoginCookieValue(result.cookieValue || cookie_value) === true;
        if (!saved) {
            zhi10_save_inflight = false;
        }
        return saved;
    }).catch(() => {
        zhi10_save_inflight = false;
        return false;
    });
}

function validateUnipusCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithMergedCookieValue(UNIPUS_VALIDATE_URL, cookie_value, 0, {
        'Referer': 'https://moocs.unipus.cn/',
        'Origin': 'https://moocs.unipus.cn',
    })
        .then((result) => ({
            valid: looksLikeUnipusLoggedInPage(result),
            cookieValue: result && result.cookieValue || cookie_value,
        }))
        .catch(() => ({ valid: false, cookieValue: cookie_value }));
}

function validateCnmoocCookieValue(cookie_value) {
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return fetchUrlWithMergedCookieValue(CNMOOC_VALIDATE_URL, cookie_value, 0, {
        'Referer': 'https://cnmooc.sjtu.cn/',
        'Origin': 'https://cnmooc.sjtu.cn',
    })
        .then((result) => ({
            valid: looksLikeCnmoocLoggedInPage(result),
            cookieValue: result && result.cookieValue || cookie_value,
        }))
        .catch(() => ({ valid: false, cookieValue: cookie_value }));
}

function trySaveUnipusCookies(cookies) {
    if (unipus_save_inflight) {
        return;
    }
    const unipus_cookies = filterUnipusCookies(cookies);
    if (!hasUnipusLoginCookies(unipus_cookies)) {
        return;
    }
    const cookie_value = buildCookieValue(unipus_cookies);
    if (!cookie_value) {
        return;
    }
    unipus_save_inflight = true;
    validateUnipusCookieValue(cookie_value).then((result) => {
        const valid = !!(result && result.valid);
        if (!valid) {
            unipus_save_inflight = false;
            return;
        }
        saveLoginCookieValue(result.cookieValue || cookie_value);
    }).catch(() => {
        unipus_save_inflight = false;
    });
}

function trySaveSmarteduCookies(cookies) {
    if (smartedu_save_inflight) {
        return true;
    }
    const smartedu_cookies = filterSmarteduCookies(cookies);
    if (!hasSmarteduLoginCookies(smartedu_cookies)) {
        return false;
    }
    const cookie_value = buildCookieValue(smartedu_cookies);
    if (!cookie_value) {
        return false;
    }
    smartedu_save_inflight = true;
    saveLoginCookieValue(cookie_value);
    return true;
}

function encodeSmarteduTokenPayload(token) {
    if (!token || typeof token !== 'object') {
        return '';
    }
    const access_token = String(token.access_token || token.accessToken || '').trim();
    const mac_key = String(token.mac_key || token.macKey || '').trim();
    if (!access_token || !mac_key) {
        return '';
    }
    const payload = Object.assign({}, token, {
        access_token: access_token,
        mac_key: mac_key,
    });
    return Buffer.from(JSON.stringify(payload), 'utf8').toString('base64').replace(/=+$/g, '');
}

function trySaveSmarteduTokenFromPage(win) {
    if (smartedu_save_inflight || !isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    const current_url = getSafeWindowUrl(win).toLowerCase();
    if (current_url.indexOf('basic.smartedu.cn') === -1 && current_url.indexOf('ykt.eduyun.cn') === -1) {
        return Promise.resolve(false);
    }
    return win.webContents.executeJavaScript(`
        (async () => {
            function safeJson(value) {
                if (!value || typeof value !== 'string') {
                    return null;
                }
                try {
                    return JSON.parse(value);
                } catch (error) {
                    return null;
                }
            }
            function normalizeToken(value) {
                if (!value) {
                    return null;
                }
                if (typeof value === 'string') {
                    value = safeJson(value) || value;
                }
                if (value && typeof value === 'object' && value.value) {
                    value = value.value;
                }
                if (typeof value === 'string') {
                    value = safeJson(value) || value;
                }
                if (value && typeof value === 'object' && value.accessToken && !value.access_token) {
                    value.access_token = value.accessToken;
                }
                if (value && typeof value === 'object' && value.macKey && !value.mac_key) {
                    value.mac_key = value.macKey;
                }
                return value && value.access_token && value.mac_key ? value : null;
            }
            try {
                if (window.uc && typeof window.uc.getTokenAsync === 'function') {
                    const token = normalizeToken(await window.uc.getTokenAsync());
                    if (token) {
                        return token;
                    }
                    if (typeof window.uc.isLogin === 'function') {
                        try {
                            await window.uc.isLogin();
                        } catch (error) {
                            ;
                        }
                        const refreshedToken = normalizeToken(await window.uc.getTokenAsync());
                        if (refreshedToken) {
                            return refreshedToken;
                        }
                    }
                }
            } catch (error) {
                ;
            }
            const stores = [window.localStorage, window.sessionStorage].filter(Boolean);
            for (const store of stores) {
                for (let i = 0; i < store.length; i++) {
                    const key = store.key(i);
                    const token = normalizeToken(store.getItem(key));
                    if (token) {
                        return token;
                    }
                }
            }
            return null;
        })();
    `, true).then((token) => {
        const token_value = encodeSmarteduTokenPayload(token);
        if (!token_value) {
            return false;
        }
        smartedu_save_inflight = true;
        saveLoginCookieValue('UC_TOKEN=' + token_value);
        return true;
    }).catch(() => false);
}

function bootstrapSmarteduToken(win, target_session, ticket_key = '') {
    if (!isWindowAlive(win)) {
        return;
    }
    ticket_key = String(ticket_key || '');
    if (smartedu_token_bootstrap_started && (!ticket_key || ticket_key === smartedu_last_bootstrap_ticket)) {
        return;
    }
    if (ticket_key) {
        smartedu_last_bootstrap_ticket = ticket_key;
    }
    smartedu_token_bootstrap_started = true;
    win.loadURL(SMARTEDU_BACK_URL).catch(() => {
        smartedu_token_bootstrap_started = false;
    });
    [0, 500, 1200, 2500, 5000, 8000].forEach((delay_ms) => {
        scheduleSmarteduCookieCheck(win, target_session, delay_ms);
    });
}

function checkCnmoocWindowLogin(win) {
    if (!isWindowAlive(win)) {
        return Promise.resolve(false);
    }
    return win.webContents.executeJavaScript(`
        (() => {
            const href = String(location.href || '').toLowerCase();
            if (href.indexOf('/home/login') !== -1) {
                return false;
            }
            const html = String((document.documentElement && document.documentElement.outerHTML) || '');
            const htmlLower = html.toLowerCase();
            if (
                document.querySelector('#userLoginPage')
                || htmlLower.indexOf('id="isguest" value="true"') !== -1
                || htmlLower.indexOf('$.g_login_coeus_user_id = "-1"') !== -1
            ) {
                return false;
            }
            return !!(
                document.querySelector('a[href*="/home/logout.mooc"]')
                || document.querySelector('a[href*="/portal/myCourseIndex/"]')
                || document.querySelector('.mycourse')
                || htmlLower.indexOf('id="isguest" value="false"') !== -1
                || /\\/home\\/logout\\.mooc/i.test(html)
                || /\\/portal\\/myCourseIndex\\//i.test(html)
            );
        })();
    `, true).then((result) => !!result).catch(() => false);
}

function trySaveCnmoocCookies(cookies, win = null) {
    if (cnmooc_save_inflight) {
        return;
    }
    const cnmooc_cookies = filterCnmoocCookies(cookies);
    if (!hasCnmoocLoginCookies(cnmooc_cookies)) {
        return;
    }
    const cookie_value = buildCookieValue(cnmooc_cookies);
    if (!cookie_value) {
        return;
    }
    cnmooc_save_inflight = true;
    checkCnmoocWindowLogin(win).then((window_valid) => {
        if (window_valid) {
            return getCurrentCnmoocCookieValue(win).then((current_cookie_value) => {
                current_cookie_value = current_cookie_value || cookie_value;
                return validateCnmoocCookieValue(current_cookie_value).then((result) => {
                    const valid = !!(result && result.valid);
                    if (!valid) {
                        cnmooc_save_inflight = false;
                        return;
                    }
                    saveLoginCookieValue(result.cookieValue || current_cookie_value);
                });
            });
        }
        return validateCnmoocCookieValue(cookie_value).then((result) => {
            const valid = !!(result && result.valid);
            if (!valid) {
                cnmooc_save_inflight = false;
                return;
            }
            saveLoginCookieValue(result.cookieValue || cookie_value);
        });
    }).catch(() => {
        cnmooc_save_inflight = false;
    });
}

function scheduleLoginCookiesCheck(target_session, cookie_query, callback, delay_ms = 0) {
    setTimeout(() => {
        if (!target_session) {
            return;
        }
        target_session.cookies.get(cookie_query || {}).then((cookies) => {
            callback(cookies || []);
        }).catch(() => {
            ;
        });
    }, Math.max(0, Number(delay_ms) || 0));
}

function scheduleSmarteduCookieCheck(win, target_session, delay_ms = 0) {
    scheduleLoginCookiesCheck(target_session, {}, (cookies) => {
        if (trySaveSmarteduCookies(cookies)) {
            return;
        }
        const ticket_key = getSmarteduBootstrapTicket(cookies);
        if ((!smartedu_login_ticket_seen && !ticket_key) || !isWindowAlive(win)) {
            return;
        }
        if (smartedu_token_bootstrap_started && (!ticket_key || ticket_key === smartedu_last_bootstrap_ticket)) {
            return;
        }
        bootstrapSmarteduToken(win, target_session, ticket_key);
    }, delay_ms);
}

function markSmarteduLoginProgress(url) {
    const current_url = String(url || '').toLowerCase();
    if (
        current_url.indexOf('/uias/ticketform') !== -1
        || current_url.indexOf('auth.smartedu.cn/uias/app/view') !== -1
        || current_url.indexOf('basic.smartedu.cn') !== -1
    ) {
        smartedu_login_ticket_seen = true;
    }
}

function scheduleUnipusCookieCheck(target_session, delay_ms = 0) {
    scheduleLoginCookiesCheck(target_session, {domain: ".unipus.cn"}, (cookies) => {
        trySaveUnipusCookies(cookies);
    }, delay_ms);
}

function scheduleSikieduCookieCheck(win, target_session, delay_ms = 0) {
    // Authentication cookies are host-only on www.sikiedu.com in some
    // sessions, so query the jar broadly and filter both host and parent
    // domains in filterSikieduCookies.
    scheduleLoginCookiesCheck(target_session, {}, (cookies) => {
        trySaveSikieduCookies(cookies, win);
    }, delay_ms);
}

function scheduleCnmoocCookieCheck(win, target_session, delay_ms = 0) {
    scheduleLoginCookiesCheck(target_session, {}, (cookies) => {
        trySaveCnmoocCookies(cookies, win);
    }, delay_ms);
}

function trySaveLexueyunAuth(win) {
    if (login_name !== 'lexueyun' || lexueyun_save_inflight || !win || win.isDestroyed()) {
        return;
    }
    win.webContents.executeJavaScript(`
        (() => {
            try {
                const direct = localStorage.getItem('lexueyun-pc-userAuth')
                    || sessionStorage.getItem('lexueyun-pc-userAuth')
                    || '';
                if (direct) {
                    return String(direct).trim();
                }
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    if (key && key.toLowerCase() === 'lexueyun-pc-userauth') {
                        const value = localStorage.getItem(key);
                        if (value) {
                            return String(value).trim();
                        }
                    }
                }
            } catch (error) {
                ;
            }
            return '';
        })();
    `).then((token) => {
        token = String(token || '').trim();
        if (!token) {
            return;
        }
        lexueyun_save_inflight = true;
        saveLoginCookieValue(token);
    }).catch(() => {
        ;
    });
}

function postFormUrlWithCookieValue(target_url, form_data, cookie_value, redirect_count = 0, extra_headers = null) {
    return new Promise((resolve) => {
        let settled = false;
        function finish(result) {
            if (!settled) {
                settled = true;
                resolve(result);
            }
        }
        try {
            const parsed = new URL(target_url);
            const payload = Object.keys(form_data || {}).map((name) => {
                const value = form_data[name] === undefined || form_data[name] === null
                    ? ''
                    : String(form_data[name]);
                return encodeURIComponent(name) + '=' + encodeURIComponent(value);
            }).join('&');
            const request_headers = Object.assign({
                'Cookie': cookie_value,
                'Referer': 'https://course.dongao.com/',
                'Origin': 'https://course.dongao.com',
                'User-Agent': DEFAULT_BROWSER_USER_AGENT,
                'Accept': 'application/json, text/plain, */*',
                'Accept-Encoding': 'identity',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Content-Length': Buffer.byteLength(payload),
                'X-Requested-With': 'XMLHttpRequest',
            }, extra_headers || {});
            const request = https.request({
                protocol: parsed.protocol,
                hostname: parsed.hostname,
                port: parsed.port || undefined,
                path: parsed.pathname + parsed.search,
                method: 'POST',
                headers: request_headers,
            }, (response) => {
                let body = '';
                response.setEncoding('utf8');
                response.on('data', (chunk) => {
                    if (body.length < 262144) {
                        body += chunk;
                    }
                });
                response.on('end', () => {
                    const location = String((response.headers || {}).location || '');
                    if (location && response.statusCode >= 300 && response.statusCode < 400 && redirect_count < 4) {
                        finish(postFormUrlWithCookieValue(new URL(location, target_url).toString(), form_data, cookie_value, redirect_count + 1, extra_headers));
                        return;
                    }
                    finish({
                        statusCode: Number(response.statusCode || 0),
                        url: target_url,
                        body: body,
                    });
                });
            });
            request.on('error', () => {
                finish(null);
            });
            request.setTimeout(12000, () => {
                request.destroy();
                finish(null);
            });
            request.write(payload);
            request.end();
        } catch (error) {
            finish(null);
        }
    });
}

function requestUrlWithCookieValue(target_url, options = {}) {
    return new Promise((resolve) => {
        let settled = false;
        function finish(result) {
            if (!settled) {
                settled = true;
                resolve(result);
            }
        }
        try {
            const parsed = new URL(target_url);
            const method = String(options.method || 'GET').toUpperCase();
            const body = options.body || '';
            const request_headers = Object.assign({
                'Cookie': options.cookieValue || '',
                'Referer': options.referer || 'https://course.dongao.com/progress',
                'Origin': options.origin || 'https://course.dongao.com',
                'User-Agent': options.userAgent || DEFAULT_BROWSER_USER_AGENT,
                'Accept': options.accept || 'application/json, text/plain, */*',
                'Accept-Encoding': 'identity',
                'X-Requested-With': 'XMLHttpRequest',
            }, options.headers || {});
            if (method !== 'GET') {
                request_headers['Content-Type'] = options.contentType || 'application/x-www-form-urlencoded; charset=UTF-8';
                request_headers['Content-Length'] = Buffer.byteLength(body);
            }
            const request = https.request({
                protocol: parsed.protocol,
                hostname: parsed.hostname,
                port: parsed.port || undefined,
                path: parsed.pathname + parsed.search,
                method: method,
                headers: request_headers,
            }, (response) => {
                let response_body = '';
                response.setEncoding('utf8');
                response.on('data', (chunk) => {
                    if (response_body.length < 262144) {
                        response_body += chunk;
                    }
                });
                response.on('end', () => {
                    finish({
                        statusCode: Number(response.statusCode || 0),
                        url: target_url,
                        location: String((response.headers || {}).location || ''),
                        body: response_body,
                    });
                });
            });
            request.on('error', () => {
                finish(null);
            });
            request.setTimeout(options.timeout || 12000, () => {
                request.destroy();
                finish(null);
            });
            if (method !== 'GET' && body) {
                request.write(body);
            }
            request.end();
        } catch (error) {
            finish(null);
        }
    });
}

function isXuexi1998Cookie(cookie) {
    if (!cookie || !XUEXI1998_COOKIE_NAMES.includes(String(cookie.name || '')) || !cookie.value) {
        return false;
    }
    const domain = normalizeCookieDomain(cookie.domain || cookie.host_key || '');
    return domain === '1998xuexi.com' || domain === 'www.1998xuexi.com';
}

function filterXuexi1998Cookies(cookies) {
    const filtered = [];
    const seen = new Set();
    (cookies || []).forEach((cookie) => {
        if (!isXuexi1998Cookie(cookie)) {
            return;
        }
        const name = String(cookie.name || '');
        if (seen.has(name)) {
            return;
        }
        seen.add(name);
        filtered.push(cookie);
    });
    return filtered;
}

function parseXuexi1998UserInfo(value) {
    let text = String(value || '').trim();
    for (let attempt = 0; attempt < 3 && text; attempt += 1) {
        try {
            const parsed = JSON.parse(text);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (error) {
            ;
        }
        try {
            const decoded = decodeURIComponent(text);
            if (decoded === text) {
                break;
            }
            text = decoded;
        } catch (error) {
            break;
        }
    }
    return null;
}

function getXuexi1998Identity(cookies) {
    const cookie_map = buildCookieMap(filterXuexi1998Cookies(cookies));
    const user_info = parseXuexi1998UserInfo(cookie_map.userInfo);
    const member_info = user_info && user_info.memberInfo;
    if (!member_info || typeof member_info !== 'object') {
        return null;
    }
    const identity = {
        memberId: String(member_info.memberId || '').trim(),
        phoneNum: String(member_info.phoneNum || '').trim(),
        Satoken: String(member_info.randomIdWeb || '').trim(),
    };
    return identity.memberId && identity.phoneNum && identity.Satoken ? identity : null;
}

function hasXuexi1998LoginCookies(cookies) {
    return !!getXuexi1998Identity(cookies);
}

function isXuexi1998CourseListResponse(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 300) {
        return false;
    }
    try {
        const payload = JSON.parse(String(result.body || '{}'));
        const success = String(payload.code || '') === '200'
            || payload.success === true
            || payload.isOk === true;
        const rows = payload.data !== undefined ? payload.data : payload.datas;
        return success && Array.isArray(rows);
    } catch (error) {
        return false;
    }
}

function validateXuexi1998Cookies(cookies) {
    const filtered_cookies = filterXuexi1998Cookies(cookies);
    const identity = getXuexi1998Identity(filtered_cookies);
    const cookie_value = buildCookieValue(filtered_cookies);
    if (!identity || !cookie_value) {
        return Promise.resolve(false);
    }
    return requestUrlWithCookieValue(XUEXI1998_COURSE_LIST_URL, {
        method: 'POST',
        body: JSON.stringify({
            orderType: 0,
            payType: [],
            courseType: [],
            learningStatus: [],
        }),
        cookieValue: cookie_value,
        referer: 'https://www.1998xuexi.com/learnCenter',
        origin: 'https://www.1998xuexi.com',
        contentType: 'application/json; charset=UTF-8',
        headers: {
            'memberId': identity.memberId,
            'phoneNum': identity.phoneNum,
            'Satoken': identity.Satoken,
            'Systype': 'stuApp',
            'device': 'web',
        },
    }).then((result) => isXuexi1998CourseListResponse(result)).catch(() => false);
}

function trySaveXuexi1998Cookies(cookies) {
    if (login_name !== 'xuexi1998' || xuexi1998_save_inflight || !hasXuexi1998LoginCookies(cookies)) {
        return false;
    }
    const filtered_cookies = filterXuexi1998Cookies(cookies);
    const cookie_value = buildCookieValue(filtered_cookies);
    if (!cookie_value) {
        return false;
    }
    xuexi1998_save_inflight = true;
    validateXuexi1998Cookies(filtered_cookies).then((valid) => {
        if (!valid) {
            xuexi1998_save_inflight = false;
            return;
        }
        saveLoginCookieValue(cookie_value);
    }).catch(() => {
        xuexi1998_save_inflight = false;
    });
    return true;
}

function hasMisonLoginCookies(cookies) {
    const required_names = ['PHPSESSID', 'ujqtlmlauth', 'ujqtlmluserid'];
    return required_names.every((name) => (
        (cookies || []).some((cookie) => cookie && cookie.name === name && cookie.value)
    ));
}

function isMisonAuthenticatedResponse(result) {
    if (!result || result.statusCode < 200 || result.statusCode >= 400) {
        return false;
    }
    const body = String(result.body || '');
    return (
        /class=\\?["']loggen-in/i.test(body)
        || /class=\\?["']toMyClass/i.test(body)
        || /\/myclass\/views\/myclass\.php/i.test(body)
    );
}

function validateMisonCookieValue(cookie_value) {
    cookie_value = String(cookie_value || '').trim();
    if (!cookie_value) {
        return Promise.resolve(false);
    }
    return requestUrlWithCookieValue(MISON_LOGIN_STATE_URL, {
        cookieValue: cookie_value,
        referer: MISON_LOGIN_REFERER,
        origin: 'https://www.mison.cn',
        userAgent: MISON_USER_AGENT,
        accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }).then((result) => isMisonAuthenticatedResponse(result)).catch(() => false);
}

function trySaveMisonCookies(cookies) {
    if (login_name !== 'mison' || mison_save_inflight || !hasMisonLoginCookies(cookies)) {
        return;
    }
    const cookie_value = buildCookieValue(cookies);
    if (!cookie_value) {
        return;
    }
    mison_save_inflight = true;
    validateMisonCookieValue(cookie_value).then((valid) => {
        if (!valid) {
            mison_save_inflight = false;
            return;
        }
        saveLoginCookieValue(cookie_value);
    }).catch(() => {
        mison_save_inflight = false;
    });
}

function saveLoginPayload(payload) {
    let options = arguments[1] || {};
    if (!payload) {
        return;
    }
    if (login_name == 'ledu') {
        payload = normalizeLeduPayload(payload);
        if (!Object.keys(payload).length) {
            return;
        }
    }
    let cookies_obj = readCookiesObject();
    let payload_login_name = login_name;
    if (isCkjrLoginName(login_name)) {
        const company_id = String(payload.companyId || '').trim().toLowerCase();
        if (company_id) {
            payload_login_name = 'ckjr.' + company_id;
        }
    }
    cookies_obj[payload_login_name] = login_name == 'ledu'
        ? buildLeduCookieValue(payload)
        : JSON.stringify(payload);
    try {
        writeCookiesObject(cookies_obj);
    } catch (error) {
        console.error('[login-mooc] write payload file failed:', cookies_file, error && error.stack || error);
        if (isCkjrLoginName(login_name)) {
            ckjr_save_inflight = false;
        }
        if (login_name == 'sparke') {
            sparke_save_inflight = false;
        }
        return false;
    }
    if (options.exit === false) {
        if (isCkjrLoginName(login_name)) {
            ckjr_save_inflight = false;
        }
        if (login_name == 'sparke') {
            sparke_save_inflight = false;
        }
        return true;
    }
    requestAppExit();
    return true;
}

function saveXinghuoLoginResult(result) {
    if (!result || !result.token || xinghuo_save_inflight) {
        return false;
    }
    xinghuo_save_inflight = true;
    const saved = saveLoginPayload({
        token: String(result.token || ''),
        student_id: String(result.student_id || ''),
        phone: String(result.phone || ''),
    }, {exit: false});
    if (!saved) {
        xinghuo_save_inflight = false;
        return false;
    }
    xinghuo_login_success = true;
    requestAppExit();
    return true;
}

function normalizeHuomiaoLoginResult(result) {
    if (!result || typeof result !== 'object' || !result.success) {
        return {};
    }
    const token = String(result.token || '').trim();
    const uid = String(result.uid || '').trim();
    const phone = String(result.phone || '').trim();
    const device_id = String(result.deviceId || '').trim();
    if (
        !token || token.length > 4096 || token.split('.').length !== 3
        || !uid || uid.length > 128
        || !/^1[3-9]\d{9}$/.test(phone)
        || !device_id || device_id.length > 128
    ) {
        return {};
    }
    return {
        token: token,
        uid: uid,
        phone: phone,
        deviceId: device_id,
    };
}

function saveHuomiaoLoginResult(result) {
    if (huomiao_save_inflight) {
        return false;
    }
    const payload = normalizeHuomiaoLoginResult(result);
    if (!Object.keys(payload).length) {
        return false;
    }
    huomiao_save_inflight = true;
    const saved = saveLoginPayload(payload, {exit: false});
    if (!saved) {
        huomiao_save_inflight = false;
        return false;
    }
    huomiao_login_success = true;
    requestAppExit();
    return true;
}

function scrubLexuepeiyouProfile(value, depth = 0) {
    if (depth > 8 || value === undefined || value === null) {
        return null;
    }
    if (Array.isArray(value)) {
        return value.map((item) => scrubLexuepeiyouProfile(item, depth + 1))
            .filter((item) => item !== null);
    }
    if (typeof value === 'object') {
        let normalized = {};
        Object.keys(value).forEach((key) => {
            if (/pass(?:word|wd)?|checkcode|smscode|captcha|verificationcode/i.test(key)) {
                return;
            }
            const item = scrubLexuepeiyouProfile(value[key], depth + 1);
            if (item !== null) {
                normalized[key] = item;
            }
        });
        return normalized;
    }
    if (['string', 'number', 'boolean'].includes(typeof value)) {
        return value;
    }
    return null;
}

function normalizeLexuepeiyouApiHost(value) {
    value = String(value || '').trim().replace(/\/+$/, '');
    if (!value) {
        return '';
    }
    try {
        const parsed = new URL(value);
        const hostname = String(parsed.hostname || '').toLowerCase();
        const allowed = hostname == 'lexuepy.com'
            || hostname.endsWith('.lexuepy.com')
            || hostname == 'qingbeikeji.com'
            || hostname.endsWith('.qingbeikeji.com');
        if (parsed.protocol != 'https:' || !allowed) {
            return '';
        }
        return parsed.protocol + '//' + parsed.host;
    } catch (error) {
        return '';
    }
}

function normalizeLexuepeiyouLoginResult(result) {
    if (!result || typeof result !== 'object' || !result.success) {
        return {};
    }
    const current = result.current && typeof result.current === 'object' && !Array.isArray(result.current)
        ? scrubLexuepeiyouProfile(result.current)
        : {};
    const student_list = Array.isArray(result.studentList)
        ? scrubLexuepeiyouProfile(result.studentList)
        : [];
    const payload = {
        token: String(result.token || '').trim(),
        userId: String(result.userId || (current && current.userId) || '').trim(),
        deviceId: String(result.deviceId || '').trim(),
        current: current || {},
        studentList: student_list || [],
        apiHost: normalizeLexuepeiyouApiHost(result.apiHost),
    };
    if (!payload.token || !payload.userId || !payload.deviceId || !payload.apiHost) {
        return {};
    }
    return payload;
}

function saveLexuepeiyouLoginResult(result) {
    if (lexuepeiyou_save_inflight) {
        return false;
    }
    const payload = normalizeLexuepeiyouLoginResult(result);
    if (!Object.keys(payload).length) {
        return false;
    }
    lexuepeiyou_save_inflight = true;
    const saved = saveLoginPayload(payload, {exit: false});
    if (!saved) {
        lexuepeiyou_save_inflight = false;
        return false;
    }
    lexuepeiyou_login_success = true;
    requestAppExit();
    return true;
}

function trySaveTmoocCookies(win, cookies) {
    if (tmooc_save_inflight || !win || win.isDestroyed()) {
        return;
    }
    const cookie_value = buildTmoocCookieValue(cookies);
    if (!cookie_value || cookie_value.indexOf('TMOOC-SESSION=') === -1) {
        return;
    }
    tmooc_save_inflight = true;
    win.webContents.executeJavaScript(`
        new Promise((resolve) => {
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', 'https://uc.tmooc.cn/userValidate/getUserInfo', true);
                xhr.withCredentials = true;
                xhr.onreadystatechange = function () {
                    if (xhr.readyState !== 4) {
                        return;
                    }
                    try {
                        resolve(JSON.parse(xhr.responseText || '{}'));
                    } catch (error) {
                        resolve(null);
                    }
                };
                xhr.onerror = function () {
                    resolve(null);
                };
                xhr.send(null);
            } catch (error) {
                resolve(null);
            }
        });
    `).then((login_info) => {
        if (!login_info || String(login_info.code) !== '1') {
            return;
        }
        saveLoginCookieValue(cookie_value);
    }).catch(() => {
        ;
    }).finally(() => {
        tmooc_save_inflight = false;
    });
}

function pushCkjrAuthRecord(details) {
    if (!details || !details.url) {
        return;
    }
    let headers = {};
    Object.keys(details.requestHeaders || {}).forEach((name) => {
        headers[name] = details.requestHeaders[name];
    });
    let lowered_headers = {};
    Object.keys(headers).forEach((name) => {
        lowered_headers[String(name || '').toLowerCase()] = String(headers[name] || '').trim();
    });
    const auth_token = normalizeCkjrToken(lowered_headers.authorization || '');
    const has_bearer_auth = !!(auth_token && /^bearer\s+/i.test(lowered_headers.authorization || ''));
    let authenticated = false;
    try {
        const parsed_url = new URL(String(details.url || ''));
        const host = String(parsed_url.hostname || '').toLowerCase();
        authenticated = has_bearer_auth && (
            details.url.indexOf('/api/') !== -1
            || host === 'kpapiop.ckjr001.com'
            || host === 'kpapiop.kw.ckjr.cn'
            || /^kpapi(?:op|1|-)/i.test(host)
            || /(?:^|\.)ckjr001\.com$/i.test(host)
            || /(?:^|\.)myckjr\.com$/i.test(host)
            || /(?:^|\.)ckjr\.cn$/i.test(host)
        );
    } catch (error) {
        authenticated = false;
    }
    if (!authenticated && details.url.indexOf('kpapiop.ckjr001.com/api/') === -1) {
        return;
    }
    ckjr_auth_records.push({
        url: details.url,
        method: details.method || 'GET',
        headers: headers,
        authenticated: authenticated,
        timestamp: Date.now(),
    });
    if (ckjr_auth_records.length > 50) {
        ckjr_auth_records = ckjr_auth_records.slice(-50);
    }
}

function decodeCkjrJwtPayload(token) {
    token = String(token || '').trim();
    if (!token) {
        return {};
    }
    if (/^bearer\s+/i.test(token)) {
        token = token.replace(/^bearer\s+/i, '').trim();
    }
    const parts = token.split('.');
    if (parts.length < 2) {
        return {};
    }
    try {
        const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
        const padded = payload + '='.repeat((4 - payload.length % 4) % 4);
        return JSON.parse(Buffer.from(padded, 'base64').toString('utf8') || '{}');
    } catch (error) {
        return {};
    }
}

function extractCkjrRecordAuthState(auth_records) {
    let state = {
        token: '',
        companyId: '',
        userId: '',
        origin: '',
        referer: '',
        storeId: '',
    };
    (auth_records || []).forEach((record) => {
        let headers = Object.assign({}, (record && record.headers) || {});
        Object.keys(headers).forEach((key) => {
            const lowered = String(key || '').toLowerCase();
            const value = String(headers[key] || '').trim();
            if (!value) {
                return;
            }
            if (!state.token && lowered === 'authorization' && /^bearer\s+/i.test(value)) {
                state.token = value.replace(/^bearer\s+/i, '').trim();
            } else if (!state.origin && lowered === 'origin') {
                state.origin = value;
            } else if (!state.referer && lowered === 'referer') {
                state.referer = value;
            } else if (!state.storeId && lowered === 'x-store-id') {
                state.storeId = value;
            } else if (lowered === 'x-dmp') {
                const company_match = value.match(/(?:^|&)c=([^&]+)/i);
                const user_match = value.match(/(?:^|&)u=([^&]+)/i);
                if (!state.companyId && company_match) {
                    state.companyId = decodeURIComponent(company_match[1] || '').trim();
                }
                if (!state.userId && user_match) {
                    state.userId = decodeURIComponent(user_match[1] || '').trim();
                }
            }
        });
    });
    if ((!state.companyId || !state.userId) && state.token) {
        const jwt_payload = decodeCkjrJwtPayload(state.token);
        if (!state.companyId) {
            state.companyId = String(jwt_payload.c || '').trim();
        }
        if (!state.userId) {
            state.userId = String(jwt_payload.u || '').trim();
        }
    }
    return state;
}

function isHuatuCookieName(name) {
    name = String(name || '');
    return HUATU_COOKIE_NAMES.includes(name)
        || name.indexOf('isHeadTeacher_') === 0
        || name.indexOf('isUserMember') === 0;
}

function parseCookieStringToMap(cookie_string) {
    let cookie_map = {};
    (cookie_string || '').split(';').forEach((item) => {
        item = String(item || '').trim();
        if (!item) {
            return;
        }
        const equal_index = item.indexOf('=');
        if (equal_index <= 0) {
            return;
        }
        const name = item.slice(0, equal_index).trim();
        const value = item.slice(equal_index + 1).trim();
        if (!name || !isHuatuCookieName(name) || !value) {
            return;
        }
        cookie_map[name] = value;
    });
    return cookie_map;
}

function buildHuatuCookieMapFromObjects(cookies) {
    let cookie_map = {};
    (cookies || []).forEach((cookie) => {
        if (!cookie || !isHuatuCookieName(cookie.name) || !cookie.value) {
            return;
        }
        cookie_map[cookie.name] = String(cookie.value);
    });
    return cookie_map;
}

function buildHuatuCookieValue(cookie_map) {
    let names = [];
    HUATU_COOKIE_NAMES.forEach((name) => {
        if ((cookie_map || {})[name]) {
            names.push(name);
        }
    });
    Object.keys(cookie_map || {}).sort().forEach((name) => {
        if (!isHuatuCookieName(name) || names.includes(name) || !cookie_map[name]) {
            return;
        }
        names.push(name);
    });
    return names.map((name) => name + '=' + cookie_map[name]).join(';');
}

function getHuatuToken(cookie_map) {
    cookie_map = cookie_map || {};
    return cookie_map.ht_token
        || cookie_map.ht_token_preview
        || cookie_map['Newuc-Token']
        || cookie_map.token
        || '';
}

function hasHuatuIdentity(cookie_map) {
    cookie_map = cookie_map || {};
    return !!(
        cookie_map.UserName
        || cookie_map.ht_uname
        || cookie_map.UserID
        || cookie_map.ht_id
        || cookie_map.userCode
        || cookie_map.userMobile
        || cookie_map.ucId
    );
}

function isHuatuBasicCookieMap(cookie_map) {
    return !!(getHuatuToken(cookie_map) && hasHuatuIdentity(cookie_map));
}
function trySaveHuatuCookies(cookies) {
    if (huatu_save_inflight) {
        return;
    }
    const cookie_map = buildHuatuCookieMapFromObjects(cookies);
    if (!isHuatuBasicCookieMap(cookie_map)) {
        return;
    }
    const cookie_value = buildHuatuCookieValue(cookie_map);
    if (!cookie_value) {
        return;
    }
    huatu_save_inflight = true;
    saveLoginCookieValue(cookie_value);
}

const WENDAO_LOGIN_URL = 'https://pc.wendao101.com/login';
const wendao_login_state = {inflight: false, lastAuth: '', lastAttemptAt: 0};

function buildWendaoLoginUrl(value) {
    // Older downloader versions still pass the retired WAP course page.
    try {
        const url = new URL(value);
        if (url.origin === 'https://pc.wendao101.com') return url.href;
    } catch (_) {}
    return WENDAO_LOGIN_URL;
}

function applyWendaoLoginLayout(win) {
    if (!isWindowAlive(win) || !/^https:\/\/pc\.wendao101\.com\//i.test(getSafeWindowUrl(win))) return;
    // The official rem-based card shrinks below its fixed-width form labels.
    return win.webContents.insertCSS(`
        .login { box-sizing:border-box; min-height:100vh; height:auto!important; padding:84px 24px 28px!important; justify-content:center!important; }
        .login_header { top:22px!important; left:24px!important; height:40px!important; }
        .login_header .textBox img { width:132px!important; height:40px!important; }
        .login .login-form { box-sizing:border-box; width:420px!important; max-width:100%; flex-shrink:0; padding:28px 0 24px!important; border-radius:8px!important; }
        .login .login-form-right-top, .login .login-form-right-top img { width:44px!important; height:44px!important; }
        .login .el-form-item { margin-bottom:24px; }
        .login .el-form-item__label, .login .el-form-item__content { font-size:14px!important; line-height:40px!important; }
        .login .el-form-item__error { font-size:12px!important; }
        .login .el-button--primary { font-size:16px!important; }
        .login .el-input, .login .el-input input { height:40px!important; font-size:14px!important; }
        .login .el-input input { padding:0 12px; border-width:1px!important; border-radius:4px!important; }
        .login .bind_code .el-input__inner { padding-right:112px!important; border:1px solid #e4e4e4; border-radius:4px; }
        .login .bind_code .bind_code_gain { top:10px!important; right:10px!important; height:20px; padding-left:10px; font-size:14px!important; line-height:20px!important; border-left:1px solid #d8d8d8; }
        .login .bind_code .login-icon { display:none; }
        .login .login_title { font-size:16px!important; margin-bottom:24px!important; }
        .login .login_title div { margin:0 16px!important; }
        .login .activeText:after { bottom:-8px; width:40px; height:3px; }
        .login .login_content { height:200px!important; }
        .login .login_content img { width:200px!important; height:200px!important; }
        .login .other-login { margin-top:20px!important; padding:0 24px!important; }
        .login .other-login-title { margin-bottom:16px!important; }
        .login .other-login-title .text { font-size:13px!important; margin:0 12px!important; }
        .login .other-login-title .line { width:40px!important; height:1px!important; }
        .login .login-icons { padding:0 12px!important; }
        .login .login-icons .icon-item img { width:30px!important; height:30px!important; margin-bottom:8px!important; }
        .login .login-icons .icon-item span { font-size:13px!important; }
        @media(max-width:480px) {
            .login { padding-left:12px!important; padding-right:12px!important; }
            .login .el-form-item__label { width:100%!important; text-align:left; }
            .login .el-form-item__content { margin-left:0!important; clear:both; }
        }
    `).catch(() => {});
}

async function trySaveWendaoLoginResult(win, cookies) {
    if (wendao_login_state.inflight || !isWindowAlive(win)
            || !/^https:\/\/pc\.wendao101\.com\//i.test(getSafeWindowUrl(win))) return false;
    wendao_login_state.inflight = true;
    try {
        const result = await win.webContents.executeJavaScript(`(() => {
            function read(key) {
                for (const storage of [localStorage, sessionStorage]) {
                    try {
                        const raw = storage.getItem(key);
                        if (!raw) continue;
                        try { return JSON.parse(raw); } catch (_) { return raw; }
                    } catch (_) {}
                }
                return '';
            }
            function scalar(value) {
                return typeof value === 'string' && !/^(null|undefined)$/i.test(value.trim()) ? value.trim() : '';
            }
            const user = read('userObj') || {};
            return {
                token: scalar(read('Admin-Token')) || scalar(read('token')),
                openId: scalar(user.openid) || scalar(user.openId) || scalar(read('openId')) || scalar(read('openid')),
            };
        })()`);
        if (!result || !isWindowAlive(win)) return false;
        const scoped = (cookies || []).filter(cookie => {
            const domain = String(cookie.domain || '').toLowerCase();
            return ['pc.wendao101.com', '.pc.wendao101.com', '.wendao101.com'].includes(domain)
                && (!cookie.expirationDate || cookie.expirationDate > Date.now() / 1000);
        });
        const adminCookie = scoped.find(cookie => cookie.name === 'Admin-Token' && cookie.value);
        const token = String(adminCookie && adminCookie.value || result.token || result.openId || '').trim();
        const openId = String(result.openId || token).trim();
        if (!token || !openId || /^(null|undefined)$/i.test(token)) return false;
        const authKey = JSON.stringify([token, openId]);
        if (wendao_login_state.lastAuth === authKey && Date.now() - wendao_login_state.lastAttemptAt < 5000) return false;
        wendao_login_state.lastAuth = authKey;
        wendao_login_state.lastAttemptAt = Date.now();
        const response = await requestJsonUrl('POST', 'https://pc.wendao101.com/prod-api/home_page/course/purchased', {
            openId, orderPlatform: 0, pageNum: 1, pageSize: 1, appNameType: 2,
        }, {
            'User-Agent': user_agent,
            'Origin': 'https://pc.wendao101.com',
            'Referer': 'https://pc.wendao101.com/',
            'Authorization': 'Bearer ' + token,
            'Cookie': buildCookieValue(scoped),
        });
        const body = parseJsonResponseBody(response);
        if (!response || response.statusCode !== 200 || !body || ![0, 200, '0', '200'].includes(body.code)
                || !body.data || typeof body.data !== 'object' || !isWindowAlive(win)
                || !/^https:\/\/pc\.wendao101\.com\//i.test(getSafeWindowUrl(win))) return false;
        return saveLoginPayload({token, openId});
    } catch (_) {
        return false;
    } finally {
        wendao_login_state.inflight = false;
    }
}

if (login_name == 'beichenlinxuan') {
    var login_url = extra_arg || 'https://edulxw.cn/login.html';
} else if (login_name == 'gongxuanwang') {
    var login_url = 'https://www.gongxuanwang.com/login';
} else if (login_name == 'renrenjiang') {
    var login_url = 'https://ke.renrenjiang.cn/#/login';
} else if (login_name == 'zlketang') {
    var login_url = 'https://www.zlketang.com/login.html';
} else if (login_name == 'yizhiknow') {
    var login_url = 'https://user.yizhiknow.com/course/list';
} else if (login_name == 'wendao') {
    var login_url = buildWendaoLoginUrl(extra_arg);
} else if (login_name == 'haiyangknow') {
    var login_url = 'https://user.haiyangknow.com/login';
} else if (login_name == 'zhidao') {
    var login_url = extra_arg || 'https://www.zhidaoxuexiao.com/';
} else if (login_name == 'wowtiku') {
    var login_url = extra_arg || 'https://www.wowtiku.com/';
} else if (login_name == 'baitong') {
    var login_url = extra_arg || 'https://learn.tibaitong.com/#/login';
} else if (login_name == 'yangcong') {
    var login_url = 'https://school.yangcongxueyuan.com/login';
} else if (login_name == 'gaodoudou') {
    var login_url = 'https://gdd.aixuexi.com/';
} else if (login_name == 'yikao88') {
    var login_url = 'https://wx.yikao88.com/login';
} else if (login_name == 'yiihuu') {
    var login_url = extra_arg || 'https://www.yiihuu.com/';
} else if (login_name == 'sieredu') {
    var login_url = 'https://www.sieredu.com/';
} else if (login_name == 'enetedu') {
    var login_url = extra_arg || 'https://www.enetedu.com/site/login';
} else if (login_name == 'sikiedu') {
    var login_url = SIKIEDU_LOGIN_URL;
} else if (login_name == 'unipus') {
    var login_url = UNIPUS_LOGIN_URL;
} else if (login_name == 'cnmooc') {
    var login_url = 'https://cnmooc.sjtu.cn/home/login.mooc';
} else if (login_name == 'chinesemooc') {
    var login_url = CHINESEMOOC_LOGIN_URL;
} else if (login_name == 'xueersi') {
    var login_url = 'https://login.xueersi.com/';
} else if (login_name == 'ledu') {
    var login_url = buildLeduLoginUrl();
} else if (login_name == 'huomiao') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'huomiao-login.html'));
} else if (login_name == 'lexuepeiyou') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'lexuepeiyou-login.html'));
} else if (login_name == 'lexueyun') {
    var login_url = LEXUEYUN_LOGIN_URL;
} else if (login_name == 'minshi') {
    var login_url = 'https://vip.minshiedu.com/#/login?redirect=/course/courseHome';
} else if (isCkjrLoginName(login_name)) {
    var login_url = extra_arg || 'https://www.ckjr001.com/';
} else if (login_name == 'huatu') {
    var login_url = 'https://v.huatu.com/';
} else if (login_name == 'houda') {
    var login_url = HOUDA_LOGIN_URL;
} else if (login_name == 'ahuyikao') {
    var login_url = 'https://www.ahuyikao.com/login/login.html';
} else if (login_name == 'med66') {
    var login_url = MED66_LOGIN_URL;
} else if (login_name == 'zhengbao') {
    var login_url = ZHENGBAO_LOGIN_URL;
} else if (login_name == 'canto') {
    var login_url = 'https://canto.kuaiji521.com/Account/Login';
} else if (login_name == 'jianshe99') {
    var login_url = JIANSHE99_LOGIN_URL;
} else if (login_name == 'dongao') {
    var login_url = DONGAO_LOGIN_URL;
} else if (login_name == 'yijiayk') {
    var login_url = YIJIAYK_LOGIN_URL;
} else if (login_name == '51cto') {
    var login_url = extra_arg || 'https://home.51cto.com/index/?reback=https%3A%2F%2Fedu.51cto.com%2Fcenter%2Fcourse%2Fuser%2Fget-study-course';
} else if (login_name == '51cto_saas') {
    var login_url = extra_arg || 'https://saas.51cto.com/?redirect=https%3A%2F%2Fsaas.51cto.com%2Flearner.html%23%2F#/login';
} else if (login_name == '51zxw') {
    var login_url = extra_arg || 'https://www.51zxw.net/login/?redirect_url=%252flogin%252fUserCenter%252fLearningRecord#!page=1';
} else if (login_name == 'speiyou') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'speiyou-login.html'));
} else if (login_name == 'xiaoyuanyouke') {
    var login_url = XIAOYUANYOUKE_LOGIN_URL;
} else if (login_name == 'houduweilai') {
    var login_url = 'https://s.houduweilai.com/login';
} else if (login_name == 'tmooc') {
    var login_url = 'https://www.tmooc.cn/';
} else if (login_name == 'yunduan') {
    var login_url = 'https://www.baijiayun.com/entry';
} else if (login_name == 'youzan' || login_name.startsWith('youzan.')) {
    var login_url = extra_arg || 'https://www.youzan.com/';
} else if (login_name == 'yikaobang') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'yikaobang-login.html'));
} else if (login_name == 'icourse163') {
    var login_url = 'https://www.icourse163.org/member/login.htm?returnUrl=aHR0cHM6Ly93d3cuaWNvdXJzZTE2My5vcmcvaW5kZXguaHRt';
} else if (login_name == 'study163') {
    var login_url = 'https://study.163.com/member/login.htm';
} else if (login_name == 'open163') {
    var login_url = 'https://vip.open.163.com/center/myOrder';
} else if (login_name == 'youdao') {
    var login_url = 'https://ke.youdao.com/login';
} else if (login_name == 'xuetangx') {
    var login_url = 'https://next.xuetangx.com';
} else if (login_name == 'xuetangx.gradsmartedu') {
    var login_url = extra_arg || 'https://www.gradsmartedu.cn';
} else if (login_name == 'imooc') {
    var login_url = 'https://imooc.com';
} else if (login_name == 'keqq') {
    var login_url = 'https://ke.qq.com';
} else if (login_name == 'course_selector') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'course-selector.html'));
} else if (login_name.includes('xiaoetech')) {
    if (login_name == 'xiaoetech') {
        var xiaoe_tech = true;
        login_url = xiaoetech_login_mode == 'web'
            ? 'https://study.xiaoe-tech.com/t_l/learnLogin#/wx'
            : 'https://study.xiaoe-tech.com/t_l/pcClientLogin';
        var xiaoetech_domain = '.xiaoe-tech.com';
    } else {
        var xiaoe_tech = false;
        const login_ary = login_name.split('.');
        if (login_ary.length == 2) {
            var is_xiaoe_pc = false;
            var app_id = login_ary[1];
            var xiaoetech_domain = null;
            var login_url = extra_arg || `https://${app_id}.h5.xiaoeknow.com/p/t/free/v1/basic-platform/h5_basic/login/auth?LoginCard=login_phone`;
        } else {
            var is_xiaoe_pc = true;
            var xiaoetech_domain = login_ary.slice(1).join('.');
            var login_url = 'https://'+xiaoetech_domain;
        }
    }
} else if (login_name.includes('baijiayunxiao')) {
    const login_ary = login_name.split('.');
    if (login_ary.length >= 2) {
        var bjyx_domain = login_ary.slice(1).join('.');
        var login_url = `https://${bjyx_domain}`;
    }
} else if (login_name == 'jinbangshidai') {
    var login_url = 'https://pc.vkbrother.com/#/login';
} else if (login_name == 'qlchat') {
    var login_url = 'https://m.qlchat.com/page/login?redirect_url=https%3A%2F%2Fm.qlchat.com%2Fwechat%2Fpage%2Fmine';
} else if (login_name == 'lizhiweike') {
    var login_url = LIZHIWEIKE_WEB_LOGIN_URL;
} else if (login_name == 'qianliao') {
    var login_url = 'https://m.qianliao.net';
} else if (login_name == 'htknow') {
    var login_url = 'https://learn.htknow.com/login';
} else if (login_name == 'icourses') {
    var login_url = 'https://www.icourses.cn';
} else if (login_name == 'iqihang') {
    var login_url = 'https://www.iqihang.com/ark/myCourse';
} else if (login_name == 'chaoxing') {
    var login_url = 'https://passport2.chaoxing.com/login';
} else if (login_name == 'bilibili') {
    var login_url = 'https://www.bilibili.com';
} else if (login_name == 'koolearn') {
    var login_url = 'https://login.koolearn.com/sso/toLogin.do';
} else if (login_name == 'roombox') {
    var login_url = 'https://uc.roombox.xdf.cn/user/authCenter?pure=1&auth=1&language=cn&organizationId=2000&from=https%3A%2F%2Fd.roombox.xdf.cn%2Fvodplayer%2F%3Fcid%3D493551909%26mainId%3D493551909%26orgId%3D2000';
} else if (login_name == "douyin") {
    var login_url = 'https://www.douyin.com';
} else if (login_name == "youku") {
    var login_url = 'https://youku.com';
} else if (login_name == 'vqq') {
    var login_url = 'https://v.qq.com';
} else if (login_name == 'meeting') {
    var login_url = 'https://meeting.tencent.com/login.html';
} else if (login_name == 'dingtalk') {
    var login_url = dingtalk_yunxuetang_login
        ? 'https://d.yunxuetang.cn/#/login'
        : 'https://login.dingtalk.com/oauth2/challenge.htm?redirect_uri=https%3A%2F%2Fshanji.dingtalk.com%2Fdingtalk_sso_call_back%3Fcontinue%3Dhttps%253A%252F%252Fshanji.dingtalk.com%252F&response_type=code&client_id=dingoafxpgcixoe61pqxoq&scope=openid';
} else if (login_name == 'feishu') {
    var login_url = 'https://www.feishu.cn/drive/me/';
} else if (login_name == 'zhihuishu') {
    var login_url = 'https://passport.zhihuishu.com/login?service=https://onlineservice-api.zhihuishu.com/gateway/f/v1/login/gologin';
    var second_login_url = 'https://studyservice-api.zhihuishu.com/login/gologin';
} else if (login_name == 'icve') {
    var login_url = 'https://sso.icve.com.cn/sso/auth?mode=simple&source=3&redirect=https%3A%2F%2Fwww.icve.com.cn';
} else if (login_name == 'smartedu') {
    var login_url = SMARTEDU_LOGIN_URL;
} else if (login_name == 'eoffcn') {
    var login_url = 'https://sso.eoffcn.com/user/login?ref=https%3A%2F%2Fxue.eoffcn.com%2Fweb%2F&ssoAppId=10003';
} else if (login_name == 'wangxiao') {
    var login_url = 'https://k.wangxiao.cn/user/';
} else if (login_name == 'educity') {
    var login_url = 'https://wangxiao.xisaiwang.com/ucenter2/login.html';
} else if (login_name == 'dxy') {
    var login_url = extra_arg || 'https://auth.dxy.cn/accounts/login';
} else if (login_name == 'wangxiao233') {
    var login_url = extra_arg || 'https://passport.233.com/login/?redirecturl=https%3A%2F%2Fwx.233.com%2Fcenter%2Fstudy%3Fdomain%3Daq%26type%3D0';
} else if (login_name == 'xuelang') {
    var login_url = 'https://open.douyin.com/platform/oauth/connect?client_key=aw1j5bqrsawzyldp&redirect_uri=https%3A%2F%2Fstudent-api.iyincaishijiao.com%2Fep%2Fh5%2Flogin%2F&scope=mobile%2Cuser_info&state=ep_h5'
} else if (login_name == 'gaotu') {
    var login_url = 'https://www.gaotu.cn/account/profile'
} else if (login_name == 'gaotu.tutu') {
    var login_url = 'https://gaotu100.com/account/profile'
} else if (login_name == 'gaotu.gaozhong') {
    var login_url = 'https://www.gtgz.cn/account/profile'
} else if (login_name == 'gaotu.suyang') {
    var login_url = 'https://www.naiyouxuexi.com/account/profile'
} else if (login_name == 'todoen') {
    var login_url = 'https://www.todoen.com/login.html'
} else if (login_name == 'orangevip') {
    var login_url = 'https://u.orangevip.com/pc/login'
} else if (login_name == 'gaodun') {
    var login_url = 'https://v.gaodun.com/login'
} else if (login_name == 'zhi10') {
    var login_url = ZHI10_LOGIN_URL;
} else if (login_name == 'pukewx') {
    var login_url = 'https://www.pukewx.com/home/user/login?back=%2Fhome%2Fuser%2Findex';
} else if (login_name == 'yuyou') {
    var login_url = 'https://omo.yuyoupx.com/#/login?redirect=%2Flesson%2Findex';
} else if (login_name == 'xuetian') {
    var login_url = 'https://www.xuetian.cn/user/login?redirect=%2Fuser%2Flearning-center%2Fcourse';
} else if (login_name == 'geekbang') {
    var login_url = 'https://account.geekbang.org/signin?redirect=https%3A%2F%2Ftime.geekbang.org%2Fdashboard%2Fcourse';
} else if (login_name == 'xuexi1998') {
    var login_url = 'https://www.1998xuexi.com/learnCenter'
} else if (login_name == 'yuketang') {
    var login_url = 'https://www.yuketang.cn/web'
} else if (login_name == 'mison') {
    var login_url = 'https://www.mison.cn/e/member/register/index.php'
} else if (login_name == 'zixueb') {
    var login_url = 'https://zixueb.cn/home'
} else if (login_name == 'kandian') {
    var login_url = 'https://www.kandianyunketang.cn/#/person/course/seriescourse'
} else if (login_name == 'yincheng') {
    var login_url = 'https://wx.yixueks.com/ycweb/#/login'
} else if (login_name == 'wrclass') {
    var login_url = 'https://pc.wrclass.com/login'
} else if (login_name == 'eduzhixin') {
    var login_url = 'https://passport.eduzhixin.com/Login'
} else if (login_name == 'dqb') {
    var login_url = 'https://dqb.yixuewk.com/user/login'
} else if (login_name == 'benzhixt') {
    var login_url = 'https://pc.benzhixt.com/pc/#/Login'
} else if (login_name == 'xsteach') {
    var login_url = 'https://www.xsteach.com/user/course'
} else if (login_name == 'magedu') {
    var login_url = 'https://edu.magedu.com/person/home/0/course'
} else if (login_name == 'jingtongxue') {
    var login_url = 'https://www.jingtongxue.com/s/pc/#/join/login'
} else if (login_name == 'caixuetang') {
    var login_url = 'https://www.caixuetang.cn/'
} else if (login_name == 'luffycity') {
    var login_url = 'https://www.luffycity.com/'
} else if (login_name == 'sparke') {
    var login_url = extra_arg || 'https://www.sparke.cn/login?redirect=https://course.sparke.cn/'
} else if (login_name == 'youlu') {
    var login_url = 'https://www.youlu.com/uc/login'
} else if (login_name == 'itbaizhan') {
    var login_url = 'https://www.itbaizhan.com/login?redirect=https://www.itbaizhan.com/'
} else if (login_name == 'nmkjxy') {
    var login_url = 'https://www.nmkjxy.com/'
} else if (login_name == 'mashibing') {
    var login_url = 'https://www.mashibing.com/'
} else if (login_name == 'chaoge') {
    var login_url = CHAOGE_LOGIN_URL;
} else if (login_name == 'shanxiang') {
    var login_url = SHANXIANG_LOGIN_URL;
} else if (login_name == 'shikaobang') {
    var login_url = SHIKAOBANG_LOGIN_URL;
} else if (login_name == 'yiqikaojiaoshi') {
    var login_url = YIQIKAOJIAOSHI_LOGIN_URL;
} else if (isFenbiLoginName(login_name)) {
    var login_url = FENBI_LOGIN_URL;
} else if (login_name == 'yixiaoerguo') {
    var login_url = 'https://www.biguo.cn/my/course'
} else if (login_name == 'huke88') {
    var login_url = 'https://huke88.com/'
} else if (login_name == 'yukebang') {
    var login_url = 'https://study.yukebang.com/login?redirect=%252Fuser%252Fstudy'
} else if (isShanganLoginName()) {
    var login_url = getShanganLoginUrl()
} else if (login_name == 'kaimingzhixue') {
    var login_url = 'https://www.lckmzx.com/login'
} else if (login_name == 'sanjieke') {
    var login_url = extra_arg || 'https://passport.sanjieke.cn/account/phone_sign_in?oauth_callback=https%3A%2F%2Fclassroom.sanjieke.cn%2Fmy_course&channel=wodejiaoshi'
} else if (login_name == 'sanjieke_fetch') {
    var login_url = 'https://study.sanjieke.cn/';
} else if (login_name == 'aishangke') {
    var login_url = extra_arg || 'https://loveshangke.com/user/login'
} else if (login_name == 'xiaoheiketang') {
    var login_url = extra_arg || 'https://www.xiaoheiketang.com/personal/myCourse'
} else if (login_name == 'yikaijiang') {
    var login_url = extra_arg || 'https://jc.e-lesson.cn/spoc/open/login.action'
} else if (login_name == 'wallstreets') {
    var login_url = 'https://wallstreets.cn/login'
} else if (login_name == 'ydshengxue') {
    var login_url = 'https://ydzy.ydshengxue.com'
} else if (login_name == 'plaso') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'plaso_login.html'));
} else if (login_name == 'aiwenyun') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'aiwenyun_login.html'));
} else if (login_name == 'jhpy') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'jhpy_login.html'));
} else if (login_name == 'jhpyedu') {
    var login_url = 'https://new-student.jhpy.com/pages/login/index';
} else if (login_name == 'huoke') {
    var huoke_target_url = String(extra_arg || '').trim();
    var login_url = localFileURL(path.join(app.getAppPath(), 'huoke-login.html'))
        + (huoke_target_url ? '?target=' + encodeURIComponent(huoke_target_url) : '');
} else if (login_name == 'kaoyanvip') {
    var login_url = 'https://www.kaoyanvip.cn/login'
} else if (login_name == 'kuke99') {
    var login_url = 'https://www.kuke99.com/learn-center'
} else if (login_name == 'hqwx') {
    var login_url = 'https://www.hqwx.com/login'
} else if (login_name == 'xinghuo') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'xinghuo-login.html'));
} else if (login_name == 'xiaoeapp') {
    var login_url = localFileURL(path.join(app.getAppPath(), 'xiaoeapp-login.html'));
    var is_xiaoeapp = true;
} else if (login_name == 'classin') {
    var classin_api_base = extra_arg || '';
    var login_url = localFileURL(path.join(app.getAppPath(), 'classin-login.html')) + '?api_base=' + encodeURIComponent(classin_api_base);
} else if (login_name == 'classin_webcast') {
    var login_url = extra_arg || 'https://live.eeo.cn/';
} else if (login_name == 'cctalk') {
    var cctalk_target_url = extra_arg || 'https://www.cctalk.com/m/my';
    var login_url = CCTALK_LOGIN_USE_WEB_PAGE ? 'https://www.cctalk.com' : (localFileURL(path.join(app.getAppPath(), 'cctalk-login.html')) + '?target=' + encodeURIComponent(cctalk_target_url));
} else if ((login_name == 'mddclass' || login_name == 'sihaigongkao')) {
    var mddclass_target_url = normalizeMddclassTargetUrl(extra_arg || MDDCLASS_DEFAULT_TARGET_URL);
    var login_url = MDDCLASS_LOGIN_USE_WEB_PAGE ? MDDCLASS_WEB_LOGIN_URL : (localFileURL(path.join(app.getAppPath(), 'mddclass-login.html')) + (login_name === 'sihaigongkao' ? '?platform=sihaigongkao' : ''));
} else if (login_name == 'moremeditation') {
    var login_url = extra_arg || 'https://h5.esnewcollege.com/pages/login/index';
} else if (login_name == 'zhongxunwx') {
    var login_url = extra_arg || 'https://www.zhongxunwx.com/home/regin/login';
} else if (login_name == 'haozaixian' || login_name == 'dazhaomofang') {
    var login_url = 'https://www.zybang.com/saasplat/general_plat/mlogin.html'
} else if (isDuanshuLoginName(login_name)) {
    const login_ary = login_name.split('.');
    const duanshu_target_url = (extra_arg && /\/course\/detail\//i.test(String(extra_arg))) ? String(extra_arg) : '';
    duanshu_pc_detail_login = !!duanshu_target_url;
    if (login_ary.length >= 2) {
        var shop_domain = login_ary.slice(1).join('.');
        var login_url = duanshu_target_url || ('https://' + shop_domain + '/#/system/mlogin');
    } else {
        var login_url = duanshu_target_url || 'https://www.duanshu.com';
    }
} else if (login_name.includes('xiwang')) {
    if (login_name == 'xiwang') {
        var login_url = 'https://www.xiwang.com/pc-login'
    } else if (login_name == 'xiwang.suyang') {
        var login_url = 'https://xue.xi-xue.com/pc-login'
    } else if (login_name == 'xiwang.youke') {
        var login_url = 'https://xue.wen-su.com/pc-login'
    }
} else if (login_name == 'login') {
    var state = getAppArg(2);
    var login_url = 'http://api.xuewuzhi.cn/downloader/login?state='+state;
} else if (login_name == 'login_test') {
    var state = getAppArg(2);
    var login_url = 'http://api.xuewuzhi.cn/downloader_test/login?state='+state;
} else if (login_name == 'login_weixin') {
    var userid = getAppArg(2);
    var login_url = 'http://api.xuewuzhi.cn/downloader/login_weixin?userid='+userid;
} else if (login_name == 'login_weixin_test') {
    var userid = getAppArg(2);
    var login_url = 'http://api.xuewuzhi.cn/downloader_test/login_weixin?userid='+userid;
} else if (login_name == 'url') {
    var url = getAppArg(2);
    var login_url = url;
}

function isXuewuzhiAccountLoginFlow() {
    if (login_name == 'login' || login_name == 'login_test'
            || login_name == 'login_weixin' || login_name == 'login_weixin_test') {
        return true;
    }
    return login_name == 'url' && /^https:\/\/www\.xuewuzhi\.cn\/downloader(?:_test)?\/v2_login_weixin(?:\?|$)/i.test(
        String(login_url || '')
    );
}

if (isXuewuzhiAccountLoginFlow()) {
    recordXuewuzhiLoginTiming('electron_login_flow_started');
}

var random_string = generateRandomString(32);
const HUOKE_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254186b) XWEB/19841';
var user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36 " + random_string;
if (login_name == 'xiaoetech' && xiaoetech_login_mode == 'pc') {
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) xiaoe-tong-client/1.2.11 Chrome/112.0.5615.204 Electron/24.8.8 Safari/537.36';
} else if (isXiaoetechStoreLoginName()) {
    user_agent = DEFAULT_BROWSER_USER_AGENT;
} else if (login_name == 'huoke') {
    user_agent = HUOKE_USER_AGENT;
} else if (login_name == 'ledu') {
    user_agent = "Mozilla/5.0 (Linux; Android 13; Redmi M2012K10C Build/TKQ1.221114.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/123.0.0.0 Mobile Safari/537.36 ledu/7.76.91";
} else if (login_name == 'dingtalk') {
    user_agent = DEFAULT_BROWSER_USER_AGENT;
} else if (login_name == 'douyin') {
    user_agent = DEFAULT_BROWSER_USER_AGENT;
} else if (login_name == 'luffycity') {
    user_agent = DEFAULT_BROWSER_USER_AGENT;
} else if (login_name == 'mison') {
    user_agent = MISON_USER_AGENT;
} else if (login_name == 'sparke') {
    user_agent = DEFAULT_BROWSER_USER_AGENT;
} else if (login_name == 'youlu') {
    user_agent = DEFAULT_BROWSER_USER_AGENT;
} else if (login_name == 'yuketang') {
    user_agent = DEFAULT_BROWSER_USER_AGENT;
} else if (login_name == 'jhpyedu') {
    user_agent = DEFAULT_BROWSER_USER_AGENT;
} else if (login_name == 'xinghuo') {
    user_agent = 'okhttp/5.0.0-alpha.2';
} else if (login_name == 'huomiao') {
    user_agent = 'Windows/11 (24H2) ClassTorch/5.8.0.16';
} else if (login_name == 'lexueyun') {
    user_agent = DEFAULT_BROWSER_USER_AGENT + ' ' + random_string;
} else if (login_name == 'xueersi') {
    user_agent = DEFAULT_BROWSER_USER_AGENT + ' ' + random_string;
} else if (login_name == 'yunduan') {
    user_agent = DEFAULT_BROWSER_USER_AGENT + ' ' + random_string;
} else if (login_name == 'cctalk' && CCTALK_LOGIN_USE_WEB_PAGE) {
    user_agent = DEFAULT_BROWSER_USER_AGENT + ' ' + random_string;
} else if ((login_name == 'mddclass' || login_name == 'sihaigongkao') && MDDCLASS_LOGIN_USE_WEB_PAGE) {
    user_agent = DEFAULT_BROWSER_USER_AGENT + ' ' + random_string;
} else if (login_name == 'xiaoyuanyouke') {
    user_agent = XIAOYUANYOUKE_USER_AGENT;
} else if (isCkjrLoginName(login_name)) {
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36 " + random_string;
}

function getStoredCookieValue(key) {
    let cookies_obj = readCookiesObject();
    let value = cookies_obj[key];
    if (typeof value === 'string') {
        return value;
    }
    if (value && typeof value === 'object') {
        const cookie_value = String(value.cookieValue || '').trim();
        if (cookie_value) {
            return cookie_value;
        }
    }
    return '';
}

function normalizeSpeiyouHeaderValue(headers, name) {
    if (!headers || !name) {
        return '';
    }
    const target = String(name).toLowerCase();
    for (const key of Object.keys(headers)) {
        if (String(key).toLowerCase() === target) {
            return String(headers[key] || '').trim();
        }
    }
    return '';
}

function extractSpeiyouAuthFromHeaders(headers) {
    const token = normalizeSpeiyouHeaderValue(headers, 'token')
        || normalizeSpeiyouHeaderValue(headers, 'authorization');
    const stuId = normalizeSpeiyouHeaderValue(headers, 'stuId')
        || normalizeSpeiyouHeaderValue(headers, 'stuid')
        || normalizeSpeiyouHeaderValue(headers, 'pu_uid');
    return {
        token: token,
        stuId: stuId,
    };
}

function isSpeiyouApiUrl(url) {
    url = String(url || '');
    return /\/\/(?:course-api-online|classroom-api-online)\.speiyou\.com\//i.test(url)
        || /\/\/passport\.100tal\.com\//i.test(url);
}

function normalizeSpeiyouString(value) {
    if (value === undefined || value === null) {
        return '';
    }
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        return String(value).trim();
    }
    return '';
}

function normalizeSpeiyouStuId(value) {
    const text = normalizeSpeiyouString(value);
    const match = text.match(/\d{5,16}/);
    return match ? match[0] : text;
}

function pickSpeiyouString() {
    for (let i = 0; i < arguments.length; i++) {
        const value = normalizeSpeiyouString(arguments[i]);
        if (value) {
            return value;
        }
    }
    return '';
}

function normalizeSpeiyouObject(value) {
    if (!value) {
        return {};
    }
    if (typeof value === 'string') {
        const raw = String(value || '').trim();
        if (!raw || (raw[0] !== '{' && raw[0] !== '[')) {
            return {};
        }
        const parsed = safeJsonParse(raw, null);
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    }
    return typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function findSpeiyouNestedValue(value, names, depth = 0) {
    if (depth > 6 || value === undefined || value === null) {
        return '';
    }
    const lowered = new Set((names || []).map((name) => String(name || '').toLowerCase()));
    if (typeof value === 'string') {
        const parsed = normalizeSpeiyouObject(value);
        if (parsed && Object.keys(parsed).length) {
            return findSpeiyouNestedValue(parsed, names, depth + 1);
        }
        return '';
    }
    if (Array.isArray(value)) {
        for (const item of value) {
            const found = findSpeiyouNestedValue(item, names, depth + 1);
            if (found) {
                return found;
            }
        }
        return '';
    }
    if (typeof value !== 'object') {
        return '';
    }
    for (const key of Object.keys(value)) {
        if (lowered.has(String(key || '').toLowerCase()) && value[key] !== undefined && value[key] !== null && value[key] !== '') {
            return normalizeSpeiyouString(value[key]);
        }
    }
    for (const key of Object.keys(value)) {
        const found = findSpeiyouNestedValue(value[key], names, depth + 1);
        if (found) {
            return found;
        }
    }
    return '';
}

function buildSpeiyouPcRequestHeaders(auth = {}, extra_headers = null) {
    const token = pickSpeiyouString(auth.token, auth.hb_token, auth.authorization);
    const stuId = normalizeSpeiyouStuId(pickSpeiyouString(auth.stuId, auth.stu_id, auth.pu_uid, auth.puUid));
    const headers = Object.assign({
        'User-Agent': SPEIYOU_PC_USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'identity',
        'Content-Type': 'application/json;charset=UTF-8',
        'terminal': 'pc',
        'appClientType': 'xes',
        'version': SPEIYOU_PC_VERSION,
        'resVer': SPEIYOU_PC_RES_VERSION,
        'lang': 'ch',
        'Origin': 'owcr://classroom',
        'Referer': 'https://speiyou.cn/',
        'token': token,
        'authorization': token,
        'stuId': stuId,
    }, extra_headers || {});
    Object.keys(headers).forEach((name) => {
        if (headers[name] === undefined || headers[name] === null || headers[name] === '') {
            delete headers[name];
        }
    });
    return headers;
}

function getSpeiyouDeviceId() {
    try {
        const interfaces = os.networkInterfaces();
        const names = Object.keys(interfaces || {});
        for (let i = 0; i < names.length; i++) {
            const list = interfaces[names[i]] || [];
            for (let j = 0; j < list.length; j++) {
                const item = list[j];
                if (item && !item.internal && item.mac && item.mac !== '00:00:00:00:00:00') {
                    return String(item.mac).toUpperCase();
                }
            }
        }
    } catch (error) {
        ;
    }
    return 'windows';
}

function normalizeSpeiyouPcLoginResponse(response_body, passport_token = '') {
    const body = normalizeSpeiyouObject(response_body);
    const data = normalizeSpeiyouObject(body.data);
    const result = normalizeSpeiyouObject(body.result);
    const token = pickSpeiyouString(
        findSpeiyouNestedValue(body, ['hb_token', 'hbt_token']),
        body.hb_token,
        data.hb_token,
        result.hb_token,
        findSpeiyouNestedValue(body, ['token']),
        body.token,
        data.token,
        result.token
    );
    const stuId = normalizeSpeiyouStuId(pickSpeiyouString(
        findSpeiyouNestedValue(body, ['pu_uid', 'puUid', 'stuId', 'stu_id', 'studentId', 'student_id']),
        body.pu_uid,
        data.pu_uid,
        result.pu_uid,
        body.stuId,
        data.stuId,
        result.stuId,
        body.stu_id,
        data.stu_id,
        result.stu_id
    ));
    return {
        token: token,
        stuId: stuId,
        pu_uid: pickSpeiyouString(body.pu_uid, data.pu_uid, result.pu_uid, stuId),
        hb_token: pickSpeiyouString(body.hb_token, data.hb_token, result.hb_token, token),
        passport_token: passport_token,
    };
}

function looksLikeSpeiyouSubjectList(response_body) {
    if (Array.isArray(response_body)) {
        return true;
    }
    const body = normalizeSpeiyouObject(response_body);
    if (!Object.keys(body).length) {
        return false;
    }
    if (Array.isArray(body.data) || Array.isArray(body.list) || Array.isArray(body.result)) {
        return true;
    }
    const data = normalizeSpeiyouObject(body.data);
    return Array.isArray(data.list) || Array.isArray(data.records);
}

async function exchangeSpeiyouPassportCode(code, passport_token = '') {
    code = normalizeSpeiyouString(code);
    passport_token = normalizeSpeiyouString(passport_token);
    if (!code) {
        return {};
    }
    const response = await requestJsonUrl(
        'POST',
        SPEIYOU_PC_STUDENT_CODE_LOGIN_URL,
        {
            code: code,
            deviceId: getSpeiyouDeviceId(),
            terminal: SPEIYOU_PC_TERMINAL,
            product: SPEIYOU_PC_PRODUCT,
            clientId: SPEIYOU_PC_CLIENT_ID,
        },
        buildSpeiyouPcRequestHeaders({ passport_token: passport_token })
    );
    const response_body = parseJsonResponseBody(response);
    if (!response || response.statusCode < 200 || response.statusCode >= 300 || !response_body) {
        return {};
    }
    return normalizeSpeiyouPcLoginResponse(response_body, passport_token);
}

async function validateSpeiyouAuthPayload(payload) {
    const token = pickSpeiyouString(payload && payload.token, payload && payload.hb_token);
    const stuId = normalizeSpeiyouStuId(pickSpeiyouString(payload && payload.stuId, payload && payload.pu_uid));
    if (!token || !stuId) {
        return false;
    }
    const response = await requestJsonUrl(
        'GET',
        SPEIYOU_PC_SUBJECT_LIST_URL,
        { stuId: stuId },
        buildSpeiyouPcRequestHeaders({ token: token, stuId: stuId })
    );
    const response_body = parseJsonResponseBody(response);
    return !!(
        response
        && response.statusCode >= 200
        && response.statusCode < 300
        && looksLikeSpeiyouSubjectList(response_body)
    );
}

function mergeSpeiyouRequestAuth(auth) {
    if (!auth || typeof auth !== 'object') {
        return speiyou_request_auth;
    }
    if (auth.token) {
        speiyou_request_auth.token = String(auth.token || '').trim();
    }
    if (auth.stuId) {
        speiyou_request_auth.stuId = String(auth.stuId || '').trim();
    }
    if (auth.pu_uid && !speiyou_request_auth.stuId) {
        speiyou_request_auth.stuId = String(auth.pu_uid || '').trim();
    }
    if (auth.hb_token) {
        speiyou_request_auth.token = String(auth.hb_token || '').trim();
        speiyou_request_auth.hb_token = String(auth.hb_token || '').trim();
    }
    if (auth.passport_token) {
        speiyou_request_auth.passport_token = String(auth.passport_token || '').trim();
    }
    return speiyou_request_auth;
}

function rememberSpeiyouRequestContext(details) {
    if (login_name !== 'speiyou' || !details || !isSpeiyouApiUrl(details.url)) {
        return;
    }
    const auth = extractSpeiyouAuthFromHeaders(details.requestHeaders || {});
    mergeSpeiyouRequestAuth(auth);
}

function buildSpeiyouCookieEntry(extra_payload = {}) {
    const merged = mergeSpeiyouRequestAuth(extra_payload);
    const token = String(merged.token || merged.hb_token || '').trim();
    const stuId = String(merged.stuId || merged.pu_uid || '').trim();
    if (!token || !stuId) {
        return null;
    }
    return {
        token: token,
        stuId: stuId,
        pu_uid: String(merged.pu_uid || stuId || '').trim(),
        hb_token: String(merged.hb_token || '').trim(),
        passport_token: String(merged.passport_token || '').trim(),
        cookieValue: 'token=' + token + ';stuId=' + stuId,
        headers: {
            token: token,
            stuId: stuId,
        },
        savedAt: new Date().toISOString(),
    };
}

function trySaveSpeiyouAuth(extra_payload = {}, force = false) {
    if (login_name !== 'speiyou' || speiyou_save_inflight) {
        return false;
    }
    const entry = buildSpeiyouCookieEntry(extra_payload);
    if (!entry) {
        return false;
    }
    if (!force && !entry.token.startsWith('tal')) {
        return false;
    }
    speiyou_save_inflight = true;
    saveLoginCookieData(JSON.stringify(entry));
    return true;
}

async function trySaveSpeiyouLoginResult(win) {
    if (login_name !== 'speiyou' || speiyou_save_inflight || !isWindowAlive(win)) {
        return false;
    }
    let result = {};
    try {
        result = await win.webContents.executeJavaScript(`
            (() => {
                function safeParse(value) {
                    if (!value) {
                        return null;
                    }
                    if (typeof value !== 'string') {
                        return value;
                    }
                    try {
                        return JSON.parse(value);
                    } catch (error) {
                        return null;
                    }
                }

                function isTokenLike(value) {
                    return typeof value === 'string' && value.length >= 24 && /^tal[A-Za-z0-9._-]+$/.test(value);
                }

                function cleanString(value) {
                    return value === undefined || value === null ? '' : String(value).trim();
                }

                function walk(value, result, depth) {
                    if (!value || depth > 6) {
                        return result;
                    }
                    if (typeof value === 'string') {
                        if (isTokenLike(value) && !result.passport_token) {
                            result.passport_token = value;
                        }
                        var parsed = safeParse(value);
                        if (parsed && parsed !== value) {
                            walk(parsed, result, depth + 1);
                        }
                        return result;
                    }
                    if (Array.isArray(value)) {
                        value.forEach(function (item) {
                            walk(item, result, depth + 1);
                        });
                        return result;
                    }
                    if (typeof value !== 'object') {
                        return result;
                    }
                    Object.keys(value).forEach(function (key) {
                        var lower = String(key || '').toLowerCase();
                        var item = value[key];
                        if ((lower === 'token' || lower === 'hb_token' || lower === 'hbt_token') && cleanString(item)) {
                            result.token = cleanString(item);
                            if (lower === 'hb_token' || lower === 'hbt_token') {
                                result.hb_token = cleanString(item);
                            }
                        } else if ((lower === 'passport_token' || lower === 'passporttoken' || lower === 'tal_token' || lower === 'taltoken') && isTokenLike(item)) {
                            result.passport_token = cleanString(item);
                        } else if (lower === 'code' && cleanString(item)) {
                            result.code = cleanString(item);
                        } else if ((lower === 'stuid' || lower === 'stu_id' || lower === 'pu_uid' || lower === 'puid' || lower === 'studentid' || lower === 'student_id') && item !== undefined && item !== null && cleanString(item)) {
                            result.stuId = cleanString(item);
                            if (lower === 'pu_uid' || lower === 'puid') {
                                result.pu_uid = cleanString(item);
                            }
                        } else if (lower === 'success' && item === true) {
                            result.success = true;
                        } else if (lower === 'cookievalue' && cleanString(item)) {
                            result.cookieValue = cleanString(item);
                        } else if (lower === 'headers' && item && typeof item === 'object') {
                            result.headers = item;
                        }
                        walk(item, result, depth + 1);
                    });
                    return result;
                }

                function scanStorage(storage, result) {
                    if (!storage) {
                        return result;
                    }
                    var directKeys = ['tal-passport-jssdk-tal-token', 'token', 'hb_token', 'passport_token', 'stuId', 'stu_id', 'pu_uid', 'studentInfo', 'student', 'userInfo', 'userInformation'];
                    directKeys.forEach(function (key) {
                        try {
                            walk(storage.getItem(key), result, 0);
                        } catch (error) {
                            ;
                        }
                    });
                    for (var i = 0; i < storage.length; i++) {
                        try {
                            var storageKey = storage.key(i);
                            var lowerKey = String(storageKey || '').toLowerCase();
                            if (lowerKey.indexOf('token') === -1 && lowerKey.indexOf('student') === -1 && lowerKey.indexOf('user') === -1 && lowerKey.indexOf('stu') === -1 && lowerKey.indexOf('tal') === -1) {
                                continue;
                            }
                            walk(storage.getItem(storageKey), result, 0);
                        } catch (error) {
                            ;
                        }
                    }
                    return result;
                }

                var result = {};
                try {
                    walk(window.__SPEIYOU_LOGIN_RESULT__, result, 0);
                } catch (error) {
                    ;
                }
                scanStorage(localStorage, result);
                scanStorage(sessionStorage, result);
                return result;
            })();
        `, true);
    } catch (error) {
        return false;
    }
    result = result && typeof result === 'object' ? result : {};
    if (result.success && result.token && result.stuId) {
        return trySaveSpeiyouAuth(result, true);
    }
    if (!result.token && result.code) {
        const exchanged = await exchangeSpeiyouPassportCode(result.code, result.passport_token).catch(() => ({}));
        result = Object.assign({}, result, exchanged || {});
    }
    if (result.token && result.stuId) {
        const valid = await validateSpeiyouAuthPayload(result).catch(() => false);
        if (valid) {
            return trySaveSpeiyouAuth(result, true);
        }
    }
    trySaveSpeiyouAuth({});
    return false;
}

function applyPlasoLoginRequestHeaders(name, details) {
    if (!['plaso', 'aiwenyun', 'jhpy'].includes(name)) return;
    let target;
    try {
        target = new URL(details.url);
    } catch (_) {
        return;
    }
    const trusted = ['plaso.cn', 'aiwenyun.cn'].some(domain =>
        target.hostname === domain || target.hostname.endsWith('.' + domain));
    if (target.protocol !== 'https:' || !trusted) return;
    const headers = details.requestHeaders;
    const refererKey = Object.keys(headers).find(key => key.toLowerCase() === 'referer');
    // Local file pages omit Referer. The login service then reports code 4
    // (incorrect password) even for valid credentials. Match its official SPA.
    if (refererKey && /^https?:\/\//i.test(String(headers[refererKey]))) return;
    if (refererKey) delete headers[refererKey];
    headers.Referer = target.origin + '/static/yxt/';
}

function createWindow() {
    const login_partition = getLoginSessionPartition(login_name);
    const active_session = login_partition
        ? session.fromPartition(login_partition)
        : session.defaultSession;
    if (isCkjrLoginName(login_name)) {
        ckjr_auth_records = [];
        ckjr_save_inflight = false;
    }
    if (login_name != 'douyin') {
        active_session.webRequest.onBeforeSendHeaders(
            {urls: ["*://*/*"]}, 
            (details, callback)=>{
                let current_user_agent = user_agent;
                if (login_name == 'dongao' && dongao_dynamic_user_agent) {
                    current_user_agent = dongao_dynamic_user_agent;
                }
                details.requestHeaders['User-Agent'] = current_user_agent;
                applyPlasoLoginRequestHeaders(login_name, details);
                if (isCkjrLoginName(login_name)) {
                    pushCkjrAuthRecord(details);
                }
                if (login_name == 'yunduan') {
                    trySaveYunduanRequestCookies(details);
                }
                if ((login_name == 'mddclass' || login_name == 'sihaigongkao')) {
                    rememberMddclassRequestContext(details);
                }
                if (login_name == 'speiyou') {
                    rememberSpeiyouRequestContext(details);
                }
                if (login_name == 'smartedu') {
                    markSmarteduLoginProgress(details.url);
                }
                callback({requestHeaders: details.requestHeaders});
        })
    }
    Menu.setApplicationMenu(null);
    const window_options = {
        icon: path.join(__dirname, 'xuewuzhi.png'),
        alwaysOnTop: true,
        webPreferences: {
            sandbox: false,
        },
    };
    if (login_partition) {
        window_options.webPreferences.partition = login_partition;
    }
    if (login_name == 'wendao' || login_name == 'yikaobang' || login_name == 'zhi10' || login_name == 'xuexi1998') {
        window_options.webPreferences.contextIsolation = true;
        window_options.webPreferences.nodeIntegration = false;
        window_options.webPreferences.sandbox = true;
    }
    if (login_name == 'zhi10') {
        window_options.title = '智拾网 登录';
        // The official login dialog is fixed at 1024 x 500; leave room for the window frame.
        window_options.width = 1100;
        window_options.height = 680;
        window_options.center = true;
    }
    if (login_name === 'yikaobang') {
        window_options.title = '医考帮 登录';
        window_options.width = 560;
        window_options.height = 620;
        window_options.alwaysOnTop = false;
        window_options.webPreferences.preload = path.join(app.getAppPath(), 'yikaobang-preload.js');
    }
    if (login_name == 'zhihuishu') {
        const work_area = screen.getPrimaryDisplay().workAreaSize;
        window_options.width = Math.floor(work_area.width * 0.9);
        window_options.height = Math.floor(work_area.height * 0.9);
        window_options.center = true;
    } else if (login_name == 'yikao88') {
        const work_area = screen.getPrimaryDisplay().workAreaSize;
        window_options.width = Math.floor(work_area.width * 0.8);
        window_options.height = Math.floor(work_area.height * 0.8);
        window_options.x = Math.floor((work_area.width - window_options.width) / 2);
        window_options.y = Math.floor((work_area.height - window_options.height) / 2);
    } else if (login_name == 'huatu') {
        const work_area = screen.getPrimaryDisplay().workAreaSize;
        window_options.width = Math.min(work_area.width, HUATU_WINDOW_WIDTH);
        window_options.height = Math.min(work_area.height, HUATU_WINDOW_HEIGHT);
        window_options.x = Math.max(0, Math.floor((work_area.width - window_options.width) / 2));
        window_options.y = Math.max(0, Math.floor((work_area.height - window_options.height) / 2));
    } else if (login_name == 'houda') {
        window_options.title = '厚大法考 登录';
        window_options.alwaysOnTop = false;
        const work_area = screen.getPrimaryDisplay().workAreaSize;
        window_options.width = Math.min(work_area.width, 920);
        window_options.height = Math.min(work_area.height, 680);
        window_options.x = Math.max(0, Math.floor((work_area.width - window_options.width) / 2));
        window_options.y = Math.max(0, Math.floor((work_area.height - window_options.height) / 2));
    } else if (login_name == 'lexueyun') {
        window_options.title = '乐学云课堂 登录';
        window_options.alwaysOnTop = false;
        const work_area = screen.getPrimaryDisplay().workAreaSize;
        window_options.width = Math.min(work_area.width, 800);
        window_options.height = Math.min(work_area.height, 600);
        window_options.x = Math.max(0, Math.floor((work_area.width - window_options.width) / 2));
        window_options.y = Math.max(0, Math.floor((work_area.height - window_options.height) / 2));
    } else if (login_name == 'dongao') {
        const work_area = screen.getPrimaryDisplay().workAreaSize;
        window_options.useContentSize = true;
        window_options.width = Math.min(work_area.width, DONGAO_WINDOW_WIDTH);
        window_options.height = Math.min(work_area.height, DONGAO_WINDOW_HEIGHT);
        window_options.x = Math.max(0, Math.floor((work_area.width - window_options.width) / 2));
        window_options.y = Math.max(0, Math.floor((work_area.height - window_options.height) / 2));
    } else if (login_name == 'ledu') {
        window_options.title = '\u4e50\u8bfb \u767b\u5f55';
        window_options.alwaysOnTop = false;
        window_options.useContentSize = true;
        window_options.width = LEDU_WINDOW_WIDTH;
        window_options.height = LEDU_WINDOW_HEIGHT;
        window_options.resizable = true;
        window_options.maximizable = true;
        window_options.fullscreenable = true;
    } else if (login_name == 'lexuepeiyou') {
        window_options.title = '乐学培优 登录';
        window_options.alwaysOnTop = false;
        window_options.useContentSize = true;
        window_options.width = 520;
        window_options.height = 650;
        window_options.resizable = true;
    } else if (login_name == 'huomiao') {
        window_options.title = '火苗会议 登录';
        window_options.alwaysOnTop = false;
        window_options.useContentSize = true;
        window_options.width = 520;
        window_options.height = 650;
        window_options.resizable = true;
    } else if (login_name == 'sparke') {
        window_options.title = '星火英语 登录';
        window_options.alwaysOnTop = false;
    } else if (login_name == 'zixueb') {
        window_options.title = '自学帮 登录';
        window_options.alwaysOnTop = false;
    } else if (login_name == 'classin') {
        window_options.title = 'ClassIn(批量) 登录';
    } else if (login_name == 'speiyou') {
        window_options.title = '学而思培优 登录';
        window_options.alwaysOnTop = false;
        window_options.useContentSize = true;
        window_options.width = 520;
        window_options.height = 720;
    } else if (login_name == 'classin_webcast') {
        window_options.title = 'ClassIn直播分享页 登录';
        window_options.alwaysOnTop = false;
    } else if (login_name == 'xinghuo') {
        window_options.title = '星火教育 登录';
        window_options.alwaysOnTop = false;
        window_options.useContentSize = true;
        window_options.width = 520;
        window_options.height = 620;
        window_options.resizable = true;
    } else if (login_name == 'plaso' || login_name == 'aiwenyun' || login_name == 'jhpy' || login_name == 'huoke') {
        const work_area = screen.getPrimaryDisplay().workAreaSize;
        window_options.height = Math.min(work_area.height, 700);
        if (login_name == 'huoke') {
            window_options.title = '获课 登录';
        }
    } else if (login_name == 'cctalk') {
        window_options.title = 'CCtalk(批量) 登录';
        window_options.width = 760;
        window_options.height = 620;
        window_options.alwaysOnTop = false;
    } else if ((login_name == 'mddclass' || login_name == 'sihaigongkao')) {
        window_options.title = login_name === 'sihaigongkao' ? '四海公考 登录' : '\u58a8\u7763\u7763 \u767b\u5f55';
    } else if (login_name.includes('xiaoetech')) {
        window_options.title = login_name == 'xiaoetech' ? '小鹅通平台 登录' : '小鹅通店铺 登录';
    }
    if (login_name == 'moremeditation' || login_name == 'jhpyedu') {
        const work_area = screen.getPrimaryDisplay().workAreaSize;
        window_options.title = login_name == 'jhpyedu' ? '家辉教育 登录' : '\u58a8\u5c14\u51a5\u60f3 \u767b\u5f55';
        window_options.alwaysOnTop = false;
        window_options.useContentSize = true;
        window_options.width = Math.min(work_area.width, login_name == 'jhpyedu' ? 430 : 390);
        window_options.height = Math.min(work_area.height, 720);
        window_options.x = Math.max(0, Math.floor((work_area.width - window_options.width) / 2));
        window_options.y = Math.max(0, Math.floor((work_area.height - window_options.height) / 2));
        window_options.resizable = true;
    }
    if (login_name == 'xiaoeapp' || login_name == 'classin' || login_name == 'classin_webcast' || login_name == 'xinghuo') {
        window_options.webPreferences = Object.assign({}, window_options.webPreferences || {}, {
            webSecurity: false,
        });
    } else if (login_name == 'ledu') {
        window_options.webPreferences = Object.assign({}, window_options.webPreferences || {}, {
            webSecurity: false,
            webviewTag: true,
        });
    } else if (login_name == 'lexueyun') {
        window_options.webPreferences = Object.assign({}, window_options.webPreferences || {}, {
            webSecurity: false,
        });
    } else if (login_name == 'plaso' || login_name == 'aiwenyun' || login_name == 'jhpy' || login_name == 'huoke' || login_name == 'speiyou' || login_name == 'lexuepeiyou' || login_name == 'huomiao' || login_name == 'xiaoyuanyouke' || ((login_name == 'mddclass' || login_name == 'sihaigongkao') && !MDDCLASS_LOGIN_USE_WEB_PAGE) || (login_name == 'cctalk' && !CCTALK_LOGIN_USE_WEB_PAGE)) {
        window_options.webPreferences = Object.assign({}, window_options.webPreferences || {}, {
            webSecurity: false,
            nodeIntegration: true,
            contextIsolation: false,
        });
    }
    if (login_name == 'yunduan') {
        const yunduan_preload = ensureYunduanDeviceCheckPreloadScript();
        window_options.webPreferences = Object.assign({}, window_options.webPreferences || {}, {
            webSecurity: false,
            contextIsolation: false,
        });
        if (yunduan_preload) {
            window_options.webPreferences.preload = yunduan_preload;
        }
    }
    var win = new BrowserWindow(window_options);
    if (login_name === 'yikaobang') {
        attachYikaobangLogin({win, ipcMain, page: login_url,
            saveAuth: saveLoginCookieValue, cancelLogin: () => app.exit(2)});
    }
    win.webContents.on('did-navigate-in-page', (event, target_url, is_main_frame) => {
        if (is_main_frame === false || !isDuanshuWechatQrFlow() || duanshu_qr_finished
                || !isDuanshuQrRefreshUrl(target_url)) {
            return;
        }
        pollDuanshuQrRefresh(win).catch(() => {});
    });
    const benzhixt_compatibility_ready = login_name == 'benzhixt'
        ? installBenzhixtCompatibility(win)
        : Promise.resolve(true);
    const xuexi1998_compatibility_ready = login_name == 'xuexi1998'
        ? installBenzhixtCompatibility(win, {
            scriptPattern: 'https://www.1998xuexi.com/_nuxt/*.js*',
            isScriptUrl: (value) => {
                const url = new URL(value);
                return url.origin === 'https://www.1998xuexi.com'
                    && /^\/_nuxt\/[^/]+\.js$/.test(url.pathname);
            },
            transformScript: (source) => BENZHIXT_COMPATIBILITY_PREFIX
                + require('./fenbi-compatibility').transformFenbiScript(
                    source, path.join(app.getPath('userData'), 'xuexi1998-script-cache')),
        })
        : Promise.resolve(true);
    if (login_name == 'xuexi1998') {
        // Chromium 80 predates CSS inset. Both the Ant login modal and the
        // nested Element slider dialog need explicit edges, otherwise the
        // captcha is clipped in a zero-width overlay below the login form.
        win.webContents.on('dom-ready', () => win.webContents.insertCSS(
            '.ant-modal-mask,.ant-modal-wrap,.el-overlay,.el-overlay-dialog'
            + '{top:0;right:0;bottom:0;left:0}'
        ).catch(() => {}));
    }
    const fenbi_compatibility_ready = isFenbiLoginName(login_name)
        ? require('./fenbi-compatibility').installFenbiCompatibility(
            win, path.join(app.getPath('userData'), 'fenbi-script-cache'))
        : Promise.resolve(true);
    if (login_name == 'sparke') {
        const prepareSparkeLoginViewport = () => {
            if (!isWindowAlive(win)) {
                return;
            }
            win.webContents.setZoomFactor(1);
            prepareSparkeLegacyLogin(win);
            centerSparkeLoginViewport(win);
            setTimeout(() => centerSparkeLoginViewport(win), 250);
            setTimeout(() => centerSparkeLoginViewport(win), 1000);
        };
        win.webContents.on('did-finish-load', prepareSparkeLoginViewport);
        win.webContents.setZoomFactor(1);
    }
    if (login_name.includes('xiaoetech') || login_name == 'sparke') {
        win.on('page-title-updated', (event) => {
            event.preventDefault();
        });
    }
    if (login_name == 'xiaoyuanyouke') {
        const openInCurrentWindow = (target_url) => {
            target_url = String(target_url || '').trim();
            if (!target_url || !/^https?:\/\//i.test(target_url)) {
                return;
            }
            try {
                win.loadURL(target_url);
            } catch (error) {
                ;
            }
        };
        if (typeof win.webContents.setWindowOpenHandler === 'function') {
            win.webContents.setWindowOpenHandler((details) => {
                openInCurrentWindow(details && details.url);
                return { action: 'deny' };
            });
        }
        win.webContents.on('new-window', (event, target_url) => {
            event.preventDefault();
            openInCurrentWindow(target_url);
        });
    }
    const login_session = win.webContents.session;
    if (isXuewuzhiAccountLoginFlow()) {
        let login_cookie_observed = false;
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (login_cookie_observed || removed || !cookie
                    || cookie.name !== 'userid' || !cookie.value) {
                return;
            }
            login_cookie_observed = true;
            recordXuewuzhiLoginTiming('login_cookie_observed');
            setTimeout(() => {
                if (isWindowAlive(win)) {
                    win.close();
                }
            }, 0);
        });
        win.on('closed', () => {
            recordXuewuzhiLoginTiming(
                'login_window_closed',
                {success_cookie: login_cookie_observed}
            );
        });
        win.webContents.on('did-fail-load', (
                event, error_code, error_description, validated_url, is_main_frame) => {
            if (is_main_frame !== false) {
                recordXuewuzhiLoginTiming(
                    'login_page_load_failed',
                    {error_code: Number(error_code) || 0}
                );
            }
        });
        win.webContents.on('render-process-gone', (event, details) => {
            recordXuewuzhiLoginTiming(
                'login_renderer_gone',
                {reason: String(details && details.reason || '').slice(0, 32)}
            );
        });
    }
    if (login_name == 'classin_webcast') {
        const checkClassinWebcastLogin = (delay_ms = 0) => {
            setTimeout(() => {
                if (!isWindowAlive(win)) {
                    return;
                }
                seedClassinWebcastUid();
                login_session.cookies.get({url: 'https://live.eeo.cn/'}).then((cookies) => {
                    trySaveClassinWebcastContext(win, cookies);
                }).catch(() => {
                    trySaveClassinWebcastContext(win, []);
                });
            }, delay_ms);
        };
        const seedClassinWebcastUid = () => {
            if (!isWindowAlive(win) || !classin_webcast_uid) {
                return;
            }
            win.webContents.executeJavaScript(`
                (() => {
                    if (localStorage.getItem('liveChatLogin') === '1') {
                        return false;
                    }
                    const uid = ${JSON.stringify(classin_webcast_uid)};
                    localStorage.setItem('liveChatUid', uid);
                    localStorage.setItem('liveChatAccount', 'yk_' + uid);
                    if (!localStorage.getItem('liveChatName')) {
                        localStorage.setItem('liveChatName', '游客' + uid);
                    }
                    localStorage.setItem('liveChatLogin', '0');
                    localStorage.setItem(
                        'liveChatExpires',
                        String(Date.now() + 7 * 24 * 60 * 60 * 1000),
                    );
                    const message_close = document.querySelector(
                        '.el-message-box__wrapper .el-message-box__headerbtn',
                    );
                    if (message_close) {
                        message_close.click();
                    }
                    const login_button = document.getElementById('top-login')
                        || document.querySelector('.top-login-li .login-btn');
                    if (!document.getElementById('login') && login_button) {
                        login_button.click();
                    }
                    return true;
                })();
            `).catch(() => {});
        };
        ['dom-ready', 'did-finish-load', 'did-navigate', 'did-navigate-in-page'].forEach((event_name) => {
            win.webContents.on(event_name, () => {
                seedClassinWebcastUid();
                checkClassinWebcastLogin(200);
                checkClassinWebcastLogin(1000);
            });
        });
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && cookie && cookie.name === 'webcast_login_status') {
                checkClassinWebcastLogin(100);
            }
        });
    }
    if (login_name == 'sparke') {
        installSparkeLegacyCallbackHandler(win, login_session);
        startSparkeLegacyActionPoll(win);
        const checkSparkeLogin = (delay_ms = 0) => {
            setTimeout(() => {
                trySaveSparkeLoginResult(win);
            }, delay_ms);
        };
        ['dom-ready', 'did-finish-load', 'did-navigate', 'did-navigate-in-page'].forEach((event_name) => {
            win.webContents.on(event_name, () => {
                checkSparkeLogin(0);
                checkSparkeLogin(500);
            });
        });
        login_session.cookies.on('changed', () => {
            checkSparkeLogin(100);
        });
    }
    if (login_name == 'luffycity') {
        installLuffycityDesktopUrlGuard(login_session);
    }
    if (login_name == 'smartedu') {
        const checkSmartedu = (delay_ms) => scheduleSmarteduCookieCheck(win, login_session, delay_ms);
        const scanSmartedu = () => {
            [0, 300, 1000, 2200].forEach(checkSmartedu);
            [600, 1600, 3200, 6000].forEach((delay_ms) => {
                setTimeout(() => {
                    trySaveSmarteduTokenFromPage(win);
                }, delay_ms);
            });
        };
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isSmarteduCookie(cookie)) {
                scanSmartedu();
            }
        });
        ['did-start-navigation', 'did-redirect-navigation', 'did-finish-load', 'did-navigate'].forEach((event_name) => {
            win.webContents.on(event_name, (event, url) => {
                markSmarteduLoginProgress(url || getSafeWindowUrl(win));
                trySaveSmarteduTokenFromPage(win);
                scanSmartedu();
            });
        });
        win.webContents.on('did-navigate-in-page', (event, url) => {
            markSmarteduLoginProgress(url || getSafeWindowUrl(win));
            trySaveSmarteduTokenFromPage(win);
            scanSmartedu();
        });
        scanSmartedu();
    }
    if (login_name == 'unipus') {
        const checkUnipus = (delay_ms) => scheduleUnipusCookieCheck(login_session, delay_ms);
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isUnipusCookie(cookie)) {
                checkUnipus(200);
                checkUnipus(1200);
            }
        });
        ['did-finish-load', 'did-navigate'].forEach((event_name) => {
            win.webContents.on(event_name, () => {
                checkUnipus(500);
                checkUnipus(1800);
            });
        });
        win.webContents.on('did-navigate-in-page', () => {
            checkUnipus(500);
        });
    }
    if (login_name == 'zhi10') {
        const checkZhi10 = (delay_ms) => scheduleLoginCookiesCheck(
            login_session, {url: 'https://www.zhi10.com/'}, trySaveZhi10Cookies, delay_ms);
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && filterZhi10Cookies([cookie]).length) {
                checkZhi10(500);
            }
        });
        ['did-finish-load', 'did-navigate'].forEach((event_name) => {
            win.webContents.on(event_name, () => checkZhi10(500));
        });
        checkZhi10(0);
    }
    if (login_name == 'sikiedu') {
        const checkSikiedu = (delay_ms) => scheduleSikieduCookieCheck(win, login_session, delay_ms);
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isSikieduCookie(cookie)) {
                checkSikiedu(200);
                checkSikiedu(1200);
            }
        });
        ['did-finish-load', 'did-navigate'].forEach((event_name) => {
            win.webContents.on(event_name, () => {
                checkSikiedu(500);
                checkSikiedu(1800);
            });
        });
        win.webContents.on('did-navigate-in-page', () => {
            checkSikiedu(500);
        });
        checkSikiedu(0);
    }
    if (login_name == 'cnmooc') {
        const checkCnmooc = (delay_ms) => scheduleCnmoocCookieCheck(win, login_session, delay_ms);
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isCnmoocCookie(cookie)) {
                checkCnmooc(200);
                checkCnmooc(1200);
            }
        });
        ['did-finish-load', 'did-navigate'].forEach((event_name) => {
            win.webContents.on(event_name, () => {
                checkCnmooc(500);
                checkCnmooc(1800);
            });
        });
        win.webContents.on('did-navigate-in-page', () => {
            checkCnmooc(500);
        });
    }
    if (login_name == 'cctalk') {
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isCctalkCookie(cookie)) {
                login_session.cookies.get({}).then((cookies) => {
                    trySaveCctalkLoginResult(win, cookies, false);
                }).catch(() => {
                    ;
                });
            }
        });
    }
    if ((login_name == 'mddclass' || login_name == 'sihaigongkao')) {
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isMddclassCookie(cookie)) {
                login_session.cookies.get({}).then((cookies) => {
                    trySaveMddclassLoginResult(win, cookies, false);
                }).catch(() => {
                    ;
                });
            }
        });
    }
    if (login_name == 'xiaoyuanyouke') {
        const checkXiaoyuanyoukeLogin = (delay_ms = 0) => {
            setTimeout(() => {
                if (!isWindowAlive(win)) {
                    return;
                }
                login_session.cookies.get({}).then((cookies) => {
                    trySaveXiaoyuanyoukeLoginResult(win, cookies);
                }).catch(() => {
                    trySaveXiaoyuanyoukeLoginResult(win);
                });
            }, delay_ms);
        };
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isXiaoyuanyoukeCookie(cookie)) {
                login_session.cookies.get({}).then((cookies) => {
                    trySaveXiaoyuanyoukeLoginResult(win, cookies);
                }).catch(() => {
                    ;
                });
            }
        });
        ['dom-ready', 'did-finish-load', 'did-navigate'].forEach((event_name) => {
            win.webContents.on(event_name, () => {
                checkXiaoyuanyoukeLogin(300);
                checkXiaoyuanyoukeLogin(1500);
            });
        });
        const xiaoyuanyouke_result_timer = setInterval(() => {
            checkXiaoyuanyoukeLogin(0);
        }, 800);
        win.on('closed', () => {
            clearInterval(xiaoyuanyouke_result_timer);
        });
    }
    if (login_name == 'yijiayk') {
        const checkYijiaykLogin = (delay_ms = 0) => {
            setTimeout(() => {
                trySaveYijiaykToken(win).catch(() => {
                    yijiayk_save_inflight = false;
                });
            }, delay_ms);
        };
        ['dom-ready', 'did-finish-load', 'did-navigate', 'did-navigate-in-page'].forEach((event_name) => {
            win.webContents.on(event_name, () => {
                checkYijiaykLogin(300);
                checkYijiaykLogin(1500);
            });
        });
        const yijiayk_result_timer = setInterval(() => {
            checkYijiaykLogin(0);
        }, 1200);
        win.on('closed', () => {
            clearInterval(yijiayk_result_timer);
        });
    }
    if (login_name == 'houda') {
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isHoudaCookie(cookie)) {
                login_session.cookies.get({}).then((cookies) => {
                    trySaveHoudaCookies(cookies);
                }).catch(() => {
                    ;
                });
            }
        });
    }
    if (login_name == 'shikaobang') {
        const checkShikaobangLogin = (delay_ms = 0) => {
            setTimeout(() => {
                if (!isWindowAlive(win)) {
                    return;
                }
                login_session.cookies.get({}).then((cookies) => {
                    trySaveShikaobangLoginResult(win, cookies);
                }).catch(() => {
                    ;
                });
            }, delay_ms);
        };
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isShikaobangCookie(cookie)) {
                checkShikaobangLogin(200);
                checkShikaobangLogin(1200);
            }
        });
        ['dom-ready', 'did-finish-load', 'did-navigate', 'did-navigate-in-page'].forEach((event_name) => {
            win.webContents.on(event_name, () => {
                checkShikaobangLogin(300);
                checkShikaobangLogin(1500);
            });
        });
    }
    if (login_name == 'lexueyun') {
        win.webContents.on('did-finish-load', () => {
            trySaveLexueyunAuth(win);
        });
        win.webContents.on('did-navigate', () => {
            trySaveLexueyunAuth(win);
        });
        win.webContents.on('did-navigate-in-page', () => {
            trySaveLexueyunAuth(win);
        });
    }
    if (login_name == 'caixuetang') {
        installCaixuetangPopupBlockers(win);
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed) {
                login_session.cookies.get({domain: ".caixuetang.cn"}).then((cookies) => {
                    trySaveCaixuetangLoginResult(win, filterCaixuetangCookies(cookies));
                }).catch(() => {
                    ;
                });
            }
        });
    }
    if (login_name == 'luffycity') {
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed) {
                login_session.cookies.get({domain: ".luffycity.com"}).then((cookies) => {
                    trySaveLuffycityLoginResult(win, filterLuffycityCookies(cookies));
                }).catch(() => {
                    ;
                });
            }
        });
    }
    if (login_name == 'jingtongxue') {
        const scheduleJingtongxueLoginScroll = (delay_ms) => {
            setTimeout(() => {
                scrollItbaizhanLoginViewportRight(win);
            }, delay_ms);
        };
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            const cookie_name = String(cookie && cookie.name || '');
            if (!removed && ['token', 'userInfo', 'up_token', 'cookie_user_'].includes(cookie_name)) {
                login_session.cookies.get({}).then((cookies) => {
                    trySaveJingtongxueLoginResult(win, filterJingtongxueCookies(cookies));
                }).catch(() => {
                    ;
                });
            }
        });
        win.webContents.on('dom-ready', () => {
            scheduleJingtongxueLoginScroll(200);
            scheduleJingtongxueLoginScroll(1000);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleJingtongxueLoginScroll(300);
            scheduleJingtongxueLoginScroll(1200);
        });
        win.webContents.on('did-navigate-in-page', () => {
            scheduleJingtongxueLoginScroll(300);
            scheduleJingtongxueLoginScroll(1000);
        });
    }
    if (login_name == 'xiaoetech' && xiaoetech_login_mode == 'pc') {
        const trySaveXiaoetechPcToken = () => {
            login_session.cookies.get({url: 'https://study.xiaoe-tech.com'}).then((cookies) => {
                const token_cookie = cookies.find((cookie) => cookie.name == 'p_token' && cookie.value);
                const token = String(token_cookie && token_cookie.value || '').trim();
                const rejected_at = Number(xiaoetech_pc_rejected_tokens.get(token) || 0);
                if (
                    !token
                    || xiaoetech_pc_token_validation_inflight
                    || (rejected_at && Date.now() - rejected_at < 3000)
                ) {
                    return;
                }
                xiaoetech_pc_token_validation_inflight = true;
                validateXiaoetechPcToken(token).then((valid) => {
                    if (valid) {
                        xiaoetech_pc_rejected_tokens.delete(token);
                        saveLoginCookieValue('p_token=' + token);
                        return;
                    }
                    xiaoetech_pc_rejected_tokens.set(token, Date.now());
                    return login_session.cookies.remove(
                        'https://study.xiaoe-tech.com',
                        'p_token',
                    ).catch(() => {});
                }).catch(() => {}).finally(() => {
                    xiaoetech_pc_token_validation_inflight = false;
                });
            }).catch(() => {});
        };
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && cookie && cookie.name == 'p_token' && cookie.value) {
                trySaveXiaoetechPcToken();
            }
        });
        win.webContents.on('did-finish-load', trySaveXiaoetechPcToken);
        win.webContents.on('did-navigate', trySaveXiaoetechPcToken);
    }
    if (isXiaoetechStoreLoginName()) {
        const trySaveXiaoetechStoreToken = () => {
            saveXiaoetechStoreLoginResult(login_session).catch(() => {});
        };
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && filterXiaoetechStoreCookies([cookie]).length) {
                saveXiaoetechStoreLoginResult(login_session, [cookie]).catch(() => {});
            }
        });
        win.webContents.on('did-finish-load', trySaveXiaoetechStoreToken);
        win.webContents.on('did-navigate', trySaveXiaoetechStoreToken);
        win.webContents.on('did-navigate-in-page', trySaveXiaoetechStoreToken);
    }
    if (login_name == 'magedu') {
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed) {
                login_session.cookies.get({domain: "edu.magedu.com"}).then((cookies) => {
                    trySaveMageduLoginResult(win, filterMageduCookies(cookies));
                }).catch(() => {
                    ;
                });
            }
        });
    }
    if (login_name == 'yunduan') {
        installYunduanDeviceCheckRequestBlocker(login_session);
        installYunduanDeviceCheckWindowBlocker(win);
        login_session.cookies.on('changed', (event, cookie, cause, removed) => {
            if (!removed && isYunduanCookie(cookie)) {
                trySaveYunduanCookies([cookie], win);
            }
        });
        login_session.setPermissionRequestHandler((web_contents, permission, callback) => {
            callback(false);
        });
    }
    win.webContents.setUserAgent(user_agent);
    if (login_name == 'wendao') {
        win.webContents.on('dom-ready', () => applyWendaoLoginLayout(win));
    }
    if (login_name == 'moremeditation') {
        win.webContents.setZoomFactor(1);
        if (typeof win.webContents.setVisualZoomLevelLimits === 'function') {
            win.webContents.setVisualZoomLevelLimits(1, 1).catch(() => {});
        }
    }
    const ckjr_store_context = isCkjrLoginName(login_name)
        ? parseCkjrStoreContext(extra_arg || login_url)
        : null;
    let effective_login_url = ckjr_store_context
        ? ckjr_store_context.loginUrl
        : login_url;
    if (login_name == 'luffycity') {
        effective_login_url = normalizeLuffycityWebUrl(effective_login_url) || 'https://www.luffycity.com/';
    }
    let last_window_url = '';
    const updateWindowUrlSnapshot = () => {
        last_window_url = getSafeWindowUrl(win, last_window_url);
    };
    win.webContents.on('did-start-navigation', updateWindowUrlSnapshot);
    win.webContents.on('did-navigate', updateWindowUrlSnapshot);
    win.webContents.on('did-finish-load', updateWindowUrlSnapshot);
    if (login_name == 'luffycity') {
        let last_luffycity_mobile_redirect_url = '';
        const redirectLuffycityMobileUrl = (url) => {
            const normalized_url = normalizeLuffycityWebUrl(url);
            if (normalized_url && normalized_url !== url && isWindowAlive(win)) {
                if (last_luffycity_mobile_redirect_url === normalized_url) {
                    return true;
                }
                last_luffycity_mobile_redirect_url = normalized_url;
                win.loadURL(normalized_url);
                return true;
            }
            return false;
        };
        win.webContents.on('will-navigate', (event, url) => {
            if (redirectLuffycityMobileUrl(url)) {
                event.preventDefault();
            }
        });
        win.webContents.on('did-navigate', (event, url) => {
            redirectLuffycityMobileUrl(url);
        });
        win.webContents.on('did-navigate-in-page', (event, url) => {
            redirectLuffycityMobileUrl(url);
        });
        win.webContents.on('did-stop-loading', () => {
            redirectLuffycityMobileUrl(getSafeWindowUrl(win, ''));
        });
    }
    if (login_name == 'yunduan') {
        win.webContents.on('will-navigate', (event, url) => {
            const yunduan_url = extractYunduanWebUrl(url);
            if (yunduan_url && yunduan_url !== url) {
                event.preventDefault();
                win.loadURL(yunduan_url);
                return;
            }
            checkYunduanLoginByCurrentUrl(win, url);
        });
        win.webContents.on('did-navigate', (event, url) => {
            checkYunduanLoginByCurrentUrl(win, url);
        });
        win.webContents.on('did-navigate-in-page', (event, url) => {
            checkYunduanLoginByCurrentUrl(win, url);
        });
        const scheduleYunduanDeviceCheckPopup = (delay_ms) => {
            suppressYunduanDeviceCheckPopup(win, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleYunduanDeviceCheckPopup(200);
            scheduleYunduanDeviceCheckPopup(1000);
            scheduleYunduanDeviceCheckPopup(2500);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleYunduanDeviceCheckPopup(200);
            scheduleYunduanDeviceCheckPopup(1200);
            scheduleYunduanDeviceCheckPopup(3200);
            login_session.cookies.get({})
                .then((cookies) => trySaveYunduanCookies(cookies, win))
                .catch(() => {
                    ;
                });
        });
    }
    if (ckjr_store_context) {
        installCkjrInitScript(win, ckjr_store_context).catch(() => {
            ;
        });
    }
    if (login_name == 'ledu') {
        const leduGuestContents = new Set();
        const leduFrameSize = (() => {
            const windowBounds = win.getBounds();
            const contentBounds = win.getContentBounds();
            return {
                width: Math.max(0, windowBounds.width - contentBounds.width),
                height: Math.max(0, windowBounds.height - contentBounds.height),
            };
        })();
        let leduApplyingMaxBounds = false;
        const applyLeduMobileView = (contents) => {
            if (!contents || contents.isDestroyed()) {
                return;
            }
            contents.setUserAgent(user_agent);
            try {
                contents.enableDeviceEmulation({
                    screenPosition: 'mobile',
                    fitToView: true,
                    scale: 1,
                    deviceScaleFactor: 3,
                    screenSize: {
                        width: LEDU_WINDOW_WIDTH,
                        height: LEDU_WINDOW_HEIGHT,
                    },
                    viewPosition: {
                        x: 0,
                        y: 0,
                    },
                    viewSize: {
                        width: LEDU_WINDOW_WIDTH,
                        height: LEDU_WINDOW_HEIGHT,
                    },
                });
            } catch (error) {
                ;
            }
        };
        const syncLeduMobileView = () => {
            leduGuestContents.forEach((contents) => {
                if (!contents || contents.isDestroyed()) {
                    leduGuestContents.delete(contents);
                    return;
                }
                applyLeduMobileView(contents);
            });
        };
        const getLeduExpandedBounds = () => {
            const display = screen.getDisplayMatching(win.getBounds());
            const workArea = display.workArea;
            let width = Math.round((workArea.height - leduFrameSize.height) * LEDU_WINDOW_ASPECT_RATIO) + leduFrameSize.width;
            let height = workArea.height;
            if (width > workArea.width) {
                width = workArea.width;
                height = Math.round((width - leduFrameSize.width) / LEDU_WINDOW_ASPECT_RATIO) + leduFrameSize.height;
            }
            return {
                x: workArea.x + Math.max(0, Math.floor((workArea.width - width) / 2)),
                y: workArea.y + Math.max(0, Math.floor((workArea.height - height) / 2)),
                width: width,
                height: height,
            };
        };
        const expandLeduWindowToFullHeight = () => {
            if (win.isDestroyed()) {
                return;
            }
            win.setBounds(getLeduExpandedBounds());
            syncLeduMobileView();
        };
        win.setAspectRatio(LEDU_WINDOW_ASPECT_RATIO, leduFrameSize);
        win.on('resize', syncLeduMobileView);
        win.on('maximize', () => {
            if (leduApplyingMaxBounds) {
                return;
            }
            leduApplyingMaxBounds = true;
            setImmediate(() => {
                try {
                    if (!win.isDestroyed() && win.isMaximized()) {
                        win.unmaximize();
                    }
                    expandLeduWindowToFullHeight();
                } finally {
                    leduApplyingMaxBounds = false;
                }
            });
        });
        win.webContents.on('did-attach-webview', (event, contents) => {
            leduGuestContents.add(contents);
            applyLeduMobileView(contents);
            contents.on('destroyed', () => {
                leduGuestContents.delete(contents);
            });
            contents.on('dom-ready', () => {
                contents.insertCSS('html,body,#app{min-height:100%!important;} body{background:#f4f5f6!important;}').catch(() => {
                    ;
                });
            });
        });
    }
    win.on('closed', () => {
        stopCookiePoll();
    });
    if (login_name == 'huatu') {
        const scheduleHuatuPreload = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    preload_win_js();
                }
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleHuatuPreload(500);
            scheduleHuatuPreload(1500);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleHuatuPreload(500);
            scheduleHuatuPreload(1800);
        });
    }
    if (login_name == 'wowtiku') {
        const scheduleWowtikuPreload = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    preload_win_js();
                }
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleWowtikuPreload(500);
            scheduleWowtikuPreload(1500);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleWowtikuPreload(500);
            scheduleWowtikuPreload(1800);
        });
    }
    if (login_name == 'houda') {
        const scheduleHoudaLoginClick = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    openHoudaLoginDialog(win).then((opened) => {
                        if (!opened) {
                            preload_win_js();
                        }
                    }).catch(() => {
                        preload_win_js();
                    });
                }
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleHoudaLoginClick(200);
            scheduleHoudaLoginClick(900);
            scheduleHoudaLoginClick(2200);
            scheduleHoudaLoginClick(5000);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleHoudaLoginClick(300);
            scheduleHoudaLoginClick(1200);
            scheduleHoudaLoginClick(3200);
            scheduleHoudaLoginClick(6500);
            scheduleHoudaLoginClick(10000);
        });
        win.webContents.on('did-navigate', () => {
            scheduleHoudaLoginClick(700);
            scheduleHoudaLoginClick(2400);
            scheduleHoudaLoginClick(5600);
        });
        win.webContents.on('did-navigate-in-page', () => {
            scheduleHoudaLoginClick(500);
            scheduleHoudaLoginClick(1600);
            scheduleHoudaLoginClick(3600);
        });
        scheduleHoudaLoginClick(3500);
        scheduleHoudaLoginClick(7000);
        scheduleHoudaLoginClick(12000);
    }
    if (login_name == 'caixuetang') {
        const scheduleCaixuetangLogin = (delay_ms) => {
            suppressCaixuetangPopups(win, delay_ms);
            clickCaixuetangLoginButton(win, delay_ms + 100);
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    login_session.cookies.get({domain: ".caixuetang.cn"}).then((cookies) => {
                        trySaveCaixuetangLoginResult(win, filterCaixuetangCookies(cookies));
                    }).catch(() => {
                        ;
                    });
                }
            }, delay_ms + 300);
        };
        win.webContents.on('dom-ready', () => {
            suppressCaixuetangPopups(win);
            scheduleCaixuetangLogin(300);
            scheduleCaixuetangLogin(1200);
            scheduleCaixuetangLogin(3000);
        });
        win.webContents.on('did-finish-load', () => {
            suppressCaixuetangPopups(win);
            scheduleCaixuetangLogin(500);
            scheduleCaixuetangLogin(1800);
            scheduleCaixuetangLogin(4200);
        });
        win.webContents.on('did-navigate', () => {
            suppressCaixuetangPopups(win);
            scheduleCaixuetangLogin(800);
            scheduleCaixuetangLogin(2600);
        });
    }
    if (login_name == 'luffycity') {
        const scheduleLuffycityLogin = (delay_ms) => {
            clickLuffycityLoginButton(win, delay_ms + 100);
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    login_session.cookies.get({domain: ".luffycity.com"}).then((cookies) => {
                        trySaveLuffycityLoginResult(win, filterLuffycityCookies(cookies));
                    }).catch(() => {
                        ;
                    });
                }
            }, delay_ms + 300);
        };
        win.webContents.on('dom-ready', () => {
            scheduleLuffycityLogin(300);
            scheduleLuffycityLogin(1200);
            scheduleLuffycityLogin(3000);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleLuffycityLogin(500);
            scheduleLuffycityLogin(1800);
            scheduleLuffycityLogin(4200);
        });
        win.webContents.on('did-navigate', () => {
            scheduleLuffycityLogin(800);
            scheduleLuffycityLogin(2600);
        });
    }
    if (login_name == 'sieredu') {
        const scheduleSiereduLogin = (delay_ms) => {
            clickSiereduLoginButton(win, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleSiereduLogin(300);
            scheduleSiereduLogin(1200);
            scheduleSiereduLogin(3000);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleSiereduLogin(500);
            scheduleSiereduLogin(1800);
            scheduleSiereduLogin(4200);
        });
        win.webContents.on('did-navigate', () => {
            scheduleSiereduLogin(800);
            scheduleSiereduLogin(2600);
        });
        win.webContents.on('did-navigate-in-page', () => {
            scheduleSiereduLogin(800);
            scheduleSiereduLogin(2600);
        });
    }
    if (login_name == 'zhidao') {
        const scheduleZhidaoLogin = (delay_ms) => {
            clickZhidaoLoginButton(win, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleZhidaoLogin(300);
            scheduleZhidaoLogin(1200);
            scheduleZhidaoLogin(3000);
            scheduleZhidaoLogin(7000);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleZhidaoLogin(500);
            scheduleZhidaoLogin(1800);
            scheduleZhidaoLogin(4200);
            scheduleZhidaoLogin(8000);
        });
        win.webContents.on('did-navigate', () => {
            scheduleZhidaoLogin(800);
            scheduleZhidaoLogin(2600);
        });
        win.webContents.on('did-navigate-in-page', () => {
            scheduleZhidaoLogin(800);
            scheduleZhidaoLogin(2600);
        });
    }
    if (login_name == 'yiihuu') {
        const scheduleYiihuuLogin = (delay_ms) => {
            clickYiihuuLoginButton(win, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleYiihuuLogin(300);
            scheduleYiihuuLogin(1200);
            scheduleYiihuuLogin(3000);
            scheduleYiihuuLogin(7000);
            scheduleYiihuuLogin(12000);
            scheduleYiihuuLogin(18000);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleYiihuuLogin(500);
            scheduleYiihuuLogin(1800);
            scheduleYiihuuLogin(4200);
        });
        win.webContents.on('did-stop-loading', () => {
            scheduleYiihuuLogin(300);
            scheduleYiihuuLogin(1200);
        });
        win.webContents.on('did-navigate', () => {
            scheduleYiihuuLogin(800);
            scheduleYiihuuLogin(2600);
        });
        win.webContents.on('did-navigate-in-page', () => {
            scheduleYiihuuLogin(800);
            scheduleYiihuuLogin(2600);
        });
    }
    if (isFenbiLoginName(login_name)) {
        const scheduleFenbiPreload = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    preload_win_js();
                    clickFenbiLoginButton(win);
                }
            }, delay_ms);
        };
        const scheduleFenbiLoginClick = (delay_ms) => {
            clickFenbiLoginButton(win, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleFenbiLoginClick(120);
            scheduleFenbiPreload(500);
            scheduleFenbiPreload(1500);
            scheduleFenbiPreload(3000);
            scheduleFenbiPreload(6000);
            scheduleFenbiLoginClick(9000);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleFenbiLoginClick(120);
            scheduleFenbiPreload(500);
            scheduleFenbiPreload(1800);
            scheduleFenbiPreload(3500);
            scheduleFenbiPreload(6500);
            scheduleFenbiLoginClick(10000);
        });
        win.webContents.on('did-frame-finish-load', () => {
            scheduleFenbiLoginClick(500);
            scheduleFenbiLoginClick(2200);
        });
        win.webContents.on('did-navigate', () => {
            scheduleFenbiLoginClick(800);
            scheduleFenbiLoginClick(2500);
        });
    }
    if (login_name == 'shikaobang') {
        const scheduleShikaobangLoginClick = (delay_ms) => {
            clickShikaobangLoginButton(win, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleShikaobangLoginClick(120);
            scheduleShikaobangLoginClick(500);
            scheduleShikaobangLoginClick(1500);
            scheduleShikaobangLoginClick(3000);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleShikaobangLoginClick(120);
            scheduleShikaobangLoginClick(800);
            scheduleShikaobangLoginClick(2200);
        });
        win.webContents.on('did-frame-finish-load', () => {
            scheduleShikaobangLoginClick(500);
            scheduleShikaobangLoginClick(2200);
        });
        win.webContents.on('did-navigate', () => {
            scheduleShikaobangLoginClick(800);
            scheduleShikaobangLoginClick(2500);
        });
    }
    if (login_name == 'yiqikaojiaoshi') {
        const scheduleYiqikaojiaoshiLoginClick = (delay_ms) => {
            clickYiqikaojiaoshiLoginButton(win, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleYiqikaojiaoshiLoginClick(120);
            scheduleYiqikaojiaoshiLoginClick(500);
            scheduleYiqikaojiaoshiLoginClick(1500);
            scheduleYiqikaojiaoshiLoginClick(3000);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleYiqikaojiaoshiLoginClick(120);
            scheduleYiqikaojiaoshiLoginClick(800);
            scheduleYiqikaojiaoshiLoginClick(2200);
        });
        win.webContents.on('did-frame-finish-load', () => {
            scheduleYiqikaojiaoshiLoginClick(500);
            scheduleYiqikaojiaoshiLoginClick(2200);
        });
        win.webContents.on('did-navigate', () => {
            scheduleYiqikaojiaoshiLoginClick(800);
            scheduleYiqikaojiaoshiLoginClick(2500);
        });
        win.webContents.on('did-navigate-in-page', () => {
            scheduleYiqikaojiaoshiLoginClick(800);
            scheduleYiqikaojiaoshiLoginClick(2500);
        });
    }
    if (login_name == 'dongao') {
        const scheduleDongaoViewportAdjust = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed() && isDongaoPassportLoginUrl(getSafeWindowUrl(win))) {
                    adjustDongaoLoginViewport(win);
                }
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleDongaoViewportAdjust(100);
            scheduleDongaoViewportAdjust(600);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleDongaoViewportAdjust(100);
            scheduleDongaoViewportAdjust(600);
        });
        win.webContents.on('did-navigate', () => {
            scheduleDongaoViewportAdjust(100);
            scheduleDongaoViewportAdjust(600);
        });
    }
    if (login_name == 'wangxiao') {
        const scheduleWangxiaoViewportAdjust = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    adjustWangxiaoLoginViewport(win);
                }
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleWangxiaoViewportAdjust(100);
            scheduleWangxiaoViewportAdjust(600);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleWangxiaoViewportAdjust(100);
            scheduleWangxiaoViewportAdjust(600);
        });
        win.webContents.on('did-navigate', () => {
            scheduleWangxiaoViewportAdjust(100);
            scheduleWangxiaoViewportAdjust(600);
        });
    }
    if (login_name == 'dingtalk') {
        // 3 秒后取消窗口置顶, 仅限钉钉登录使用
        setTimeout(() => {
            if (!win || win.isDestroyed()) {
                return;
            }
            win.setAlwaysOnTop(false);
        }, 3200);
    }
    if (login_name == 'lizhiweike') {
        const syncLizhiweikeLoginUi = () => {
            injectLizhiweikeLoginSwitcher(win);
            saveLizhiweikeLoginResult(win);
        };
        win.webContents.on('dom-ready', () => {
            setTimeout(syncLizhiweikeLoginUi, 100);
            setTimeout(syncLizhiweikeLoginUi, 800);
        });
        win.webContents.on('did-finish-load', () => {
            setTimeout(syncLizhiweikeLoginUi, 100);
            setTimeout(syncLizhiweikeLoginUi, 1200);
        });
        win.webContents.on('did-navigate', () => {
            setTimeout(syncLizhiweikeLoginUi, 100);
            setTimeout(syncLizhiweikeLoginUi, 800);
        });
        win.webContents.on('did-navigate-in-page', () => {
            setTimeout(syncLizhiweikeLoginUi, 100);
            setTimeout(syncLizhiweikeLoginUi, 800);
        });
    }
    if (login_name == 'yukebang') {
        const syncYukebangLogin = () => {
            saveYukebangLoginResult(win);
        };
        win.webContents.on('dom-ready', () => {
            setTimeout(syncYukebangLogin, 300);
            setTimeout(syncYukebangLogin, 1500);
        });
        win.webContents.on('did-finish-load', () => {
            setTimeout(syncYukebangLogin, 500);
            setTimeout(syncYukebangLogin, 2000);
        });
        win.webContents.on('did-navigate', () => {
            setTimeout(syncYukebangLogin, 800);
            setTimeout(syncYukebangLogin, 2600);
        });
        win.webContents.on('did-navigate-in-page', () => {
            setTimeout(syncYukebangLogin, 800);
            setTimeout(syncYukebangLogin, 2600);
        });
    }
    if (isShanganLoginName()) {
        const syncShanganLogin = () => {
            saveShanganLoginResult(win);
        };
        win.webContents.on('dom-ready', () => {
            setTimeout(syncShanganLogin, 300);
            setTimeout(syncShanganLogin, 1500);
        });
        win.webContents.on('did-finish-load', () => {
            setTimeout(syncShanganLogin, 500);
            setTimeout(syncShanganLogin, 2000);
        });
        win.webContents.on('did-navigate', () => {
            setTimeout(syncShanganLogin, 800);
            setTimeout(syncShanganLogin, 2600);
        });
        win.webContents.on('did-navigate-in-page', () => {
            setTimeout(syncShanganLogin, 800);
            setTimeout(syncShanganLogin, 2600);
        });
    }
    if (login_name == 'ledu') {
        const leduBounds = win.getBounds();
        win.setMinimumSize(leduBounds.width, leduBounds.height);
    }
    if (login_name.includes('xiaoetech') || login_name == 'lizhiweike') {
        win.setMinimumSize(360, 720);
        if (!win.isDestroyed()) {
            win.reload();
        }
    }
    let login_page_loaded = false;
    const loadLoginPage = () => {
        if (login_page_loaded || !isWindowAlive(win)) {
            return;
        }
        login_page_loaded = true;
        if (isDuanshuWechatQrFlow()) {
            duanshu_qr_win = win;
            try {
                const work_area = screen.getDisplayMatching(win.getBounds()).workAreaSize;
                win.setTitle('短书微信登录');
                win.setAlwaysOnTop(false);
                win.setResizable(true);
                win.setMinimumSize(Math.min(360, work_area.width), Math.min(560, work_area.height));
                win.setContentSize(Math.min(540, work_area.width), Math.min(680, work_area.height - 40));
                win.center();
            } catch (error) {
                ;
            }
            startDuanshuQrLogin(win, false).catch(() => {});
            return;
        }
        if (login_name == 'yiihuu') {
            clickYiihuuLoginButton(win, 2500);
            clickYiihuuLoginButton(win, 5000);
            clickYiihuuLoginButton(win, 8000);
            clickYiihuuLoginButton(win, 12000);
            clickYiihuuLoginButton(win, 18000);
        }
        const page_load = win.loadURL(effective_login_url);
        if (ckjr_store_context) page_load.catch(() => {});
    };
    if (login_name == 'cctalk') {
        win.webContents.on('did-navigate-in-page', (event, target_url) => {
            trySaveCctalkLoginResultFromUrl(target_url);
        });
        win.webContents.on('did-finish-load', () => {
            if (CCTALK_LOGIN_USE_WEB_PAGE) {
                setTimeout(preload_win_js, 300);
                setTimeout(preload_win_js, 1200);
                setTimeout(preload_win_js, 2600);
            }
            setTimeout(() => {
                login_session.cookies.get({}).then((cookies) => {
                    trySaveCctalkLoginResult(win, cookies, false);
                }).catch(() => {
                    ;
                });
            }, 300);
        });
    }
    if ((login_name == 'mddclass' || login_name == 'sihaigongkao')) {
        win.webContents.on('did-finish-load', () => {
            if (MDDCLASS_LOGIN_USE_WEB_PAGE) {
                setTimeout(preload_win_js, 300);
                setTimeout(preload_win_js, 1200);
                setTimeout(preload_win_js, 2600);
            }
            setTimeout(() => {
                login_session.cookies.get({}).then((cookies) => {
                    trySaveMddclassLoginResult(win, cookies, false);
                }).catch(() => {
                    ;
                });
            }, 300);
        });
    }
    if (ckjr_store_context) {
        win.webContents.on('did-finish-load', () => {
            setTimeout(() => {
                syncCkjrStoreContext(win, ckjr_store_context);
            }, 120);
            setTimeout(() => {
                syncCkjrStoreContext(win, ckjr_store_context);
            }, 900);
        });
    }
    if (login_name == 'huke88') {
        const scheduleHuke88Preload = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    preload_win_js();
                }
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleHuke88Preload(300);
            scheduleHuke88Preload(1200);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleHuke88Preload(500);
            scheduleHuke88Preload(1800);
            scheduleHuke88Preload(3500);
        });
        win.webContents.on('did-navigate', () => {
            scheduleHuke88Preload(800);
            scheduleHuke88Preload(2200);
        });
    }
    if (login_name == 'itbaizhan' || login_name == 'canto' || login_name == 'educity' || login_name == 'yukebang' || isShanganLoginName() || login_name == 'dxy' || login_name == 'yikaijiang' || login_name == 'baitong' || login_name == 'youlu' || login_name == 'xuetian') {
        const scheduleItbaizhanViewportRight = (delay_ms) => {
            setTimeout(() => {
                scrollItbaizhanLoginViewportRight(win, isShanganLoginName());
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleItbaizhanViewportRight(200);
            scheduleItbaizhanViewportRight(900);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleItbaizhanViewportRight(300);
            scheduleItbaizhanViewportRight(1200);
            scheduleItbaizhanViewportRight(2500);
        });
        win.webContents.on('did-navigate', () => {
            scheduleItbaizhanViewportRight(500);
            scheduleItbaizhanViewportRight(1600);
        });
    }
    if (login_name == 'mashibing') {
        const scheduleMashibingPreload = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    preload_win_js();
                }
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleMashibingPreload(300);
            scheduleMashibingPreload(1200);
            scheduleMashibingPreload(2500);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleMashibingPreload(500);
            scheduleMashibingPreload(1800);
            scheduleMashibingPreload(3500);
            scheduleMashibingPreload(6500);
        });
        win.webContents.on('did-navigate', () => {
            scheduleMashibingPreload(800);
            scheduleMashibingPreload(2200);
            scheduleMashibingPreload(5000);
        });
    }
    if (login_name == 'nmkjxy') {
        const scheduleNmkjxyPreload = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    preload_win_js();
                }
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleNmkjxyPreload(300);
            scheduleNmkjxyPreload(900);
            scheduleNmkjxyPreload(1800);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleNmkjxyPreload(500);
            scheduleNmkjxyPreload(1500);
            scheduleNmkjxyPreload(3000);
            scheduleNmkjxyPreload(5500);
        });
        win.webContents.on('did-navigate', () => {
            scheduleNmkjxyPreload(600);
            scheduleNmkjxyPreload(1600);
            scheduleNmkjxyPreload(3500);
        });
    }
    if (login_name == 'ydshengxue') {
        win.webContents.on('did-finish-load', () => {
            setTimeout(preload_win_js, 800);
            setTimeout(preload_win_js, 2200);
        });
    }
    if (login_name == 'zixueb') {
        const scheduleZixuebLoginClick = (delay_ms) => {
            setTimeout(() => {
                if (!win.isDestroyed()) {
                    preload_win_js();
                }
            }, delay_ms);
        };
        win.webContents.on('dom-ready', () => {
            scheduleZixuebLoginClick(250);
            scheduleZixuebLoginClick(900);
        });
        win.webContents.on('did-finish-load', () => {
            scheduleZixuebLoginClick(400);
            scheduleZixuebLoginClick(1400);
            scheduleZixuebLoginClick(3000);
        });
        win.webContents.on('did-navigate', () => {
            scheduleZixuebLoginClick(600);
            scheduleZixuebLoginClick(1800);
        });
    }
    function preload_win_js() {
        if (!isWindowAlive(win)) {
            return;
        }
        if (login_name == 'shanxiang') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    var style = document.getElementById('xuewuzhi-shanxiang-login-fix');
                    if (!style) {
                        style = document.createElement('style');
                        style.id = 'xuewuzhi-shanxiang-login-fix';
                        (document.head || document.documentElement).appendChild(style);
                    }
                    style.textContent = [
                        'html,body{min-width:0!important;overflow-x:hidden!important;}',
                        '.all-header,.head-app-member,.head-app-layout,.fix-left,.fix-box,#jesong_panel,.jesong_pan_icon{display:none!important;}',
                        '.backimg{min-width:0!important;width:100%!important;height:auto!important;min-height:100vh!important;padding:20px 0 60px!important;box-sizing:border-box!important;}',
                        '.cnt1200{width:100%!important;max-width:100%!important;min-width:0!important;}',
                        '.new-login-layout{top:0!important;margin:0 auto 40px!important;}'
                    ].join('');
                    var panel = document.querySelector('.new-login-layout') || document.querySelector('.js-login-form');
                    if (!panel) {
                        return;
                    }
                    requestAnimationFrame(function () {
                        var rect = panel.getBoundingClientRect();
                        var top = window.pageYOffset + rect.top - Math.max(20, (window.innerHeight - rect.height) / 2);
                        window.scrollTo(0, Math.max(0, top));
                    });
                })();
                `
            );
        } else if (login_name == 'xuetangx' || login_name == 'xuetangx.gradsmartedu') {
            win.webContents.executeJavaScript(
                `
                var login_btn = document.getElementsByClassName("h_login_login")[0];
                if (login_btn) {
                    login_btn.click();
                }
                `
            );
        } else if  (login_name == 'imooc') {
            win.webContents.executeJavaScript(
                `
                var login_btn = document.getElementById("js-signin-btn");
                if (login_btn) {
                    login_btn.click();
                }
                `
            );
        } else if  (login_name == 'keqq') {
            win.webContents.executeJavaScript(
                `
                var login_btn = document.getElementsByClassName("btn")[0];
                if (login_btn) {
                    login_btn.click();
                }
                `
            );
        } else if  (login_name == 'study163') {
            win.webContents.executeJavaScript(
                `
                var login_btn = document.getElementsByClassName("ux-btn")[0];
                if (login_btn) {
                    login_btn.click();
                }
                `
            );
        } else if  (login_name.includes('xiaoetech')) {
            if (xiaoe_tech && xiaoetech_login_mode == 'web') {
                win.webContents.executeJavaScript(
                    `
                    window.scrollTo(document.body.scrollWidth, 0);
                    `
                );
            } else if (is_xiaoe_pc) {
                win.webContents.executeJavaScript(
                    `
                    var login_btn = document.getElementsByClassName("func")[0];
                    if (login_btn) {
                        login_btn.click();
                    } else {
                        login_btn = document.getElementsByClassName("xe-navigation__item")[2];
                        if (login_btn) {
                            login_btn.click();
                        }
                    }
                    `
                );
            }
        } else if  (login_name.includes('baijiayunxiao')) {
            win.webContents.executeJavaScript(
                `
                var login_btn = document.getElementsByClassName("lnk-login-register")[0];
                if (login_btn) {
                    login_btn.click();
                }
                `
            );
        } else if (login_name == 'yunduan') {
            suppressYunduanDeviceCheckPopup(win);
        } else if (login_name == 'bilibili') {
            win.webContents.executeJavaScript(
                `
                var login_btn_div = document.getElementsByClassName("header-login-entry")[0];
                if (login_btn_div) {
                    login_btn_div.click();
                }
                `
            );
        } else if  (login_name == 'icourse163' || login_name == 'koolearn' || login_name == 'eoffcn' || login_name.includes('xiwang') || login_name == 'hqwx' || login_name == 'xueersi' || login_name == 'zlketang' || login_name == 'med66' || login_name == 'zhengbao' || login_name == 'jianshe99' || login_name == '51cto' || login_name == '51zxw' || login_name == 'wangxiao233' || login_name == 'wrclass' || login_name == 'youlu') {
            win.webContents.executeJavaScript(
                `
                window.scrollTo(document.body.scrollWidth, 0);
                `
            );
        } else if (login_name == 'huatu') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    function isVisible(el) {
                        if (!el) {
                            return false;
                        }
                        var style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        return el.getClientRects().length > 0;
                    }

                    function maybeClick(target) {
                        if (!target || !isVisible(target)) {
                            return false;
                        }
                        var originalTarget = target;
                        if ((target.tagName === 'SPAN' || target.tagName === 'B' || target.tagName === 'STRONG') && target.parentElement && isVisible(target.parentElement)) {
                            target = target.parentElement;
                        }
                        try {
                            target.click();
                        } catch (error) {
                            ;
                        }
                        try {
                            target.dispatchEvent(new MouseEvent('click', {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            }));
                        } catch (error) {
                            ;
                        }
                        try {
                            if (window.jQuery && originalTarget) {
                                window.jQuery(originalTarget).trigger('click');
                                if (target !== originalTarget) {
                                    window.jQuery(target).trigger('click');
                                }
                            }
                        } catch (error) {
                            ;
                        }
                        return true;
                    }

                    function isLoggedIn() {
                        return !!document.querySelector('.logout,.fun_login_avatar,.fun_login_drag,[class*="logout"],[class*="avatar"],[class*="userInfo"],[class*="user-info"]');
                    }

                    function hasLoginPanel() {
                        var selectors = [
                            '#loginDialog',
                            '[id*="loginDialog"]',
                            '[class*="loginDialog"]',
                            '[class*="login-dialog"]',
                            '[class*="login_box"]',
                            '[class*="login-box"]',
                            '#loginDialog input',
                            '#loginDialog a',
                            '#loginDialog button',
                            '[class*="login_box"] input',
                            '[class*="login-box"] input'
                        ];
                        for (var i = 0; i < selectors.length; i++) {
                            var candidate = document.querySelector(selectors[i]);
                            if (candidate && isVisible(candidate)) {
                                return true;
                            }
                        }
                        return false;
                    }

                    function tryOpenLogin() {
                        if (isLoggedIn() || hasLoginPanel()) {
                            return true;
                        }

                        var exactLoginEntry = document.getElementById('loginEntry');
                        if (maybeClick(exactLoginEntry) && hasLoginPanel()) {
                            return true;
                        }

                        var selectors = [
                            '#loginEntry',
                            '#loginReg .fun_entry',
                            '#loginReg .fun_entry span',
                            '.login-btn',
                            '.loginBtn',
                            '[class*="header"] [class*="login"]',
                            '[class*="top"] [class*="login"]',
                            '[class*="nav"] [class*="login"]',
                            'button[data-track*="login"]',
                            'a[data-track*="login"]',
                            'a[href*="login"]'
                        ];
                        for (var i = 0; i < selectors.length; i++) {
                            var loginBtn = document.querySelector(selectors[i]);
                            if (!maybeClick(loginBtn)) {
                                continue;
                            }
                            if (hasLoginPanel()) {
                                return true;
                            }
                        }

                        var roots = [
                            document.querySelector('.htzxHeader'),
                            document.querySelector('.g-header-wrap'),
                            document.querySelector('.htzxWrap'),
                            document.querySelector('header'),
                            document.querySelector('[class*="header"]'),
                            document.querySelector('[class*="top"]'),
                            document.querySelector('[class*="nav"]'),
                            document.body
                        ];
                        for (var rootIndex = 0; rootIndex < roots.length; rootIndex++) {
                            var root = roots[rootIndex];
                            if (!root) {
                                continue;
                            }
                            var clickables = root.querySelectorAll('button,a,div,span,strong,b,i,em,p,li');
                            for (var j = 0; j < clickables.length; j++) {
                                var item = clickables[j];
                                if (!isVisible(item)) {
                                    continue;
                                }
                                var text = (item.innerText || item.textContent || '').replace(/\\s+/g, '');
                                if (!text || text.indexOf('登录') === -1) {
                                    continue;
                                }
                                if (text.length > 10) {
                                    continue;
                                }
                                var rect = item.getBoundingClientRect();
                                if (rect.top > Math.max(window.innerHeight * 0.42, 260)) {
                                    continue;
                                }
                                if (root !== document.body && rect.left < window.innerWidth * 0.42) {
                                    continue;
                                }
                                if (maybeClick(item) && hasLoginPanel()) {
                                    return true;
                                }
                            }
                        }
                        return hasLoginPanel() || isLoggedIn();
                    }

                    if (!window.__xwzHuatuAutoOpenLogin) {
                        window.__xwzHuatuAutoOpenLogin = {
                            tries: 0,
                            timer: null,
                            observer: null
                        };
                    }
                    var state = window.__xwzHuatuAutoOpenLogin;

                    function stopWatching() {
                        if (state.timer) {
                            clearInterval(state.timer);
                            state.timer = null;
                        }
                        if (state.observer) {
                            state.observer.disconnect();
                            state.observer = null;
                        }
                    }

                    stopWatching();
                    if (tryOpenLogin()) {
                        return;
                    }

                    if (typeof MutationObserver !== 'undefined') {
                        var observerTarget = document.getElementById('app') || document.getElementById('root') || document.body;
                        if (observerTarget) {
                            state.observer = new MutationObserver(function () {
                                if (tryOpenLogin()) {
                                    stopWatching();
                                }
                            });
                            state.observer.observe(observerTarget, {
                                childList: true,
                                subtree: true
                            });
                        }
                    }

                    state.tries = 0;
                    state.timer = setInterval(function () {
                        state.tries += 1;
                        if (tryOpenLogin() || state.tries >= 25) {
                            stopWatching();
                        }
                    }, 700);
                })();
                `,
                true
            ).catch(() => {});
        } else if (login_name == 'houda') {
            openHoudaLoginDialog(win);
        } else if (login_name == 'yijiayk') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    function isVisible(el) {
                        if (!el) {
                            return false;
                        }
                        var style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        return el.getClientRects().length > 0;
                    }

                    function maybeClick(target) {
                        if (!target || !isVisible(target)) {
                            return false;
                        }
                        target.click();
                        target.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));
                        return true;
                    }

                    var loginBtn = document.querySelector('[class*="login"]')
                        || document.querySelector('[id*="login"]');

                    if (loginBtn && maybeClick(loginBtn)) {
                        return;
                    }

                    var header = document.querySelector('header,[class*="header"],[class*="nav"]') || document.body;
                    var clickables = header.querySelectorAll('button,a,div,span');
                    for (var i = 0; i < clickables.length; i++) {
                        var item = clickables[i];
                        if (!isVisible(item)) {
                            continue;
                        }
                        var text = (item.innerText || item.textContent || '').replace(/\\s+/g, '');
                        if (text !== '登录') {
                            continue;
                        }
                        var rect = item.getBoundingClientRect();
                        if (rect.top > Math.max(window.innerHeight * 0.35, 220)) {
                            continue;
                        }
                        if (rect.left < window.innerWidth * 0.55) {
                            continue;
                        }
                        maybeClick(item);
                        break;
                    }
                })();
                `
            );
        } else if (login_name == 'wowtiku') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    function isVisible(el) {
                        if (!el) {
                            return false;
                        }
                        var style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        return el.getClientRects().length > 0;
                    }

                    function maybeClick(target) {
                        if (!target || !isVisible(target)) {
                            return false;
                        }
                        if ((target.tagName === 'SPAN' || target.tagName === 'B' || target.tagName === 'I') && target.parentElement && isVisible(target.parentElement)) {
                            target = target.parentElement;
                        }
                        try {
                            target.click();
                        } catch (error) {
                            ;
                        }
                        try {
                            target.dispatchEvent(new MouseEvent('click', {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            }));
                        } catch (error) {
                            ;
                        }
                        return true;
                    }

                    function hasLoginPanel() {
                        return !!Array.from(document.querySelectorAll(
                            '.el-dialog,.van-popup,.popup,.login-box,.login_box,[class*="login"],input[type="password"],input[placeholder*="手机"],input[placeholder*="验证码"]'
                        )).find(function (node) {
                            if (!isVisible(node)) {
                                return false;
                            }
                            var rect = node.getBoundingClientRect();
                            return rect.width > 80 && rect.height > 28;
                        });
                    }

                    if (hasLoginPanel()) {
                        return;
                    }

                    var selectors = [
                        '.login',
                        '.login-btn',
                        '.loginBtn',
                        '.login-button',
                        '[class*="login"]',
                        '[class*="Login"]',
                        'button',
                        'a',
                        'div',
                        'span'
                    ];

                    var candidates = [];
                    selectors.forEach(function (selector) {
                        Array.from(document.querySelectorAll(selector)).forEach(function (node) {
                            if (candidates.indexOf(node) === -1) {
                                candidates.push(node);
                            }
                        });
                    });

                    var bestNode = null;
                    var bestScore = -1;
                    candidates.forEach(function (node) {
                        if (!isVisible(node)) {
                            return;
                        }
                        var text = (node.innerText || node.textContent || '').replace(/\s+/g, '');
                        var className = String(node.className || '');
                        var id = String(node.id || '');
                        if (text.indexOf('登录') === -1 && text.indexOf('登陆') === -1 && !/login/i.test(className + ' ' + id)) {
                            return;
                        }
                        var rect = node.getBoundingClientRect();
                        if (rect.width < 20 || rect.height < 16) {
                            return;
                        }
                        var centerX = rect.left + rect.width / 2;
                        var centerY = rect.top + rect.height / 2;
                        var distance = Math.abs(centerX - window.innerWidth / 2) + Math.abs(centerY - window.innerHeight / 2);
                        var score = 100000 - distance;
                        if (text === '登录' || text === '登陆') {
                            score += 2000;
                        }
                        if (/login/i.test(className + ' ' + id)) {
                            score += 800;
                        }
                        if (rect.top > window.innerHeight * 0.15 && rect.top < window.innerHeight * 0.85) {
                            score += 500;
                        }
                        if (score > bestScore) {
                            bestScore = score;
                            bestNode = node;
                        }
                    });

                    if (maybeClick(bestNode)) {
                        return;
                    }

                    var centerNode = document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2);
                    while (centerNode && centerNode !== document.body) {
                        var centerText = (centerNode.innerText || centerNode.textContent || '').replace(/\s+/g, '');
                        if (centerText.indexOf('登录') !== -1 || centerText.indexOf('登陆') !== -1 || /login/i.test(String(centerNode.className || '') + ' ' + String(centerNode.id || ''))) {
                            maybeClick(centerNode);
                            return;
                        }
                        centerNode = centerNode.parentElement;
                    }
                })();
                `
            );
        } else if (login_name == 'yikao88') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    function isVisible(el) {
                        if (!el) {
                            return false;
                        }
                        var style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        return el.getClientRects().length > 0;
                    }

                    function maybeClick(target) {
                        if (!target || !isVisible(target)) {
                            return false;
                        }
                        if (target.tagName === 'SPAN' && target.parentElement) {
                            target = target.parentElement;
                        }
                        target.click();
                        target.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));
                        return true;
                    }

                    var loginPageReady = !!(
                        document.querySelector('input[type="password"]')
                        || document.querySelector('input[placeholder*="手机号"],input[placeholder*="验证码"]')
                        || document.querySelector('#login_container canvas,#login_container iframe')
                    );
                    if ((window.location.pathname || '').indexOf('/login') !== -1 && loginPageReady) {
                        return;
                    }

                    var selectors = [
                        '.person1 .login-group b',
                        '.person1 .login-group span',
                        '.login-group b',
                        '.login-group span',
                        '[class*="login-group"] b',
                        '[class*="login-group"] span'
                    ];
                    for (var i = 0; i < selectors.length; i++) {
                        var candidate = document.querySelector(selectors[i]);
                        if (!isVisible(candidate)) {
                            continue;
                        }
                        var text = (candidate.innerText || candidate.textContent || '').replace(/\\s+/g, '');
                        if (text.indexOf('登录') === -1) {
                            continue;
                        }
                        if (maybeClick(candidate)) {
                            return;
                        }
                    }

                    var area = document.querySelector('.person1,.shouyebanner,.shouyebanner-box,[class*="banner"],header,[class*="header"]') || document.body;
                    var clickables = area.querySelectorAll('button,a,div,span,b');
                    for (var j = 0; j < clickables.length; j++) {
                        var item = clickables[j];
                        if (!isVisible(item)) {
                            continue;
                        }
                        var itemText = (item.innerText || item.textContent || '').replace(/\\s+/g, '');
                        if (itemText !== '登录') {
                            continue;
                        }
                        var rect = item.getBoundingClientRect();
                        if (rect.top > Math.max(window.innerHeight * 0.8, 560)) {
                            continue;
                        }
                        if (rect.left < window.innerWidth * 0.55) {
                            continue;
                        }
                        if (maybeClick(item)) {
                            break;
                        }
                    }
                })();
                `
            );
        } else if (login_name == 'tmooc') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    function isVisible(el) {
                        if (!el) {
                            return false;
                        }
                        var style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        return el.getClientRects().length > 0;
                    }

                    function maybeClick(target) {
                        if (!target || !isVisible(target)) {
                            return false;
                        }
                        target.click();
                        target.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));
                        return true;
                    }

                    var loginDialog = document.querySelector('#login_boxxxw,#login_boxxxw2222,.js-md-180417-login-cj,.js-md-180417-login-cj2');
                    if (isVisible(loginDialog)) {
                        return;
                    }

                    var loginBtn = document.getElementById('login_xxw')
                        || document.querySelector('#login_statelty .no-login #login_xxw')
                        || document.querySelector('#login_statelty .no-login li:last-child a');

                    if (loginBtn && maybeClick(loginBtn)) {
                        return;
                    }

                    var header = document.querySelector('#login_statelty .no-login,.login-area,#no-login-nav,header,[class*="header"],[class*="top"],[class*="nav"]') || document.body;
                    var clickables = header.querySelectorAll('button,a,div,span');
                    for (var i = 0; i < clickables.length; i++) {
                        var item = clickables[i];
                        if (!isVisible(item)) {
                            continue;
                        }
                        var text = (item.innerText || item.textContent || '').replace(/\\s+/g, '');
                        if (text.indexOf('登录') === -1) {
                            continue;
                        }
                        var rect = item.getBoundingClientRect();
                        if (rect.top > Math.max(window.innerHeight * 0.35, 220)) {
                            continue;
                        }
                        if (rect.left < window.innerWidth * 0.55) {
                            continue;
                        }
                        if (maybeClick(item)) {
                            break;
                        }
                    }
                })();
                `
            );
        } else if (login_name == 'youku') {
            win.webContents.executeJavaScript(
                `
                var login_btn_div = document.getElementsByClassName("crmusercenter_avatar")[0];
                if (login_btn_div) {
                    login_btn_div.click();
                }
                `
            );
        } else if (login_name == 'vqq') {
            win.webContents.executeJavaScript(
                `
                var login_btn = document.getElementsByClassName("btn_pop_link")[0];
                if (login_btn) {
                    login_btn.click();
                }
                `
            );
        } else if (login_name == 'icve') {
            win.webContents.executeJavaScript(
                `
                var login_btn = document.getElementById("btn-login");
                if (login_btn) {
                    login_btn.click();
                }
                `
            );
        } else if (login_name.includes('gaotu')) {
            win.webContents.executeJavaScript(
                `
                var login_btn = document.getElementsByClassName("icon-guanbi")[1];
                if (login_btn) {
                    login_btn.click();
                }
                `
            );
        } else if (login_name == 'ydshengxue') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    function isVisible(el) {
                        if (!el) {
                            return false;
                        }
                        var style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        return el.getClientRects().length > 0;
                    }

                    function maybeClick(target) {
                        if (!target || !isVisible(target)) {
                            return false;
                        }
                        if (target.tagName === 'SPAN' && target.parentElement && isVisible(target.parentElement)) {
                            target = target.parentElement;
                        }
                        target.click();
                        target.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));
                        return true;
                    }

                    function hasLoginPanel() {
                        var selectors = [
                            '#mobileLogin',
                            '[id*="mobileLogin"]',
                            'input[type="password"]',
                            'input[placeholder*="手机号"]',
                            'input[placeholder*="验证码"]',
                            'input[placeholder*="短信"]',
                            'input[placeholder*="账号"]',
                            'iframe[src*="reg.163.com"]',
                            'iframe[src*="urs"]',
                            '[class*="loginDialog"]',
                            '[class*="login-dialog"]',
                            '[class*="loginModal"]',
                            '[class*="login-modal"]',
                            '[class*="login_box"]',
                            '[class*="login-box"]'
                        ];
                        for (var i = 0; i < selectors.length; i++) {
                            var candidate = document.querySelector(selectors[i]);
                            if (candidate && (candidate.tagName === 'INPUT' || isVisible(candidate))) {
                                return true;
                            }
                        }
                        return false;
                    }

                    function tryOpenLogin() {
                        if (hasLoginPanel()) {
                            return true;
                        }

                        var selectors = [
                            'button.OT9T9',
                            '.QuNnH button.OT9T9',
                            '.QuNnH span._1X0al',
                            '._8516S button.OT9T9',
                            '._8516S span._1X0al',
                            '.index_login__yqc2t',
                            '[class*="index_login"]',
                            '[class*="loginBtn"]',
                            '[class*="login-btn"]',
                            '[class*="login_btn"]',
                            '[class*="header"] [class*="login"]',
                            'header [class*="login"]',
                            '.header [class*="login"]',
                            '.top [class*="login"]',
                            '.nav [class*="login"]'
                        ];
                        for (var i = 0; i < selectors.length; i++) {
                            var candidate = document.querySelector(selectors[i]);
                            if (maybeClick(candidate)) {
                                return true;
                            }
                        }

                        var roots = [
                            document.querySelector('._8516S'),
                            document.querySelector('.QuNnH'),
                            document.querySelector('header'),
                            document.querySelector('[class*="header"]'),
                            document.querySelector('[class*="top"]'),
                            document.querySelector('[class*="nav"]'),
                            document.body
                        ];
                        for (var rootIndex = 0; rootIndex < roots.length; rootIndex++) {
                            var root = roots[rootIndex];
                            if (!root) {
                                continue;
                            }
                            var clickables = root.querySelectorAll('button,a,div,span');
                            for (var j = 0; j < clickables.length; j++) {
                                var item = clickables[j];
                                if (!isVisible(item)) {
                                    continue;
                                }
                                var text = (item.innerText || item.textContent || '').replace(/\\s+/g, '');
                                if (!text) {
                                    continue;
                                }
                                if (text.indexOf('登录') === -1
                                    && text.indexOf('去登录') === -1
                                    && text.indexOf('立即登录') === -1
                                    && text.indexOf('请登录') === -1) {
                                    continue;
                                }
                                var rect = item.getBoundingClientRect();
                                if (rect.top > Math.max(window.innerHeight * 0.45, 260)) {
                                    continue;
                                }
                                if (root !== document.body && rect.left < window.innerWidth * 0.45) {
                                    continue;
                                }
                                if (maybeClick(item)) {
                                    return true;
                                }
                            }
                        }

                        return hasLoginPanel();
                    }

                    if (!window.__xwzYdshengxueAutoOpenLogin) {
                        window.__xwzYdshengxueAutoOpenLogin = {
                            tries: 0,
                            timer: null,
                            observer: null
                        };
                    }
                    var state = window.__xwzYdshengxueAutoOpenLogin;
                    function stopWatching() {
                        if (state.timer) {
                            clearInterval(state.timer);
                            state.timer = null;
                        }
                        if (state.observer) {
                            state.observer.disconnect();
                            state.observer = null;
                        }
                    }

                    stopWatching();

                    if (tryOpenLogin()) {
                        return;
                    }

                    if (typeof MutationObserver !== 'undefined') {
                        var observerTarget = document.getElementById('root') || document.body;
                        if (observerTarget) {
                            state.observer = new MutationObserver(function () {
                                if (tryOpenLogin()) {
                                    stopWatching();
                                }
                            });
                            state.observer.observe(observerTarget, {
                                childList: true,
                                subtree: true
                            });
                        }
                    }

                    state.tries = 0;
                    state.timer = setInterval(function () {
                        state.tries += 1;
                        if (tryOpenLogin() || state.tries >= 25) {
                            stopWatching();
                        }
                    }, 800);
                })();
                `
            );
        } else if (login_name == 'open163') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    var LOGIN_TEXT = '\u767b\u5f55';
                    var PLEASE_LOGIN_TEXT = '\u8bf7\u767b\u5f55';
                    var LOGIN_NOW_TEXT = '\u7acb\u5373\u767b\u5f55';
                    var LOGIN_REGISTER_TEXT = '\u767b\u5f55\u6ce8\u518c';
                    var LOGIN_SLASH_REGISTER_TEXT = '\u767b\u5f55/\u6ce8\u518c';
                    var REGISTER_SLASH_LOGIN_TEXT = '\u6ce8\u518c/\u767b\u5f55';

                    function isVisible(el) {
                        if (!el) {
                            return false;
                        }
                        var style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        return el.getClientRects().length > 0;
                    }

                    function hasLoginPanel() {
                        var selectors = [
                            'iframe.page',
                            'iframe[src*="login_common"]',
                            'iframe[src*="reg.163.com"]',
                            'iframe[src*="urs"]',
                            'input[type="password"]',
                            'input[placeholder*="手机号"]',
                            'input[placeholder*="验证码"]',
                            'input[placeholder*="账号"]',
                            '[class*="loginDialog"]',
                            '[class*="login-dialog"]',
                            '[class*="loginModal"]',
                            '[class*="login-modal"]'
                        ];
                        for (var i = 0; i < selectors.length; i++) {
                            var target = document.querySelector(selectors[i]);
                            if (target && (target.tagName === 'INPUT' || isVisible(target))) {
                                return true;
                            }
                        }
                        return false;
                    }

                    function callOpenCourseLogin() {
                        try {
                            if (window.openCourse && window.openCourse._urs && typeof window.openCourse._urs.showIframe === 'function') {
                                window.openCourse._urs.showIframe();
                                return hasLoginPanel();
                            }
                            if (window.openCourse && window.openCourse._ursInstance && typeof window.openCourse._ursInstance.showIframe === 'function') {
                                window.openCourse._ursInstance.showIframe();
                                return hasLoginPanel();
                            }
                            if (window.openCourse && window.openCourse.ui && typeof window.openCourse.ui.loginui === 'function') {
                                window.openCourse.ui.loginui();
                                return hasLoginPanel();
                            }
                        } catch (error) {
                            ;
                        }
                        return false;
                    }

                    function clickLogin(target) {
                        if (!target || !isVisible(target)) {
                            return false;
                        }
                        try {
                            target.click();
                            target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                            return true;
                        } catch (error) {
                            return false;
                        }
                    }

                    function normalizeText(node) {
                        return (node && (node.innerText || node.textContent || '') || '').replace(/\s+/g, '');
                    }

                    function isLoginText(text) {
                        return text === LOGIN_TEXT
                            || text === PLEASE_LOGIN_TEXT
                            || text === LOGIN_NOW_TEXT
                            || text === LOGIN_REGISTER_TEXT
                            || text === LOGIN_SLASH_REGISTER_TEXT
                            || text === REGISTER_SLASH_LOGIN_TEXT;
                    }

                    function tryOpenLogin() {
                        if (hasLoginPanel()) {
                            return true;
                        }
                        if (callOpenCourseLogin()) {
                            return true;
                        }
                        var selectors = [
                            '.MyOpenHeader_login',
                            '.mine-login',
                            '[class*="mine-login"]',
                            '[class*="Mine"] [class*="login"]',
                            '[class*="mine"] [class*="login"]',
                            '[class*="login"]',
                            '#j-topnav a',
                            '#j-topnav span',
                            '.m-topnav a',
                            '.m-topnav span',
                            '.m-header a',
                            '.m-header span',
                            'header a',
                            'header button',
                            'header span',
                            '.m-head a',
                            '.m-head button',
                            '.m-head span',
                            '.u-nav a',
                            '.u-nav button',
                            '.u-nav span'
                        ];
                        for (var i = 0; i < selectors.length; i++) {
                            var nodes = document.querySelectorAll(selectors[i]);
                            for (var j = 0; j < nodes.length; j++) {
                                var node = nodes[j];
                                var text = normalizeText(node);
                                if ((isLoginText(text) || text.indexOf(LOGIN_TEXT) !== -1) && clickLogin(node)) {
                                    return true;
                                }
                            }
                        }
                        var clickables = document.querySelectorAll('a,button,span,div,p,li');
                        var candidates = [];
                        for (var k = 0; k < clickables.length; k++) {
                            var item = clickables[k];
                            if (!isVisible(item)) {
                                continue;
                            }
                            var itemText = normalizeText(item);
                            if (!isLoginText(itemText)) {
                                continue;
                            }
                            var rect = item.getBoundingClientRect();
                            if (rect.top > Math.max(window.innerHeight * 0.42, 320)) {
                                continue;
                            }
                            candidates.push({
                                node: item,
                                score: rect.top - rect.left / 100 + (itemText === LOGIN_TEXT ? 0 : 5)
                            });
                        }
                        candidates.sort(function (a, b) { return a.score - b.score; });
                        for (var c = 0; c < candidates.length; c++) {
                            if (clickLogin(candidates[c].node)) {
                                return true;
                            }
                        }
                        return hasLoginPanel();
                    }

                    if (!window.__xwzOpen163AutoOpenLogin) {
                        window.__xwzOpen163AutoOpenLogin = { tries: 0, timer: null, observer: null };
                    }
                    var state = window.__xwzOpen163AutoOpenLogin;
                    function stopWatching() {
                        if (state.timer) {
                            clearInterval(state.timer);
                            state.timer = null;
                        }
                        if (state.observer) {
                            state.observer.disconnect();
                            state.observer = null;
                        }
                    }
                    stopWatching();
                    if (tryOpenLogin()) {
                        return;
                    }
                    if (typeof MutationObserver !== 'undefined') {
                        state.observer = new MutationObserver(function () {
                            if (tryOpenLogin()) {
                                stopWatching();
                            }
                        });
                        state.observer.observe(document.body, { childList: true, subtree: true });
                    }
                    state.tries = 0;
                    state.timer = setInterval(function () {
                        state.tries += 1;
                        if (tryOpenLogin() || state.tries >= 45) {
                            stopWatching();
                        }
                    }, 800);
                })();
                `
            );
        } else if (login_name == 'nmkjxy') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    var LOGIN = '\u767b\u5f55';
                    var REGISTER = '\u6ce8\u518c';
                    var LOGIN_REGISTER = '\u767b\u5f55/\u6ce8\u518c';
                    var LOGGED_IN = '\u5df2\u767b\u5f55';
                    var LOGOUT = '\u9000\u51fa\u767b\u5f55';
                    var WECHAT_LOGIN = '\u5fae\u4fe1\u626b\u7801\u767b\u5f55';
                    var PHONE = '\u624b\u673a\u53f7';
                    var VERIFY_CODE = '\u9a8c\u8bc1\u7801';
                    var ACCOUNT_LOGIN = '\u8d26\u53f7\u767b\u5f55';
                    var USER_AGREEMENT = '\u7528\u6237\u534f\u8bae';
                    var PRIVACY_POLICY = '\u9690\u79c1\u653f\u7b56';
                    var AGREE = '\u540c\u610f';
                    var CONFIRM = '\u786e\u5b9a';
                    var KNOWN = '\u6211\u77e5\u9053\u4e86';
                    var READ_AND_AGREE = '\u9605\u8bfb\u5e76\u540c\u610f';
                    function isVisible(el) {
                        if (!el) {
                            return false;
                        }
                        var style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                            return false;
                        }
                        var rect = el.getBoundingClientRect();
                        return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
                    }
                    function textOf(el) {
                        return String((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, '');
                    }
                    function readToken() {
                        try {
                            var direct = localStorage.getItem('token') || sessionStorage.getItem('token') || '';
                            if (direct) {
                                return direct;
                            }
                            for (var i = 0; i < localStorage.length; i++) {
                                var key = localStorage.key(i);
                                if (key && String(key).toLowerCase() === 'token') {
                                    var value = localStorage.getItem(key);
                                    if (value) {
                                        return value;
                                    }
                                }
                            }
                        } catch (error) {
                            ;
                        }
                        return '';
                    }
                    function hasLoginPanel() {
                        var selectors = [
                            'kjxy-desktop-login-modal',
                            '.login .login-plan',
                            '.login-plan',
                            '.login-box .login',
                            '.login-box',
                            '[class*=login-modal]',
                            '[class*=LoginModal]',
                            '[class*=login-dialog]',
                            '[class*=LoginDialog]'
                        ];
                        for (var i = 0; i < selectors.length; i++) {
                            var nodes = document.querySelectorAll(selectors[i]);
                            for (var j = 0; j < nodes.length; j++) {
                                var text = textOf(nodes[j]);
                                if (isVisible(nodes[j]) && (text.indexOf(WECHAT_LOGIN) !== -1 || text.indexOf(PHONE) !== -1 || text.indexOf(VERIFY_CODE) !== -1 || text.indexOf(ACCOUNT_LOGIN) !== -1)) {
                                    return true;
                                }
                            }
                        }
                        return false;
                    }
                    function clickElement(el) {
                        if (!el) {
                            return false;
                        }
                        try {
                            el.scrollIntoView({ block: 'center', inline: 'center' });
                        } catch (error) {
                            ;
                        }
                        try {
                            el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                        } catch (error) {
                            ;
                        }
                        try {
                            if (typeof el.click === 'function') {
                                el.click();
                            }
                        } catch (error) {
                            ;
                        }
                        return true;
                    }
                    function confirmAgreementPopup() {
                        var panels = Array.prototype.slice.call(document.querySelectorAll('.ant-modal,.el-dialog,.ivu-modal,.van-dialog,[role=dialog],[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog],[class*=popup],[class*=Popup],[class*=mask],[class*=Mask]'));
                        panels.push(document.body);
                        var confirmTexts = [AGREE, CONFIRM, KNOWN, READ_AND_AGREE, AGREE + '\u5e76\u7ee7\u7eed', AGREE + '\u5e76\u767b\u5f55'];
                        for (var i = 0; i < panels.length; i++) {
                            var panel = panels[i];
                            if (!panel || !isVisible(panel)) {
                                continue;
                            }
                            var panelText = textOf(panel);
                            if (panelText.indexOf(USER_AGREEMENT) === -1 && panelText.indexOf(PRIVACY_POLICY) === -1) {
                                continue;
                            }
                            var buttons = panel.querySelectorAll('button,.ant-btn,.el-button,.ivu-btn,.van-button,[role=button],a,span,div');
                            for (var j = 0; j < buttons.length; j++) {
                                var node = buttons[j];
                                if (!isVisible(node)) {
                                    continue;
                                }
                                var text = textOf(node);
                                for (var k = 0; k < confirmTexts.length; k++) {
                                    if (text === confirmTexts[k] || text.indexOf(confirmTexts[k]) !== -1) {
                                        clickElement(node);
                                        return true;
                                    }
                                }
                            }
                        }
                        return false;
                    }
                    function closeBlockingPopups() {
                        var loginTexts = [LOGIN, LOGIN_REGISTER, WECHAT_LOGIN, VERIFY_CODE + LOGIN, ACCOUNT_LOGIN];
                        var closeSelectors = [
                            '.ant-modal-close', '.ant-modal-close-x', '.ant-drawer-close', '.modal-close', '.dialog-close',
                            '.popup-close', '.close-btn', '.close', '[class*=close]', '[class*=Close]',
                            'button[aria-label=Close]', 'button[aria-label=close]'
                        ];
                        var closed = false;
                        for (var i = 0; i < closeSelectors.length; i++) {
                            var nodes = document.querySelectorAll(closeSelectors[i]);
                            for (var j = 0; j < nodes.length; j++) {
                                var node = nodes[j];
                                if (!isVisible(node)) {
                                    continue;
                                }
                                var panel = node.closest && node.closest('.ant-modal,.ant-drawer,[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog],[class*=popup],[class*=Popup],[class*=mask],[class*=Mask]');
                                var panelText = textOf(panel || node.parentElement || document.body);
                                var isLoginPanel = false;
                                for (var k = 0; k < loginTexts.length; k++) {
                                    if (panelText.indexOf(loginTexts[k]) !== -1) {
                                        isLoginPanel = true;
                                        break;
                                    }
                                }
                                if (isLoginPanel || panelText.indexOf(PHONE) !== -1 || panelText.indexOf(VERIFY_CODE) !== -1) {
                                    continue;
                                }
                                var rect = node.getBoundingClientRect();
                                if (rect.top > window.innerHeight || rect.left > window.innerWidth) {
                                    continue;
                                }
                                clickElement(node);
                                closed = true;
                            }
                        }
                        return closed;
                    }
                    function findLoginButtonBySelector() {
                        var selectors = [
                            '.not-login',
                            '.not-login-box .not-login',
                            '.logincard .not-login',
                            '.login-card .not-login',
                            '[class*=not-login]',
                            '[class*=login-register]',
                            '[class*=loginBtn]',
                            '[class*=login-btn]',
                            '[class*=login_btn]',
                            '[class*=LoginBtn]',
                            '[class*=header] [class*=login]',
                            '[class*=nav] [class*=login]'
                        ];
                        for (var i = 0; i < selectors.length; i++) {
                            var nodes = document.querySelectorAll(selectors[i]);
                            for (var j = 0; j < nodes.length; j++) {
                                var node = nodes[j];
                                if (!isVisible(node)) {
                                    continue;
                                }
                                var text = textOf(node);
                                if (text.indexOf(LOGGED_IN) !== -1 || text.indexOf(LOGOUT) !== -1) {
                                    continue;
                                }
                                if (text.indexOf(LOGIN) !== -1 || text.indexOf(REGISTER) !== -1 || /not-login|login/i.test(String(node.className || ''))) {
                                    return node;
                                }
                            }
                        }
                        return null;
                    }
                    function findLoginButtonByText() {
                        var roots = ['.logincard', '[class*=login]', '[class*=header]', '[class*=nav]', '[class*=top]', 'body'];
                        var candidates = [];
                        for (var r = 0; r < roots.length; r++) {
                            var root = document.querySelector(roots[r]);
                            if (!root) {
                                continue;
                            }
                            var nodes = root.querySelectorAll('button,a,div,span,p');
                            for (var i = 0; i < nodes.length; i++) {
                                var node = nodes[i];
                                if (!isVisible(node)) {
                                    continue;
                                }
                                var text = textOf(node);
                                if (!text || text.indexOf(LOGIN) === -1 || text.indexOf(LOGGED_IN) !== -1 || text.indexOf(LOGOUT) !== -1) {
                                    continue;
                                }
                                if (text.length > 30 && text.indexOf(LOGIN_REGISTER) === -1) {
                                    continue;
                                }
                                var rect = node.getBoundingClientRect();
                                var score = 0;
                                if (text === LOGIN_REGISTER || text === LOGIN) {
                                    score += 200;
                                }
                                if (String(node.className || '').indexOf('not-login') !== -1) {
                                    score += 180;
                                }
                                if (node.closest && node.closest('.logincard')) {
                                    score += 120;
                                }
                                score += Math.max(0, rect.right) / Math.max(1, window.innerWidth) * 50;
                                score -= Math.max(0, rect.top) / 20;
                                candidates.push({ node: node, score: score });
                            }
                        }
                        candidates.sort(function (a, b) { return b.score - a.score; });
                        return candidates.length ? candidates[0].node : null;
                    }
                    function clickByCoordinates() {
                        var points = [
                            [window.innerWidth * 0.82, 185],
                            [window.innerWidth * 0.82, 235],
                            [window.innerWidth * 0.90, 36],
                            [window.innerWidth * 0.82, 90]
                        ];
                        for (var i = 0; i < points.length; i++) {
                            var x = Math.max(1, Math.min(window.innerWidth - 2, points[i][0]));
                            var y = Math.max(1, Math.min(window.innerHeight - 2, points[i][1]));
                            var node = document.elementFromPoint(x, y);
                            while (node && node !== document.body) {
                                var text = textOf(node);
                                if ((text.indexOf(LOGIN) !== -1 || text.indexOf(REGISTER) !== -1 || /not-login|login/i.test(String(node.className || ''))) && text.indexOf(LOGGED_IN) === -1) {
                                    clickElement(node);
                                    return true;
                                }
                                node = node.parentElement;
                            }
                        }
                        return false;
                    }
                    function tryOpenLogin() {
                        confirmAgreementPopup();
                        if (readToken() || hasLoginPanel()) {
                            return true;
                        }
                        if (!confirmAgreementPopup()) {
                            closeBlockingPopups();
                        }
                        var target = findLoginButtonBySelector() || findLoginButtonByText();
                        if (target) {
                            clickElement(target);
                            return true;
                        }
                        return clickByCoordinates();
                    }
                    if (tryOpenLogin()) {
                        return;
                    }
                    if (!window.__xwzNmkjxyLoginAutoClicker) {
                        window.__xwzNmkjxyLoginAutoClicker = { tries: 0, timer: null, observer: null };
                    }
                    var state = window.__xwzNmkjxyLoginAutoClicker;
                    if (state.timer) {
                        clearInterval(state.timer);
                    }
                    if (state.observer && state.observer.disconnect) {
                        state.observer.disconnect();
                    }
                    state.tries = 0;
                    state.timer = setInterval(function () {
                        state.tries += 1;
                        if (tryOpenLogin() || state.tries >= 40) {
                            clearInterval(state.timer);
                            state.timer = null;
                            if (state.observer && state.observer.disconnect) {
                                state.observer.disconnect();
                                state.observer = null;
                            }
                        }
                    }, 500);
                    if (typeof MutationObserver !== 'undefined' && document.body) {
                        state.observer = new MutationObserver(function () {
                            if (tryOpenLogin()) {
                                if (state.timer) {
                                    clearInterval(state.timer);
                                    state.timer = null;
                                }
                                if (state.observer && state.observer.disconnect) {
                                    state.observer.disconnect();
                                    state.observer = null;
                                }
                            }
                        });
                        state.observer.observe(document.body, { childList: true, subtree: true, attributes: true });
                    }
                })();
                `
            );
        } else if (login_name == 'kaoyanvip') {
            win.webContents.executeJavaScript(
                `
                document.getElementsByClassName('login-app-footer')[0].style.display = 'none';
                `
            );
        } else if (login_name == 'mashibing') {
            win.webContents.executeJavaScript(
                `
                (function () {
                    if (window.__lel_mashibing_try_open_login__) {
                        try {
                            window.__lel_mashibing_try_open_login__();
                        } catch (e) {}
                    }
                    if (window.__lel_mashibing_login_clicker__) {
                        return;
                    }
                    window.__lel_mashibing_login_clicker__ = true;
                    function isVisible(el) {
                        if (!el) {
                            return false;
                        }
                        var style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') {
                            return false;
                        }
                        var rect = el.getBoundingClientRect();
                        return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
                    }
                    function textOf(el) {
                        return String((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, '');
                    }
                    function isLoginText(text) {
                        return text === '登录' || text === '登录/注册' || text === '立即登录' || (text.indexOf('登录') >= 0 && text.length <= 10);
                    }
                    function hasLoginPanel() {
                        var panelNodes = Array.prototype.slice.call(document.querySelectorAll('.msb-login-container__dialog,.login-dialog,.login-box,.login-form,[class*=login],[class*=Login],[class*=modal],[class*=dialog],iframe'));
                        for (var i = 0; i < panelNodes.length; i++) {
                            if (!isVisible(panelNodes[i])) {
                                continue;
                            }
                            if (String(panelNodes[i].className || '').indexOf('msb-login-container__dialog') >= 0) {
                                return true;
                            }
                            var panelText = textOf(panelNodes[i]);
                            if (panelText.indexOf('验证码') >= 0 || panelText.indexOf('手机号') >= 0 || panelText.indexOf('密码') >= 0 || (panelText.indexOf('微信') >= 0 && panelText.indexOf('登录') >= 0 && panelText.indexOf('扫码') >= 0)) {
                                return true;
                            }
                        }
                        return false;
                    }
                    function clickNode(node) {
                        try {
                            node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                        } catch (e) {}
                        node.click();
                    }
                    function getLoginTarget(node) {
                        var nodes = [node];
                        try {
                            nodes = nodes.concat(Array.prototype.slice.call(node.querySelectorAll('span,button,a,div')));
                        } catch (e) {}
                        var targets = [];
                        for (var i = 0; i < nodes.length; i++) {
                            var item = nodes[i];
                            if (!isVisible(item) || !isLoginText(textOf(item))) {
                                continue;
                            }
                            var rect = item.getBoundingClientRect();
                            targets.push({node: item, area: rect.width * rect.height});
                        }
                        targets.sort(function (a, b) { return a.area - b.area; });
                        return targets.length > 0 ? targets[0].node : null;
                    }
                    function tryOpenLogin() {
                        if (hasLoginPanel()) {
                            return true;
                        }
                        if (window.__lel_mashibing_last_login_click__ && Date.now() - window.__lel_mashibing_last_login_click__ < 1500) {
                            return false;
                        }
                        var selectors = [
                            '.user .isLogin span', '.isLogin span', '.isLogin', 'header .user span', '.header .user span', '[class*=header] .user span',
                            'header button', 'header a', 'header span', 'header div', '.header button', '.header a', '.header span', '.header div',
                            '[class*=header] button', '[class*=header] a', '[class*=header] span', '[class*=header] div', 'button', 'a', 'span', 'div'
                        ];
                        var nodeSet = [];
                        var candidates = [];
                        for (var selectorIndex = 0; selectorIndex < selectors.length; selectorIndex++) {
                            var nodes = Array.prototype.slice.call(document.querySelectorAll(selectors[selectorIndex]));
                            for (var i = 0; i < nodes.length; i++) {
                                var node = nodes[i];
                                if (nodeSet.indexOf(node) >= 0) {
                                    continue;
                                }
                                nodeSet.push(node);
                                var target = getLoginTarget(node);
                                if (!target) {
                                    continue;
                                }
                                var rect = target.getBoundingClientRect();
                                var text = textOf(target);
                                var score = selectorIndex * 20 + (rect.top <= 160 ? 0 : 10000) + rect.top - rect.left / 10 + (text === '登录' ? 0 : 20) + Math.min(rect.width * rect.height, 5000) / 5000;
                                candidates.push({node: target, score: score});
                            }
                        }
                        candidates.sort(function (a, b) { return a.score - b.score; });
                        if (candidates.length > 0) {
                            window.__lel_mashibing_last_login_click__ = Date.now();
                            clickNode(candidates[0].node);
                            return hasLoginPanel();
                        }
                        return false;
                    }
                    window.__lel_mashibing_try_open_login__ = tryOpenLogin;
                    tryOpenLogin();
                    var tries = 0;
                    var timer = setInterval(function () {
                        tries += 1;
                        if (tryOpenLogin() || tries >= 30) {
                            clearInterval(timer);
                            window.__lel_mashibing_login_clicker__ = false;
                        }
                    }, 800);
                })();
                `
            );
        } else if (login_name == 'lizhiweike') {
            injectLizhiweikeLoginSwitcher(win);
            saveLizhiweikeLoginResult(win);
            win.webContents.executeJavaScript(
                `
                var cancel_btn = document.getElementsByClassName("style-module_cancel__qF3eE")[0];
                if (cancel_btn) {
                    cancel_btn.click();
                }
                var learn_btn = document.getElementsByClassName("tabImg")[2];
                if (learn_btn) {
                    learn_btn.click();
                }
                `
            );
        } else if (login_name == 'huke88') {
            win.webContents.executeJavaScript(
                `
                (function () {
                function is_visible(el) {
                    if (!el) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    if (!style || style.display == 'none' || style.visibility == 'hidden' || style.opacity == '0') {
                        return false;
                    }
                    var rect = el.getBoundingClientRect();
                    return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
                }

                function normalize_text(el) {
                    return String((el && (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title'))) || '').replace(/\s+/g, '').trim();
                }

                function has_login_page() {
                    return is_visible(document.querySelector('#loginModal,.hkt-win'));
                }

                function click_target(el) {
                    if (!el) {
                        return false;
                    }
                    try {
                        el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'auto' });
                    } catch (error) {
                        ;
                    }
                    if (!is_visible(el)) {
                        return false;
                    }
                    var rect = el.getBoundingClientRect();
                    var options = {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: rect.left + rect.width / 2,
                        clientY: rect.top + rect.height / 2
                    };
                    ['pointerover', 'mouseover', 'mousemove', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(function (event_name) {
                        try {
                            el.dispatchEvent(new MouseEvent(event_name, options));
                        } catch (error) {
                            ;
                        }
                    });
                    try {
                        el.click();
                    } catch (error) {
                        ;
                    }
                    return true;
                }

                function find_login_button() {
                    var selectors = [
                        '#registerBtn',
                        'a#registerBtn',
                        '#new-header #registerBtn',
                        '.huke-header #registerBtn',
                        '#new-header .login-box a:first-child',
                        '.huke-header .login-box a:first-child'
                    ];
                    for (var i = 0; i < selectors.length; i++) {
                        var node = document.querySelector(selectors[i]);
                        if (is_visible(node) && normalize_text(node).indexOf('\u767b\u5f55') !== -1) {
                            return node;
                        }
                    }
                    var candidates = document.querySelectorAll('#new-header a,.huke-header a,.login-box a,button');
                    for (var j = 0; j < candidates.length; j++) {
                        if (is_visible(candidates[j]) && normalize_text(candidates[j]) == '\u767b\u5f55') {
                            return candidates[j];
                        }
                    }
                    return null;
                }

                if (!window.__xwzHuke88AutoOpenLogin) {
                    window.__xwzHuke88AutoOpenLogin = { tries: 0, timer: null };
                }
                var state = window.__xwzHuke88AutoOpenLogin;
                if (has_login_page()) {
                    if (state.timer) {
                        clearInterval(state.timer);
                        state.timer = null;
                    }
                    return;
                }
                if (!state.timer) {
                    state.timer = setInterval(function () {
                        state.tries += 1;
                        if (has_login_page() || state.tries >= 20) {
                            clearInterval(state.timer);
                            state.timer = null;
                            return;
                        }
                        click_target(find_login_button());
                    }, 600);
                }
                click_target(find_login_button());
                })();
                `
            );
        } else if (isFenbiLoginName(login_name)) {
            win.webContents.executeJavaScript(
                `
                (function () {
                function is_visible(el) {
                    if (!el) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    if (!style || style.display == 'none' || style.visibility == 'hidden' || Number(style.opacity || 1) === 0) {
                        return false;
                    }
                    var rect = el.getBoundingClientRect();
                    return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
                }
                function normalized_text(el) {
                    return String((el && (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title'))) || '').replace(/\s+/g, '').trim();
                }
                function dispatch_click(el) {
                    if (!el) {
                        return false;
                    }
                    try {
                        el.scrollIntoView({ block: 'center', inline: 'center' });
                    } catch (error) {
                        ;
                    }
                    var events = ['pointerover', 'mouseover', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
                    for (var i = 0; i < events.length; i++) {
                        try {
                            var event_name = events[i];
                            var event_obj = event_name.indexOf('pointer') === 0 && typeof PointerEvent !== 'undefined'
                                ? new PointerEvent(event_name, { bubbles: true, cancelable: true, view: window, pointerType: 'mouse', isPrimary: true })
                                : new MouseEvent(event_name, { bubbles: true, cancelable: true, view: window });
                            el.dispatchEvent(event_obj);
                        } catch (error) {
                            ;
                        }
                    }
                    try {
                        el.click();
                    } catch (error) {
                        ;
                    }
                    return true;
                }
                function has_login_panel() {
                    var visible_text = '';
                    var panel_nodes = document.querySelectorAll('[role=dialog],[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog],[class*=login-panel],[class*=LoginPanel],[class*=loginPanel],[class*=login-box],[class*=LoginBox],[class*=loginBox],form,iframe');
                    for (var i = 0; i < panel_nodes.length; i++) {
                        if (!is_visible(panel_nodes[i])) {
                            continue;
                        }
                        if (panel_nodes[i].classList.contains('fenbi-login-modal-wrapper')) {
                            return true;
                        }
                        var text = normalized_text(panel_nodes[i]);
                        visible_text += text;
                        if (text.indexOf('\u624b\u673a\u53f7') !== -1 && (text.indexOf('\u9a8c\u8bc1\u7801') !== -1 || text.indexOf('\u5bc6\u7801') !== -1 || text.indexOf('\u5fae\u4fe1') !== -1)) {
                            return true;
                        }
                    }
                    var inputs = Array.prototype.slice.call(document.querySelectorAll('input'));
                    var visible_inputs = inputs.filter(is_visible);
                    if (visible_inputs.length > 0) {
                        var body_text = normalized_text(document.body);
                        if (body_text.indexOf('\u624b\u673a\u53f7') !== -1 || body_text.indexOf('\u9a8c\u8bc1\u7801') !== -1 || body_text.indexOf('\u5bc6\u7801') !== -1) {
                            return true;
                        }
                    }
                    return visible_text.indexOf('\u9a8c\u8bc1\u7801\u767b\u5f55') !== -1 || visible_text.indexOf('\u5bc6\u7801\u767b\u5f55') !== -1;
                }
                function is_login_button(node) {
                    if (!is_visible(node)) {
                        return false;
                    }
                    var text = normalized_text(node);
                    var class_name = String(node.className || '');
                    if (class_name.indexOf('login-button') !== -1 || class_name.indexOf('loginButton') !== -1) {
                        return true;
                    }
                    if (!text || text.indexOf('\u767b\u5f55') === -1 || text.indexOf('\u5df2\u767b\u5f55') !== -1 || text.indexOf('\u9000\u51fa\u767b\u5f55') !== -1) {
                        return false;
                    }
                    if (text.length > 12) {
                        return false;
                    }
                    return true;
                }
                function find_login_button() {
                    var direct_selectors = [
                        '.login-button',
                        '[class*=login-button]',
                        '[class*=loginButton]',
                        '.info-wrapper .login-button',
                        '.fb-header-wrapper .login-button',
                        'app-header .login-button',
                        'fb-header .login-button'
                    ];
                    for (var d = 0; d < direct_selectors.length; d++) {
                        var direct_list = document.querySelectorAll(direct_selectors[d]);
                        for (var di = 0; di < direct_list.length; di++) {
                            if (is_visible(direct_list[di])) {
                                return direct_list[di];
                            }
                        }
                    }
                    var selector_groups = [
                        '.info-wrapper button,.info-wrapper a,.info-wrapper div,.info-wrapper span',
                        '.fb-header-wrapper button,.fb-header-wrapper a,.fb-header-wrapper div,.fb-header-wrapper span',
                        'header button,header a,header div,header span',
                        '.header button,.header a,.header div,.header span',
                        '[class*=header] button,[class*=header] a,[class*=header] div,[class*=header] span',
                        '[class*=nav] button,[class*=nav] a,[class*=nav] div,[class*=nav] span',
                        'button[class*=login],a[class*=login],[class*=loginBtn],[class*=login-btn],[class*=Login]'
                    ];
                    var candidates = [];
                    for (var s = 0; s < selector_groups.length; s++) {
                        var list = document.querySelectorAll(selector_groups[s]);
                        for (var i = 0; i < list.length; i++) {
                            var node = list[i];
                            if (!is_login_button(node)) {
                                continue;
                            }
                            var rect = node.getBoundingClientRect();
                            candidates.push({ element: node, score: rect.top * 10000 + (window.innerWidth - rect.left) });
                        }
                    }
                    if (!candidates.length) {
                        var all_nodes = document.querySelectorAll('button,a,div,span');
                        for (var j = 0; j < all_nodes.length; j++) {
                            var item = all_nodes[j];
                            if (!is_login_button(item)) {
                                continue;
                            }
                            var item_rect = item.getBoundingClientRect();
                            candidates.push({ element: item, score: item_rect.top * 10000 + (window.innerWidth - item_rect.left) });
                        }
                    }
                    candidates.sort(function (a, b) { return a.score - b.score; });
                    return candidates.length ? candidates[0].element : null;
                }
                function try_open_login() {
                    if (has_login_panel()) {
                        return true;
                    }
                    var login_btn = find_login_button();
                    if (!login_btn) {
                        return false;
                    }
                    dispatch_click(login_btn);
                    setTimeout(function () {
                        if (!has_login_panel()) {
                            dispatch_click(login_btn);
                            if (login_btn.parentElement) {
                                dispatch_click(login_btn.parentElement);
                            }
                        }
                    }, 220);
                    return has_login_panel();
                }
                if (!window.__xwzFenbiAutoOpenLogin) {
                    window.__xwzFenbiAutoOpenLogin = {
                        tries: 0,
                        timer: null,
                        observer: null
                    };
                }
                var state = window.__xwzFenbiAutoOpenLogin;
                function stop_watch() {
                    if (state.timer) {
                        clearInterval(state.timer);
                        state.timer = null;
                    }
                    if (state.observer) {
                        state.observer.disconnect();
                        state.observer = null;
                    }
                }
                if (has_login_panel()) {
                    stop_watch();
                    return true;
                }
                try_open_login();
                if (!state.timer) {
                    state.tries = 0;
                    state.timer = setInterval(function () {
                        state.tries += 1;
                        if (try_open_login() || state.tries >= 20) {
                            setTimeout(function () {
                                if (has_login_panel() || state.tries >= 20) {
                                    stop_watch();
                                }
                            }, 300);
                        }
                    }, 700);
                }
                if (!state.observer && document.documentElement) {
                    state.observer = new MutationObserver(function () {
                        try_open_login();
                    });
                    state.observer.observe(document.documentElement, { childList: true, subtree: true });
                }
                return false;
                })();
                `
            );
        } else if (login_name == 'cctalk' && CCTALK_LOGIN_USE_WEB_PAGE) {
            win.webContents.executeJavaScript(
                `
                (function () {
                function is_visible(el) {
                    if (!el) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    if (!style || style.display == 'none' || style.visibility == 'hidden' || style.opacity == '0') {
                        return false;
                    }
                    var rect = el.getBoundingClientRect();
                    return el.getClientRects().length > 0 && rect.width > 0 && rect.height > 0;
                }
                function text_of(el) {
                    return String((el && (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title'))) || '').replace(/\s+/g, '').trim();
                }
                function click_node(node) {
                    if (!node) {
                        return;
                    }
                    ['mouseover','mouseenter','pointerdown','mousedown','pointerup','mouseup','click'].forEach(function (type) {
                        try { node.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window })); } catch (e) {}
                    });
                    try { node.click(); } catch (e) {}
                }
                function has_login_dialog() {
                    var dialogs = Array.prototype.slice.call(document.querySelectorAll('.hp-modal-content,.hp-dialog-content,[class*="login" i][class*="modal" i],[class*="login" i][class*="dialog" i],[class*="login" i][class*="panel" i]'));
                    for (var dialogIndex = 0; dialogIndex < dialogs.length; dialogIndex++) {
                        if (!is_visible(dialogs[dialogIndex])) {
                            continue;
                        }
                        var dialogText = text_of(dialogs[dialogIndex]);
                        if (dialogText.indexOf('微信登录') >= 0 || dialogText.indexOf('手机号登录') >= 0 || dialogText.indexOf('帐号密码登录') >= 0 || dialogText.indexOf('扫码') >= 0) {
                            return true;
                        }
                    }
                    return false;
                }
                if (has_login_dialog()) {
                    return;
                }
                var directLinks = Array.prototype.slice.call(document.querySelectorAll('.ui-lib-right-pass-login-link'));
                for (var directIndex = 0; directIndex < directLinks.length; directIndex++) {
                    if (is_visible(directLinks[directIndex]) && text_of(directLinks[directIndex]) === '登录') {
                        click_node(directLinks[directIndex]);
                        return;
                    }
                }
                var nodes = Array.prototype.slice.call(document.querySelectorAll('button,a,div,span'));
                var candidates = [];
                for (var i = 0; i < nodes.length; i++) {
                    var node = nodes[i];
                    if (!is_visible(node)) {
                        continue;
                    }
                    var text = text_of(node);
                    if (text !== '登录' && text !== '登录注册' && text !== '登录/注册' && text !== '注册/登录') {
                        continue;
                    }
                    var rect = node.getBoundingClientRect();
                    if (rect.top > Math.max(180, window.innerHeight * 0.35) || rect.left < window.innerWidth * 0.45) {
                        continue;
                    }
                    candidates.push({ node: node, score: rect.top - rect.left / 100 + (text === '登录' ? 0 : 5) });
                }
                candidates.sort(function (a, b) { return a.score - b.score; });
                if (candidates.length > 0) {
                    click_node(candidates[0].node);
                }
                })();
                `
            ).catch(() => {});
        } else if (login_name == 'icourses') {
            win.webContents.executeJavaScript(
                `
                (function () {
                function is_visible(el) {
                    if (!el) {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    if (!style || style.display == 'none' || style.visibility == 'hidden') {
                        return false;
                    }
                    return el.getClientRects().length > 0;
                }

                var login_dialog = document.querySelector('.login-container,[class*="login-container"]');
                if (is_visible(login_dialog)) {
                    return;
                }

                var user_dropdown = document.querySelector('.header .user-dropdown,[class*="user-dropdown"]');
                if (is_visible(user_dropdown)) {
                    return;
                }

                var selectors = [
                    '.header .login-register .login-btn',
                    '.header .login-register',
                    '[class*="header"] [class*="login-register"] [class*="login-btn"]',
                    '[class*="header"] [class*="login-register"]',
                    '.login-register .login-btn',
                    '.login-register',
                ];
                var login_btn = null;
                for (var i = 0; i < selectors.length; i++) {
                    var candidate = document.querySelector(selectors[i]);
                    if (is_visible(candidate)) {
                        login_btn = candidate;
                        break;
                    }
                }

                if (!login_btn) {
                    var header = document.querySelector('.header-container,[class*="header-container"],.header,[class*="header"]') || document.body;
                    var clickables = header.querySelectorAll('button,a,div,span');
                    for (var j = 0; j < clickables.length; j++) {
                        var item = clickables[j];
                        if (!is_visible(item)) {
                            continue;
                        }
                        var text = (item.innerText || item.textContent || '').replace(/\\s+/g, '');
                        if (!text || text.indexOf('登录') == -1) {
                            continue;
                        }
                        var rect = item.getBoundingClientRect();
                        if (rect.top > Math.max(window.innerHeight * 0.35, 180)) {
                            continue;
                        }
                        if (rect.left < window.innerWidth * 0.55) {
                            continue;
                        }
                        login_btn = item;
                        break;
                    }
                }

                if (login_btn) {
                    login_btn.click();
                    if (!document.querySelector('.login-container,[class*="login-container"]')) {
                        login_btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    }
                }
                })();
                `
            );
        } else if (login_name == 'zixueb') {
            win.webContents.executeJavaScript(
                `
                (() => {
                    try {
                        if (localStorage.getItem('__token__')) {
                            return 'logged-in';
                        }
                    } catch (error) {
                        ;
                    }
                    if (document.querySelector('.login-container')) {
                        return 'login-open';
                    }
                    var loginButton = document.querySelector('.login-register-btn .login-btn')
                        || document.querySelector('.login-btn')
                        || document.querySelector('.login-register-btn');
                    if (!loginButton) {
                        var candidates = document.querySelectorAll('button,a,div,span');
                        for (var index = 0; index < candidates.length; index += 1) {
                            var node = candidates[index];
                            var text = (node.innerText || node.textContent || '').replace(/\\s+/g, '').trim();
                            if (text !== '登录') {
                                continue;
                            }
                            var rect = node.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0 && rect.top <= 180 && rect.left >= window.innerWidth * 0.5) {
                                loginButton = node;
                                break;
                            }
                        }
                    }
                    if (!loginButton) {
                        return 'not-found';
                    }
                    loginButton.click();
                    if (!document.querySelector('.login-container')) {
                        loginButton.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                        }));
                    }
                    return 'clicked';
                })();
                `
            );
        } else if (login_name == 'kuke99') {
            win.webContents.executeJavaScript(
                `
                var login_btn = document.getElementsByClassName("btn-kkc")[0];
                if (login_btn) {
                    login_btn.click();
                }
                `
            );
        }
    }
    setTimeout(preload_win_js, 3200);
    setTimeout(preload_win_js, 6400);
    setTimeout(preload_win_js, 10000);
    var cookie_name = {};
    if (login_name == 'xuetangx') {
        cookie_name = {name:"sessionid"};
    } else if (login_name == 'xuetangx.gradsmartedu') {
        cookie_name = {};
    } else if (login_name == 'icourse163') {
        cookie_name = {domain:".icourse163.org"};
    } else if (login_name == 'study163') {
        cookie_name = {domain:".study.163.com"};
    } else if (login_name == 'open163') {
        cookie_name = {domain:".163.com"};
    } else if (login_name == 'youdao') {
        cookie_name = {name:"DICT_PERS"};
    } else if (login_name == 'imooc') {
        cookie_name = {name:"apsid"};
    } else if (login_name == 'keqq') {
        cookie_name = {domain:".ke.qq.com"};
    } else if (login_name.includes('xiaoetech')) {
        cookie_name = {};
    } else if (login_name.includes('baijiayunxiao')) {
        cookie_name = {domain:".baijiayunxiao.com"};
    } else if (login_name == 'lexueyun') {
        cookie_name = {};
    } else if (login_name == 'jinbangshidai') {
        cookie_name = {};
    } else if (login_name == 'qlchat') {
        cookie_name = {domain:".qlchat.com"};
    } else if (login_name == 'lizhiweike') {
        cookie_name = {domain:".m.lizhiweike.com"};
    } else if (login_name == 'qianliao') {
        cookie_name = {};
    } else if (login_name == 'htknow') {
        cookie_name = {domain:".htknow.com"};
    } else if (login_name == 'haiyangknow') {
        cookie_name = {name: "__haiyangknow_placeholder__"};
    } else if (login_name == 'icourses') {
        cookie_name = {domain:".icourses.cn"};
    } else if (login_name == 'iqihang') {
        cookie_name = {domain:".iqihang.com"};
    } else if (login_name == 'chaoxing') {
        cookie_name = {};
    } else if (login_name == 'bilibili') {
        cookie_name = {name:"SESSDATA"};
    } else if (login_name == 'koolearn') {
        cookie_name = {domain:".koolearn.com"};
    } else if (login_name == 'roombox') {
        cookie_name = {name:"XDF_H5_TOKEN"};
    } else if (login_name == 'douyin') {
        cookie_name = {url: 'https://www.douyin.com/'};
    } else if (login_name == 'youku') {
        cookie_name = {name:"P_sck"};
    } else if (login_name == 'vqq') {
        cookie_name = {domain:".qq.com"};
    } else if (login_name == 'meeting') {
        cookie_name = {domain:".tencent.com"};
    } else if (login_name == 'dingtalk') {
        cookie_name = dingtalk_yunxuetang_login
            ? {url:"https://d.yunxuetang.cn"}
            : {domain:".dingtalk.com"};
    } else if (login_name == 'feishu') {
        cookie_name = {name:"session"};
    } else if (login_name == 'zhihuishu') {
        cookie_name = {url:"https://studyservice-api.zhihuishu.com"};
    } else if (login_name == 'icve') {
        cookie_name = {domain:".icve.com.cn"};
    } else if (login_name == 'yikaijiang') {
        cookie_name = {domain:".jc.e-lesson.cn"};
    } else if (login_name == 'beichenlinxuan') {
        cookie_name = {domain:".edulxw.cn"};
    } else if (login_name == 'zhidao') {
        cookie_name = {domain:".zhidaoxuexiao.com"};
    } else if (login_name == 'educity') {
        cookie_name = {domain:".xisaiwang.com"};
    } else if (login_name == 'smartedu') {
        cookie_name = {};
    } else if (login_name == 'eoffcn') {
        cookie_name = {domain:".eoffcn.com"};
    } else if (login_name == 'wangxiao') {
        cookie_name = {name: '__wangxiao_placeholder__'};
    } else if (login_name == 'dxy') {
        cookie_name = {domain:".dxy.cn"};
    } else if (login_name == 'wangxiao233') {
        cookie_name = {name: '__wangxiao233_placeholder__'};
    } else if (login_name == 'xuelang') {
        cookie_name = {domain:".iyincaishijiao.com"};
    } else if (login_name == 'gaotu') {
        cookie_name = {domain:".gaotu.cn"};
    } else if (login_name == 'gaotu.tutu') {
        cookie_name = {domain:".gaotu100.com"};
    } else if (login_name == 'gaotu.gaozhong') {
        cookie_name = {domain:".gtgz.cn"};
    } else if (login_name == 'gaotu.suyang') {
        cookie_name = {domain:".naiyouxuexi.com"};
    } else if (login_name == 'todoen') {
        cookie_name = {domain:".todoen.com"};
    } else if (login_name == 'orangevip') {
        cookie_name = {domain:".orangevip.com"};
    } else if (login_name == 'gaodun') {
        cookie_name = {domain:".gaodun.com"};
    } else if (login_name == 'zhi10') {
        cookie_name = {url: 'https://www.zhi10.com/'};
    } else if (login_name == 'pukewx') {
        cookie_name = {url: 'https://www.pukewx.com/'};
    } else if (login_name == 'yuyou') {
        cookie_name = {url: 'https://omo.yuyoupx.com/'};
    } else if (login_name == 'xuetian') {
        cookie_name = {url: 'https://www.xuetian.cn/'};
    } else if (login_name == 'geekbang') {
        cookie_name = {url: 'https://time.geekbang.org/'};
    } else if (login_name == 'xuexi1998') {
        cookie_name = {domain:"www.1998xuexi.com"};
    } else if (login_name == 'yuketang') {
        cookie_name = {domain:"www.yuketang.cn"};
    } else if (login_name == 'mison') {
        // 美森认证 Cookie 是 www.mison.cn 的 host-only Cookie。
        cookie_name = {domain:"www.mison.cn"};
    } else if (login_name == 'zixueb') {
        cookie_name = {};
    } else if (login_name == 'kandian') {
        cookie_name = {domain:"www.kandianyunketang.cn"};
    } else if (login_name == 'yincheng') {
        cookie_name = {domain:".wx.yixueks.com"};
    } else if (login_name == 'wrclass') {
        cookie_name = {domain:"pc.wrclass.com"};
    } else if (login_name == 'eduzhixin') {
        cookie_name = {domain:".eduzhixin.com"};
    } else if (login_name == 'dqb') {
        cookie_name = {domain:"dqb.yixuewk.com"};
    } else if (login_name == 'benzhixt') {
        cookie_name = {name: "__benzhixt_placeholder__"};
    } else if (login_name == 'xsteach') {
        cookie_name = {domain:".xsteach.com"};
    } else if (login_name == 'magedu') {
        cookie_name = {domain:"edu.magedu.com"};
    } else if (login_name == 'jingtongxue') {
        cookie_name = {domain:".jingtongxue.com"};
    } else if (login_name == 'caixuetang') {
        cookie_name = {domain: ".caixuetang.cn"};
    } else if (login_name == 'luffycity') {
        cookie_name = {domain: ".luffycity.com"};
    } else if (login_name == 'sparke') {
        // Authentication is stored in localStorage; query all cookies only
        // so the normal polling path can still run on the login page.
        cookie_name = {};
    } else if (login_name == 'youlu') {
        cookie_name = {domain: ".youlu.com", name: "TOKEN"};
    } else if (login_name == 'houda') {
        cookie_name = {domain:".houdask.com"};
    } else if (login_name == 'itbaizhan') {
        cookie_name = {domain:".itbaizhan.com"};
    } else if (login_name == 'nmkjxy') {
        cookie_name = {url:"https://www.nmkjxy.com"};
    } else if (login_name == 'mashibing') {
        cookie_name = {url:"https://www.mashibing.com"};
    } else if (login_name == 'chaoge') {
        cookie_name = {domain:".chaogejiaoyu.com"};
    } else if (login_name == 'shanxiang') {
        cookie_name = {domain:".sx1211.com"};
    } else if (login_name == 'shikaobang') {
        cookie_name = {};
    } else if (login_name == 'yiqikaojiaoshi') {
        cookie_name = {};
    } else if (isFenbiLoginName(login_name)) {
        cookie_name = {domain:".fenbi.com"};
    } else if (login_name == 'yixiaoerguo') {
        cookie_name = {domain:".biguo.cn"};
    } else if (login_name == 'huke88') {
        cookie_name = {domain:".huke88.com"};
    } else if (login_name == 'yukebang') {
        cookie_name = {};
    } else if (isShanganLoginName()) {
        cookie_name = {url: getShanganTargetOrigin()};
    } else if (login_name == 'kaimingzhixue') {
        cookie_name = {domain:".lckmzx.com"};
    } else if (login_name == 'sanjieke') {
        cookie_name = {};
    } else if (login_name == 'aishangke') {
        cookie_name = {};
    } else if (login_name == 'xiaoheiketang') {
        cookie_name = {domain: ".xiaoheiketang.com"};
    } else if (login_name == 'wallstreets') {
        cookie_name = {domain:".wallstreets.cn"};
    } else if (login_name == 'ydshengxue') {
        cookie_name = {domain:".ydshengxue.com"};
    } else if (login_name == 'plaso') {
        cookie_name = {name:"access_token"};
    } else if (login_name == 'aiwenyun') {
        cookie_name = {name:"access_token"};
    } else if (login_name == 'jhpy') {
        cookie_name = {name:"access_token"};
    } else if (login_name == 'jhpyedu') {
        // The new student site keeps its bearer token in Local Storage.
        cookie_name = {};
    } else if (login_name == 'huoke') {
        cookie_name = {name: "__huoke_placeholder__"};
    } else if (login_name == 'kaoyanvip') {
        cookie_name = {name:"Pcsite-Token"};
    } else if (login_name == 'kuke99') {
        cookie_name = {name:"TOKEN"};
    } else if (login_name == 'hqwx') {
        cookie_name = {name:"passport"};
    } else if (login_name == 'xinghuo') {
        cookie_name = {name: '__xinghuo_placeholder__'};
    } else if (login_name == 'huomiao') {
        cookie_name = {name: '__huomiao_placeholder__'};
    } else if (login_name == 'xiaoeapp') {
        cookie_name = {name: '__xiaoeapp_placeholder__'};
    } else if (login_name == 'classin') {
        cookie_name = {name: '__classin_placeholder__'};
    } else if (login_name == 'classin_webcast') {
        cookie_name = {url: 'https://live.eeo.cn/'};
    } else if (login_name == 'cctalk') {
        cookie_name = {};
    } else if ((login_name == 'mddclass' || login_name == 'sihaigongkao')) {
        cookie_name = {};
    } else if (login_name == 'zhongxunwx') {
        cookie_name = {domain:".zhongxunwx.com"};
    } else if (login_name == 'moremeditation') {
        cookie_name = {};
    } else if (login_name == 'haozaixian' || login_name == 'dazhaomofang') {
        cookie_name = {name:"ZYBUSS"};
    } else if (isDuanshuLoginName(login_name)) {
        cookie_name = {name: "__duanshu_placeholder__"};
    } else if (login_name.includes('xiwang')) {
        if (login_name == 'xiwang.youke') {
            cookie_name = {name:"tal_token_xwyk"};
        } else {
            cookie_name = {name:"tal_token"};
        }
} else if (login_name == 'huatu') {
    cookie_name = {};
} else if (login_name == 'med66') {
    cookie_name = {name: '__med66_placeholder__'};
} else if (login_name == 'zhengbao') {
    cookie_name = {name: '__zhengbao_placeholder__'};
} else if (login_name == 'canto') {
    cookie_name = {url: "https://canto.kuaiji521.com"};
} else if (login_name == 'jianshe99') {
    cookie_name = {name: '__jianshe99_placeholder__'};
} else if (login_name == 'dongao') {
    cookie_name = {};
} else if (login_name == 'ahuyikao') {
    cookie_name = {url: "https://www.ahuyikao.com"};
    } else if (login_name == 'xueersi') {
        cookie_name = {name: "tal_token"};
    } else if (login_name == 'ledu') {
        cookie_name = {name: "__ledu_placeholder__"};
    } else if (login_name == 'minshi') {
        cookie_name = {name: "__minshi_placeholder__"};
    } else if (isCkjrLoginName(login_name)) {
        cookie_name = {name: "__ckjr_placeholder__"};
    } else if (login_name == 'yijiayk') {
        cookie_name = {};
    } else if (login_name == '51cto') {
        cookie_name = {url: "https://edu.51cto.com/"};
    } else if (login_name == '51cto_saas') {
        cookie_name = {domain: ".51cto.com"};
    } else if (login_name == '51zxw') {
        cookie_name = {domain: ".51zxw.net"};
    } else if (login_name == 'gongxuanwang') {
        cookie_name = {name: "edu_token"};
    } else if (login_name == 'renrenjiang') {
        cookie_name = {name: "__renrenjiang_placeholder__"};
    } else if (login_name == 'zlketang') {
        cookie_name = {name: "SWOOLESESSSIONNAME"};
    } else if (login_name == 'yizhiknow') {
        cookie_name = {name: "__yizhiknow_placeholder__"};
    } else if (login_name == 'wendao') {
        cookie_name = {url: 'https://pc.wendao101.com/'};
    } else if (login_name == 'haiyangknow') {
        cookie_name = {name: "__haiyangknow_placeholder__"};
    } else if (login_name == 'wowtiku') {
        cookie_name = {name: "__wowtiku_placeholder__"};
    } else if (login_name == 'baitong') {
        cookie_name = {name: "__baitong_placeholder__"};
    } else if (login_name == 'yangcong') {
        cookie_name = {name: "__yangcong_placeholder__"};
    } else if (login_name == 'gaodoudou') {
        cookie_name = {domain:"gdd.aixuexi.com"};
    } else if (login_name == 'yikao88') {
        cookie_name = {domain: ".yikao88.com"};
    } else if (login_name == 'yiihuu') {
        cookie_name = {domain: ".yiihuu.com"};
    } else if (login_name == 'sieredu') {
        cookie_name = {domain: ".sieredu.com"};
    } else if (login_name == 'enetedu') {
        cookie_name = {domain: ".enetedu.com"};
    } else if (login_name == 'sikiedu') {
        // PHPSESSID/REMEMBERME are host-only on www.sikiedu.com.  The
        // subsequent filter keeps unrelated domains out of the saved value.
        cookie_name = {};
    } else if (login_name == 'unipus') {
        cookie_name = {domain: ".unipus.cn"};
    } else if (login_name == 'cnmooc') {
        cookie_name = {domain: ".cnmooc.sjtu.cn"};
    } else if (login_name == 'chinesemooc') {
        cookie_name = {domain: ".chinesemooc.org"};
    } else if (login_name == 'lexuepeiyou') {
        cookie_name = {};
    } else if (login_name == 'speiyou') {
        cookie_name = {name: "token"};
    } else if (login_name == 'xiaoyuanyouke') {
        cookie_name = {};
    } else if (login_name == 'houduweilai') {
        cookie_name = {name: "__houdu_placeholder__"};
    } else if (login_name == 'tmooc') {
        cookie_name = {};
    } else if (login_name == 'yunduan') {
        cookie_name = {};
    } else if (login_name == 'youzan' || login_name.startsWith('youzan.')) {
        cookie_name = {name: "KDTSESSIONID"};
    } else if (login_name == 'yikaobang') {
        cookie_name = {domain: 'ykb-h5-web.yikaobang.com.cn'};
    } else if (login_name == 'login' || login_name == 'login_test' || login_name == 'login_weixin' || login_name == 'login_weixin_test' || login_name == 'url' ) {
        cookie_name = {name:"userid"};
    } else {
        app.quit();
    }
    var clear_finished = false, error_appeared = false, duanshu_redirect_ticks = 0;
    resetLoginSession(login_session, effective_login_url)
    .then(() => {
        if ((login_name == 'mddclass' || login_name == 'sihaigongkao') && MDDCLASS_LOGIN_USE_WEB_PAGE && !MDDCLASS_RESTORE_STORED_COOKIES) {
            return;
        }
        return restoreMddclassStoredCookies(login_session, typeof mddclass_target_url !== 'undefined' ? mddclass_target_url : '').catch(() => {});
    })
    .then(() => {
        if (!isDuanshuLoginName(login_name) || duanshu_pc_detail_login) {
            return;
        }
        return detectDuanshuWechatOnly(effective_login_url).then((result) => {
            duanshu_wechat_login_required = !!(result && result.required);
            duanshu_qr_origin = duanshuOriginForHost(result && result.host);
            duanshu_qr_shop_id = String(result && result.shop_id || '').trim();
        });
    })
    .then(() => benzhixt_compatibility_ready)
    .then(() => xuexi1998_compatibility_ready)
    .then(() => fenbi_compatibility_ready)
    .then(() => {
        clear_finished = true;
        loadLoginPage();
    }).catch((error) => {
        // console.error('[login-mooc] read cookie file failed:', cookies_file, error && error.stack || error);
        error_appeared = true;
    })

    cookie_poll_timer = setInterval(function() {
        if (error_appeared) {
            stopCookiePoll();
            app.quit();
        }
        if (!isWindowAlive(win)) {
            stopCookiePoll();
            return;
        }
        if (clear_finished) {
            loadLoginPage();
            if (login_name === 'yikaobang') return;
            if (isDuanshuWechatQrFlow()) {
                pollDuanshuQrRefresh(win).catch(() => {});
                return;
            }
            let include_names = null
            if (login_name == 'yikao88') {
                include_names = ['token', 'memberId'];
            } else if (login_name == 'yiihuu') {
                include_names = ['PHPSESSID', 'cookie_ssologin', 'dig', 'userinfo', 'yiihuu_sso', 'yiihuu_sso_encode', 'nick'];
            } else if (login_name == 'chaoxing') {
                include_names = ['_uid', '_d', 'UID', 'vc3', 'uf'];
            } else if (login_name == 'vqq') {
                include_names = ['vqq_vuserid', 'vqq_vusession'];
            } else if (login_name == 'meeting') {
                include_names = ['we_meet_token', 'corp_id', 'app_uid'];
            } else if (login_name == 'dingtalk') {
                include_names = dingtalk_yunxuetang_login ? null
                    : ['account', 'deviceid', 'access_token', 'XSRF-TOKEN', 'cna', 'isg', 'tfstk', 'xlly_s', 'pub_uid'];
            } else if (login_name == 'icourse163') {
                include_names = ['STUDY_SESS'];
            } else if (login_name == 'study163') {
                include_names = ['STUDY_SESS'];
            } else if (login_name == 'open163') {
                include_names = ['NTES_OSESS', 'P_OINFO', 'S_OINFO', 'NTES_YD_SESS', 'NTES_YD_PASSPORT', 'P_INFO', 'S_INFO', '__oc_uuid', '_ntes_nuid', '_antanalysis_s_id'];
            } else if (login_name == 'zhihuishu') {
                include_names = ZHIHUISHU_COOKIE_NAMES.slice();
            } else if (login_name == 'icve') {
                include_names = ['token'];
            } else if (login_name == 'yikaijiang') {
                include_names = ['JSESSIONID', 'UC00OOIIll11', 'whaty.lms.webtrn.cn', 'tgw_l7_route'];
            } else if (login_name == 'beichenlinxuan') {
                include_names = ['token', 'server_name_session', 'Hm_lpvt_e7bc2f7ec69c04d5ddf9c1966af35f34', 'Hm_lvt_e7bc2f7ec69c04d5ddf9c1966af35f34', 'HMACCOUNT', 'MEIQIA_TRACK_ID', 'MEIQIA_VISIT_ID'];
            } else if (login_name == 'zhidao') {
                include_names = ['ZHIDAO_USER_ACCOUNT'];
            } else if (login_name == 'educity') {
                include_names = ['_sid_', 'cstk', 'anyid'];
            } else if (login_name == 'smartedu') {
                include_names = null;
            } else if (login_name == 'eoffcn') {
                include_names = ['x-sso-gateway-web-token'];
            } else if (login_name == 'wangxiao') {
                include_names = WANGXIAO_COOKIE_NAMES.slice();
            } else if (login_name == 'dxy') {
                include_names = null;
            } else if (login_name == 'wangxiao233') {
                include_names = WANGXIAO233_COOKIE_NAMES.slice();
            } else if (login_name == 'keqq') {
                include_names = ['uin', 'uid_origin_uid_type', 'uid_origin_auth_type', 'uid_a2'];
            } else if (login_name == 'koolearn') {
                include_names = ['sso.ssoId', 'ssoSessionID'];
            } else if (login_name == 'yunduan') {
                include_names = ['ORGSUPERSESSID'];
            } else if (login_name.includes('xiaoetech')) {
                if (xiaoe_tech) {
                    include_names = ['p_token'];
                } else {
                    include_names = XIAOETECH_STORE_COOKIE_NAMES.slice();
                }
            } else if (login_name == 'ahuyikao') {
                include_names = AHU_COOKIE_NAMES.slice();
            } else if (login_name == 'qlchat') {
                include_names = ['userId', 'rsessionid', 'isCheckJsession'];
            } else if (login_name == 'qianliao') {
                include_names = ['userId', 'rsessionId'];
            } else if (login_name == 'xuelang') {
                include_names = ['sid_guard'];
            } else if (login_name.includes('gaotu')) {
                include_names = ['__user_info__', '__user_token__'];
            } else if (login_name == 'todoen') {
                include_names = ['userid', 'token', 'sid', 'secret'];
            } else if (login_name == 'orangevip') {
                include_names = ['PHPSESSID', 'CL_authcode'];
            } else if (login_name == 'gaodun') {
                include_names = ['Accesstoken'];
            } else if (login_name == 'zhi10') {
                include_names = ['PHPSESSID', 'REMEMBERME'];
            } else if (login_name == 'pukewx') {
                include_names = ['pukewx'];
            } else if (login_name == 'yuyou') {
                include_names = ['accessToken'];
            } else if (login_name == 'xuetian') {
                include_names = ['xtp_V2.1_userInfo', 'xtp_V2.1_qid'];
            } else if (login_name == 'geekbang') {
                // The URL query below scopes cookies to the course host.
                include_names = null;
            } else if (login_name == 'gaodoudou') {
                include_names = ['acw_tc', 'ptxkhzyapp', 'ptxkhzyappUserId'];
            } else if (login_name == 'xuexi1998') {
                include_names = ['userInfo', 'acw_tc', 'cdn_sec_tc', 'sl-session'];
            } else if (login_name == 'yuketang') {
                include_names = ['sessionid', 'csrftoken', 'django_language'];
            } else if (login_name == 'mison') {
                include_names = [
                    'PHPSESSID', 'ujqtlmlauth', 'ujqtlmlgroupid',
                    'ujqtlmlrnd', 'ujqtlmluserid', 'ujqtlmlusername',
                    'shade', 'fromurl'
                ];
            } else if (login_name == 'zixueb') {
                include_names = null;
            } else if (login_name == 'yincheng') {
                include_names = ['accessToken'];
            } else if (login_name == 'wrclass') {
                include_names = ['user_token'];
            } else if (login_name == 'eduzhixin') {
                include_names = ['Authorization', 'session_key', 'PHPSESSID', 'subject', '_c_WBKFRo'];
            } else if (login_name == 'dqb') {
                include_names = ['NEEDSTOKEN'];
            } else if (login_name == 'sieredu') {
                include_names = ['sid', 'deviceId'];
            } else if (login_name == 'enetedu') {
                include_names = ['eneteduToken', 'acw_tc'];
            } else if (login_name == 'sikiedu') {
                include_names = null;
            } else if (login_name == 'unipus') {
                include_names = null;
            } else if (login_name == 'cnmooc') {
                include_names = null;
            } else if (login_name == 'chinesemooc') {
                include_names = ['PHPSESSID', 'WP22113997UACID', 'WP22113997UACCODE', 'acw_tc'];
            } else if (login_name == 'xsteach') {
                include_names = ['xsteachID', 'Hm_lpvt_666eed3d1138aba8c53e5d28cf45cdff', 'Hm_lvt_666eed3d1138aba8c53e5d28cf45cdff', 'HMACCOUNT', 'robotId'];
            } else if (login_name == 'magedu') {
                include_names = ['gupao_edu_college_token'];
            } else if (login_name == 'jingtongxue') {
                include_names = ['yunId', 'account_www.jingtongxue.com', 'client_id', 'companyId', 'cookie_user_', 'JSESSIONID', 'schoolId', 'schoolModalFlag', 'SESSION', 'uniqueVisitorId', 'up_token', 'token', 'userInfo', 'userId'];
            } else if (login_name == 'houda') {
                include_names = HOUDA_COOKIE_NAMES.slice();
            } else if (login_name == 'lexueyun') {
                include_names = null;
            } else if (login_name == 'itbaizhan') {
                include_names = ['PHPSESSID', 'token', 'user'];
            } else if (login_name == 'nmkjxy') {
                include_names = null;
            } else if (login_name == 'mashibing') {
                include_names = ['token', 'uuid'];
            } else if (login_name == 'chaoge') {
                include_names = CHAOGE_COOKIE_NAMES.slice();
            } else if (login_name == 'shanxiang') {
                include_names = ['PHPSESSID', 'sx_home_sx_wx_1211_sxenwebtoken', 'sx_home_sx_wx_1211_sxenwebinfo', 'mantis5864'];
            } else if (login_name == 'shikaobang') {
                include_names = SHIKAOBANG_COOKIE_NAMES.slice();
            } else if (login_name == 'yiqikaojiaoshi') {
                include_names = YIQIKAOJIAOSHI_COOKIE_NAMES.slice();
            } else if (isFenbiLoginName(login_name)) {
                include_names = FENBI_COOKIE_NAMES.slice();
            } else if (login_name == 'yixiaoerguo') {
                include_names = ['sc_token_pro'];
            } else if (login_name == 'huke88') {
                include_names = ['_identity-usernew', 'advanced-frontend', '_csrf-frontend', 'abuv'];
            } else if (login_name == 'kaimingzhixue') {
                include_names = ['studentToken'];
            } else if ((login_name == 'mddclass' || login_name == 'sihaigongkao')) {
                include_names = MDDCLASS_COOKIE_NAMES.slice();
            } else if (login_name == 'sanjieke') {
                include_names = SANJIEKE_COOKIE_NAMES.slice();
            } else if (login_name == 'aishangke') {
                include_names = AISHANGKE_COOKIE_NAMES.slice();
            } else if (login_name == 'wallstreets') {
                include_names = ['PHPSESSID'];
            } else if (login_name == 'ydshengxue') {
                include_names = ['DICT_SESS', 'DICT_LOGIN'];
            } else if (login_name == 'lizhiweike') {
                include_names = ['id', 'id_token', 'token'];
            } else if (login_name == 'htknow') {
                include_names = ['base_KEY', 'token', 'custom_id', 'user', 'wechatList', 'appletList', 'ksList'];
            } else if (login_name == 'haiyangknow') {
                include_names = ['Admin-Token', 'p_h5_u', 'selectedStreamLevel'];
            } else if (login_name == 'baitong') {
                include_names = ['zk_token', 'zk-user-id', 'p_h5_u', 'selectedStreamLevel', 'lock'];
            } else if (login_name == 'iqihang') {
                include_names = ['accessToken'];
            } else if (login_name.includes('baijiayunxiao')) {
                include_names = ['studentToken'];
            } else if (login_name == 'jinbangshidai') {
                include_names = ['ToKen'];
            } else if (isDuanshuLoginName(login_name)) {
                include_names = ['x-member', 'userInfo_release', 'userInfo_pre', 'userInfo_test'];
            } else if (login_name == 'youzan' || login_name.startsWith('youzan.')) {
                include_names = ['KDTSESSIONID', 'nobody_sign', '_kdt_id_', 'open_token', 'dfp', 'yz_fp_hash', 'acw_tc'];
            } else if (login_name == 'sparke') {
                include_names = null;
            } else if (login_name == '51cto') {
                // Keep playback verification cookies, including EdgeOne tokens.
                // The URL query limits the export to cookies sent to the course host.
                include_names = null;
            } else if (login_name == '51cto_saas') {
                include_names = ['51CTO_ATHENA_TOKEN', 'qp_saas_cid', 'qp_saas_id', 'X-Campus-Version', 'playDEF', 'selectedStreamLevel', 'Webp'];
            } else if (login_name == 'med66') {
                include_names = ['client_ucToken', 'cdeluid', 'username', 'sid', 'JSESSIONID', 'lastloginuser', 'SelCourse', 'cdelPublicKey'];
            } else if (login_name == 'zhengbao') {
                include_names = ['client_ucToken', 'cdeluid', 'username', 'sid', 'JSESSIONID', 'SESSION', 'lastloginuser', 'SelCourse', 'publicKey', 'cdelPublicKey'];
            } else if (login_name == 'jianshe99') {
                include_names = ['client_ucToken', 'cdeluid', 'username', 'sid', 'JSESSIONID', 'lastloginuser', 'SelCourse', 'cdelPublicKey', 'clientID'];
            } else if (login_name == 'huatu') {
                include_names = HUATU_COOKIE_NAMES.slice();
            } else if (login_name == 'cctalk') {
                include_names = CCTALK_COOKIE_NAMES.slice();
            } else if (login_name == 'speiyou') {
                include_names = null;
            } else if (login_name == '51zxw') {
                include_names = null;
            } else if (login_name == 'xiaoyuanyouke') {
                include_names = XIAOYUANYOUKE_COOKIE_NAMES.slice();
            } else if (login_name == 'yijiayk') {
                include_names = null;
            } else if (login_name == 'zhongxunwx') {
                include_names = ['thinkjs'];
            } else if (login_name == 'xuetangx.gradsmartedu') {
                include_names = null;
            } else if (login_name == 'classin_webcast') {
                include_names = ['webcast_login_status'];
            }

            let cookie_query = cookie_name;
            if (login_name == 'jingtongxue') {
                cookie_query = {};
            }
            if (login_name == 'dxy') {
                cookie_query = {};
            }
            if (isYouzanLoginName(login_name)) {
                cookie_query = {};
            }
            if (include_names && include_names.length > 1 && login_name != 'zhihuishu' && login_name != 'gaodoudou') {
                cookie_query = {};
            }

            login_session.cookies.get(cookie_query)
            .then((cookies) => {
                if (!isWindowAlive(win)) {
                    return;
                }
                // console.log(cookies);

                if (login_name == 'douyin') {
                    trySaveDouyinCookies(cookies);
                    return;
                }

                if (login_name == 'dongao') {
                    cookies = filterDongaoCookies(cookies);
                }
                if (login_name == 'yiqikaojiaoshi') {
                    cookies = cookies.filter((cookie) => isYiqikaojiaoshiCookie(cookie));
                }
                if (login_name == 'dxy') {
                    cookies = filterDxyCookies(cookies);
                }

                if (isCkjrLoginName(login_name)) {
                    syncCkjrStoreContext(win, ckjr_store_context);
                    return;
                }

                if (include_names) {
                    let filter_cookies = [];
                    cookies.forEach(cookie=>{
                        if ((login_name == 'huatu' && isHuatuCookieName(cookie.name)) || (login_name == 'houda' && isHoudaCookie(cookie) && include_names.includes(cookie.name)) || (login_name == 'chaoge' && isChaogeCookie(cookie) && include_names.includes(cookie.name)) || (login_name == 'shanxiang' && isShanxiangCookie(cookie) && include_names.includes(cookie.name)) || (login_name == 'shikaobang' && isShikaobangCookie(cookie) && include_names.includes(cookie.name)) || (isFenbiLoginName(login_name) && isFenbiCookie(cookie) && include_names.includes(cookie.name)) || (login_name != 'houda' && login_name != 'chaoge' && login_name != 'shanxiang' && login_name != 'shikaobang' && !isFenbiLoginName(login_name) && include_names.includes(cookie.name))) {
                            filter_cookies.push(cookie);
                        }
                    })
                    cookies = filter_cookies;
                }
                if (login_name == 'zhihuishu') {
                    cookies = normalizeZhihuishuCookies(cookies);
                }
                if (login_name == 'smartedu') {
                    cookies = filterSmarteduCookies(cookies);
                }
                if (login_name == 'unipus') {
                    cookies = filterUnipusCookies(cookies);
                }
                if (login_name == 'sikiedu') {
                    cookies = filterSikieduCookies(cookies);
                }
                if (login_name == 'cnmooc') {
                    cookies = filterCnmoocCookies(cookies);
                }
                if (login_name == 'chinesemooc') {
                    cookies = filterChinesemoocCookies(cookies);
                }
                if (login_name == 'gaodoudou') {
                    const scoped_cookies = filterGaodoudouCookies(cookies);
                    if (hasGaodoudouLoginCookies(scoped_cookies)) {
                        saveLoginCookieValue(buildCookieValue(scoped_cookies));
                    }
                    return;
                }
                if (login_name == 'xuexi1998') {
                    trySaveXuexi1998Cookies(cookies);
                    return;
                }
                if (login_name == 'mison') {
                    trySaveMisonCookies(cookies);
                    return;
                }
                if (login_name == 'xuetangx.gradsmartedu') {
                    trySaveGradsmartCookies(cookies);
                    return;
                }

                if (login_name == 'dxy') {
                    trySaveDxyLoginResult(cookies);
                    return;
                }
                if (login_name == 'classin_webcast') {
                    trySaveClassinWebcastContext(win, cookies);
                    return;
                }
                if (login_name == 'yiqikaojiaoshi') {
                    trySaveYiqikaojiaoshiLoginResult(cookies);
                    return;
                }

                if (login_name == 'huatu') {
                    trySaveHuatuCookies(cookies);
                }
                if (login_name == 'houda') {
                    trySaveHoudaCookies(cookies);
                    return;
                }
                if (login_name == 'lexueyun') {
                    trySaveLexueyunAuth(win);
                    return;
                }
                if (login_name == 'speiyou') {
                    trySaveSpeiyouLoginResult(win).catch((error) => {
                        ;
                    });
                    return;
                }
                if (login_name == 'xiaoyuanyouke') {
                    trySaveXiaoyuanyoukeLoginResult(win, cookies).catch((error) => {
                        ;
                    });
                    return;
                }
                if (login_name == 'yijiayk') {
                    trySaveYijiaykToken(win).catch((error) => {
                        yijiayk_save_inflight = false;
                    });
                    return;
                }
                if (login_name == 'pukewx') {
                    trySavePukewxLogin(win, cookies);
                    return;
                }
                if (login_name == 'yuyou') {
                    trySaveYuyouLogin(win);
                    return;
                }
                if (login_name == 'todoen') {
                    trySaveTodoenLoginResult(win, cookies).catch((error) => {
                        ;
                    });
                    return;
                }
                if (login_name == 'smartedu') {
                    trySaveSmarteduTokenFromPage(win);
                    if (!trySaveSmarteduCookies(cookies) && hasSmarteduSsoCookies(cookies)) {
                        scheduleSmarteduCookieCheck(win, login_session);
                    }
                    return;
                }
                if (login_name == 'unipus') {
                    trySaveUnipusCookies(cookies);
                    return;
                }
                if (login_name == 'sikiedu') {
                    trySaveSikieduCookies(cookies, win);
                    return;
                }
                if (login_name == 'zhi10') {
                    trySaveZhi10Cookies(cookies);
                    return;
                }
                if (login_name == 'cnmooc') {
                    trySaveCnmoocCookies(cookies, win);
                    return;
                }
                if (login_name == 'wendao') {
                    trySaveWendaoLoginResult(win, cookies);
                    return;
                }
                if (login_name == 'enetedu') {
                    const cookie_value = buildCookieValue(cookies);
                    win.webContents.executeJavaScript(`
                        (() => {
                            function safeParse(value) {
                                if (!value) {
                                    return null;
                                }
                                if (typeof value !== 'string') {
                                    return value;
                                }
                                try {
                                    return JSON.parse(value);
                                } catch (error) {
                                    return value;
                                }
                            }
                            function dumpStorage(storage) {
                                var result = {};
                                if (!storage) {
                                    return result;
                                }
                                for (var i = 0; i < storage.length; i++) {
                                    var key = storage.key(i);
                                    if (key) {
                                        result[key] = storage.getItem(key);
                                    }
                                }
                                return result;
                            }
                            function readToken(storage) {
                                if (!storage) {
                                    return '';
                                }
                                var direct = storage.getItem('eneteduToken') || storage.getItem('token') || storage.getItem('accessToken') || '';
                                if (direct) {
                                    return direct;
                                }
                                for (var i = 0; i < storage.length; i++) {
                                    var key = storage.key(i);
                                    var value = key ? storage.getItem(key) : '';
                                    var parsed = safeParse(value);
                                    if (parsed && typeof parsed === 'object') {
                                        var token = parsed.eneteduToken || parsed.token || parsed.accessToken || '';
                                        if (token) {
                                            return String(token);
                                        }
                                    }
                                    if (key && key.toLowerCase().indexOf('token') !== -1 && value) {
                                        return String(value);
                                    }
                                }
                                return '';
                            }
                            return {
                                href: window.location.href || '',
                                cookie: document.cookie || '',
                                eneteduToken: readToken(localStorage) || readToken(sessionStorage),
                                localStorage: dumpStorage(localStorage),
                                sessionStorage: dumpStorage(sessionStorage),
                            };
                        })();
                    `).then((result) => {
                        if (!result) {
                            return;
                        }
                        result.cookie = result.cookie || cookie_value;
                        if (result.eneteduToken || result.cookie) {
                            saveLoginPayload(result);
                        }
                    }).catch(() => {
                        if (cookie_value) {
                            saveLoginCookieValue(cookie_value);
                        }
                    });
                    return;
                }
                if (login_name == 'sparke') {
                    trySaveSparkeLoginResult(win);
                    return;
                }
                if (login_name == 'cctalk') {
                    trySaveCctalkLoginResult(win, cookies, false);
                    return;
                }
                if ((login_name == 'mddclass' || login_name == 'sihaigongkao')) {
                    trySaveMddclassLoginResult(win, cookies, false);
                    return;
                }
                if (login_name == 'caixuetang') {
                    trySaveCaixuetangLoginResult(win, filterCaixuetangCookies(cookies));
                    return;
                }
                if (login_name == 'luffycity') {
                    trySaveLuffycityLoginResult(win, filterLuffycityCookies(cookies));
                    return;
                }
                if (login_name == 'jingtongxue') {
                    trySaveJingtongxueLoginResult(win, filterJingtongxueCookies(cookies));
                    return;
                }
                if (login_name == 'magedu') {
                    trySaveMageduLoginResult(win, filterMageduCookies(cookies));
                    return;
                }
                if (login_name == 'tmooc') {
                    trySaveTmoocCookies(win, cookies);
                    return;
                }
                if (login_name == 'yunduan') {
                    trySaveYunduanCookies(cookies, win);
                    return;
                }
                if (isDuanshuLoginName(login_name) && cookies.length >= 1) {
                    const current_url = getSafeWindowUrl(win, login_url);
                    const target_env = getDuanshuCookieEnvFromUrl(current_url || extra_arg || login_url);
                    let member_cookie = cookies.find(cookie => cookie.name === 'userInfo_' + target_env && cookie.value);
                    if (!member_cookie) {
                        member_cookie = cookies.find(cookie => /^userInfo_(release|pre|test)$/.test(cookie.name) && cookie.value);
                    }
                    if (!member_cookie) {
                        member_cookie = cookies.find(cookie => cookie.name === 'x-member' && cookie.value);
                    }
                    if (member_cookie && saveDuanshuCookieValue(member_cookie.value)) {
                        return;
                    }
                }
                if (login_name == 'wangxiao') {
                    if (!hasWangxiaoLoginCookies(cookies)) {
                        return;
                    }
                    trySaveWangxiaoCookies(cookies);
                    return;
                }
                if (login_name == 'wangxiao233') {
                    if (!hasWangxiao233LoginCookies(cookies)) {
                        return;
                    }
                    trySaveWangxiao233Cookies(cookies);
                    return;
                }

                if (login_name == 'jinbangshidai') {
                    const cookie_token = ((cookies || []).find((cookie) => cookie && cookie.name === 'ToKen' && cookie.value) || {}).value || '';
                    win.webContents.executeJavaScript(`
                        (() => {
                            try {
                                const keys = ['ToKen', 'token', 'Token', 'TOKEN'];
                                for (const key of keys) {
                                    const value = localStorage.getItem(key) || sessionStorage.getItem(key);
                                    if (value) {
                                        return value;
                                    }
                                }
                                for (let i = 0; i < localStorage.length; i++) {
                                    const key = localStorage.key(i);
                                    if (key && key.toLowerCase() === 'token') {
                                        const value = localStorage.getItem(key);
                                        if (value) {
                                            return value;
                                        }
                                    }
                                }
                            } catch (error) {
                                ;
                            }
                            return '';
                        })();
                    `).then((token) => {
                        token = String(token || cookie_token || '').trim();
                        if (token) {
                            saveLoginCookieValue('ToKen=' + token);
                        }
                    }).catch((error) => {
                        if (cookie_token) {
                            saveLoginCookieValue('ToKen=' + cookie_token);
                        }
                    });
                    return;
                }

                if (login_name == 'yixiaoerguo') {
                    const cookie_token = (cookies || []).find(cookie => cookie.name == 'sc_token_pro' && cookie.value);
                    win.webContents.executeJavaScript(`
                        (() => {
                            function readToken(storage) {
                                if (!storage) {
                                    return '';
                                }
                                var direct = storage.getItem('sc_token_pro') || storage.getItem('token') || '';
                                if (direct) {
                                    return direct;
                                }
                                for (var i = 0; i < storage.length; i++) {
                                    var key = storage.key(i);
                                    if (key && key.indexOf('sc_token') !== -1) {
                                        var value = storage.getItem(key);
                                        if (value) {
                                            return value;
                                        }
                                    }
                                }
                                return '';
                            }
                            try {
                                return readToken(localStorage) || readToken(sessionStorage) || '';
                            } catch (error) {
                                return '';
                            }
                        })();
                    `).then((token) => {
                        token = token || (cookie_token ? cookie_token.value : '');
                        if (token) {
                            saveLoginCookieValue('sc_token_pro=' + token);
                        }
                    }).catch((error) => {
                        if (cookie_token && cookie_token.value) {
                            saveLoginCookieValue('sc_token_pro=' + cookie_token.value);
                        }
                    });
                    return;
                }

                if (login_name == 'benzhixt') {
                    if (benzhixt_save_inflight) {
                        return;
                    }
                    win.webContents.executeJavaScript(`
                        (() => {
                            function readValue(storage) {
                                if (!storage) {
                                    return '';
                                }
                                const value = storage.getItem('bzza-pc') || '';
                                if (!value) {
                                    return '';
                                }
                                try {
                                    const payload = JSON.parse(value);
                                    if (payload && (payload.token || (payload.userInfo && payload.userInfo.token))) {
                                        return value;
                                    }
                                } catch (error) {
                                    return '';
                                }
                                return '';
                            }
                            try {
                                return readValue(window.localStorage) || readValue(window.sessionStorage) || '';
                            } catch (error) {
                                return '';
                            }
                        })();
                    `).then((cookie_value) => {
                        cookie_value = String(cookie_value || '').trim();
                        if (cookie_value) {
                            benzhixt_save_inflight = true;
                            saveLoginCookieValue(cookie_value);
                        }
                    }).catch((error) => {
                        ;
                    });
                    return;
                }

                if (login_name == 'xinghuo') {
                    if (xinghuo_save_inflight) {
                        return;
                    }
                    win.webContents.executeJavaScript('window.__XINGHUO_RESULT__')
                    .then((result) => {
                        saveXinghuoLoginResult(result);
                    }).catch(() => {});
                    return;
                }

                if (login_name == 'huomiao') {
                    if (huomiao_save_inflight) {
                        return;
                    }
                    win.webContents.executeJavaScript('window.__HUOMIAO_LOGIN_RESULT__')
                    .then((result) => {
                        saveHuomiaoLoginResult(result);
                    }).catch(() => {});
                    return;
                }

                if (login_name == 'lexuepeiyou') {
                    if (lexuepeiyou_save_inflight) {
                        return;
                    }
                    win.webContents.executeJavaScript('window.__LEXUEPEIYOU_LOGIN_RESULT__')
                    .then((result) => {
                        saveLexuepeiyouLoginResult(result);
                    }).catch(() => {});
                    return;
                }

                if (login_name == 'xiaoeapp') {
                    win.webContents.executeJavaScript('window.__XIAOEAPP_RESULT__')
                    .then((result) => {
                        if (result && result.token) {
                            fs.exists(cookies_file, function(exist) {
                                let cookies_obj = {};
                                if (exist) {
                                    try {
                                        let data = fs.readFileSync(cookies_file);
                                        cookies_obj = JSON.parse(data.toString());
                                    } catch (error) {
                                        cookies_obj = {};
                                    }
                                }
                                let cookie_value = '';
                                const parts = [
                                    ['token', result.token || ''],
                                    ['b_user_id', result.b_user_id || ''],
                                    ['app_user_id', result.app_user_id || ''],
                                    ['union_id', result.union_id || result.app_user_id || ''],
                                ];
                                parts.forEach(([name, value]) => {
                                    if (!value) {
                                        return;
                                    }
                                    if (cookie_value.length !== 0) {
                                        cookie_value += ';';
                                    }
                                    cookie_value += name + '=' + value;
                                });
                                cookies_obj[login_name] = cookie_value;
                                fs.writeFile(cookies_file, JSON.stringify(cookies_obj), function(){
                                    app.quit();
                                });
                            });
                        }
                    }).catch(() => {});
                } else if (login_name == 'renrenjiang') {
                    win.webContents.executeJavaScript(`
                        (() => {
                            function safeParse(value) {
                                if (!value) {
                                    return null;
                                }
                                try {
                                    return JSON.parse(value);
                                } catch (error) {
                                    return null;
                                }
                            }

                            function pickToken(value) {
                                if (!value) {
                                    return '';
                                }
                                if (typeof value === 'string') {
                                    var parsed = safeParse(value);
                                    if (parsed && typeof parsed === 'object') {
                                        return parsed.id || parsed.token || parsed.value || value;
                                    }
                                    return value;
                                }
                                if (typeof value === 'object') {
                                    return value.id || value.token || value.value || '';
                                }
                                return '';
                            }

                            var href = window.location.href || '';
                            var tokenMatch = href.match(/[?#&]access_token=([^&#]+)/);
                            var accessToken = tokenMatch ? decodeURIComponent(tokenMatch[1]) : '';
                            var tokenRaw = localStorage.getItem('_token') || '';
                            var refreshRaw = localStorage.getItem('_refresh_token') || '';
                            var userRaw = localStorage.getItem('_ukit') || '';
                            var userObj = safeParse(userRaw);
                            if (!userObj || typeof userObj !== 'object') {
                                userObj = {};
                            }
                            var adminTokenMatch = (document.cookie || '').match(/(?:^|;\\s*)Admin-Token=([^;]+)/);
                            var adminToken = adminTokenMatch ? decodeURIComponent(adminTokenMatch[1]) : '';
                            var storageAccessToken = pickToken(localStorage.getItem('access_token') || '')
                                || pickToken(sessionStorage.getItem('access_token') || '')
                                || pickToken(tokenRaw)
                                || adminToken;
                            var tokenValue = pickToken(tokenRaw) || adminToken || storageAccessToken;
                            var refreshValue = pickToken(refreshRaw);
                            return {
                                href: href,
                                access_token: accessToken || storageAccessToken,
                                token: tokenValue,
                                refresh_token: refreshValue,
                                user_id: userObj.id || userObj.user_id || '',
                                user: userObj,
                                admin_token: adminToken,
                            };
                        })();
                    `).then((result) => {
                        if (result && (result.access_token || result.token)) {
                            fs.exists(cookies_file, function(exist) {
                                let cookies_obj = {};
                                if (exist) {
                                    try {
                                        let data = fs.readFileSync(cookies_file);
                                        cookies_obj = JSON.parse(data.toString());
                                    } catch (error) {
                                        cookies_obj = {};
                                    }
                                }
                                cookies_obj[login_name] = JSON.stringify(result);
                                fs.writeFile(cookies_file, JSON.stringify(cookies_obj), function(){
                                    app.quit();
                                });
                            });
                        }
                    }).catch(() => {});
                } else if (login_name == 'ledu') {
                    win.webContents.executeJavaScript(`
                        (() => ({
                            payload: window.__LEDU_LOGIN_RESULT__ || null,
                            debug: window.__LEDU_LOGIN_DEBUG__ || null,
                        }))();
                    `).then(async (result) => {
                        if (ledu_save_inflight) {
                            return;
                        }
                        ledu_save_inflight = true;
                        const storedPayload = normalizeLeduPayload(readStoredLoginPayload('ledu'));
                        let livePayload = mergeLeduPayload(
                            result && result.debug ? normalizeLeduPayload(result.debug.payload) : {},
                            result && result.payload ? normalizeLeduPayload(result.payload) : {}
                        );
                        livePayload = enrichLeduPayloadFromDebug(livePayload, result && result.debug ? result.debug : null);
                        const freshPayload = getLeduFreshLoginPayload(result);
                        let mergedPayload = freshPayload;
                        try {
                            if (Object.keys(mergedPayload).length) {
                                mergedPayload = await normalizeLeduPayloadForPc(mergedPayload);
                            }
                        } catch (error) {
                            mergedPayload = normalizeLeduPayload(mergedPayload);
                        }
                        try {
                            if (result && result.debug) {
                                writeLeduDebugSnapshot(Object.assign({}, result.debug, {
                                    payload: mergedPayload,
                                    live_payload: livePayload,
                                    fresh_payload: freshPayload,
                                    has_fresh_login_evidence: !!Object.keys(freshPayload).length,
                                    stored_payload: storedPayload,
                                    updated_at: Date.now(),
                                }));
                            }
                            const readyToExit = isLeduPayloadReady(mergedPayload);
                            if (Object.keys(freshPayload).length && (isLeduPayloadBetter(mergedPayload, storedPayload) || readyToExit)) {
                                saveLoginPayload(mergedPayload, { exit: readyToExit });
                            }
                        } finally {
                            ledu_save_inflight = false;
                        }
                    }).catch(() => {});
                } else if (login_name == 'minshi') {
                    win.webContents.executeJavaScript(`
                        (() => {
                            function safeParse(value) {
                                if (!value) {
                                    return null;
                                }
                                try {
                                    return JSON.parse(value);
                                } catch (error) {
                                    return null;
                                }
                            }

                            function normalizePayload(value) {
                                if (!value) {
                                    return null;
                                }
                                if (typeof value === 'string') {
                                    value = safeParse(value);
                                }
                                if (!value || typeof value !== 'object' || Array.isArray(value)) {
                                    return null;
                                }
                                var token = '';
                                ['token', 'authorization', 'Authorization', 'access_token', 'accessToken'].some((key) => {
                                    var current = value[key];
                                    if (typeof current === 'string' && current.trim()) {
                                        token = current.trim();
                                        return true;
                                    }
                                    return false;
                                });
                                if (!token) {
                                    return null;
                                }
                                return value;
                            }

                            return normalizePayload(localStorage.getItem('user'))
                                || normalizePayload(sessionStorage.getItem('user'))
                                || null;
                        })();
                    `).then((result) => {
                        if (result && result.token) {
                            saveLoginPayload(result);
                        }
                    }).catch(() => {});
                } else if (login_name == 'yangcong') {
                    win.webContents.executeJavaScript(`
                        (() => {
                            var value = '';
                            try {
                                value = localStorage.getItem('authorization') || sessionStorage.getItem('authorization') || '';
                            } catch (error) {
                                value = '';
                            }
                            return value;
                        })();
                    `).then((authorization) => {
                        if (authorization) {
                            saveLoginCookieValue('authorization=' + authorization);
                        }
                    }).catch(() => {});
                } else if (login_name == 'baitong' && !cookies.some(cookie => cookie.name == 'zk_token' && cookie.value)) {
                    win.webContents.executeJavaScript(`
                        (() => {
                            try {
                                return localStorage.getItem('zk_token') || sessionStorage.getItem('zk_token') || '';
                            } catch (error) {
                                return '';
                            }
                        })();
                    `).then((token) => {
                        token = String(token || '').trim();
                        if (token) {
                            saveLoginCookieValue('zk_token=' + token);
                        }
                    }).catch(() => {});
                } else if (((login_name == 'yizhiknow' || login_name == 'wowtiku') && cookies.length < 1) || (login_name == 'haiyangknow' && !cookies.some(cookie => cookie.name == 'Admin-Token' && cookie.value))) {
                    win.webContents.executeJavaScript(`
                        (() => {
                            function safeParse(value) {
                                if (!value) {
                                    return null;
                                }
                                try {
                                    return JSON.parse(value);
                                } catch (error) {
                                    return null;
                                }
                            }

                            function isTokenLike(value) {
                                if (typeof value !== 'string') {
                                    return false;
                                }
                                return value.length >= 32 && /^[A-Za-z0-9._-]+$/.test(value);
                            }

                            function pickToken(value) {
                                if (!value) {
                                    return '';
                                }
                                if (typeof value === 'string') {
                                    var parsed = safeParse(value);
                                    if (parsed && typeof parsed === 'object') {
                                        return pickToken(parsed);
                                    }
                                    return isTokenLike(value) ? value : '';
                                }
                                if (Array.isArray(value)) {
                                    for (var i = 0; i < value.length; i++) {
                                        var arrToken = pickToken(value[i]);
                                        if (arrToken) {
                                            return arrToken;
                                        }
                                    }
                                    return '';
                                }
                                if (typeof value === 'object') {
                                    var keys = ['Admin-Token', 'Access-Token', 'access_token', 'accessToken', 'zk_token', 'token', 'Token'];
                                    for (var k = 0; k < keys.length; k++) {
                                        var direct = value[keys[k]];
                                        if (isTokenLike(direct)) {
                                            return direct;
                                        }
                                    }
                                    for (var key in value) {
                                        if (!Object.prototype.hasOwnProperty.call(value, key)) {
                                            continue;
                                        }
                                        var nestedToken = pickToken(value[key]);
                                        if (nestedToken) {
                                            return nestedToken;
                                        }
                                    }
                                }
                                return '';
                            }

                            function scanStorage(storage) {
                                if (!storage) {
                                    return '';
                                }
                                var directKeys = ['Admin-Token', 'Access-Token', 'access_token', 'accessToken', 'zk_token', 'token', 'Token'];
                                for (var i = 0; i < directKeys.length; i++) {
                                    var directValue = storage.getItem(directKeys[i]);
                                    var directToken = pickToken(directValue);
                                    if (directToken) {
                                        return directToken;
                                    }
                                }
                                for (var j = 0; j < storage.length; j++) {
                                    var key = storage.key(j);
                                    var value = storage.getItem(key);
                                    if (!value) {
                                        continue;
                                    }
                                    if (key && key.toLowerCase().indexOf('token') !== -1) {
                                        var guessed = pickToken(value);
                                        if (guessed) {
                                            return guessed;
                                        }
                                    }
                                    var parsed = safeParse(value);
                                    var parsedToken = pickToken(parsed);
                                    if (parsedToken) {
                                        return parsedToken;
                                    }
                                }
                                return '';
                            }

                            var href = window.location.href || '';
                            var hrefMatch = href.match(/[?#&](?:Access-Token|access_token|accessToken|zk_token|token)=([^&#]+)/i);
                            var hrefToken = hrefMatch ? decodeURIComponent(hrefMatch[1]) : '';
                            var token = hrefToken || scanStorage(localStorage) || scanStorage(sessionStorage);
                            return {
                                href: href,
                                token: token,
                            };
                        })();
                    `).then((result) => {
                        if (result && result.token) {
                            saveLoginCookieValue((login_name == 'haiyangknow' ? 'Admin-Token=' : 'token=') + result.token);
                        }
                    }).catch(() => {});
                } else if (login_name == 'plaso') {
                    win.webContents.executeJavaScript('window.__PLASO_LOGIN_RESULT__')
                    .then((result) => {
                        if (result && result.success && result.accessToken) {
                            saveLoginCookieValue('access_token=' + result.accessToken);
                        }
                    }).catch(() => {});
                } else if (login_name == 'aiwenyun' || login_name == 'jhpy') {
                    win.webContents.executeJavaScript('window.__LOCAL_LOGIN_RESULT__')
                    .then((result) => {
                        if (result && result.success && result.token) {
                            saveLoginCookieValue('access_token=' + result.token);
                        }
                    }).catch(() => {});
                } else if (login_name == 'huoke') {
                    win.webContents.executeJavaScript('window.__HUOKE_LOGIN_RESULT__')
                    .then((result) => {
                        if (result && result.success && (result.cookieValue || result.token)) {
                            saveLoginCookieValue(result.cookieValue || ('Accesstoken=' + result.token));
                        }
                    }).catch(() => {});
                } else if ((login_name == 'mddclass' || login_name == 'sihaigongkao')) {
                    trySaveMddclassLoginResult(win, cookies, true);
                    return;
                } else if (login_name == 'cctalk') {
                    trySaveCctalkLoginResult(win, cookies, true);
                    return;
                } else if (login_name == 'classin') {
                    win.webContents.executeJavaScript('window.__CLASSIN_LOGIN_RESULT__')
                    .then((result) => {
                        if (result && result.success && !classin_login_closing) {
                            classin_login_success = true;
                            classin_login_closing = true;
                            setTimeout(() => {
                                app.quit();
                            }, 500);
                        }
                    }).catch(() => {});
                } else if (login_name == 'icourses') {
                    win.webContents.executeJavaScript(`
                        ({
                            token: localStorage.getItem('icourses_website_user_token') || '',
                            userInfo: localStorage.getItem('icourses_website_user_info') || '',
                        });
                    `).then((icourses_result) => {
                        if (icourses_result && icourses_result.token) {
                            fs.exists(cookies_file, function(exist) {
                                let cookies_obj = {};
                                if (exist) {
                                    try {
                                        let data = fs.readFileSync(cookies_file);
                                        cookies_obj = JSON.parse(data.toString());
                                    } catch (error) {
                                        cookies_obj = {};
                                    }
                                }
                                let cookie_value = '';
                                cookies.forEach(cookie=>{
                                    if (cookie_value.length != 0) {
                                        cookie_value += ';';
                                    }
                                    cookie_value += cookie.name+'='+cookie.value;
                                })
                                if (cookie_value.length != 0) {
                                    cookie_value += ';';
                                }
                                cookie_value += 'icourses_website_user_token=' + icourses_result.token;
                                if (icourses_result.userInfo) {
                                    cookie_value += ';icourses_website_user_info=' + encodeURIComponent(icourses_result.userInfo);
                                }
                                cookies_obj[login_name] = cookie_value;
                                fs.writeFile(cookies_file, JSON.stringify(cookies_obj), function(){
                                    app.quit();
                                });
                            });
                        }
                    }).catch(() => {});
                } else if (login_name == 'lizhiweike') {
                    injectLizhiweikeLoginSwitcher(win);
                    saveLizhiweikeLoginResult(win);
                } else if (isDuanshuLoginName(login_name) && cookies.length < 1) {
                    // 短书 H5 使用 storage，PC 详情页使用 userInfo_<env> cookie。
                    win.webContents.executeJavaScript(`
                        function readMember(storage) {
                            if (!storage) return null;
                            for (var i = 0; i < storage.length; i++) {
                                var key = storage.key(i);
                                if (!key || (key.indexOf('userinfo_production') === -1 && key.indexOf('user_info_production') === -1 && key.indexOf('userInfo_') !== 0 && key.indexOf('x-member') === -1)) continue;
                                var value = storage.getItem(key);
                                var text = String(value || '').trim();
                                var obj = null;
                                try {
                                    try { text = decodeURIComponent(text); } catch (decodeError1) {}
                                    try { text = decodeURIComponent(text); } catch (decodeError2) {}
                                    obj = JSON.parse(text);
                                    if (obj && typeof obj.value === 'string') {
                                        var inner = obj.value;
                                        try { inner = decodeURIComponent(inner); } catch (decodeError3) {}
                                        try { inner = decodeURIComponent(inner); } catch (decodeError4) {}
                                        obj = JSON.parse(inner);
                                    }
                                } catch (error) {
                                    obj = null;
                                }
                                var member_id = obj ? (obj.id || obj.member_id || obj.memberId) : '';
                                if (!obj || !member_id || !obj.signature) continue;
                                var parts = key.split('.');
                                return {member: value, shop_id: parts.length > 1 ? parts[0] : (obj.shop_id || obj.shopId || '')};
                            }
                            return null;
                        }
                        var result = readMember(localStorage) || readMember(sessionStorage);
                        ({
                            cookies: result ? [{name: 'x-member', value: result.member}, {name: 'x-shop', value: result.shop_id || ''}] : [],
                            href: window.location.href,
                        });
                    `).then((duanshu_result) => {
                        const ls_cookies = (duanshu_result && duanshu_result.cookies) || [];
                        const current_url = (duanshu_result && duanshu_result.href) || '';
                        const x_member = ls_cookies.find(c => c.name === 'x-member' && c.value);
                        if (x_member) {
                            duanshu_redirect_ticks = 0;
                            const x_shop = ls_cookies.find(c => c.name === 'x-shop' && c.value);
                            saveDuanshuCookieValue(x_member.value, x_shop ? x_shop.value : '');
                        } else if (current_url.includes('duanshu.com') && !current_url.includes('system/mlogin')) {
                            duanshu_redirect_ticks = 0;
                        } else {
                            duanshu_redirect_ticks = 0;
                        }
                    }).catch((error) => {
                        ;
                    });
                } else if ((login_name.includes('baijiayunxiao') || login_name == 'kaimingzhixue' || login_name == 'jinbangshidai') && cookies.length < 1) {
                    var keys = login_name == 'jinbangshidai' ? ['ToKen'] : ['studentToken'];
                    win.webContents.executeJavaScript(`
                        var keys = ${JSON.stringify(keys)};
                        var cookies = [];
                        keys.forEach(key => {
                            var value = localStorage.getItem(key);
                            if (value) {
                                cookies.push({
                                    name: key.split('/')[1] || key,
                                    value: value,
                                });
                            }
                        });
                        cookies;
                    `).then((cookies) => {
                        // console.log(cookies);
                        if (cookies.length == 1) {
                            fs.exists(cookies_file, function(exist) {
                                let cookies_obj = {};
                                if (exist) {
                                    try {
                                        let data = fs.readFileSync(cookies_file);
                                        cookies_obj = JSON.parse(data.toString());
                                    } catch (error) {
                                        // console.error('[login-mooc] read cookie file failed:', cookies_file, error && error.stack || error);
                                        cookies_obj = {};
                                    }
                                }
                                let cookie_value = '';
                                cookies.forEach(cookie=>{
                                    if (cookie_value.length != 0) {
                                        cookie_value += ';';
                                    }
                                    cookie_value += cookie.name+'='+cookie.value;
                                })
                                // console.log(cookies);
                                cookies_obj[login_name] = cookie_value;
                                fs.writeFile(cookies_file, JSON.stringify(cookies_obj), function(){
                                    app.quit();
                                });
                            });
                        }
                    }).catch((error) => {
                        ;
                    });
                } else if (login_name == 'htknow' && cookies.length < 7) {
                    var keys = ['base_KEY', 'token', 'custom_id', 'user', 'wechatList', 'appletList', 'ksList'];
                    win.webContents.executeJavaScript(`
                        var keys = ${JSON.stringify(keys)};
                        var cookies = [];
                        keys.forEach(key => {
                            var value = localStorage.getItem(key);
                            if (value) {
                                cookies.push({
                                    name: key.split('/')[1] || key,
                                    value: value,
                                });
                            }
                        });
                        cookies;
                    `).then((cookies) => {
                        // console.log(cookies);
                        if (cookies.length == 7 ) {
                            fs.exists(cookies_file, function(exist) {
                                let cookies_obj = {};
                                if (exist) {
                                    try {
                                        let data = fs.readFileSync(cookies_file);
                                        cookies_obj = JSON.parse(data.toString());
                                    } catch (error) {
                                        console.error('[login-mooc] read cookie file failed:', cookies_file, error && error.stack || error);
                                        cookies_obj = {};
                                    }
                                }
                                let cookie_value = '';
                                cookies.forEach(cookie=>{
                                    if (cookie_value.length != 0) {
                                        cookie_value += ';';
                                    }
                                    cookie_value += cookie.name+'='+cookie.value;
                                })
                                // console.log(cookies);
                                cookies_obj[login_name] = cookie_value;
                                fs.writeFile(cookies_file, JSON.stringify(cookies_obj), function(){
                                    app.quit();
                                });
                            });
                        }
                    }).catch((error) => {
                        ;
                    });
                } else if (login_name == 'houduweilai' && cookies.length < 1) {
                    win.webContents.executeJavaScript(`
                        ({
                            token: localStorage.getItem('user-token') || '',
                            userInfo: localStorage.getItem('user-info') || '',
                        });
                    `).then((houdu_result) => {
                        if (houdu_result && houdu_result.token) {
                            let cookie_value = 'user-token=' + houdu_result.token;
                            if (houdu_result.userInfo) {
                                cookie_value += ';user-info=' + encodeURIComponent(houdu_result.userInfo);
                            }
                            saveLoginCookieValue(cookie_value);
                        }
                    }).catch((error) => {
                        ;
                    });
                } else if (login_name == 'iqihang' && cookies.length < 1) {
                    var keys = ['accessToken'];
                    win.webContents.executeJavaScript(`
                        var keys = ${JSON.stringify(keys)};
                        var cookies = [];
                        keys.forEach(key => {
                            var value = localStorage.getItem(key);
                            if (value) {
                                cookies.push({
                                    name: key.split('/')[1] || key,
                                    value: value,
                                });
                            }
                        });
                        cookies;
                    `).then((cookies) => {
                        // console.log(cookies);
                        if (cookies.length == 1 ) {
                            fs.exists(cookies_file, function(exist) {
                                let cookies_obj = {};
                                if (exist) {
                                    try {
                                        let data = fs.readFileSync(cookies_file);
                                        cookies_obj = JSON.parse(data.toString());
                                    } catch (error) {
                                        console.error('[login-mooc] read cookie file failed:', cookies_file, error && error.stack || error);
                                        cookies_obj = {};
                                    }
                                }
                                let cookie_value = '';
                                cookies.forEach(cookie=>{
                                    if (cookie_value.length != 0) {
                                        cookie_value += ';';
                                    }
                                    cookie_value += cookie.name+'='+cookie.value;
                                })
                                // console.log(cookies);
                                cookies_obj[login_name] = cookie_value;
                                fs.writeFile(cookies_file, JSON.stringify(cookies_obj), function(){
                                    app.quit();
                                });
                            });
                        }
                    }).catch((error) => {
                        ;
                    });
                } else if (login_name == 'zixueb') {
                    win.webContents.executeJavaScript(`
                        (() => {
                            try {
                                return localStorage.getItem('__token__') || '';
                            } catch (error) {
                                return '';
                            }
                        })();
                    `).then((token) => {
                        token = String(token || '').trim();
                        if (token) {
                            saveLoginCookieValue('__token__=' + token);
                        }
                    }).catch((error) => {
                        ;
                    });
                    return;
                } else if (login_name == 'jhpyedu') {
                    win.webContents.executeJavaScript(`
                        (async () => {
                            try {
                                let token = localStorage.getItem('token') || '';
                                token = String(token || '').trim().replace(/^Bearer\\s+/i, '');
                                if (!token) {
                                    return '';
                                }
                                const response = await fetch('/api/uber/campus/usercenter/user/getUserInfo', {
                                    method: 'GET',
                                    headers: {
                                        'Authorization': 'Bearer ' + token,
                                        'Use-Scene': '99',
                                        'token-scene': '105',
                                        'domainType': 'py',
                                        'Content-Type': 'application/json',
                                    },
                                });
                                if (!response.ok) {
                                    return '';
                                }
                                const result = await response.json();
                                const user = result && result.data;
                                return String(result && result.code) === '200'
                                    && user && (user.id || user.userId) ? token : '';
                            } catch (error) {
                                return '';
                            }
                        })();
                    `, true).then((token) => {
                        token = String(token || '').trim();
                        if (token) {
                            saveLoginCookieValue('token=' + token);
                        }
                    }).catch(() => {});
                    return;
                } else if (login_name == 'moremeditation') {
                    win.webContents.executeJavaScript(`
                        (() => {
                            try {
                                const direct = localStorage.getItem('token') || sessionStorage.getItem('token') || '';
                                if (direct) {
                                    return direct;
                                }
                                for (let i = 0; i < localStorage.length; i++) {
                                    const key = localStorage.key(i);
                                    if (key && key.toLowerCase() === 'token') {
                                        const value = localStorage.getItem(key);
                                        if (value) {
                                            return value;
                                        }
                                    }
                                }
                            } catch (error) {
                                ;
                            }
                            return '';
                        })();
                    `).then((token) => {
                        token = String(token || '').trim();
                        if (token) {
                            saveLoginCookieValue('token=' + token);
                        }
                    }).catch((error) => {
                        ;
                    });
                    return;
                } else if (login_name == 'yukebang') {
                    saveYukebangLoginResult(win);
                    return;
                } else if (isShanganLoginName()) {
                    saveShanganLoginResult(win, cookies);
                    return;
                } else if (login_name == 'nmkjxy') {
                    win.webContents.executeJavaScript(`
                        (() => {
                            try {
                                const direct = localStorage.getItem('token') || sessionStorage.getItem('token') || '';
                                if (direct) {
                                    return direct;
                                }
                                for (let i = 0; i < localStorage.length; i++) {
                                    const key = localStorage.key(i);
                                    if (key && key.toLowerCase() === 'token') {
                                        const value = localStorage.getItem(key);
                                        if (value) {
                                            return value;
                                        }
                                    }
                                }
                            } catch (error) {
                                ;
                            }
                            return '';
                        })();
                    `).then((token) => {
                        token = String(token || '').trim();
                        if (token) {
                            saveLoginCookieValue('token=' + token);
                        }
                    }).catch((error) => {
                        ;
                    });
                    return;
                } else if (login_name == 'speiyou') {
                    trySaveSpeiyouLoginResult(win).catch((error) => {
                        ;
                    });
                    return;
                }

                if (dingtalk_yunxuetang_login) {
                    trySaveDingtalkYunxuetangLoginResult(win);
                    return;
                }
                if (dingtalk_yunketang_login) {
                    if (hasDingtalkLoginCookies(cookies)) {
                        saveLoginCookieValue(JSON.stringify({dingtalkCookie: buildCookieValue(cookies)}), 'dingtalk.yunketang');
                    }
                    return;
                }
                if (login_name == 'sanjieke' && !hasSanjiekeLoginCookies(cookies)) {
                    return;
                }
                if (login_name == 'aishangke' && !hasAishangkeLoginCookies(cookies)) {
                    return;
                }
                if (login_name == 'xiaoheiketang' && !cookies.some(cookie => cookie.name == 'xhkt-Token' && cookie.value)) {
                    return;
                }
                if (login_name == 'dongao' && !hasDongaoLoginCookies(cookies)) {
                    return;
                }
                if (login_name == 'dingtalk' && !hasDingtalkLoginCookies(cookies)) {
                    return;
                }
                if (login_name == 'chaoge' && !hasChaogeLoginCookies(cookies)) {
                    return;
                }
                if (login_name == 'shanxiang' && !hasShanxiangLoginCookies(cookies)) {
                    return;
                }
                if (login_name == 'shikaobang' && !hasShikaobangLoginCookies(cookies)) {
                    return;
                }
                if (login_name == 'yiqikaojiaoshi' && !hasYiqikaojiaoshiLoginCookies(cookies)) {
                    return;
                }
                if (isFenbiLoginName(login_name) && !hasFenbiLoginCookies(cookies)) {
                    return;
                }
                if (login_name == 'yiihuu' && !hasYiihuuLoginCookies(cookies)) {
                    return;
                }
                if (login_name == 'ahuyikao') {
                    trySaveAhuCookies(cookies);
                    return;
                }

                if (cookies.length != 0) {
                    // console.log(cookies);
                    if (login_name == 'yikaijiang') {
                        const cookie_value = buildCookieValue(cookies);
                        validateYikaijiangCookieValue(cookie_value).then((valid) => {
                            if (valid) {
                                saveLoginCookieValue(cookie_value);
                            }
                        });
                    } else if (login_name == 'zhongxunwx') {
                        const cookie_value = buildCookieValue(cookies);
                        validateZhongxunwxCookieValue(cookie_value).then((valid) => {
                            if (valid) {
                                saveLoginCookieValue(cookie_value);
                            }
                        });
                    } else if (login_name == 'dxy') {
                        const cookie_value = buildCookieValue(cookies);
                        validateDxyCookieValue(cookie_value).then((valid) => {
                            if (valid) {
                                saveLoginCookieValue(cookie_value);
                            }
                        });
                    } else if (login_name == 'educity') {
                        const cookie_value = buildCookieValue(cookies);
                        validateEducityCookieValue(cookie_value).then((valid) => {
                            if (valid) {
                                saveLoginCookieValue(cookie_value);
                            }
                        });
                    } else if (login_name == 'zhihuishu' && cookies.length < 4) {
                        win.loadURL(second_login_url);
                    } else if (login_name == 'keqq' && cookies.length < 4) {
                        ;
                    } else if (login_name == 'chaoxing' && cookies.length < 5) {
                        ;
                    } else if (login_name == 'vqq' && cookies.length < 2) {
                        ;
                    } else if (login_name == 'meeting' && cookies.length < 3) {
                        ;
                    } else if (login_name == 'dingtalk' && cookies.length < 2) {
                        ;
                    } else if (login_name == 'icve' && cookies.length < 1) {
                        ;
                    } else if (login_name == 'yikaijiang' && !cookies.some(cookie => cookie.name == 'JSESSIONID' && cookie.value)) {
                        ;
                    } else if (login_name == 'beichenlinxuan' && !cookies.some(cookie => cookie.name == 'token' && cookie.value)) {
                        ;
                    } else if (login_name == 'eoffcn' && cookies.length < 1) {
                        ;
                    } else if (login_name == 'koolearn' && cookies.length < 2) {
                        ;
                    } else if (login_name == 'study163' && cookies.length < 1) {
                        ;
                    } else if (login_name == 'open163' && !cookies.some(cookie => ['NTES_OSESS', 'P_OINFO', 'NTES_YD_SESS', 'NTES_YD_PASSPORT'].includes(cookie.name) && cookie.value)) {
                        ;
                    } else if (login_name == 'open163') {
                        saveLoginCookieValue(buildCookieValue(cookies));
                    } else if (login_name == 'xiaoetech' && xiaoetech_login_mode == 'pc') {
                        ;
                    } else if (login_name.includes('xiaoetech') && cookies.length < 1) {
                        ;
                    } else if (login_name == 'xiaoetech' && getSafeWindowUrl(win).includes('bindPhoneNumber')) {
                        ;
                    } else if (login_name == 'qlchat' && cookies.length < 3) {
                        ;
                    } else if (login_name == 'qianliao' && cookies.length < 2) {
                        ;
                    } else if (login_name == 'xuelang' && cookies.length < 1) {
                        ;
                    } else if (login_name.includes('gaotu') && cookies.length < 2) {
                        ;
                    } else if (login_name == 'todoen' && !cookies.some(cookie => cookie.name == 'userid' && cookie.value)) {
                        ;
                    } else if (login_name.includes('xiwang') && login_name != 'xiwang.youke' && cookies.length < 2) {
                        ;
                    } else if (login_name == 'xueersi' && cookies.length < 2) {
                        ;
                    } else if (login_name == 'orangevip' && cookies.length < 2) {
                        ;
                    } else if (login_name == 'gaodun' && cookies.length < 1) {
                        ;
                    } else if (login_name == 'xuetian' && !hasXuetianLoginCookie(cookies)) {
                        ;
                    } else if (login_name == 'geekbang') {
                        trySaveGeekbangLoginResult(win, cookies);
                    } else if (login_name == 'yuketang' && !cookies.some(cookie => cookie.name == 'sessionid' && cookie.value)) {
                        ;
                    } else if (login_name == 'kandian' && (!cookies.some(cookie => cookie.name == 'uid' && cookie.value) || !cookies.some(cookie => cookie.name == 'sessionkey' && cookie.value))) {
                        ;
                    } else if (login_name == 'yincheng' && !cookies.some(cookie => cookie.name == 'accessToken' && cookie.value)) {
                        ;
                    } else if (login_name == 'wrclass' && !cookies.some(cookie => cookie.name == 'user_token' && cookie.value)) {
                        ;
                    } else if (login_name == 'eduzhixin' && !cookies.some(cookie => cookie.name == 'Authorization' && cookie.value)) {
                        ;
                    } else if (login_name == 'dqb') {
                        const token_cookie = cookies.find(cookie => cookie.name == 'NEEDSTOKEN' && cookie.value);
                        if (token_cookie) {
                            const token = token_cookie.value;
                            win.webContents.executeJavaScript(`
                                fetch('/user/learn/all/courses', {
                                    credentials: 'include',
                                    headers: {'X-Token': ${JSON.stringify(token)}}
                                }).then(response => response.text())
                                  .then(text => text.indexOf('/user/logout') >= 0)
                                  .catch(() => false)
                            `).then((valid) => {
                                if (valid) {
                                    saveLoginCookieValue('NEEDSTOKEN=' + token);
                                }
                            }).catch(() => {});
                        }
                    } else if (login_name == 'xsteach' && !cookies.some(cookie => cookie.name == 'xsteachID' && cookie.value)) {
                        ;
                    } else if (login_name == 'magedu') {
                        trySaveMageduLoginResult(win, filterMageduCookies(cookies));
                    } else if (login_name == 'jingtongxue') {
                        trySaveJingtongxueLoginResult(win, filterJingtongxueCookies(cookies));
                    } else if (login_name == 'caixuetang') {
                        trySaveCaixuetangLoginResult(win, filterCaixuetangCookies(cookies));
                    } else if (login_name == 'luffycity') {
                        trySaveLuffycityLoginResult(win, filterLuffycityCookies(cookies));
                    } else if (login_name == 'youlu' && !cookies.some(cookie => cookie.name == 'TOKEN' && cookie.value)) {
                        ;
                    } else if (login_name == 'itbaizhan' && !cookies.some(cookie => cookie.name == 'token')) {
                        ;
                    } else if (login_name == 'nmkjxy') {
                        ;
                    } else if (login_name == 'mashibing' && !cookies.some(cookie => cookie.name == 'token' && cookie.value)) {
                        ;
                    } else if (login_name == 'xiaoyuanyouke') {
                        trySaveXiaoyuanyoukeLoginResult(win, cookies).catch((error) => {
                            ;
                        });
                    } else if (login_name == 'todoen') {
                        trySaveTodoenLoginResult(win, cookies).catch((error) => {
                            ;
                        });
                    } else if (login_name == 'unipus') {
                        trySaveUnipusCookies(cookies);
                    } else if (login_name == 'cnmooc') {
                        trySaveCnmoocCookies(cookies, win);
                    } else if (login_name == 'chinesemooc' && !isChinesemoocPostLoginUrl(getSafeWindowUrl(win))) {
                        ;
                    } else if (login_name == 'chaoge') {
                        const cookie_value = buildCookieValue(cookies);
                        validateChaogeCookieValue(cookie_value).then((valid) => {
                            if (!valid) {
                                return;
                            }
                            saveLoginCookieValue(cookie_value);
                        });
                    } else if (login_name == 'shanxiang') {
                        const cookie_value = buildCookieValue(cookies);
                        validateShanxiangCookieValue(cookie_value).then((valid) => {
                            if (!valid) {
                                return;
                            }
                            saveLoginCookieValue(cookie_value);
                        });
                    } else if (login_name == 'shikaobang') {
                        trySaveShikaobangLoginResult(win, cookies);
                    } else if (login_name == 'yiqikaojiaoshi') {
                        const cookie_value = buildCookieValue(cookies);
                        validateYiqikaojiaoshiCookieValue(cookie_value).then((valid) => {
                            if (!valid) {
                                return;
                            }
                            saveLoginCookieValue(cookie_value);
                        });
                    } else if (isFenbiLoginName(login_name)) {
                        const cookie_value = buildCookieValue(cookies);
                        validateFenbiCookieValue(cookie_value).then((valid) => {
                            if (!valid) {
                                return;
                            }
                            saveLoginCookieValue(cookie_value);
                        });
                    } else if (login_name == 'yixiaoerguo') {
                        ;
                    } else if (login_name == 'yangcong') {
                        ;
                    } else if (login_name == 'huke88' && !cookies.some(cookie => cookie.name == '_identity-usernew' && cookie.value)) {
                        ;
                    } else if (login_name == 'kaimingzhixue' && cookies.length < 1) {
                        ;
                    } else if (login_name == 'wangxiao233' && !hasWangxiao233LoginCookies(cookies)) {
                        ;
                    } else if ((login_name == 'mddclass' || login_name == 'sihaigongkao') && !hasMddclassLoginCookies(cookies)) {
                        ;
                    } else if (login_name == 'wallstreets' && cookies.length < 1) {
                        ;
                    } else if (login_name == 'wallstreets' && (getSafeWindowUrl(win).includes('login') || getSafeWindowUrl(win).includes('register') || getSafeWindowUrl(win).includes('qq.com'))) {
                        ;
                    } else if (login_name == 'ydshengxue' && cookies.length < 2) {
                        ;
                    } else if (login_name == 'lizhiweike') {
                        injectLizhiweikeLoginSwitcher(win);
                        saveLizhiweikeLoginResult(win);
                    } else if (login_name == 'htknow' && cookies.length < 6) {
                        ;
                    } else if (login_name == 'haiyangknow' && !cookies.some(cookie => cookie.name == 'Admin-Token' && cookie.value)) {
                        ;
                    } else if (login_name == 'baitong' && !cookies.some(cookie => cookie.name == 'zk_token' && cookie.value)) {
                        ;
                    } else if (login_name == 'icourses') {
                        ;
                    } else if (login_name == 'iqihang' && cookies.length < 1) {
                        ;
                    } else if (login_name.includes('baijiayunxiao') && cookies.length < 1) {
                        ;
                    } else if ((login_name == 'youzan' || login_name.startsWith('youzan.')) && cookies.length < 2) {
                        ;
                    } else if (login_name == '51cto_saas' && !cookies.some(cookie => cookie.name == '51CTO_ATHENA_TOKEN' && cookie.value)) {
                        ;
                    } else if (login_name == '51cto' && !hasCto51LoginCookies(cookies)) {
                        ;
                    } else if (login_name == '51zxw' && !cookies.some(cookie => cookie.name == 'newsMember' && cookie.value)) {
                        ;
                    } else if (login_name == 'med66' && cookies.length < 4) {
                        ;
                    } else if (login_name == 'zhengbao' && cookies.length < 4) {
                        ;
                    } else if (login_name == 'canto' && !cookies.some(cookie => cookie.name == '.AspNetCore.Cookies' && cookie.value)) {
                        ;
                    } else if (login_name == 'jianshe99' && cookies.length < 4) {
                        ;
                    } else if (login_name == 'huatu') {
                        ;
                    } else if (login_name == 'xiaoeapp') {
                        ;
                    } else if (login_name == 'renrenjiang') {
                        ;
                    } else if (login_name == 'youzan' || login_name.startsWith('youzan.')) {
                        handleYouzanPostLogin(win, cookies);
                    } else if (login_name == 'aishangke') {
                        const current_url = getSafeWindowUrl(win);
                        if (!isAishangkeLoggedInUrl(current_url)) {
                            return;
                        }
                        const cookie_value = buildCookieValue(cookies);
                        if (!cookie_value) {
                            return;
                        }
                        saveLoginCookieValue(cookie_value);
                    } else if (login_name == 'med66') {
                        const cookie_value = buildCookieValue(cookies);
                        validateMed66CookieValue(cookie_value).then((valid) => {
                            if (!valid) {
                                return;
                            }
                            saveLoginCookieValue(cookie_value);
                        }).catch((error) => {
                            ;
                        });
                    } else if (login_name == 'zhengbao') {
                        const cookie_value = buildCookieValue(cookies);
                        validateZhengbaoCookieValue(cookie_value).then((valid) => {
                            if (!valid) {
                                return;
                            }
                            saveLoginCookieValue(cookie_value);
                        }).catch((error) => {
                            ;
                        });
                    } else if (login_name == 'canto') {
                        const cookie_value = buildCookieValue(cookies);
                        if (cookie_value && cookie_value.indexOf('.AspNetCore.Cookies=') !== -1) {
                            saveLoginCookieValue(cookie_value);
                        }
                    } else if (login_name == 'jianshe99') {
                        const cookie_value = buildCookieValue(cookies);
                        validateJianshe99CookieValue(cookie_value).then((valid) => {
                            if (!valid) {
                                return;
                            }
                            saveLoginCookieValue(cookie_value);
                        }).catch((error) => {
                            ;
                        });
                    } else if (login_name == 'dongao') {
                        handleDongaoPostLogin(win, cookies);
                    } else if (login_name == 'zlketang') {
                        win.webContents.executeJavaScript(`
                            new Promise((resolve) => {
                                try {
                                    var xhr = new XMLHttpRequest();
                                    xhr.open('GET', 'https://www.zlketang.com/wxpub/api/user_info', true);
                                    xhr.withCredentials = true;
                                    xhr.onreadystatechange = function () {
                                        if (xhr.readyState !== 4) {
                                            return;
                                        }
                                        try {
                                            resolve(JSON.parse(xhr.responseText || '{}'));
                                        } catch (error) {
                                            resolve(null);
                                        }
                                    };
                                    xhr.onerror = function () {
                                        resolve(null);
                                    };
                                    xhr.send(null);
                                } catch (error) {
                                    resolve(null);
                                }
                            });
                        `).then((login_info) => {
                            if (!login_info || Number(login_info.errcode) !== 0) {
                                return;
                            }
                            fs.exists(cookies_file, function(exist) {
                                let cookies_obj = {};
                                if (exist) {
                                    try {
                                        let data = fs.readFileSync(cookies_file);
                                        cookies_obj = JSON.parse(data.toString());
                                    } catch (error) {
                                        cookies_obj = {};
                                    }
                                }
                                let cookie_value = '';
                                cookies.forEach(cookie=>{
                                    if (cookie_value.length != 0) {
                                        cookie_value += ';';
                                    }
                                    cookie_value += cookie.name+'='+cookie.value;
                                })
                                cookies_obj[login_name] = cookie_value;
                                fs.writeFile(cookies_file, JSON.stringify(cookies_obj), function(){
                                    app.quit();
                                });
                            });
                        }).catch((error) => {
                            ;
                        });
                    } else if (login_name == 'yikao88' && cookies.length < 2) {
                        ;
                    } else if (login_name == 'yiihuu') {
                        const cookie_value = buildCookieValue(cookies);
                        if (cookie_value) {
                            saveLoginCookieValue(cookie_value);
                        }
                    } else if (login_name == 'sieredu' && !cookies.some(cookie => cookie.name == 'sid' && cookie.value)) {
                        ;
                    } else if (login_name != 'login' && login_name != 'login_test' && login_name != 'login_weixin' && login_name!= 'login_weixin_test' && login_name!= 'url') {
                        fs.exists(cookies_file, function(exist) {
                            let cookies_obj = {};
                            if (exist) {
                                try {
                                    let data = fs.readFileSync(cookies_file);
                                    cookies_obj = JSON.parse(data.toString());
                                } catch (error) {
                                    // console.error('[login-mooc] read cookie file failed:', cookies_file, error && error.stack || error);
                                    cookies_obj = {};
                                }
                            }
                            let cookie_value = '';
                            cookies.forEach(cookie=>{
                                if (cookie_value.length != 0) {
                                    cookie_value += ';';
                                }
                                cookie_value += cookie.name+'='+cookie.value;
                            })
                            // console.log(cookies);
                            cookies_obj[login_name] = cookie_value;
                            fs.writeFile(cookies_file, JSON.stringify(cookies_obj), function(){
                                app.quit();
                            });
                        });
                    } else {
                        app.quit();
                    }
                }
            }).catch((error) => {
                // console.error('[login-mooc] read cookie file failed:', cookies_file, error && error.stack || error);
                app.quit();
            })
        }
    }, 1000);
}

function generateRandomString(length) {
    const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
        result += characters.charAt(Math.floor(Math.random() * characters.length));
    }
    return result;
}

function writeCourseSelectorClosedResult(status = 'closed', reason = '') {
    if (login_name != 'course_selector') {
        return;
    }
    const job_path = String(extra_arg || '');
    if (!job_path || !fs.existsSync(job_path)) {
        return;
    }
    let selector_job = null;
    try {
        selector_job = JSON.parse(fs.readFileSync(job_path, 'utf8'));
    } catch (error) {
        return;
    }
    const result_path = String(selector_job && selector_job.result_path || '');
    if (!result_path) {
        return;
    }
    const schema_version = Number(selector_job.schema_version || 1);
    const fallback_status = status === 'unavailable' ? 'unavailable' : 'closed';
    try {
        if (fs.existsSync(result_path)) {
            try {
                const current_result = JSON.parse(fs.readFileSync(result_path, 'utf8'));
                const current_status = current_result && current_result.status;
                const selection_shape_valid = !['confirmed', 'advance'].includes(current_status) || (
                    Array.isArray(current_result.selected_ids)
                    && current_result.settings
                    && typeof current_result.settings === 'object'
                    && !Array.isArray(current_result.settings)
                );
                if (
                    Number(current_result && current_result.schema_version) === schema_version
                    && ['confirmed', 'cancelled', 'closed', 'unavailable'].includes(current_status)
                    && selection_shape_valid
                ) {
                    return;
                }
            } catch (error) {
                // Replace an incomplete or incompatible result with a safe close result.
            }
        }
        const temp_path = result_path + '.main.tmp';
        fs.writeFileSync(temp_path, JSON.stringify({
            schema_version,
            status: fallback_status,
            startup_error: ['startup_timeout', 'page_load_failed', 'renderer_crashed',
                'renderer_init_failed', 'window_create_failed'].includes(reason) ? reason : '',
            selected_ids: [],
            settings: selector_job.settings && typeof selector_job.settings === 'object'
                ? selector_job.settings
                : {},
        }), 'utf8');
        if (fs.existsSync(result_path)) {
            fs.unlinkSync(result_path);
        }
        fs.renameSync(temp_path, result_path);
    } catch (error) {
        try {
            fs.unlinkSync(result_path + '.main.tmp');
        } catch (cleanup_error) {
            // The downloader also removes this deterministic temp file on cleanup.
        }
    }
}

function createCourseSelectorWindow() {
    Menu.setApplicationMenu(null);
    let directory_settings = false;
    let ready_path = '';
    try {
        const selector_job = JSON.parse(fs.readFileSync(String(extra_arg || ''), 'utf8'));
        directory_settings = selector_job.stage === 'download_directory';
        ready_path = String(selector_job.ready_path || '');
    } catch (error) {
        // The selector page reports invalid or missing job data.
    }
    let selector_exiting = false;
    let selector_closing = false;
    let startup_timer = null;
    let selector_window = null;
    let window_shown = false;
    let page_ready = false;
    const clearStartupTimer = () => {
        if (startup_timer) clearTimeout(startup_timer);
        startup_timer = null;
    };
    const exitFailedSelector = (reason = 'renderer_crashed') => {
        if (selector_exiting || selector_closing) {
            return;
        }
        selector_exiting = true;
        clearStartupTimer();
        writeCourseSelectorClosedResult('unavailable', reason);
        app.exit(1);
    };
    const showSelector = () => {
        if (window_shown) return true;
        if (selector_exiting || selector_closing || !selector_window || selector_window.isDestroyed()) return false;
        try {
            if (selector_window.isMinimized()) selector_window.restore();
            selector_window.show();
            selector_window.focus();
            window_shown = true;
            return true;
        } catch (error) {
            exitFailedSelector('window_create_failed');
            return false;
        }
    };
    const markSelectorReady = () => {
        if (page_ready || selector_exiting || selector_closing) return;
        try {
            if (!showSelector()) return;
            if (ready_path) {
                fs.writeFileSync(ready_path + '.tmp', JSON.stringify({schema_version: 1, status: 'ready'}), 'utf8');
                fs.renameSync(ready_path + '.tmp', ready_path);
            }
            page_ready = true;
            clearStartupTimer();
        } catch (error) {
            exitFailedSelector('renderer_init_failed');
        }
    };
    const onSelectorReady = event => {
        if (selector_window && event.sender === selector_window.webContents) markSelectorReady();
    };
    const onSelectorError = event => {
        if (selector_window && event.sender === selector_window.webContents) exitFailedSelector('renderer_init_failed');
    };
    try {
        const work_area = screen.getPrimaryDisplay().workAreaSize;
        selector_window = new BrowserWindow({
            title: directory_settings ? '修改下载目录' : '课程下载选择',
            icon: path.join(__dirname, 'xuewuzhi.png'),
            width: Math.min(work_area.width, directory_settings ? 840 : 1240),
            height: Math.min(work_area.height, directory_settings ? 650 : 820),
            minWidth: Math.min(work_area.width, directory_settings ? 540 : 860),
            minHeight: Math.min(work_area.height, directory_settings ? 620 : 640),
            useContentSize: true,
            center: true,
            show: false,
            alwaysOnTop: directory_settings,
            backgroundColor: '#f3f6f4',
            webPreferences: {
                sandbox: false,
                nodeIntegration: true,
                contextIsolation: false,
                webSecurity: true,
            },
        });
        if (directory_settings) {
            const [window_width, window_height] = selector_window.getSize();
            const [content_width, content_height] = selector_window.getContentSize();
            const frame_width = window_width - content_width;
            const frame_height = window_height - content_height;
            // Include the native frame when fitting the dialog to a scaled desktop.
            selector_window.setMinimumSize(
                Math.min(work_area.width, 540 + frame_width),
                Math.min(work_area.height, 560 + frame_height)
            );
            selector_window.setContentSize(
                Math.min(840, Math.max(1, work_area.width - frame_width)),
                Math.min(650, Math.max(1, work_area.height - frame_height))
            );
            selector_window.center();
        }
        course_selector_window = selector_window;
        ipcMain.on('course-selector-ready', onSelectorReady);
        ipcMain.on('course-selector-startup-error', onSelectorError);
        startup_timer = setTimeout(() => exitFailedSelector('startup_timeout'), 45000);
        selector_window.on('close', () => {
            selector_closing = true;
            clearStartupTimer();
            if (!selector_exiting) {
                writeCourseSelectorClosedResult();
            }
        });
        selector_window.on('closed', () => {
            selector_closing = true;
            clearStartupTimer();
            ipcMain.removeListener('course-selector-ready', onSelectorReady);
            ipcMain.removeListener('course-selector-startup-error', onSelectorError);
            if (course_selector_window === selector_window) {
                course_selector_window = null;
            }
        });
        selector_window.once('ready-to-show', showSelector);
        selector_window.webContents.once('did-finish-load', () => {
            showSelector();
            // Directory settings and old diagnostic jobs predate the handshake.
            if (directory_settings || !ready_path) markSelectorReady();
        });
        if (typeof selector_window.webContents.setWindowOpenHandler === 'function') {
            selector_window.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
        }
        // Electron 8 uses new-window; its local selector has Node access and
        // must never open or navigate to content outside this application.
        const denySelectorNavigation = event => event.preventDefault();
        selector_window.webContents.on('new-window', denySelectorNavigation);
        selector_window.webContents.on('will-navigate', denySelectorNavigation);
        selector_window.webContents.on('will-redirect', denySelectorNavigation);
        selector_window.webContents.on('did-fail-load', (
            event, error_code, error_description, validated_url, is_main_frame
        ) => {
            if (is_main_frame !== false) {
                exitFailedSelector('page_load_failed');
            }
        });
        selector_window.webContents.on('crashed', () => exitFailedSelector('renderer_crashed'));
        selector_window.webContents.on('render-process-gone', () => exitFailedSelector('renderer_crashed'));
        const selector_page = directory_settings ? 'download-directory.html' : 'course-selector.html';
        const selector_url = localFileURL(path.join(app.getAppPath(), selector_page))
            + '?job=' + encodeURIComponent(String(extra_arg || ''));
        selector_window.loadURL(selector_url).catch(() => exitFailedSelector('page_load_failed'));
    } catch (error) {
        exitFailedSelector('window_create_failed');
    }
}

function loginWindowClosedWithoutSuccess() {
    return (isDuanshuWechatQrFlow() && !duanshu_qr_finished)
            || (login_name == 'yikaobang' && !yikaobang_login_success)
            || (login_name == 'classin' && !classin_login_success)
            || (login_name == 'xinghuo' && !xinghuo_login_success)
            || (login_name == 'huomiao' && !huomiao_login_success)
            || (login_name == 'lexuepeiyou' && !lexuepeiyou_login_success)
            || (login_name == 'sparke' && !sparke_login_success);
}

app.on('window-all-closed', () => {
    // Gaodoudou login is hosted in an external Edge/Chrome process and
    // intentionally has no Electron BrowserWindow.  Electron may emit
    // window-all-closed while that browser is still starting, so do not
    // quit the login host here.  createGaodoudouEdgeLogin owns the terminal
    // exit path (success, cancellation, startup failure, or browser close).
    if (login_name == 'gaodoudou') {
        return;
    }
    stopCookiePoll();
    if (loginWindowClosedWithoutSuccess()) {
        app.exit(2);
    } else {
        app.quit();
    }
});

if (login_name == 'charge') {
    require('./charge-window').startChargeWindow();
} else if (login_name == 'invite') {
    require('./charge-window').startChargeWindow('invite');
} else if (login_name == 'universal') {
    require('./universal-window').startUniversalWindow();
} else if (login_name == 'course_selector') {
    app.on('ready', createCourseSelectorWindow);
} else if (cookies_file && login_url) {
    // app.commandLine.appendSwitch("--disable-http-cache");
    app.commandLine.appendSwitch('--ignore-certificate-errors', 'true')
    if (login_name == 'sanjieke_fetch') {
        app.on('ready', runSanjiekeFetchHelper);
    } else if (login_name == 'gaodoudou') {
        app.on('ready', createGaodoudouEdgeLogin);
    } else {
        app.on('ready', createWindow);
    }
} else {
    // console.log("error in argv!");
    app.quit();
}

/*
    electron 打包命令

1. 安装 electron和electron-builder
    npm install electron --save-dev --platform=win32
    npm install --save-dev electron-builder
2. 在 package.json 加入 "build" 配置项
    "build": "node_modules/.bin/electron-builder -w"
3. 运行打包命令
    npm run build

*/

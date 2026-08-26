/**
 * CSInterface مبسّط — الحد الأدنى المطلوب للتخاطب مع مضيف Adobe (Premiere Pro).
 * CEP يحقن window.__adobe_cep__ داخل اللوحة، وهذا الملف مجرد غلاف مريح حوله.
 * إذا أردت النسخة الرسمية الكاملة من Adobe (CEP-Resources) فهي متوافقة تماماً مع هذا الاستخدام.
 */
var SystemPath = {
    USER_DATA: 'userData',
    COMMON_FILES: 'commonFiles',
    MY_DOCUMENTS: 'myDocuments',
    APPLICATION: 'application',
    EXTENSION: 'extension',
    HOST_APPLICATION: 'hostApplication'
};

function CSInterface() {}

CSInterface.prototype.hostAvailable = function () {
    return typeof window.__adobe_cep__ !== 'undefined';
};

CSInterface.prototype.evalScript = function (script, callback) {
    if (typeof callback !== 'function') callback = function () {};
    if (!this.hostAvailable()) {
        callback('EvalScript error.');
        return;
    }
    window.__adobe_cep__.evalScript(script, callback);
};

CSInterface.prototype.getHostEnvironment = function () {
    if (!this.hostAvailable()) return null;
    try { return JSON.parse(window.__adobe_cep__.getHostEnvironment()); } catch (e) { return null; }
};

CSInterface.prototype.getSystemPath = function (type) {
    if (!this.hostAvailable()) return '';
    var path = decodeURI(window.__adobe_cep__.getSystemPath(type));
    var OSVersion = this.getOSInformation();
    if (OSVersion.indexOf('Windows') >= 0) path = path.replace('file:///', '');
    else path = path.replace('file://', '');
    return path;
};

CSInterface.prototype.getOSInformation = function () {
    var userAgent = navigator.userAgent;
    if (navigator.platform === 'Win32' || navigator.platform === 'Windows') return 'Windows';
    if (navigator.platform === 'MacIntel' || navigator.platform === 'Macintosh') return 'Mac OS X';
    return userAgent;
};

CSInterface.prototype.getExtensionID = function () {
    return this.hostAvailable() ? window.__adobe_cep__.getExtensionId() : '';
};

CSInterface.prototype.openURLInDefaultBrowser = function (url) {
    if (typeof cep !== 'undefined' && cep.util) cep.util.openURLInDefaultBrowser(url);
};

CSInterface.prototype.getHostCapabilities = function () {
    if (!this.hostAvailable()) return null;
    try { return JSON.parse(window.__adobe_cep__.getHostCapabilities()); } catch (e) { return null; }
};

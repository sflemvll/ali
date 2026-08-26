/* main.js — منطق لوحة بريمير: يربط المحادثة بالسيرفر المحلي وينفّذ ExtendScript داخل بريمير. */
(function () {
  'use strict';

  var cs = new CSInterface();
  var ws = null;
  var reconnectTimer = null;
  var reconnectDelay = 1000;

  var el = {
    chat: document.getElementById('chat'),
    input: document.getElementById('input'),
    send: document.getElementById('send'),
    status: document.getElementById('status'),
    dot: document.getElementById('dot'),
    settings: document.getElementById('settings'),
    settingsBtn: document.getElementById('settingsBtn'),
    serverUrl: document.getElementById('serverUrl'),
    autoRun: document.getElementById('autoRun'),
    showCode: document.getElementById('showCode'),
    reconnectBtn: document.getElementById('reconnectBtn'),
    resetBtn: document.getElementById('resetBtn')
  };

  // ── تخزين الإعدادات ──────────────────────────────────────────────
  function loadPrefs() {
    try {
      var p = JSON.parse(localStorage.getItem('premiereAI') || '{}');
      if (p.serverUrl) el.serverUrl.value = p.serverUrl;
      if (p.autoRun !== undefined) el.autoRun.checked = p.autoRun;
      if (p.showCode !== undefined) el.showCode.checked = p.showCode;
    } catch (e) {}
  }
  function savePrefs() {
    try {
      localStorage.setItem('premiereAI', JSON.stringify({
        serverUrl: el.serverUrl.value,
        autoRun: el.autoRun.checked,
        showCode: el.showCode.checked
      }));
    } catch (e) {}
  }

  // ── واجهة المحادثة ───────────────────────────────────────────────
  function addMsg(cls, text) {
    var d = document.createElement('div');
    d.className = 'msg ' + cls;
    d.textContent = text;
    el.chat.appendChild(d);
    el.chat.scrollTop = el.chat.scrollHeight;
    return d;
  }
  function addCode(parent, code) {
    var pre = document.createElement('pre');
    pre.className = 'code';
    pre.textContent = code;
    parent.appendChild(pre);
    el.chat.scrollTop = el.chat.scrollHeight;
  }
  function setStatus(text, cls) {
    el.status.textContent = text;
    el.dot.className = 'dot ' + cls;
  }

  // ── تنفيذ ExtendScript داخل بريمير ───────────────────────────────
  function runInPremiere(code, done) {
    var call = 'AI_run(' + JSON.stringify(code) + ')';
    cs.evalScript(call, function (raw) {
      if (raw === 'EvalScript error.' || raw === undefined || raw === null || raw === '') {
        done({ ok: false, error: 'فشل تنفيذ السكربت داخل بريمير (EvalScript error). غالباً خطأ صياغة في الكود أو خاصية غير موجودة.' });
        return;
      }
      var parsed;
      try { parsed = JSON.parse(raw); }
      catch (e) { parsed = { ok: true, data: String(raw) }; }
      done(parsed);
    });
  }

  function handleExec(msg) {
    var box = null;
    if (el.showCode.checked) {
      box = addMsg('step', 'تنفيذ داخل بريمير:');
      addCode(box, msg.code);
    }
    setStatus('يشتغل داخل بريمير…', 'busy');

    function go() {
      runInPremiere(msg.code, function (res) {
        setStatus('متصل', 'on');
        send({ type: 'exec_result', id: msg.id, ok: !!res.ok, data: res.data, error: res.error });
        if (!res.ok && el.showCode.checked) addMsg('err', '↳ ' + (res.error || 'خطأ غير معروف'));
      });
    }

    if (el.autoRun.checked) { go(); return; }

    // وضع التأكيد اليدوي
    var holder = box || addMsg('step', 'الذكاء يريد تنفيذ هذا الكود:');
    if (!box) addCode(holder, msg.code);
    var bar = document.createElement('div');
    bar.className = 'approve';
    var yes = document.createElement('button'); yes.className = 'yes'; yes.textContent = 'نفّذ';
    var no  = document.createElement('button'); no.className  = 'no';  no.textContent  = 'ارفض';
    bar.appendChild(yes); bar.appendChild(no);
    holder.appendChild(bar);
    yes.onclick = function () { bar.remove(); go(); };
    no.onclick = function () {
      bar.remove();
      setStatus('متصل', 'on');
      send({ type: 'exec_result', id: msg.id, ok: false, error: 'المستخدم رفض تنفيذ هذا الكود. اسأله شنو يريد بدلاً عنه.' });
    };
  }

  // ── الاتصال بالسيرفر ─────────────────────────────────────────────
  function send(obj) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  }

  function connect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    if (ws) { try { ws.onclose = null; ws.close(); } catch (e) {} }

    setStatus('جاري الاتصال…', 'busy');
    try { ws = new WebSocket(el.serverUrl.value); }
    catch (e) { setStatus('عنوان سيرفر غير صالح', 'off'); return; }

    ws.onopen = function () {
      reconnectDelay = 1000;
      setStatus('متصل', 'on');
      var env = cs.getHostEnvironment();
      cs.evalScript('AI_ping()', function (raw) {
        var info = null;
        try { info = JSON.parse(raw).data; } catch (e) {}
        send({ type: 'hello', host: env ? env.appName + ' ' + env.appVersion : 'unknown', premiere: info });
      });
    };

    ws.onmessage = function (ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      switch (msg.type) {
        case 'exec':      handleExec(msg); break;
        case 'assistant': addMsg('ai', msg.text); el.send.disabled = false; break;
        case 'status':    setStatus(msg.text, 'busy'); break;
        case 'thinking':  addMsg('step', msg.text); break;
        case 'error':     addMsg('err', msg.text); el.send.disabled = false; setStatus('متصل', 'on'); break;
        case 'reset_ok':  addMsg('sys', 'بدأت محادثة جديدة.'); break;
      }
    };

    ws.onclose = function () {
      setStatus('انقطع الاتصال — إعادة المحاولة…', 'off');
      el.send.disabled = false;
      reconnectTimer = setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 15000);
    };

    ws.onerror = function () { setStatus('خطأ اتصال بالسيرفر', 'off'); };
  }

  // ── أحداث الواجهة ────────────────────────────────────────────────
  function submit() {
    var text = el.input.value.trim();
    if (!text) return;
    if (!ws || ws.readyState !== 1) { addMsg('err', 'ما أكو اتصال بالسيرفر. شغّل السيرفر ثم اضغط «إعادة الاتصال».'); return; }
    addMsg('user', text);
    el.input.value = '';
    el.send.disabled = true;
    setStatus('الذكاء يفكر…', 'busy');
    send({ type: 'user_message', text: text });
  }

  el.send.onclick = submit;
  el.input.onkeydown = function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
  };
  el.settingsBtn.onclick = function () { el.settings.classList.toggle('hidden'); };
  el.reconnectBtn.onclick = function () { savePrefs(); connect(); };
  el.resetBtn.onclick = function () { send({ type: 'reset' }); };
  el.autoRun.onchange = savePrefs;
  el.showCode.onchange = savePrefs;
  el.serverUrl.onchange = savePrefs;

  loadPrefs();
  if (!cs.hostAvailable()) addMsg('err', 'هذه الصفحة لا تعمل خارج بريمير (لم يتم العثور على CEP).');
  connect();
})();

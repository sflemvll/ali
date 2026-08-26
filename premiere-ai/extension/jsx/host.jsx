/**
 * host.jsx — مكتبة ExtendScript لتشغيل أوامر Adobe Premiere Pro من الذكاء الاصطناعي.
 *
 * كل دالة ترجع نص JSON: {"ok":true,"data":...} أو {"ok":false,"error":"..."}
 * الذكاء الاصطناعي يستدعي AI.exec("<code>") لتنفيذ أي كود ExtendScript حر،
 * أو يستدعي دوال المساعدة الجاهزة أدناه (أسرع وأقل عرضة للخطأ).
 */

// ExtendScript = ES3، لا يوجد كائن JSON، لذلك نكتب مُسلسِلاً بسيطاً.
var AI = (function () {

    var TICKS_PER_SECOND = 254016000000;
    var MAX_DEPTH = 8;

    function esc(s) {
        s = String(s);
        var out = '', c, code;
        for (var i = 0; i < s.length; i++) {
            c = s.charAt(i);
            code = s.charCodeAt(i);
            if (c === '"') out += '\\"';
            else if (c === '\\') out += '\\\\';
            else if (c === '\n') out += '\\n';
            else if (c === '\r') out += '\\r';
            else if (c === '\t') out += '\\t';
            else if (code < 32 || code > 126) {
                var h = code.toString(16);
                while (h.length < 4) h = '0' + h;
                out += '\\u' + h;
            } else out += c;
        }
        return '"' + out + '"';
    }

    function stringify(v, depth) {
        depth = depth || 0;
        if (v === null || v === undefined) return 'null';
        var t = typeof v;
        if (t === 'number') return isFinite(v) ? String(v) : 'null';
        if (t === 'boolean') return v ? 'true' : 'false';
        if (t === 'string') return esc(v);
        if (depth > MAX_DEPTH) return esc(String(v));
        if (v instanceof Array) {
            var a = [];
            for (var i = 0; i < v.length; i++) a.push(stringify(v[i], depth + 1));
            return '[' + a.join(',') + ']';
        }
        if (t === 'object') {
            // كائنات بريمير الأصلية لا يمكن تعدادها بأمان — نحوّلها لنص
            var isPlain = (v.constructor === Object) || (v.reflect === undefined);
            if (!isPlain) return esc(String(v));
            var parts = [];
            for (var k in v) {
                if (!v.hasOwnProperty(k)) continue;
                var val;
                try { val = stringify(v[k], depth + 1); } catch (e) { val = esc('<error>'); }
                parts.push(esc(k) + ':' + val);
            }
            return '{' + parts.join(',') + '}';
        }
        return esc(String(v));
    }

    function ok(data) { return '{"ok":true,"data":' + stringify(data, 0) + '}'; }
    function err(e) {
        var msg = (e && e.message) ? e.message : String(e);
        var line = (e && e.line) ? (' [سطر ' + e.line + ']') : '';
        return '{"ok":false,"error":' + esc(msg + line) + '}';
    }

    function secToTime(sec) {
        var t = new Time();
        t.seconds = sec;
        return t;
    }
    function secToTicks(sec) { return String(Math.round(sec * TICKS_PER_SECOND)); }
    function ticksToSec(ticks) { return Number(ticks) / TICKS_PER_SECOND; }

    function requireProject() {
        if (!app.project) throw new Error('لا يوجد مشروع مفتوح في بريمير.');
        return app.project;
    }
    function requireSeq() {
        var s = app.project.activeSequence;
        if (!s) throw new Error('لا يوجد تسلسل (Sequence) نشط. افتح تسلسلاً أولاً.');
        return s;
    }
    function qeSeq() {
        app.enableQE();
        var s = qe.project.getActiveSequence();
        if (!s) throw new Error('QE: لا يوجد تسلسل نشط.');
        return s;
    }

    // ── قراءة الحالة ────────────────────────────────────────────────
    function clipInfo(clip, idx) {
        return {
            index: idx,
            name: clip.name,
            start: clip.start.seconds,
            end: clip.end.seconds,
            duration: clip.duration.seconds,
            inPoint: clip.inPoint.seconds,
            outPoint: clip.outPoint.seconds,
            selected: clip.isSelected()
        };
    }

    function trackInfo(track, idx, withClips) {
        var info = {
            index: idx,
            name: track.name,
            clipCount: track.clips.numItems,
            muted: track.isMuted()
        };
        if (withClips) {
            var clips = [];
            for (var i = 0; i < track.clips.numItems; i++) {
                clips.push(clipInfo(track.clips[i], i));
            }
            info.clips = clips;
        }
        return info;
    }

    function fps(seq) {
        try {
            var d = seq.getSettings().videoFrameRate.seconds;
            return d ? Math.round((1 / d) * 1000) / 1000 : null;
        } catch (e) { return null; }
    }

    function seqInfo(seq, withClips) {
        var v = [], a = [], i;
        for (i = 0; i < seq.videoTracks.numTracks; i++) v.push(trackInfo(seq.videoTracks[i], i, withClips));
        for (i = 0; i < seq.audioTracks.numTracks; i++) a.push(trackInfo(seq.audioTracks[i], i, withClips));
        return {
            name: seq.name,
            id: seq.sequenceID,
            duration: seq.end ? ticksToSec(seq.end) : null,
            playhead: seq.getPlayerPosition().seconds,
            fps: fps(seq),
            videoTracks: v,
            audioTracks: a
        };
    }

    function walkItems(item, depth, out, path) {
        if (depth > 4) return;
        for (var i = 0; i < item.children.numItems; i++) {
            var ch = item.children[i];
            var entry = { name: ch.name, type: ch.type, path: path };
            try { entry.mediaPath = ch.getMediaPath(); } catch (e) {}
            out.push(entry);
            if (ch.type === ProjectItemType.BIN) {
                walkItems(ch, depth + 1, out, path + '/' + ch.name);
            }
        }
    }

    function state(deep) {
        var p = requireProject();
        var seqs = [];
        for (var i = 0; i < p.sequences.numSequences; i++) seqs.push(p.sequences[i].name);
        var s = null;
        try { s = p.activeSequence ? seqInfo(p.activeSequence, deep !== false) : null; } catch (e) {}
        var items = [];
        try { walkItems(p.rootItem, 0, items, ''); } catch (e) {}
        return {
            projectName: p.name,
            projectPath: p.path,
            appVersion: app.version,
            sequences: seqs,
            activeSequence: s,
            projectItems: items
        };
    }

    // ── البحث عن عنصر في المشروع ────────────────────────────────────
    function findItem(nameOrIndex, root) {
        var p = requireProject();
        root = root || p.rootItem;
        if (typeof nameOrIndex === 'number') return root.children[nameOrIndex];
        var lower = String(nameOrIndex).toLowerCase();
        var found = null;
        function scan(node, depth) {
            if (found || depth > 4) return;
            for (var i = 0; i < node.children.numItems; i++) {
                var ch = node.children[i];
                if (String(ch.name).toLowerCase() === lower) { found = ch; return; }
                if (ch.type === ProjectItemType.BIN) scan(ch, depth + 1);
            }
        }
        scan(root, 0);
        if (!found) {
            // مطابقة جزئية
            function scan2(node, depth) {
                if (found || depth > 4) return;
                for (var i = 0; i < node.children.numItems; i++) {
                    var ch = node.children[i];
                    if (String(ch.name).toLowerCase().indexOf(lower) !== -1) { found = ch; return; }
                    if (ch.type === ProjectItemType.BIN) scan2(ch, depth + 1);
                }
            }
            scan2(root, 0);
        }
        if (!found) throw new Error('لم أجد عنصراً باسم: ' + nameOrIndex);
        return found;
    }

    // ── عمليات ──────────────────────────────────────────────────────
    function importFiles(paths, binName) {
        var p = requireProject();
        var target = p.rootItem;
        if (binName) {
            try { target = findItem(binName); } catch (e) { target = p.rootItem.createBin(binName); }
        }
        var okDone = p.importFiles(paths, true, target, false);
        return { imported: okDone, count: paths.length, bin: target.name };
    }

    function appendClip(nameOrIndex, videoTrack, audioTrack) {
        var seq = requireSeq();
        var item = findItem(nameOrIndex);
        videoTrack = (videoTrack === undefined || videoTrack === null) ? 0 : videoTrack;
        audioTrack = (audioTrack === undefined || audioTrack === null) ? 0 : audioTrack;
        var vt = seq.videoTracks[videoTrack];
        var end = 0;
        if (vt.clips.numItems > 0) end = vt.clips[vt.clips.numItems - 1].end.seconds;
        vt.overwriteClip(item, secToTime(end));
        return { added: item.name, atSecond: end, videoTrack: videoTrack };
    }

    function insertAt(nameOrIndex, seconds, videoTrack, overwrite) {
        var seq = requireSeq();
        var item = findItem(nameOrIndex);
        var vt = seq.videoTracks[videoTrack || 0];
        if (overwrite === false) vt.insertClip(item, secToTime(seconds));
        else vt.overwriteClip(item, secToTime(seconds));
        return { added: item.name, atSecond: seconds };
    }

    function razor(seconds, trackIndex, isAudio) {
        var q = qeSeq();
        var tc = timecodeAt(seconds);
        if (trackIndex === undefined || trackIndex === null) {
            q.razor(tc);       // يقص كل المسارات
            return { cutAt: seconds, tracks: 'all' };
        }
        var t = isAudio ? q.getAudioTrackAt(trackIndex) : q.getVideoTrackAt(trackIndex);
        t.razor(tc);
        return { cutAt: seconds, track: trackIndex, audio: !!isAudio };
    }

    function timecodeAt(seconds) {
        var seq = requireSeq();
        var t = secToTime(seconds);
        var settings = seq.getSettings();
        return t.getFormatted(settings.videoFrameRate, seq.videoDisplayFormat);
    }

    function removeClip(trackIndex, clipIndex, ripple, isAudio) {
        var seq = requireSeq();
        var track = isAudio ? seq.audioTracks[trackIndex] : seq.videoTracks[trackIndex];
        var clip = track.clips[clipIndex];
        if (!clip) throw new Error('لا يوجد مقطع بهذا الرقم على المسار.');
        var nm = clip.name;
        clip.remove(!!ripple, true);
        return { removed: nm, ripple: !!ripple };
    }

    function moveClip(trackIndex, clipIndex, newStartSeconds, isAudio) {
        var seq = requireSeq();
        var track = isAudio ? seq.audioTracks[trackIndex] : seq.videoTracks[trackIndex];
        var clip = track.clips[clipIndex];
        clip.move(secToTime(newStartSeconds - clip.start.seconds));
        return { moved: clip.name, newStart: clip.start.seconds };
    }

    function setClipSpeed(trackIndex, clipIndex, speedPercent, isAudio) {
        var q = qeSeq();
        var t = isAudio ? q.getAudioTrackAt(trackIndex) : q.getVideoTrackAt(trackIndex);
        var item = t.getItemAt(clipIndex);
        if (!item) throw new Error('لا يوجد مقطع بهذا الرقم.');
        item.setSpeed(speedPercent / 100, null, false, true, false);
        return { clip: item.name, speed: speedPercent + '%' };
    }

    function addTransition(transitionName, trackIndex, clipIndex, atStart, durationSeconds, isAudio) {
        var q = qeSeq();
        var t = isAudio ? q.getAudioTrackAt(trackIndex) : q.getVideoTrackAt(trackIndex);
        var item = t.getItemAt(clipIndex);
        var fx = isAudio ? qe.project.getAudioTransitionByName(transitionName)
                         : qe.project.getVideoTransitionByName(transitionName);
        if (!fx) throw new Error('لم أجد انتقالاً باسم: ' + transitionName);
        var dur = timecodeAt(durationSeconds || 1);
        item.addTransition(fx, atStart !== false, dur);
        return { transition: transitionName, clip: item.name, atStart: atStart !== false };
    }

    function addEffect(effectName, trackIndex, clipIndex, isAudio) {
        var q = qeSeq();
        var t = isAudio ? q.getAudioTrackAt(trackIndex) : q.getVideoTrackAt(trackIndex);
        var item = t.getItemAt(clipIndex);
        var fx = isAudio ? qe.project.getAudioEffectByName(effectName)
                         : qe.project.getVideoEffectByName(effectName);
        if (!fx) throw new Error('لم أجد تأثيراً باسم: ' + effectName);
        item.addVideoEffect ? item.addVideoEffect(fx) : item.addAudioEffect(fx);
        return { effect: effectName, clip: item.name };
    }

    function listEffects(filter) {
        app.enableQE();
        var out = [], i, n;
        var vf = qe.project.getVideoEffectList();
        for (i = 0; i < vf.length; i++) {
            n = String(vf[i]);
            if (!filter || n.toLowerCase().indexOf(String(filter).toLowerCase()) !== -1) out.push(n);
        }
        return out;
    }

    function setClipProperty(trackIndex, clipIndex, componentName, propertyName, value, isAudio) {
        var seq = requireSeq();
        var track = isAudio ? seq.audioTracks[trackIndex] : seq.videoTracks[trackIndex];
        var clip = track.clips[clipIndex];
        for (var c = 0; c < clip.components.numItems; c++) {
            var comp = clip.components[c];
            if (String(comp.displayName).toLowerCase() !== String(componentName).toLowerCase()) continue;
            for (var pI = 0; pI < comp.properties.numItems; pI++) {
                var prop = comp.properties[pI];
                if (String(prop.displayName).toLowerCase() !== String(propertyName).toLowerCase()) continue;
                prop.setValue(value, true);
                return { clip: clip.name, component: componentName, property: propertyName, value: value };
            }
        }
        throw new Error('لم أجد الخاصية ' + componentName + ' > ' + propertyName + ' على هذا المقطع.');
    }

    function listClipProperties(trackIndex, clipIndex, isAudio) {
        var seq = requireSeq();
        var track = isAudio ? seq.audioTracks[trackIndex] : seq.videoTracks[trackIndex];
        var clip = track.clips[clipIndex];
        var out = [];
        for (var c = 0; c < clip.components.numItems; c++) {
            var comp = clip.components[c], props = [];
            for (var pI = 0; pI < comp.properties.numItems; pI++) props.push(String(comp.properties[pI].displayName));
            out.push({ component: String(comp.displayName), properties: props });
        }
        return out;
    }

    function addMarker(seconds, name, comment) {
        var seq = requireSeq();
        var m = seq.markers.createMarker(seconds);
        if (name) m.name = name;
        if (comment) m.comments = comment;
        return { marker: name || '', at: seconds };
    }

    function listMarkers() {
        var seq = requireSeq();
        var out = [], m = seq.markers.getFirstMarker();
        while (m) {
            out.push({ name: m.name, comment: m.comments, start: m.start.seconds, end: m.end.seconds });
            m = seq.markers.getNextMarker(m);
        }
        return out;
    }

    function setPlayhead(seconds) {
        var seq = requireSeq();
        seq.setPlayerPosition(secToTicks(seconds));
        return { playhead: seconds };
    }

    function newSequence(name) {
        var p = requireProject();
        var s = p.createNewSequence(name, String(new Date().getTime()));
        return { created: name };
    }

    function newSequenceFromClips(name, itemNames) {
        var p = requireProject();
        var items = [];
        for (var i = 0; i < itemNames.length; i++) items.push(findItem(itemNames[i]));
        p.createNewSequenceFromClips(name, items, p.rootItem);
        return { created: name, clips: itemNames.length };
    }

    function exportSequence(outputPath, presetPath, useQueue) {
        var seq = requireSeq();
        if (useQueue) {
            app.encoder.launchEncoder();
            var jobID = app.encoder.encodeSequence(seq, outputPath, presetPath, 0, 0);
            app.encoder.startBatch();
            return { queued: true, jobID: jobID, output: outputPath };
        }
        seq.exportAsMediaDirect(outputPath, presetPath, app.encoder.ENCODE_ENTIRE);
        return { exporting: true, output: outputPath };
    }

    function saveProject() {
        requireProject().save();
        return { saved: true };
    }

    function undo() { app.enableQE(); qe.project.undo(); return { undone: true }; }

    // ── منفّذ الكود الحر ─────────────────────────────────────────────
    function exec(code) {
        var __result = eval(code);
        return __result;
    }

    return {
        // أدوات داخلية
        _stringify: stringify,
        ok: ok, err: err,
        secToTime: secToTime, secToTicks: secToTicks, ticksToSec: ticksToSec,
        timecodeAt: timecodeAt,
        findItem: findItem, requireSeq: requireSeq, qeSeq: qeSeq,
        // واجهة عالية المستوى
        state: state,
        importFiles: importFiles,
        append: appendClip,
        insertAt: insertAt,
        razor: razor,
        removeClip: removeClip,
        moveClip: moveClip,
        setClipSpeed: setClipSpeed,
        addTransition: addTransition,
        addEffect: addEffect,
        listEffects: listEffects,
        setClipProperty: setClipProperty,
        listClipProperties: listClipProperties,
        addMarker: addMarker,
        listMarkers: listMarkers,
        setPlayhead: setPlayhead,
        newSequence: newSequence,
        newSequenceFromClips: newSequenceFromClips,
        exportSequence: exportSequence,
        saveProject: saveProject,
        undo: undo,
        exec: exec
    };
})();

/**
 * نقطة الدخول الوحيدة من اللوحة: تُنفِّذ الكود وتُرجِع JSON دائماً.
 * اللوحة تستدعيها هكذا: evalScript('AI_run(' + JSON.stringify(code) + ')')
 */
function AI_run(code) {
    try {
        var r = AI.exec(code);
        return AI.ok(r === undefined ? 'تم التنفيذ' : r);
    } catch (e) {
        return AI.err(e);
    }
}

function AI_ping() {
    try {
        return AI.ok({ app: app.appName || 'Premiere Pro', version: app.version, project: app.project ? app.project.name : null });
    } catch (e) {
        return AI.err(e);
    }
}

// 화면만 담당한다. 진단과 생성 계산은 모두 파이썬 서버(app.py)가 한다.
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  var toastTimer;
  function toast(msg) {
    var t = $('toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, 1800);
  }

  // ---------- 진단 ----------
  var checkSeq = 0, checkTimer;

  function renderCheck(d) {
    $('result').dataset.level = d.level;
    $('pill').textContent = d.label;

    var sample = $('sample');
    sample.textContent = '';
    if (d.sample) {
      sample.appendChild(document.createTextNode('예시 '));
      sample.appendChild(el('code', null, d.sample));
      sample.appendChild(document.createTextNode(' 의 결과예요'));
    }

    var clock = $('clock');
    clock.textContent = '';
    if (d.clock.single) {
      clock.className = 'clock single';
      var one = el('div', 'cell');
      one.appendChild(el('b', null, d.clock.single));
      clock.appendChild(one);
    } else {
      clock.className = 'clock';
      d.clock.cells.forEach(function (c) {
        var cell = el('div', 'cell' + (c.zero ? ' zero' : ''));
        cell.appendChild(el('b', null, c.value));
        cell.appendChild(el('span', null, c.unit));
        clock.appendChild(cell);
      });
    }
    $('bar').style.width = d.meter + '%';

    var reasons = $('reasons');
    reasons.textContent = '';
    d.reasons.forEach(function (r) {
      var li = el('li', null, r.text);
      if (r.token) {
        li.appendChild(document.createTextNode(' '));
        li.appendChild(el('code', null, r.token));
      }
      reasons.appendChild(li);
    });

    var scen = $('scen');
    scen.textContent = '';
    d.scenarios.forEach(function (s) {
      var li = el('li');
      var what = el('div', 'what');
      what.appendChild(el('b', null, s.name + ' · ' + s.speed));
      what.appendChild(el('small', null, s.note));
      li.appendChild(what);
      li.appendChild(el('div', 'time', s.time));
      scen.appendChild(li);
    });
  }

  function check() {
    var seq = ++checkSeq;
    post('/api/check', { password: $('pw').value }).then(function (d) {
      if (seq === checkSeq) renderCheck(d);      // 늦게 온 예전 응답은 버린다
    }).catch(function () {
      if (seq === checkSeq) $('pill').textContent = '서버에 연결할 수 없어요';
    });
  }

  $('pw').addEventListener('input', function () {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(check, 120);
  });

  $('toggle').addEventListener('click', function () {
    var show = $('pw').type === 'password';
    $('pw').type = show ? 'text' : 'password';
    this.textContent = show ? '숨기기' : '보기';
    this.setAttribute('aria-pressed', String(show));
  });

  // ---------- 생성 ----------
  var current = '', genSeq = 0;
  var KINDS = ['lower', 'upper', 'digit', 'symbol'];

  function paintSlider() {
    var len = $('len');
    len.style.setProperty('--fill', ((len.value - len.min) / (len.max - len.min) * 100) + '%');
    $('lenout').textContent = len.value + '자';
  }

  function generate() {
    var kinds = KINDS.filter(function (k) { return $('c-' + k).checked; });
    if (!kinds.length) { $('c-lower').checked = true; kinds = ['lower']; }
    paintSlider();
    var seq = ++genSeq;
    post('/api/generate', { length: +$('len').value, kinds: kinds, no_ambiguous: $('c-amb').checked }).then(function (d) {
      if (seq !== genSeq) return;
      current = d.password;
      var out = $('out');
      out.textContent = '';
      Array.prototype.forEach.call(d.password, function (ch) {
        out.appendChild(el('span', /[0-9]/.test(ch) ? 'd' : (/[A-Za-z]/.test(ch) ? null : 's'), ch));
      });
      var stat = $('genstat');
      stat.textContent = '';
      stat.appendChild(document.createTextNode('같은 공격으로 '));
      stat.appendChild(el('strong', null, d.time));
      stat.appendChild(document.createTextNode(' · 무작위성 ' + d.bits + '비트'));
    }).catch(function () {
      $('genstat').textContent = '서버에 연결할 수 없어요';
    });
  }

  $('copy').addEventListener('click', function () {
    if (!current) return;
    var fallback = function () {
      var range = document.createRange();
      range.selectNodeContents($('out'));
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      toast('선택했어요. Ctrl/⌘+C로 복사하세요');
    };
    try {
      navigator.clipboard.writeText(current).then(function () { toast('복사했어요'); }, fallback);
    } catch (e) { fallback(); }
  });
  $('regen').addEventListener('click', generate);
  ['len', 'c-lower', 'c-upper', 'c-digit', 'c-symbol', 'c-amb'].forEach(function (id) {
    $(id).addEventListener('input', generate);
  });

  check();
  generate();
})();

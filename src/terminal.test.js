// Drives the built docs/index.html through window.TERMLINK and paints the
// results over the page. There is no test runner here, so run it by hand:
//
//   python3 -c "h=open('docs/index.html').read(); t=open('src/terminal.test.js').read(); \
//     tag='<'+'/body>'; s='<scr'+'ipt>'+t+'</scr'+'ipt>'; \
//     open('/tmp/t.html','w').write(h.replace(tag, s+tag))"
//   firefox --headless --window-size=1000,700 --screenshot /tmp/t.png file:///tmp/t.html
//
// The tag names are split on purpose: a literal closing script tag anywhere in
// this file — comments included — ends the block the browser injected it into.
//
// The screenshot says ALL n CHECKS PASS, or names what broke.

(function () {
  var out = [], fails = 0;
  function t(name, cond, extra) {
    if (!cond) fails++;
    out.push((cond ? "PASS  " : "FAIL  ") + name + (extra ? "   [" + extra + "]" : ""));
  }
  var T = window.TERMLINK;
  var CELL = 12;

  // ── opening state ──
  t("starts playable with 4 attempts", T.state() === "play" && T.attempts() === 4,
    T.state() + "/" + T.attempts());
  t("caret opens on a selectable token", T.tokenAt(T.caret()) >= 0);
  t("13 words and 8 tricks are live",
    T.tokens().filter(function (x) { return x.alive && x.kind === "word"; }).length === 13 &&
    T.tokens().filter(function (x) { return x.alive && x.kind === "trick"; }).length === 8);

  // ── movement ──
  T.setCaret(0);
  T.press("ArrowRight"); t("right steps one character", T.caret() === 1, T.caret());
  T.press("ArrowLeft");  t("left steps back", T.caret() === 0, T.caret());
  T.press("ArrowUp");    t("up on the top row is a no-op", T.caret() === 0, T.caret());
  T.press("ArrowDown");  t("down moves one row", T.caret() === CELL, T.caret());
  T.setCaret(179); T.press("ArrowDown");
  t("down on the last row of column 1 is a no-op", T.caret() === 179, T.caret());
  T.setCaret(180); T.press("ArrowUp");
  t("up on the top row of column 2 is a no-op", T.caret() === 180, T.caret());
  T.setCaret(185); T.press("ArrowDown");
  t("down stays inside column 2", T.caret() === 197, T.caret());

  // ── tab hopping ──
  T.setCaret(0);
  T.press("Tab"); var first = T.caret();
  t("tab lands on a token", T.tokenAt(first) >= 0, first);
  T.press("Tab"); var second = T.caret();
  t("tab advances to the next token", second > first, first + " -> " + second);
  T.press("Tab", true);
  t("shift+tab goes back", T.caret() === first, T.caret());

  // ── a wrong guess ──
  T.reset();
  var answer = T.answer();
  var duds = T.tokens().filter(function (x) { return x.kind === "word" && x.text !== answer; });
  T.setCaret(duds[0].start); T.press("Enter");
  t("a wrong guess costs an attempt", T.attempts() === 3, T.attempts());
  var log = T.log();
  t("the denial is logged", log.indexOf(">Entry denied.") >= 0);
  t("likeness is reported", /^>\d+\/\d+ correct\.$/.test(log[log.length - 1]), log[log.length - 1]);

  // ── likeness maths ──
  function likeness(a, b) {
    var n = Math.min(a.length, b.length), h = 0;
    for (var i = 0; i < n; i++) if (a[i] === b[i]) h++;
    return h;
  }
  var reported = Number(log[log.length - 1].match(/(\d+)\//)[1]);
  t("likeness matches character-by-character overlap",
    reported === likeness(duds[0].text, answer),
    duds[0].text + " vs " + answer + " = " + reported);

  // ── the win ──
  T.reset();
  var right = T.tokens().filter(function (x) { return x.kind === "word" && x.text === T.answer(); })[0];
  T.setCaret(right.start); T.press("Enter");
  t("the password unlocks the terminal", T.state() === "win", T.state());
  t("the skill matrix replaces the dump",
    document.getElementById("dump").className === "readout" &&
    document.querySelectorAll("#dump div").length > 15,
    document.querySelectorAll("#dump div").length + " lines");
  t("the reset button takes focus on a win",
    document.activeElement === document.getElementById("reset"),
    document.activeElement.id || document.activeElement.tagName);
  t("every sector is listed",
    /LANGUAGES/.test(document.getElementById("dump").textContent) &&
    /SYSTEMS/.test(document.getElementById("dump").textContent));

  // ── lockout ──
  T.reset();
  var ans2 = T.answer();
  var duds2 = T.tokens().filter(function (x) { return x.kind === "word" && x.text !== ans2; });
  for (var i = 0; i < 4; i++) { T.setCaret(duds2[i].start); T.press("Enter"); }
  t("four misses lock the terminal", T.state() === "lock" && T.attempts() === 0,
    T.state() + "/" + T.attempts());
  t("the lock is announced", T.log().indexOf(">TERMINAL LOCKED") >= 0);
  t("the reset button takes focus on lockout",
    document.activeElement === document.getElementById("reset"),
    document.activeElement.id || document.activeElement.tagName);
  T.setCaret(duds2[5].start); T.press("Enter");
  t("keys are inert after lockout", T.attempts() === 0 && T.state() === "lock",
    T.state() + "/" + T.attempts());

  // ── bracket tricks, both branches ──
  var realRandom = Math.random;
  Math.random = function () { return 0.1; };          // < 0.25 -> replenish
  T.reset();
  var burn = T.tokens().filter(function (x) { return x.kind === "word" && x.text !== T.answer(); })[0];
  T.setCaret(burn.start); T.press("Enter");
  var mid = T.attempts();
  var trick = T.tokens().filter(function (x) { return x.kind === "trick"; })[0];
  T.setCaret(trick.start); T.press("Enter");
  t("a bracket trick replenishes attempts", mid === 3 && T.attempts() === 4,
    mid + " -> " + T.attempts());
  t("a used trick stops being selectable", T.tokenAt(trick.start) < 0);

  Math.random = function () { return 0.9; };          // >= 0.25 -> remove a dud
  T.reset();
  var live = T.tokens().filter(function (x) { return x.kind === "word" && x.text !== T.answer(); });
  var doomed = live[Math.floor(0.9 * live.length)];
  var trick2 = T.tokens().filter(function (x) { return x.kind === "trick"; })[0];
  T.setCaret(trick2.start); T.press("Enter");
  var dots = T.chars().slice(doomed.start, doomed.start + doomed.text.length);
  t("a bracket trick blanks out a dud", /^\.+$/.test(dots), doomed.text + " -> " + dots);
  t("the removed dud is no longer selectable", T.tokenAt(doomed.start) < 0);
  t("the password is never the dud removed", doomed.text !== T.answer());
  Math.random = realRandom;

  // ── reset ──
  T.reset();
  t("reset restores the dump and the attempts",
    T.state() === "play" && T.attempts() === 4 && T.chars().indexOf("..") < 0,
    T.state() + "/" + T.attempts());

  var pre = document.createElement("pre");
  pre.textContent = (fails ? fails + " FAILURE(S)" : "ALL " + out.length + " CHECKS PASS") +
                    "\n\n" + out.join("\n");
  pre.setAttribute("style",
    "position:fixed;inset:0;z-index:99;margin:0;padding:16px;background:#000;" +
    "color:" + (fails ? "#ff6b6b" : "#2fff6b") + ";font:13px/1.45 monospace;overflow:auto");
  document.body.appendChild(pre);
})();

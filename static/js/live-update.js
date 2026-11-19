/*
 * 画面の自動更新（顧問の画面）
 *
 * 数秒ごとにサーバー（matching.views.live_updates）に問い合わせて、
 *  1. サイドバーの件数（未読メッセージ・届いた申し込み）を書き換える
 *  2. その画面が見ているデータ（body の data-live-watch）が変わっていたら、
 *     画面の中身（.admin-content）だけを読み込み直す
 *
 * 入力の途中で中身が変わると困るので、フォームに入力・選択している間は
 * 読み込み直さず、「新しい情報があります」の案内とボタンを出す。
 */
(function () {
    "use strict";

    var INTERVAL = 5000;          // 問い合わせの間隔（ミリ秒）
    var body = document.body;
    var url = body.dataset.liveUrl;
    if (!url || !window.fetch) { return; }

    var watch = (body.dataset.liveWatch || "").split(/\s+/).filter(Boolean);
    var notice = document.getElementById("live-notice");
    var baseline = null;          // 画面を表示したときの目印
    var userId = null;            // ログイン中のアカウント
    var dirty = false;            // フォームに入力・選択したか
    var stopped = false;
    var timer = null;

    // ---------- 入力中かどうか ----------

    function content() {
        return document.querySelector(".admin-content");
    }

    function watchForms() {
        var area = content();
        if (!area) { return; }
        area.querySelectorAll('form[method="post"]').forEach(function (form) {
            form.addEventListener("input", function () { dirty = true; });
            form.addEventListener("change", function () { dirty = true; });
            form.addEventListener("submit", function () { stopped = true; });
        });
    }

    function isBusy() {
        if (dirty) { return true; }
        var el = document.activeElement;
        var area = content();
        return !!(el && area && area.contains(el) &&
                  /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) && el.type !== "submit");
    }

    // ---------- 案内 ----------

    function showNotice(text, withButton) {
        if (!notice) { return; }
        notice.textContent = text;
        if (withButton) {
            var button = document.createElement("button");
            button.type = "button";
            button.textContent = "更新する";
            button.addEventListener("click", function () { window.location.reload(); });
            notice.appendChild(button);
        }
        notice.hidden = false;
        notice.classList.toggle("is-sticky", !!withButton);
        if (!withButton) {
            clearTimeout(showNotice.timer);
            showNotice.timer = setTimeout(function () { notice.hidden = true; }, 3000);
        }
    }

    // ---------- サイドバーの件数 ----------

    function updateBadges(badges) {
        document.querySelectorAll("[data-badge-key]").forEach(function (link) {
            var count = badges[link.dataset.badgeKey] || 0;
            var badge = link.querySelector(".sidebar-badge");
            if (count > 0) {
                if (!badge) {
                    badge = document.createElement("span");
                    badge.className = "sidebar-badge";
                    link.appendChild(badge);
                }
                badge.textContent = count;
                badge.setAttribute("aria-label", count + "件");
            } else if (badge) {
                badge.remove();
            }
        });
    }

    // ---------- 画面の中身を読み込み直す ----------

    function changed(versions) {
        return watch.some(function (key) { return baseline[key] !== versions[key]; });
    }

    function refreshContent(versions) {
        return fetch(window.location.href, { credentials: "same-origin", cache: "no-store" })
            .then(function (response) {
                // ログイン画面などに移動させられたときは、何もしない
                if (!response.ok || response.redirected) { throw new Error("skip"); }
                return response.text();
            })
            .then(function (html) {
                var doc = new DOMParser().parseFromString(html, "text/html");
                var fresh = doc.querySelector(".admin-content");
                var area = content();
                if (!fresh || !area || isBusy()) { return; }
                area.innerHTML = fresh.innerHTML;
                baseline = versions;
                watchForms();
                showNotice("最新の情報に更新しました。", false);
            })
            .catch(function () { /* 次の問い合わせで、もう一度試す */ });
    }

    // ---------- 問い合わせ ----------

    function poll() {
        if (stopped) { return; }
        if (document.hidden) { schedule(); return; }   // 見ていないタブでは問い合わせない

        fetch(url, { credentials: "same-origin", cache: "no-store", headers: { "Accept": "application/json" } })
            .then(function (response) {
                if (response.status === 403) { throw new Error("forbidden"); }
                if (!response.ok) { throw new Error("retry"); }
                return response.json();
            })
            .then(function (data) {
                if (userId !== null && data.user !== userId) { throw new Error("forbidden"); }
                userId = data.user;
                updateBadges(data.badges);

                if (baseline === null) { baseline = data.versions; return; }
                if (!watch.length || !changed(data.versions)) { return; }
                if (isBusy()) {
                    showNotice("新しい情報があります。入力が終わったら、画面を更新してください。", true);
                    return;
                }
                return refreshContent(data.versions);
            })
            .catch(function (error) {
                if (error.message === "forbidden") {
                    // 別のタブでログアウト・別のアカウントにログインしたとき
                    stopped = true;
                    showNotice("ログイン状態が変わったため、自動更新を止めました。", true);
                }
            })
            .then(schedule);
    }

    function schedule() {
        if (stopped) { return; }
        clearTimeout(timer);
        timer = setTimeout(poll, INTERVAL);
    }

    // タブに戻ってきたときは、すぐに確認する
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden && !stopped) { clearTimeout(timer); poll(); }
    });

    watchForms();
    poll();
})();

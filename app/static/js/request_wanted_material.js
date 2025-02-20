// request_material.js

document.addEventListener('DOMContentLoaded', function () {
    // モーダルを開くボタン
    document.getElementById('openModal').addEventListener('click', function () {
        document.getElementById('modalOverlay').style.display = 'flex';
    });

    // モーダルを閉じるボタン（ヘッダーの×）
    document.getElementById('closeModal').addEventListener('click', function () {
        document.getElementById('modalOverlay').style.display = 'none';
    });

    // モーダルを閉じるボタン（フッターのキャンセル）
    document.getElementById('cancelModal').addEventListener('click', function () {
        document.getElementById('modalOverlay').style.display = 'none';
    });

    // モーダル内の送信ボタン
    document.getElementById('confirmSubmit').addEventListener('click', function () {
        document.getElementById('wantedRequestForm').submit();
    });

    // 閉じるボタンの動作
    document.querySelectorAll('[data-close]').forEach(function(element) {
        element.addEventListener('click', function() {
            this.parentElement.style.display = 'none';
        });
    });
});

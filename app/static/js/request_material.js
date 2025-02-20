document.addEventListener("DOMContentLoaded", function() {
    var requestForm = document.getElementById('requestForm');
    var openModalBtn = document.getElementById('openModal');
    var modalOverlay = document.getElementById('modalOverlay');
    var closeModalBtn = document.getElementById('closeModal');
    var cancelModalBtn = document.getElementById('cancelModal');
    var confirmSubmitBtn = document.getElementById('confirmSubmit');
    var closeBtns = document.querySelectorAll('[data-close]');

    // モーダルを開く
    openModalBtn.addEventListener('click', function () {
        modalOverlay.style.display = 'flex';
    });

    // モーダルを閉じる関数
    function closeModal() {
        modalOverlay.style.display = 'none';
    }

    // モーダルを閉じるイベント
    closeModalBtn.addEventListener('click', closeModal);
    cancelModalBtn.addEventListener('click', closeModal);
    closeBtns.forEach(function(btn) {
        btn.addEventListener('click', closeModal);
    });

    // フォーム送信の確認
    confirmSubmitBtn.addEventListener('click', function () {
        requestForm.submit();
    });

    // フォームの送信をカスタム処理（バリデーションなど）
    requestForm.addEventListener('submit', function(event) {
        event.preventDefault(); // デフォルトの送信を防止
        // 必要なバリデーションや処理をここに追加
        modalOverlay.style.display = 'flex'; // モーダルを表示
    });

    // フラッシュメッセージの閉じるボタン
    const flashCloseBtns = document.querySelectorAll('.close-btn');
    flashCloseBtns.forEach(function(btn) {
        btn.addEventListener('click', function() {
            btn.parentElement.style.display = 'none';
        });
    });

    // 不要な要素を削除する関数
    function removeChatGPTElements() {
        const elementsToRemove = document.querySelectorAll('use-chat-gpt-ai, use-chat-gpt-ai-content-menu, max-ai-minimum-app');
        elementsToRemove.forEach(el => el.remove());
    }

    removeChatGPTElements();

    const observer = new MutationObserver(removeChatGPTElements);
    observer.observe(document.body, { childList: true, subtree: true });
});

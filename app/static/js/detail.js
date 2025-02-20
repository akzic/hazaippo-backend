// app/static/js/detail.js
document.addEventListener("DOMContentLoaded", function() {
    // ユーザーの詳細表示ボタンにクリックイベントを追加
    document.getElementById('showProfileButton').addEventListener('click', function() {
        var profileDetails = document.getElementById('profileDetails');
        // プロフィール詳細の表示・非表示を切り替え
        profileDetails.style.display = profileDetails.style.display === 'none' ? 'block' : 'none';
    });

    // ChatGPT関連の要素を削除する関数
    function removeChatGPTElements() {
        const elementsToRemove = document.querySelectorAll('use-chat-gpt-ai, use-chat-gpt-ai-content-menu, max-ai-minimum-app');
        elementsToRemove.forEach(el => el.remove());
    }

    // 初回実行
    removeChatGPTElements();

    // DOMの変更を監視し、ChatGPT関連の要素を削除
    const observer = new MutationObserver(removeChatGPTElements);
    observer.observe(document.body, { childList: true, subtree: true });
});

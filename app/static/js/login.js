document.addEventListener('DOMContentLoaded', function() {
    // フラッシュメッセージを3秒後にフェードアウトする
    setTimeout(function() {
        var flashMessages = document.getElementById('flash-messages');
        if (flashMessages) {
            flashMessages.style.transition = 'opacity 0.5s ease-out';
            flashMessages.style.opacity = 0;
            setTimeout(function() {
                flashMessages.remove();
            }, 500);
        }
    }, 3000);

    function removeChatGPTElements() {
        const elementsToRemove = document.querySelectorAll('use-chat-gpt-ai, use-chat-gpt-ai-content-menu, max-ai-minimum-app');
        elementsToRemove.forEach(el => el.remove());
    }

    removeChatGPTElements();

    const observer = new MutationObserver(removeChatGPTElements);
    observer.observe(document.body, { childList: true, subtree: true });
});

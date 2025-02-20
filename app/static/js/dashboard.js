document.addEventListener("DOMContentLoaded", function() {
    const flashMessageContainer = document.getElementById('flash-message-container');
    if (flashMessageContainer && flashMessageContainer.children.length > 0) {
        setTimeout(function() {
            flashMessageContainer.style.display = 'none';
        }, 3000);
    }

    function removeChatGPTElements() {
        const elementsToRemove = document.querySelectorAll('use-chat-gpt-ai, use-chat-gpt-ai-content-menu, max-ai-minimum-app');
        elementsToRemove.forEach(el => el.remove());
    }

    removeChatGPTElements();

    const observer = new MutationObserver(removeChatGPTElements);
    observer.observe(document.body, { childList: true, subtree: true });
});
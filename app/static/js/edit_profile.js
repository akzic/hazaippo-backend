document.addEventListener("DOMContentLoaded", function() {
    var imageInput = document.getElementById("image");
    var imagePreview = document.getElementById("imagePreview");

    if (imageInput) {
        imageInput.addEventListener("change", function() {
            var file = this.files[0];
            if (file) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    imagePreview.src = e.target.result;
                    imagePreview.style.display = "block";
                };
                reader.readAsDataURL(file);
            }
        });
    }

    function removeChatGPTElements() {
        const elementsToRemove = document.querySelectorAll('use-chat-gpt-ai, use-chat-gpt-ai-content-menu, max-ai-minimum-app');
        elementsToRemove.forEach(el => el.remove());
    }

    removeChatGPTElements();

});

function openTab(evt, tabName) {
    var i, tabcontent, tabbuttons;
    tabcontent = document.getElementsByClassName("tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    tabbuttons = document.getElementsByClassName("tab-button");
    for (i = 0; i < tabbuttons.length; i++) {
        tabbuttons[i].className = tabbuttons[i].className.replace(" active", "");
    }
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.className += " active";
}
// app/static/js/edit_material.js

document.addEventListener("DOMContentLoaded", function() {
    const materialType = document.getElementById("material_type");
    const woodTypeGroup = document.getElementById("wood_type_group");
    const plasterboardTypeGroup = document.getElementById("board_material_type_group");
    const panelTypeGroup = document.getElementById("panel_type_group");
    const size3 = document.getElementById("material_size_3"); // サイズ3フィールド

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

    // フィールドの表示・非表示を切り替える関数
    function toggleFields() {
        const selectedType = materialType.value;

        // 全ての追加フィールドを非表示に
        woodTypeGroup.style.display = "none";
        plasterboardTypeGroup.style.display = "none";
        panelTypeGroup.style.display = "none";

        // 選択されたタイプに応じてフィールドを表示
        if (selectedType === "木材") {
            woodTypeGroup.style.display = "";
        } else if (selectedType === "ボード材") {
            plasterboardTypeGroup.style.display = "";
        } else if (selectedType === "パネル材") {
            panelTypeGroup.style.display = "";
        }

        // ボード材またはパネル材が選択された場合、サイズ3のプレースホルダーを変更
        if (selectedType === "ボード材" || selectedType === "パネル材") {
            size3.placeholder = "厚み";
        } else {
            size3.placeholder = "";
        }
    }

    // material_typeの変更イベントにtoggleFieldsをバインド
    materialType.addEventListener("change", toggleFields);

    // 初期表示の設定
    toggleFields();
});

// app/static/js/search_wanted.js

$(document).ready(function() {
    // 検索フォームのAJAX送信処理
    $('#search-wanted-form').on('submit', function(event) {
        event.preventDefault(); // フォームのデフォルトの送信を防ぐ

        $.ajax({
            url: $(this).attr('action'), // フォームのaction属性を使用
            method: $(this).attr('method'), // フォームのmethod属性を使用
            data: $(this).serialize(), // フォームデータをシリアライズ
            headers: {
                'X-Requested-With': 'XMLHttpRequest' // AJAXリクエストであることを示すヘッダー
            },
            success: function(response) {
                // メッセージを表示
                if (response.messages && response.messages.length > 0) {
                    $('#flash-container').empty();
                    response.messages.forEach(function(message, index){
                        var category = response.categories[index] || 'info';
                        var alertClass = 'alert-' + (category === 'error' ? 'danger' : category);
                        $('#flash-container').append(
                            '<div class="flash-message ' + alertClass + '">' + message + '</div>'
                        );
                    });
                }

                // 検索結果の有無をチェック
                if (response.has_results) {
                    // 検索結果がある場合、結果を表示
                    if (response.html) {
                        $('#search-wanted-results').html(response.html).show(); // 結果を更新して表示
                    }

                    // 検索結果へスムーズにスクロール
                    $('html, body').animate({
                        scrollTop: $('#search-wanted-results').offset().top
                    }, 1000); // 1000ミリ秒でスクロール
                } else {
                    // 検索結果がない場合、モーダルを表示
                    showModal();

                    // 検索結果コンテナをクリア
                    $('#search-wanted-results').empty();
                }
            },
            error: function(xhr, status, error) {
                console.error('希望材料検索中にエラーが発生しました:', error);
                alert('希望材料検索中にエラーが発生しました。もう一度お試しください。');
            }
        });
    });

    // 材料タイプの変更に応じたフィールドの表示/非表示
    const materialType = $("#wanted_material_type");
    const size3 = $("#wanted_size_3");
    const woodTypeGroup = $("#wanted_wood_type_group");
    const boardMaterialTypeGroup = $("#wanted_board_material_type_group");
    const panelTypeGroup = $("#wanted_panel_type_group");

    function toggleFields() {
        const selectedType = materialType.val();

        // すべての追加フィールドを非表示に
        woodTypeGroup.hide();
        boardMaterialTypeGroup.hide();
        panelTypeGroup.hide();

        // 選択されたタイプに応じてフィールドを表示
        if (selectedType === "木材") {
            woodTypeGroup.show();
        } else if (selectedType === "ボード材") {
            boardMaterialTypeGroup.show();
        } else if (selectedType === "パネル材") {
            panelTypeGroup.show();
        }

        // ボード材またはパネル材が選択された場合、サイズ3のプレースホルダーを変更
        if (selectedType === "ボード材" || selectedType === "パネル材") {
            size3.attr("placeholder", "厚み");
        } else {
            size3.attr("placeholder", "");
        }
    }

    // カスタムモーダルを表示する関数
    function showModal() {
        var modal = document.getElementById("no-results-modal");
        var closeButton = document.getElementsByClassName("close-button")[0];

        // モーダルを表示
        modal.style.display = "block";

        // 閉じるボタンがクリックされたとき
        closeButton.onclick = function() {
            modal.style.display = "none";
        }

        // モーダルの外側がクリックされたとき
        window.onclick = function(event) {
            if (event.target == modal) {
                modal.style.display = "none";
            }
        }
    }

    // 材料タイプの変更イベントにリスナーを追加
    materialType.on("change", toggleFields);

    // 初期表示時にフィールドの表示状態を設定
    toggleFields();
});

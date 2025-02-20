// app/static/js/search.js

// グローバルスコープに showOnMap 関数を定義
window.showOnMap = function(address, mapElementId) {
    // Google Maps API がロードされているか確認
    if (typeof google === 'undefined' || !google.maps) {
        alert('Google Maps API がロードされていません。');
        return;
    }

    var mapElement = document.getElementById(mapElementId);
    if (!mapElement) {
        alert('マップ要素が見つかりません: ' + mapElementId);
        return;
    }

    // 既にマップが初期化されている場合は再利用
    if (mapElement.dataset.mapInitialized === 'true') {
        var map = mapElement.mapInstance;
        // マップをクリア（既存のマーカーを削除）
        if (map.currentMarker) {
            map.currentMarker.setMap(null);
        }
    } else {
        // マップを初期化
        var map = new google.maps.Map(mapElement, {
            zoom: 15
        });
        mapElement.mapInstance = map;
        mapElement.dataset.mapInitialized = 'true';
    }

    // ジオコーダーを作成
    var geocoder = new google.maps.Geocoder();
    geocoder.geocode({ 'address': address }, function(results, status) {
        if (status === 'OK') {
            // マップの中心を設定
            map.setCenter(results[0].geometry.location);
            // マーカーを追加
            var marker = new google.maps.Marker({
                map: map,
                position: results[0].geometry.location
            });
            map.currentMarker = marker; // 現在のマーカーを保存
            // マップコンテナを表示
            mapElement.style.display = 'block';
        } else {
            alert('住所をマップに表示できませんでした: ' + status);
        }
    });
};

// 材料タイプの変更に応じたフィールドの表示/非表示
function toggleFields() {
    var materialType = $('#material_type').val();
    $('#wood_type_group').hide();
    $('#board_material_type_group').hide();
    $('#panel_type_group').hide();

    if (materialType === '木材') {
        $('#wood_type_group').show();
    } else if (materialType === 'ボード材') {
        $('#board_material_type_group').show();
    } else if (materialType === 'パネル材') {
        $('#panel_type_group').show();
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

$(document).ready(function(){
    // 初期ロード時に検索結果を空にする
    $('#search-results').empty(); // 初期表示を空にする

    // 初期ロード時にフィールドの表示を設定
    toggleFields();

    // 端材の種類が変更されたときにフィールドの表示を切り替える
    $('#material_type').change(function(){
        toggleFields();
    });

    // 検索フォームのAJAX送信
    $('#search-form').on('submit', function(e) {
        e.preventDefault(); // 通常のフォーム送信を防止

        var formData = $(this).serialize(); // フォームデータをシリアライズ

        $.ajax({
            type: 'POST',
            url: $(this).attr('action'), // フォームのaction属性を使用
            data: formData,
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
                        $('#search-results').html(response.html).show(); // 結果を更新して表示
                    }

                    // 検索結果へスムーズにスクロール
                    $('html, body').animate({
                        scrollTop: $('#search-results').offset().top
                    }, 1000); // 1000ミリ秒でスクロール
                } else {
                    // 検索結果がない場合、モーダルを表示
                    showModal();

                    // 検索結果コンテナをクリア
                    $('#search-results').empty();
                }
            },
            error: function(xhr, status, error) {
                console.error('検索中にエラーが発生しました:', error);
                alert('検索中にエラーが発生しました。もう一度お試しください。');
            }
        });
    });
});

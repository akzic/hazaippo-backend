// static/js/material_list.js

document.addEventListener("DOMContentLoaded", function() {
    // AJAX用のURLベース
    const editMaterialAjaxBaseUrl = '/materials/edit_material_ajax/0';
    const deleteMaterialAjaxBaseUrl = '/materials/delete_material_ajax/0';
    const deleteHistoryMaterialAjaxBaseUrl = '/materials/delete_history_material/0';

    // 都道府県リスト
    const prefectures = [
        "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
        "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
        "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
        "岐阜県", "静岡県", "愛知県", "三重県",
        "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
        "鳥取県", "島根県", "岡山県", "広島県", "山口県",
        "徳島県", "香川県", "愛媛県", "高知県",
        "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"
    ];

    // タブ切り替え機能
    window.openTab = function(evt, tabName) {
        // 全てのタブコンテンツを非表示にする
        var tabcontent = document.getElementsByClassName("tabcontent");
        for (var i = 0; i < tabcontent.length; i++) {
            tabcontent[i].style.display = "none";
        }

        // 全てのタブボタンから 'active' クラスを削除
        var tablinks = document.getElementsByClassName("tablinks");
        for (var i = 0; i < tablinks.length; i++) {
            tablinks[i].className = tablinks[i].className.replace(" active", "");
        }

        // 選択されたタブコンテンツを表示し、対応するタブボタンに 'active' クラスを追加
        document.getElementById(tabName).style.display = "block";
        evt.currentTarget.className += " active";
    }

    // 編集用の関数
    window.editRow = function(button) {
        const row = button.closest('tr');
        const materialId = row.getAttribute('data-material-id');

        // テーブルセルを取得
        const typeCell = row.querySelector('.type');
        const categoryCell = row.querySelector('.category');
        const quantityCell = row.querySelector('.quantity');
        const sizeCell = row.querySelector('.size');
        const locationCell = row.querySelector('.location');
        const deadlineCell = row.querySelector('.deadline');
        const noteCell = row.querySelector('.note');
        const actionCell = row.querySelector('.action-buttons');

        // 現在の値を取得
        const type = typeCell.textContent.trim();
        const category = categoryCell.textContent.trim();
        const quantity = quantityCell.textContent.trim();
        const sizeText = sizeCell.textContent.trim();
        const size = sizeText === "指定なし" ? [0.0, 0.0, 0.0] : sizeText.split(' × ').map(Number);
        const locationParts = row.querySelector('.location').textContent.trim().split(' ');
        const m_prefecture = locationParts[0] || "";
        const m_city = locationParts[1] || "";
        const m_address = locationParts.slice(2).join(' ') || "";
        const deadline = deadlineCell.textContent.trim();
        const note = noteCell.textContent.trim();

        // サイズが3つに満たない場合を考慮
        while (size.length < 3) {
            size.push(0.0);
        }

        // セルを入力フィールドに置き換え（登録日は編集不可）
        typeCell.innerHTML = `
            <select class="edit-material_type">
                <option value="">選択してください</option>
                <option value="木材" ${type === "木材" ? "selected" : ""}>木材</option>
                <option value="軽量鉄骨" ${type === "軽量鉄骨" ? "selected" : ""}>軽量鉄骨</option>
                <option value="ボード材" ${type === "ボード材" ? "selected" : ""}>ボード材</option>
                <option value="パネル材" ${type === "パネル材" ? "selected" : ""}>パネル材</option>
                <option value="その他" ${type === "その他" ? "selected" : ""}>その他</option>
            </select>
        `;
        
        categoryCell.innerHTML = `
            <select class="edit-category">
                <option value="">選択してください</option>
                <!-- 初期表示では対応する材種のみを表示 -->
            </select>
        `;

        // 材種選択肢の初期設定
        const typeSelect = row.querySelector('.edit-material_type');
        const categorySelect = row.querySelector('.edit-category');

        function updateCategoryOptions(selectedType, currentCategory) {
            let options = '<option value="">選択してください</option>';
            if (selectedType === "木材") {
                options += `
                    <option value="無垢材" ${currentCategory === "無垢材" ? "selected" : ""}>無垢材</option>
                    <option value="集成材（積層材）" ${currentCategory === "集成材（積層材）" ? "selected" : ""}>集成材（積層材）</option>
                    <option value="広葉樹" ${currentCategory === "広葉樹" ? "selected" : ""}>広葉樹</option>
                    <option value="針葉樹" ${currentCategory === "針葉樹" ? "selected" : ""}>針葉樹</option>
                    <option value="ヒノキ" ${currentCategory === "ヒノキ" ? "selected" : ""}>ヒノキ</option>
                    <option value="スギ" ${currentCategory === "スギ" ? "selected" : ""}>スギ</option>
                    <option value="ヒバ" ${currentCategory === "ヒバ" ? "selected" : ""}>ヒバ</option>
                    <option value="マツ（ベイマツ、アカマツ）" ${currentCategory === "マツ（ベイマツ、アカマツ）" ? "selected" : ""}>マツ（ベイマツ、アカマツ）</option>
                    <option value="ケヤキ" ${currentCategory === "ケヤキ" ? "selected" : ""}>ケヤキ</option>
                    <option value="ツガ" ${currentCategory === "ツガ" ? "selected" : ""}>ツガ</option>
                    <option value="キリ" ${currentCategory === "キリ" ? "selected" : ""}>キリ</option>
                    <option value="ホワイトウッド" ${currentCategory === "ホワイトウッド" ? "selected" : ""}>ホワイトウッド</option>
                    <option value="ウォールナット" ${currentCategory === "ウォールナット" ? "selected" : ""}>ウォールナット</option>
                    <option value="パイン" ${currentCategory === "パイン" ? "selected" : ""}>パイン</option>
                `;
            } else if (selectedType === "ボード材") {
                options += `
                    <option value="防火質" ${currentCategory === "防火質" ? "selected" : ""}>防火質</option>
                    <option value="防塵質" ${currentCategory === "防塵質" ? "selected" : ""}>防塵質</option>
                `;
            } else if (selectedType === "パネル材") {
                options += `
                    <option value="床材" ${currentCategory === "床材" ? "selected" : ""}>床材</option>
                    <option value="壁材" ${currentCategory === "壁材" ? "selected" : ""}>壁材</option>
                `;
            } else {
                // その他の場合は選択肢を無効にする
                options = '<option value="">選択できません</option>';
            }
            categorySelect.innerHTML = options;
        }

        // 初期化
        updateCategoryOptions(type, category);

        // イベントリスナーの追加
        typeSelect.addEventListener('change', function() {
            const selectedType = this.value;
            updateCategoryOptions(selectedType, "");
        });

        quantityCell.innerHTML = `<input type="number" min="1" value="${quantity}" required />`;

        sizeCell.innerHTML = `
            <input type="number" min="0" step="0.1" class="size_1" value="${size[0]}" style="width: 30%;" required /> × 
            <input type="number" min="0" step="0.1" class="size_2" value="${size[1]}" style="width: 30%;" required /> × 
            <input type="number" min="0" step="0.1" class="size_3" value="${size[2]}" style="width: 30%;" required />
        `;

        // location を m_prefecture, m_city, m_address に編集
        locationCell.innerHTML = `
            <select class="edit-m-prefecture">
                <option value="">選択してください</option>
                ${prefectures.map(pref => `<option value="${pref}" ${pref === m_prefecture ? "selected" : ""}>${pref}</option>`).join('')}
            </select><br/>
            <input type="text" class="edit-m-city" value="${m_city}" placeholder="市区町村" style="width: 45%;" /> 
            <input type="text" class="edit-m-address" value="${m_address}" placeholder="住所" style="width: 45%;" />
        `;

        deadlineCell.innerHTML = `<input type="datetime-local" class="edit-deadline" value="${convertToInputDate(deadline)}" required />`;

        noteCell.innerHTML = `<input type="text" value="${note !== "N/A" ? note : ""}" />`;

        // アクションボタンを「保存」と「キャンセル」に変更
        actionCell.innerHTML = `
            <button class="save-button btn btn-success" onclick="saveEdit(this, ${materialId})">保存</button>
            <button class="cancel-button btn btn-secondary" onclick="cancelEdit(this)">キャンセル</button>
        `;

        // 編集中の行をハイライト
        row.classList.add('editable');
    }

    window.saveEdit = function(button, materialId) {
        const row = button.closest('tr');

        // 入力フィールドから値を取得
        const typeInput = row.querySelector('.edit-material_type').value.trim();
        const categoryInput = row.querySelector('.edit-category').value.trim();
        const quantityInput = row.querySelector('.quantity input').value.trim();
        const size1Input = row.querySelector('.size_1').value.trim();
        const size2Input = row.querySelector('.size_2').value.trim();
        const size3Input = row.querySelector('.size_3').value.trim();
        const m_prefectureInput = row.querySelector('.edit-m-prefecture').value.trim();
        const m_cityInput = row.querySelector('.edit-m-city').value.trim();
        const m_addressInput = row.querySelector('.edit-m-address').value.trim();
        const deadlineInput = row.querySelector('.edit-deadline').value.trim();
        const noteInput = row.querySelector('.note input').value.trim();

        // CSRFトークンを取得
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        // 締切日をDateオブジェクトに変換
        const deadlineDate = new Date(deadlineInput);
        const now = new Date();

        // 締切日が現在日時を過ぎているかチェック
        if (deadlineDate < now) {
            alert('締切日は現在日時より前に設定できません。');
            return;
        }

        // データを準備
        const data = {
            type: typeInput,
            category: categoryInput,
            quantity: quantityInput,
            size_1: parseFloat(size1Input),
            size_2: parseFloat(size2Input),
            size_3: parseFloat(size3Input),
            m_prefecture: m_prefectureInput || "",
            m_city: m_cityInput || "",
            m_address: m_addressInput || "",
            deadline: deadlineInput,
            note: noteInput || ""
        };

        // 材種フィールドの追加
        if (typeInput === "木材") {
            data.wood_type = categoryInput || "";
            data.board_material_type = "";
            data.panel_type = "";
        } else if (typeInput === "ボード材") {
            data.board_material_type = categoryInput || "";
            data.wood_type = "";
            data.panel_type = "";
        } else if (typeInput === "パネル材") {
            data.panel_type = categoryInput || "";
            data.wood_type = "";
            data.board_material_type = "";
        } else {
            data.wood_type = "";
            data.board_material_type = "";
            data.panel_type = "";
        }

        // 編集用の URL を生成
        const url = editMaterialAjaxBaseUrl.replace('/0', `/${materialId}`);

        // AJAXリクエストを送信
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken  // CSRFトークンをヘッダーに含める
            },
            body: JSON.stringify(data),
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(errData => { throw errData; });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                // 成功した場合、テーブルを更新
                row.querySelector('.type').textContent = data.material.type;
                row.querySelector('.category').textContent = data.material.wood_type || data.material.board_material_type || data.material.panel_type || "";
                
                // サイズの表示
                if (data.material.size_1 === 0.0 && data.material.size_2 === 0.0 && data.material.size_3 === 0.0) {
                    row.querySelector('.size').textContent = "指定なし";
                } else {
                    row.querySelector('.size').textContent = `${data.material.size_1} × ${data.material.size_2} × ${data.material.size_3}`;
                }

                // 場所の表示
                const locationText = [data.material.m_prefecture, data.material.m_city, data.material.m_address].filter(part => part).join(' ');
                row.querySelector('.location').textContent = locationText;
                row.querySelector('.location').setAttribute('data-m-prefecture', data.material.m_prefecture || "");
                row.querySelector('.location').setAttribute('data-m-city', data.material.m_city || "");
                row.querySelector('.location').setAttribute('data-m-address', data.material.m_address || "");

                row.querySelector('.quantity').textContent = data.material.quantity;
                row.querySelector('.deadline').textContent = formatDateTime(data.material.deadline);
                row.querySelector('.note').textContent = data.material.note || "";

                // 締切日が過去かどうかのクラスを更新
                const deadlineDate = new Date(data.material.deadline);
                const now = new Date();
                if (deadlineDate < now) {
                    row.querySelector('.deadline').classList.add('deadline-past');
                } else {
                    row.querySelector('.deadline').classList.remove('deadline-past');
                }

                // アクションボタンを元に戻す
                const csrfTokenValue = csrfToken; // 既に取得済み
                const deleteUrl = deleteMaterialAjaxBaseUrl.replace('/0', `/${materialId}`);
                const deleteHistoryUrl = deleteHistoryMaterialAjaxBaseUrl.replace('/0', `/${materialId}`);

                // Determine which tab the row is in
                const tabContent = row.closest('.tabcontent');
                const tabId = tabContent.id;

                if (tabId === 'Unmatched') {
                    // Unmatched tab: Restore Edit and Delete buttons
                    row.querySelector('.action-buttons').innerHTML = `
                        <button class="edit-button btn btn-primary" onclick="editRow(this)">編集</button>
                        <form action="${deleteUrl}" method="POST" style="display:inline;">
                            <input type="hidden" name="csrf_token" value="${csrfTokenValue}">
                            <button type="submit" class="btn btn-danger" onclick="return confirm('対象の資材を削除してもよろしいですか。');">削除</button>
                        </form>
                    `;
                } else if (tabId === 'Completed') {
                    // Completed tab: Restore only Delete History button
                    row.querySelector('.action-buttons').innerHTML = `
                        <form class="delete-history-form" data-material-id="${materialId}" action="${deleteHistoryUrl}" method="POST" style="display:inline;">
                            <input type="hidden" name="csrf_token" value="${csrfTokenValue}">
                            <button type="submit" class="btn btn-warning">履歴削除</button>
                        </form>
                    `;
                }

                // ハイライトを解除
                row.classList.remove('editable');

                alert(data.message);
            } else {
                alert(`更新に失敗しました: ${data.message}`);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            if (error.message) {
                alert(`更新に失敗しました: ${error.message}`);
            } else {
                alert('更新中にエラーが発生しました。');
            }
        });
    }

    window.cancelEdit = function(button) {
        const row = button.closest('tr');

        // 編集をキャンセルして元の状態に戻すためにページをリロード
        window.location.reload();
    }

    // 日時フォーマットの変換（YYYY-MM-DD HH:MM:SS から YYYY-MM-DDTHH:MM）
    function convertToInputDate(datetimeStr) {
        const date = new Date(datetimeStr.replace(/-/g, '/'));  // Safari対策
        const year = date.getFullYear();
        const month = ('0' + (date.getMonth()+1)).slice(-2);
        const day = ('0' + date.getDate()).slice(-2);
        const hours = ('0' + date.getHours()).slice(-2);
        const minutes = ('0' + date.getMinutes()).slice(-2);
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    }

    // 日時フォーマットの変換（YYYY-MM-DDTHH:MM から YYYY-MM-DD HH:MM:SS）
    function formatDateTime(datetimeStr) {
        const date = new Date(datetimeStr);
        const year = date.getFullYear();
        const month = ('0' + (date.getMonth()+1)).slice(-2);
        const day = ('0' + date.getDate()).slice(-2);
        const hours = ('0' + date.getHours()).slice(-2);
        const minutes = ('0' + date.getMinutes()).slice(-2);
        const seconds = ('0' + date.getSeconds()).slice(-2);
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    }

    // モーダル関連
    const modal = document.getElementById("deadlineModal");
    const span = modal.querySelector(".close");

    // モーダルを閉じる
    span.onclick = function() {
        modal.style.display = "none";
    }

    // モーダルの外側をクリックしたら閉じる
    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = "none";
        }
    }

    // ページ読み込み時に締切日が過ぎている資材をチェック
    function checkDeadlines() {
        const rows = document.querySelectorAll('#Unmatched tbody tr, #MatchedUncompleted tbody tr, #Completed tbody tr');
        let hasPastDeadline = false;
        const now = new Date();

        rows.forEach(row => {
            const deadlineStr = row.getAttribute('data-deadline');
            if (!deadlineStr) return;
            const deadline = new Date(deadlineStr);
            if (deadline < now) {
                hasPastDeadline = true;
                // 締切日セルに赤い枠線を追加
                const deadlineCell = row.querySelector('.deadline');
                if (deadlineCell) {
                    deadlineCell.classList.add('deadline-past');
                }
            }
        });

        if (hasPastDeadline) {
            modal.style.display = "block";
        }
    }

    checkDeadlines();

    // 削除フォームのイベントリスナーを追加
    const deleteForms = document.querySelectorAll('.delete-form, .delete-history-form');
    deleteForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            event.preventDefault(); // 通常のフォーム送信を防止

            const materialId = this.getAttribute('data-material-id');
            const actionUrl = this.getAttribute('action');
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
            const isHistoryDelete = this.classList.contains('delete-history-form'); // 履歴削除かどうかを判定

            let confirmMessage = '対象の資材を削除してもよろしいですか。';
            if (isHistoryDelete) {
                confirmMessage = '対象の資材の履歴を削除してもよろしいですか。';
            }

            if (!confirm(confirmMessage)) {
                return; // ユーザーがキャンセルした場合
            }

            // ロードインジケーターを表示
            document.getElementById('loading-indicator').style.display = 'block';

            // AJAXリクエストを送信
            fetch(actionUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken // CSRFトークンをヘッダーに含める
                },
                body: JSON.stringify({}) // 必要なデータがあればここに追加
            })
            .then(response => response.json())
            .then(data => {
                // ロードインジケーターを非表示
                document.getElementById('loading-indicator').style.display = 'none';

                if (data.status === 'success') {
                    alert(data.message); // 成功メッセージを表示

                    // 削除された行をテーブルから削除
                    const row = form.closest('tr');
                    if (row) {
                        // 削除アニメーション
                        row.style.transition = "opacity 0.5s ease-out";
                        row.style.opacity = "0";
                        setTimeout(() => {
                            row.remove();
                        }, 500); // 0.5秒後に削除
                    }
                } else {
                    alert(`削除に失敗しました: ${data.message}`);
                }
            })
            .catch(error => {
                // ロードインジケーターを非表示
                document.getElementById('loading-indicator').style.display = 'none';

                console.error('Error:', error);
                alert('削除中にエラーが発生しました。');
            });
        });
    });

});

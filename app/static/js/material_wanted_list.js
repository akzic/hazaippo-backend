// app/static/js/material_wanted_list.js

document.addEventListener("DOMContentLoaded", function() {
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

    // 希望端材の編集用の関数
    window.editWantedRow = function(button) {
        const row = button.closest('tr');
        const wantedMaterialId = row.getAttribute('data-wanted-material-id');

        // テーブルセルを取得
        const typeCell = row.querySelector('.type');
        const categoryCell = row.querySelector('.category');
        const quantityCell = row.querySelector('.quantity');
        const sizeCell = row.querySelector('.size');
        const deadlineCell = row.querySelector('.deadline');
        const noteCell = row.querySelector('.note');
        const actionCell = row.querySelector('.action-buttons');

        // 現在の値を取得
        const type = typeCell.textContent.trim();
        const category = categoryCell.textContent.trim();
        const quantity = quantityCell.textContent.trim();
        const size = sizeCell.textContent.trim().split(' × ');
        const deadline = deadlineCell.textContent.trim();
        const note = noteCell.textContent.trim();

        // サイズが3つに満たない場合を考慮
        while (size.length < 3) {
            size.push('');
        }

        // セルを入力フィールドに置き換え（登録日とマッチ日時は編集不可）
        typeCell.innerHTML = `
            <select class="edit-type" required>
                <option value="">選択してください</option>
                <option value="木材" ${type === "木材" ? "selected" : ""}>木材</option>
                <option value="軽量鉄骨" ${type === "軽量鉄骨" ? "selected" : ""}>軽量鉄骨</option>
                <option value="ボード材" ${type === "ボード材" ? "selected" : ""}>ボード材</option>
                <option value="パネル材" ${type === "パネル材" ? "selected" : ""}>パネル材</option>
                <option value="その他" ${type === "その他" ? "selected" : ""}>その他</option>
            </select>
        `;
        
        categoryCell.innerHTML = `
            <select class="edit-category" required>
                <option value="">選択してください</option>
                <!-- 初期表示では対応する材種のみを表示 -->
            </select>
        `;

        // 材種選択肢の初期設定
        const typeSelect = row.querySelector('.edit-type');
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
            <input type="number" min="0" step="0.1" class="size_1" value="${size[0]}" style="width: 30%;" /> × 
            <input type="number" min="0" step="0.1" class="size_2" value="${size[1]}" style="width: 30%;" /> × 
            <input type="number" min="0" step="0.1" class="size_3" value="${size[2]}" style="width: 30%;" />
        `;
        // locationCell.innerHTML = `...`; // 「場所」列を削除したため、この行を削除またはコメントアウト

        deadlineCell.innerHTML = `
            <input type="datetime-local" class="edit-deadline" value="${convertToInputDate(deadline)}" required />
        `;
        noteCell.innerHTML = `<input type="text" value="${note}" />`;

        // アクションボタンを「保存」と「キャンセル」に変更
        actionCell.innerHTML = `
            <button class="save-button btn btn-success" onclick="saveWantedEdit(this, ${wantedMaterialId})">保存</button>
            <button class="cancel-button btn btn-secondary" onclick="cancelWantedEdit(this)">キャンセル</button>
        `;

        // 編集中の行をハイライト
        row.classList.add('editable');
    }

    // saveWantedEdit 関数の修正
    window.saveWantedEdit = function(button, wantedMaterialId) {
        const row = button.closest('tr');

        // 入力フィールドから値を取得
        const typeInput = row.querySelector('.type select').value.trim();
        const categoryInput = row.querySelector('.category select').value.trim();
        const quantityInput = row.querySelector('.quantity input').value.trim();
        const size1Input = row.querySelector('.size_1').value.trim();
        const size2Input = row.querySelector('.size_2').value.trim();
        const size3Input = row.querySelector('.size_3').value.trim();
        const deadlineInput = row.querySelector('.edit-deadline').value.trim();
        const noteInput = row.querySelector('.note input').value.trim();

        // データを準備
        const data = {
            type: typeInput,
            category: categoryInput,
            quantity: quantityInput,
            size_1: size1Input !== '' ? parseFloat(size1Input) : 0.0,
            size_2: size2Input !== '' ? parseFloat(size2Input) : 0.0,
            size_3: size3Input !== '' ? parseFloat(size3Input) : 0.0,
            deadline: deadlineInput,
            note: noteInput || ""
        };

        // 「材種」を必須にするバリデーション
        const requiredTypes = ["木材", "ボード材", "パネル材"];
        if (requiredTypes.includes(typeInput) && categoryInput === "") {
            alert('「材種」を選択してください。');
            return;
        }

        // 必須フィールドのチェック（サイズフィールドを除外）
        const requiredFields = ['type', 'quantity', 'deadline'];
        for (let field of requiredFields) {
            if (!data[field] || data[field].toString().trim() === '') {
                alert(`${field} は必須項目です。`);
                return;
            }
        }

        // 締切日のバリデーション（⑥）
        const deadlineDate = new Date(data.deadline);
        const now = new Date();
        if (deadlineDate < now) {
            alert('締切日は現在日時より前に設定できません。');
            return;
        }

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

        // CSRFトークンを取得
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        // 編集用の URL を生成
        const url = editWantedMaterialAjaxBaseUrl.replace('/0', `/${wantedMaterialId}`);

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
                row.querySelector('.type').textContent = data.wanted_material.type;
                row.querySelector('.category').textContent = data.wanted_material.wood_type || data.wanted_material.board_material_type || data.wanted_material.panel_type || "";
                row.querySelector('.quantity').textContent = data.wanted_material.quantity;

                // サイズの表示
                row.querySelector('.size').textContent = `${data.wanted_material.size_1} × ${data.wanted_material.size_2} × ${data.wanted_material.size_3}`;

                // 締切日の表示と赤枠の設定（②）
                const deadlineCell = row.querySelector('.deadline');
                if (data.wanted_material.deadline !== '未設定') {
                    const deadlineDate = new Date(data.wanted_material.deadline);
                    deadlineCell.textContent = deadlineDate.toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' });

                    if (deadlineDate < new Date()) {
                        deadlineCell.classList.add('deadline-past');
                    } else {
                        deadlineCell.classList.remove('deadline-past');
                    }

                    // 行の data-deadline 属性を更新
                    row.setAttribute('data-deadline', data.wanted_material.deadline);
                } else {
                    deadlineCell.textContent = '未設定';
                    deadlineCell.classList.remove('deadline-past');

                    // 行の data-deadline 属性を更新
                    row.setAttribute('data-deadline', '');
                }

                row.querySelector('.note').textContent = data.wanted_material.note || "";

                // アクションボタンを元に戻す
                row.querySelector('.action-buttons').innerHTML = `
                    <button class="edit-button btn btn-primary" onclick="editWantedRow(this)">編集</button>
                    <button class="delete-button btn btn-danger" onclick="deleteWantedMaterial(this, '${wantedMaterialId}')">削除</button>
                `;

                // ハイライトを解除
                row.classList.remove('editable');

                alert(data.message);

                // 再度締切日が過ぎているかチェック（②）
                checkDeadline(row);
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

    window.cancelWantedEdit = function(button) {
        const row = button.closest('tr');

        // 編集をキャンセルして元の状態に戻すためにページをリロード
        window.location.reload();
    }

    // AJAXによる希望材料の削除
    window.deleteWantedMaterial = function(button, wantedMaterialId) {
        if (!confirm('対象の希望端材を削除してもよろしいですか。')) {
            return;
        }

        // CSRFトークンを取得
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        // 削除用の URL を生成
        const url = deleteWantedMaterialAjaxBaseUrl.replace('/0', `/${wantedMaterialId}`);

        // ロードインジケーターを表示
        document.getElementById('loading-indicator').style.display = 'block';

        // AJAXリクエストを送信
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken  // CSRFトークンをヘッダーに含める
            },
            credentials: 'same-origin'
        })
        .then(response => response.json())
        .then(data => {
            // ロードインジケーターを非表示
            document.getElementById('loading-indicator').style.display = 'none';

            if (data.status === 'success') {
                // 成功した場合、行を削除
                const rowToDelete = button.closest('tr');
                if (rowToDelete) {
                    rowToDelete.remove();
                }
                alert(data.message);
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
    }

    // 締切日が過ぎている端材が存在するかチェックしてモーダルを表示（⑤）
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
                // 締切日セルに赤い枠線を追加（②）
                const deadlineCell = row.querySelector('.deadline');
                if (deadlineCell) {
                    deadlineCell.classList.add('deadline-past');
                }
            }
        });

        if (hasPastDeadline) {
            showModal();
        }
    }

    // モーダル表示関数
    function showModal() {
        const modal = document.getElementById("deadlineModal");
        modal.style.display = "block";
    }

    // モーダルを閉じる関数
    function closeModal() {
        const modal = document.getElementById("deadlineModal");
        modal.style.display = "none";
    }

    // モーダルの「×」ボタンをクリックしたときに閉じる
    const modal = document.getElementById("deadlineModal");
    const span = modal.querySelector(".close");
    span.onclick = function() {
        closeModal();
    }

    // モーダルの外側をクリックしたら閉じる
    window.onclick = function(event) {
        if (event.target == modal) {
            closeModal();
        }
    }

    // 締切日が過ぎている場合に赤枠を追加する関数（②）
    function addDeadlinePastClass(row) {
        const deadlineStr = row.getAttribute('data-deadline');
        if (!deadlineStr) return;
        const deadline = new Date(deadlineStr);
        const now = new Date();
        if (deadline < now) {
            const deadlineCell = row.querySelector('.deadline');
            if (deadlineCell) {
                deadlineCell.classList.add('deadline-past');
            }
        }
    }

    // 締切日が過ぎているかチェックして赤枠を追加（②）
    function checkDeadline(row) {
        const deadlineStr = row.getAttribute('data-deadline');
        if (!deadlineStr) return;
        const deadline = new Date(deadlineStr);
        const now = new Date();
        const deadlineCell = row.querySelector('.deadline');
        if (deadline < now && deadlineCell) {
            deadlineCell.classList.add('deadline-past');
        } else if (deadlineCell) {
            deadlineCell.classList.remove('deadline-past');
        }
    }

    // 日時フォーマットの変換（YYYY-MM-DD HH:MM:SS から YYYY-MM-DDTHH:MM）
    function convertToInputDate(datetimeStr) {
        if (!datetimeStr || datetimeStr === '未設定') return '';
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
        if (!datetimeStr) return '未設定';
        const date = new Date(datetimeStr);
        const year = date.getFullYear();
        const month = ('0' + (date.getMonth()+1)).slice(-2);
        const day = ('0' + date.getDate()).slice(-2);
        const hours = ('0' + date.getHours()).slice(-2);
        const minutes = ('0' + date.getMinutes()).slice(-2);
        const seconds = ('0' + date.getSeconds()).slice(-2);
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    }

    // ページ読み込み時に締切日が過ぎている端材をチェック（②, ⑤）
    checkDeadlines();

    // ロードインジケーターのスタイルを追加
    const style = document.createElement('style');
    style.innerHTML = `
        #loading-indicator {
            display: none;
            position: fixed;
            z-index: 1001;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            padding: 20px;
            background-color: rgba(255,255,255,0.9);
            border: 1px solid #ccc;
            border-radius: 5px;
            text-align: center;
        }
    `;
    document.head.appendChild(style);
});

// モーダル関連は既にHTMLに含まれているため、JavaScript内で処理

// サイズが全て0.0の場合「指定なし」を表示するロジックはテンプレート側で既に実装済み（①）

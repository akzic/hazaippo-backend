// app/static/js/register_material.js

document.addEventListener("DOMContentLoaded", function() {
    const materialType = document.getElementById('material_type');
    const woodTypeGroup = document.getElementById('wood_type_group');
    const boardMaterialTypeGroup = document.getElementById('board_material_type_group');
    const panelTypeGroup = document.getElementById('panel_type_group');
    const size3Input = document.getElementById('material_size_3');
    const imageInput = document.getElementById('image');
    const form = document.getElementById('registerMaterialForm');
    const m_prefectureInput = document.getElementById('m_prefecture');
    const m_cityInput = document.getElementById('m_city');
    const m_addressInput = document.getElementById('m_address');
    const cityDatalist = document.getElementById('city_options');
    const addressDatalist = document.getElementById('address_options');
    const debugData = document.getElementById('debugData');
    const deleteImageButton = document.getElementById('deleteImageButton');
    const submitButton = document.getElementById('submitButton');

    // カメラモーダル関連の要素
    const cameraModal = document.getElementById('cameraModal');
    const cameraContent = document.getElementById('cameraContent');
    const closeCamera = document.getElementById('closeCamera');
    const cameraStream = document.getElementById('cameraStream');
    const captureImageBtn = document.getElementById('captureImageBtn');
    const startCameraButton = document.getElementById('startCameraButton'); // カメラ起動ボタン

    // 選択モーダル関連の要素
    const selectionModal = document.getElementById('selectionModal');
    const closeSelectionModal = document.getElementById('closeSelectionModal');
    const selectionContent = document.getElementById('selectionContent');
    
    // Successモーダル関連の要素
    const successModal = document.getElementById('successModal');
    const closeSuccessModal = document.getElementById('closeSuccessModal');

    // 一般エラーメッセージ要素
    const generalError = document.getElementById('general-error');

    let stream = null;

    // business_structure をデータ属性から取得
    const businessStructure = form.dataset.businessStructure;
    const dashboardURL = form.dataset.dashboardUrl; // ダッシュボードホームのURLを取得

    // AI処理結果を保持
    let aiResults = {
        preprocessed: {},
        non_preprocessed: {}
    };

    // タスクIDの保持
    let currentTaskId = null;
    let taskCheckInterval = null;

    // 最大試行回数を設定
    const MAX_RETRIES = 5;
    let retryCount = 0;

    /**
     * フォームのフィールド表示を切り替える関数
     */
    function toggleFields() {
        const selectedType = materialType.value;

        // 全ての追加フィールドを非表示に
        woodTypeGroup.style.display = "none";
        boardMaterialTypeGroup.style.display = "none";
        panelTypeGroup.style.display = "none";

        // 選択されたタイプに応じてフィールドを表示
        if (selectedType === "木材") {
            woodTypeGroup.style.display = "";
        } else if (selectedType === "ボード材") {
            boardMaterialTypeGroup.style.display = "";
        } else if (selectedType === "パネル材") {
            panelTypeGroup.style.display = "";
        }

        // ボード材またはパネル材が選択された場合
        if (selectedType === "ボード材" || selectedType === "パネル材") {
            size3Input.placeholder = "厚み (mm)";
        } else {
            size3Input.placeholder = "";
        }

        logFormData();
    }

    /**
     * 数値入力のバリデーション
     * - quantity: 1から100まで
     * - size fields: 0より大きい
     */
    function validateNumberInput(event) {
        const field = event.target;
        const value = field.value;

        // 既存の半角数字チェック
        if (value === '') {
            field.setCustomValidity('');
            return;
        }
        if (!/^\d*\.?\d*$/.test(value)) {
            field.setCustomValidity("半角数字のみを入力してください。");
        } else {
            field.setCustomValidity("");
        }

        // 追加のバリデーション
        if (field.id === 'quantity') {
            if (parseInt(value, 10) > 100) {
                field.setCustomValidity("数量は1から100までの値を入力してください。");
            } else if (parseInt(value, 10) < 1) {
                field.setCustomValidity("数量は1から100までの値を入力してください。");
            } else {
                // 数量が有効な範囲内の場合はエラーメッセージをクリア
                field.setCustomValidity("");
            }
        } else if (['material_size_1', 'material_size_2', 'material_size_3'].includes(field.id)) {
            if (parseFloat(value) <= 0) {
                field.setCustomValidity("0より大きい値を入力してください。");
            } else {
                // サイズが有効な場合はエラーメッセージをクリア
                field.setCustomValidity("");
            }
        }

        logFormData();
    }

    /**
     * 画像入力変更時のハンドラ
     */
    function handleImageChange() {
        const file = this.files[0];
        const imagePreview = document.getElementById('imagePreview');
        if (file && imagePreview) {
            const reader = new FileReader();
            reader.onload = function(e) {
                imagePreview.src = e.target.result;
                imagePreview.style.display = 'block';
                deleteImageButton.style.display = 'inline-block';
            };
            reader.readAsDataURL(file);
        }

        if (file) {
            // 画像を処理
            sendImageAndLocation(file);
        }

        logFormData();
    }

    /**
     * 締め切り日時のバリデーション
     */
    function validateDeadline(event) {
        const deadlineInput = document.getElementById('form_deadline');
        const deadlineValue = new Date(deadlineInput.value);
        const currentDate = new Date();

        if (isNaN(deadlineValue.getTime())) {
            alert('有効な締め切り日時を入力してください。');
            event.preventDefault();
            return;
        }

        if (deadlineValue < currentDate) {
            alert('締め切り日時は登録日時以降にしてください。');
            event.preventDefault();
        }

        logFormData();
    }

    /**
     * 都道府県が選択された際に市区町村の候補を取得する関数
     */
    function fetchCityOptions(prefecture) {
        fetch(`/materials/get_cities/${encodeURIComponent(prefecture)}`)
            .then(response => response.json())
            .then(data => {
                // 市区町村の候補を更新
                while (cityDatalist.firstChild) {
                    cityDatalist.removeChild(cityDatalist.firstChild);
                }

                if (data.cities && data.cities.length > 0) {
                    data.cities.forEach(city => {
                        const option = document.createElement('option');
                        option.value = city;
                        cityDatalist.appendChild(option);
                    });
                } else {
                    const option = document.createElement('option');
                    option.text = '該当する市区町村がありません';
                    option.disabled = true;
                    cityDatalist.appendChild(option);
                }

                logFormData();
            })
            .catch(error => {
                console.error('市区町村の取得に失敗しました:', error);
                const option = document.createElement('option');
                option.text = '市区町村の取得に失敗しました';
                option.disabled = true;
                cityDatalist.appendChild(option);
            });
    }

    /**
     * 市区町村が入力された際に住所の候補を取得する関数
     */
    function fetchAddressOptions(prefecture, city) {
        fetch(`/materials/get_addresses/${encodeURIComponent(prefecture)}/${encodeURIComponent(city)}`)
            .then(response => response.json())
            .then(data => {
                // 住所の候補を更新
                while (addressDatalist.firstChild) {
                    addressDatalist.removeChild(addressDatalist.firstChild);
                }

                if (data.addresses && data.addresses.length > 0) {
                    data.addresses.forEach(address => {
                        const option = document.createElement('option');
                        option.value = address;
                        addressDatalist.appendChild(option);
                    });
                } else {
                    const option = document.createElement('option');
                    option.text = '該当する住所がありません';
                    option.disabled = true;
                    addressDatalist.appendChild(option);
                }

                logFormData();
            })
            .catch(error => {
                console.error('住所の取得に失敗しました:', error);
                const option = document.createElement('option');
                option.text = '住所の取得に失敗しました';
                option.disabled = true;
                addressDatalist.appendChild(option);
            });
    }

    /**
     * フォームデータをデバッグ表示する関数
     */
    function logFormData() {
        const formData = {
            material_type: materialType.value,
            wood_type: document.getElementById('wood_type') ? document.getElementById('wood_type').value : '',
            board_material_type: document.getElementById('board_material_type') ? document.getElementById('board_material_type').value : '',
            panel_type: document.getElementById('panel_type') ? document.getElementById('panel_type').value : '',
            material_size_1: document.getElementById('material_size_1').value,
            material_size_2: document.getElementById('material_size_2').value,
            material_size_3: document.getElementById('material_size_3').value,
            m_prefecture: m_prefectureInput ? m_prefectureInput.value : '',
            m_city: m_cityInput ? m_cityInput.value : '',
            m_address: m_addressInput ? m_addressInput.value : '',
            quantity: document.getElementById('quantity').value,
            deadline: document.getElementById('form_deadline').value,
            exclude_weekends: document.getElementById('exclude_weekends').checked,
            note: document.getElementById('note').value,
            ai_preprocessed: aiResults.preprocessed,
            ai_non_preprocessed: aiResults.non_preprocessed
        };
        debugData.textContent = JSON.stringify(formData, null, 2);
        console.log("Form Data:", formData);
    }

    /**
     * 位置情報を取得する関数
     */
    function getLocation() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error("Geolocation is not supported by this browser."));
            } else {
                navigator.geolocation.getCurrentPosition(
                    position => {
                        resolve({
                            latitude: position.coords.latitude,
                            longitude: position.coords.longitude
                        });
                    },
                    error => {
                        reject(error);
                    }
                );
            }
        });
    }

    /**
     * カメラを起動する関数
     */
    async function startCamera() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            cameraStream.srcObject = stream;
            cameraStream.style.display = 'block';
            captureImageBtn.disabled = false;
            cameraModal.style.display = 'block';
        } catch (err) {
            console.error("カメラの起動に失敗しました:", err);
            alert("カメラの起動に失敗しました。");
        }
    }

    /**
     * 画像をキャプチャする関数
     */
    function captureImage() {
        const capturedCanvas = document.getElementById('capturedCanvas');
        const context = capturedCanvas.getContext('2d');
        context.drawImage(cameraStream, 0, 0, capturedCanvas.width, capturedCanvas.height);
        const dataURL = capturedCanvas.toDataURL('image/png');
        capturedCanvas.style.display = 'none';
        cameraStream.style.display = 'none';
        captureImageBtn.disabled = true;
        cameraModal.style.display = 'none';

        // 画像データをFileオブジェクトに変換
        fetch(dataURL)
            .then(res => res.blob())
            .then(blob => {
                const file = new File([blob], "captured_image.png", { type: "image/png" });
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                imageInput.files = dataTransfer.files;

                // 画像と位置情報をサーバーに送信
                sendImageAndLocation(file);
            })
            .catch(err => {
                console.error("画像の処理に失敗しました:", err);
            });

        // ストリームを停止
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
    }

    /**
     * 画像と位置情報をサーバーに送信する関数
     */
    async function sendImageAndLocation(file) {
        // フォーム送信ボタンを無効化
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent = "処理中...";
        }

        // 位置情報の取得
        let locationData = null;
        try {
            locationData = await getLocation();
        } catch (error) {
            console.error("位置情報の取得に失敗しました:", error);
            alert("位置情報の取得に失敗しました。位置情報を許可してください。");
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.textContent = "登録";
            }
            return;
        }

        // フォームデータの作成
        const formData = new FormData();
        formData.append('image', file);
        formData.append('latitude', locationData.latitude);
        formData.append('longitude', locationData.longitude);

        try {
            const response = await fetch('/camera_ai/process_image', { // camera_ai Blueprint のエンドポイント
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                if (errorData && errorData.message) {
                    generalError.textContent = errorData.message;
                    generalError.style.display = 'block';
                } else {
                    generalError.textContent = '予期しないエラーが発生しました。';
                    generalError.style.display = 'block';
                }
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = "登録";
                }
                return;
            }

            const data = await response.json();
            if (data.status === 'success') {
                // タスクIDを保持
                currentTaskId = data.task_id;
                // retryCountをリセット
                retryCount = 0;
                // タスクのステータスを定期的にチェック
                taskCheckInterval = setInterval(checkTaskStatus, 2000);
                // Successメッセージを表示（既存のフラッシュメッセージと連動）
                // 既存のフラッシュメッセージ機構を利用している場合は不要
                // ここではアラートではなく、フラッシュメッセージを利用
            } else {
                generalError.textContent = `データの抽出に失敗しました: ${data.message}`;
                generalError.style.display = 'block';
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = "登録";
                }
            }
        } catch (error) {
            console.error("データの送信に失敗しました:", error);
            generalError.textContent = 'データの送信に失敗しました。';
            generalError.style.display = 'block';
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.textContent = "登録";
            }
        }
    }

    /**
     * タスクステータスをチェックする関数
     */
    async function checkTaskStatus() {
        try {
            const response = await fetch(`/camera_ai/task_status/${currentTaskId}`, {
                method: 'GET'
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            if (data.status === 'success') {
                // AIからのデータを保持
                aiResults.preprocessed = data.preprocessed;
                aiResults.non_preprocessed = data.non_preprocessed;

                // モーダルに結果を表示
                displaySelectionModal();

                // タスクステータスチェックを停止
                clearInterval(taskCheckInterval);
                taskCheckInterval = null;

                // フォーム送信ボタンを有効化
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = "登録";
                }

                // Successメッセージを表示（既存のフラッシュメッセージ機構を利用）
                // ここでは既に別途フラッシュメッセージが設定されている場合は不要
            } else if (data.status === 'pending') {
                // タスクがまだ実行中
                console.log(`タスクステータス: pending`);
                retryCount++;
                if (retryCount >= MAX_RETRIES) {
                    console.warn('最大試行回数に達しました。');
                    clearInterval(taskCheckInterval);
                    taskCheckInterval = null;
                    alert('タスクが時間内に完了しませんでした。');
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.textContent = "登録";
                    }
                }
            } else {
                // タスクが失敗
                clearInterval(taskCheckInterval);
                taskCheckInterval = null;
                alert(`画像の処理に失敗しました: ${data.message}`);
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = "登録";
                }
            }
        } catch (error) {
            console.error("タスクステータスの取得に失敗しました:", error);
            retryCount++;
            if (retryCount >= MAX_RETRIES) {
                console.warn('最大試行回数に達しました。');
                clearInterval(taskCheckInterval);
                taskCheckInterval = null;
                alert('タスクステータスの取得に失敗しました。最大試行回数に達しました。');
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = "登録";
                }
            }
        }
    }

    /**
     * 画像を削除する関数
     */
    function deleteImage() {
        imageInput.value = ''; // ファイル入力をクリア
        const imagePreview = document.getElementById('imagePreview');
        if (imagePreview) {
            imagePreview.src = '#';
            imagePreview.style.display = 'none';
        }
        deleteImageButton.style.display = 'none'; // ボタンを非表示
        logFormData();
    }

    /**
     * カメラモーダルを閉じる関数
     */
    function closeCameraModal() {
        if (cameraModal) {
            cameraModal.style.display = 'none';
        }
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
    }

    /**
     * 認識結果を選択するモーダルを表示する関数
     */
    function displaySelectionModal() {
        // モーダルの内容を設定
        selectionContent.innerHTML = generateResultHTML(aiResults.preprocessed, '前処理あり');
        selectionContent.innerHTML += generateResultHTML(aiResults.non_preprocessed, '前処理なし');

        // モーダルを表示
        selectionModal.style.display = 'block';
    }

    /**
     * 認識結果のHTMLを生成する関数
     * @param {Object} result - preprocessed または non_preprocessed の結果
     * @param {string} label - 結果のラベル ('前処理あり' または '前処理なし')
     * @returns {string} - HTML文字列
     */
    function generateResultHTML(result, label) {
        let html = `<div class="result-section mb-4">`;
        html += `<h4>${label}の結果</h4>`;
        html += `<p><strong>端材の種類：</strong> ${result.material_type || '認識不可'}</p>`;

        if (result.material_type === '木材') {
            html += `<p><strong>木材の種類：</strong> ${result.wood_type ? result.wood_type : '認識不可'}</p>`;
        } else if (result.material_type === 'ボード材') {
            html += `<p><strong>ボード材の種類：</strong> ${result.board_material_type ? result.board_material_type : '認識不可'}</p>`;
        } else if (result.material_type === 'パネル材') {
            html += `<p><strong>パネル材の種類：</strong> ${result.panel_type ? result.panel_type : '認識不可'}</p>`;
        }

        html += `<p><strong>サイズ１：</strong> ${result.material_size_1 ? result.material_size_1 : '認識不可'}</p>`;
        html += `<p><strong>サイズ２：</strong> ${result.material_size_2 ? result.material_size_2 : '認識不可'}</p>`;
        html += `<p><strong>サイズ３：</strong> ${result.material_size_3 ? result.material_size_3 : '認識不可'}</p>`;
        html += `<p><strong>数量：</strong> ${result.quantity > 0 ? result.quantity : '認識不可'}</p>`;

        // 新しく追加された位置情報
        if (result.location) {
            html += `<p><strong>位置情報：</strong> ${result.location}</p>`;
        }

        html += `<button class="btn btn-primary select-result-btn" data-result-type="${label === '前処理あり' ? 'preprocessed' : 'non_preprocessed'}">この結果を選択</button>`;
        html += `</div>`;

        return html;
    }

    /**
     * 日本の住所を郵便番号と国名を除去し、都道府県、市区町村、住所に分割する関数
     * @param {string} location - フォーマットされた住所文字列
     * @returns {Object|null} - { prefecture, city, address } または null
     */
    function parseJapaneseAddress(location) {
        try {
            console.log("元のlocation:", location);
            // 住所から国名を除去 (例: 日本、)
            location = location.replace(/^日本[、,]\s*/, '');
            console.log("国名除去後:", location);
            
            // 住所から郵便番号を除去 (例: 〒123-4567)
            location = location.replace(/〒\d{3}-\d{4}\s*/, '');
            console.log("郵便番号除去後:", location);

            // 都道府県のリスト
            const prefectures = [
                '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
                '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
                '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
                '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
                '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
                '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
                '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'
            ];

            // 都道府県を抽出
            let prefecture = null;
            for (let pref of prefectures) {
                if (location.startsWith(pref)) {
                    prefecture = pref;
                    break;
                }
            }

            if (!prefecture) {
                console.warn("都道府県が見つかりませんでした。");
                return null;
            }

            console.log("抽出された都道府県:", prefecture);

            // 都道府県を除いた部分を解析
            let remaining = location.slice(prefecture.length).trim();
            console.log("都道府県を除いた残り:", remaining);

            // 市区町村を抽出（市、区、町、村で終わる）
            const cityMatch = remaining.match(/^([^市区町村]*[市区町村]+)/);
            let city = null;
            let address = null;

            if (cityMatch) {
                city = cityMatch[1];
                address = remaining.slice(city.length).trim();
                console.log("抽出された市区町村:", city);
                console.log("抽出された住所:", address);
            } else {
                // 市区町村が見つからない場合
                city = '';
                address = remaining;
                console.warn("市区町村が見つかりませんでした。");
            }

            return {
                prefecture: prefecture,
                city: city,
                address: address
            };
        } catch (error) {
            console.error("住所のパース中にエラーが発生しました:", error);
            return null;
        }
    }

    /**
     * フォーム送信時に認識結果をフォームに反映する関数
     * @param {string} resultType - 'preprocessed' または 'non_preprocessed'
     */
    function selectResult(resultType) {
        const selectedResult = aiResults[resultType];
        if (selectedResult.status === 'success') {
            // フォームフィールドにデータをセット
            if (selectedResult.material_type) {
                materialType.value = selectedResult.material_type;
                // イベントをトリガーして関連フィールドを表示
                const event = new Event('change');
                materialType.dispatchEvent(event);
            }

            // サブタイプのフィールドをセット
            if (selectedResult.material_type === '木材' && selectedResult.wood_type) {
                const woodTypeField = document.getElementById('wood_type');
                if (woodTypeField) {
                    woodTypeField.value = selectedResult.wood_type;
                }
            }

            if (selectedResult.material_type === 'ボード材' && selectedResult.board_material_type) {
                const boardMaterialTypeField = document.getElementById('board_material_type');
                if (boardMaterialTypeField) {
                    boardMaterialTypeField.value = selectedResult.board_material_type;
                }
            }

            if (selectedResult.material_type === 'パネル材' && selectedResult.panel_type) {
                const panelTypeField = document.getElementById('panel_type');
                if (panelTypeField) {
                    panelTypeField.value = selectedResult.panel_type;
                }
            }

            // サイズフィールドをセット
            if (selectedResult.material_size_1) {
                const size1Field = document.getElementById('material_size_1');
                if (size1Field) {
                    size1Field.value = selectedResult.material_size_1;
                }
            }

            if (selectedResult.material_size_2) {
                const size2Field = document.getElementById('material_size_2');
                if (size2Field) {
                    size2Field.value = selectedResult.material_size_2;
                }
            }

            if (selectedResult.material_size_3) {
                const size3Field = document.getElementById('material_size_3');
                if (size3Field) {
                    size3Field.value = selectedResult.material_size_3;
                }
            }

            // 数量フィールドをセット
            if (selectedResult.quantity > 0) {
                const quantityField = document.getElementById('quantity');
                if (quantityField) {
                    quantityField.value = selectedResult.quantity;
                }
            } else {
                // 数量が0の場合は認識不可としてクリア
                const quantityField = document.getElementById('quantity');
                if (quantityField) {
                    quantityField.value = '';
                }
            }

            // 位置情報をフォームに反映
            if (selectedResult.location) {
                const parsedLocation = parseJapaneseAddress(selectedResult.location);
                if (parsedLocation) {
                    const { prefecture, city, address } = parsedLocation;
                    if (m_prefectureInput) {
                        m_prefectureInput.value = prefecture || '';
                        // 市区町村の候補を更新
                        fetchCityOptions(prefecture || '');
                    }
                    if (m_cityInput) {
                        m_cityInput.value = city || '';
                        // 住所の候補を更新
                        fetchAddressOptions(prefecture || '', city || '');
                    }
                    if (m_addressInput) {
                        m_addressInput.value = address || '';
                    }
                } else {
                    // パースに失敗した場合は単一フィールドに割り当て
                    if (m_prefectureInput) {
                        m_prefectureInput.value = '';
                    }
                    if (m_cityInput) {
                        m_cityInput.value = '';
                    }
                    if (m_addressInput) {
                        m_addressInput.value = selectedResult.location || '';
                    }
                }
            }

            toggleFields();
        }
    }

    /**
     * 受け渡し場所のフィールドに関連するイベントリスナーを設定
     */
    function setupLocationEventListeners() {
        if (m_prefectureInput) {
            m_prefectureInput.addEventListener('change', function() {
                const selectedPrefecture = this.value;
                if (selectedPrefecture) {
                    fetchCityOptions(selectedPrefecture);
                }

                // 住所の候補をクリア
                while (addressDatalist.firstChild) {
                    addressDatalist.removeChild(addressDatalist.firstChild);
                }
                m_addressInput.value = '';
            });
        }

        if (m_cityInput && m_prefectureInput) {
            m_cityInput.addEventListener('input', function() {
                const selectedPrefecture = m_prefectureInput.value;
                const enteredCity = this.value.trim();
                if (selectedPrefecture && enteredCity) {
                    // APIから住所の候補を取得
                    fetchAddressOptions(selectedPrefecture, enteredCity);
                } else {
                    // 住所の候補をクリア
                    while (addressDatalist.firstChild) {
                        addressDatalist.removeChild(addressDatalist.firstChild);
                    }
                    m_addressInput.value = '';
                }
            });
        }
    }

    /**
     * フォーム送信時に位置情報を確認する関数
     */
    function handleFormSubmit(event) {
        // 必要に応じてフォーム送信前の追加処理をここに記述
        // 例: 位置情報が正しく入力されているか確認
    }

    /**
     * イベントリスナーの設定
     */
    function setupEventListeners() {
        if (materialType) {
            materialType.addEventListener('change', toggleFields);
        }

        if (imageInput) {
            imageInput.addEventListener('change', handleImageChange);
        }

        const sizeFields = ['material_size_1', 'material_size_2', 'material_size_3'];
        sizeFields.forEach(id => {
            const input = document.getElementById(id);
            if (input) {
                input.addEventListener('input', validateNumberInput);
            }
        });

        const quantityInput = document.getElementById('quantity');
        if (quantityInput) {
            quantityInput.addEventListener('input', validateNumberInput);
        }

        const deadlineInput = document.getElementById('form_deadline');
        if (form && deadlineInput) {
            form.addEventListener('submit', validateDeadline);
            form.addEventListener('submit', handleFormSubmit);
        }

        // 受け渡し場所のイベントリスナーを設定
        setupLocationEventListeners();

        // カメラモーダルのイベントリスナー
        if (startCameraButton) {
            startCameraButton.addEventListener('click', startCamera);
        }

        if (captureImageBtn) {
            captureImageBtn.addEventListener('click', captureImage);
        }

        if (closeCamera) {
            closeCamera.addEventListener('click', closeCameraModal);
        }

        if (deleteImageButton) {
            deleteImageButton.addEventListener('click', deleteImage);
        }

        // 選択モーダル内の動的ボタンに対するイベントリスナー
        selectionContent.addEventListener('click', function(event) {
            if (event.target && event.target.matches('.select-result-btn')) {
                const resultType = event.target.getAttribute('data-result-type');
                selectResult(resultType);
                // モーダルを閉じる処理をここに移動（念のため）
                selectionModal.style.display = 'none';
            }
        });

        if (closeSelectionModal) {
            closeSelectionModal.addEventListener('click', function() {
                selectionModal.style.display = 'none';
            });
        }

        // Successモーダルのイベントリスナー
        if (closeSuccessModal) {
            closeSuccessModal.addEventListener('click', function() {
                successModal.style.display = 'none';
            });
        }

        // モーダル外クリックで閉じる
        window.addEventListener('click', function(event) {
            if (event.target == cameraModal) {
                closeCameraModal();
            }
            if (event.target == selectionModal) {
                selectionModal.style.display = 'none';
            }
            if (event.target == successModal) {
                successModal.style.display = 'none';
            }
        });
    }

    /**
     * 不要なChatGPT要素を削除する関数
     */
    function removeChatGPTElements() {
        const elementsToRemove = document.querySelectorAll('use-chat-gpt-ai, use-chat-gpt-ai-content-menu, max-ai-minimum-app');
        elementsToRemove.forEach(el => el.remove());
    }

    /**
     * チャットGPT関連の要素を削除する処理
     */
    function removeChatGPTElementsAndSetup() {
        removeChatGPTElements();

        const observer = new MutationObserver(removeChatGPTElements);
        observer.observe(document.body, { childList: true, subtree: true });
    }

    /**
     * フラッシュメッセージの処理
     */
    function handleFlashMessages() {
        // 修正ポイント: クラス名を '.flash-message.alert-success' に変更
        var flashMessages = document.querySelectorAll('.flash-message.alert-success');
        if (flashMessages.length > 0) {
            // Success Modal を表示
            if (successModal) {
                successModal.style.display = 'block';
                // 2秒後にダッシュボードホームに遷移
                setTimeout(function() {
                    window.location.href = dashboardURL;
                }, 2000);
            }
        }

        if (generalError) {
            if (generalError.textContent.trim() !== "") {
                generalError.style.display = 'block';
            } else {
                generalError.style.display = 'none';
            }
        }
    }

    /**
     * フォーム送信ボタンの確認
     */
    function checkSubmitButton() {
        if (!submitButton) {
            console.warn("フォーム送信ボタン（ID: submitButton）が見つかりません。");
        }
    }

    /**
     * 初期化関数
     */
    function initialize() {
        setupEventListeners();
        removeChatGPTElementsAndSetup();
        handleFlashMessages();
        checkSubmitButton();
        logFormData();
    }

    // 初期化を実行
    initialize();
});

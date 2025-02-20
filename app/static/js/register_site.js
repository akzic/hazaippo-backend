// static/js/register_site.js

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('siteRegisterForm');
    const addressInput = document.getElementById('site_address');
    const addressError = document.getElementById('addressError');
    const submitBtn = document.getElementById('submitBtn');
    const alertPlaceholder = document.getElementById('alertPlaceholder');
    const prefectureSelect = document.getElementById('site_prefecture');
    const cityInput = document.getElementById('site_city');
    const successMessage = document.getElementById('successMessage');

    let isAddressValid = false;

    // 住所入力フィールドのイベントリスナー
    addressInput.addEventListener('blur', function () {
        validateAddress();
    });

    prefectureSelect.addEventListener('change', function () {
        validateAddress();
    });

    cityInput.addEventListener('blur', function () {
        validateAddress();
    });

    // フォーム送信時のイベントリスナー
    form.addEventListener('submit', function (e) {
        e.preventDefault(); // デフォルトのフォーム送信を防止

        if (!isAddressValid) {
            addressError.textContent = '住所を正しく入力してください。';
            addressError.classList.remove('d-none');
            return;
        }

        // フォームからデータを取得
        const sitePrefecture = prefectureSelect.value.trim();
        const siteCity = cityInput.value.trim();
        const siteAddress = addressInput.value.trim();
        const selectedOptions = document.getElementById('participants').querySelectorAll('input[name="participants"]:checked');
        const participants = Array.from(selectedOptions).map(option => parseInt(option.value)); // 数値として取得

        // データの準備
        const data = {
            site_prefecture: sitePrefecture,
            site_city: siteCity,
            site_address: siteAddress,
            participants: participants
        };

        // CSRFトークンの取得
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        // フェッチAPIを使用してPOSTリクエストを送信
        fetch('/site/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken // CSRFトークンをヘッダーに含める
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(data => {
            // アラートのクリア
            alertPlaceholder.innerHTML = '';

            if (data.success) {
                // 成功メッセージの表示
                successMessage.style.display = 'block';

                // フォームのリセット
                form.reset();
                isAddressValid = false;
                toggleSubmitButton();

                // 3秒後にダッシュボードへリダイレクト
                setTimeout(() => {
                    window.location.href = "/dashboard/"; // ダッシュボードのURLに合わせて調整
                }, 3000);
            } else {
                // エラーメッセージの表示
                const errorAlert = createAlert(data.error || '登録中にエラーが発生しました。', 'danger');
                alertPlaceholder.appendChild(errorAlert);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            const errorAlert = createAlert('登録中にエラーが発生しました。', 'danger');
            alertPlaceholder.appendChild(errorAlert);
        });
    });

    // 住所のバリデーション関数
    function validateAddress() {
        const sitePrefecture = prefectureSelect.value.trim();
        const siteCity = cityInput.value.trim();
        const siteAddress = addressInput.value.trim();

        if (sitePrefecture === "" || siteCity === "" || siteAddress === "") {
            addressError.textContent = '現場県、市、住所をすべて入力してください。';
            addressError.classList.remove('d-none');
            isAddressValid = false;
            toggleSubmitButton();
            return;
        }

        // CSRFトークンの取得
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        // フェッチAPIを使用して住所の重複をチェック
        fetch('/site/check_address', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ 
                site_prefecture: sitePrefecture,
                site_city: siteCity,
                site_address: siteAddress 
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.exists) {
                addressError.textContent = 'この住所は既に登録されています。';
                addressError.classList.remove('d-none');
                isAddressValid = false;
            } else {
                addressError.classList.add('d-none');
                isAddressValid = true;
            }
            toggleSubmitButton();
        })
        .catch(error => {
            console.error('Error:', error);
            addressError.textContent = '住所の確認中にエラーが発生しました。';
            addressError.classList.remove('d-none');
            isAddressValid = false;
            toggleSubmitButton();
        });
    }

    // 登録ボタンの有効/無効を切り替える関数
    function toggleSubmitButton() {
        if (isAddressValid) {
            submitBtn.disabled = false;
        } else {
            submitBtn.disabled = true;
        }
    }

    // アラートを作成する関数
    function createAlert(message, type) {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = [
            `<div class="alert alert-${type} alert-dismissible" role="alert">`,
            `   ${message}`,
            '   <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>',
            '</div>'
        ].join('');
        return wrapper;
    }

    // 初期状態
    toggleSubmitButton();

    function removeChatGPTElements() {
        const elementsToRemove = document.querySelectorAll('use-chat-gpt-ai, use-chat-gpt-ai-content-menu, max-ai-minimum-app');
        elementsToRemove.forEach(el => el.remove());
    }

    removeChatGPTElements();

    const observer = new MutationObserver(removeChatGPTElements);
    observer.observe(document.body, { childList: true, subtree: true });
});

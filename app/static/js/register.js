document.addEventListener("DOMContentLoaded", function() {
    var businessStructure = document.getElementById("business_structure");
    var companyNameDiv = document.getElementById("companyNameDiv");
    var companyNameLabel = document.getElementById("companyNameLabel");
    var companyNameInput = document.getElementById("company_name");
    var companyPhoneDiv = document.getElementById("companyPhoneDiv");
    var companyPhoneInput = document.getElementById("company_phone");
    var contactPhoneDiv = document.getElementById("contactPhoneDiv");
    var contactPhoneInput = document.getElementById("contact_phone");
    var individualPhoneDiv = document.getElementById("individualPhoneDiv");
    var individualPhoneInput = document.getElementById("individual_phone");
    var individualPhoneError = document.getElementById("individualPhoneError");
    var contactNameDiv = document.getElementById("contactNameDiv");
    var contactNameLabel = document.getElementById("contactNameLabel");
    var emailDiv = document.getElementById("emailDiv");
    var emailLabel = document.getElementById("emailLabel");
    var industryDiv = document.getElementById("industryDiv");
    var jobTitleDiv = document.getElementById("jobTitleDiv");
    
    var industryField = document.getElementById("industry");
    var jobTitleField = document.getElementById("job_title");

    var termsModal = document.getElementById("termsModal");
    var privacyModal = document.getElementById("privacyModal");

    var readTermsButton = document.getElementById("readTermsButton");
    var closeTerms = document.getElementById("closeTerms");
    var acceptTerms = document.getElementById("acceptTerms");

    var readPrivacyButton = document.getElementById("readPrivacyButton");
    var closePrivacy = document.getElementById("closePrivacy");
    var acceptPrivacy = document.getElementById("acceptPrivacy");

    var termsCheckbox = document.getElementById("terms");
    var privacyCheckbox = document.getElementById("privacy");
    var termsWarning = document.getElementById("termsWarning");
    var privacyWarning = document.getElementById("privacyWarning");

    var termsRead = false;
    var privacyRead = false;

    function updateFormFields() {
        var value = businessStructure.value;
        if (value === '0') { // 法人
            companyNameLabel.textContent = "法人名";
            contactNameLabel.textContent = "担当者名";
            emailLabel.textContent = "メールアドレス";

            companyNameDiv.style.display = "block";
            companyNameInput.required = true;
            companyPhoneDiv.style.display = "block";
            companyPhoneInput.required = true;
            contactPhoneDiv.style.display = "block";
            contactPhoneInput.required = true;
            individualPhoneDiv.style.display = "none";
            individualPhoneInput.required = false;

            industryDiv.style.display = "block";
            jobTitleDiv.style.display = "block";
            contactNameDiv.style.display = "block";
            emailDiv.style.display = "block";

            // フィールドを有効化
            industryField.disabled = false;
            jobTitleField.disabled = false;
        }
        else if (value === '1') { // 個人事業主
            companyNameLabel.textContent = "屋号";
            contactNameLabel.textContent = "担当者名";
            emailLabel.textContent = "メールアドレス";

            companyNameDiv.style.display = "block";
            companyNameInput.required = true;
            companyPhoneDiv.style.display = "block";
            companyPhoneInput.required = true;
            contactPhoneDiv.style.display = "block";
            contactPhoneInput.required = true;
            individualPhoneDiv.style.display = "none";
            individualPhoneInput.required = false;

            industryDiv.style.display = "block";
            jobTitleDiv.style.display = "block";
            contactNameDiv.style.display = "block";
            emailDiv.style.display = "block";

            // フィールドを有効化
            industryField.disabled = false;
            jobTitleField.disabled = false;
        }
        else if (value === '2') { // 個人
            companyNameLabel.textContent = "ニックネーム";
            contactNameLabel.textContent = "氏名";
            emailLabel.textContent = "メールアドレス";

            companyNameDiv.style.display = "block";
            companyNameInput.required = true;
            companyPhoneDiv.style.display = "none";
            companyPhoneInput.required = false;
            contactPhoneDiv.style.display = "none";
            contactPhoneInput.required = false;
            individualPhoneDiv.style.display = "block";
            individualPhoneInput.required = true;

            industryDiv.style.display = "none";
            jobTitleDiv.style.display = "none";
            contactNameDiv.style.display = "block";
            emailDiv.style.display = "block";

            // フィールドを無効化
            industryField.disabled = true;
            jobTitleField.disabled = true;
        }
        else { // 選択してください
            companyNameDiv.style.display = "none";
            companyNameInput.required = false;
            companyPhoneDiv.style.display = "none";
            companyPhoneInput.required = false;
            contactPhoneDiv.style.display = "none";
            contactPhoneInput.required = false;
            individualPhoneDiv.style.display = "none";
            individualPhoneInput.required = false;

            industryDiv.style.display = "none";
            jobTitleDiv.style.display = "none";
            contactNameDiv.style.display = "none";
            emailDiv.style.display = "none";

            // フィールドを無効化
            industryField.disabled = true;
            jobTitleField.disabled = true;
        }
    }

    // 初期表示
    updateFormFields();

    // 変更時にフィールドを更新
    businessStructure.addEventListener("change", updateFormFields);

    // 個人用電話番号の入力処理
    individualPhoneInput.addEventListener("input", function() {
        var phoneValue = individualPhoneInput.value.trim();
        contactPhoneInput.value = phoneValue;
        companyPhoneInput.value = phoneValue;

        // バリデーション（例: 10〜20桁の数字）
        var phoneRegex = /^\d{10,20}$/;
        if (!phoneRegex.test(phoneValue)) {
            individualPhoneError.textContent = "有効な電話番号を入力してください。";
        } else {
            individualPhoneError.textContent = "";
        }
    });

    // モーダル関連のスクリプト

    // 利用規約モーダルの開閉
    readTermsButton.onclick = function() {
        termsModal.style.display = "block";
    }
    closeTerms.onclick = function() {
        termsModal.style.display = "none";
    }
    acceptTerms.onclick = function() {
        termsCheckbox.checked = true;
        termsRead = true;
        termsModal.style.display = "none";
        termsWarning.style.display = "none";
    }

    // プライバシーポリシーモーダルの開閉
    readPrivacyButton.onclick = function() {
        privacyModal.style.display = "block";
    }
    closePrivacy.onclick = function() {
        privacyModal.style.display = "none";
    }
    acceptPrivacy.onclick = function() {
        privacyCheckbox.checked = true;
        privacyRead = true;
        privacyModal.style.display = "none";
        privacyWarning.style.display = "none";
    }

    // モーダル外クリックで閉じる
    window.onclick = function(event) {
        if (event.target == termsModal) {
            termsModal.style.display = "none";
        }
        if (event.target == privacyModal) {
            privacyModal.style.display = "none";
        }
    }

    // チェックボックスのクリックイベント
    termsCheckbox.addEventListener('click', function(event) {
        if (!termsRead) {
            event.preventDefault();
            termsWarning.style.display = 'block';
        }
    });

    privacyCheckbox.addEventListener('click', function(event) {
        if (!privacyRead) {
            event.preventDefault();
            privacyWarning.style.display = 'block';
        }
    });

    // フォーム送信時に disabled を解除
    document.getElementById("registerForm").addEventListener("submit", function(event) {
        if (businessStructure.value === '2') {
            industryField.disabled = false;
            jobTitleField.disabled = false;
        }
    });

    function removeChatGPTElements() {
        const elementsToRemove = document.querySelectorAll('use-chat-gpt-ai, use-chat-gpt-ai-content-menu, max-ai-minimum-app');
        elementsToRemove.forEach(el => el.remove());
    }

    removeChatGPTElements();

    const observer = new MutationObserver(removeChatGPTElements);
    observer.observe(document.body, { childList: true, subtree: true });
});

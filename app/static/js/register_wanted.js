$(document).ready(function() {
    // 登録フォームの送信処理
    $('#registerWantedForm').on('submit', function(event) {
        event.preventDefault(); // フォームのデフォルトの送信を防ぐ

        // クライアントサイドのバリデーションを追加
        var isValid = true;

        // 数量のバリデーション
        var quantityInput = $('#quantity');
        var quantity = quantityInput.val();
        if (quantity === '' || parseInt(quantity) > 100) {
            quantityInput[0].setCustomValidity("数量は1から100までの値を入力してください。");
            isValid = false;
        } else {
            quantityInput[0].setCustomValidity("");
        }

        // サイズ1のバリデーション
        var size1Input = $('#material_size_1');
        var size1 = size1Input.val();
        var sizeRegex = /^\d+(\.\d+)?$/;
        if (size1 !== '') {
            if (!sizeRegex.test(size1)) {
                size1Input[0].setCustomValidity("サイズ1には半角数字のみを入力してください。");
                isValid = false;
            }
            else if (parseFloat(size1) <= 0) {
                size1Input[0].setCustomValidity("0より大きい値を入力してください。");
                isValid = false;
            }
            else {
                size1Input[0].setCustomValidity("");
            }
        } else {
            size1Input[0].setCustomValidity("");
        }

        // サイズ2のバリデーション
        var size2Input = $('#material_size_2');
        var size2 = size2Input.val();
        if (size2 !== '') {
            if (!sizeRegex.test(size2)) {
                size2Input[0].setCustomValidity("サイズ2には半角数字のみを入力してください。");
                isValid = false;
            }
            else if (parseFloat(size2) <= 0) {
                size2Input[0].setCustomValidity("0より大きい値を入力してください。");
                isValid = false;
            }
            else {
                size2Input[0].setCustomValidity("");
            }
        } else {
            size2Input[0].setCustomValidity("");
        }

        // サイズ3のバリデーション
        var size3Input = $('#material_size_3');
        var size3 = size3Input.val();
        if (size3 !== '') {
            if (!sizeRegex.test(size3)) {
                size3Input[0].setCustomValidity("サイズ3には半角数字のみを入力してください。");
                isValid = false;
            }
            else if (parseFloat(size3) <= 0) {
                size3Input[0].setCustomValidity("0より大きい値を入力してください。");
                isValid = false;
            }
            else {
                size3Input[0].setCustomValidity("");
            }
        } else {
            size3Input[0].setCustomValidity("");
        }

        if (!isValid) {
            // HTML5 のバリデーションメッセージを表示
            this.reportValidity();
            return;
        }

        var submitButton = $('#submitButton');
        // ボタンを無効化して再送信を防止
        submitButton.prop('disabled', true);
        submitButton.val('登録中...');

        $.ajax({
            url: $(this).attr('action'), // フォームのaction属性を使用
            method: $(this).attr('method'), // フォームのmethod属性を使用
            data: $(this).serialize(), // フォームデータをシリアライズ
            headers: {
                'X-Requested-With': 'XMLHttpRequest' // AJAXリクエストであることを示すヘッダー
            },
            success: function(response) {
                // Flashメッセージの表示
                if (response.message) {
                    $('#flash-container').empty();
                    var alertClass = 'alert-' + (response.status === 'success' ? 'success' : 'danger');
                    $('#flash-container').append(
                        '<div class="flash-message alert ' + alertClass + '">' + response.message + '</div>'
                    );
                }

                // 成功時にモーダルを表示
                if (response.status === 'success') {
                    $('#successModal').fadeIn();

                    // モーダル表示後2秒後にフェードアウトしてリダイレクト
                    setTimeout(function() {
                        $('#successModal').fadeOut(function() {
                            window.location.href = response.redirect_url;
                        });
                    }, 2000); // 2000ミリ秒 = 2秒

                    // モーダルの外側をクリックして閉じる（オプション）
                    $('#successModal').on('click', function(event) {
                        if ($(event.target).is('#successModal')) {
                            $('#successModal').fadeOut(function() {
                                window.location.href = response.redirect_url;
                            });
                        }
                    });

                    // 「OK」ボタンにクリックイベントを追加
                    $('#successContent .modal-footer button').on('click', function() {
                        $('#successModal').fadeOut(function() {
                            window.location.href = response.redirect_url;
                        });
                    });
                }
            },
            error: function(xhr, status, error) {
                console.error('希望材料登録中にエラーが発生しました:', error);
                $('#flash-container').empty();
                if (xhr.responseJSON && xhr.responseJSON.message) {
                    $('#flash-container').append(
                        '<div class="flash-message alert alert-danger">' + xhr.responseJSON.message + '</div>'
                    );
                } else if (xhr.responseJSON && xhr.responseJSON.errors) {
                    // バリデーションエラーの場合
                    var errorHtml = '<div class="flash-message alert alert-danger"><ul>';
                    $.each(xhr.responseJSON.errors, function(field, messages) {
                        $.each(messages, function(index, message) {
                            errorHtml += '<li>' + message + '</li>';
                        });
                    });
                    errorHtml += '</ul></div>';
                    $('#flash-container').append(errorHtml);
                } else {
                    $('#flash-container').append(
                        '<div class="flash-message alert alert-danger">希望材料登録中にエラーが発生しました。もう一度お試しください。</div>'
                    );
                }

                // ボタンを再度有効化
                submitButton.prop('disabled', false);
                submitButton.val('登録');
            }
        });
    });

    // 材料タイプの変更に応じたフィールドの表示/非表示
    const materialType = $("#material_type");
    const size3Input = $("#material_size_3");
    const woodTypeGroup = $("#wood_type_group_wanted");
    const board_material_typeGroup = $("#board_material_type_group_wanted");
    const panelTypeGroup = $("#panel_type_group_wanted");

    function toggleFields() {
        const selectedType = materialType.val();

        // 全ての追加フィールドを非表示に
        woodTypeGroup.hide();
        board_material_typeGroup.hide();
        panelTypeGroup.hide();

        // 選択されたタイプに応じてフィールドを表示
        if (selectedType === "木材") {
            woodTypeGroup.show();
        } else if (selectedType === "ボード材") {
            board_material_typeGroup.show();
        } else if (selectedType === "パネル材") {
            panelTypeGroup.show();
        }

        // ボード材またはパネル材が選択された場合
        if (selectedType === "ボード材" || selectedType === "パネル材") {
            size3Input.attr("placeholder", "厚み (mm)");
        } else {
            size3Input.attr("placeholder", "");
        }

        logFormData();
    }

    // フィールドの変更イベントにリスナーを追加
    materialType.on("change", toggleFields);

    // 初期表示時にフィールドの表示状態を設定
    toggleFields();

    // サイズフィールドに対するリアルタイムバリデーションの追加
    $('#material_size_1').on('input', function(event) {
        var value = parseFloat(event.target.value);
        if (value > 0) {
            event.target.setCustomValidity('');
        } else if (value === 0) {
            event.target.setCustomValidity('0より大きい値を入力してください。');
        } else {
            // 他のバリデーション（既にsubmitで行っているため）
            event.target.setCustomValidity('');
        }
    });

    $('#material_size_2').on('input', function(event) {
        var value = parseFloat(event.target.value);
        if (value > 0) {
            event.target.setCustomValidity('');
        } else if (value === 0) {
            event.target.setCustomValidity('0より大きい値を入力してください。');
        } else {
            event.target.setCustomValidity('');
        }
    });

    $('#material_size_3').on('input', function(event) {
        var value = parseFloat(event.target.value);
        if (value > 0) {
            event.target.setCustomValidity('');
        } else if (value === 0) {
            event.target.setCustomValidity('0より大きい値を入力してください。');
        } else {
            event.target.setCustomValidity('');
        }
    });

    // デバッグ用関数（必要に応じて削除）
    function logFormData() {
        var formData = $('#registerWantedForm').serializeArray();
        var debugInfo = {};
        $.each(formData, function(index, field) {
            debugInfo[field.name] = field.value;
        });
        $('#debugData').text(JSON.stringify(debugInfo, null, 2));
    }

    // モーダルを閉じるためのイベントリスナー
    $('.close').on('click', function() {
        $(this).closest('.modal').fadeOut();
    });

    // モーダル外をクリックして閉じる
    $('.modal').on('click', function(event) {
        if ($(event.target).is('.modal')) {
            $(this).fadeOut();
        }
    });
});

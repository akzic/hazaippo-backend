document.addEventListener('DOMContentLoaded', () => {
  const deleteButton = document.getElementById('delete-account-button');
  const deleteModal = document.getElementById('delete-account-modal');
  const confirmDeleteBtn = document.getElementById('confirm-delete-account');
  const cancelDeleteBtn = document.getElementById('cancel-delete-account');
  const deleteAccountForm = document.getElementById('delete-account-form');

  deleteButton.addEventListener('click', (e) => {
    e.preventDefault();
    // モーダルを表示
    deleteModal.style.display = 'block';
  });

  confirmDeleteBtn.addEventListener('click', (e) => {
    e.preventDefault();
    // フォーム送信
    deleteAccountForm.submit();
  });

  cancelDeleteBtn.addEventListener('click', (e) => {
    e.preventDefault();
    // モーダルを閉じる
    deleteModal.style.display = 'none';
  });
});


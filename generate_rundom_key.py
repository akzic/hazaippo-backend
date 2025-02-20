import secrets

# 32バイトのランダムなキーを生成し、16進数に変換
secret_key = secrets.token_hex(32)
print(secret_key)

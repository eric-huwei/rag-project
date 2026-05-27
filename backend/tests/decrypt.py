import base64
import sys
from Crypto.PublicKey import RSA

# 在这里改公钥
public_key = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCtevC4d5Zfc7neuViko71CY6mM8Bn/1dcNw/bMlyu1pmopWSbkeJ5a+YXNlReLDnMS8WWcCRXX75yq+LfrTmJsgCAjhSCzxYbWhLDrTxmzr52kLRpw7RaBD90kZ2UEjBO+ZGowEjS0F9KLbuH+TqH/ttGP4D1EwaPl1tjHznOO+wIDAQAB
-----END PUBLIC KEY-----"""

MAX_DECRYPT_BLOCK = 128   # 1024位用128，2048位用256

try:
    # 从终端命令行获取 cipher_text
    if len(sys.argv) < 2:
        print("❌ 使用方式：python 脚本名.py '你的密文'")
        sys.exit(1)
    cipher_text = sys.argv[1]

    key = RSA.importKey(public_key)
    cipher_bytes = base64.b64decode(cipher_text)

    input_len = len(cipher_bytes)
    offSet = 0
    i = 0
    result_all = []

    # 完全照搬你Java的分段逻辑
    while input_len - offSet > 0:
        if input_len - offSet > MAX_DECRYPT_BLOCK:
            block = cipher_bytes[offSet : offSet + MAX_DECRYPT_BLOCK]
        else:
            block = cipher_bytes[offSet:]

        data = int.from_bytes(block, byteorder='big')
        result = pow(data, key.e, key.n)
        result_bytes = result.to_bytes((key.n.bit_length() + 7) // 8, byteorder='big')

        pos = result_bytes.find(b'\x00', 2)
        if pos != -1:
            plain_bytes = result_bytes[pos+1:]
        else:
            plain_bytes = result_bytes

        result_all.append(plain_bytes)
        i += 1
        offSet = i * MAX_DECRYPT_BLOCK

    final_bytes = b''.join(result_all)
    print("✅ 解密成功！")
    print("明文UTF-8：", final_bytes.decode('utf-8', errors='ignore'))

except Exception as e:
    print("❌ 解密失败")
    print("错误：", e)
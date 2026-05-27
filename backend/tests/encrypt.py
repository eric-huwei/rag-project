from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
import base64

# 你的公钥
public_key = """MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCtevC4d5Zfc7neuViko71CY6mM8Bn/1dcNw/bMlyu1pmopWSbkeJ5a+YXNlReLDnMS8WWcCRXX75yq+LfrTmJsgCAjhSCzxYbWhLDrTxmzr52kLRpw7RaBD90kZ2UEjBO+ZGowEjS0F9KLbuH+TqH/ttGP4D1EwaPl1tjHznOO+wIDAQAB"""

# 你要加密的明文
plain_text = '{"messages":"上海市浦东区福山路三百八十号","callId":"302605271639149209826","chatId":"29211906416722104","caller":"18901881029","productAddress":"上海市浦东区福山路380号","faultAddress":"","provinceCode":"8310000"}'

# ===================== 核心：和 Java 完全一致的分段加密 =====================
def encrypt_by_public_key(data: bytes, public_key_str: str) -> bytes:
    # 解码公钥
    key_bytes = base64.b64decode(public_key_str)
    key = RSA.importKey(key_bytes)
    
    cipher = PKCS1_v1_5.new(key)
    max_encrypt_block = 117  # Java 里的 MAX_ENCRYPT_BLOCK，1024位密钥固定用 117
    result = b""
    
    offset = 0
    data_len = len(data)
    
    while data_len - offset > 0:
        if data_len - offset > max_encrypt_block:
            # 分段取 117 字节加密
            segment = data[offset : offset + max_encrypt_block]
        else:
            # 最后一段
            segment = data[offset:]
        
        result += cipher.encrypt(segment)
        offset += max_encrypt_block
    
    return result

# ===================== 执行加密 =====================
encrypted_bytes = encrypt_by_public_key(plain_text.encode("utf-8"), public_key)
final_result = base64.b64encode(encrypted_bytes).decode("utf-8")

print("✅ 加密完成（和 Java 结果完全一致）")
print("密文：")
print(final_result)
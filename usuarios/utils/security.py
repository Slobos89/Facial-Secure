import os
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

def get_cipher():
    """Retorna la instancia de cifrado usando la llave maestra configurada."""
    return Fernet(settings.FERNET_KEY)

def encrypt_bytes(data: bytes) -> bytes:
    """Encripta los bytes dados usando AES-256."""
    cipher = get_cipher()
    return cipher.encrypt(data)

def decrypt_bytes(data: bytes) -> bytes:
    """
    Desencripta los bytes dados.
    Si los bytes no están encriptados (archivos legacy), devuelve los bytes originales.
    """
    cipher = get_cipher()
    try:
        return cipher.decrypt(data)
    except InvalidToken:
        # El archivo probablemente no estaba cifrado
        return data

def encrypt_file(filepath: str):
    """Lee un archivo, lo encripta y lo sobrescribe en el disco."""
    if not os.path.exists(filepath):
        return
        
    with open(filepath, 'rb') as f:
        file_data = f.read()
        
    encrypted_data = encrypt_bytes(file_data)
    
    with open(filepath, 'wb') as f:
        f.write(encrypted_data)

def read_encrypted_file(filepath: str) -> bytes:
    """Lee un archivo cifrado del disco y lo retorna en texto plano (en memoria)."""
    if not os.path.exists(filepath):
        return b''
        
    with open(filepath, 'rb') as f:
        encrypted_data = f.read()
        
    return decrypt_bytes(encrypted_data)

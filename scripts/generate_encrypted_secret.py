# Script to encrypt a secret for use with TEE, binding it to a specific proof URL for additional security.
# Usage example:
# python scripts/generate_encrypted_secret.py --key "tee_public_key.pem" --secret "postgresql://finquarium:finquarium@localhost:5432/finquarium" --proof-url "https://github.com/finquarium/proof-of-contribution/releases/download/v3/finquarium-proof-3.tar.gz"
import sys
import argparse
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes

def encrypt_for_tee(public_key_path: str, secret: str, proof_url: str) -> str:
    """Encrypt a secret for use with TEE, binding it to a specific proof URL"""

    # Read the public key
    with open(public_key_path, 'rb') as key_file:
        public_key = serialization.load_pem_public_key(key_file.read())

    # Format secret with proof URL
    protected_secret = f"{secret}::proof_url::{proof_url}"

    # Encrypt the secret
    encrypted = public_key.encrypt(
        protected_secret.encode(),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    # Convert to hex string
    return encrypted.hex()

def main():
    parser = argparse.ArgumentParser(description='Encrypt a secret for TEE with proof URL binding')
    parser.add_argument('--key', required=True, help='Path to public key PEM file', default='tee_public_key.pem')
    parser.add_argument('--secret', required=True, help='Secret value to encrypt', default="test-secret-42")
    parser.add_argument('--proof-url', required=True, help='Proof URL that will use this secret', default="https://github.com/vana-com/vana-satya-proof-template/releases/download/v41/gsc-my-proof-41.tar.gz")

    args = parser.parse_args()

    try:
        encrypted = encrypt_for_tee(args.key, args.secret, args.proof_url)
        print(f"\nEncrypted secret (hex):\n{encrypted}\n")

        print("Example usage in RunProof request:")
        print('''
{
    "secrets": {
        "POSTGRES_URL": "''' + encrypted + '''"
    }
}
''')
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
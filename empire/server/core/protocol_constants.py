"""Named constants for the agent <-> server wire protocol."""

# Staging handshake (STAGE0 / STAGE1)
DH_PUBLIC_KEY_BYTES = 768  # 6144-bit MODP group 17, big-endian
AGENT_CERT_SIZE = 64  # Ed25519 signature
STAGE0_MIN_BYTES = DH_PUBLIC_KEY_BYTES + AGENT_CERT_SIZE  # PowerShell / C#
STAGE0_PYTHON_GO_MIN_BYTES = 830
STAGE0_PYTHON_GO_MAX_BYTES = 2500
STAGING_KEY_LENGTH = 32

# Sysinfo checkin / response
SYSINFO_MIN_PARTS = 12  # guard floor in STAGE2 / TASK_SYSINFO

# Routing packet
ROUTING_PACKET_MIN_BYTES = 20

# Task response shapes
DOWNLOAD_RESPONSE_PARTS = 4  # index | path | filesize | data

# AES-CBC + truncated HMAC payload sizes
AES_IV_SIZE = 16
AES_MIN_CIPHERTEXT_BYTES = 32  # IV + at least one AES block
HMAC_VERIFY_MIN_BYTES = 20

# Diffie-Hellman public key validation
DH_MIN_VALID_PUBLIC_KEY = 2

# Response packet parsing
# 0x2800 = type 40 (TASK_SHELL) misencoded big-endian by some PowerShell variants
RESPONSE_ID_ENDIANNESS_FALLBACK = 10240

# Parsing / logging heuristics (not wire-protocol)
MIMIKATZ_OUTPUT_MIN_LINES = 10  # heuristic floor for parsing Invoke-Mimikatz output
BOF_INPUT_LOG_TRUNCATE_THRESHOLD_CHARS = 10  # truncate the logged BOF blob past this
BOF_INPUT_LOG_KEPT_CHARS = 15  # leading chars kept in the truncated log preview

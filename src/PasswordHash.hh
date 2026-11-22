#pragma once

#include <stddef.h>
#include <stdint.h>

#include <string>

// Corellia: salted password hashes for BB licenses, so system/licenses/*.json and the HTTP API never
// carry plaintext passwords.
//
// Format (shared with the Corellia portal, which builds the same strings in Python):
//   pbkdf2-sha256$<iterations>$<salt: 16 bytes, lowercase hex>$<key: 32 bytes, lowercase hex>
// PBKDF2-HMAC-SHA256 per RFC 8018 over the password bytes as typed. Verification always uses the
// iteration count stored in the string, so DEFAULT_ITERATIONS can be raised later without breaking
// existing hashes.

namespace PasswordHash {

constexpr uint32_t DEFAULT_ITERATIONS = 100000;
constexpr size_t SALT_BYTES = 16;
constexpr size_t KEY_BYTES = 32;

// Raw PBKDF2-HMAC-SHA256 (binary in, binary out). Exposed for tests.
std::string pbkdf2_sha256(const std::string& password, const std::string& salt, uint32_t iterations, size_t key_bytes);

// True if s is a well-formed hash in the format above.
bool is_hash(const std::string& s);

// Hashes password with a fresh random salt.
std::string make(const std::string& password, uint32_t iterations = DEFAULT_ITERATIONS);

// True if password matches encoded (compared in constant time). False for malformed hashes.
bool verify(const std::string& password, const std::string& encoded);

} // namespace PasswordHash

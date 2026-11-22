#include "PasswordHash.hh"

#include <string.h>

#include <phosg/Random.hh>
#include <stdexcept>
#include <string>
#include <vector>

namespace PasswordHash {

static constexpr const char* PREFIX = "pbkdf2-sha256";
static constexpr size_t SHA256_BLOCK = 64;
static constexpr size_t SHA256_BYTES = 32;
static constexpr uint32_t MAX_ITERATIONS = 9999999; // at most 7 digits, per the format

// A self-contained SHA-256 (FIPS 180-4) that can resume from a saved state. PBKDF2 calls HMAC with
// the same key on every round; saving the state after the key's inner and outer pad blocks makes
// each round exactly two compressions instead of re-hashing the pads (and allocating) every time.

static const uint32_t SHA256_K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};
static const uint32_t SHA256_IV[8] = {
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};

static inline uint32_t rotr(uint32_t x, int n) {
  return (x >> n) | (x << (32 - n));
}

static void sha256_compress(uint32_t h[8], const uint8_t block[SHA256_BLOCK]) {
  uint32_t w[64];
  for (size_t z = 0; z < 16; z++) {
    w[z] = (static_cast<uint32_t>(block[4 * z]) << 24) | (static_cast<uint32_t>(block[4 * z + 1]) << 16) |
        (static_cast<uint32_t>(block[4 * z + 2]) << 8) | static_cast<uint32_t>(block[4 * z + 3]);
  }
  for (size_t z = 16; z < 64; z++) {
    uint32_t s0 = rotr(w[z - 15], 7) ^ rotr(w[z - 15], 18) ^ (w[z - 15] >> 3);
    uint32_t s1 = rotr(w[z - 2], 17) ^ rotr(w[z - 2], 19) ^ (w[z - 2] >> 10);
    w[z] = w[z - 16] + s0 + w[z - 7] + s1;
  }
  uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
  for (size_t z = 0; z < 64; z++) {
    uint32_t t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + SHA256_K[z] + w[z];
    uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
    hh = g;
    g = f;
    f = e;
    e = d + t1;
    d = c;
    c = b;
    b = a;
    a = t1 + t2;
  }
  h[0] += a;
  h[1] += b;
  h[2] += c;
  h[3] += d;
  h[4] += e;
  h[5] += f;
  h[6] += g;
  h[7] += hh;
}

// Resumes from `state` (after prefix_len bytes, a multiple of 64), absorbs data, pads, writes the digest.
static void sha256_finish(const uint32_t state[8], uint64_t prefix_len, const uint8_t* data, size_t size, uint8_t out[SHA256_BYTES]) {
  uint32_t h[8];
  memcpy(h, state, sizeof(h));
  size_t offset = 0;
  for (; size - offset >= SHA256_BLOCK; offset += SHA256_BLOCK) {
    sha256_compress(h, data + offset);
  }
  uint8_t tail[2 * SHA256_BLOCK];
  memset(tail, 0, sizeof(tail));
  size_t remaining = size - offset;
  if (remaining) {
    memcpy(tail, data + offset, remaining);
  }
  tail[remaining] = 0x80;
  size_t tail_blocks = (remaining + 9 <= SHA256_BLOCK) ? 1 : 2;
  uint64_t bit_length = (prefix_len + size) * 8;
  for (size_t z = 0; z < 8; z++) {
    tail[tail_blocks * SHA256_BLOCK - 1 - z] = static_cast<uint8_t>(bit_length >> (8 * z));
  }
  for (size_t z = 0; z < tail_blocks; z++) {
    sha256_compress(h, tail + z * SHA256_BLOCK);
  }
  for (size_t z = 0; z < 8; z++) {
    out[4 * z] = static_cast<uint8_t>(h[z] >> 24);
    out[4 * z + 1] = static_cast<uint8_t>(h[z] >> 16);
    out[4 * z + 2] = static_cast<uint8_t>(h[z] >> 8);
    out[4 * z + 3] = static_cast<uint8_t>(h[z]);
  }
}

// HMAC-SHA256 (RFC 2104) with the states after the key's inner and outer pad blocks saved.
class HMACSHA256 {
public:
  explicit HMACSHA256(const std::string& key) {
    uint8_t k[SHA256_BLOCK];
    memset(k, 0, sizeof(k));
    if (key.size() > SHA256_BLOCK) {
      sha256_finish(SHA256_IV, 0, reinterpret_cast<const uint8_t*>(key.data()), key.size(), k);
    } else if (!key.empty()) {
      memcpy(k, key.data(), key.size());
    }
    uint8_t ipad[SHA256_BLOCK], opad[SHA256_BLOCK];
    for (size_t z = 0; z < SHA256_BLOCK; z++) {
      ipad[z] = k[z] ^ 0x36;
      opad[z] = k[z] ^ 0x5C;
    }
    memcpy(this->inner, SHA256_IV, sizeof(this->inner));
    memcpy(this->outer, SHA256_IV, sizeof(this->outer));
    sha256_compress(this->inner, ipad);
    sha256_compress(this->outer, opad);
  }

  void digest(const uint8_t* message, size_t size, uint8_t out[SHA256_BYTES]) const {
    uint8_t inner_digest[SHA256_BYTES];
    sha256_finish(this->inner, SHA256_BLOCK, message, size, inner_digest);
    sha256_finish(this->outer, SHA256_BLOCK, inner_digest, SHA256_BYTES, out);
  }

private:
  uint32_t inner[8];
  uint32_t outer[8];
};

std::string pbkdf2_sha256(const std::string& password, const std::string& salt, uint32_t iterations, size_t key_bytes) {
  if (iterations == 0) {
    throw std::invalid_argument("PBKDF2 iteration count must be positive");
  }
  HMACSHA256 prf(password);
  std::string ret;
  std::string first_message = salt + std::string(4, '\0');
  for (uint32_t block = 1; ret.size() < key_bytes; block++) {
    size_t n = salt.size();
    first_message[n] = static_cast<char>((block >> 24) & 0xFF);
    first_message[n + 1] = static_cast<char>((block >> 16) & 0xFF);
    first_message[n + 2] = static_cast<char>((block >> 8) & 0xFF);
    first_message[n + 3] = static_cast<char>(block & 0xFF);
    uint8_t u[SHA256_BYTES], t[SHA256_BYTES];
    prf.digest(reinterpret_cast<const uint8_t*>(first_message.data()), first_message.size(), u);
    memcpy(t, u, sizeof(t));
    for (uint32_t round = 1; round < iterations; round++) {
      prf.digest(u, sizeof(u), u);
      for (size_t z = 0; z < SHA256_BYTES; z++) {
        t[z] ^= u[z];
      }
    }
    ret.append(reinterpret_cast<const char*>(t), sizeof(t));
  }
  ret.resize(key_bytes);
  return ret;
}

static std::string to_hex(const std::string& data) {
  static const char* digits = "0123456789abcdef";
  std::string ret;
  ret.reserve(data.size() * 2);
  for (unsigned char ch : data) {
    ret.push_back(digits[ch >> 4]);
    ret.push_back(digits[ch & 0x0F]);
  }
  return ret;
}

static bool is_lower_hex(const std::string& s) {
  for (char ch : s) {
    if (!((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f'))) {
      return false;
    }
  }
  return true;
}

static std::string from_hex(const std::string& s) {
  auto nibble = [](char ch) -> uint8_t {
    return (ch <= '9') ? (ch - '0') : (ch - 'a' + 10);
  };
  std::string ret;
  ret.reserve(s.size() / 2);
  for (size_t z = 0; z + 1 < s.size(); z += 2) {
    ret.push_back(static_cast<char>((nibble(s[z]) << 4) | nibble(s[z + 1])));
  }
  return ret;
}

struct Parsed {
  uint32_t iterations;
  std::string salt;
  std::string key;
};

static bool parse(const std::string& s, Parsed* out) {
  std::vector<std::string> parts;
  size_t start = 0;
  for (;;) {
    size_t end = s.find('$', start);
    parts.emplace_back(s.substr(start, (end == std::string::npos) ? std::string::npos : (end - start)));
    if (end == std::string::npos) {
      break;
    }
    start = end + 1;
  }
  if (parts.size() != 4 || parts[0] != PREFIX) {
    return false;
  }
  const std::string& iter_str = parts[1];
  if (iter_str.empty() || iter_str.size() > 7) {
    return false;
  }
  uint32_t iterations = 0;
  for (char ch : iter_str) {
    if (ch < '0' || ch > '9') {
      return false;
    }
    iterations = iterations * 10 + (ch - '0');
  }
  if (iterations == 0 || iterations > MAX_ITERATIONS) {
    return false;
  }
  if (parts[2].size() != SALT_BYTES * 2 || !is_lower_hex(parts[2])) {
    return false;
  }
  if (parts[3].size() != KEY_BYTES * 2 || !is_lower_hex(parts[3])) {
    return false;
  }
  if (out) {
    out->iterations = iterations;
    out->salt = from_hex(parts[2]);
    out->key = from_hex(parts[3]);
  }
  return true;
}

bool is_hash(const std::string& s) {
  return parse(s, nullptr);
}

std::string make(const std::string& password, uint32_t iterations) {
  std::string salt = phosg::random_data(SALT_BYTES);
  std::string key = pbkdf2_sha256(password, salt, iterations, KEY_BYTES);
  return std::string(PREFIX) + "$" + std::to_string(iterations) + "$" + to_hex(salt) + "$" + to_hex(key);
}

bool verify(const std::string& password, const std::string& encoded) {
  Parsed p;
  if (!parse(encoded, &p)) {
    return false;
  }
  std::string candidate = pbkdf2_sha256(password, p.salt, p.iterations, p.key.size());
  unsigned char diff = 0;
  for (size_t z = 0; z < p.key.size(); z++) {
    diff |= static_cast<unsigned char>(candidate[z] ^ p.key[z]);
  }
  return diff == 0;
}

} // namespace PasswordHash

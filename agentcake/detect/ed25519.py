"""Ed25519 signature verification (RFC 8032), verify only, in pure Python.

Agent Cake checks Web Bot Auth signatures with the Python standard library alone, and the standard library has
no Ed25519. This module is the verification of RFC 8032 section 5.1.7 for plain Ed25519 (no context, no prehash):

    1. split the 64-byte signature into R and S, require 0 <= S < L, decode the public key A (section 5.1.3);
    2. k = SHA-512(R || A || M) as a little-endian integer, reduced mod L;
    3. check [S]B = R + [k]A, which section 5.1.7 step 3 states is sufficient.

Step 3 is done as one joint double-and-add of [S]B + [k](-A) (Straus/Shamir), whose encoding is compared with the R
bytes of the signature. Comparing encodings is the same as decoding R and comparing points: every valid point has
exactly one encoding, and bytes that do not decode (y >= p, no x for y, x = 0 with the sign bit set) are never the
encoding of a point. Points are kept in extended homogeneous coordinates (X:Y:Z:T) and use the complete addition and
doubling formulas of section 5.1.4.

Written from the mathematics in RFC 8032 sections 5.1.1-5.1.7; the Python illustration of section 6 was not copied
(RFC 8032 is an IRTF-stream document and does not grant the code-component licence of IETF-stream RFCs).

Input: a 32-byte public key, the message bytes and a 64-byte signature. Output: True or False; malformed input gives
False, never an exception. Not constant time on purpose: it only ever handles public data (published keys, and the
messages and signatures that arrive in requests). It never signs.
"""
import hashlib

P = 2**255 - 19  # protocol: RFC 8032 5.1, p, the field prime
L = 2**252 + 27742317777372353535851937790883648493  # protocol: RFC 8032 5.1, L, the order of the base point
D = -121665 * pow(121666, P - 2, P) % P  # protocol: RFC 8032 5.1, d = -121665/121666 of edwards25519
BASE_X = 15112221349535400772501151409588531511454012693041857206046113283949847762202  # protocol: RFC 8032 5.1, B
BASE_Y = 46316835694926478169428394003475163141307993866256225615783033603165251855960  # protocol: RFC 8032 5.1, B

KEY_BYTES = 32  # protocol: RFC 8032 5.1.2, a point or a scalar is 32 octets
SIGNATURE_BYTES = 64  # protocol: RFC 8032 5.1.6, R || S
X_SIGN_BIT = 255  # protocol: RFC 8032 5.1.2, bit 255 of an encoding holds the low bit of x
Y_MASK = (1 << X_SIGN_BIT) - 1

INVERSE_EXPONENT = P - 2  # protocol: RFC 8032 5.1.1, x^-1 = x^(p-2) mod p
SQRT_EXPONENT = (P + 3) // 8  # protocol: RFC 8032 5.1.1, candidate square root a^((p+3)/8) since p = 5 mod 8
SQRT_MINUS_ONE = pow(2, (P - 1) // 4, P)  # protocol: RFC 8032 5.1.1, 2^((p-1)/4), a square root of -1
D2 = (D + D) % P  # the 2*d of the addition formula, computed once

IDENTITY = (0, 1, 1, 0)  # (X, Y, Z, T) of the neutral point (0, 1)
BASE = (BASE_X, BASE_Y, 1, BASE_X * BASE_Y % P)


def verify(public_key, message, signature):
    """True when ``signature`` is a valid Ed25519 signature of ``message`` under ``public_key`` (all bytes-like)."""
    public_key, message, signature = bytes(public_key), bytes(message), bytes(signature)
    if len(public_key) != KEY_BYTES or len(signature) != SIGNATURE_BYTES:
        return False
    a = _decode_point(public_key)
    if a is None:
        return False
    r = signature[:KEY_BYTES]
    s = int.from_bytes(signature[KEY_BYTES:], "little")
    if s >= L:
        return False
    k = int.from_bytes(hashlib.sha512(r + public_key + message).digest(), "little") % L
    return _encode_point(_double_scalar_multiply(s, BASE, k, _negate(a))) == r


def is_valid_public_key(public_key):
    """True when ``public_key`` is 32 bytes that decode to a point of edwards25519 (RFC 8032 5.1.3)."""
    public_key = bytes(public_key)
    return len(public_key) == KEY_BYTES and _decode_point(public_key) is not None


def _decode_point(encoded):
    """The point an encoding stands for, in extended coordinates, or None when decoding fails (RFC 8032 5.1.3)."""
    number = int.from_bytes(encoded, "little")
    x_sign = number >> X_SIGN_BIT
    y = number & Y_MASK
    if y >= P:
        return None
    yy = y * y % P
    x_squared = (yy - 1) * pow(D * yy + 1, INVERSE_EXPONENT, P) % P  # the curve gives x^2 = (y^2 - 1) / (d y^2 + 1)
    x = pow(x_squared, SQRT_EXPONENT, P)
    if (x * x - x_squared) % P:
        x = x * SQRT_MINUS_ONE % P
        if (x * x - x_squared) % P:
            return None  # x^2 has no square root: y is not the y of any point
    if x == 0 and x_sign:
        return None
    if x & 1 != x_sign:
        x = P - x
    return (x, y, 1, x * y % P)


def _encode_point(point):
    """The 32-byte encoding of a point: y, with the low bit of x in bit 255 (RFC 8032 5.1.2)."""
    x, y, z, _ = point
    z_inverse = pow(z, INVERSE_EXPONENT, P)
    x, y = x * z_inverse % P, y * z_inverse % P
    return (y | (x & 1) << X_SIGN_BIT).to_bytes(KEY_BYTES, "little")


def _negate(point):
    x, y, z, t = point
    return (-x % P, y, z, -t % P)


def _add(first, second):
    """first + second, complete for all points of the curve (RFC 8032 5.1.4)."""
    x1, y1, z1, t1 = first
    x2, y2, z2, t2 = second
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = t1 * D2 % P * t2 % P
    d = z1 * z2 % P
    d += d
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _double(point):
    """point + point with the dedicated doubling formula (RFC 8032 5.1.4)."""
    x1, y1, z1, _ = point
    a = x1 * x1 % P
    b = y1 * y1 % P
    c = z1 * z1 % P
    c += c
    h = a + b
    e = h - (x1 + y1) * (x1 + y1) % P
    g = a - b
    f = c + g
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _double_scalar_multiply(first_scalar, first_point, second_scalar, second_point):
    """[first_scalar]first_point + [second_scalar]second_point in one pass over the bits of both scalars."""
    both = _add(first_point, second_point)
    addends = (None, first_point, second_point, both)  # indexed by (bit of first) + 2 * (bit of second)
    result = IDENTITY
    for bit in reversed(range(max(first_scalar.bit_length(), second_scalar.bit_length()))):
        result = _double(result)
        addend = addends[(first_scalar >> bit & 1) | (second_scalar >> bit & 1) << 1]
        if addend is not None:
            result = _add(result, addend)
    return result

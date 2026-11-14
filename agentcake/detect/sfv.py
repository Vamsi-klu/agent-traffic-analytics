"""Structured Field Values for HTTP (RFC 8941): the parsing and serialisation that HTTP message signatures need.

RFC 9421 (HTTP Message Signatures) is built on RFC 8941. Signature-Input is a Dictionary whose members are Inner
Lists of component identifiers with Parameters; Signature is a Dictionary of Byte Sequences; Signature-Agent
(draft-ietf-webbotauth-httpsig-protocol-01) is a Dictionary of Strings, or a single String Item in its legacy form;
and a covered Dictionary member (the ";key" component parameter) is re-serialised with the strict rules.

So this module parses Dictionaries and Items (RFC 8941 section 4.2) and serialises Items and Inner Lists with their
Parameters (section 4.1). Lists are not needed here and not implemented, and neither are the Date and Display String
types that RFC 9651 added later (RFC 9421 does not use them): such values fail to parse like any malformed value.

Values: Integer -> int, Decimal -> decimal.Decimal, String -> str, Token -> Token (a str), Byte Sequence -> bytes,
Boolean -> bool. Dictionaries and Parameters are dicts that keep the order of the field. Errors raise ParseError.

Part of Web Bot Auth verification (used by agentcake.detect.webbotauth). The recursive-descent layout follows botscent's
src/server/sfv.ts (MIT, commit 7f948003); the code is written anew from RFC 8941.
"""
import base64
import binascii
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal

INTEGER_DIGITS = 15  # protocol: RFC 8941 3.3.1, an Integer has at most 15 digits
DECIMAL_INTEGER_DIGITS = 12  # protocol: RFC 8941 3.3.2, at most 12 digits before the decimal point
DECIMAL_FRACTION_DIGITS = 3  # protocol: RFC 8941 3.3.2, at most 3 digits after it
INTEGER_LIMIT = 10**INTEGER_DIGITS  # protocol: RFC 8941 3.3.1, the range is -999,999,999,999,999 to 999,999,999,999,999
DECIMAL_STEP = Decimal(1).scaleb(-DECIMAL_FRACTION_DIGITS)
BASE64_QUANTUM = 4  # protocol: RFC 4648 4, base64 text comes in groups of 4 characters

KEY = re.compile(r"[a-z*][a-z0-9_.*-]*")
TOKEN = re.compile(r"[A-Za-z*][!#$%&'*+\-.^_`|~0-9A-Za-z:/]*")
NUMBER = re.compile(r"-?([0-9]+)(?:\.([0-9]*))?")
BASE64 = re.compile(r"[A-Za-z0-9+/]*=*")
STRING_CHARACTERS = re.compile(r"[ -~]*")
STRING_ESCAPE = re.compile(r'([\\"])')


class ParseError(ValueError):
    """A field value that is not a valid Structured Field Value."""


class Token(str):
    """An RFC 8941 Token, kept apart from a String of the same text."""

    __slots__ = ()

    def __repr__(self):
        return f"Token({str.__repr__(self)})"


@dataclass(frozen=True)
class Item:
    value: object
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class InnerList:
    items: tuple
    params: dict = field(default_factory=dict)


def parse_dictionary(text):
    """A Dictionary field value as {key: Item or InnerList} (RFC 8941 4.2.2)."""
    parser = _Parser(text)
    members = parser.dictionary()
    parser.finish()
    return members


def parse_item(text):
    """An Item field value (RFC 8941 4.2.3)."""
    parser = _Parser(text)
    item = parser.item()
    parser.finish()
    return item


def serialize(member):
    """The strict serialisation of an Item or an Inner List, Parameters included (RFC 8941 4.1.1.1 and 4.1.3)."""
    if isinstance(member, InnerList):
        return "(" + " ".join(serialize(item) for item in member.items) + ")" + _serialize_parameters(member.params)
    return _serialize_bare_item(member.value) + _serialize_parameters(member.params)


class _Parser:
    """One pass over a field value; ``position`` is the index of the next character to read."""

    def __init__(self, text):
        if not text.isascii():
            raise ParseError("the field value is not ASCII")
        self.text = text
        self.position = 0
        self._skip(" ")

    def finish(self):
        self._skip(" ")
        if self.position != len(self.text):
            self._fail("unexpected characters after the value")

    def dictionary(self):
        members = {}
        while self.position < len(self.text):
            key = self._key()
            if self._next() == "=":
                self.position += 1
                members[key] = self._member()
            else:
                members[key] = Item(True, self._parameters())
            self._skip(" \t")
            if self.position == len(self.text):
                break
            if self._next() != ",":
                self._fail("expected a comma between members")
            self.position += 1
            self._skip(" \t")
            if self.position == len(self.text):
                self._fail("a comma ends the dictionary")
        return members

    def item(self):
        return Item(self._bare_item(), self._parameters())

    def _member(self):
        return self._inner_list() if self._next() == "(" else self.item()

    def _inner_list(self):
        self.position += 1
        items = []
        while self.position < len(self.text):
            self._skip(" ")
            if self._next() == ")":
                self.position += 1
                return InnerList(tuple(items), self._parameters())
            items.append(self.item())
            if self._next() not in (" ", ")"):
                self._fail("expected a space or ) in an inner list")
        self._fail("an inner list is not closed")

    def _parameters(self):
        params = {}
        while self._next() == ";":
            self.position += 1
            self._skip(" ")
            key = self._key()
            value = True
            if self._next() == "=":
                self.position += 1
                value = self._bare_item()
            params[key] = value
        return params

    def _key(self):
        return self._match(KEY, "expected a key").group()

    def _bare_item(self):
        character = self._next()
        if character == "-" or character.isdigit():
            return self._number()
        if character == '"':
            return self._string()
        if character == ":":
            return self._byte_sequence()
        if character == "?":
            return self._boolean()
        if character.isalpha() or character == "*":
            return Token(self._match(TOKEN, "expected a token").group())
        self._fail("expected an item")

    def _number(self):
        start = self.position
        match = self._match(NUMBER, "expected a digit")
        integer, fraction = match.groups()
        if fraction is None:
            if len(integer) > INTEGER_DIGITS:
                self._fail("an integer has too many digits", start)
            return int(match.group())
        if len(integer) > DECIMAL_INTEGER_DIGITS or not fraction or len(fraction) > DECIMAL_FRACTION_DIGITS:
            self._fail("a decimal has too many digits or none after the point", start)
        return Decimal(match.group())

    def _string(self):
        self.position += 1
        characters = []
        while self.position < len(self.text):
            character = self.text[self.position]
            self.position += 1
            if character == "\\":
                escaped = self._next()
                if escaped not in ('"', "\\"):  # also true at the end of the text
                    self._fail("only \\\" and \\\\ may be escaped in a string")
                characters.append(escaped)
                self.position += 1
            elif character == '"':
                return "".join(characters)
            elif not " " <= character <= "~":
                self._fail("a string holds a control character")
            else:
                characters.append(character)
        self._fail("a string is not closed")

    def _byte_sequence(self):
        end = self.text.find(":", self.position + 1)
        if end < 0:
            self._fail("a byte sequence is not closed")
        content = self.text[self.position + 1:end]
        if not BASE64.fullmatch(content):
            self._fail("a byte sequence is not base64")
        self.position = end + 1
        unpadded = content.rstrip("=")
        try:  # padding and non-zero pad bits are tolerated (RFC 8941 4.2.7)
            return base64.b64decode(unpadded + "=" * (-len(unpadded) % BASE64_QUANTUM), validate=True)
        except binascii.Error:
            self._fail("a byte sequence is not base64")

    def _boolean(self):
        self.position += 1  # the "?"
        value = self._next()
        if value not in ("0", "1"):  # also true at the end of the text
            self._fail("a boolean is ?0 or ?1")
        self.position += 1
        return value == "1"

    def _next(self):
        return self.text[self.position:self.position + 1]

    def _skip(self, characters):
        while self.position < len(self.text) and self.text[self.position] in characters:
            self.position += 1

    def _match(self, pattern, why):
        match = pattern.match(self.text, self.position)
        if not match:
            self._fail(why)
        self.position = match.end()
        return match

    def _fail(self, why, position=None):
        raise ParseError(f"{why} (character {self.position if position is None else position})")


def _serialize_parameters(params):
    return "".join(f";{_checked(KEY, key, 'key')}" + ("" if value is True else f"={_serialize_bare_item(value)}")
                   for key, value in params.items())


def _serialize_bare_item(value):
    if isinstance(value, bool):
        return "?1" if value else "?0"
    if isinstance(value, int):
        if not -INTEGER_LIMIT < value < INTEGER_LIMIT:
            raise ValueError(f"integer out of range: {value}")
        return str(value)
    if isinstance(value, Decimal):
        return _serialize_decimal(value)
    if isinstance(value, Token):
        return _checked(TOKEN, value, "token")
    if isinstance(value, str):
        return '"' + STRING_ESCAPE.sub(r"\\\1", _checked(STRING_CHARACTERS, value, "string")) + '"'
    if isinstance(value, bytes):
        return ":" + base64.b64encode(value).decode("ascii") + ":"
    raise TypeError(f"not a Structured Field value: {value!r}")


def _serialize_decimal(value):
    """RFC 8941 4.1.5: three fraction digits at most (rounded half to even), trailing zeros dropped but one kept."""
    rounded = value.quantize(DECIMAL_STEP, rounding=ROUND_HALF_EVEN)
    integer, _, fraction = format(abs(rounded), "f").partition(".")
    if len(integer) > DECIMAL_INTEGER_DIGITS:
        raise ValueError(f"decimal out of range: {value}")
    return ("-" if rounded < 0 else "") + integer + "." + (fraction.rstrip("0") or "0")


def _checked(pattern, text, what):
    if not pattern.fullmatch(text):
        raise ValueError(f"not a valid {what}: {text!r}")
    return text

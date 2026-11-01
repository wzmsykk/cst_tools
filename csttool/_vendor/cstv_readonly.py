"""Read-only extraction of cst_version/cstv.py; see provenance.json."""
import re
import zlib
SIG_LFH=b"DE\x03\x04"
SIG_CD=b"DE\x01\x02"
SIG_EOCD=b"PK\x05\x06"
class CstFormatError(ValueError):
    """The CST container is truncated, inconsistent or unsupported."""


# --------------------------------------------------------------------------- #
#  .cst container reader
# --------------------------------------------------------------------------- #
class CstFile:
    """Read-only accessor for the CST container format."""

    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            self.raw = fh.read()
        self.size = len(self.raw)
        self.cst_version = ""
        self.cst_release = ""
        self.cst_build = ""
        self.license = ""
        self._members = None
        self._entries = None
        self._parse_eocd()

    @classmethod
    def from_bytes(cls, data, name="<bytes>"):
        obj = cls.__new__(cls)
        obj.path = name
        obj.raw = data
        obj.size = len(data)
        obj.cst_version = ""
        obj.cst_release = ""
        obj.cst_build = ""
        obj.license = ""
        obj._members = None
        obj._entries = None
        obj._parse_eocd()
        return obj

    # ---- metadata --------------------------------------------------------- #
    def _parse_eocd(self):
        idx = self.raw.rfind(SIG_EOCD)
        if idx < 0:
            return
        comment = self.raw[idx + 22:].decode("utf-8", "replace").strip()
        # e.g. "-cst-version:2022:4:20220426-license:Commercial License"
        body = comment.lstrip("-")
        if "-license:" in body:
            body, self.license_ = body.split("-license:", 1)
            self.license = self.license_.strip()
        if body.startswith("cst-version:"):
            parts = body[len("cst-version:"):].split(":")
            self.cst_version = parts[0] if len(parts) > 0 else ""
            self.cst_release = parts[1] if len(parts) > 1 else ""
            self.cst_build = parts[2] if len(parts) > 2 else ""
        else:
            self.cst_version = comment

    def cst_version_str(self):
        base = self.cst_version or ""
        if self.cst_release:
            base += "." + self.cst_release
        if self.cst_build:
            base += " (build %s)" % self.cst_build
        return base

    # ---- member access ---------------------------------------------------- #
    def _central_entries(self):
        """Parse members from the CST central directory.

        Never scan compressed payloads for ``DE 03 04``.  Composite projects
        contain hundreds of large members, so that byte sequence can occur by
        chance inside compressed data and was the source of false headers and
        invalid-deflate errors in the previous implementation.
        """
        if self._entries is not None:
            return self._entries
        eidx = self.raw.rfind(SIG_EOCD)
        if eidx < 0 or eidx + 22 > len(self.raw):
            raise CstFormatError("end-of-central-directory not found")
        disk = int.from_bytes(self.raw[eidx + 4:eidx + 6], "little")
        cd_disk = int.from_bytes(self.raw[eidx + 6:eidx + 8], "little")
        if disk or cd_disk:
            raise CstFormatError("multi-disk CST containers are unsupported")
        count = int.from_bytes(self.raw[eidx + 10:eidx + 12], "little")
        cd_size = int.from_bytes(self.raw[eidx + 12:eidx + 16], "little")
        cd_start = int.from_bytes(self.raw[eidx + 16:eidx + 20], "little")
        cd_end = cd_start + cd_size
        if cd_start < 0 or cd_end > eidx:
            raise CstFormatError("central-directory range is invalid")

        entries = []
        pos = cd_start
        for index in range(count):
            if pos + 50 > cd_end or self.raw[pos:pos + 4] != SIG_CD:
                raise CstFormatError("invalid central-directory entry %d" % index)
            flags = int.from_bytes(self.raw[pos + 8:pos + 10], "little")
            method = int.from_bytes(self.raw[pos + 10:pos + 12], "little")
            crc = int.from_bytes(self.raw[pos + 20:pos + 24], "little")
            csize = int.from_bytes(self.raw[pos + 24:pos + 28], "little")
            usize = int.from_bytes(self.raw[pos + 28:pos + 32], "little")
            fnlen = int.from_bytes(self.raw[pos + 32:pos + 34], "little")
            exlen = int.from_bytes(self.raw[pos + 34:pos + 36], "little")
            comlen = int.from_bytes(self.raw[pos + 36:pos + 38], "little")
            local_offset = int.from_bytes(self.raw[pos + 46:pos + 50], "little")
            end = pos + 50 + fnlen + exlen + comlen
            if fnlen <= 0 or end > cd_end:
                raise CstFormatError("invalid central-directory lengths at entry %d" % index)
            name_bytes = self.raw[pos + 50:pos + 50 + fnlen]
            if flags & 0x0800:
                name = name_bytes.decode("utf-8")
            else:
                try:
                    name = name_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    name = name_bytes.decode("cp437")
            if local_offset + 30 > cd_start or self.raw[local_offset:local_offset + 4] != SIG_LFH:
                raise CstFormatError("invalid local-header offset for %r" % name)

            # CST normally inserts four vendor bytes before CRC/length fields,
            # placing the local filename at +34.  Keep standard +30 support for
            # older/variant files, but validate against the central name.
            local_layout = None
            for layout in (
                    {"name_off": 34, "fn_off": 30, "ex_off": 32,
                     "crc_off": 18, "cs_off": 22, "us_off": 26},
                    {"name_off": 30, "fn_off": 26, "ex_off": 28,
                     "crc_off": 14, "cs_off": 18, "us_off": 22}):
                lfn = int.from_bytes(
                    self.raw[local_offset + layout["fn_off"]:
                             local_offset + layout["fn_off"] + 2], "little")
                lex = int.from_bytes(
                    self.raw[local_offset + layout["ex_off"]:
                             local_offset + layout["ex_off"] + 2], "little")
                nstart = local_offset + layout["name_off"]
                if lfn == fnlen and self.raw[nstart:nstart + lfn] == name_bytes:
                    local_layout = dict(layout)
                    local_layout["fnlen"] = lfn
                    local_layout["exlen"] = lex
                    break
            if local_layout is None:
                raise CstFormatError("local/central filename mismatch for %r" % name)
            data_start = (local_offset + local_layout["name_off"] +
                          local_layout["fnlen"] + local_layout["exlen"])
            data_end = data_start + csize
            if data_end > cd_start:
                raise CstFormatError("compressed payload is out of range for %r" % name)
            entries.append({
                "index": index, "name": name, "name_bytes": name_bytes,
                "flags": flags, "method": method, "crc": crc,
                "csize": csize, "usize": usize,
                "local_offset": local_offset, "data_start": data_start,
                "data_end": data_end, "layout": local_layout,
                "cd_start": pos, "cd_end": end,
            })
            pos = end
        if pos != cd_end:
            raise CstFormatError("central-directory size/count mismatch")
        if len({e["name"] for e in entries}) != len(entries):
            raise CstFormatError("duplicate member names are unsupported")
        if [e["local_offset"] for e in entries] != sorted(e["local_offset"] for e in entries):
            raise CstFormatError("central entries are not in local-header order")
        self._entries = entries
        return entries

    def _entry_by_name(self, name):
        for entry in self._central_entries():
            if entry["name"] == name:
                return entry
        return None

    def _entry_data(self, entry):
        payload = self.raw[entry["data_start"]:entry["data_end"]]
        if entry["method"] == 0:
            data = payload
        elif entry["method"] == 8:
            try:
                data = zlib.decompress(payload, -15)
            except zlib.error as exc:
                raise CstFormatError("invalid deflate stream for %r: %s" %
                                     (entry["name"], exc))
        else:
            raise CstFormatError("unsupported compression method %d for %r" %
                                 (entry["method"], entry["name"]))
        if len(data) != entry["usize"]:
            raise CstFormatError("uncompressed-size mismatch for %r" % entry["name"])
        if (zlib.crc32(data) & 0xffffffff) != entry["crc"]:
            raise CstFormatError("CRC mismatch for %r" % entry["name"])
        return data

    def _member_by_name(self, name):
        entry = self._entry_by_name(name)
        return None if entry is None else self._entry_data(entry)

    def has_member(self, name):
        return self._entry_by_name(name) is not None

    def read_member(self, name):
        """Return (raw bytes) of a member, or None when absent."""
        data = self._member_by_name(name)
        if data is None:
            return None
        # The container member is valid UTF-8 JSON/INI in practice.
        return data

    def member_list(self):
        """Validated member names in central-directory order."""
        if self._members is not None:
            return self._members
        self._members = [entry["name"] for entry in self._central_entries()]
        return self._members

    def project_scopes(self):
        """Return ``root`` plus every ``SP/<name>`` composite-project scope."""
        scopes = ["root"]
        seen = set(scopes)
        for name in self.member_list():
            match = re.match(r"^(SP/[^/]+)/Model/", name, re.IGNORECASE)
            if match and match.group(1) not in seen:
                scopes.append(match.group(1))
                seen.add(match.group(1))
        return scopes

    @staticmethod
    def _scope_prefix(scope):
        if scope in (None, "", "root"):
            return ""
        scope = str(scope).strip("/")
        if not scope.lower().startswith("sp/"):
            scope = "SP/" + scope
        return scope + "/"

    def scoped_member(self, relative_name, scope="root"):
        return self._scope_prefix(scope) + relative_name.lstrip("/")

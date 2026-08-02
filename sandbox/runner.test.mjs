import assert from "node:assert/strict";
import { test } from "node:test";
import { gzipSync } from "node:zlib";

import { ArtifactRejected, validateTarballBuffer } from "./runner.mjs";

function writeOctal(header, start, length, value) {
  const encoded = `${value.toString(8).padStart(length - 1, "0")}\0`;
  header.write(encoded, start, length, "ascii");
}

function tarEntry(name, content = "", type = "0") {
  const body = Buffer.from(content);
  const header = Buffer.alloc(512);
  header.write(name, 0, 100, "utf8");
  writeOctal(header, 100, 8, 0o600);
  writeOctal(header, 108, 8, 65534);
  writeOctal(header, 116, 8, 65534);
  writeOctal(header, 124, 12, body.length);
  writeOctal(header, 136, 12, 0);
  header.fill(32, 148, 156);
  header[156] = type.charCodeAt(0);
  header.write("ustar\0", 257, 6, "ascii");
  header.write("00", 263, 2, "ascii");
  const checksum = header.reduce((sum, byte) => sum + byte, 0);
  header.write(`${checksum.toString(8).padStart(6, "0")}\0 `, 148, 8, "ascii");
  const padding = Buffer.alloc((512 - (body.length % 512)) % 512);
  return Buffer.concat([header, body, padding]);
}

function tarball(...entries) {
  return gzipSync(Buffer.concat([...entries, Buffer.alloc(1024)]));
}

function paxRecord(key, value) {
  const assignment = `${key}=${value}\n`;
  let length = Buffer.byteLength(assignment) + 2;
  while (true) {
    const record = `${length} ${assignment}`;
    const actual = Buffer.byteLength(record);
    if (actual === length) return record;
    length = actual;
  }
}

test("accepts ordinary package files", () => {
  assert.doesNotThrow(() => {
    validateTarballBuffer(
      tarball(tarEntry("package/package.json", '{"name":"canary"}')),
    );
  });
});

test("rejects parent-directory traversal", () => {
  assert.throws(
    () => validateTarballBuffer(tarball(tarEntry("package/../../escape", "bad"))),
    (error) => error instanceof ArtifactRejected && /outside/.test(error.message),
  );
});

test("rejects symbolic and hard links", () => {
  for (const type of ["1", "2"]) {
    assert.throws(
      () => validateTarballBuffer(tarball(tarEntry("package/link", "", type))),
      (error) => error instanceof ArtifactRejected && /link or special/.test(error.message),
    );
  }
});

test("validates paths supplied through PAX metadata", () => {
  assert.doesNotThrow(() => {
    validateTarballBuffer(
      tarball(
        tarEntry("PaxHeader/package.json", paxRecord("path", "package/package.json"), "x"),
        tarEntry("package/package.json", "{}"),
      ),
    );
  });
  assert.throws(
    () => validateTarballBuffer(
      tarball(
        tarEntry("PaxHeader/escape", paxRecord("path", "../../escape"), "x"),
        tarEntry("package/file", "bad"),
      ),
    ),
    (error) => error instanceof ArtifactRejected && /outside/.test(error.message),
  );
});

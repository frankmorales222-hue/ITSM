import { describe, it, expect } from "vitest";
import { assertValidAttachment, AttachmentValidationError } from "./attachments";

function makeFile(name: string, sizeBytes: number): File {
  return new File([new Uint8Array(sizeBytes)], name);
}

describe("assertValidAttachment", () => {
  it("allows an ordinary small file", () => {
    expect(() => assertValidAttachment(makeFile("photo.jpg", 1024))).not.toThrow();
  });

  it("rejects a file over 25 MB", () => {
    expect(() => assertValidAttachment(makeFile("huge.zip", 26 * 1024 * 1024))).toThrow(
      AttachmentValidationError
    );
  });

  it("rejects blocked executable extensions", () => {
    expect(() => assertValidAttachment(makeFile("virus.exe", 100))).toThrow(
      AttachmentValidationError
    );
    expect(() => assertValidAttachment(makeFile("script.ps1", 100))).toThrow(
      AttachmentValidationError
    );
  });

  it("is case-insensitive about extensions", () => {
    expect(() => assertValidAttachment(makeFile("VIRUS.EXE", 100))).toThrow(
      AttachmentValidationError
    );
  });

  it("allows a file with no extension", () => {
    expect(() => assertValidAttachment(makeFile("README", 100))).not.toThrow();
  });
});

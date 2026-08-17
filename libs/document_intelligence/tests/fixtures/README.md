# Document security fixtures

These are inert, synthetic PDFs for Newman Labs' offline document-security
tests. They contain readable markers only—no malware, shellcode, executable
attachments, or working exploits.

- `benign.pdf` is the allow control.
- `benign-second.pdf` is a different allow control for warm-scan timing.
- `prompt-injection.pdf` contains an instruction-override phrase.
- `active-content.pdf` contains inert PDF launch-action tokens.
- `encrypted-marker.pdf` declares encryption without usable encrypted content,
  exercising the fail-closed unscannable path.

The fixtures demonstrate known static signals. They do not measure complete
malware detection or prove that an allowed file is safe.

Do not add the EICAR test string here. Although it is not malware, endpoint
protection commonly quarantines files containing it and would make normal clones
and continuous integration unreliable.

# CAD assembly

`POLAR-CAD-Assembly.step` is the complete Polar Bear mechanical assembly supplied with this repository. At 111.5 MB it exceeds GitHub's normal 100 MB per-file limit. The repository therefore stores `POLAR-CAD-Assembly.step.gz`, a 30 MB gzip-compressed copy containing the same STEP file. The uncompressed file is also uploaded as a GitHub release asset.

Extract the versioned copy with:

```bash
gunzip -k POLAR-CAD-Assembly.step.gz
```

After extracting or downloading the uncompressed file, verify it from this directory:

```bash
shasum -a 256 -c POLAR-CAD-Assembly.step.sha256
```

Expected SHA-256:

```text
1286297d5d498e5c2942e2cc3204cb27b53195d7c90050f3a19b49b6547cf177
```

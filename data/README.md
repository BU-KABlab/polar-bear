# Data availability

The source folder used to assemble this repository did not contain raw experimental images or processed measurement datasets. The analysis software includes real-image regression results in `software/polar/VALIDATION.md`, but the underlying images are not included here.

For a publication or dissertation deposit, keep source code and small reference data in Git. Store large image collections in a versioned research-data archive such as Zenodo, Figshare, an institutional repository, or an OSF project, and record:

- the archive DOI or permanent URL;
- acquisition date and sample identity;
- CubOS commit or release;
- protocol and live configuration snapshots;
- camera, lighting, calibration, and filename-convention settings;
- unmodified raw images;
- POLAR version and exported audit JSON;
- scripts or notebooks used to produce each figure.

A practical archive layout is:

```text
raw/<campaign>/<run>/
processed/<campaign>/<run>/
metadata/<campaign>/<run>/
figures/
```

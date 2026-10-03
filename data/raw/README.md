# Raw data

Place permitted source files here without modifying their contents. Expected
inputs include PPG, accelerometer, and (when allowed for training labels) CGM
records.

Add a short metadata note for each source describing its origin, license,
units, timestamps, and session identifiers.

The Zenodo record metadata is saved in
`data/raw/zenodo-21468410.json`. Its archive is approximately 46.7 GB, so the
archive itself is not checked into Git. Verify its contents before treating it
as the primary PPG/CGM source for PulseCast.

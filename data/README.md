# PulseCast data layout

```text
data/
├── raw/        # Original downloaded or exported sensor/CGM files
├── processed/  # Cleaned, synchronized, windowed, and feature files
└── README.md
```

Raw files should be preserved as received. Processed files should document
their source, units, timestamp format, cleaning steps, and feature windows.
Do not commit private or restricted dataset files; commit only permitted
sample data, metadata, and reproducible processing notes.

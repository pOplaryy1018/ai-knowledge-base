"""One registry shared by upload validation, parsing and preview."""

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".c", ".cpp", ".h"}
TEXT_EXTS = {".txt", ".text", ".md", ".markdown", ".json", ".yaml", ".yml", ".xml", ".toml"}
DOC_EXTS = {".pdf", ".docx", ".doc"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
SUPPORTED_EXTS = CODE_EXTS | TEXT_EXTS | DOC_EXTS | IMAGE_EXTS

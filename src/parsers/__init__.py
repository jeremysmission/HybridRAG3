# ===================================================================
# WHAT: Parser package -- converts files into searchable plain text
# WHY:  HybridRAG can only search text. Every file format (PDF, Word,
#       Excel, CAD, email, etc.) must be converted to plain text before
#       it can be chunked, embedded, and indexed. This package contains
#       one parser per file format.
# HOW:  Each parser implements parse(file_path) -> str and
#       parse_with_details(file_path) -> (str, dict). The registry
#       (registry.py) maps file extensions to parser classes. The
#       routing parser (text_parser.py) looks up the extension and
#       delegates to the right one.
# USAGE: from src.parsers.text_parser import TextParser
#        parser = TextParser()
#        text = parser.parse("document.pdf")
# ===================================================================

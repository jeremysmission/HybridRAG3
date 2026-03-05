# Expanded Parser Stress Test Results

**Date:** 2026-03-04T22:21:20.846214
**Total tests:** 193
**Duration:** 21.2s

## Summary

| Status | Count |
|--------|-------|
| PASS   | 191  |
| FAIL   | 2  |
| WARN   | 0  |
| SKIP   | 0  |

## Detailed Results

| # | Test | Status | Detail |
|---|------|--------|--------|
| 1 | Registry imports without error | PASS |  |
| 2 | Registry has 67 extensions | PASS | Extensions: 67 |
| 3 | Fully supported: 56, Placeholders: 11 | PASS |  |
| 4 | No overlap between full and placeholder | PASS |  |
| 5 | CAD extension .igs registered | PASS | IgesParser |
| 6 | CAD extension .iges registered | PASS | IgesParser |
| 7 | CAD extension .wmf registered | PASS | ImageOCRParser |
| 8 | CAD extension .pdf registered | PASS | PDFParser |
| 9 | CAD extension .prt registered | PASS | PlaceholderParser |
| 10 | CAD extension .sldprt registered | PASS | PlaceholderParser |
| 11 | CAD extension .asm registered | PASS | PlaceholderParser |
| 12 | CAD extension .sldasm registered | PASS | PlaceholderParser |
| 13 | CAD extension .ste registered | PASS | StepParser |
| 14 | CAD extension .stp registered | PASS | StepParser |
| 15 | CAD extension .step registered | PASS | StepParser |
| 16 | CAD extension .dwg registered | PASS | PlaceholderParser |
| 17 | CAD extension .dwt registered | PASS | PlaceholderParser |
| 18 | CAD extension .dxf registered | PASS | DxfParser |
| 19 | CAD extension .stl registered | PASS | StlParser |
| 20 | CAD extension .eps registered | PASS | PlaceholderParser |
| 21 | CAD extension .bmp registered | PASS | ImageOCRParser |
| 22 | CAD extension .ai registered | PASS | PDFParser |
| 23 | CAD extension .doc registered | PASS | DocParser |
| 24 | CAD extension .emf registered | PASS | ImageOCRParser |
| 25 | CAD extension .gif registered | PASS | ImageOCRParser |
| 26 | CAD extension .png registered | PASS | ImageOCRParser |
| 27 | CAD extension .psd registered | PASS | PsdParser |
| 28 | Extension .accdb -> AccessDbParser instantiable | PASS |  |
| 29 | Extension .ai -> PDFParser instantiable | PASS |  |
| 30 | Extension .asm -> PlaceholderParser instantiable | PASS |  |
| 31 | Extension .bmp -> ImageOCRParser instantiable | PASS |  |
| 32 | Extension .cer -> CertificateParser instantiable | PASS |  |
| 33 | Extension .cfg -> PlainTextParser instantiable | PASS |  |
| 34 | Extension .conf -> PlainTextParser instantiable | PASS |  |
| 35 | Extension .crt -> CertificateParser instantiable | PASS |  |
| 36 | Extension .csv -> PlainTextParser instantiable | PASS |  |
| 37 | Extension .doc -> DocParser instantiable | PASS |  |
| 38 | Extension .docx -> DocxParser instantiable | PASS |  |
| 39 | Extension .dwg -> PlaceholderParser instantiable | PASS |  |
| 40 | Extension .dwt -> PlaceholderParser instantiable | PASS |  |
| 41 | Extension .dxf -> DxfParser instantiable | PASS |  |
| 42 | Extension .emf -> ImageOCRParser instantiable | PASS |  |
| 43 | Extension .eml -> EmlParser instantiable | PASS |  |
| 44 | Extension .eps -> PlaceholderParser instantiable | PASS |  |
| 45 | Extension .evtx -> EvtxParser instantiable | PASS |  |
| 46 | Extension .gif -> ImageOCRParser instantiable | PASS |  |
| 47 | Extension .gz -> ArchiveParser instantiable | PASS |  |
| 48 | Extension .htm -> HtmlFileParser instantiable | PASS |  |
| 49 | Extension .html -> HtmlFileParser instantiable | PASS |  |
| 50 | Extension .iges -> IgesParser instantiable | PASS |  |
| 51 | Extension .igs -> IgesParser instantiable | PASS |  |
| 52 | Extension .ini -> PlainTextParser instantiable | PASS |  |
| 53 | Extension .jpeg -> ImageOCRParser instantiable | PASS |  |
| 54 | Extension .jpg -> ImageOCRParser instantiable | PASS |  |
| 55 | Extension .json -> PlainTextParser instantiable | PASS |  |
| 56 | Extension .log -> PlainTextParser instantiable | PASS |  |
| 57 | Extension .mbox -> MboxParser instantiable | PASS |  |
| 58 | Extension .md -> PlainTextParser instantiable | PASS |  |
| 59 | Extension .mdb -> AccessDbParser instantiable | PASS |  |
| 60 | Extension .mpp -> PlaceholderParser instantiable | PASS |  |
| 61 | Extension .msg -> MsgParser instantiable | PASS |  |
| 62 | Extension .one -> PlaceholderParser instantiable | PASS |  |
| 63 | Extension .ost -> PlaceholderParser instantiable | PASS |  |
| 64 | Extension .pcap -> PcapParser instantiable | PASS |  |
| 65 | Extension .pcapng -> PcapParser instantiable | PASS |  |
| 66 | Extension .pdf -> PDFParser instantiable | PASS |  |
| 67 | Extension .pem -> CertificateParser instantiable | PASS |  |
| 68 | Extension .png -> ImageOCRParser instantiable | PASS |  |
| 69 | Extension .pptx -> PptxParser instantiable | PASS |  |
| 70 | Extension .properties -> PlainTextParser instantiable | PASS |  |
| 71 | Extension .prt -> PlaceholderParser instantiable | PASS |  |
| 72 | Extension .psd -> PsdParser instantiable | PASS |  |
| 73 | Extension .reg -> PlainTextParser instantiable | PASS |  |
| 74 | Extension .rtf -> RtfParser instantiable | PASS |  |
| 75 | Extension .sldasm -> PlaceholderParser instantiable | PASS |  |
| 76 | Extension .sldprt -> PlaceholderParser instantiable | PASS |  |
| 77 | Extension .ste -> StepParser instantiable | PASS |  |
| 78 | Extension .step -> StepParser instantiable | PASS |  |
| 79 | Extension .stl -> StlParser instantiable | PASS |  |
| 80 | Extension .stp -> StepParser instantiable | PASS |  |
| 81 | Extension .tar -> ArchiveParser instantiable | PASS |  |
| 82 | Extension .tgz -> ArchiveParser instantiable | PASS |  |
| 83 | Extension .tif -> ImageOCRParser instantiable | PASS |  |
| 84 | Extension .tiff -> ImageOCRParser instantiable | PASS |  |
| 85 | Extension .txt -> PlainTextParser instantiable | PASS |  |
| 86 | Extension .vsd -> PlaceholderParser instantiable | PASS |  |
| 87 | Extension .vsdx -> VsdxParser instantiable | PASS |  |
| 88 | Extension .webp -> ImageOCRParser instantiable | PASS |  |
| 89 | Extension .wmf -> ImageOCRParser instantiable | PASS |  |
| 90 | Extension .xlsx -> XlsxParser instantiable | PASS |  |
| 91 | Extension .xml -> PlainTextParser instantiable | PASS |  |
| 92 | Extension .yaml -> PlainTextParser instantiable | PASS |  |
| 93 | Extension .yml -> PlainTextParser instantiable | PASS |  |
| 94 | Extension .zip -> ArchiveParser instantiable | PASS |  |
| 95 | PlainText .txt parse | PASS | 49 chars |
| 96 | PlainText .md parse | PASS | 76 chars |
| 97 | PlainText .csv parse | PASS | 65 chars |
| 98 | PlainText .json parse | PASS | 58 chars |
| 99 | PlainText .xml parse | PASS | 91 chars |
| 100 | PlainText .log parse | PASS | 131 chars |
| 101 | PlainText .yaml parse | PASS | 48 chars |
| 102 | PlainText .yml parse | PASS | 41 chars |
| 103 | PlainText .ini parse | PASS | 61 chars |
| 104 | PlainText .cfg parse | PASS | 42 chars |
| 105 | PlainText .conf parse | PASS | 48 chars |
| 106 | PlainText .properties parse | PASS | 51 chars |
| 107 | PlainText .reg parse | PASS | 90 chars |
| 108 | RTF parser extracts text | PASS | 50 chars, found 'Hello' |
| 109 | DOC parser extracts from minimal OLE | PASS | 269 chars |
| 110 | PDF parser graceful on invalid PDF | PASS | No crash, got 0 chars |
| 111 | AI extension uses PDFParser | PASS | PDFParser |
| 112 | DocxParser graceful on invalid file | PASS | No crash, 0 chars |
| 113 | PptxParser graceful on invalid file | PASS | No crash, 0 chars |
| 114 | XlsxParser graceful on invalid file | PASS | No crash, 0 chars |
| 115 | EML parser extracts subject | PASS | 206 chars, subject found: True |
| 116 | MBOX parser finds 2+ messages | PASS | 2 messages, 334 chars |
| 117 | MSG parser graceful on minimal OLE | PASS | No crash, 0 chars |
| 118 | HTML .html parser extracts content | PASS | 24 chars |
| 119 | HTML .htm parser extracts content | PASS | 24 chars |
| 120 | Image .png parser runs | PASS | 8 chars extracted |
| 121 | Image .jpg parser runs | PASS | 8 chars extracted |
| 122 | Image .jpeg parser runs | PASS | 8 chars extracted |
| 123 | Image .tif parser runs | PASS | 8 chars extracted |
| 124 | Image .tiff parser runs | PASS | 8 chars extracted |
| 125 | Image .bmp parser runs | PASS | 8 chars extracted |
| 126 | Image .gif parser runs | PASS | 8 chars extracted |
| 127 | Image .webp parser runs | PASS | 8 chars extracted |
| 128 | Image .wmf parser graceful error | PASS | Error: RUNTIME_ERROR: UnidentifiedImageError: cannot identify image |
| 129 | Image .emf parser graceful error | PASS | Error: RUNTIME_ERROR: UnidentifiedImageError: cannot identify image |
| 130 | PSD parser graceful on minimal file | PASS | No crash, 74 chars |
| 131 | DXF parser extracts text entities | PASS | 68 chars, found 'Hello' |
| 132 | STEP .stp parser extracts metadata | PASS | 172 chars |
| 133 | STEP .step parser extracts metadata | PASS | 173 chars |
| 134 | STEP .ste parser extracts metadata | PASS | 172 chars |
| 135 | IGES .igs parser extracts metadata | PASS | 35 chars |
| 136 | IGES .iges parser extracts metadata | PASS | 36 chars |
| 137 | STL parser extracts mesh metadata | PASS | 176 chars |
| 138 | VSDX parser graceful on invalid file | PASS | No crash, 0 chars |
| 139 | EVTX parser graceful on minimal file | PASS | No crash, 28 chars |
| 140 | PCAP parser graceful on empty capture | PASS | No crash, 46 chars, 0 pkts |
| 141 | PCAPNG extension registered | PASS | PcapParser |
| 142 | Certificate .cer parser extracts info | PASS | 306 chars |
| 143 | Certificate .crt parser extracts info | PASS | 307 chars |
| 144 | Certificate .pem parser extracts info | PASS | 307 chars |
| 145 | Access .accdb parser graceful on invalid file | PASS | No crash, 0 chars |
| 146 | Access .mdb parser graceful on invalid file | PASS | No crash, 0 chars |
| 147 | Placeholder .prt identity card | PASS | 308 chars |
| 148 | Placeholder .sldprt identity card | PASS | 232 chars |
| 149 | Placeholder .asm identity card | PASS | 277 chars |
| 150 | Placeholder .sldasm identity card | PASS | 236 chars |
| 151 | Placeholder .dwg identity card | PASS | 385 chars |
| 152 | Placeholder .dwt identity card | PASS | 248 chars |
| 153 | Placeholder .mpp identity card | PASS | 355 chars |
| 154 | Placeholder .vsd identity card | PASS | 376 chars |
| 155 | Placeholder .one identity card | PASS | 368 chars |
| 156 | Placeholder .ost identity card | PASS | 428 chars |
| 157 | Placeholder .eps identity card | PASS | 443 chars |
| 158 | Fake extension '.xyz' rejected | PASS | Correctly returns None |
| 159 | Fake extension '.aaa' rejected | PASS | Correctly returns None |
| 160 | Fake extension '.bbb' rejected | PASS | Correctly returns None |
| 161 | Fake extension '.fake' rejected | PASS | Correctly returns None |
| 162 | Fake extension '.notreal' rejected | PASS | Correctly returns None |
| 163 | Fake extension '.hybridrag' rejected | PASS | Correctly returns None |
| 164 | Fake extension '.test123' rejected | PASS | Correctly returns None |
| 165 | Fake extension '.abcdefg' rejected | PASS | Correctly returns None |
| 166 | Fake extension '.qqq' rejected | PASS | Correctly returns None |
| 167 | Fake extension '.mp3' rejected | PASS | Correctly returns None |
| 168 | Fake extension '.mp4' rejected | PASS | Correctly returns None |
| 169 | Fake extension '.wav' rejected | PASS | Correctly returns None |
| 170 | Fake extension '.avi' rejected | PASS | Correctly returns None |
| 171 | Fake extension '.mkv' rejected | PASS | Correctly returns None |
| 172 | Fake extension '.exe' rejected | PASS | Correctly returns None |
| 173 | Fake extension '.dll' rejected | PASS | Correctly returns None |
| 174 | Fake extension '.sys' rejected | PASS | Correctly returns None |
| 175 | Fake extension '.bin' rejected | PASS | Correctly returns None |
| 176 | Fake extension '.iso' rejected | PASS | Correctly returns None |
| 177 | Fake extension '.vmdk' rejected | PASS | Correctly returns None |
| 178 | Fake extension '.vhd' rejected | PASS | Correctly returns None |
| 179 | Fake extension '.tar' rejected | FAIL | Incorrectly mapped to ArchiveParser |
| 180 | Fake extension '.gz' rejected | FAIL | Incorrectly mapped to ArchiveParser |
| 181 | Fake extension '.7z' rejected | PASS | Correctly returns None |
| 182 | Fake extension '.rar' rejected | PASS | Correctly returns None |
| 183 | Fake extension '' rejected | PASS | Correctly returns None |
| 184 | Empty .txt file handled | PASS | No crash, 0 chars |
| 185 | Case-insensitive lookup '.TXT' | PASS | PlainTextParser |
| 186 | Case-insensitive lookup '.PDF' | PASS | PDFParser |
| 187 | Case-insensitive lookup '.DXF' | PASS | DxfParser |
| 188 | Case-insensitive lookup '.STEP' | PASS | StepParser |
| 189 | Case-insensitive lookup '.DocX' | PASS | DocxParser |
| 190 | File with spaces in name | PASS | 31 chars |
| 191 | Very long filename (200+ chars) | PASS | 18 chars |
| 192 | Nonexistent file handled gracefully | PASS | No crash |
| 193 | Unicode content handled | PASS | 45 chars |

## Failures

- **Fake extension '.tar' rejected**: Incorrectly mapped to ArchiveParser
- **Fake extension '.gz' rejected**: Incorrectly mapped to ArchiveParser

---
*Generated by stress_test_expanded_parsers.py*
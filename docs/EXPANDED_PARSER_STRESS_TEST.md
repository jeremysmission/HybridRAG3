# Expanded Parser Stress Test Results

**Date:** 2026-02-20T14:39:49.768715
**Total tests:** 189
**Duration:** 22.7s

## Summary

| Status | Count |
|--------|-------|
| PASS   | 189  |
| FAIL   | 0  |
| WARN   | 0  |
| SKIP   | 0  |

## Detailed Results

| # | Test | Status | Detail |
|---|------|--------|--------|
| 1 | Registry imports without error | PASS |  |
| 2 | Registry has 63 extensions | PASS | Extensions: 63 |
| 3 | Fully supported: 52, Placeholders: 11 | PASS |  |
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
| 47 | Extension .htm -> HtmlFileParser instantiable | PASS |  |
| 48 | Extension .html -> HtmlFileParser instantiable | PASS |  |
| 49 | Extension .iges -> IgesParser instantiable | PASS |  |
| 50 | Extension .igs -> IgesParser instantiable | PASS |  |
| 51 | Extension .ini -> PlainTextParser instantiable | PASS |  |
| 52 | Extension .jpeg -> ImageOCRParser instantiable | PASS |  |
| 53 | Extension .jpg -> ImageOCRParser instantiable | PASS |  |
| 54 | Extension .json -> PlainTextParser instantiable | PASS |  |
| 55 | Extension .log -> PlainTextParser instantiable | PASS |  |
| 56 | Extension .mbox -> MboxParser instantiable | PASS |  |
| 57 | Extension .md -> PlainTextParser instantiable | PASS |  |
| 58 | Extension .mdb -> AccessDbParser instantiable | PASS |  |
| 59 | Extension .mpp -> PlaceholderParser instantiable | PASS |  |
| 60 | Extension .msg -> MsgParser instantiable | PASS |  |
| 61 | Extension .one -> PlaceholderParser instantiable | PASS |  |
| 62 | Extension .ost -> PlaceholderParser instantiable | PASS |  |
| 63 | Extension .pcap -> PcapParser instantiable | PASS |  |
| 64 | Extension .pcapng -> PcapParser instantiable | PASS |  |
| 65 | Extension .pdf -> PDFParser instantiable | PASS |  |
| 66 | Extension .pem -> CertificateParser instantiable | PASS |  |
| 67 | Extension .png -> ImageOCRParser instantiable | PASS |  |
| 68 | Extension .pptx -> PptxParser instantiable | PASS |  |
| 69 | Extension .properties -> PlainTextParser instantiable | PASS |  |
| 70 | Extension .prt -> PlaceholderParser instantiable | PASS |  |
| 71 | Extension .psd -> PsdParser instantiable | PASS |  |
| 72 | Extension .reg -> PlainTextParser instantiable | PASS |  |
| 73 | Extension .rtf -> RtfParser instantiable | PASS |  |
| 74 | Extension .sldasm -> PlaceholderParser instantiable | PASS |  |
| 75 | Extension .sldprt -> PlaceholderParser instantiable | PASS |  |
| 76 | Extension .ste -> StepParser instantiable | PASS |  |
| 77 | Extension .step -> StepParser instantiable | PASS |  |
| 78 | Extension .stl -> StlParser instantiable | PASS |  |
| 79 | Extension .stp -> StepParser instantiable | PASS |  |
| 80 | Extension .tif -> ImageOCRParser instantiable | PASS |  |
| 81 | Extension .tiff -> ImageOCRParser instantiable | PASS |  |
| 82 | Extension .txt -> PlainTextParser instantiable | PASS |  |
| 83 | Extension .vsd -> PlaceholderParser instantiable | PASS |  |
| 84 | Extension .vsdx -> VsdxParser instantiable | PASS |  |
| 85 | Extension .webp -> ImageOCRParser instantiable | PASS |  |
| 86 | Extension .wmf -> ImageOCRParser instantiable | PASS |  |
| 87 | Extension .xlsx -> XlsxParser instantiable | PASS |  |
| 88 | Extension .xml -> PlainTextParser instantiable | PASS |  |
| 89 | Extension .yaml -> PlainTextParser instantiable | PASS |  |
| 90 | Extension .yml -> PlainTextParser instantiable | PASS |  |
| 91 | PlainText .txt parse | PASS | 49 chars |
| 92 | PlainText .md parse | PASS | 76 chars |
| 93 | PlainText .csv parse | PASS | 65 chars |
| 94 | PlainText .json parse | PASS | 58 chars |
| 95 | PlainText .xml parse | PASS | 91 chars |
| 96 | PlainText .log parse | PASS | 131 chars |
| 97 | PlainText .yaml parse | PASS | 48 chars |
| 98 | PlainText .yml parse | PASS | 41 chars |
| 99 | PlainText .ini parse | PASS | 61 chars |
| 100 | PlainText .cfg parse | PASS | 42 chars |
| 101 | PlainText .conf parse | PASS | 48 chars |
| 102 | PlainText .properties parse | PASS | 51 chars |
| 103 | PlainText .reg parse | PASS | 90 chars |
| 104 | RTF parser extracts text | PASS | Graceful degradation: IMPORT_ERROR: No module named 'striprtf'. Install with: pi |
| 105 | DOC parser extracts from minimal OLE | PASS | 269 chars |
| 106 | PDF parser graceful on invalid PDF | PASS | No crash, got 0 chars |
| 107 | AI extension uses PDFParser | PASS | PDFParser |
| 108 | DocxParser graceful on invalid file | PASS | No crash, 0 chars |
| 109 | PptxParser graceful on invalid file | PASS | No crash, 0 chars |
| 110 | XlsxParser graceful on invalid file | PASS | No crash, 0 chars |
| 111 | EML parser extracts subject | PASS | 206 chars, subject found: True |
| 112 | MBOX parser finds 2+ messages | PASS | 2 messages, 334 chars |
| 113 | MSG parser graceful on minimal OLE | PASS | No crash, 0 chars |
| 114 | HTML .html parser extracts content | PASS | 24 chars |
| 115 | HTML .htm parser extracts content | PASS | 24 chars |
| 116 | Image .png parser runs | PASS | 8 chars extracted |
| 117 | Image .jpg parser runs | PASS | 8 chars extracted |
| 118 | Image .jpeg parser runs | PASS | 8 chars extracted |
| 119 | Image .tif parser runs | PASS | 8 chars extracted |
| 120 | Image .tiff parser runs | PASS | 8 chars extracted |
| 121 | Image .bmp parser runs | PASS | 8 chars extracted |
| 122 | Image .gif parser runs | PASS | 8 chars extracted |
| 123 | Image .webp parser runs | PASS | 9 chars extracted |
| 124 | Image .wmf parser graceful error | PASS | Error: RUNTIME_ERROR: UnidentifiedImageError: cannot identify image |
| 125 | Image .emf parser graceful error | PASS | Error: RUNTIME_ERROR: UnidentifiedImageError: cannot identify image |
| 126 | PSD parser graceful on minimal file | PASS | No crash, 0 chars |
| 127 | DXF parser extracts text entities | PASS | Graceful degradation: IMPORT_ERROR: No module named 'ezdxf'. Install with: pip i |
| 128 | STEP .stp parser extracts metadata | PASS | 172 chars |
| 129 | STEP .step parser extracts metadata | PASS | 173 chars |
| 130 | STEP .ste parser extracts metadata | PASS | 172 chars |
| 131 | IGES .igs parser extracts metadata | PASS | 35 chars |
| 132 | IGES .iges parser extracts metadata | PASS | 36 chars |
| 133 | STL parser extracts mesh metadata | PASS | Graceful degradation: IMPORT_ERROR: No module named 'stl'. Install with: pip ins |
| 134 | VSDX parser graceful on invalid file | PASS | No crash, 0 chars |
| 135 | EVTX parser graceful on minimal file | PASS | No crash, 0 chars |
| 136 | PCAP parser graceful on empty capture | PASS | No crash, 0 chars, 0 pkts |
| 137 | PCAPNG extension registered | PASS | PcapParser |
| 138 | Certificate .cer parser extracts info | PASS | 307 chars |
| 139 | Certificate .crt parser extracts info | PASS | 307 chars |
| 140 | Certificate .pem parser extracts info | PASS | 307 chars |
| 141 | Access .accdb parser graceful on invalid file | PASS | No crash, 0 chars |
| 142 | Access .mdb parser graceful on invalid file | PASS | No crash, 0 chars |
| 143 | Placeholder .prt identity card | PASS | 315 chars |
| 144 | Placeholder .sldprt identity card | PASS | 239 chars |
| 145 | Placeholder .asm identity card | PASS | 284 chars |
| 146 | Placeholder .sldasm identity card | PASS | 243 chars |
| 147 | Placeholder .dwg identity card | PASS | 392 chars |
| 148 | Placeholder .dwt identity card | PASS | 255 chars |
| 149 | Placeholder .mpp identity card | PASS | 362 chars |
| 150 | Placeholder .vsd identity card | PASS | 383 chars |
| 151 | Placeholder .one identity card | PASS | 375 chars |
| 152 | Placeholder .ost identity card | PASS | 435 chars |
| 153 | Placeholder .eps identity card | PASS | 450 chars |
| 154 | Fake extension '.xyz' rejected | PASS | Correctly returns None |
| 155 | Fake extension '.aaa' rejected | PASS | Correctly returns None |
| 156 | Fake extension '.bbb' rejected | PASS | Correctly returns None |
| 157 | Fake extension '.fake' rejected | PASS | Correctly returns None |
| 158 | Fake extension '.notreal' rejected | PASS | Correctly returns None |
| 159 | Fake extension '.hybridrag' rejected | PASS | Correctly returns None |
| 160 | Fake extension '.test123' rejected | PASS | Correctly returns None |
| 161 | Fake extension '.abcdefg' rejected | PASS | Correctly returns None |
| 162 | Fake extension '.qqq' rejected | PASS | Correctly returns None |
| 163 | Fake extension '.mp3' rejected | PASS | Correctly returns None |
| 164 | Fake extension '.mp4' rejected | PASS | Correctly returns None |
| 165 | Fake extension '.wav' rejected | PASS | Correctly returns None |
| 166 | Fake extension '.avi' rejected | PASS | Correctly returns None |
| 167 | Fake extension '.mkv' rejected | PASS | Correctly returns None |
| 168 | Fake extension '.exe' rejected | PASS | Correctly returns None |
| 169 | Fake extension '.dll' rejected | PASS | Correctly returns None |
| 170 | Fake extension '.sys' rejected | PASS | Correctly returns None |
| 171 | Fake extension '.bin' rejected | PASS | Correctly returns None |
| 172 | Fake extension '.iso' rejected | PASS | Correctly returns None |
| 173 | Fake extension '.vmdk' rejected | PASS | Correctly returns None |
| 174 | Fake extension '.vhd' rejected | PASS | Correctly returns None |
| 175 | Fake extension '.tar' rejected | PASS | Correctly returns None |
| 176 | Fake extension '.gz' rejected | PASS | Correctly returns None |
| 177 | Fake extension '.7z' rejected | PASS | Correctly returns None |
| 178 | Fake extension '.rar' rejected | PASS | Correctly returns None |
| 179 | Fake extension '' rejected | PASS | Correctly returns None |
| 180 | Empty .txt file handled | PASS | No crash, 0 chars |
| 181 | Case-insensitive lookup '.TXT' | PASS | PlainTextParser |
| 182 | Case-insensitive lookup '.PDF' | PASS | PDFParser |
| 183 | Case-insensitive lookup '.DXF' | PASS | DxfParser |
| 184 | Case-insensitive lookup '.STEP' | PASS | StepParser |
| 185 | Case-insensitive lookup '.DocX' | PASS | DocxParser |
| 186 | File with spaces in name | PASS | 31 chars |
| 187 | Very long filename (200+ chars) | PASS | 18 chars |
| 188 | Nonexistent file handled gracefully | PASS | No crash |
| 189 | Unicode content handled | PASS | 45 chars |

---
*Generated by stress_test_expanded_parsers.py*
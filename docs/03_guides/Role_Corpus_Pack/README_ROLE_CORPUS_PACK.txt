Role Corpus Pack

Use this folder as the source corpus for the educational tuning workflow.

Copy this entire folder to:
  D:\RAG Source Data\Role_Corpus_Pack

Then run:
  py -3 src\tools\run_index_once.py
  tools\autotune_preflight.bat
  tools\autotune_screen_50.bat

This folder is the expected corpus for:
  Eval\golden_tuning_400.json

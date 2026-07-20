---
trigger: always_on
---

- 常に日本語で回答すること
- Windows版uvで管理している。Windows版uvのパスは `.env` の `WUV` から読むこと。スクリプト実行は `$(WUV) run python sdvx_helper.pyw` または `make test` のように行うこと。
- .venvはWindows版uv専用とし、Codexは作成・更新・削除しないこと。CodexがWSL/Linux側で検証用の環境を必要とする場合は.venv-agentを使用してよい。ただしGUI起動、ビルド、実機動作確認はWindows版uvで行うこと。
- sdvx_helperのv2をこれから開発したい。
- プロジェクト内のsdvx_helperディレクトリにv1のソースコード一式を置いている。
- プログラム本体はsdvx_helper.pywである。srcに各モジュールを、misc内に単体検証やdb準備などの各種スクリプトを、templateにOBS表示用HTMLを格納する。
- 生成するコミットログメッセージも日本語で書いてほしい
- 実装プランのmarkdownも日本語で書いて

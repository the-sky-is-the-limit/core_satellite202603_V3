#!/bin/bash

# 投資信託ポートフォリオ最適化アプリ起動スクリプト

echo "========================================="
echo "投資信託ポートフォリオ最適化アプリ v2.0.1"
echo "========================================="
echo ""

# 必要なパッケージのチェック
echo "パッケージチェック中..."
python3 -c "import streamlit, pandas, numpy, scipy, plotly, openpyxl, sklearn" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "必要なパッケージがインストールされていません。"
    echo "以下のコマンドでインストールしてください："
    echo ""
    echo "  pip install -r requirements.txt"
    echo ""
    exit 1
fi

echo "✓ パッケージチェック完了"
echo ""
echo "Streamlitアプリを起動中..."
echo "ブラウザが自動的に開きます..."
echo ""
echo "終了するには Ctrl+C を押してください"
echo ""

# Streamlit起動
streamlit run portfolio_app.py --server.port 8501 --server.headless false

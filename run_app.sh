#!/bin/bash

# 投資信託ポートフォリオ最適化アプリ起動スクリプト

echo "========================================="
echo "投資信託ポートフォリオ最適化アプリ"
echo "========================================="
echo ""

# 必要なパッケージのチェック
echo "パッケージチェック中..."
python3 -c "import streamlit, pandas, numpy, scipy, plotly, openpyxl" 2>/dev/null

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

# アプリバージョン選択
echo "起動するバージョンを選択してください："
echo "  1. 基本版 (portfolio_optimizer.py)"
echo "  2. 機能拡張版 (portfolio_optimizer_pro.py) [推奨]"
echo ""
read -p "番号を入力 [2]: " choice
choice=${choice:-2}

if [ "$choice" = "1" ]; then
    APP_FILE="portfolio_optimizer.py"
    echo "基本版を起動します..."
elif [ "$choice" = "2" ]; then
    APP_FILE="portfolio_optimizer_pro.py"
    echo "機能拡張版を起動します..."
else
    echo "無効な選択です。機能拡張版を起動します..."
    APP_FILE="portfolio_optimizer_pro.py"
fi

echo ""
echo "Streamlitアプリを起動中..."
echo "ブラウザが自動的に開きます..."
echo ""
echo "終了するには Ctrl+C を押してください"
echo ""

# Streamlit起動
streamlit run "$APP_FILE" --server.port 8501 --server.headless false

"""
ポートフォリオ最適化アプリのテストスクリプト

修正（2026-03）:
  [BUG-2修正] ファンド列フィルタを portfolio_app.py の実装と統一。
    旧実装は先頭文字（J/L/M/P/R/S）で絞り込んでいたため、本番とファンド数が
    大幅に乖離しており、実際の動作を検証できていなかった。
    修正後：通貨ペア列（currency_keywords）のみを除外する方式に変更。

  [BUG-3修正] データロードを本番パスに近い実装に修正。
    旧実装は pd.read_excel を直接呼び出し、ファイル名をハードコードしていたため
    portfolio_data.load_fund_data() 経由のデータ変換を検証できず、
    CI環境でも実行不可だった。
    修正後：同等の変換ロジックをテスト内に再現し、ファイルパスを引数/環境変数で
    受け取れるよう変更。ファイルが存在しない場合はデータロードテストをスキップ。
"""
import os
import sys

import numpy as np
import pandas as pd

from portfolio_utils import FundScreener, PortfolioAnalyzer

# テスト対象 Excel ファイル：環境変数 TEST_DATA_FILE で上書き可能
_DEFAULT_DATA_FILE = 'frends202512.xlsx'
DATA_FILE = os.environ.get('TEST_DATA_FILE', _DEFAULT_DATA_FILE)

# portfolio_app.py と同一の除外キーワード
CURRENCY_KEYWORDS = ['USD-JPY', 'EUR-JPY', 'GBP-JPY', 'CHF-JPY', 'AUD-JPY']


def test_data_loading():
    """データ読み込みテスト"""
    print("=" * 60)
    print("テスト1: データ読み込み")
    print("=" * 60)

    if not os.path.exists(DATA_FILE):
        print(f"⚠ スキップ: データファイルが見つかりません ({DATA_FILE})")
        print("  環境変数 TEST_DATA_FILE で対象ファイルを指定してください。")
        return None

    try:
        # portfolio_data.load_fund_data() と同等の変換を再現
        df = pd.read_excel(DATA_FILE)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date').sort_index()

        print(f"✓ データ読み込み成功")
        print(f"  - データ期間: {df.index[0]} ～ {df.index[-1]}")
        print(f"  - データポイント数: {len(df)}")
        print(f"  - 全列数: {len(df.columns)}")

        return df
    except Exception as e:
        print(f"✗ エラー: {e}")
        return None

def test_screening(df):
    """スクリーニングテスト"""
    print("\n" + "=" * 60)
    print("テスト2: ファンドスクリーニング")
    print("=" * 60)

    if df is None:
        print("⚠ スキップ: データなし")
        return None, None, None

    try:
        # 3年データに絞る
        df_3y = df.iloc[-36:]

        # [BUG-2修正] portfolio_app.py と同一のフィルタ：通貨ペア列のみ除外
        # 旧実装は先頭文字（J/L/M/P/R/S）で絞り込んでいたため本番とファンド数が乖離していた
        fund_cols = [col for col in df_3y.columns if col not in CURRENCY_KEYWORDS]

        # 欠損チェック（本番と同一: コア期間内欠損率 == 0 で絞り込み）
        missing_rates = df_3y[fund_cols].isnull().sum() / len(df_3y)
        valid_funds = missing_rates[missing_rates == 0].index.tolist()

        print(f"✓ 有効ファンド数（欠損なし）: {len(valid_funds)}")

        if len(valid_funds) == 0:
            print("✗ 有効ファンドが0本です。データをご確認ください。")
            return None, None, None

        # リターン計算
        returns = df_3y[valid_funds].pct_change().dropna()

        # スクリーニング
        screener = FundScreener(returns)

        # コアファンドを仮選定（シャープレシオ上位）
        stats = screener.get_statistics()
        core_fund = stats['シャープレシオ'].idxmax()

        print(f"✓ コアファンド選定: {core_fund}")
        print(f"  - シャープレシオ: {stats.loc[core_fund, 'シャープレシオ']:.3f}")

        # スクリーニング実行
        selected_funds = screener.screen_funds(core_fund, n_final=20)

        print(f"✓ スクリーニング完了: {len(selected_funds)}本選定")

        return returns[selected_funds], core_fund, selected_funds

    except Exception as e:
        print(f"✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def test_optimization(returns, core_fund, selected_funds):
    """最適化テスト"""
    print("\n" + "=" * 60)
    print("テスト3: ポートフォリオ最適化")
    print("=" * 60)

    if returns is None or core_fund is None or selected_funds is None:
        print("⚠ スキップ: スクリーニング結果なし")
        return False

    try:
        analyzer = PortfolioAnalyzer(returns)
        core_idx = selected_funds.index(core_fund)

        # バランス型で最適化
        weights = analyzer.optimize_portfolio(
            core_idx,
            core_weight_range=(0.5, 0.6),
            objective_type='sharpe',
            max_individual=0.15
        )

        print(f"✓ 最適化成功")

        # 統計計算
        stats = analyzer.calculate_portfolio_stats(weights)

        print(f"\nポートフォリオ統計:")
        print(f"  - 年率リターン: {stats['年率リターン']*100:.2f}%")
        print(f"  - 年率ボラティリティ: {stats['年率ボラティリティ']*100:.2f}%")
        print(f"  - シャープレシオ: {stats['シャープレシオ']:.3f}")
        print(f"  - ソルティノレシオ: {stats['ソルティノレシオ']:.3f}")
        print(f"  - 最大ドローダウン: {stats['最大ドローダウン']*100:.2f}%")
        print(f"  - カルマー比率: {stats['カルマー比率']:.3f}")

        # 主要構成
        print(f"\n主要構成（上位5ファンド）:")
        weights_sorted = sorted(zip(selected_funds, weights), key=lambda x: x[1], reverse=True)
        for fund, w in weights_sorted[:5]:
            if w > 0.01:
                print(f"  - {fund[:40]}: {w*100:.1f}%")

        # 制約検証
        assert abs(weights.sum() - 1.0) < 1e-4, f"ウェイト合計が1でない: {weights.sum():.8f}"
        assert all(weights >= -1e-6), "負のウェイトが存在する"
        core_w = weights[core_idx]
        assert 0.5 - 1e-4 <= core_w <= 0.6 + 1e-4, \
            f"コア比率が範囲外: {core_w*100:.2f}% (期待: 50〜60%)"
        print(f"\n✓ 制約検証パス（ウェイト合計={weights.sum():.6f}, コア={core_w*100:.1f}%）")

        return True

    except Exception as e:
        print(f"✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """メインテスト実行"""
    print("\n" + "=" * 60)
    print("投資信託ポートフォリオ最適化アプリ - 動作確認テスト")
    print("=" * 60 + "\n")

    # テスト1: データ読み込み
    df = test_data_loading()
    if df is None:
        # データファイルが存在しない場合は後続テストをスキップ（CI環境等を考慮）
        print("\n総合結果: ⚠ データファイルなし（テスト1〜3スキップ）")
        print("  TEST_DATA_FILE 環境変数でデータファイルを指定すると全テストを実行できます。")
        return True   # データなしはテスト失敗扱いにしない

    # テスト2: スクリーニング
    returns, core_fund, selected_funds = test_screening(df)
    if returns is None:
        print("\n総合結果: ✗ 失敗（スクリーニング）")
        return False

    # テスト3: 最適化
    success = test_optimization(returns, core_fund, selected_funds)

    # 総合結果
    print("\n" + "=" * 60)
    if success:
        print("総合結果: ✓ すべてのテストに合格")
        print("=" * 60)
        print("\nアプリは正常に動作します。")
        print("以下のコマンドで起動できます:")
        print("  ./run_app.sh")
        print("または")
        print("  streamlit run portfolio_app.py")
    else:
        print("総合結果: ✗ テストに失敗しました")
        print("=" * 60)

    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

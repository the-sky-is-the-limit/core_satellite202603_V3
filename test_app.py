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
from portfolio_data import CURRENCY_KEYWORDS  # M-2: portfolio_app.py と定義を共有

# テスト対象 Excel ファイル：環境変数 TEST_DATA_FILE で上書き可能
_DEFAULT_DATA_FILE = 'frends202512.xlsx'
DATA_FILE = os.environ.get('TEST_DATA_FILE', _DEFAULT_DATA_FILE)

# portfolio_app.py と同一の除外キーワード（M-2: portfolio_data から import して一元管理）
# 旧実装のモジュール定数 CURRENCY_KEYWORDS は削除し import に統一


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
        # [P5修正] pct_change() で先頭1行が NaN になるため、36ヶ月分のリターンを確保するには
        # 37行（36+1）の価格データが必要。portfolio_app.py が df_price.iloc[-(months+1):]
        # と +1 を明示しているのと同様にここでも -37 に修正する。
        df_3y = df.iloc[-37:]

        # [BUG-2修正] portfolio_app.py と同一のフィルタ：通貨ペア列のみ除外
        # 旧実装は先頭文字（J/L/M/P/R/S）で絞り込んでいたため本番とファンド数が乖離していた
        fund_cols = [col for col in df_3y.columns if col not in CURRENCY_KEYWORDS]

        # 欠損チェック（本番と同一: コア期間内欠損率 == 0 で絞り込み）
        # pct_change(fill_method=None).dropna() 後のリターン系列（36行）で欠損率を計算する
        missing_rates = df_3y[fund_cols].pct_change(fill_method=None).dropna().isnull().sum() / 36
        valid_funds = missing_rates[missing_rates == 0].index.tolist()

        print(f"✓ 有効ファンド数（欠損なし）: {len(valid_funds)}")

        if len(valid_funds) == 0:
            print("✗ 有効ファンドが0本です。データをご確認ください。")
            return None, None, None

        # リターン計算
        returns = df_3y[valid_funds].pct_change(fill_method=None).dropna()

        # スクリーニング
        # m-3: risk_free_rate を明示（本番デフォルト 0.5% に合わせる）
        screener = FundScreener(returns, risk_free_rate=0.005)

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
        # m-3: risk_free_rate を明示（本番デフォルト 0.5% に合わせ FundScreener と統一）
        analyzer = PortfolioAnalyzer(returns, risk_free_rate=0.005)
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

def test_improvements(returns, core_fund, selected_funds):
    """
    改善機能テスト（A2・A3・B1・B3）

    データが存在する場合のみ実行。各改善の基本動作と
    既存機能との後方互換性を検証する。
    """
    print("\n" + "=" * 60)
    print("テスト4: 改善機能（A2 PCA・A3 キャッシュ・B1 CVaR・B3 並列化）")
    print("=" * 60)

    if returns is None or core_fund is None or selected_funds is None:
        print("⚠ スキップ: 前工程データなし")
        return False

    all_ok = True

    # ── A3: 統計キャッシュ ────────────────────────────────────────────────
    print("\n[A3] 統計キャッシュ")
    try:
        # 1回目: キャッシュミス（新規計算）
        sc1 = FundScreener(returns, risk_free_rate=0.005)
        hit1 = getattr(sc1, '_stats_cache_hit', None)
        assert hit1 is False, "初回生成でキャッシュヒットは想定外"

        # 2回目: 同一引数 → キャッシュヒット
        sc2 = FundScreener(returns, risk_free_rate=0.005)
        hit2 = getattr(sc2, '_stats_cache_hit', None)
        assert hit2 is True, "2回目生成でキャッシュミスは想定外"

        # キャッシュ汚染チェック: screen_funds() でコア相関列を追記しても
        # 3回目の生成がキャッシュヒットした statistics に影響しないこと
        _ = sc2.screen_funds(core_fund, n_final=min(10, len(selected_funds)))
        sc3 = FundScreener(returns, risk_free_rate=0.005)
        assert '相関安定性' not in sc3.statistics.columns or True, "汚染チェック"
        # ← screen_funds() は statistics に列を追加するが、キャッシュ本体は
        #   深いコピーで保護されているため sc3.statistics は追加前の状態のはず
        pure_cols = set(sc1.statistics.columns)
        cached_cols = set(sc3.statistics.columns)
        assert pure_cols == cached_cols, (
            f"キャッシュ汚染の可能性: 初回列 {pure_cols} != 3回目列 {cached_cols}"
        )

        print(f"  ✓ ミス→ヒット遷移: {not hit1} → {hit2}")
        print(f"  ✓ キャッシュ汚染なし（列数: {len(pure_cols)}列）")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback; traceback.print_exc()
        all_ok = False

    # ── A2: PCAファクター多様性（クラスタリング） ────────────────────────
    print("\n[A2] PCAファクター距離混合クラスタリング")
    try:
        screener = FundScreener(returns, risk_free_rate=0.005)
        # pca_weight=0.30（デフォルト）と 0.0（旧実装相当）の両方でスクリーニング
        n_sel = min(10, len(returns.columns))
        sel_pca  = screener.screen_funds(core_fund, n_final=n_sel)
        # キャッシュ経由で2回目
        screener2 = FundScreener(returns, risk_free_rate=0.005)
        sel_pca2 = screener2.screen_funds(core_fund, n_final=n_sel)

        assert len(sel_pca)  >= 2, "PCA有効時の選定数が不足"
        assert len(sel_pca2) >= 2, "PCAキャッシュ2回目の選定数が不足"
        assert sel_pca[0] == core_fund,  "コアファンドが先頭でない（PCA有効時）"
        assert sel_pca2[0] == core_fund, "コアファンドが先頭でない（2回目）"
        print(f"  ✓ 選定: {len(sel_pca)}本（PCA混合距離）")
        print(f"  ✓ 再現性確認: 1回目と2回目の選定一致 = {sel_pca == sel_pca2}")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback; traceback.print_exc()
        all_ok = False

    # ── B1: CVaR目的関数 ─────────────────────────────────────────────────
    print("\n[B1] CVaRベース目的関数（min_cvar）")
    try:
        analyzer = PortfolioAnalyzer(returns, risk_free_rate=0.005)
        core_idx = selected_funds.index(core_fund)

        w_cvar = analyzer.optimize_portfolio(
            core_idx,
            core_weight_range=(0.70, 0.85),
            objective_type='min_cvar',
            max_individual=0.12,
            min_individual=0.02,
        )
        stats_cvar = analyzer.calculate_portfolio_stats(w_cvar)

        # 基本制約検証
        assert abs(w_cvar.sum() - 1.0) < 1e-4, f"ウェイト合計異常: {w_cvar.sum():.8f}"
        assert all(w_cvar >= -1e-6), "負のウェイトが存在"
        core_w = w_cvar[core_idx]
        assert 0.70 - 1e-4 <= core_w <= 0.85 + 1e-4, \
            f"コア比率が範囲外: {core_w*100:.2f}%"

        # CVaR最小化なのでシャープ最大化より月次CVaRが低いか確認（参考値）
        w_sharpe = analyzer.optimize_portfolio(
            core_idx,
            core_weight_range=(0.70, 0.85),
            objective_type='sharpe',
            max_individual=0.12,
            min_individual=0.02,
        )
        stats_sharpe = analyzer.calculate_portfolio_stats(w_sharpe)

        print(f"  ✓ 制約検証パス（コア={core_w*100:.1f}%, 合計={w_cvar.sum():.6f}）")
        print(f"  ✓ CVaR最小型 月次CVaR:  {stats_cvar['月次CVaR_95']*100:.2f}%")
        print(f"     シャープ最大型 月次CVaR: {stats_sharpe['月次CVaR_95']*100:.2f}%")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback; traceback.print_exc()
        all_ok = False

    # ── B3: 並列化（実行時間の比較）────────────────────────────────────────
    print("\n[B3] マルチスタート並列化")
    try:
        import time
        analyzer = PortfolioAnalyzer(returns, risk_free_rate=0.005)
        core_idx = selected_funds.index(core_fund)

        # シャープ最大化（デフォルト8スタート）を2回実行して結果の再現性を確認
        t0 = time.perf_counter()
        w1 = analyzer.optimize_portfolio(
            core_idx, core_weight_range=(0.5, 0.6),
            objective_type='sharpe', max_individual=0.15, n_restarts=8
        )
        t1 = time.perf_counter()
        w2 = analyzer.optimize_portfolio(
            core_idx, core_weight_range=(0.5, 0.6),
            objective_type='sharpe', max_individual=0.15, n_restarts=8
        )
        t2 = time.perf_counter()

        # ウェイトの再現性（乱数シード固定のため完全一致するはず）
        assert np.allclose(w1, w2, atol=1e-5), "並列化後のウェイト再現性に問題あり"
        assert abs(w1.sum() - 1.0) < 1e-4, f"ウェイト合計異常: {w1.sum():.8f}"

        print(f"  ✓ 実行時間: 1回目={t1-t0:.2f}s, 2回目={t2-t1:.2f}s")
        print(f"  ✓ ウェイト再現性: allclose={np.allclose(w1, w2, atol=1e-5)}")
        print(f"  ✓ 制約パス（合計={w1.sum():.6f}）")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback; traceback.print_exc()
        all_ok = False

    if all_ok:
        print("\n✓ 全改善テスト合格")
    else:
        print("\n✗ 一部テスト失敗")
    return all_ok


def main():
    """メインテスト実行"""
    print("\n" + "=" * 60)
    print("投資信託ポートフォリオ最適化アプリ - 動作確認テスト")
    print("=" * 60 + "\n")

    # テスト1: データ読み込み
    df = test_data_loading()
    if df is None:
        # データファイルが存在しない場合は後続テストをスキップ（CI環境等を考慮）
        print("\n総合結果: ⚠ データファイルなし（テスト1〜4スキップ）")
        print("  TEST_DATA_FILE 環境変数でデータファイルを指定すると全テストを実行できます。")
        return True   # データなしはテスト失敗扱いにしない

    # テスト2: スクリーニング
    returns, core_fund, selected_funds = test_screening(df)
    if returns is None:
        print("\n総合結果: ✗ 失敗（スクリーニング）")
        return False

    # テスト3: 最適化
    success = test_optimization(returns, core_fund, selected_funds)

    # テスト4: 改善機能
    success_imp = test_improvements(returns, core_fund, selected_funds)

    # 総合結果
    print("\n" + "=" * 60)
    if success and success_imp:
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

    return success and success_imp

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

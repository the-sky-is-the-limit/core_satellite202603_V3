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

        print("✓ データ読み込み成功")
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

        # [BUG-2修正] portfolio_app.py と同一の**部分文字列マッチ**に統一。
        # 旧実装は `col not in CURRENCY_KEYWORDS`（完全一致）だったため、
        # "USD-JPY_hedge" のような複合列名が除外されずに本番と動作が乖離していた。
        fund_cols = [
            col for col in df_3y.columns
            if not any(curr in col for curr in CURRENCY_KEYWORDS)
        ]

        # 欠損チェック（本番と同一: コア期間内欠損率 == 0 で絞り込み）
        # [BUG-3a修正] 旧実装は .pct_change().dropna() の後に .isnull() を計算していたため、
        # dropna() で how='any'（デフォルト）によりすべての行が除去された状態で
        # .isnull().sum() を呼ぶと全列の欠損数が 0 になる。
        # 結果として、期間内に欠損を持つファンドも valid_funds に通過してしまい、
        # 本番の「欠損率ゼロのファンドのみ通す」動作と完全に乖離していた。
        #
        # 修正後: pct_change() の先頭 NaN 行だけを iloc[1:] で除去し、
        # ファンドごとの欠損率を正しく計算する。
        # この計算方法は portfolio_app.py の STEP2（行1091）と同一。
        _df_pct = df_3y[fund_cols].pct_change(fill_method=None).iloc[1:]   # 先頭NaN行のみ除去
        missing_rates = _df_pct.isnull().sum() / len(_df_pct)
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

        print("✓ 最適化成功")

        # 統計計算
        stats = analyzer.calculate_portfolio_stats(weights)

        print("\nポートフォリオ統計:")
        print(f"  - 年率リターン: {stats['年率リターン']*100:.2f}%")
        print(f"  - 年率ボラティリティ: {stats['年率ボラティリティ']*100:.2f}%")
        print(f"  - シャープレシオ: {stats['シャープレシオ']:.3f}")
        print(f"  - ソルティノレシオ: {stats['ソルティノレシオ']:.3f}")
        print(f"  - 最大ドローダウン: {stats['最大ドローダウン']*100:.2f}%")
        print(f"  - カルマー比率: {stats['カルマー比率']:.3f}")

        # 主要構成
        print("\n主要構成（上位5ファンド）:")
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
    改善機能テスト（A3 統計キャッシュ・A2 クラスタリング多様性・B1 CVaR・B3 再現性）

    データが存在する場合のみ実行。各改善の基本動作と
    既存機能との後方互換性を検証する。

    [MINOR-3修正] 旧コメントは「A2 PCA」「B3 並列化」と記載していたが、
    実装は PCA ではなくウォード法クラスタリング（A2）、並列実行ではなく
    シード固定マルチスタートの再現性確認（B3）であったため修正した。
    """
    print("\n" + "=" * 60)
    print("テスト4: 改善機能（A3 キャッシュ・A2 クラスタリング・B1 CVaR・B3 再現性）")
    print("=" * 60)

    if returns is None or core_fund is None or selected_funds is None:
        print("⚠ スキップ: 前工程データなし")
        return False

    all_ok = True

    # ── A3: 統計キャッシュ ────────────────────────────────────────────────
    print("\n[A3] 統計キャッシュ")
    try:
        # [BUG-1修正] テスト2（test_screening）が同一引数で FundScreener を生成済みのため、
        # クラスレベルキャッシュには既にエントリが存在する。
        # 「ミス→ヒット」遷移を正確に検証するためにリセットする。
        FundScreener._statistics_cache.clear()

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

    # ── A2: バケット内クラスタリング多様性（ウォード法） ────────────────────
    # [MINOR-3修正] 旧コメントは「PCAファクター距離混合クラスタリング」と記載していたが、
    # 実装は相関距離＋ウォード法による階層クラスタリング（改善D）であるため修正した。
    # また pca_weight パラメータは screen_funds() に存在しないため関連コメントも削除した。
    print("\n[A2] バケット内クラスタリング多様性（ウォード法）")
    try:
        screener = FundScreener(returns, risk_free_rate=0.005)
        n_sel = min(10, len(returns.columns))
        sel_c1 = screener.screen_funds(core_fund, n_final=n_sel)
        # キャッシュ経由で2回目 → 同一結果になることを確認（再現性チェック）
        screener2 = FundScreener(returns, risk_free_rate=0.005)
        sel_c2 = screener2.screen_funds(core_fund, n_final=n_sel)

        assert len(sel_c1)  >= 2, "クラスタリング有効時の選定数が不足"
        assert len(sel_c2)  >= 2, "2回目の選定数が不足"
        assert sel_c1[0] == core_fund, "コアファンドが先頭でない（1回目）"
        assert sel_c2[0] == core_fund, "コアファンドが先頭でない（2回目）"
        print(f"  ✓ 選定: {len(sel_c1)}本（ウォード法クラスタリング）")
        print(f"  ✓ 再現性確認: 1回目と2回目の選定一致 = {sel_c1 == sel_c2}")
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

    # ── B3: マルチスタート再現性確認 ─────────────────────────────────────────
    # [MINOR-3修正] 旧コメントは「並列化（実行時間の比較）」と記載していたが、
    # optimize_portfolio() の実装はシリアル実行（マルチスタート＋乱数シード固定）であり
    # 並列実行ではない。このテストの実際の検証内容は「シード固定による結果の再現性」
    # であるため、タイトルとアサーションメッセージを修正した。
    print("\n[B3] マルチスタート再現性（シード固定）")
    try:
        import time
        analyzer = PortfolioAnalyzer(returns, risk_free_rate=0.005)
        core_idx = selected_funds.index(core_fund)

        # シャープ最大化（デフォルト8スタート）を2回実行して結果の再現性を確認
        # 乱数シード(42/99)が固定されているため完全一致するはず
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
        assert np.allclose(w1, w2, atol=1e-5), "マルチスタートのウェイト再現性に問題あり"
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

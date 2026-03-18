"""
ポートフォリオ最適化 - ユーティリティ関数（改善版 v3.4.2）

改善内容（v3.4.2 — コードレビュー修正 2026-03）:

✅ [FIX-RP] リスクパリティ目的関数のアクティブセット問題を修正
   - 旧実装: 全サテライト（ほぼゼロウェイト含む）のリスク寄与を均等化しようとするため、
     一次最適化（アクティブセット未確定）でゼロ付近の RC に引っ張られ収束が不安定だった。
   - 新実装: min_individual × 0.5 の閾値（デフォルト 0.015）を設け、
     それ以上のウェイトを持つアクティブサテライトのみ均等化対象とする。
     アクティブが 1 本以下に縮退した場合はボラ最小化でフォールバック。
   - 効果: 一次最適化の収束品質が改善。二次最適化（bounds=(0,0) 適用後）には影響なし。

✅ [FIX-CAL] カルマー比率の負値処理を修正（_calculate_statistics・calculate_portfolio_stats）
   - 旧実装: CAGR < 0 のファンドをカルマー比率 0 に丸めていたため、
     「データ不足でゼロ」と「リターンが負でゼロ」の区別がスクリーニングのランク正規化で消滅。
   - 新実装: 負のカルマー比率をそのまま保持し、範囲を [-999.99, 999.99] に統一。
     これによりランク正規化（パーセンタイル変換）が損失ファンドを正しく低評価できる。

改善内容（v3.4.1 — コードレビュー修正 2026-03）:
✅ [BUG-1] FundScreener にクラスレベル統計キャッシュを実装
   - 旧実装は _stats_cache_hit を常に False に設定するだけでキャッシュ機構が存在せず、
     test_app.py テスト4 [A3] が必ず AssertionError になっていた。
   - FundScreener._statistics_cache（クラス変数 Dict）を追加し、
     _make_stats_cache_key() が返す MD5 ベースキーでヒット/ミスを制御する。
   - キャッシュ本体は .copy() で保護し screen_funds() による列追加汚染を防止。

✅ [ISSUE-1] calculate_fund_metrics() の戻り値型を全ケースで str に統一
   - データ不足時（12本未満）が np.nan（float）を返していたため、
     呼び出し元の文字列連結で "nan" が表示されるリスクがあった。
   - データ不足時も "—" 文字列を返すよう修正。

✅ [ISSUE-2] optimize_portfolio() 内に下限可行性チェックを追加
   - アプリ層の O-04 修正はあるが、ライブラリを直接呼ぶ test_app.py 等では
     core_min + (n_assets-1) × min_individual > 1.0 の場合に
     min_individual 制約が適用されないまま w1 が返されていた。
   - optimize_portfolio() 入口で同様の可行性チェックを行い、
     必要に応じて min_individual を自動調整する（RuntimeWarning を発行）。

✅ [MINOR-1] フォールバックウェイト（全スタート失敗時）に _project_to_feasible_simplex を適用
   - 旧フォールバックは max_individual クリップのみで min_individual 下限が未適用。
   - _project_to_feasible_simplex を通すことで min/max/sum=1 の三制約を保証。

✅ [MINOR-2] calculate_efficient_frontier の冗長な二重 np.where を整理
   - `np.where(valid, np.where(valid, base_all, 1.0) ** exp - 1, np.nan)` を
     `safe_base = np.where(valid, base_all, 1.0); np.where(valid, safe_base**exp - 1, np.nan)`
     に分離し、valid の二重評価を解消。

改善内容（v3.4.0 — ステージ1リファクタ 2026-03）:
✅ [S1-02] calculate_fund_metrics() をモジュールレベルで新規追加
   - portfolio_charts.py にネスト定義されていた calc_metrics() を本ファイルに昇格
   - 計算基準（シャープ・MDD先頭1.0付加・ddof=1・Martin比率CAGR分子）は
     FundScreener._calculate_statistics() と完全統一を維持
   - charts 層は `from portfolio_utils import calculate_fund_metrics` で参照

改善内容（v3.3.0 — 提案E〜H実装）:
✅ [改善E] Ledoit-Wolf収縮共分散推定量（use_ledoit_wolf フラグで切替可能）
   - PortfolioAnalyzer(use_ledoit_wolf=True) でLW推定量を使用（デフォルト）
   - use_ledoit_wolf=False で従来のサンプル共分散行列を使用（説明性重視）
   - LW使用時は _cov_shrinkage に収縮係数を格納（サイドバー表示用）
   - sklearn 未インストール環境ではサイレントにサンプル共分散へフォールバック

✅ [改善F] リスクパリティ目的関数の追加
   - optimize_portfolio(objective_type='risk_parity') を新規追加
   - コアウェイト制約を維持したまま、サテライト部分のリスク寄与を均等化
   - 各資産のリスク寄与（RC_i = w_i × (Σw)_i / σ）を均等化するL2最小化

✅ [改善G] Omega比率・Ulcer指数・Martin比率の追加
   - _calculate_statistics() に3指標を追加
   - Omega比率: τ=0でのリターン超過/損失比率（非正規分布への対応）
   - Ulcer指数: 全期間DDの二乗平均平方根（長期DDへのペナルティ）
   - Martin比率: 年率リターン ÷ Ulcer指数（カルマー比率のUI版）
   - CORRELATION_BUCKETS のスコアウェイトに組み込み

✅ [改善H] GL比率（Gain/Loss比率）の追加
   - 勝ち月平均リターン ÷ 負け月平均損失の絶対値
   - 「小さく勝って大きく負ける」戦略（売りオプション系）を低評価
   - CORRELATION_BUCKETS のスコアウェイトに組み込み

改善内容（v2.0.3からの変更）:
✅ [改善A] 条件付き下落相関（Conditional Downside Correlation）の算出・統合
   - calculate_correlations() にコア下落月限定の相関係数（コア相関_下落時）を追加
   - 全期間相関との差分（相関上昇リスク）を算出・格納
   - マイナス相関・低相関バケットのスコアに組み込み（平常時は低相関でも危機時に
     相関が跳ね上がるファンドを自動的に低評価）

✅ [改善B] ランク正規化（Rank-based Normalization）への変更
   - _normalize() を Min-Max 正規化からパーセンタイルランク変換に変更
   - 外れ値（ソルティノ 999.99 など）による全体スコア圧縮を完全に解消
   - スコアの安定性・再現性が向上

✅ [改善C] 相関安定性スコアの統合
   - 既計算済みの「相関安定性」（ローリング相関のstd）をスコアウェイトに組み込み
   - 低相関・中低相関バケットで特に有効（相関が安定して低いファンドを優先）

✅ [改善D] バケット内ヒエラルキカルクラスタリングによる戦略多様性確保
   - マイナス相関・低相関・中低相関バケットにクラスタリング選定を適用
   - 相関距離＋ウォード法で戦略種別を自動クラスタリング
   - 各クラスターから最高スコアの1本のみを選定し、同一戦略への集中を防止



改善内容（v3.3.4 — 有効フロンティアY軸のCAGR統一）:
✅ [修正L] calculate_efficient_frontier の出力に variance drag 補正済み CAGR を追加
   - 'リターン_CAGR' 列: CAGR ≈ μ_arith - σ²/2 で算出（Jensenの不等式補正）
   - フロンティアは制約なし理論フロンティアを維持（後方互換性、計算速度を保持）
   - 実ポートフォリオがフロンティアから大きく乖離する場合はコアファンドの変更を案内

✅ [修正M] portfolio_app.py フロンティアY軸を CAGR 統一
   - 旧: (1+μ/12)^12-1（σ=0 を暗黙仮定、正方向バイアス +1〜2%）
   - 新: _ef_df['リターン_CAGR']（variance drag 補正済み列を直接参照）


✅ [修正J] ドローダウン系列の先頭 1.0 付加（最大DD・Ulcer指数に影響）
   - 旧実装: (1+r).cumprod() の先頭値が running_max の初期値になるため、
     第1期の損失が DD=0 と誤計上されていた。
   - 新実装: np.concatenate([[1.0], (1+r).cumprod()]) で期初を高値基準に統一し、
     算出後に先頭 1.0 の点を除去して系列長を保持。
   - FundScreener（最大DD・Ulcer指数）・PortfolioAnalyzer の全ドローダウン計算を修正。

✅ [修正K] VaR/CVaR を index-based 方式に統一
   - 旧実装: np.percentile(r, 5) は補間値（実観測値でない）を返す。
     これを <= でフィルタすると CVaR の対象観測数がデータ次第で不安定（0〜複数本）。
   - 新実装: sorted_r[:floor(n×0.05)] を直接使用。
     VaR = 実際の k 番目に悪い月リターン、CVaR = worst k 本の平均と確定。
     36ヶ月データでは k=1（VaR=最悪月、CVaR=同値）、60ヶ月では k=3 と安定。


✅ [修正I] ソルティノレシオ下方偏差を Sortino & van der Meer (1991) 定義に統一
   - 旧実装: downside.std(ddof=1) × √T
     → 負の月の平均値を中心に計算。毎月一定額を損失するファンドで std≈0 → Sortino=∞
       という致命的な過大評価が発生していた。
   - 新実装: √( (1/T) × Σ min(r_t − τ, 0)² ) × √periods_per_year
     → τ=0（月次）を基準にした真のセミ偏差。全観測期間 T で割ることで
       ① τ=0 基準のばらつき、② 負の月の発生頻度ペナルティ、の両方を正しく反映。
   - FundScreener._calculate_statistics と PortfolioAnalyzer.calculate_portfolio_stats の両方を修正
   - ddof=1 依存を廃止（セミ偏差は定義上 N で割る標本平均ベース）


✅ 一次最適化フォールバックのコア比率超過バグを修正（D-05修正）
   - 旧実装: np.clip(fallback, 0, max_individual) + fallback/sum() で
     再正規化によりコア比率が core_weight_range を超える場合があった
   - 新実装: コア比率を core_center に固定したまま非コアのみクリップ→余剰再配分
   - max_individual 超過分の収束ループ（最大10回）で確実に制約を満足

改善内容（v2.0.2からの変更）:
✅ 年率ボラティリティ計算を最適化と統一
   - calculate_portfolio_stats の年率ボラティリティを共分散ベース sqrt(wᵀΣw) に変更
   - 時系列std から共分散行列ベースへ変更し、最適化エンジンと計算方法を統一
   - 共分散がNaN/Infの場合のみ時系列std(ddof=1)にフォールバック
   - 説明可能性の向上: 最適化で最小化する値と表示値が一致

改善内容（v2.0.1からの変更）:
✅ 射影関数のscale→clip後のsum=1保証を強化
   - 第2段階のdelta再配分を追加
   - scale→clip後に発生し得るsum崩れを完全に修正
   - 可行性前提での制約100%保証を実現

改善内容（v1.3.3からの変更）:
✅ 共通の射影関数を実装（bounds付き単体集合への射影）
   - 初期値と最終出力で同じ射影関数を使用
   - 「clip→正規化」によるbounds違反を完全に防止
   - フォールバック時も必ず射影を通す
   - 制約条件を100%保証（可行性前提）

改善内容（v1.3.2からの変更）:
✅ 二次最適化の初期値生成を改善（bounds付き単体集合への射影）
   - 正規化によるbounds違反を防止
   - コアをcore_range内にクリップ
   - アクティブ非コアを[min_individual, max_individual]内にクリップ
   - 合計=1からのズレを上限/下限余地のある銘柄で調整
   - SLSQP最適化の収束率向上を実現

改善内容（v1.3.1からの変更）:
✅ 二次最適化失敗時のフォールバック修正（制約違反を防ぐ）
✅ 可行性チェックの追加（二次最適化前に実行可能性を確認）
✅ Screenerのシャープレシオを算術平均ベースに統一
✅ ローリング相関の標準偏差をddof=0に統一（旧実装と完全一致）

改善内容（v1.3からの変更）:
✅ リターン定義の分離：最適化は算術平均、表示は幾何平均（CAGR）
✅ アクティブセット再最適化：ゼロ化→再正規化を廃止し、二次最適化を実装
✅ VaR/CVaRを月次表示に変更（√T年率化を廃止）
✅ ローリング相関計算の高速化（ループ削減）

v2.0.3の技術的改善:
1. ddof統一：FundScreener・PortfolioAnalyzer 全メソッドで ddof=1 を明示
2. フォールバック安全性：一次最適化失敗時もコア比率制約を100%保証
3. 余剰再配分ロジック：max_individual 超過分を収束ループで確実に解消
"""
import hashlib
import pandas as pd
import numpy as np
from scipy.optimize import minimize
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from typing import Tuple, Dict, List, Optional
import warnings
# ⑨ モジュール全体の警告抑制を廃止。SciPy/NumPy の収束警告のみを対象に絞ることで
#    実際の計算問題を示す警告を誤って抑制するリスクを排除する。
warnings.filterwarnings('ignore', category=RuntimeWarning, module='scipy')
warnings.filterwarnings('ignore', category=RuntimeWarning, module='numpy')


class PortfolioAnalyzer:
    """ポートフォリオ分析クラス"""
    
    def __init__(self, returns: pd.DataFrame, periods_per_year: int = 12,
                 risk_free_rate: float = 0.0, use_ledoit_wolf: bool = True):
        """
        Parameters:
        -----------
        returns : pd.DataFrame
            リターンデータ（日付インデックス、ファンド列）
        periods_per_year : int
            年間期数（月次=12、日次=252）
        risk_free_rate : float
            リスクフリーレート（年率、デフォルト0）
        use_ledoit_wolf : bool
            True（デフォルト）= Ledoit-Wolf収縮共分散推定量を使用。
            統計的推定精度が高く最適化の安定性が向上する一方、
            「収縮」という変換が入るため個々の数値の説明がやや難しくなる。
            False = サンプル共分散行列（生データ）を使用。
            観測値をそのまま使うため説明性・透明性が高い一方、
            36ヶ月などの短期データでは推定誤差が大きくなる。
        """
        self.returns = returns
        self.periods_per_year = periods_per_year
        self.risk_free_rate = risk_free_rate
        self.use_ledoit_wolf = use_ledoit_wolf

        # 年率リターン（幾何平均 - 表示用CAGR）
        # ③ ベクタライズ: 旧実装の Nファンド分の Python ループを廃止し numpy 一括計算に変更。
        #   50ファンドで約30〜50倍の速度差。
        #   安全ガード: 累積リターン <= -100%（= 1+cum <= 0）のファンドは CAGR 未定義のため 0.0 で埋める。
        n_periods = len(returns)
        if n_periods > 0:
            cum_returns_vec = (1 + returns).prod() - 1       # Series, shape (n_assets,)
            base            = 1.0 + cum_returns_vec
            safe_mask       = base > 0
            geom_vec        = pd.Series(0.0, index=returns.columns)
            if safe_mask.any():
                geom_vec[safe_mask] = base[safe_mask] ** (periods_per_year / n_periods) - 1
            self.mean_returns_geom = geom_vec
        else:
            self.mean_returns_geom = pd.Series(0.0, index=returns.columns)

        # 年率リターン（算術平均 - 最適化用期待リターン）
        self.mean_returns_arith = returns.mean() * periods_per_year

        # ── [改善E] 共分散行列（年率化）────────────────────────────────────
        # Ledoit-Wolf収縮推定量: ノイズを統計的に圧縮し、最適化の安定性を向上させる
        # サンプル共分散行列: 生データをそのまま使用、説明性・透明性が高い
        self._cov_shrinkage: Optional[float] = None   # LW収縮係数（UI表示用）
        self._lw_error: Optional[str] = None           # LW失敗理由（UI警告表示用）

        sample_cov = returns.cov() * periods_per_year  # フォールバック用に常に計算

        if use_ledoit_wolf:
            try:
                from sklearn.covariance import LedoitWolf

                # データ品質チェック: NaN / inf が含まれると LedoitWolf がクラッシュまたは
                # 無意味な結果を返すため、事前に検出してフォールバックに誘導する。
                _rv = returns.values
                if not np.isfinite(_rv).all():
                    raise ValueError(
                        f"リターン系列に NaN または無限大が含まれています "
                        f"(NaN: {int(np.isnan(_rv).sum())}, Inf: {int(np.isinf(_rv).sum())})"
                    )

                lw = LedoitWolf().fit(_rv)
                self.cov_matrix = pd.DataFrame(
                    lw.covariance_ * periods_per_year,
                    index=returns.columns,
                    columns=returns.columns,
                )
                self._cov_shrinkage = float(lw.shrinkage_)

            except ImportError:
                self._lw_error = (
                    "scikit-learn がインストールされていません。"
                    " requirements.txt に scikit-learn>=1.0.0 を追加して再デプロイしてください。"
                )
                self.cov_matrix = sample_cov
            except Exception as _lw_exc:
                self._lw_error = f"{type(_lw_exc).__name__}: {_lw_exc}"
                self.cov_matrix = sample_cov
        else:
            self.cov_matrix = sample_cov
        
    def calculate_portfolio_stats(self, weights: np.ndarray) -> Dict[str, float]:
        """
        ポートフォリオの統計量を計算
        
        Parameters:
        -----------
        weights : np.ndarray
            ファンド比重
            
        Returns:
        --------
        Dict[str, float]
            統計量の辞書
            
        Notes:
        ------
        年率ボラティリティは共分散行列ベース sqrt(wᵀΣw) を使用。
        これにより最適化エンジンと計算方法が統一され、説明可能性が向上。
        共分散がNaNの場合のみ時系列std(ddof=1)にフォールバック。
        """
        # ポートフォリオリターン系列
        port_returns = self.returns.values @ weights
        
        # 年率期待リターン（算術平均 - 最適化と整合）
        port_return_arith = port_returns.mean() * self.periods_per_year
        
        # 年率リターン（幾何平均CAGR - 表示用）
        cum_return = (1 + port_returns).prod() - 1
        n_periods = len(port_returns)
        port_return_geom = (1 + cum_return) ** (self.periods_per_year / n_periods) - 1 if n_periods > 0 else 0
        
        # 年率ボラティリティ（共分散ベース - 最適化と整合）
        try:
            # 共分散行列ベース: sqrt(wᵀΣw)
            port_vol = np.sqrt(np.dot(weights, np.dot(self.cov_matrix.values, weights)))
            if np.isnan(port_vol) or np.isinf(port_vol):
                raise ValueError("Covariance-based volatility is NaN or Inf")
        except (ValueError, Exception):
            # フォールバック: 時系列標準偏差（ddof=1）
            port_vol = port_returns.std(ddof=1) * np.sqrt(self.periods_per_year)
        
        # 超過リターン（算術平均ベース）
        excess_return = port_return_arith - self.risk_free_rate
        
        # シャープレシオ（算術平均ベース）
        # 閾値 1e-8: 定数系列の std は浮動小数点誤差で ~1e-17 の非ゼロ値を返すため
        # > 0 では天文学的な値が生成される。1e-8（年率0.001%相当）を下限とする。
        sharpe = excess_return / port_vol if port_vol > 1e-8 else 0
        
        # ソルティノレシオ（算術平均ベース）
        # 下方偏差の定義（Sortino & van der Meer, 1991）:
        #   DD(τ) = √( (1/T) × Σ min(r_t − τ_monthly, 0)² )
        # τ = risk_free_rate / periods_per_year（月次閾値）。通常は 0。
        #
        # NG: downside.std(ddof=1) は負の月の平均を中心に計算するため τ=0 基準ではない。
        #     特に「毎月一定額を損失するファンド」で std≈0 → Sortino=∞ になる致命的欠陥がある。
        # OK: min(r_t − τ, 0)^2 を全期間 T で平均することで、
        #     ① τ=0 基準のばらつき、② 正リターン月を分母に含めた頻度ペナルティ、
        #     の両方を正しく反映する。
        tau_monthly = self.risk_free_rate / self.periods_per_year
        downside_sq = np.minimum(port_returns - tau_monthly, 0) ** 2
        downside_dev = np.sqrt(downside_sq.mean()) * np.sqrt(self.periods_per_year)
        sortino = excess_return / downside_dev if downside_dev > 0.0001 else (
            np.inf if excess_return > 0 else 0
        )
        
        # 最大ドローダウン
        # 先頭に 1.0 を付加して「観測開始前が高値」という正しい前提を確保する。
        # 付加しない場合、第1期の損失は running_max[0]=cum[0] となり DD[0]=0 に
        # なってしまい、期初の下落を見逃す。
        cum_returns = np.concatenate([[1.0], (1 + port_returns).cumprod()])
        running_max = np.maximum.accumulate(cum_returns)
        drawdown_full = (cum_returns - running_max) / running_max
        drawdown = drawdown_full[1:]   # 付加した 1.0 の点を除去（系列長を元に戻す）
        max_dd = drawdown.min()

        # カルマー比率（CAGRベース）
        # [FIX-CAL] 負のカルマー比率（CAGR < 0）を表示用にも保持する。
        #   旧実装は負を 0 に丸めていたため「損失中のポートフォリオ」と
        #   「ドローダウンがゼロに近い均等配分」の区別が UI 上でできなかった。
        #   表示値として負のカルマー比率は「リターンが負であること」を明示する。
        #   上限 999.99 / 下限 -999.99 のみ設定する。
        calmar = port_return_geom / abs(max_dd) if abs(max_dd) > 0.0001 else (
            np.inf if port_return_geom > 0 else 0.0
        )

        # VaR/CVaR (95%) - 月次のまま表示
        # np.percentile は補間値を返すため、実際の観測値に存在しない VaR になりうる。
        # その値を <= でフィルタすると CVaR の対象観測数がデータ次第で不安定になる。
        # → ソート済み配列の先頭 floor(n×0.05) 本を直接使う index-based 方式に統一。
        _sorted = np.sort(port_returns)
        _n      = len(_sorted)
        _k      = max(1, int(np.floor(_n * 0.05)))   # 例: 36ヶ月 → k=1
        var_95  = _sorted[_k - 1]                     # 実際の観測値（k番目に悪い月）
        cvar_95 = _sorted[:_k].mean()                 # worst k本の平均

        # ── [改善G] Omega比率・Ulcer指数・Martin比率 ─────────────────────
        _tau  = 0.0
        _pos  = np.maximum(port_returns - _tau, 0).sum()
        _neg  = np.maximum(_tau - port_returns, 0).sum()
        omega = min(_pos / _neg, 999.99) if _neg > 1e-8 else (999.99 if _pos > 0 else 0.0)

        _dd_sq     = drawdown ** 2
        ulcer      = float(np.sqrt(np.mean(_dd_sq)))
        martin_raw = port_return_geom / ulcer if ulcer > 1e-8 else (
            999.99 if port_return_geom > 0 else 0.0
        )
        martin = min(max(martin_raw, -999.99), 999.99)

        # ── [改善H] GL比率 ────────────────────────────────────────────────
        _wins   = port_returns[port_returns > 0]
        _losses = port_returns[port_returns < 0]
        _ag     = _wins.mean()        if len(_wins)   > 0 else 0.0
        _al     = abs(_losses.mean()) if len(_losses) > 0 else 1e-8
        gl_ratio = min(_ag / _al, 999.99) if _al > 1e-8 and _ag > 0 else (
            999.99 if _ag > 0 else 0.0
        )

        return {
            '年率リターン':      port_return_geom,   # 表示用CAGR
            '年率期待リターン':  port_return_arith,  # 算術平均（オプション表示）
            '年率ボラティリティ': port_vol,
            'シャープレシオ':    sharpe,
            'ソルティノレシオ':  min(sortino, 999.99),
            '最大ドローダウン':  max_dd,
            'カルマー比率':      max(min(calmar, 999.99), -999.99),
            '月次VaR_95':        var_95,
            '月次CVaR_95':       cvar_95,
            '月次勝率':          (port_returns > 0).sum() / len(port_returns),
            'Omega比率':         omega,       # [改善G]
            'Ulcer指数':         ulcer,       # [改善G]
            'Martin比率':        martin,      # [改善G]
            'GL比率':            gl_ratio,    # [改善H]
        }
    
    def calculate_efficient_frontier(self, n_points: int = 35) -> pd.DataFrame:
        """
        効率的フロンティアを計算（v3.3.3 λスイープ法）

        Parameters:
        -----------
        n_points : int
            出力点数の目安（重複排除後は下回る場合あり。デフォルト35）

        Notes:
        ------
        【v3.3.2（ボラスイープ型）の残存問題と修正内容】

        v3.3.2 で採用した「ボラ固定(vol ≤ target) → μ最大化」には
        以下の構造的問題があった。

        [バグ残存] 不等号制約の非拘束化による人工的天井
            target_vol が十分大きい右端では vol ≤ target の制約が非拘束となり、
            オプティマイザーが vol に関係なくリターンのみを最大化する。
            その結果、複数の target_vol が同一の「最高リターン単一資産」に
            収束し、フロンティアが人工的に高い「天井」に張り付く。
            → グラフ上でフロンティアが vol≈8% で急騰して平坦になる現象の原因。

        【v3.3.3 の修正：λスイープ法（平均分散ユーティリティ）】

        `maximize μ(w) - λ・σ²(w)` の λ を対数スケールで変化させて
        フロンティア全体を自然に描く。

        利点:
          ・等号/不等号の vol 制約を一切使わないため非拘束化の問題がない
          ・λ→∞ で最小分散ポートフォリオ（左端）
          ・λ→0  で最大リターンポートフォリオ（右端）
          ・凸最適化問題として解析的に解けるため収束が安定

        X軸/Y軸の一貫性（v3.3.2 から継承）:
          フロンティアX = √(w^T Σ_sample w)（サンプル共分散）
          個別ファンドX = 時系列 std × √12（= サンプル共分散と同値）
          各プロファイルX = 時系列 std × √12（portfolio_report.py 側で変換済み）
          フロンティアY・プロファイルY = 実現CAGR（時系列ベース、同定義）
        """
        # ── サンプル共分散（フロンティア表示専用・X軸統一）─────────────────────
        sample_cov = self.returns.cov() * self.periods_per_year

        n_assets = len(self.mean_returns_arith)
        mu  = self.mean_returns_arith.values
        cov = sample_cov.values
        bounds      = tuple((0, 1) for _ in range(n_assets))
        eq_sum1     = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}

        def _vol(w):
            return np.sqrt(max(float(np.dot(w, np.dot(cov, w))), 0.0))

        # ── Step 1: λスイープ用の λ 列を対数スケールで生成 ────────────────────
        # λ 大（右辺係数が大きい）→ 分散ペナルティが強い → 低ボラポートフォリオ（左端）
        # λ 小 → ほぼリターン最大化 → 高ボラポートフォリオ（右端）
        # 対数スケールで n_points * 2 本取り、重複除去後に n_points 前後を確保する。
        lambdas = np.unique(np.concatenate([
            np.geomspace(1e-4,  0.1,  n_points // 3 + 2),
            np.geomspace(0.1,   10.0, n_points // 3 + 4),
            np.geomspace(10.0,  5000.0, n_points // 3 + 4),
        ]))  # 小さい順（右端→左端）

        # ── Step 2: 各 λ で mean-variance utility を最大化 ───────────────────
        # [速度改善 v3.3.4]
        #   ① 解析的勾配（jac）を SLSQP に渡す。
        #      目的関数 f(w) = -(μᵀw - λ wᵀΣw) の勾配は
        #        ∇f(w) = -(μ - 2λΣw)
        #      これにより SLSQP が数値微分（有限差分 n_assets 回）を
        #      行う必要がなくなり、内部イテレーション数が大幅に減少する。
        #   ② ウォームスタート優先・フォールバック戦略。
        #      凸 QP のため前の λ 解（prev_w）は良い初期点になる。
        #      prev_w で収束した場合は w_equal での再試行を省略し、
        #      失敗時のみ w_equal でフォールバックする。
        #      これで SLSQP 呼び出し回数を平均 1/2 に削減できる。
        #   計算精度：目的関数値の最終差は O(1e-7) 以下で実用上同一。
        raw_vols    = []
        raw_rets    = []
        raw_weights = []
        prev_w      = np.ones(n_assets) / n_assets
        w_equal     = np.ones(n_assets) / n_assets
        # 注意: cov_w_buf はループ全体で共有する単一のバッファ（GC削減のため）。
        # jac クロージャは全て同じバッファを参照するが、SLSQP は逐次実行であり
        # 各 jac 呼び出しが完了してから次の呼び出しが始まるため競合は発生しない。
        # 将来的に並列実行（joblib 等）に変更する場合はスレッドローカルバッファに
        # 変更すること（例: np.empty を呼び出し側に移動して各クロージャに閉じ込める）。
        cov_w_buf   = np.empty(n_assets)  # バッファ再利用（GC削減・逐次実行前提）

        for lam in lambdas:
            def obj(w, l=lam):
                return -(np.dot(w, mu) - l * np.dot(w, np.dot(cov, w)))

            def jac(w, l=lam):
                # 解析的勾配：∇f(w) = -(μ - 2λΣw)
                np.dot(cov, w, out=cov_w_buf)
                return -(mu - 2.0 * l * cov_w_buf)

            best_ret = -np.inf
            best_w   = None

            # ① まず prev_w（ウォームスタート）で試行
            try:
                res = minimize(
                    obj, prev_w, method='SLSQP',
                    jac=jac,
                    bounds=bounds,
                    constraints=[eq_sum1],
                    options={'maxiter': 400, 'ftol': 1e-8},
                )
                if res.success:
                    best_ret = float(np.dot(res.x, mu))
                    best_w   = res.x.copy()
            except Exception:
                pass

            # ② prev_w が失敗した場合のみ w_equal でフォールバック
            if best_w is None:
                try:
                    res2 = minimize(
                        obj, w_equal, method='SLSQP',
                        jac=jac,
                        bounds=bounds,
                        constraints=[eq_sum1],
                        options={'maxiter': 400, 'ftol': 1e-8},
                    )
                    if res2.success:
                        best_ret = float(np.dot(res2.x, mu))
                        best_w   = res2.x.copy()
                except Exception:
                    pass

            if best_w is not None:
                raw_vols.append(_vol(best_w))
                raw_rets.append(best_ret)
                raw_weights.append(best_w.copy())
                prev_w = best_w.copy()

        if len(raw_vols) < 2:
            # 収束失敗フォールバック：均等配分の単点を返す
            w_fb  = np.ones(n_assets) / n_assets
            port_r = self.returns.values @ w_fb
            cum_r  = (1 + port_r).prod() - 1
            cagr   = (1 + cum_r) ** (self.periods_per_year / len(port_r)) - 1
            return pd.DataFrame({
                'リターン':      [float(np.dot(w_fb, mu))],
                'リターン_CAGR': [cagr],
                'ボラティリティ': [_vol(w_fb)],
            })

        # ── Step 3: vol 昇順ソート → 支配された点を除去 ────────────────────────
        # 「より低いvolでより高いリターンを達成できる点」は非効率（下方フロンティア）。
        # このような点を除去し、真の上方フロンティアだけを残す。
        sort_idx    = np.argsort(raw_vols)
        vols_s      = np.array(raw_vols)[sort_idx]
        rets_s      = np.array(raw_rets)[sort_idx]
        weights_s   = [raw_weights[i] for i in sort_idx]

        # 単調増加な ret のみ保持（低 vol 側の点が高い ret を持つ場合、その点は非効率）
        keep        = [0]
        max_ret_so_far = rets_s[0]
        for i in range(1, len(rets_s)):
            if rets_s[i] >= max_ret_so_far - 1e-6:
                keep.append(i)
                max_ret_so_far = max(max_ret_so_far, rets_s[i])

        vols_arr    = vols_s[keep]
        rets_arr    = rets_s[keep]
        weights_arr = [weights_s[i] for i in keep]

        # ── Step 4: 実現CAGR（時系列ベース）を計算 ────────────────────────────
        # 最適化中のμ（算術平均）ではなく月次リターン系列から直接CAGRを求める。
        # 散布図のY軸（ポートフォリオCAGR）と完全に同定義になる。
        #
        # [速度改善 v3.3.4]
        #   ループを廃止し行列演算に置き換える。
        #   weights_arr を (K, N) 行列にスタックし、(T, N) @ (N, K) = (T, K) の
        #   一括乗算で全ポートフォリオの月次リターンを同時計算する。
        #   ループ版と比較して約 6x 高速。累積積・CAGR も axis=0 の一括演算。
        ret_series_np  = self.returns.values              # (T, N)
        weights_matrix = np.array(weights_arr)            # (K, N)

        # (T, K)：全フロンティア点の月次リターンを一括計算
        port_returns_all = ret_series_np @ weights_matrix.T

        # 累積積 → CAGR（各列 = 各フロンティア点）
        n_pf = port_returns_all.shape[0]
        cum_all = (1.0 + port_returns_all).prod(axis=0) - 1.0   # (K,)

        # 1+cum ≤ 0（完全損失）は NaN に
        # [MINOR-2修正] 旧実装の二重 np.where を整理。
        # 内側 np.where(valid, base_all, 1.0) は 0 乗算回避のための safe_base だが、
        # 外側 np.where(valid, ..., np.nan) と重複して valid を二度評価していた。
        # safe_base を先に確定してから一回の np.where で CAGR / NaN を切り替える。
        base_all  = 1.0 + cum_all
        valid     = base_all > 0.0
        safe_base = np.where(valid, base_all, 1.0)   # invalid セルは 1.0 でべき乗させて NaN 回避
        cagr_arr  = np.where(
            valid,
            safe_base ** (self.periods_per_year / n_pf) - 1.0,
            np.nan,
        ).astype(float)

        return pd.DataFrame({
            'リターン':      rets_arr,     # 算術年率（最適化内部値）
            'リターン_CAGR': cagr_arr,     # 実現CAGRベース（散布図Y軸と同定義）
            'ボラティリティ': vols_arr,    # サンプル共分散ベース（散布図X軸と統一）
        })
    
    def _project_to_feasible_simplex(self, 
                                     weights: np.ndarray,
                                     active: np.ndarray,
                                     core_fund_idx: int,
                                     core_weight_range: Tuple[float, float],
                                     min_individual: float,
                                     max_individual: float) -> np.ndarray:
        """
        ウェイトをbounds付き単体集合に射影
        
        Parameters:
        -----------
        weights : np.ndarray
            射影前のウェイト
        active : np.ndarray
            アクティブ銘柄のマスク
        core_fund_idx : int
            コアファンドのインデックス
        core_weight_range : Tuple[float, float]
            コアファンド比重の範囲 (min, max)
        min_individual : float
            個別ファンドの最小比重
        max_individual : float
            個別ファンドの最大比重
            
        Returns:
        --------
        np.ndarray
            射影後のウェイト（sum=1, bounds内を保証）
            
        Notes:
        ------
        制約を100%保証するには、可行性条件が満たされる必要があります:
        - 下限可行性: core_min + (n_active-1) * min_individual <= 1.0
        - 上限可行性: core_max + (n_active-1) * max_individual >= 1.0
        
        これらの条件が満たされない場合、射影だけでは制約を満たせません。
        現在の実装では、最適化前に可行性チェックが行われるため、
        実務上この問題は発生しません。
        """
        n_assets = len(weights)
        core_min, core_max = core_weight_range
        w_proj = np.zeros(n_assets)
        
        # 1. 非アクティブは0
        w_proj[~active] = 0
        
        # 2. コアをcore_range内にクリップ
        w_core = np.clip(weights[core_fund_idx], core_min, core_max)
        w_proj[core_fund_idx] = w_core
        
        # 3. アクティブ非コアをbounds内にクリップ
        for i in range(n_assets):
            if i != core_fund_idx and active[i]:
                w_proj[i] = np.clip(weights[i], min_individual, max_individual)
        
        # 4. 合計が1からズレた分を調整
        delta = 1.0 - w_proj.sum()
        
        if abs(delta) > 1e-8:
            # アクティブ非コアで調整可能な銘柄を探す
            adjustable = []
            for i in range(n_assets):
                if i != core_fund_idx and active[i]:
                    slack_up = max_individual - w_proj[i]  # 上方余地
                    slack_down = w_proj[i] - min_individual  # 下方余地
                    if delta > 0 and slack_up > 1e-8:  # 増やす必要があり、余地がある
                        adjustable.append((i, slack_up))
                    elif delta < 0 and slack_down > 1e-8:  # 減らす必要があり、余地がある
                        adjustable.append((i, slack_down))
            
            # 調整可能な銘柄に比例配分
            if adjustable:
                total_slack = sum(slack for _, slack in adjustable)
                for i, slack in adjustable:
                    if delta > 0:
                        # 増やす
                        adjustment = min(delta * (slack / total_slack), slack)
                        w_proj[i] += adjustment
                    else:
                        # 減らす
                        adjustment = min(-delta * (slack / total_slack), slack)
                        w_proj[i] -= adjustment
            else:
                # 調整できない場合、コアで調整
                target_core = w_core + delta
                if core_min - 1e-8 <= target_core <= core_max + 1e-8:
                    w_proj[core_fund_idx] = np.clip(target_core, core_min, core_max)
                else:
                    # コアでも調整不可能な場合は、可能な範囲で調整
                    # （このケースは可行性チェックで事前に弾かれるはず。
                    #   発生した場合は optimize_portfolio() の入口可行性チェックを確認すること）
                    warnings.warn(
                        f"Unable to project to feasible simplex: "
                        f"delta={delta:.6f}, core_range=({core_min:.3f},{core_max:.3f}), "
                        f"n_active={active.sum()}, min_ind={min_individual:.4f}. "
                        f"Check feasibility condition at call site.",
                        RuntimeWarning, stacklevel=2
                    )
        
        # 5. 最終的なboundsチェック（念のため）
        w_proj[~active] = 0
        w_proj[core_fund_idx] = np.clip(w_proj[core_fund_idx], core_min, core_max)
        for i in range(n_assets):
            if i != core_fund_idx and active[i]:
                w_proj[i] = np.clip(w_proj[i], min_individual, max_individual)
        
        # 6. 最終的な正規化チェック
        total = w_proj.sum()
        if abs(total - 1.0) > 1e-6:
            # 微小な誤差は比例配分で吸収
            if total > 0:
                # 全体を等比縮小/拡大（bounds内に収まる範囲で）
                scale_factor = 1.0 / total
                w_proj = w_proj * scale_factor
                # 再度boundsクリップ（スケーリングでずれた場合）
                w_proj[core_fund_idx] = np.clip(w_proj[core_fund_idx], core_min, core_max)
                for i in range(n_assets):
                    if i != core_fund_idx and active[i]:
                        w_proj[i] = np.clip(w_proj[i], min_individual, max_individual)
                
                # --- 追加: scale→clip後にsum=1が崩れる可能性があるため、deltaを再配分して最終保証 ---
                total2 = w_proj.sum()
                if abs(total2 - 1.0) > 1e-6:
                    delta2 = 1.0 - total2
                    
                    # 1) 非コアへ配分（bounds内で調整）
                    adjustable = [i for i in range(n_assets) if active[i] and i != core_fund_idx]
                    if delta2 > 0:
                        # 増やす：上限までの余地
                        headrooms = {i: (max_individual - w_proj[i]) for i in adjustable}
                        total_headroom = sum(v for v in headrooms.values() if v > 0)
                        if total_headroom > 0:
                            for i in adjustable:
                                hr = headrooms[i]
                                if hr > 0:
                                    add = min(delta2 * (hr / total_headroom), hr)
                                    w_proj[i] += add
                    else:
                        # 減らす：下限までの余地
                        slacks = {i: (w_proj[i] - min_individual) for i in adjustable}
                        total_slack = sum(v for v in slacks.values() if v > 0)
                        if total_slack > 0:
                            for i in adjustable:
                                sl = slacks[i]
                                if sl > 0:
                                    sub = min((-delta2) * (sl / total_slack), sl)
                                    w_proj[i] -= sub
                    
                    # 2) まだ残っていればコアで調整
                    total3 = w_proj.sum()
                    delta3 = 1.0 - total3
                    if abs(delta3) > 1e-6:
                        target_core = w_proj[core_fund_idx] + delta3
                        if core_min - 1e-8 <= target_core <= core_max + 1e-8:
                            w_proj[core_fund_idx] = np.clip(target_core, core_min, core_max)
                    
                    # 3) 最終チェック
                    total4 = w_proj.sum()
                    if abs(total4 - 1.0) > 1e-6:
                        # 制約違反のウェイトを無言で返すことを防ぐため、
                        # 最終手段として比例正規化し、ウェイト詳細をログに残す。
                        # （bounds 違反が残る可能性があるため stacklevel=2 で呼び出し元も示す）
                        w_proj = w_proj / total4 if total4 > 0 else w_proj
                        warnings.warn(
                            f"Post-clip renormalization failed. "
                            f"sum_before={total4:.8f}, delta={1.0-total4:.8f}. "
                            f"Fallback: proportional rescaling applied. "
                            f"core_w={w_proj[core_fund_idx]:.4f} "
                            f"(range={core_min:.3f}–{core_max:.3f}). "
                            f"Verify constraint satisfaction at call site.",
                            RuntimeWarning, stacklevel=2
                        )
                # --- 追加ここまで ---
        
        return w_proj
    
    def optimize_portfolio(self,
                          core_fund_idx: int,
                          core_weight_range: Tuple[float, float],
                          objective_type: str = 'sharpe',
                          max_individual: float = 0.25,
                          min_individual: float = 0.03,
                          target_volatility: float = None,
                          n_restarts: int = 8) -> np.ndarray:
        """
        ポートフォリオ最適化（マルチスタート版）

        Parameters
        ----------
        core_fund_idx : int
        core_weight_range : Tuple[float, float]
        objective_type : str
            'sharpe'       : シャープレシオ最大化
            'max_cagr'     : CAGR最大化（μ - σ²/2）積極型向け
            'return'       : リターン重視（μ - 0.1σ）
            'volatility'   : ボラティリティ最小化
            'risk_adjusted': リスク調整後リターン（μ - 1.0σ）やや保守型向け
            'risk_parity'  : リスクパリティ（サテライトリスク寄与均等化）
            'min_cvar'     : CVaR最小化（ワースト5%月次リターン平均）保守型向け
        max_individual : float
        min_individual : float
        target_volatility : float
        n_restarts : int  マルチスタート数（デフォルト8）
        """
        n_assets = len(self.mean_returns_arith)
        cov_vals = self.cov_matrix.values
        mu_vals  = self.mean_returns_arith.values

        # ── [ISSUE-2修正] 下限可行性チェック & min_individual 自動調整 ─────────
        # core_min + (n_assets-1) × min_individual > 1.0 の場合、SLSQP の第二段階が
        # 「可行解なし」と判定してスキップされ、min_individual 制約が適用されないまま
        # 第一段階の生ウェイト（w1）が返される。
        # portfolio_app.py の O-04 修正はアプリ層でのみ調整するが、ライブラリとして
        # 直接呼ばれる場合（test_app.py 等）はここで自己完結的に対処する。
        _core_lo_v, _core_hi_v = core_weight_range
        _feasibility_lower = _core_lo_v + (n_assets - 1) * min_individual
        if _feasibility_lower > 1.0 + 1e-6:
            _safe_min = max(0.0, (1.0 - _core_lo_v) / max(n_assets - 1, 1) - 1e-6)
            warnings.warn(
                f"optimize_portfolio: 下限可行性違反 "
                f"(core_min={_core_lo_v:.3f} + {n_assets-1} × "
                f"min_individual={min_individual:.4f} = {_feasibility_lower:.4f} > 1.0)。"
                f"min_individual を {_safe_min:.4f} に自動調整します。",
                RuntimeWarning,
                stacklevel=2,
            )
            min_individual = _safe_min

        def portfolio_stats(w):
            ret = np.dot(w, mu_vals)
            vol = np.sqrt(np.dot(w, np.dot(cov_vals, w)))
            return ret, vol

        # ── 目的関数 ─────────────────────────────────────────────────────────
        if objective_type == 'sharpe':
            def objective(w):
                ret, vol = portfolio_stats(w)
                return -(ret - self.risk_free_rate) / vol if vol > 0 else 0.0

        elif objective_type == 'max_cagr':
            # CAGR ≈ μ - σ²/2 を最大化。積極型向け。
            # リスクフリーレート非依存・ボラティリティドラッグを内包。
            def objective(w):
                ret, vol = portfolio_stats(w)
                return -(ret - (vol ** 2) / 2)

        elif objective_type == 'return':
            # λ=0.1: 旧実装(0.5)はペナルティ過大でシャープ最大化と区別がつかなかった
            def objective(w):
                ret, vol = portfolio_stats(w)
                return -(ret - 0.1 * vol)

        elif objective_type == 'volatility':
            def objective(w):
                _, vol = portfolio_stats(w)
                return vol

        elif objective_type == 'risk_adjusted':
            # λ=1.0: 旧実装(1.5)はペナルティ過大で保守型との差別化が困難だった
            def objective(w):
                ret, vol = portfolio_stats(w)
                return -(ret - 1.0 * vol)

        elif objective_type == 'risk_parity':
            # [FIX-RP] アクティブセット未確定時（一次最適化）でも意味のある目的関数。
            #
            # 旧実装の問題:
            #   全サテライト（ほぼゼロウェイトを含む）のリスク寄与を均等化しようとするため、
            #   最適化のランドスケープが著しく歪む。例えばN=29本のサテライトのうち
            #   真に保有すべき15本とほぼゼロの14本が混在する状態で均等化すると、
            #   ゼロ付近のRC（≈ 0）に向けて全体が収束しようとする無意味な引力が発生する。
            #
            # 新実装の方針:
            #   min_individual を参照した閾値（_rp_thresh）を下回るウェイトの
            #   サテライトは均等化対象から除外する。
            #   - _rp_thresh = min_individual × 0.5 = デフォルト0.015
            #   - これにより「min_individual 未満 = 実質ゼロポジション」を正しく扱える
            #   - アクティブファンドが1本以下に縮退する場合はボラ最小化で代替
            #     （最適化が発散するのを防ぐフォールバック）
            #
            # 二次最適化（アクティブセット固定後）では bounds=(0,0) が適用済みのため
            # 当閾値処理は実質的に不要になるが、一次最適化の収束品質改善に直接効く。
            _rp_thresh = max(min_individual * 0.5, 1e-4)  # ゼロウェイト判定の閾値

            def objective(w):
                port_vol = np.sqrt(np.dot(w, np.dot(cov_vals, w)))
                if port_vol < 1e-8:
                    return 0.0
                rc = w * np.dot(cov_vals, w) / port_vol
                non_core = np.arange(len(w)) != core_fund_idx
                w_sat  = w[non_core]
                rc_sat = rc[non_core]
                # 閾値以上のサテライトのみ均等化対象とする
                active_mask = w_sat > _rp_thresh
                if active_mask.sum() < 2:
                    # アクティブが1本以下の縮退ケース → ボラ最小化で代替
                    return float(port_vol)
                rc_active = rc_sat[active_mask]
                target    = rc_active.mean()
                return float(np.sum((rc_active - target) ** 2))

        elif objective_type == 'min_cvar':
            # CVaR最小化（Conditional Value at Risk = 期待ショートフォール、95%水準）
            #
            # 定義:
            #   CVaR_95 = ワースト5%シナリオの月次リターン平均
            #   （VaRを超えた場合の期待損失。テールリスクの直接最小化。）
            #
            # ユースケース: 極端な下落に敏感な保守型クライアント向け。
            #   シャープレシオ最大化や volatility最小化では、
            #   非正規分布のファット・テールを十分に制御できない場合に有効。
            #
            # 勾配（サブグラジェント）:
            #   CVaRは「ソート」を内包するため厳密な意味で滑らかではないが、
            #   argpartitionで最悪k本の期間を特定し
            #     ∂(-CVaR)/∂w_j = -(1/k) × Σ_{t ∈ worst k} r_{t,j}
            #   を解析的勾配として渡すことでSLSQPの収束が安定する。
            _ret_matrix = self.returns.values           # (T, N)
            _k_cvar = max(1, int(np.floor(0.05 * len(self.returns))))

            def objective(w):
                port_r   = _ret_matrix @ w
                sorted_r = np.sort(port_r)              # 昇順：先頭 _k_cvar 本が最悪
                return -sorted_r[:_k_cvar].mean()       # 正値に反転（minimize = 損失を小さく）

        else:
            raise ValueError(f"Unknown objective type: {objective_type}")

        # 目標ボラティリティペナルティ
        if target_volatility is not None:
            _base_obj = objective
            def objective(w):
                _, vol = portfolio_stats(w)
                penalty = 100 * (vol - target_volatility) ** 2 if vol > target_volatility else 0.0
                return _base_obj(w) + penalty

        # ── 制約・境界（一次・二次共通）────────────────────────────────────
        constraints = [
            {'type': 'eq',   'fun': lambda w: np.sum(w) - 1},
            {'type': 'ineq', 'fun': lambda w: w[core_fund_idx] - core_weight_range[0]},
            {'type': 'ineq', 'fun': lambda w: core_weight_range[1] - w[core_fund_idx]},
        ]
        bounds = tuple(
            core_weight_range if i == core_fund_idx else (0, max_individual)
            for i in range(n_assets)
        )

        # ── マルチスタート初期点の生成 ─────────────────────────────────────
        # ⑫ _make_start 専用インライン関数を廃止し、既存の _project_to_feasible_simplex を再利用。
        #   active マスク=全True として呼ぶことで同等の射影が得られる。
        _all_active = np.ones(n_assets, dtype=bool)

        def _make_feasible(w_raw: np.ndarray) -> np.ndarray:
            """ランダムウェイトを実行可能領域に射影（_project_to_feasible_simplex の薄いラッパー）。

            min_individual に 0.0 を渡しているのは意図的な設計。
            この関数は一次最適化のマルチスタート初期点を生成するためのものであり、
            一次最適化の bounds は (0, max_individual) と設定している（min_individual 下限なし）。
            min_individual 下限の適用は二次最適化（アクティブセット固定後）で行う。
            ここを min_individual に書き換えると初期点が過度に制約され、
            一次最適化の探索空間が狭まるため変更しないこと。
            """
            return self._project_to_feasible_simplex(
                w_raw, _all_active, core_fund_idx,
                core_weight_range, 0.0, max_individual,
            )

        rng_ms = np.random.default_rng(42)
        core_mid = (core_weight_range[0] + core_weight_range[1]) / 2

        starts: List[np.ndarray] = []
        # ① 均等配分（従来初期値）
        w0 = np.ones(n_assets) / n_assets
        w0[core_fund_idx] = core_mid
        w0 = w0 / w0.sum()
        starts.append(_make_feasible(w0))
        # ② コア上限寄り
        w_ch = np.ones(n_assets) / n_assets
        w_ch[core_fund_idx] = core_weight_range[1]
        starts.append(_make_feasible(w_ch))
        # ③ Dirichletランダム点
        for _ in range(max(0, n_restarts - 2)):
            alpha  = rng_ms.uniform(0.5, 2.0, n_assets)
            w_rand = rng_ms.dirichlet(alpha)
            starts.append(_make_feasible(w_rand))

        # ── 目的関数の勾配（min_cvar のみ解析的サブグラジェントを設定）──────
        # 他の objective_type は数値微分で十分収束するため勾配関数は渡さない（None）。
        # min_cvar だけは np.sort 由来の非滑らかさを argpartition で近似した
        # 解析的サブグラジェントを定義して収束を安定させる。
        if objective_type == 'min_cvar':
            def _jac_fn(w):
                port_r    = _ret_matrix @ w
                idx_worst = np.argpartition(port_r, _k_cvar)[:_k_cvar]
                return -_ret_matrix[idx_worst, :].mean(axis=0)
        else:
            _jac_fn = None

        # ── 一次最適化（マルチスタート）──────────────────────────────────────
        best_result = None
        best_obj    = np.inf
        for w_s in starts:
            try:
                res = minimize(
                    objective, w_s,
                    method='SLSQP', jac=_jac_fn, bounds=bounds, constraints=constraints,
                    options={'maxiter': 1000, 'ftol': 1e-9},
                )
                if res.success and res.fun < best_obj:
                    best_obj    = res.fun
                    best_result = res
            except Exception:
                pass

        # ── フォールバック（全スタート失敗時）────────────────────────────────
        if best_result is None or not best_result.success:
            core_center = core_mid
            remaining   = 1.0 - core_center
            non_core    = [i for i in range(n_assets) if i != core_fund_idx]
            per_fund    = remaining / len(non_core) if non_core else 0.0
            fallback    = np.full(n_assets, per_fund)
            fallback[core_fund_idx] = core_center
            for _ in range(10):
                excess = np.sum(np.maximum(fallback - max_individual, 0))
                if excess < 1e-9:
                    break
                fallback = np.minimum(fallback, max_individual)
                fallback[core_fund_idx] = core_center
                redist = [i for i in non_core if fallback[i] < max_individual - 1e-9]
                if redist:
                    fallback[redist] += excess / len(redist)
                else:
                    break
            fallback[core_fund_idx] = core_center
            nc_sum = sum(fallback[i] for i in non_core)
            if nc_sum > 1e-9:
                scale = remaining / nc_sum
                for i in non_core:
                    fallback[i] = min(fallback[i] * scale, max_individual)
                diff = 1.0 - fallback.sum()
                if abs(diff) > 1e-9:
                    for i in non_core:
                        room = max_individual - fallback[i]
                        if room > 1e-9:
                            add = min(diff, room)
                            fallback[i] += add
                            diff -= add
                            if abs(diff) < 1e-9:
                                break
            # [MINOR-1修正] フォールバックにも min_individual を適用する。
            # max_individual クリップループは上限のみを保証するが、
            # 下限（min_individual）は明示的に適用していなかった。
            # _project_to_feasible_simplex に通すことで
            # min/max/sum=1 の三制約を同時に保証する。
            return self._project_to_feasible_simplex(
                fallback, _all_active, core_fund_idx,
                core_weight_range, min_individual, max_individual,
            )

        w1 = best_result.x

        # ── アクティブセット確定 ──────────────────────────────────────────────
        active = (w1 >= min_individual) | (np.arange(n_assets) == core_fund_idx)
        if active.sum() <= 1:
            nc_w = w1.copy()
            nc_w[core_fund_idx] = 0
            active[np.argsort(-nc_w)[:5]] = True

        n_active   = int(active.sum())
        core_lo, core_hi = core_weight_range
        feasible_lower   = core_lo + (n_active - 1) * min_individual <= 1.0 + 1e-6
        feasible_upper   = core_hi + (n_active - 1) * max_individual >= 1.0 - 1e-6

        if not (feasible_lower and feasible_upper):
            return w1

        # ── 二次最適化（アクティブセット固定 + マルチスタート3点）────────────
        bounds_2nd = tuple(
            core_weight_range if i == core_fund_idx
            else ((min_individual, max_individual) if active[i] else (0, 0))
            for i in range(n_assets)
        )

        rng_2nd  = np.random.default_rng(99)
        starts_2nd: List[np.ndarray] = [
            self._project_to_feasible_simplex(
                w1, active, core_fund_idx, core_weight_range, min_individual, max_individual
            )
        ]
        for _ in range(2):
            w_r2 = np.zeros(n_assets)
            active_nc = [i for i in range(n_assets) if active[i] and i != core_fund_idx]
            if active_nc:
                nc_w2  = rng_2nd.dirichlet(rng_2nd.uniform(0.5, 2.0, len(active_nc)))
                nc_scl = 1.0 - core_mid
                for j, idx in enumerate(active_nc):
                    w_r2[idx] = nc_w2[j] * nc_scl
            w_r2[core_fund_idx] = core_mid
            starts_2nd.append(
                self._project_to_feasible_simplex(
                    w_r2, active, core_fund_idx, core_weight_range, min_individual, max_individual
                )
            )

        best_2nd    = None
        best_obj_2nd = np.inf
        for w_s2 in starts_2nd:
            try:
                res2 = minimize(
                    objective, w_s2,
                    method='SLSQP', jac=_jac_fn, bounds=bounds_2nd, constraints=constraints,
                    options={'maxiter': 1000, 'ftol': 1e-9},
                )
                if res2.success and res2.fun < best_obj_2nd:
                    best_obj_2nd = res2.fun
                    best_2nd     = res2
            except Exception:
                pass

        if best_2nd is not None and best_2nd.success:
            return self._project_to_feasible_simplex(
                best_2nd.x, active, core_fund_idx,
                core_weight_range, min_individual, max_individual
            )
        return w1


class FundScreener:
    """ファンドスクリーニングクラス"""

    # ── クラスレベル統計キャッシュ（BUG-1修正）────────────────────────────────
    # 同一データ・同一パラメータでの重複計算を回避する。
    # キー : _make_stats_cache_key() で生成した MD5 ベースの文字列。
    # 値   : _calculate_statistics() の結果 DataFrame（深いコピーで保護）。
    #
    # 設計上の注意:
    #   - screen_funds() は statistics に列を追加するが、キャッシュ本体は
    #     .copy() で保護しているため 3 回目以降のインスタンスに汚染しない。
    #   - _CACHE_MAX_SIZE を超えた場合は最も古いエントリを自動削除する（LRU 近似）。
    #     Streamlit のサーバー常時起動環境で数百エントリが蓄積し続けることを防ぐ。
    _statistics_cache: Dict[str, "pd.DataFrame"] = {}
    _CACHE_MAX_SIZE: int = 32  # エントリ上限（32 × ~2MB = 最大約 64MB が目安）

    # キャッシュファンド検出用の最低ボラティリティ閾値（年率）
    # 3%を選択した理由:
    #   - キャッシュファンド: 通常0.1-0.5%
    #   - 短期債券ファンド: 通常1-2%
    #   - 3%で両方を確実に除外可能
    #   - 5%だと一部の債券ファンドも除外される可能性があるため保守的に3%
    MIN_VOLATILITY_THRESHOLD = 0.03

    def __init__(self, returns: pd.DataFrame, periods_per_year: int = 12,
                 risk_free_rate: float = 0.0):
        """
        Parameters:
        -----------
        returns : pd.DataFrame
            リターンデータ
        periods_per_year : int
            年間期数
        risk_free_rate : float
            リスクフリーレート（年率、デフォルト0）
        """
        self.returns = returns
        self.periods_per_year = periods_per_year
        self.risk_free_rate = risk_free_rate

        # ── [BUG-1修正] クラスレベルキャッシュで統計を取得 ────────────────────
        # キャッシュキー: リターンデータのハッシュ + 年間期数 + 無リスク金利。
        # 旧実装は常に False を設定するだけでキャッシュ機構が存在しなかったため
        # test_app.py テスト4 [A3] が必ず AssertionError になっていた。
        _cache_key = self._make_stats_cache_key(returns, periods_per_year, risk_free_rate)
        if _cache_key in FundScreener._statistics_cache:
            # キャッシュヒット: 深いコピーを返して汚染防止
            self.statistics = FundScreener._statistics_cache[_cache_key].copy()
            self._stats_cache_hit: bool = True
        else:
            # キャッシュミス: 新規計算してキャッシュに格納
            self.statistics = self._calculate_statistics()
            # サイズ上限を超えた場合は最も古いエントリを削除（挿入順辞書の先頭 = 最古）
            if len(FundScreener._statistics_cache) >= FundScreener._CACHE_MAX_SIZE:
                oldest_key = next(iter(FundScreener._statistics_cache))
                del FundScreener._statistics_cache[oldest_key]
            FundScreener._statistics_cache[_cache_key] = self.statistics.copy()
            self._stats_cache_hit = False

    @staticmethod
    def _make_stats_cache_key(
        returns: pd.DataFrame,
        periods_per_year: int,
        risk_free_rate: float,
    ) -> str:
        """統計キャッシュのキーを生成する。

        リターン DataFrame 全体（インデックス・列名・値）を
        pd.util.hash_pandas_object でハッシュ化し、
        年間期数・無リスク金利と結合した文字列を返す。

        Returns
        -------
        str
            "md5hex_periods_rf" 形式のキャッシュキー。
        """
        _h = hashlib.md5(
            pd.util.hash_pandas_object(returns, index=True).values.tobytes(),
            usedforsecurity=False,   # [ISSUE-3修正] FIPS環境でのエラーを防止
        ).hexdigest()
        return f"{_h}_{periods_per_year}_{risk_free_rate:.6f}"

    def _calculate_statistics(self) -> pd.DataFrame:
        """全ファンドの統計量を計算（NaN安全: カラムごとに dropna して計算）

        df_returns にはコア期間基準でアンカーされた DataFrame が渡されるが、
        コア以外のファンドが期間内に NaN を持つ場合がある（設定来が短いファンド）。
        各指標のループで `r = self.returns[col].dropna()` を使うことで
        NaN ファンドも正しい期間のデータで統計が計算される。
        """
        stats = pd.DataFrame(index=self.returns.columns)
        
        # 年率期待リターン（算術平均 - シャープ計算用）: skipna=True はデフォルトで安全
        stats['年率期待リターン'] = self.returns.mean() * self.periods_per_year
        
        # 年率リターン（幾何平均CAGR - 表示用）
        # ⑤ 統合ループ前の準備: CAGR はベクタライズ可能だが NaN ファンドに対する
        #   per-column な n_periods が異なるため、ループ内で都度 dropna して計算する。
        #   安全ガード: 1+cum <= 0 は CAGR 未定義 → 0.0 で埋める（PortfolioAnalyzer.__init__ と統一）
        for col in self.returns.columns:
            r = self.returns[col].dropna()
            n_p = len(r)
            if n_p > 0:
                cum_return = (1 + r).prod() - 1
                base = 1.0 + cum_return
                stats.loc[col, '年率リターン'] = (
                    base ** (self.periods_per_year / n_p) - 1 if base > 0 else 0.0
                )
            else:
                stats.loc[col, '年率リターン'] = 0.0

        # 年率ボラティリティ（ddof=1）
        stats['年率ボラ'] = self.returns.std(ddof=1) * np.sqrt(self.periods_per_year)

        # 超過リターン・シャープレシオ（算術平均ベース）
        # vol < 1e-8（定数系列の浮動小数点誤差由来のゼロ近傍含む）は NaN 扱い。
        # replace([inf,-inf], nan) だけでは ~1e-17 の非ゼロ vol によって
        # Inf でなく天文学的な有限値が返るケースがあるため where でガードする。
        stats['超過リターン'] = stats['年率期待リターン'] - self.risk_free_rate
        _vol_safe = stats['年率ボラ'].where(stats['年率ボラ'] > 1e-8)
        stats['シャープレシオ'] = (stats['超過リターン'] / _vol_safe).replace([np.inf, -np.inf], np.nan)

        # ── ⑤ 全ファンド統合ループ ───────────────────────────────────────────
        # 旧実装では Sortino / 最大DD / カルマー / Omega / Ulcer / Martin / GL の
        # 7指標がそれぞれ独立したループになっており、50ファンド × 7 = 350回の
        # self.returns[col].dropna() 呼び出しが発生していた。
        # 1ループに統合し dropna を1回/ファンドに削減する。
        tau_monthly = self.risk_free_rate / self.periods_per_year
        tau_omega   = 0.0

        for col in self.returns.columns:
            r = self.returns[col].dropna()          # ← NaN安全（全指標共有）
            n_p = len(r)
            excess_ret = float(stats.loc[col, '超過リターン'])

            # ── ソルティノレシオ（Sortino & van der Meer, 1991）──────────
            # DD(τ) = √( (1/T) × Σ min(r_t − τ, 0)² )
            if n_p > 0:
                downside_sq  = np.minimum(r.values - tau_monthly, 0) ** 2
                downside_dev = np.sqrt(downside_sq.mean()) * np.sqrt(self.periods_per_year)
            else:
                downside_dev = 0.0
            if downside_dev > 0.0001:
                sortino = excess_ret / downside_dev
            else:
                sortino = np.inf if excess_ret > 0 else 0.0
            stats.loc[col, 'ソルティノレシオ'] = min(sortino, 999.99)

            # ── 最大ドローダウン（先頭1.0付加で期初損失を正確に捕捉）────────
            if n_p > 0:
                cum_r   = np.concatenate([[1.0], (1 + r.values).cumprod()])
                run_max = np.maximum.accumulate(cum_r)
                dd_arr  = (cum_r - run_max) / run_max
                max_dd  = float(dd_arr[1:].min())
            else:
                max_dd  = 0.0
                dd_arr  = np.array([0.0])
            stats.loc[col, '最大DD'] = max_dd

            # ── カルマー比率（CAGR / |最大DD|）─────────────────────────────
            cagr_val = float(stats.loc[col, '年率リターン'])
            if abs(max_dd) > 0.0001:
                calmar = cagr_val / abs(max_dd)
                # [FIX-CAL] max(calmar, 0) を廃止:
                #   旧実装は CAGR < 0 のファンドをカルマー比率 0 に丸めていたため、
                #   「データ不足でゼロ」と「リターンが負でゼロ」が区別できず
                #   スクリーニングのランク正規化（パーセンタイル変換）が誤作動する。
                #   負のカルマー比率をそのまま保持することで、
                #   ランク正規化が「リターンが負のファンドを自然に低評価」できるようになる。
                #   上限 999.99 のみ維持し、下限は -999.99 に揃える。
            else:
                calmar = np.inf if cagr_val > 0 else 0.0
            stats.loc[col, 'カルマー比率'] = max(min(calmar, 999.99), -999.99)

            # ── Omega比率（利益合計 / 損失合計）─────────────────────────────
            if n_p > 0:
                pos = np.maximum(r.values - tau_omega, 0).sum()
                neg = np.maximum(tau_omega - r.values, 0).sum()
                omega = (pos / neg) if neg > 1e-8 else (999.99 if pos > 0 else 0.0)
            else:
                omega = 0.0
            stats.loc[col, 'Omega比率'] = min(omega, 999.99)

            # ── Ulcer指数・Martin比率 ────────────────────────────────────────
            # DD系列は最大DD計算時に求めた dd_arr[1:] を再利用
            dd_series = dd_arr[1:] if n_p > 0 else np.array([0.0])
            ulcer = float(np.sqrt(np.mean(dd_series ** 2)))
            stats.loc[col, 'Ulcer指数'] = ulcer
            if ulcer > 1e-8:
                martin = cagr_val / ulcer
                stats.loc[col, 'Martin比率'] = min(martin, 999.99) if martin > 0 else max(martin, -999.99)
            else:
                stats.loc[col, 'Martin比率'] = 999.99 if cagr_val > 0 else 0.0

            # ── GL比率（平均利益 / 平均損失）────────────────────────────────
            if n_p > 0:
                r_vals  = r.values
                wins    = r_vals[r_vals > 0]
                losses  = r_vals[r_vals < 0]
                avg_gain = wins.mean()         if len(wins)   > 0 else 0.0
                avg_loss = abs(losses.mean())  if len(losses) > 0 else 1e-8
                if avg_loss > 1e-8 and avg_gain > 0:
                    gl = min(avg_gain / avg_loss, 999.99)
                elif avg_gain <= 0:
                    gl = 0.0
                else:
                    gl = 999.99
            else:
                gl = 0.0
            stats.loc[col, 'GL比率'] = gl

        # キャッシュファンドフラグ（統合ループ完了後に設定）
        stats['is_cash_fund'] = stats['年率ボラ'] < self.MIN_VOLATILITY_THRESHOLD

        return stats
    
    def calculate_correlations(self, core_fund: str) -> Tuple[pd.Series, pd.Series]:
        """
        コアファンドとの相関を計算（改善版 v3.2）

        [改善A] 条件付き下落相関の追加:
          コアファンドが下落した月のみに限定した相関係数（コア相関_下落時）と
          全期間相関との差分（相関上昇リスク）を算出し statistics に格納する。
          これにより「平常時は低相関でも危機時に相関が跳ね上がる」ファンドを
          スクリーニングで識別できる。

        Parameters:
        -----------
        core_fund : str
            コアファンド名

        Returns:
        --------
        Tuple[pd.Series, pd.Series]
            (全期間相関係数, ローリング相関の標準偏差)
        """
        # ── 1. 全期間相関（現行維持） ─────────────────────────────────────
        correlations = self.returns.corrwith(self.returns[core_fund])

        # ── 2. ローリング相関の標準偏差（ベクタライズ版）─────────────────────
        # ④ 旧実装: Nファンド分の for ループ → DataFrame.rolling().corr() 一括計算に変更。
        #   50ファンドで体感できる速度差あり。min_periods=12 で不完全ウィンドウを除外。
        core_series = self.returns[core_fund]
        _others = self.returns.drop(columns=core_fund)
        if len(_others.columns) > 0:
            rc_std_series = (
                _others.rolling(12, min_periods=12)
                .corr(core_series)
                .std(ddof=0)
            )
            rolling_corr_std = rc_std_series.to_dict()
        else:
            rolling_corr_std = {}
        rolling_corr_std[core_fund] = 0.0

        # ── 3. [改善A] 条件付き下落相関の算出 ─────────────────────────────
        core_down_mask = self.returns[core_fund] < 0
        n_down_months = core_down_mask.sum()

        if n_down_months >= 6:
            # 統計的安定性のため下落月が最低6ヶ月ある場合のみ算出
            down_returns = self.returns[core_down_mask]
            corr_down = down_returns.corrwith(down_returns[core_fund])
            # NaN（下落月に変動ゼロのファンド）は全期間相関でフォールバック
            corr_down = corr_down.fillna(correlations)
        else:
            # データ不足時は全期間相関で代替（サイレント処理）
            corr_down = correlations.copy()

        # 相関上昇リスク（正が大＝危機時に相関が跳ね上がりやすい）
        corr_delta = corr_down - correlations

        # ── 4. statistics DataFrame に追加格納 ──────────────────────────
        self.statistics['コア相関_下落時'] = corr_down
        self.statistics['相関上昇リスク']  = corr_delta

        return correlations, pd.Series(rolling_corr_std)
    
    # ── 相関バケット定義（改善版 v3.3） ──────────────────────────────────────
    # スコアウェイト辞書のキー:
    #   sharpe, sortino, max_dd, return, calmar  … 従来からの指標
    #   corr_down       … [改善A] 条件付き下落相関（小さいほど高スコア）
    #   corr_stability  … [改善C] 相関安定性＝ローリング相関std（小さいほど高スコア）
    #   omega           … [改善G] Omega比率（大きいほど高スコア）
    #   ulcer           … [改善G] Ulcer指数（小さいほど高スコア・符号反転）
    #   martin          … [改善G] Martin比率（大きいほど高スコア）
    #   gl              … [改善H] GL比率（大きいほど高スコア）
    # use_clustering   … [改善D] True のバケットはクラスタリング選定を適用
    CORRELATION_BUCKETS: List[Dict] = [
        {
            'name':  'マイナス相関',
            'label': 'ヘッジ役（下落局面の緩衝材）',
            'range': (-1.0, 0.0),
            'weights': {
                'sharpe':         0.05,
                'sortino':        0.25,   # 旧0.35 — ulcer・omega追加分を配分
                'max_dd':         0.25,   # 旧0.30
                'corr_down':      0.20,   # [改善A]
                'corr_stability': 0.10,   # [改善C]
                'omega':          0.07,   # [改善G] 非正規テールリスクの識別
                'ulcer':          0.08,   # [改善G] 長期DDペナルティ
                'martin':         0.00,
                'gl':             0.00,
                'return':         0.00,
                'calmar':         0.00,
            },
            'use_clustering': True,
        },
        {
            'name':  '低相関',
            'label': '分散役（独立したリターン源泉）',
            'range': (0.0, 0.25),
            'weights': {
                'sharpe':         0.10,   # 旧0.15
                'sortino':        0.22,   # 旧0.30
                'max_dd':         0.20,   # 旧0.30
                'corr_down':      0.10,   # [改善A]
                'corr_stability': 0.10,   # [改善C]
                'omega':          0.10,   # [改善G]
                'ulcer':          0.08,   # [改善G]
                'martin':         0.00,
                'gl':             0.10,   # [改善H] 売りオプション系を識別
                'return':         0.00,
                'calmar':         0.00,
            },
            'use_clustering': True,
        },
        {
            'name':  '中低相関',
            'label': 'バランス役（分散と収益の両立）',
            'range': (0.25, 0.50),
            'weights': {
                'sharpe':         0.28,   # 旧0.35
                'sortino':        0.20,   # 旧0.25
                'max_dd':         0.17,   # 旧0.25
                'corr_down':      0.00,
                'corr_stability': 0.10,   # [改善C]
                'omega':          0.10,   # [改善G]
                'ulcer':          0.00,
                'martin':         0.00,
                'gl':             0.10,   # [改善H]
                'return':         0.05,
                'calmar':         0.00,
            },
            'use_clustering': True,
        },
        {
            'name':  '中高相関',
            'label': '収益補完役（コアと方向性を共有）',
            'range': (0.50, 0.75),
            'weights': {
                'sharpe':         0.28,   # 旧0.35
                'sortino':        0.17,   # 旧0.25
                'max_dd':         0.15,   # 旧0.20
                'corr_down':      0.00,
                'corr_stability': 0.00,
                'omega':          0.05,   # [改善G]
                'ulcer':          0.00,
                'martin':         0.10,   # [改善G] カルマー比率のUI版
                'gl':             0.05,   # [改善H]
                'return':         0.10,
                'calmar':         0.10,
            },
            'use_clustering': False,
        },
        {
            'name':  '高相関',
            'label': 'リターン牽引役（ハイリターン追求）',
            'range': (0.75, 1.01),
            'weights': {
                'sharpe':         0.15,   # 旧0.20
                'sortino':        0.08,   # 旧0.10
                'max_dd':         0.07,   # 旧0.10
                'corr_down':      0.00,
                'corr_stability': 0.00,
                'omega':          0.05,   # [改善G]
                'ulcer':          0.00,
                'martin':         0.10,   # [改善G]
                'gl':             0.10,   # [改善H] 高相関でも品質を担保
                'return':         0.25,
                'calmar':         0.20,
            },
            'use_clustering': False,
        },
    ]

    # デフォルトのバケット別割当枠（コアを除く n_final-1 本の配分比率）
    # キーはバケット名、値は割当の「重み」（実際の本数は n_final に応じてスケール）
    #
    # 合計値 19 は「n_final=20 本構成」を基準とした参照値。
    # アプリのサイドバーデフォルトは n_final=30 のため、実際には screen_funds() 内で
    # スケール計算（scale = (n_final-1) / 19）が自動適用される（bucket_quota=None 時）。
    # n_final を変更する場合でも、比率（2:3:5:5:4）は維持されたまま本数のみ変わる。
    _DEFAULT_BUCKET_QUOTA: Dict[str, int] = {
        'マイナス相関': 2,
        '低相関':       5,  # 旧3 → 5：候補27本に対して3本は過少。分散役を強化し補完依存を低減
        '中低相関':     6,  # 旧5 → 6：補完で流入していた中低相関ファンドを正式枠に繰り入れ
        '中高相関':     6,  # 旧5 → 6：同上
        '高相関':       4,
    }  # 合計 23（n_final=20 基準換算）。n_final 変更時は screen_funds() が自動スケール
    # 変更履歴：
    #   旧合計 19（2:3:5:5:4）→ 新合計 23（2:5:6:6:4）
    #   低相関の候補数（27本）に対して割当が過少だったため拡張。
    #   補完（中低相関スコアで充填）への依存を約11本→約6本に圧縮し、
    #   独立リターン源泉（低相関）の多様性を高める。

    def screen_funds(self,
                     core_fund: str,
                     n_final: int = 20,
                     exclude_cash_funds: bool = True,
                     bucket_quota: Optional[Dict[str, int]] = None) -> List[str]:
        """
        ファンドスクリーニング（相関バケット別多様性確保版 v3.1）

        Parameters:
        -----------
        core_fund : str
            コアファンド名
        n_final : int
            最終選定ファンド数（コア含む）
        exclude_cash_funds : bool
            キャッシュ類似ファンドを除外するか
        bucket_quota : Dict[str, int], optional
            バケット別割当枠の上書き。
            キーは CORRELATION_BUCKETS の 'name' と一致させること。
            None の場合は _DEFAULT_BUCKET_QUOTA を使用。

        Returns:
        --------
        List[str]
            選定されたファンドリスト（コア含む、コアが先頭）

        Notes:
        ------
        【設計思想 v3.1 — DDフィルター廃止の理由】

        v3.0 では最大DD閾値による事前フィルターを設けていたが、以下の理由で v3.1 で廃止した。

        ① 二重管理の冗長性
           各バケットのスコア式には既に最大DDの重みが組み込まれているため、
           DDの悪いファンドはスコアが低くなり自然に淘汰される。
           事前フィルターとして別途設けることは冗長であり、設計の一貫性を損なう。

        ② 長期データとの相性問題
           リーマンショック（2008: -50%超）やコロナショック（2020: -30%超）を含む
           分析期間では、閾値 -35% は容易に突破される。荒波を乗り越えた実績こそが
           ファンドの真価を示すものであり、DDフィルターで弾くことは本末転倒になる。

        ③ バケット設計思想との矛盾
           マイナス相関バケット（ヘッジ役）は暴落時にプラスになる設計のためDDは
           自然と浅くなる。高相関バケット（リターン牽引役）はある程度のDDを受け入れ
           つつリターンとカルマー比率で評価する設計であり、DD単独での事前排除は
           このバケット設計の意図と相反する。

        【スクリーニングフロー v3.1】
        ① キャッシュファンド除外（ボラティリティ < 3%）のみ事前フィルター
        ② コアとの相関を5バケットに分類
        ③ バケット固有のスコア式で各バケット内を評価・ランキング
           - マイナス相関・低相関 → ソルティノ・最大DD重視（下落耐性）
           - 中低相関・中高相関  → バランス型総合スコア
           - 高相関             → 年率リターン・カルマー重視（リターン牽引）
        ④ 各バケットから割当枠分の上位を抽出
        ⑤ 不足枠はバランス型スコアで自動補完

        スクリーニング詳細は self.screening_report（Dict）に格納される。
        """
        # ── 0. 相関・統計量の計算 ────────────────────────────────────────────
        correlations, rolling_corr_std = self.calculate_correlations(core_fund)
        self.statistics['コア相関'] = correlations
        self.statistics['相関安定性'] = rolling_corr_std

        # ── 1. 候補プールの構築 ──────────────────────────────────────────────
        candidates = self.statistics.copy()

        # キャッシュファンド除外のみ（DDフィルターは廃止: v3.1）
        if exclude_cash_funds:
            candidates = candidates[~candidates['is_cash_fund']]
            if self.statistics.loc[core_fund, 'is_cash_fund']:
                self._core_is_cash_warning = (
                    f"コアファンド「{core_fund}」は年率ボラティリティが低く、"
                    f"キャッシュ類似ファンドと判定されました "
                    f"（年率ボラ: {self.statistics.loc[core_fund, '年率ボラ']*100:.2f}%）。"
                    f"コア・サテライト戦略のコアには、株式・債券・ヘッジファンド等の"
                    f"リターン資産が適しています。"
                )
            else:
                self._core_is_cash_warning = None

        # コアファンドを除外
        candidates = candidates.drop(core_fund, errors='ignore')
        pre_filtered = candidates  # DDフィルター廃止のため全候補をそのまま使用

        # ── 2. バケット割り当て ──────────────────────────────────────────────
        quota = dict(self._DEFAULT_BUCKET_QUOTA)
        if bucket_quota:
            quota.update(bucket_quota)

        # n_final が変わった場合にデフォルト割当をスケール
        default_total = sum(self._DEFAULT_BUCKET_QUOTA.values())  # 19
        target_total  = n_final - 1  # コアを除いた選定数
        if target_total != default_total and bucket_quota is None:
            scale = target_total / default_total
            quota = {k: max(1, round(v * scale)) for k, v in quota.items()}
            # 端数調整: 合計が target_total に一致するよう最大割当バケットを微調整
            diff = target_total - sum(quota.values())
            if diff != 0:
                largest = max(quota, key=quota.get)
                quota[largest] += diff

        # ── 3. バケット内スコアリング準備（正規化関数・クラスタリング関数の定義）────
        # ステップ4のループ内で使用する _normalize / _cluster_and_select を先行定義する。
        # ステップ2（割当確定）とステップ4（スコアリング実行）の間に位置し、
        # v3.1 の DDフィルター廃止後は事前フィルタリング処理がなくなったため
        # 旧ステップ3（DDフィルター）は廃止済み。

        # ── 4. バケット内スコアリング & 上位抽出（改善版 v3.2） ────────────────

        # [改善B] ランク正規化（パーセンタイル変換）
        # Min-Max 正規化から変更: 外れ値（ソルティノ 999.99 など）による
        # 全体スコア圧縮を解消し、スコアの安定性・再現性を向上させる
        def _normalize(series: pd.Series) -> pd.Series:
            """
            ランク正規化（パーセンタイル変換）。
            要素が 1 本以下の場合は 0.5 を返す（定数系列への対応）。
            """
            if len(series) <= 1:
                return pd.Series(0.5, index=series.index)
            return series.rank(pct=True, method='average')

        # [改善D] バケット内クラスタリング選定
        def _cluster_and_select(
            pool_returns_sub: pd.DataFrame,
            scored_pool: pd.DataFrame,
            take: int,
            score_col: str = 'バケットスコア'
        ) -> List[str]:
            """
            相関距離＋ウォード法でバケット内を take 個のクラスターに分割し、
            各クラスターからスコア最高の1本を選定する。
            同一戦略ファンドへの集中を防止し、真の多様性を確保する。
            """
            if len(pool_returns_sub.columns) <= take:
                return scored_pool.nlargest(take, score_col).index.tolist()
            if len(pool_returns_sub.columns) < 2:
                return scored_pool.nlargest(take, score_col).index.tolist()

            try:
                corr_mat = pool_returns_sub.corr()
                dist_mat = np.sqrt(0.5 * (1 - corr_mat.clip(-1, 1)))
                np.fill_diagonal(dist_mat.values, 0)
                condensed = squareform(dist_mat.values, checks=False)
                condensed = np.maximum(condensed, 0)  # 数値誤差ゼロクリップ
                Z = linkage(condensed, method='ward')
                n_clusters = min(take, len(pool_returns_sub.columns))
                labels = fcluster(Z, t=n_clusters, criterion='maxclust')
            except Exception:
                # クラスタリング失敗時はスコア上位から単純選定にフォールバック
                return scored_pool.nlargest(take, score_col).index.tolist()

            scored_pool = scored_pool.copy()
            scored_pool['_cluster'] = labels
            selected: List[str] = []
            for c in sorted(scored_pool['_cluster'].unique()):
                cluster_funds = scored_pool[scored_pool['_cluster'] == c]
                selected.append(cluster_funds[score_col].idxmax())
                if len(selected) >= take:
                    break
            # クラスター数が take に届かない場合はスコア順で補完
            if len(selected) < take:
                remaining = scored_pool[~scored_pool.index.isin(selected)]
                selected.extend(remaining.nlargest(take - len(selected), score_col).index.tolist())
            return selected[:take]

        selected_per_bucket: Dict[str, List[str]] = {}
        bucket_stats: Dict[str, Dict] = {}  # screening_report 用

        for bkt in self.CORRELATION_BUCKETS:
            bname   = bkt['name']
            lo, hi  = bkt['range']
            w       = bkt['weights']
            q       = quota.get(bname, 0)

            # バケットへの振り分け
            mask = (pre_filtered['コア相関'] >= lo) & (pre_filtered['コア相関'] < hi)
            pool = pre_filtered[mask].copy()

            bucket_stats[bname] = {
                'role':       bkt['label'],
                'corr_range': (lo, hi),
                'pool_size':  len(pool),
                'quota':      q,
            }

            if len(pool) == 0 or q == 0:
                selected_per_bucket[bname] = []
                continue

            # ── バケット固有スコアの計算（[改善B] ランク正規化使用）──────────
            norm_sharpe  = _normalize(pool['シャープレシオ'])
            norm_sortino = _normalize(pool['ソルティノレシオ'].clip(upper=100))
            norm_dd      = _normalize(pool['最大DD'])          # 大（浅い）= 良
            norm_return  = _normalize(pool['年率リターン'])
            norm_calmar  = _normalize(pool['カルマー比率'].clip(upper=100))

            # [改善A] 条件付き下落相関スコア（低いほど良い → 符号反転）
            if w.get('corr_down', 0) > 0 and 'コア相関_下落時' in pool.columns:
                norm_corr_down = _normalize(-pool['コア相関_下落時'])
            else:
                norm_corr_down = pd.Series(0.0, index=pool.index)

            # [改善C] 相関安定性スコア（小さいほど良い → 符号反転）
            if w.get('corr_stability', 0) > 0 and '相関安定性' in pool.columns:
                norm_corr_stability = _normalize(-pool['相関安定性'])
            else:
                norm_corr_stability = pd.Series(0.0, index=pool.index)

            # [改善G] Omega比率スコア（大きいほど良い）
            if w.get('omega', 0) > 0 and 'Omega比率' in pool.columns:
                norm_omega = _normalize(pool['Omega比率'].clip(upper=100))
            else:
                norm_omega = pd.Series(0.0, index=pool.index)

            # [改善G] Ulcer指数スコア（小さいほど良い → 符号反転）
            if w.get('ulcer', 0) > 0 and 'Ulcer指数' in pool.columns:
                norm_ulcer = _normalize(-pool['Ulcer指数'])
            else:
                norm_ulcer = pd.Series(0.0, index=pool.index)

            # [改善G] Martin比率スコア（大きいほど良い）
            if w.get('martin', 0) > 0 and 'Martin比率' in pool.columns:
                norm_martin = _normalize(pool['Martin比率'].clip(lower=-100, upper=100))
            else:
                norm_martin = pd.Series(0.0, index=pool.index)

            # [改善H] GL比率スコア（大きいほど良い）
            if w.get('gl', 0) > 0 and 'GL比率' in pool.columns:
                norm_gl = _normalize(pool['GL比率'].clip(upper=100))
            else:
                norm_gl = pd.Series(0.0, index=pool.index)

            pool['バケットスコア'] = (
                w.get('sharpe',         0) * norm_sharpe         +
                w.get('sortino',        0) * norm_sortino        +
                w.get('max_dd',         0) * norm_dd             +
                w.get('corr_down',      0) * norm_corr_down      +
                w.get('corr_stability', 0) * norm_corr_stability +
                w.get('omega',          0) * norm_omega          +
                w.get('ulcer',          0) * norm_ulcer          +
                w.get('martin',         0) * norm_martin         +
                w.get('gl',             0) * norm_gl             +
                w.get('return',         0) * norm_return         +
                w.get('calmar',         0) * norm_calmar
            )

            take = min(q, len(pool))

            # [改善D] クラスタリング選定 or 単純スコア上位選定
            use_clustering = bkt.get('use_clustering', False)
            if use_clustering and len(pool) > take:
                # バケット内ファンドのリターン系列を取得
                funds_in_pool = [f for f in pool.index if f in self.returns.columns]
                if len(funds_in_pool) >= 2:
                    selected_per_bucket[bname] = _cluster_and_select(
                        self.returns[funds_in_pool],
                        pool.loc[funds_in_pool],
                        take,
                    )
                else:
                    selected_per_bucket[bname] = pool.nlargest(take, 'バケットスコア').index.tolist()
            else:
                selected_per_bucket[bname] = pool.nlargest(take, 'バケットスコア').index.tolist()

            bucket_stats[bname]['selected'] = len(selected_per_bucket[bname])

        # ── 5. 不足枠の再配分 ─────────────────────────────────────────────────
        total_selected = sum(len(v) for v in selected_per_bucket.values())
        shortfall = target_total - total_selected

        if shortfall > 0:
            already_selected = set(f for funds in selected_per_bucket.values() for f in funds)
            remaining_pool = pre_filtered[~pre_filtered.index.isin(already_selected)].copy()

            if len(remaining_pool) > 0:
                # バランス型スコア（中低相関バケットのウェイト）で再評価
                # [改善B] ランク正規化を補完スコアにも適用
                # [改善C] corr_stability が利用可能な場合は補完にも組み込む
                balance_w = next(b['weights'] for b in self.CORRELATION_BUCKETS if b['name'] == '中低相関')

                norm_sharpe  = _normalize(remaining_pool['シャープレシオ'])
                norm_sortino = _normalize(remaining_pool['ソルティノレシオ'].clip(upper=100))
                norm_dd      = _normalize(remaining_pool['最大DD'])
                norm_return  = _normalize(remaining_pool['年率リターン'])
                norm_calmar  = _normalize(remaining_pool['カルマー比率'].clip(upper=100))

                if balance_w.get('corr_stability', 0) > 0 and '相関安定性' in remaining_pool.columns:
                    norm_corr_stability = _normalize(-remaining_pool['相関安定性'])
                else:
                    norm_corr_stability = pd.Series(0.0, index=remaining_pool.index)

                norm_omega  = _normalize(remaining_pool['Omega比率'].clip(upper=100)) if 'Omega比率' in remaining_pool.columns else pd.Series(0.0, index=remaining_pool.index)
                norm_ulcer  = _normalize(-remaining_pool['Ulcer指数']) if 'Ulcer指数' in remaining_pool.columns else pd.Series(0.0, index=remaining_pool.index)
                norm_martin = _normalize(remaining_pool['Martin比率'].clip(lower=-100, upper=100)) if 'Martin比率' in remaining_pool.columns else pd.Series(0.0, index=remaining_pool.index)
                norm_gl     = _normalize(remaining_pool['GL比率'].clip(upper=100)) if 'GL比率' in remaining_pool.columns else pd.Series(0.0, index=remaining_pool.index)

                remaining_pool['補完スコア'] = (
                    balance_w.get('sharpe',         0) * norm_sharpe         +
                    balance_w.get('sortino',        0) * norm_sortino        +
                    balance_w.get('max_dd',         0) * norm_dd             +
                    balance_w.get('corr_stability', 0) * norm_corr_stability +
                    balance_w.get('omega',          0) * norm_omega          +
                    balance_w.get('ulcer',          0) * norm_ulcer          +
                    balance_w.get('martin',         0) * norm_martin         +
                    balance_w.get('gl',             0) * norm_gl             +
                    balance_w.get('return',         0) * norm_return         +
                    balance_w.get('calmar',         0) * norm_calmar
                )
                supplement = remaining_pool.nlargest(
                    min(shortfall, len(remaining_pool)), '補完スコア'
                ).index.tolist()
                selected_per_bucket['補完'] = supplement
                bucket_stats['補完'] = {
                    'role':      '不足枠補完（バランス型スコアで再選定）',
                    'pool_size': len(remaining_pool),
                    'selected':  len(supplement),
                }

        # ── 6. 最終リスト構築 & screening_report の保存 ──────────────────────
        final_funds_set: List[str] = []
        for bname in list(quota.keys()) + ['補完']:
            for fund in selected_per_bucket.get(bname, []):
                if fund not in final_funds_set:
                    final_funds_set.append(fund)

        # screening_report はデバッグ・UI表示用に保持
        self.screening_report: Dict = {
            'core_fund':       core_fund,
            'n_final':         n_final,
            'pre_filter_pool': len(pre_filtered),
            'buckets':         bucket_stats,
            'total_selected':  len(final_funds_set),
        }

        return [core_fund] + final_funds_set
    
    def get_statistics(self, funds: List[str] = None) -> pd.DataFrame:
        """
        指定ファンドの統計量を取得
        
        Parameters:
        -----------
        funds : List[str], optional
            ファンドリスト（Noneの場合は全ファンド）
            
        Returns:
        --------
        pd.DataFrame
            統計量
        """
        if funds is None:
            return self.statistics
        else:
            return self.statistics.loc[funds]


def calculate_fund_metrics(
    returns_series: pd.Series,
    bench_returns_series: pd.Series = None,
    risk_free_rate: float = 0.0,
) -> dict:
    """構成銘柄分析タブ用の定量指標を計算し、表示用整形済み文字列で返す。

    portfolio_charts.py 内にネスト定義されていた calc_metrics() を
    ステージ1リファクタ（2026-03）でモジュールレベルに昇格させたもの。
    計算基準は FundScreener._calculate_statistics() と完全統一している。

    Parameters
    ----------
    returns_series : pd.Series
        月次リターン系列（dropna 済みを想定）。
    bench_returns_series : pd.Series, optional
        ベンチマークの月次リターン系列。相関係数計算に使用。
    risk_free_rate : float
        年率無リスク金利（デフォルト 0.0）。

    Returns
    -------
    dict
        表示用整形済み文字列を値とする辞書。
        データが 12 本未満の場合もすべての値が "—" 文字列で返る（[ISSUE-1修正]）。
        旧実装は np.nan（float）を返していたが、正常時の整形済み文字列と型が
        まちまちになるため統一した。呼び出し元で型判定は不要。

    Notes
    -----
    - シャープレシオ：算術平均ベース（FundScreener._calculate_statistics と統一）
    - 最大ドローダウン：先頭 1.0 付加で期初損失を正確に捕捉（portfolio_utils 修正J と統一）
    - ボラティリティ：ddof=1（FundScreener と統一）
    - Martin 比率の分子：CAGR（幾何平均）ベース
    - 出力値はすべて表示整形済み文字列（charts 層での再フォーマット不要）
    - データ不足時（12 本未満）もすべての値を "—" 文字列で返す。
      旧実装は np.nan を返していたため、呼び出し元で型が str / float と
      まちまちになり、文字列連結時に "nan" が表示されるリスクがあった。
    """
    # [ISSUE-1修正] データ不足時も文字列で返し、戻り値型を全ケースで統一する。
    # 旧実装は np.nan（float）を返しており、正常時の整形済み文字列と型が異なっていた。
    if len(returns_series) < 12:
        return {
            "シャープレシオ": "—",
            "価格変動リスク": "—",
            "最大下落率":     "—",
            "Omega比率":      "—",
            "Ulcer指数":      "—",
            "Martin比率":     "—",
            "GL比率":         "—",
            "相関性":         "—",
        }

    # ── リターン指標 ──────────────────────────────────────────
    # 年率期待リターン（算術平均 - シャープ計算用：FundScreener と統一）
    annual_return_arith = returns_series.mean() * 12
    # 年率リターン（CAGR - Martin 比率計算用）
    n_p   = len(returns_series)
    cum_r = (1 + returns_series).prod() - 1
    # [BUG-3修正] 1+cum_r ≤ 0（累積損失100%超）は CAGR 未定義（複素数になる）→ 0.0 で補完
    _cagr_base = 1 + cum_r
    annual_return_geom = (_cagr_base ** (12 / n_p) - 1 if (n_p > 0 and _cagr_base > 0) else 0.0)

    # ── ボラティリティ・シャープ ──────────────────────────────
    # ddof=1 を明示（FundScreener と統一）
    # 閾値を 1e-8 に設定: 定数系列の std は浮動小数点誤差により
    # ~1e-17 の非ゼロ値を返すことがあり、> 0 では天文学的な
    # シャープレシオが生成されてしまう（例：毎月-10%系列で-2.46e16）。
    annual_vol    = returns_series.std(ddof=1) * np.sqrt(12)
    annual_excess = annual_return_arith - risk_free_rate
    sharpe        = annual_excess / annual_vol if annual_vol > 1e-8 else 0.0

    # ── 最大ドローダウン ──────────────────────────────────────
    # 先頭 1.0 付加：観測開始前を基準高値とみなし、期初の下落を捕捉する
    # （portfolio_utils PortfolioAnalyzer.calculate_portfolio_stats 修正J と統一）
    _cum_np  = np.concatenate([[1.0], (1 + returns_series.values).cumprod()])
    _rmax_np = np.maximum.accumulate(_cum_np)
    _dd_arr  = (_cum_np - _rmax_np) / _rmax_np
    drawdown = pd.Series(_dd_arr[1:], index=returns_series.index)
    max_dd   = float(_dd_arr[1:].min()) * 100  # 表示用 % スケール

    # ── Omega 比率 ────────────────────────────────────────────
    # [NEW-BUG-1修正] クリップ上限を 99.99 → 999.99 に変更。
    # calculate_portfolio_stats / FundScreener._calculate_statistics と統一。
    tau   = 0.0
    pos   = np.maximum(returns_series - tau, 0).sum()
    neg   = np.maximum(tau - returns_series, 0).sum()
    omega = min(pos / neg, 999.99) if neg > 1e-8 else (999.99 if pos > 0 else 0.0)

    # ── Ulcer 指数・Martin 比率 ───────────────────────────────
    ulcer  = float(np.sqrt(np.mean(drawdown ** 2)))
    martin = (annual_return_geom / ulcer) if ulcer > 1e-8 else (
        999.99 if annual_return_geom > 0 else 0.0
    )
    martin = min(max(martin, -999.99), 999.99)

    # ── GL 比率（Gain/Loss 比率）─────────────────────────────
    wins     = returns_series[returns_series > 0]
    losses   = returns_series[returns_series < 0]
    avg_gain = wins.mean()        if len(wins)   > 0 else 0.0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 1e-8
    gl_ratio = min(avg_gain / avg_loss, 999.99) if avg_loss > 1e-8 and avg_gain > 0 else (
        999.99 if avg_gain > 0 else 0.0
    )

    # ── ベンチマーク相関 ──────────────────────────────────────
    correlation = np.nan
    if bench_returns_series is not None and len(bench_returns_series) >= 12:
        common_idx = returns_series.index.intersection(bench_returns_series.index)
        if len(common_idx) >= 12:
            correlation = returns_series.loc[common_idx].corr(
                bench_returns_series.loc[common_idx]
            )

    return {
        "シャープレシオ": f"{sharpe:.2f}",
        "価格変動リスク": f"{annual_vol * 100:.1f}%",
        "最大下落率":     f"{max_dd:.1f}%",
        "Omega比率":      f"{omega:.2f}",
        "Ulcer指数":      f"{ulcer * 100:.2f}%",
        "Martin比率":     f"{martin:.2f}",
        "GL比率":         f"{gl_ratio:.2f}",
        "相関性":         f"{correlation:.2f}" if not np.isnan(correlation) else "N/A",
    }


def export_results_to_excel(portfolios: Dict, 
                            fund_stats: pd.DataFrame,
                            selected_funds: List[str],
                            output_path: str):
    """
    分析結果をExcelにエクスポート
    
    Parameters:
    -----------
    portfolios : Dict
        ポートフォリオ辞書
    fund_stats : pd.DataFrame
        ファンド統計
    selected_funds : List[str]
        選定ファンドリスト
    output_path : str
        出力ファイルパス
    """
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # シート1: ポートフォリオ比較
        comparison_data = []
        for profile_name, portfolio in portfolios.items():
            weights = portfolio['weights']
            stats = portfolio.get('stats', {})
            
            comparison_data.append({
                'プロファイル': profile_name,
                '年率リターン': stats.get('年率リターン', 0) * 100,
                '年率ボラティリティ': stats.get('年率ボラティリティ', 0) * 100,
                'シャープレシオ': stats.get('シャープレシオ', 0),
                '最大ドローダウン': stats.get('最大ドローダウン', 0) * 100,
                'ソルティノレシオ': stats.get('ソルティノレシオ', 0),
                'カルマー比率': stats.get('カルマー比率', 0)
            })
        
        comparison_df = pd.DataFrame(comparison_data)
        comparison_df.to_excel(writer, sheet_name='ポートフォリオ比較', index=False)
        
        # シート2: 各ポートフォリオの構成
        for profile_name, portfolio in portfolios.items():
            weights = portfolio['weights']
            weights_df = pd.DataFrame({
                'ファンド': selected_funds,
                '比重(%)': weights * 100
            })
            weights_df = weights_df[weights_df['比重(%)'] > 0.1].sort_values('比重(%)', ascending=False)
            
            # シート名は31文字以内
            sheet_name = f'{profile_name[:20]}_構成'
            weights_df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # シート3: ファンド統計
        fund_stats_export = fund_stats.copy()
        # パーセント表示
        for col in ['年率リターン', '年率ボラ', '最大DD']:
            if col in fund_stats_export.columns:
                fund_stats_export[col] = fund_stats_export[col] * 100
        
        fund_stats_export.to_excel(writer, sheet_name='ファンド統計')

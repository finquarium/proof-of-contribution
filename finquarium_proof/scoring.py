"""Trading data scoring and points calculation"""
from dataclasses import dataclass
from finquarium_proof.models.contribution import TradingStats

@dataclass
class PointsBreakdown:
    """Detailed breakdown of points awarded"""
    volume_points: int
    volume_reason: str
    diversity_points: int
    diversity_reason: str
    history_points: int
    history_reason: str
    total_points: int

class ContributionScorer:
    """Calculates points and scores for trading data contributions"""

    def calculate_volume_points(self, volume: float) -> tuple[int, str]:
        """Calculate points based on trading volume"""
        if volume >= 1_000_000:
            return 500, "500 (1M+ volume)"
        elif volume >= 100_000:
            return 150, "150 (100k+ volume)"
        elif volume >= 10_000:
            return 50, "50 (10k+ volume)"
        elif volume >= 1_000:
            return 25, "25 (1k+ volume)"
        elif volume >= 100:
            return 5, "5 (100+ volume)"
        return 1, "1 (minimum reward)"

    def calculate_diversity_points(self, unique_assets: int) -> tuple[int, str]:
        """Calculate points based on portfolio diversity"""
        if unique_assets >= 5:
            return 30, "30 (5+ assets)"
        elif unique_assets >= 3:
            return 10, "10 (3-4 assets)"
        return 0, "0 (< 3 assets)"

    def calculate_history_points(self, days: int) -> tuple[int, str]:
        """Calculate points based on trading history length"""
        if days >= 1095:  # 3 years
            return 100, "100 (3+ years)"
        elif days >= 365:  # 1 year
            return 50, "50 (1+ year)"
        return 0, "0 (< 1 year)"

    def calculate_score(self, stats: TradingStats) -> PointsBreakdown:
        """Calculate total points and provide breakdown"""
        volume_points, volume_reason = self.calculate_volume_points(stats.total_volume)
        diversity_points, diversity_reason = self.calculate_diversity_points(len(stats.unique_assets))
        history_points, history_reason = self.calculate_history_points(stats.activity_period_days)

        return PointsBreakdown(
            volume_points=volume_points,
            volume_reason=volume_reason,
            diversity_points=diversity_points,
            diversity_reason=diversity_reason,
            history_points=history_points,
            history_reason=history_reason,
            total_points=max(volume_points + diversity_points + history_points, 1)  # Ensure minimum of 1 point
        )

    def normalize_score(self, points: int, max_points: int) -> float:
        """Convert points to 0-1 score range with minimum score for 0.01 FIN"""
        min_score = 0.00000158730158730159  # This gives 0.01 FIN when multiplied by REWARD_FACTOR (630)
        raw_score = points / max_points
        return max(raw_score, min_score)  # Ensure minimum score is achieved
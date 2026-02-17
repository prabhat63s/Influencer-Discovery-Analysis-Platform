from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.services.data import influencer_dataset

logger = logging.getLogger(__name__)

_metrics_lock = threading.Lock()
_METRICS_DF: Optional[pd.DataFrame] = None


REQUIRED_COLUMNS = [
    "followers",
    "following",
    "posts",
    "average_likes",
    "average_comments",
    "suspicious_fake_followers",
    "real_followers",
    "real_percentage",
    "RATE",
    "NICHE",
    "Name",
    "PROFILE LINK",
    "CITY / STATE / BASE",
]


def _prepare_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure numeric columns are typed correctly and safe for division."""
    numeric_cols = [
        "followers",
        "following",
        "posts",
        "average_likes",
        "average_comments",
        "suspicious_fake_followers",
        "real_followers",
        "real_percentage",
        "RATE",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Avoid division by zero
    df["followers"] = df["followers"].replace(0, 1.0)
    df["following"] = df["following"].replace(0, 1.0)
    df["posts"] = df["posts"].replace(0, 1.0)
    df["average_likes"] = df["average_likes"].replace(0, 0.01)
    df["RATE"] = df["RATE"].replace(0, 0.01)
    df["real_followers"] = df["real_followers"].replace(0, 0.01)

    return df


def _calculate_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all derived metrics."""
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")

    df = _prepare_numeric(df)

    total_engagement = df["average_likes"] + df["average_comments"]

    # Engagement metrics
    # CRITICAL FIX: Preserve scraped engagement_rate if already present and valid
    # Only recalculate if missing or zero (for static CSV data)
    if "engagement_rate" in df.columns and (df["engagement_rate"] > 0).any():
        # Engagement rate already exists from scrapers (e.g., Spreadd.io) - keep it!
        # Just ensure values are valid (no NaN, etc.)
        df["engagement_rate"] = df["engagement_rate"].fillna(0.0)
        # Log that we're preserving scraped values
        logger.debug("Preserving scraped engagement_rate values from external source")
        # Cap engagement rate at 100% (can't exceed follower count)
        over_100 = df["engagement_rate"] > 100.0
        if over_100.any():
            logger.warning(
                f"Capping {over_100.sum()} engagement rate(s) from scraped data that exceed 100%"
            )
            df.loc[over_100, "engagement_rate"] = 100.0
    else:
        # No valid engagement_rate present - calculate from averages
        df["engagement_rate"] = (total_engagement / df["followers"])
        # Cap engagement rate at 100% (can't exceed follower count)
        over_100 = df["engagement_rate"] > 100.0
        if over_100.any():
            logger.warning(
                f"Capping {over_100.sum()} calculated engagement rate(s) that exceed 100% "
                f"(likely data quality issue: engagement > followers)"
            )
            df.loc[over_100, "engagement_rate"] = 100.0
    df["like_to_follower_ratio"] = (df["average_likes"] / df["followers"]) * 100
    df["comment_to_follower_ratio"] = (df["average_comments"] / df["followers"]) * 100
    df["comment_to_like_ratio"] = (df["average_comments"] / df["average_likes"]) * 100
    df["engagement_per_post"] = total_engagement / df["posts"]
    df["engagement_velocity"] = total_engagement / (df["followers"] + df["following"])

    # Authenticity metrics
    df["fake_follower_ratio"] = (df["suspicious_fake_followers"] / df["followers"]) * 100
    df["real_follower_ratio"] = (df["real_followers"] / df["followers"]) * 100
    df["fake_to_real_ratio"] = df["suspicious_fake_followers"] / df["real_followers"]
    df["authenticity_score"] = (df["real_percentage"] * 0.7) - (df["fake_follower_ratio"] * 0.3)
    df["trust_index"] = (df["real_followers"] - df["suspicious_fake_followers"]) / df["followers"]
    df["follower_quality_velocity"] = np.where(
        df["fake_follower_ratio"] > 0,
        df["real_percentage"] / df["fake_follower_ratio"],
        df["real_percentage"],
    )

    # ROI & cost metrics
    df["cost_per_follower"] = df["RATE"] / df["followers"]
    df["cost_per_1000_followers"] = df["cost_per_follower"] * 1000
    df["cost_per_engagement"] = df["RATE"] / total_engagement.replace(0, 0.01)
    df["cost_per_real_follower"] = df["RATE"] / df["real_followers"]
    df["cost_efficiency_index"] = df["cost_per_engagement"] / (df["engagement_rate"] / 100).replace(0, 0.01)
    df["roi_proxy"] = (df["engagement_rate"] / df["cost_per_engagement"])
    df["authentic_roi"] = (df["real_percentage"] / 100) * (df["engagement_rate"] / df["cost_per_engagement"])

    # Growth & behavior metrics
    df["follower_to_following_ratio"] = df["followers"] / df["following"]
    df["reciprocity_index"] = df["following"] / df["followers"]
    df["growth_saturation_index"] = df["followers"] / (df["followers"] + df["following"])
    df["activity_saturation_index"] = df["posts"] / (df["followers"] + df["following"])
    df["engagement_maturity"] = (
        (df["engagement_rate"] * df["real_percentage"]) / (df["followers"] / 1000).replace(0, 0.01)
    )

    # Content & interaction metrics
    df["comment_depth_ratio"] = df["average_comments"] / (df["average_likes"] + 1)
    df["audience_interaction_score"] = (
        ((df["average_comments"] * 2) + df["average_likes"]) / df["followers"] * 100
    )
    df["post_efficiency_score"] = total_engagement / df["posts"]
    df["engagement_to_post_density"] = df["post_efficiency_score"] / df["followers"]

    # Reach & value metrics
    df["effective_reach"] = df["followers"] * (df["engagement_rate"] / 100)
    df["effective_real_reach"] = df["real_followers"] * (df["engagement_rate"] / 100)
    df["return_on_engagement"] = df["effective_real_reach"] / df["RATE"]
    df["influence_value_score"] = (
        df["followers"] * df["real_percentage"] * df["engagement_rate"]
    ) / (df["RATE"] * 100)

    # Quality & power metrics
    df["influence_power_index"] = (
        df["followers"] * df["engagement_rate"] * df["real_percentage"]
    ) / 10000
    df["true_engagement_weighted_index"] = (total_engagement) * (df["real_percentage"] / 100)
    df["authenticity_weighted_cost_index"] = df["RATE"] / (
        (df["real_followers"] * df["engagement_rate"] / 100).replace(0, 0.01)
    )
    df["influence_efficiency_ratio"] = df["influence_power_index"] / df["RATE"]
    df["performance_to_cost_index"] = (df["engagement_rate"] * df["real_percentage"]) / df["RATE"]

    # Benchmarking metrics
    niche_stats = df.groupby("NICHE").agg(
        engagement_rate_mean=("engagement_rate", "mean"),
        engagement_rate_std=("engagement_rate", "std"),
        rate_mean=("RATE", "mean"),
    )
    df = df.join(niche_stats, on="NICHE")
    df["normalized_engagement_index"] = df["engagement_rate"] / df["engagement_rate_mean"].replace(0, 0.01)
    df["normalized_cost_index"] = df["RATE"] / df["rate_mean"].replace(0, 0.01)
    df["niche_performance_ratio"] = df["normalized_engagement_index"] / df["normalized_cost_index"].replace(
        0, 0.01
    )

    if "CITY / STATE / BASE" in df.columns:
        city_stats = df.groupby("CITY / STATE / BASE").agg(city_eng_mean=("engagement_rate", "mean"))
        df = df.join(city_stats, on="CITY / STATE / BASE")
        df["location_advantage_index"] = df["engagement_rate"] / df["city_eng_mean"].replace(0, 0.01)

    niche_efficiency = df.groupby("NICHE").agg(
        engagement_rate_mean_ce=("engagement_rate", "mean"),
        rate_mean_ce=("RATE", "mean"),
    ).reset_index()
    niche_efficiency["category_efficiency"] = niche_efficiency["engagement_rate_mean_ce"] / niche_efficiency[
        "rate_mean_ce"
    ].replace(0, 0.01)
    niche_efficiency = niche_efficiency[["NICHE", "category_efficiency"]]
    df = df.merge(niche_efficiency, on="NICHE", how="left")

    # Fraud & anomaly metrics
    df["consistency_index"] = total_engagement / df["followers"]
    df["fake_engagement_index"] = (df["fake_follower_ratio"] * df["engagement_rate"]) / 100
    low_ratio_penalty = (df["follower_to_following_ratio"] < 1).astype(int) * 20
    low_engagement_penalty = (df["engagement_rate"] < 0.5).astype(int) * 30
    df["bot_probability"] = (df["fake_follower_ratio"] + low_ratio_penalty + low_engagement_penalty) / 1.5
    df["post_engagement_imbalance"] = abs(df["engagement_per_post"] - df["engagement_per_post"].mean())
    df["engagement_deviation_index"] = np.where(
        df["engagement_rate_std"] > 0,
        (df["engagement_rate"] - df["engagement_rate_mean"]) / df["engagement_rate_std"],
        0,
    )

    # Composite scores
    df["influencer_quality_score"] = (
        (df["engagement_rate"] * 0.4) + (df["real_percentage"] * 0.4) - (df["fake_follower_ratio"] * 0.2)
    )
    df["true_engagement_score"] = df["engagement_rate"] * (df["real_percentage"] / 100)
    df["health_score"] = (
        (df["engagement_rate"] * 0.3)
        + (df["real_percentage"] * 0.3)
        + ((1 - df["fake_follower_ratio"] / 100) * 0.2)
        + (df["follower_to_following_ratio"] * 0.2)
    ).clip(0, 100)
    df["authenticity_engagement_index"] = (df["real_percentage"] * df["engagement_rate"]) / 100
    df["influence_stability_ratio"] = np.where(
        df["fake_follower_ratio"] > 0,
        (df["real_percentage"] / df["fake_follower_ratio"]) * df["follower_to_following_ratio"],
        df["real_percentage"] * df["follower_to_following_ratio"],
    )
    df["true_influence_index"] = (
        (df["authenticity_engagement_index"] * np.log1p(df["followers"])) / df["RATE"]
    )
    df["campaign_roi_score"] = (
        (df["authentic_roi"] / df["authentic_roi"].replace(0, np.nan).mean()) * 100
    ).replace([np.inf, -np.inf, np.nan], 0)

    return df


def _ensure_metrics_loaded() -> pd.DataFrame:
    global _METRICS_DF
    if _METRICS_DF is not None:
        return _METRICS_DF

    with _metrics_lock:
        if _METRICS_DF is not None:
            return _METRICS_DF

        base_df = influencer_dataset.get_dataset()
        metrics_df = _calculate_metrics(base_df.copy(deep=True))
        _METRICS_DF = metrics_df
        return metrics_df


def refresh_metrics() -> None:
    """Force reload of the dataset and recompute metrics."""
    global _METRICS_DF
    with _metrics_lock:
        base_df = influencer_dataset.refresh_dataset()
        _METRICS_DF = _calculate_metrics(base_df.copy(deep=True))


def get_metrics(limit: Optional[int] = None) -> List[Dict[str, float]]:
    """Return metrics records as list of dictionaries."""
    df = _ensure_metrics_loaded()
    if limit is not None and limit > 0:
        df = df.head(limit)
    return df.replace({np.nan: None}).to_dict(orient="records")


def get_summary() -> Dict[str, float]:
    """Return summary statistics of key metrics."""
    df = _ensure_metrics_loaded()
    return summarize_metrics_dataframe(df)


def calculate_metrics_from_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Public helper to calculate metrics from an arbitrary dataframe."""
    return _calculate_metrics(df.copy(deep=True))


def summarize_metrics_dataframe(df: pd.DataFrame) -> Dict[str, float]:
    """Summarize metrics from a dataframe."""
    if df.empty:
        return {
            "total_influencers": 0,
            "avg_engagement_rate": 0.0,
            "avg_authenticity_score": 0.0,
            "avg_health_score": 0.0,
            "avg_fake_follower_ratio": 0.0,
            "avg_cost_per_engagement": 0.0,
            "top_niche_by_engagement": "",
            "top_niche_by_quality": "",
        }

    summary = {
        "total_influencers": int(len(df)),
        "avg_engagement_rate": float(df["engagement_rate"].mean()),
        "avg_authenticity_score": float(df["authenticity_score"].mean()),
        "avg_health_score": float(df["health_score"].mean()),
        "avg_fake_follower_ratio": float(df["fake_follower_ratio"].mean()),
        "avg_cost_per_engagement": float(df["cost_per_engagement"].mean()),
        "top_niche_by_engagement": str(
            df.groupby("NICHE")["engagement_rate"].mean().idxmax() if not df.empty else ""
        ),
        "top_niche_by_quality": str(
            df.groupby("NICHE")["influencer_quality_score"].mean().idxmax() if not df.empty else ""
        ),
    }
    return summary


def get_metrics_dataframe() -> pd.DataFrame:
    """Return a copy of the metrics dataframe."""
    return _ensure_metrics_loaded().copy(deep=True)


def get_metrics_map_by_profile_link(fields: Optional[List[str]] = None) -> Dict[str, Dict[str, float]]:
    """Return metrics keyed by normalized profile link."""
    df = _ensure_metrics_loaded()
    metrics_fields = fields or [
        "engagement_rate",
        "authenticity_score",
        "health_score",
        "influencer_quality_score",
        "true_influence_index",
        "campaign_roi_score",
    ]

    mapping: Dict[str, Dict[str, float]] = {}
    if "PROFILE LINK" not in df.columns:
        return mapping

    for _, row in df.iterrows():
        key = str(row["PROFILE LINK"]).strip().lower()
        if not key:
            continue
        metrics = {}
        for field in metrics_fields:
            if field in row:
                value = row[field]
                metrics[field] = float(value) if pd.notna(value) else None
        mapping[key] = metrics
    return mapping

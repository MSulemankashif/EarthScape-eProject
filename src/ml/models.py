"""
Machine learning models for climate analytics
=============================================
Implements the "Machine Learning Models" functional requirement:

  * AnomalyDetectionModel   - Isolation Forest over multivariate readings
  * TrendPredictionModel    - linear/seasonal trend forecast per metric
  * CorrelationAnalyzer     - Pearson correlation matrix between climate
                              variables (with significance ranking)

Models are trained on demand, persisted with joblib under data/models/ and
exposed through a single `ClimateModelRegistry` used by the web dashboard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

from src.config import MODELS_DIR
from src.utils.logger import get_logger

log = get_logger("earthscape.ml")

METRICS = ["temperature_c", "humidity_pct", "rainfall_mm", "co2_ppm",
           "pm25", "wind_speed_kph", "sea_level_mm"]


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------
@dataclass
class AnomalyDetectionModel:
    """Isolation-Forest based climate anomaly detector."""

    contamination: float = 0.02
    random_state: int = 42
    model: IsolationForest | None = field(default=None, repr=False)
    scaler: StandardScaler | None = field(default=None, repr=False)
    features: list[str] = field(default_factory=lambda: list(METRICS))

    def train(self, df: pd.DataFrame) -> "AnomalyDetectionModel":
        data = self._prepare(df)
        self.scaler = StandardScaler()
        scaled = self.scaler.fit_transform(data)
        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(scaled)
        log.info("Anomaly model trained on %d readings (%d features)",
                 len(data), len(self.features))
        return self

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in self.features if c in df.columns]
        if not cols:
            raise ValueError("No usable feature columns found for anomaly model")
        data = df[cols].apply(pd.to_numeric, errors="coerce")
        # Median imputation keeps rows with partial missing data usable
        data = data.fillna(data.median(numeric_only=True))
        self.features = cols
        return data

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return the input rows annotated with is_anomaly & anomaly_score."""
        if self.model is None:
            raise RuntimeError("Model is not trained. Call train() first.")
        data = self._prepare(df)
        scaled = self.scaler.transform(data)
        scores = self.model.decision_function(scaled)
        labels = self.model.predict(scaled)  # -1 anomaly, 1 normal

        out = df.copy().reset_index(drop=True)
        out["anomaly_score"] = np.round(-scores, 4)
        out["is_anomaly"] = labels == -1
        n_anom = int(out["is_anomaly"].sum())
        log.info("Anomaly prediction: %d / %d flagged", n_anom, len(out))
        return out

    def save(self, path: Path | None = None) -> Path:
        path = path or (MODELS_DIR / "anomaly_model.joblib")
        joblib.dump({"model": self.model, "scaler": self.scaler,
                     "features": self.features}, path)
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "AnomalyDetectionModel":
        path = path or (MODELS_DIR / "anomaly_model.joblib")
        blob = joblib.load(path)
        obj = cls()
        obj.model, obj.scaler, obj.features = (blob["model"], blob["scaler"],
                                               blob["features"])
        return obj


# ---------------------------------------------------------------------------
# Trend prediction
# ---------------------------------------------------------------------------
@dataclass
class TrendPredictionModel:
    """
    Predicts future values of a climate metric.

    A linear trend is fitted over an ordinal time index plus a 365-day
    seasonal sine/cosine pair (annual cycle), which is the classic
    decomposition taught in climate-science big-data courses.
    """

    metric: str = "temperature_c"
    model: LinearRegression | None = field(default=None, repr=False)
    scaler: StandardScaler | None = field(default=None, repr=False)
    last_date: pd.Timestamp | None = None

    @staticmethod
    def _design(dates: pd.Series) -> np.ndarray:
        t = (dates - dates.min()).dt.days.to_numpy(dtype=float)
        ang = 2 * np.pi * t / 365.25
        return np.column_stack([t, np.sin(ang), np.cos(ang)])

    def train(self, df: pd.DataFrame, date_col: str = "date") -> "TrendPredictionModel":
        work = df[[date_col, self.metric]].copy()
        work[date_col] = pd.to_datetime(work[date_col])
        work[self.metric] = pd.to_numeric(work[self.metric], errors="coerce")
        work = work.dropna().sort_values(date_col)

        # Daily resample averages out noise before fitting
        daily = work.set_index(date_col).resample("D")[self.metric].mean().dropna()
        if len(daily) < 30:
            raise ValueError(f"Need >= 30 daily points to model '{self.metric}' "
                             f"(got {len(daily)})")

        X = self._design(daily.index.to_series())
        y = daily.to_numpy()

        self.scaler = StandardScaler()
        Xs = self.scaler.fit_transform(X)
        self.model = LinearRegression().fit(Xs, y)
        self.last_date = daily.index.max()

        preds = self.model.predict(Xs)
        ss_res = float(np.sum((y - preds) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
        log.info("Trend model '%s' trained: %d points, R²=%.3f, slope=%.5f C/day",
                 self.metric, len(daily), r2, self.model.coef_[0])
        self.r2 = r2
        return self

    def forecast(self, days: int = 90) -> pd.DataFrame:
        """Project the metric forward `days` days."""
        if self.model is None:
            raise RuntimeError("Model is not trained.")
        future_dates = pd.date_range(
            start=self.last_date + timedelta(days=1), periods=days, freq="D")
        X = self._design(pd.Series(future_dates))
        preds = self.model.predict(self.scaler.transform(X))
        return pd.DataFrame({"date": future_dates.date,
                             self.metric: np.round(preds, 2)})

    def summary(self) -> dict:
        """Human readable trend description for the dashboard."""
        if self.model is None:
            raise RuntimeError("Model is not trained.")
        slope = float(self.model.coef_[0])  # per-day slope in scaled space
        annual = slope * 365.25
        direction = "warming" if annual > 0 else "cooling" if annual < 0 else "stable"
        return {
            "metric": self.metric,
            "slope_per_year": round(annual, 4),
            "direction": direction,
            "r2": round(getattr(self, "r2", 0.0), 4),
            "trained_until": str(self.last_date.date()) if self.last_date else None,
        }


# ---------------------------------------------------------------------------
# Correlation analysis
# ---------------------------------------------------------------------------
@dataclass
class CorrelationAnalyzer:
    """Pearson correlation analysis across climate variables."""

    matrix: pd.DataFrame | None = field(default=None, repr=False)

    def analyze(self, df: pd.DataFrame,
                columns: Iterable[str] = METRICS) -> pd.DataFrame:
        cols = [c for c in columns if c in df.columns]
        numeric = df[cols].apply(pd.to_numeric, errors="coerce")
        self.matrix = numeric.corr(method="pearson").round(3)
        log.info("Correlation matrix computed over %d columns", len(cols))
        return self.matrix

    def top_relationships(self, k: int = 8) -> list[dict]:
        """Strongest |r| pairs, excluding self-correlations."""
        if self.matrix is None:
            raise RuntimeError("Call analyze() first.")
        pairs = []
        cols = list(self.matrix.columns)
        for i, a in enumerate(cols):
            for b in cols[i + 1:]:
                r = self.matrix.loc[a, b]
                if pd.isna(r):
                    continue
                pairs.append({
                    "variable_a": a,
                    "variable_b": b,
                    "pearson_r": float(r),
                    "strength": self._strength(r),
                    "direction": "positive" if r >= 0 else "negative",
                })
        pairs.sort(key=lambda p: abs(p["pearson_r"]), reverse=True)
        return pairs[:k]

    @staticmethod
    def _strength(r: float) -> str:
        ar = abs(r)
        if ar >= 0.8:
            return "very strong"
        if ar >= 0.6:
            return "strong"
        if ar >= 0.4:
            return "moderate"
        if ar >= 0.2:
            return "weak"
        return "negligible"


# ---------------------------------------------------------------------------
# Registry - single entry point used by the web app
# ---------------------------------------------------------------------------
class ClimateModelRegistry:
    """Train / persist / reload all climate models."""

    def __init__(self, model_dir: Path = MODELS_DIR):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.anomaly: AnomalyDetectionModel | None = None
        self.trends: dict[str, TrendPredictionModel] = {}

    # -- anomaly ------------------------------------------------------------
    def train_anomaly(self, df: pd.DataFrame,
                      contamination: float = 0.02) -> AnomalyDetectionModel:
        self.anomaly = AnomalyDetectionModel(contamination=contamination).train(df)
        self.anomaly.save(self.model_dir / "anomaly_model.joblib")
        return self.anomaly

    def load_anomaly(self) -> AnomalyDetectionModel | None:
        path = self.model_dir / "anomaly_model.joblib"
        if self.anomaly is None and path.exists():
            self.anomaly = AnomalyDetectionModel.load(path)
        return self.anomaly

    # -- trends -------------------------------------------------------------
    def train_trend(self, df: pd.DataFrame, metric: str,
                    date_col: str = "date") -> TrendPredictionModel:
        model = TrendPredictionModel(metric=metric).train(df, date_col)
        self.trends[metric] = model
        joblib.dump({"model": model.model, "scaler": model.scaler,
                     "last_date": model.last_date, "r2": model.r2},
                    self.model_dir / f"trend_{metric}.joblib")
        return model

    def load_trend(self, metric: str) -> TrendPredictionModel | None:
        if metric in self.trends:
            return self.trends[metric]
        path = self.model_dir / f"trend_{metric}.joblib"
        if not path.exists():
            return None
        blob = joblib.load(path)
        model = TrendPredictionModel(metric=metric)
        model.model, model.scaler = blob["model"], blob["scaler"]
        model.last_date, model.r2 = blob["last_date"], blob["r2"]
        self.trends[metric] = model
        return model

    # -- correlation --------------------------------------------------------
    @staticmethod
    def correlate(df: pd.DataFrame) -> dict:
        analyzer = CorrelationAnalyzer()
        matrix = analyzer.analyze(df)
        return {"matrix": matrix.to_dict(),
                "columns": list(matrix.columns),
                "top_relationships": analyzer.top_relationships()}

    # -- status -------------------------------------------------------------
    def status(self) -> dict:
        trends = {}
        for metric in METRICS:
            model = self.load_trend(metric)
            if model and model.model is not None:
                trends[metric] = model.summary()
        return {
            "anomaly_model_trained": self.anomaly is not None
                                     or (self.model_dir / "anomaly_model.joblib").exists(),
            "trend_models": trends,
            "model_dir": str(self.model_dir),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

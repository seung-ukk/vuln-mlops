"""Create a harmless statsmodels artifact for functional lab verification."""

from __future__ import annotations

import json

import mlflow
import mlflow.statsmodels
import numpy as np
import statsmodels.api as sm

from modelgate.config import get_settings


def main() -> None:
    settings = get_settings()
    mlflow.set_tracking_uri(settings.tracking_uri)
    mlflow.set_experiment("modelgate-benign-samples")

    x = sm.add_constant(np.arange(8.0))
    y = 1.5 + 2.0 * np.arange(8.0)
    model = sm.OLS(y, x).fit()

    with mlflow.start_run() as run:
        info = mlflow.statsmodels.log_model(model, name="model")
        print(
            json.dumps(
                {
                    "run_id": run.info.run_id,
                    "artifact_uri": info.model_uri,
                    "model_type": "statsmodels.OLS",
                    "safe_sample": True,
                }
            )
        )


if __name__ == "__main__":
    main()

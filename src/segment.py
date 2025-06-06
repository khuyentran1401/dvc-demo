import pickle
import warnings
from typing import Tuple

import numpy as np
import pandas as pd
from omegaconf import DictConfig
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from yellowbrick.cluster import KElbowVisualizer
import hydra
from pathlib import Path
import mlflow
from sklearn.metrics import silhouette_score
from mlflow.models import infer_signature

warnings.simplefilter(action="ignore", category=DeprecationWarning)


def read_process_data(config: DictConfig):
    return pd.read_csv(config.intermediate.path)


def get_pca_model(data: pd.DataFrame) -> PCA:
    pca = PCA(n_components=4)
    pca.fit(data)
    return pca


def reduce_dimension(df: pd.DataFrame, pca: PCA) -> pd.DataFrame:
    n_components = pca.n_components_
    columns = [f"col{i+1}" for i in range(n_components)]
    return pd.DataFrame(pca.transform(df), columns=columns)


def get_projection(pca_df: pd.DataFrame) -> dict:
    """Get projection of data in the reduced dimensionality space"""
    return {f"dim{i+1}": pca_df[col] for i, col in enumerate(pca_df.columns)}


def get_best_k_cluster(pca_df: pd.DataFrame) -> pd.DataFrame:
    elbow = KElbowVisualizer(KMeans(), metric="distortion")
    elbow.fit(pca_df)
    k_best = elbow.elbow_value_
    return k_best


def get_clusters_model(
    pca_df: pd.DataFrame, k: int
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    model = KMeans(n_clusters=k)
    return model.fit(pca_df)


def predict(model, pca_df: pd.DataFrame):
    return model.predict(pca_df)


def insert_clusters_to_df(df: pd.DataFrame, clusters: np.ndarray) -> pd.DataFrame:
    return df.assign(clusters=clusters)


def save_data_and_model(data: pd.DataFrame, model: KMeans, config: DictConfig):
    Path(config.final.path).parent.mkdir(exist_ok=True)
    data.to_csv(config.final.path, index=False)

    Path(config.model.path).parent.mkdir(exist_ok=True)
    pickle.dump(model, open(config.model.path, "wb"))


@hydra.main(config_path="../config", config_name="main", version_base="1.2")
def segment(config: DictConfig) -> None:

    # Data processing
    data = read_process_data(config)
    pca = get_pca_model(data)
    pca_df = reduce_dimension(data, pca)
    k_best = get_best_k_cluster(pca_df)
    model = get_clusters_model(pca_df, k_best)
    pred = predict(model, pca_df)
    data = insert_clusters_to_df(data, pred)
    silhouette_avg = silhouette_score(pca_df, pred)

    # Save data and model locally
    save_data_and_model(data, model, config)

    with mlflow.start_run():

        mlflow.log_params({"n_components": 3, "random_state": 42, "best_k": k_best})
        mlflow.log_metric("silhouette_score", silhouette_avg)
        signature = infer_signature(pca_df, pred)
        mlflow.sklearn.log_model(
            model, "kmeans_model", signature=signature, input_example=pca_df.head()
        )
        mlflow.log_artifact(config.final.path, "processed_data")


if __name__ == "__main__":
    segment()

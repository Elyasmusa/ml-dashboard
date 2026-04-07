import torch
import torch.nn as nn
from models.base_model import BaseMLModel


class ProductPredictorNet(nn.Module):
    """Dense multi-output regression network that predicts next-order product quantities."""

    def __init__(self, input_dim: int, output_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.BatchNorm1d(128),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.BatchNorm1d(64),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class ProductPredictor(BaseMLModel):
    """Factory that builds the ProductPredictorNet."""

    def __init__(self, input_dim: int, output_dim: int):
        self.input_dim = input_dim
        self.output_dim = output_dim

    def get_name(self) -> str:
        return "product_predictor"

    def get_description(self) -> str:
        return "Predicts next-order product quantities for each franchise location."

    def build(self) -> nn.Module:
        return ProductPredictorNet(self.input_dim, self.output_dim)

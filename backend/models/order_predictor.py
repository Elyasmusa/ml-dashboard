import torch
import torch.nn as nn
from models.base_model import BaseMLModel


class OrderPredictorNet(nn.Module):
    """Dense regression network that predicts days until the next franchise order."""

    def __init__(self, input_dim: int):
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
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class OrderPredictor(BaseMLModel):
    """Factory that builds the OrderPredictorNet."""

    def __init__(self, input_dim: int):
        self.input_dim = input_dim

    def get_name(self) -> str:
        return "order_predictor"

    def get_description(self) -> str:
        return "Predicts days until the next franchise store order based on location, products, and order date."

    def build(self) -> nn.Module:
        return OrderPredictorNet(self.input_dim)

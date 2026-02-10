from pathlib import Path
from datetime import datetime
from config import settings
from schemas.model_info import ModelInfo


class ModelRegistry:
    def list_models(self) -> list[ModelInfo]:
        model_dir = settings.model_dir
        results = []
        if model_dir.exists():
            for p in model_dir.glob("*.keras"):
                results.append(self._path_to_info(p))
            for p in model_dir.glob("*.h5"):
                results.append(self._path_to_info(p))
        return results

    def get_model(self, model_name: str) -> ModelInfo:
        model_dir = settings.model_dir
        for ext in (".keras", ".h5"):
            path = model_dir / f"{model_name}{ext}"
            if path.exists():
                return self._path_to_info(path)
        raise FileNotFoundError(f"Model '{model_name}' not found")

    @staticmethod
    def _path_to_info(path: Path) -> ModelInfo:
        stat = path.stat()
        return ModelInfo(
            name=path.stem,
            file_path=str(path),
            created_at=datetime.fromtimestamp(stat.st_mtime),
        )

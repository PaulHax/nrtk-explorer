"""
Module to load a dataset.

Example:
    dataset = get_dataset("path/to/dataset.json")
"""

from typing import Sequence as SequenceType
from functools import lru_cache
from pathlib import Path
import json
from PIL import Image
from datasets import (
    load_dataset,
    get_dataset_infos,
    Sequence,
    ClassLabel,
)


class JsonDataset:
    """Read a COCO JSON and get the image file path given an image id."""

    def __init__(self, path: str):
        with open(path) as f:
            self.data = json.load(f)
            self.fpath = path
            self.cats = {cat["id"]: cat for cat in self.data["categories"]}
            self.anns = {ann["id"]: ann for ann in self.data["annotations"]}
            self.imgs = {img["id"]: img for img in self.data["images"]}

    def get_image_fpath(self, selected_id: int):
        """Get the image file path given an image id."""
        dataset_dir = Path(self.fpath).parent
        file_name = self.imgs[selected_id]["file_name"]
        return str(dataset_dir / file_name)

    def get_image(self, id: int):
        """Get the image given an image id."""
        image_fpath = self.get_image_fpath(id)
        return Image.open(image_fpath)


def make_coco_dataset(path: str):
    try:
        import kwcoco

        class NrtkCocoDataset(kwcoco.CocoDataset):
            def get_image(self, id: int):
                """Get the image given an image id."""
                image_fpath = self.get_image_fpath(id)
                return Image.open(image_fpath)

        return NrtkCocoDataset(path)
    except ImportError:
        return JsonDataset(path)


def is_coco_dataset(path: str):
    """Check if the file is a COCO dataset JSON."""
    import os

    if not os.path.exists(path):
        return False

    required_keys = ['"images"', '"categories"', '"annotations"']
    with open(path) as f:
        content = f.read()
        return all(key in content for key in required_keys)


def expand_hugging_face_datasets(dataset_identifiers: SequenceType[str]):
    expanded_identifiers = []
    for identifier in dataset_identifiers:
        if is_coco_dataset(identifier):
            expanded_identifiers.append(identifier)
        else:
            infos = get_dataset_infos(identifier)
            for config_name, info in infos.items():
                for split_name in info.splits:
                    expanded_identifiers.append(f"{identifier}@{config_name}@{split_name}")
    return expanded_identifiers


HF_ROWS_MAX_TO_DOWNLOAD = 5000
HF_ROWS_TO_TAKE_STREAMING = 600


class HuggingFaceDataset:
    """Interface to Hugging Face Dataset with the same API as JsonDataset."""

    def __init__(self, identifier: str):
        parts = identifier.split("@")
        if len(parts) == 3:
            repo_name, selected_config_name, selected_split_name = parts
        else:
            raise ValueError("Identifier must be in the format 'dataset@config@split'")

        infos = get_dataset_infos(repo_name)
        selected_info = infos[selected_config_name]
        num_examples = selected_info.splits[selected_split_name].num_examples
        self._streaming = num_examples > HF_ROWS_MAX_TO_DOWNLOAD

        dataset = load_dataset(
            repo_name, selected_config_name, split=selected_split_name, streaming=self._streaming
        )

        if self._streaming:
            self._dataset = dataset.take(HF_ROWS_TO_TAKE_STREAMING)
        else:
            self._dataset = dataset
        self._metadata = self._dataset.remove_columns(["image"])

        imgs, row_idx_to_id, id_to_row_idx = self._load_images()
        self.imgs = imgs
        self._row_idx_to_id = row_idx_to_id
        self._id_to_row_idx = id_to_row_idx

        self.cats = self._load_categories()

        self.anns = self._load_annotations()

    def _load_images(self):
        images = {}
        row_idx_to_id = {}
        id_to_row_idx = {}
        dataset = self._dataset if self._streaming else self._metadata
        for idx, example in enumerate(dataset):
            id = example.get("id", example.get("image_id", idx))
            images[id] = {
                "id": id,
            }
            row_idx_to_id[idx] = id
            id_to_row_idx[id] = example["image"] if self._streaming else idx

        return images, row_idx_to_id, id_to_row_idx

    def get_image(self, id):
        """Get the image given an image id."""
        if self._streaming:
            return self._id_to_row_idx[id]
        row = self._id_to_row_idx[id]
        return self._dataset[row]["image"]

    def _load_categories(self):
        def extract_labels(feature):
            if isinstance(feature, ClassLabel):
                return feature.names
            if hasattr(feature, "names"):
                return feature.names
            if isinstance(feature, Sequence):
                return extract_labels(feature.feature)
            if isinstance(feature, dict):
                for key in ["category", "label"]:
                    if key in feature:
                        return extract_labels(feature[key])
            return None

        labels = None
        features = self._metadata.features

        if "labels" in features:
            labels = extract_labels(features["labels"])
        if not labels and "objects" in features:
            labels = extract_labels(features["objects"])
        if labels is None:
            return {}
        return {i: {"id": i, "name": str(name)} for i, name in enumerate(labels)}

    def _load_annotations(self):
        annotations = {}

        counter = 0

        def make_id():
            nonlocal counter
            counter += 1
            return f"ann_{counter}"

        new_cats = set()
        for idx, example in enumerate(self._metadata):
            if "objects" in example:
                objects = example["objects"]
                image_id = self._row_idx_to_id[idx]
                dataset_has_ids = True
                ids = objects.get("id", objects.get("bbox_id"))
                if ids is None:
                    ids = [make_id() for _ in range(len(objects["bbox"]))]
                    dataset_has_ids = False

                categories = objects.get("category", objects.get("label"))

                for annotation_id, bbox, category_id in zip(ids, objects["bbox"], categories):
                    if category_id not in self.cats:
                        new_cats.add(category_id)

                    annotations[annotation_id] = {
                        "id": annotation_id if dataset_has_ids else None,
                        "image_id": image_id,
                        "category_id": category_id,
                        "bbox": bbox,
                    }

        if new_cats:
            max_existing_id = max(self.cats.keys(), default=0)
            for new_cat in new_cats:
                max_existing_id += 1
                self.cats[max_existing_id] = {"id": max_existing_id, "name": str(new_cat)}
            name_to_id = {cat["name"]: cat["id"] for cat in self.cats.values()}
            for annotation in annotations.values():
                annotation["category_id"] = name_to_id[annotation["category_id"]]

        return annotations


@lru_cache
def __load_dataset(identifier: str):
    """Load the dataset."""

    absolute_path = str(Path(identifier).resolve())

    if is_coco_dataset(absolute_path):
        return make_coco_dataset(absolute_path)

    # Assume identifier is a Hugging Face Dataset
    return HuggingFaceDataset(identifier)


def get_dataset(identifier: str):
    """Get the dataset object.
    Args:
        identifier (str): Path to the dataset file or HuggingFace hub dataset identifier.
    Return:
        dataset: Dataset object.
    """
    return __load_dataset(identifier)

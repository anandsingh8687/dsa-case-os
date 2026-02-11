"""
Training pipeline for the Document Classifier ML model.
Uses TF-IDF + Logistic Regression for multi-class classification.
"""
import pandas as pd
import joblib
from pathlib import Path
from typing import Optional, Dict, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import numpy as np

from app.core.enums import DocumentType


class ClassifierTrainer:
    """Trains and evaluates the document classifier ML model."""

    def __init__(self, model_dir: Optional[Path] = None):
        """
        Initialize the trainer.

        Args:
            model_dir: Directory to save trained models (default: backend/models/)
        """
        if model_dir is None:
            backend_dir = Path(__file__).parent.parent.parent.parent
            model_dir = backend_dir / "models"

        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True, parents=True)

        self.vectorizer = None
        self.model = None

    def load_training_data(self, csv_path: str) -> Tuple[pd.DataFrame, bool]:
        """
        Load training data from CSV.

        Expected CSV format:
        - filename: Name of the document file
        - doc_type: DocumentType enum value (e.g., "aadhaar", "pan_personal")
        - text: OCR extracted text

        Args:
            csv_path: Path to the training data CSV

        Returns:
            Tuple of (DataFrame, success_flag)
        """
        try:
            df = pd.read_csv(csv_path)

            # Validate required columns
            required_cols = ["doc_type", "text"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")

            # Remove rows with empty text
            df = df[df["text"].notna() & (df["text"].str.strip() != "")]

            # Validate doc_types
            valid_types = [dt.value for dt in DocumentType]
            invalid_types = df[~df["doc_type"].isin(valid_types)]["doc_type"].unique()
            if len(invalid_types) > 0:
                print(f"⚠ Warning: Invalid doc_types found: {invalid_types}")
                df = df[df["doc_type"].isin(valid_types)]

            print(f"✓ Loaded {len(df)} training samples")
            print(f"  Document types distribution:")
            print(df["doc_type"].value_counts().to_string())

            return df, True

        except Exception as e:
            print(f"✗ Error loading training data: {e}")
            return pd.DataFrame(), False

    def train(
        self,
        training_data: pd.DataFrame,
        test_size: float = 0.2,
        random_state: int = 42,
        max_features: int = 5000,
        cross_validate: bool = True,
    ) -> Dict:
        """
        Train the classifier model.

        Args:
            training_data: DataFrame with 'text' and 'doc_type' columns
            test_size: Fraction of data to use for testing
            random_state: Random seed for reproducibility
            max_features: Maximum number of TF-IDF features
            cross_validate: Whether to perform cross-validation

        Returns:
            Dictionary with training metrics
        """
        print("=" * 60)
        print("Training Document Classifier")
        print("=" * 60)

        # Prepare data
        X = training_data["text"].values
        y = training_data["doc_type"].values

        # Split data
        # Use stratification only if we have enough samples
        n_classes = len(set(y))
        test_samples = int(len(y) * test_size)
        use_stratify = test_samples >= n_classes

        if use_stratify:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=random_state, stratify=y
            )
        else:
            print(f"⚠️  Small dataset: Using random split instead of stratified split")
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=random_state
            )

        print(f"\n📊 Data split:")
        print(f"  Training samples: {len(X_train)}")
        print(f"  Test samples: {len(X_test)}")

        # Create TF-IDF vectorizer
        print(f"\n🔧 Creating TF-IDF vectorizer (max_features={max_features})...")
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=(1, 3),  # Unigrams, bigrams, and trigrams
            min_df=2,  # Ignore terms that appear in less than 2 documents
            max_df=0.8,  # Ignore terms that appear in more than 80% of documents
            sublinear_tf=True,  # Use logarithmic TF scaling
            strip_accents="unicode",
        )

        X_train_vectorized = self.vectorizer.fit_transform(X_train)
        X_test_vectorized = self.vectorizer.transform(X_test)

        print(f"  Vocabulary size: {len(self.vectorizer.vocabulary_)}")

        # Train Logistic Regression
        print(f"\n🤖 Training Logistic Regression classifier...")
        self.model = LogisticRegression(
            max_iter=1000,
            multi_class="multinomial",
            solver="lbfgs",
            class_weight="balanced",  # Handle imbalanced classes
            random_state=random_state,
        )

        self.model.fit(X_train_vectorized, y_train)

        # Evaluate on test set
        print(f"\n📈 Evaluating on test set...")
        y_pred = self.model.predict(X_test_vectorized)
        test_accuracy = (y_pred == y_test).mean()

        print(f"  Test Accuracy: {test_accuracy:.4f}")

        # Detailed classification report
        print(f"\n📋 Classification Report:")
        print(classification_report(y_test, y_pred, zero_division=0))

        # Confusion matrix
        print(f"\n🔢 Confusion Matrix:")
        cm = confusion_matrix(y_test, y_pred)
        print(cm)

        # Cross-validation
        cv_scores = None
        if cross_validate and len(X_train) >= 10:  # Only do CV if enough samples
            # Use min(5, samples) for number of folds
            n_folds = min(5, len(X_train) // 2)
            print(f"\n🔄 Performing {n_folds}-fold cross-validation...")
            try:
                cv_scores = cross_val_score(
                    self.model, X_train_vectorized, y_train, cv=n_folds, scoring="accuracy"
                )
                print(f"  CV Accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std() * 2:.4f})")
            except ValueError as e:
                print(f"  ⚠️  Skipping CV: {e}")
        elif cross_validate:
            print(f"\n⚠️  Dataset too small for cross-validation (only {len(X_train)} training samples)")

        # Feature importance (top keywords per class)
        print(f"\n🔑 Top keywords per document type:")
        self._print_top_features(n=10)

        # Prepare metrics
        metrics = {
            "test_accuracy": float(test_accuracy),
            "training_samples": len(X_train),
            "test_samples": len(X_test),
            "vocabulary_size": len(self.vectorizer.vocabulary_),
            "classes": self.model.classes_.tolist(),
        }

        if cv_scores is not None:
            metrics["cv_accuracy_mean"] = float(cv_scores.mean())
            metrics["cv_accuracy_std"] = float(cv_scores.std())

        print(f"\n✓ Training complete!")
        return metrics

    def _print_top_features(self, n: int = 10):
        """Print top N features for each class."""
        feature_names = self.vectorizer.get_feature_names_out()

        for i, class_label in enumerate(self.model.classes_):
            # Get coefficients for this class
            coef = self.model.coef_[i]

            # Get top N features
            top_indices = np.argsort(coef)[-n:][::-1]
            top_features = [feature_names[idx] for idx in top_indices]

            print(f"  {class_label:30s}: {', '.join(top_features)}")

    def save_model(self) -> bool:
        """Save the trained model and vectorizer."""
        if self.model is None or self.vectorizer is None:
            print("✗ No model to save. Train the model first.")
            return False

        try:
            model_file = self.model_dir / "classifier_model.joblib"
            vectorizer_file = self.model_dir / "classifier_vectorizer.joblib"

            joblib.dump(self.model, model_file)
            joblib.dump(self.vectorizer, vectorizer_file)

            print(f"\n💾 Model saved to: {self.model_dir}/")
            print(f"  - {model_file.name}")
            print(f"  - {vectorizer_file.name}")

            return True

        except Exception as e:
            print(f"✗ Error saving model: {e}")
            return False

    def load_model(self) -> bool:
        """Load a previously trained model."""
        try:
            model_file = self.model_dir / "classifier_model.joblib"
            vectorizer_file = self.model_dir / "classifier_vectorizer.joblib"

            if not model_file.exists() or not vectorizer_file.exists():
                print(f"✗ Model files not found in {self.model_dir}/")
                return False

            self.model = joblib.load(model_file)
            self.vectorizer = joblib.load(vectorizer_file)

            print(f"✓ Model loaded from {self.model_dir}/")
            return True

        except Exception as e:
            print(f"✗ Error loading model: {e}")
            return False

    def evaluate_on_new_data(self, test_data: pd.DataFrame) -> Dict:
        """
        Evaluate the model on new test data.

        Args:
            test_data: DataFrame with 'text' and 'doc_type' columns

        Returns:
            Dictionary with evaluation metrics
        """
        if self.model is None or self.vectorizer is None:
            print("✗ No model loaded. Train or load a model first.")
            return {}

        X_test = test_data["text"].values
        y_test = test_data["doc_type"].values

        X_test_vectorized = self.vectorizer.transform(X_test)
        y_pred = self.model.predict(X_test_vectorized)

        accuracy = (y_pred == y_test).mean()

        print(f"\n📈 Evaluation Results:")
        print(f"  Accuracy: {accuracy:.4f}")
        print(f"\n📋 Classification Report:")
        print(classification_report(y_test, y_pred, zero_division=0))

        return {
            "accuracy": float(accuracy),
            "test_samples": len(X_test),
        }


# ─── CLI Interface ────────────────────────────────────────────────────────────

def train_from_csv(
    csv_path: str,
    model_dir: Optional[str] = None,
    test_size: float = 0.2,
    max_features: int = 5000,
) -> bool:
    """
    Convenience function to train from CSV and save the model.

    Args:
        csv_path: Path to training data CSV
        model_dir: Directory to save models
        test_size: Fraction for test split
        max_features: Max TF-IDF features

    Returns:
        True if successful
    """
    trainer = ClassifierTrainer(model_dir=Path(model_dir) if model_dir else None)

    # Load data
    df, success = trainer.load_training_data(csv_path)
    if not success or len(df) == 0:
        return False

    # Train
    metrics = trainer.train(
        training_data=df,
        test_size=test_size,
        max_features=max_features,
        cross_validate=True,
    )

    # Save
    return trainer.save_model()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python classifier_trainer.py <training_data.csv> [model_dir]")
        sys.exit(1)

    csv_path = sys.argv[1]
    model_dir = sys.argv[2] if len(sys.argv) > 2 else None

    success = train_from_csv(csv_path, model_dir)
    sys.exit(0 if success else 1)
